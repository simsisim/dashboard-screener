"""
Pattern detector — GLB / Green Line Breakout (feedback_4.md Task 5).

Source: metaData_v1/src/screeners/drwish_screener.py (params :42-48,
is_pivot_high :99-119, calculate_historical_glb_levels :149-238,
detect_glb_signals :240-313; daily timeframe). Thresholds in config.py
(GLB_*), verbatim.

Methodology:
  pivot high (strength s) — H[p] > max(H[p-s..p-1]) AND
                            H[p] >= max(H[p+1..p+s])
  GLB pivot               — a pivot whose high is the maximum of its
                            63-bar lookback window (incl. itself)
  confirmed               — no HIGH in the `confirmation` bars after the
                            pivot exceeds the level
  broken                  — some later CLOSE exceeds the level
  breakout (signal)       — the latest bar's HIGH is above the current
                            GLB level (the highest confirmed-open pivot
                            within the lookback window), pivot age >=
                            confirmation bars

INCREMENTAL CACHE (feedback_4.md requirement (b)): most of GLB's history
is immutable — a pivot older than `confirmation` bars is permanently
confirmed/rejected, and a broken level never needs rescanning. This
module keeps a per-ticker JSON cache under
results/{GLB_CACHE_DIR_NAME}/{SYMBOL}.json holding the computed records
+ the bar count they cover + a close-price fingerprint of that bar (a
split/rewrite of history invalidates the cache via fingerprint
mismatch). On each run only the NEW bars are scanned for breakouts of
open records, and only pivots near the trailing edge (not yet fully
formed when last computed) are (re)checked. A parameter change also
invalidates the cache.

The cold path is vectorized per ticker with numpy (rolling-max pivot
test, broadcast breakout scan), so even a first-ever run over a scoped
universe stays in seconds — measured in test_dashboard_app.py.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
import config


def _params_hash(params: dict) -> str:
    return str(sorted((k, round(float(v), 6) if isinstance(v, (int, float))
                       else str(v)) for k, v in params.items()))


def _cache_path(ticker: str) -> Path:
    d = config.RESULTS_DIR / config.GLB_CACHE_DIR_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d / f'{ticker.replace(".", "-")}.json'


def _load_cache(ticker: str, params_hash: str) -> dict | None:
    p = _cache_path(ticker)
    if not p.exists():
        return None
    try:
        c = json.loads(p.read_text())
        if c.get('params_hash') != params_hash:
            return None
        return c
    except Exception:
        return None


def _save_cache(ticker: str, params_hash: str, state: dict):
    p = _cache_path(ticker)
    p.write_text(json.dumps(state))


def _rolling_max(a: np.ndarray, w: int) -> np.ndarray:
    """Trailing-window max (incl. current), NaN-padded head."""
    s = pd.Series(a)
    return s.rolling(w, min_periods=w).max().to_numpy()


def _pivot_mask(highs: np.ndarray, strength: int) -> np.ndarray:
    """Vectorized is_pivot_high: left window strictly below the center,
    right window at or below it."""
    n = len(highs)
    mask = np.zeros(n, dtype=bool)
    if n < 2 * strength + 1:
        return mask
    s = pd.Series(highs)
    # left max over [p-s, p-1] = trailing window of s+1 shifted by 1
    left_max = s.rolling(strength, min_periods=strength).max().shift(1).to_numpy()
    # right max over [p+1, p+s] = forward window
    right_max = s.rolling(strength, min_periods=strength).max() \
        .shift(-strength).to_numpy()
    with np.errstate(invalid='ignore'):
        mask = (highs > left_max) & (highs >= right_max)
    mask[:strength] = False
    mask[n - strength:] = False
    return mask


def _compute_records(highs: np.ndarray, closes: np.ndarray,
                     dates: list, params: dict, start_bar: int,
                     existing: list) -> list:
    """
    GLB records from `start_bar` (trailing-edge pivots) merged with
    `existing` cached records; then scan new bars for breakouts of open
    records. Vectorized where it counts.
    """
    s = params['pivot_strength']
    lookback = params['lookback_bars']
    conf = params['confirmation_bars']
    require_conf = params['require_confirmation']
    n = len(highs)

    records = list(existing)

    # ---- new pivots in the trailing region --------------------------------
    pmask = _pivot_mask(highs, s)
    lookback_max = _rolling_max(highs, lookback)
    first = max(start_bar, s)
    new_pivots = [p for p in range(first, n - s)
                  if pmask[p] and highs[p] >= lookback_max[p]]

    # breakout scan for new pivots (vectorized per pivot)
    for p in new_pivots:
        level = float(highs[p])
        conf_end = min(p + conf, n)
        is_conf = True
        if require_conf and conf_end > p + 1:
            is_conf = bool(np.max(highs[p + 1:conf_end]) <= level)
        if require_conf and not is_conf:
            continue
        scan_from = min(p + conf, n)
        broken_idx = None
        if scan_from < n:
            above = np.flatnonzero(closes[scan_from:] > level)
            if len(above):
                broken_idx = scan_from + int(above[0])
        records.append({
            'level': level,
            'detection_date': dates[p],
            'breakout_date': dates[broken_idx] if broken_idx is not None else None,
            'is_confirmed': bool(is_conf),
            'is_broken': broken_idx is not None,
        })

    # ---- scan new bars for breakouts of still-open records ----------------
    # (records whose detection is old enough that their confirmation window
    #  closed long ago are permanently confirmed — no re-check needed)
    for rec in records:
        if rec['is_broken']:
            continue
        det_idx = dates.index(rec['detection_date']) \
            if rec['detection_date'] in dates else None
        if det_idx is None:
            continue
        conf_end = min(det_idx + conf, n)
        if require_conf and det_idx + 1 < conf_end:
            if np.max(highs[det_idx + 1:conf_end]) > rec['level']:
                rec['is_confirmed'] = False
                continue
            rec['is_confirmed'] = True
        scan_from = min(max(det_idx + conf, start_bar), n)
        if scan_from < n:
            above = np.flatnonzero(closes[scan_from:] > rec['level'])
            if len(above):
                rec['breakout_date'] = dates[scan_from + int(above[0])]
                rec['is_broken'] = True
    return records


def evaluate(tickers: list, data: dict, params: dict | None = None) -> pd.DataFrame:
    """
    tickers: scoped subset (explicit argument — on-demand architecture).
    data: wide OHLCV matrices already restricted to the scoped tickers.
    params overrides: pivot_strength, lookback_bars, historical_bars,
    confirmation_bars, require_confirmation.
    """
    p = {
        'pivot_strength': config.GLB_PIVOT_STRENGTH,
        'lookback_bars': config.GLB_LOOKBACK_BARS,
        'historical_bars': config.GLB_HISTORICAL_BARS,
        'confirmation_bars': config.GLB_CONFIRMATION_BARS,
        'require_confirmation': config.GLB_REQUIRE_CONFIRMATION,
    }
    p.update(params or {})
    phash = _params_hash(p)

    tickers = [t for t in tickers if t in data['close'].columns]
    close_all = data['close'][tickers]
    high_all = data['high'][tickers]

    rows = []
    for t in tickers:
        h_ser = high_all[t].dropna()
        c_ser = close_all[t].reindex(h_ser.index)
        if len(h_ser) < config.GLB_MIN_DATA_POINTS:
            rows.append({'ticker': t, 'in_glb_breakout': False,
                         'glb_level': np.nan, 'glb_detection_date': None,
                         'glb_days_since_pivot': np.nan, 'as_of': None})
            continue
        highs = h_ser.to_numpy(float)
        closes = c_ser.to_numpy(float)
        dates = [d.strftime('%Y-%m-%d') for d in h_ser.index]

        cache = _load_cache(t, phash)
        if cache is not None and cache.get('through', -1) < len(highs) - 1:
            fp = closes[cache['through']]
            if cache.get('through_close') != float(fp):
                cache = None   # history rewritten (split adjustment) — cold
        if cache is None:
            # cold: scan the historical window only
            start_bar = max(p['pivot_strength'],
                            len(highs) - p['historical_bars'])
            records = _compute_records(highs, closes, dates, p,
                                       start_bar, [])
        else:
            records = cache['records']
            # trailing-edge pivots: formed after the cached through-bar
            start_bar = max(p['pivot_strength'],
                            cache['through'] - p['pivot_strength'] + 1)
            records = _compute_records(highs, closes, dates, p,
                                       start_bar, records)

        through = len(highs) - 1
        _save_cache(t, phash, {
            'params_hash': phash,
            'through': through,
            'through_close': float(closes[through]),
            'records': records,
        })

        # ---- latest-bar signal: current GLB level + breakout state ----
        lookback_max = _rolling_max(highs, p['lookback_bars'])
        open_levels = [r for r in records
                       if not r['is_broken'] and r['is_confirmed']
                       and r['detection_date'] in dates
                       and dates.index(r['detection_date'])
                       >= len(highs) - 1 - p['lookback_bars']]
        glb_level = max((r['level'] for r in open_levels), default=np.nan)
        breakout = False
        days_since = np.nan
        det_date = None
        if not np.isnan(glb_level):
            breakout = bool(highs[-1] > glb_level or closes[-1] > glb_level)
            det_date = max(open_levels, key=lambda r: r['detection_date']) \
                if open_levels else None
            if det_date:
                dd = dates.index(det_date['detection_date'])
                days_since = len(highs) - 1 - dd
        rows.append({
            'ticker': t,
            'in_glb_breakout': breakout,
            'glb_level': round(float(glb_level), 3) if not np.isnan(glb_level) else np.nan,
            'glb_detection_date': det_date['detection_date'] if det_date else None,
            'glb_days_since_pivot': int(days_since) if not np.isnan(days_since) else np.nan,
            'as_of': dates[-1],
        })

    out = pd.DataFrame(rows).set_index('ticker')
    out.index.name = 'ticker'
    return out

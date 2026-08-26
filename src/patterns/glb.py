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
module keeps a per-ticker, per-parameter-combo JSON cache under
results/{GLB_CACHE_DIR_NAME}/{SYMBOL}__{params_hash8}.json holding the
computed records + the bar count they cover + a close-price fingerprint
of that bar (a split/rewrite of history invalidates the cache via
fingerprint mismatch). On each run only the NEW bars are scanned for
breakouts of open records, and only pivots near the trailing edge (not
yet fully formed when last computed) are (re)checked.

Namespacing by params_hash (TODO_caching.md, research/pivot_model/)
means switching between two regularly-alternated parameter combos (e.g.
the dashboard's Confirmation/Lookback controls) no longer evicts the
other's cache — each combo keeps its own persistent, independently
incremental slot instead of fighting over one. The params_hash stored
inside each file is still checked on load (belt-and-suspenders against a
hash collision), so a mismatch still falls back to a cold rebuild rather
than ever returning a wrong answer.

The cold path is vectorized per ticker with numpy (rolling-max pivot
test, broadcast breakout scan), so even a first-ever run over a scoped
universe stays in seconds — measured in test_dashboard_app.py. The
confirmation check (no HIGH in the next `confirmation` bars exceeds the
pivot) is answered via one precomputed forward-rolling-max array
(`_rolling_forward_max`, O(n)) instead of a per-pivot Python-loop slice
`max()` call — validated byte-identical against the previous per-pivot
implementation in research/pivot_model/validate_against_glb.py (which
also caught and fixed an off-by-one in that array's window size before
this landed here).
"""
import hashlib
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


def _cache_path(ticker: str, params_hash: str) -> Path:
    d = config.RESULTS_DIR / config.GLB_CACHE_DIR_NAME
    d.mkdir(parents=True, exist_ok=True)
    short_hash = hashlib.md5(params_hash.encode()).hexdigest()[:8]
    return d / f'{ticker.replace(".", "-")}__{short_hash}.json'


def _load_cache(ticker: str, params_hash: str) -> dict | None:
    p = _cache_path(ticker, params_hash)
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
    p = _cache_path(ticker, params_hash)
    p.write_text(json.dumps(state))


def _rolling_max(a: np.ndarray, w: int) -> np.ndarray:
    """Trailing-window max (incl. current), NaN-padded head."""
    s = pd.Series(a)
    return s.rolling(w, min_periods=w).max().to_numpy()


def _rolling_forward_max(a: np.ndarray, w: int) -> np.ndarray:
    """fwd[p] = max(a[p+1 .. p+w]), exactly `w` bars strictly after p; NaN
    where the window runs past the end (caller falls back to a direct
    slice max there). Array-lookup replacement for a per-pivot
    `np.max(highs[p+1:conf_end])` Python-loop slice call — see
    research/pivot_model/shared_primitives.py for the derivation and the
    off-by-one it's easy to get wrong (glb.py's own confirmation slice is
    `w = confirmation_bars - 1` bars, since `conf_end` is Python's
    exclusive slice end)."""
    if w < 1:
        return np.full(len(a), np.nan)
    s = pd.Series(a)
    return s.rolling(w, min_periods=w).max().shift(-w).to_numpy()


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
                     existing: list, pmask: np.ndarray | None = None,
                     lookback_max: np.ndarray | None = None,
                     fwd_conf_max: np.ndarray | None = None) -> list:
    """
    GLB records from `start_bar` (trailing-edge pivots) merged with
    `existing` cached records; then scan new bars for breakouts of open
    records. Vectorized where it counts.

    pmask/lookback_max/fwd_conf_max: precomputed arrays (see
    evaluate_multi), for when a caller already has them and multiple
    scenarios can share the same array — each depends on exactly one of
    pivot_strength/lookback_bars/confirmation_bars, so two scenarios that
    agree on that one value get byte-identical arrays (see
    research/pivot_model/ for why that's exact, not approximate). Omit any
    of them (as evaluate()'s single-scenario call does) to compute it here
    instead.
    """
    s = params['pivot_strength']
    lookback = params['lookback_bars']
    conf = params['confirmation_bars']
    require_conf = params['require_confirmation']
    n = len(highs)

    records = list(existing)

    # ---- new pivots in the trailing region --------------------------------
    if pmask is None:
        pmask = _pivot_mask(highs, s)
    if lookback_max is None:
        lookback_max = _rolling_max(highs, lookback)
    # shared across both loops below — conf is fixed for this whole call
    if fwd_conf_max is None:
        fwd_conf_max = _rolling_forward_max(highs, conf - 1)
    first = max(start_bar, s)
    new_pivots = [p for p in range(first, n - s)
                  if pmask[p] and highs[p] >= lookback_max[p]]

    # breakout scan for new pivots (vectorized per pivot)
    for p in new_pivots:
        level = float(highs[p])
        conf_end = min(p + conf, n)
        is_conf = True
        if require_conf and conf_end > p + 1:
            fm = fwd_conf_max[p]
            is_conf = bool(fm <= level) if not np.isnan(fm) else \
                bool(np.max(highs[p + 1:conf_end]) <= level)
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
            fm = fwd_conf_max[det_idx]
            still_ok = bool(fm <= rec['level']) if not np.isnan(fm) else \
                bool(np.max(highs[det_idx + 1:conf_end]) <= rec['level'])
            if not still_ok:
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
        sig = _latest_signal(highs, closes, dates, records, p['lookback_bars'])
        rows.append({'ticker': t, **sig, 'as_of': dates[-1]})

    out = pd.DataFrame(rows).set_index('ticker')
    out.index.name = 'ticker'
    return out


def _latest_signal(highs: np.ndarray, closes: np.ndarray, dates: list,
                   records: list, lookback: int) -> dict:
    """Current GLB level + breakout state from the latest bar — same logic
    for one scenario regardless of whether it ran via evaluate() or
    evaluate_multi()."""
    n = len(highs)
    open_levels = [r for r in records
                  if not r['is_broken'] and r['is_confirmed']
                  and r['detection_date'] in dates
                  and dates.index(r['detection_date']) >= n - 1 - lookback]
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
            days_since = n - 1 - dd
    return {
        'in_glb_breakout': breakout,
        'glb_level': round(float(glb_level), 3) if not np.isnan(glb_level) else np.nan,
        'glb_detection_date': det_date['detection_date'] if det_date else None,
        'glb_days_since_pivot': int(days_since) if not np.isnan(days_since) else np.nan,
    }


def evaluate_multi(tickers: list, data: dict, scenarios: dict) -> pd.DataFrame:
    """
    Same as evaluate(), but for SEVERAL parameter scenarios in one call,
    sharing work across scenarios that agree on a setting instead of
    recomputing it once per scenario (research/pivot_model/): the pivot
    mask depends only on pivot_strength, the lookback rolling-max only on
    lookback_bars, the confirmation rolling-max only on confirmation_bars
    — two scenarios that share a value get the literal same array, computed
    once. Each scenario still reads/writes its own (ticker, params_hash)
    incremental cache exactly like evaluate() does, so this doesn't change
    caching behavior across separate calls over time, only work done
    *within* one call across scenarios.

    tickers: scoped subset (explicit argument — on-demand architecture).
    data: wide OHLCV matrices already restricted to the scoped tickers.
    scenarios: {name: params_override_dict}, each merged onto GLB's config
    defaults the same way evaluate()'s `params` argument is.

    Returns one DataFrame indexed by ticker with columns suffixed
    `_{name}` per scenario (in_glb_breakout_{name}, glb_level_{name},
    glb_detection_date_{name}, glb_days_since_pivot_{name}), plus a shared
    `as_of`.
    """
    resolved = {}
    for name, override in scenarios.items():
        p = {
            'pivot_strength': config.GLB_PIVOT_STRENGTH,
            'lookback_bars': config.GLB_LOOKBACK_BARS,
            'historical_bars': config.GLB_HISTORICAL_BARS,
            'confirmation_bars': config.GLB_CONFIRMATION_BARS,
            'require_confirmation': config.GLB_REQUIRE_CONFIRMATION,
        }
        p.update(override or {})
        resolved[name] = p

    tickers = [t for t in tickers if t in data['close'].columns]
    close_all = data['close'][tickers]
    high_all = data['high'][tickers]

    empty_sig = {'in_glb_breakout': False, 'glb_level': np.nan,
                'glb_detection_date': None, 'glb_days_since_pivot': np.nan}

    rows = []
    for t in tickers:
        h_ser = high_all[t].dropna()
        c_ser = close_all[t].reindex(h_ser.index)
        row = {'ticker': t, 'as_of': None}

        if len(h_ser) < config.GLB_MIN_DATA_POINTS:
            for name in resolved:
                for k, v in empty_sig.items():
                    row[f'{k}_{name}'] = v
            rows.append(row)
            continue

        highs = h_ser.to_numpy(float)
        closes = c_ser.to_numpy(float)
        dates = [d.strftime('%Y-%m-%d') for d in h_ser.index]
        n = len(highs)

        pmask_cache: dict[int, np.ndarray] = {}
        lookback_cache: dict[int, np.ndarray] = {}
        fwdconf_cache: dict[int, np.ndarray] = {}

        for name, p in resolved.items():
            phash = _params_hash(p)
            s = p['pivot_strength']
            lb = p['lookback_bars']
            conf = p['confirmation_bars']

            if s not in pmask_cache:
                pmask_cache[s] = _pivot_mask(highs, s)
            if lb not in lookback_cache:
                lookback_cache[lb] = _rolling_max(highs, lb)
            if conf not in fwdconf_cache:
                fwdconf_cache[conf] = _rolling_forward_max(highs, conf - 1)

            cache = _load_cache(t, phash)
            if cache is not None and cache.get('through', -1) < n - 1:
                fp = closes[cache['through']]
                if cache.get('through_close') != float(fp):
                    cache = None
            if cache is None:
                start_bar = max(s, n - p['historical_bars'])
                existing = []
            else:
                start_bar = max(s, cache['through'] - s + 1)
                existing = cache['records']
            records = _compute_records(
                highs, closes, dates, p, start_bar, existing,
                pmask_cache[s], lookback_cache[lb], fwdconf_cache[conf])

            _save_cache(t, phash, {
                'params_hash': phash,
                'through': n - 1,
                'through_close': float(closes[n - 1]),
                'records': records,
            })

            sig = _latest_signal(highs, closes, dates, records, lb)
            for k, v in sig.items():
                row[f'{k}_{name}'] = v

        row['as_of'] = dates[-1]
        rows.append(row)

    out = pd.DataFrame(rows).set_index('ticker')
    out.index.name = 'ticker'
    return out

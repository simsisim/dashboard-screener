"""
Timing signal — ATR1 volatility stop / ATR cloud (feedback_4.md Task 3).

Source: metaData_v1/src/screeners/atr1_screener.py:41-107 (vol_stop +
calculate_atr_cloud — "exact implementation from atr_cloud.py validated
against TradingView"; per more_screeners_2.md, atr_screener.py duplicates
the same math and was ignored). Parameters in config.py (ATR1_*):
length=20, factor=3.0, length2=20, factor2=1.5.

vol_stop is genuinely recursive — each bar's stop/max/min/uptrend depend
on the previous bar's, with a reseed to the current price on trend flips.
Ported as a per-ticker loop over RAW NUMPY ARRAYS (state in plain
floats/bools), not the source's .iloc/.loc-in-a-loop style —
more_screeners_2.md calls that out as meaningfully faster.

Cloud: two vol-stops (Close source; 20/3.0 and 20/1.5).
  crossUp = vStop2 crosses above vStop
  crossDn = vStop2 crosses below vStop

Outputs (latest bar per ticker): `atr1_trend` (uptrend/downtrend from
the primary stop), `atr1_stop_level` (vStop), `atr1_stop_level2`
(vStop2), `atr1_cross_up`, `atr1_cross_dn` (true only on the flip day),
`atr1_signal_type` ('Long'/'Short', from the most recent crossUp/crossDn
anywhere in history), `atr1_signal_date`, `atr1_days_since_signal`
(calendar days — ported from metaData_v1/atr1_screener.py's
`days_since_signal`, deliberately calendar-day like the source rather
than PVB's bar-count convention elsewhere in this project),
`atr1_signal_price`, `atr1_performance_since_signal`, `as_of` (the
ticker's own last valid bar date).

On-demand module: explicit ticker list; NOT in the daily batch.

INCREMENTAL CACHE: vol_stop is a Markov state machine (bar i depends only
on bar i-1), same problem shape as src/timing/pvb.py — but cross_up/
cross_dn need the *two* trailing bars of both stop lines, so (unlike
PVB, one seed value is enough) the per-ticker JSON cache under
results/{ATR1_CACHE_DIR_NAME}/{ticker}.json keeps state at both the
`through` bar and `through - 1` for each of the two vol-stop lines,
plus a through_close fingerprint (split/rewrite -> cold) and a
params_hash (threshold change -> cold). The Wilder-RMA seed only needs
one trailing value — nothing reads its second-to-last value. The cache
also carries `last_cross_date/type/price` (the most recent crossUp/
crossDn found anywhere in history) forward at the top level — updated
only when a NEW cross is found in the newly-computed region
[through+1, n), otherwise carried unchanged, since a warm run can't
rescan bars before the watermark (they're not reconstructed).
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
    d = config.RESULTS_DIR / config.ATR1_CACHE_DIR_NAME
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
    _cache_path(ticker).write_text(json.dumps(state))


def _line_state(stop, uptrend, max_, min_, atr, idx) -> dict:
    """Seed state at bar `idx`, plus `idx - 1` for the cross-detection
    lookback (None fields when idx == 0 — too short to have a prior bar)."""
    rma = float(atr[idx]) if not np.isnan(atr[idx]) else None
    state = {
        'stop_seed': float(stop[idx]), 'uptrend_seed': bool(uptrend[idx]),
        'max_seed': float(max_[idx]), 'min_seed': float(min_[idx]),
        'rma_seed': rma,
        'stop_seed2': None, 'uptrend_seed2': None,
        'max_seed2': None, 'min_seed2': None,
    }
    if idx >= 1:
        state.update({
            'stop_seed2': float(stop[idx - 1]), 'uptrend_seed2': bool(uptrend[idx - 1]),
            'max_seed2': float(max_[idx - 1]), 'min_seed2': float(min_[idx - 1]),
        })
    return state


def _true_range_np(high, low, close):
    prev_close = np.concatenate([[close[0]], close[:-1]])
    tr = np.maximum(high - low, np.maximum(np.abs(high - prev_close),
                                           np.abs(low - prev_close)))
    return tr


def _wild_rma_np(values, length, resume_from: tuple | None = None):
    """Wilder RMA: SMA-seeded recursive smoothing (TradingView ta.rma).

    resume_from: optional (start_index, seed_value) — out[start_index-1]
    = seed_value, loop continues from start_index instead of re-deriving
    the SMA seed from scratch. Cold path (resume_from=None) unchanged."""
    out = np.full(len(values), np.nan)
    if resume_from is not None:
        start_index, seed_value = resume_from
        out[start_index - 1] = seed_value
        for i in range(start_index, len(values)):
            v = values[i]
            out[i] = out[i - 1] if np.isnan(v) else (out[i - 1] * (length - 1) + v) / length
        return out
    valid = np.flatnonzero(~np.isnan(values))
    if len(valid) == 0 or len(values) - valid[0] < length:
        return out
    start = valid[0]
    out[start + length - 1] = np.nanmean(values[start:start + length])
    for i in range(start + length, len(values)):
        v = values[i]
        if np.isnan(v):
            out[i] = out[i - 1]
        else:
            out[i] = (out[i - 1] * (length - 1) + v) / length
    return out


def vol_stop_np(high, low, close, length, factor, resume_from: dict | None = None):
    """Source atr1_screener.py:41-85, ported to raw numpy arrays.

    resume_from: optional {'through': int, 'rma_seed', 'stop_seed',
    'uptrend_seed', 'max_seed', 'min_seed', 'stop_seed2', 'uptrend_seed2',
    'max_seed2', 'min_seed2'} — *_seed = state AT bar `through`, *_seed2 =
    state at bar `through - 1`. Continues from through+1 instead of
    recomputing from bar 1 (cold path unchanged when resume_from=None)."""
    tr = _true_range_np(high, low, close)
    src = close
    n = len(src)

    if resume_from is not None:
        th = resume_from['through']
        atr = _wild_rma_np(tr, length, resume_from=(th + 1, resume_from['rma_seed']))
        max_ = np.full(n, np.nan)
        min_ = np.full(n, np.nan)
        stop = np.full(n, np.nan)
        uptrend = np.ones(n, dtype=bool)
        if th >= 1:
            max_[th - 1], min_[th - 1] = resume_from['max_seed2'], resume_from['min_seed2']
            stop[th - 1], uptrend[th - 1] = resume_from['stop_seed2'], resume_from['uptrend_seed2']
        max_[th], min_[th] = resume_from['max_seed'], resume_from['min_seed']
        stop[th], uptrend[th] = resume_from['stop_seed'], resume_from['uptrend_seed']
        atr_m = np.full(n, np.nan)
        loop_start = th + 1
    else:
        atr = _wild_rma_np(tr, length)
        max_ = src.copy()
        min_ = src.copy()
        stop = np.full(n, 0.0)
        uptrend = np.ones(n, dtype=bool)
        atr_m = np.full(n, np.nan)
        loop_start = 1

    for i in range(loop_start, n):
        atr_m[i] = tr[i] if np.isnan(atr[i]) else atr[i] * factor
        max_[i] = max(max_[i - 1], src[i])
        min_[i] = min(min_[i - 1], src[i])
        if uptrend[i - 1]:
            new_stop = max(stop[i - 1], max_[i] - atr_m[i])
        else:
            new_stop = min(stop[i - 1], min_[i] + atr_m[i])
        stop[i] = src[i] if np.isnan(new_stop) else new_stop
        uptrend[i] = (src[i] - stop[i]) >= 0.0
        if uptrend[i] != uptrend[i - 1]:
            max_[i] = src[i]
            min_[i] = src[i]
            stop[i] = (src[i] - atr_m[i]) if uptrend[i] else (src[i] + atr_m[i])
    return stop, uptrend, max_, min_, atr


def evaluate(tickers: list, data: dict) -> pd.DataFrame:
    high_all, low_all, close_all = (data['high'][tickers],
                                    data['low'][tickers], data['close'][tickers])

    phash = _params_hash({'len1': config.ATR1_LENGTH, 'f1': config.ATR1_FACTOR,
                          'len2': config.ATR1_LENGTH2, 'f2': config.ATR1_FACTOR2})

    rows = []
    for t in tickers:
        h = high_all[t].dropna()
        if len(h) < max(config.ATR1_LENGTH, config.ATR1_LENGTH2) + 2:
            rows.append({'ticker': t, 'atr1_trend': None,
                         'atr1_stop_level': np.nan, 'atr1_stop_level2': np.nan,
                         'atr1_cross_up': False, 'atr1_cross_dn': False,
                         'atr1_signal_type': None, 'atr1_signal_date': None,
                         'atr1_days_since_signal': np.nan, 'atr1_signal_price': np.nan,
                         'atr1_performance_since_signal': np.nan,
                         'as_of': None})
            continue
        # align all series to this ticker's own valid bars
        idx = h.index
        l = low_all[t].reindex(idx)
        c = close_all[t].reindex(idx)
        h_arr, l_arr, c_arr = h.to_numpy(float), l.to_numpy(float), c.to_numpy(float)
        n = len(h_arr)

        resume1 = resume2 = None
        prev_cross_date = prev_cross_type = prev_cross_price = None
        scan_start = 1
        cache = _load_cache(t, phash)
        if cache is not None:
            through = cache.get('through', -1)
            l1, l2 = cache.get('line1'), cache.get('line2')
            valid_fp = (1 <= through < n
                       and cache.get('through_close') == float(c_arr[through]))
            has_seeds = (l1 and l2 and l1.get('rma_seed') is not None
                        and l2.get('rma_seed') is not None
                        and l1.get('stop_seed2') is not None
                        and l2.get('stop_seed2') is not None)
            if valid_fp and has_seeds:
                resume1 = dict(l1, through=through)
                resume2 = dict(l2, through=through)
                scan_start = through + 1   # a cross AT `through` was already
                                            # checked (and cached) last run
                prev_cross_date = cache.get('last_cross_date')
                prev_cross_type = cache.get('last_cross_type')
                prev_cross_price = cache.get('last_cross_price')
            # else: no cache / stale (params changed) / fingerprint
            # mismatch (split-rewrite) / too-short history — cold below

        stop1, uptrend, max1, min1, atr1 = vol_stop_np(
            h_arr, l_arr, c_arr, config.ATR1_LENGTH, config.ATR1_FACTOR,
            resume_from=resume1)
        stop2, uptrend2, max2, min2, atr2 = vol_stop_np(
            h_arr, l_arr, c_arr, config.ATR1_LENGTH2, config.ATR1_FACTOR2,
            resume_from=resume2)

        cross_up = bool(stop2[-1] > stop1[-1]
                        and stop2[-2] <= stop1[-2])
        cross_dn = bool(stop2[-1] < stop1[-1]
                        and stop2[-2] >= stop1[-2])

        # last crossUp/crossDn anywhere in [scan_start, n) — ported from
        # metaData_v1/atr1_screener.py's signal_df = crossUp | crossDn scan,
        # but incremental: only the newly-computed region is scanned, and
        # a cache hit with no new cross carries prev_cross_* forward as-is.
        last_cross_date, last_cross_type, last_cross_price = \
            prev_cross_date, prev_cross_type, prev_cross_price
        for i in range(scan_start, n):
            if (np.isnan(stop1[i - 1]) or np.isnan(stop2[i - 1])
                    or np.isnan(stop1[i]) or np.isnan(stop2[i])):
                continue
            if stop2[i] > stop1[i] and stop2[i - 1] <= stop1[i - 1]:
                last_cross_date = idx[i].strftime('%Y-%m-%d')
                last_cross_type, last_cross_price = 'Long', float(c_arr[i])
            elif stop2[i] < stop1[i] and stop2[i - 1] >= stop1[i - 1]:
                last_cross_date = idx[i].strftime('%Y-%m-%d')
                last_cross_type, last_cross_price = 'Short', float(c_arr[i])

        if last_cross_date is not None:
            days_since_signal = (idx[-1] - pd.Timestamp(last_cross_date)).days
            perf_since_signal = (c_arr[-1] / last_cross_price - 1.0) * 100.0 \
                if last_cross_price else np.nan
        else:
            days_since_signal = np.nan
            perf_since_signal = np.nan

        _save_cache(t, phash, {
            'params_hash': phash,
            'through': n - 1,
            'through_close': float(c_arr[-1]),
            'line1': _line_state(stop1, uptrend, max1, min1, atr1, n - 1),
            'line2': _line_state(stop2, uptrend2, max2, min2, atr2, n - 1),
            'last_cross_date': last_cross_date,
            'last_cross_type': last_cross_type,
            'last_cross_price': last_cross_price,
        })

        rows.append({
            'ticker': t,
            'atr1_trend': 'uptrend' if uptrend[-1] else 'downtrend',
            'atr1_stop_level': round(float(stop1[-1]), 3),
            'atr1_stop_level2': round(float(stop2[-1]), 3),
            'atr1_cross_up': cross_up,
            'atr1_cross_dn': cross_dn,
            'atr1_signal_type': last_cross_type,
            'atr1_signal_date': last_cross_date,
            'atr1_days_since_signal': days_since_signal,
            'atr1_signal_price': last_cross_price if last_cross_price is not None else np.nan,
            'atr1_performance_since_signal': round(perf_since_signal, 2) if not np.isnan(perf_since_signal) else np.nan,
            'as_of': idx[-1].strftime('%Y-%m-%d'),
        })

    out = pd.DataFrame(rows).set_index('ticker')
    out.index.name = 'ticker'
    return out

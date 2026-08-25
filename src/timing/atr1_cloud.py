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
`as_of` (the ticker's own last valid bar date).

On-demand module: explicit ticker list; NOT in the daily batch.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
import config


def _true_range_np(high, low, close):
    prev_close = np.concatenate([[close[0]], close[:-1]])
    tr = np.maximum(high - low, np.maximum(np.abs(high - prev_close),
                                           np.abs(low - prev_close)))
    return tr


def _wild_rma_np(values, length):
    """Wilder RMA: SMA-seeded recursive smoothing (TradingView ta.rma)."""
    out = np.full(len(values), np.nan)
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


def vol_stop_np(high, low, close, length, factor):
    """Source atr1_screener.py:41-85, ported to raw numpy arrays."""
    tr = _true_range_np(high, low, close)
    atr = _wild_rma_np(tr, length)
    src = close
    n = len(src)
    max_ = src.copy()
    min_ = src.copy()
    stop = np.full(n, 0.0)
    uptrend = np.ones(n, dtype=bool)
    atr_m = np.full(n, np.nan)
    for i in range(1, n):
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
    return stop, uptrend


def evaluate(tickers: list, data: dict) -> pd.DataFrame:
    high_all, low_all, close_all = (data['high'][tickers],
                                    data['low'][tickers], data['close'][tickers])

    rows = []
    for t in tickers:
        h = high_all[t].dropna()
        if len(h) < max(config.ATR1_LENGTH, config.ATR1_LENGTH2) + 2:
            rows.append({'ticker': t, 'atr1_trend': None,
                         'atr1_stop_level': np.nan, 'atr1_stop_level2': np.nan,
                         'atr1_cross_up': False, 'atr1_cross_dn': False,
                         'as_of': None})
            continue
        # align all series to this ticker's own valid bars
        l = low_all[t].reindex(h.index)
        c = close_all[t].reindex(h.index)

        stop1, uptrend = vol_stop_np(h.to_numpy(float), l.to_numpy(float),
                                     c.to_numpy(float),
                                     config.ATR1_LENGTH, config.ATR1_FACTOR)
        stop2, uptrend2 = vol_stop_np(h.to_numpy(float), l.to_numpy(float),
                                      c.to_numpy(float),
                                      config.ATR1_LENGTH2, config.ATR1_FACTOR2)
        cross_up = bool(stop2[-1] > stop1[-1]
                        and stop2[-2] <= stop1[-2])
        cross_dn = bool(stop2[-1] < stop1[-1]
                        and stop2[-2] >= stop1[-2])
        rows.append({
            'ticker': t,
            'atr1_trend': 'uptrend' if uptrend[-1] else 'downtrend',
            'atr1_stop_level': round(float(stop1[-1]), 3),
            'atr1_stop_level2': round(float(stop2[-1]), 3),
            'atr1_cross_up': cross_up,
            'atr1_cross_dn': cross_dn,
            'as_of': h.index[-1].strftime('%Y-%m-%d'),
        })

    out = pd.DataFrame(rows).set_index('ticker')
    out.index.name = 'ticker'
    return out

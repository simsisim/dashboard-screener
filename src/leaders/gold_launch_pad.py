"""
Leader filter — Golden Launch Pad (more_screeners.md Task 2).

Original: https://www.tradingview.com/script/DvE0wDfI-Golden-Launch-Pad/
(now removed from TradingView — "Publication has ghosted"; the
metaData_v1 port is the authoritative reference:
metaData_v1/src/screeners/gold_launch_pad.py, params :43-60, logic
:_calculate_zscore_spread/_check_bullish_stacking/_check_positive_slopes/
_check_price_above_fastest_ma/_check_price_near_cluster).

Five conditions on the LATEST bar of wide matrices (EMA periods 10/20/50):
  1. Tightly grouped — each EMA z-scored against its own trailing
     51-bar window (zscore_window=50, inclusive, matching the source's
     window_data = ma_values[i-50:i+1]); spread = max(z) - min(z) across
     the 3 EMAs <= 1.0
  2. Bullishly stacked — EMA10 > EMA20 > EMA50
  3. Positive slope — OLS linregress slope of each EMA over
     int(period*0.3)+1 bars > 0.0001 (indicators.rolling_linreg_slope,
     the vectorized form of the source's per-bar scipy linregress)
  4. Price above fastest EMA — close > EMA10
  5. Near cluster — |close - mean(EMA10,EMA20,EMA50)| <= 2.0 x
     rolling(20) stdev of close (ddof=1, pandas default, as the source)

Outputs: `in_gold_launch_pad` bool, `glp_spread` (raw z-spread),
`glp_spread_score` = 1 - spread/max_spread clipped [0, 1],
`glp_strong` = spread_score >= 0.7 (source's Strong/Moderate split).

The source wrapper's base filters (min price $5, min 20d avg volume
100K) are wrapper-level, not part of the 5 methodology conditions; the
project's own liquidity gate covers the volume side (documented choice,
IMPLEMENTATION_PLAN.md §11.2).
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
import config
from src import indicators


def evaluate(close: pd.DataFrame) -> pd.DataFrame:
    periods = config.GLP_MA_PERIODS
    emas = {p: indicators.ema(close, p) for p in periods}

    # 1) z-score spread: rolling mean/std over the inclusive trailing
    #    window (zscore_window+1 bars ending at t), ddof=0 like np.nanstd
    w = config.GLP_ZSCORE_WINDOW + 1
    z = {}
    for p, ema in emas.items():
        roll_mean = ema.rolling(w, min_periods=w).mean()
        roll_std = ema.rolling(w, min_periods=w).std(ddof=0)
        z[p] = (ema - roll_mean) / roll_std.replace(0, np.nan)
    # elementwise max/min across the 3 period-frames (Date x ticker)
    z_periods = list(z.values())
    z_max, z_min = z_periods[0], z_periods[0]
    for zf in z_periods[1:]:
        z_max = pd.DataFrame(np.fmax(z_max.values, zf.values),
                             index=z_max.index, columns=z_max.columns)
        z_min = pd.DataFrame(np.fmin(z_min.values, zf.values),
                             index=z_min.index, columns=z_min.columns)
    glp_spread = z_max - z_min

    # 2) bullishly stacked
    stacked = (emas[periods[0]] > emas[periods[1]]) & \
              (emas[periods[1]] > emas[periods[2]])

    # 3) positive OLS slopes
    positive = None
    for p in periods:
        lookback = max(1, int(p * config.GLP_SLOPE_LOOKBACK_PCT))
        slope = indicators.rolling_linreg_slope(emas[p], lookback + 1)
        pos = slope > config.GLP_MIN_SLOPE
        positive = pos if positive is None else (positive & pos)

    # 4) price above fastest EMA
    above_fast = close.iloc[-1] > emas[periods[0]].iloc[-1]

    # 5) near the MA cluster
    cluster_avg = pd.concat([e.iloc[-1] for e in emas.values()], axis=1).mean(axis=1)
    prox_std = close.rolling(config.GLP_PROXIMITY_WINDOW,
                             min_periods=config.GLP_PROXIMITY_WINDOW).std().iloc[-1]
    near = (close.iloc[-1] - cluster_avg).abs() <= \
        config.GLP_PROXIMITY_STDEV * prox_std

    last_spread = glp_spread.iloc[-1]
    spread_score = (1.0 - last_spread / config.GLP_MAX_SPREAD).clip(0.0, 1.0)

    in_glp = (last_spread <= config.GLP_MAX_SPREAD) & stacked.iloc[-1] & \
        positive.iloc[-1] & above_fast & near

    out = pd.DataFrame(index=close.columns)
    out.index.name = 'ticker'
    out['glp_spread'] = last_spread.round(4)
    out['glp_spread_score'] = spread_score.round(3)
    out['glp_strong'] = (spread_score >= config.GLP_STRONG_SCORE).fillna(False)
    out['in_gold_launch_pad'] = in_glp.fillna(False).astype(bool)
    return out

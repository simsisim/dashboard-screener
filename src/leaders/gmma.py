"""
Leader filter — GMMA / Guppy Multiple Moving Average state
(more_screeners.md Task 4; source metaData_v1/src/screeners/guppy_screener.py:
_check_alignment :287, _check_compression_breakout :347, _check_expansion,
_check_crossover; periods 3/5/8/10/12/15 short + 30/35/40/45/50/60 long).

Filter-shaped output per TAXONOMY.md / the backlog's own guidance ("don't
force it into an `in_gmma` flag"): a categorical `gmma_state` column plus
numeric spreads.

States (priority order):
  'bullish'      — ALL short EMAs > ALL long EMAs (perfect alignment)
  'bearish'      — ALL short EMAs < ALL long EMAs
  'compression_breakout' — total group spread was <= 2% within the last
                   5 days and is now > 1.5x that recent minimum
  'expanding'    — total spread > 1.5x its value 10 bars ago (strong trend)
  'bullish_crossover' / 'bearish_crossover' — st/lt group average crossed
                   within the last GMMA_CROSSOVER_CONFIRM_DAYS, otherwise
                   'transitioning'

Numerics: gmma_separation_pct, gmma_total_spread (st_spread + lt_spread,
each (max-min)/min), gmma_compression_ratio (min spread over the last 5
bars), gmma_breakout_strength (current / recent-min spread).

Implementation note: group min/max/mean are computed by concatenating the
group's EMA frames along a period axis and grouping by date — axis=1
reductions would collapse the ticker dimension.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
import config
from src import indicators


def _last(s):
    """Last row of a Date x ticker frame as a ticker-indexed Series
    (single-ticker frames reduce iloc[-1] to a scalar)."""
    last = s.iloc[-1]
    if isinstance(last, pd.Series):
        return last
    return pd.Series({s.columns[0]: last})


def _group_stats(periods, close):
    frames = [indicators.ema(close, p) for p in periods]
    mn = mx = frames[0]
    for f in frames[1:]:
        mn = pd.DataFrame(np.fmin(mn.values, f.values),
                          index=mn.index, columns=mn.columns)
        mx = pd.DataFrame(np.fmax(mx.values, f.values),
                          index=mx.index, columns=mx.columns)
    # elementwise mean (NaN until the longest EMA has warmed up)
    mean = frames[0].copy()
    for f in frames[1:]:
        mean = mean + f
    return mn, mx, mean / len(frames)


def evaluate(close: pd.DataFrame) -> pd.DataFrame:
    short_p = config.GMMA_SHORT_PERIODS
    long_p = config.GMMA_LONG_PERIODS

    st_min, st_max, st_avg = _group_stats(short_p, close)
    lt_min, lt_max, lt_avg = _group_stats(long_p, close)

    # perfect alignment, elementwise: every short > every long
    # <=> min(short) > max(long); bearish = max(short) < min(long)
    bullish = st_min > lt_max
    bearish = st_max < lt_min

    separation_pct = ((st_avg - lt_avg).abs() / lt_avg.replace(0, np.nan) * 100)

    st_spread = (st_max - st_min) / st_min.replace(0, np.nan)
    lt_spread = (lt_max - lt_min) / lt_min.replace(0, np.nan)
    total_spread = st_spread + lt_spread

    recent_min = total_spread.rolling(5, min_periods=5).min()
    was_compressed = recent_min <= config.GMMA_COMPRESSION_RATIO
    now_expanding = total_spread > recent_min * config.GMMA_EXPANSION_MULT
    compression_breakout = was_compressed & now_expanding

    expanding = total_spread > (total_spread.shift(config.GMMA_SPREAD_LOOKBACK)
                                * config.GMMA_EXPANSION_MULT)

    # crossover: st_avg above lt_avg now but at/below it within the last
    # crossover_confirmation_days (source default 3)
    cd = config.GMMA_CROSSOVER_CONFIRM_DAYS
    cross_up = (st_avg > lt_avg) & \
        (st_avg <= lt_avg).rolling(cd, min_periods=1).max().astype(bool)
    cross_dn = (st_avg < lt_avg) & \
        (st_avg >= lt_avg).rolling(cd, min_periods=1).max().astype(bool)

    state = pd.DataFrame('transitioning', index=close.index,
                         columns=close.columns)
    state[bullish.fillna(False)] = 'bullish'
    state[bearish.fillna(False)] = 'bearish'
    state[expanding.fillna(False)] = 'expanding'
    state[compression_breakout.fillna(False)] = 'compression_breakout'
    # crossovers only relabel 'transitioning' cells
    state[cross_up.fillna(False) & (state == 'transitioning')] = \
        'bullish_crossover'
    state[cross_dn.fillna(False) & (state == 'transitioning')] = \
        'bearish_crossover'

    out = pd.DataFrame(index=close.columns)
    out.index.name = 'ticker'
    out['gmma_state'] = _last(state)
    out['gmma_separation_pct'] = _last(separation_pct).round(2)
    out['gmma_total_spread'] = _last(total_spread).round(4)
    out['gmma_compression_ratio'] = _last(recent_min).round(4)
    out['gmma_breakout_strength'] = (_last(total_spread)
                                     / _last(recent_min).replace(0, np.nan)).round(2)
    out['gmma_bullish_alignment'] = _last(bullish).fillna(False).astype(bool)
    out['gmma_bearish_alignment'] = _last(bearish).fillna(False).astype(bool)
    out['gmma_compression_breakout'] = _last(compression_breakout).fillna(
        False).astype(bool)
    return out

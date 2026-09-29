"""
Focus metric — 21dma-structure pullback (PrimeTrading).

Source: gd_systems/primeTrading/21dma-structure TV script_v7.3.txt
("ADJUSTABLE MA STRUCTURE", BalarezoCapital, modified by PrimeTrading),
daily defaults: EMA, length 21.

Script logic, ported as-is:
  band      MAHigh / MAClose / MALow = EMA21 of high / close / low
  trend     up   if all three MAs > their previous value (isRising)
            down if all three MAs < their previous value (isFalling)
            else hold the previous state (center-line color memory;
            nz(..., trendUpColor) -> starts as up)
  bearish   high < MALow (useHighBelowCondition = true, the default)

Pullback rule (user decision, not in the script — a "look at the chart"
flag, not an entry signal):
  ma21s_dist_pct  close vs the band: 0 inside [MALow, MAHigh], +x% above
                  MAHigh, -x% below MALow
  in_21dma_pullback = trend up AND |dist| <= config.MA21S_PULLBACK_PCT
  ma21s_zone      above (0..+2%) / inside / undercut (-2..0%) —
                  extended (> +2%) / below (< -2%) outside the window
  ma21s_bearish_bar  the script's bearish bar on the latest bar (whole bar
                  under the band) — shown, not excluded
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
import config
from src import indicators


def evaluate(high: pd.DataFrame, low: pd.DataFrame,
             close: pd.DataFrame) -> pd.DataFrame:
    n = config.MA21S_LENGTH
    ma_h = indicators.ema(high, n)
    ma_c = indicators.ema(close, n)
    ma_l = indicators.ema(low, n)

    rising = (ma_h > ma_h.shift(1)) & (ma_c > ma_c.shift(1)) & (ma_l > ma_l.shift(1))
    falling = (ma_h < ma_h.shift(1)) & (ma_c < ma_c.shift(1)) & (ma_l < ma_l.shift(1))
    trend = (pd.DataFrame(np.where(rising, 1.0, np.where(falling, -1.0, np.nan)),
                          index=close.index, columns=close.columns)
             .ffill().fillna(1.0).iloc[-1])

    c, h = close.iloc[-1], high.iloc[-1]
    top, bot = ma_h.iloc[-1], ma_l.iloc[-1]
    dist = pd.Series(0.0, index=close.columns)
    dist = dist.mask(c > top, (c / top - 1) * 100)
    dist = dist.mask(c < bot, (c / bot - 1) * 100)
    enough = close.notna().sum() >= n
    valid = c.notna() & top.notna() & bot.notna() & enough
    dist = dist.where(valid).round(2)

    w = config.MA21S_PULLBACK_PCT
    zone = pd.Series(np.select(
        [dist > w, dist > 0, dist == 0, dist >= -w, dist < -w],
        ['extended', 'above', 'inside', 'undercut', 'below'], default=None),
        index=close.columns, dtype=object).where(valid)

    out = pd.DataFrame(index=close.columns)
    out.index.name = 'ticker'
    out['ma21s_high'] = top.round(4)
    out['ma21s_close'] = ma_c.iloc[-1].round(4)
    out['ma21s_low'] = bot.round(4)
    out['ma21s_trend'] = pd.Series(np.where(trend > 0, 'up', 'down'),
                                   index=close.columns).where(valid)
    out['ma21s_dist_pct'] = dist
    out['ma21s_zone'] = zone
    out['ma21s_bearish_bar'] = ((h < bot) & valid).astype(bool)
    out['in_21dma_pullback'] = ((out['ma21s_trend'] == 'up')
                                & (dist.abs() <= w)).fillna(False).astype(bool)
    return out

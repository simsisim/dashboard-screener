"""
Focus metric c) — Weinstein stage classification with abc sub-stages
(intro.md 2c). Vectorized port of yf-gics/src/stage_analysis.py::_classify
(same thresholds; lkm_rs/common/stage.py is the same logic per-ticker).

Stages:
  2A — early uptrend: price > 200-SMA, 50 > 200, 200-SMA rising, but the
       150-SMA hasn't confirmed yet (price <= 150 or 150 <= 200). Entry zone.
  2B — mid uptrend: full alignment price > 150 > 200, 50 > 200, 200 rising.
       Core holding zone.
  2C — late uptrend: still structured but 200-SMA flattening (20d slope
       <= 0.15%) or price has slipped under its 50-SMA. Tighten stops.
  3  — distribution/topping: price > 200 but 50 < 200, or price just under
       200 with the golden cross still intact and 200 rising.
  4  — decline: price and MAs pointing down.
  1  — basing (default when none of the above).
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
import config
from src import indicators

_STAGE_SCORE = {'2B': 100, '2A': 85, '2C': 70, '1': 45, '3': 25, '4': 5}


def evaluate(close: pd.DataFrame) -> pd.DataFrame:
    c = close
    s50 = indicators.sma(c, config.STAGE_SMA_SHORT)
    s150 = indicators.sma(c, config.STAGE_SMA_MED)
    s200 = indicators.sma(c, config.STAGE_SMA_LONG)
    slope200 = indicators.slope_pct(s200, config.STAGE_SLOPE_WINDOW)

    price = c.iloc[-1]
    v50, v150, v200 = s50.iloc[-1], s150.iloc[-1], s200.iloc[-1]
    s200s = slope200.iloc[-1]

    above200 = price > v200
    above150 = price > v150
    above50 = price > v50
    golden_x = v50 > v200
    s150_gt_200 = v150 > v200
    rising = s200s > config.STAGE_SLOPE_RISING
    flat = s200s.abs() <= config.STAGE_SLOPE_RISING

    stage = pd.Series('1', index=c.columns, dtype=object)

    # Stage 2 family (checked first)
    stage[(above200 & golden_x & rising & above150 & s150_gt_200
           & ~((s200s < config.STAGE_SLOPE_LATE) & ~above50))] = '2B'
    stage[(above200 & golden_x & rising & ~(above150 & s150_gt_200))] = '2A'
    stage[(above200 & golden_x & rising & above150 & s150_gt_200
           & (s200s < config.STAGE_SLOPE_LATE) & ~above50)] = '2C'
    stage[above200 & golden_x & flat] = '2C'

    # Stage 3
    stage[above200 & ~golden_x] = '3'
    stage[(~above200) & (v50 > v200 * 0.98) & rising] = '3'

    # Stage 4
    stage[(~above200) & (~golden_x) & (s200s < 0)] = '4'
    stage[(~above200) & (~golden_x) & flat] = '4'

    out = pd.DataFrame(index=c.columns)
    out.index.name = 'ticker'
    out['stage'] = stage
    out['stage_score'] = stage.map(_STAGE_SCORE).astype(int)
    out['slope200_pct'] = s200s.round(3)
    out['pct_vs_sma50'] = ((price / v50 - 1) * 100).round(2)
    out['pct_vs_sma150'] = ((price / v150 - 1) * 100).round(2)
    out['pct_vs_sma200'] = ((price / v200 - 1) * 100).round(2)
    return out

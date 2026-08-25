"""
Leader screener — 20-Day EMA Pullback Test (feedback_7.md item 4).

Source: EarningsBeats.com scan language, via more_screeners_3.md (which
added a 5th condition — EMA20 rising — beyond the original 4-condition
syntax; that addition is part of THIS project's definition, decided in
the draft, not the source).

Five conditions on the LATEST bar:
  1. SCTR (scooter_score) > 75      — reuses the existing scooter column,
                                      not recomputed
  2. Open > EMA20
  3. Low < EMA20
  4. Close > EMA20
  5. EMA20 rising                   — today > EMA20 N bars ago
                                     (config.EMA20_SLOPE_LOOKBACK = 5, one
                                     trading week; deliberately a
                                     lightweight point-to-point comparison,
                                     not an OLS slope like GLP's)

Conditions 2-4 together are the "pullback" signature: the bar opened
above the EMA, dipped under it intraday, and closed back above — a test
of the 20-day EMA as support that held.

Outputs: `in_ema20_pullback` bool + `ema20` (byproduct column, useful as
its own filter ingredient later).

Daily-batch module (full universe, wide matrices) — NOT on-demand.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
import config
from src import indicators


def evaluate(close: pd.DataFrame, open_: pd.DataFrame,
             low: pd.DataFrame, scooter_score: pd.Series) -> pd.DataFrame:
    ema20 = indicators.ema(close, 20)
    last_ema = ema20.iloc[-1]
    last_open = open_.iloc[-1]
    last_low = low.iloc[-1]
    last_close = close.iloc[-1]

    lookback = config.EMA20_SLOPE_LOOKBACK
    ema_past = ema20.iloc[-1 - lookback]
    rising = last_ema > ema_past

    sctr_ok = scooter_score.reindex(close.columns) > config.EMA20_SCTR_MIN

    in_pullback = (sctr_ok & (last_open > last_ema)
                   & (last_low < last_ema)
                   & (last_close > last_ema) & rising)

    out = pd.DataFrame(index=close.columns)
    out.index.name = 'ticker'
    out['in_ema20_pullback'] = in_pullback.fillna(False).astype(bool)
    out['ema20'] = last_ema.round(3)
    out['ema20_rising'] = rising.fillna(False).astype(bool)
    return out

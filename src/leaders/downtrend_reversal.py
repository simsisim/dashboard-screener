"""
Leader screener — Downtrend Reversal / Pullback Scan (feedback_7.md
item 5).

Source: EarningsBeats.com Pullback Scan language, via more_screeners_3.md.

Signal (LATEST bar): today's High exceeds yesterday's High, preceded by a
STRICTLY declining sequence of daily Highs for the
config.DOWNTREND_REVERSAL_LOOKBACK_DAYS (6) days before that:

    H[t-1] > H[t-2] > H[t-3] > H[t-4] > H[t-5] > H[t-6]
    and H[t] > H[t-1]

i.e. six straight lower highs, then today's high breaks the streak — the
"classic down-trend reversal to the upside" trigger.

Output: `in_downtrend_reversal` bool. Single vectorized pass across the
wide matrix (no per-ticker loop). Daily-batch module — NOT on-demand.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
import config


def evaluate(high: pd.DataFrame) -> pd.DataFrame:
    lookback = config.DOWNTREND_REVERSAL_LOOKBACK_DAYS

    # strictly declining chain: H[t-k] > H[t-k-1] for k = 1..lookback
    declining = high.shift(1) > high.shift(2)
    for k in range(2, lookback + 1):
        declining &= high.shift(k) > high.shift(k + 1)

    # reversal bar: today's high breaks yesterday's high
    reversal = (high > high.shift(1)) & declining

    out = pd.DataFrame(index=high.columns)
    out.index.name = 'ticker'
    out['in_downtrend_reversal'] = reversal.iloc[-1].fillna(False).astype(bool)
    return out

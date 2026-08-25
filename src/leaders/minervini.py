"""
Leader filter a) — Minervini Trend Template.

8 criteria (Mark Minervini, "Trade Like a Stock Market Wizard"):
  1. Close > SMA150 and Close > SMA200
  2. SMA150 > SMA200
  3. SMA200 trending up >= 1 month (20-day slope > 0)
  4. SMA50 > SMA150 and SMA50 > SMA200
  5. Close > SMA50
  6. Close >= 1.30 x 52-week low
  7. Close >= 0.75 x 52-week high (within 25% of the high)
  8. RS percentile >= 70 (IBD-style weighted blend, cross-sectional)

Ported from the project's two verified implementations:
- lkm_rs/common/stage.py + config.py (daily variant: SMA 50/150/200, slope
  window 20d, 1.30x/0.75x 52w bounds, IBD RS blend) — backtest-validated
  there (large-cap bucket beats both nulls).
- metaData_v1/src/screeners/minervini_screener.py (same 8 criteria).

Vectorized: evaluates the LATEST bar of wide Date×ticker matrices.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
import config
from src import indicators


def evaluate(close: pd.DataFrame, rs_pct: pd.Series | None = None) -> pd.DataFrame:
    """
    close: wide Close matrix (Date×ticker). rs_pct: optional pre-computed
    cross-sectional RS percentile Series for the latest date (index=ticker);
    computed here when not given.
    Returns a per-ticker DataFrame indexed by ticker with the 8 criterion
    booleans, `minervini_count` (0-8), `rs_pct`, and supporting values.
    """
    c = close
    sma50 = indicators.sma(c, config.MINERVINI_SMA_SHORT)
    sma150 = indicators.sma(c, config.MINERVINI_SMA_MED)
    sma200 = indicators.sma(c, config.MINERVINI_SMA_LONG)
    high52 = indicators.rolling_high(c, config.BARS_52W)
    low52 = indicators.rolling_low(c, config.BARS_52W)
    slope200 = indicators.slope_pct(sma200, config.MINERVINI_SLOPE_WINDOW)

    if rs_pct is None:
        rs_raw = indicators.ibd_rs_raw(c)
        rs_pct = indicators.cross_sectional_percentile(rs_raw).iloc[-1]

    last = c.iloc[-1]
    v50, v150, v200 = sma50.iloc[-1], sma150.iloc[-1], sma200.iloc[-1]
    h52, l52 = high52.iloc[-1], low52.iloc[-1]
    s200 = slope200.iloc[-1]
    rs_row = rs_pct.reindex(c.columns)

    crit = {}
    crit['m1_close_above_150_200'] = (last > v150) & (last > v200)
    crit['m2_sma150_above_200'] = v150 > v200
    crit['m3_sma200_rising_1m'] = s200 > 0
    crit['m4_sma50_above_150_200'] = (v50 > v150) & (v50 > v200)
    crit['m5_close_above_sma50'] = last > v50
    crit['m6_30pct_above_52w_low'] = last >= l52 * config.MINERVINI_ABOVE_52W_LOW
    crit['m7_within_25pct_of_52w_high'] = last >= h52 * config.MINERVINI_FROM_52W_HIGH
    crit['m8_rs_ge_70'] = rs_row >= config.MINERVINI_MIN_RS

    out = pd.DataFrame({k: v.reindex(c.columns) for k, v in crit.items()})
    out.index.name = 'ticker'
    out['minervini_count'] = out[list(crit)].sum(axis=1).astype(int)
    out['rs_pct'] = rs_row.round(1)
    out['close'] = last
    out['pct_from_52w_high'] = (last / h52 - 1).mul(100).round(2)
    out['pct_above_52w_low'] = (last / l52 - 1).mul(100).round(2)
    out['sma200_slope_pct'] = s200.round(3)
    out['in_minervini'] = out['minervini_count'] >= config.MINERVINI_MIN_PASS
    return out


def leaders(evaluate_df: pd.DataFrame) -> pd.DataFrame:
    """The Minervini leaders' list."""
    return evaluate_df[evaluate_df['in_minervini']].copy()

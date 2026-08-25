"""
Focus metrics — volume + ADX filter columns (more_screeners.md Task 3).

Filter-shaped, per TAXONOMY.md: single formulas -> threshold-able columns,
no leaders flag. Sources (metaData_v1):
- volume_suite_components/volume_indicators.py: VROC (:29), ADTV (:41),
  MFI (:219)
- adx_report.py -> src/indicators/indicators_calculation.py::
  calculate_adx — Wilder RMA ADX/DMI, Joe Rabil's ADX(13,8) setup
  (atrMA=diMA=adxMA=RMA), "compute-only, no rule evaluation"

Columns (latest bar of wide matrices):
  vroc25       — (vol - vol[t-25]) / vol[t-25] * 100
  adtv_50      — 50d average daily volume in SHARES (NOT dollars —
                 adv50_dollar already covers the $ side; J3 resolved:
                 not a duplicate)
  mfi14        — Money Flow Index 0-100
  adx13, plus_di13, minus_di13 — Wilder-smoothed DMI

RVOL is intentionally NOT added again: Stockbee's `rel_volume_today`
(Task 1) is exactly RVOL(20) at the latest bar.

Wilder RMA note: the reference seeds with the SMA of the first `length`
valid values then recurses; pandas ewm(alpha=1/n, adjust=False) is the
same recursion seeded from the first value — differences decay
exponentially and the validate.py cross-check bounds them.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
import config


def _wilder_rma_df(series: pd.DataFrame, length: int) -> pd.DataFrame:
    """Wilder RMA over wide matrices (ewm form — see module docstring)."""
    return series.ewm(alpha=1.0 / length, adjust=False,
                      min_periods=length).mean()


def evaluate(high: pd.DataFrame, low: pd.DataFrame, close: pd.DataFrame,
             volume: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame(index=close.columns)
    out.index.name = 'ticker'

    # VROC (volume_indicators.py :29)
    n = config.VOLADX_VROC_PERIOD
    base = volume.shift(n)
    out['vroc25'] = ((volume.iloc[-1] - base.iloc[-1])
                     / base.iloc[-1].replace(0, np.nan) * 100).round(2)

    # ADTV (volume_indicators.py :41) — shares, 50d
    out['adtv_50'] = volume.rolling(
        config.VOLADX_ADTV_WINDOW,
        min_periods=config.VOLADX_ADTV_WINDOW).mean().iloc[-1].round(0)

    # MFI (volume_indicators.py :219)
    m = config.VOLADX_MFI_PERIOD
    tp = (high + low + close) / 3.0
    raw_flow = tp * volume
    pos_flow = raw_flow.where(tp > tp.shift(1), 0.0)
    neg_flow = raw_flow.where(tp < tp.shift(1), 0.0)
    pos_sum = pos_flow.rolling(m, min_periods=m).sum()
    neg_sum = neg_flow.rolling(m, min_periods=m).sum()
    money_ratio = pos_sum / neg_sum.replace(0, np.nan)
    out['mfi14'] = (100.0 - 100.0 / (1.0 + money_ratio)).iloc[-1].round(2)

    # ADX/DMI (calculate_adx, Rabil 13/13/8)
    atr_len, di_len, adx_len = (config.VOLADX_ATR_LEN, config.VOLADX_DI_LEN,
                                config.VOLADX_ADX_LEN)
    prev_close = close.shift(1)
    prev_high, prev_low = high.shift(1), low.shift(1)
    up_move = high - prev_high
    down_move = prev_low - low
    plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
    minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)

    a = high - low
    b = (high - prev_close).abs()
    c = (low - prev_close).abs()
    tr = pd.DataFrame(np.fmax(np.fmax(a.values, b.fillna(0).values),
                              c.fillna(0).values),
                      index=high.index, columns=high.columns)
    tr = tr.where(prev_close.notna(), a)

    atr = _wilder_rma_df(tr, atr_len)
    plus_di = 100.0 * _wilder_rma_df(plus_dm, di_len) / atr
    minus_di = 100.0 * _wilder_rma_df(minus_dm, di_len) / atr
    di_sum = plus_di + minus_di
    dx = 100.0 * (plus_di - minus_di).abs() / di_sum.where(di_sum != 0)
    adx = _wilder_rma_df(dx, adx_len)

    out['plus_di13'] = plus_di.iloc[-1].round(2)
    out['minus_di13'] = minus_di.iloc[-1].round(2)
    out['adx13'] = adx.iloc[-1].round(2)
    return out

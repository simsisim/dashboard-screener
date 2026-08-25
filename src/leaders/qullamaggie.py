"""
Leader filter — Qullamaggie Suite (more_screeners.md Task 5).

Source: metaData_v1/src/screeners/qullamaggie_suite.py (RS filter :226,
MA-stack :270, ATR-RS :315, range position :349). All thresholds in
config.py (QULLA_*), verbatim from that source.

Five conditions, all on the LATEST bar:
  1. RS >= 97 (cross-sectional percentile of momentum) on AT LEAST ONE
     horizon — 1w/5d, 1m/20d, 3m/60d, 6m/120d (source qualifies a
     ticker when ANY timeframe clears the bar)
  2. Perfect MA stack — Price >= EMA10 >= SMA20 >= SMA50 >= SMA100 >=
     SMA200 (SMA20/SMA100 are new columns this task adds)
  3. ATR-RS >= 50 — percentile rank of ATR(14) within the $1B+-cap
     universe (high ATR = big moves = Qullamaggie's tradability bar)
  4. Range position >= 50% — price in the upper half of its 20d range
  5. Market cap >= $1B

Outputs: `in_qullamaggie` bool + numerics (best RS, qualified horizons,
ATR-RS percentile, range position, MA-stack flag, ATR extension to
SMA50 — the source's sort key).
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
import config
from src import indicators


def evaluate(close: pd.DataFrame, high: pd.DataFrame, low: pd.DataFrame,
             atr14: pd.DataFrame, market_cap: pd.Series) -> pd.DataFrame:
    # 1) RS >= 97 on >= 1 horizon (percentile of n-bar momentum)
    rs_pct = {}
    for name, lb in config.QULLA_RS_HORIZONS.items():
        roc = indicators.roc(close, lb).iloc[-1]
        rs_pct[name] = indicators.cross_sectional_percentile(
            roc.to_frame().T).iloc[0]
    rs_df = pd.DataFrame(rs_pct)
    best_rs = rs_df.max(axis=1)
    qualified = rs_df.ge(config.QULLA_RS_THRESHOLD).fillna(False)
    n_qualified = qualified.sum(axis=1)
    qualified_names = qualified.apply(
        lambda r: '/'.join(rs_df.columns[r.values]), axis=1)

    # 2) perfect MA stack
    ema10 = indicators.ema(close, 10).iloc[-1]
    sma20 = indicators.sma(close, 20).iloc[-1]
    sma50 = indicators.sma(close, 50).iloc[-1]
    sma100 = indicators.sma(close, 100).iloc[-1]
    sma200 = indicators.sma(close, 200).iloc[-1]
    price = close.iloc[-1]
    ma_stack = ((price >= ema10) & (ema10 >= sma20) & (sma20 >= sma50)
                & (sma50 >= sma100) & (sma100 >= sma200))

    # 3) ATR-RS percentile within the $1B+ universe
    atr_last = atr14.iloc[-1]
    big = market_cap.reindex(close.columns) >= config.QULLA_MIN_MARKET_CAP
    atr_rank = pd.Series(np.nan, index=close.columns)
    if big.sum() > 1:
        atr_rank[big] = atr_last[big].rank(pct=True) * 100.0

    # 4) range position in the 20d range
    w = config.QULLA_RANGE_WINDOW
    hi20 = high.rolling(w, min_periods=w).max().iloc[-1]
    lo20 = low.rolling(w, min_periods=w).min().iloc[-1]
    rng = (hi20 - lo20).replace(0, np.nan)
    range_pos = (price - lo20) / rng

    # 5) market cap gate
    cap_ok = big.fillna(False)

    in_q = ((n_qualified >= 1) & ma_stack.fillna(False)
            & (atr_rank >= config.QULLA_ATR_RS_THRESHOLD)
            & (range_pos >= config.QULLA_RANGE_POSITION) & cap_ok)

    atr_ext_sma50 = (price - sma50) / atr_last.replace(0, np.nan)

    out = pd.DataFrame(index=close.columns)
    out.index.name = 'ticker'
    out['in_qullamaggie'] = in_q.fillna(False).astype(bool)
    out['qulla_rs_best'] = best_rs.round(1)
    out['qulla_qualified_timeframes'] = qualified_names.where(
        n_qualified > 0, '')
    out['qulla_ma_stack'] = ma_stack.fillna(False).astype(bool)
    out['qulla_atr_rs'] = atr_rank.round(1)
    out['qulla_range_position'] = range_pos.round(3)
    out['qulla_atr_ext_sma50'] = atr_ext_sma50.round(2)
    return out

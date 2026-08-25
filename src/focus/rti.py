"""
Focus metric d) — Range Tightening Indicator (intro.md 2d: TradingView
yaIeno72, "Range Tightening Indicator (RTI)" by Ollie_AllCaps).

RTI quantifies price volatility relative to recent price action to flag
low-volatility consolidations that often precede breakouts:
  RTI(N)  = SMA(high - low, N), normalized: / typical_price * 100
            (typical_price = (H+L+C)/3 — the normalization used by the
            project's own metaData_v1/src/screeners/rti_screener.py; the
            TradingView pine itself is dynamically loaded and could not be
            fetched, so the local verified implementation + the script's
            published description are the source of truth)
  N: 5 (short-term momentum), 15 (swing), 50 (longer term / custom default)
  Zones on RTI(50): 1: 0-5 extremely tight, 2: 5-10 low, 3: 10-15 moderate
  Orange dots: >= 2 consecutive bars with RTI(50) < 20
  Range expansion: RTI >= 2x its recent minimum after being <= 20
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
import config


def _rti_pct(high: pd.DataFrame, low: pd.DataFrame, close: pd.DataFrame,
             period: int) -> pd.DataFrame:
    typical = (high + low + close) / 3.0
    rng = (high - low).rolling(period, min_periods=period).mean()
    return rng / typical * 100.0


def evaluate(high: pd.DataFrame, low: pd.DataFrame, close: pd.DataFrame) -> pd.DataFrame:
    rti_s = _rti_pct(high, low, close, config.RTI_PERIODS['short'])
    rti_w = _rti_pct(high, low, close, config.RTI_PERIODS['swing'])
    rti_l = _rti_pct(high, low, close, config.RTI_PERIODS['long'])

    last_l = rti_l.iloc[-1]
    last_s = rti_s.iloc[-1]
    last_w = rti_w.iloc[-1]

    out = pd.DataFrame(index=close.columns)
    out.index.name = 'ticker'
    out['rti_short'] = last_s.round(2)
    out['rti_swing'] = last_w.round(2)
    out['rti'] = last_l.round(2)

    zone = pd.Series('—', index=close.columns, dtype=object)
    zone[last_l < config.RTI_ZONE3] = '3'
    zone[last_l < config.RTI_ZONE2] = '2'
    zone[last_l < config.RTI_ZONE1] = '1'
    out['rti_zone'] = zone

    # orange dots: >= 2 consecutive bars of RTI(50) < 20, ending today
    low_vol = rti_l < config.RTI_LOW_VOL
    prev1 = low_vol.shift(1, fill_value=False)
    out['rti_dots'] = bool_series(low_vol.iloc[-1] & prev1.iloc[-1])
    out['rti_low_vol_streak'] = _streak_len(low_vol).iloc[-1]

    # range expansion: current RTI(5) >= mult x its 50-bar min, after <= 20
    min50 = rti_s.rolling(50, min_periods=50).min()
    was_low = min50 <= config.RTI_LOW_VOL
    expansion = (last_s >= config.RTI_EXPANSION_MULT * min50.iloc[-1]) & was_low.iloc[-1]
    out['rti_expansion'] = bool_series(expansion)
    return out


def bool_series(s: pd.Series) -> pd.Series:
    """Coerce a possibly-object comparison result to a clean boolean Series."""
    return s.astype('boolean').fillna(False).astype(bool)


def _streak_len(low_vol: pd.DataFrame) -> pd.DataFrame:
    """Length of the current consecutive-True streak per cell (vectorized):
    cumsum minus the cumsum value at the last False, forward-filled."""
    cs = low_vol.cumsum()
    reset = cs.where(~low_vol).ffill().fillna(0)
    return (cs - reset).where(low_vol, 0)

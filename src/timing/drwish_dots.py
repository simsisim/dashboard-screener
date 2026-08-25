"""
Timing signals — Dr. Wish Blue Dot / Black Dot (feedback_4.md Task 1).

Source: metaData_v1/src/screeners/drwish_screener.py — params :51-64
(daily timeframe multiplier = 1.0, so the base defaults ARE the effective
values), stochastic :82-97, blue dot :314-360, black dot :361-418.
Thresholds in config.py (DRWISH_*), verbatim.

Blue Dot (latest bar): stochastic %K crossed UP through 20
  (yesterday < 20, today > 20) while the 50-day SMA is rising.
Black Dot (latest bar): %K printed at/below 25 within the last 3 bars,
  close > previous close, and trend confirmed (close > SMA30 OR
  close > EMA21).

Same-day snapshot shape (like Stockbee) — evaluated on the latest bar of
each ticker's own history. `evaluate` takes an explicit ticker list (the
scoped subset) per the on-demand architecture; each output row carries
`as_of` — that ticker's own last valid bar date (mixed-data transparency,
feedback_4 round decision).
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


def stochastic_k(high, low, close, period):
    """Source :82-97 — 100*(C - LL) / (HH - LL), doji -> 0."""
    ll = low.rolling(period, min_periods=period).min()
    hh = high.rolling(period, min_periods=period).max()
    denom = (hh - ll).replace(0, np.nan)
    return (100.0 * (close - ll) / denom).fillna(0.0)


def _last_valid_dates(frame: pd.DataFrame) -> pd.Series:
    """Each ticker's own last valid bar date (mixed-data transparency)."""
    as_of = frame.apply(lambda col: col.last_valid_index())
    as_of = pd.Series(as_of)
    as_of.index.name = 'ticker'
    return as_of


def evaluate(tickers: list, data: dict) -> pd.DataFrame:
    """
    tickers: the scoped subset (explicit argument — on-demand architecture).
    data: dict of wide OHLCV matrices (open/high/low/close/volume) already
    restricted to the scoped columns by the caller.
    """
    high, low, close = data['high'][tickers], data['low'][tickers], \
        data['close'][tickers]

    stoch = stochastic_k(high, low, close, config.DRWISH_STOCH_PERIOD)
    stoch_today = _last(stoch)
    stoch_prev = _last(stoch.shift(1))

    # Blue Dot
    sma_blue = indicators.sma(close, config.DRWISH_BLUE_SMA_PERIOD)
    sma_blue_rising = _last(sma_blue.diff() > 0)
    blue = ((stoch_prev < config.DRWISH_BLUE_STOCH_THRESHOLD)
            & (stoch_today > config.DRWISH_BLUE_STOCH_THRESHOLD)
            & sma_blue_rising)

    # Black Dot
    sma_black = _last(indicators.sma(close, config.DRWISH_BLACK_SMA_PERIOD))
    ema_black = _last(indicators.ema(close, config.DRWISH_BLACK_EMA_PERIOD))
    lb = config.DRWISH_BLACK_LOOKBACK
    stoch_lookback_min = stoch.iloc[-lb:].min()   # already per-ticker
    was_oversold = stoch_lookback_min <= config.DRWISH_BLACK_STOCH_THRESHOLD
    closing_higher = _last(close) > _last(close.shift(1))
    trend_confirmed = (_last(close) > sma_black) | (_last(close) > ema_black)
    black = was_oversold & closing_higher & trend_confirmed

    as_of = _last_valid_dates(close)

    out = pd.DataFrame(index=tickers)
    out.index.name = 'ticker'
    out['in_blue_dot'] = blue.fillna(False).astype(bool)
    out['in_black_dot'] = black.fillna(False).astype(bool)
    out['stoch_k'] = stoch_today.round(2)
    out['stoch_k_prev'] = stoch_prev.round(2)
    out['min_stoch_lookback'] = stoch_lookback_min.round(2)
    out['as_of'] = as_of.dt.strftime('%Y-%m-%d')
    return out

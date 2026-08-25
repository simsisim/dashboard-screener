"""
Shared vectorized indicators over wide Date×ticker matrices.

Every function here is a faithful port of a verified sibling implementation
(provenance cited per function); all operate on wide matrices so the whole
~4,000-ticker universe is processed at once.
"""
import numpy as np
import pandas as pd

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config


def sma(close: pd.DataFrame, n: int) -> pd.DataFrame:
    """Simple moving average (column-wise)."""
    return close.rolling(n, min_periods=n).mean()


def ema(close: pd.DataFrame, n: int) -> pd.DataFrame:
    """Exponential moving average (pandas ewm span, adjust=False — the
    convention used by test_scooter/sctr_model.py and yf-gics)."""
    return close.ewm(span=n, adjust=False).mean()


def wilder_atr(high: pd.DataFrame, low: pd.DataFrame, close: pd.DataFrame,
               period: int = config.ATR_PERIOD) -> pd.DataFrame:
    """
    Wilder-smoothed ATR, vectorized across columns.

    Port of metaData_v1/src/basic_calculations.py::calculate_atr_and_atrext
    Step 1-2 (TR = max(H-L, |H-Cprev|, |L-Cprev|); first ATR = SMA of first
    `period` TRs; then ATR_t = (ATR_prev*(period-1) + TR_t)/period), which is
    pandas ewm(alpha=1/period, adjust=False) on TR — algebraically identical,
    implemented here with ewm for speed. Arithmetic is numpy-based (no index
    alignment), so differently-named single-column frames are safe; a ticker's
    first valid bar uses TR = H - L (np.fmax skips the NaN prev-close terms).
    """
    h = high.to_numpy(dtype=float)
    l = low.to_numpy(dtype=float)
    c = close.to_numpy(dtype=float)
    prev_c = np.vstack([np.full((1, c.shape[1]), np.nan), c[:-1]])
    tr = np.fmax(np.fmax(h - l, np.abs(h - prev_c)), np.abs(l - prev_c))
    tr_df = pd.DataFrame(tr, index=high.index, columns=high.columns)
    return tr_df.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()


def atr_pct(close: pd.DataFrame, atr: pd.DataFrame) -> pd.DataFrame:
    """ATR as % of price (ALEX pine: atr_pct = atr/close*100)."""
    return atr / close * 100.0


def adr_pct(high: pd.DataFrame, low: pd.DataFrame, close: pd.DataFrame,
            period: int = config.ADR_PERIOD) -> pd.DataFrame:
    """
    Average Daily Range % — ALEX pine: adr_val = ta.sma(high-low, 20);
    adr_pct = adr_val/close*100. Same as StockScreenHero's "20d ADR %".
    Numpy-based (no column alignment), like wilder_atr.
    """
    rng = pd.DataFrame(high.to_numpy(dtype=float) - low.to_numpy(dtype=float),
                       index=high.index, columns=high.columns)
    return rng.rolling(period, min_periods=period).mean() / close * 100.0


def avg_dollar_volume(close: pd.DataFrame, volume: pd.DataFrame,
                      period: int = config.ADV_PERIOD) -> pd.DataFrame:
    """50d average dollar volume (StockScreenHero '50d Av. Dollar Volume')."""
    return (close * volume).rolling(period, min_periods=period).mean()


def avg_volume(close: pd.DataFrame, volume: pd.DataFrame,
               period: int = config.ADV_PERIOD) -> pd.DataFrame:
    return volume.rolling(period, min_periods=period).mean()


def rolling_high(close: pd.DataFrame, window: int = config.BARS_52W) -> pd.DataFrame:
    return close.rolling(window, min_periods=window).max()


def rolling_low(close: pd.DataFrame, window: int = config.BARS_52W) -> pd.DataFrame:
    return close.rolling(window, min_periods=window).min()


def roc(close: pd.DataFrame, n: int) -> pd.DataFrame:
    """Rate of change % (test_scooter/sctr_model.py::_roc)."""
    base = close.shift(n)
    return (close - base) / base.replace(0, np.nan) * 100.0


def rsi(close: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """Wilder RSI 0-100 (test_scooter/sctr_model.py::_rsi)."""
    delta = close.diff()
    gains = delta.clip(lower=0)
    losses = (-delta).clip(lower=0)
    avg_gain = gains.ewm(alpha=1.0 / period, adjust=False).mean()
    avg_loss = losses.ewm(alpha=1.0 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return rsi.where(avg_loss != 0, 100.0)


def slope_pct(series: pd.DataFrame, window: int) -> pd.DataFrame:
    """
    % change of a series over `window` bars — the yf-gics/lkm_rs
    _slope_pct((new/old - 1)*100), vectorized.
    """
    old = series.shift(window)
    return (series / old - 1.0) * 100.0


def rolling_linreg_slope(series: pd.DataFrame, n: int) -> pd.DataFrame:
    """
    Slope of the ordinary-least-squares linear regression of the series
    over a rolling window of n bars (x = 0..n-1, oldest -> newest), in
    series units per bar. Closed form via lag-weighted sums, so it is
    fully vectorized across tickers (no per-window Python loop):

        slope = (sum_p p*y_p - n*mean_x*mean_y) / (sum_p p^2 - n*mean_x^2)

    where p is the within-window position and sum_p p*y_p is expressed as
    a fixed-weight sum of lagged series. Used by the Golden Launch Pad
    screener (metaData_v1 gold_launch_pad.py uses scipy.stats.linregress
    per bar per ticker — same numbers, this is the vectorized form).
    """
    mean_x = (n - 1) / 2.0
    sum_p2 = (n - 1) * n * (2 * n - 1) / 6.0
    sum_y = series.rolling(n, min_periods=n).sum()
    # sum over lags s=0..n-1 of (n-1-s) * y_{t-s}  ==  sum_p p*y_p
    wsum = None
    for s in range(n):
        term = (n - 1 - s) * series.shift(s)
        wsum = term if wsum is None else wsum + term
    denom = sum_p2 - n * mean_x * mean_x
    return (wsum - mean_x * sum_y) / denom


def ibd_rs_raw(close: pd.DataFrame) -> pd.DataFrame:
    """
    IBD-style weighted multi-period RS blend (lkm_rs/common/rs_signal.py::
    ibd_rs_raw): weighted 3/6/9/12-month cumulative returns, most recent
    quarter double-weighted — config.IBD_RS_LOOKBACKS/WEIGHTS.
    """
    total = sum(config.IBD_RS_WEIGHTS)
    rs = None
    for lookback, weight in zip(config.IBD_RS_LOOKBACKS, config.IBD_RS_WEIGHTS):
        comp = roc(close, lookback)
        rs = comp * (weight / total) if rs is None else rs + comp * (weight / total)
    return rs


def cross_sectional_percentile(raw: pd.DataFrame, scale: float = 100.0) -> pd.DataFrame:
    """Percentile rank of each row across tickers (0..scale)."""
    return raw.rank(axis=1, pct=True) * scale


def pct_vs_ma(close: pd.DataFrame, ma: pd.DataFrame) -> pd.DataFrame:
    """(close/ma - 1)*100 — 'Price vs Xema/Xsma' dashboard columns."""
    return (close / ma - 1.0) * 100.0


def pct_from_52w_high(close: pd.DataFrame, high52: pd.DataFrame) -> pd.DataFrame:
    return (close / high52 - 1.0) * 100.0


def pct_from_52w_low(close: pd.DataFrame, low52: pd.DataFrame) -> pd.DataFrame:
    return (close / low52 - 1.0) * 100.0


def momentum(close: pd.DataFrame) -> dict:
    """Price % gains over the dashboard windows (5d/1m/3m/6m)."""
    return {name: roc(close, n) for name, n in config.MOMENTUM_WINDOWS.items()}

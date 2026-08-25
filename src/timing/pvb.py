"""
Timing signal — PVB price-volume breakout state machine (feedback_4.md
Task 2).

Source: metaData_v1/src/screeners/pvb_screener.py::
_generate_pvb_TWmodel_signals (indicator layer :29-66 is plain rolling
math; the signal layer :68-160 is a per-ticker STATE MACHINE — a Buy
persists until a Sell fires or 5 consecutive closes below the SMA trigger
"Close Buy"; symmetric for Sell). Parameters from metaData_v1's runtime
config (user_data.csv): 30/30/50, close_threshold 5.

State transitions (Long and Short, evaluated per bar):
  Buy        — close > PREV Price_Highest AND volume > PREV Volume_Highest
               AND close > SMA AND state != Buy
  Sell       — close < PREV Price_Lowest AND volume > PREV Volume_Highest
               AND close < SMA AND state != Sell
  Close Buy  — while Buy: 5 consecutive closes < SMA
  Close Sell — while Sell: 5 consecutive closes > SMA

Outputs (latest bar per ticker): `pvb_signal` (Buy / Sell / Close Buy /
Close Sell / No Signal), `pvb_days_since_signal`, `pvb_signal_price`,
`pvb_performance_since_signal`, `pvb_signal_date`, `as_of` (the ticker's
own last valid bar date — mixed-data transparency).

On-demand module: `evaluate` takes an explicit ticker list (the scoped
subset); NOT part of run_screeners.py's daily batch.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
import config
from src import indicators


def evaluate(tickers: list, data: dict) -> pd.DataFrame:
    close = data['close'][tickers]
    open_ = data['open'][tickers]
    high = data['high'][tickers]
    low = data['low'][tickers]
    volume = data['volume'][tickers]

    pbp = config.PVB_PRICE_BREAKOUT_PERIOD
    vbp = config.PVB_VOLUME_BREAKOUT_PERIOD
    tll = config.PVB_TRENDLINE_LENGTH
    thr = config.PVB_CLOSE_THRESHOLD

    price_high = high.rolling(pbp, min_periods=pbp).max()
    price_low = low.rolling(pbp, min_periods=pbp).min()
    vol_high = volume.rolling(vbp, min_periods=vbp).max()
    sma = indicators.sma(close, tll)

    states = []
    for t in tickers:
        c = close[t].to_numpy(dtype=float)
        o = open_[t].to_numpy(dtype=float)
        ph = price_high[t].to_numpy(dtype=float)
        pl = price_low[t].to_numpy(dtype=float)
        vh = vol_high[t].to_numpy(dtype=float)
        s = sma[t].to_numpy(dtype=float)
        idx = close[t].index

        signal = "No Signal"
        sig_i = None
        consec = 0
        for i in range(1, len(c)):
            if np.isnan(s[i]) or np.isnan(ph[i - 1]):
                continue
            if (not np.isnan(ph[i - 1])
                    and c[i] > ph[i - 1]
                    and not np.isnan(vh[i - 1])
                    and volume[t].iloc[i] > vh[i - 1]
                    and c[i] > s[i]
                    and signal != "Buy"):
                signal, sig_i, consec = "Buy", i, 0
            elif (not np.isnan(pl[i - 1])
                  and c[i] < pl[i - 1]
                  and not np.isnan(vh[i - 1])
                  and volume[t].iloc[i] > vh[i - 1]
                  and c[i] < s[i]
                  and signal != "Sell"):
                signal, sig_i, consec = "Sell", i, 0

            if signal == "Buy":
                consec = consec + 1 if c[i] < s[i] else 0
                if consec >= thr:
                    signal, sig_i, consec = "Close Buy", i, 0
            elif signal == "Sell":
                consec = consec + 1 if c[i] > s[i] else 0
                if consec >= thr:
                    signal, sig_i, consec = "Close Sell", i, 0

        states.append((t, signal, sig_i))

    rows = []
    for t, signal, sig_i in states:
        c_arr = close[t]
        last_valid = c_arr.last_valid_index()
        price = c_arr.loc[last_valid] if last_valid is not None else np.nan
        if sig_i is not None:
            sig_date = c_arr.index[sig_i]
            days_since = c_arr.index.get_loc(last_valid) - sig_i \
                if last_valid is not None else np.nan
            sig_price = c_arr.iloc[sig_i]
            perf = (price / sig_price - 1.0) * 100.0 if sig_price else np.nan
        else:
            sig_date, days_since, sig_price, perf = None, np.nan, np.nan, np.nan
        rows.append({
            'ticker': t, 'pvb_signal': signal,
            'pvb_days_since_signal': days_since,
            'pvb_signal_price': sig_price,
            'pvb_performance_since_signal': round(perf, 2) if not np.isnan(perf) else np.nan,
            'pvb_signal_date': sig_date.strftime('%Y-%m-%d') if sig_date is not None else None,
            'as_of': last_valid.strftime('%Y-%m-%d') if last_valid is not None else None,
        })

    out = pd.DataFrame(rows).set_index('ticker')
    out.index.name = 'ticker'
    return out

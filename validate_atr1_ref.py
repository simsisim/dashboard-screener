"""ATR1 reference check — run by validate.py in an isolated subprocess.

Computes the ATR cloud (vStop/vStop2/uptrend/crosses) AND the
days_since_signal/signal_type "last crossover" fields for a few tickers
with metaData_v1's atr1_screener.py (the authoritative port — both the
low-level calculate_atr_cloud this project's vol_stop_np already matched,
and the higher-level atr1_screener() wrapper whose signal-scan logic was
ported into atr1_cloud.py's evaluate() this session) so this project's
atr1_cloud.py can be compared against it."""
import json
import sys

import pandas as pd

sys.path.insert(0, '/home/imagda/_invest2024/python/metaData_v1')
from src.screeners.atr1_screener import calculate_atr_cloud, atr1_screener  # noqa: E402

CUR = '/home/imagda/_invest2024/python/downloadData_v1/data/market_data/daily/current'
ARCH = '/home/imagda/_invest2024/python/downloadData_v1/data/market_data/daily/archive'

TICKERS = ['AAPL', 'MSFT', 'QMCO']


def _load(t):
    parts = []
    for base in (ARCH, CUR):
        try:
            parts.append(pd.read_csv(f'{base}/{t}.csv', low_memory=False))
        except FileNotFoundError:
            pass
    df = pd.concat(parts).drop_duplicates(subset='Date').sort_values('Date')
    df['Date'] = pd.to_datetime(df['Date'], utc=True, errors='coerce')
    df = df.dropna(subset=['Date'])
    df['Date'] = df['Date'].dt.tz_localize(None).dt.normalize()
    df = df.set_index('Date')[['Open', 'High', 'Low', 'Close', 'Volume']]
    return df.apply(pd.to_numeric, errors='coerce').dropna()


def main():
    out = {}
    batch = {}
    for t in TICKERS:
        df = _load(t)
        batch[t] = df
        r = calculate_atr_cloud(df, length=20, factor=3.0, length2=20,
                                factor2=1.5, src='Close', src2='Close')
        out[t] = {'vStop': float(r['vStop'].iloc[-1]),
                  'vStop2': float(r['vStop2'].iloc[-1]),
                  'uptrend': bool(r['uptrend'].iloc[-1]),
                  'crossUp': bool(r['crossUp'].iloc[-1]),
                  'crossDn': bool(r['crossDn'].iloc[-1])}

    # cap_history_data=0 disables the 252-bar optimization so this scans
    # the same full history atr1_cloud.py's evaluate() does
    screened = atr1_screener(batch, params={
        'length': 20, 'factor': 3.0, 'length2': 20, 'factor2': 1.5,
        'src': 'Close', 'src2': 'Close', 'min_volume': 0, 'min_price': 0,
        'cap_history_data': 0,
    })
    by_ticker = {r['ticker']: r for r in screened}
    for t in TICKERS:
        r = by_ticker.get(t, {})
        out[t]['signal_type'] = r.get('signal_type')
        out[t]['signal_date'] = r['signal_date'].strftime('%Y-%m-%d') \
            if r.get('signal_date') is not None else None
        out[t]['days_since_signal'] = r.get('days_since_signal')
        out[t]['price_change_pct'] = r.get('price_change_pct')

    print(json.dumps(out))


if __name__ == '__main__':
    main()

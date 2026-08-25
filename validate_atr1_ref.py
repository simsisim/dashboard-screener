"""ATR1 reference check — run by validate.py in an isolated subprocess.

Computes the ATR cloud (vStop/vStop2/uptrend/crosses) for a few tickers
with metaData_v1's atr1_screener.py (the authoritative port) so this
project's atr1_cloud.py can be compared against it."""
import json
import sys

import pandas as pd

sys.path.insert(0, '/home/imagda/_invest2024/python/metaData_v1')
from src.screeners.atr1_screener import calculate_atr_cloud  # noqa: E402

CUR = '/home/imagda/_invest2024/python/downloadData_v1/data/market_data/daily/current'
ARCH = '/home/imagda/_invest2024/python/downloadData_v1/data/market_data/daily/archive'


def main():
    out = {}
    for t in ['AAPL', 'MSFT', 'QMCO']:
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
        df = df.apply(pd.to_numeric, errors='coerce').dropna()
        r = calculate_atr_cloud(df, length=20, factor=3.0, length2=20,
                                factor2=1.5, src='Close', src2='Close')
        out[t] = {'vStop': float(r['vStop'].iloc[-1]),
                  'vStop2': float(r['vStop2'].iloc[-1]),
                  'uptrend': bool(r['uptrend'].iloc[-1]),
                  'crossUp': bool(r['crossUp'].iloc[-1]),
                  'crossDn': bool(r['crossDn'].iloc[-1])}
    print(json.dumps(out))


if __name__ == '__main__':
    main()

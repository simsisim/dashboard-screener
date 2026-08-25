"""GLB reference check — run by validate.py in an isolated subprocess.

Computes historical GLB records with metaData_v1's drwish_screener (the
authoritative port) so this project's glb.py can be compared against it."""
import json
import sys

import pandas as pd

sys.path.insert(0, '/home/imagda/_invest2024/python/metaData_v1')
from src.screeners.drwish_screener import DrWishCalculator  # noqa: E402

CUR = '/home/imagda/_invest2024/python/downloadData_v1/data/market_data/daily/current'
ARCH = '/home/imagda/_invest2024/python/downloadData_v1/data/market_data/daily/archive'


def main():
    scr = DrWishCalculator({'timeframe': 'daily'})
    out = {}
    for t in ['AAPL', 'MSFT']:
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
        records = scr.calculate_historical_glb_levels(df)
        out[t] = [{'level': round(r['glb_level'], 3),
                   'detection': r['detection_date'].strftime('%Y-%m-%d'),
                   'confirmed': r['is_confirmed'],
                   'broken': r['is_broken']} for r in records]
    print(json.dumps(out))


if __name__ == '__main__':
    main()

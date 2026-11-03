"""
One-off: QQQ daily bars before downloadData_v1's first day (2020-01-02), for
Reversal Odds' 10-year window (docs/reversal_odds_plan.md). Everything from
2020 on still comes from downloadData_v1; src/reversal_odds.py joins the two.

    python3 fetch_qqq_history.py

Keeps the first overlap day so the loader can line the price levels up.
"""
from pathlib import Path

import yfinance as yf

OUT = Path(__file__).resolve().parent / 'data_history' / 'QQQ_pre2020.csv'
START, OVERLAP = '2005-01-01', '2020-01-03'     # end is exclusive

df = yf.download('QQQ', start=START, end=OVERLAP, auto_adjust=True, progress=False)
df.columns = df.columns.get_level_values(0)
df = df[['Open', 'High', 'Low', 'Close', 'Volume']].rename_axis('Date')
OUT.parent.mkdir(exist_ok=True)
df.to_csv(OUT)
print(f'{OUT}: {len(df)} rows, {df.index[0]:%Y-%m-%d} -> {df.index[-1]:%Y-%m-%d}')

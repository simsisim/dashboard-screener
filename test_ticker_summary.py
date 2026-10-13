"""
Unit suite for src/ticker_summary.py (TODO.md item 7).

Runnable, like test_top_movers.py:
    python3 test_ticker_summary.py       # PASS/FAIL summary, exit 0/1

Covers: price/trend wording (52w-high edge), Confluence status + badge
gained/lost from a temp history.db, HVE/HV1Y lines (same-day merge,
pending next day, earnings + gap held), index-rank tone, earnings text,
and that missing data never raises.
"""
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from src import ticker_summary as ts  # noqa: E402
from src.history_db import HistoryDB  # noqa: E402

PASS, FAIL = 'PASS', 'FAIL'
results = []


def check(name, ok, detail=''):
    results.append((PASS if ok else FAIL, name, detail))


row = pd.Series({
    'close': 100.0, 'daily_gain_pct': -1.25, 'gain_5d': 4.0, 'gain_1m': 10.0,
    'gain_3m': np.nan, 'pct_from_52w_high': 0.0, 'stage': '2A',
    'minervini_count': 8, 'gmma_state': 'bullish', 'rs_pct': 91.0,
    'scooter_score': 88.0, 'in_minervini': True, 'in_scooter': False,
    'hve_date': '2026-10-08', 'hve_bars_since': 2, 'hve_1st_dch_pct': 6.0,
    'hve_2nd_dch_pct': 1.0, 'hve_since_record_pct': 2.5,
    'hve_gap_held': True, 'hve_earnings': True,
    'hv1y_date': '2026-10-08', 'hv1y_bars_since': 2,
})

pt = ts.price_trend(row)
check('price: at the 52w high, gain_3m skipped',
      any('At its 52-week high' in l for l in pt)
      and '3 months' not in pt[0] and '−1.2%' in pt[0], str(pt))

vt = ts.volume_text(row)
check('volume: recent HVE on earnings, gap held, HV1Y same day merged',
      'on an earnings day' in vt[0] and 'gap held' in vt[0]
      and vt[1] == 'It is also the 1-year volume high.', str(vt))
pend = row.copy()
pend['hve_bars_since'], pend['hve_2nd_dch_pct'] = 0, np.nan
v2 = ts.volume_text(pend)[0]
check('volume: record on the latest bar -> no "next" text',
      'the latest session' in v2 and 'next' not in v2, v2)

with tempfile.TemporaryDirectory() as tmp:
    db = HistoryDB(Path(tmp) / 'h.db')
    cf = lambda n, b: pd.DataFrame(        # noqa: E731
        {'n_families': [n], 'n_badges': [len(b)], 'confluence_score': [0.0],
         'families': [['trend_rs'] * n], 'badges': [b]}, index=['XYZ'])
    db.write_confluence('2026-10-06', cf(3, ['MM', 'SC', 'NrH']))
    db.write_confluence('2026-10-07', cf(3, ['MM', 'SC', 'NrH']))
    db.write_confluence('2026-10-08', cf(3, ['MM', 'NrH']))
    db.write_confluence('2026-10-09', cf(1, ['MM']))
    ct = ts.confluence_text('XYZ', row, db)
    check('confluence: today from the row + "just dropped below" (3 -> 2)',
          ct[0].startswith('Today: **2 families** (MM, GMMA, RS90, NrH)')
          and 'just dropped below' in ct[0], ct[0])
    one = ts.confluence_text('XYZ', pd.Series({'in_minervini': True}), db)
    check('confluence: singular "1 family"',
          one[0].startswith('Today: **1 family** (MM)'), one[0])
    check('confluence: 3 of 4 sessions at >= 3',
          '**3 of 4**' in ct[1], ct[1])
    check('confluence: lost SC after 10-07, NrH after 10-08',
          any(l == 'Lost SC after 10-07, NrH after 10-08.' for l in ct), str(ct))

    db.write_movers(pd.DataFrame({
        'snapshot_date': ['2026-10-08', '2026-10-09'] * 2,
        'index_code': ['SP500'] * 4,
        'symbol': ['XYZ', 'XYZ', 'AAA', 'AAA'],
        'change_pct': [2.0, -1.0, 1.0, 3.0],
        'rank_top': [1, 2, 2, 1], 'rank_bottom': [2, 1, 1, 2]}))
    rt = ts.ranking_text('XYZ', db)
    check('ranking: tone + best/worst day',
          'S&P 500' in rt[0] and 'best 10-08 (+2.0%)' in rt[0]
          and 'worst 10-09 (−1.0%)' in rt[0], str(rt))
    check('ranking: not in any index',
          ts.ranking_text('NOPE', db) == ['Not in the S&P 500 or NASDAQ 100 lists.'])

fin = pd.Series({'qh1_date': '2026-08-26', 'qh1_eps': 2.22,
                 'qh1_eps_estimate': 2.09, 'qh1_surprise_pct': 6.16,
                 'qh1_eps_growth_yoy': 1.114, 'next_earnings_date': '2026-11-17',
                 'next_earnings_is_estimate': True,
                 'last_updated': '2026-10-13 11:20:00'})
et = ts.earnings_text(fin)
check('earnings: EPS vs estimate, surprise, YoY, estimated next date',
      'EPS 2.22 vs 2.09' in et[0] and '+6.2% surprise' in et[0]
      and '+111%' in et[0] and '(estimated)' in et[1], str(et))

try:
    secs = ts.build('XYZ', pd.Series({'close': 5.0}), None, None)
    ok = [t for t, _ in secs][0] == 'Price & trend'
except Exception as e:                          # noqa: BLE001
    ok, secs = False, e
check('build: a nearly empty row and no db/fundamentals never raises', ok,
      str(secs))

for status, name, detail in results:
    print(f'{status}  {name}' + (f'\n      {detail}' if status == FAIL and detail else ''))
n_fail = sum(r[0] == FAIL for r in results)
print(f'\n{len(results) - n_fail}/{len(results)} passed')
sys.exit(1 if n_fail else 0)

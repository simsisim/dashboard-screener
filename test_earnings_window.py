"""
Unit suite for src/earnings_window.py (around-earnings chart).

Runnable, like test_ticker_summary.py:
    python3 test_earnings_window.py      # PASS/FAIL summary, exit 0/1

Synthetic bars + report dates: report-date parsing (newest first, dupes,
next_earnings_date), day-0 session (weekend, future), the % path from the
start day, the average over earlier complete windows only, an upcoming
report's partial path, HV1Y/HVE record days, and that the chart builds.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from src import earnings_window as ew  # noqa: E402

PASS, FAIL = 'PASS', 'FAIL'
results = []


def check(name, ok, detail=''):
    results.append((PASS if ok else FAIL, name, detail))


idx = pd.bdate_range('2025-01-01', periods=300)
close = pd.Series(100.0 + np.arange(300), index=idx)     # +1 per bar
daily = pd.DataFrame({'Close': close, 'Volume': 1_000.0}, index=idx)

fin = pd.Series({'next_earnings_date': None,
                 'qh1_date': f'{idx[250]:%Y-%m-%d}',
                 'qh2_date': f'{idx[190]:%Y-%m-%d}',
                 'qh3_date': f'{idx[130]:%Y-%m-%d}',
                 'qh4_date': f'{idx[130]:%Y-%m-%d}',      # duplicate
                 'qh5_date': f'{idx[10]:%Y-%m-%d}',       # window before data
                 'q1_date': '2030-01-01'})                # not a report col
rep = ew.report_dates(fin)
check('report_dates: unique, newest first, q*_date ignored',
      rep == [idx[250], idx[190], idx[130], idx[10]], str(rep))
check('report_dates: no fundamentals -> []', ew.report_dates(None) == [])

sat = idx[100] + pd.Timedelta(days=(5 - idx[100].weekday()) % 7)
check('day0_pos: a weekend date -> the next session',
      idx[ew.day0_pos(idx, sat)] > sat
      and idx[ew.day0_pos(idx, sat)].weekday() == 0)
fut = idx[-1] + pd.offsets.BDay(3)
check('day0_pos: future date counted in business days',
      ew.day0_pos(idx, fut) == len(idx) - 1 + 3, str(ew.day0_pos(idx, fut)))

av = ew.available(daily, rep, before=20)
check('available: drops a report whose window starts before the data',
      [d for d, _ in av] == rep[:3], str(av))

b = ew.build(daily, rep, 0, n_avg=4, anchor=-20, before=20, after=20)
cur = b['current']
check('build: current = newest report, path 0 at the start day',
      b['report'] == idx[250] and cur.at[-20, 'pct'] == 0, str(b['report']))
exp = (close.iloc[270] / close.iloc[230] - 1) * 100
check('build: day +20 = close vs the start close',
      abs(cur.at[20, 'pct'] - exp) < 1e-9, f'{cur.at[20, "pct"]} vs {exp}')
check('build: average uses only the 2 earlier reports',
      b['n_used'] == 2, str(b['n_used']))
a20 = np.mean([(close.iloc[p + 20] / close.iloc[p - 20] - 1) * 100
               for p in (190, 130)])
check('build: average path = mean of their % paths',
      abs(b['avg'].at[20] - a20) < 1e-9, f'{b["avg"].at[20]} vs {a20}')
b1 = ew.build(daily, rep, 0, n_avg=1, anchor=-1, before=20, after=20)
check('build: n_avg caps the quarters, anchor moves the zero',
      b1['n_used'] == 1 and b1['current'].at[-1, 'pct'] == 0
      and b1['avg'].at[-1] == 0)
b0 = ew.build(daily, rep, 0, n_avg=0, before=20, after=20)
check('build: n_avg 0 -> no average', b0['n_used'] == 0 and b0['avg'].empty)
check('build: which past the list -> None',
      ew.build(daily, rep, 5, before=20, after=20) is None)

# upcoming report 5 sessions ahead: path stops at day -6
up = ew.report_dates(pd.Series({'next_earnings_date':
                                f'{idx[-1] + pd.offsets.BDay(5):%Y-%m-%d}',
                                'qh1_date': f'{idx[250]:%Y-%m-%d}'}))
bu = ew.build(daily, up, 0, n_avg=1, before=20, after=20)
last_day = bu['current']['pct'].dropna().index[-1]
check('build: upcoming report -> partial path up to the last bar',
      bu['report'] > idx[-1] and last_day == -5 and bu['n_used'] == 1,
      f'last day {last_day}')

vol = pd.Series(1_000.0, index=idx)
vol.iloc[260] = 5_000.0
vol.iloc[100] = 9_000.0          # inside the first year: no HV1Y yet
rd = ew.record_days(daily.assign(Volume=vol), hve_dates=[f'{idx[260]:%Y-%m-%d}'])
check('record_days: HV1Y needs a full year, HVE wins on the same day',
      idx[100] not in rd.index and rd.get(idx[260]) == 'HVE', str(rd.head()))

try:
    spec = ew.chart(b, rd, 'TEST').to_dict()
    ok = 'vconcat' in spec
except Exception as e:                          # noqa: BLE001
    ok, spec = False, e
check('chart: builds a valid Altair spec (records + average)', ok, str(spec)[:200])
try:
    ew.chart(bu, None, 'TEST').to_dict()
    ok = True
except Exception as e:                          # noqa: BLE001
    ok = e
check('chart: partial path, no records', ok is True, str(ok))

for status, name, detail in results:
    print(f'{status}  {name}' + (f'\n      {detail}' if status == FAIL and detail else ''))
n_fail = sum(r[0] == FAIL for r in results)
print(f'\n{len(results) - n_fail}/{len(results)} passed')
sys.exit(1 if n_fail else 0)

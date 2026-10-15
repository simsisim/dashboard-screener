"""
Unit suite for src/growth_cycle.py (TODO.md §6).

Runnable, like test_ticker_summary.py:
    python3 test_growth_cycle.py         # PASS/FAIL summary, exit 0/1

Calibration against PrimeTrading's public Growth Cycle readings (needs the
real IWF / IWD files in downloadData_v1), plus synthetic checks of the
partial-week structure and the zone rules.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from src import growth_cycle as gc  # noqa: E402

PASS, FAIL = 'PASS', 'FAIL'
results = []


def check(name, ok, detail=''):
    results.append((PASS if ok else FAIL, name, detail))


# --- synthetic: partial-week structure ---------------------------------
idx = pd.bdate_range('2026-01-05', periods=15)      # 3 weeks, Mon..Fri
s = pd.Series(np.arange(1.0, 16.0), index=idx)
up = gc._weekly_ema(s, 'max', 10)
a = 2 / 11
w1 = 5.0                                             # week 1 high
check('structure: first week = its running high', up.iloc[2] == 3.0, str(up.iloc[:5]))
check('structure: week 2 Tue = a*7 + (1-a)*EMA(week 1)',
      abs(up.iloc[6] - (a * 7 + (1 - a) * w1)) < 1e-12, str(up.iloc[6]))

# --- calibration on real data -------------------------------------------
try:
    data = gc.load_inputs()
    m = gc.compute(gc.ratio_bars(data))
except Exception as e:                               # noqa: BLE001
    m = None
    check('real data loads', False, repr(e))

if m is not None and m.index.max() >= pd.Timestamp('2026-10-13'):
    r = m.loc
    check('upper line Oct 6-8 = his 0.4989',
          all(abs(r[d, 'upper'] - 0.4989) < 0.0003
              for d in ('2026-10-06', '2026-10-07', '2026-10-08')),
          str(m.loc['2026-10-06':'2026-10-08', 'upper'].round(4).tolist()))
    # open: ours runs 0.35-0.6% above his lower line (upper is exact)
    check('lower line Oct 6 within 0.75% of his 0.4857',
          abs(r['2026-10-06', 'lower'] / 0.4857 - 1) < 0.0075,
          f"{r['2026-10-06', 'lower']:.4f}")
    check('risk-on since Sep 18 (risk-off on Sep 17)',
          not r['2026-09-17', 'risk_on']
          and r['2026-10-08', 'gate_since'] == pd.Timestamp('2026-09-18'),
          str(r['2026-10-08', 'gate_since']))
    check('momentum Oct 6 ≈ his +0.73σ',
          abs(r['2026-10-06', 'momentum_sigma'] - 0.73) < 0.1,
          f"{r['2026-10-06', 'momentum_sigma']:.2f}")
    check('momentum 9/28 ≈ his +1.86σ (±0.2)',
          abs(r['2026-09-28', 'momentum_sigma'] - 1.86) < 0.2,
          f"{r['2026-09-28', 'momentum_sigma']:.2f}")
    check('stretch 9/28 ≈ his +1.27σ (±0.15)',
          abs(r['2026-09-28', 'stretch_sigma'] - 1.27) < 0.15,
          f"{r['2026-09-28', 'stretch_sigma']:.2f}")
    for day, n in (('2026-09-28', 7), ('2026-10-06', 13), ('2026-10-08', 15)):
        check(f'{day}: Ramp Up, day {n}',
              r[day, 'zone'] == 'Ramp Up' and r[day, 'day_in_zone'] == n,
              f"{r[day, 'zone']} day {r[day, 'day_in_zone']}")
    check('Oct 9: Reload, risk-on intact',
          r['2026-10-09', 'zone'] == 'Reload' and r['2026-10-09', 'risk_on'],
          r['2026-10-09', 'zone'])
    check('Ramp Up went straight to Reload (no Trim / Hold Sep 18 - Oct 13)',
          not m.loc['2026-09-18':'2026-10-13', 'zone'].isin(['Trim', 'Hold']).any(),
          str(m.loc['2026-09-18':'2026-10-13', 'zone'].value_counts().to_dict()))
    check('Oct 13: still risk-on, momentum cooled (< 0)',
          r['2026-10-13', 'risk_on'] and r['2026-10-13', 'momentum_sigma'] < 0,
          f"{r['2026-10-13', 'momentum_sigma']:.2f}")
    st = gc.zone_stats(m, data['close']['QQEW'], '2022-01-01')
    check('zone stats: all six zones, days add up',
          list(st.index) == list(gc.ZONES)
          and st.days.sum() == len(m.loc['2022-01-01':]), str(st.days.to_dict()))
elif m is not None:
    check('real data reaches 2026-10-13', False, str(m.index.max()))

for status, name, detail in results:
    print(f'{status}  {name}' + (f'\n      {detail}' if status == FAIL and detail else ''))
n_fail = sum(r[0] == FAIL for r in results)
print(f'\n{len(results) - n_fail}/{len(results)} passed')
sys.exit(1 if n_fail else 0)

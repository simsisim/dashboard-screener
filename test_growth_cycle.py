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

# --- synthetic: midline, dead-band, Trim vs Hold -------------------------
mid = gc._weekly_ema(s, 'last', 10)
check('midline: week 2 Tue = a*today + (1-a)*EMA(week 1 close)',
      abs(mid.iloc[6] - (a * 7 + (1 - a) * 5.0)) < 1e-12, str(mid.iloc[6]))

rs = np.random.default_rng(7)
_n = 300
_i = pd.bdate_range('2024-01-01', periods=_n)
_c = pd.Series(np.exp(np.cumsum(rs.normal(0.0005, 0.006, _n))) * 0.5, index=_i)
_b = pd.DataFrame({'O': _c, 'H': _c * 1.002, 'L': _c * 0.998, 'C': _c})
_m = gc.compute(_b)
_ms = _m.momentum_sigma
_b_ = gc.config.GC_MOM_BAND
check('dead-band: past the band sets the side',
      _m.rising[_ms > _b_].all() and not _m.rising[_ms < -_b_].any())
_flat = _m.index[_m.mom_flat][_m.mom_flat.values.nonzero()[0] > 0]
check('dead-band: inside the band keeps the last side',
      len(_flat) > 0 and all(
          _m.rising.iloc[_m.index.get_loc(d)] == _m.rising.iloc[_m.index.get_loc(d) - 1]
          for d in _flat), f'{len(_flat)} flat days')
_x = _m.risk_on & (_m.ext_sigma > gc.config.GC_EXTENDED)
_hot = _m.stretch_sigma > gc.config.GC_TRIM_STRETCH
check('extended: Trim = stretch past +2σ, Hold otherwise, either momentum',
      _x.any() and (_m.zone[_x & _hot] == 'Trim').all()
      and (_m.zone[_x & ~_hot] == 'Hold').all(), str(_m.zone[_x].value_counts().to_dict()))
check('not extended: never Trim / Hold',
      not _m.zone[~_x].isin(['Trim', 'Hold']).any())

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
    # open: ours runs 0.1-0.25% above his lower line (upper is exact)
    for day, low in (('2026-10-09', 0.4865), ('2026-10-14', 0.4869),
                     ('2026-10-30', 0.4753)):
        check(f'lower line {day} within 0.25% of his {low}',
              abs(r[day, 'lower'] / low - 1) < 0.0025, f"{r[day, 'lower']:.4f}")
    check('risk-on since Sep 18 (risk-off on Sep 17)',
          not r['2026-09-17', 'risk_on']
          and r['2026-10-08', 'gate_since'] == pd.Timestamp('2026-09-18'),
          str(r['2026-10-08', 'gate_since']))
    for day, gap, prev in (('2026-10-09', 2.2, 2.8), ('2026-10-14', -0.8, 3.0),
                           ('2026-10-30', -5.3, -3.1)):
        check(f'{day}: midline gap ≈ his {gap:+}% (10 sessions earlier {prev:+}%)',
              abs(r[day, 'gap_pct'] - gap) < 0.15
              and abs(r[day, 'gap_prev_pct'] - prev) < 0.3,
              f"{r[day, 'gap_pct']:.2f} / {r[day, 'gap_prev_pct']:.2f}")
    for day, sig in (('2026-09-28', 1.86), ('2026-10-06', 0.73), ('2026-10-08', 0.25),
                     ('2026-10-09', -0.02), ('2026-10-14', -1.08), ('2026-10-30', -0.60)):
        check(f'{day}: momentum ≈ his {sig:+}σ (±0.12)',
              abs(r[day, 'momentum_sigma'] - sig) < 0.12,
              f"{r[day, 'momentum_sigma']:.2f}")
    for day, sig in (('2026-09-28', 1.27), ('2026-10-09', 0.42), ('2026-10-14', -0.91),
                     ('2026-10-30', -2.27)):
        check(f'{day}: stretch ≈ his {sig:+}σ (±0.1)',
              abs(r[day, 'stretch_sigma'] - sig) < 0.1, f"{r[day, 'stretch_sigma']:.2f}")
    for day, sig in (('2026-10-09', 0.44), ('2026-10-14', 0.0), ('2026-10-30', -1.91)):
        check(f'{day}: gate ≈ his {sig:+}σ (±0.1)',
              abs(r[day, 'gate_sigma'] - sig) < 0.1, f"{r[day, 'gate_sigma']:.2f}")
    for day, z, n in (('2026-09-28', 'Ramp Up', 7), ('2026-10-06', 'Ramp Up', 13),
                      ('2026-10-08', 'Ramp Up', 15), ('2026-10-09', 'Ramp Up', 16),
                      ('2026-10-14', 'Reload', 3), ('2026-10-30', 'Risk-off', 11)):
        check(f'{day}: {z}, day {n}',
              r[day, 'zone'] == z and r[day, 'day_in_zone'] == n,
              f"{r[day, 'zone']} day {r[day, 'day_in_zone']}")
    check('Oct 9: momentum flat, held rising (his board)',
          r['2026-10-09', 'mom_flat'] and r['2026-10-09', 'rising'])
    check('risk-off since Oct 16 (Oct 15 still risk-on)',
          r['2026-10-15', 'risk_on']
          and r['2026-10-30', 'gate_since'] == pd.Timestamp('2026-10-16'),
          str(r['2026-10-30', 'gate_since']))
    check('Ramp Up went straight to Reload (no Trim / Hold Sep 18 - Oct 13)',
          not m.loc['2026-09-18':'2026-10-13', 'zone'].isin(['Trim', 'Hold']).any(),
          str(m.loc['2026-09-18':'2026-10-13', 'zone'].value_counts().to_dict()))
    # his cards, Oct 30 close: same window (last 1144 sessions, from Apr 11 2022)
    m30 = m.loc[:'2026-10-30']
    st = gc.zone_stats(m30, data['close']['QQEW'], gc.config.GC_HISTORY_SESSIONS)
    check('zone stats: window starts Apr 11 2022 at Oct 30, as on his board',
          m30.tail(gc.config.GC_HISTORY_SESSIONS).index[0] == pd.Timestamp('2022-04-11'),
          str(m30.tail(gc.config.GC_HISTORY_SESSIONS).index[0]))
    check('zone stats: all six zones, days add up',
          list(st.index) == list(gc.ZONES)
          and st.days.sum() == gc.config.GC_HISTORY_SESSIONS, str(st.days.to_dict()))
    for z, days, won in (('Risk-off', 299, 46), ('Probe', 195, 50), ('Ramp Up', 222, 65),
                         ('Trim', 81, 57), ('Hold', 104, 53), ('Reload', 243, 58)):
        check(f'{z}: days within 12 of his {days}, growth won within 6 of his {won}%',
              abs(st.days[z] - days) <= 12 and abs(st.growth_won_pct[z] - won) <= 6,
              f'{st.days[z]} days, won {st.growth_won_pct[z]:.0f}%')
    # next download: Nov 2 close (ratio 0.4481, band 0.4703-0.4862)
    if m.index.max() >= pd.Timestamp('2026-11-02'):
        check('Nov 2: Risk-off day 12', r['2026-11-02', 'zone'] == 'Risk-off'
              and r['2026-11-02', 'day_in_zone'] == 12)
        check('Nov 2: momentum ≈ his -0.92σ, stretch ≈ his -2.52σ',
              abs(r['2026-11-02', 'momentum_sigma'] + 0.92) < 0.12
              and abs(r['2026-11-02', 'stretch_sigma'] + 2.52) < 0.1,
              f"{r['2026-11-02', 'momentum_sigma']:.2f} / "
              f"{r['2026-11-02', 'stretch_sigma']:.2f}")
elif m is not None:
    check('real data reaches 2026-10-13', False, str(m.index.max()))

for status, name, detail in results:
    print(f'{status}  {name}' + (f'\n      {detail}' if status == FAIL and detail else ''))
n_fail = sum(r[0] == FAIL for r in results)
print(f'\n{len(results) - n_fail}/{len(results)} passed')
sys.exit(1 if n_fail else 0)

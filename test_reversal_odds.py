"""
Unit suite for src/reversal_odds.py (docs/reversal_odds_plan.md).

    python3 test_reversal_odds.py         # PASS/FAIL summary, exit 0/1

Synthetic checks of the rules, plus calibration on his Nov 2 2026 board. Nov 2
is added by hand while downloadData_v1 still ends before it.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import config  # noqa: E402
from src import reversal_odds as ro  # noqa: E402

results = []


def check(name, ok, detail=''):
    results.append(('PASS' if ok else 'FAIL', name, detail))


# --- synthetic: state rules, trigger ------------------------------------
rs = np.random.default_rng(11)
n = 2200
idx = pd.bdate_range('2015-01-01', periods=n)
c = pd.Series(np.exp(np.cumsum(rs.normal(0.0003, 0.012, n))) * 100, index=idx)
syn = pd.DataFrame({'O': c, 'H': c * 1.006, 'L': c * 0.994, 'C': c})
m = ro.compute(syn)
cut = config.REV_CUT
check('state: Reversal = stretched down with 50 above 200',
      (m.state[(m.z <= -cut) & m.above] == 'Reversal').all()
      and ((m.z <= -cut) & m.above).any())
check('state: Probe = stretched down with 50 below 200',
      (m.state[(m.z <= -cut) & ~m.above] == 'Probe').all()
      and ((m.z <= -cut) & ~m.above).any())
check('state: Extended only with 50 above 200',
      not (m.state[~m.above] == 'Extended').any())
check('state: quiet days are Trend / Risk-off',
      (m.state[(m.z.abs() < cut) & m.above] == 'Trend').all()
      and (m.state[(m.z.abs() < cut) & ~m.above] == 'Risk-off').all())
x_at = (m.trigger - m.ema) / m.atr
check('trigger: stretch at the trigger price sits on the cut',
      (((x_at - m.x_mean) / m.x_std + cut).abs() < 1e-9).all())
_w = config.REV_WEEKLY_EMA
config.REV_WEEKLY_EMA = 30
_m2 = ro.compute(syn)
config.REV_WEEKLY_EMA = _w
check('weekly gauge never decides a state',
      (_m2.state == m.state).all() and not _m2.z_w.equals(m.z_w))

# --- join ---------------------------------------------------------------
bars, full = ro.load_bars()
check('history: pre-2020 file joined', full and bars.index[0].year == 2005,
      str(bars.index[0]))
check('history: dates unique and sorted',
      bars.index.is_unique and bars.index.is_monotonic_increasing)
_j = bars.C.pct_change().loc['2020-01-02']
check('history: no jump at the join (2020-01-02 move ≈ real +1.67%)',
      abs(_j * 100 - 1.67) < 0.1, f'{_j * 100:.2f}%')

# --- calibration: his Nov 2 board ---------------------------------------
D = pd.Timestamp('2026-11-02')
if bars.index.max() < D and bars.index.max() >= pd.Timestamp('2026-10-30'):
    bars = pd.concat([bars.loc[:'2026-10-30'], pd.DataFrame(
        {'O': 695.32, 'H': 699.43, 'L': 680.33, 'C': 681.09}, index=[D])])
if bars.index.max() >= D:
    m = ro.compute(bars.loc[:D])
    t = m.loc[D]
    check('Nov 2: Reversal, flagged 2 sessions',
          t.state == 'Reversal' and t.state_day == 2, f'{t.state} {t.state_day}')
    check('Nov 2: stretch ≈ his -2.30σ', abs(t.z + 2.30) < 0.05, f'{t.z:.2f}')
    check('Nov 2: trigger ≈ his 691.98', abs(t.trigger - 691.98) < 1.0, f'{t.trigger:.2f}')
    check('Nov 2: percentile ≈ his 2nd', abs(t.pct - 2) < 1.5, f'{t.pct:.1f}')
    check('Nov 2: regime ≈ his +6.6%, day 343 (±1)',
          abs(t.regime_pct - 6.6) < 0.1 and abs(t.regime_day - 343) <= 1,
          f'{t.regime_pct:.2f} day {t.regime_day}')
    check('Nov 2: weekly gauge ≈ his -1.71σ', abs(t.z_w + 1.71) < 0.05, f'{t.z_w:.2f}')
    fs, base = ro.flag_stats(m)
    check('flags: Reversal N = his 43 (±2)', abs(fs.n['Reversal'] - 43) <= 2, str(fs.n['Reversal']))
    check('flags: Probe N ≈ his 17 (±2)', abs(fs.n['Probe'] - 17) <= 2, str(fs.n['Probe']))
    check('flags: Extended N ≈ his 18 (±5)', abs(fs.n['Extended'] - 18) <= 5, str(fs.n['Extended']))
    check('baseline ≈ his +1.54% / +4.65%, up 65% / 71%',
          abs(base['fwd20'] - 1.54) < 0.15 and abs(base['fwd60'] - 4.65) < 0.25
          and abs(base['up20'] - 65) < 2 and abs(base['up60'] - 71) < 2, str(base))
    rg = ro.regime_stats(m)
    check('regime: 50 above 200 ≈ his 1690 sessions, 21.0% CAGR, -29% DD',
          abs(rg.sessions.iloc[0] - 1690) <= 15 and abs(rg.cagr.iloc[0] - 21) < 1
          and abs(rg.max_dd.iloc[0] + 29) < 1, rg.iloc[0].round(1).to_string())
else:
    check('real data reaches 2026-10-30', False, str(bars.index.max()))

for status, name, detail in results:
    print(f'{status}  {name}' + (f'\n      {detail}' if status == 'FAIL' and detail else ''))
n_fail = sum(r[0] == 'FAIL' for r in results)
print(f'\n{len(results) - n_fail}/{len(results)} passed')
sys.exit(1 if n_fail else 0)

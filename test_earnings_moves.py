"""
Unit suite for src/focus/earnings_moves.py (💥 Earnings Moves tab).

Runnable, like test_earnings_window.py:
    python3 test_earnings_moves.py      # PASS/FAIL summary, exit 0/1

Synthetic bars for three tickers: an after-close report (reaction = the
session after, bigger volume), a before-open report with a gap down, and a
ticker with no report but a shock bar. Checks the reaction-day rule, gap /
day / volume multiple / close strength, gap held + stop held in both
directions, the lookback window, the PVB trigger and shock-bar counting.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import config  # noqa: E402
from src.focus import earnings_moves as em  # noqa: E402

PASS, FAIL = 'PASS', 'FAIL'
results = []


def check(name, ok, detail=''):
    results.append((PASS if ok else FAIL, name, detail))


N = 120
idx = pd.bdate_range('2026-01-01', periods=N)
T = ['UP', 'DN', 'NEWS']
c = pd.DataFrame(100.0, index=idx, columns=T)
o, h, l = c.copy(), c + 1, c - 1
v = pd.DataFrame(1_000.0, index=idx, columns=T)

# UP: report after the close on bar 100 -> reaction on bar 101:
# gap +8% (open 108), close 110 near the high 111, low 107, volume 5x
c.loc[idx[101]:, 'UP'] = 110.0
o.loc[idx[101], 'UP'], h.loc[idx[101], 'UP'], l.loc[idx[101], 'UP'] = \
    108.0, 111.0, 107.0
h.loc[idx[102]:, 'UP'], l.loc[idx[102]:, 'UP'] = 111.0, 109.0
o.loc[idx[102]:, 'UP'] = 110.0
v.loc[idx[101], 'UP'] = 5_000.0

# DN: report before the open on bar 110 -> reaction on bar 110: gap -10%
# (open 90), close 88 at the low; later bar 115 trades above its high
c.loc[idx[110]:, 'DN'] = 88.0
o.loc[idx[110], 'DN'], h.loc[idx[110], 'DN'], l.loc[idx[110], 'DN'] = \
    90.0, 91.0, 88.0
o.loc[idx[111]:, 'DN'] = 88.0
h.loc[idx[111]:, 'DN'], l.loc[idx[111]:, 'DN'] = 89.0, 87.0
h.loc[idx[115], 'DN'] = 92.0          # above the reaction high, not the gap
v.loc[idx[110], 'DN'] = 3_000.0
# an older DN report outside the 60-bar window must be ignored
old_dn = idx[20]

# NEWS: no report, a +6% gap on 4.5x volume at bar 118 (shock bar)
c.loc[idx[118]:, 'NEWS'] = 107.0
o.loc[idx[118], 'NEWS'], h.loc[idx[118], 'NEWS'], l.loc[idx[118], 'NEWS'] = \
    106.0, 108.0, 105.0
o.loc[idx[119], 'NEWS'], h.loc[idx[119], 'NEWS'], l.loc[idx[119], 'NEWS'] = \
    107.0, 108.0, 106.5
v.loc[idx[118], 'NEWS'] = 4_500.0

data = {'open': o, 'high': h, 'low': l, 'close': c, 'volume': v}
er = pd.DataFrame({'qh1_date': [f'{idx[100]:%Y-%m-%d}',
                                f'{idx[110]:%Y-%m-%d}', None],
                   'qh2_date': [None, f'{old_dn:%Y-%m-%d}', None]},
                  index=T)
out = em.evaluate(data, er, lookback=60)

u = out.loc['UP']
check('reaction day: after-close report -> the session after (bigger vol)',
      u['em_date'] == f'{idx[101]:%Y-%m-%d}' and u['em_day'] == 1
      and u['em_report_date'] == f'{idx[100]:%Y-%m-%d}', str(u['em_date']))
check('gap % / day % / bars since',
      abs(u['em_gap_pct'] - 8.0) < 1e-9 and abs(u['em_day_pct'] - 10.0) < 1e-9
      and u['em_bars_since'] == N - 1 - 101,
      f'{u["em_gap_pct"]} {u["em_day_pct"]} {u["em_bars_since"]}')
check('vol × avg = 5 (vs the 50 bars before)', abs(u['em_vol_x'] - 5) < 1e-9,
      str(u['em_vol_x']))
check('close strength: 110 in 107..111 = 75%',
      abs(u['em_close_str_pct'] - 75) < 1e-9, str(u['em_close_str_pct']))
check('gap up: gap held + stop held, PVB trigger',
      bool(u['em_gap_held']) and bool(u['em_low_held']) and bool(u['em_pvb']))

d = out.loc['DN']
check('before-open report -> day 0; older report outside the window ignored',
      d['em_date'] == f'{idx[110]:%Y-%m-%d}' and d['em_day'] == 0,
      str(d['em_date']))
check('gap down: close strength mirrored (closed at the low = 100%)',
      abs(d['em_close_str_pct'] - 100) < 1e-9 and d['em_gap_pct'] < 0,
      str(d['em_close_str_pct']))
check('gap down: gap held, stop broken by a high above the day’s high',
      bool(d['em_gap_held']) and not bool(d['em_low_held']))

n = out.loc['NEWS']
check('no report -> no em row', pd.isna(n['em_date']))
check('shock bar: +6% gap on 4.5x volume, counted once',
      n['sb_date'] == f'{idx[118]:%Y-%m-%d}' and n['sb_count'] == 1
      and abs(n['sb_gap_pct'] - 6) < 1e-9, str(n[['sb_date', 'sb_count']]))
check('UP is also a shock bar (8% gap, 5x vol); DN is (10%, 3x) not',
      out.at['UP', 'sb_count'] == 1 and out.at['DN', 'sb_count'] == 0)

short = em.evaluate(data, er, lookback=5)
check('lookback 5: only events in the last 5 bars',
      short['em_date'].isna().all() and short.at['NEWS', 'sb_count'] == 1)

last = pd.DataFrame({'qh1_date': [f'{idx[-1]:%Y-%m-%d}']}, index=['UP'])
lt = em.evaluate(data, last, lookback=60).loc['UP']
check('reaction on the latest bar: gap/stop held = NA, day 0',
      lt['em_day'] == 0 and pd.isna(lt['em_gap_held'])
      and pd.isna(lt['em_low_held']))
check('no earnings frame never raises',
      em.evaluate(data, None, lookback=60)['em_date'].isna().all())
check('config: shock-bar thresholds are metaVolume’s (4x, 5%)',
      config.SB_VOL_MULT == 4.0 and config.SB_GAP_MIN_PCT == 5.0)

for status, name, detail in results:
    print(f'{status}  {name}' + (f'\n      {detail}' if status == FAIL and detail else ''))
n_fail = sum(r[0] == FAIL for r in results)
print(f'\n{len(results) - n_fail}/{len(results)} passed')
sys.exit(1 if n_fail else 0)

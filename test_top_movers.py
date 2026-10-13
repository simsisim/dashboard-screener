"""
Unit suite for src/leaders/top_movers.py + src/history_db.py
(docs/top_movers_plan.md).

Runnable, like test_confluence.py:
    python3 test_top_movers.py       # PASS/FAIL summary, exit 0/1

Covers:
  1. % change vs previous close, top/bottom ranks, alphabetical tie-break
  2. a session below MOVERS_MIN_COVERAGE is skipped; a missing bar -> no row
  3. members missing from the price matrix are ignored
  4. write_movers / write_hits replace a session (idempotent re-run)
  5. repeat_table: hits, hit rate, streak, avg change
  6. index_membership keeps first_seen / extends last_seen
  7. write_confluence / confluence_window
"""
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import config  # noqa: E402
from src.history_db import HistoryDB, repeat_table  # noqa: E402
from src.leaders import top_movers  # noqa: E402

PASS, FAIL = 'PASS', 'FAIL'
results = []


def check(name, ok, detail=''):
    results.append((PASS if ok else FAIL, name, detail))


def _close():
    """4 sessions × 4 tickers. Day 2: AAA +10, BBB -5, CCC +10 (tie with
    AAA), DDD 0. Day 3: DDD has no bar. Day 4: only AAA has a bar."""
    idx = pd.to_datetime(['2026-10-05', '2026-10-06', '2026-10-07',
                          '2026-10-08'])
    return pd.DataFrame({
        'AAA': [100.0, 110.0, 121.0, 133.1],
        'BBB': [100.0, 95.0, 95.0, np.nan],
        'CCC': [50.0, 55.0, 55.0, np.nan],
        'DDD': [20.0, 20.0, np.nan, np.nan],
    }, index=idx)


# 1-3: evaluate
config.MOVERS_MIN_COVERAGE = 0.75
members = {'IX': ['AAA', 'BBB', 'CCC', 'DDD', 'ZZZ_NO_DATA'][:4],
           'IY': ['AAA', 'BBB', 'ZZZ_NO_DATA']}
df = top_movers.evaluate(_close(), members)
d2 = df[(df.snapshot_date == '2026-10-06') & (df.index_code == 'IX')] \
    .set_index('symbol')
check('pct change vs previous close',
      np.isclose(d2.loc['AAA', 'change_pct'], 10.0)
      and np.isclose(d2.loc['BBB', 'change_pct'], -5.0), d2.to_string())
check('top rank: tie broken alphabetically (AAA before CCC)',
      d2.loc['AAA', 'rank_top'] == 1 and d2.loc['CCC', 'rank_top'] == 2)
check('bottom rank: biggest loser = 1', d2.loc['BBB', 'rank_bottom'] == 1)
check('first session has no change -> no rows',
      not (df.snapshot_date == '2026-10-05').any())
d3 = df[(df.snapshot_date == '2026-10-07') & (df.index_code == 'IX')]
check('missing bar -> no row, session kept at 3/4 coverage',
      sorted(d3.symbol) == ['AAA', 'BBB', 'CCC'], str(sorted(d3.symbol)))
check('session below coverage skipped (1 of 4)',
      not ((df.snapshot_date == '2026-10-08') & (df.index_code == 'IX')).any())
check('coverage counts members without prices (IY: 2 of 3 < 75%)',
      not (df.index_code == 'IY').any())
config.MOVERS_MIN_COVERAGE = 0.6
iy = top_movers.evaluate(_close(), {'IY': members['IY']})
check('member without prices ignored',
      set(iy.symbol) == {'AAA', 'BBB'} and len(iy) == 4, iy.to_string())
config.MOVERS_MIN_COVERAGE = 0.75
check('sessions=N keeps only the last N dates',
      set(top_movers.evaluate(_close(), members, sessions=2).snapshot_date)
      == {'2026-10-07'})

# 4-6: db round trip
with tempfile.TemporaryDirectory() as tmp:
    db = HistoryDB(Path(tmp) / 'h.db')
    db.write_movers(df)
    db.write_movers(df)                       # re-run: no duplicates
    top = db.movers('2026-10-06', 'IX', 2, 'top')
    check('write_movers idempotent + movers() top N',
          top.symbol.tolist() == ['AAA', 'CCC'], top.to_string())

    flags = pd.DataFrame({'in_x': [True, False], 'in_y': [True, True]},
                         index=['AAA', 'BBB'])
    db.write_hits('2026-10-06', flags)
    db.write_hits('2026-10-06', flags.iloc[:1])   # replaces the session
    hits = db.repeat_hits('y', 5)
    check('write_hits replaces the session; screen name without in_',
          hits.symbol.tolist() == ['AAA'] and db.screens() == ['x', 'y'],
          hits.to_string())

    cf = pd.DataFrame({'n_families': [3, 0], 'n_badges': [4, 0],
                       'confluence_score': [40.0, 0.0],
                       'families': [['trend_rs', 'breakout', 'timing'], []],
                       'badges': [['MM', 'SC', '52H', 'PVB'], []]},
                      index=['AAA', 'BBB'])
    db.write_confluence('2026-10-06', cf)
    db.write_confluence('2026-10-06', cf)          # re-run replaces
    db.write_confluence('2026-10-07', cf)
    rows, sess = db.confluence_window(1)
    check('write_confluence: no-badge tickers skipped, window = last N runs',
          sess == ['2026-10-07'] and rows.symbol.tolist() == ['AAA']
          and rows.families.iloc[0] == 'trend_rs,breakout,timing',
          rows.to_string())

    db.write_membership('2026-10-06', {'IX': ['AAA']})
    db.write_membership('2026-10-01', {'IX': ['AAA']})
    db.write_membership('2026-10-07', {'IX': ['AAA']})
    m = db._query('SELECT first_seen, last_seen FROM index_membership')
    check('membership first/last seen', m.iloc[0].tolist()
          == ['2026-10-01', '2026-10-07'], m.to_string())

sessions = ['2026-10-09', '2026-10-08', '2026-10-07', '2026-10-06']
rows = pd.DataFrame({
    'snapshot_date': ['2026-10-09', '2026-10-08', '2026-10-06',
                      '2026-10-08', '2026-10-01'],
    'symbol': ['AAA', 'AAA', 'AAA', 'BBB', 'BBB'],
    'change_pct': [4.0, 2.0, 6.0, -3.0, 9.0],
})
rep = repeat_table(rows, sessions).set_index('symbol')
check('repeat: hits / streak / avg (out-of-window row ignored)',
      rep.loc['AAA', ['hits', 'streak']].tolist() == [3, 2]
      and np.isclose(rep.loc['AAA', 'avg_change_pct'], 4.0)
      and rep.loc['BBB', ['hits', 'streak']].tolist() == [1, 0]
      and rep.loc['AAA', 'hit_rate'] == 75.0, rep.to_string())
check('repeat: most hits first', rep.index.tolist() == ['AAA', 'BBB'])

for status, name, detail in results:
    print(f'{status}  {name}' + (f'\n      {detail}' if status == FAIL and detail else ''))
n_fail = sum(r[0] == FAIL for r in results)
print(f'\n{len(results) - n_fail}/{len(results)} passed')
sys.exit(1 if n_fail else 0)

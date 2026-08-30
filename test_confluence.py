"""
Unit suite for src/confluence.py (IMPLEMENTATION_PLAN.md §19).

Runnable, like validate.py / test_dashboard_app.py:
    python3 test_confluence.py       # PASS/FAIL summary, exit 0/1

Covers what test_dashboard_app.py (UI) does not:
  1. each badge test fires on exactly the right rows
  2. n_badges / n_families / confluence_score maths (family cap at 2)
  3. `extra` (opportunistic on-demand) merge is null-safe
  4. a missing source column -> badge unlit, no raise
  5. rank(): most-confluent first, tie-breaks
  6. guard: every batch badge's source column exists in the live
     screener_results.csv (column-rename regression — feedback_5 class)
"""
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from src import confluence  # noqa: E402

PASS, FAIL = 'PASS', 'FAIL'
results = []


def check(name, ok, detail=''):
    results.append((PASS if ok else FAIL, name, detail))


def _synthetic():
    """4 tickers, hand-placed flags:
      AAA: MM+KQ+SC+GLP+GMMA+RS90 (6 badges, ALL trend_rs) -> 1 family
      BBB: MM (trend_rs) + ON (fund) + ADL (accum) + 52H (breakout) -> 4 fam
      CCC: nothing
      DDD: RS90 only -> 1 family
    """
    idx = pd.Index(['AAA', 'BBB', 'CCC', 'DDD'], name='ticker')
    z = pd.Series(False, index=idx)
    df = pd.DataFrame(index=idx)
    df['in_minervini'] = [True, True, False, False]
    df['in_qullamaggie'] = [True, False, False, False]
    df['in_scooter'] = [True, False, False, False]
    df['in_gold_launch_pad'] = [True, False, False, False]
    df['gmma_state'] = ['bullish', 'bearish', 'transitioning', 'bearish']
    df['rs_pct'] = [95.0, 40.0, 10.0, 92.0]
    df['in_canslim'] = [False, True, False, False]
    df['in_cantata'] = z
    df['in_adl_accumulation'] = [False, True, False, False]
    df['in_volume_anomaly'] = z
    df['in_9m_movers'] = z
    df['in_weekly_movers'] = z
    df['in_daily_gainers'] = z
    df['in_52w_high_breakout'] = [False, True, False, False]
    df['pct_from_52w_high'] = [-40.0, -50.0, -60.0, -70.0]  # none within 5%
    df['in_ema20_pullback'] = z
    df['in_downtrend_reversal'] = z
    df['stage'] = ['2B', '1', '4', '2A']
    df['rti_zone'] = ['1', '2', np.nan, '1']
    df['scooter_score'] = [99.0, 50.0, 10.0, 88.0]
    return df


def main():
    df = _synthetic()
    c = confluence.compute(df)

    # 1. badge tests
    check('badge MM fires on AAA,BBB', list(c['bdg_MM']) == [1, 1, 0, 0])
    check('badge GMMA only on bullish', list(c['bdg_GMMA']) == [1, 0, 0, 0])
    check('badge RS90 on AAA,DDD (>=90)', list(c['bdg_RS90']) == [1, 0, 0, 1])
    check('badge NrH unlit (none within 5%)', c['bdg_NrH'].sum() == 0)

    # 2. counts + family cap
    row = c.loc['AAA']
    check('AAA n_badges = 6', int(row['n_badges']) == 6, str(row['n_badges']))
    check('AAA n_families = 1 (all trend_rs)', int(row['n_families']) == 1,
          str(row['families']))
    # score: trend_rs capped at 2 of 6 -> 2 / (2*6) * 100 = 16.7
    check('AAA confluence_score family-capped ~16.7',
          abs(row['confluence_score'] - 16.7) < 0.1, str(row['confluence_score']))
    rb = c.loc['BBB']
    check('BBB n_families = 4', int(rb['n_families']) == 4, str(rb['families']))
    check('BBB score = 4/12*100 = 33.3',
          abs(rb['confluence_score'] - 33.3) < 0.1, str(rb['confluence_score']))
    check('CCC empty', int(c.loc['CCC']['n_badges']) == 0
          and c.loc['CCC']['badges'] == [])

    # context tags (stage 2x + RTI zone), never counted
    check('AAA context = stage 2B + RTI z1',
          c.loc['AAA']['context'] == ['stage 2B', 'RTI z1'],
          str(c.loc['AAA']['context']))
    check('CCC context empty (stage 4, no rti)',
          c.loc['CCC']['context'] == [], str(c.loc['CCC']['context']))

    # 3. extra merge — null-safe, adds a breakout badge to AAA
    extra = {'DB': pd.Series([True, False, False, False], index=df.index),
             'C&H': None}  # None must not raise
    c2 = confluence.compute(df, extra)
    check('extra DB lights AAA breakout family',
          int(c2.loc['AAA']['n_families']) == 2
          and 'breakout' in c2.loc['AAA']['families'],
          str(c2.loc['AAA']['families']))
    check('extra None value tolerated', c2.loc['AAA']['bdg_C&H'] == 0)

    # 4. missing source column -> unlit, no raise
    thin = df.drop(columns=['in_qullamaggie', 'gmma_state'])
    c3 = confluence.compute(thin)
    check('missing columns -> badges unlit, no raise',
          c3['bdg_KQ'].sum() == 0 and c3['bdg_GMMA'].sum() == 0)

    # 5. rank
    r = confluence.rank(c, 'n_families')
    check('rank: BBB (4 fam) first', r.index[0] == 'BBB', str(list(r.index)))
    check('rank: tie AAA vs DDD broken by scooter (AAA 99 > DDD 88)',
          list(r.index).index('AAA') < list(r.index).index('DDD'))

    # 6. guard — live screener_results.csv still has every batch source col
    date_dirs = [d for d in (ROOT / 'results').iterdir()
                 if d.is_dir() and re.fullmatch(r'\d{4}-\d{2}-\d{2}', d.name)
                 and (d / 'screener_results.csv').exists()]
    if date_dirs:
        live = pd.read_csv(sorted(date_dirs)[-1] / 'screener_results.csv', nrows=5)
        missing = [c for c in confluence.BATCH_SOURCE_COLS
                   if c not in live.columns]
        check('guard: all batch badge source columns present in latest run',
              not missing, f'missing: {missing}')
    else:
        check('guard: latest run present', False, 'no results/YYYY-MM-DD found')

    print()
    ok_all = True
    for status, name, detail in results:
        print(f'[{status}] {name}  ({detail})')
        ok_all &= status == PASS
    print(f'\n{sum(s == PASS for s, _, _ in results)}/{len(results)} '
          f'confluence checks passed')
    sys.exit(0 if ok_all else 1)


if __name__ == '__main__':
    main()

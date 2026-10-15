"""
Unit suite for src/sr_panels.py (Market Health → Sustainability Ratio).

Runnable, like test_growth_cycle.py:
    python3 test_sr_panels.py            # PASS/FAIL summary, exit 0/1

Covers: gap adjustment == market_charts' loop (SR_v1.pine), ratio / no-gaps
panels, MA overlays + status line, editor-row cleaning, layout save/load,
every built-in preset resolving on real data.
"""
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from src import sr_panels as srp  # noqa: E402

PASS, FAIL = 'PASS', 'FAIL'
results = []


def check(name, ok, detail=''):
    results.append((PASS if ok else FAIL, name, detail))


def loop_reference(close, open_, start):
    """market_charts/src/gap_adjust.py, verbatim logic."""
    c, o, d = close.to_numpy(float), open_.to_numpy(float), close.index
    adj, cum = c.copy(), 0.0
    for i in range(1, len(c)):
        if d[i] >= pd.Timestamp(start):
            cum += o[i] - c[i - 1]
        adj[i] = c[i] - cum
    return pd.Series(adj, index=close.index)


rng = np.random.default_rng(7)
idx = pd.bdate_range('2025-01-01', periods=300)
close = pd.Series(100 + rng.normal(0, 1, 300).cumsum(), index=idx)
open_ = close.shift(1).fillna(100) + rng.normal(0, 0.5, 300)
for start in (idx[0], idx[120]):
    diff = (srp.gap_adjust(close, open_, start)
            - loop_reference(close, open_, start)).abs().max()
    check(f'gap_adjust == market_charts loop (start {start:%Y-%m-%d})',
          diff < 1e-9, f'max diff {diff}')
check('gap_adjust: unchanged before the start date',
      (srp.gap_adjust(close, open_, idx[120]).iloc[:120] == close.iloc[:120]).all())

data = {'close': pd.DataFrame({'A': close, 'B': close * 0 + 50}),
        'open': pd.DataFrame({'A': open_, 'B': close * 0 + 50})}
r = srp.panel_series({'type': 'Ratio', 'a': 'A', 'b': 'B'}, data, idx[0])
check('ratio = A / B', np.allclose(r, close / 50))
check('missing ticker -> None',
      srp.panel_series({'type': 'Ticker', 'a': 'ZZZ', 'b': ''}, data, idx[0]) is None)
df = srp.with_mas(close)
check('MAs: SMA200 from bar 200, EMA21 from bar 1',
      df['SMA200'].iloc[198:].notna().sum() == 101 and df['EMA21'].notna().all())
st_line = srp.status(df)
check('status line names each MA + 1W / 1M',
      all(m in st_line for m in ('EMA21', 'SMA200', '1W', '1M')), st_line)

rows = [{'type': 'Ticker', 'a': ' spy ', 'b': 'x'}, {'type': 'Ratio', 'a': 'xly', 'b': ''},
        {'type': 'Ratio', 'a': 'xly', 'b': 'xlp'}, {'type': None, 'a': 'QQQ', 'b': None},
        {'type': 'Ratio no gaps', 'a': 'IWD', 'b': 'IWF'}]
check('clean_panels: trims, upper-cases, drops incomplete rows',
      srp.clean_panels(rows) == [{'type': 'Ticker', 'a': 'SPY', 'b': ''},
                                 {'type': 'Ratio', 'a': 'XLY', 'b': 'XLP'},
                                 {'type': 'Ratio no gaps', 'a': 'IWD', 'b': 'IWF'}],
      str(srp.clean_panels(rows)))

with tempfile.TemporaryDirectory() as tmp:
    srp.MY_LAYOUTS = Path(tmp)
    p = srp.save_layout('my test/1', rows)
    check('save/load layout round-trips (unsafe chars replaced)',
          p.name == 'my test_1.json' and srp.list_layouts() == ['my test_1']
          and srp.load_layout('my test_1') == srp.clean_panels(rows), p.name)

# real data: every preset resolves (all tickers in downloadData_v1)
_all = sorted({t for ps in srp.PRESETS.values() for t in srp.tickers_of(ps)})
real = srp.load(_all)
bad = [f'{name}: {srp.label(pn)}' for name, ps in srp.PRESETS.items() for pn in ps
       if srp.panel_series(pn, real, real['close'].index[-504]) is None]
check('every built-in preset panel has data', not bad, '; '.join(bad))

for status, name, detail in results:
    print(f'{status}  {name}' + (f'\n      {detail}' if status == FAIL and detail else ''))
n_fail = sum(r[0] == FAIL for r in results)
print(f'\n{len(results) - n_fail}/{len(results)} passed')
sys.exit(1 if n_fail else 0)

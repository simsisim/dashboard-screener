"""
Cross-validation of this module's indicator ports against the sibling
projects' verified implementations (the sources cited in the docstrings).

Run from the module root:
    python3 validate.py

Each reference implementation runs in a SUBPROCESS (isolated interpreter) to
avoid `src`/`config` package-name collisions between projects. Checks:
  1. Wilder ATR(14) + ATRext(SMA40) vs metaData_v1 basic_calculations loop
  2. Weinstein stage vs lkm_rs common.stage.compute_stage
  3. SCTR raw score vs test_scooter sctr_model.compute_raw_score_matrix
  4. RTI/ADR/extension internal consistency (formula identities)
"""
import json
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent


def _latest_run_dir():
    """Newest results/YYYY-MM-DD batch dir holding screener_results.csv
    (same guard as the dashboard's own latest_run_dir(); the on-demand
    tabs mkdir an empty today/ dir on every dashboard boot)."""
    date_dirs = [d for d in (ROOT / 'results').iterdir()
                 if d.is_dir() and re.fullmatch(r'\d{4}-\d{2}-\d{2}', d.name)
                 and (d / 'screener_results.csv').exists()]
    return sorted(date_dirs)[-1]
sys.path.insert(0, str(ROOT))

import config
from src import data_loader, indicators
from src.focus import atr_extension as ate
from src.focus import rti as rti_mod
from src.focus import stages as stg_mod
from src.leaders import scooter as sco_mod

PASS, FAIL = 'PASS', 'FAIL'
results = []


def check(name, ok, detail=''):
    results.append((PASS if ok else FAIL, name, detail))


REF_SCRIPTS = {
    'meta': r'''
import sys, json
import pandas as pd
sys.path.insert(0, '/home/imagda/_invest2024/python/metaData_v1')
from src.basic_calculations import calculate_atr_and_atrext
df = pd.read_csv('%s')
df['Date'] = pd.to_datetime(df['Date'], utc=True).dt.tz_localize(None).dt.normalize()
df = df.set_index('Date')[['Open','High','Low','Close','Volume']]
print(json.dumps({'atr14': calculate_atr_and_atrext(df)['atr'],
                  'atrext40': calculate_atr_and_atrext(df, sma_period=40)['atrext_dollar']}))
''' % config.DAILY_CURRENT.joinpath('AAPL.csv'),

    'lkm': r'''
import sys, json
import pandas as pd
sys.path.insert(0, '/home/imagda/_invest2024/python/lkm_rs')
import config as lkm_config
from common.stage import compute_stage
from backtesting.test1_minervini import build_daily_price_matrix
tickers = ['AAPL','MSFT','NVDA','JPM','XOM']
prices, _ = build_daily_price_matrix(tickers)
out = {}
for t in tickers:
    sr = compute_stage(prices[t].dropna(),
                       sma_short=lkm_config.STAGE_DAILY_SMA_SHORT,
                       sma_med=lkm_config.STAGE_DAILY_SMA_MED,
                       sma_long=lkm_config.STAGE_DAILY_SMA_LONG,
                       slope_window=lkm_config.STAGE_DAILY_SLOPE_WINDOW,
                       min_bars=lkm_config.STAGE_DAILY_MIN_BARS,
                       lookback_52w=lkm_config.STAGE_DAILY_LOOKBACK_52W)
    out[t] = sr['stage'] if sr else None
print(json.dumps(out))
''',

    'sctr': r'''
import sys, json
import pandas as pd
sys.path.insert(0, '/home/imagda/_invest2024/python/test_scooter')
import sctr_model
sys.path.insert(0, '/home/imagda/_invest2024/python/dashboard-screener')
from src import data_loader
tickers = ['AAPL','MSFT','NVDA','JPM','XOM']
data = data_loader.load_price_matrices(tickers, use_batch=False, verbose=False)
raw = sctr_model.compute_raw_score_matrix(data['close'])
print(json.dumps({t: float(raw[t].dropna().iloc[-1]) for t in tickers}))
''',
}


def run_ref(key):
    out = subprocess.run([sys.executable, '-c', REF_SCRIPTS[key]],
                         capture_output=True, text=True, timeout=600)
    if out.returncode != 0:
        raise RuntimeError(out.stderr[-500:])
    lines = [l for l in out.stdout.strip().splitlines() if l.startswith('{')]
    return json.loads(lines[-1])


def main():
    tickers = ['AAPL', 'MSFT', 'NVDA', 'JPM', 'XOM']
    data = data_loader.load_price_matrices(tickers, use_batch=False, verbose=False)
    close, high, low = data['close'], data['high'], data['low']

    # 1. ATR / ATRext vs metaData_v1 (same 160-bar window for both sides)
    ref = run_ref('meta')
    df = pd.read_csv(config.DAILY_CURRENT / 'AAPL.csv')
    df['Date'] = pd.to_datetime(df['Date'], utc=True).dt.tz_localize(None).dt.normalize()
    df = df.set_index('Date')[['High', 'Low', 'Close']]
    my_atr = float(indicators.wilder_atr(df[['High']], df[['Low']], df[['Close']]).iloc[-1, 0])
    check('ATR14 vs metaData_v1', abs(my_atr - ref['atr14']) < 1e-3,
          f'ref={ref["atr14"]:.6f} ours={my_atr:.6f}')
    my_ext = (float(df['Close'].iloc[-1]) - float(df['Close'].rolling(40).mean().iloc[-1])) / my_atr
    check('ATRext40 vs metaData_v1', abs(my_ext - ref['atrext40']) < 1e-3,
          f'ref={ref["atrext40"]:.6f} ours={my_ext:.6f}')

    # 2. stages vs lkm_rs
    ref = run_ref('lkm')
    mine = stg_mod.evaluate(close)
    mism = [t for t, s in ref.items() if mine.loc[t, 'stage'] != s]
    check('Weinstein stages vs lkm_rs', not mism,
          '5/5 match' if not mism else f'mismatch: {mism}')

    # 3. SCTR raw vs test_scooter (relative tolerance: raw scores are O(100s))
    ref = run_ref('sctr')
    mine_sco = sco_mod.compute_scores(close)
    worst = max(abs(float(mine_sco.loc[t, 'scooter_raw']) - ref[t]) /
                max(1.0, abs(ref[t])) for t in ref)
    check('SCTR raw vs test_scooter', worst < 1e-6, f'max rel diff={worst:.2e}')

    # 4. internal identities (evaluate() rounds outputs to 2 decimals —
    # compare against the same rounding)
    ext = ate.evaluate(high, low, close, data['volume'])
    atr = indicators.wilder_atr(high, low, close, config.ATR_PERIOD)
    e21_check = ((close.iloc[-1] - indicators.ema(close, 21).iloc[-1])
                 / atr.iloc[-1]).round(2)
    d = (ext['ext_21ema_atr'] - e21_check).abs().max()
    check('ext_21ema_atr identity', d < 1e-6, f'max diff={d:.2e}')
    adr = indicators.adr_pct(high, low, close, 20)
    rng = pd.DataFrame(high.to_numpy(float) - low.to_numpy(float),
                       index=high.index, columns=high.columns)
    d = (adr.iloc[-1] - (rng.rolling(20).mean() / close * 100).iloc[-1]).abs().max()
    check('adr20_pct identity', d < 1e-6, f'max diff={d:.2e}')
    r = rti_mod.evaluate(high, low, close)
    check('rti zone ordering', ((r['rti'] < 5) == (r['rti_zone'] == '1')).all()
          and ((r['rti'] >= 15) == (r['rti_zone'] == '—')).all(),
          f'zones consistent')

    # 5. presets: shape validity + behavioral equivalence for ALL presets
    # (feedback_2.md §0: only 1 of 8 was exercised before, which is how a
    # key-name regression shipped as "9/9 passed")
    sys.path.insert(0, str(ROOT))
    import dashboard_filters as dfil

    def apply_advanced(mask, adv, r):
        """Mirror of dashboard.py's advanced-mask logic (data-level)."""
        if adv.get('adv_leaders'):
            cols = [f'in_{s}' for s in adv['adv_leaders']]
            flags = r[cols].fillna(False).astype(bool)
            mask &= (flags.any(axis=1)
                     if adv.get('adv_leaders_mode', 'Any (union)').startswith('Any')
                     else flags.all(axis=1))
        if adv.get('adv_stages'):
            mask &= r['stage'].isin(adv['adv_stages'])
        if adv.get('adv_max_ext', 10.0) < 10.0:
            mask &= (r['ext_21ema_atr'].fillna(99) <= adv['adv_max_ext']) & \
                    (r['ext_40sma_atr'].fillna(99) <= adv['adv_max_ext'])
        if adv.get('adv_rti_zone'):
            mask &= r['rti_zone'].isin(adv['adv_rti_zone'])
        mask &= r['rs_pct'].fillna(0) >= adv.get('adv_min_rs', 0.0)
        if 'minervini_count' in r.columns:
            mask &= r['minervini_count'].fillna(0) >= adv.get('adv_min_count', 0)
        # boolean screener flags (feedback_3.md presets) — the mask IS the
        # column; adv_ prefix strips to the column name
        for _flag in ('adv_9m_movers', 'adv_weekly_movers', 'adv_daily_gainers',
                      'adv_gold_launch_pad', 'adv_qullamaggie',
                      'adv_volume_anomaly', 'adv_adl_accumulation',
                      'adv_cantata'):
            if adv.get(_flag):
                col = 'in_' + _flag[4:]   # adv_x flag -> in_x column
                if col in r.columns:
                    mask &= r[col].fillna(False).astype(bool)
        if adv.get('adv_ce_min', 0.0) > 0 and 'ce_score' in r.columns:
            mask &= r['ce_score'].fillna(0) >= adv['adv_ce_min']
        if adv.get('adv_gmma_state'):
            mask &= r['gmma_state'].isin(adv['adv_gmma_state'])
        return mask

    shape_ok, shape_msgs = True, []
    for pname, p in dfil.PRESETS.items():
        if set(p.keys()) != {'selections', 'advanced'}:
            shape_ok = False
            shape_msgs.append(f'{pname}: keys {set(p.keys())}')
        for k, v in p.get('selections', {}).items():
            if k not in dfil.SPEC_BY_KEY:
                shape_ok = False
                shape_msgs.append(f'{pname}: bad filter key {k}')
            elif isinstance(v, (tuple, list)) and v and v[0] == 'custom':
                lo0, hi0, _ = dfil.CUSTOM_RANGE[dfil.SPEC_BY_KEY[k][2]]
                if not (lo0 <= v[1] <= v[2] <= hi0):
                    shape_ok = False
                    shape_msgs.append(f'{pname}: custom range {v} outside bounds')
            elif v != 'All' and v not in dict(
                    dfil.THRESHOLD_FAMILIES[dfil.SPEC_BY_KEY[k][2]]):
                shape_ok = False
                shape_msgs.append(f'{pname}: bad label {k}={v!r}')
        for k in p.get('advanced', {}):
            # MUST be the adv_-prefixed session-state names — a short name
            # here silently no-ops (feedback_2.md §0's exact regression)
            if k not in dfil.ADVANCED_DEFAULTS:
                shape_ok = False
                shape_msgs.append(f'{pname}: dead advanced key {k}')
    check('preset shapes valid', shape_ok, '; '.join(shape_msgs[:3]) or 'all 8 presets')

    # behavioral: every preset's mask == its hand-written manual equivalent
    # (bucket labels are INCLUSIVE lower bounds: '> 0%' means >= 0)
    res = pd.read_csv(_latest_run_dir() / 'screener_results.csv',
                  index_col='ticker')
    EXPECTED = {
        'Minervini 8/8 (liquid)':
            lambda r: r['in_minervini'].fillna(False) & (r['adv50_dollar'] >= 1e6),
        'Weinstein 2A/2B not extended':
            lambda r: r['stage'].isin(['2A', '2B'])
            & (r['ext_21ema_atr'] <= 2.0) & (r['ext_40sma_atr'] <= 2.0)
            & (r['adv50_dollar'] >= 1e6),
        'CANSLIM C-A-I leaders':
            lambda r: r['in_canslim'].fillna(False),
        'SCOOTER >= 90':
            lambda r: r['in_scooter'].fillna(False),
        'CANTATA CE leaders':
            lambda r: r['in_cantata'].fillna(False),
        'Tight consolidation (RTI)':
            lambda r: r['rti_zone'].isin(['1', '2']) & (r['adv50_dollar'] >= 1e6),
        'Leaders not extended (<= 2 ATR)':
            lambda r: (r['in_minervini'].fillna(False) | r['in_canslim'].fillna(False)
                       | r['in_scooter'].fillna(False))
            & (r['ext_21ema_atr'] <= 2.0) & (r['ext_40sma_atr'] <= 2.0)
            & (r['adv50_dollar'] >= 1e6),
        'Momentum Leader (Narrow)':
            lambda r: (r['pct_vs_50sma'] >= 0) & (r['pct_vs_200sma'] >= 0)
            & (r['adr20_pct'] >= 6) & (r['adr20_pct'] <= 60)
            & (r['adv50_dollar'] >= 20e6),
        'Large-cap uptrend pullback':
            lambda r: (r['market_cap'] >= 10e9) & (r['pct_vs_200sma'] >= 0)
            & (r['pct_from_52w_high'] >= -25) & (r['adv50_dollar'] >= 5e6)
            & r['stage'].isin(['2A', '2B']),
        # feedback_3.md presets — the flag presets' mask IS the column
        'Stockbee 9M Movers':
            lambda r: r['in_9m_movers'].fillna(False),
        'Stockbee 20% Weekly Movers':
            lambda r: r['in_weekly_movers'].fillna(False),
        'Stockbee 4% Daily Gainers':
            lambda r: r['in_daily_gainers'].fillna(False),
        'Golden Launch Pad':
            lambda r: r['in_gold_launch_pad'].fillna(False)
            & (r['adv50_dollar'] >= 1e6),
        'Qullamaggie Suite':
            lambda r: r['in_qullamaggie'].fillna(False),
        'ADL Accumulation':
            lambda r: r['in_adl_accumulation'].fillna(False),
    }
    bad = []
    counts = []
    for pname, p in dfil.PRESETS.items():
        if pname not in EXPECTED:
            bad.append(f'{pname}: no manual equivalent')
            continue
        m_preset = apply_advanced(
            dfil.build_mask(res, dfil.normalize_selections(p['selections'])),
            p.get('advanced', {}), res)
        m_manual = EXPECTED[pname](res).fillna(False)
        if not bool((m_preset == m_manual.reindex(m_preset.index)).all()) \
                or int(m_preset.sum()) == 0:
            bad.append(f'{pname}: preset={int(m_preset.sum())} '
                       f'manual={int(m_manual.sum())}')
        counts.append(f'{pname.split(" (")[0]}={int(m_preset.sum())}')
    check(f'ALL {len(dfil.PRESETS)} presets == manual filters', not bad,
          '; '.join(bad[:3]) or ' | '.join(counts))

    # 5c. Workflows tab (docs/workflows_tab.md) — build_advanced_mask
    # extraction is a faithful no-op at defaults and matches the independent
    # apply_advanced mirror; run_workflow chains == a single combined mask.
    from src import workflow as wf_mod
    _noop = dfil.build_advanced_mask(res, {})
    check('build_advanced_mask({}) is all-True', bool(_noop.all()),
          f'{int((~_noop).sum())} rows dropped by an empty advanced dict')

    _bam_bad = []
    for pname, p in dfil.PRESETS.items():
        _a = {**dfil.ADVANCED_DEFAULTS, **p.get('advanced', {})}
        m_new = dfil.build_advanced_mask(res, _a)
        m_mirror = apply_advanced(pd.Series(True, index=res.index), _a, res)
        if not bool((m_new == m_mirror).all()):
            _bam_bad.append(f'{pname}: {int((m_new != m_mirror).sum())} diff')
    check('build_advanced_mask == inline mirror (every preset advanced block)',
          not _bam_bad, '; '.join(_bam_bad[:3]) or f'{len(dfil.PRESETS)} presets')

    _w1 = {'stages': [{'name': 'A', 'source': 'universe',
                       'selections': {'adr': '> 5%'}}]}
    _r1 = wf_mod.run_workflow(res, _w1)
    _direct = res[dfil.build_mask(res, dfil.normalize_selections(
        {'adr': '> 5%'}))]
    _w2 = {'stages': [
        {'name': 'A', 'source': 'universe', 'selections': {'adr': '> 5%'}},
        {'name': 'B', 'source': 'A', 'selections': {'vs200': '> 0%'}}]}
    _r2 = wf_mod.run_workflow(res, _w2)
    _combined = res[dfil.build_mask(res, dfil.normalize_selections(
        {'adr': '> 5%', 'vs200': '> 0%'}))]
    # source order-independence: two 'universe'-sourced stages yield the same
    # rows regardless of their relative order
    _w3a = {'stages': [
        {'name': 'X', 'source': 'universe', 'selections': {'adr': '> 5%'}},
        {'name': 'Y', 'source': 'universe', 'selections': {'vs200': '> 0%'}}]}
    _w3b = {'stages': [
        {'name': 'Y', 'source': 'universe', 'selections': {'vs200': '> 0%'}},
        {'name': 'X', 'source': 'universe', 'selections': {'adr': '> 5%'}}]}
    check('run_workflow: single==build_mask, chain==combined, order-independent',
          set(_r1.focus.index) == set(_direct.index)
          and set(_r2.focus.index) == set(_combined.index)
          and (set(wf_mod.run_workflow(res, _w3a).by_name['X'].frame.index)
               == set(wf_mod.run_workflow(res, _w3b).by_name['X'].frame.index)),
          f'single={len(_r1.focus)} chain={len(_r2.focus)}/{len(_combined)}')

    # match='any' ORs the selection clauses (Ollie's 1M/3M/6M scans = a union)
    _any = {'stages': [{'name': 'A', 'source': 'universe', 'match': 'any',
                        'selections': {'above21low': '> 30%',
                                       'above63low': '> 50%',
                                       'above126low': '> 100%'}}]}
    _or_manual = ((res['pct_above_21d_low'] >= 30)
                  | (res['pct_above_63d_low'] >= 50)
                  | (res['pct_above_126d_low'] >= 100))
    _and_one = {'stages': [{'name': 'A', 'source': 'universe',
                            'selections': {'above21low': '> 30%',
                                           'above63low': '> 50%',
                                           'above126low': '> 100%'}}]}
    check("run_workflow match='any' == OR of clauses (and stricter 'all')",
          set(wf_mod.run_workflow(res, _any).focus.index)
          == set(res.index[_or_manual.fillna(False)])
          and len(wf_mod.run_workflow(res, _and_one).focus)
          <= len(wf_mod.run_workflow(res, _any).focus),
          f"any={int(_or_manual.fillna(False).sum())}")

    _wfe, _mono = [], True
    for _name, _wf in dfil.builtin_workflows().items():
        _e = wf_mod.validate_workflow(_wf)
        if _e:
            _wfe.append(f'{_name}: {_e[0]}')
        _rr = wf_mod.run_workflow(res, _wf)
        for _s in _rr.stages:
            if _s.n_out > _s.n_in:
                _mono = False
        if _rr.stages and not set(_rr.focus.index).issubset(
                set.union(*[set(s.frame.index) for s in _rr.stages])):
            _wfe.append(f'{_name}: focus not a subset of its stages')
    check('builtin workflows valid + monotonic + focus ⊆ stages',
          _mono and not _wfe,
          '; '.join(_wfe[:3]) or f'{len(dfil.builtin_workflows())} workflows')

    # 5a-bis. TradingView watchlist export — EXCHANGE:SYMBOL, comma separated,
    # ###header divider, dedup; unknown exchange -> bare symbol.
    _tv = dfil.tradingview_watchlist(
        pd.DataFrame({'exchange': ['NASDAQ', 'NYSE', 'NYSE Arca', None]},
                     index=['AAPL', 'BRK.A', 'SEB', 'AAPL']),
        section='wl')
    _tv_frame = dfil.tradingview_watchlist(res.head(50))
    check('tradingview_watchlist: prefix + sections + dedup + df frame',
          _tv == '###wl,NASDAQ:AAPL,NYSE:BRK.A,AMEX:SEB\n'
          and _tv_frame.endswith('\n') and ',' in _tv_frame
          and all(':' not in tok
                  or tok.split(':')[0] in dfil.TV_EXCHANGE_MAP.values()
                  for tok in _tv_frame.strip().split(',')),
          _tv.strip())

    # 5b. CANTATA / CE — score bounds + composition + two CEF items
    # reconstructed straight from the financial snapshot
    cta_bad = []
    if 'ce_score' not in res.columns:
        cta_bad.append('ce_score column missing from screener_results')
    else:
        cet, cef, ce = res['cet_score'], res['cef_score'], res['ce_score']
        if not (cet.dropna().between(0, 7).all()
                and cef.dropna().between(0, 11).all()
                and ce.dropna().between(0, 18).all()):
            cta_bad.append(f'out of range: cet[{cet.min()},{cet.max()}] '
                           f'cef[{cef.min()},{cef.max()}] ce[{ce.min()},{ce.max()}]')
        if not np.allclose((cet + cef).fillna(-1), ce.fillna(-1), atol=1e-6):
            cta_bad.append('ce_score != cet_score + cef_score')
        fin = pd.read_csv(config.FIN_DATA_CSV, low_memory=False).set_index('ticker')
        fin = fin.reindex(res.index)
        pos_eps = ((pd.to_numeric(fin['q1_eps'], errors='coerce') > 0)
                   & (pd.to_numeric(fin['q2_eps'], errors='coerce') > 0)).fillna(False)
        roe = pd.to_numeric(fin['returnOnEquity'], errors='coerce').fillna(
            pd.to_numeric(fin['y1_roe'], errors='coerce'))
        roe_ok = (roe >= config.CANTATA_CEF_ROE_MIN).fillna(False)
        if 'cef_pos_eps' in res.columns and not bool(
                (res['cef_pos_eps'].fillna(False) == pos_eps).all()):
            cta_bad.append('cef_pos_eps != (q1_eps>0 & q2_eps>0)')
        if 'cef_roe' in res.columns and not bool(
                (res['cef_roe'].fillna(False) == roe_ok).all()):
            cta_bad.append('cef_roe != (ROE >= 0.17)')
    check('CANTATA CE: bounds + CET+CEF composition + CEF items vs snapshot',
          not cta_bad, '; '.join(cta_bad[:3]) or
          (f"in_cantata={int(res['in_cantata'].sum())} "
           f"median CE={res['ce_score'].median():.1f}"
           if 'ce_score' in res.columns else ''))

    # 6. save->load round trip preserves a custom-range selection
    # (feedback_2.md: the 'Custom…' string was saved, bounds dropped)
    panel = dfil.normalize_selections({'vs50': '> 0%',
                                       'adr': ('custom', 6.0, 60.0)})
    dfil.save_screener('__rt_check__', panel, {'adv_stages': ['2A', '2B']})
    loaded = dfil.load_screener('__rt_check__')
    restored = {}
    for k, v in loaded['selections'].items():
        if isinstance(v, (tuple, list)) and v and v[0] == 'custom':
            restored[k] = ('custom', float(v[1]), float(v[2]))
        else:
            restored[k] = v
    same = all(restored[k] == panel[k] for k in panel) \
        and loaded['advanced'].get('adv_stages') == ['2A', '2B']
    m_orig = dfil.build_mask(res, panel)
    m_rest = dfil.build_mask(res, restored)
    check('save/load round trip keeps custom ranges',
          same and bool((m_orig == m_rest).all()) and int(m_orig.sum()) > 0,
          f'adr={restored.get("adr")} rows={int(m_orig.sum())}')
    dfil.delete_screener('__rt_check__')

    # 7. Stockbee Movers (more_screeners.md Task 1): module output vs the
    # bullet conditions recomputed directly as pandas masks
    from src.leaders import stockbee_movers as stb
    stb_data = data  # same 5-ticker matrices loaded at the top
    stb_out = stb.evaluate(stb_data['open'], stb_data['high'],
                           stb_data['low'], stb_data['close'],
                           stb_data['volume'])
    _o, _h, _l = stb_data['open'], stb_data['high'], stb_data['low']
    _c, _v = stb_data['close'], stb_data['volume']
    _avg20 = _v.rolling(config.STOCKBEE_REL_VOL_WINDOW,
                        min_periods=config.STOCKBEE_REL_VOL_WINDOW).mean()
    _rv = _v.iloc[-1] / _avg20.iloc[-1]
    _wo = _o.iloc[-config.STOCKBEE_WEEK_WINDOW]
    _wc = _c.iloc[-1]
    _wg = (_wc / _wo.replace(0, np.nan) - 1) * 100
    _av5 = _v.iloc[-config.STOCKBEE_WEEK_WINDOW:].mean()
    _wrv = _av5 / _avg20.iloc[-1]
    _dg = _c.pct_change().iloc[-1] * 100
    _s50 = indicators.sma(_c, 50).iloc[-1]

    m_9m = ((_v.iloc[-1] >= config.STOCKBEE_9M_MIN_VOLUME)
            & (_rv >= config.STOCKBEE_9M_MIN_REL_VOL)
            & (_c.iloc[-1] > _o.iloc[-1]))
    m_wk = ((_wg >= config.STOCKBEE_WEEKLY_MIN_GAIN_PCT)
            & (_av5 >= config.STOCKBEE_WEEKLY_MIN_AVG_VOLUME)
            & (_wrv >= config.STOCKBEE_WEEKLY_MIN_REL_VOL)
            & (_wc > _wo))
    m_dl = ((_dg >= config.STOCKBEE_DAILY_MIN_GAIN_PCT)
            & (_v.iloc[-1] >= config.STOCKBEE_DAILY_MIN_VOLUME)
            & (_rv >= config.STOCKBEE_DAILY_MIN_REL_VOL)
            & (_c.iloc[-1] > _o.iloc[-1])
            & (_c.iloc[-1] > _s50))
    for label, mine, manual in [
            ('9m movers', stb_out['in_9m_movers'], m_9m),
            ('weekly movers', stb_out['in_weekly_movers'], m_wk),
            ('daily gainers', stb_out['in_daily_gainers'], m_dl)]:
        mine = mine.reindex(manual.index).fillna(False).astype(bool)
        manual = manual.fillna(False).astype(bool)
        check(f'stockbee {label}: module == manual mask',
              bool((mine == manual).all()),
              f'n_match={int(mine.sum())}/{len(mine)}')

    # 8. Golden Launch Pad (Task 2): cross-check vs metaData_v1's own
    # GoldLaunchPadScreener on the same tickers (isolated subprocess —
    # new math to this project: z-score spread + OLS slopes)
    ref_script = r'''
import sys, json
import pandas as pd
sys.path.insert(0, '/home/imagda/_invest2024/python/metaData_v1')
from src.screeners.gold_launch_pad import GoldLaunchPadScreener
CUR = '/home/imagda/_invest2024/python/downloadData_v1/data/market_data/daily/current'
ARCH = '/home/imagda/_invest2024/python/downloadData_v1/data/market_data/daily/archive'
tickers = ['AAPL', 'MSFT', 'NVDA', 'JPM', 'XOM', 'QMCO', 'DELL', 'MRVL']
batch = {}
for t in tickers:
    parts = []
    for base in (ARCH, CUR):
        try:
            parts.append(pd.read_csv(f'{base}/{t}.csv', low_memory=False))
        except FileNotFoundError:
            pass
    df = pd.concat(parts).drop_duplicates(subset='Date').sort_values('Date')
    df['Date'] = pd.to_datetime(df['Date'], utc=True, errors='coerce')
    df = df.dropna(subset=['Date'])
    df['Date'] = df['Date'].dt.tz_localize(None).dt.normalize()
    df = df.set_index('Date')[['Open', 'High', 'Low', 'Close', 'Volume']]
    batch[t] = df.apply(pd.to_numeric, errors='coerce').dropna()
scr = GoldLaunchPadScreener({'gold_launch_pad': {}})
out = scr.run_gold_launch_pad_screening(batch)
print(json.dumps({'passing': sorted(r['ticker'] for r in out),
                  'scores': {r['ticker']: r.get('spread_score') for r in out}}))
'''
    out = subprocess.run([sys.executable, '-c', ref_script],
                         capture_output=True, text=True, timeout=900)
    if out.returncode != 0:
        check('GLP cross-check vs metaData_v1', False, out.stderr[-200:])
    else:
        ref = json.loads([l for l in out.stdout.strip().splitlines()
                          if l.startswith('{')][-1])
        from src.leaders import gold_launch_pad as glp_mod
        glp_data = data_loader.load_price_matrices(
            ['AAPL', 'MSFT', 'NVDA', 'JPM', 'XOM', 'QMCO', 'DELL', 'MRVL'],
            use_batch=False, verbose=False)
        mine = glp_mod.evaluate(glp_data['close'])
        # the reference also applies base filters (close >= $5, 20d avg
        # share volume >= 100K) on top of the 5 conditions — apply the
        # same for an apples-to-apples set comparison
        avg_vol20 = glp_data['volume'].rolling(20, min_periods=20).mean().iloc[-1]
        base = (glp_data['close'].iloc[-1] >= 5.0) & (avg_vol20 >= 100_000)
        mine_passing = sorted(mine.index[mine['in_gold_launch_pad'] & base])
        check('GLP cross-check vs metaData_v1',
              set(mine_passing) == set(ref['passing']),
              f"ours={mine_passing} ref={ref['passing']}")

    # 8b. GMMA (Task 4): synthetic series with known states
    # (the source is a state machine — constructed fixtures are the honest
    # behavioral check; calibrated in IMPLEMENTATION_PLAN.md §11.4)
    from src.leaders import gmma as gmma_mod
    _n = 320
    _idx = pd.date_range('2025-01-01', periods=_n, freq='B')

    def _syn_state(closes):
        c = pd.DataFrame({'SYN': np.asarray(closes, dtype=float)}, index=_idx)
        return gmma_mod.evaluate(c).loc['SYN', 'gmma_state']

    _c_cb = np.full(_n, 100.0)
    _c_cb[-8:] = 100 * (1.003 ** np.arange(1, 9))
    _c_exp = np.full(_n, 100.0)
    _c_exp[-20:] = 100 * (1.004 ** np.arange(1, 21))
    gmma_cases = [
        ('steady rise -> bullish', 100 * (1.005 ** np.arange(_n)), 'bullish'),
        ('steady fall -> bearish', 100 * (0.995 ** np.arange(_n)), 'bearish'),
        ('flat+0.3%x8 -> compression_breakout', _c_cb, 'compression_breakout'),
        ('flat+0.4%x20 -> expanding', _c_exp, 'expanding'),
        ('pure flat -> transitioning', np.full(_n, 100.0), 'transitioning'),
    ]
    gmma_bad = [f'{lbl}: got {got}' for lbl, closes, want in gmma_cases
                if (got := _syn_state(closes)) != want]
    check('GMMA synthetic states', not gmma_bad,
          '; '.join(gmma_bad[:2]) or f'{len(gmma_cases)} fixtures')

    # 8c. Qullamaggie (Task 5): module == direct recomputation on the
    # same 5-ticker matrices (behavioral, like the stockbee checks)
    from src.leaders import qullamaggie as qm
    _atr14 = indicators.wilder_atr(_c_exp_frame := stb_data['high'],
                                   stb_data['low'], stb_data['close'])
    # market caps from the universe file
    _uni = data_loader.load_universe().set_index('Symbol')['market_cap']
    _mc = _uni.reindex(stb_data['close'].columns)
    q_out = qm.evaluate(stb_data['close'], stb_data['high'],
                        stb_data['low'], _atr14, _mc)
    _px = stb_data['close'].iloc[-1]
    # RS: percentile of n-bar momentum per horizon, ANY >= 97
    _rs_any = None
    for _lb in config.QULLA_RS_HORIZONS.values():
        _roc = indicators.roc(stb_data['close'], _lb).iloc[-1]
        _pct = _roc.rank(pct=True) * 100.0
        _rs_any = (_pct >= config.QULLA_RS_THRESHOLD) if _rs_any is None \
            else (_rs_any | (_pct >= config.QULLA_RS_THRESHOLD))
    _stack = ((_px >= indicators.ema(stb_data['close'], 10).iloc[-1])
              & (indicators.ema(stb_data['close'], 10).iloc[-1]
                 >= indicators.sma(stb_data['close'], 20).iloc[-1])
              & (indicators.sma(stb_data['close'], 20).iloc[-1]
                 >= indicators.sma(stb_data['close'], 50).iloc[-1])
              & (indicators.sma(stb_data['close'], 50).iloc[-1]
                 >= indicators.sma(stb_data['close'], 100).iloc[-1])
              & (indicators.sma(stb_data['close'], 100).iloc[-1]
                 >= indicators.sma(stb_data['close'], 200).iloc[-1]))
    _big = _mc >= config.QULLA_MIN_MARKET_CAP
    _arank = pd.Series(np.nan, index=_px.index)
    _a14 = _atr14.iloc[-1]
    if _big.sum() > 1:
        _arank[_big] = _a14[_big].rank(pct=True) * 100.0
    _hi = stb_data['high'].rolling(config.QULLA_RANGE_WINDOW).max().iloc[-1]
    _lo = stb_data['low'].rolling(config.QULLA_RANGE_WINDOW).min().iloc[-1]
    _rpos = (_px - _lo) / (_hi - _lo).replace(0, np.nan)
    m_q = (_rs_any & _stack.fillna(False)
           & (_arank >= config.QULLA_ATR_RS_THRESHOLD)
           & (_rpos >= config.QULLA_RANGE_POSITION) & _big.fillna(False))
    m_q = m_q.reindex(q_out.index).fillna(False).astype(bool)
    mine_q = q_out['in_qullamaggie'].fillna(False).astype(bool)
    check('qullamaggie: module == manual mask',
          bool((mine_q == m_q).all()),
          f'n_match={int(mine_q.sum())}/{len(mine_q)}')

    # 8d. Volume anomaly (Task 6): synthetic spike + z-score identity
    from src.focus import volume_anomaly as van_mod
    _vol = stb_data['volume']
    _vm = _vol.rolling(config.VOLANOM_LOOKBACK,
                       min_periods=config.VOLANOM_LOOKBACK).mean()
    _vs = _vol.rolling(config.VOLANOM_LOOKBACK,
                       min_periods=config.VOLANOM_LOOKBACK).std()
    _vz = (_vol.iloc[-1] - _vm.iloc[-1]) / _vs.iloc[-1].replace(0, np.nan)
    _vr = _vol.iloc[-1] / _vm.iloc[-1].replace(0, np.nan)
    _van = ((_vol.iloc[-1] > _vm.iloc[-1]
             + config.VOLANOM_STD_THRESHOLD * _vs.iloc[-1])
            & (_vol.iloc[-1] > config.VOLANOM_MIN_VOLUME)
            & (_vr > config.VOLANOM_MIN_RELATIVE))
    van_out = van_mod.evaluate(_vol)
    mine_van = van_out['in_volume_anomaly'].reindex(_van.index).fillna(False).astype(bool)
    check('volume anomaly: module == manual mask',
          bool((mine_van == _van.fillna(False).astype(bool)).all()),
          f'n_match={int(mine_van.sum())}/{len(mine_van)}')
    _zdiff = (van_out['volume_zscore'] - _vz).abs().max()
    check('volume anomaly: z-score identity', _zdiff < 0.01,
          f'max diff={_zdiff:.2e}')
    # synthetic spike sanity: 5x volume on the last bar must flag
    _vol_sp = _vol.copy()
    _vol_sp.iloc[-1] = _vol_sp.iloc[-1] * 5
    _sp = van_mod.evaluate(_vol_sp)
    check('volume anomaly: synthetic 5x spike flags',
          bool(_sp['in_volume_anomaly'].any()),
          f'{int(_sp["in_volume_anomaly"].sum())} flagged')

    # 9. Volume + ADX columns (Task 3): numeric cross-checks vs metaData_v1
    ref_script = r'''
import sys, json
import pandas as pd
sys.path.insert(0, '/home/imagda/_invest2024/python/metaData_v1')
from src.screeners.volume_suite_components.volume_indicators import (
    add_vroc, add_money_flow_index)
from src.indicators.indicators_calculation import calculate_adx
CUR = '/home/imagda/_invest2024/python/downloadData_v1/data/market_data/daily/current'
ARCH = '/home/imagda/_invest2024/python/downloadData_v1/data/market_data/daily/archive'
out = {}
for t in ['AAPL', 'MSFT', 'QMCO']:
    parts = []
    for base in (ARCH, CUR):
        try:
            parts.append(pd.read_csv(f'{base}/{t}.csv', low_memory=False))
        except FileNotFoundError:
            pass
    df = pd.concat(parts).drop_duplicates(subset='Date').sort_values('Date')
    df['Date'] = pd.to_datetime(df['Date'], utc=True, errors='coerce')
    df = df.dropna(subset=['Date'])
    df['Date'] = df['Date'].dt.tz_localize(None).dt.normalize()
    df = df.set_index('Date')
    df = df[['Open', 'High', 'Low', 'Close', 'Volume']].apply(
        pd.to_numeric, errors='coerce').dropna()
    df = add_vroc(df, period=25)
    df = add_money_flow_index(df, period=14)
    adx = calculate_adx(df, atr_len=13, di_len=13, adx_len=8)
    out[t] = {'vroc25': float(df['VROC'].iloc[-1]),
              'mfi14': float(df['MFI'].iloc[-1]),
              'adtv_50': float(df['Volume'].rolling(50).mean().iloc[-1]),
              'adx13': float(adx['ADX'].iloc[-1]),
              'plus_di13': float(adx['plus_DI'].iloc[-1]),
              'minus_di13': float(adx['minus_DI'].iloc[-1])}
print(json.dumps(out))
'''
    out = subprocess.run([sys.executable, '-c', ref_script],
                         capture_output=True, text=True, timeout=900)
    if out.returncode != 0:
        check('volume/ADX cross-check vs metaData_v1', False,
              out.stderr[-200:])
    else:
        ref = json.loads([l for l in out.stdout.strip().splitlines()
                          if l.startswith('{')][-1])
        vadx_data = data_loader.load_price_matrices(
            ['AAPL', 'MSFT', 'QMCO'], use_batch=False, verbose=False)
        from src.focus import volume_adx as vadx_mod
        mine = vadx_mod.evaluate(vadx_data['high'], vadx_data['low'],
                                 vadx_data['close'], vadx_data['volume'])
        worst_v, worst_c = 0.0, ''
        for t, vals in ref.items():
            for col, ref_val in vals.items():
                mine_val = float(mine.loc[t, col])
                rel = abs(mine_val - ref_val) / max(1.0, abs(ref_val))
                if rel > worst_v:
                    worst_v, worst_c = rel, f'{t}.{col}'
        # Wilder RMA seeding differs (SMA-seed vs first-value-seed) — the
        # recursion converges, bound the residual at 0.5% relative
        check('volume/ADX cross-check vs metaData_v1', worst_v < 0.005,
              f'worst rel diff={worst_v:.2e} at {worst_c}')

    # 10. ADL 5-step suite (Task 7): composite scores vs the metaData_v1
    # ad_line/ package (validate_adl_ref.py, isolated subprocess)
    out = subprocess.run([sys.executable, str(ROOT / 'validate_adl_ref.py')],
                         capture_output=True, text=True, timeout=900)
    if out.returncode != 0:
        check('ADL composite vs metaData_v1', False, out.stderr[-200:])
    else:
        ref = json.loads([l for l in out.stdout.strip().splitlines()
                          if l.startswith('{')][-1])
        adl_data = data_loader.load_price_matrices(
            ['AAPL', 'MSFT', 'QMCO'], use_batch=False, verbose=False)
        from src.leaders import adl_accumulation as adl_mod
        mine = adl_mod.evaluate(adl_data['high'], adl_data['low'],
                                adl_data['close'], adl_data['volume'])
        worst_v, worst_c = 0.0, ''
        col_map = {'consistency': 'adl_consistency_score',
                   'momentum': 'adl_momentum_score',
                   'alignment': 'adl_alignment_score',
                   'composite': 'adl_composite_score'}
        for t, vals in ref.items():
            for ref_col, ref_val in vals.items():
                mine_val = float(mine.loc[t, col_map[ref_col]])
                rel = abs(mine_val - ref_val) / max(1.0, abs(ref_val))
                if rel > worst_v:
                    worst_v, worst_c = rel, f'{t}.{ref_col}'
        check('ADL composite vs metaData_v1', worst_v < 0.02,
              f'worst rel diff={worst_v:.2e} at {worst_c}')

    # 10b. Dr. Wish dots (Task 1 timing): module == manual conditions
    from src.timing import drwish_dots as dots_mod
    _dot_tickers = list(stb_data['close'].columns)
    dots_out = dots_mod.evaluate(_dot_tickers, stb_data)
    _stoch = dots_mod.stochastic_k(stb_data['high'], stb_data['low'],
                                   stb_data['close'],
                                   config.DRWISH_STOCH_PERIOD)
    _st_today = _stoch.iloc[-1]
    _st_prev = _stoch.iloc[-2]
    _sma50r = (indicators.sma(stb_data['close'],
                              config.DRWISH_BLUE_SMA_PERIOD).diff()
               > 0).iloc[-1]
    _m_blue = ((_st_prev < config.DRWISH_BLUE_STOCH_THRESHOLD)
               & (_st_today > config.DRWISH_BLUE_STOCH_THRESHOLD) & _sma50r)
    _sma30 = indicators.sma(stb_data['close'],
                            config.DRWISH_BLACK_SMA_PERIOD).iloc[-1]
    _ema21 = indicators.ema(stb_data['close'],
                            config.DRWISH_BLACK_EMA_PERIOD).iloc[-1]
    _min3 = _stoch.iloc[-config.DRWISH_BLACK_LOOKBACK:].min()
    _m_black = ((_min3 <= config.DRWISH_BLACK_STOCH_THRESHOLD)
                & (stb_data['close'].iloc[-1]
                   > stb_data['close'].iloc[-2])
                & ((stb_data['close'].iloc[-1] > _sma30)
                   | (stb_data['close'].iloc[-1] > _ema21)))
    for label, mine_m, manual_m in [
            ('blue dot', dots_out['in_blue_dot'], _m_blue),
            ('black dot', dots_out['in_black_dot'], _m_black)]:
        mine_m = mine_m.reindex(manual_m.index).fillna(False).astype(bool)
        manual_m = manual_m.fillna(False).astype(bool)
        check(f'drwish {label}: module == manual mask',
              bool((mine_m == manual_m).all()),
              f'n_match={int(mine_m.sum())}/{len(mine_m)}')

    # 10c. PVB (Task 2 timing): module final state == an independently
    # written reference loop (straight port of the source's rules)
    from src.timing import pvb as pvb_mod
    _tickers = list(stb_data['close'].columns)
    pvb_out = pvb_mod.evaluate(_tickers, stb_data)
    _ph = stb_data['high'].rolling(config.PVB_PRICE_BREAKOUT_PERIOD).max()
    _pl = stb_data['low'].rolling(config.PVB_PRICE_BREAKOUT_PERIOD).min()
    _vh = stb_data['volume'].rolling(config.PVB_VOLUME_BREAKOUT_PERIOD).max()
    _sma = indicators.sma(stb_data['close'], config.PVB_TRENDLINE_LENGTH)
    bad_pvb = []
    for _t in _tickers:
        _c = stb_data['close'][_t].to_numpy(float)
        _v = stb_data['volume'][_t].to_numpy(float)
        _phv, _plv = _ph[_t].to_numpy(float), _pl[_t].to_numpy(float)
        _vhv, _smv = _vh[_t].to_numpy(float), _sma[_t].to_numpy(float)
        sig, consec = 'No Signal', 0
        sig_i = None
        for i in range(1, len(_c)):
            if np.isnan(_smv[i]) or np.isnan(_phv[i - 1]):
                continue
            if (_c[i] > _phv[i - 1] and not np.isnan(_vhv[i - 1])
                    and _v[i] > _vhv[i - 1] and _c[i] > _smv[i]
                    and sig != 'Buy'):
                sig, sig_i, consec = 'Buy', i, 0
            elif (not np.isnan(_plv[i - 1]) and _c[i] < _plv[i - 1]
                  and not np.isnan(_vhv[i - 1]) and _v[i] > _vhv[i - 1]
                  and _c[i] < _smv[i] and sig != 'Sell'):
                sig, sig_i, consec = 'Sell', i, 0
            if sig == 'Buy':
                consec = consec + 1 if _c[i] < _smv[i] else 0
                if consec >= config.PVB_CLOSE_THRESHOLD:
                    sig, sig_i, consec = 'Close Buy', i, 0
            elif sig == 'Sell':
                consec = consec + 1 if _c[i] > _smv[i] else 0
                if consec >= config.PVB_CLOSE_THRESHOLD:
                    sig, sig_i, consec = 'Close Sell', i, 0
        if sig != pvb_out.loc[_t, 'pvb_signal']:
            bad_pvb.append(f'{t if False else _t}: ref={sig} '
                           f'module={pvb_out.loc[_t, "pvb_signal"]}')
    check('pvb: module == reference state machine', not bad_pvb,
          '; '.join(bad_pvb[:2]) or f'{len(_tickers)} tickers match')

    # 11. ATR1 cloud (Task 3 timing): exact cross-check vs metaData_v1
    # calculate_atr_cloud (validate_atr1_ref.py, isolated subprocess)
    out = subprocess.run([sys.executable, str(ROOT / 'validate_atr1_ref.py')],
                         capture_output=True, text=True, timeout=900)
    if out.returncode != 0:
        check('ATR1 cloud vs metaData_v1', False, out.stderr[-200:])
    else:
        ref = json.loads([l for l in out.stdout.strip().splitlines()
                          if l.startswith('{')][-1])
        from src.timing import atr1_cloud as atr1_mod
        atr1_data = data_loader.load_price_matrices(
            ['AAPL', 'MSFT', 'QMCO'], use_batch=False, verbose=False)
        mine = atr1_mod.evaluate(['AAPL', 'MSFT', 'QMCO'], atr1_data)
        bad = []
        for t, vals in ref.items():
            if abs(float(mine.loc[t, 'atr1_stop_level']) - vals['vStop']) > 0.01:
                bad.append(f'{t}.vStop mine={mine.loc[t, "atr1_stop_level"]} ref={vals["vStop"]}')
            if abs(float(mine.loc[t, 'atr1_stop_level2']) - vals['vStop2']) > 0.01:
                bad.append(f'{t}.vStop2 mine={mine.loc[t, "atr1_stop_level2"]} ref={vals["vStop2"]}')
            if (mine.loc[t, 'atr1_trend'] == 'uptrend') != vals['uptrend']:
                bad.append(f'{t}.uptrend mine={mine.loc[t, "atr1_trend"]}')
        check('ATR1 cloud vs metaData_v1', not bad,
              '; '.join(bad[:2]) or '3 tickers exact')

        # 11b. ATR1 days_since_signal/signal_type (this session's port of
        # atr1_screener()'s "last crossover" scan, on top of the already-
        # validated vol_stop_np — new logic, deserves its own check rather
        # than riding on 11's pass)
        bad2 = []
        for t, vals in ref.items():
            if mine.loc[t, 'atr1_signal_type'] != vals.get('signal_type'):
                bad2.append(f"{t}.signal_type mine={mine.loc[t, 'atr1_signal_type']} "
                            f"ref={vals.get('signal_type')}")
            if mine.loc[t, 'atr1_signal_date'] != vals.get('signal_date'):
                bad2.append(f"{t}.signal_date mine={mine.loc[t, 'atr1_signal_date']} "
                            f"ref={vals.get('signal_date')}")
            ref_days = vals.get('days_since_signal')
            mine_days = mine.loc[t, 'atr1_days_since_signal']
            if ref_days is not None and (pd.isna(mine_days) or int(mine_days) != int(ref_days)):
                bad2.append(f"{t}.days_since mine={mine_days} ref={ref_days}")
        check('ATR1 days_since_signal/signal_type vs metaData_v1', not bad2,
              '; '.join(bad2[:2]) or '3 tickers exact')

    # 12. GLB (Task 5 patterns): records vs metaData_v1
    # (validate_glb_ref.py, isolated subprocess) + cache behavior
    out = subprocess.run([sys.executable, str(ROOT / 'validate_glb_ref.py')],
                         capture_output=True, text=True, timeout=900)
    if out.returncode != 0:
        check('GLB records vs metaData_v1', False, out.stderr[-200:])
    else:
        ref = json.loads([l for l in out.stdout.strip().splitlines()
                          if l.startswith('{')][-1])
        from src.patterns import glb as glb_mod
        glb_data = data_loader.load_price_matrices(
            ['AAPL', 'MSFT'], use_batch=False, verbose=False)
        glb_mod.evaluate(['AAPL', 'MSFT'], glb_data)   # ensure caches warm
        # cache is namespaced by params_hash (TODO_caching.md fix) —
        # rebuild the same default params dict evaluate() used internally
        # to find the right cache file.
        default_params = {
            'pivot_strength': config.GLB_PIVOT_STRENGTH,
            'lookback_bars': config.GLB_LOOKBACK_BARS,
            'historical_bars': config.GLB_HISTORICAL_BARS,
            'confirmation_bars': config.GLB_CONFIRMATION_BARS,
            'require_confirmation': config.GLB_REQUIRE_CONFIRMATION,
        }
        phash = glb_mod._params_hash(default_params)
        bad = []
        for t, ref_records in ref.items():
            cpath = glb_mod._cache_path(t, phash)
            mine = json.loads(cpath.read_text())['records']
            mine_set = {(round(r['level'], 3), r['detection_date'],
                         r['is_confirmed'], r['is_broken'])
                        for r in mine}
            ref_set = {(round(r['level'], 3), r['detection'],
                        r['confirmed'], r['broken']) for r in ref_records}
            if mine_set != ref_set:
                only_mine = mine_set - ref_set
                only_ref = ref_set - mine_set
                bad.append(f'{t}: +{len(only_mine)}/-{len(only_ref)} '
                           f'differing records')
        check('GLB records vs metaData_v1', not bad,
              '; '.join(bad[:2]) or 'AAPL+MSFT record sets identical')

    # 13. Cup & Handle (Task 6 patterns): synthetic fixture — a by-
    # construction cup & handle that Strict/Default/Loose must all detect,
    # cross-checked against patterns_v0's own detector
    # (validate_ch_ref.py --synthetic, isolated subprocess)
    _n_ch = 170
    _idx_ch = pd.date_range('2025-01-01', periods=_n_ch, freq='B')
    # seg0 rises 72 -> 100: >= 30% prior advance into the left rim, so the
    # §16 Task A setup-gain gate (strict 30%) is satisfied on this fixture
    # (kept identical to validate_ch_ref.build_synthetic).
    _ch_segs = [np.linspace(72, 100, 56),
                np.concatenate([np.linspace(100, 92.5, 7),
                                np.linspace(92.5, 103, 13)]),
                np.linspace(103, 82.4, 31),
                np.linspace(82.4, 102.5, 27),
                np.linspace(102.5, 96.8, 8),
                np.linspace(96.8, 112, 31)]
    _ch_close = np.concatenate(_ch_segs)[:_n_ch]
    _rng_ch = np.random.default_rng(42)
    _ch_close = np.maximum(
        _ch_close + _rng_ch.normal(0, 0.25, _n_ch).cumsum() * 0.08, 1)
    from src.patterns import cup_handle as ch_mod
    _ch_data = {'close': pd.DataFrame({'SYN': _ch_close}, index=_idx_ch),
                'volume': pd.DataFrame(
                    {'SYN': np.arange(1, _n_ch + 1) * 1e6}, index=_idx_ch)}
    _ch_out = ch_mod.evaluate(['SYN'], _ch_data).loc['SYN']
    ch_bad = []
    if not _ch_out['in_cup_handle_strict']:
        ch_bad.append('strict did not fire')
    if _ch_out['cup_handle_stage_strict'] != 'breakout':
        ch_bad.append(f"strict stage={_ch_out['cup_handle_stage_strict']}")
    if abs(_ch_out['cup_depth_pct_strict'] - 20.15) > 0.5:
        ch_bad.append(f"strict depth={_ch_out['cup_depth_pct_strict']}")
    check('C&H synthetic: all presets detect the constructed pattern',
          not ch_bad, '; '.join(ch_bad[:2]) or
          f"strict quality={_ch_out['cup_handle_quality_score_strict']}")

    # §16 breakoutwatch alignment — the added gates: each must (a) report its
    # column on the good fixture and (b) reject when its own threshold is
    # made impossible, while Loose (all gates non-binding) still fires.
    _ch_bad2 = []
    _sg = _ch_out['cup_handle_setup_gain_pct_strict']
    if not (pd.notna(_sg) and _sg >= 30.0):
        _ch_bad2.append(f'strict setup_gain={_sg} (<30)')
    _rt = _ch_out['cup_handle_ratio_strict']
    if not (pd.notna(_rt) and _rt >= 3.0):
        _ch_bad2.append(f'strict cup:handle ratio={_rt} (<3)')
    _dr = _ch_out['cup_handle_days_since_rim_strict']
    if not (pd.notna(_dr) and _dr <= 90):
        _ch_bad2.append(f'strict days_since_rim={_dr} (>90)')
    if not _ch_out['in_cup_handle_loose']:
        _ch_bad2.append('loose did not fire (gates should be non-binding)')
    # CQ (report-only) must be present and a finite blend of rcq/hq
    for _p in ('strict', 'loose'):
        _cq = _ch_out[f'cup_handle_cq_{_p}']
        _rc = _ch_out[f'cup_handle_rcq_{_p}']
        _hqv = _ch_out[f'cup_handle_hq_{_p}']
        if not (pd.notna(_cq) and min(_rc, _hqv) - 1e-6 <= _cq
                <= max(_rc, _hqv) + 1e-6):
            _ch_bad2.append(f'{_p} cq={_cq} not within [rcq,hq]=[{_rc},{_hqv}]')
    _ch_np = _ch_close.astype(float)
    _ch_vol = (np.arange(1, _n_ch + 1) * 1e6).astype(float)
    for _gate, _override in (
            ('setup_gain_min', {'setup_gain_min': 0.99}),
            ('pivot_max_age', {'pivot_max_age': 1}),
            ('cup_handle_ratio_min', {'cup_handle_ratio_min': 99.0})):
        _pp = dict(config.CUPHANDLE_PRESETS['strict'])
        _pp.update(_override)
        _rr = ch_mod._evaluate_preset(_ch_np, None, None, _ch_vol, _pp)
        if _rr['found']:
            _ch_bad2.append(f'{_gate}: gate did not reject')
    # midpoint rule (Task D) — attributed: a deep-low-handle variant that a
    # permissive preset finds; turning ONLY handle_midpoint_rule on rejects it
    _ch_lh = _ch_np.copy()
    _ch_lh[134:142] -= 14.0                      # push the handle well below mid-base
    _pp_lo = dict(config.CUPHANDLE_PRESETS['loose'])
    _pp_lo.update({'cup_min_duration': 20, 'handle_max_depth_pct': 1.0,
                   'handle_position_min': 0.0, 'handle_midpoint_rule': False})
    _pp_hi = dict(_pp_lo, handle_midpoint_rule=True)
    _found_lo = ch_mod._evaluate_preset(_ch_lh, None, None, _ch_vol, _pp_lo)['found']
    _found_hi = ch_mod._evaluate_preset(_ch_lh, None, None, _ch_vol, _pp_hi)['found']
    if not (_found_lo and not _found_hi):
        _ch_bad2.append(f'midpoint rule: off={_found_lo} on={_found_hi} '
                        '(expected True/False)')
    check('C&H §16 gates: reported on fixture + each rejects at its limit',
          not _ch_bad2, '; '.join(_ch_bad2[:3]) or
          f"setup_gain={round(_sg, 1)}% ratio={_rt} "
          f"hq={_ch_out['cup_handle_hq_strict']} "
          f"rcq={_ch_out['cup_handle_rcq_strict']} "
          f"cq={_ch_out['cup_handle_cq_strict']}")

    # cross-check vs patterns_v0's own detector on the same synthetic data
    out = subprocess.run([sys.executable, str(ROOT / 'validate_ch_ref.py'),
                          '--synthetic'],
                         capture_output=True, text=True, timeout=900)
    if out.returncode != 0:
        check('C&H vs patterns_v0 (synthetic)', False, out.stderr[-200:])
    else:
        ref = json.loads([l for l in out.stdout.strip().splitlines()
                          if l.startswith('{')][-1])['SYN']
        ok = (ref['found'] and ref['stage'] == 'breakout'
              and abs(ref['cup_depth'] * 100
                      - _ch_out['cup_depth_pct_loose']) < 0.5
              and abs(ref['handle_depth'] * 100
                      - _ch_out['handle_depth_pct_loose']) < 0.5)
        check('C&H vs patterns_v0 (synthetic)', ok,
              f"ref found={ref['found']} stage={ref['stage']} "
              f"depth={round(ref['cup_depth'] * 100, 2)}")

    # 14. feedback_7.md items — RSI, 52w flags, EMA20 pullback,
    # Downtrend reversal
    # (a) RSI: hand-written SMA-seeded Wilder RSI vs indicators.rsi
    #     (ewm form — same recursion, different seed; converges), + bounds
    _c_aapl = stb_data['close']['AAPL'].to_numpy(float)
    delta = np.diff(_c_aapl, prepend=_c_aapl[0])
    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)
    period = config.RSI_PERIOD
    avg_gain = np.full(len(gain), np.nan)
    avg_loss = np.full(len(loss), np.nan)
    avg_gain[period] = gain[1:period + 1].mean()
    avg_loss[period] = loss[1:period + 1].mean()
    for i in range(period + 1, len(gain)):
        avg_gain[i] = (avg_gain[i - 1] * (period - 1) + gain[i]) / period
        avg_loss[i] = (avg_loss[i - 1] * (period - 1) + loss[i]) / period
    rs = avg_gain / np.where(avg_loss == 0, np.nan, avg_loss)
    rsi_ref = 100.0 - 100.0 / (1.0 + rs)
    rsi_mine = float(indicators.rsi(stb_data['close'], period)
                     ['AAPL'].iloc[-1])
    ref_last = rsi_ref[-1]
    check('RSI14 vs hand-written Wilder recursion',
          abs(rsi_mine - ref_last) < 0.01,
          f'ref={ref_last:.4f} ours={rsi_mine:.4f}')
    _rsi_all = indicators.rsi(stb_data['close'], period)
    _valid = _rsi_all.iloc[-1].dropna()
    check('RSI14 bounded [0, 100]',
          bool((_valid >= 0).all() and (_valid <= 100).all()),
          f'min={_valid.min():.2f} max={_valid.max():.2f}')

    # (b) 52w event flags: identity vs the rolling high/low
    _h5, _l5 = stb_data['high'], stb_data['low']
    _rh_prev = indicators.rolling_high(_h5, config.BARS_52W).shift(1)
    _rl_prev = indicators.rolling_low(_l5, config.BARS_52W).shift(1)
    _flag_hi = (_h5.iloc[-1] > _rh_prev.iloc[-1]).fillna(False).astype(bool)
    _flag_lo = (_l5.iloc[-1] < _rl_prev.iloc[-1]).fillna(False).astype(bool)
    # identity: a 52w-high breakout means today's high IS the trailing
    # 252-bar max (the flag's own definition, recomputed independently)
    _is_new_high = (_h5.iloc[-1] >= indicators.rolling_high(
        _h5, config.BARS_52W).iloc[-1])
    _is_new_low = (_l5.iloc[-1] <= indicators.rolling_low(
        _l5, config.BARS_52W).iloc[-1])
    check('52w high breakout flag identity',
          bool((_flag_hi == _is_new_high).all()),
          f'{int(_flag_hi.sum())} breakouts')
    check('52w low breakdown flag identity',
          bool((_flag_lo == _is_new_low).all()),
          f'{int(_flag_lo.sum())} breakdowns')

    # (c) EMA20 pullback: module vs manual 5-condition mask
    from src.leaders import ema20_pullback as e20
    # scooter_score comes from the SCTR section's own computation
    _sctr = sco_mod.compute_scores(stb_data['close'])['scooter_score']
    e20_out = e20.evaluate(stb_data['close'], stb_data['open'],
                           stb_data['low'], _sctr)
    _e20 = indicators.ema(stb_data['close'], 20)
    _e20_last = _e20.iloc[-1]
    _e20_past = _e20.iloc[-1 - config.EMA20_SLOPE_LOOKBACK]
    _m_e20 = ((_sctr.reindex(_e20_last.index) > config.EMA20_SCTR_MIN)
              & (stb_data['open'].iloc[-1] > _e20_last)
              & (stb_data['low'].iloc[-1] < _e20_last)
              & (stb_data['close'].iloc[-1] > _e20_last)
              & (_e20_last > _e20_past))
    _m_e20 = _m_e20.reindex(e20_out.index).fillna(False).astype(bool)
    mine_e20 = e20_out['in_ema20_pullback'].fillna(False).astype(bool)
    check('ema20 pullback: module == manual mask',
          bool((mine_e20 == _m_e20).all()),
          f'n_match={int(mine_e20.sum())}/{len(mine_e20)}')

    # (d) Downtrend reversal: module vs manual chained shifts
    from src.leaders import downtrend_reversal as dtrev_mod
    dtrev_out = dtrev_mod.evaluate(stb_data['high'])
    _h = stb_data['high']
    _dec = _h.shift(1) > _h.shift(2)
    for k in range(2, config.DOWNTREND_REVERSAL_LOOKBACK_DAYS + 1):
        _dec &= _h.shift(k) > _h.shift(k + 1)
    _m_rev = ((_h > _h.shift(1)) & _dec).iloc[-1]
    _m_rev = _m_rev.reindex(dtrev_out.index).fillna(False).astype(bool)
    mine_rev = dtrev_out['in_downtrend_reversal'].fillna(False).astype(bool)
    check('downtrend reversal: module == manual mask',
          bool((mine_rev == _m_rev).all()),
          f'n_match={int(mine_rev.sum())}/{len(mine_rev)}')

    # 15. HVE volume records: vectorized ledger == a literal per-date loop of
    # metaVolume's vol_daily_checker.check_and_update_hve over the same bars
    from src.focus import volume_records as vr
    hve_tk = ['AAPL', 'NVDA', 'KOD', 'NAD', 'NUV', 'BEAG', 'MNST', 'BRK.A']
    hve_data = data_loader.load_price_matrices(hve_tk, verbose=False)
    hve_out, hve_ev, hve_info = vr.evaluate(hve_data['volume'], hve_data['close'])
    _rec, _cut = vr.load_baseline()
    _top = _rec[_rec['n'] == 1].set_index('Symbol')['volume']
    _ok = hve_out.index[hve_out['hve_status'] == 'ok']
    loop_ev = []
    for t in _ok:
        prior = [_top[vr._baseline_symbol(t, set(_top.index))]]
        for d, v in hve_data['volume'][t].loc[lambda s: s.index > _cut].items():
            if pd.notna(v) and v > max(prior):
                loop_ev.append((t, d))
                prior.append(v)
    mine_ev = list(zip(hve_ev['ticker'], hve_ev['date']))
    check('HVE: vectorized ledger == metaVolume per-date loop',
          sorted(mine_ev) == sorted(loop_ev),
          f'{len(mine_ev)} events vs {len(loop_ev)}, {len(_ok)} ok tickers')
    check('HVE: BRK.A maps to baseline BRK-A',
          hve_out.loc['BRK.A', 'hve_status'] != 'no_baseline',
          hve_out.loc['BRK.A', 'hve_status'])
    check('HVE: MNST (volume re-adjusted 2x) is baseline_mismatch',
          hve_out.loc['MNST', 'hve_status'] == 'baseline_mismatch',
          hve_out.loc['MNST', 'hve_status'])
    # synthetic: 2x the record on the latest bar must be a record at bar 0
    _v2 = hve_data['volume'].copy()
    _v2.loc[_v2.index[-1], 'AAPL'] = hve_out.loc['AAPL', 'hve_volume'] * 2
    _o2, _e2, _ = vr.evaluate(_v2)
    check('HVE: synthetic 2x record on latest bar flags',
          _o2.loc['AAPL', 'hve_bars_since'] == 0
          and _o2.loc['AAPL', 'hve_count_50'] >= 1,
          f'bars_since={_o2.loc["AAPL", "hve_bars_since"]}')
    # HV1Y: vectorized == per-ticker idxmax of the trailing window
    _h1 = vr.evaluate_hv1y(hve_data['volume'])
    _bad = []
    for t in hve_tk:
        _s = hve_data['volume'][t]
        if _s.notna().sum() < config.HV1Y_BARS:
            continue
        _w = _s.tail(config.HV1Y_BARS)
        if (_h1.loc[t, 'hv1y_date'] != f'{_w.idxmax():%Y-%m-%d}'
                or _h1.loc[t, 'hv1y_volume'] != _w.max()):
            _bad.append(t)
    check('HV1Y: vectorized == per-ticker trailing-window max', not _bad,
          f'mismatches: {_bad}')

    # 16. 21dma-structure: vectorized == a bar-by-bar replay of the Pine
    # script (EMA21 of high/close/low, trend memory, band distance)
    from src.focus import ma_structure as ms_mod
    ms_tk = ['AAPL', 'NVDA', 'MSFT', 'JPM', 'XOM', 'TSLA', 'PLTR', 'HOOD']
    ms_data = data_loader.load_price_matrices(ms_tk, verbose=False)
    ms_out = ms_mod.evaluate(ms_data['high'], ms_data['low'], ms_data['close'])
    _alpha, _bad = 2 / (config.MA21S_LENGTH + 1), []
    for t in ms_tk:
        _h, _l, _c = (ms_data[k][t].dropna() for k in ('high', 'low', 'close'))
        eh, el, ec, trend = _h.iloc[0], _l.iloc[0], _c.iloc[0], 'up'
        for i in range(1, len(_c)):
            nh = _alpha * _h.iloc[i] + (1 - _alpha) * eh
            nl = _alpha * _l.iloc[i] + (1 - _alpha) * el
            nc = _alpha * _c.iloc[i] + (1 - _alpha) * ec
            if nh > eh and nc > ec and nl > el:
                trend = 'up'
            elif nh < eh and nc < ec and nl < el:
                trend = 'down'
            eh, el, ec = nh, nl, nc
        cl = _c.iloc[-1]
        dist = (0.0 if el <= cl <= eh
                else (cl / eh - 1) * 100 if cl > eh else (cl / el - 1) * 100)
        pb = trend == 'up' and abs(round(dist, 2)) <= config.MA21S_PULLBACK_PCT
        r = ms_out.loc[t]
        if (r['ma21s_trend'] != trend or abs(r['ma21s_dist_pct'] - dist) > 0.011
                or bool(r['in_21dma_pullback']) != pb):
            _bad.append(t)
    check('21dma-structure: vectorized == bar-by-bar Pine replay', not _bad,
          f'mismatches: {_bad}')

    print()
    ok_all = True
    for status, name, detail in results:
        print(f'[{status}] {name}  ({detail})')
        ok_all &= status == PASS
    print(f'\n{sum(s == PASS for s, _, _ in results)}/{len(results)} checks passed')
    sys.exit(0 if ok_all else 1)


if __name__ == '__main__':
    main()

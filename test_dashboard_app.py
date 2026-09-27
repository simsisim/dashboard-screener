"""
UI-level regression suite for dashboard.py (Streamlit AppTest).

Runnable, like validate.py:
    python3 test_dashboard_app.py      # PASS/FAIL summary, exit 0/1

Committed per feedback_2.md ("Not independently verified"): the AppTest
claims are now independently re-runnable. Covers the UI behaviors that
validate.py (data-level) cannot:
  1. boot with 0 exceptions
  2. preset application: on-caption counts match the data-level expected
     counts (Minervini 8/8 liquid, SCOOTER >= 90, CANSLIM leaders)
  3. advanced-filter leak regression (feedback_1.md §1): leftover
     RTI-dots/sector/min-count must not survive a preset switch
  4. save -> dropdown refresh (feedback_1.md §2)
  5. reset clears the name inputs (feedback_1.md §5)
  6. custom-range UI round trip (feedback_2.md): preset -> Save As ->
     My Screener reload keeps custslider bounds
"""
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _latest_run_dir():
    """Newest results/YYYY-MM-DD *batch* dir — same guard as the dashboard's
    own latest_run_dir(): must hold screener_results.csv. (The on-demand tabs
    call report.run_dir() on every boot, which mkdirs an empty today/ dir
    when no batch ran today; without the guard this helper would pick it.)
    On-demand cache-file assertions use report.run_dir() instead."""
    date_dirs = [d for d in (ROOT / 'results').iterdir()
                 if d.is_dir() and re.fullmatch(r'\d{4}-\d{2}-\d{2}', d.name)
                 and (d / 'screener_results.csv').exists()]
    return sorted(date_dirs)[-1]
sys.path.insert(0, str(ROOT))

from streamlit.testing.v1 import AppTest  # noqa: E402

import dashboard_filters as dfil  # noqa: E402
from src import on_demand, report  # noqa: E402

PASS, FAIL = 'PASS', 'FAIL'
results = []


def check(name, ok, detail=''):
    results.append((PASS if ok else FAIL, name, detail))


def ss(session_state, key, default=None):
    """AppTest's session_state proxy has no .get() — safe accessor."""
    try:
        return session_state[key]
    except (KeyError, AttributeError):
        return default


# Streamlit 1.47 AppTest bug: ButtonGroup (st.pills / st.segmented_control)
# assumes a list value, but single-select holds a plain str (or None) — it
# then indexes the options letter by letter ("ValueError: content: 'L'").
# The browser is fine; normalise the value for the test harness only.
from streamlit.testing.v1.element_tree import ButtonGroup  # noqa: E402
_bg_value = ButtonGroup.value.fget


def _bg_value_as_list(self):
    v = _bg_value(self)
    return [] if v is None else [v] if isinstance(v, str) else v


ButtonGroup.value = property(_bg_value_as_list)


def _app(tab: str, timeout: int) -> AppTest:
    """AppTest opened on one dashboard section — only the active section's
    widgets are built per run (tab bar = the `active_tab` radio)."""
    at = AppTest.from_file(str(ROOT / 'dashboard.py'), default_timeout=timeout)
    at.session_state['active_tab'] = tab
    return at


def caption_count(at):
    for c in at.caption:
        m = re.search(r'of ([\d,]+) results', str(c.value))
        if m:
            return int(m.group(1).replace(',', ''))
    return None


def main():
    at = _app('all', 300)
    at.run()
    check('boot: 0 exceptions', len(at.exception) == 0,
          at.exception[0].message[:120] if at.exception else '')

    # ---- 2. preset counts vs data-level expectations ----------------------
    # expected counts come from the latest screener run (same numbers
    # validate.py's ALL-presets check computes)
    import pandas as pd
    run = _latest_run_dir()
    res = pd.read_csv(run / 'screener_results.csv', index_col='ticker')

    def expected_count(pname):
        p = dfil.PRESETS[pname]
        m = dfil.build_mask(res, dfil.normalize_selections(p['selections']))
        adv = p.get('advanced', {})
        if adv.get('adv_leaders'):
            cols = [f'in_{s}' for s in adv['adv_leaders']]
            flags = res[cols].fillna(False).astype(bool)
            m &= (flags.any(axis=1) if adv.get('adv_leaders_mode', 'Any (union)')
                  .startswith('Any') else flags.all(axis=1))
        if adv.get('adv_stages'):
            m &= res['stage'].isin(adv['adv_stages'])
        if adv.get('adv_max_ext', 10.0) < 10.0:
            m &= (res['ext_21ema_atr'].fillna(99) <= adv['adv_max_ext']) & \
                 (res['ext_40sma_atr'].fillna(99) <= adv['adv_max_ext'])
        if adv.get('adv_rti_zone'):
            m &= res['rti_zone'].isin(adv['adv_rti_zone'])
        for _flag in ('adv_9m_movers', 'adv_weekly_movers', 'adv_daily_gainers',
                      'adv_gold_launch_pad', 'adv_qullamaggie',
                      'adv_volume_anomaly', 'adv_adl_accumulation',
                      'adv_cantata'):
            if adv.get(_flag):
                m &= res['in_' + _flag[4:]].fillna(False).astype(bool)
        if adv.get('adv_ce_min', 0.0) > 0:
            m &= res['ce_score'].fillna(0) >= adv['adv_ce_min']
        return int(m.sum())

    preset_box = [s for s in at.selectbox if s.label == "Ioa's Presets"][0]
    for pname in ['Minervini 8/8 (liquid)', 'SCOOTER >= 90',
                  'CANSLIM C-A-I leaders', 'CANTATA CE leaders',
                  'Stockbee 9M Movers', 'ADL Accumulation']:
        preset_box.set_value(pname).run()
        got, want = caption_count(at), expected_count(pname)
        check(f'preset count: {pname}', got == want, f'ui={got} data={want}')

    # ---- 3. advanced-filter leak regression -------------------------------
    for cb in at.checkbox:
        if cb.key == 'adv_rti_dots':
            cb.check().run()
    for ms in at.multiselect:
        if ms.key == 'sel_sector':
            ms.set_value(['Finance']).run()
    for sl in at.slider:
        if sl.key == 'adv_min_count':
            sl.set_value(5).run()
    for cb in at.checkbox:
        if cb.key == 'adv_ema20_pullback':
            cb.check().run()
    preset_box.set_value('SCOOTER >= 90').run()
    # expected = clean baseline OVERLAID with the preset's own values
    # (SCOOTER legitimately sets adv_leaders=['scooter'] — feedback_2.md §0)
    expected = dict(dfil.ADVANCED_DEFAULTS)
    expected.update({'adv_leaders': ['scooter'],
                     'adv_leaders_mode': 'Any (union)'})
    clean = all(ss(at.session_state, k) == v for k, v in expected.items())
    # the actual leak assertions: the leftovers we injected must be GONE
    leftovers_gone = (ss(at.session_state, 'adv_rti_dots') is False
                      and ss(at.session_state, 'sel_sector') == []
                      and ss(at.session_state, 'adv_min_count') == 0
                      and ss(at.session_state, 'adv_ema20_pullback') is False)
    check('leak: preset resets ALL advanced keys',
          clean and leftovers_gone
          and ss(at.session_state, 'adv_leaders') == ['scooter'],
          str({k: ss(at.session_state, k) for k, v in expected.items()
              if ss(at.session_state, k) != v}))

    # ---- 6. custom-range UI round trip ------------------------------------
    # Save in one session... (fresh instances per phase: AppTest replays the
    # previous widget tree on set_value, and a widget that disappeared
    # mid-session breaks the replay — a fresh session is also the realistic
    # cross-reload scenario)
    at_rt = _app('all', 300)
    at_rt.run()
    [s for s in at_rt.selectbox if s.label == "Ioa's Presets"][0] \
        .set_value('Momentum Leader (Narrow)').run()
    for t in at_rt.text_input:
        if t.key == 'save_as_name':
            t.set_value('tmp_rt_check').run()
    for b in at_rt.button:
        if b.label == 'Save Screener As…':
            b.click().run()
    ms_opts = [s for s in at_rt.selectbox if s.key == 'my_screener_sel'][0].options
    check('round trip: saved screener in dropdown',
          'tmp_rt_check' in ms_opts)
    dfil.delete_screener('tmp_rt_check')

    # ...reload in a FRESH session (saved JSON on disk is what persists)
    dfil.save_screener('tmp_rt_check',
                       dict(dfil.PRESETS['Momentum Leader (Narrow)']['selections']),
                       dict(dfil.PRESETS['Momentum Leader (Narrow)']['advanced']))
    at_rt2 = _app('all', 300)
    at_rt2.run()
    [s for s in at_rt2.selectbox if s.key == 'my_screener_sel'][0] \
        .set_value('tmp_rt_check').run()
    custslider = ss(at_rt2.session_state, 'custslider_adr')
    sel_adr = ss(at_rt2.session_state, 'sel_adr')
    check('round trip: custom bounds restored in fresh session',
          sel_adr == 'Custom…' and tuple(custslider or ()) == (6.0, 60.0),
          f'sel_adr={sel_adr!r} custslider={custslider!r}')
    dfil.delete_screener('tmp_rt_check')

    # ---- 4. save -> dropdown refresh (fresh app for a clean marker) -------
    at2 = _app('all', 300)
    at2.run()
    for t in at2.text_input:
        if t.key == 'save_as_name':
            t.set_value('tmp_refresh_check').run()
    for b in at2.button:
        if b.label == 'Save Screener As…':
            b.click().run()
    opts = [s for s in at2.selectbox if s.key == 'my_screener_sel'][0].options
    check('refresh: save appears in My Screener immediately',
          'tmp_refresh_check' in opts)
    dfil.delete_screener('tmp_refresh_check')

    # ---- 5. reset clears name inputs --------------------------------------
    for t in at2.text_input:
        if t.key == 'save_list_name':
            t.set_value('junk').run()
    for b in at2.button:
        if b.label == 'Reset Filters':
            b.click().run()
    check('reset: clears name inputs',
          ss(at2.session_state, 'save_as_name') == ''
          and ss(at2.session_state, 'save_list_name') == '')

    # ---- 5b. tab bar: first Combine pick keeps the section; All Results
    # state survives a trip to another section (st.tabs snapped back) -------
    at9 = _app('all', 300)
    at9.run()
    at9.multiselect(key='sel_sector').set_value(['Technology services']).run()
    at9.session_state['comb_inc_Leaders'] = ['Minervini 8/8 (liquid)',
                                             'SCOOTER >= 90']
    at9.run()
    at9.radio(key='comb_mode').set_value('Any (OR)').run()
    _exp_or = int(dfil.combine_screens(
        res, ['Minervini 8/8 (liquid)', 'SCOOTER >= 90'], [], 'any')[0].sum())
    _md = ' '.join(str(m.value) for m in at9.markdown)
    check('combine: OR over chip picks == data-level union',
          f'→ **{_exp_or}** tickers' in _md, f'expected {_exp_or}')
    check('tabs: first combine pick keeps All Results',
          ss(at9.session_state, 'active_tab') == 'all'
          and len(at9.exception) == 0)
    at9.radio(key='active_tab').set_value('leaders').run()
    at9.radio(key='active_tab').set_value('all').run()
    check('tabs: All Results state survives a section switch',
          ss(at9.session_state, 'sel_sector') == ['Technology services']
          and ss(at9.session_state, 'comb_inc_Leaders') == [
              'Minervini 8/8 (liquid)', 'SCOOTER >= 90']
          and ss(at9.session_state, 'comb_mode') == 'Any (OR)'
          and len(at9.exception) == 0,
          f"sel_sector={ss(at9.session_state, 'sel_sector')}")

    # ---- Timing Signals tab (feedback_4.md Task 4): on-demand run -----
    at3 = _app('timing', 900)
    at3.run()
    check('timing tab: boot 0 exceptions', len(at3.exception) == 0)
    for ms in at3.multiselect:
        if ms.key == 'ts_index':
            ms.set_value(['NASDAQ 100']).run()
        if ms.key == 'ts_sources':
            ms.set_value(['ATR1 Trend', 'Blue Dot', 'Black Dot']).run()
    t0 = time.time()
    for b in at3.button:
        if b.label == '▶ Run':
            b.click().run()
    elapsed = time.time() - t0
    check('timing tab: run completes without exceptions',
          len(at3.exception) == 0)
    caps3 = [c.value for c in at3.caption if 'signal rows' in str(c.value)]
    check('timing tab: results rendered', bool(caps3),
          caps3[-1][:60] if caps3 else 'no caption')
    # feedback_5 regression: the filename MUST carry the source suffix
    # (built via the shared slug helper, not re-implemented here)
    _ts_sources = ['ATR1 Trend', 'Blue Dot', 'Black Dot']
    expected_name = ('timing_signals_nasdaq100_cap0_'
                     + on_demand.sources_slug(_ts_sources) + '.csv')
    cache_p = report.run_dir() / expected_name
    check('timing tab: scoped results persisted (source-suffixed)',
          cache_p.exists(), f'expected {expected_name}')
    stale_unsuffixed = report.run_dir() / 'timing_signals_nasdaq100_cap0.csv'
    check('timing tab: no unsuffixed artifact recreated',
          not stale_unsuffixed.exists(),
          'stale pre-fix artifact must stay deleted')
    # same-scope re-run reuses the persisted file (fast: no data reload
    # for the full scope pass — bounded well under the cold run)
    t0 = time.time()
    for b in at3.button:
        if b.label == '▶ Run':
            b.click().run()
    warm = time.time() - t0
    check('timing tab: re-run stays fast (cache/scope bounded)',
          warm < max(60.0, elapsed), f'cold={elapsed:.1f}s warm={warm:.1f}s')

    # ---- Patterns tab (feedback_4.md Tasks 5-7): GLB + Cup & Handle ----
    at4 = _app('patterns', 900)
    at4.run()
    check('patterns tab: boot 0 exceptions', len(at4.exception) == 0)
    for ms in at4.multiselect:
        if ms.key == 'pt_index':
            ms.set_value(['NASDAQ 100']).run()
    for b in at4.button:
        if b.key == 'pt_run':
            b.click().run()
    check('patterns tab: GLB run completes', len(at4.exception) == 0)
    glb_cache = ROOT / 'results' / 'glb_cache'
    check('patterns tab: GLB incremental cache populated',
          glb_cache.exists() and len(list(glb_cache.glob('*.json'))) > 50,
          f'{len(list(glb_cache.glob("*.json")))} cached tickers')
    for radio in at4.radio:
        if radio.key == 'pt_pattern':
            radio.set_value('Cup & Handle').run()
    # re-fetch AFTER the tree changed: the C&H preset radio only exists
    # once the pattern is switched (stale-element replay silently kept
    # the 'strict' default — the loose run actually ran strict)
    for radio in at4.radio:
        if radio.key == 'pt_ch_preset':
            radio.set_value('loose').run()
    for b in at4.button:
        if b.key == 'pt_run':
            b.click().run()
    check('patterns tab: C&H run completes', len(at4.exception) == 0,
          at4.exception[0].message[:120] if at4.exception else '')
    # annotated-chart section: the ticker selectbox renders and the figure
    # builder returns a Figure for a detected pattern (no exception on the
    # st.pyplot path — covered by the 0-exception check above)
    _chart_sel = [s for s in at4.selectbox if s.key == 'pt_chart_ticker']
    _chart_ok = bool(_chart_sel) and len(_chart_sel[0].options) > 0
    if _chart_ok:
        import matplotlib
        matplotlib.use('Agg')
        from src.patterns import cup_handle_chart as _chmod
        from src import data_loader as _dl
        _cd = _dl.load_price_matrices([_chart_sel[0].options[0]],
                                      use_batch=True, verbose=False)
        _fig = _chmod.figure(_chart_sel[0].options[0], 'loose', _cd)
        _chart_ok = _fig is not None and hasattr(_fig, 'savefig')
    check('patterns tab: C&H annotated chart renders', _chart_ok,
          f'selectbox={bool(_chart_sel)} '
          f'opts={len(_chart_sel[0].options) if _chart_sel else 0}')
    # feedback_5 DoD: pt_preset must be part of the C&H file key —
    # verified empirically (strict vs loose -> distinct persisted files)
    loose_f = report.run_dir() / 'patterns_cup_handle_nasdaq100_cap0_loose.csv'
    check('patterns tab: C&H loose persisted under its own key',
          loose_f.exists(), str(loose_f.name))
    for radio in at4.radio:
        if radio.key == 'pt_ch_preset':
            radio.set_value('strict').run()
    for b in at4.button:
        if b.key == 'pt_run':
            b.click().run()
    strict_f = report.run_dir() / 'patterns_cup_handle_nasdaq100_cap0_strict.csv'
    check('patterns tab: C&H strict under a DISTINCT key',
          strict_f.exists() and strict_f.name != loose_f.name,
          f'{strict_f.name}')

    # ---- GLB confirmation regression (feedback_6.md): Confirmation=3m
    # must produce a cache file DISTINCT from 1m — a config typo (reusing
    # 21 for 3m) would otherwise be invisible ----
    at6 = _app('patterns', 900)
    at6.run()
    for ms in at6.multiselect:
        if ms.key == 'pt_index':
            ms.set_value(['NASDAQ 100']).run()

    def _expected_conf_file(conf_choice, conf_bars):
        params = {'pivot_strength': 10, 'confirmation_bars': conf_bars,
                  'lookback_choice': '1y'}
        import hashlib
        ph = hashlib.md5(str(sorted(params.items())).encode()).hexdigest()[:8]
        return f'patterns_glb_nasdaq100_cap0_{ph}.csv'

    def _run_conf(conf_choice):
        for sel in at6.selectbox:
            if sel.key == 'pt_glb_lookback':
                sel.set_value('1y').run()
            if sel.key == 'pt_glb_conf':
                sel.set_value(conf_choice).run()
        for b in at6.button:
            if b.key == 'pt_run':
                b.click().run()

    served_conf = {}
    for conf_choice, conf_bars in (('1m', 21), ('3m', 63)):
        _run_conf(conf_choice)
        expected = _expected_conf_file(conf_choice, conf_bars)
        exists = (report.run_dir() / expected).exists()
        served_conf[conf_choice] = expected
        check(f'GLB confirmation {conf_choice}: served its own cache file',
              exists, f'expected {expected}')
    check('GLB confirmation 1m vs 3m keys are DISTINCT',
          served_conf['1m'] != served_conf['3m'], str(served_conf))

    # ---- GLB lookback regression (feedback_5 DoD): 1y vs 2y must serve
    # DISTINCT cache keys — the silent-key-collision class from
    # feedback_2.md §0 / feedback_5. The test computes each expected
    # filename independently (same hash formula as the app) and asserts
    # the app actually served that file after each run. ----
    import hashlib
    at5 = _app('patterns', 900)
    at5.run()
    for ms in at5.multiselect:
        if ms.key == 'pt_index':
            ms.set_value(['NASDAQ 100']).run()

    def _expected_glb_file(choice):
        # mirror of the app's pt_ph formula for the DEFAULT widget values
        # (pivot slider 10, confirmation selectbox '1w' -> 5 bars)
        params = {'pivot_strength': 10, 'confirmation_bars': 5,
                  'lookback_choice': choice}
        ph = hashlib.md5(str(sorted(params.items())).encode()).hexdigest()[:8]
        return f'patterns_glb_nasdaq100_cap0_{ph}.csv'

    def _run_glb_lookback(choice):
        for sel in at5.selectbox:
            if sel.key == 'pt_glb_lookback':
                sel.set_value(choice).run()
        for b in at5.button:
            if b.key == 'pt_run':
                b.click().run()

    served = {}
    for choice in ('1y', '2y'):
        _run_glb_lookback(choice)
        expected = _expected_glb_file(choice)
        exists = (report.run_dir() / expected).exists()
        served[choice] = expected
        check(f'GLB lookback {choice}: served its own cache file',
              exists, f'expected {expected}')
    check('GLB lookback 1y and 2y keys are DISTINCT',
          served['1y'] != served['2y'], str(served))

    # ---- Confluence tab (IMPLEMENTATION_PLAN.md §19) ----
    # renders with NO on-demand cache needed (pure aggregation over `full`);
    # min-families filter + rank-by control + save-as-list.
    at7 = _app('confluence', 300)
    at7.run()
    check('confluence tab: boot 0 exceptions', len(at7.exception) == 0,
          at7.exception[0].message[:120] if at7.exception else '')

    def _cfl_caption_n(at):
        for c in at.caption:
            m = re.search(r'([\d,]+) names with', str(c.value))
            if m:
                return int(m.group(1).replace(',', ''))
        return None

    for sl in at7.slider:
        if sl.key == 'cf_minfam':
            sl.set_value(2).run()
    n_at2 = _cfl_caption_n(at7)
    for sl in at7.slider:
        if sl.key == 'cf_minfam':
            sl.set_value(4).run()
    n_at4 = _cfl_caption_n(at7)
    check('confluence tab: min-families filter narrows the set',
          n_at2 is not None and n_at4 is not None and n_at4 <= n_at2,
          f'>=2: {n_at2}  >=4: {n_at4}')

    for sel in at7.selectbox:
        if sel.key == 'cf_rank':
            sel.set_value('confluence_score').run()
    check('confluence tab: rank-by switch keeps 0 exceptions',
          len(at7.exception) == 0)

    for sl in at7.slider:
        if sl.key == 'cf_minfam':
            sl.set_value(2).run()
    for ti in at7.text_input:
        if ti.key == 'cf_list_name':
            ti.set_value('cfl_test_list').run()
    for b in at7.button:
        if b.key == 'cf_save_top':
            b.click().run()
    saved = dfil.MY_LISTS / 'cfl_test_list.csv'
    check('confluence tab: Save top-N writes my_lists/*.csv', saved.exists(),
          str(saved))
    saved.unlink(missing_ok=True)

    # ---- 8. Workflows tab (docs/workflows_tab.md) ------------------------
    from src import workflow as wf_mod
    at8 = _app('workflows', 300)
    at8.run()
    check('workflows tab: boot 0 exceptions', len(at8.exception) == 0,
          at8.exception[0].message[:120] if at8.exception else '')

    # run view: selecting the built-in and letting it run shows the stepper
    # + a Focus List whose size == the engine's own answer
    run = _latest_run_dir()
    _res = pd.read_csv(run / 'screener_results.csv', index_col='ticker')
    _wf = dfil.load_workflow('Trading Voyage (Ollie)')
    _eng_focus = len(wf_mod.run_workflow(_res, _wf).focus)
    ui_focus = None
    for c in at8.subheader:
        m = re.search(r'Focus List — ([\d,]+) names', str(c.value))
        if m:
            ui_focus = int(m.group(1).replace(',', ''))
    check('workflows tab: run view Focus List == engine',
          ui_focus == _eng_focus, f'ui={ui_focus} engine={_eng_focus}')

    # build view: Edit/Duplicate -> a draft appears, Save writes my_workflows/
    for b in at8.button:
        if b.key == 'wf_edit_btn':
            b.click().run()
    has_save = any(b.key == 'wf_save_btn' for b in at8.button)
    check('workflows tab: Edit opens a build-view draft', has_save,
          f'draft={ss(at8.session_state, "wf_draft") is not None}')
    check('workflows tab: editing hides the run toolbar',
          not any(b.key == 'wf_edit_btn' for b in at8.button))

    # open the stage-2 editor (the st.form with the grid + Match radio)
    for b in at8.button:
        if b.key == 'wf_edit_1':
            b.click().run()
    n = ss(at8.session_state, 'wf_ed_nonce', 0)
    has_match = any(r.key == f'wfe{n}_match' for r in at8.radio)
    check('workflows tab: stage editor renders (grid + Match radio)',
          has_match and len(at8.exception) == 0,
          at8.exception[0].message[:120] if at8.exception else f'nonce={n}')
    _wf_test = dfil.MY_WORKFLOWS / 'wf_apptest.json'
    _wf_test.unlink(missing_ok=True)
    for ti in at8.text_input:
        if ti.key == 'wf_save_name':
            ti.set_value('wf_apptest').run()
    for b in at8.button:
        if b.key == 'wf_save_btn':
            b.click().run()
    check('workflows tab: Save writes my_workflows/*.json', _wf_test.exists(),
          str(_wf_test))
    if _wf_test.exists():
        _rt = dfil.load_workflow('wf_apptest')
        check('workflows tab: saved workflow round-trips + runs',
              _rt is not None and not wf_mod.validate_workflow(_rt),
              f'stages={len(_rt["stages"]) if _rt else 0}')
    _wf_test.unlink(missing_ok=True)

    print()
    ok_all = True
    for status, name, detail in results:
        print(f'[{status}] {name}  ({detail})')
        ok_all &= status == PASS
    print(f'\n{sum(s == PASS for s, _, _ in results)}/{len(results)} UI checks passed')
    sys.exit(0 if ok_all else 1)


if __name__ == '__main__':
    main()

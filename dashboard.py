"""
Step-2 Filters — Streamlit dashboard.

Mirrors the StockScreenHero layout from intro.md's dashboard reference
(dashboard_screener.png): a filter panel on top, sortable results table
below, plus the leaders' lists and the focus list.

Run:
  streamlit run dashboard.py
Data: the latest results/YYYY-MM-DD/ produced by run_screeners.py
(a "Re-run screeners" button triggers run_screeners.py via subprocess).
Screening only — NOT backtesting (intro.md).
"""
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / 'results'
sys.path.insert(0, str(ROOT))
import config  # noqa: E402  (module-root paths)
from src import data_loader, on_demand, report  # noqa: E402
from src.timing import atr1_cloud, drwish_dots, pvb  # noqa: E402
from src.patterns import cup_handle, cup_handle_chart, glb  # noqa: E402

st.set_page_config(page_title='Step-2 Filters — Leaders & Focus',
                   layout='wide')

# ---------------------------------------------------------------- data ----
@st.cache_data(ttl=600)
def latest_run_dir() -> Path | None:
    if not RESULTS.exists():
        return None
    date_dirs = [d for d in RESULTS.iterdir()
                 if d.is_dir() and re.fullmatch(r'\d{4}-\d{2}-\d{2}',
                                                d.name)
                 and (d / 'screener_results.csv').exists()]
    runs = sorted(date_dirs, reverse=True)
    return runs[0] if runs else None


@st.cache_data(ttl=600)
def load_tables(run: Path):
    full = pd.read_csv(run / 'screener_results.csv', index_col='ticker')
    focus = pd.read_csv(run / 'focus_list.csv', index_col='ticker') \
        if (run / 'focus_list.csv').exists() else pd.DataFrame()
    leaders = {}
    for name in ('minervini', 'canslim', 'scooter', 'all'):
        p = run / f'leaders_{name}.csv'
        if p.exists():
            df = pd.read_csv(p, index_col='ticker')
            leaders[name] = df
    return full, focus, leaders


def rerun_screeners():
    with st.spinner('Running screeners over the full universe (~1-2 min)...'):
        proc = subprocess.run([sys.executable, str(ROOT / 'run_screeners.py')],
                              capture_output=True, text=True)
    if proc.returncode == 0:
        st.cache_data.clear()
        st.rerun()
    else:
        st.error(f'screener run failed:\n{proc.stderr[-2000:]}')


run = latest_run_dir()
if run is None:
    st.title('Step-2 Filters — Leaders & Focus')
    st.warning('No results yet. Click the button to run the screeners.')
    st.button('Run screeners now', on_click=rerun_screeners, type='primary')
    st.stop()

full, focus, leaders = load_tables(run)
if full is None or not len(full):
    st.error('screener_results.csv is empty — re-run the screeners.')
    st.stop()


# --------------------------------------------------- universe index data ---
@st.cache_data
def universe_index_map():
    """Cached wrapper around on_demand.universe_index_map (single source
    of truth for the universe 'Index' parsing — feedback round-4 cleanup)."""
    return on_demand.universe_index_map()


@st.cache_data
def index_choices():
    counts = {}
    for members in on_demand.universe_index_map().values():
        for idx in members:
            counts[idx] = counts.get(idx, 0) + 1
    return sorted(counts, key=counts.get, reverse=True)


IDX_MAP = universe_index_map()


def parse_ticker_file(f) -> list:
    """Ticker symbols from an uploaded CSV/TXT. Accepts a Symbol/Ticker
    column (or the first column) and comma-separated values inside cells."""
    name = f.name.lower()
    if name.endswith('.csv'):
        df = pd.read_csv(f, dtype=str)
        col = next((c for c in df.columns
                    if str(c).strip().lower() in ('symbol', 'ticker', 'sym')),
                   df.columns[0])
        raw = df[col].astype(str).tolist()
    else:
        raw = f.read().decode('utf-8', errors='ignore').splitlines()
    syms = set()
    for item in raw:
        for part in str(item).split(','):
            p = part.strip().upper()
            if p:
                syms.add(p)
    return sorted(syms)

# --------------------------------------------------------------- header ---
st.title('Step-2 Filters — Leaders & Focus')
c1, c2 = st.columns([3, 2])
c1.markdown(f"**Run date:** `{run.name}`  |  **Tickers:** {len(full):,}  |  "
            f"screening only, not backtesting")
if c2.button('Re-run screeners', on_click=rerun_screeners):
    pass
st.caption(f"Module root: `{ROOT}` — see IMPLEMENTATION_PLAN.md and README.md there.")

tab_focus, tab_leaders, tab_all, tab_timing, tab_patterns, tab_detail = st.tabs(
    ['🎯 Focus List', '🏆 Leaders’ Lists', '🔎 All Results (filter panel)',
     '🕐 Timing Signals', '🌊 Patterns', '📋 Ticker detail'])

# ------------------------------------------ All Results (sketch layout) --
import dashboard_filters as dfil  # noqa: E402


def _init_filter_state():
    for k in dfil.SPEC_BY_KEY:
        st.session_state.setdefault(f'sel_{k}', 'All')
    for k, (label, col, fam) in dfil.SPEC_BY_KEY.items():
        lo, hi, _step = dfil.CUSTOM_RANGE[fam]
        st.session_state.setdefault(f'custlo_{k}', lo)
        st.session_state.setdefault(f'custhi_{k}', hi)
    for k, default in dfil.ADVANCED_DEFAULTS.items():
        st.session_state.setdefault(k, default)
    for k, default in {'result_n': 30, 'sort_order': 'Descending'}.items():
        st.session_state.setdefault(k, default)


def _apply_preset(name: str):
    """Method-template preset -> session state (widgets read it this run).
    Starts from the FULL no-op advanced baseline (feedback_1.md §1) so no
    leftover filter leaks into the new preset; a ('custom', lo, hi)
    selection (tuple in code, list after a JSON round trip — feedback_2.md)
    flips that widget to its 'Custom…' slider."""
    p = dfil.PRESETS[name]
    for k, v in dfil.normalize_selections(p.get('selections', {})).items():
        if isinstance(v, (tuple, list)) and v and v[0] == 'custom':
            st.session_state[f'sel_{k}'] = 'Custom…'
            st.session_state[f'custslider_{k}'] = (float(v[1]), float(v[2]))
        else:
            st.session_state[f'sel_{k}'] = v
    advanced = dict(dfil.ADVANCED_DEFAULTS)     # full clean baseline first
    advanced.update(p.get('advanced', {}))      # then the preset's values
    for k, v in advanced.items():
        st.session_state[k] = v


def _reset_filters():
    """Runs as an on_click callback — i.e. BEFORE the widgets are
    instantiated on the next run, which is the only safe time to write
    widget-backed session_state keys."""
    for k in dfil.SPEC_BY_KEY:
        st.session_state[f'sel_{k}'] = 'All'
    for k, default in dfil.ADVANCED_DEFAULTS.items():
        st.session_state[k] = default
    for k, default in {'search': '', 'my_list_sel': '— None Selected —',
                       'apply_upload': False,
                       'preset_sel': '— None Selected —',
                       'my_screener_sel': '— None Selected —',
                       '_applied_preset': '— None Selected —',
                       '_applied_screener': '— None Selected —',
                       'save_as_name': '', 'save_list_name': '',
                       '_flash': ''}.items():
        st.session_state[k] = default


_init_filter_state()

with tab_all:
    # ---------------- top bar: Presets | Lists | My Screener | My Lists ----
    tb1, tb2, tb3, tb4 = st.columns(4)
    with tb1:
        preset_sel = st.selectbox("Ioa's Presets",
                                  ['— None Selected —'] + list(dfil.PRESETS),
                                  key='preset_sel',
                                  help='built-in method templates that set the '
                                       'filter panel below')
        # apply ONCE per selection (a marker, not the dropdown value —
        # otherwise every rerun would wipe manual widget edits)
        if (preset_sel != '— None Selected —'
                and st.session_state.get('_applied_preset') != preset_sel):
            _apply_preset(preset_sel)
            st.session_state['_applied_preset'] = preset_sel
    with tb2:
        up = st.file_uploader(
            'Upload list (CSV/TXT)', type=['csv', 'txt'], key='lists_uploader',
            help='User-owned uploads — saved to my_lists/. ("Ioa\'s Lists" is '
                 'reserved for curated/shipped lists, per TAXONOMY.md)')
        upload_syms = parse_ticker_file(up) if up is not None else []
        if up is not None:
            matched = [t for t in upload_syms
                       if t in full.index or t.replace('.', '-') in full.index]
            st.caption(f'{len(upload_syms)} symbols, {len(matched)} in universe')
            st.checkbox('Apply uploaded list', key='apply_upload',
                        help='restrict results to the uploaded tickers')
            if st.button('Save upload as list', key='save_upload'):
                nm = Path(up.name).stem
                dfil.save_list(nm, upload_syms)
                st.session_state['_flash'] = f'saved my_lists/{nm}.csv'
                st.rerun()
    with tb3:
        screener_sel = st.selectbox('My Screener',
                                    ['— None Selected —'] + dfil.saved_screeners(),
                                    key='my_screener_sel')
        if (screener_sel != '— None Selected —'
                and st.session_state.get('_applied_screener') != screener_sel):
            _saved = dfil.load_screener(screener_sel)
            if _saved:
                # same clean-baseline pattern as presets (feedback_1.md §1):
                # defaults first, then everything the snapshot captured
                for k, v in dfil.ADVANCED_DEFAULTS.items():
                    st.session_state[k] = v
                for k, v in _saved.get('selections', {}).items():
                    if isinstance(v, (tuple, list)) and v and v[0] == 'custom':
                        # custom range saved by _current_panel — restore the
                        # slider bounds too, not just the 'Custom…' label
                        st.session_state[f'sel_{k}'] = 'Custom…'
                        st.session_state[f'custslider_{k}'] = (float(v[1]),
                                                               float(v[2]))
                    elif k in dfil.SPEC_BY_KEY:
                        st.session_state[f'sel_{k}'] = v
                for k, v in _saved.get('advanced', {}).items():
                    if k in st.session_state or k in dfil.ADVANCED_DEFAULTS:
                        st.session_state[k] = v
            st.session_state['_applied_screener'] = screener_sel
        if st.button('Delete screener', key='del_screener',
                     disabled=screener_sel == '— None Selected —'):
            dfil.delete_screener(screener_sel)
            st.session_state['_flash'] = f'deleted screener {screener_sel}'
            st.rerun()
    with tb4:
        list_sel = st.selectbox('My Lists',
                                ['— None Selected —'] + dfil.saved_lists(),
                                key='my_list_sel')
        if list_sel != '— None Selected —':
            if st.button('Delete list', key='del_list'):
                (dfil.MY_LISTS / f'{list_sel}.csv').unlink(missing_ok=True)
                st.session_state['_flash'] = f'deleted list {list_sel}'
                st.rerun()
    active_list = ([] if list_sel == '— None Selected —'
                   else dfil.load_list(list_sel))

    # flash messages survive the st.rerun() that save actions trigger
    _msg = st.session_state.pop('_flash', None)
    if _msg:
        st.success(_msg)
    st.divider()

    # --------------------------- filter rows (sketch rows 1-4) ------------
    st.subheader('Filters')

    def _thresh_widget(key: str):
        label, _col, fam = dfil.SPEC_BY_KEY[key]
        options = [lbl for lbl, _rng in dfil.THRESHOLD_FAMILIES[fam]] + ['Custom…']
        val = st.selectbox(label, options, key=f'sel_{key}')
        if val == 'Custom…':
            lo0, hi0, step0 = dfil.CUSTOM_RANGE[fam]
            st.slider(f'{label} range', lo0, hi0,
                      (st.session_state[f'custlo_{key}'],
                       st.session_state[f'custhi_{key}']),
                      step=step0, key=f'custslider_{key}')

    r1c1, r1c2, r1c3, r1c4, r1c5 = st.columns(5)
    with r1c1:
        _thresh_widget('mktcap')
    with r1c2:
        st.multiselect('Sector', sorted(full['sector'].dropna().unique()),
                       key='sel_sector')
    with r1c3:
        st.multiselect('Industry Group', sorted(full['industry'].dropna().unique()),
                       key='sel_industry')
    with r1c4:
        _thresh_widget('price')
    with r1c5:
        _thresh_widget('vs10')

    r2c1, r2c2, r2c3, r2c4, r2c5 = st.columns(5)
    for c, k in zip((r2c1, r2c2, r2c3, r2c4, r2c5),
                    ('vs21', 'vs50', 'vs200', 'within_high', 'gain5')):
        with c:
            _thresh_widget(k)

    r3c1, r3c2, r3c3, r3c4, r3c5 = st.columns(5)
    for c, k in zip((r3c1, r3c2, r3c3, r3c4, r3c5),
                    ('gain1m', 'gain3m', 'gain6m', 'adr', 'avgvol')):
        with c:
            _thresh_widget(k)

    r4c1, r4c2, r4c3 = st.columns([1, 1, 3])
    with r4c1:
        _thresh_widget('adv')
    with r4c2:
        _thresh_widget('rsi14')

    # ----------------------------- buttons (sketch) ------------------------
    def _current_panel():
        """Capture the panel for saving. A filter sitting on 'Custom…' is
        stored as ('custom', lo, hi) from its slider key — the bare string
        would silently drop the bounds (feedback_2.md)."""
        _cur = {}
        for k in dfil.SPEC_BY_KEY:
            val = st.session_state[f'sel_{k}']
            if val == 'Custom…':
                lo, hi = st.session_state.get(
                    f'custslider_{k}',
                    (st.session_state[f'custlo_{k}'],
                     st.session_state[f'custhi_{k}']))
                val = ('custom', float(lo), float(hi))
            _cur[k] = val
        _adv = {kk: st.session_state[kk] for kk in dfil.ADVANCED_DEFAULTS}
        return _cur, _adv

    b1, b2, b3, b4 = st.columns([1, 1, 1, 2])
    b1.button('Reset Filters', on_click=_reset_filters,
              help='restores every filter to All / defaults')
    can_overwrite = screener_sel != '— None Selected —'
    if b2.button('Save Screener', disabled=not can_overwrite):
        _cur, _adv = _current_panel()
        _p = dfil.save_screener(screener_sel, _cur, _adv)
        st.session_state['_flash'] = f'saved {_p.name}'
        st.rerun()
    with b3:
        save_as_name = st.text_input('Screener As…', key='save_as_name',
                                     placeholder='name…', label_visibility='collapsed')
        if st.button('Save Screener As…', disabled=not save_as_name.strip()):
            _cur, _adv = _current_panel()
            _p = dfil.save_screener(save_as_name.strip(), _cur, _adv)
            st.session_state['_flash'] = f'saved {_p.name}'
            st.rerun()

    # --------------------- advanced filters (collapsible) ------------------
    with st.expander('Advanced filters (stage, RS, RTI, leaders lists, '
                     'exchange, index…)'):
        a1, a2, a3, a4 = st.columns(4)
        a1.multiselect('Leaders lists',
                       ['minervini', 'canslim', 'scooter', 'cantata'],
                       key='adv_leaders')
        a2.radio('Combine lists', ['Any (union)', 'All (intersection)'],
                 key='adv_leaders_mode', disabled=not st.session_state['adv_leaders'])
        a3.multiselect('Stage', ['1', '2A', '2B', '2C', '3', '4'], key='adv_stages',
                       help='empty = all stages')
        a4.multiselect('RTI zone', ['1', '2', '3'], key='adv_rti_zone',
                       help='empty = all zones')
        a5, a6, a7, a8 = st.columns(4)
        a5.slider('max ext (ATR, both MAs)', -5.0, 10.0, key='adv_max_ext', step=0.5,
                  help='10.0 = off')
        a6.slider('RS % ≥', 0.0, 100.0, key='adv_min_rs', step=1.0)
        a7.slider('Minervini count ≥', 0, 8, key='adv_min_count')
        a8.multiselect('Exchange', sorted(full['exchange'].dropna().unique()),
                       key='adv_exchange')
        a9, a10, a11, a12 = st.columns(4)
        a9.multiselect('Index membership', index_choices(), key='adv_index')
        a10.checkbox('RTI low-vol dots', key='adv_rti_dots')
        a11.checkbox('RTI range expansion', key='adv_rti_exp')
        a12.checkbox('Stockbee 9M mover', key='adv_9m_movers')
        a13, a14, a15, a16 = st.columns(4)
        a13.checkbox('Stockbee 20% weekly mover', key='adv_weekly_movers')
        a14.checkbox('Stockbee 4% daily gainer', key='adv_daily_gainers')
        a15.checkbox('Golden Launch Pad', key='adv_gold_launch_pad')
        a16.multiselect('GMMA state',
                        ['bullish', 'bearish', 'compression_breakout',
                         'expanding', 'bullish_crossover', 'bearish_crossover',
                         'transitioning'], key='adv_gmma_state')
        a17, a18, a19, a20 = st.columns(4)
        a17.checkbox('Qullamaggie suite', key='adv_qullamaggie')
        a18.checkbox('Volume anomaly (3-sigma)', key='adv_volume_anomaly')
        a19.checkbox('ADL accumulation (composite >= 70)', key='adv_adl_accumulation')
        a20, a21, a22, a23 = st.columns(4)
        a20.checkbox('52w high breakout', key='adv_52w_high_breakout')
        a21.checkbox('52w low breakdown', key='adv_52w_low_breakdown')
        a22.checkbox('EMA20 pullback test', key='adv_ema20_pullback')
        a23.checkbox('Downtrend reversal', key='adv_downtrend_reversal')
        a24, a25, _a26, _a27 = st.columns(4)
        a24.checkbox('CANTATA CE leader', key='adv_cantata',
                     help=f'in_cantata: CE >= {config.CANTATA_MIN_CE} of 18')
        a25.slider('CANTATA CE ≥', 0.0, 18.0, key='adv_ce_min', step=0.5,
                   help='0 = off; CET(0-7) + CEF(0-11)')
        st.markdown('**Volume & trend filters**')
        v1, v2, v3, v4 = st.columns(4)
        with v1:
            _thresh_widget('vroc')
        with v2:
            _thresh_widget('adtv')
        with v3:
            _thresh_widget('mfi')
        with v4:
            _thresh_widget('adx')

    # ------------------------------- mask ----------------------------------
    selections = {}
    for key in dfil.SPEC_BY_KEY:
        val = st.session_state[f'sel_{key}']
        if val == 'Custom…':
            lo, hi = st.session_state.get(f'custslider_{key}',
                                          (st.session_state[f'custlo_{key}'],
                                           st.session_state[f'custhi_{key}']))
            selections[key] = ('custom', lo, hi)
        else:
            selections[key] = val

    mask = dfil.build_mask(full, selections)
    if st.session_state['sel_sector']:
        mask &= full['sector'].isin(st.session_state['sel_sector'])
    if st.session_state['sel_industry']:
        mask &= full['industry'].isin(st.session_state['sel_industry'])
    if st.session_state['adv_leaders']:
        cols = [f'in_{s}' for s in st.session_state['adv_leaders']]
        if all(c in full.columns for c in cols):
            flags = full[cols].fillna(False).astype(bool)
            mask &= (flags.any(axis=1)
                     if st.session_state['adv_leaders_mode'].startswith('Any')
                     else flags.all(axis=1))
    if st.session_state['adv_stages']:
        mask &= full['stage'].isin(st.session_state['adv_stages'])
    if st.session_state['adv_max_ext'] < 10.0:
        mask &= (full['ext_21ema_atr'].fillna(99) <= st.session_state['adv_max_ext']) & \
                (full['ext_40sma_atr'].fillna(99) <= st.session_state['adv_max_ext'])
    mask &= full['rs_pct'].fillna(0) >= st.session_state['adv_min_rs']
    if 'minervini_count' in full.columns:
        mask &= full['minervini_count'].fillna(0) >= st.session_state['adv_min_count']
    if st.session_state['adv_rti_zone']:
        mask &= full['rti_zone'].isin(st.session_state['adv_rti_zone'])
    if st.session_state['adv_rti_dots']:
        mask &= full['rti_dots'].fillna(False).astype(bool)
    if st.session_state['adv_rti_exp']:
        mask &= full['rti_expansion'].fillna(False).astype(bool)
    for _flag in ('adv_9m_movers', 'adv_weekly_movers', 'adv_daily_gainers',
                  'adv_gold_launch_pad', 'adv_qullamaggie',
                  'adv_volume_anomaly', 'adv_adl_accumulation',
                  'adv_52w_high_breakout', 'adv_52w_low_breakdown',
                  'adv_ema20_pullback', 'adv_downtrend_reversal',
                  'adv_cantata'):
        if st.session_state.get(_flag):
            mask &= full[f'in_{_flag[4:]}'].fillna(False).astype(bool)
    if st.session_state.get('adv_ce_min', 0.0) > 0 and 'ce_score' in full.columns:
        mask &= full['ce_score'].fillna(0) >= st.session_state['adv_ce_min']
    if st.session_state.get('adv_gmma_state'):
        mask &= full['gmma_state'].isin(st.session_state['adv_gmma_state'])
    if st.session_state['adv_exchange']:
        mask &= full['exchange'].isin(st.session_state['adv_exchange']).fillna(False)
    if st.session_state['adv_index']:
        _sel = set(st.session_state['adv_index'])
        mask &= pd.Series(full.index.map(
            lambda t: bool(IDX_MAP.get(str(t).upper(), frozenset()) & _sel)),
            index=full.index)
    if active_list:
        _variants = {t.replace('.', '-') for t in active_list}
        mask &= pd.Series(full.index.isin(active_list) | full.index.isin(_variants),
                          index=full.index)
    if upload_syms and st.session_state.get('apply_upload'):
        _variants = {t.replace('.', '-') for t in upload_syms}
        mask &= pd.Series(full.index.isin(upload_syms) | full.index.isin(_variants),
                          index=full.index)
    view_cols = ['close', 'scooter_score', 'rs_pct', 'minervini_count', 'stage',
                 'ext_21ema_atr', 'ext_40sma_atr', 'adr20_pct', 'rti', 'rti_zone',
                 'rti_dots', 'rti_expansion', 'rel_volume_today', 'daily_gain_pct',
                 'weekly_gain_pct', 'in_9m_movers', 'in_weekly_movers',
                 'in_daily_gainers', 'glp_spread', 'glp_spread_score',
                 'glp_strong', 'in_gold_launch_pad',
                 'gmma_state', 'gmma_separation_pct', 'gmma_total_spread',
                 'gmma_compression_breakout',
                 'in_volume_anomaly', 'volume_zscore', 'volume_ratio',
                 'rsi14', 'in_52w_high_breakout', 'in_52w_low_breakdown',
                 'in_ema20_pullback', 'ema20', 'in_downtrend_reversal',
                 'in_adl_accumulation', 'adl_composite_score',
                 'adl_consistency_score', 'adl_momentum_score',
                 'adl_alignment_score', 'adl_momentum_signal',
                 'adl_ma_alignment', 'adl_current_streak',
                 'in_qullamaggie', 'qulla_rs_best', 'qulla_qualified_timeframes',
                 'qulla_ma_stack', 'qulla_atr_rs', 'qulla_range_position',
                 'qulla_atr_ext_sma50',
                 'vroc25', 'adtv_50', 'mfi14', 'adx13', 'plus_di13',
                 'minus_di13',
                 'gain_5d', 'gain_1m', 'gain_3m', 'gain_6m',
                 'pct_from_52w_high', 'pct_vs_21ema', 'pct_vs_50sma', 'pct_vs_200sma',
                 'adv50_dollar', 'avg_volume50', 'market_cap', 'exchange', 'sector',
                 'industry', 'index_membership',
                 'in_minervini', 'in_canslim', 'in_scooter', 'sources']
    view_cols = [c for c in view_cols if c in full.columns]
    filtered = full[mask][view_cols]

    # ------------------------- results section (sketch) --------------------
    active_name = (preset_sel if preset_sel != '— None Selected —'
                   else (screener_sel if screener_sel != '— None Selected —'
                         else 'Custom'))
    st.subheader(f'{active_name} – Results')
    sc1, sc2, sc3, sc4 = st.columns([2, 1, 2, 1])
    search = sc1.text_input('Search', key='search', placeholder='Ticker or name…')
    n_results = sc2.selectbox('Number of Results', [30, 50, 100, 500, 'All'],
                              key='result_n')
    order_by = sc3.selectbox('Order Results by', view_cols, key='order_by')
    sort_order = sc4.selectbox('Sort Order', ['Descending', 'Ascending'],
                               key='sort_order')

    result = filtered
    if search.strip():
        q = search.strip().lower()
        hit = pd.Series(full.index.str.lower().str.contains(q), index=full.index)
        if 'description' in full.columns:
            hit |= full['description'].astype(str).str.lower().str.contains(
                q, na=False)
        result = result[hit.reindex(result.index).fillna(False)]
    result = result.sort_values(
        order_by, ascending=st.session_state['sort_order'].startswith('Asc'))
    n_show = len(result) if n_results == 'All' else min(int(n_results), len(result))
    st.caption(f'Showing 1 to {n_show:,} of {len(result):,} results '
               f'({len(full):,} tickers screened)')
    show = result if n_results == 'All' else result.head(int(n_results))

    # ---- sparkline closes for the shown rows (lazy per-ticker read) -------
    @st.cache_data(show_spinner=False)
    def _spark_closes(symbol: str, run_name: str):
        """Last ~120 daily closes for one ticker; None when no file.
        run_name IS part of the cache key (no leading underscore) so a
        fresh screener run re-reads the updated daily files."""
        for stem in (symbol, symbol.replace('.', '-')):
            for base in (config.DAILY_CURRENT, config.DAILY_ARCHIVE):
                p = base / f'{stem}.csv'
                if p.exists():
                    try:
                        s = pd.read_csv(p, usecols=['Close'])['Close']
                        return [round(float(x), 2) for x in s.tail(120)]
                    except Exception:
                        return None
        return None

    table = show.round(2).copy()
    col_cfg = None
    if len(table) <= 200:          # sparklines only for page-sized views
        table.insert(1, 'spark', [_spark_closes(t, run.name) for t in table.index])
        col_cfg = {'spark': st.column_config.LineChartColumn(
            '120d', width=170, help='last ~120 daily closes')}

    event = st.dataframe(
        table, use_container_width=True,
        height=min(120 + 35 * max(1, len(table)), 760),
        on_select='rerun', selection_mode='multi-row', key='results_sel',
        column_config=col_cfg,
    )
    try:
        rows = event.selection.rows
    except AttributeError:
        rows = (event.get('selection', {}) or {}).get('rows', []) \
            if isinstance(event, dict) else []
    selected_tickers = list(table.index[rows]) if rows else []
    if selected_tickers:
        st.caption(f'**{len(selected_tickers)} row(s) selected**: '
                   f'{", ".join(selected_tickers[:12])}'
                   f'{" …" if len(selected_tickers) > 12 else ""}')

    # ----------------------- export / list-save actions --------------------
    d1, d2, d3 = st.columns([1, 1, 3])
    d1.download_button('Download CSV (all results)',
                       result.round(3).to_csv().encode(),
                       file_name=f'filtered_{run.name}.csv')
    if selected_tickers:
        d1.download_button('Download CSV (selected)',
                           result.loc[selected_tickers].round(3).to_csv().encode(),
                           file_name=f'selected_{run.name}.csv')
    list_name = d2.text_input('List name', key='save_list_name',
                              placeholder='list name…')
    save_selected = d2.button('Save SELECTED as list',
                              disabled=not (list_name.strip() and selected_tickers),
                              help='save just the tickers you ticked in the table')
    save_all = d3.button('Save ALL results as list',
                         disabled=not list_name.strip())
    if (save_selected or save_all) and list_name.strip():
        tickers = selected_tickers if save_selected else result.index
        dfil.save_list(list_name.strip(), tickers)
        st.session_state['_flash'] = (f'saved {len(tickers)} tickers to '
                                      f'my_lists/{list_name.strip()}.csv')
        st.rerun()

# ------------------------------------------------------------ leaders -----
with tab_leaders:
    for name, label in [('minervini', 'Minervini trend template (8/8)'),
                        ('canslim', 'CANSLIM C-A-I'),
                        ('scooter', 'SCOOTER / SCTR ≥ 90'),
                        ('all', 'Union (deduped, all lists)')]:
        df = leaders.get(name)
        with st.expander(f'{label} — {0 if df is None else len(df)} tickers',
                         expanded=(name == 'all')):
            if df is not None and len(df):
                st.dataframe(df.round(2), use_container_width=True, height=360)
                st.download_button(f'Download leaders_{name}.csv',
                                   df.round(3).to_csv().encode(),
                                   file_name=f'leaders_{name}_{run.name}.csv')

# ------------------------------------------------------------- focus ------
with tab_focus:
    st.markdown(f"**{len(focus)} tickers** — leaders ∩ stage ∈ {{2A, 2B}} ∩ "
                f"not very-extended ∩ liquid. Sorted by SCOOTER.")
    if len(focus):
        st.dataframe(focus.round(2), use_container_width=True, height=520)
        st.download_button('Download focus_list.csv',
                           focus.round(3).to_csv().encode(),
                           file_name=f'focus_list_{run.name}.csv')
    else:
        st.info('Empty focus list in this run.')

# ------------------------------------------------------------- detail -----
with tab_detail:
    ticker = st.selectbox('Ticker', sorted(full.index))
    if ticker:
        row = full.loc[ticker]
        left, right = st.columns([1, 2])
        left.metric('Close', f"{row['close']:,.2f}")
        if 'scooter_score' in row:
            left.metric('SCOOTER', f"{row['scooter_score']:.1f}")
        if 'rs_pct' in row:
            left.metric('RS %', f"{row['rs_pct']:.1f}")
        right.markdown(
            f"**{row.get('description', '')}**  \n"
            f"{row.get('sector', '')} / {row.get('industry', '')} — "
            f"{row.get('exchange', '')}  \n"
            f"Stage **{row.get('stage', '?')}** | ext21 **{row.get('ext_21ema_atr', '?')}** "
            f"ATR | ext40 **{row.get('ext_40sma_atr', '?')}** ATR | "
            f"ADR20 **{row.get('adr20_pct', '?')}**% | RTI **{row.get('rti', '?')}** "
            f"(zone {row.get('rti_zone', '?')})")
        detail = row.to_frame('value')
        detail['value'] = detail['value'].map(
            lambda v: f'{v:,.3f}' if isinstance(v, float) else str(v))
        st.dataframe(detail, use_container_width=True, height=560)

st.caption(f"Step-2 Filters module — Minervini / CANSLIM C-A-I / SCOOTER leaders; "
           f"ATR-ext vs 21EMA & 40SMA, ADR, Weinstein stages, RTI focus metrics. "
           f"Data: downloadData_v1 (universe + daily bars + financial snapshot).")

# ------------------------------------------------- Timing Signals (on-demand)
# feedback_4.md Task 4 — on-demand scoped computation, NOT the daily batch.
# Shared scope/run/progress/persist plumbing lives in src/on_demand.py.

TIMING_SOURCES = {
    # ui label -> (module key, evaluate fn, state options)
    'PVB': ('pvb', pvb.evaluate,
            ['Buy', 'Sell', 'Close Buy', 'Close Sell', 'No Signal']),
    'ATR1 Trend': ('atr1', atr1_cloud.evaluate,
                   ['uptrend', 'downtrend']),
    'Blue Dot': ('dots', drwish_dots.evaluate, ['Blue Dot']),
    'Black Dot': ('dots', drwish_dots.evaluate, ['Black Dot']),
}


def _timing_long_table(combined: dict, current_close: pd.Series) -> pd.DataFrame:
    """Per-source result frames -> one long row-per-(ticker, source) table."""
    rows = []
    for source_name, df in combined.items():
        for t, r in df.iterrows():
            cur = current_close.get(t)
            if source_name == 'PVB':
                rows.append({
                    'ticker': t, 'source': 'PVB',
                    'signal_state': r['pvb_signal'],
                    'days_since': r['pvb_days_since_signal'],
                    'signal_price': r['pvb_signal_price'],
                    'current_price': cur,
                    'pct_chg_since_signal': r['pvb_performance_since_signal'],
                    'stop_level': None,
                    'as_of': r.get('as_of'),
                })
            elif source_name == 'ATR1 Trend':
                rows.append({
                    'ticker': t, 'source': 'ATR1 Trend',
                    'signal_state': r['atr1_trend'],
                    'days_since': r.get('atr1_days_since_signal'),
                    'signal_price': r.get('atr1_signal_price'),
                    'current_price': cur,
                    'pct_chg_since_signal': r.get('atr1_performance_since_signal'),
                    'stop_level': r['atr1_stop_level'],
                    'as_of': r.get('as_of'),
                })
            else:  # dots module — emit a row per dot that actually fired
                # (the module is shared by the Blue/Black labels, so check
                #  both columns no matter which label selected it)
                for dot_name, col in (('Blue Dot', 'in_blue_dot'),
                                      ('Black Dot', 'in_black_dot')):
                    if bool(r.get(col, False)):
                        rows.append({
                            'ticker': t, 'source': dot_name,
                            'signal_state': dot_name,
                            'days_since': 0,
                            'signal_price': cur,
                            'current_price': cur,
                            'pct_chg_since_signal': None,
                            'stop_level': None,
                            'as_of': r.get('as_of'),
                        })
    long_df = pd.DataFrame(rows)
    if len(long_df):
        long_df = long_df.set_index('ticker')
    return long_df


@st.cache_data(show_spinner=False)
def _spark_closes_ts(symbol: str, run_name: str):
    for stem in (symbol, symbol.replace('.', '-')):
        for base in (config.DAILY_CURRENT, config.DAILY_ARCHIVE):
            p = base / f'{stem}.csv'
            if p.exists():
                try:
                    s = pd.read_csv(p, usecols=['Close'])['Close']
                    return [round(float(x), 2) for x in s.tail(120)]
                except Exception:
                    return None
    return None


with tab_timing:
    st.caption('On-demand timing signals — computed for the scoped subset '
               'only (never part of the daily batch). Each row shows its '
               'own as-of bar date.')

    # ---------------- scope ----------------
    ts1, ts2, _ts3 = st.columns([3, 2, 2])
    ts_indexes = ts1.multiselect('Scope: index membership', index_choices(),
                                 default=['S&P 500'], key='ts_index')
    ts_cap = ts2.select_slider('Min market cap',
                               options=[0, 300e6, 1e9, 2e9, 10e9],
                               value=0, key='ts_cap',
                               format_func=lambda v: f'${v:,.0f}')
    if set(ts_indexes) & {'Russell 3000', 'NASDAQ Composite',
                          'Mini-Russell 2000', 'STOXX Global 1800'}:
        st.warning('Wide scope — may take longer.')
    ts_sources = st.multiselect('Signal source', list(TIMING_SOURCES),
                                default=['Blue Dot'], key='ts_sources')
    ts_force = st.checkbox('Force re-run (ignore today\'s cache)',
                           key='ts_force')

    # the cache key must cover EVERY result-affecting input: scope AND the
    # selected sources (switching Blue Dot -> PVB must not serve the old
    # source's cached file — same class as the feedback_5 GLB key bug)
    ts_key = on_demand.scope_key(ts_indexes, ts_cap)
    if ts_sources:
        ts_key += '_' + on_demand.sources_slug(ts_sources)
    ts_run_dir = report.run_dir()

    ts_run = st.button('▶ Run', key='ts_run',
                       disabled=not (ts_sources and ts_indexes))

    if ts_run:
        # same-day cache reuse comes FIRST — a cached run skips the data
        # load and the compute entirely (feedback_4.md: "check for it
        # before running"); 'Force re-run' bypasses it
        cached_ts = None
        if not ts_force:
            cached_ts = on_demand.load_cached(ts_run_dir, 'timing_signals',
                                              ts_key)
        if cached_ts is not None:
            st.session_state['ts_results'] = cached_ts
            st.session_state['ts_scope_key'] = ts_key
            st.info('Reused today\'s cached run for this scope (tick '
                    "'Force re-run' to recompute).")
        else:
            tickers = on_demand.resolve_scope(ts_indexes, ts_cap,
                                              full['market_cap'])
            if not tickers:
                st.warning('Scope resolved to 0 tickers.')
            else:
                st.info(f'{len(tickers)} tickers in scope — loading data…')
                data_ts = data_loader.load_price_matrices(
                    tickers, use_batch=True, verbose=False)
                # dedupe: Blue/Black Dot share one module
                module_keys = {TIMING_SOURCES[s][0] for s in ts_sources}
                sources = {}
                for s in ts_sources:
                    mkey, fn, _opts = TIMING_SOURCES[s]
                    sources.setdefault(mkey, (s, fn))
                bar = st.progress(0.0, text='Processing 0/'
                                  f'{len(tickers)} tickers…')

                def _cb(done, total):
                    bar.progress(done / total,
                                 text=f'Processing {done}/{total} tickers…')

                combined = on_demand.run_scoped(
                    tickers, data_ts,
                    {k: v[1] for k, v in sources.items()}, _cb)
                # run_scoped keys by module key ('atr1', 'dots', 'pvb') —
                # the long-table builder branches on the UI label: rename
                combined = {sources[k][0]: v for k, v in combined.items()}
                bar.empty()
                long_df = _timing_long_table(combined, full['close'])
                p = on_demand.persist(ts_run_dir, 'timing_signals', ts_key,
                                      long_df)
                st.session_state['ts_results'] = long_df
                st.session_state['ts_scope_key'] = ts_key
                st.success(f'saved {p.name}')

    # first visit to the tab (no Run clicked): show today's cached run
    if not ts_run and not ts_force:
        cached = on_demand.load_cached(ts_run_dir, 'timing_signals', ts_key)
        if cached is not None:
            st.session_state['ts_results'] = cached
            st.session_state['ts_scope_key'] = ts_key

    ts_results = st.session_state.get('ts_results')
    ts_active_key = st.session_state.get('ts_scope_key')

    # state filter + max-days render PERMANENTLY with a pre-registered
    # session key (an appear/disappear widget breaks AppTest replay and
    # UX alike); values are clamped to the available options each run
    _all_states = ['Buy', 'Sell', 'Close Buy', 'Close Sell', 'No Signal',
                   'uptrend', 'downtrend', 'Blue Dot', 'Black Dot']
    _avail = (sorted(ts_results['signal_state'].unique())
              if ts_results is not None and len(ts_results) else _all_states)
    st.session_state['ts_states'] = [
        s for s in st.session_state.get('ts_states', _avail) if s in _avail
    ] or list(_avail)
    f1, f2 = st.columns([2, 1])
    ts_states = f1.multiselect('State filter', _avail, key='ts_states')
    ts_max_days = f2.slider('Max days since signal', 0, 30, 10,
                            key='ts_max_days',
                            help='rows without a signal age (dots, '
                                 'ATR1 trend) always pass')

    if ts_results is not None and not len(ts_results):
        st.info('Run completed: 0 signals fired in this scope for the '
                'selected source(s).')
    if ts_results is not None and len(ts_results):
        if ts_active_key != ts_key:
            st.caption(f"Showing the cached run for scope `{ts_active_key}` "
                       f"(current scope `{ts_key}` — press ▶ Run to "
                       f"recompute).")

        view = ts_results
        if ts_states:
            view = view[view['signal_state'].isin(ts_states)]
        if 'days_since' in view.columns:
            days = pd.to_numeric(view['days_since'], errors='coerce')
            view = view[days.isna() | (days <= ts_max_days)]

        view = view.sort_values('days_since', ascending=False,
                                na_position='last')
        st.caption(f'{len(view):,} signal rows '
                   f'(scope key `{ts_active_key}`)')
        show = view.head(300).copy()
        if len(show) <= 200:
            show.insert(len(show.columns), 'spark',
                        [_spark_closes_ts(t, run.name) for t in show.index])
        st.dataframe(
            show,
            use_container_width=True,
            height=min(120 + 32 * max(1, len(show)), 700),
            column_config={
                'spark': st.column_config.LineChartColumn('120d', width=170),
            },
        )
        d1, d2, _d3 = st.columns([1, 1, 3])
        d1.download_button('Download CSV', view.to_csv().encode(),
                           file_name=f'timing_signals_{ts_key}_{run.name}.csv')
        ln = d2.text_input('List name', key='ts_list_name',
                           placeholder='list name…')
        if d2.button('Save as list', key='ts_save_list',
                     disabled=not ln.strip()):
            dfil.save_list(ln.strip(), view.index)
            st.success(f'saved {len(view)} tickers to '
                       f'my_lists/{ln.strip()}.csv')

# --------------------------------------------------- Patterns (on-demand)
# feedback_4.md Task 7 — pattern-geometry detectors with user-adjustable
# parameters (GLB sliders; Cup & Handle named presets). Same shared
# scope/Run/progress/persist plumbing as the Timing Signals tab.

with tab_patterns:
    st.caption('On-demand pattern detectors — scoped computation; GLB '
               'uses an incremental per-ticker cache (results/glb_cache/).')

    pt1, pt2, _pt3 = st.columns([3, 2, 2])
    pt_indexes = pt1.multiselect('Scope: index membership', index_choices(),
                                 default=['S&P 500'], key='pt_index')
    pt_whole_universe = pt1.checkbox(
        'Or run against the WHOLE universe (ignore index selection above)',
        key='pt_whole_universe',
        help='Every ticker in tradingview_universe.csv, not just one '
             'index — the same universe Leaders/Focus are built from.')
    # resolve_scope/scope_key already treat an EMPTY index list as "match
    # everything" — the checkbox just makes that reachable/discoverable
    # instead of requiring the user to deselect every tag to get there.
    pt_scope_indexes = [] if pt_whole_universe else pt_indexes
    pt_cap = pt2.select_slider('Min market cap',
                               options=[0, 300e6, 1e9, 2e9, 10e9],
                               value=0, key='pt_cap',
                               format_func=lambda v: f'${v:,.0f}')
    if pt_whole_universe or set(pt_indexes) & {
            'Russell 3000', 'NASDAQ Composite',
            'Mini-Russell 2000', 'STOXX Global 1800'}:
        st.warning('Wide scope — may take longer.')

    pt_pattern = st.radio('Pattern', ['Green Line Breakout (GLB)',
                                      'Cup & Handle'],
                          key='pt_pattern', horizontal=True)

    pt_params = {}
    pt_compare = False
    if pt_pattern.startswith('Green Line'):
        g1, g2, g3 = st.columns(3)
        pt_params['pivot_strength'] = g1.slider('Pivot strength', 3, 20,
                                                config.GLB_PIVOT_STRENGTH,
                                                key='pt_glb_strength',
                                                help='bars left/right of a '
                                                     'pivot high')
        pt_compare = st.checkbox(
            'Compare multiple lookback/confirmation combos instead of one',
            key='pt_glb_compare',
            help='Pick which combos to run at once below — pivot '
                 'detection and rolling windows are shared across combos '
                 'that agree on a setting, so ticking more of them stays '
                 'fast. Pivot strength above is shared by all of them.')
        pt_selected_names = []
        if pt_compare:
            g2.selectbox('Lookback period', ['3m', '6m', '1y', '2y',
                                             'complete'],
                        key='pt_glb_lookback', disabled=True,
                        help='ignored while comparing combos')
            g3.selectbox('Confirmation period', ['1w', '2w', '1m', '3m'],
                        key='pt_glb_conf', disabled=True,
                        help='ignored while comparing combos')
            hc1, hc2, hc3, hc4 = st.columns([1, 2, 1.3, 1.6])
            hc1.markdown('**Run**')
            hc2.markdown('**Combo**')
            hc3.markdown('**Lookback**')
            hc4.markdown('**Confirmation**')
            for c in config.GLB_PRESET_CHOICES:
                rc1, rc2, rc3, rc4 = st.columns([1, 2, 1.3, 1.6])
                checked = rc1.checkbox(
                    c['label'], key=f"pt_glb_combo_{c['name']}",
                    value=c['name'] in config.GLB_PRESET_DEFAULT_SELECTED,
                    label_visibility='collapsed')
                rc2.write(c['label'])
                rc3.write(f"{c['lookback_bars']} bars")
                rc4.write(f"{c['confirmation_bars']} bars")
                if checked:
                    pt_selected_names.append(c['name'])
            if not pt_selected_names:
                st.warning('Pick at least one combo to run.')
        else:
            _lb_choice = g2.selectbox('Lookback period',
                                      ['3m', '6m', '1y', '2y', 'complete'],
                                      key='pt_glb_lookback')
            _lb_bars = {'3m': 63, '6m': 126, '1y': 252,
                       '2y': 504}.get(_lb_choice)
            _conf = g3.selectbox('Confirmation period',
                                 ['1w', '2w', '1m', '3m'],
                                 key='pt_glb_conf')
            # '3m' = 63 bars, same day-count convention as the Lookback
            # dropdown's own '3m': 63 mapping (feedback_6.md)
            pt_params['confirmation_bars'] = {'1w': 5, '2w': 10, '1m': 21,
                                              '3m': 63}[_conf]
            # the cache key hash covers the LOOKBACK CHOICE (widget state)
            # — lookback_bars itself is only resolved after data load
            # ('complete' needs the bar count); hashing the widget state
            # means any visible parameter change produces a different key
            # (feedback_5 class bug)
            pt_params['lookback_choice'] = _lb_choice
    else:
        pt_preset = st.radio('Cup & Handle preset',
                             ['strict', 'default', 'loose'],
                             key='pt_ch_preset', horizontal=True,
                             help='Strict = O\'Neil-style textbook; Loose = '
                                  'patterns_v0 tuned config (permissive)')

    pt_key = on_demand.scope_key(pt_scope_indexes, pt_cap)
    if pt_pattern.startswith('Green Line') and pt_compare:
        import hashlib
        pt_ph = hashlib.md5(
            str((pt_params['pivot_strength'],
                sorted(pt_selected_names))).encode()) \
            .hexdigest()[:8]
        pt_file_key = f'glb_compare_{pt_key}_{pt_ph}'
    elif pt_pattern.startswith('Green Line'):
        import hashlib
        pt_ph = hashlib.md5(str(sorted(pt_params.items())).encode()) \
            .hexdigest()[:8]
        pt_file_key = f'glb_{pt_key}_{pt_ph}'
    else:
        pt_file_key = f'cup_handle_{pt_key}_{pt_preset}'
    pt_run_dir = report.run_dir()

    pt_combo_ok = not (pt_pattern.startswith('Green Line') and pt_compare
                      and not pt_selected_names)
    pt_run = st.button('▶ Run', key='pt_run',
                       disabled=not (pt_indexes or pt_whole_universe)
                       or not pt_combo_ok)

    if pt_run:
        cached_pt_early = on_demand.load_cached(pt_run_dir, 'patterns',
                                                pt_file_key)
        if cached_pt_early is not None:
            st.session_state['pt_results'] = cached_pt_early
            st.session_state['pt_file_key'] = pt_file_key
            st.info("Reused today's cached run for this scope+parameters "
                    "(recompute happens tomorrow, or via Download after a "
                    "forced re-run).")
        else:
            tickers = on_demand.resolve_scope(pt_scope_indexes, pt_cap,
                                              full['market_cap'])
            if not tickers:
                st.warning('Scope resolved to 0 tickers.')
            else:
                data_pt = data_loader.load_price_matrices(
                    tickers, use_batch=True, verbose=False)
                bar = st.progress(0.0, text='Processing 0/'
                                  f'{len(tickers)} tickers…')

                def _cb_pt(done, total):
                    bar.progress(done / total,
                                 text=f'Processing {done}/{total} tickers…')

                if pt_pattern.startswith('Green Line') and pt_compare:
                    choices_by_name = {c['name']: c
                                      for c in config.GLB_PRESET_CHOICES}
                    scenarios = {
                        name: {'lookback_bars':
                              choices_by_name[name]['lookback_bars'],
                              'confirmation_bars':
                              choices_by_name[name]['confirmation_bars'],
                              'pivot_strength': pt_params['pivot_strength']}
                        for name in pt_selected_names
                    }
                    pt_df = glb.evaluate_multi(tickers, data_pt, scenarios)
                elif pt_pattern.startswith('Green Line'):
                    _lbs = len(data_pt.get('close', pd.DataFrame()))
                    if _lb_choice == 'complete':
                        pt_params['lookback_bars'] = max(_lbs - 20, 100)
                    elif _lb_bars:
                        pt_params['lookback_bars'] = min(_lb_bars,
                                                         max(_lbs - 20, 100))
                    pt_df = glb.evaluate(tickers, data_pt, pt_params)
                else:
                    pt_df = cup_handle.evaluate(tickers, data_pt,
                                                presets=[pt_preset])
                bar.empty()
                p = on_demand.persist(pt_run_dir, 'patterns', pt_file_key,
                                      pt_df)
                st.session_state['pt_results'] = pt_df
                st.session_state['pt_file_key'] = pt_file_key
                st.success(f'saved {p.name}')

    if not pt_run:
        cached_pt = on_demand.load_cached(pt_run_dir, 'patterns',
                                          pt_file_key)
        if cached_pt is not None:
            st.session_state['pt_results'] = cached_pt
            st.session_state['pt_file_key'] = pt_file_key

    pt_results = st.session_state.get('pt_results')
    pt_active = st.session_state.get('pt_file_key')

    if pt_results is not None and len(pt_results):
        if pt_active != pt_file_key:
            st.caption(f"Showing cached run `{pt_active}` (current "
                       f"`{pt_file_key}` — press ▶ Run to recompute).")
        st.caption(f'{len(pt_results):,} tickers processed '
                   f'(scope key `{pt_active}`)')
        is_glb_compare = pt_pattern.startswith('Green Line') and any(
            c.startswith('in_glb_breakout_') for c in pt_results.columns)
        if is_glb_compare:
            # combo selection is now user-driven (the table above), not a
            # fixed config list — read back which ones this run actually
            # has, in the table's display order
            preset_names = [c['name'] for c in config.GLB_PRESET_CHOICES
                            if f"in_glb_breakout_{c['name']}"
                            in pt_results.columns]
            view_cols_pt = ['as_of']
            for name in preset_names:
                view_cols_pt += [f'in_glb_breakout_{name}',
                                 f'glb_level_{name}',
                                 f'glb_detection_date_{name}',
                                 f'glb_days_since_pivot_{name}']
        elif pt_pattern.startswith('Green Line'):
            view_cols_pt = ['in_glb_breakout', 'glb_level',
                            'glb_detection_date', 'glb_days_since_pivot',
                            'as_of']
        else:
            view_cols_pt = [c for c in pt_results.columns
                            if pt_preset in c or c == 'as_of']
        view_cols_pt = [c for c in view_cols_pt if c in pt_results.columns]
        show_pt = pt_results[view_cols_pt].copy()
        if is_glb_compare:
            breakout_cols = [c for c in show_pt.columns
                             if c.startswith('in_glb_breakout_')]
            if breakout_cols:
                show_pt = show_pt[show_pt[breakout_cols].any(axis=1)]
        elif 'in_glb_breakout' in show_pt.columns:
            show_pt = show_pt[show_pt['in_glb_breakout'] == True]  # noqa: E712
        elif 'in_cup_handle_' + pt_preset in show_pt.columns:
            show_pt = show_pt[
                show_pt['in_cup_handle_' + pt_preset] == True]  # noqa: E712
        st.caption(f'{len(show_pt):,} with a signal found '
                  f'(out of {len(pt_results):,} processed)')
        if len(show_pt) <= 200:
            show_pt.insert(len(show_pt.columns), 'spark',
                           [_spark_closes_ts(t, run.name)
                            for t in show_pt.index])
        st.dataframe(show_pt, use_container_width=True,
                     height=min(120 + 32 * max(1, len(show_pt)), 700),
                     column_config={
                         'spark': st.column_config.LineChartColumn(
                             '120d', width=170)})
        d1, d2, _d3 = st.columns([1, 1, 3])
        d1.download_button('Download CSV', pt_results.to_csv().encode(),
                           file_name=f'patterns_{pt_file_key}_{run.name}.csv')
        ln = d2.text_input('List name', key='pt_list_name',
                           placeholder='list name…')
        if d2.button('Save as list', key='pt_save_list',
                     disabled=not ln.strip()):
            dfil.save_list(ln.strip(), show_pt.index)
            st.success(f'saved {len(show_pt)} tickers to '
                       f'my_lists/{ln.strip()}.csv')

        # ---- annotated cup & handle chart for a selected ticker ----
        if not pt_pattern.startswith('Green Line') and len(show_pt):
            st.markdown('---')
            chart_t = st.selectbox(
                'Annotated chart (K-A-B-C-D, stages, target/stop, RCQ/HQ/CQ)',
                list(show_pt.index), key='pt_chart_ticker')
            if chart_t:
                try:
                    _cd = data_loader.load_price_matrices(
                        [chart_t], use_batch=True, verbose=False)
                    _fig = cup_handle_chart.figure(chart_t, pt_preset, _cd)
                    if _fig is None:
                        st.info(f'{chart_t}: the detector no longer resolves '
                                'a pattern for this preset (data changed since '
                                'the run).')
                    else:
                        st.pyplot(_fig)
                        import matplotlib.pyplot as _plt
                        _plt.close(_fig)
                except Exception as _e:                    # noqa: BLE001
                    st.warning(f'chart failed for {chart_t}: {_e}')
    elif pt_results is not None:
        st.info('Run completed: 0 patterns detected in this scope with '
                'the current parameters.')

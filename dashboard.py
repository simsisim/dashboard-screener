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

import numpy as np
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / 'results'
sys.path.insert(0, str(ROOT))
import config  # noqa: E402  (module-root paths)
from src import confluence, data_loader, on_demand, report  # noqa: E402
from src import workflow as wf_engine  # noqa: E402
from src.patterns import cup_handle, cup_handle_chart, glb  # noqa: E402
from src.focus import volume_records  # noqa: E402
from src import leader_map  # noqa: E402
from src.history_db import HistoryDB, repeat_table  # noqa: E402
from src import ticker_summary  # noqa: E402

st.set_page_config(page_title='Dashboard Screener',
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
c1, c2 = st.columns([3, 2])
c1.markdown(f"**Run date:** `{run.name}`  |  **Tickers:** {len(full):,}  |  "
            f"screening only, not backtesting")
if c2.button('Re-run screeners', on_click=rerun_screeners):
    pass

# Tab bar = a horizontal radio, not st.tabs: st.tabs keeps the selected tab
# only in the browser, so a rerun that reshapes the page (e.g. the first
# Combine-screens pick) snapped back to the first tab. The radio's value is
# server-side session state, and only the active section is built per rerun.
TABS = {
    'leaders': '🏆 Leaders’ Lists',
    'all': '🔎 Screener',
    'volume': '🔊 Volume Records',
    'movers': '📈 Top Movers',
    'focus': '🎯 Focus List',
    'confluence': '🎖️ Confluence',
    'patterns': '🌊 Patterns',
    'workflows': '🧭 Workflows',
    'detail': '📋 Ticker detail',
    'leadermap': '📍 Where is each leader?',
    'growth': '🌱 Growth Cycle',
    'sr': '⚖️ Sustainability Ratio',
}
# Only the active section's widgets are drawn, and Streamlit drops the state
# of any keyed widget not drawn in a run — so switching tabs would wipe e.g.
# the Screener filters. Re-assigning each value to itself turns it into
# plain session state, which survives. Buttons, uploads, downloads and table
# selections can't be written via session_state, so they are skipped.
_NO_PERSIST = {'results_sel', 'cf_sel', 'comb_clear', 'comb2_clear',
               'comb3_clear', 'comb4_clear', 'comb_add_level',
               'comb_drop_level',
               'lists_uploader',
               'pt_run',
               'wf_edit_btn', 'wf_new_btn', 'wf_del_btn', 'del_screener',
               'cf_save_sel', 'cf_save_top', 'cfh_save_list', 'pt_save_list',
               'vr_save_list', 'vr_reset', 'vrd_peb', 'vrd_reset_btn',
               'mv_save_list', 'lm_run', 'lm_upload',
               'save_upload', 'del_list', 'wf_add_stage', 'wf_save_btn',
               'wf_discard', 'wf_focus_save', 'wf_focus_csv', 'wf_focus_tv',
               'sr_save_btn', 'sr_add', 'sr_del_btn'}
_NO_PERSIST_PREFIX = ('FormSubmitter:', 'wf_up_', 'wf_dn_', 'wf_edit_',
                      'wf_dupe_', 'wf_dropstg_', 'lead_tv_', 'wf_stage_csv_',
                      'wf_stage_tv_', 'lm_setups_', 'sr_up', 'sr_dn',
                      'sr_rm')
for _k in list(st.session_state.keys()):
    if _k not in _NO_PERSIST and not _k.startswith(_NO_PERSIST_PREFIX):
        st.session_state[_k] = st.session_state[_k]

# Navigation rows: a group, then its tabs; under Screen, "📌 Presets" (last)
# opens a third row (Leaders' Lists, Focus List). `active_tab` (plain session state)
# stays the single source of truth — tests and the reruns above key on it;
# the rows follow it, and each group / sub-row reopens its last-used tab.
TAB_GROUPS = {
    '🔎 Screen': ['all', 'confluence', 'workflows', 'presets'],
    '📡 Signals': ['volume', 'patterns'],
    '🌍 Market Movers': ['movers'],
    '🩺 Market Health': ['growth', 'sr'],
    '📋 Ticker': ['detail', 'leadermap'],
}
TAB_SUBROWS = {'presets': ['leaders', 'focus']}
NAV_LABELS = {**TABS, 'presets': '📌 Presets'}
_NAV_PATH = {}                      # tab -> (group, row-2 item)
for _g, _items in TAB_GROUPS.items():
    for _it in _items:
        for _t in TAB_SUBROWS.get(_it, [_it]):
            _NAV_PATH[_t] = (_g, _it)
assert set(_NAV_PATH) == set(TABS), 'every tab needs a place in the rows'


def _first_tab(item: str) -> str:
    """Last-used (else first) tab behind a group or a row-2 item."""
    if item in TAB_GROUPS:
        return st.session_state.get(f'_last_tab_{item}') or \
            _first_tab(TAB_GROUPS[item][0])
    if item in TAB_SUBROWS:
        return st.session_state.get(f'_last_tab_{item}', TAB_SUBROWS[item][0])
    return item


def _on_nav(key: str):
    st.session_state['active_tab'] = _first_tab(st.session_state[key])


if st.session_state.get('active_tab') not in _NAV_PATH:
    st.session_state['active_tab'] = 'leaders'     # landing tab, as before
ACTIVE_TAB = st.session_state['active_tab']
_group, _row2 = _NAV_PATH[ACTIVE_TAB]
st.session_state['tab_group'] = _group
st.session_state['tab_row2'] = _row2
# group row reads as the main navigation: larger, semi-bold labels
st.markdown('<style>.st-key-tab_group [data-testid="stMarkdownContainer"] p '
            '{font-size: 1.3rem; font-weight: 600;}</style>',
            unsafe_allow_html=True)
st.radio('Group', list(TAB_GROUPS), horizontal=True, key='tab_group',
         on_change=_on_nav, args=('tab_group',), label_visibility='collapsed')
st.radio('Section', TAB_GROUPS[_group], format_func=NAV_LABELS.get,
         horizontal=True, key='tab_row2', on_change=_on_nav,
         args=('tab_row2',), label_visibility='collapsed')
if _row2 in TAB_SUBROWS:
    st.session_state['tab_row3'] = ACTIVE_TAB
    st.radio('Preset', TAB_SUBROWS[_row2], format_func=TABS.get,
             horizontal=True, key='tab_row3', on_change=_on_nav,
             args=('tab_row3',), label_visibility='collapsed')
    st.session_state[f'_last_tab_{_row2}'] = ACTIVE_TAB
st.session_state[f'_last_tab_{_group}'] = ACTIVE_TAB
st.divider()

# --------------------------------------------- Screener (sketch layout) --
import dashboard_filters as dfil  # noqa: E402


# ---- sparkline closes (lazy per-ticker read) — shared by Screener,
# Confluence and Workflows, so it lives at module level
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


def _universe_line() -> str:
    """'How … is built' opener shared by every tab: what the screening
    universe is, with counts as recorded by THIS run (report.write_dashboard's
    "Universe: N tickers | loaded: … | missing: … | short history: …")."""
    _md = run / 'dashboard.md'
    m = re.search(r'Universe: (\d+) tickers \| loaded: (\d+) \| '
                  r'missing: (\d+) \| short history: (\d+)',
                  _md.read_text() if _md.exists() else '')
    n_uni, n_load, n_miss, n_short = (m.groups() if m
                                      else ('?', str(len(full)), '?', '?'))
    return (f'<b>Universe</b> — <code>{config.UNIVERSE_CSV.name}</code> used '
            f'as-is, <b>no pre-filter</b> (no market-cap, price, volume or '
            f'exchange cut): {n_uni} tickers. {n_miss} have no daily price '
            f'file and are skipped → {n_load} screened. {n_short} of those '
            f'have &lt; {config.MIN_BARS_TEMPLATE} daily bars: too short for '
            f'Minervini / SCTR, but they can still pass CANSLIM '
            f'(fundamentals only)')


def _hve_line() -> str:
    """Info-box line: which HVE baseline the volume-record columns use."""
    s = volume_records.read_status()
    if not s:
        return ('<b>HVE volume records</b> — no ledger yet: copy metaVolume\'s '
                '<code>HVE_historical_daily.csv</code> + '
                '<code>baseline_metadata.json</code> into '
                '<code>volume_records/baseline/</code> and re-run the screeners')
    age = (pd.Timestamp(s['last_bar']) - pd.Timestamp(s['baseline_cutoff'])).days
    sc = s['status_counts']
    return (f'<b>HVE volume records</b> — all-time records 2020-01-02 → '
            f'{s["baseline_cutoff"]} come from the metaVolume baseline '
            f'({s["baseline_tickers"]} tickers, imported by hand); the '
            f'{s["bars_after_cutoff"]} bars after it (to {s["last_bar"]}) are '
            f'checked on every run: {s["events"]} new records. Baseline is '
            f'{age} days old{" — consider a metaVolume rebuild" if age > 365 else ""}. '
            f'No HVE value for: {sc.get("no_baseline", 0)} not in the baseline, '
            f'{sc.get("short_history", 0)} with &lt; {config.HVE_MIN_BARS} bars, '
            f'{sc.get("baseline_mismatch", 0)} whose volume history changed '
            f'since the baseline (split re-adjustment)')


def _how_built(title: str, lines: list):
    """Collapsed info box: one gray italic line per rule (HTML, since
    Streamlit doesn't parse markdown inside a raw <div>)."""
    with st.expander(title):
        for line in lines:
            st.markdown(f'<div style="color:gray;font-style:italic;'
                        f'margin-bottom:0.4rem">{line}</div>',
                        unsafe_allow_html=True)


def _tv_txt(frame, section: str) -> bytes:
    """`frame` (indexed by ticker) -> TradingView “Upload list…” .txt bytes:
    EXCHANGE:SYMBOL, comma-separated, leading ###section divider. The exchange
    prefix comes from the frame's own `exchange` column when present, else from
    the master `full` table (unknown -> bare symbol). Split by hand above the
    TradingView 1000-symbol import cap."""
    ex = None
    if 'exchange' not in getattr(frame, 'columns', []):
        ex = full['exchange'].reindex(frame.index).to_dict()
    return dfil.tradingview_watchlist(frame, exchanges=ex, section=section).encode()


_TV_HELP = ('EXCHANGE:SYMBOL, comma-separated — paste-ready for TradingView '
            '“Upload list…”. Split by hand if over 1000 names.')


def _init_filter_state(p: str = ''):
    for k in dfil.SPEC_BY_KEY:
        st.session_state.setdefault(f'{p}sel_{k}', 'All')
    for k, (label, col, fam) in dfil.SPEC_BY_KEY.items():
        lo, hi, _step = dfil.CUSTOM_RANGE[fam]
        st.session_state.setdefault(f'{p}custlo_{k}', lo)
        st.session_state.setdefault(f'{p}custhi_{k}', hi)
    for k, default in dfil.ADVANCED_DEFAULTS.items():
        st.session_state.setdefault(f'{p}{k}', default)
    if p:
        return
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


# timing-signal filter key -> its detail columns in the Screener results
# (src/timing/daily.py; ages in trading bars, 0 = latest bar)
TIMING_DETAIL = {
    'blue_since': ['blue_dot_bars_since'],
    'black_since': ['black_dot_bars_since'],
    'pvb_buy_since': ['pvb_signal', 'pvb_signal_date', 'pvb_bars_since',
                      'pvb_performance_since_signal'],
    'atr1_long_since': ['atr1_trend', 'atr1_signal_type', 'atr1_signal_date',
                        'atr1_bars_since', 'atr1_performance_since_signal',
                        'atr1_stop_level'],
}

# Combine screens levels: session-state key prefix per level (level 1 =
# 'comb'); levels 1-3 always shown, level 4 via '＋ Add level 4'
COMB_PREFIXES = ('comb', 'comb2', 'comb3', 'comb4')
COMB_MIN_LEVELS = 3


def _reset_filters():
    """Runs as an on_click callback — i.e. BEFORE the widgets are
    instantiated on the next run, which is the only safe time to write
    widget-backed session_state keys."""
    _reset_panel()
    for k in [k for k in st.session_state
              if str(k).startswith(tuple(f'{p}_{x}_' for p in COMB_PREFIXES
                                         for x in ('inc', 'exc')))]:
        st.session_state[k] = []
    for k, default in {'search': '', 'my_list_sel': '— None Selected —',
                       'apply_upload': False,
                       'preset_sel': '— None Selected —',
                       'my_screener_sel': '— None Selected —',
                       '_applied_preset': '— None Selected —',
                       '_applied_screener': '— None Selected —',
                       'save_as_name': '', 'save_list_name': '',
                       **{f'{p}_mode': 'All (AND)' for p in COMB_PREFIXES},
                       'comb_levels': 'Funnel',
                       'comb_n_levels': COMB_MIN_LEVELS,
                       '_flash': ''}.items():
        st.session_state[k] = default


# ---- Screener filter panel, reusable per tab via a key prefix `p` ----
def _thresh_widget(key: str, p: str = ''):
    label, _col, fam = dfil.SPEC_BY_KEY[key]
    options = [lbl for lbl, _rng in dfil.THRESHOLD_FAMILIES[fam]] + ['Custom…']
    val = st.selectbox(label, options, key=f'{p}sel_{key}')
    if val == 'Custom…':
        lo0, hi0, step0 = dfil.CUSTOM_RANGE[fam]
        st.slider(f'{label} range', lo0, hi0,
                  (st.session_state[f'{p}custlo_{key}'],
                   st.session_state[f'{p}custhi_{key}']),
                  step=step0, key=f'{p}custslider_{key}')


def _filter_grid(p: str = ''):
    """The Screener's threshold grid (rows 1-4). `p` prefixes every
    widget key, so another tab gets the same panel with its own state."""
    r1c1, r1c2, r1c3, r1c4, r1c5 = st.columns(5)
    with r1c1:
        _thresh_widget('mktcap', p)
    with r1c2:
        st.multiselect('Sector', sorted(full['sector'].dropna().unique()),
                       key=f'{p}sel_sector')
    with r1c3:
        st.multiselect('Industry Group', sorted(full['industry'].dropna().unique()),
                       key=f'{p}sel_industry')
    with r1c4:
        _thresh_widget('price', p)
    with r1c5:
        _thresh_widget('vs10', p)

    r2c1, r2c2, r2c3, r2c4, r2c5 = st.columns(5)
    for c, k in zip((r2c1, r2c2, r2c3, r2c4, r2c5),
                    ('vs21', 'vs50', 'vs200', 'within_high', 'gain5')):
        with c:
            _thresh_widget(k, p)

    r3c1, r3c2, r3c3, r3c4, r3c5 = st.columns(5)
    for c, k in zip((r3c1, r3c2, r3c3, r3c4, r3c5),
                    ('gain1m', 'gain3m', 'gain6m', 'adr', 'avgvol')):
        with c:
            _thresh_widget(k, p)

    r4c1, r4c2, r4c3 = st.columns([1, 1, 3])
    with r4c1:
        _thresh_widget('adv', p)
    with r4c2:
        _thresh_widget('rsi14', p)


def _advanced_filters(p: str = ''):
    """The Screener's 'Advanced filters' expander, keys prefixed by `p`."""
    with st.expander('Advanced filters (stage, RS, RTI, leaders lists, '
                     'exchange, index…)'):
        a1, a2, a3, a4 = st.columns(4)
        a1.multiselect('Leaders lists',
                       ['minervini', 'canslim', 'scooter', 'cantata'],
                       key=f'{p}adv_leaders')
        a2.radio('Combine lists', ['Any (union)', 'All (intersection)'],
                 key=f'{p}adv_leaders_mode', disabled=not st.session_state[f'{p}adv_leaders'])
        a3.multiselect('Stage', ['1', '2A', '2B', '2C', '3', '4'], key=f'{p}adv_stages',
                       help='empty = all stages')
        a4.multiselect('RTI zone', ['1', '2', '3'], key=f'{p}adv_rti_zone',
                       help='empty = all zones')
        a5, a6, a7, a8 = st.columns(4)
        a5.slider('max ext (ATR, 21EMA & 40SMA)', -5.0, 10.0, key=f'{p}adv_max_ext', step=0.5,
                  help='10.0 = off')
        a6.slider('RS % ≥', 0.0, 100.0, key=f'{p}adv_min_rs', step=1.0)
        a7.slider('Minervini count ≥', 0, 8, key=f'{p}adv_min_count')
        a8.multiselect('Exchange', sorted(full['exchange'].dropna().unique()),
                       key=f'{p}adv_exchange')
        a9x, a9y, _a9z, _a9w = st.columns(4)
        a9x.slider('max ext vs 21 EMA (ATR)', -5.0, 10.0, key=f'{p}adv_max_ext21',
                   step=0.5, help='Ollie: 3. 10.0 = off')
        a9y.slider('max ext vs 50 SMA (ATR)', -5.0, 10.0, key=f'{p}adv_max_ext50',
                   step=0.5, help='Ollie: 5. 10.0 = off')
        a9, a10, a11, a12 = st.columns(4)
        a9.multiselect('Index membership', index_choices(), key=f'{p}adv_index')
        a10.checkbox('RTI low-vol dots', key=f'{p}adv_rti_dots')
        a11.checkbox('RTI range expansion', key=f'{p}adv_rti_exp')
        a12.checkbox('Stockbee 9M mover', key=f'{p}adv_9m_movers')
        a13, a14, a15, a16 = st.columns(4)
        a13.checkbox('Stockbee 20% weekly mover', key=f'{p}adv_weekly_movers')
        a14.checkbox('Stockbee 4% daily gainer', key=f'{p}adv_daily_gainers')
        a15.checkbox('Golden Launch Pad', key=f'{p}adv_gold_launch_pad')
        a16.multiselect('GMMA state',
                        ['bullish', 'bearish', 'compression_breakout',
                         'expanding', 'bullish_crossover', 'bearish_crossover',
                         'transitioning'], key=f'{p}adv_gmma_state')
        a17, a18, a19, a20 = st.columns(4)
        a17.checkbox('Qullamaggie suite', key=f'{p}adv_qullamaggie')
        a18.checkbox('Volume anomaly (3-sigma)', key=f'{p}adv_volume_anomaly')
        a19.checkbox('ADL accumulation (composite >= 70)', key=f'{p}adv_adl_accumulation')
        a20, a21, a22, a23 = st.columns(4)
        a20.checkbox('52w high breakout', key=f'{p}adv_52w_high_breakout')
        a21.checkbox('52w low breakdown', key=f'{p}adv_52w_low_breakdown')
        a22.checkbox('EMA20 pullback test', key=f'{p}adv_ema20_pullback')
        a23.checkbox('Downtrend reversal', key=f'{p}adv_downtrend_reversal')
        a24, a25, a26, a27 = st.columns(4)
        a24.checkbox('CANTATA CE leader', key=f'{p}adv_cantata',
                     help=f'in_cantata: CE >= {config.CANTATA_MIN_CE} of 18')
        a25.slider('CANTATA CE ≥', 0.0, 18.0, key=f'{p}adv_ce_min', step=0.5,
                   help='0 = off; CET(0-7) + CEF(0-11)')
        a26.checkbox('21dma-structure pullback', key=f'{p}adv_21dma_pullback',
                     help=f'trend up + close within ±{config.MA21S_PULLBACK_PCT:g}% '
                          'of the EMA21 high/low band (PrimeTrading script)')
        a27.multiselect('21dma-structure zone',
                        ['extended', 'above', 'inside', 'undercut', 'below'],
                        key=f'{p}adv_ma21s_zone',
                        help='close vs the band: above/undercut = within '
                             f'{config.MA21S_PULLBACK_PCT:g}% of it; empty = all')
        a28, a29, _a30, _a31 = st.columns(4)
        a28.multiselect('21dma-structure trend', ['up', 'down'],
                        key=f'{p}adv_ma21s_trend', help='empty = all')
        with a29:
            _thresh_widget('ma21s_dist', p)
        st.markdown('**Volume & trend filters**')
        v1, v2, v3, v4 = st.columns(4)
        with v1:
            _thresh_widget('vroc', p)
        with v2:
            _thresh_widget('adtv', p)
        with v3:
            _thresh_widget('mfi', p)
        with v4:
            _thresh_widget('adx', p)
        v5, v6, _v7, _v8 = st.columns(4)
        with v5:
            _thresh_widget('hve_since', p)
        with v6:
            _thresh_widget('hv1y_since', p)
        st.markdown('**Timing signals** — trading bars since the signal '
                    '(0 = latest bar)')
        t1, t2, t3, t4 = st.columns(4)
        for _col, _k in zip((t1, t2, t3, t4), ('blue_since', 'black_since',
                                               'pvb_buy_since',
                                               'atr1_long_since')):
            with _col:
                _thresh_widget(_k, p)


def _panel_selections(p: str = '') -> dict:
    selections = {}
    for key in dfil.SPEC_BY_KEY:
        val = st.session_state[f'{p}sel_{key}']
        if val == 'Custom…':
            lo, hi = st.session_state.get(f'{p}custslider_{key}',
                                          (st.session_state[f'{p}custlo_{key}'],
                                           st.session_state[f'{p}custhi_{key}']))
            selections[key] = ('custom', lo, hi)
        else:
            selections[key] = val
    return selections


def _panel_mask(df: pd.DataFrame, p: str = '') -> pd.Series:
    """Threshold grid + the whole Advanced panel over `df` —
    build_advanced_mask is the single source of truth, shared with the
    Workflows tab engine (src/workflow.py); feedback: workflows_tab.md §4"""
    mask = dfil.build_mask(df, _panel_selections(p))
    mask &= dfil.build_advanced_mask(
        df, {k: st.session_state[f'{p}{k}'] for k in dfil.ADVANCED_DEFAULTS},
        IDX_MAP)
    return mask


def _reset_panel(p: str = ''):
    for k in dfil.SPEC_BY_KEY:
        st.session_state[f'{p}sel_{k}'] = 'All'
    for k, default in dfil.ADVANCED_DEFAULTS.items():
        st.session_state[f'{p}{k}'] = default


_init_filter_state()

if ACTIVE_TAB == 'all':
    _how_built('ℹ️ How the Screener is built', [
        _universe_line(),
        'Every screen, preset and filter below narrows this universe. '
        'Combine levels 2–4 are optional: in <b>Funnel</b> mode each level '
        'only screens the survivors of the levels above it (level 1 AND 2 '
        'AND 3 — e.g. leaders with Any (OR), then Tight with All (AND), then '
        'Blue OR Black Dot); in <b>Merge</b> mode every level screens the whole '
        'universe and the results are joined (level 1 OR 2 OR 3). Empty '
        'levels are skipped. The Filters panel is ANDed on top of the result',
        _hve_line(),
    ])
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

    # ------------------ combine screens (mask-level AND / OR / NOT) -------
    st.subheader('Combine screens')
    _cats = dfil.screen_categories()
    st.session_state.setdefault('comb_levels', 'Funnel')
    st.session_state.setdefault('comb_n_levels', COMB_MIN_LEVELS)
    comb_levels = st.radio(
        'Connect the levels', ['Funnel', 'Merge'], key='comb_levels',
        horizontal=True,
        help='Funnel: each level only screens the tickers that survived the '
             'levels above it (level 1 AND level 2 AND …). Merge: every level '
             'screens the whole universe and the results are joined '
             '(level 1 OR level 2 OR …). Empty levels are skipped.')

    def _combine_level(p: str, n_pick: int, n_comb: int, level_label: str,
                       within: pd.Series | None = None):
        """One Pick + Combine block; `p` is the session-state key prefix
        ('comb' = level 1, 'comb2' … 'comb4'). `within` (the levels above,
        Funnel mode) restricts the mask AND every per-screen count to the
        tickers that survived them. Chip picker like the
        StockCharts Screener: one '<p>_inc_<category>' / '<p>_exc_<category>'
        pills widget per category; the Include / Exclude sets are the union
        over categories (hidden categories' picks survive via the tab-bar
        state carry-forward at the top of the script)."""
        inc_p, exc_p = f'{p}_inc_', f'{p}_exc_'
        for _k in [k for k in st.session_state
                   if str(k).startswith((inc_p, exc_p))]:
            _ok = _cats.get(_k[len(inc_p):], [])      # drop deleted screeners
            st.session_state[_k] = [x for x in (st.session_state[_k] or [])
                                    if x in _ok]
        if st.session_state.get(f'{p}_cat') not in _cats:
            st.session_state[f'{p}_cat'] = next(iter(_cats))
        st.session_state.setdefault(f'{p}_pick_as', 'Include')
        include = [x for c in _cats
                   for x in st.session_state.get(inc_p + c) or []]
        exclude = [x for c in _cats
                   for x in st.session_state.get(exc_p + c) or []]

        st.markdown(f'**{n_pick}&nbsp;&nbsp;Pick screens{level_label}**')
        with st.container(border=True):
            pc1, pc2 = st.columns([1, 2])
            with pc1:
                cat = st.pills('Category', list(_cats), key=f'{p}_cat',
                               selection_mode='single') or next(iter(_cats))
                pick_as = st.segmented_control(
                    'Clicking a screen adds it to', ['Include', 'Exclude (NOT)'],
                    key=f'{p}_pick_as') or 'Include'
            with pc2:
                _pref = inc_p if pick_as == 'Include' else exc_p
                st.pills(f'Screens in {cat}'
                         + ('' if pick_as == 'Include' else ' — excluding'),
                         _cats[cat], selection_mode='multi',
                         key=_pref + cat,
                         help="Ioa's presets and your saved screeners ('My: …'), "
                              'each evaluated on its own. Click again to remove.')

        def _clear():
            for _k in [k for k in st.session_state
                       if str(k).startswith((inc_p, exc_p))]:
                st.session_state[_k] = []

        mode = st.session_state.get(f'{p}_mode', 'All (AND)')
        m, hits = dfil.combine_screens(
            full, include, exclude,
            'any' if mode.startswith('Any') else 'all', IDX_MAP)
        # pin both to full.index as plain bools, so the funnel AND and the
        # Merge OR below never align two differently ordered indexes
        m = m.reindex(full.index, fill_value=False).astype(bool)
        hits = hits.reindex(full.index, fill_value=False).astype(bool)
        if within is not None:
            w = within.reindex(full.index, fill_value=False).to_numpy(dtype=bool)
            m = m & w
            hits = pd.DataFrame(hits.to_numpy(dtype=bool) & w[:, None],
                                index=hits.index, columns=hits.columns)
        st.markdown(f'**{n_comb}&nbsp;&nbsp;Combine{level_label}**')
        with st.container(border=True):
            if not (include or exclude):
                st.caption('No screens picked yet — pick one or more above. '
                           'The Filters panel below is ANDed on top of the result.')
            else:
                cc1, cc2 = st.columns([4, 1])
                with cc2:
                    st.radio('Match', ['All (AND)', 'Any (OR)'], key=f'{p}_mode',
                             disabled=len(include) < 2)
                with cc1:
                    _join = ' · AND · ' if mode.startswith('All') else ' · OR · '
                    _expr = _join.join(
                        f'`{c}` ({int(hits[c].sum())})' for c in hits)
                    if exclude:
                        _expr += ((' · ' if _expr else '')
                                  + ' · '.join(f'NOT `{c}`' for c in exclude))
                    st.markdown(_expr)
                    st.markdown(f'→ **{int(m.sum())}** tickers')
                    st.button('Clear all screens', key=f'{p}_clear',
                              on_click=_clear)
        return m, hits, bool(include or exclude)

    # Funnel: each level screens only the survivors of the levels above
    # (e.g. leaders, then Tight within them, then a dot within those).
    # Merge: every level screens the whole universe; results are ORed.
    _funnel = comb_levels == 'Funnel'
    n_levels = st.session_state['comb_n_levels']
    comb_mask = None                       # None = no level picked yet
    comb_hits = pd.DataFrame(index=full.index)
    _on = []
    for _i, _p in enumerate(COMB_PREFIXES[:n_levels], 1):
        _within = comb_mask if _funnel else None
        if _i == 1:
            _lbl = ''
        elif _within is not None:
            _lbl = (f' — level {_i}, within the {int(_within.sum())} tickers '
                    'from the levels above')
        else:
            _lbl = f' — level {_i}' + ('' if _funnel else ' (merged)')
        _m, _h, _lvl_on = _combine_level(_p, 2 * _i - 1, 2 * _i, _lbl,
                                         within=_within)
        if not _lvl_on:
            continue
        _on.append(_i)
        # Funnel: _m is already restricted to the levels above
        comb_mask = _m if (comb_mask is None or _funnel) else comb_mask | _m
        # a screen picked in two levels — keep one hits column
        comb_hits = pd.concat(
            [comb_hits, _h.loc[:, ~_h.columns.isin(comb_hits.columns)]], axis=1)
    if comb_mask is None:                  # nothing picked: all-True
        comb_mask = pd.Series(True, index=full.index)
    if len(_on) > 1:
        _op = ' AND ' if _funnel else ' OR '
        st.markdown(f'**{_op.join(f"Combine {i}" for i in _on)}** → '
                    f'**{int(comb_mask.sum())}** tickers '
                    '(before the Filters panel)')

    def _add_level():
        st.session_state['comb_n_levels'] = min(
            len(COMB_PREFIXES), st.session_state['comb_n_levels'] + 1)

    def _drop_level():
        p = COMB_PREFIXES[st.session_state['comb_n_levels'] - 1]
        for k in [k for k in st.session_state
                  if str(k).startswith((f'{p}_inc_', f'{p}_exc_'))]:
            st.session_state[k] = []
        st.session_state['comb_n_levels'] -= 1

    if n_levels < len(COMB_PREFIXES):
        st.button(f'＋ Add level {n_levels + 1}', key='comb_add_level',
                  on_click=_add_level)
    else:
        st.button(f'✕ Remove level {n_levels}', key='comb_drop_level',
                  on_click=_drop_level, help='clears its picks')
    st.divider()

    # --------------------------- filter rows (sketch rows 1-4) ------------
    st.subheader('Filters')

    _filter_grid()

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
    _advanced_filters()

    # ------------------------------- mask ----------------------------------
    mask = _panel_mask(full)
    if active_list:
        _variants = {t.replace('.', '-') for t in active_list}
        mask &= pd.Series(full.index.isin(active_list) | full.index.isin(_variants),
                          index=full.index)
    if upload_syms and st.session_state.get('apply_upload'):
        _variants = {t.replace('.', '-') for t in upload_syms}
        mask &= pd.Series(full.index.isin(upload_syms) | full.index.isin(_variants),
                          index=full.index)
    view_cols = ['close', 'scooter_score', 'rs_pct', 'minervini_count', 'stage',
                 'ext_21ema_atr', 'ext_40sma_atr', 'ext_50sma_atr', 'ext_10wsma_atr',
                 'adr20_pct', 'rti',
                 'rti_zone',
                 'rti_dots', 'rti_expansion', 'rel_volume_today', 'daily_gain_pct',
                 'weekly_gain_pct', 'in_9m_movers', 'in_weekly_movers',
                 'in_daily_gainers', 'glp_spread', 'glp_spread_score',
                 'glp_strong', 'in_gold_launch_pad',
                 'gmma_state', 'gmma_separation_pct', 'gmma_total_spread',
                 'gmma_compression_breakout',
                 'in_volume_anomaly', 'volume_zscore', 'volume_ratio',
                 'in_21dma_pullback', 'ma21s_zone', 'ma21s_dist_pct',
                 'ma21s_trend', 'ma21s_bearish_bar', 'ma21s_high',
                 'ma21s_close', 'ma21s_low',
                 'hve_bars_since', 'hve_date', 'hve_count_50', 'hve_status',
                 'hv1y_bars_since', 'hv1y_date', 'hv1y_vs_prior_pct',
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
    view_cols += [c for cols in TIMING_DETAIL.values() for c in cols]
    # a timing signal in use — a Timing chip in any level (or a saved
    # screener using it), or its filter in the panel — puts its detail
    # columns right after hits / matched_by
    _picked = [x for _p in COMB_PREFIXES[:n_levels] for c in _cats
               for side in ('inc', 'exc')
               for x in st.session_state.get(f'{_p}_{side}_{c}') or []]
    _used = {k for x in _picked
             for k, v in (dfil.screen_spec(x) or {}).get('selections', {}).items()
             if v != 'All'}
    _used |= {k for k in TIMING_DETAIL
              if st.session_state.get(f'sel_{k}', 'All') != 'All'}
    _front = [c for k, cols in TIMING_DETAIL.items() if k in _used
              for c in cols]
    view_cols = _front + [c for c in view_cols if c not in _front]
    view_cols = [c for c in view_cols if c in full.columns]
    mask &= comb_mask
    filtered = full[mask][view_cols]
    if comb_hits.shape[1]:
        # which Include screens each ticker hit — sort by 'hits' in OR mode
        # to rank the names several methods agree on
        _h = comb_hits.loc[filtered.index]
        filtered = filtered.copy()
        filtered.insert(0, 'matched_by', [
            ', '.join(c for c, v in r.items() if v)
            for _t, r in _h.iterrows()])
        filtered.insert(0, 'hits', _h.sum(axis=1).astype(int))
        view_cols = ['hits', 'matched_by'] + view_cols

    # ------------------------- results section (sketch) --------------------
    # what actually screens the results (Combine picks + Filters panel) —
    # not the dropdowns, which stay put after the panel is edited. Shared
    # by the title, the export file names and the List-name default.
    def _picks(p):
        inc = [x for c in _cats for x in st.session_state.get(f'{p}_inc_{c}') or []]
        exc = [x for c in _cats for x in st.session_state.get(f'{p}_exc_{c}') or []]
        mode = st.session_state.get(f'{p}_mode', 'All (AND)')
        return inc, exc, 'any' if mode.startswith('Any') else 'all'

    _cur_s, _cur_a = _current_panel()
    _loaded = [x for x in (preset_sel, dfil.MY_SCREENER_PREFIX + screener_sel)
               if not x.endswith('— None Selected —')]
    _panel = dfil.panel_label(_cur_s, _cur_a, _loaded)
    if (active_list or (upload_syms and st.session_state.get('apply_upload'))) \
            and '+f' not in _panel:
        _panel += '+f'
    active_name = dfil.screen_label([_picks(p) for p in COMB_PREFIXES[:n_levels]],
                                    funnel=_funnel, panel=_panel)
    st.subheader(f'{active_name} – Results')
    sc1, sc2, sc3, sc4 = st.columns([2, 1, 2, 1])
    search = sc1.text_input('Search', key='search', placeholder='Ticker or name…')
    n_results = sc2.selectbox('Number of Results', [30, 50, 100, 500, 'All'],
                              key='result_n')
    if st.session_state.get('order_by') not in view_cols:
        st.session_state.pop('order_by', None)   # e.g. 'hits' after un-combining
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
                       file_name=f'{active_name}_{run.name}.csv')
    d1.download_button('⭳ TradingView .txt (all)',
                       _tv_txt(result, f'{active_name} — {run.name}'),
                       file_name=f'{active_name}_{run.name}.txt',
                       mime='text/plain', help=_TV_HELP)
    if selected_tickers:
        d1.download_button('Download CSV (selected)',
                           result.loc[selected_tickers].round(3).to_csv().encode(),
                           file_name=f'{active_name}_sel_{run.name}.csv')
        d1.download_button('⭳ TradingView .txt (selected)',
                           _tv_txt(result.loc[selected_tickers],
                                   f'{active_name} (selected) — {run.name}'),
                           file_name=f'{active_name}_sel_{run.name}.txt',
                           mime='text/plain', help=_TV_HELP)
    # pre-fill with the screen label; follow it while the user hasn't typed
    if st.session_state.get('save_list_name', '') in (
            '', st.session_state.get('_auto_list_name')):
        st.session_state['save_list_name'] = f'{active_name}_{run.name}'
    st.session_state['_auto_list_name'] = f'{active_name}_{run.name}'
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
# ------------------------------------------------ Volume Records ----------
# Screener-style tab over the volume-record screens: 1 Pick screens (HVE,
# HV1Y — Include / Exclude), 2 Combine (AND / OR), 3 Filters. One level.
# HVE: records up to the baseline cutoff come from the metaVolume baseline
# (imported by hand into volume_records/baseline/), after it from the ledger
# run_screeners.py recomputes every run. HV1Y: rolling 1-year high, computed
# every run (src/focus/volume_records.py).
VR_SCREENS = ['HVE', 'HV1Y']
# on-screen labels of the per-record columns, after the HVE / HV1Y prefix
VR_LABELS = {'date': 'date', 'bars_since': 'days ago', 'records': 'count',
             'vs_prior_pct': 'vol vs prev %', '1st_dch_pct': 'px day1 %',
             '2nd_dch_pct': 'px day2 %', 'since_record_pct': 'px since %',
             'range_since_pct': 'px range %', 'gap_held': 'gap held',
             'earnings': 'on earnings'}
VR_DIRECTIONS = ['Up & held', 'Up & faded', 'Down & bounced',
                 'Down & continued', 'Pending']
_VRD_DEFAULTS = {'vrd_dir': [], 'vrd_er': False, 'vrd_min1st': 0.0,
                 'vrd_gap': False, 'vrd_since': 0.0, 'vrd_range': 0.0,
                 'vrd_days': (0, 250)}


def _vr_direction(d1: pd.Series, d2: pd.Series) -> pd.Series:
    """Record day (1st dch) up/down x next day (2nd dch) held/reversed.
    'Pending' = the record is the latest bar (no next day yet)."""
    up = d1 > 0
    out = np.where(d2.isna(), 'Pending',
                   np.where(up, np.where(d2 >= 0, 'Up & held', 'Up & faded'),
                            np.where(d2 > 0, 'Down & bounced',
                                     'Down & continued')))
    return pd.Series(np.where(d1.isna(), None, out), index=d1.index)


def _vrd_reset():
    for k, v in _VRD_DEFAULTS.items():
        st.session_state[k] = v


def _vrd_post_earnings_base():
    """Preset: gapped up on earnings, kept the gap, now moving sideways
    5-15 sessions later (user's pattern: gap up, then 7-13 days sideways)."""
    _vrd_reset()
    st.session_state.update({
        'vr_inc': ['HV1Y'], 'vr_exc': [], 'vr_n_bars': 16,
        'vrd_dir': ['Up & held', 'Up & faded'], 'vrd_er': True,
        'vrd_min1st': 5.0, 'vrd_gap': True, 'vrd_since': 5.0,
        'vrd_days': (5, 15)})

if ACTIVE_TAB == 'volume':
    _how_built('ℹ️ How Volume Records are built', [
        _universe_line(),
        _hve_line(),
        '<b>HVE</b> (highest volume ever) = a day whose volume beats every '
        'earlier day since 2020-01-02, the start of the price history '
        '(metaVolume’s rule, strictly greater). <b>HV1Y</b> = the highest '
        f'volume of the trailing {config.HV1Y_BARS} bars (~1 year; metaVolume '
        'uses 365 calendar days). Both need ≥ '
        f'{config.HVE_MIN_BARS} bars of history',
        '<b>Last N bars</b> counts trading bars, the latest bar included: '
        'N = 10 is the latest bar and the 9 before it. For HVE a window '
        'reaching back past the baseline cutoff also sees the baseline’s own '
        'records',
        'Column names: <b>HVE …</b> / <b>HV1Y …</b> = which record; '
        '<b>vol</b> = volume, <b>px</b> = price. Only the record day uses '
        'volume — every <b>px</b> column follows the price from then on',
        '<b>vol vs prev %</b> = how far (%) the record day’s volume beat the '
        'record before it (HVE) or the highest of the year before it (HV1Y). '
        '<b>days ago</b> = trading days since the record day. <b>HVE count</b> '
        '= how many all-time records the ticker set inside the window',
        '<b>px day1 %</b> = close on the record day vs the close the day '
        'before. <b>px day2 %</b> = close the day after vs the record day '
        '(empty when the record is the latest bar)',
        '<b>Direction</b> (step 3) judges each row on its HVE when it matched '
        'HVE, else its HV1Y. Up/Down = px day1; held/faded, bounced/'
        'continued = px day2; Pending = record on the latest bar. '
        '<b>px since %</b> = today’s close vs the record-day close. <b>px '
        'range %</b> = (highest high − lowest low since the record day) / '
        'record close — small means a tight sideways base. <b>gap held</b> = '
        'every low after the record day stayed above the close before it. '
        '<b>on earnings</b> = the record day is a report date or the session '
        'after (reports after the close move the price next day), from '
        'qh*_date in financial_data_0_5.csv — empty when the ticker has no '
        'earnings history',
        '<b>▶ Post-earnings base</b>: HV1Y within 16 bars, earnings-driven, '
        'record day ≥ +5%, gap held, 5–15 sessions ago, today within ±5% of '
        'the record close. Every value stays editable afterwards',
        '<b>Filters</b> (step 4) = the Screener tab’s panel (same grid and '
        'Advanced filters, own settings here)',
    ])
    _st = volume_records.read_status()
    if not _st or not _st.get('bar_dates') or 'hv1y_bars_since' not in full:
        st.warning('No HVE ledger / HV1Y columns yet — re-run the screeners.')
        st.stop()

    for _k, _v in {'vr_inc': ['HVE'], 'vr_exc': [], 'vr_pick_as': 'Include',
                   'vr_mode': 'All (AND)', 'vr_excl_funds': True,
                   **_VRD_DEFAULTS}.items():
        st.session_state.setdefault(_k, _v)

    # ---- 1 Pick screens
    st.markdown('**1&nbsp;&nbsp;Pick screens**')
    with st.container(border=True):
        pc1, pc2, pc3 = st.columns([1, 1.3, 1])
        vr_pick_as = pc1.segmented_control(
            'Clicking a screen adds it to', ['Include', 'Exclude (NOT)'],
            key='vr_pick_as') or 'Include'
        pc2.pills('Volume-record screens'
                  + ('' if vr_pick_as == 'Include' else ' — excluding'),
                  VR_SCREENS, selection_mode='multi',
                  key='vr_inc' if vr_pick_as == 'Include' else 'vr_exc',
                  help='Click again to remove.')
        vr_n = pc3.number_input('Within the last N bars', 1,
                                len(_st['bar_dates']), 10, key='vr_n_bars',
                                help='applies to every screen')
    vr_inc = [x for x in st.session_state['vr_inc'] or [] if x in VR_SCREENS]
    vr_exc = [x for x in st.session_state['vr_exc'] or [] if x in VR_SCREENS]

    # per-screen masks over the whole universe
    _ok = full.index[full['hve_status'] == 'ok']
    rec = volume_records.recent_records(vr_n, full.index)
    rec = rec[rec['ticker'].isin(_ok)]
    vr_masks = {
        'HVE': pd.Series(full.index.isin(rec['ticker'].unique()), index=full.index),
        'HV1Y': (full['hv1y_bars_since'] < vr_n).fillna(False).astype(bool),
    }
    vr_mode = st.session_state.get('vr_mode', 'All (AND)')
    if vr_inc:
        _m = [vr_masks[x] for x in vr_inc]
        vr_mask = (pd.concat(_m, axis=1).any(axis=1) if vr_mode.startswith('Any')
                   else pd.concat(_m, axis=1).all(axis=1))
    else:
        vr_mask = pd.Series(False, index=full.index)
    for x in vr_exc:
        vr_mask &= ~vr_masks[x]

    # ---- 2 Combine
    st.markdown('**2&nbsp;&nbsp;Combine**')
    with st.container(border=True):
        if not vr_inc:
            st.caption('No screen included yet — pick HVE and/or HV1Y above '
                       '(Exclude only removes names from an included screen).')
        else:
            cc1, cc2 = st.columns([4, 1])
            cc2.radio('Match', ['All (AND)', 'Any (OR)'], key='vr_mode',
                      disabled=len(vr_inc) < 2)
            _join = ' · AND · ' if vr_mode.startswith('All') else ' · OR · '
            _expr = _join.join(f'`{x}` ({int(vr_masks[x].sum())})'
                               for x in vr_inc)
            if vr_exc:
                _expr += ' · ' + ' · '.join(
                    f'NOT `{x}` ({int(vr_masks[x].sum())})' for x in vr_exc)
            cc1.markdown(_expr)
            cc1.markdown(f'→ **{int(vr_mask.sum())}** tickers '
                         '(before Direction and Filters below)')
            if len(vr_inc) == 2:
                cc1.caption('Every HVE is also an HV1Y (an all-time record '
                            'also beats the past year), so AND gives the HVE '
                            'list and OR the HV1Y list. To see 1-year volume '
                            'highs that are NOT all-time records: Include '
                            'HV1Y + Exclude HVE.')

    # ---- 3 Direction — price behaviour around / since the record day
    st.markdown('**3&nbsp;&nbsp;Direction**')
    with st.container(border=True):
        d1c, d2c = st.columns([3, 1])
        d1c.pills('Record day → next day (empty = all)', VR_DIRECTIONS,
                  selection_mode='multi', key='vrd_dir',
                  help='Up/Down = record-day close vs the day before (px '
                       'day1). Held/faded, bounced/continued = the next '
                       'day (px day2). Pending = the record is the latest bar')
        d2c.button('▶ Post-earnings base', key='vrd_peb',
                   on_click=_vrd_post_earnings_base,
                   help='HV1Y on an earnings day, up ≥ 5%, gap held, now '
                        '5–15 sessions later within ±5% of the record close')
        d2c.button('Reset Direction', key='vrd_reset_btn', on_click=_vrd_reset)
        e1, e2, e3, e4, e5 = st.columns(5)
        e1.checkbox('Earnings-driven only', key='vrd_er',
                    help='record day = an earnings date or the session after '
                         '(qh*_date in financial_data_0_5.csv)')
        e2.number_input('Record-day change ≥ (%)', -100.0, 100.0, step=1.0,
                        key='vrd_min1st', help='px day1 %; 0 = off')
        e3.checkbox('Gap held', key='vrd_gap',
                    help='every low after the record day stayed above the '
                         'close before it')
        e4.number_input('px since within ± (%)', 0.0, 100.0, step=1.0,
                        key='vrd_since', help='today vs the record-day close; '
                                              '0 = off')
        e5.number_input('px range ≤ (%)', 0.0, 500.0, step=1.0,
                        key='vrd_range', help='(highest high − lowest low '
                        'since the record day) / record close; 0 = off')
        _dmax = max(int(vr_n) - 1, 1)
        _dlo, _dhi = st.session_state['vrd_days']
        if _dhi >= st.session_state.get('_vrd_days_max', _dmax):
            _dhi = _dmax              # "up to the window" follows N
        st.session_state['_vrd_days_max'] = _dmax
        st.session_state['vrd_days'] = (min(_dlo, _dmax), min(_dhi, _dmax))
        st.slider('Days since the record day', 0, _dmax, key='vrd_days',
                  help='0 = the latest bar; bounded by "within the last N bars"')

    # ---- 4 Filters — the Screener's panel, own state (keys 'vrf_…')
    _init_filter_state('vrf_')
    st.markdown('**4&nbsp;&nbsp;Filters**')
    with st.container(border=True):
        f1, f2, f3 = st.columns([1, 1, 1])
        vr_min_vs = f1.number_input('vol vs prev ≥ (%)', 0.0, 1000.0, 0.0, 5.0,
                                    key='vr_min_vs_prior',
                                    help='best of the matched screens; 0 = off')
        vr_nofunds = f2.checkbox('Exclude funds (Investment trusts)',
                                 key='vr_excl_funds',
                                 help='closed-end / muni funds: their volume '
                                      'spikes are fund events, not accumulation')
        f3.button('Reset Filters', key='vr_reset', on_click=_reset_panel,
                  args=('vrf_',), help='restores every filter to All / defaults')
        _filter_grid('vrf_')
        _advanced_filters('vrf_')

    vr_mask &= _panel_mask(full, 'vrf_')
    base = full[vr_mask]
    if len(base):
        # per-ticker table: HVE facts within the window + HV1Y facts
        tbl = pd.DataFrame(index=base.index)
        _hits = pd.DataFrame({x: vr_masks[x].loc[base.index] for x in vr_inc})
        tbl['matched_by'] = [', '.join(c for c, v in r.items() if v)
                             for _t, r in _hits.iterrows()]
        _r = rec[rec['ticker'].isin(base.index)]
        tbl['hve_date'] = base['hve_date']
        tbl['hve_bars_since'] = base['hve_bars_since']
        tbl['hve_records'] = (_r.groupby('ticker').size()
                              .reindex(base.index).fillna(0).astype(int))
        tbl['hve_vs_prior_pct'] = np.nan         # newest record in the window
        if len(_r):
            _lt = _r.loc[_r.groupby('ticker')['date'].idxmax()].set_index('ticker')
            tbl['hve_vs_prior_pct'] = ((_lt['volume'].astype(float)
                                        / _lt['prior_max'].astype(float) - 1)
                                       * 100).round(1).reindex(base.index)
        _met = ('1st_dch_pct', '2nd_dch_pct', 'since_record_pct',
                'range_since_pct', 'gap_held', 'earnings')
        for c in ([f'hve_{m}' for m in _met]
                  + ['hv1y_date', 'hv1y_bars_since', 'hv1y_vs_prior_pct']
                  + [f'hv1y_{m}' for m in _met]):
            tbl[c] = base[c] if c in base else np.nan
        # the record a row is judged on: its HVE when it matched HVE,
        # else its HV1Y — drives Direction and the step-3 filters
        _use_hve = (_hits['HVE'] if 'HVE' in _hits
                    else pd.Series(False, index=tbl.index))
        _recv = {m: tbl[f'hve_{m}'].where(_use_hve, tbl[f'hv1y_{m}'])
                 for m in _met + ('bars_since',)}
        tbl.insert(0, 'direction', _vr_direction(_recv['1st_dch_pct'],
                                                 _recv['2nd_dch_pct']))
        tbl.insert(1, 'earnings', _recv['earnings'])
        ctx_cols = ['close', 'gain_5d', 'gain_1m', 'rel_volume_today', 'stage',
                    'rs_pct', 'ext_21ema_atr', 'adr20_pct', 'adv50_dollar',
                    'market_cap', 'sector', 'industry', 'exchange']
        tbl = tbl.join(base[[c for c in ctx_cols if c in base.columns]])

        # filters
        keep = pd.Series(True, index=tbl.index)
        _vs = pd.concat([tbl['hve_vs_prior_pct'].where(_hits['HVE'])
                         if 'HVE' in _hits else None,
                         tbl['hv1y_vs_prior_pct'].where(_hits['HV1Y'])
                         if 'HV1Y' in _hits else None], axis=1).max(axis=1)
        if vr_min_vs > 0:
            keep &= _vs >= vr_min_vs
        if vr_nofunds:
            keep &= tbl['industry'] != 'Investment trusts'
        ss = st.session_state
        if ss['vrd_dir']:
            keep &= tbl['direction'].isin(ss['vrd_dir'])
        if ss['vrd_er']:
            keep &= tbl['earnings'].astype('boolean').fillna(False)
        if ss['vrd_min1st']:
            keep &= _recv['1st_dch_pct'] >= ss['vrd_min1st']
        if ss['vrd_gap']:
            keep &= _recv['gap_held'].astype('boolean').fillna(False)
        if ss['vrd_since']:
            keep &= _recv['since_record_pct'].abs() <= ss['vrd_since']
        if ss['vrd_range']:
            keep &= _recv['range_since_pct'] <= ss['vrd_range']
        _bs = pd.to_numeric(_recv['bars_since'], errors='coerce')
        keep &= _bs.between(*ss['vrd_days'])
        _recent = pd.concat([tbl['hve_bars_since'].where(_hits['HVE'])
                             if 'HVE' in _hits else None,
                             tbl['hv1y_bars_since'].where(_hits['HV1Y'])
                             if 'HV1Y' in _hits else None], axis=1).min(axis=1)
        tbl = (tbl.assign(_recent=_recent, _vs=_vs)[keep]
               .sort_values(['_recent', '_vs'], ascending=[True, False])
               .drop(columns=['_recent', '_vs']))
        # only the included screens' columns (hve_* / hv1y_*); matched_by
        # says nothing when a single screen is included
        _hide = [c for x in VR_SCREENS if x not in vr_inc
                 for c in tbl.columns if c.startswith(f'{x.lower()}_')]
        if len(vr_inc) < 2:
            _hide.append('matched_by')
        tbl = tbl.drop(columns=_hide)
    else:
        tbl = pd.DataFrame()

    _span = (f'{_st["bar_dates"][-min(vr_n, len(_st["bar_dates"]))]} → '
             f'{_st["bar_dates"][-1]}')
    st.caption(f'{len(tbl):,} tickers after filters — last {vr_n} bars ({_span})')
    if len(tbl):
        show = tbl.copy()
        show.index.name = 'ticker'
        if len(show) <= 200:
            show.insert(1, 'spark',
                        [_spark_closes(t, run.name) for t in show.index])
        # display labels only (CSV keeps the plain names): record columns
        # read "<HVE|HV1Y> <vol|px> …", other percent columns get a % sign
        _pct_cfg = {c: st.column_config.NumberColumn(
                        c[:-4] + ' %' if c.endswith('_pct') else c + ' %')
                    for c in show.columns
                    if (c.endswith('_pct') and c != 'rs_pct')   # rs = percentile
                    or c in ('gain_5d', 'gain_1m')}
        for _x in VR_SCREENS:
            _pre = _x.lower()
            for _c, _lbl in VR_LABELS.items():
                if f'{_pre}_{_c}' in show.columns:
                    _pct_cfg[f'{_pre}_{_c}'] = (
                        st.column_config.Column(f'{_x} {_lbl}')
                        if _c in ('date', 'gap_held', 'earnings')
                        else st.column_config.NumberColumn(f'{_x} {_lbl}'))
        st.dataframe(show, use_container_width=True,
                     height=min(120 + 35 * len(show), 700),
                     column_config={'spark': st.column_config.LineChartColumn(
                         '120d', width=170), **_pct_cfg})
        _tag = '_'.join(vr_inc) + ''.join(f'_not{x}' for x in vr_exc)
        d1, d2, _d3 = st.columns([1, 1, 3])
        d1.download_button('Download CSV', tbl.to_csv().encode(),
                           file_name=f'volrec_{_tag}_last{vr_n}_{run.name}.csv')
        d1.download_button('⭳ TradingView .txt',
                           _tv_txt(tbl, f'{" ".join(vr_inc)} last {vr_n} bars'),
                           file_name=f'volrec_{_tag}_last{vr_n}_{run.name}.txt',
                           mime='text/plain', help=_TV_HELP)
        ln = d2.text_input('List name', key='vr_list_name',
                           placeholder='list name…')
        if d2.button('Save as list', key='vr_save_list',
                     disabled=not ln.strip()):
            dfil.save_list(ln.strip(), tbl.index)
            st.success(f'saved {len(tbl)} tickers to '
                       f'my_lists/{ln.strip()}.csv')

# ----------------------------------------------------------- Top Movers ---
# Ranked gainers/losers per index + repeat hits over the last N sessions,
# read from results/history.db (docs/top_movers_plan.md). Written by
# run_screeners.py (movers for every session, screen hits per run).
MV_INDEX_NAMES = {'SP500': 'S&P 500', 'NASDAQ100': 'NASDAQ 100'}


@st.cache_data(ttl=600)
def _mv(method: str, *args):
    """Cached HistoryDB read — one entry per (method, args)."""
    return getattr(HistoryDB(), method)(*args)


def _mv_context(tbl: pd.DataFrame) -> pd.DataFrame:
    """symbol-indexed table + name/sector/industry from the screener run."""
    ctx = full.reindex(tbl['symbol'])[['description', 'sector', 'industry']]
    out = tbl.set_index('symbol').join(ctx)
    out.index.name = 'ticker'
    return out


if ACTIVE_TAB == 'movers':
    _how_built('ℹ️ How Top Movers are built', [
        '<b>% change</b> = close vs the previous close, from the downloadData_v1 '
        'daily bars, for every member of the index (member lists: '
        '<code>downloadData_v1/data/tickers/sp500_tickers.csv</code> and '
        '<code>nasdaq100_tickers.csv</code>). Rank 1 = biggest gainer (top) or '
        'biggest loser (bottom)',
        f'A session is skipped when fewer than {config.MOVERS_MIN_COVERAGE:.0%} '
        'of the members have a bar. Past sessions use <i>today’s</i> member '
        'lists (survivorship bias)',
        '<b>Repeat hits</b>: over the last N sessions, how often a ticker made '
        'the top/bottom N. <b>Streak</b> = consecutive sessions up to the '
        'newest one. Screener history lives in Confluence → Last N days',
    ])
    if not config.HISTORY_DB.exists() or not _mv('mover_dates', 'SP500'):
        st.warning('No movers yet — run `python3 run_screeners.py '
                   '--backfill-movers` once.')
        st.stop()

    mv_view = st.radio('View', ['Movers', 'Repeat hits', 'Ticker history'],
                       key='mv_view', horizontal=True)

    if mv_view == 'Movers':
        c1, c2, c3 = st.columns([1, 1, 1])
        mv_ix = c1.selectbox('Index', list(MV_INDEX_NAMES),
                             format_func=MV_INDEX_NAMES.get, key='mv_ix')
        mv_date = c2.selectbox('Session', _mv('mover_dates', mv_ix),
                               key='mv_date')
        mv_n = c3.number_input('Top / bottom N', 1, 100,
                               config.MOVERS_TOP_N, key='mv_n')
        g1, g2 = st.columns(2)
        for col, side, title in ((g1, 'top', '▲ Gainers'),
                                 (g2, 'bottom', '▼ Losers')):
            tbl = _mv_context(_mv('movers', mv_date, mv_ix, int(mv_n), side))
            col.markdown(f'**{title}** — {MV_INDEX_NAMES[mv_ix]}, {mv_date}')
            col.dataframe(tbl, use_container_width=True,
                          height=min(80 + 35 * len(tbl), 700),
                          column_config={'change_pct': st.column_config.NumberColumn(
                              '% chg', format='%+.2f')})

    elif mv_view == 'Repeat hits':
        sources = {f'{side} N · {name}': (ix, side)
                   for ix, name in MV_INDEX_NAMES.items()
                   for side in ('top', 'bottom')}
        c1, c2, c3 = st.columns([2, 1, 1])
        mv_src = c1.selectbox('Source', list(sources), key='mv_src',
                              help='top or bottom N of an index')
        key, side = sources[mv_src]
        mv_days = c2.number_input('Last N sessions', 1, 250,
                                  config.REPEAT_DAYS, key='mv_days')
        mv_rn = c3.number_input('Top / bottom N', 1, 100, config.MOVERS_TOP_N,
                                key='mv_rn')
        rep = _mv('repeat_movers', key, int(mv_rn), side, int(mv_days))
        label = f'{side}{int(mv_rn)}_{key}'
        if rep.empty:
            st.info('No hits in this window.')
            st.stop()
        tbl = _mv_context(rep)
        st.caption(f'{len(tbl)} tickers · window: {int(tbl["sessions"].iloc[0])} '
                   'sessions')
        st.dataframe(tbl, use_container_width=True,
                     height=min(120 + 35 * len(tbl), 700),
                     column_config={
                         'hit_rate': st.column_config.ProgressColumn(
                             'hit %', format='%.0f%%', min_value=0, max_value=100),
                         'avg_change_pct': st.column_config.NumberColumn(
                             'avg % chg', format='%+.2f')})
        _tag = f'repeat_{label}_last{int(mv_days)}'
        d1, d2, _d3 = st.columns([1, 1, 3])
        d1.download_button('Download CSV', tbl.to_csv().encode(),
                           file_name=f'{_tag}_{run.name}.csv')
        d1.download_button('⭳ TradingView .txt', _tv_txt(tbl, _tag),
                           file_name=f'{_tag}_{run.name}.txt',
                           mime='text/plain', help=_TV_HELP)
        ln = d2.text_input('List name', key='mv_list_name',
                           placeholder='list name…')
        if d2.button('Save as list', key='mv_save_list',
                     disabled=not ln.strip()):
            dfil.save_list(ln.strip(), tbl.index)
            st.success(f'saved {len(tbl)} tickers to my_lists/{ln.strip()}.csv')

    else:
        sym = st.text_input('Ticker', key='mv_sym').strip().upper()
        if sym:
            ranks = _mv('ticker_ranks', sym)
            hits = _mv('ticker_hits', sym)
            if ranks.empty and hits.empty:
                st.info(f'{sym}: not in any index list or screener hit.')
            t1, t2 = st.columns(2)
            t1.markdown('**Rank in each index**')
            t1.dataframe(ranks, use_container_width=True, hide_index=True,
                         height=500)
            t2.markdown('**Screeners passed**')
            t2.dataframe(hits, use_container_width=True, hide_index=True,
                         height=500)

# ------------------------------------------------- Growth Cycle -----------
# PrimeTrading Lab Report "Growth Cycle": growth / value (IWF / IWD) risk
# gate x momentum -> six zones (src/growth_cycle.py, TODO.md §6). Computed
# on load (~0.5 s, 3 tickers), cached per IWF file version.
GC_COLORS = {'Risk-off': '#e07a7a', 'Probe': '#d9b86c', 'Ramp Up': '#4caf50',
             'Trim': '#2f6fd6', 'Hold': '#8fa6bf', 'Reload': '#7f9c7a'}
GC_ACTION = {'Risk-off': 'Defensive — build the watchlist',
             'Probe': 'Growth improving, gate not reclaimed — test small',
             'Ramp Up': 'Fresh risk-on, momentum rising — build into leaders',
             'Trim': 'Strong but stretched — harvest, don’t chase',
             'Hold': 'Extended but digesting — let winners work, no new size',
             'Reload': 'Pullback inside risk-on — leaders back to support '
                       '(watch for a failed reload)'}


@st.cache_data(show_spinner=False)
def _gc_model(_version: float):
    from src import growth_cycle
    data = growth_cycle.load_inputs()
    model = growth_cycle.compute(growth_cycle.ratio_bars(data))
    stats = growth_cycle.zone_stats(model, data['close'][config.GC_STATS_TICKER],
                                    config.GC_HISTORY_START)
    return model, stats, growth_cycle.zone_episodes(model)


if ACTIVE_TAB == 'growth':
    import altair as alt
    _how_built('ℹ️ How the Growth Cycle is built', [
        f'<b>Ratio</b> = growth / value = {config.GC_GROWTH} / '
        f'{config.GC_VALUE} daily bars (downloadData_v1). Rebuilt from '
        'PrimeTrading’s Lab Report “Growth Cycle” — only its public '
        'description and screenshots; calibrated on his readings Sep 18 – '
        'Oct 9 2026 (<code>test_growth_cycle.py</code>)',
        f'<b>10w structure</b> = EMA{config.GC_STRUCT_WEEKS} of the ratio’s '
        'weekly highs and weekly lows; the current week counts, so the band '
        'moves daily. <b>Risk gate</b>: close above the band = risk-on, below '
        '= risk-off, inside = keeps the last side',
        f'<b>Momentum</b> (x) = {config.GC_MOM_DAYS}-day change of the gap '
        f'to the band’s upper line, {config.GC_MOM_SMOOTH}-day mean, over its '
        f'own {config.GC_SIGMA_DAYS}-day σ; rising while > '
        f'+{config.GC_MOM_RISING}σ. <b>Gate σ</b> (y) = distance outside '
        f'the band in σ of that gap; extended above +{config.GC_EXTENDED}σ',
        '<b>Zones</b>: risk-off + fading = Risk-off · risk-off + rising = '
        'Probe · risk-on + rising = Ramp Up (Trim when extended) · risk-on + '
        'fading = Reload (Hold when extended). Day N = sessions in the zone',
        f'<b>Zone stats</b>: next {config.GC_STATS_FWD} sessions after each '
        f'day in the zone since {config.GC_HISTORY_START} — '
        f'{config.GC_STATS_TICKER} up %, its average move, and how often '
        'growth beat value. Zones describe the environment, not buy / sell '
        'signals',
    ])
    _iwf = config.DAILY_CURRENT / f'{config.GC_GROWTH}.csv'
    gc_m, gc_stats, gc_ep = _gc_model(_iwf.stat().st_mtime if _iwf.exists() else 0)
    if gc_m.empty:
        st.warning(f'No {config.GC_GROWTH} / {config.GC_VALUE} data.')
        st.stop()
    _t = gc_m.iloc[-1]
    _z = _t['zone']
    _gate = (f'Risk-on · since {_t.gate_since:%b %d}' if _t.risk_on
             else f'Risk-off · since {_t.gate_since:%b %d}')
    _mom = 'rising' if _t.momentum_sigma > config.GC_MOM_RISING else 'fading'
    st.markdown(
        f'<div style="background:{GC_COLORS[_z]};color:white;padding:0.8rem '
        f'1.2rem;border-radius:0.5rem;margin-bottom:0.8rem">'
        f'<span style="font-size:1.8rem;font-weight:700">{_z}</span>'
        f'&nbsp;&nbsp;<span style="font-size:1.05rem">{_gate} — momentum '
        f'{_mom} · day {_t.day_in_zone} in zone · {_t.name:%a %Y-%m-%d} '
        f'close</span><br><span style="font-size:0.95rem">{GC_ACTION[_z]}'
        f'</span></div>', unsafe_allow_html=True)
    k1, k2, k3, k4 = st.columns(4)
    k1.metric('Ratio vs 10w band', f'{_t.ratio:.4f}',
              f'band {_t.lower:.4f} – {_t.upper:.4f}', delta_color='off')
    k2.metric('Momentum', f'{_t.momentum_sigma:+.2f}σ',
              f'{_t.momentum_sigma - gc_m.momentum_sigma.iloc[-2]:+.2f}σ vs prior')
    k3.metric('Gate σ (outside band)', f'{_t.gate_sigma:+.2f}σ',
              f'gap to upper line {_t.gap_pct:+.2f}%', delta_color='off')
    k4.metric('Stretch vs 21d EMA', f'{_t.stretch_sigma:+.2f}σ',
              f'{_t.stretch_pct:+.2f}%', delta_color='off')

    _zscale = alt.Scale(domain=list(GC_COLORS), range=list(GC_COLORS.values()))
    c_map, c_ratio = st.columns([1, 1])
    with c_map:
        gc_path_n = st.slider('Path: last N sessions', 5, 60, 20, key='gc_path_n')
        _p = gc_m.tail(gc_path_n).rename_axis('Date').reset_index()
        _xr = max(3.0, float(_p.momentum_sigma.abs().max()) + 0.5)
        _yr = max(2.5, float(_p.gate_sigma.abs().max()) + 0.5)
        _mx, _ex = config.GC_MOM_RISING, config.GC_EXTENDED
        _regions = pd.DataFrame([
            ('Risk-off', -_xr, _mx, -_yr, 0), ('Probe', _mx, _xr, -_yr, 0),
            ('Reload', -_xr, _mx, 0, _ex), ('Ramp Up', _mx, _xr, 0, _ex),
            ('Hold', -_xr, _mx, _ex, _yr), ('Trim', _mx, _xr, _ex, _yr)],
            columns=['zone', 'x', 'x2', 'y', 'y2'])
        _bg = alt.Chart(_regions).mark_rect().encode(
            x=alt.X('x:Q', scale=alt.Scale(domain=[-_xr, _xr]),
                    title='Momentum (σ) — + = rising'),
            x2='x2', y=alt.Y('y:Q', scale=alt.Scale(domain=[-_yr, _yr]),
                             title='Risk gate — σ outside the 10w band'),
            y2='y2', color=alt.Color('zone:N', scale=_zscale, legend=None))
        _lbl = alt.Chart(_regions.assign(xm=lambda d: (d.x + d.x2) / 2,
                                         ym=lambda d: (d.y + d.y2) / 2)
                         ).mark_text(fontWeight='bold').encode(
            x='xm:Q', y='ym:Q', text='zone:N')
        _line = alt.Chart(_p).mark_line(color='white', strokeWidth=2.5).encode(
            x='momentum_sigma:Q', y='gate_sigma:Q', order='Date:T')
        _pts = alt.Chart(_p).mark_circle(size=60, opacity=1, stroke='black',
                                          strokeWidth=1).encode(
            x='momentum_sigma:Q', y='gate_sigma:Q',
            color=alt.Color('zone:N', scale=_zscale, legend=None),
            tooltip=[alt.Tooltip('Date:T', format='%Y-%m-%d'), 'zone',
                     alt.Tooltip('momentum_sigma:Q', format='+.2f', title='momentum σ'),
                     alt.Tooltip('gate_sigma:Q', format='+.2f', title='gate σ'),
                     'day_in_zone'])
        _now = alt.Chart(_p.tail(1)).mark_point(size=260, color='black',
                                                strokeWidth=2).encode(
            x='momentum_sigma:Q', y='gate_sigma:Q')
        st.altair_chart((_bg + _lbl + _line + _pts + _now).properties(height=420),
                        use_container_width=True)
        st.caption('Gate σ is 0 while the ratio is inside the band — the risk '
                   'gate then keeps its last side, so a point on the line can be '
                   'either Reload or Risk-off.')
    with c_ratio:
        gc_span = st.radio('Range', ['3M', '6M', '1Y', '2Y', 'All'], index=2,
                           horizontal=True, key='gc_span')
        _days = {'3M': 63, '6M': 126, '1Y': 252, '2Y': 504}.get(gc_span, len(gc_m))
        _r = gc_m.tail(_days).rename_axis('Date').reset_index()
        _band = alt.Chart(_r).mark_area(color='#3d5a78').encode(
            x=alt.X('Date:T', title=None),
            y=alt.Y('lower:Q', scale=alt.Scale(zero=False),
                    title=f'{config.GC_GROWTH} / {config.GC_VALUE}'),
            y2='upper:Q')
        _rp = alt.Chart(_r).mark_circle(size=30, opacity=1).encode(
            x='Date:T', y='ratio:Q',
            color=alt.Color('zone:N', scale=_zscale,
                            legend=alt.Legend(orient='bottom', title=None)),
            tooltip=[alt.Tooltip('Date:T', format='%Y-%m-%d'), 'zone',
                     alt.Tooltip('ratio:Q', format='.4f'),
                     alt.Tooltip('lower:Q', format='.4f'),
                     alt.Tooltip('upper:Q', format='.4f')])
        st.altair_chart((_band + _rp).properties(height=440),
                        use_container_width=True)

    st.markdown(f'**Zone every day since {config.GC_HISTORY_START[:4]}**')
    _s = gc_m.loc[config.GC_HISTORY_START:].rename_axis('Date').reset_index()
    _s['next'] = _s.Date.shift(-1).fillna(_s.Date.iloc[-1] + pd.Timedelta(days=1))
    st.altair_chart(alt.Chart(_s).mark_rect().encode(
        x=alt.X('Date:T', title=None), x2='next:T',
        color=alt.Color('zone:N', scale=_zscale,
                        legend=alt.Legend(orient='bottom', title=None)),
        tooltip=[alt.Tooltip('Date:T', format='%Y-%m-%d'), 'zone', 'day_in_zone']
    ).properties(height=70), use_container_width=True)

    s1, s2 = st.columns([1, 1])
    with s1:
        st.markdown(f'**Zone stats** — next {config.GC_STATS_FWD} sessions, '
                    f'since {config.GC_HISTORY_START[:4]}')
        st.dataframe(gc_stats.reset_index(), hide_index=True,
                     use_container_width=True, column_config={
                         'zone': 'Zone', 'days': 'Days', 'episodes': 'Episodes',
                         'up_pct': st.column_config.NumberColumn(
                             f'{config.GC_STATS_TICKER} up %', format='%.0f%%'),
                         'avg_move_pct': st.column_config.NumberColumn(
                             f'{config.GC_STATS_TICKER} avg move', format='%+.1f%%'),
                         'growth_won_pct': st.column_config.NumberColumn(
                             'Growth beat value', format='%.0f%%')})
    with s2:
        st.markdown('**Recent zone changes**')
        _e = gc_ep.tail(12).iloc[::-1].copy()
        _e['start'] = _e.start.dt.strftime('%Y-%m-%d')
        _e['end'] = _e.end.dt.strftime('%Y-%m-%d')
        st.dataframe(_e, hide_index=True, use_container_width=True, column_config={
            'zone': 'Zone', 'start': 'From', 'end': 'To', 'sessions': 'Sessions',
            'ratio_chg_pct': st.column_config.NumberColumn('Ratio chg',
                                                           format='%+.2f%%')})

# ------------------------------------------ Sustainability Ratio ----------
# Stacked daily panels of tickers / ratios (src/sr_panels.py) — replaces the
# CSV-driven PNGs of market_manipulation/market_charts. Layout = a built-in
# preset or a saved my_layouts/*.json, edited in a table on the page.
@st.cache_data(show_spinner=False)
def _sr_data(tickers: tuple, _version: float):
    from src import sr_panels
    d = sr_panels.load(list(tickers))
    return {'close': d['close'], 'open': d['open']}


if ACTIVE_TAB == 'sr':
    import altair as alt
    from src import sr_panels as srp
    _how_built('ℹ️ How the Sustainability Ratio panels are built', [
        'Daily closes from downloadData_v1, one chart per panel, all on the '
        'same date range. <b>Ticker</b> = its close · <b>Ratio</b> = close A '
        '/ close B · <b>Ratio no gaps</b> = both legs gap-adjusted, then A / '
        'B: from the start date on, every overnight gap (open − prior close) '
        'is summed and taken off the close, so only intraday moves remain '
        '(market_charts <code>gap_adjust.py</code> / SR_v1.pine). Start date '
        'empty = first day of the range',
        'Moving averages (EMA21, SMA50, SMA150, SMA200) are computed on the '
        'full history, so they are valid from the first bar shown. The line '
        'under each title: close vs each MA, 1W = 5 sessions, 1M = 21',
        f'Layouts: built-in presets, or your own saved as JSON in '
        f'<code>my_layouts/</code>. Up to {srp.MAX_PANELS} panels',
    ])
    _saved = srp.list_layouts()
    _opts = list(srp.PRESETS) + [f'💾 {n}' for n in _saved]
    if '_sr_select' in st.session_state:          # just saved -> show it
        st.session_state['sr_layout'] = st.session_state.pop('_sr_select')
    if st.session_state.get('sr_layout') not in _opts:
        st.session_state.pop('sr_layout', None)
    if st.session_state.get('_sr_flash'):
        st.success(st.session_state.pop('_sr_flash'))
    c1, c2, c3, c4 = st.columns([2.2, 1.8, 0.8, 2.0])
    sr_layout = c1.selectbox('Layout', _opts, key='sr_layout')
    sr_span = c2.radio('Range', ['3M', '6M', '1Y', '2Y', '5Y'], index=3,
                       horizontal=True, key='sr_span')
    sr_log = c3.checkbox('Log scale', key='sr_log')
    sr_mas = c4.multiselect('Moving averages', [m[0] for m in srp.MAS],
                            default=[m[0] for m in srp.MAS], key='sr_mas')
    # fixed figure size: 700 px split over the panels (>= 140 px each)
    _h, _w = 700, 1100
    _base = (srp.load_layout(sr_layout[2:]) if sr_layout.startswith('💾 ')
             else srp.PRESETS[sr_layout]) or []

    # ---- builder: the working layout lives in session state; picking
    # another Layout reloads it. Row widgets carry a nonce in their key so
    # add / move / remove redraw them from the list.
    if st.session_state.get('_sr_src') != sr_layout:
        st.session_state['_sr_src'] = sr_layout
        st.session_state['sr_build'] = [dict(p) for p in _base]
        st.session_state['sr_nonce'] = st.session_state.get('sr_nonce', 0) + 1
    _bl = st.session_state['sr_build']
    _nc = st.session_state['sr_nonce']
    for _k in [k for k in st.session_state                # rows of old nonces
               if re.fullmatch(r'sr_(t|a|b|up|dn|rm)\d+_(\d+)', str(k))
               and not str(k).endswith(f'_{_nc}')]:
        del st.session_state[_k]
    _choices = srp.ticker_choices()

    def _sr_move(i: int, j: int):
        b = st.session_state['sr_build']
        b[i], b[j] = b[j], b[i]
        st.session_state['sr_nonce'] += 1

    def _sr_remove(i: int):
        st.session_state['sr_build'].pop(i)
        st.session_state['sr_nonce'] += 1

    def _sr_add():
        st.session_state['sr_build'].append({'type': 'Ticker', 'a': 'SPY', 'b': ''})
        st.session_state['sr_nonce'] += 1

    with st.expander(f'🛠 Build / edit layout — {len(_bl)} chart'
                     f'{"s" if len(_bl) != 1 else ""}'):
        for _i, _row in enumerate(_bl):
            _opts_t = list(_choices) + [t for t in (_row['a'], _row['b'])
                                        if t and t not in _choices]

            def _fmt_t(t):
                return f'{t} — {_choices[t]}' if _choices.get(t) else t
            _dflt_b = 'QQQ' if _row['a'] == 'SPY' else 'SPY'
            r0, r1, r2, r3, r4 = st.columns([0.5, 1.4, 2.4, 2.4, 1.2])
            r0.markdown(f'**{_i + 1}**')
            _row['type'] = r1.selectbox(
                'Type', srp.PANEL_TYPES, key=f'sr_t{_i}_{_nc}',
                index=srp.PANEL_TYPES.index(_row['type']),
                label_visibility='collapsed')
            _row['a'] = r2.selectbox(
                'Ticker / A', _opts_t, key=f'sr_a{_i}_{_nc}', format_func=_fmt_t,
                index=_opts_t.index(_row['a']) if _row['a'] in _opts_t else 0,
                label_visibility='collapsed')
            if _row['type'] != 'Ticker':
                _row['b'] = r3.selectbox(
                    'B', _opts_t, key=f'sr_b{_i}_{_nc}', format_func=_fmt_t,
                    index=_opts_t.index(_row['b']) if _row['b'] in _opts_t
                    else _opts_t.index(_dflt_b) if _dflt_b in _opts_t else 0,
                    label_visibility='collapsed')
            else:
                r3.markdown('<span style="color:gray">—</span>',
                            unsafe_allow_html=True)
            b1, b2, b3 = r4.columns(3)
            b1.button('↑', key=f'sr_up{_i}_{_nc}', disabled=_i == 0,
                      on_click=_sr_move, args=(_i, _i - 1), help='Move up')
            b2.button('↓', key=f'sr_dn{_i}_{_nc}', disabled=_i == len(_bl) - 1,
                      on_click=_sr_move, args=(_i, _i + 1), help='Move down')
            b3.button('✕', key=f'sr_rm{_i}_{_nc}', on_click=_sr_remove,
                      args=(_i,), help='Remove chart')
        st.button('＋ Add chart', key='sr_add', on_click=_sr_add,
                  disabled=len(_bl) >= srp.MAX_PANELS)
        st.caption(f'Tickers: the first {config.SR_TICKER_LIST_N} rows of '
                   f'<code>{config.SR_TICKER_LIST.name}</code> (indexes, '
                   'sectors, styles, bonds). Changes show right away; they '
                   'are kept only once saved.', unsafe_allow_html=True)
        e1, e2, e3, e4 = st.columns([1.3, 1.6, 0.9, 0.9])
        sr_gap_start = e1.date_input('No-gaps start (empty = range start)',
                                     value=None, key='sr_gap_start')
        _sv_name = e2.text_input('Save layout as…', key='sr_save_name',
                                 placeholder='layout name')
        e3.write('')
        if e3.button('💾 Save layout', key='sr_save_btn',
                     disabled=not _sv_name.strip() or not _bl):
            # the Layout list above is already drawn: rerun so it lists
            # (and selects) the new file
            _p = srp.save_layout(_sv_name, _bl)
            st.session_state['_sr_select'] = f'💾 {_p.stem}'
            st.session_state['_sr_src'] = f'💾 {_p.stem}'    # keep the rows
            st.session_state['_sr_flash'] = f'Saved layout “{_p.stem}” ({_p.name}).'
            st.rerun()
        e4.write('')
        if sr_layout.startswith('💾 ') and e4.button(
                f'🗑 Delete “{sr_layout[2:]}”', key='sr_del_btn'):
            srp.delete_layout(sr_layout[2:])
            st.session_state['_sr_flash'] = f'Deleted layout “{sr_layout[2:]}”.'
            st.rerun()

    sr_panels = srp.clean_panels(_bl)
    if not sr_panels:
        st.info('No charts — add one in 🛠 Build / edit layout.')
        st.stop()
    _spy = config.DAILY_CURRENT / 'SPY.csv'
    _d = _sr_data(tuple(srp.tickers_of(sr_panels)),
                  _spy.stat().st_mtime if _spy.exists() else 0)
    _n = {'3M': 63, '6M': 126, '1Y': 252, '2Y': 504, '5Y': 1260}[sr_span]
    _dates = _d['close'].dropna(how='all').index[-_n:]
    _x0, _x1 = _dates[0], _dates[-1]
    _gs = pd.Timestamp(sr_gap_start) if sr_gap_start else _x0
    try:
        _dark = st.context.theme.type == 'dark'
    except AttributeError:
        _dark = True
    _line = '#e5e7eb' if _dark else '#111827'
    _ma_col = {m[0]: m[3] for m in srp.MAS}

    # one figure, panels stacked on a shared date axis (labels on the
    # bottom panel only); drag / wheel zooms all panels, hover draws the
    # same date line through every panel
    _views = []
    for _pn in sr_panels:
        _s = srp.panel_series(_pn, _d, _gs)
        _lbl = srp.label(_pn)
        if _s is None:
            st.warning(f'{_lbl}: no daily data in downloadData_v1 for '
                       f'{", ".join(t for t in (_pn["a"], _pn["b"]) if t)}.')
            continue
        _df = srp.with_mas(_s)
        _sub = srp.status(_df)
        _df = _df.loc[_x0:_x1]
        if _df.empty:
            st.warning(f'{_lbl}: no bars in the selected range.')
            continue
        _views.append((_lbl, _df, _sub))
    if not _views:
        st.stop()
    st.markdown(' &nbsp; '.join(
        f'<span style="color:{_ma_col[m]};font-weight:600">━ {m}</span>'
        for m in sr_mas), unsafe_allow_html=True)
    _ph = max(140, _h // len(_views))
    _zoom = alt.selection_interval(bind='scales', encodings=['x'], name='zoom')
    _hover = alt.selection_point(fields=['Date'], nearest=True, on='pointerover',
                                 clear='pointerout', empty=False, name='hover')
    _charts = []
    for _k, (_lbl, _df, _sub) in enumerate(_views):
        _last = _k == len(_views) - 1
        _v = _df['value'].iloc[-1]
        _fmt = '.2f' if abs(_v) >= 10 else '.4f'
        _long = (_df[['value'] + sr_mas].rename(columns={'value': _lbl})
                 .rename_axis('Date').reset_index()
                 .melt('Date', var_name='series', value_name='val').dropna())
        _x = alt.X('Date:T', title=None, scale=alt.Scale(domain=[_x0, _x1]),
                   axis=alt.Axis(labels=_last, ticks=_last, format='%b %y'))
        _y = alt.Y('val:Q', title=None, scale=alt.Scale(
            type='log' if sr_log else 'linear', zero=False))
        _base_ch = alt.Chart(_long).encode(x=_x)
        _lines = _base_ch.mark_line().encode(
            y=_y,
            color=alt.Color('series:N', legend=None, scale=alt.Scale(
                domain=[_lbl] + sr_mas,
                range=[_line] + [_ma_col[m] for m in sr_mas])),
            strokeWidth=alt.condition(alt.datum.series == _lbl,
                                      alt.value(1.8), alt.value(1.1)))
        _main = _long[_long.series == _lbl]
        _pts = alt.Chart(_main).mark_point(opacity=0, size=60).encode(
            x=_x, y=_y,
            tooltip=[alt.Tooltip('Date:T', format='%Y-%m-%d'),
                     alt.Tooltip('val:Q', format=_fmt, title=_lbl)])
        _rule = _base_ch.mark_rule(color='gray').encode().transform_filter(_hover)
        _layer = alt.layer(_lines, _rule, _pts).properties(
            width=_w, height=_ph, title=alt.TitleParams(
                f'{_lbl}  {_v:{_fmt}}', subtitle=_sub, anchor='start',
                fontSize=14, subtitleColor='gray'))
        _charts.append(_layer.add_params(_zoom, _hover))
    st.altair_chart(alt.vconcat(*_charts, spacing=6).resolve_scale(
        x='shared', y='independent'), use_container_width=False)

# ------------------------------------------ Where is each leader? --------
# PrimeTrading Lab Report "Leaders Map" for a user list FILE (no presets):
# each ticker on two clocks in daily ATR14 units — x = vs the 21-day EMA,
# y = vs the 10-week SMA (src/leader_map.py). Writes leader_map_<list>.png
# and .csv into the run folder, then shows them.
LM_DIRS = (ROOT / 'watchlists', dfil.MY_LISTS)

if ACTIVE_TAB == 'leadermap':
    _how_built('ℹ️ How the leader map works', [
        '<b>What it answers.</b> For every name in your list, two questions: '
        '<b>is the weekly trend still intact?</b> (up / down on the map) and '
        '<b>is the daily entry still there, or already missed?</b> (left / '
        'right). The green box is where both answers are “yes”',
        '<b>How to read a dot.</b> Right of the box = the stock ran away from '
        'its 21-day average (extended: wait for a pullback, don’t chase). Left '
        'of the box = it closed under the 21-day average (weakening). Above the '
        'dashed +4 line = stretched far above its 10-week average. Under the 0 '
        'line = it closed below its 10-week average: the weekly trend is lost',
        '<b>Why “in ATR”.</b> Distances are measured in ATR — the stock’s '
        'average daily move over 14 days — not in % or $. “+1 ATR above the 21 '
        'EMA” means one normal day’s move above it, for a calm stock or a wild '
        'one alike, so all names share one scale',
        '<b>Across (daily)</b> = (today’s close − 21-day EMA) ÷ ATR14',
        '<b>Up (weekly)</b> = (today’s close − 10-week SMA) ÷ the same daily '
        'ATR14. We only have daily bars, and that is enough: a weekly close is '
        'simply the last daily close of that week (normally Friday). We take '
        'each week’s last close and average the last 10. The current, '
        'unfinished week counts with today’s close — exactly what TradingView '
        'does for a weekly average shown on a daily chart. (downloadData’s own '
        'weekly files are not used.) The worked example below shows the 10 '
        'weekly closes for any ticker',
        f'<b>Zones.</b> Daily: under the 21-day &lt; {config.LMAP_DAILY_UNDER:g} '
        f'ATR · in the band {config.LMAP_DAILY_UNDER:g} to +{config.LMAP_DAILY_ABOVE:g} '
        f'· above &gt; +{config.LMAP_DAILY_ABOVE:g}. Weekly: lost &lt; 0 · '
        f'normal 0 to +{config.LMAP_WEEKLY_EXT:g} · extended &gt; +{config.LMAP_WEEKLY_EXT:g}. '
        'Buy area = in the band AND weekly normal. A name under its 10-week '
        'average is “lost the weekly” wherever it sits left/right',
        '<b>Sources.</b> Formulas: Alex’s TradingView script “ALEX – ATR '
        'Extensions” (<code>gd_systems/primeTrading/ATR extensions Sizing TV '
        'script_v7.txt</code>: <code>dist(x) = (close − x) / atr_val</code>, '
        '<code>atr_val</code> = daily ATR14, 21 EMA daily, 10 SMA weekly). Zones, '
        'box and states: his Lab Report “Leaders Map”. Checked against his '
        'report: the 9/25 map positions and the 9/28 buy-area / on-weakness '
        'names (validate.py #17)',
        '<b>Input</b>: one list file (TradingView .txt or CSV/TXT) from '
        '<code>watchlists/</code>, <code>my_lists/</code> or an upload — no '
        'presets; a CSV <code>theme</code> column groups “Where they cluster”, '
        f'else the industry. Latest bar only (run <code>{run.name}</code>). '
        'Output: <code>results/&lt;run&gt;/leader_map_&lt;list&gt;.png / .csv</code> '
        'and <code>leader_setups_&lt;list&gt;.png / .csv</code>',
        '<b>Setups — the plan</b> (below the map) turns the buy-area and '
        '“on weakness” names into a plan on the same daily axis: buy range, '
        'entry, stop at the bottom of the box, 2R target, where the name '
        'travelled over the last 30 sessions and how many of them closed in '
        'the band — rules explained above the plan'
    ])
    if 'ext_10wsma_atr' not in full.columns:
        st.warning('This run has no weekly column (ext_10wsma_atr) — re-run '
                   'the screeners.')
        st.stop()

    _files = sorted((p for d in LM_DIRS if d.exists() for p in d.iterdir()
                     if p.suffix.lower() in ('.txt', '.csv')),
                    key=lambda p: p.stat().st_mtime, reverse=True)
    _labels = {f'{p.parent.name}/{p.name}': p for p in _files}
    lc1, lc2, lc3 = st.columns([2, 2, 1], vertical_alignment='bottom')
    lm_pick = lc1.selectbox('List file (newest first)', ['— None Selected —']
                            + list(_labels), key='lm_file')
    lm_up = lc2.file_uploader('…or upload a list (CSV/TXT)', type=['csv', 'txt'],
                              key='lm_upload')
    lm_go = lc3.button('Generate map', key='lm_run', type='primary')

    src_name, src_text, src_themes = None, None, {}
    if lm_up is not None:
        src_name = Path(lm_up.name).stem
        src_text = lm_up.getvalue().decode('utf-8', errors='ignore')
    elif lm_pick in _labels:
        _p = _labels[lm_pick]
        src_name, src_text = _p.stem, _p.read_text(errors='ignore')
        src_themes = leader_map.read_themes(_p) if _p.suffix.lower() == '.csv' else {}

    if src_name:
        _slug = dfil._safe(src_name).replace(' ', '_')
        png_p = run / f'leader_map_{_slug}.png'
        csv_p = run / f'leader_map_{_slug}.csv'
        spng_p = run / f'leader_setups_{_slug}.png'
        scsv_p = run / f'leader_setups_{_slug}.csv'
        if lm_go or not png_p.exists() or not scsv_p.exists():
            tickers = leader_map.parse_tickers(src_text)
            # list names outside the universe: compute the two columns on the fly
            _out = [t for t in tickers if leader_map._lookup(full, t) is None]
            extra = None
            if _out:
                from src.focus import atr_extension
                _d = data_loader.load_price_matrices(_out, verbose=False)
                if len(_d['meta']):
                    extra = atr_extension.evaluate(_d['high'], _d['low'],
                                                   _d['close'], _d['volume'])
                    extra['close'] = _d['close'].iloc[-1]
            pos, missing = leader_map.build(full, tickers, src_themes, extra)
            _nf = pd.DataFrame(index=pd.Index(missing, name='ticker'))
            pd.concat([pos.assign(not_found=False),
                       _nf.assign(not_found=True)]).to_csv(csv_p)
            leader_map.plot(pos, 'Where is each leader?',
                            f'{src_name} · as of the {run.name} run · '
                            f'{len(pos)} of {len(tickers)} placed'
                            + (f' · not found: {", ".join(missing)}' if missing else ''),
                            png_p)
            _sets = leader_map.build_setups(pos)
            _sets.to_csv(scsv_p)
            if len(_sets):
                leader_map.plot_setups(
                    _sets, 'Setups — the plan',
                    f'{src_name} · as of the {run.name} run · '
                    f'{int((_sets["role"] == "buy").sum())} in the buy area, '
                    f'{int((_sets["role"] == "weakness").sum())} on weakness '
                    f'(≤ +{config.LMAP_SETUP_MAX_ABOVE:g} ATR above the box)', spng_p)
            elif spng_p.exists():
                spng_p.unlink()
        raw = pd.read_csv(csv_p, index_col=0)
        _nfm = raw['not_found'].astype(str).eq('True')
        pos, missing = raw[~_nfm].drop(columns='not_found'), list(raw.index[_nfm])
        pos['list_rank'] = pos['list_rank'].astype('Int64')

        with st.expander('🗺️ Map', expanded=True):
            st.image(str(png_p), use_container_width=True)
            st.download_button('⭳ PNG', png_p.read_bytes(), file_name=png_p.name,
                               mime='image/png')
        st.caption(f'`{png_p.relative_to(ROOT)}` · {len(pos)} placed'
                   + (f' · not found (no price file): {", ".join(missing)}'
                      if missing else ''))

        sc1, sc2 = st.columns([3, 2])
        with sc1:
            st.markdown('**By state — best first**')
            for key, title, wk in leader_map.STATES:
                names = pos.index[pos['state'] == key]
                with st.container(border=True):
                    st.markdown(f'**{title}** · <span style="color:gray">{wk}'
                                f'</span> — **{len(names)}**',
                                unsafe_allow_html=True)
                    st.caption(' '.join(names) if len(names) else '—')
        with sc2:
            st.markdown('**Where they cluster** — in the buy area / total')
            cl = leader_map.clusters(pos)
            cl['share'] = (cl['in_buy_area'] / cl['total'] * 100).round(0)
            st.dataframe(cl, use_container_width=True,
                         column_config={'share': st.column_config.ProgressColumn(
                             'in box', min_value=0, max_value=100, format='%d%%')})
            st.caption('Group = the list file’s theme column when present, '
                       'else the TradingView industry.')

        # ---- Setups — the plan
        st.subheader('Setups — the plan')
        _sets = pd.read_csv(scsv_p, index_col=0) if scsv_p.exists() else pd.DataFrame()
        st.caption(
            'Every name in the buy area, then every name “on weakness” (above the '
            f'box by at most +{config.LMAP_SETUP_MAX_ABOVE:g} ATR, weekly normal), '
            'in list order. <b>buy / wait for</b> = the box in price (21 EMA − 0.5 '
            'ATR … + 1 ATR). <b>Entry</b> = today’s close in the buy area; on '
            'weakness = the top of the 21dma-structure (21 EMA of the highs), '
            'i.e. wait for the pullback. <b>Stop</b> = the bottom of the box. '
            f'<b>Target</b> = entry + {config.LMAP_SETUP_R:g} × (entry − stop). '
            'Checked against the 9/28 Prime Report (validate.py #18). Alex’s own '
            'checklist / theme picks and the “tight / higher lows / volume dry” '
            'tags are not modelled.', unsafe_allow_html=True)
        if len(_sets) and spng_p.exists():
            with st.expander('🗺️ The plan', expanded=True):
                st.image(str(spng_p), use_container_width=True)
                st.download_button('⭳ PNG', spng_p.read_bytes(),
                                   file_name=spng_p.name, mime='image/png',
                                   key='lm_setups_png')
            _cols = ['role', 'x', 'close', 'buy_lo', 'buy_hi', 'entry', 'stop',
                     'stop_pct', 'target', 'target_pct', 'in_band_30',
                     'travel_min', 'travel_max', 'x_30_ago', 'group', 'rs_pct',
                     'list_rank']
            st.dataframe(_sets[[c for c in _cols if c in _sets]],
                         use_container_width=True,
                         height=min(120 + 35 * len(_sets), 500))
            s1, s2, _s3 = st.columns([1, 1, 3])
            s1.download_button('Download setups CSV', scsv_p.read_bytes(),
                               file_name=scsv_p.name, key='lm_setups_csv')
            s2.download_button('⭳ TradingView .txt (setups)',
                               _tv_txt(_sets, f'Setups — {src_name}'),
                               file_name=f'leader_setups_{_slug}.txt',
                               mime='text/plain', help=_TV_HELP,
                               key='lm_setups_tv')
        else:
            st.caption('No name in the buy area or on weakness today.')

        st.subheader('All positions')
        tbl = pos.sort_values('list_rank')
        st.dataframe(tbl, use_container_width=True,
                     height=min(120 + 35 * len(tbl), 600))

        # worked example: the actual numbers behind one dot
        with st.expander('🧮 Worked example — the numbers behind one dot'):
            ex_t = st.selectbox('Ticker', list(tbl.index), key='lm_explain')
            ex = leader_map.explain(ex_t) if ex_t else None
            if ex is None:
                st.caption('no price file for this ticker')
            else:
                _stt = leader_map.STATE_TITLE[leader_map.classify(ex['x'], ex['y'])]
                st.markdown(
                    f"**{ex['ticker']}** at the {ex['date']:%Y-%m-%d} close  \n"
                    f"close **{ex['close']:,.2f}** · 21-day EMA **{ex['ema21']:,.2f}** · "
                    f"ATR14 **{ex['atr']:,.2f}** (the stock's average daily move)  \n"
                    f"**Across (daily)** = ({ex['close']:,.2f} − {ex['ema21']:,.2f}) ÷ "
                    f"{ex['atr']:,.2f} = **{ex['x']:+.2f} ATR** → "
                    f"{dict(under='under the 21-day', band='in the 21-day band', above='above the 21-day band')[leader_map.daily_zone(ex['x'])]}  \n"
                    f"**Up (weekly)** = ({ex['close']:,.2f} − {ex['sma10w']:,.2f}) ÷ "
                    f"{ex['atr']:,.2f} = **{ex['y']:+.2f} ATR**, where "
                    f"{ex['sma10w']:,.2f} is the average of the 10 weekly closes below  \n"
                    f"→ state: **{_stt}**")
                _w = ex['weeks'].copy()
                _w['last trading day'] = _w['last trading day'].dt.strftime('%a %Y-%m-%d')
                _w.index = _w.index.strftime('%Y-%m-%d')
                st.dataframe(_w.round(2), use_container_width=True)
                st.caption('Each weekly close = the last daily close of that week. '
                           'The newest week may be unfinished — it then uses '
                           'today’s close, like TradingView on a daily chart.')
        d1, d2, _d3 = st.columns([1, 1, 3])
        d1.download_button('Download CSV', tbl.to_csv().encode(),
                           file_name=csv_p.name)
        _buy = tbl[tbl['state'] == 'buy']
        d2.download_button('⭳ TradingView .txt (buy area)',
                           _tv_txt(_buy, f'Buy area — {src_name}'),
                           file_name=f'leader_map_buy_{_slug}.txt',
                           mime='text/plain', help=_TV_HELP,
                           disabled=not len(_buy))
    else:
        st.info('Pick a list file (or upload one) to draw the map.')

if ACTIVE_TAB == 'leaders':
    _how_built('ℹ️ How these lists are built', [
        _universe_line(),
        f'<b>Minervini trend template</b> — all {config.MINERVINI_MIN_PASS} '
        f'of: close > SMA150 & SMA200 · SMA150 > SMA200 · SMA200 rising '
        f'({config.MINERVINI_SLOPE_WINDOW}d slope > 0) · SMA50 > SMA150 & '
        f'SMA200 · close > SMA50 · close ≥ '
        f'{config.MINERVINI_ABOVE_52W_LOW:.2f}× 52w low · close ≥ '
        f'{config.MINERVINI_FROM_52W_HIGH:.2f}× 52w high · RS percentile ≥ '
        f'{config.MINERVINI_MIN_RS} (IBD-style blend)',
        f'<b>CANSLIM C-A-I</b> — C: latest quarterly EPS YoY ≥ '
        f'+{config.CANSLIM_C_MIN_YOY:.0%} (year-ago EPS ≥ '
        f'${config.CANSLIM_C_MIN_BASE_EPS:.2f}) · A: 3y annual EPS CAGR ≥ '
        f'+{config.CANSLIM_A_MIN_CAGR:.0%} · I: institutional ownership ≥ '
        f'{config.CANSLIM_I_MIN_INST:.0%} — all three',
        f'<b>SCOOTER / SCTR</b> — StockCharts Technical Rank ≥ '
        f'{config.SCOOTER_MIN_SCORE:.0f}: 60% long-term (% vs 200 EMA, '
        f'125d ROC), 30% mid (% vs 50 EMA, 20d ROC), 10% short (RSI14, PPO '
        f'slope), ranked 0–99.9 within this universe',
        '<b>Union</b> — every ticker in at least one of the three lists, '
        'deduped; <code>sources</code> / <code>n_sources</code> show which',
    ])
    for name, label in [('minervini', 'Minervini trend template (8/8)'),
                        ('canslim', 'CANSLIM C-A-I'),
                        ('scooter', 'SCOOTER / SCTR ≥ 90'),
                        ('all', 'Union (deduped, all lists)')]:
        df = leaders.get(name)
        with st.expander(f'{label} — {0 if df is None else len(df)} tickers',
                         expanded=(name == 'all')):
            if df is not None and len(df):
                st.dataframe(df.round(2), use_container_width=True, height=360)
                lc1, lc2, _lc3 = st.columns([1, 1, 2])
                lc1.download_button(f'Download leaders_{name}.csv',
                                    df.round(3).to_csv().encode(),
                                    file_name=f'leaders_{name}_{run.name}.csv')
                lc2.download_button(
                    '⭳ TradingView .txt',
                    _tv_txt(df, f'Leaders · {label}'),
                    file_name=f'leaders_{name}_{run.name}.txt',
                    mime='text/plain', key=f'lead_tv_{name}', help=_TV_HELP)

# ------------------------------------------------------------- focus ------
if ACTIVE_TAB == 'focus':
    # mirrors run_screeners.py's focus gates (defaults; CLI overrides such as
    # --stages / --no-liquidity-gate aren't recorded in the run)
    _how_built('ℹ️ How the Focus List is built', [
        _universe_line(),
        '<b>Leaders</b> — in at least one Leaders’ List (Minervini, CANSLIM or '
        'SCOOTER; see the Leaders’ Lists tab)',
        f'<b>Stage</b> — Weinstein stage {" or ".join(config.FOCUS_STAGES)} '
        '(early / mid uptrend)',
        f'<b>Not very extended</b> — ≤ {config.EXT_THRESHOLD_2:g} ATR above '
        f'both the {config.EXT_EMA_PERIOD} EMA and the {config.EXT_SMA_PERIOD} SMA',
        f'<b>Liquid</b> — {config.ADV_PERIOD}-day average dollar volume ≥ '
        f'${config.MIN_ADV_DOLLAR / 1e6:g}M'
        + ('' if config.APPLY_LIQUIDITY_GATE else ' (gate currently OFF)'),
        '<b>Sort</b> — SCOOTER (SCTR) score, highest first',
    ])
    st.markdown(f"**{len(focus)} tickers**")
    if len(focus):
        st.dataframe(focus.round(2), use_container_width=True, height=520)
        fc1, fc2, _fc3 = st.columns([1, 1, 2])
        fc1.download_button('Download focus_list.csv',
                            focus.round(3).to_csv().encode(),
                            file_name=f'focus_list_{run.name}.csv')
        fc2.download_button('⭳ TradingView .txt',
                            _tv_txt(focus, f'Focus List — {run.name}'),
                            file_name=f'focus_list_{run.name}.txt',
                            mime='text/plain', help=_TV_HELP)
    else:
        st.info('Empty focus list in this run.')

# --------------------------------------------------------- confluence ----
# IMPLEMENTATION_PLAN.md §19 — badge-count leaders. Pure aggregation over the
# daily batch's screener_results.csv (`full`); nothing here runs a screener.
# On-demand pattern badges (DB, C&H) are merged opportunistically from
# today's cache when the Patterns tab has already produced it.
_CFL_CSS = """
<style>
.cfl-wrap { display:flex; flex-direction:column; gap:8px; }
.cfl-card { display:flex; justify-content:space-between; align-items:center;
  gap:12px; background:rgba(255,255,255,.03); border:1px solid rgba(255,255,255,.08);
  border-left:4px solid #64748b; border-radius:10px; padding:10px 14px; }
.cfl-head { display:flex; align-items:baseline; gap:10px; }
.cfl-tkr { font-weight:700; font-size:1.05rem; }
.cfl-chg { font-weight:600; font-size:.9rem; }
.cfl-sub { color:#94a3b8; font-size:.8rem; margin:2px 0 6px; }
.cfl-badges { display:flex; flex-wrap:wrap; gap:5px; }
.cfl-pill { font-size:.72rem; font-weight:700; color:#0b1220; border-radius:6px;
  padding:2px 7px; line-height:1.5; }
.cfl-ctx { background:transparent; color:#94a3b8; border:1px solid rgba(255,255,255,.18);
  font-weight:500; }
.cfl-scores { display:flex; gap:8px; flex:0 0 auto; }
.cfl-sq, .cfl-ci { width:42px; height:42px; display:flex; align-items:center;
  justify-content:center; font-weight:700; color:#0b1220; font-size:.95rem; }
.cfl-sq { border-radius:9px; } .cfl-ci { border-radius:50%; }
</style>
"""


def _cfl_cap(v):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return '—'
    for unit, div in (('T', 1e12), ('B', 1e9), ('M', 1e6)):
        if v >= div:
            return f'${v / div:.1f}{unit}'
    return f'${v:,.0f}'


def _cfl_tier(v, steps):
    col = steps[0][1]
    for thr, c in steps:
        if v >= thr:
            col = c
    return col


_FAM_STEPS = [(0, '#64748b'), (2, '#22c55e'), (3, '#eab308'), (4, '#f97316')]
_BADGE_STEPS = [(0, '#64748b'), (3, '#22c55e'), (5, '#eab308'), (7, '#f97316')]
_SCORE_STEPS = [(0, '#64748b'), (30, '#22c55e'), (50, '#eab308'), (70, '#f97316')]


def _confluence_cards(df_top: pd.DataFrame, circle_key: str):
    fam_c = confluence.FAMILY_COLORS
    fam_of = confluence.BADGE_FAMILY
    rows = [_CFL_CSS, '<div class="cfl-wrap">']
    for t, r in df_top.iterrows():
        chg = pd.to_numeric(pd.Series([r.get('daily_gain_pct')]),
                            errors='coerce').iloc[0]
        accent = ('#22c55e' if pd.notna(chg) and chg > 0
                  else '#ef4444' if pd.notna(chg) and chg < 0 else '#64748b')
        chg_html = (f'<span class="cfl-chg" style="color:{accent}">'
                    f'{chg:+.1f}%</span>' if pd.notna(chg) else '')
        g1m = r.get('gain_1m')
        adr = r.get('adr20_pct')
        sub = ' · '.join(filter(None, [
            _cfl_cap(r.get('market_cap')),
            f'{g1m:+.1f}% 1m' if pd.notna(g1m) else None,
            f'ADR {adr:.1f}%' if pd.notna(adr) else None]))
        pills = ''.join(
            f'<span class="cfl-pill" style="background:{fam_c[fam_of[c]]}" '
            f'title="{confluence.BADGE_LABEL[c]}">{c}</span>'
            for c in r['badges'])
        pills += ''.join(f'<span class="cfl-pill cfl-ctx">{tag}</span>'
                         for tag in r['context'])
        circ_val = r[circle_key]
        circ_col = _cfl_tier(circ_val,
                             _SCORE_STEPS if circle_key == 'confluence_score'
                             else _FAM_STEPS)
        rows.append(
            f'<div class="cfl-card" style="border-left-color:{accent}">'
            f'<div class="cfl-main">'
            f'<div class="cfl-head"><span class="cfl-tkr">{t}</span>'
            f'{chg_html}</div>'
            f'<div class="cfl-sub">{sub}</div>'
            f'<div class="cfl-badges">{pills}</div></div>'
            f'<div class="cfl-scores">'
            f'<span class="cfl-sq" style="background:'
            f'{_cfl_tier(r["n_badges"], _BADGE_STEPS)}" '
            f'title="{r["n_badges"]} badges">{r["n_badges"]}</span>'
            f'<span class="cfl-ci" style="background:{circ_col}" '
            f'title="{circle_key}">{circ_val:.0f}</span></div></div>')
    rows.append('</div>')
    return '\n'.join(rows)


def _confluence_history(scope, min_fam: int, must: list, days: int):
    """Confluence over the last `days` stored runs (results/history.db):
    per ticker, on how many runs it met Min families / Must include —
    ranked by that count, then streak. Batch badges only."""
    rows, sessions = _mv('confluence_window', days)
    if not sessions:
        st.warning('No Confluence history yet — run `python3 run_screeners.py '
                   '--backfill-hits` once.')
        return
    rows = rows[rows['symbol'].isin(scope) & (rows['n_families'] >= min_fam)]
    for fam in must:
        rows = rows[rows['families'].str.split(',').apply(lambda fs: fam in fs)]
    st.caption(f'{len(sessions)} runs: {sessions[-1]} → {sessions[0]} · '
               f'{len(scope):,} tickers in scope · counted when ≥ {min_fam} '
               'families' + (f' incl. {", ".join(must)}' if must else '')
               + ' · batch badges only (no Patterns)')
    if rows.empty:
        st.info('No ticker met the filters on any of these runs.')
        return
    rep = repeat_table(rows[['snapshot_date', 'symbol']], sessions) \
        .drop(columns='avg_change_pct').set_index('symbol')
    fam = rows.groupby('symbol')['n_families']
    rep['avg_families'] = fam.mean().round(1)
    rep['max_families'] = fam.max()
    today = rows[rows['snapshot_date'] == sessions[0]].set_index('symbol')
    rep['families_today'] = today['n_families'].reindex(rep.index).astype('Int64')
    rep['badges_today'] = today['badges'].reindex(rep.index)
    rep = rep.rename(columns={'hits': 'days', 'sessions': 'of'})
    rep = rep[['days', 'of', 'hit_rate', 'streak', 'avg_families',
               'max_families', 'families_today', 'badges_today',
               'first_hit', 'last_hit']]
    rep = rep.join(full[['sector', 'industry']], how='left')
    rep.index.name = 'ticker'
    st.caption(f'{len(rep):,} tickers')
    if len(rep) <= 200:
        rep.insert(2, 'spark', [_spark_closes(t, run.name) for t in rep.index])
    st.dataframe(rep, use_container_width=True,
                 height=min(120 + 35 * len(rep), 720),
                 column_config={
                     'spark': st.column_config.LineChartColumn('120d', width=150),
                     'hit_rate': st.column_config.ProgressColumn(
                         'days %', format='%.0f%%', min_value=0, max_value=100)})
    tag = f'confluence_last{days}_min{min_fam}'
    d1, d2, _d3 = st.columns([1, 1, 3])
    d1.download_button('Download CSV', rep.drop(columns='spark', errors='ignore')
                       .to_csv().encode(), file_name=f'{tag}_{run.name}.csv')
    d1.download_button('⭳ TradingView .txt', _tv_txt(rep, tag),
                       file_name=f'{tag}_{run.name}.txt', mime='text/plain',
                       help=_TV_HELP)
    ln = d2.text_input('List name', key='cfh_list_name', placeholder='list name…')
    if d2.button('Save as list', key='cfh_save_list', disabled=not ln.strip()):
        dfil.save_list(ln.strip(), rep.index)
        st.success(f'saved {len(rep)} tickers to my_lists/{ln.strip()}.csv')


if ACTIVE_TAB == 'confluence':
    _cf_fams = {}
    for _code, _lbl, _fam, _t in confluence.BADGES:
        _cf_fams.setdefault(_fam, []).append(_code)
    _how_built('ℹ️ How Confluence is built', [
        _universe_line(),
        'Every screener answers yes/no per ticker; Confluence collects '
        '<i>which</i> ones fired (a <b>badge</b> each) and ranks the names '
        'where the most <b>independent method families</b> agree — a union '
        'sorted by count, not an intersection',
        '<b>Families</b> (a family counts once, however many of its badges '
        'fire — Minervini, SCOOTER, RS90… are one idea, not five): '
        + '; '.join(f'<b>{f}</b> {" ".join(c)}' for f, c in _cf_fams.items()),
        '<b>n_families</b> (default rank) = families with ≥ 1 badge. '
        '<b>n_badges</b> = all badges lit. <b>confluence_score</b> = 0–100, '
        'at most 2 badges per family, normalised — a tie-breaker, not a '
        'backtested expectancy',
        'Stage 2A/2B/2C and the RTI zone show on the cards as faint context '
        'pills, never counted. Timing badges (PVB, ATR1, blue/black dots) are '
        'computed in the daily run. Pattern badges (DB, C&H) light up only '
        'when the Patterns tab has been run today',
        '<b>Scope</b> (index, min market cap), <b>Min families</b> and '
        '<b>Must include family</b> only filter the latest run — nothing is '
        'recomputed. Details: <code>docs/confluence.md</code>',
        '<b>Last N days</b>: every run saves each ticker’s families and '
        'badges to <code>results/history.db</code> (batch badges only, so '
        'all days count the same way). <b>days</b> = on how many of the last '
        'N runs the ticker met Min families / Must include; sorted by days, '
        'then streak (consecutive runs up to the newest). Past sessions are '
        'recomputed as of their own date (<code>run_screeners.py '
        '--backfill-days N</code>) with today’s screeners — but CANSLIM (ON) '
        'and CANTATA (CE) use today’s fundamentals snapshot for every day',
    ])
    st.caption('Badge-count leaders — the names lit up by the most independent '
               'method *families*. Pure aggregation over the latest daily run '
               f'(`{run.name}`); press "Re-run screeners" above to refresh. '
               'Pattern badges (DB, C&H) appear only when the Patterns tab '
               'has been run today.')

    cf_mode = st.radio('Show', ['Today', 'Last N days'], key='cf_mode',
                       horizontal=True,
                       help='Today = the latest run, ranked by families. '
                            'Last N days = how many of the last N runs each '
                            'ticker met the filters below')
    cf_hist = cf_mode == 'Last N days'

    cf1, cf2, cf3 = st.columns([3, 2, 2])
    cf_indexes = cf1.multiselect('Scope: index membership', index_choices(),
                                 key='cf_index',
                                 help='empty = whole universe')
    cf_cap = cf2.select_slider('Min market cap',
                               options=[0, 300e6, 1e9, 2e9, 10e9], value=0,
                               key='cf_cap', format_func=lambda v: f'${v:,.0f}')
    if cf_hist:
        cf_days = cf3.number_input('Last N days (runs)', 1, 250, 20,
                                   key='cf_days')
    else:
        cf_rank = cf3.selectbox('Rank by', ['n_families', 'n_badges',
                                            'confluence_score'], key='cf_rank')
    cf4, cf5, cf6 = st.columns([2, 2, 2])
    cf_minfam = cf4.slider('Min families', 0, len(confluence.FAMILIES), 3,
                           key='cf_minfam')
    cf_must = cf5.multiselect('Must include family', confluence.FAMILIES,
                              key='cf_must')
    if not cf_hist:
        cf_n = cf6.selectbox('Cards to show', [20, 30, 50, 100], index=1,
                             key='cf_n')

    # scope mask over `full` — no data load, no compute of screeners
    cf_mask = pd.Series(True, index=full.index)
    if cf_indexes:
        _sel = set(cf_indexes)
        cf_mask &= pd.Series(full.index.map(
            lambda t: bool(IDX_MAP.get(str(t).upper(), frozenset()) & _sel)),
            index=full.index)
    if cf_cap:
        cf_mask &= pd.to_numeric(full['market_cap'], errors='coerce').fillna(0) >= cf_cap
    scoped = full[cf_mask]

    if cf_hist:
        _confluence_history(scoped.index, cf_minfam, cf_must, int(cf_days))
        st.stop()

    cf_extra = confluence.merge_ondemand(report.run_dir(), scoped.index)
    st.caption(f'{len(scoped):,} tickers in scope · on-demand badges '
               + (f'live: {", ".join(cf_extra)}' if cf_extra
                  else 'none cached today'))

    cf_df = confluence.compute(scoped, cf_extra)
    cf_df = cf_df[cf_df['n_families'] >= cf_minfam]
    for fam in cf_must:
        cf_df = cf_df[cf_df['families'].apply(lambda fs: fam in fs)]
    cf_df = confluence.rank(cf_df, cf_rank)

    st.caption(f'{len(cf_df):,} names with ≥ {cf_minfam} families')
    if not len(cf_df):
        st.info('No names meet the family threshold in this scope.')
    else:
        top = cf_df.head(int(cf_n))
        st.markdown(_confluence_cards(top, cf_rank), unsafe_allow_html=True)

        st.divider()
        bdg_cols = [f'bdg_{c}' for c, *_ in confluence.BADGES]
        tbl_cols = (['n_families', 'n_badges', 'confluence_score', 'close',
                     'daily_gain_pct', 'gain_1m', 'adr20_pct', 'stage',
                     'rs_pct', 'scooter_score', 'market_cap', 'sector']
                    + bdg_cols)
        tbl_cols = [c for c in tbl_cols if c in cf_df.columns]
        tbl = cf_df[tbl_cols].copy()
        if len(tbl) <= 200:
            tbl.insert(1, 'spark',
                       [_spark_closes(t, run.name) for t in tbl.index])
        cf_event = st.dataframe(
            tbl.round(2), use_container_width=True,
            height=min(120 + 32 * max(1, len(tbl)), 720),
            on_select='rerun', selection_mode='multi-row', key='cf_sel',
            column_config={'spark': st.column_config.LineChartColumn(
                '120d', width=150)})
        try:
            cf_rows = cf_event.selection.rows
        except AttributeError:
            cf_rows = (cf_event.get('selection', {}) or {}).get('rows', []) \
                if isinstance(cf_event, dict) else []
        cf_selected = list(tbl.index[cf_rows]) if cf_rows else []

        e1, e2, e3 = st.columns([1, 1, 3])
        e1.download_button(
            'Download CSV (ranked)',
            cf_df[tbl_cols + ['badges', 'families']].round(3).to_csv().encode(),
            file_name=f'confluence_{run.name}.csv')
        e1.download_button(
            '⭳ TradingView .txt',
            _tv_txt(cf_df, f'Confluence — {run.name}'),
            file_name=f'confluence_{run.name}.txt',
            mime='text/plain', help=_TV_HELP)
        cf_ln = e2.text_input('List name', key='cf_list_name',
                              placeholder='list name…')
        cf_save_sel = e2.button('Save SELECTED as list', key='cf_save_sel',
                                disabled=not (cf_ln.strip() and cf_selected))
        cf_save_top = e3.button(f'Save top {int(cf_n)} as list',
                                key='cf_save_top', disabled=not cf_ln.strip())
        if (cf_save_sel or cf_save_top) and cf_ln.strip():
            _tk = cf_selected if cf_save_sel else list(top.index)
            dfil.save_list(cf_ln.strip(), _tk)
            st.success(f'saved {len(_tk)} tickers to my_lists/{cf_ln.strip()}.csv')

# ------------------------------------------------------------- detail -----
@st.cache_data(ttl=600)
def _fin_table() -> pd.DataFrame:
    """Fundamentals snapshot (earnings dates / results) for the summary."""
    try:
        return data_loader.load_financial_data()
    except OSError:
        return pd.DataFrame()


if ACTIVE_TAB == 'detail':
    ticker = st.selectbox('Ticker', sorted(full.index))
    if ticker:
        row = full.loc[ticker]
        # readable summary first (TODO item 7); the full metric dump below
        _fin = _fin_table()
        _sections = ticker_summary.build(
            ticker, row,
            HistoryDB() if config.HISTORY_DB.exists() else None,
            _fin.loc[ticker] if ticker in _fin.index else None)
        with st.container(border=True):
            st.markdown(f"#### {ticker} — {row.get('description', '')}")
            _half = (len(_sections) + 1) // 2
            for _col, _part in zip(st.columns(2), (_sections[:_half],
                                                   _sections[_half:])):
                _col.markdown(ticker_summary.to_markdown(_part))
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
        with right.expander(f'HVE record ladder — status: '
                            f'{row.get("hve_status", "?")}'):
            try:
                st.dataframe(volume_records.ticker_ladder(ticker),
                             use_container_width=True, hide_index=True)
            except OSError:
                st.caption('no HVE baseline in volume_records/baseline/')
        detail = row.to_frame('value')
        detail['value'] = detail['value'].map(
            lambda v: f'{v:,.3f}' if isinstance(v, float) else str(v))
        st.dataframe(detail, use_container_width=True, height=560)


# sparkline closes for the on-demand Patterns tab
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


# --------------------------------------------------- Patterns (on-demand)
# feedback_4.md Task 7 — pattern-geometry detectors with user-adjustable
# parameters (GLB sliders; Cup & Handle named presets). Same shared
# scope/Run/progress/persist plumbing (src/on_demand.py).

if ACTIVE_TAB == 'patterns':
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
        if len(show_pt):
            d1.download_button(
                '⭳ TradingView .txt (signals)',
                _tv_txt(show_pt, f'Patterns · {pt_file_key}'),
                file_name=f'patterns_{pt_file_key}_{run.name}.txt',
                mime='text/plain', help=_TV_HELP)
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
            # a kept pick from an earlier result list (persisted state)
            # would come back as the value although it's not an option
            if st.session_state.get('pt_chart_ticker') not in show_pt.index:
                st.session_state.pop('pt_chart_ticker', None)
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

# ------------------------------------------------------ Workflows (in-memory)
# docs/workflows_tab.md — a saved multi-stage funnel run end-to-end over the
# latest daily screener_results.csv. No screener re-run, no data load: every
# stage just row-filters `full` with dfil.build_mask + build_advanced_mask.

def _wf_md(txt) -> str:
    """Escape workflow-authored text for st.caption/markdown — a bare
    '$' pair renders as LaTeX (e.g. 'price>$3 ... ADV>$1M')."""
    return str(txt).replace('$', r'\$')


WF_STEP_COLS = ['close', 'adr20_pct', 'rti_zone', 'ext_21ema_atr',
                'ext_40sma_atr', 'ext_50sma_atr', 'pct_above_63d_low', 'gain_1m', 'gain_3m',
                'gain_6m', 'rs_pct', 'stage', 'sector']
WF_EDITOR_FLAGS = {
    'adv_gold_launch_pad': 'Golden Launch Pad',
    'adv_qullamaggie': 'Qullamaggie suite',
    'adv_9m_movers': 'Stockbee 9M mover',
    'adv_weekly_movers': 'Stockbee 20% weekly',
    'adv_daily_gainers': 'Stockbee 4% daily',
    'adv_volume_anomaly': 'Volume anomaly (3σ)',
    'adv_adl_accumulation': 'ADL accumulation',
    'adv_cantata': 'CANTATA CE leader',
    'adv_rti_dots': 'RTI low-vol dots',
}
_WF_EXPOSED_ADV = ({'adv_leaders', 'adv_leaders_mode', 'adv_stages',
                    'adv_rti_zone', 'adv_max_ext', 'adv_max_ext21',
                    'adv_max_ext50'} | set(WF_EDITOR_FLAGS))


def _wf_unique_stage_name(base: str, draft: dict) -> str:
    names = {s['name'] for s in draft['stages']}
    if base not in names:
        return base
    i = 2
    while f'{base} ({i})' in names:
        i += 1
    return f'{base} ({i})'


def _wf_unique_workflow_name(base: str) -> str:
    taken = set(dfil.builtin_workflows()) | set(dfil.saved_workflows())
    if base not in taken:
        return base
    i = 2
    while f'{base} ({i})' in taken:
        i += 1
    return f'{base} ({i})'


def _wf_stage_editor(draft: dict, i: int):
    """Inline editor for draft['stages'][i]. Rendered in an st.form; every
    widget key carries wf_ed_nonce so re-opening seeds fresh from the stage
    (same trick as _apply_preset's re-seed marker)."""
    n = st.session_state['wf_ed_nonce']
    stg = draft['stages'][i]
    existing_sel = dict(stg.get('selections', {}))
    carried_custom = {k: v for k, v in existing_sel.items()
                      if isinstance(v, (list, tuple)) and v and v[0] == 'custom'}
    adv0 = dict(stg.get('advanced', {}))
    carried_adv = {k: v for k, v in adv0.items() if k not in _WF_EXPOSED_ADV}

    with st.form(f'wf_editor_{n}', border=True):
        st.markdown(f'**✎ Edit stage {i + 1}**')
        e1, e2 = st.columns(2)
        name = e1.text_input('Stage name', value=stg['name'],
                             key=f'wfe{n}_name')
        src_opts = ['universe'] + [s['name'] for s in draft['stages'][:i]]
        cur_src = stg.get('source', 'universe')
        src = e2.selectbox('Input from', src_opts,
                           index=src_opts.index(cur_src)
                           if cur_src in src_opts else 0,
                           key=f'wfe{n}_src',
                           help='the full universe, or an earlier stage')
        fin = st.checkbox('★ this stage contributes to the Focus List',
                          value=bool(stg.get('focus_input')), key=f'wfe{n}_fin')
        note = st.text_area('Note / rationale', value=stg.get('note', ''),
                            key=f'wfe{n}_note', height=68)

        if carried_custom:
            st.caption('custom ranges kept as-is: ' + ', '.join(
                f'{dfil.SPEC_BY_KEY[k][0]} {v[1]:g}–{v[2]:g}'
                for k, v in carried_custom.items()))

        st.markdown('**Stage filter** — same grid as the Screener tab')
        match = st.radio(
            'Combine the filters below with', ['all (AND)', 'any (OR)'],
            index=1 if stg.get('match') == 'any' else 0,
            key=f'wfe{n}_match', horizontal=True,
            help='“any (OR)” lets one stage express a union — e.g. Ollie’s '
                 '1M / 3M / 6M momentum scans')
        new_sel = {}
        grid = st.columns(4)
        for j, (fkey, flabel, _col, fam) in enumerate(dfil.FILTER_SPECS):
            opts = [lbl for lbl, _ in dfil.THRESHOLD_FAMILIES[fam]]
            cur = existing_sel.get(fkey, 'All')
            cur = cur if cur in opts else 'All'
            pick = grid[j % 4].selectbox(flabel, opts,
                                         index=opts.index(cur),
                                         key=f'wfe{n}_f_{fkey}')
            if pick != 'All':
                new_sel[fkey] = pick

        with st.expander('Advanced', expanded=bool(adv0)):
            a_lead = st.multiselect(
                'Leaders lists', ['minervini', 'canslim', 'scooter', 'cantata'],
                default=adv0.get('adv_leaders', []), key=f'wfe{n}_lead')
            a_mode = st.radio(
                'Combine leaders', ['Any (union)', 'All (intersection)'],
                index=0 if adv0.get('adv_leaders_mode', 'Any (union)'
                                    ).startswith('Any') else 1,
                key=f'wfe{n}_mode', horizontal=True)
            a_stg = st.multiselect(
                'Weinstein stage', ['1', '2A', '2B', '2C', '3', '4'],
                default=adv0.get('adv_stages', []), key=f'wfe{n}_stg')
            a_rti = st.multiselect(
                'RTI zone', ['1', '2', '3'],
                default=adv0.get('adv_rti_zone', []), key=f'wfe{n}_rti')
            a_ext = st.slider(
                'max ext (ATR, 21EMA & 40SMA; 10 = off)', -5.0, 10.0,
                value=float(adv0.get('adv_max_ext', 10.0)), step=0.5,
                key=f'wfe{n}_ext')
            e1, e2 = st.columns(2)
            a_ext21 = e1.slider('max ext vs 21 EMA (ATR; 10 = off)', -5.0, 10.0,
                                value=float(adv0.get('adv_max_ext21', 10.0)),
                                step=0.5, key=f'wfe{n}_ext21')
            a_ext50 = e2.slider('max ext vs 50 SMA (ATR; 10 = off)', -5.0, 10.0,
                                value=float(adv0.get('adv_max_ext50', 10.0)),
                                step=0.5, key=f'wfe{n}_ext50')
            fcols = st.columns(3)
            a_flags = {}
            for k, (fk, fl) in enumerate(WF_EDITOR_FLAGS.items()):
                a_flags[fk] = fcols[k % 3].checkbox(
                    fl, value=bool(adv0.get(fk)), key=f'wfe{n}_{fk}')
            if carried_adv:
                st.caption('other advanced keys kept from the JSON: '
                           + ', '.join(carried_adv))

        c_apply, c_cancel = st.columns(2)
        applied = c_apply.form_submit_button('Apply stage', type='primary')
        cancelled = c_cancel.form_submit_button('Cancel')

    if cancelled:
        st.session_state['wf_edit_idx'] = -1
        st.session_state['wf_ed_nonce'] += 1
        st.rerun()
    if applied:
        new_sel.update(carried_custom)
        new_adv = dict(carried_adv)
        if a_lead:
            new_adv['adv_leaders'] = a_lead
            new_adv['adv_leaders_mode'] = a_mode
        if a_stg:
            new_adv['adv_stages'] = a_stg
        if a_rti:
            new_adv['adv_rti_zone'] = a_rti
        if a_ext < 10.0:
            new_adv['adv_max_ext'] = a_ext
        if a_ext21 < 10.0:
            new_adv['adv_max_ext21'] = a_ext21
        if a_ext50 < 10.0:
            new_adv['adv_max_ext50'] = a_ext50
        for fk, v in a_flags.items():
            if v:
                new_adv[fk] = True
        stg2 = {'name': name.strip() or stg['name'], 'source': src,
                'note': note.strip()}
        if match.startswith('any') and len(new_sel) > 1:
            stg2['match'] = 'any'
        if new_sel:
            stg2['selections'] = new_sel
        if new_adv:
            stg2['advanced'] = new_adv
        if fin:
            stg2['focus_input'] = True
        draft['stages'][i] = stg2
        st.session_state['wf_edit_idx'] = -1
        st.session_state['wf_ed_nonce'] += 1
        st.rerun()


def _wf_cb_edit():
    """on_click: open the selected workflow for editing (built-ins as a
    copy). Widget-keyed state (wf_selected) can only be written from a
    callback — it runs before the widgets re-instantiate."""
    name = st.session_state.get('wf_selected')
    src = dfil.load_workflow(name) or {'name': name, 'stages': []}
    if dfil.is_builtin_workflow(name):
        src['name'] = _wf_unique_workflow_name(f'{name} (mine)')
    _wf_open_draft(src)


def _wf_cb_new():
    _wf_open_draft({
        'name': _wf_unique_workflow_name('New workflow'), 'description': '',
        'stages': [{'name': 'Stage 1', 'source': 'universe'}], 'checklist': []})


def _wf_open_draft(src: dict):
    """Seed the build-view state for `src` — the name/checklist editor keys
    are seeded here (from a callback) so the widgets can omit value= and
    just persist their own edits afterwards."""
    st.session_state['wf_draft'] = src
    st.session_state['wf_edit_idx'] = -1
    st.session_state['wf_save_name'] = src.get('name', '')
    st.session_state['wf_cl_edit'] = '\n'.join(src.get('checklist', []))


def _wf_cb_delete():
    name = st.session_state.get('wf_selected')
    if name and not dfil.is_builtin_workflow(name):
        dfil.delete_workflow(name)
        st.session_state.pop('wf_selected', None)
        st.session_state['wf_flash'] = f'deleted workflow {name}'


def _wf_cb_discard():
    st.session_state['wf_draft'] = None


def _wf_cb_save():
    draft = st.session_state.get('wf_draft')
    if not draft:
        return
    name = (st.session_state.get('wf_save_name') or '').strip()
    if not name:
        st.session_state['wf_error'] = 'workflow name is required'
        return
    draft['checklist'] = [ln.strip() for ln
                          in (st.session_state.get('wf_cl_edit') or '')
                          .splitlines() if ln.strip()]
    errs = wf_engine.validate_workflow(draft)
    if dfil.is_builtin_workflow(name):
        errs.append('name collides with a built-in — pick another')
    if errs:
        st.session_state['wf_error'] = ' • '.join(errs)
        return
    dfil.save_workflow(name, draft)
    st.session_state['wf_draft'] = None
    st.session_state['wf_selected'] = name
    st.session_state['wf_flash'] = f'saved my_workflows/{name}.json'


if ACTIVE_TAB == 'workflows':
    st.session_state.setdefault('wf_draft', None)
    st.session_state.setdefault('wf_edit_idx', -1)
    st.session_state.setdefault('wf_ed_nonce', 0)

    _bi = list(dfil.builtin_workflows())
    _saved = dfil.saved_workflows()
    wf_names = _bi + [s for s in _saved if s not in _bi]

    # one path in, one path out: the tab shows the selected workflow's run;
    # ✎ Edit / Duplicate or ＋ New opens the builder (a draft exists), and
    # 💾 Save / Discard closes it again — no separate view switch
    draft = st.session_state.get('wf_draft')
    wf_sel = st.session_state.get('wf_selected') or wf_names[0]
    if wf_sel not in wf_names:
        wf_sel = st.session_state['wf_selected'] = wf_names[0]
    is_bi = dfil.is_builtin_workflow(wf_sel)
    if draft is None:
        tw1, tw2, tw3, tw4, _tw5 = st.columns([3, 1.1, 0.7, 0.8, 1.6],
                                              vertical_alignment='bottom')
        wf_sel = tw1.selectbox('Workflow', wf_names, key='wf_selected')
        is_bi = dfil.is_builtin_workflow(wf_sel)
        tw2.button('✎ Edit / Duplicate', key='wf_edit_btn',
                   on_click=_wf_cb_edit,
                   help='built-ins open as an editable copy')
        tw3.button('＋ New', key='wf_new_btn', on_click=_wf_cb_new)
        tw4.button('🗑 Delete', key='wf_del_btn', on_click=_wf_cb_delete,
                   disabled=is_bi or wf_sel not in _saved,
                   help='saved workflows only')
    else:
        st.session_state.setdefault('wf_save_name', draft.get('name', ''))
        with st.container(border=True):
            ev1, ev2, ev3, _ev4 = st.columns([3, 1.1, 1, 1.4],
                                             vertical_alignment='bottom')
            ev1.text_input('✎ Editing — workflow name', key='wf_save_name')
            ev2.button('💾 Save workflow', type='primary', key='wf_save_btn',
                       on_click=_wf_cb_save)
            ev3.button('Discard changes', key='wf_discard',
                       on_click=_wf_cb_discard)
    _flash = st.session_state.pop('wf_flash', None)
    if _flash:
        st.success(_flash)
    _wf_err = st.session_state.pop('wf_error', None)
    if _wf_err:
        st.error(_wf_err)

    st.caption(f'data as of `{run.name}` · read-only — press '
               '“Re-run screeners” at the top to refresh the underlying data. '
               'A workflow is a **sequential funnel**; for “how many methods '
               'agree on a name” use the Confluence tab.')
    st.divider()

    # ---------------------------------------------------------- RUN VIEW ----
    if draft is None:
        wf = dfil.load_workflow(wf_sel)
        if is_bi:
            st.caption('🔒 built-in — click **✎ Edit / Duplicate** to change '
                       'the stages or the checklist.')
        res = None
        try:
            res = wf_engine.run_workflow(full, wf, IDX_MAP)
        except Exception as e:                                  # noqa: BLE001
            st.error(f'workflow could not run: {e}')
        if res is not None:
            if wf.get('description'):
                st.caption(_wf_md(wf['description']))
            for i, (sr, sd) in enumerate(zip(res.stages, wf['stages'])):
                with st.container(border=True):
                    h1, h2 = st.columns([5, 1])
                    star = ' ★ feeds Focus List' if sr.focus_input else ''
                    src_lbl = ('full universe' if sr.source == 'universe'
                               else f'Stage — {sr.source}')
                    h1.markdown(f"**{i + 1}. {sr.name}**{star}")
                    h1.caption(_wf_md(f'from: {src_lbl}  ·  '
                                     f'{wf_engine.stage_summary(sd)}'))
                    if sr.note:
                        h1.caption(_wf_md(f'✎ {sr.note}'))
                    h2.markdown(f"`{sr.n_in:,} → `**`{sr.n_out:,}`**")
                    with st.expander(f'show table ({sr.n_out})'):
                        _cols = [c for c in WF_STEP_COLS if c in sr.frame.columns]
                        st.dataframe(sr.frame[_cols].round(2),
                                     use_container_width=True,
                                     height=min(90 + 32 * max(1, len(sr.frame)),
                                                420))
                        if sr.n_out:
                            _stem = dfil._safe(f'{wf_sel}_{sr.name}')
                            sc1, sc2, _sc3 = st.columns([1, 1, 2])
                            sc1.download_button(
                                '⭳ CSV', sr.frame.round(3).to_csv().encode(),
                                file_name=f'{_stem}_{run.name}.csv',
                                key=f'wf_stage_csv_{i}')
                            sc2.download_button(
                                '⭳ TradingView .txt',
                                _tv_txt(sr.frame, f'{wf_sel} · {sr.name}'),
                                file_name=f'{_stem}_{run.name}.txt',
                                mime='text/plain', key=f'wf_stage_tv_{i}',
                                help=_TV_HELP)

            st.subheader(f'📋 Focus List — {len(res.focus):,} names')
            if len(res.focus):
                _fc = [c for c in WF_STEP_COLS if c in res.focus.columns]
                ftab = res.focus[_fc].round(2).copy()
                fcfg = None
                if len(ftab) <= 200:
                    ftab.insert(1, 'spark',
                                [_spark_closes(t, run.name) for t in ftab.index])
                    fcfg = {'spark': st.column_config.LineChartColumn(
                        '120d', width=140)}
                st.dataframe(ftab, use_container_width=True, column_config=fcfg,
                             height=min(120 + 34 * max(1, len(ftab)), 640))
                fa1, fa2, _fa3 = st.columns([1, 1, 2])
                fa1.download_button(
                    'Download CSV', res.focus.round(3).to_csv().encode(),
                    file_name=f'workflow_focus_{run.name}.csv',
                    key='wf_focus_csv')
                fa1.download_button(
                    '⭳ TradingView .txt',
                    _tv_txt(res.focus, f'{wf_sel} — Focus'),
                    file_name=f'{dfil._safe(wf_sel)}_focus_{run.name}.txt',
                    mime='text/plain', key='wf_focus_tv', help=_TV_HELP)
                _ln = fa2.text_input('List name', key='wf_focus_ln',
                                     placeholder='list name…')
                if fa2.button('Save as list', key='wf_focus_save',
                              disabled=not _ln.strip()):
                    dfil.save_list(_ln.strip(), res.focus.index)
                    st.success(f'saved {len(res.focus)} tickers to '
                               f'my_lists/{_ln.strip()}.csv')
            else:
                st.info('No names survived this workflow in the latest run.')

            if res.checklist:
                st.subheader('✅ Manual checklist')
                st.caption('Not computed — needs pre-market / catalyst / '
                           'breadth data. Confirm each before an entry.')
                for ci, item in enumerate(res.checklist):
                    st.checkbox(item, key=f'wf_cl_{wf_sel}_{ci}')

    # -------------------------------------------------------- BUILD VIEW ----
    else:
        if dfil.is_builtin_workflow(wf_sel) and draft.get('name') != wf_sel:
            st.caption('✎ editing a **copy** of the built-in — it will be '
                       'saved as a new workflow.')
        st.markdown(f"**{len(draft['stages'])} stage(s)**")

        dbyname = {}
        try:
            dbyname = wf_engine.run_workflow(full, draft, IDX_MAP).by_name
        except Exception as e:                              # noqa: BLE001
            st.warning(f'draft not fully runnable yet: {e}')

        for i, stg in enumerate(draft['stages']):
            r1, r2, r3 = st.columns([4, 1.4, 3])
            fin = ' ★' if stg.get('focus_input') else ''
            r1.markdown(f"**{i + 1}. {stg['name']}**{fin}")
            r1.caption(_wf_md(f"from: {stg.get('source', 'universe')}"
                         f"  ·  {wf_engine.stage_summary(stg)}"))
            _sr = dbyname.get(stg['name'])
            r2.markdown(f"`{_sr.n_in:,}→{_sr.n_out:,}`" if _sr else '`—`')
            bc = r3.columns(5)
            if bc[0].button('↑', key=f'wf_up_{i}', disabled=i == 0):
                draft['stages'][i - 1], draft['stages'][i] = \
                    draft['stages'][i], draft['stages'][i - 1]
                st.session_state['wf_edit_idx'] = -1
                st.rerun()
            if bc[1].button('↓', key=f'wf_dn_{i}',
                            disabled=i == len(draft['stages']) - 1):
                draft['stages'][i + 1], draft['stages'][i] = \
                    draft['stages'][i], draft['stages'][i + 1]
                st.session_state['wf_edit_idx'] = -1
                st.rerun()
            if bc[2].button('✎', key=f'wf_edit_{i}',
                            help='edit this stage'):
                st.session_state['wf_edit_idx'] = i
                st.session_state['wf_ed_nonce'] += 1
                st.rerun()
            if bc[3].button('⧉', key=f'wf_dupe_{i}',
                            help='duplicate this stage'):
                import copy as _copy
                ns = _copy.deepcopy(stg)
                ns['name'] = _wf_unique_stage_name(
                    ns['name'] + ' copy', draft)
                ns['focus_input'] = False
                draft['stages'].insert(i + 1, ns)
                st.session_state['wf_edit_idx'] = -1
                st.rerun()
            if bc[4].button('🗑', key=f'wf_dropstg_{i}',
                            disabled=len(draft['stages']) == 1,
                            help='delete this stage'):
                draft['stages'].pop(i)
                st.session_state['wf_edit_idx'] = -1
                st.rerun()
            if st.session_state.get('wf_edit_idx') == i:
                _wf_stage_editor(draft, i)

        if st.button('＋ Add stage', key='wf_add_stage'):
            draft['stages'].append(
                {'name': _wf_unique_stage_name(
                    f'Stage {len(draft["stages"]) + 1}', draft),
                 'source': 'universe'})
            st.session_state['wf_edit_idx'] = len(draft['stages']) - 1
            st.session_state['wf_ed_nonce'] += 1
            st.rerun()

        st.divider()
        st.session_state.setdefault(
            'wf_cl_edit', '\n'.join(draft.get('checklist', [])))
        st.text_area('Checklist — one item per line', key='wf_cl_edit',
                     height=150)

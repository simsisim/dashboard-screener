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
from src.timing import atr1_cloud, drwish_dots, pvb  # noqa: E402
from src.patterns import cup_handle, cup_handle_chart, glb  # noqa: E402
from src.focus import volume_records  # noqa: E402
from src import leader_map  # noqa: E402

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

# Tab bar = a horizontal radio, not st.tabs: st.tabs keeps the selected tab
# only in the browser, so a rerun that reshapes the page (e.g. the first
# Combine-screens pick) snapped back to the first tab. The radio's value is
# server-side session state, and only the active section is built per rerun.
TABS = {
    'leaders': '🏆 Leaders’ Lists',
    'all': '🔎 Screener',
    'volume': '🔊 Volume Records',
    'focus': '🎯 Focus List',
    'confluence': '🎖️ Confluence',
    'timing': '🕐 Timing Signals',
    'patterns': '🌊 Patterns',
    'workflows': '🧭 Workflows',
    'detail': '📋 Ticker detail',
    'leadermap': '📍 Where is each leader?',
}
# Only the active section's widgets are drawn, and Streamlit drops the state
# of any keyed widget not drawn in a run — so switching tabs would wipe e.g.
# the Screener filters. Re-assigning each value to itself turns it into
# plain session state, which survives. Buttons, uploads, downloads and table
# selections can't be written via session_state, so they are skipped.
_NO_PERSIST = {'results_sel', 'cf_sel', 'comb_clear', 'comb2_clear',
               'lists_uploader',
               'ts_run', 'pt_run',
               'wf_edit_btn', 'wf_new_btn', 'wf_del_btn', 'del_screener',
               'cf_save_sel', 'cf_save_top', 'ts_save_list', 'pt_save_list',
               'vr_save_list', 'lm_run', 'lm_upload',
               'save_upload', 'del_list', 'wf_add_stage', 'wf_save_btn',
               'wf_discard', 'wf_focus_save', 'wf_focus_csv', 'wf_focus_tv'}
_NO_PERSIST_PREFIX = ('FormSubmitter:', 'wf_up_', 'wf_dn_', 'wf_edit_',
                      'wf_dupe_', 'wf_dropstg_', 'lead_tv_', 'wf_stage_csv_',
                      'wf_stage_tv_', 'lm_setups_')
for _k in list(st.session_state.keys()):
    if _k not in _NO_PERSIST and not _k.startswith(_NO_PERSIST_PREFIX):
        st.session_state[_k] = st.session_state[_k]

ACTIVE_TAB = st.radio('Section', list(TABS), format_func=TABS.get,
                      horizontal=True, key='active_tab',
                      label_visibility='collapsed')
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
    for k in [k for k in st.session_state
              if str(k).startswith(('comb_inc_', 'comb_exc_',
                                    'comb2_inc_', 'comb2_exc_'))]:
        st.session_state[k] = []
    for k, default in {'search': '', 'my_list_sel': '— None Selected —',
                       'apply_upload': False,
                       'preset_sel': '— None Selected —',
                       'my_screener_sel': '— None Selected —',
                       '_applied_preset': '— None Selected —',
                       '_applied_screener': '— None Selected —',
                       'save_as_name': '', 'save_list_name': '',
                       'comb_mode': 'All (AND)', 'comb2_mode': 'All (AND)',
                       'comb_levels': 'Funnel',
                       '_flash': ''}.items():
        st.session_state[k] = default


_init_filter_state()

if ACTIVE_TAB == 'all':
    _how_built('ℹ️ How the Screener is built', [
        _universe_line(),
        'Every screen, preset and filter below narrows this universe. '
        'Combine level 2 is optional: in <b>Funnel</b> mode it only screens '
        'level 1’s survivors (level 1 AND level 2 — e.g. leaders with All '
        '(AND), then Tight / not-extended with Any (OR)); in <b>Merge</b> mode '
        'both levels screen the whole universe and are joined (level 1 OR '
        'level 2). The Filters panel is ANDed on top of the result',
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
    comb_levels = st.radio(
        'Connect level 1 and level 2', ['Funnel', 'Merge'], key='comb_levels',
        horizontal=True,
        help='Funnel: level 2 only screens the tickers that survived level 1 '
             '(level 1 AND level 2). Merge: both levels screen the whole '
             'universe and their results are joined (level 1 OR level 2).')

    def _combine_level(p: str, n_pick: int, n_comb: int, level_label: str,
                       within: pd.Series | None = None):
        """One Pick + Combine block; `p` is the session-state key prefix
        ('comb' = level 1, 'comb2' = level 2). `within` (level 1's result,
        Funnel mode) restricts the mask AND every per-screen count to the
        tickers that survived the previous level. Chip picker like the
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

    comb_mask, comb_hits, _lvl1_on = _combine_level('comb', 1, 2, '')
    # Funnel: level 2 screens only level 1's survivors (e.g. leaders
    # intersected, then Tight OR not-extended within them). Merge: both
    # levels screen the whole universe and the results are ORed.
    _funnel = comb_levels == 'Funnel'
    _within = comb_mask if (_funnel and _lvl1_on) else None
    if _within is not None:
        _l2_label = f' — within the {int(comb_mask.sum())} tickers from level 1'
    else:
        _l2_label = ' — level 2' + ('' if _funnel else ' (merged with level 1)')
    comb2_mask, comb2_hits, _lvl2_on = _combine_level(
        'comb2', 3, 4, _l2_label, within=_within)
    if _lvl2_on:
        if not _lvl1_on:
            comb_mask = comb2_mask         # an empty level 1 is all-True
        elif _funnel:
            comb_mask = comb2_mask         # already restricted to level 1
        else:
            comb_mask = comb_mask | comb2_mask
        # a screen picked in both levels has the same mask — keep one column
        comb_hits = pd.concat(
            [comb_hits, comb2_hits.loc[:, ~comb2_hits.columns.isin(comb_hits.columns)]],
            axis=1)
        if _lvl1_on:
            _op = 'AND' if _funnel else 'OR'
            st.markdown(f'**Combine 1 {_op} Combine 2** → '
                        f'**{int(comb_mask.sum())}** tickers '
                        '(before the Filters panel)')
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
        a5.slider('max ext (ATR, 21EMA & 40SMA)', -5.0, 10.0, key='adv_max_ext', step=0.5,
                  help='10.0 = off')
        a6.slider('RS % ≥', 0.0, 100.0, key='adv_min_rs', step=1.0)
        a7.slider('Minervini count ≥', 0, 8, key='adv_min_count')
        a8.multiselect('Exchange', sorted(full['exchange'].dropna().unique()),
                       key='adv_exchange')
        a9x, a9y, _a9z, _a9w = st.columns(4)
        a9x.slider('max ext vs 21 EMA (ATR)', -5.0, 10.0, key='adv_max_ext21',
                   step=0.5, help='Ollie: 3. 10.0 = off')
        a9y.slider('max ext vs 50 SMA (ATR)', -5.0, 10.0, key='adv_max_ext50',
                   step=0.5, help='Ollie: 5. 10.0 = off')
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
        a24, a25, a26, a27 = st.columns(4)
        a24.checkbox('CANTATA CE leader', key='adv_cantata',
                     help=f'in_cantata: CE >= {config.CANTATA_MIN_CE} of 18')
        a25.slider('CANTATA CE ≥', 0.0, 18.0, key='adv_ce_min', step=0.5,
                   help='0 = off; CET(0-7) + CEF(0-11)')
        a26.checkbox('21dma-structure pullback', key='adv_21dma_pullback',
                     help=f'trend up + close within ±{config.MA21S_PULLBACK_PCT:g}% '
                          'of the EMA21 high/low band (PrimeTrading script)')
        a27.multiselect('21dma-structure zone',
                        ['extended', 'above', 'inside', 'undercut', 'below'],
                        key='adv_ma21s_zone',
                        help='close vs the band: above/undercut = within '
                             f'{config.MA21S_PULLBACK_PCT:g}% of it; empty = all')
        a28, a29, _a30, _a31 = st.columns(4)
        a28.multiselect('21dma-structure trend', ['up', 'down'],
                        key='adv_ma21s_trend', help='empty = all')
        with a29:
            _thresh_widget('ma21s_dist')
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
        v5, v6, _v7, _v8 = st.columns(4)
        with v5:
            _thresh_widget('hve_since')
        with v6:
            _thresh_widget('hv1y_since')

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

    # threshold grid + the whole Advanced panel (sector/industry included) —
    # build_advanced_mask is the single source of truth, shared with the
    # Workflows tab engine (src/workflow.py); feedback: workflows_tab.md §4
    mask = dfil.build_mask(full, selections)
    mask &= dfil.build_advanced_mask(
        full, {k: st.session_state[k] for k in dfil.ADVANCED_DEFAULTS}, IDX_MAP)
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
    active_name = (preset_sel if preset_sel != '— None Selected —'
                   else (screener_sel if screener_sel != '— None Selected —'
                         else 'Custom'))
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
                       file_name=f'filtered_{run.name}.csv')
    d1.download_button('⭳ TradingView .txt (all)',
                       _tv_txt(result, f'Filtered — {run.name}'),
                       file_name=f'filtered_{run.name}.txt',
                       mime='text/plain', help=_TV_HELP)
    if selected_tickers:
        d1.download_button('Download CSV (selected)',
                           result.loc[selected_tickers].round(3).to_csv().encode(),
                           file_name=f'selected_{run.name}.csv')
        d1.download_button('⭳ TradingView .txt (selected)',
                           _tv_txt(result.loc[selected_tickers],
                                   f'Selected — {run.name}'),
                           file_name=f'selected_{run.name}.txt',
                           mime='text/plain', help=_TV_HELP)
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
        '<b>vs prior</b> = how far (%) the day beat the record before it '
        '(HVE) or the highest of the year before it (HV1Y). <b>HVE records</b> '
        '= how many all-time records the ticker set inside the window',
    ])
    _st = volume_records.read_status()
    if not _st or not _st.get('bar_dates') or 'hv1y_bars_since' not in full:
        st.warning('No HVE ledger / HV1Y columns yet — re-run the screeners.')
        st.stop()

    for _k, _v in {'vr_inc': ['HVE'], 'vr_exc': [], 'vr_pick_as': 'Include',
                   'vr_mode': 'All (AND)', 'vr_excl_funds': True}.items():
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
                         '(before the Filters below)')
            if len(vr_inc) == 2:
                cc1.caption('Every HVE is also an HV1Y (an all-time record '
                            'also beats the past year), so AND gives the HVE '
                            'list and OR the HV1Y list. To see 1-year volume '
                            'highs that are NOT all-time records: Include '
                            'HV1Y + Exclude HVE.')

    # ---- 3 Filters
    st.markdown('**3&nbsp;&nbsp;Filters**')
    with st.container(border=True):
        f1, f2, f3, f4 = st.columns(4)
        _opts = {fam: dict(dfil.THRESHOLD_FAMILIES[fam])
                 for fam in ('mktcap', 'price', 'adv_dollar')}
        vr_cap = f1.selectbox('Market cap', list(_opts['mktcap']),
                              key='vr_mktcap')
        vr_price = f2.selectbox('Last closing price', list(_opts['price']),
                                key='vr_price')
        vr_adv = f3.selectbox('50d Av. Dollar Volume (ADV)',
                              list(_opts['adv_dollar']), key='vr_adv')
        vr_min_vs = f4.number_input('vs prior ≥ (%)', 0.0, 1000.0, 0.0, 5.0,
                                    key='vr_min_vs_prior',
                                    help='best of the matched screens; 0 = off')
        f5, f6, f7 = st.columns([1.5, 1.5, 1])
        vr_idx = f5.multiselect('Index membership (empty = whole universe)',
                                index_choices(), key='vr_index')
        vr_sec = f6.multiselect('Sector', sorted(full['sector'].dropna().unique()),
                                key='vr_sector')
        vr_nofunds = f7.checkbox('Exclude funds (Investment trusts)',
                                 key='vr_excl_funds',
                                 help='closed-end / muni funds: their volume '
                                      'spikes are fund events, not accumulation')

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
        for c in ('hv1y_date', 'hv1y_bars_since', 'hv1y_vs_prior_pct'):
            tbl[c] = base[c]
        ctx_cols = ['close', 'gain_5d', 'gain_1m', 'rel_volume_today', 'stage',
                    'rs_pct', 'ext_21ema_atr', 'adr20_pct', 'adv50_dollar',
                    'market_cap', 'sector', 'industry', 'exchange']
        tbl = tbl.join(base[[c for c in ctx_cols if c in base.columns]])

        # filters
        keep = pd.Series(True, index=tbl.index)
        for col, sel, fam in (('market_cap', vr_cap, 'mktcap'),
                              ('close', vr_price, 'price'),
                              ('adv50_dollar', vr_adv, 'adv_dollar')):
            rng = _opts[fam][sel]
            if rng is not None:
                keep &= tbl[col].notna() & (tbl[col] >= rng[0])
        _vs = pd.concat([tbl['hve_vs_prior_pct'].where(_hits['HVE'])
                         if 'HVE' in _hits else None,
                         tbl['hv1y_vs_prior_pct'].where(_hits['HV1Y'])
                         if 'HV1Y' in _hits else None], axis=1).max(axis=1)
        if vr_min_vs > 0:
            keep &= _vs >= vr_min_vs
        if vr_idx:
            _sel = set(vr_idx)
            keep &= np.array([bool(IDX_MAP.get(str(t).upper(), frozenset())
                                   & _sel) for t in tbl.index])
        if vr_sec:
            keep &= tbl['sector'].isin(vr_sec)
        if vr_nofunds:
            keep &= tbl['industry'] != 'Investment trusts'
        _recent = pd.concat([tbl['hve_bars_since'].where(_hits['HVE'])
                             if 'HVE' in _hits else None,
                             tbl['hv1y_bars_since'].where(_hits['HV1Y'])
                             if 'HV1Y' in _hits else None], axis=1).min(axis=1)
        tbl = (tbl.assign(_recent=_recent, _vs=_vs)[keep]
               .sort_values(['_recent', '_vs'], ascending=[True, False])
               .drop(columns=['_recent', '_vs']))
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
        st.dataframe(show, use_container_width=True,
                     height=min(120 + 35 * len(show), 700),
                     column_config={'spark': st.column_config.LineChartColumn(
                         '120d', width=170)})
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
# On-demand pattern/timing badges are merged opportunistically from today's
# cache when the Patterns/Timing tabs have already produced it.
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


if ACTIVE_TAB == 'confluence':
    st.caption('Badge-count leaders — the names lit up by the most independent '
               'method *families*. Pure aggregation over the latest daily run '
               f'(`{run.name}`); press "Re-run screeners" above to refresh. '
               'Pattern/timing badges (DB, C&H, PVB, ATR1, dots) appear only '
               'when the Patterns/Timing tabs have been run today.')

    cf1, cf2, cf3 = st.columns([3, 2, 2])
    cf_indexes = cf1.multiselect('Scope: index membership', index_choices(),
                                 key='cf_index',
                                 help='empty = whole universe')
    cf_cap = cf2.select_slider('Min market cap',
                               options=[0, 300e6, 1e9, 2e9, 10e9], value=0,
                               key='cf_cap', format_func=lambda v: f'${v:,.0f}')
    cf_rank = cf3.selectbox('Rank by', ['n_families', 'n_badges',
                                        'confluence_score'], key='cf_rank')
    cf4, cf5, cf6 = st.columns([2, 2, 2])
    cf_minfam = cf4.slider('Min families', 0, len(confluence.FAMILIES), 3,
                           key='cf_minfam')
    cf_must = cf5.multiselect('Must include family', confluence.FAMILIES,
                              key='cf_must')
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
if ACTIVE_TAB == 'detail':
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


if ACTIVE_TAB == 'timing':
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
        d1.download_button('⭳ TradingView .txt',
                           _tv_txt(view, f'Timing · {ts_key}'),
                           file_name=f'timing_signals_{ts_key}_{run.name}.txt',
                           mime='text/plain', help=_TV_HELP)
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

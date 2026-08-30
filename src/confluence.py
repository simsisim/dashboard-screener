"""
Confluence — badge-count leaders (IMPLEMENTATION_PLAN.md §19).

Invert every always-on screener to per-ticker: the names lit up by the most
*independent* method families are the ones "in the strike zone". This is a
union with a membership-count sort, NOT an intersection (an intersection of
~20 screeners returns nothing).

Pure aggregation over the daily batch's screener_results.csv (the dashboard's
`full` DataFrame) — nothing here runs a screener or reads a bar file. The
expensive on-demand pattern/timing signals (GLB, Cup & Handle, PVB, ATR1,
Dr-Wish dots) are merged *opportunistically* by the dashboard from today's
cache via `merge_ondemand()`; when a cache file is absent the badge is just
left unlit.

Ranking key: **n_families**, not n_badges — MM / KQ / GLP / GMMA-bullish /
RS90 / SC all fundamentally need strong RS + stacked MAs + an uptrend, so a
raw badge count rewards one idea wearing six hats.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# family -> card-pill colour; dict order also fixes the family (and score) order
FAMILY_COLORS = {
    'trend_rs':     '#eab308',   # amber   — trend / RS leadership
    'fundamentals': '#3b82f6',   # blue    — earnings / sponsorship
    'accumulation': '#14b8a6',   # teal    — volume / distribution-vs-accumulation
    'breakout':     '#22c55e',   # green   — base breakout structure
    'pullback':     '#a855f7',   # purple  — re-entry into an existing trend
    'timing':       '#f97316',   # orange  — on-demand daily trigger
}
FAMILIES = list(FAMILY_COLORS)

# on-demand badges — not in the daily batch; merge_ondemand() supplies them
ONDEMAND_CODES = {'DB', 'C&H', 'PVB', 'ATR1', 'blue', 'black'}
# code -> the `in_*` column its test reads (so merge_ondemand can inject it)
_ONDEMAND_COL = {
    'DB': 'in_glb_breakout', 'C&H': 'in_cup_handle',
    'PVB': 'in_pvb_buy', 'ATR1': 'in_atr1_uptrend',
    'blue': 'in_blue_dot', 'black': 'in_black_dot',
}


# --------------------------------------------------------------- tests ----
def _flag(col):
    """A boolean column; absent -> all-False."""
    def t(full):
        if col in full.columns:
            return full[col].fillna(False).astype(bool)
        return pd.Series(False, index=full.index)
    return t


def _ge(col, thr):
    def t(full):
        if col not in full.columns:
            return pd.Series(False, index=full.index)
        return (pd.to_numeric(full[col], errors='coerce') >= thr).fillna(False)
    return t


def _eq(col, val):
    def t(full):
        if col not in full.columns:
            return pd.Series(False, index=full.index)
        return full[col].astype(str) == val
    return t


# (code, label, family, test) — list order == card render order
BADGES = [
    ('MM',    'Minervini trend template',  'trend_rs',     _flag('in_minervini')),
    ('KQ',    'Qullamaggie suite',         'trend_rs',     _flag('in_qullamaggie')),
    ('SC',    'SCOOTER / SCTR ≥ 90',   'trend_rs',     _flag('in_scooter')),
    ('GLP',   'Golden Launch Pad',         'trend_rs',     _flag('in_gold_launch_pad')),
    ('GMMA',  'GMMA bullish',              'trend_rs',     _eq('gmma_state', 'bullish')),
    ('RS90',  'RS percentile ≥ 90',    'trend_rs',     _ge('rs_pct', 90)),
    ('ON',    'CANSLIM C-A-I',             'fundamentals', _flag('in_canslim')),
    ('CE',    'CANTATA / CE leader',       'fundamentals', _flag('in_cantata')),
    ('ADL',   'ADL accumulation',          'accumulation', _flag('in_adl_accumulation')),
    ('VOL',   'Volume anomaly (3σ)',   'accumulation', _flag('in_volume_anomaly')),
    ('SB9',   'Stockbee 9M mover',         'accumulation', _flag('in_9m_movers')),
    ('SBW',   'Stockbee 20% weekly mover', 'accumulation', _flag('in_weekly_movers')),
    ('SB4',   'Stockbee 4% daily gainer',  'accumulation', _flag('in_daily_gainers')),
    ('52H',   '52-week-high breakout',     'breakout',     _flag('in_52w_high_breakout')),
    ('NrH',   'Within 5% of 52w high',     'breakout',     _ge('pct_from_52w_high', -5)),
    ('DB',    'Green-line breakout',       'breakout',     _flag('in_glb_breakout')),
    ('C&H',   'Cup & Handle',              'breakout',     _flag('in_cup_handle')),
    ('EMA20', 'EMA20 pullback test',       'pullback',     _flag('in_ema20_pullback')),
    ('REV',   'Downtrend reversal',        'pullback',     _flag('in_downtrend_reversal')),
    ('PVB',   'Price-Volume Breakout buy', 'timing',       _flag('in_pvb_buy')),
    ('ATR1',  'ATR1 cloud uptrend',        'timing',       _flag('in_atr1_uptrend')),
    ('blue',  'Dr Wish blue dot',          'timing',       _flag('in_blue_dot')),
    ('black', 'Dr Wish black dot',         'timing',       _flag('in_black_dot')),
]

BADGE_FAMILY = {code: fam for code, _l, fam, _t in BADGES}
BADGE_LABEL = {code: lbl for code, lbl, _f, _t in BADGES}
_CODES = [code for code, *_ in BADGES]

# batch (always-on) badge source columns — asserted present by the guard test
BATCH_SOURCE_COLS = sorted({
    'in_minervini', 'in_qullamaggie', 'in_scooter', 'in_gold_launch_pad',
    'gmma_state', 'rs_pct', 'in_canslim', 'in_cantata', 'in_adl_accumulation',
    'in_volume_anomaly', 'in_9m_movers', 'in_weekly_movers', 'in_daily_gainers',
    'in_52w_high_breakout', 'pct_from_52w_high', 'in_ema20_pullback',
    'in_downtrend_reversal',
})


# ------------------------------------------------------------- compute ----
def compute(full: pd.DataFrame, extra: dict | None = None) -> pd.DataFrame:
    """Aggregate the always-on screener flags into per-ticker badge counts.

    full  : screener_results.csv as loaded by the dashboard (index = ticker).
    extra : {badge_code: bool Series} of on-demand pattern/timing signals the
            dashboard pulled from today's cache (see merge_ondemand). Injected
            as the `in_*` column each badge's test reads; None / missing codes
            leave those badges unlit. Null-safe.

    Returns a copy of `full` with added columns:
      bdg_<code>        bool per badge
      badges            list[str] active codes, in registry order
      n_badges          int  (context tags excluded)
      families          list[str] families with >=1 active badge
      n_families        int   <- primary rank key
      confluence_score  float 0-100, capped at 2 badges per family
      context           list[str] stage / RTI-zone tags (never counted)
    """
    out = full.copy()

    for code, series in (extra or {}).items():
        col = _ONDEMAND_COL.get(code)
        if col is not None and series is not None:
            out[col] = (pd.Series(series).reindex(out.index)
                        .fillna(False).astype(bool))

    # boolean matrix rows x codes
    B = pd.DataFrame(
        {code: test(out).reindex(out.index).fillna(False).astype(bool)
         for code, _l, _f, test in BADGES},
        index=out.index)
    for code in _CODES:
        out[f'bdg_{code}'] = B[code]

    bvals = B.values
    out['n_badges'] = bvals.sum(axis=1).astype(int)
    out['badges'] = [[_CODES[j] for j in np.flatnonzero(r)] for r in bvals]

    fam_hit = pd.DataFrame(
        {fam: B[[c for c in _CODES if BADGE_FAMILY[c] == fam]].any(axis=1)
         for fam in FAMILIES},
        index=out.index)
    fvals = fam_hit.values
    out['n_families'] = fvals.sum(axis=1).astype(int)
    out['families'] = [[FAMILIES[j] for j in np.flatnonzero(r)] for r in fvals]

    # score: <=2 badges counted per family, normalised to 0-100
    capped = np.zeros(len(out), dtype=float)
    for fam in FAMILIES:
        fam_codes = [c for c in _CODES if BADGE_FAMILY[c] == fam]
        capped += np.minimum(B[fam_codes].values.sum(axis=1), 2)
    out['confluence_score'] = (capped / (2 * len(FAMILIES)) * 100).round(1)

    stage_s = (out['stage'].astype(str) if 'stage' in out.columns
               else pd.Series('', index=out.index))
    rti_s = (out['rti_zone'] if 'rti_zone' in out.columns
             else pd.Series(np.nan, index=out.index))
    out['context'] = [
        (['stage ' + s] if s in ('2A', '2B', '2C') else [])
        + (['RTI z' + str(z).split('.')[0]]
           if pd.notna(z) and str(z) not in ('', 'nan') else [])
        for s, z in zip(stage_s, rti_s)
    ]
    return out


def rank(df: pd.DataFrame, by: str = 'n_families') -> pd.DataFrame:
    """Sort a compute() frame, most confluent first. `by` in
    {'n_families','n_badges','confluence_score'}; ties break on the other
    two then SCOOTER/RS."""
    keys = ['n_families', 'confluence_score', 'n_badges']
    keys = [by] + [k for k in keys if k != by]
    for extra in ('scooter_score', 'rs_pct'):
        if extra in df.columns:
            keys.append(extra)
    return df.sort_values(keys, ascending=False)


# ---------------------------------------------------- opportunistic merge --
def merge_ondemand(run_dir, index) -> dict:
    """Scan today's run dir for pattern/timing caches and lift the on-demand
    badge signals out of whatever files are present (union of positives).
    Returns {badge_code: bool Series aligned to `index`} for the families a
    cache actually covers — codes with no cache file are omitted entirely
    (so the badge stays unlit rather than showing a false negative).
    """
    from pathlib import Path
    run_dir = Path(run_dir)
    index = pd.Index(index)
    extra: dict = {}
    if not run_dir.is_dir():
        return extra

    def _series(tickers):
        return pd.Series(index.isin(list(tickers)), index=index)

    glb_files = list(run_dir.glob('patterns_glb_*.csv'))
    if glb_files:
        tk = set()
        for p in glb_files:
            try:
                d = pd.read_csv(p)
            except Exception:
                continue
            cols = [c for c in d.columns if c.startswith('in_glb_breakout')]
            if cols and 'ticker' in d.columns:
                tk |= set(d.loc[d[cols].astype(bool).any(axis=1), 'ticker'])
        extra['DB'] = _series(tk)

    ch_files = list(run_dir.glob('patterns_cup_handle_*.csv'))
    if ch_files:
        tk = set()
        for p in ch_files:
            try:
                d = pd.read_csv(p)
            except Exception:
                continue
            cols = [c for c in d.columns if c.startswith('in_cup_handle_')]
            if cols and 'ticker' in d.columns:
                tk |= set(d.loc[d[cols].astype(bool).any(axis=1), 'ticker'])
        extra['C&H'] = _series(tk)

    tim_files = list(run_dir.glob('timing_signals_*.csv'))
    if tim_files:
        buckets = {'PVB': set(), 'ATR1': set(), 'blue': set(), 'black': set()}
        for p in tim_files:
            try:
                d = pd.read_csv(p)
            except Exception:
                continue
            if 'ticker' not in d.columns:
                continue
            src = d.get('source', pd.Series(index=d.index, dtype=str)).astype(str)
            st = d.get('signal_state', pd.Series(index=d.index, dtype=str)).astype(str)
            tkc = d['ticker']
            buckets['PVB'] |= set(tkc[(src == 'PVB') & (st == 'Buy')])
            buckets['ATR1'] |= set(tkc[(src == 'ATR1 Trend') & (st == 'uptrend')])
            buckets['blue'] |= set(tkc[src == 'Blue Dot'])
            buckets['black'] |= set(tkc[src == 'Black Dot'])
        for code, tk in buckets.items():
            extra[code] = _series(tk)

    return extra

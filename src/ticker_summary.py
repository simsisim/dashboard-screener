"""
Ticker summary — a readable, rule-based text for the Ticker detail tab
(TODO.md item 7). Built only from data already on disk: the screener row,
results/history.db (Confluence history, index ranks) and the fundamentals
snapshot (earnings). No new downloads, no LLM.

build() returns [(section title, [markdown lines])]; the dashboard renders
it above the full metric table. Thresholds live in config.SUMMARY_*.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config
from src import confluence

INDEX_NAMES = {'SP500': 'S&P 500', 'NASDAQ100': 'NASDAQ 100'}


# ------------------------------------------------------------- format ----
def _num(v) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if np.isnan(f) else f


def _pct(v, digits: int = 1) -> str:
    f = _num(v)
    if f is None:
        return 'n/a'
    return f'{f:+.{digits}f}%'.replace('-', '−')


def _day(d) -> str:
    """'2026-10-08' -> '10-08' this year, else the full date."""
    s = str(d)[:10]
    return s[5:] if s[:4] == str(pd.Timestamp.today().year) else s


def _codes(s) -> list:
    if not isinstance(s, str):                 # NaN: no badge that session
        return []
    return [c for c in s.split(',') if c]


def _badges(codes) -> str:
    return ', '.join(codes) if codes else 'none'


# ----------------------------------------------------------- sections ----
def price_trend(row: pd.Series) -> list:
    out = []
    moves = [f'{_pct(row.get("daily_gain_pct"))} on the day']
    for col, lbl in (('gain_5d', '5 days'), ('gain_1m', '1 month'),
                     ('gain_3m', '3 months')):
        if _num(row.get(col)) is not None:
            moves.append(f'{_pct(row.get(col))} over {lbl}')
    close = _num(row.get('close'))
    out.append(f'Close **{close:,.2f}**: ' + ', '.join(moves) + '.'
               if close is not None else ', '.join(moves) + '.')
    hi = _num(row.get('pct_from_52w_high'))
    if hi is not None:
        out.append('**At its 52-week high.**' if hi >= -0.05 else
                   f'**{abs(hi):.1f}% below** its 52-week high.')
    facts = []
    if pd.notna(row.get('stage')):
        facts.append(f'Stage **{row.get("stage")}**')
    if _num(row.get('minervini_count')) is not None:
        facts.append(f'Minervini **{int(row["minervini_count"])}/8**')
    if pd.notna(row.get('gmma_state')):
        facts.append(f'GMMA {row.get("gmma_state")}')
    if _num(row.get('rs_pct')) is not None:
        facts.append(f'RS percentile {row["rs_pct"]:.1f}')
    if _num(row.get('scooter_score')) is not None:
        facts.append(f'SCOOTER {row["scooter_score"]:.0f}')
    if facts:
        out.append(', '.join(facts) + '.')
    return out


def confluence_text(ticker: str, row: pd.Series, db) -> list:
    """Today's families/badges + how often >= SUMMARY_MIN_FAMILIES over the
    last SUMMARY_WINDOW sessions + badges gained / lost recently."""
    need, window = config.SUMMARY_MIN_FAMILIES, config.SUMMARY_WINDOW
    today = confluence.compute(row.to_frame().T.infer_objects(), None).iloc[0]
    fam_now = int(today['n_families'])
    out = []
    rows, sessions = (pd.DataFrame(), [])
    if db is not None:
        rows, sessions = db.confluence_window(window)
    hist = (rows[rows['symbol'] == ticker].set_index('snapshot_date')
            .reindex(sessions) if len(sessions) else pd.DataFrame())
    fam = (hist['n_families'].fillna(0).astype(int)
           if len(hist) else pd.Series(dtype=int))

    status = ''
    if len(fam) >= 2:
        prev = int(fam.iloc[1])
        if fam_now < need <= prev:
            status = f' — **just dropped below** the ≥ {need} filter'
        elif fam_now >= need > prev:
            status = f' — **just reached** the ≥ {need} filter'
    out.append(f'Today: **{fam_now} famil{"y" if fam_now == 1 else "ies"}** '
               f'({_badges(list(today["badges"]))}){status}.')

    if len(fam):
        n_ok = int((fam >= need).sum())
        tone = ('a steady name' if n_ok >= 0.75 * len(fam) else
                'rarely there' if n_ok <= 0.15 * len(fam) else
                'on and off')
        out.append(f'Last {len(fam)} sessions: **{n_ok} of {len(fam)}** at '
                   f'≥ {need} families — {tone}.')

        # badge changes over the last SUMMARY_BADGE_LOOKBACK sessions
        look = hist.iloc[:config.SUMMARY_BADGE_LOOKBACK]
        sets = [set(_codes(b)) for b in look['badges']]
        dates = list(look.index)
        if sets:
            gained, lost = [], []                   # (date, code), newest first
            for code in set().union(*sets):
                present = [code in s for s in sets]
                if present[0]:
                    k = 0                           # current streak start
                    while k + 1 < len(present) and present[k + 1]:
                        k += 1
                    if k + 1 < len(present):        # started inside window
                        gained.append((dates[k], code))
                else:
                    k = present.index(True)         # last day it was lit
                    lost.append((dates[k], code))
            if lost:
                out.append('Lost ' + ', '.join(
                    f'{c} after {_day(d)}' for d, c in sorted(lost)) + '.')
            if gained:
                out.append('Gained ' + ', '.join(
                    f'{c} on {_day(d)}' for d, c in sorted(gained)) + '.')
    return out


def volume_text(row: pd.Series) -> list:
    recent = config.SUMMARY_RECENT_RECORD_BARS
    out = []
    hve_bars = _num(row.get('hve_bars_since'))
    if pd.isna(row.get('hve_date')):
        out.append('No all-time volume record (HVE) on file.')
    elif hve_bars is not None and hve_bars < recent:
        nxt = (f', {_pct(row.get("hve_2nd_dch_pct"))} the next'
               if _num(row.get('hve_2nd_dch_pct')) is not None else '')
        out.append(f'**All-time volume record (HVE) {_day(row["hve_date"])}** '
                   f'({_ago(hve_bars)}){_er(row, "hve")}: price '
                   f'{_pct(row.get("hve_1st_dch_pct"))} that day{nxt}'
                   + _since(row, 'hve') + '.')
    else:
        out.append(f'No recent HVE: the all-time volume record is from '
                   f'{row["hve_date"]}.')
    hv1y = row.get('hv1y_date')
    if pd.notna(hv1y) and str(hv1y) == str(row.get('hve_date')) \
            and hve_bars is not None and hve_bars < recent:
        out.append('It is also the 1-year volume high.')
    elif pd.notna(hv1y):
        bars = _num(row.get('hv1y_bars_since'))
        ago = f' ({_ago(bars)})' if bars is not None else ''
        nxt = (f', {_pct(row.get("hv1y_2nd_dch_pct"))} the next'
               if _num(row.get('hv1y_2nd_dch_pct')) is not None else '')
        out.append(f'Last 1-year volume high: **{hv1y}**{ago}'
                   f'{_er(row, "hv1y")}. Price '
                   f'{_pct(row.get("hv1y_1st_dch_pct"))} that day{nxt}'
                   + _since(row, 'hv1y') + '.')
    return out


def _ago(bars) -> str:
    b = int(bars)
    return 'the latest session' if b == 0 else f'{b} session{"s" * (b != 1)} ago'


def _er(row: pd.Series, p: str) -> str:
    return (' — **on an earnings day**'
            if str(row.get(f'{p}_earnings')) == 'True' else '')


def _since(row: pd.Series, p: str) -> str:
    v = _num(row.get(f'{p}_since_record_pct'))
    bars = _num(row.get(f'{p}_bars_since'))
    if v is None or not bars:
        return ''
    gap = row.get(f'{p}_gap_held')
    held = ('; gap held' if str(gap) == 'True' else
            '; gap filled' if str(gap) == 'False' else '')
    return f'; {_pct(v)} since{held}'


def ranking_text(ticker: str, db) -> list:
    if db is None:
        return []
    ranks = db.ticker_ranks(ticker)
    out = []
    n = config.SUMMARY_RANK_SESSIONS
    for code, g in ranks.groupby('index_code', sort=False):
        g = g.head(n)
        if g.empty:
            continue
        size = int(g['index_size'].median())
        lo, hi = int(g['rank_top'].min()), int(g['rank_top'].max())
        third = g['rank_top'].mean() / size
        tone = ('near the top' if third <= 1 / 3 else
                'mid-pack' if third <= 2 / 3 else 'near the bottom')
        worst = g.loc[g['change_pct'].idxmin()]
        best = g.loc[g['change_pct'].idxmax()]
        out.append(f'**{INDEX_NAMES.get(code, code)}** (last {len(g)} '
                   f'sessions): {tone} — gainer rank {lo}–{hi} of ~{size}; '
                   f'best {_day(best["snapshot_date"])} '
                   f'({_pct(best["change_pct"])}), worst '
                   f'{_day(worst["snapshot_date"])} '
                   f'({_pct(worst["change_pct"])}).')
    return out or ['Not in the S&P 500 or NASDAQ 100 lists.']


def earnings_text(fin: pd.Series | None) -> list:
    if fin is None or fin.empty:
        return ['No earnings data in the fundamentals file.']
    out = []
    d = fin.get('qh1_date')
    if pd.notna(d) and str(d) not in ('N/A', 'nan'):
        eps, est = _num(fin.get('qh1_eps')), _num(fin.get('qh1_eps_estimate'))
        parts = [f'Last report **{d}**']
        if eps is not None and est is not None:
            parts.append(f'EPS {eps:.2f} vs {est:.2f} expected')
        if _num(fin.get('qh1_surprise_pct')) is not None:
            parts.append(f'{_pct(fin["qh1_surprise_pct"])} surprise')
        g = _num(fin.get('qh1_eps_growth_yoy'))
        if g is not None:
            parts.append(f'{_pct(g * 100, 0)} vs the same quarter last year')
        out.append(', '.join(parts) + '.')
    nd = fin.get('next_earnings_date')
    if pd.notna(nd) and str(nd) not in ('N/A', 'nan'):
        est = ' (estimated)' if str(fin.get('next_earnings_is_estimate')) == 'True' else ''
        out.append(f'Next report: **{nd}**{est}.')
    upd = str(fin.get('last_updated', ''))[:10]
    if upd:
        out.append(f'_Fundamentals as of {upd}._')
    return out or ['No earnings dates on file.']


# --------------------------------------------------------------- build ----
def build(ticker: str, row: pd.Series, db=None,
          fin: pd.Series | None = None) -> list:
    """[(title, [markdown lines])] — each section skipped if it has no text."""
    sections = [
        ('Price & trend', price_trend(row)),
        ('Confluence', confluence_text(ticker, row, db)),
        ('Volume records', volume_text(row)),
        ('Index ranking', ranking_text(ticker, db)),
        ('Earnings', earnings_text(fin)),
    ]
    return [(t, lines) for t, lines in sections if lines]


def to_markdown(sections: list) -> str:
    return '\n\n'.join(f'**{t}**\n' + '\n'.join(f'- {l}' for l in lines)
                       for t, lines in sections)

"""
Top movers per index — the ranked gainers/losers lists CNBC used to give
(docs/top_movers_plan.md; replaces sandBox/cnbs, which CNBC now blocks).

For every member of each index in config.MOVERS_INDEXES and every session:
  change_pct  = close / previous close - 1  (in %)
  rank_top    = 1 for the biggest gainer
  rank_bottom = 1 for the biggest loser

Unlike the other screeners this is evaluated on ALL dates, not only the
latest bar: the history is free (prices are on disk), so a backfill is one
call. A session where fewer than MOVERS_MIN_COVERAGE of the members have a
change is skipped (a hole in the download would rank a partial index).

Members come from downloadData_v1/data/tickers/<index>_tickers.csv — today's
lists, so backfilled sessions carry survivorship bias (plan, "Backfill").
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
import config

COLUMNS = ['snapshot_date', 'index_code', 'symbol', 'change_pct',
           'rank_top', 'rank_bottom']


def load_members() -> dict:
    """{index_code: sorted list of tickers} from the downloadData_v1 lists."""
    members = {}
    for code, path in config.MOVERS_INDEXES.items():
        df = pd.read_csv(path, dtype=str)
        col = 'ticker' if 'ticker' in df.columns else df.columns[0]
        syms = df[col].dropna().str.strip().str.upper()
        members[code] = sorted(set(syms[syms != '']))
    return members


def evaluate(close: pd.DataFrame, members: dict,
             sessions: int | None = None) -> pd.DataFrame:
    """
    Long table (COLUMNS) of every member's daily % change and rank.

    `close` is the wide Date×ticker matrix; members missing from it are
    ignored. `sessions` keeps only the last N dates (None = all).
    """
    pct = close.sort_index().pct_change(fill_method=None) * 100.0
    if sessions is not None:
        pct = pct.iloc[-sessions:]
    out = []
    for code, syms in members.items():
        cols = sorted(c for c in syms if c in pct.columns)
        if not cols:
            continue
        sub = pct[cols]
        # coverage against the full member list, not only the loaded ones
        ok = sub.notna().sum(axis=1) >= config.MOVERS_MIN_COVERAGE * len(syms)
        sub = sub[ok]
        if sub.empty:
            continue
        # 'first' = ties broken alphabetically (columns are sorted), so a
        # top-N query never returns more than N rows
        top = sub.rank(axis=1, ascending=False, method='first')
        bottom = sub.rank(axis=1, ascending=True, method='first')
        long = pd.DataFrame({
            'change_pct': sub.stack(),
            'rank_top': top.stack(),
            'rank_bottom': bottom.stack(),
        })
        long.index.names = ['snapshot_date', 'symbol']
        long = long.reset_index()
        long['index_code'] = code
        out.append(long)
    if not out:
        return pd.DataFrame(columns=COLUMNS)
    df = pd.concat(out, ignore_index=True)
    df['snapshot_date'] = pd.to_datetime(df['snapshot_date']).dt.strftime('%Y-%m-%d')
    df['change_pct'] = df['change_pct'].round(3)
    df[['rank_top', 'rank_bottom']] = df[['rank_top', 'rank_bottom']].astype(int)
    return df[COLUMNS]

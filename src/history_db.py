"""
History DB — results only, for top movers and repeat hits
(docs/top_movers_plan.md; table layout follows stockCharts/data/stockcharts.db).

  mover_ranks       every index member's daily % change + rank (top/bottom)
  screen_hits       which ticker passed which screener (the in_* flags)
  index_membership  first/last session a ticker was seen in an index
  confluence_daily  each ticker's Confluence families/badges per session
                    (batch badges only; tickers with no badge not stored)

Writes replace a whole session (delete + insert), so re-running a day is
safe and a ticker that left an index doesn't linger. Repeat-hit maths
(hits, streak) is done in pandas over the selected window.
"""
import sqlite3
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS mover_ranks (
    snapshot_date TEXT NOT NULL,
    index_code    TEXT NOT NULL,
    symbol        TEXT NOT NULL,
    change_pct    REAL,
    rank_top      INTEGER,
    rank_bottom   INTEGER,
    PRIMARY KEY (snapshot_date, index_code, symbol)
);
CREATE TABLE IF NOT EXISTS screen_hits (
    snapshot_date TEXT NOT NULL,
    screen        TEXT NOT NULL,
    symbol        TEXT NOT NULL,
    PRIMARY KEY (snapshot_date, screen, symbol)
);
CREATE TABLE IF NOT EXISTS confluence_daily (
    snapshot_date    TEXT NOT NULL,
    symbol           TEXT NOT NULL,
    n_families       INTEGER,
    n_badges         INTEGER,
    confluence_score REAL,
    families         TEXT,             -- comma-separated
    badges           TEXT,             -- comma-separated
    PRIMARY KEY (snapshot_date, symbol)
);
CREATE TABLE IF NOT EXISTS index_membership (
    index_code TEXT NOT NULL,
    symbol     TEXT NOT NULL,
    first_seen TEXT NOT NULL,
    last_seen  TEXT NOT NULL,
    PRIMARY KEY (index_code, symbol)
);
"""

REPEAT_COLUMNS = ['symbol', 'hits', 'sessions', 'hit_rate', 'streak',
                  'avg_change_pct', 'first_hit', 'last_hit']


class HistoryDB:
    def __init__(self, path: Path | str | None = None):
        self.path = Path(path or config.HISTORY_DB)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.executescript(SCHEMA)

    def _conn(self):
        return sqlite3.connect(self.path)

    def _query(self, sql: str, params=()) -> pd.DataFrame:
        with self._conn() as c:
            return pd.read_sql_query(sql, c, params=params)

    # ------------------------------------------------------------ writes --
    def write_movers(self, df: pd.DataFrame) -> int:
        """Replace every (session, index) present in `df` (top_movers.COLUMNS)."""
        if df.empty:
            return 0
        keys = df[['snapshot_date', 'index_code']].drop_duplicates()
        with self._conn() as c:
            c.executemany('DELETE FROM mover_ranks WHERE snapshot_date = ? '
                          'AND index_code = ?', keys.itertuples(index=False))
            c.executemany(
                'INSERT INTO mover_ranks VALUES (?, ?, ?, ?, ?, ?)',
                df[['snapshot_date', 'index_code', 'symbol', 'change_pct',
                    'rank_top', 'rank_bottom']].itertuples(index=False))
        return len(df)

    def write_hits(self, snapshot_date: str, flags: pd.DataFrame) -> int:
        """Replace one session's hits from a ticker × in_* boolean frame.
        Screen name = the column without its 'in_' prefix."""
        rows = []
        for col in flags.columns:
            hit = flags[col].fillna(False).astype(bool)
            screen = col[3:] if col.startswith('in_') else col
            rows += [(snapshot_date, screen, str(s)) for s in hit.index[hit]]
        with self._conn() as c:
            c.execute('DELETE FROM screen_hits WHERE snapshot_date = ?',
                      (snapshot_date,))
            c.executemany('INSERT INTO screen_hits VALUES (?, ?, ?)', rows)
        return len(rows)

    def write_confluence(self, snapshot_date: str, cf: pd.DataFrame) -> int:
        """Replace one session from confluence.compute() output (ticker
        index; `families` / `badges` are lists)."""
        cf = cf[cf['n_badges'] > 0]
        rows = [(snapshot_date, str(t), int(r.n_families), int(r.n_badges),
                 float(r.confluence_score), ','.join(r.families),
                 ','.join(r.badges)) for t, r in cf.iterrows()]
        with self._conn() as c:
            c.execute('DELETE FROM confluence_daily WHERE snapshot_date = ?',
                      (snapshot_date,))
            c.executemany('INSERT INTO confluence_daily VALUES '
                          '(?, ?, ?, ?, ?, ?, ?)', rows)
        return len(rows)

    def write_membership(self, snapshot_date: str, members: dict) -> None:
        rows = [(code, s, snapshot_date, snapshot_date)
                for code, syms in members.items() for s in syms]
        with self._conn() as c:
            c.executemany(
                'INSERT INTO index_membership VALUES (?, ?, ?, ?) '
                'ON CONFLICT(index_code, symbol) DO UPDATE SET '
                'first_seen = MIN(first_seen, excluded.first_seen), '
                'last_seen = MAX(last_seen, excluded.last_seen)', rows)

    # ------------------------------------------------------------- reads --
    def mover_dates(self, index_code: str) -> list:
        return self._query('SELECT DISTINCT snapshot_date FROM mover_ranks '
                           'WHERE index_code = ? ORDER BY snapshot_date DESC',
                           (index_code,))['snapshot_date'].tolist()

    def hit_dates(self) -> list:
        return self._query('SELECT DISTINCT snapshot_date FROM screen_hits '
                           'ORDER BY snapshot_date DESC')['snapshot_date'].tolist()

    def confluence_dates(self) -> list:
        return self._query('SELECT DISTINCT snapshot_date FROM confluence_daily '
                           'ORDER BY snapshot_date DESC')['snapshot_date'].tolist()

    def confluence_window(self, days: int) -> tuple:
        """(rows, sessions) for the last `days` stored sessions, newest
        session first."""
        sessions = self.confluence_dates()[:days]
        if not sessions:
            return pd.DataFrame(), []
        rows = self._query('SELECT * FROM confluence_daily '
                           'WHERE snapshot_date >= ?', (min(sessions),))
        return rows, sessions

    def screens(self) -> list:
        return self._query('SELECT DISTINCT screen FROM screen_hits '
                           'ORDER BY screen')['screen'].tolist()

    def movers(self, snapshot_date: str, index_code: str, n: int,
               side: str = 'top') -> pd.DataFrame:
        rank = 'rank_top' if side == 'top' else 'rank_bottom'
        return self._query(
            f'SELECT {rank} AS rank, symbol, change_pct FROM mover_ranks '
            f'WHERE snapshot_date = ? AND index_code = ? AND {rank} <= ? '
            f'ORDER BY {rank}', (snapshot_date, index_code, n))

    def repeat_movers(self, index_code: str, n: int, side: str = 'top',
                      days: int = 20) -> pd.DataFrame:
        """Who made the top (bottom) N of `index_code` most often over the
        last `days` sessions."""
        rank = 'rank_top' if side == 'top' else 'rank_bottom'
        sessions = self.mover_dates(index_code)[:days]
        if not sessions:
            return pd.DataFrame(columns=REPEAT_COLUMNS)
        rows = self._query(
            f'SELECT snapshot_date, symbol, change_pct FROM mover_ranks '
            f'WHERE index_code = ? AND {rank} <= ? AND snapshot_date >= ?',
            (index_code, n, min(sessions)))
        return repeat_table(rows, sessions)

    def repeat_hits(self, screen: str, days: int = 20) -> pd.DataFrame:
        """Who passed `screen` most often over the last `days` stored runs."""
        sessions = self.hit_dates()[:days]
        if not sessions:
            return pd.DataFrame(columns=REPEAT_COLUMNS)
        rows = self._query(
            'SELECT snapshot_date, symbol FROM screen_hits '
            'WHERE screen = ? AND snapshot_date >= ?', (screen, min(sessions)))
        return repeat_table(rows, sessions)

    def ticker_ranks(self, symbol: str) -> pd.DataFrame:
        return self._query(
            'SELECT snapshot_date, index_code, change_pct, rank_top, '
            'rank_bottom, (SELECT COUNT(*) FROM mover_ranks x '
            ' WHERE x.snapshot_date = r.snapshot_date '
            ' AND x.index_code = r.index_code) AS index_size '
            'FROM mover_ranks r WHERE symbol = ? '
            'ORDER BY snapshot_date DESC, index_code', (symbol.upper(),))

    def ticker_hits(self, symbol: str) -> pd.DataFrame:
        return self._query(
            "SELECT snapshot_date, GROUP_CONCAT(screen, ', ') AS screens "
            'FROM screen_hits WHERE symbol = ? GROUP BY snapshot_date '
            'ORDER BY snapshot_date DESC', (symbol.upper(),))


def repeat_table(rows: pd.DataFrame, sessions: list) -> pd.DataFrame:
    """
    Aggregate hit rows (snapshot_date, symbol[, change_pct]) over `sessions`
    (newest first): hits, hit rate, current streak (consecutive sessions up
    to the newest one), average % change, first/last hit.
    """
    if rows.empty:
        return pd.DataFrame(columns=REPEAT_COLUMNS)
    rows = rows[rows['snapshot_date'].isin(sessions)]
    order = {d: i for i, d in enumerate(sessions)}        # 0 = newest
    out = []
    for sym, g in rows.groupby('symbol'):
        pos = sorted(order[d] for d in g['snapshot_date'])
        streak = 0
        while streak < len(pos) and pos[streak] == streak:
            streak += 1
        out.append({
            'symbol': sym, 'hits': len(pos), 'sessions': len(sessions),
            'hit_rate': round(len(pos) / len(sessions) * 100, 1),
            'streak': streak,
            'avg_change_pct': (round(g['change_pct'].mean(), 2)
                               if 'change_pct' in g else None),
            'first_hit': g['snapshot_date'].min(),
            'last_hit': g['snapshot_date'].max(),
        })
    df = pd.DataFrame(out, columns=REPEAT_COLUMNS)
    return df.sort_values(['hits', 'streak', 'last_hit', 'symbol'],
                          ascending=[False, False, False, True],
                          ignore_index=True)

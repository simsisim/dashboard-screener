# Plan — Top Movers + Repeat Hits (replaces sandBox/cnbs)

Status: **steps 1–3 done** (2026-10-13): movers backfilled 250 sessions, screen hits from 13 runs, tab live. Dow 30 deliberately left out for now.

## Why here

- CNBC blocks automated access since 2026-10-10, so `sandBox/cnbs` is retired.
- This project already reads `downloadData_v1` in place (`config.DOWNLOAD_ROOT`), so the
  daily OHLCV for every S&P 500 / NASDAQ 100 stock is already on disk. No new download.
- Top movers is one more screener on daily bars, next to Stockbee Movers.
- "Repeat hits" (who keeps showing up) is useful for *every* screener here, not only movers.
- Results are stored the `stockCharts` way: a small SQLite with only the results, not the metrics.

## What it does

1. **Top movers per index** — for each session: % change vs previous close for every member of
   S&P 500 and NASDAQ 100, ranked top (gainers) and bottom (losers). Same output CNBC gave.
2. **Repeat hits** — over the last X sessions: how often a ticker made the top/bottom N of an
   index, or passed any screener; plus first/last hit and current streak.

## Inputs (all from downloadData_v1, read-only)

| What | Where |
|---|---|
| Daily bars | `data/market_data/daily/{archive,current}/{SYM}.csv` via `src/data_loader.load_price_matrices` |
| S&P 500 members | `data/tickers/sp500_tickers.csv` (499 rows today) |
| NASDAQ 100 members | `data/tickers/nasdaq100_tickers.csv` (98 rows today) |

Members missing from the screener universe are loaded in addition, so no index member is dropped.

## Storage — `results/history.db` (SQLite, results only)

```sql
CREATE TABLE mover_ranks (            -- one row per member per session (~600 rows/day)
    snapshot_date TEXT NOT NULL,      -- date of the latest bar, not date.today()
    index_code    TEXT NOT NULL,      -- 'SP500' | 'NASDAQ100'
    symbol        TEXT NOT NULL,
    change_pct    REAL,
    rank_top      INTEGER,            -- 1 = biggest gainer
    rank_bottom   INTEGER,            -- 1 = biggest loser
    PRIMARY KEY (snapshot_date, index_code, symbol)
);
CREATE TABLE screen_hits (            -- which ticker passed which screener on which session
    snapshot_date TEXT NOT NULL,
    screen        TEXT NOT NULL,      -- e.g. 'minervini', 'daily_gainers', 'glp' (the in_* flags)
    symbol        TEXT NOT NULL,
    PRIMARY KEY (snapshot_date, screen, symbol)
);
CREATE TABLE index_membership (       -- stockCharts pattern: when a ticker was seen in an index
    index_code TEXT NOT NULL,
    symbol     TEXT NOT NULL,
    first_seen TEXT NOT NULL,
    last_seen  TEXT NOT NULL,
    PRIMARY KEY (index_code, symbol)
);
```

Upsert per session, so re-running a day replaces it. The db is rebuildable (see Backfill).

## Code

| File | Change |
|---|---|
| `src/leaders/top_movers.py` | **new** — `evaluate(close, members) -> long DataFrame`, vectorized over all dates (not only the latest bar) |
| `src/history_db.py` | **new** — create tables, upsert, queries: `movers(date, index, n, side)`, `repeat_movers(index, n, side, days)`, `repeat_hits(screen, days)`, `ticker_history(symbol)`. Repeat-movers SQL ported from `sandBox/cnbs/src/db.py::frequent_movers` |
| `config.py` | member-list paths, `MOVERS_INDEXES`, defaults (`MOVERS_TOP_N = 10`, `REPEAT_DAYS = 20`) |
| `run_screeners.py` | after loading data: compute movers → db; at the end: write the `in_*` flags of `screener_results.csv` to `screen_hits`. New flags `--movers-only`, `--backfill-movers N` |
| `dashboard.py` | new tab **📈 Top Movers** (see below) |
| `test_top_movers.py` | **new** — synthetic matrices: % change, ranking, ties, NaN/missing bar, upsert idempotence, repeat-hit counts and streak |

## Dashboard tab "📈 Top Movers"

- **Movers** — session picker, index (S&P 500 / NASDAQ 100), N, gainers/losers side by side,
  with sector/industry from the universe.
- **Repeat hits** — source = top/bottom N of an index *or* any screener; window X sessions →
  ticker, hits, hits/sessions, avg % change, current streak, first/last hit. Sortable;
  "save as list" via the existing `my_lists` mechanism.
- **Ticker history** — one ticker: daily rank in each index + every screener it passed.

## Backfill

- Movers: computed from the price history already on disk, so `--backfill-movers 250` fills a
  year in seconds. Caveat: uses *today's* member lists (survivorship); from now on each day is
  stored with the members of that day.
- Screener hits: from the 14 existing `results/YYYY-MM-DD/screener_results.csv` (2026-08-24 →
  2026-10-11); older history doesn't exist.

## Daily run

Unchanged: after `downloadData_v1` has updated (its file times show ~06:35 Berlin),
`python3 run_screeners.py` also writes movers + hits. `--movers-only` for a quick run.
Warn and skip if the latest bar is missing for > 5% of index members (same idea as
`check_missing_days`).

## Steps

1. `top_movers.py` + `history_db.py` + tests.
2. Hook into `run_screeners.py`, backfill movers 250 sessions, backfill screen hits.
3. Dashboard tab (Movers → Repeat hits → Ticker history).
4. README section + retire cnbs (below).

## Retire sandBox/cnbs

- Decide on its uncommitted changes (`is_rolled_over` work) — commit as final state or drop.
- Disable the GitHub Action, archive `simsisim/cnbc-markets` (asks first — changes the GitHub repo).
- README: replace the alternatives section with a short "retired, moved to dashboard-screener" note.

## Later / not now

- Dow 30 (needs a `dow30_tickers.csv` in downloadData_v1).
- Sector ETF / futures / FX table and Sector Rotation view (from `indexes_tickers.csv`).
- Movers for the whole universe (not only index members) with a liquidity filter.

## Open questions

- Default N for top/bottom: 10?
- Backfill length: 250 sessions (1 year) enough?

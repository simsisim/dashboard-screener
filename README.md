# Step-2 Filters Module

Screening module (NOT backtesting) implementing intro.md's Step 2: it runs the
1st-category filters over the ~4,000-ticker universe to build **Leaders'
Lists**, then applies the 2nd-category metrics to build a **Focus List** —
presented through CSV outputs and a Streamlit dashboard. The human operator
picks the actual trades (entries/exits are out of scope).

## Quick start

```bash
cd /home/imagda/_invest2024/python/screeners

# 1) run the screeners (full universe, ~1-2 min)
python3 run_screeners.py

# 2) open the dashboard
streamlit run dashboard.py
```

Outputs land in `results/YYYY-MM-DD/`:

| File | Contents |
|------|----------|
| `screener_results.csv` | every ticker × every metric (the filter-panel data) |
| `leaders_minervini.csv` | Minervini trend-template 8/8 list |
| `leaders_canslim.csv` | CANSLIM C-A-I list |
| `leaders_scooter.csv` | SCOOTER (SCTR ≥ 90) list |
| `leaders_all.csv` | union, deduped, with per-list membership flags |
| `focus_list.csv` | leaders ∩ stage 2A/2B ∩ not very-extended ∩ liquid |
| `dashboard.md` | human-readable summary |

## The filters

**1st cat — Leaders' Lists** (a ticker on a list is NOT a buy signal — it
still needs a low-risk entry; intro.md)

*Additional leaders/focus screeners (more_screeners.md backlog, all with
behavioral validate.py checks):* **Stockbee Movers** (9M-share / 20%-weekly
/ 4%-daily, `src/leaders/stockbee_movers.py`), **Golden Launch Pad**
(tight EMA 10/20/50 cluster + stack + slopes, `src/leaders/gold_launch_pad.py`),
**GMMA state** (`src/leaders/gmma.py`), **Qullamaggie Suite**
(`src/leaders/qullamaggie.py`), **volume anomaly 3-sigma**
(`src/focus/volume_anomaly.py`), **ADL 5-step accumulation**
(`src/leaders/adl_accumulation.py`), plus VROC/ADTV/MFI/ADX filter columns
(`src/focus/volume_adx.py`). All filterable in the Advanced section.

- **Minervini trend template** — the 8 criteria (price vs 50/150/200-SMA
  alignment, 200-SMA rising ≥1 month, ≥30% above 52w low, within 25% of 52w
  high, IBD-style RS ≥ 70). Ported from `lkm_rs` (backtest-validated there).
- **CANSLIM C-A-I** — from the `downloadData_v1` financial snapshot:
  C = latest quarterly diluted EPS YoY ≥ +25% (q1 vs q5, base-EPS floor),
  A = 3-year EPS CAGR ≥ +25%, I = institutional ownership ≥ 20%.
  (N/S/L/M are not financial-data-filterable — intro.md's scope decision.)
- **SCOOTER** = SCTR (StockCharts Technical Rank, John Murphy): six weighted
  components → cross-sectional percentile 0–99.9. Ported verbatim from
  `test_scooter/sctr_model.py`.

**2nd cat — Focus metrics** (computed for every ticker; filterable columns)

- **ATR extension** vs 21 EMA and 40 SMA in ATR units (+ the exact ALEX pine
  variant), thresholds ±2.0/±5.0 ATR — TradingView `60GMm8mE`
  ("ALEX - ATR Extensions + ADR + Table").
- **ADR** 20-day % and 50-day average dollar volume (the two "IMPORTANT"
  StockScreenHero columns from the Jack Corsellis dashboard reference).
- **Weinstein stages** 1 / 2A / 2B / 2C / 3 / 4 — ported from
  `yf-gics/src/stage_analysis.py`.
- **RTI** (Range Tightening Indicator, TradingView `yaIeno72`): 5/15/50-bar
  range %, zones, low-vol dots, range-expansion flag.
- **Dashboard context**: % vs 10/21/50/200 MAs, % from 52w high/low,
  5d/1m/3m/6m gains, market cap, sector, industry.

## CLI

```
python3 run_screeners.py                    # full run
python3 run_screeners.py --leaders-only     # skip focus metrics
python3 run_screeners.py --focus-only       # focus gates on the whole universe
python3 run_screeners.py --min-scooter 95 --min-rs 80
python3 run_screeners.py --stages 2A,2B,2C
python3 run_screeners.py --no-liquidity-gate
python3 run_screeners.py --combine intersection
python3 run_screeners.py --ticker AAPL      # single-ticker metric dump
python3 run_screeners.py --limit 200        # debug on first N tickers
```

All thresholds live in `config.py` (single source of truth, provenance cited
inline).

## Dashboard

`streamlit run dashboard.py` — StockScreenHero-style layout per the user
sketch (`images/corsellis_screener/`): top bar **Ioa's Presets** (built-in
method templates incl. Corsellis's "Momentum Leader (Narrow)") / **Ioa's
Lists** (CSV upload) / **My Screener** (saved filter panels, load + delete) /
**My Lists** (saved ticker lists); the 4-row filter grid with threshold
dropdowns + Custom… sliders; Reset / Save Screener / Save Screener As…
(JSON in `my_screeners/`); results section with Search, Number of Results,
Order Results by, Sort Order, "Showing 1 to N of M", per-row selection with
**sparkline chart column** (120d closes), save-selected/all-as-list, CSV
download, and a **TradingView `.txt`** export (`EXCHANGE:SYMBOL`,
comma-separated, `###` section divider — paste into TradingView's *Upload
list…*; `dfil.tradingview_watchlist()`, offered on every results table:
Leaders, Screener, Focus List, Confluence, Timing, Patterns, Workflows).
Advanced filters (stage, RS, RTI, leaders
union/intersection, exchange, index) in a collapsible section. The
**Re-run screeners** button executes `run_screeners.py` from the UI.

Filter/screener/preset/list conventions: see
`images/corsellis_screener/TAXONOMY.md`.

## Data (owned by downloadData_v1, consumed in place)

- Universe: `user_input/tradingview_universe.csv` (4,034 symbols)
- Daily bars: `data/market_data/daily/archive` (2020-01→2025-12) +
  `current` (2026-01→now) + `market_data_batch/daily` tail — merged into
  ~1,670-bar histories per ticker
- Fundamentals: `data/fin_data/financial_data_0_8.csv` (snapshot; no network)
- Shares outstanding: `data/market_data/shares_outstanding/*.csv`

## Timing Signals & Patterns tabs (on-demand)

Two further tabs run **on demand** against a scoped subset (index
membership + min market cap) — never in the daily batch:

- **🕐 Timing Signals** — PVB state machine, ATR1 volatility-stop cloud,
  Dr. Wish Blue/Black Dot (`src/timing/`). Scope → sources → ▶ Run with a
  per-ticker progress bar; state filter + max-days-since; results persist
  to `results/{date}/timing_signals_{scope}.csv` (same-day reuse).
- **🌊 Patterns** — GLB Green Line Breakout (`src/patterns/glb.py`,
  incremental per-ticker cache under `results/glb_cache/`, adjustable
  pivot/lookback/confirmation) and Cup & Handle
  (`src/patterns/cup_handle.py`, Strict/Default/Loose parameter presets).
  Persist to `results/{date}/patterns_*.csv`.

Every module carries per-row `as_of` dates (mixed-data transparency) and
is covered by behavioral checks in `validate.py` /
`test_dashboard_app.py`.

## Workflows tab

**🧭 Workflows** (`src/workflow.py`, `config.WORKFLOWS`, `docs/workflows_tab.md`)
runs a saved **multi-stage screening funnel** end-to-end over the latest daily
`screener_results.csv` — no re-run, no data load: each stage row-filters the
previous one (or the full universe) with the *same* `dfil.build_mask` +
`dfil.build_advanced_mask` the All-Results panel uses. Output is a **Focus
List** (the deduped union of the stages flagged `focus_input`) plus a manual
pre-entry checklist for the parts that need pre-market / catalyst / breadth data.

- **Run** (default) — the stepper: per-stage `in → out` counts, filter
  summary, rationale note, expandable table; then the Focus List (sparklines,
  save-as-list, CSV) and the checklist.
- **Edit** — **✎ Edit / Duplicate** or **＋ New** opens the builder:
  construct/reorder/retune stages in an inline editor (the same threshold grid
  as the Screener tab, keyed per stage), edit the checklist; **💾 Save** (to
  `my_workflows/*.json`) or **Discard** returns to the run. Built-ins are
  read-only; Edit / Duplicate opens one as an editable copy.
- Ships with `Trading Voyage (Ollie)` and `Trading Voyage - Daily studies
  (Ollie)` — the Voyage Trading Group method (`sandBox/Oliver_wiedmeier/`).
- New columns for it: `pct_above_{21,63,126}d_low` (`src/indicators.
  pct_above_rolling_low`) — "price is X% above its N-day low", Ollie's scans.

## Validation

Two re-runnable suites:

```bash
python3 validate.py             # 41/41 data-level checks (ports vs sources,
                                # ALL 15 presets vs manual filters, round trip,
                                # build_advanced_mask + workflow engine)
python3 test_dashboard_app.py   # 40/40 UI checks (Streamlit AppTest: preset
                                # counts, leak regression, refresh, reset,
                                # timing/patterns/confluence/workflows tabs)
```

- ATR14 vs `metaData_v1` per-stock loop on identical window: diff 2.5e-05
- ATRext40 vs `metaData_v1` `atrext_dollar`: diff 2e-06
- Weinstein stages vs `lkm_rs.compute_stage`: 5/5 tickers match
- SCTR raw vs `test_scooter`: bit-identical (rel diff 0.0)
- ext/ADR identities + RTI zone ordering: exact
- Full run: 4,035 universe → 3,961 loaded → Minervini 391 / SCOOTER 366 /
  CANSLIM 141 / union 740 (7 on all three; 487 of 740 with flat/shrinking
  shares outstanding) / focus 431

See `IMPLEMENTATION_PLAN.md` for the full design, bibliography mapping and
v2 review changelog.

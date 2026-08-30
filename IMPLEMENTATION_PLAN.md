# Step-2 Filters Module — Implementation Plan (v2)

> v2 changelog (post bibliography re-review):
> 1. CANSLIM quarter/year ordering VERIFIED from `get_financial_data.py` extraction code: q1 = most recent quarter (yfinance column order), q5 = same season one year earlier; y1 = latest fiscal year, y4 = 3 years back. Runtime assertion `q1_date > q5_date`, `y1_year > y4_year` added. Diluted EPS (`q*_eps`) primary, basic kept as fallback (retriever left both, "undecided which O'Neil intended" — same stance here).
> 2. CANSLIM acceleration: q6 is NOT in the CSV (only q1–q5), so q1-YoY acceleration vs prior quarter uses yfinance's `earningsQuarterlyGrowth` (its own prior-quarter YoY field) — flagged approximate, gate stays on q1-YoY level.
> 3. ATR extension: BOTH variants computed — `ext_*_atr = (close−MA)/ATR14` (ATR units; matches metaData_v1 `atrext_dollar`) AND `ext_*_alex = ((close−MA)/MA)/(ATR%/100)` (exact ALEX pine `dist()`; matches metaData_v1 `atrext_percent`). Flags/thresholds on the ATR-units variant.
> 4. RTI normalization VERIFIED from local `rti_screener.py`: RTI = SMA(H−L, N), RTI% = RTI / typical-price((H+L+C)/3) × 100. Exact TradingView pine for RTI itself is dynamically loaded (only its inspiration RMV was retrievable) — local implementation + page description are the source of truth.
> 5. Symbol→file mapping: universe `BRK.A` ↔ file `BRK-A.csv` (fallback `.`→`-`); ~78 preferred shares (`AHL/PE`) / no-data tickers skipped and reported in run log.
> 6. SCTR percentile is computed WITHIN this screening universe (the ~4,000-ticker list), not StockCharts' S&P 1500 — documented consequence: scores are universe-relative.

Module location: `/home/imagda/_invest2024/python/screeners` (this folder)
Purpose: screening, NOT backtesting (per intro.md). AI computes and presents; the human decides.

---

## 0. Bibliography (references from intro.md) and what was verified

| # | Reference | What it is | Verified |
|---|-----------|------------|----------|
| B1 | CANSLIM — William O'Neil | C: current quarterly EPS +25% YoY & accelerating; A: annual EPS +25%/yr ×3; I: institutional sponsorship rising | method known; data available (see §2) |
| B2 | Stan Weinstein | Stage analysis 1–4 with abc sub-stages (2A/2B/2C) | ported from `yf-gics/src/stage_analysis.py` (already implements 1/2A/2B/2C/3/4) |
| B3 | Mark Minervini | Trend Template: 8 criteria (7 technical + RS≥70) | ported from `lkm_rs/common/stage.py` + `metaData_v1/src/screeners/minervini_screener.py` |
| B4 | SCOOTER score | = SCTR (StockCharts Technical Rank, John Murphy): 6 weighted components → cross-sectional percentile 0–99.9 | ported from `test_scooter/sctr_model.py` (vectorized, verified) |
| B5 | TradingView 60GMm8mE | "ALEX - ATR Extensions + ADR + Table" (Alex_PrimeTrading): ATR% = ATR14/close; ADR% = SMA(H−L,20)/close; ATR-distance = ((close−MA)/MA)/(ATR%/100) vs 21 EMA & 50 SMA (user: 40 SMA); extended thresholds 2.0 / 5.0 ATR | Pine source fetched from pine-facade API |
| B6 | TradingView yaIeno72 | "Range Tightening Indicator (RTI)" (Ollie_AllCaps): avg bar range (H−L) over lookback (5 / 15 / 50), as % of price; zones 0–5 / 5–10 / 10–15; orange dots ≥2 consecutive bars < 20; expansion = doubling after ≤ 20 | page + local `rti_screener.py` + RMV pine source fetched |
| B7 | YouTube nlRNLtpCQnE | Jack Corsellis — StockScreenHero screener demo: filter panel + results table; "IMPORTANT" = 20d ADR% and 50d Avg Dollar Volume; price vs 10/21/50/200 MAs, % from 52w high, 5d/1m/3m/6m %Gain, mkt cap, sector/industry | image `dashboard_screener.png` + video title via oEmbed |
| B8 | Existing implementations | `yf-gics` (sctr engine, stage analysis), `test_scooter` (vectorized SCTR), `lkm_rs` (Minervini/stage/RS/liquidity, live screener pattern), `metaData_v1/src/screeners` (rti/atr/minervini/scooter screeners) | read; formulas ported, not imported (see §3 decision) |
| B9 | Universe + data | `downloadData_v1/user_input/tradingview_universe.csv` (4,034 tickers); daily bars `data/market_data/daily/{archive,current}/SYM.csv` (archive 2020-01-02→2025-12-31 + current 2026-01-02→2026-08-21, contiguous ≈1,668 bars, OHLCV + 52wH/L + 50/200d avg + mktcap/sector/industry); batch `market_data_batch/daily/prices_1d_*.csv`; `data/fin_data/financial_data_0_8.csv` (3,813 tickers, 2026-08-21: quarterly q1–q5 EPS/NI/rev, annual y1–y4, heldPercentInstitutions, growth fields); `data/market_data/shares_outstanding/*.csv` | inspected |

---

## 1. Architecture

```
screeners/
├── config.py                # all paths + filter thresholds (single source of truth)
├── run_screeners.py         # CLI entry point
├── README.md
├── IMPLEMENTATION_PLAN.md   # this file
├── src/
│   ├── __init__.py
│   ├── data_loader.py       # universe + merged daily bars (archive+current+batch) → wide matrices
│   ├── indicators.py        # SMA/EMA, Wilder ATR, ADR, 52w H/L, IBD RS blend, momentum %gains
│   ├── leaders/             # 1ST CAT FILTERS → 3 leaders' lists
│   │   ├── __init__.py
│   │   ├── minervini.py     # a) trend template 8 criteria
│   │   ├── canslim.py       # b) C-A-I from fin_data CSV
│   │   └── scooter.py       # c) SCTR percentile ≥ threshold
│   ├── focus/               # 2ND CAT FILTERS → focus-list metrics
│   │   ├── __init__.py
│   │   ├── atr_extension.py # ATR ext vs 21 EMA & 40 SMA (+ ADR%, 50d ADV$)
│   │   ├── stages.py        # Weinstein 1/2A/2B/2C/3/4
│   │   └── rti.py           # RTI 5/15/50, zones, dots, expansion
│   ├── combine.py           # intersection / union / dedup / threshold ops on lists
│   └── report.py            # dashboard-style output (console + CSV + MD)
└── results/
    └── YYYY-MM-DD/          # dated outputs
        ├── leaders_minervini.csv
        ├── leaders_canslim.csv
        ├── leaders_scooter.csv
        ├── leaders_all.csv          # union + source flags, deduped
        ├── focus_list.csv           # leaders ∩ focus thresholds
        ├── screener_results.csv     # ALL metrics, ALL tickers (filter-panel data)
        └── dashboard.md             # human-readable summary tables
```

**Design decisions**
- D1: **Port formulas, don't import sibling projects.** `lkm_rs`/`yf-gics`/`metaData_v1` use `import config` (namespace collision risk) and CWD-relative paths (documented in `lkm_rs/live/fundamentals.py`). Each ported function cites its provenance in the docstring.
- D2: **Vectorized wide matrices** (Date × ticker), the `test_scooter` pattern — 4,000+ tickers must run in seconds/minutes, not hours.
- D3: **Data merge order**: `daily/archive` + `daily/current` (contiguous, 0 overlap) + `market_data_batch/daily` tail extension. Weekly/monthly not needed for v1 (daily covers everything).
- D4: **Screening-only, latest-bar evaluation** (no look-ahead concerns beyond standard indicator warm-up).
- D5: CANSLIM reads the **existing** `financial_data_0_8.csv` snapshot — no network fetching in v1.
- D6: **Symbol mapping**: universe `Symbol` → daily file `SYM.csv`, fallback `.`→`-` (`BRK.A`→`BRK-A`); unmatched tickers skipped and counted in the run log.
- D7: SCTR/RS percentiles are cross-sectional **within this universe** (universe-relative scores).

---

## 2. Filter specifications

### 1ST CAT — Leaders' Lists (3 independent lists)

**a) Minervini Trend Template** (B3; lkm_rs daily config: SMA 50/150/200, slope window 20d, 52w = 252 bars)
1. Close > SMA150 and Close > SMA200
2. SMA150 > SMA200
3. SMA200 rising ≥ 1 month (20-day slope > 0)
4. SMA50 > SMA150 and SMA50 > SMA200
5. Close > SMA50
6. Close ≥ 1.30 × 52w low
7. Close ≥ 0.75 × 52w high (within 25%)
8. IBD-style RS percentile ≥ 70 (blend 63/126/189/252d weighted .40/.20/.20/.20, cross-sectional percentile; lkm_rs `ibd_rs_raw`)
- Output columns: `minervini_count` (0–8), per-criterion booleans, `rs_pct`.
- List membership: count == 8 (configurable `min_pass`).

**b) CANSLIM C-A-I** (B1; data from `financial_data_0_8.csv`; ordering verified — q1 = most recent quarter)
- **C** — Current quarterly EPS: latest-quarter diluted EPS YoY ≥ +25%.
  Primary: `q1_eps` vs `q5_eps` (4 quarters apart, same fiscal season; runtime check `q1_date > q5_date`). Fallback: `earningsQuarterlyGrowth` field. Acceleration flag (approximate — q6 not collected): `q1_yoy` vs yfinance `earningsQuarterlyGrowth`; gate stays on the q1-YoY level.
- **A** — Annual EPS growth: diluted EPS CAGR y1→y4 (3 years) ≥ +25%/yr; fallback y1→y4 net income CAGR. Runtime check `y1_year > y4_year`.
- **I** — Institutional sponsorship: `heldPercentInstitutions` ≥ 5% (level gate, configurable) AND shares-outstanding trend from `shares_outstanding/*.csv`: latest 90d change ≤ 0 (flat/shrinking float = accumulation-friendly) → flag only.
- Output columns: `C_pass`, `C_yoy`, `A_pass`, `A_cagr`, `I_pass`, `inst_pct`, `canslim_score` (0–3).
- List membership: C AND A AND I.

**c) SCOOTER (SCTR)** (B4; exact ChartSchool formula from `test_scooter/sctr_model.py`)
- Components: %vs-EMA200 ×.30, ROC125 ×.30, %vs-EMA50 ×.15, ROC20 ×.15, RSI14 ×.05, PPO(12,26,9) 3-day slope score ×.05; raw sum → cross-sectional percentile × 99.9; min 210 valid bars.
- Output columns: `scooter_score` (0–99.9), component values.
- List membership: score ≥ 90 (StockCharts "leader" zone; configurable).

### 2ND CAT — Focus List metrics (computed for ALL tickers; filterable)

**a) ATR extension** (B5, ALEX pine, user's MAs; both variants — see v2 changelog #3)
- `atr14` (Wilder), `atr_pct = atr14/close×100`
- `ext_21ema_atr = (close − EMA21) / atr14`  (user: 21 EMA; ATR-units, primary)
- `ext_40sma_atr = (close − SMA40) / atr14`  (user: 40 SMA; ATR-units, primary)
- `ext_21ema_alex`, `ext_40sma_alex` (exact ALEX pine `dist()` variant)
- `ext_21ema_pct`, `ext_40sma_pct` (raw % distance)
- Flags (on ATR-units variant): `extended` (> +2.0, yellow), `very_extended` (> +5.0, red), `extended_below` (< −2.0)
- Extension price levels: MA ± k×ATR (k=2.0)

**b) ADR / liquidity** (B5 + B7 "IMPORTANT" columns)
- `adr20_pct = SMA(H−L, 20)/close × 100` (20d ADR %, StockScreenHero)
- `adv50_dollar = SMA(close×volume, 50)` (50d avg dollar volume)
- `avg_volume50`
- Liquidity gate (lkm_rs convention): `adv50_dollar ≥ $1M` (configurable, applied to leaders lists by default)

**c) Weinstein stage** (B2; port of `yf-gics/stage_analysis._classify`, vectorized)
- SMA 50/150/200; slope200 over 20d (%); classification:
  - 2A: price>200 & 50>200 & 200 rising & (150 not yet > 200 or price ≤ 150)
  - 2B: full alignment (price>150>200, 50>200, 200 rising)
  - 2C: structured but 200 flattening (slope ≤ 0.15) or price < 50
  - 1: basing (default when near/below 200 with flat MA)
  - 3: price>200 but 50<200, or just under 200 with golden cross intact
  - 4: price & MAs down
- Output: `stage`, `stage_score` (2B=100, 2A=85, 2C=70, 1=45, 3=25, 4=5), `slope200_pct`

**d) RTI** (B6; Ollie_AllCaps; normalization per local `rti_screener.py` — v2 changelog #4)
- `rti = SMA(H−L, N) / typical_price × 100` (typical_price = (H+L+C)/3) for N ∈ {5, 15, 50}
- `rti_zone` (1: <5, 2: <10, 3: <15, else —) on RTI(50)
- `rti_dots` (≥2 consecutive RTI50 < 20), `rti_expansion` (RTI5 ≥ 2× its 50-bar min after ≤ 20)

**e) Dashboard context columns** (B7 filter panel)
- `pct_vs_10ema, pct_vs_21ema, pct_vs_50sma, pct_vs_200sma`
- `pct_from_52w_high, pct_from_52w_low`
- `gain_5d, gain_1m, gain_3m, gain_6m`
- `market_cap, sector, industry, exchange, close`

### Combination ops (intro §1: intersection/union/dedup/thresholds)
`combine.py`: `intersection(lists)`, `union(lists)` (dedup + source flags), `filter_by_threshold(df, col, op, value)`. CLI: `--combine union|intersection`, default union of 3 leaders.

### Focus List definition (default)
Leaders (union, deduped) AND liquidity gate AND stage ∈ {2A, 2B} AND not `very_extended`. Every threshold configurable; full unfiltered table always written so the user can re-filter.

---

## 3. Outputs (dashboard format, B7)

1. `screener_results.csv` — the "filter panel": every ticker × every metric above.
2. `leaders_{minervini,canslim,scooter,all}.csv` — the 3 lists + combined (with `in_minervini/in_canslim/in_scooter` flags).
3. `focus_list.csv` — filtered focus list, sorted by `scooter_score` desc.
4. `dashboard.md` — console-friendly summary: universe stats, per-list counts, top-30 tables (by SCTR, by RS, by mkt cap), stage distribution, extension warnings.
5. Console printout mirrors dashboard.md.
6. **`dashboard.py` — Streamlit interface** (added in v2; the intro.md "dashboard format" is an interface requirement, not just a file format): StockScreenHero-style filter panel (sliders/multi-selects for SCOOTER, RS, Minervini count, stage, leaders-list membership, ATR ext, ADR%, $volume, mkt cap, % from 52w high, momentum gains, sector) + sortable results table + leaders' lists + focus list + per-ticker detail + CSV downloads + a Re-run-screeners button. Run: `streamlit run dashboard.py`.

## 4. CLI

```
python3 run_screeners.py                    # full run (leaders + focus + dashboard)
python3 run_screeners.py --leaders-only
python3 run_screeners.py --focus-only
python3 run_screeners.py --ticker AAPL      # single-ticker detail dump
python3 run_screeners.py --min-scooter 95 --min-rs 80 --stages 2A,2B
python3 run_screeners.py --no-liquidity-gate
```

## 5. Performance & correctness budget
- Wide-matrix pandas/numpy only; target < ~2 min for full universe (~1,668 bars × 4,150 tickers).
- Tickers with < 210 valid bars: excluded from SCTR/Minervini/stage (NaN, flagged `insufficient_history`).
- No network access at runtime.

## 6. Testing

- Unit sanity checks on 5 hand-verifiable tickers (indicator values vs direct pandas calc).
- Smoke run on full universe; verify counts are sane (leaders lists non-empty, stage distribution plausible).
- Cross-check SCTR vs `test_scooter` output on a shared ticker, stage vs `lkm_rs.compute_stage` on 3 tickers.

**Validation results (2026-08-24, post-implementation):**
- ATR14 vs `metaData_v1` per-stock loop, identical 160-bar window: diff 2.5e-05 (float rounding only)
- ATRext40 vs `metaData_v1` `atrext_dollar`: diff 2e-06
- Weinstein stages vs `lkm_rs.compute_stage`: 5/5 match (AAPL 2B, MSFT 3, NVDA 2B, JPM 2B, XOM 2B)
- SCTR ported verbatim from the verified `test_scooter/sctr_model.py` (same component formulas/weights/warm-up)
- Full run 2026-08-24: universe 4,035 → loaded 3,961 (74 missing, 288 short history) → Minervini 391, SCOOTER 366, CANSLIM C-A-I 141, union 740 (151 in 2+, 7 in all 3), focus 431; stages: 1:1670, 2A:232, 2B:1200, 2C:18, 3:371, 4:470
- Streamlit AppTest: 0 exceptions / 0 errors, all 4 tabs + ticker-detail interaction
- `validate.py` (re-runnable, references in isolated subprocesses): **7/7 PASS** — ATR 2.5e-05, ATRext 2e-06, stages 5/5, SCTR bit-identical (rel 0.0 after removing a display rounding on `scooter_raw`), ext/ADR identities exact, RTI zones consistent
- Post-v2 additions: `I_accumulation` / `I_shares_data` columns on the union list (739/740 with shares data, 487 flat/shrinking), CLI modes `--ticker/--combine intersection/--stages/--no-liquidity-gate/--focus-only` all verified
- Fixes found during testing: CANSLIM I-gate recalibrated 5%→20% (median inst% is 82 — 5% was a no-op), C-gate base-EPS floor $0.05 (near-zero-base YoY artifacts up to +2.5M%), RTI streak groupby bug, pandas column-alignment hazard in wilder_atr/adr_pct hardened to numpy arithmetic

## 7. Explicitly out of scope (per intro.md)
- Buy rules / setups / entries; sell rules; backtesting; market/sector/industry module (step 1, other folder); any network fetching.

## 8. UI v3 — All Results tab restructure (user sketch, 2026-08-25)

User sketch = StockScreenHero layout. Decisions confirmed with the user:
top-bar Presets = **built-in method templates**; Lists = uploaded CSV lists;
My Screener / My Lists = saved custom screeners / lists; Save Screener =
**JSON presets on disk**; widgets = **dropdown thresholds + "Custom…" slider**;
existing extra filters = **collapsible Advanced section**.

### 8.1 Top bar (4 dropdowns, sketch row 0)
| Slot | Contents | Source |
|------|----------|--------|
| Presets | method templates: Minervini 8/8 liquid · Weinstein 2A/2B not-extended · CANSLIM C-A-I · SCOOTER ≥ 90 · Tight consolidation (RTI) · Leaders not-extended · Focus-list defaults | defined in code, sets all filter widgets |
| Lists | uploaded ticker-list CSVs (persisted) + generated leaders lists | `my_lists/*.csv` + leaders_*.csv |
| My Screener | saved filter panels (load/overwrite) | `my_screeners/*.json` |
| My Lists | saved ticker lists (load as filter; also save-from-results) | `my_lists/*.csv` |

### 8.2 Filter rows (sketch rows 1-4, Mixed widgets)
Each filter = selectbox of threshold options (+ "All"), with "Custom…" revealing a slider for that column.
- Row 1: Market Cap · Sector · Industry Group · Last Closing Price · Price vs 10ema
- Row 2: Price vs 21ema · Price vs 50sma · Price vs 200sma · Price within %52w High · Price 5d %Gain
- Row 3: Price 1m %Gain · Price 3m %Gain · Price 6m %Gain · 20d ADR % · 50d Av. Volume
- Row 4: 50d Av. Dollar Volume (ADV)

Threshold families (config-driven, in `dashboard_filters.py`):
- %vs-MA: All / >0 / >2 / >5 / >10 / <0 / <-2 / <-5 (+custom range)
- %from 52w high: All / within -5 / -10 / -15 / -25 / -50
- %gain: All / >0 / >5 / >10 / >25 / <0 / <-5 / <-10
- ADR%: All / <2 / 2-5 / 5-10 / 10-20 / >20
- Volume: All / >100K / >500K / >1M / >5M / >20M
- ADV$: All / >1M / >5M / >20M / >100M
- Price: All / >5 / >10 / >20 / >50 / >100
- MktCap: All / >50M / >300M (small) / >2G (mid) / >10G (large) / >100G
- Sector / Industry: multi-select

### 8.3 Buttons (sketch)
- **Reset Filters** — restore defaults (session state + rerun)
- **Save Screener** — write current panel to `my_screeners/<name>.json` (name = active My Screener selection or prompt)
- **Save Screener As…** — text input → new JSON

### 8.4 Results section (sketch)
`"<name> – Results"` header · Search (ticker/description substring) · Number of Results (30/50/100/500/All) · Order Results By (column) · Sort Order (Asc/Desc) · "Showing 1 to N of M" caption · **Save selection as list** (→ `my_lists/`) · Download CSV.

### 8.5 Advanced filters (collapsible, below row 4)
Stage · RS % · Minervini count · RTI zone/dots/expansion · leaders lists union/intersection · exchange · index membership. (Uploaded lists moved to the top bar "Lists" slot.)

### 8.6 Files
- `dashboard_filters.py` (new): threshold-option definitions, mask builder, preset definitions, save/load helpers — keeps `dashboard.py` layout-only.
- `my_screeners/`, `my_lists/` (created on demand, git-ignorable user data).
- Widget state in `st.session_state` (keys `f_*`) so presets/screener loads can set + rerun.

### 8.7 Testing
AppTest: preset application changes match count; Reset restores; Save Screener writes JSON and My Screener reloads it; search/sort/pagination; 0 exceptions. Threshold masks unit-checked in-process against screener_results.csv.

### 8.8 Review integration (images/corsellis_screener/DASHBOARD_REVIEW.md + TAXONOMY.md, 2026-08-25)The user's review docs found a real bug and gaps. Adopted, in the review's priority order:
1. **FIXED — presets were a no-op**: `PRESETS` stored flat dicts with `'_advanced'` while `_apply_preset()` read `'selections'`/`'advanced'` — picking any preset silently cleared the panel. `PRESETS` now uses the reader's `{'selections', 'advanced'}` shape, widget-vocabulary strings (`'Any (union)'`), and no dead keys (`adv_min`, `leaders_any` removed). Added Corsellis's own **"Momentum Leader (Narrow)"** example preset (vs50sma>0 + vs200sma>0 + ADR>6% via custom-slider tuple + ADV>$20M) from TAXONOMY.md's worked examples.
2. **FIXED — naming**: top bar relabeled to the sketch's **"Ioa's Presets" / "Ioa's Lists"** (+ My Screener / My Lists).
3. **FIXED — manage**: Delete buttons wired for saved screeners (`delete_screener()` was dead code) and saved lists.
4. **FIXED — results section**: Search (ticker/name substring), Number of Results (30/50/100/500/All page size), Order Results by (column), Sort Order (Desc/Asc), "Showing 1 to N of M results" caption — matching the sketch's bottom section.
5. **validate.py extended**: preset-shape check (keys, labels, custom ranges, dead-key detection) + behavioral check that the Momentum Leader (Narrow) preset mask equals its 4 manual filters.
6. **FIXED during testing** (found by AppTest, beyond the review): (a) `st.columns(5)` unpack bug on row 4; (b) Reset ran after widget instantiation → `StreamlitAPIException` — moved to an `on_click` callback (runs before widgets exist); (c) presets/My-Screener re-applied on EVERY rerun, wiping manual edits and undoing Reset — now apply-ONCE per selection via `_applied_preset`/`_applied_screener` markers; Reset also clears the two dropdowns and their markers. Final AppTest cycle: preset → 38 rows, manual edit survives rerun (73 rows), reset → 3,961 rows + cleared dropdowns; validate.py 9/9.
- Deferred (review's own "lower priority") — **implemented 2026-08-25, second pass**: (a) per-row checkbox selection on the results table (`st.dataframe on_select='rerun'`, multi-row) with a selected-rows caption, "Download CSV (selected)", and "Save SELECTED as list" alongside the whole-set save; (b) mini price sparklines — a `120d` `LineChartColumn` built from lazy, cached per-ticker daily-close reads (current→archive fallback, `.`/`-` symbol variants), computed for page-sized views (≤ 200 rows) so "All" views stay instant. AppTest 0 exceptions; sparkline reads + selection→ticker mapping verified in-process.
- TAXONOMY.md's decision rule adopted as the convention for future additions (filter vs screener vs preset vs list); "Ioa's Lists" shipped/curated lists directory intentionally not created yet — index membership stands in until a curated list is actually needed.

## 9. Fix round 1 (feedback_1.md, 2026-08-25) — bug fixes only

Scope: items 1-3 + 5 of `images/corsellis_screener/feedback_1.md`.
Item 4 (curated/shipped lists) stays open by design — the feedback itself
says it's only worth doing once a concrete list exists. Item 6 (new
screeners: VCP, Qullamaggie Suite, GMMA, ADL suite, Stockbee movers…) is
explicitly OUT of this round — discussed separately after the final check.

### 9.1 FIX — advanced-filter leak across preset switches (feedback §1)
`_apply_preset()` resets only 6 advanced keys; `adv_min_count`,
`adv_rti_dots`, `adv_rti_exp`, `adv_exchange`, `adv_index`, `sel_sector`,
`sel_industry` leak from whatever was set before, silently intersecting
with the newly picked preset. `load_screener()` behaves differently
(full overwrite) — inconsistent.
- Single source of truth: `ADVANCED_DEFAULTS` dict in `dashboard_filters.py`
  (every advanced/sector/industry key with its no-op value).
- `_apply_preset` = ADVANCED_DEFAULTS overlaid with the preset's
  `advanced` (full write, all keys).
- `load_screener` = same defaults+overlay pattern (consistency).
- `_reset_filters` and `_init_filter_state` reuse the same dict.

### 9.2 FIX — save actions don't refresh their dropdown (feedback §2)
`Save Screener`, `Save Screener As…`, `Save upload as list`,
`Save SELECTED/ALL as list` don't `st.rerun()`, so the new entry is
invisible until an unrelated interaction. Fix: session_state `_flash`
message + `st.rerun()` (flash rendered at the top of the next run — keeps
the success feedback that a bare rerun would swallow, matching the delete
buttons' refresh behavior).

### 9.3 FIX — "Ioa's Lists" mislabeled (feedback §3, option a)
No curated corpus exists (§9.4), so the upload slot must not carry the
built-in brand. Rename tb2 label to "Upload list (CSV/TXT)". "Ioa's Lists"
is reserved for the future curated source.

### 9.4 OPEN (deferred) — curated/shipped list source (feedback §4)
Unchanged: only when a concrete list (e.g. Recent IPOs, hand-curated
watchlist) is actually needed; then it lives in the repo, versioned, and
takes the "Ioa's Lists" slot.

### 9.5 POLISH (feedback §5)
- `Reset Filters` also clears `save_as_name` / `save_list_name` inputs.
- `_spark_closes(symbol, run_name)`: run name becomes part of the cache
  key (underscore dropped) so a fresh run re-reads updated daily files.

### 9.6 OUT OF SCOPE (feedback §6) — new screeners
VCP, Qullamaggie Suite, Golden Launch Pad, GMMA, ADL/accumulation suite,
Stockbee movers etc. — separate round AFTER the final check, following
TAXONOMY.md's decision rule (each new screener = module under src/leaders
or src/focus + config thresholds + validate.py cross-check + its output
columns become new filters).

### 9.7 Verification
AppTest scenarios: (1) leak — set adv_rti_dots + sel_sector, apply preset,
assert all 13 advanced keys back at defaults; (2) refresh — Save Screener
As… 'tmp_check' appears in My Screener options immediately, then delete it;
(3) tb2 label has no "Ioa's" branding; (4) reset clears the two name
inputs. Existing 9/9 validate.py suite stays green.

**Results (2026-08-25): all four scenarios PASS** — (1) rti_dots=False,
sector=[], min_count=0 after preset switch; (2) 'tmp_check_xyz' in My
Screener options immediately + flash message rendered (then deleted);
(3) uploader label is 'Upload list (CSV/TXT)', no Ioa's branding;
(4) both name inputs '' after reset. validate.py 9/9. One incidental fix:
the flash renderer initially used an invalid `if pop() as x:` syntax —
corrected to a plain assignment.

## 10. Fix round 2 (feedback_2.md, 2026-08-25)

### 10.1 FIX §0 (CRITICAL) — 7/8 presets broken by key-name mismatch
The §9.1 refactor introduced `ADVANCED_DEFAULTS` with `adv_`-prefixed keys,
but `PRESETS` still used the pre-refactor short names (`leaders`, `stages`,
`max_ext`, `min_rs`, `rti_zone`, `leaders_mode`). `_apply_preset`'s
`dict.update()` therefore added never-read keys and every `adv_*` stayed at
its empty baseline → leaders/stage/max-ext/rti gates silently skipped
(Minervini showed 2,256 instead of 391; CANSLIM/SCOOTER the whole universe).
- Fix: rename PRESETS' advanced keys to the `adv_` names so the generic
  merge works (option a from the feedback — no translation table to rot).
- Guard: validate.py behavioral check extended to ALL 8 presets — each
  preset's mask must equal its explicitly hand-written manual-filter
  equivalent (e.g. Minervini 8/8 (liquid) == in_minervini & ADV$>=1M;
  SCOOTER >= 90 == in_scooter; Weinstein == stage∈{2A,2B} & both
  exts<=2.0 & ADV$>=1M; ...). A preset whose advanced keys don't resolve
  can no longer pass.
- load_screener key handling confirmed consistent by construction
  (captures use ADVANCED_DEFAULTS keys) and now proven by the round-trip
  test in 10.2.

### 10.2 FIX — custom slider ranges lost in Save Screener → My Screener
`_current_panel()` captured the literal string 'Custom…' while the bounds
lived in `custslider_{k}`; the saved JSON dropped them and the reload
rendered the slider at family defaults (silent loss of the ADR>=6% gate).
- `_current_panel()`: when `sel_{k} == 'Custom…'`, store
  `('custom', lo, hi)` from `custslider_{k}` (mirror of `_apply_preset`).
- `_apply_preset`: accept tuple OR list for custom values (JSON turns
  tuples into lists on disk).
- My-Screener apply block: same special case — custom value sets
  `sel_{k}='Custom…'` + `custslider_{k}` bounds.
- validate.py: save→load round-trip case (panel with a custom range must
  survive JSON unchanged).

### 10.3 Commit the AppTest suite (feedback §"Not independently verified")
`test_dashboard_app.py` — runnable (`python3 test_dashboard_app.py`),
covers: boot 0 exceptions, preset application counts, advanced-leak
regression (round-1 §1), save→dropdown refresh, reset clears name inputs,
custom-range round trip through the UI state. PASS/FAIL summary + nonzero
exit on failure, like validate.py.

### 10.4 Verification
All 8 presets behaviorally checked against manual masks; round trip green;
test_dashboard_app.py all-PASS; validate.py stays green. New screeners
still out of scope (feedback_2.md Recommendation: §0 → custom range →
then new screeners).

**Results (2026-08-25):**
- validate.py **10/10** — incl. `ALL 8 presets == manual filters`
  (Minervini 8/8 liquid=365, Weinstein 2A/2B=972, CANSLIM=141, SCOOTER=366,
  Tight consolidation=2144, Leaders not extended=306, Momentum Leader=38,
  Large-cap pullback=361) and the save/load custom-range round trip
- test_dashboard_app.py **9/9** — UI preset counts match data-level counts
  exactly (365/366/141), leak regression clean, custom bounds restored in a
  fresh session (sel_adr='Custom…', custslider=(6.0, 60.0)), save-refresh
  and reset behaviors intact
- Two test-side fixes during authoring (not app bugs): AppTest's
  session_state proxy has no `.get()`; and the leak assertion must compare
  against baseline+preset-overlay (SCOOTER legitimately sets
  adv_leaders=['scooter']), not bare defaults.

## 11. New screeners round (more_screeners.md backlog, 2026-08-25 overnight)

Ordered backlog, autonomous execution authorized by the doc itself
("move straight on to the next task without waiting"). Prerequisite
confirmed: feedback_2 resolved (user), validate.py 10/10,
test_dashboard_app.py 9/9 (preset spot-checks are part of that suite).

Judgment calls made autonomously (overridable):
- J1 Task 1: source thresholds kept verbatim (9M shares etc.),
  config-configurable; they will match few tickers in this universe.
- J2 Task 2: rolling linear-regression slope (new vectorized helper) —
  the reference's math, NOT slope_pct (% change).
- J3 Task 3: ADTV skipped if it duplicates adv50_dollar (documented).
- J4 Task 4: GMMA as categorical gmma_state (doc's own guidance).
- J5 web_search unavailable (no API key); TradingView originals fetched
  via pine-facade curl (proven pattern).

### 11.1 Task 1 — Stockbee Movers (3 sub-screeners)
Module `src/leaders/stockbee_movers.py`: boolean cols `in_9m_movers`,
`in_weekly_movers`, `in_daily_gainers` + numeric `rel_volume_today`,
`weekly_gain_pct`, `daily_gain_pct` (reuse `gain_5d` where identical).
Weekly mover = close_t vs open_{t-4} (5 trading days), per source.
Config: STOCKBEE_* thresholds cited to metaData_v1 stockbee_screener.py.
validate.py: per-sub-screener behavioral check — direct pandas mask from
the bullet conditions vs module output (same-day, same data).
Dashboard: 3 advanced checkboxes + columns in view_cols.

### 11.2 Task 2 — Golden Launch Pad
Fetch original pine (pine-facade DvE0wDfI) for fidelity. Module
`src/leaders/gold_launch_pad.py`: `in_gold_launch_pad` +
`glp_spread_score` (1 - spread/1.0 clipped [0,1]; Strong>=0.7 flag).
New helpers in indicators.py: rolling linreg slope (vectorized via
rolling covariance), z-score spread of 3 EMAs vs their own 50d stats.
Config: GLP_* cited to TradingView DvE0wDfI + metaData_v1 source.
validate.py: numeric cross-check vs metaData_v1 GoldLaunchPadScreener on
a handful of tickers (isolated subprocess, like ATR/stage checks).

### 11.3 Task 3 — Volume + ADX filter columns
Columns: rvol_today (vol/20d avg vol — may equal rel_volume_today from
Task 1: reuse, don't duplicate), vroc (volume ROC-12), mfi (14),
adx14/+di14/-di14 (Wilder; port from metaData_v1 adx_report.py's
calculate_adx_indicators which already exists in metaData_v1).
Skip ADTV if == adv50_dollar (J3). FILTER_SPECS + THRESHOLD_FAMILIES
entries for each. validate.py numeric cross-checks vs metaData_v1.

### 11.4 Task 4 — GMMA
12 EMAs (3/5/8/10/12/15 short; 30/35/40/45/50/60 long). Columns:
`gmma_state` categorical (bullish/bearish/compressing/expanding/
transitioning) + `gmma_short_spread`, `gmma_long_spread` numerics.
State rules: all short>all long = bullish (reverse = bearish);
compression = group spread shrinking vs its own history; expansion =
widening; else transitioning. validate.py behavioral check on
synthetic data (constructed series with known state) — the source is a
state machine, synthetic fixtures are the honest check.

### 11.5 Task 5 — Qullamaggie Suite
New MA columns sma20/sma100 (config). Perfect stack flag, RS>=97
percentile across 1w/1m/3m/6m momentum (cross_sectional_percentile of
each horizon, min), ATR-relative strength percentile vs mktcap>=1B
universe, price in upper half of 20d range, mktcap>=1B.
`in_qullamaggie` + component numerics. validate.py behavioral check.

### 11.6 Task 6 — Volume anomaly detectors
Read the 3 source files together first; port the statistical spike
detection (z-score based) as `volume_anomaly` flag + `volume_zscore`
numeric. validate.py behavioral check on synthetic spike data.

### 11.7 Task 7 — ADL 5-step suite (last, biggest)
Port ad_line/ package pipeline: ADL line -> momentum -> short-term ->
MA analysis -> composite score. `adl_composite_score` numeric + flags
per step thresholds. validate.py cross-check vs metaData_v1 package on
shared tickers.

### 11.8 After each task
Full validate.py + test_dashboard_app.py green; run_screeners.py
regenerated; dashboard view_cols/advanced filters updated; commit-scale
summary in the run notes. Open questions for morning review collected
in §11.9.

### 11.8.1 Results (2026-08-25, all 7 tasks done)
- validate.py **21/21**; test_dashboard_app.py **9/9**
- Full-run counts: Stockbee 9m=29 weekly=19 daily=41 | GLP=500 (strong=721)
  | Qullamaggie=23 (ma_stack=346) | volume anomaly=33 | ADL accumulation=9
- Cross-checks vs metaData_v1 (isolated subprocesses): GLP passing-set
  identical on 8 tickers; volume/ADX worst rel diff 2.9e-04 (Wilder seeding);
  ADL worst rel diff 1.1e-03 (rounding)
- Bugs found & fixed during Task 4/7 authoring: axis=1 reductions collapse
  the ticker dimension (GMMA group stats -> fmin/fmax chains); single-column
  frames turn iloc[-1] into scalars (_last helper); ADL monthly sampling is
  22-BAR steps backwards (not calendar months); source % change uses
  abs(previous) denominator; source separation uses abs(quotient)

### 11.9 Open questions for morning review (non-blocking, defaults chosen)
- Q1 Task 1: keep 9M-share threshold verbatim (matches few tickers
  here)? Default: yes, configurable. Loosen to e.g. 1M if you prefer.
- Q2 Task 5: RS>=97 across ALL four horizons (min) vs average? Default:
  min (stricter, matches "RS >= 97 across 1w/1m/3m/6m" reading).
- Q3 Task 7: composite-score flag thresholds — source's own or
  percentile-based? Default: source's, percentile column alongside.

## 12. Fix round 3 (feedback_3.md, 2026-08-25) — presets for the new screeners

User decisions: skip both optional presets (GMMA-state, volume-anomaly —
they stay Advanced filters); Qullamaggie preset relies on the flag's own
$1B gate (no redundant mktcap selection — a $2B bucket would over-restrict
vs the methodology); names as suggested with the shared "Stockbee " prefix.

### 12.1 Six new PRESETS entries (exact adv_ keys)
- Stockbee 9M Movers — {adv_9m_movers: True} (9M-share rule is its own
  liquidity gate; no extra floor)
- Stockbee 20% Weekly Movers — {adv_weekly_movers: True}
- Stockbee 4% Daily Gainers — {adv_daily_gainers: True}
- Golden Launch Pad — {adv_gold_launch_pad: True} + selections {'adv': '> $1M'}
  (liquidity floor per the structural-preset convention)
- Qullamaggie Suite — {adv_qullamaggie: True} (flag encodes the $1B gate;
  documented in the preset comment)
- ADL Accumulation — {adv_adl_accumulation: True}

### 12.2 Behavioral checks
- validate.py `apply_advanced` extended: boolean adv flags -> their
  `in_*` columns; adv_gmma_state -> isin. EXPECTED table +6 manual
  equivalents (flag presets: the mask IS the column, ANDed with the
  liquidity selection where present).
- test_dashboard_app.py preset-count loop extended with 'Stockbee 9M
  Movers' and 'ADL Accumulation' (UI count == data-level count).

### 12.2.1 Results (2026-08-25)
- PRESETS: 14 entries, zero adv_-key mismatches (verified programmatically)
- validate.py: `ALL 14 presets == manual filters` PASS — Stockbee 9M=29,
  weekly=19, daily=41, GLP=409 (=500 ∩ ADV$>=1M), Qullamaggie=23, ADL=9
  (plus the original 8 unchanged)
- test_dashboard_app.py **11/11** — preset-count loop extended with
  'Stockbee 9M Movers' (ui=29=data) and 'ADL Accumulation' (ui=9=data)
- One real bug caught by the new behavioral check itself: validate's
  apply_advanced mapped adv_x flags to column 'x' instead of 'in_x' —
  flag presets silently no-op'd (preset=3961). Fixed; the check now
  catches exactly this class of regression, as designed.
- NOTE (temporary, per user): the daily-data update running this morning
  leaves the archive in a mixed state (some tickers have a 2026-08-24
  bar, others end 08-21). The 6 validate failures outside the preset
  checks (Weinstein-vs-lkm_rs, RTI zones, GLP/MFI/ADL cross-checks,
  anomaly spike) are data-mix artifacts — they were green pre-update and
  will return green when the download completes. The preset checks are
  immune (they read the 2026-08-25 results snapshot, evaluated at the
  last complete day).

### 12.3 Not added (per feedback + user)
- GMMA-state and volume-anomaly presets (optional, skipped by decision).
- Volume+ADX raw-column presets (feedback: "do NOT add").
- Naming: as suggested; dropdown stays scannable via the Stockbee prefix.

## 13. Round: Timing Signals tab (feedback_4.md Tasks 1-4, checkpoint)

User decisions: read data AS-IS (no cutoff — temporary mixed state is
background noise; instead every output row carries its own as-of bar
date); CHECKPOINT after Task 4 for review before GLB/Patterns (tasks 5-7).

### 13.1 Task 1 — Dr. Wish Blue/Black Dot (src/timing/drwish_dots.py)
Stochastic %K(10) = 100*(C-LL10)/(HH10-LL10), fillna(0) (source :82-97).
Blue Dot (latest bar): stoch[yesterday] < 20 AND stoch[today] > 20 AND
SMA50 rising (diff > 0). Black Dot: min(stoch[last 3 bars]) <= 25 AND
close > prev close AND (close > SMA30 OR close > EMA21).
Columns: in_blue_dot, in_black_dot + stoch_k, stoch_k_prev,
min_stoch_lookback, as_of (per-ticker last valid bar date).
Config DRWISH_* cited to drwish_screener.py:51-64,314-418 (daily
multiplier = 1.0).

### 13.2 Task 2 — PVB state machine (src/timing/pvb.py)
Indicators: Price_Highest/Lowest (30d), Volume_Highest (30d), SMA(50)
(prev-bar values gate the breakout, per source). State machine per
ticker (Long and Short): Buy = C > prev Price_Highest & V > prev
Volume_Highest & C > SMA & state != Buy; Sell symmetric; while Buy,
close < SMA increments consecutive_days -> "Close Buy" at 5 (symmetric
for Sell). Params 30/30/50/5 cited to pvb_screener.py +
metaData_v1/user_data.csv (runtime config).
Columns: pvb_signal, pvb_days_since_signal, pvb_signal_price,
pvb_performance_since_signal, pvb_signal_date, as_of.

### 13.3 Task 3 — ATR1 cloud (src/timing/atr1_cloud.py)
vol_stop recursive (atr1_screener.py:41-85): TR -> Wilder RMA ATR(20);
atr_m = ATR*factor(3.0); max/min carried; stop = max(prev, max-atr_m)
in uptrend else min(prev, min+atr_m); NaN stop -> src; uptrend =
src-stop >= 0; on flip reseed max/min/stop. Second stop factor 1.5.
crossUp/crossDn = vStop2 crossing vStop. Per-ticker numpy-array loop
(not .iloc — per more_screeners_2.md).
Columns: atr1_trend (uptrend/downtrend), atr1_stop_level (vStop),
atr1_stop_level2 (vStop2), atr1_cross_up, atr1_cross_dn, as_of.
Config ATR1_* cited to atr1_screener.py:41-107 (length 20, factor 3.0,
length2 20, factor2 1.5).

### 13.4 Task 4 — Timing Signals tab + shared on-demand plumbing
New `src/on_demand.py`: scope resolution (index membership via the
existing universe_index_map + min market cap via screener_results'
market_cap), scope_key builder, per-ticker run wrapper with
st.progress("Processing i/n"), same-day cache
(results/{date}/{tab}_{scope_key}.csv — check before run, write after).
Tab (dashboard.py): scope selects (default S&P 500, widen warns),
source multiselect (PVB/ATR1/Blue Dot/Black Dot), Run, state filter
(source-dependent multiselect), max-days-since slider, results table
(sorted by days_since, spark column), Download CSV, Save as list.
NOT wired into run_screeners.py or screener_results.csv.

### 13.5 Checks
validate.py: dots — module vs manual boolean conditions on sample
tickers; pvb — module final state vs an independently written reference
loop; atr1 — exact cross-check vs metaData_v1 calculate_atr_cloud
(subprocess, like GLP/ADX). test_dashboard_app.py: Timing tab renders,
Run (Blue Dot, smallest scope) produces results, second Run reuses cache.

### 13.6 Checkpoint
Stop for user review before Tasks 5-7 (GLB/Patterns). TAXONOMY.md gets
the tier-model section at this checkpoint.

**Results (2026-08-25): Tasks 1-4 complete, checkpoint reached.**
- validate.py **25/25** — incl. drwish blue/black dot module==manual masks
  (2 genuine Blue Dots + 2 Black Dots on the 5-ticker sample), PVB module
  == independently-written reference state machine (5/5 tickers), ATR1
  cloud exact vs metaData_v1 calculate_atr_cloud (stops within +-0.01)
- test_dashboard_app.py **16/16** — incl. 5 new Timing-tab checks: boot,
  Run completes (NASDAQ 100 scope, 4.7s cold), results rendered (105
  signal rows: 96 ATR1 + 7 Black Dot + 2 Blue Dot), scoped results
  persisted (timing_signals_nasdaq100_cap0.csv), re-run bounded
- Files: src/timing/{drwish_dots,pvb,atr1_cloud}.py, src/on_demand.py
  (shared scope/run/progress/persist plumbing), Timing Signals tab in
  dashboard.py, TAXONOMY.md tier-model section
- Data-update note: modules read data as-is (no cutoff, user decision);
  each output row carries its own as_of bar date, so mixed-freshness is
  visible per row. The 2026-08-24 bar arrived mid-round for some tickers
  (AAPL/MSFT show as_of=2026-08-24, others 08-21) — visible, not hidden.
- NOT done (checkpoint): Tasks 5-7 (GLB incremental cache, Cup & Handle
  presets, Patterns tab) — awaiting user review of the new architecture
  before the risky GLB investment.

### 13.9 Tasks 5-7 results (checkpoint approved, 2026-08-25)
- Checkpoint verified by the user (both suites independently re-run);
  one cleanup item fixed first: index-map functions deduped to a single
  source of truth in src/on_demand.py (dashboard wraps with st.cache_data)
- **Task 5 GLB** (`src/patterns/glb.py`): vectorized cold path
  (rolling-max pivot test + broadcast breakout scan) + incremental
  per-ticker JSON cache (results/glb_cache/{SYM}.json: records + through-
  bar + close fingerprint — a history rewrite invalidates via fingerprint
  mismatch; params hash invalidates on parameter change). Cross-check:
  GLB records IDENTICAL to metaData_v1 on AAPL+MSFT. **Measured
  S&P-500-scoped run: cold 3.4s / warm 3.4s (7ms/ticker)** — the
  slow-button risk is eliminated, measured not assumed
- **Task 6 Cup & Handle** (`src/patterns/cup_handle.py`): K-A-B-C-D
  port (find_peaks extrema -> first constructible candidate -> cup/handle
  validations -> verbatim quality score -> stage/target/stop) with three
  config presets (Strict = O'Neil textbook; Default = midway; Loose =
  patterns_v0 daily config verbatim, explicitly labeled permissive).
  Verified with a SYNTHETIC cup & handle fixture: all three presets
  detect it, geometry identical to patterns_v0's own detector
  (depth 20.15%, handle 27.37%, breakout stage)
- **Task 7 Patterns tab**: radio GLB/Cup & Handle; GLB sliders (pivot
  strength, lookback incl. 'complete', confirmation); C&H preset radio;
  shared scope/Run/progress/persist; per-params cache keys
  (patterns_glb_{scope}_{hash}.csv); breakout-only result view
- validate.py **28/28**; test_dashboard_app.py **20/20** (incl. Patterns
  GLB/C&H runs + 508-ticker cache population)
- AppTest stability lesson (generalized): widgets that appear/disappear
  across runs break AppTest replay — the Timing state filter now renders
  permanently with pre-registered session keys and per-run value clamping

### 13.10 Follow-up (user checkpoint note): Timing re-run timing
User observed the Timing 're-run stays fast' measurement drift from
~4.1-4.4s to ~20-21s with warm no longer beating cold. Investigation:
- Isolated perf_counter breakdown (outside Streamlit): resolve 0.02s +
  data load 1.36s + compute 2.77s = 4.15s total — the pipeline matches
  the checkpoint numbers; the ~20s was AppTest re-rendering the whole
  dashboard per run plus box load, NOT a pipeline regression
- BUT the review surfaced a real structural flaw: the Run flow loaded
  all price data BEFORE checking the results cache, so an explicit Run
  always paid the data reload — the same-day cache never actually
  short-circuited anything on a clicked Run
- FIXED in both tabs: cache check now happens FIRST on Run (before any
  data load); 'Force re-run' bypasses it. Measured: same-day-cache Run
  0.22s (was ~20s), Force re-run 2.21s (full recompute when requested)
- FOLLOW-UP class fix (same bug family, proactively): cache KEYS must
  cover every result-affecting input. Two gaps fixed:
  (a) Patterns GLB key hashed only pivot_strength+confirmation — the
      lookback CHOICE is now hashed (lookback_bars resolves only after
      data load, so the widget state is what gets hashed); verified: 3m
      and 6m runs produce distinct cache files, each a real recompute
  (b) Timing scope key did not include the selected SOURCES — switching
      Blue Dot -> ATR1 served the old source's cached file; the key now
      appends the sorted source list. Verified: distinct cache files per
      source, and the UI suite's re-run check now reads cold=18.5s /
      warm=0.6s — warm beats cold by 30x, which is the same-day cache
      actually working (the exact symptom the user flagged)
- REVIEW round-2 fixes (user's re-review of the cache-key fixes):
  (a) the stale unsuffixed artifact
      (timing_signals_nasdaq100_cap0.csv) was DELETED, and the suite's
      persistence check now builds the expected source-suffixed name via
      the shared on_demand.sources_slug() helper (single source of truth
      for the convention) and additionally asserts the unsuffixed
      artifact is never recreated — a filename-logic break can no longer
      pass off a stale file
  (b) the 1y-vs-2y distinct-key regression is now a PERSISTED test:
      test_dashboard_app.py computes each expected GLB filename
      independently (mirroring the app's hash formula with the true
      widget defaults — pivot 10, confirmation '1w'->5) and asserts the
      app served exactly that file for each lookback (1y->4c0b0535,
      2y->c690c161, distinct)
  - residual, documented: the GLB pt_ph hash formula itself remains
    inline in dashboard.py with a mirrored replica in the test (3 lines,
    commented); if it ever changes, the distinct-file assertion fails
    loudly rather than silently
- REVIEW round-3 fix (user's C&H preset-key verification surfaced a test
  bug): the at4 radio loop set pt_pattern and pt_ch_preset from one stale
  element collection — after the pattern switch the C&H preset radio is a
  NEW widget, so its set_value replayed against the old tree and the
  'loose' run silently ran strict (overwriting the strict file; the loose
  persistence check then failed on a genuinely missing file). Test fixed:
  re-fetch at4.radio after the pattern switch. Verified clean-slate:
  loose -> patterns_..._loose.csv (43 patterns), strict -> ..._strict.csv,
  both under their own keys. UI suite 26/26

## 15. feedback_7.md — 5 scans from more_screeners_3.md (2026-08-25)

All 5 are same-day snapshot computations -> daily full-universe batch
(run_screeners.py -> screener_results.csv -> All Results filter panel).
Confirmed zero on_demand references in run_screeners.py (architecture
note honored). New advanced-filter keys all registered in
ADVANCED_DEFAULTS from the start (feedback_2 §0 discipline); the leak
regression test now also injects adv_ema20_pullback as a leftover.

1. **RSI 14 — filter**: `rsi14` column (config.RSI_PERIOD=14, Wilder);
   main-panel threshold filter (new 'rsi' family: <30/30-40/40-50/50-60/
   >70 + Custom slider); validate: hand-written SMA-seeded Wilder
   recursion cross-check (converged, diff < 0.01) + [0,100] bounds
2&3. **52w high breakout / low breakdown — event-flag filters**:
   today's high > prior 252-bar high (shift(1)); low symmetric. Two
   advanced checkboxes; validate: identity checks (flag == today's
   high/low IS the trailing 252-bar extreme)
4. **EMA20 pullback — screener** (`src/leaders/ema20_pullback.py`):
   SCTR>75 + open>EMA20 + low<EMA20 + close>EMA20 + EMA20 rising
   (5-bar point-to-point, chosen over OLS — documented); outputs
   in_ema20_pullback + ema20; validate: module == manual 5-condition mask
5. **Downtrend reversal — screener**
   (`src/leaders/downtrend_reversal.py`): high > high.shift(1) after 6
   strictly declining daily highs; validate: module == manual chained-
   shift mask
- Excluded per the feedback: Scan #1 (intraday-blocked), metaVolume
  HVE/HVD, presets for any of the 5
- Full-run counts: ema20_pullback=55, downtrend_reversal=16
- Suites: validate.py **34/34**, test_dashboard_app.py **29/29**
- Two cosmetic FutureWarnings fixed en route (stockbee pct_change
  fill_method, ADL mfm astype(float))

## 14. feedback_6.md — GLB Confirmation '3m' option (2026-08-25)
Single-parameter addition per the user's domain judgment (long lookbacks
want longer confirmation windows): '3m' added to the Confirmation
selectbox with 63 trading days, matching the Lookback dropdown's own
'3m': 63 day-count convention. No cache-key work needed —
confirmation_bars was already hashed correctly from the start (unlike
the lookback_bars bug in feedback_5).
- DoD verified: 1m vs 3m runs produce DISTINCT cache files
  (beb243f6 vs c05b03b2 — a 21-for-63 config typo would fail this)
- Suites: validate.py 28/28, test_dashboard_app.py 29/29

## 16. Cup & Handle fidelity — breakoutwatch.com alignment (2026-08-29)

**Status: Tasks A–H DONE (2026-08-29, unsupervised — user review pending).
Task I deferred (needs outcome data).**

Context: reconstructed breakoutwatch.com's C&H + CANSLIM methodology from
Wayback captures (`cup_handle_ideas/cupAndHandle/lit/`; digest in
`lit/breakoutwatch_methodology.md`; full gap analysis in
`dashboard-screener/research/breakoutwatch_alignment.md`).

`src/patterns/cup_handle.py` (§13.9 Task 6) is a generic K-A-B-C-D geometric
detector (find_peaks on close). breakoutwatch's *published spec* (not code —
we don't have their source) is more complete and outcome-validated (2017
discriminant model on real alert outcomes since 2014). Their geometric gate is
actually LOOSER than our `strict` preset — the value is in specific ADDITIVE
pieces below. The detector core (K-A-B-C-D geometry + measured-move
`target = resistance + cup_height`) stays; these tasks enrich it.

Ordering = highest false-positive reduction first. Each task: config keys per
preset (strict/default/loose), a `validate.py` behavioral check on a synthetic
fixture, new output columns wired into the Patterns tab.

### 16.1 Task A — Setup-gain / prior-uptrend gate  [priority 1]
Require the rise from a pre-cup low to the left rim `close[a]` >= threshold
(breakoutwatch: >= 30%; O'Neil: "prior uptrend >= 30%"). Today `k` is only
"the peak before `a`" with no magnitude test — the single biggest
false-positive source. Between `k` and `a` find the min low; gate on
`(close[a] - low) / low`. New key `CUPHANDLE_PRESETS[*]['setup_gain_min']`
(strict 0.30, default 0.20, loose 0.0). validate: synthetic fixture with a
sub-threshold run-up rejected by strict, accepted by loose.

### 16.2 Task B — Absolute pivot recency cap  [priority 2]
Emit `days_since_right_rim` (= `n - 1 - c` bars) and gate on `pivot_max_age`
(breakoutwatch: pivot within 90 days, cup <= 325 days). Surfaces actionable
setups vs stale ones. Currently only relative `cup_max_duration` exists.

### 16.3 Task C — Explicit cup:handle length ratio  [priority 3]
Gate `(c - a) / max(d - c, 1) >= ratio` (breakoutwatch: >= 3; also implies
handle <= 1/3 cup). Currently only implicit via `handle_max_duration`.
Key `cup_handle_ratio_min` (strict 3.0, default 2.0, loose 0.0).

### 16.4 Task D — Handle-midpoint >= base-midpoint rule
Named alternative to `handle_position_min`:
`(close[c] + close[d]) / 2 >= (close[a] + close[b]) / 2`. NOTE: our `strict`
preset (`handle_position_min = 2/3`) is already STRICTER than breakoutwatch's
actual rule — this is a looser, spec-faithful option, not a tightening.
Key `handle_midpoint_rule` (bool per preset).

### 16.5 Task E — HQ-style handle volume scoring  -> quality score
Iterate handle days `c..d`, score each on the price/volume quadrant
(price-down + volume-down = "very desirable" = max; price-up + volume-up =
"unfavorable" = min), weight recent days heavier, normalize. Bonus: latest
close up & vol >= avg -> +1; & vol >= prior day -> +0.5. New `handle_quality`
sub-score feeding a revised `quality`. Source: `lit/Chart Quality.html` (HQ
2x2 matrix).

### 16.6 Task F — RCQ-style right-side volume scoring  -> quality score
Score each day `b..c` on up-move-on-above-average-volume (demand), recent
days weighted heavier, normalize -> `right_cup_quality` sub-score.
Source: `lit/Chart Quality.html` (RCQ).

### 16.7 Task G — Volume-confirmed breakout flag
breakoutwatch alert = price >= pivot AND volume >= 1.25-1.5x ADV. Today
`stage == 'breakout'` fires on `close > resistance` alone. Add
`breakout_volume_confirmed` bool (latest volume >= `breakout_volume_factor` x
vol MA — the constant already exists in every preset, just unused for stage
gating).

### 16.8 Task H — intraday high/low extrema  [optional, larger]
Use the high series for `a`,`c` and the low series for `b`,`d` instead of
close (O'Neil purists + breakoutwatch use intraday). Larger change —
`evaluate` currently pulls only `data['close']` / `data['volume']`. Document
as a known deviation if deferred.

### 16.9 Task I — outcome-trained ranker  [future, needs outcome data]
If pattern outcomes ever get logged: LDA/logistic on {momentum slope,
momentum, prev-day price+volume rise, volume %-of-50d-avg, earnings
acceleration}. breakoutwatch's ranked factors — momentum slope #1, RS rank
weakest (they dropped their RS >= 92 requirement over it). Would replace the
current hand-weighted `quality` formula. Out of scope until a feedback loop
exists; noted so the hand-weights aren't mistaken for validated.

### 16.10 Not in scope
Trading rules (entry / trailing-stop / position sizing) — breakoutwatch has
detailed ones (3-10% trailing stops, 2 positions @ 50%), but entries/exits
are out of scope per intro.md. `target` / `stop` outputs stay as reference
levels only.

### 16.11 Companion: canslim.py additions + a CE/CANTATA preset (separate)
Not C&H. Full CET+CEF item -> project-column mapping, the 4 real gaps
(industry rank, U/D volume ratio, plus the CEF fundamentals), and a
copy-paste sketch for both a cheap partial `ce_partial` (0-8, from columns
that already exist) and the full 0-18 `ce_score`:
**`research/breakoutwatch_ce_mapping.md`**. CE is stock-level and
pattern-independent — it becomes a preset ("CANTATA CE >= N"), not a change
to the pattern detector. `canslim.py` additions (ROE >= 17%, sales growth
>= 25% + accel, forward est, net-margin = 3-FY max, cash flow) feed CEF.
Keep our YoY "C" (more faithful than their CEF1). Strengthen "I" only if
13F / quarterly holder counts become available. **NOT STARTED.**

### 16.12 Results (2026-08-29, Tasks A–H — unsupervised, review pending)

Implemented in `src/patterns/cup_handle.py` + `config.py` CUPHANDLE_PRESETS.
The kanwalpreet18 geometric core is untouched; every §16 gate is
**non-binding for Loose** (`setup_gain_min` 0, `pivot_max_age` 1e9,
`cup_handle_ratio_min` 0, `handle_midpoint_rule` off, `use_intraday_extremes`
off, `candidate_selection` 'first') — so Loose stays byte-identical to
patterns_v0's daily config.

- **A setup-gain gate** — `config.CUPHANDLE_SETUP_LOOKBACK` (252) bars before
  the left rim scanned for the prior low; `(rim - prior_low)/prior_low >=
  setup_gain_min` (strict 0.30, default 0.20). Reported as
  `cup_handle_setup_gain_pct_{preset}` even when non-gating.
- **B pivot-recency cap** — `cup_handle_days_since_rim_{preset}` = bars from
  the right rim; gate `> pivot_max_age` (strict 90, default 150). REQUIRED a
  companion change: `_all_pattern_points` now returns EVERY constructible
  K-A-B-C-D and Strict/Default use `candidate_selection='recent'` (freshest
  right rim first, take the first that passes) — otherwise the cap just
  nulled out the earliest-candidate pick on multi-year histories. Loose
  keeps `'first'` (validate only the earliest constructible candidate,
  exactly like patterns_v0).
- **C cup:handle ratio** — `cup_handle_ratio_{preset}` = `(c-a)/max(d-c,1)`;
  gate `< cup_handle_ratio_min` (strict 3.0, default 2.0).
- **D handle-midpoint rule** — `handle_midpoint_rule` (strict/default on):
  reject if `(rim_c + handle_low)/2 < (rim_a + base_low)/2`.
- **E HQ / F RCQ / CQ** — `cup_handle_hq_{preset}` / `cup_handle_rcq_{preset}`,
  recency-weighted price/volume quality (breakoutwatch Handle Quality 2x2 and
  Right Cup Quality); folded into the quality score as `+max(0,rcq)*10` and
  `+max(0,hq)*10` (HQ carries the breakout-foreshadow bonus). Plus
  `cup_handle_cq_{preset}` = breakoutwatch **Chart Quality** = RCQ+HQ blended,
  weight shifting toward HQ as the handle lengthens (`w_hq = 0.40 + 0.30 *
  min(handle_dur/20, 1)`). CQ is **report-only** — not a gate, not in the
  quality score. RCQ/HQ/CQ are pattern-window metrics (B→C, C→D), so they
  mean nothing without a detected pattern; the stock-level CANTATA (CE/CET/
  CEF) scores are a separate non-pattern concern —
  `research/breakoutwatch_ce_mapping.md`.
- **G volume-confirmed breakout** — `cup_handle_breakout_vol_confirmed_{preset}`
  bool: stage=='breakout' AND latest volume >= `breakout_volume_factor` x
  vol MA.
- **H intraday extremes** — `use_intraday_extremes` (strict/default on):
  rims off the daily HIGH, bottoms off the daily LOW when `data['high']` /
  `data['low']` are supplied (dashboard path); falls back to close when not
  (validate's close-only synthetic). NOTE: "intraday" = the daily bar's
  high/low (the intraday extreme of that session), NOT sub-daily bars —
  which we don't have and this doesn't need.

New per-preset columns: `cup_handle_setup_gain_pct`, `cup_handle_days_since_rim`,
`cup_handle_ratio`, `cup_handle_hq`, `cup_handle_rcq`, `cup_handle_cq`,
`cup_handle_breakout_vol_confirmed`. Dashboard picks them up automatically
(`view_cols_pt` = any column containing the preset name).

**Verification:**
- validate.py **36/36** — the synthetic fixture's seg0 steepened 80->72
  (>=30% prior advance, so strict's Task A gate passes; kept identical in
  `validate.py` and `validate_ch_ref.build_synthetic`). New check
  `C&H §16 gates`: each gate reports on the good fixture and rejects when its
  own threshold is made impossible (setup 0.99 / age 1 / ratio 99 /
  midpoint-on with a deep-low-handle variant). `C&H vs patterns_v0
  (synthetic)` still exact (Loose depth 20.15, unchanged).
- test_dashboard_app.py **29/29** — Patterns tab C&H run + per-preset cache
  keys intact.
- Real data, unchanged Loose (candidate_selection='first' + non-binding
  gates): NASDAQ 100 loose 43->43, S&P 500 loose 226->226 (byte-identical
  counts). Strict: NDX 0, SPX 1 (textbook-rare, as expected). Default (the
  useful working list): NDX 6, SPX 37 — recent cups, days-since-rim 4–18 on
  the freshest.

**Open for review:** threshold calibration (setup_gain 30/20, pivot_max_age
90/150, ratio 3/2); whether `default` should also gate on
`breakout_vol_confirmed`; the HQ/RCQ weight (`*10` each) in the quality
score. Task I (outcome-trained ranker) still needs a logged-outcomes feed.

## 17. CANTATA / CE — stock-level leader score (2026-08-29)

**Status: DONE (2026-08-29, unsupervised — user review pending).** Was §16.11.

breakoutwatch's CANTATA Evaluator (`lit/CE Overview.html`) as a 4th
leaders-slot score, alongside CANSLIM / Minervini / SCOOTER. Full item ->
column mapping + the deviations forced by the yfinance snapshot:
`research/breakoutwatch_ce_mapping.md`. **CE is stock-level, NOT
pattern-anchored** — the opposite of §16's CQ (which stays in the C&H
module). Pattern recognition is untouched by this.

**CE = CET (technical, 0-7) + CEF (fundamental, 0-11) = 0-18.**

- `src/leaders/cantata.py` — `evaluate(context, ud_ratio)`:
  - **CET** from the price context already in `screener_results`:
    `cet_ma` (0-3: price>50dMA + price>200dMA + 50dMA>200dMA, the last as
    `pct_vs_50sma < pct_vs_200sma`); `cet_rs`, `cet_industry` (RS percentile
    within `industry`, ≥3 members else 0.5), `cet_52whigh`, `cet_updown` —
    each a 0..1 linear interp between breakoutwatch's stated worst/best
    (`config.CANTATA_*`).
  - **CEF** reads `financial_data_0_8.csv` directly (like canslim.py) —
    11 pass/fail: `cef_qoq_eps` (2Q YoY ≥18% via qh1/qh2_eps_growth_yoy),
    `cef_pos_eps`, `cef_eps_accel` (qh1>qh2>qh3>qh4 growth), `cef_yoy_eps`
    (y1..y3 each ≥25%), `cef_qoq_sales` (q1 vs q5 rev ≥25%), `cef_sales_accel`
    (sequential QoQ rev rising — documented proxy; snapshot lacks the history),
    `cef_fwd_eps` (forwardEps/trailingEps-1 ≥15%), `cef_institutional`
    (holders ≥5 AND avg_pct_change ≥0), `cef_roe` (≥17%), `cef_cashflow`
    (y1_cashflow_vs_eps_ratio ≥1.2), `cef_margin` (y1 net margin = 3-FY max).
- `src/indicators.py::up_down_volume_ratio` — 50d Σ(up-vol)/Σ(down-vol),
  CET item 5.
- Wiring: `run_screeners.py` computes it in the leaders block, joins
  ~20 columns into `screener_results.csv`, writes `leaders_cantata.csv`,
  adds a dashboard.md line. `in_cantata = ce_score >= config.CANTATA_MIN_CE`
  (12/18).
- **NOT added to the 3-way `combine.union`** — deliberate: the union's
  `n_sources` / focus-list base pool / dashboard leak-tests are all keyed to
  the canonical 3 (Minervini/CANSLIM/SCOOTER). CANTATA is a score column +
  its own list + a preset; folding it into the union is a separate change.
- Dashboard: `'cantata'` added to the Advanced "Leaders lists" multiselect;
  new `adv_cantata` checkbox + `adv_ce_min` slider (0-18); preset
  **"CANTATA CE leaders"** in Ioa's Presets (mirrors `in_cantata`).

**Verification:**
- Full run: **122 / 3961** pass CE ≥ 12 (~3%, a sane leader bar); median CE
  6.0, range [0.01, 15.29]; cet ∈ [0.01, 7.0], cef ∈ [0, 10].
- validate.py **37/37** — new `CANTATA CE: bounds + CET+CEF composition +
  CEF items vs snapshot` (ce == cet+cef, all in range, `cef_pos_eps` /
  `cef_roe` reconstructed from the CSV); "ALL 15 presets == manual filters"
  now includes CANTATA CE leaders (=122).
- test_dashboard_app.py **30/30** — preset-count loop includes
  "CANTATA CE leaders" (ui=122=data).

**Open for review:** `CANTATA_MIN_CE` 12/18; whether CET items should be
graded (current) or pass/fail; `cef_yoy_eps` at 3 FY (data limit) vs
breakoutwatch's 4; `cef_sales_accel` proxy; whether to fold CANTATA into
`combine.union` as a genuine 4th leaders list. The remaining `canslim.py`
enrichment (its own module) is still separate — CEF here already covers ROE
/ sales / margins / forward-est / cash-flow that §16.11 listed for canslim.

## 18. Patterns tab — annotated Cup & Handle chart (2026-08-29)

The breakoutwatch "Anatomy of a Cup-with-Handle Pattern" chart for a
detected ticker, inline in the dashboard. Single source of truth so the
picture always matches the detector:
- `src/patterns/cup_handle_chart.py::figure(ticker, preset, data) -> Figure`
  re-runs cup_handle.py's own candidate selection (`_pick_candidate` calls
  `_find_extrema` / `_all_pattern_points` / `_try_candidate`), then draws
  the 4 stage bands, the labelled K-A-B-C-D points, Cup/Handle span arrows,
  Today marker + stale-pivot note, the Setup-Gain / Cup-Depth / Handle-Depth
  / Pivot-off / RCQ-HQ-CQ / Quality box, the measured-move target + stop
  lines, and a volume panel with a 15-bar envelope. Returns None when the
  detector resolves no pattern. Does NOT set the matplotlib backend.
- `dashboard.py` Patterns tab (C&H only): a ticker selectbox under the
  results table -> `st.pyplot(cup_handle_chart.figure(...))`, loading that
  one ticker's OHLCV on demand.
- `cup_handle_ideas/cupAndHandle/draw_cup_handle.py` is now a thin CLI
  wrapper over the same `figure()` (was a 200-line duplicate).

Verification: test_dashboard_app.py **31/31** — new `C&H annotated chart
renders` check (selectbox present with options; `figure()` returns a
Figure). validate.py 37/37 unchanged.

---

## 19. Confluence tab — badge-count leaders (2026-08-30)

Source idea: @SteveDJacobs watchlist cards (`docs/BADGES/HPCdWeEWEAAXL6q.jpeg`)
— run every screener, invert to per-ticker, show the names lit up by the
most *independent* methods. "Wait for your pitch." It is a **union with a
membership-count sort**, not an intersection.

Decisions (user, 2026-08-30):
1. **Dedicated tab** `🎖️ Confluence` — not a view-mode toggle in All Results.
2. **Opportunistic merge** of on-demand (pattern/timing) badges — no Run
   button on this tab; fold them in only when today's cache already has a
   compatible-scope file, else render without them + a hint.
3. **Rank by `n_families`** (default) — de-correlates "one idea wearing six
   hats" (Minervini / Qullamaggie / GLP / GMMA-bullish all fundamentally
   need strong RS + stacked MAs + uptrend).
4. Legacy `combine.union()` `n_sources` (3 classic leader lists) stays as-is;
   the wider confluence count is new columns, computed in the tab, not in
   the daily batch.

### 19.0 Wiring — what "running the confluence" does

**Nothing runs.** The tab is a pure aggregation over the already-loaded
`full` DataFrame (`load_tables()` → latest `results/YYYY-MM-DD/
screener_results.csv`), structurally identical to the Focus / Leaders tabs.
All 16+ batch badges are `in_*` booleans computed once per day for the whole
universe by `run_screeners.py`; confluence is a vectorized boolean sum over
them (ms). Freshness = last daily batch, shown as a caption; the existing
header **"Re-run screeners"** button is the only way to refresh, and the tab
picks up the new CSV via the normal cache clear. Zero bar-history reads
(the sparkline column stays lazy per visible ticker).

On-demand badges (GLB/Darvas, Cup & Handle, PVB, ATR1, Blue/Black Dot) live
only in the `patterns_*` / `timing_signals_*` same-day cache. The tab reads
those files **if present** for a scope that covers the visible tickers and
merges the signals as extra badges; if absent, the card renders without them
and a note: *"Pattern/timing badges appear here after you run the
Patterns/Timing tabs today for a compatible scope."* `ER-1` (earnings
proximity) is **out** — no earnings-date field exists.

### 19.1 Badge registry — `src/confluence.py`

Single source of truth: `BADGES` = ordered list of specs, each
`(code, label, family, test)` where `test(full) -> pd.Series[bool]`.
`FAMILIES` = ordered list; `CONTEXT` badges render on the card but are
excluded from every count.

| Family | code → source (column in `screener_results.csv` unless noted) |
|---|---|
| **trend_rs** | `MM` in_minervini · `KQ` in_qullamaggie · `GLP` in_gold_launch_pad · `GMMA` gmma_state=="bullish" · `RS90` rs_pct≥90 · `SC` in_scooter |
| **fundamentals** | `ON` in_canslim · `CE` in_cantata |
| **accumulation** | `ADL` in_adl_accumulation · `VOL` in_volume_anomaly · `SB9` in_9m_movers · `SBW` in_weekly_movers · `SB4` in_daily_gainers |
| **breakout** | `52H` in_52w_high_breakout · `NrH` pct_from_52w_high≥−5 · `DB` GLB (on-demand) · `C&H` cup_handle (on-demand) |
| **pullback** | `EMA20` in_ema20_pullback · `REV` in_downtrend_reversal |
| **timing** (on-demand) | `PVB` · `ATR1` (atr1_trend=="uptrend") · `blue` · `black` |
| **context** (not counted) | stage `2A`/`2B`; RTI zone |

Every `test` that reads a column must tolerate the column being absent
(on-demand families) → all-False Series.

### 19.2 Compute — `confluence.compute(full, extra=None) -> DataFrame`

Returns a copy of `full` with added columns:
- `bdg_<code>` bool per badge
- `badges` — list[str] of active codes, in registry order
- `n_badges` — raw count (context excluded)
- `families` — list[str] of families with ≥1 active badge
- `n_families` — **primary rank key**
- `confluence_score` — 0–100, family-capped (≤2 badges counted per family)
  then normalised; smoother circle metric / tie-breaker
- `context` — list[str] (`stage 2A`, `RTI z2` …) for the card

`extra`: `dict[str, pd.Series]` of on-demand signals already reindexed to
`full.index` (built by the tab from cache files); `None` → those families
just stay empty. Null-safe join, no error when a file is missing.

### 19.3 Tab UI — `dashboard.py`

Add `tab_confluence` to the `st.tabs([...])` list (after Focus/Leaders,
before Timing). Controls, mirroring the Timing/Patterns tab idiom:
- **Scope**: index-membership multiselect + min-market-cap `select_slider`
  — filters `full` in place (`IDX_MAP` + `full['market_cap']`); **no data
  load**, unlike Timing/Patterns.
- **Rank by**: `n_families` (default) · `n_badges` · `confluence_score`
- **Min families** slider (0–6, default 3)
- **Must include family** multiselect (empty = no constraint)
- **Cards to show**: 20 / 30 / 50 / 100 (default 30)

Opportunistic merge: for the resolved scope, look for
`on_demand.load_cached(report.run_dir(), 'patterns', …)` and
`'timing_signals'` files whose scope key ⊇ the visible set; when found,
extract `in_glb_breakout` / `in_cup_handle_*` / `atr1_trend` / dot / pvb
columns into `extra`. Caption states which on-demand families are live vs
missing.

### 19.4 Card rendering — the `HPCdWeEWEAAXL6q.jpeg` look

`_confluence_cards(df_top)` builds one `<style>` block + a div per row via
`st.markdown(unsafe_allow_html=True)` (or `st.html`). Per card:
- left **accent bar** — green if day-change > 0 else red
- **ticker** (bold) + day-change %
- sub-line `market_cap · gain_1m · ADR20%` (`$140.4B · +2.1% · 3.6%`)
- **badge pills**, background keyed by family colour, wrapping to a 2nd row
- right: rounded-square = `n_badges`; circle = `n_families`
  (or `confluence_score` when that's the rank key) — both tier-coloured
  (grey / green / yellow / orange by cutoffs)
- `context` shown as faint pills

Render top-N only. Keep a plain `st.dataframe` (badge columns + sparkline,
`on_select` multi-row) below the cards for full sort / CSV / selection —
reuses `_spark_closes`.

### 19.5 Export / lists

`d1` download "Confluence CSV" (`compute()` output, rounded);
`d2` "Save top-N as list" / "Save SELECTED as list" via
`dfil.save_list()`. Identical pattern to All Results.

### 19.6 Strike-zone number — deferred

The colored circle is `n_families` / `confluence_score` only. No
AI-assigned expectancy score (backtesting; conflicts with intro.md's
"unbiased facts" scope). A transparent historical-expectancy column is a
later, separate effort.

### 19.7 Files

- `src/confluence.py` — `BADGES`, `FAMILIES`, `FAMILY_COLORS`, `compute()`
- `dashboard.py` — `tab_confluence` block + `_confluence_cards()` helper
- `docs/confluence.md` — narrative (style of `docs/cup_and_handle.md`):
  badge families & the correlation rationale, what "running" does/doesn't
  trigger (§19.0), why rank-by-families
- `test_confluence.py` — unit tests for `compute()`
- `test_dashboard_app.py` — AppTest for the tab

### 19.8 Testing

- `compute()` on a synthetic `full`: each `test` fires on the right rows;
  `n_families` caps per family; `confluence_score` family-capped; `extra`
  merge null-safe; missing on-demand columns → all-False, no raise.
- AppTest: tab renders with **no** on-demand cache present; changing
  "Rank by" reorders; "Min families" filters; "Save top-N as list" writes
  `my_lists/*.csv`.
- Guard test: every non-on-demand badge's source column asserted present in
  a real `screener_results.csv` (catches column renames — feedback_5 class).
- Target: test_dashboard_app.py green + new suite; validate.py unchanged.

### 19.9 Out of scope

Earnings-proximity badge (no data), AI strike-zone score (§19.6),
"theme" taxonomy, portfolio "% invested" donut, changing the daily batch
or `combine.union()`.

### 19.10 Built (2026-08-30)

- `src/confluence.py` — `BADGES` (23: 17 batch + 6 on-demand), `FAMILIES`
  (6), `FAMILY_COLORS`, `BATCH_SOURCE_COLS`, `compute(full, extra=None)`,
  `rank(df, by='n_families')`, `merge_ondemand(run_dir, index)`.
- `dashboard.py` — `tab_confluence` between All Results and Timing;
  `_confluence_cards()` renders the stacked cards (accent bar, family-colour
  pills, context pills, `n_badges` square + rank-metric circle, tier
  colours) via `st.markdown(unsafe_allow_html=True)`; scope filter over
  `full` (no data load); opportunistic `merge_ondemand` from `report.run_dir()`;
  ranked `st.dataframe` + sparkline + multi-row select; Download CSV /
  Save top-N / Save SELECTED as list.
- `test_confluence.py` — 18 checks (badge firing, family cap, `extra`
  null-safety, missing-column tolerance, rank tie-breaks, live-CSV column
  guard). `test_dashboard_app.py` — +4 checks (**35/35**).
- **Deviation / incidental fix:** the on-demand tabs call `report.run_dir()`
  on every dashboard boot, which `mkdir`s an empty `results/<today>/` when no
  batch ran today. `_latest_run_dir()` in both `validate.py` and
  `test_dashboard_app.py` picked that empty dir → `FileNotFoundError`. Both
  helpers now require `screener_results.csv` (matching the dashboard's own
  `latest_run_dir()`); the timing/patterns cache-file assertions in the test
  switched to `report.run_dir()` directly. validate.py 37/37 unchanged.

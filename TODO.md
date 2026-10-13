# TODO — dashboard-screener

Written 2026-09-28 to pick up next session. Order matters: 1 → 2 first.

## 1. Data gap (blocks everything below)

The 2026-09-25 run is mostly empty for 50-day indicators: only ~194 of
3,961 tickers have `rti`, `adv50_dollar`, `pct_vs_50sma`, `adr20_pct`,
`ext_50sma_atr` (`pct_vs_200sma` 184). Cause: the downloadData_v1 daily
files are missing **2026-09-22** (97% of tickers) and **2026-08-11** (32%);
any rolling window over the hole is NaN for ~50 sessions. Every preset,
the Focus List and the Workflows are affected, not just "tight".

- [x] Backfill in downloadData_v1 — DONE 2026-09-28 there (08-11 in 4,148,
      09-22 in 4,138 of 4,164 files); downloadData now has its own gap check.
- [x] Re-run `python3 run_screeners.py` — DONE 2026-09-28 (results/2026-09-28):
      rti/adv50/pct_vs_50sma/adr20/ext_50sma_atr 3,931 of 3,961, pct_vs_200sma 3,692.
- [x] Missing-day guard — DONE 2026-09-28: `data_loader.check_missing_days`
      (NYSE sessions, last 60, > 20% of live tickers without a bar) → loud
      WARNING block in `run_screeners.py` after loading.

Note: `data_loader.py` only appends batch rows *after* a ticker's last
per-ticker bar (`b[b.index > tail_from]`), so a batch file for a past date
does NOT fill a hole — the fix must go into the per-ticker files.

## 2. "Tight base" screener (agreed approach)

User's definition: tight / narrow = price only — small daily moves, sideways
consolidation / base. Nothing to do with volume. Always applied AFTER the
leaders, never to the whole universe.

- [ ] New columns in `run_screeners.py`, each relative to the stock itself:
      - range contraction: ADR(10) / ADR(50)          (start: < 0.7)
      - box width: (20d highest high − lowest low) / close  (start: < ~12%)
      - flat box: |20d net change| vs box height       (start: < 1/3)
- [ ] "Tight base" preset = those three only (no trend / liquidity inside).
- [ ] Built-in workflow **"Leaders → Tight base"**: stage 1 = leaders from
      the universe, stage 2 = Tight base on stage 1's output → Focus List.
      Open question for the user: stage 1 = plain union (Minervini / CANSLIM /
      SCOOTER) or union + stage 2A/2B?
- [ ] Tune thresholds on the leaders (~500), not the whole universe — only
      after step 1, with real data. Consider a tightness score column to
      sort tightest first.

## 3. Preset fixes found in the review

- [ ] RTI isn't "range tightening": our `rti` = 50d avg (H−L)/price × 100, a
      volatility *level* (corr 0.87 with ADR%). Zone 1–2 (< 10) passes most
      calm stocks (2,144 on a full-data run). Either rebuild as range-relative
      (current range vs its own recent range, 0–100) or replace its use by
      the Tight base columns. Affects "Tight consolidation (RTI)",
      "TW: Tight and orderly", "TW: not extended".
- [ ] "Momentum Leader (Narrow)" is the opposite of tight (ADR > 6%) —
      rename (e.g. "Momentum Leader (high ADR)"); TAXONOMY.md says ADV
      > $50M but the preset uses > $20M (no $50M option exists).
- [ ] TW presets: price custom 3–1000 excludes > $1,000 stocks; Ollie's rule
      is only price > $3.

## 4. Smaller follow-ups

- [ ] Leaders' Lists tab doesn't show the CANTATA list (leaders_cantata.csv
      is written every run) — add it + a line in the info box.
- [ ] "How … is built" info box for the remaining tabs (Timing, Patterns,
      Workflows; Confluence done 2026-10-13) — helpers `_how_built` /
      `_universe_line` in dashboard.py.
- [ ] Save "Combine screens" selections as a named screener.
- [ ] 21dma-structure pullback: if the fixed ±2% window is noisy on
      volatile names, add an ATR-based window (e.g. ±0.5 ATR) — agreed to
      start with % (config.MA21S_PULLBACK_PCT).
- [ ] Open a PR `workflows-tab` → `main` (branch pushed, commit 2edfbc0).
- [ ] Uncommitted, not from this work — decide: `results/` cache changes
      (~20k files), `src/patterns/glb_chart.py`, `watchlists/`.

## 5. Volume Records tab (metaVolume integration)

- [x] DONE 2026-10-13 (now step 4; shared `_filter_grid` / `_advanced_filters`
      with key prefix `vrf_`). Filters: bring the Screener tab's full Filters panel into 3 Filters
      (today: a short tab-specific set — market cap, price, ADV, vs prior,
      index, sector, exclude funds). Needs its own session-key prefix: the
      Screener's `sel_*` widgets would otherwise change both tabs at once.
- [ ] Next screens: HVD top-N ranks (metaVolume's HVD file is date-sorted,
      not volume-sorted — re-sort on import), then maybe volume anomaly /
      Stockbee 9M as chips in 1 Pick screens.
- [x] `volume_records/`: baseline committed, ledger gitignored (rebuilt
      every run) — decided 2026-09-29.

## 6. Where is each leader? (leader map tab)

- [ ] "As-of date" picker: redraw the map for any past close (e.g. to line up
      with the Prime Report being read) — slice the price panel to that date
      and recompute ext_21ema_atr / ext_10wsma_atr for the list only
      (today: latest bar of the screener run).
- [ ] Alex's themes: a CSV `theme` column already overrides the industry
      grouping — build / keep a theme map file if industry proves too coarse.
- [ ] SKHY (in his list) has no price file in downloadData_v1.
- [ ] Setups — the plan: the report's per-name tags ("tight", "higher lows ·
      12d", "volume dry") and "reclaimed Sep 25 · back inside 1d · 25th pct"
      (this leg ranked against 3 years of the stock's own legs) are not
      defined in the report — write our own rules if wanted. Alex's pick
      (checklist 4/5, one per theme) is not modelled either: we list every
      buy-area name + every name <= +2 ATR above the box.
- [ ] Growth Cycle page (Lab Report "Growth Cycle", 9/28 screenshot):
      - Ratio = growth / value = IWF / IWD (confirmed: his 9/28 "growth
        125.18 · value 250.01" = our IWF 125.20 / IWD 250.05; both in
        downloadData_v1 from 2020).
      - Risk gate: the ratio's "10w structure" = EMA10 of its weekly highs
        and weekly lows (weekly bars built from daily). Close above the band
        = risk-on, below = risk-off, inside = keep the last side.
      - Momentum: 10-day change in the ratio's gap to that band's midline,
        smoothed 3 days, / 63-day volatility (sigma); flips only past
        +-0.25 sigma. Extended above +1.3 sigma; Trim if also > +2 sigma from
        its 21-day EMA.
      - Six zones: Risk-off, Probe, Ramp Up, Reload, Hold, Trim (counter-
        clockwise cycle); "zone every day" history strip since 2022.
      - Zone stats ("next 20 days, up x% of the time, growth won y%"): use
        QQEW (First Trust equal-weight NASDAQ-100; Alex uses QQQE, the
        Direxion equivalent) — user added QQEW to downloadData_v1, available
        after its next run.
      - Calibrate against his readings before trusting it: 9/28 = Ramp Up,
        day 7; risk-on since Sep 18; momentum +1.86 sigma; 21d stretch
        +1.27 sigma. Some rules are ambiguous (which volatility, the +-0.25
        sigma flip) — expect a few iterations.
- [x] Second row of tabs — DONE 2026-10-13 (group row / tab row / Presets
      sub-row; `TAB_GROUPS` in dashboard.py).

## 7. Ticker detail: readable summary — DONE 2026-10-13

Done: `src/ticker_summary.py` (rules, thresholds `config.SUMMARY_*`), shown
above the metric table in 📋 Ticker → Ticker detail; `test_ticker_summary.py`
(11 checks). Original request below.


The 📋 Ticker → Ticker detail tab shows one long metric dump that is hard to
read. KEEP it as it is, and add above it an automatic plain-language summary
per ticker, built from data we already have (no new downloads), e.g. NVDA:

- **Price & trend** — close, day / 5d / 1m / 3m change, % from 52w high;
  stage, Minervini count, GMMA state, RS percentile, SCOOTER.
- **Confluence** — families + badges today; days at >= 3 families in the
  last 20 (`history.db` confluence_daily); badges gained / lost recently
  ("lost 52H after 10-06, GLP after 10-07").
- **Volume records** — last HVE date (+ "none recent"), last HV1Y date with
  1st / 2nd dch %.
- **Index ranking** — S&P 500 / NASDAQ 100 rank over the last 5 sessions
  (`mover_ranks`).
- **Earnings** — last report: EPS vs estimate, surprise %, YoY growth;
  next report date (`financial_data_0_5.csv`, qh1_* / next_earnings_date).

Rule-based text (thresholds in config), not an LLM. Target format (NVDA,
2026-10-12 session):

    Price & trend
    - Close 226.32: −1.3% on the day, −5.3% over 5 days, +3.7% over 1 month,
      +6.9% over 3 months. 5.4% below its 52-week high.
    - Stage 2B, Minervini 8/8, GMMA bullish, RS percentile 74.5, SCOOTER 78.
    Confluence
    - Today: 2 families (MM, GMMA, ON, CE) — just dropped below the >= 3 filter.
    - Last 20 days: 16 of 20 at >= 3 families — a steady name.
    - Lost 52H after 10-06, GLP after 10-07, NrH on 10-12 (fits the 5-day pullback).
    Volume records
    - No recent HVE: all-time volume record 2023-05-25.
    - Last 1-year volume high 2026-02-26: −5.5% that day, −4.2% the next.
    NASDAQ 100 ranking (last 5 sessions): rank 48–77 of ~95, worst 10-08 (−2.9%).
    Earnings
    - Last report 2026-08-26: EPS 2.22 vs 2.09 expected, +6.2% surprise,
      +111% YoY. Next report: 2026-11-17.

## 8. Navigation label — DONE 2026-10-13

- [x] First nav row: rename the group "🌍 Market" to "🌍 Market Movers"
      (`TAB_GROUPS` in dashboard.py; also update the "Screener history lives
      in Confluence" / README mentions of "Market"). Only `TAB_GROUPS`
      needed it — no other mentions found.

## 9. Timing signals in the Screener (agreed 2026-10-13)

Blue Dot alone over the whole universe is noise; on leaders / a list it is
useful → compute the signals daily and filter them in the Screener.

- [x] Step 1 — DONE 2026-10-13: `src/timing/daily.py` in `run_screeners.py`
      (skipped for --as-of runs: PVB/ATR1 caches only move forward).
      Columns `*_bars_since` (trading bars) + PVB/ATR1 state, date, perf.
      Screener: category "Timing" (Blue Dot ≤ 5, Black Dot ≤ 5, PVB Buy ≤ 10,
      ATR1 Long cross ≤ 10 bars) + "Timing signals" row in Advanced filters.
      Cost: ~9 s/day with warm caches, ~95 s cold.
- [x] Step 2 — DONE 2026-10-13: Combine screens shows levels 1–3, "＋ Add
      level 4" / "✕ Remove level 4" (`COMB_PREFIXES` in dashboard.py); one
      Funnel / Merge switch for the whole chain, empty levels skipped.
- [x] Step 3 — DONE 2026-10-13: signal detail columns in the Screener
      results (front when a Timing chip / filter is in use, `TIMING_DETAIL`
      in dashboard.py); Timing Signals tab removed (src/on_demand.py stays
      for Patterns). Confluence timing badges now read the daily `in_pvb_buy`
      / `in_atr1_uptrend` / `in_blue_dot` / `in_black_dot` (same rules as
      the tab); --as-of runs compute them too (own `*_asof` caches), and
      history.db was backfilled 20 sessions so the history counts them on
      every day.

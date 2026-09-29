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
- [ ] "How … is built" info box for the remaining tabs (Confluence, Timing,
      Patterns, Workflows, Ticker detail) — helpers `_how_built` /
      `_universe_line` in dashboard.py.
- [ ] Save "Combine screens" selections as a named screener.
- [ ] 21dma-structure pullback: if the fixed ±2% window is noisy on
      volatile names, add an ATR-based window (e.g. ±0.5 ATR) — agreed to
      start with % (config.MA21S_PULLBACK_PCT).
- [ ] Open a PR `workflows-tab` → `main` (branch pushed, commit 2edfbc0).
- [ ] Uncommitted, not from this work — decide: `results/` cache changes
      (~20k files), `src/patterns/glb_chart.py`, `watchlists/`.

## 5. Volume Records tab (metaVolume integration)

- [ ] Filters: bring the Screener tab's full Filters panel into 3 Filters
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
- [ ] Second row of tabs once there are 2-3 Lab Report pages.

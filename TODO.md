# TODO — dashboard-screener

Written 2026-09-28 to pick up next session. Order matters: 1 → 2 first.

## 1. Data gap (blocks everything below)

The 2026-09-25 run is mostly empty for 50-day indicators: only ~194 of
3,961 tickers have `rti`, `adv50_dollar`, `pct_vs_50sma`, `adr20_pct`,
`ext_50sma_atr` (`pct_vs_200sma` 184). Cause: the downloadData_v1 daily
files are missing **2026-09-22** (97% of tickers) and **2026-08-11** (32%);
any rolling window over the hole is NaN for ~50 sessions. Every preset,
the Focus List and the Workflows are affected, not just "tight".

- [ ] Backfill in downloadData_v1 — runbook in `../downloadData_v1/to_do.md`
      ("Backfill missing daily bars").
- [ ] Re-run `python3 run_screeners.py`, then check coverage: those columns
      should have values for ~3,700+ tickers again.
- [ ] Add a missing-day guard to `run_screeners.py` (after
      `data_loader.load_price_matrices`): warn loudly when a date in the last
      ~60 bars is missing for more than ~20% of tickers, so a hole can't
      silently empty the columns again.

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
- [ ] Open a PR `workflows-tab` → `main` (branch pushed, commit 2edfbc0).
- [ ] Uncommitted, not from this work — decide: `results/` cache changes
      (~20k files), `src/patterns/glb_chart.py`, `watchlists/`.

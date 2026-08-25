# Feedback round 4 — two new tabs: Timing Signals and Patterns

Fresh context for whoever picks this up — this doc assumes no memory of
the conversation that produced it. Read this whole file before starting;
it explains *why* the structure is what it is, not just what to build,
because several design choices here were deliberately walked back from a
simpler-looking alternative and you should understand why before
"simplifying" them back.

## The decision, summarized

The dashboard is getting **two new tabs** — 🕐 **Timing Signals** and
🌊 **Patterns** — to hold 6 screeners that don't exist yet:

- **Timing Signals**: PVB, ATR1 (`vol_stop`/ATR Cloud), Dr. Wish Blue Dot,
  Dr. Wish Black Dot
- **Patterns**: Dr. Wish GLB (Green Line Breakout), Cup & Handle
  (from a *different* source project, `patterns_v0`, not `metaData_v1`)

**Do NOT touch the existing "🔎 All Results (filter panel)" tab or its
Advanced Filters expander.** This was explicitly considered and rejected
— see "Why All Results stays exactly as it is" below before doing
anything that moves things out of it.

## Why three buckets, not one "Screeners" tab for everything

We arrived at this after first proposing (and then rejecting) folding
these into a single "Screeners" tab alongside the existing 9 named-method
screeners (Minervini, CANSLIM, SCOOTER, Stockbee ×3, Golden Launch Pad,
Qullamaggie, ADL Accumulation). Two independent axes decide where
something goes:

1. **Does it answer "is this a candidate to watch" or "should I act
   right now"?** The 9 existing screeners are the former — durable
   classifications with no urgency clock, *designed* to compose with the
   generic filter panel (that composability is the whole point of the
   screener→filter pattern established since round 1 — e.g. the
   `"Leaders not extended (<= 2 ATR)"` preset is a screener flag AND a
   raw filter combined in one query). PVB/ATR1/Blue Dot/Black Dot answer
   the latter — a Buy/Sell state or a trailing-stop level is meaningless
   without "as of when," and nobody's asking to combine "PVB fired a Buy
   signal" with "ADR% > 6%" in one filter query the way the existing
   screeners are used. That's **Timing Signals**.
2. **Are the parameters settled, or genuinely unresolved/exploratory?**
   GLB and Cup & Handle are pattern-*geometry* detectors with many
   interacting parameters (GLB: ~6-7, including period-strings;
   Cup & Handle: 14, CSV-driven) where the "right" values are actually
   debatable — `patterns_v0`'s own `readme.md` documents its threshold
   config being loosened repeatedly (cup depth 10%→1% min, handle
   position "upper 30%"→"anywhere," etc.) just to get any hits at all.
   These aren't "pick sensible defaults once and move on" the way
   Minervini's trend template is — they may genuinely want to stay
   user-adjustable. That's **Patterns**.

PVB/ATR1/Blue Dot/Black Dot use *settled* technical-indicator defaults
(standard breakout/ATR-cloud/stochastic parameters, not a documented
tuning saga) — so despite having several config constants each, they
don't need tunable UI the way Patterns does. They're "fixed config, one
state output" just like the existing 9 screeners — they just answer a
different *question*, which is why they get their own tab rather than
joining the existing 9.

## Why All Results stays exactly as it is

The original proposal was also to move the 9 existing named-method
screeners out of "All Results" into a "Screeners" tab, to reduce
crowding in the Advanced Filters expander. **This was rejected.** Reason:
those 9 screeners were specifically built to compose with the generic
filters in one query (see the preset example above) — splitting them
into a separate tab would break that composability (existing presets
like `"Leaders not extended"` combine a screener flag with a raw filter
in the same mask) or require significant rearchitecting for no real
gain. The actual crowding is narrower than "the whole tab" — it's the
Advanced Filters *expander* specifically, which has grown to ~20
checkboxes/multiselects in one flat list. If that's worth addressing,
the fix is **sub-grouping the expander into labeled sections** (e.g.
"Leaders & Screeners" / "Stage, Trend & RS" / "Volatility & Volume" /
"Universe") — same tab, same combinability, just organized. This is
optional polish, not required for this round — do it only if there's
spare time after the two new tabs are done.

## On-demand, scoped computation — the core architecture change in this round

Every screener built in prior rounds is computed for the **full universe,
once a day**, inside `run_screeners.py`'s batch — the dashboard only ever
filters pre-computed columns, never triggers computation. **That changes
for these 6 screeners.** They're expensive enough (see
`more_screeners_2.md`: PVB/ATR1 = Moderate runtime, GLB = Slow, Cup &
Handle = Fast-ish/Moderate, all per-ticker-loop-shaped, all multiplied by
~4,000 tickers) that always computing them for everyone, every day, isn't
the right default. Instead:

- **PVB, ATR1, Blue Dot, Black Dot, GLB, and Cup & Handle are NOT part of
  `run_screeners.py`'s daily full-universe batch.** Don't add their
  columns to `screener_results.csv`.
- Each of the two new tabs gets a **scope selector** at the top:
  **Index membership** (S&P 500 / NASDAQ 100 / Russell 1000 / etc. —
  reuse the exact same universe-CSV `Index` column and parsing already
  built for the existing "Index membership" advanced filter —
  `dashboard.py`'s `universe_index_map()` / `index_choices()` / `IDX_MAP`
  — don't reparse this from scratch) plus a **market-cap threshold**
  (reuse the existing `market_cap` column, already computed for the full
  universe by the daily batch). Sector/exchange/uploaded-list scoping is
  explicitly **not** included this round — Index + market cap only, keep
  it simple.
- A **Run** button triggers computation for just the scoped subset,
  against that tab's screener(s). Default the scope to something small
  (S&P 500 or similar) — don't default to "full universe."
- **While it runs, show a progress bar** (`st.progress()`, updated per
  ticker processed — "Processing 240/500...") — **not** a blind
  `st.spinner()`. This is a required part of the implementation, not
  polish: the whole point of scoping is to make the wait tolerable and
  *visible*, and a progress bar is what actually communicates that to
  the user. True background/async execution (letting the user leave the
  tab while it runs) was discussed and deliberately deferred — good
  future work, not required this round; the blocking-but-visible
  progress bar is the agreed baseline.
- **Persist scoped results** to `results/{date}/{tab}_{scope_key}.csv`
  (e.g. `results/2026-08-25/timing_signals_sp500.csv`,
  `results/2026-08-25/patterns_glb_nasdaq100.csv`) so switching tabs or
  reloading the dashboard doesn't lose a completed run — same pattern as
  every other results file this project already writes, just triggered
  on-demand instead of daily. Re-running with the same scope on the same
  day can reuse the cached file rather than recomputing (check for it
  before running).
- Consequence for module design: each `src/timing/*.py` and
  `src/patterns/*.py` module's main function should accept an explicit
  **ticker list** (the scoped subset) as an argument, not assume "the
  full universe" — this is what makes both the scoping *and* the
  `validate.py` behavioral checks (which only need to run against a
  handful of sample tickers, not all 4,000) natural to write.

This works *with* GLB's incremental-caching requirement below, not
instead of it — scoping bounds cost immediately (500 tickers instead of
4,000, an ~8x reduction on the very first run), caching makes repeated
runs against overlapping scopes progressively cheaper over time. Both
apply to GLB; scoping alone is likely sufficient for PVB/ATR1/Cup&Handle
given they're only Moderate/Fast-ish to begin with.

## New module organization

Following the existing convention (`src/leaders/` for candidate
screeners, `src/focus/` for filter-shaped metrics), add two new
directories matching the two new tabs:

- `src/timing/` — `pvb.py`, `atr1_cloud.py`, `drwish_dots.py` (Blue Dot +
  Black Dot together, since they share the same stochastic building
  block and source file)
- `src/patterns/` — `glb.py`, `cup_handle.py`

## New column-naming convention

These columns live in the on-demand scoped result files described above
(`results/{date}/{tab}_{scope_key}.csv`), not in `screener_results.csv`.
Timing signals produce a *state*, not just a boolean — follow this shape:

- `pvb_signal` (categorical: Buy / Sell / Close Buy / Close Sell / No
  Signal), `pvb_days_since_signal`, `pvb_signal_price`,
  `pvb_performance_since_signal`
- `atr1_trend` (categorical: uptrend / downtrend), `atr1_stop_level`,
  `atr1_cross_up`, `atr1_cross_dn` (event flags — true only on the
  actual flip day)
- `in_blue_dot`, `in_black_dot` (booleans — these are same-day snapshot
  signals per `more_screeners_2.md`, simpler than PVB/ATR1)

Patterns produce richer per-pattern metadata, matching what the source
detectors already compute:

- `in_glb_breakout`, `glb_level`, `glb_detection_date`,
  `glb_days_since_pivot`
- `in_cup_handle`, `cup_handle_stage` (forming / breakout / complete —
  matches `_determine_pattern_stage` in the source), `cup_handle_quality_score`,
  `cup_depth_pct`, `handle_depth_pct`, `cup_handle_target_price`,
  `cup_handle_stop_loss`

## Ordered task list

Build order (easiest first, same discipline as `more_screeners.md`):
finish each task's Definition of Done (module + `config.py` thresholds
with citations + a **behavioral** `validate.py` check + dashboard wiring)
before moving to the next. Full detail on each screener's algorithm and
build/runtime cost is already written up in `more_screeners_2.md` — this
doc doesn't repeat that, it tells you what to do with it.

1. **Blue Dot / Black Dot** (`src/timing/drwish_dots.py`) — source:
   `metaData_v1/src/screeners/drwish_screener.py:314-418`. Simplest of
   the six per `more_screeners_2.md` (Medium build, Fast runtime,
   same-day-snapshot-shaped). That doc flagged its own estimate as
   provisional since the function bodies weren't read line-by-line —
   read them fully before starting.
2. **PVB** (`src/timing/pvb.py`) — source:
   `metaData_v1/src/screeners/pvb_screener.py`. Needs the per-ticker
   signal-state-machine treatment described in `more_screeners_2.md`
   (persistent Buy/Sell state, not a same-day condition).
3. **ATR1 / vol_stop** (`src/timing/atr1_cloud.py`) — source:
   `metaData_v1/src/screeners/atr1_screener.py:41-107`. Recursive
   per-bar calc — per `more_screeners_2.md`, implement the per-ticker
   loop over raw numpy arrays, not the source's `.iloc`/`.loc` pattern
   (meaningfully faster). Note `atr_screener.py` duplicates this same
   math — use `atr1_screener.py` as the source, ignore the duplicate.
4. **Build the Timing Signals tab** — once all three of the above land.
   This is also where the shared scope-selector / Run-button /
   progress-bar / results-persistence plumbing (see the architecture
   section above) gets built for the first time — write it as something
   the Patterns tab (task 7) can reuse, not tab-specific code. See mock
   below.
5. **GLB** (`src/patterns/glb.py`) — source:
   `metaData_v1/src/screeners/drwish_screener.py:99-313`.
   **Two mitigations apply together here, both required**:
   (a) it must accept a scoped ticker list and run against that, per the
   on-demand architecture above — this alone cuts cost ~8x for an
   S&P-500-sized scope vs. the full universe; (b) on top of that, it must
   still be built as an **incremental/cached computation** within
   whatever scope is chosen, not a naive full-history recompute every
   run. Rationale for (b): most of GLB's history is immutable — a pivot
   older than `pivot_strength` days is permanently confirmed/rejected,
   and a GLB level that's already broken never needs rescanning. Only
   (a) still-open levels need checking against each new day's close, and
   (b) pivots near the trailing edge need fresh confirmation. Maintain a
   small per-ticker state cache (level price, detection date,
   open/broken), keyed by ticker, reusable across scopes (a ticker
   cached from an S&P 500 run doesn't need recomputing if it also
   appears in a later NASDAQ 100 run) — built once against
   `config.DAILY_ARCHIVE`, updated incrementally as `config.DAILY_CURRENT`
   grows. If the incremental approach can't be done in the time
   available, **stop and flag it rather than shipping the naive O(n²)
   version even scoped down** — a slow-loading button was explicitly
   called out as unacceptable during design, not a minor tradeoff.
6. **Cup & Handle** (`src/patterns/cup_handle.py`) — source:
   `patterns_v0/src/cup_handle_detector.py` + `cup_handle_config.py` +
   `peak_trough_detector.py`. **Architecture note, read before starting**:
   because this pattern's parameters are meant to be explorable (see
   "Patterns tab" mock below), don't build it as one fixed config.
   Compute it, on-demand against the scoped ticker list, under **2-3
   named parameter presets** ("Strict/textbook", "Default", "Loose" —
   e.g. Strict ≈ O'Neil-style 12-33% cup depth / handle in upper third;
   Loose ≈ closer to `patterns_v0`'s tuned config from its `readme.md`),
   each producing its own `in_cup_handle_{preset}` column set, rather
   than picking one fixed threshold set to bake in. **Do not default to
   `patterns_v0`'s already-loosened config as the only option** — that
   config was tuned specifically to force hits on their dataset and
   produced a 45.5% hit rate with an average quality score of 18.2/100;
   ship "Strict" as the real O'Neil-style definition and let "Loose" be
   the explicitly-labeled permissive option, not the unlabeled default.
   True live-parameter sliders (recompute on drag) are explicitly **out
   of scope for this round** — see the architecture note in the Patterns
   tab mock.
7. **Build the Patterns tab** — once GLB and Cup & Handle land. Shared
   scope-selector/progress-bar/results-persistence plumbing from the
   architecture section above should be written once and reused by both
   the Timing Signals tab (task 4) and this one — don't duplicate it.

## Where to find implementation detail

- `more_screeners_2.md` — build-difficulty and runtime-cost analysis for
  all 6 screeners, already read against the actual source code (not
  docstrings) — read this first for each screener.
- `SCREENER_INVENTORY.md` — original survey/categorization,
  `metaData_v1/src/screeners/` file locations.
- `TAXONOMY.md` — the filter/screener/preset/list decision framework
  this whole project runs on. **Add the tier model from this doc
  (candidate-screeners vs. timing-signals vs. patterns) as a new section
  there once these tabs exist** — small task, keeps the reference doc
  current for whoever reads it next.
- `feedback_1.md`/`feedback_2.md`/`feedback_3.md` — the established
  testing discipline: every preset/flag needs a **behavioral**
  `validate.py` check (module output == independently-recomputed manual
  mask), not a shape-only check — this is the exact gap that let a real
  regression through in round 2. Don't repeat that.
- Source files: `metaData_v1/src/screeners/pvb_screener.py`,
  `atr1_screener.py`, `drwish_screener.py`; `patterns_v0/src/
  cup_handle_detector.py`, `cup_handle_config.py`, `peak_trough_detector.py`.

## Mock: 🕐 Timing Signals tab

Same spirit as the existing tabs — fixed-config screeners, no tunable
parameters (matches the existing 9 screeners' philosophy), but its own
signal-specific columns instead of the generic filter panel:

```
🕐 Timing Signals
──────────────────────────────────────────────────────────
Scope:  Index membership [S&P 500 ▾]   Min market cap [$0 ▾]
        (default: S&P 500 — deliberately small; widening this warns
         "may take longer" rather than silently accepting it)

Signal source:  [ ] PVB   [ ] ATR1 Trend   [ ] Blue Dot   [ ] Black Dot
                (multiselect — pick one or more sources to include)

                              [ ▶ Run ]

── while running ──
[████████████░░░░░░░░]  240 / 500 tickers processed
(st.progress(), not a blind spinner — this is required, see the
 architecture section above)
──────────────────────────────────────────────────────────
State filter:   [multiselect, options depend on source(s) picked —
                 e.g. PVB: Buy/Sell/Close Buy/Close Sell;
                      ATR1: Uptrend/Downtrend/Cross Up/Cross Dn]

Max days since signal:  [slider 0-30, default 10]
──────────────────────────────────────────────────────────
Results (sorted by days_since_signal, most recent first) — from the last
completed run for the current scope; re-running with an unchanged scope
on the same day reuses the persisted file instead of recomputing:

ticker | source | signal_state | days_since | signal_price |
current_price | %chg_since_signal | stop_level (ATR1 only) | spark
──────────────────────────────────────────────────────────
[Download CSV]   [Save as list]
```

## Mock: 🌊 Patterns tab

Different philosophy from every other tab in this dashboard — the
pattern's own parameters are exposed as adjustable controls, because
(per the design conversation) these patterns' "correct" thresholds are
genuinely unresolved, unlike the settled screeners elsewhere:

```
🌊 Patterns
──────────────────────────────────────────────────────────
Scope:  Index membership [S&P 500 ▾]   Min market cap [$0 ▾]
        (same shared scope control as Timing Signals — default small,
         warn on widening)

Pattern:  ( ) Green Line Breakout (GLB)   ( ) Cup & Handle
          (radio — one at a time; each has its own distinct parameter
           set that doesn't compose with the other's)

── if GLB selected ──
Pivot strength:      [slider]
Lookback period:     [selectbox: 6m / 1y / 2y / complete]
Confirmation period: [selectbox]

── if Cup & Handle selected ──
Preset:  ( ) Strict (textbook)   ( ) Default   ( ) Loose
         (picks among the precomputed `in_cup_handle_{preset}` column
          sets — NOT a live recompute; see architecture note in Task 6.
          True continuous sliders are a future round, not this one.)

                              [ ▶ Run ]

── while running ──
[████████████░░░░░░░░]  240 / 500 tickers processed
──────────────────────────────────────────────────────────
Results (from the last completed run for the current scope+pattern;
persisted per `results/{date}/patterns_{glb|cup_handle}_{scope}.csv`):

GLB:            ticker | glb_level | detection_date | days_since_pivot |
                current_price | %_above_level | spark

Cup & Handle:   ticker | stage (forming/breakout/complete) |
                quality_score | cup_depth_pct | handle_depth_pct |
                target_price | stop_loss | spark
──────────────────────────────────────────────────────────
[Download CSV]   [Save as list]
```

## Definition of done (per screener-build task, same as prior rounds)

- [ ] New module under `src/timing/` or `src/patterns/`, docstring cites
      the source file and original methodology
- [ ] Thresholds in `config.py` with provenance comments
- [ ] Main function takes an explicit ticker list argument (the scoped
      subset) — **not** hardcoded to the full universe, and **not**
      wired into `run_screeners.py`'s daily batch or `screener_results.csv`
- [ ] Results write to `results/{date}/{tab}_{scope_key}.csv` on a
      completed on-demand run; a re-run with the same scope on the same
      day reuses the cached file instead of recomputing
- [ ] **Behavioral** `validate.py` check — module output vs. an
      independently-recomputed manual mask/value, run against a handful
      of sample tickers (not the full universe — that's the point of
      accepting a ticker-list argument)
- [ ] `test_dashboard_app.py` extended to cover the new tab's live-UI
      behavior once that tab exists, including that the scope
      selector/Run button/progress bar actually work
- [ ] Full `validate.py` run still green — all checks, not just new ones
- [ ] GLB specifically: confirm the incremental-cache approach actually
      keeps a scoped run fast — measure it, don't assume it (e.g. time
      an S&P-500-scoped run, cold and warm-cache)

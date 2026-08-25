# More screeners — ordered backlog

Scoped from `SCREENER_INVENTORY.md`'s survey of `metaData_v1/src/screeners`,
picking the **simplest, best-defined** candidates first. This is a
backlog, not a single 2-hour task: work through the tasks **in order**.
When you finish one (its "Definition of done" checklist passes and
`validate.py` is fully green), move straight on to the next task in the
list without waiting for a new prompt. Stop and ask only if a task's
approach is genuinely ambiguous, a source file contradicts this doc, or a
definition-of-done item can't be satisfied.

**Prerequisite — do not start this until `feedback_2.md` is resolved**:
§0 (7/8 presets broken) is a live regression affecting the existing
screeners; §1 (custom-range round-trip) is smaller but real. Confirm
`validate.py` is fully green and spot-check a couple of the currently-
broken presets in the running dashboard before adding new surface area
on top of a known-broken filter panel.

## Column idea (not scoped, no task yet): signal persistence / streak length

Surfaced from manually checking Golden Launch Pad on MELI vs. LLY
(2026-08-25): any boolean screener flag (`in_gold_launch_pad`,
`in_qullamaggie`, `in_9m_movers`, etc.) is currently evaluated fresh every
day with no memory of yesterday, so there's no way to tell "this just
turned on today" from "this has been true on and off for weeks" without
manually recomputing history the way this conversation did by hand. A
**"days flagged true in the trailing N sessions"** and/or **"current
streak length"** column per flag-producing screener would make that
distinction visible in the dashboard itself. Generic enough to apply to
any `in_*` boolean column, not just GLP — worth scoping as its own small
task once there's appetite, not urgent.

## How this codebase differs from the metaData_v1 source files

Don't port the `metaData_v1` files verbatim. They're written per-ticker
(`Dict[str, pd.DataFrame]` + Python `for ticker in batch_data` loops,
sometimes with an inner day-by-day loop too — see `gold_launch_pad.py`'s
`_calculate_zscore_spread`). This project is vectorized over **wide
matrices** instead (`src/indicators.py`: one `Close`/`Volume`/etc.
DataFrame with `columns=ticker`, `index=Date` — see
`src/data_loader.py:28,152-154`), which is how Minervini/SCOOTER/ATR-ext
run over ~4,000 tickers in 1-2 minutes. Re-implement each condition using
the existing `indicators.py` helpers (`sma`, `ema`, `slope_pct`,
`cross_sectional_percentile`, `pct_vs_ma`, `roc`, `avg_volume`,
`avg_dollar_volume`) operating on the whole matrix at once — a per-ticker
Python loop over the full universe will be noticeably slower and is not
the pattern the rest of this codebase uses.

## Task 1 (do first): Stockbee Movers — 3 sub-screeners

Source: `metaData_v1/src/screeners/stockbee/stockbee_screener.py`. Only
the 3 stock-level sub-strategies — the 4th (**Top 20% Industries & Top 4
Performers**) is explicitly **out of scope**, see below.

Each is a same-day snapshot classification — no multi-bar pattern
matching, just comparisons on today's/this-week's OHLCV vs. rolling
averages:

**a) 9M Movers** (`stockbee_screener.py:198-275`)
- Today's Volume ≥ 9,000,000
- Today's Volume / 20-day avg Volume ≥ 1.25 (relative volume)
- Today's Close > today's Open (green candle)

**b) 20% Weekly Movers** (`:277-374`)
- Last 5 trading days: Close (day 5) vs Open (day 1) change ≥ +20%
- 5-day avg Volume ≥ 100,000
- 5-day avg Volume / 20-day avg Volume ≥ 1.25
- Week's Close > week's Open (green week)

**c) 4% Daily Gainers** (`:376-471`)
- 1-day % change (today's Close vs yesterday's Close) ≥ +4%
- Today's Volume ≥ 100,000
- Today's Volume / 20-day avg Volume ≥ 1.5
- Today's Close > today's Open (green candle)
- Today's Close > 50-day SMA

**Implementation:**
- New module `src/leaders/stockbee_movers.py` — 3 boolean columns
  (`in_9m_movers`, `in_weekly_movers`, `in_daily_gainers`) plus the
  underlying numeric columns each condition needs (`rel_volume_today`,
  `weekly_gain_pct`, `daily_gain_pct` — some of these may already
  partially exist under different names, e.g. `gain_5d`; check
  `config.py`/`screener_results.csv` columns before adding duplicates).
- Thresholds (9M shares, 1.25x/1.5x relative volume, 20%/4% gain
  thresholds, $100K min volume) go in `config.py`, cited to this source
  file, same as the other three screeners.
- `validate.py`: add a **behavioral** check per sub-screener — recompute
  each condition directly as a pandas boolean mask on the same day's
  data (same shape as the existing `preset == manual filters` check) and
  assert your module's output matches. This is a near copy-paste of the
  bullet points above, so it should be quick, and it's exactly the kind
  of check that would have caught the §0 regression in feedback_2.md.
- Wire into `dashboard_filters.py` (three new advanced-filter checkboxes,
  same pattern as `adv_rti_dots`/`adv_rti_exp`) and `dashboard.py` (either
  a new `tab_leaders` expander or just add the 3 boolean columns + the
  numeric ones to `view_cols`).

**Estimate:** ~45-60 min including wiring — no new indicator machinery
needed beyond what `indicators.py` already has.

## Task 2: Golden Launch Pad

Source: `metaData_v1/src/screeners/gold_launch_pad.py`. Original:
https://www.tradingview.com/script/DvE0wDfI-Golden-Launch-Pad/

Conditions (defaults from the reference implementation, `:43-60`):

1. **Tightly grouped MAs** — 3 EMAs (default periods 10/20/50). For each
   EMA, compute its Z-score against its own trailing 50-day mean/stdev;
   the spread (max Z-score − min Z-score across the 3 EMAs) must be
   ≤ 1.0 (`max_spread_threshold`).
2. **Bullishly stacked** — EMA10 > EMA20 > EMA50.
3. **All 3 EMAs have positive slope** — linear-regression slope over a
   lookback of 30% of each EMA's period (`slope_lookback_pct`), slope
   > 0.0001 (`min_slope_threshold`). `indicators.slope_pct` may already
   cover this or be adaptable — check before writing a new rolling-
   linregress helper.
4. **Price above the fastest EMA** — Close > EMA10.
5. **Price near the MA cluster** — `|Close − mean(EMA10, EMA20, EMA50)|
   ≤ 2.0 × (20-day rolling stdev of Close)` (`price_proximity_stdv`,
   `proximity_window`).

**Implementation:**
- New module `src/leaders/gold_launch_pad.py` — `in_gold_launch_pad`
  boolean + `glp_spread_score` (e.g. `1 - zscore_spread/max_spread`,
  clipped to [0,1], matching the reference's "Strong"/"Moderate"
  strength split at 0.7).
- Thresholds in `config.py`, cited to the TradingView script + this
  source file.
- `validate.py`: this one is genuinely new math to this project (the
  Z-score-spread and rolling-slope calcs don't exist elsewhere here), so
  cross-check against `metaData_v1`'s own `GoldLaunchPadScreener` output
  on a handful of tickers — same pattern as the existing ATR/stage
  cross-checks against their `metaData_v1` originals — rather than a
  from-scratch manual-filter check.
- Wire into `dashboard_filters.py`/`dashboard.py` same as Task 1.

**Estimate:** ~45-60 min — more genuinely new code than Task 1 (the
Z-score spread and rolling slope are new to this codebase), but every
threshold is a concrete number from the source, no open design questions.

**Status: implemented, left as-is for now.** Verified against MELI and
LLY (2026-08-25 conversation) — computation is correct (independently
reproduced all 5 conditions from raw price data on both tickers, matches
the module's output exactly), but two limitations surfaced worth
revisiting later, not fixing now:
- **No trend/RS/stage gate** — the pattern is direction-blind by
  construction (ported faithfully from the source, which has no such
  gate either: `_apply_base_filters` only checks price/volume/ETF-
  exclusion). It fires the same way on a strong Stage 2B leader near
  highs with RS 80 (LLY) as on a weak Stage 3 laggard 23% off its high
  with RS 26 (MELI) — the geometry can't tell those apart on its own.
- **No persistence/minimum-duration requirement** — evaluated fresh
  every day with no memory, so it flickers in and out on marginal cases
  (MELI: true only 4/90 trailing days, non-contiguous) vs. a more
  durable coiling pattern (LLY: true 25/90 days). A real base should
  probably need to hold for some minimum stretch to count.

**TODO — recheck this model's implementation.** The pattern's original
TradingView script (linked above) is gone/deleted — `metaData_v1`'s port
is currently the only spec this was built against. Worth searching
TradingView for a current/better Golden Launch Pad implementation (or a
close equivalent) to cross-check against, since the only reference this
project has is one unverified third-party port of a since-deleted
script.

## Task 3: Volume + ADX filter columns (no new screener, just filters)

Two `metaData_v1` sources are **filter-shaped**, not screener-shaped —
per `SCREENER_INVENTORY.md`, each is a single formula → one new column,
same as ADR%/ADV today. No leaders flag, no combination logic, just new
threshold-able columns:

- `volume_suite_components/volume_indicators.py` — RVOL (relative
  volume), ADTV (average daily $ volume — check for overlap with the
  existing `adv50_dollar` before adding), VROC (volume rate of change),
  MFI (money flow index).
- `adx_report.py` — ADX, +DI, -DI (its own docstring already says
  "compute-only, no rule evaluation" — just port the indicator values).

Add each as a new column in `screener_results.csv`, a `config.py`
citation, a `validate.py` numeric cross-check against the `metaData_v1`
source (same shape as the ATR/ADR identity checks), and a new entry in
`dashboard_filters.FILTER_SPECS`/`THRESHOLD_FAMILIES`. No new `src/leaders/`
module needed — this is the fastest task in the backlog.

## Task 4: GMMA (Guppy Multiple Moving Average)

Source: `metaData_v1/src/screeners/guppy_screener.py`. 12 EMAs — short
group (3/5/8/10/12/15), long group (30/35/40/45/50/60). Compute all 12
(cheap, vectorized), then derive: bullish alignment (all short EMAs >
all long EMAs), bearish alignment (reverse), compression (groups
converging), expansion (groups diverging), crossover (short group
crossing the long group). Per `SCREENER_INVENTORY.md` this leans
**filter-shaped** (a categorical `gmma_state` column: bullish/bearish/
compressing/expanding) rather than a leaders-list boolean — pick
whichever the actual computed values naturally produce, don't force it
into an `in_gmma` flag if the reference output is really a state machine.

## Task 5: Qullamaggie Suite

Source: `metaData_v1/src/screeners/qullamaggie_suite.py`. RS ≥ 97 across
1w/1m/3m/6m + perfect MA stack (`Price ≥ EMA10 ≥ SMA20 ≥ SMA50 ≥ SMA100 ≥
SMA200` — note SMA20/SMA100 don't exist in this project yet, will need
new columns) + ATR-relative-strength ≥ 50 vs the $1B+-market-cap universe
+ price in upper half of the 20-day range + market cap ≥ $1B. More
new-column work than Tasks 1-4 (multiple new MA periods, a new
cross-sectional ATR-RS rank using `indicators.cross_sectional_percentile`
the same way SCOOTER/RS already do) — budget more time than the earlier
tasks.

## Task 6: Volume anomaly detectors

Source: `metaData_v1/src/screeners/volume_suite_components/` —
`HVAbsoluteETC.py`, `HVStdv.py`, `enhanced_volume_anomaly.py`. Multi-method
statistical volume-anomaly detection (std-deviation-based spike
detection, benchmark comparisons). Genuinely screener-shaped (multi-step
logic → a flag), more involved than Task 3's plain indicators — read all
three source files together before starting, they're related.

## Task 7: ADL 5-step accumulation suite

Source: `metaData_v1/src/screeners/ad_line/` (prefer this refactored
package over the top-level `adl_screener.py` monolith — see
`SCREENER_INVENTORY.md`). Five sequential steps: `adl_calculator` →
`adl_mom_analysis` → `adl_short_term` → `adl_ma_analysis` →
`adl_composite_scoring`. The biggest task in this backlog — a genuinely
new signal type (institutional accumulation via the A/D line), multi-file
port. Do this last; by this point the `src/leaders/`+`config.py`+
`validate.py`+dashboard-wiring pattern should be routine.

## Not in this backlog (separate decisions, don't pull in without asking)

- **Stockbee's Industry Leaders** (4th sub-strategy) — cross-sectional
  industry ranking belongs to the separate Step-1 market/sector module
  `intro.md` scoped out of this project, not this one.
- **Dr. Wish, PVB** — Step-3 entry-timing signals per `intro.md`'s own
  scope decision, not Step-2 leader classification.
- **`value_momentum_screener.py`** — flagged in `SCREENER_INVENTORY.md`
  as exploratory/weaker than the others; optional, lowest priority, ask
  before spending time on it.
- **`breakout_screener.py`** — possible fast-start VCP-lite proxy per
  `VCP_RESEARCH.md`, but that's a different initiative (full VCP), not
  part of this backlog — don't fold it in here.

## Permanently excluded — do not implement

- **Giusti momentum ranking** — user decision: excluded for good, not a
  "later round" candidate. Don't port `giusti_screener.py` in any future
  round of this list.

## Definition of done (apply to each task separately)

- [ ] New module under `src/leaders/`, docstring cites the `metaData_v1`
      source file and original methodology link
- [ ] Thresholds live in `config.py`, not hardcoded in the module
- [ ] New columns land in `screener_results.csv` via `run_screeners.py`
- [ ] `validate.py` check added and passing — **behavioral**, asserting
      an actual mask/ticker-count match, not just "ran without crashing"
      (this is the exact gap that let the feedback_2.md §0 regression
      through — don't repeat it)
- [ ] Any new dashboard filter/preset that uses these columns gets wired
      into `dashboard_filters.py` **and** its own `validate.py` check if
      it's a preset (same reasoning as above)
- [ ] `dashboard.py` shows the new column(s) somewhere (Leaders tab
      expander or `view_cols`)
- [ ] Full `validate.py` run still green — **all** checks, not just the
      new ones

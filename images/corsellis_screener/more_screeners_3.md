# More screeners, round 3 (DRAFT) — StockCharts/EarningsBeats-style scans + the metaVolume idea

**Status: draft, not yet a task list to hand off.** Research only, ranked
by simplicity as requested. Two sources feeding this draft:
1. Five scan syntaxes the user pulled from an EarningsBeats.com writeup
   (StockCharts scan-language conditions), evaluated against what this
   project already has.
2. The "future trigger" idea raised while discussing whether to fold
   `metaVolume` (a separate, mature standalone project — HVE/HVD volume-
   milestone tracking with its own pre/post-processor pipeline) into this
   one: *if* live, filterable, always-fresh HVE/HVD columns are ever
   wanted (composable with Minervini/Stage/RS the way the built-in
   screeners are, not a manually re-uploaded list), that would mean
   porting a **simplified version of just the HVE/HVD logic** as a new
   `src/focus/` screener — same pattern as the existing 3σ
   `volume_anomaly.py`. Listed here as item 6, lowest priority, since
   the recommendation for now is still "keep it separate, upload as a
   list" (see the conversation this draft follows from).

## Quick summary, simplest first

| # | Scan | Kind (`TAXONOMY.md`) | Difficulty | What's already built that helps |
|---|---|---|---|---|
| 4 | RSI 40-50 pullback | **Filter** | Trivial | `indicators.rsi()` already exists, fully unused today |
| 5 | 52-week-high breakout | **Filter** (derived event flag) | Trivial-Low | `indicators.rolling_high()` + `config.BARS_52W` already exist; `pct_from_52w_high` is the closest existing cousin |
| 3 | 20-day EMA pullback test | **Screener** (3 conditions + SCTR gate + added slope check) | Low | SCTR = `scooter_score`, already computed; only EMA20 + a rising-slope check are new |
| 2 | Downtrend reversal (6-day lower-highs) | **Screener** (6-day chained condition) | Low | Nothing reused, but pure `.shift()`/rolling comparisons, no loops, no new indicator needed |
| 1 | High volume (intraday pace) | **Blocked as literally specified** | — | This project has no intraday data source at all — see below |
| 6 | metaVolume HVE/HVD (simplified port) | **Screener** | Medium-High | Separate standalone project to distill, not a source-file port — lowest priority, only if live composability is actually wanted |

## 4. RSI 40-50 Test — simplest of all five

Syntax: `RSI(14, Close) > 40 AND RSI(14, Close) < 50`

`src/indicators.py:92` already has `rsi(close, period=14)` — written,
tested implicitly by nothing calling it yet, just never wired into
`run_screeners.py`'s output or `dashboard_filters.py`'s filter panel.
This is the cheapest possible addition in this whole draft: add
`ctx['rsi14'] = indicators.rsi(close).iloc[-1]` to `run_screeners.py`,
add one `FILTER_SPECS` row (`'rsi14', 'RSI 14', 'rsi14', <new 0-100
family>`) to `dashboard_filters.py`. No new module, no `config.py`
threshold (RSI's 40/50 bounds are exactly what the *user* picks in the
UI dropdown/slider, same as every other filter — not baked in).

## 5. 52-Week Highs (Breakout Scan) — very simple

Syntax: `Daily High > Yesterday's MAX(253, Daily High)`

`indicators.rolling_high(close, window=config.BARS_52W)` already exists
and already backs `pct_from_52w_high` (a *continuous* "how far below the
high" metric, already in `screener_results.csv`). What's missing is the
discrete **event** flag this scan actually asks for — "did today's High
newly exceed the past ~253 days' High" — which `pct_from_52w_high` alone
doesn't tell you (it could read 0% or slightly negative on an old high
day without today specifically being a *fresh* breakout). One new
derived boolean column (`in_52w_breakout` = `high.iloc[-1] >
rolling_high(high, 253).shift(1).iloc[-1]`), reusing the existing
rolling-high machinery almost directly. Borderline filter/screener by
`TAXONOMY.md`'s letter (it's a sharper cut of an existing metric rather
than combining ≥2 raw indicators) — treat as a lightweight filter
column, no new module needed.

## 5b. 52-Week Lows (symmetric addition, not from the original 5 scans)

Added by user request, mirroring #5 exactly in the opposite direction:
`Daily Low < Yesterday's MIN(253, Daily Low)`. `indicators.rolling_low()`
already exists (same file, same `BARS_52W` default) and `pct_from_52w_low`
is already a computed column, same relationship to this new flag as
`pct_from_52w_high` has to #5's breakout flag. Identical shape, identical
effort — build both together (`in_52w_high_breakout` /
`in_52w_low_breakdown`).

## 3. 20-Day EMA Test (Pullback Scan) — simple, reuses SCOOTER

Original syntax: `SCTR>75 AND Open>EMA(20) AND Low<EMA(20) AND Close>EMA(20)`

**Decision: add a 5th condition, EMA20 rising, not left implicit via
SCTR alone.** The source syntax doesn't check the EMA's slope directly —
SCTR>75 only implies an uptrend indirectly. To make this a genuine
pullback-in-an-uptrend test rather than "price is near *some* average
today," add an explicit slope check: **EMA20 today > EMA20 N days ago**
(a simple point-to-point comparison, e.g. N=5 or N=10 trading days —
lighter-weight than Golden Launch Pad's OLS-regression slope check,
since this scan doesn't need that level of rigor; a plain "up from N
days ago" is the standard, common way this kind of condition is checked
and keeps the whole scan a single-pass vectorized comparison).

Full condition set once built:
1. `SCTR > 75` (`scooter_score > 75`, already computed)
2. `Open > EMA20`
3. `Low < EMA20`
4. `Close > EMA20`
5. `EMA20 > EMA20.shift(N)` (rising) — **new, added per this decision**

All-daily-bar fields (Open/Low/Close are standard OHLC, not intraday
ticks — this one's fully computable end-of-day despite reading like an
intraday test). `SCTR` maps directly to the already-computed
`scooter_score` (round-1 screener, validated, in `screener_results.csv`
today). The only new piece is EMA20 itself — `indicators.ema(close, 20)`
is a one-line call using the existing `ema()` helper (this project
currently exposes EMA10/21 and SMA50/200, not EMA20 specifically); the
slope check is one more `.shift(N)` comparison on that same column, no
new machinery. Once EMA20 exists, all five conditions are a straight
`&`-chain across the wide matrices — no loop, no state. This is a
genuine multi-condition **screener** by `TAXONOMY.md`'s test (combines
≥2 raw indicators into one named pass/fail), but still a small,
same-day-snapshot one — same tier as Stockbee's movers from round 1, not
GLB-tier. The slope-lookback `N` should live in `config.py` as a named
constant (e.g. `EMA20_SLOPE_LOOKBACK`), not hardcoded inline.

## 2. Downtrend Reversal (Pullback Scan) — simple, nothing reused

Syntax: today's High > yesterday's High, AND a strictly declining
sequence of daily Highs for the 6 days before that (each of the prior 6
days' highs lower than the one before it).

No existing column helps directly, but this needs nothing exotic either
— it's six `.shift(n)` comparisons chained with `&`, fully vectorizable
across the whole matrix in one shot (`high.shift(1) > high.shift(2) >
... > high.shift(6)`, then `high > high.shift(1)` for today). No pivot
detection, no forward-scanning, no per-ticker loop — same computational
shape as `breakout_screener.py` from `more_screeners_2.md` (Low
build, Fast runtime). Slightly more new logic than #3 or #5 since
nothing's reused, but still a same-day, single-pass condition.

## 1. High Volume (intraday pace) — blocked as literally specified

Syntax: `Daily Volume > Daily SMA(90, Daily Volume) * 0.40`

Read the *purpose* text carefully, not just the syntax — this scan is
explicitly meant to run **intraday, close to 10:00am ET**, comparing
**partial-day volume-so-far** against a benchmark, to catch stocks
pacing toward an unusually heavy full day early in the session. The
"× 0.40" isn't a loose full-day threshold (which would barely filter
anything) — it only makes sense as "40% of the 90-day average daily
volume already traded within the first ~1-1.5 hours," which is a strong
signal precisely because so little of the session has elapsed.

**This project has no intraday data source at all** — everything here
is end-of-day daily bars (`config.DAILY_ARCHIVE`/`DAILY_CURRENT`, one
row per completed session). This isn't a "hard to compute" problem like
GLB was — the data this scan needs literally doesn't exist anywhere in
this pipeline. Two honest paths, not a difficulty question:

- **Out of scope as specified**, unless/until an intraday volume feed
  gets added to `downloadData_v1` (a much bigger undertaking, well
  outside this project's boundary).
- **A different, EOD-adaptable scan** exists nearby if a full-day
  relative-volume signal is what's actually wanted instead: "today's
  *closed* full-day Volume > K × its 90-day SMA." That's a trivial
  filter (`avg_volume` vs `rolling(90)` already has the building blocks)
  — but it's not the same signal. It loses the entire "catch it early in
  the session" purpose the scan was designed for, and it's also close to
  redundant with what Stockbee's relative-volume checks and
  `volume_anomaly.py`'s z-score already cover. Worth a deliberate yes/no
  from the user before building the EOD version under the same name —
  don't silently reinterpret "Scan #1" as something materially different
  from what it says.

## 6. metaVolume HVE/HVD (simplified port) — future, lowest priority

Carried over from the conversation this draft follows from. Not source-
file porting like everything else in this project — `metaVolume` is a
mature, separately-operated system (frozen baseline + safe-to-replay
incremental daily checker). If ever wanted as live composable columns:
distill just the HVE (expanding-cummax milestone) and HVD (top-N-ever
ranking) *logic* into a new `src/focus/` module, same spirit as
`volume_anomaly.py`, rather than importing or re-running metaVolume
itself from inside `screeners`. Only worth doing if the upload-a-list
workflow (already fully functional today, zero new code) turns out not
to be enough — see the fuller reasoning in the conversation this item
came from.

## Suggested order if/when this becomes a real task list

**4 → 5 → 3 → 2**, all low-effort and independent of each other (any
order among them is fine, this is just cheapest-first). **1** needs an
explicit scope decision before anything gets built under its name. **6**
sits in the backlog, no urgency, revisit only if the "want live
composability" trigger condition actually comes up.

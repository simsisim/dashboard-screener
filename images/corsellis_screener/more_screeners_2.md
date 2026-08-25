# More screeners, round 2 — the harder ones

Step 1 only, per your instruction: **difficulty/time approximation**, grounded
in actually reading each source file (not guessing from docstrings). No
scope or priority decisions here yet — that's a separate step. Files
covered: `pvb_screener.py`, `drwish_screener.py` (+ `drwish_charts.py`),
`breakout_screener.py`, `atr1_screener.py`, `atr1_trailing_stops.py`,
`atr_screener.py`, and (added after the fact, different source project)
`patterns_v0`'s Cup & Handle detector.

**Two different things get called "difficulty/time" below — they don't
always move together, so they're now split into separate columns:**
- **Build difficulty / est. build time** — how long it takes a developer
  to read the source, port the logic, and validate it. A one-time cost.
- **Runtime cost** — how long the *resulting* screener adds to every
  `run_screeners.py` pass over the full ~4,000-ticker universe (the
  README's "full universe, ~1-2 min" number). This is the ongoing cost,
  and it's what "is this the Dr. Wish problem" is really asking about.
  Something can be slow to build but fast to run, or vice versa — GLB
  below is unusual in being bad on *both* axes at once.

## Quick summary

| Screener | Build difficulty | Est. build time | **Runtime cost** | Why |
|---|---|---|---|---|
| `breakout_screener.py` | **Low** | ~30-45 min | **Fast** | one vectorized rolling-window op across the whole matrix at once, same shape as Task 1/2 in `more_screeners.md` |
| `pvb_screener.py` | **Medium** | ~1.5-2 hrs | **Moderate** | signal is *stateful* (Buy/Sell/Close persists across days) — needs a per-ticker loop, but a single straight pass per ticker, no nested scanning |
| `atr1_screener.py` (vol_stop / ATR cloud) | **Medium-High** | ~2-3 hrs | **Moderate** | genuinely recursive per-bar calc (each day depends on the day before) — also a per-ticker loop, also a single straight pass, same cost profile as PVB |
| `atr1_trailing_stops.py` | *(rides on atr1_screener.py)* | +~20 min | *(rides on atr1_screener.py)* | thin wrapper around the above, no new math |
| `atr_screener.py` (ATR2) | **Low for the new part** | ~30 min if wanted | **Fast** (already-ported part) / **Moderate** (stop half, if built) | the screening part is already ported/validated; only the trailing-stop half is new, and it duplicates atr1_screener.py's math |
| `drwish_screener.py` — Blue Dot / Black Dot | **Medium** | ~1.5-2 hrs combined | **Fast** | built on a plain rolling-window stochastic calc — vectorizable, not the expensive part of Dr. Wish |
| `drwish_screener.py` — GLB (Green Line Breakout) | **High** | ~3-5+ hrs | **Slow — the real risk** | nested historical pivot-scan, O(n²)-shaped per ticker — **this is "the Dr. Wish problem" you flagged**, and it's the only one here that's bad on both axes at once |
| `drwish_charts.py` | **N/A** | — | **N/A** | not a screener, a matplotlib chart-image generator; no equivalent need in this project (dashboard already has sparklines) |
| `patterns_v0` Cup & Handle detector | **Medium-High** | ~2.5-3.5 hrs | **Fast-ish/Moderate** | `scipy.find_peaks` is one fast vectorized call per ticker, no nested forward-scan like GLB — the "Medium-High" rating is entirely about *build* complexity (new architecture, output reshaping, a threshold-tuning judgment call), not runtime |

## `patterns_v0` — Cup & Handle detector — build: Medium-High (~2.5-3.5 hrs), runtime: Fast-ish/Moderate

Different source project from the `metaData_v1` batch above:
`/home/imagda/_invest2024/python/patterns_v0/src/cup_handle_detector.py`
(486 lines) + `cup_handle_config.py` (105 lines, CSV-driven thresholds) +
`peak_trough_detector.py` (172 lines). Implements the "kanwalpreet18"
5-point (K-A-B-C-D) cup-and-handle methodology: K=prior trend start,
A=left rim, B=cup bottom, C=right rim, D=handle bottom.

**Computationally, this is fine** — cheaper than it looks. Peak/trough
detection uses `scipy.signal.find_peaks` (`peak_trough_detector.py:44,52`),
a single vectorized, C-backed call per ticker — no O(n²) risk like GLB.
`_find_pattern_points` then loops over the *troughs found* (typically a
few dozen per ~1700-bar series, not thousands) filtering nearby peaks
with list comprehensions — cheap. Validation and quality-scoring
(`_validate_cup_formation`, `_validate_handle_formation`,
`_calculate_quality_score`) are simple arithmetic on 5 scalar price
points. At ~4000 tickers this should run in seconds, not minutes.

**Where the time actually goes:**
1. **Architecture mismatch.** Everything built so far in this project is
   either a same-day snapshot evaluated across the whole wide matrix at
   once (Minervini, GLP, Stockbee, Qullamaggie) or a per-ticker state
   machine (PVB, ATR cloud). This is a third shape: per-ticker **multi-
   point pattern matching over history** — closer in spirit to VCP
   (`VCP_RESEARCH.md`) than to anything already built. It has to run as
   a per-ticker loop (`scipy.find_peaks` needs each ticker's own close
   series separately), and the K-A-B-C-D point-finding logic
   (`_find_pattern_points`, `cup_handle_detector.py:191-269`) is real new
   logic to port faithfully, not just a threshold translation.
2. **Output shape doesn't fit this project's convention.** The source
   returns one nested result dict per ticker (pattern points, quality
   score, target price, stop loss) via an OOP `CupHandleDetector` class
   and CSV-based config loading — this project wants flat columns in
   `screener_results.csv` (`in_cup_handle`, `cup_handle_quality_score`,
   `cup_depth_pct`, etc.), so the result structure needs re-shaping, not
   just the math.
3. **A real fidelity question, not just difficulty.** `readme.md` in
   `patterns_v0` documents its own tuning history: the *textbook*
   O'Neil-style thresholds (which is what "cup and handle" normally
   means — cup depth ~12-33%, handle in the *upper third* of the cup)
   produced almost no matches, so they were progressively loosened —
   min cup depth 10%→1%, max depth 25%→80%, duration 5-10 days→3-120
   days, handle position "upper 30%"→"anywhere in the cup" (0% minimum),
   handle max depth 40%→100% — to get a 45.5% hit rate with an **average
   quality score of 18.2** (out of 100). That's the config this project
   would inherit by default. Worth deciding *before* porting whether to
   (a) use the loosened config as-is (fast, but arguably not detecting
   "cup and handle" in the classical sense any more — more like "any
   dip-then-bump"), (b) restore closer-to-textbook thresholds and accept
   a much lower hit rate, or (c) treat the config as tunable in
   `config.py` from day one (same approach already recommended for VCP)
   rather than porting one fixed number set. This is a judgment call,
   not something the code itself resolves.

## `breakout_screener.py` — build: Low (~30-45 min), runtime: Fast

Rolling max/min over a lookback window, a range-tightness check, a
breakout-above-resistance threshold, and a volume-surge ratio. Same shape
as everything already built in `more_screeners.md` (Task 1/2/3) — pure
rolling-window arithmetic, fully vectorizable over the wide matrices, no
per-bar state. The easiest file in this batch by a clear margin.

## `pvb_screener.py` — build: Medium (~1.5-2 hrs), runtime: Moderate

The indicator layer (`Price_Highest`/`Price_Lowest`/`Volume_Highest`/`SMA`
in `_calculate_pvb_TWmodel_indicators`) is trivial rolling-window math,
same as `breakout_screener.py`.

The complexity is in `_generate_pvb_TWmodel_signals`: this isn't a
same-day snapshot condition like Minervini/GLP/Stockbee — it's a **state
machine**. A "Buy" signal, once triggered, *persists* across days until
either a "Sell" fires or 5+ consecutive days close below the SMA trigger
a "Close Buy." To know today's signal state you conceptually need to walk
forward from the last state change, not just look at today's row in
isolation. The reference implementation does this with an explicit
per-ticker Python loop (`for i in range(1, len(data))`) carrying
`current_signal`/`consecutive_days` forward.

This is portable to the wide-matrix architecture, but not as a single
vectorized boolean like the round-1 screeners — it needs either (a) a
per-ticker loop over each ticker's own history (cheap per-ticker at
~1700 bars, ~4000 tickers total — a few seconds, not a bottleneck by
itself) or (b) a vectorized "days since last True" trick using
`groupby`/`cumsum` on the raw breakout/reversal booleans, which is more
elegant but requires more careful thought to get exactly right
(the 5-consecutive-day close condition and the "signal doesn't re-fire
while already in that state" logic both need to survive the vectorization
without behavior drift).

## `atr1_screener.py` (`vol_stop` / ATR Cloud) — build: Medium-High (~2-3 hrs), runtime: Moderate

Read `vol_stop()` directly (`atr1_screener.py:41-85`) — this is a
**genuinely recursive** calculation, not just "stateful" like PVB. Each
day's `stop` level depends on *yesterday's* `stop`/`max`/`min`/`uptrend`,
with a conditional reset whenever the trend flips (`max`/`min`/`stop` all
get reseeded to the current price). This is the same computational shape
as a SuperTrend/Chandelier-exit indicator — the classic case that resists
plain `pandas.rolling()` vectorization because each step's output feeds
directly into the next step's branching logic.

The reference implementation's per-bar loop uses `.iloc[i]`/`.loc[idx,
col] = ...` inside the loop, which is slow in practice (repeated
label-based indexing on a growing frame). A faithful port should drop
down to raw numpy arrays inside the per-ticker loop (state carried in
plain floats/bools, not DataFrame cells) — still a Python loop per
ticker, but meaningfully faster than the source's own approach. At
~4000 tickers × ~1700 bars, a numpy-array version of this loop should
run in low single-digit seconds; a naive line-for-line port keeping the
`.iloc`/`.loc` pattern could be noticeably slower — worth doing the numpy
version from the start rather than porting the indexing style verbatim.

**Note:** `atr_screener.py` (ATR2) independently implements the *same*
"ATR cloud" concept a second time
(`_calculate_volatility_stops_atr_cloud_style`, same `length=20,
factor=3.0, length2=20, factor2=1.5` signature) — these two files
duplicate each other's trailing-stop math. If this ever gets built, pick
one source, not both.

## `atr1_trailing_stops.py` — rides on atr1_screener.py (both axes), +~20 min build

Thin wrapper: imports `calculate_atr_cloud` from `atr1_screener.py`
directly and reformats its output. No new math — the entire cost here
*is* `atr1_screener.py`'s cost. If that one's built, this one is close to
free; if it isn't, this one has nothing to stand on.

## `atr_screener.py` (ATR2) — build: Low for what's actually new (~30 min if wanted), runtime: Fast (already-ported part) / Moderate (stop half)

Per `SCREENER_INVENTORY.md`, the volatility-percentile screening half of
this file (High/Low volatility classification, `ATRext_$` thresholds) is
**already the validation reference** `src/focus/atr_extension.py` is
checked against in `validate.py` — nothing new to port there, it's
already done.

The only genuinely new part is `_calculate_volatility_stops_atr_cloud_style`
/ `generate_atr_trailing_stops` (`:302-369, 438-509`) — which, as noted
above, is a second implementation of the exact same ATR-cloud trailing
stop as `atr1_screener.py`. Not worth building twice; if the trailing-stop
concept gets built at all, it should be built once (from whichever source
reads cleaner) and shared, not duplicated across two modules the way the
source project has it.

## `drwish_screener.py` — Blue Dot / Black Dot — build: Medium (~1.5-2 hrs combined), runtime: Fast

`detect_blue_dot_signals` (`:314-360`) and `detect_black_dot_signals`
(`:361-418`) are each ~50-60 lines, built on `calculate_stochastic`
(`:82-97`, a plain rolling-window %K — fully vectorizable, cheap) plus
some trend-confirmation conditions. Based on function size and the
building blocks they call, these look same-day-snapshot-shaped (like
Stockbee/GLP), not history-scanning like GLB below — I did not read
their full bodies line-by-line, so treat this estimate as provisional
until someone actually opens `:314-418` before starting.

## `drwish_screener.py` — GLB (Green Line Breakout) — build: High (~3-5+ hrs), runtime: Slow — the real risk

This is "the Dr. Wish problem" — the one screener in this whole list
that's bad on *both* the build-difficulty and runtime-cost axes at once,
which is exactly what you were asking about. Everything else in this
document, including Cup & Handle which got a similar-looking "Medium-High"
build rating, is fine at runtime — only this one risks slowing down every
daily `run_screeners.py` pass. Reading
`calculate_historical_glb_levels` (`:149-238`) confirms why —
it's not just a big function, it's **algorithmically expensive**:

- `is_pivot_high` (`:99-119`) does a manual left/right comparison loop
  per candidate bar — O(strength) per call, called potentially thousands
  of times.
- `calculate_historical_glb_levels` wraps that in an **outer loop over
  every bar** in the historical lookback window, and for **every pivot
  found**, runs an **inner loop scanning forward** through the rest of
  the series to find when/if that level eventually breaks
  (`:200: for future_bar in range(bar_index + confirmation_bars,
  len(df))`). That's an O(n²)-shaped cost per ticker in the worst case —
  many pivots × a forward scan for each one.
- `detect_glb_signals` (`:240+`) does a similar pivot-then-scan pattern
  again for live signal detection.

At ~1700 bars/ticker × ~4000 tickers, a line-for-line port of this
(especially keeping the source's `.iloc`-in-a-loop style) is a real risk
of running for minutes rather than seconds — plausibly the slowest thing
in this entire project if ported naively. It's *possible* to vectorize
the core "next bar where cumulative-max clears this level" question with
numpy (rolling-forward-max comparisons instead of an explicit inner
loop), but that's a meaningfully harder rewrite than a faithful port,
not just a translation — budget accordingly if this one's ever attempted.

## `drwish_charts.py` — not applicable

471 lines, entirely `matplotlib` chart-image generation
(`_plot_glb_signals`, `_plot_blue_dot_signals`, etc.) — this is a
companion visualization tool for `drwish_screener.py`'s own separate
report workflow in `metaData_v1`, not a screener itself. This project has
no per-ticker chart-image pipeline (the closest equivalent is the
Streamlit `LineChartColumn` sparkline already in `dashboard.py`, which is
a completely different, much simpler mechanism). Nothing here to port
regardless of what happens with `drwish_screener.py`.

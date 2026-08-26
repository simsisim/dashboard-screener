# Multi-scenario GLB / Cup&Handle: a shared-primitive pivot model

## The question

`glb.py` exposes 3 tunable knobs: `pivot_strength`, `lookback_bars`,
`confirmation_bars`. The dashboard lets a user flip between scenarios like:

  a) lookback 3m (63d),  confirmation 2w (10d)   — today's default
  b) lookback 6m (126d), confirmation 1m (21d)
  c) lookback 1-2y (252-504d), confirmation 3m (63d)

Today, each scenario is computed as an independent full O(n) rescan (`glb.py`'s
`_compute_records`, one call per parameter combo). `cup_handle.py` has the same
shape of problem across its 3 presets (`strict`/`default`/`loose`) — different
`prominence_threshold`/`distance_threshold` change what counts as a peak/trough,
so `scipy.signal.find_peaks` is called fresh per preset too.

The question: is there a shared computation that N parameter combos can all
draw from, instead of N independent full passes?

## What the reference implementations actually do

- `kanwalpreet18/canslimTechnical` (R): kernel-smooth the price series
  (`np::npreg`, local-linear), find local extrema of the **smoothed** curve
  (`diff(sign(diff(fitted)))`), then walk a 4-point state machine over
  *consecutive extrema* (peak→trough→peak→trough) checking **ratios**
  (retracement %, e.g. trough must be 65-85% of the peak) and **durations**
  (day-count ranges between consecutive extrema), gated by an up/down
  volume ratio ("relative price volume") as a conviction filter. This is a
  textbook cup-and-handle detector, and structurally it's exactly what this
  repo's `cup_handle.py` already does (K-A-B-C-D via `find_peaks` +
  depth/duration/tolerance checks) — same family of algorithm, independently
  arrived at.
- `HumanRupert/marketsmith_pattern_recognition` (Python): turned out to be a
  thin REST client for MarketSmith's own (proprietary, server-side) pattern
  API (`src/ms/pattern.py`) — it fetches `cupWithHandles` from MarketSmith,
  it doesn't compute them. No algorithm to borrow here, just confirmation
  that "cup with handle" is MarketSmith's own vocabulary for this family of
  shape.
- `tysoncung/crypto-chart-patterns` (`pattern_detector.py`): smooths price
  with a short moving average, takes `scipy.signal.argrelextrema` for
  local max/min, then slides a **fixed 5-point window over consecutive
  extrema** and tests simple inequality/tolerance predicates per pattern
  (Head & Shoulders, Double Top/Bottom, ...). Same shape as the other two:
  reduce to a sparse extrema sequence once, then pattern-match a small
  fixed-size window over it. It doesn't address multi-parameter reuse at
  all (one smoothing/window config per run) but it's a third independent
  confirmation that "sparse extrema sequence + predicate window" is the
  general-purpose primitive underlying this whole family of patterns, not
  just GLB/Cup&Handle.

So the useful algorithmic idea (from canslimTechnical, and already present in
this repo's `cup_handle.py`) is: **reduce the O(n)-bar series to a sparse
sequence of extrema, then match shape via ratios/durations over that sparse
sequence.** GLB is the same idea in miniature — it's a degenerate 1-pivot
"cup" (find the dominant pivot high in a window, require it to hold for a
confirmation window, breakout = close above it) with no cup-depth/duration
ratio checks at all.

## The mathematical property that makes multi-scenario cheap

Both `glb.py`'s pivot test and `cup_handle.py`'s extrema test have a
**nesting property**: making the parameter *stricter* only ever **removes**
candidates, never adds new ones.

- GLB: `is_pivot_high(strength=s)` requires `H[p]` to beat the max over a
  left/right window of size `s`. A bigger window is a superset of a smaller
  one, so `max` over it is `>=` the smaller window's max. **A pivot valid at
  a large strength is automatically valid at any smaller strength.** The
  pivot set is monotonically non-increasing in `s`.
- Same logic for `lookback_bars` (a candidate that's the max over a *longer*
  trailing window is also the max over any shorter trailing window ending at
  the same point) and for `confirmation_bars` (checking "no higher high in
  the next C bars" for a *larger* C is a strictly harder test than for a
  smaller C).

This means: computing at the finest (most permissive) setting used across
all scenarios, once, and then filtering that one candidate/statistic set for
each stricter scenario, is **provably equivalent** to rerunning the whole
scan per scenario — not an approximation.

`cup_handle.py`'s `find_peaks(prominence=..., distance=...)` extrema are
*approximately* nested the same way (looser prominence/distance -> more
peaks) but scipy's peak-suppression isn't proven strictly monotonic the way
a plain rolling-max is, so treat that one as a good empirical bet, not a
theorem — worth confirming empirically before relying on it (see
"Next steps").

## Prototype in this folder

`shared_primitives.py` reimplements GLB's cold-path record computation
(`compute_glb_multi`) so that for a *list* of scenarios it:

1. Computes the pivot mask once per **distinct** `pivot_strength` (dedup —
   today's 3 named scenarios all share strength=10, so this alone collapses
   3 passes into 1).
2. Computes the trailing rolling-max once per **distinct** `lookback_bars`.
3. Computes a *forward* rolling-max once per **distinct** `confirmation_bars`
   (replacing the per-pivot Python-loop slice-`max()` call in today's
   `_compute_records` with an O(1) array lookup — same nesting argument
   applies to confirmation length).
4. Only the breakout scan (level-dependent, since each pivot has its own
   price level) stays per-pivot; it was never the shared part.

`validate_against_glb.py` loads real daily OHLCV for a handful of tickers,
runs the 3 named scenarios through both today's `glb.py` (baseline, one
independent cold pass per scenario) and the new shared engine, and asserts
the two produce byte-identical records — this is meant to be a **reliability
check**, not just a speed demo: the whole point is that sharing computation
must not change a single answer.

## Result

Run `python3 research/pivot_model/validate_against_glb.py` — it prints, per
ticker, whether all 3 scenarios match exactly, and the wall-clock for
"3 independent passes" vs "1 shared pass". On 9 real S&P tickers (~1670
daily bars each, archive+current), scenarios a/3m·2w, b/6m·1m, c/1-2y·3m
(pivot_strength held at 10 across all 3, per the conversation — only
lookback/confirmation vary):

```
All tickers/scenarios match: YES
Per-scenario dedup: distinct pivot_strengths=1, distinct lookbacks=3, distinct confirmations=3, scenarios=3
Baseline (3 independent passes): ~29 ms
Shared engine (1 pass, all 3):   ~19 ms
Speedup: ~1.5x
```

The dedup print shows why: pivot_strength is shared across all 3 named
scenarios (the pivot mask, the most expensive step, computes once instead
of 3x), while lookback and confirmation each still need 3 distinct rolling
arrays since the 3 scenarios never repeat those values. If a user actually
toggles between just 2 of the 3 (as the "compares settings back and forth"
case in TODO_caching.md describes), the win compounds with the existing
per-ticker incremental cache once both changes land together — the shared
pass only has to (re)happen once per NEW bar, not once per (bar × scenario).

**A bug the validation step caught, worth keeping as a cautionary note:**
the first version of `_rolling_forward_max` computed the confirmation
window as `conf` bars after the pivot; `glb.py`'s actual slice
(`highs[p+1:conf_end]` with `conf_end = min(p+conf, n)`) is `conf - 1`
bars — Python's exclusive slice end means the bar *at* `conf_end` is never
included. That one-bar discrepancy produced silent `MISMATCH`es on 2 of 9
tickers (JPM, XOM) — real cases where a high on that boundary bar changed
whether a pivot counted as confirmed. This is exactly why "reliable" means
*validate against the existing implementation on real data*, not just
"looks right by inspection" — an off-by-one here doesn't crash, it quietly
drops or keeps GLB levels.

## Next steps (not done yet — scope was "identify a simple, reliable model")

- If this validates cleanly, the same dedup can slot into `glb.py`'s real
  incremental cache (this is the actual fix for `TODO_caching.md`): instead
  of one cache file per `(ticker, params_hash)`, cache the shared arrays
  per `(ticker, pivot_strength)` / `(ticker, lookback_bars)` /
  `(ticker, confirmation_bars)` and let scenarios recombine them.
- **Checked** (`check_cup_handle_nesting.py`, 60 random tickers from the
  actual universe, `strict`/`default`/`loose` peaks+troughs): unlike GLB,
  cup_handle's presets do **not** nest as a mathematically guaranteed
  chain. `default -> loose` and `strict -> loose` were 100% exact-subset
  on this sample (0 violations out of ~3,800-7,800 points each), but
  `strict -> default` had 0.4% of strict's peaks/troughs genuinely absent
  from default (not just index-shifted — confirmed absent even allowing
  +/-2 bars), on 18/60 tickers (7/60 once you allow the +/-2 bar
  tolerance). Root cause: `prominence_threshold` and `distance_threshold`
  change together per preset, and scipy's greedy distance-suppression
  interacts with prominence in a way that isn't a single monotonic dial —
  a point can survive at both the loosest and the strictest setting yet
  get suppressed at the in-between one. **Conclusion: don't port GLB's
  "compute once at loosest, filter down" trick to cup_handle's presets
  without accounting for this** — it would be a ~99.6%-correct
  approximation, not the exact equivalence GLB gets. Given `find_peaks`
  itself is cheap relative to the rest of the K-A-B-C-D matching, the
  right call is to leave the 3 presets calling `find_peaks` independently
  as today, rather than trade guaranteed correctness for a speedup on a
  part that isn't the bottleneck.
- The hierarchical/percentage-threshold "zigzag" approach (used in a lot of
  real multi-scale technical-pattern literature) is a more radical
  unification — one swing decomposition serving *both* GLB and Cup&Handle
  as different-length matches over the same sparse pivot list — but that's
  a bigger design change than "identify a simple, reliable model" calls for
  right now, flagged here for later.

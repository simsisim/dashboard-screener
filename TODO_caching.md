# RESOLVED (GLB) / TODO (PVB, ATR1): per-ticker caches don't support
# multiple parameter combos warm at once

## Status: fixed for GLB

`glb.py`'s cache is now namespaced by `params_hash` (see `_cache_path`,
`src/patterns/glb.py`): `results/glb_cache/{SYMBOL}__{hash8}.json`, one file
per `(ticker, params_hash)` instead of one per ticker. Switching between two
regularly-alternated parameter combos (e.g. Confirmation 1m vs 3m) no longer
evicts the other — each keeps its own persistent, independently-incremental
slot. The `params_hash` stored inside each file is still checked on load, so
a hash collision still falls back to a cold rebuild rather than ever
returning a wrong answer — the correctness guard described below is
unchanged, just no longer also acting as an eviction mechanism.

Alongside the cache-key fix, the confirmation check inside
`_compute_records` (no HIGH in the next `confirmation` bars exceeds a
candidate pivot's level) was switched from a per-pivot Python-loop
`np.max(highs[p+1:conf_end])` slice call to one precomputed forward-rolling-
max array (`_rolling_forward_max`, O(n) once per call) with O(1) lookups.
Both changes were validated byte-identical against the pre-change
implementation on 8 real tickers x 3 scenarios (0 mismatches) before
landing — see `research/pivot_model/` for the derivation, the nesting
argument that makes this a proof rather than an approximation, and an
off-by-one the validation script itself caught before this landed in
production (glb.py's own confirmation slice is `conf - 1` bars, not `conf`,
because of Python's exclusive slice end).

`validate.py`'s GLB reference check (§12) was updated to look up the
namespaced cache file (via `glb_mod._cache_path(t, phash)`) instead of the
old bare `{ticker}.json` path — it would otherwise have silently pointed at
a file `evaluate()` no longer writes.

The old bare-name cache files (`results/glb_cache/{TICKER}.json`, no `__`
suffix) are now orphaned/unused — harmless dead cache entries, left in
place rather than deleted since they're git-tracked and cleaning them up
wasn't asked for.

## Also added: `evaluate_multi()` — share work across scenarios in one call

The cache-namespacing fix above only helps when you come *back* to a
setting you've used before. It does nothing for the first time you try a
combo, and it does nothing if you want several scenarios' results at once
in a single call (today's dashboard calls `evaluate()` once per Run click,
one scenario at a time, so there was previously no caller shaped like
that).

`glb.evaluate_multi(tickers, data, scenarios: dict[name, params])` now
exists for that case: it computes several scenarios in one call, and for
scenarios that agree on `pivot_strength` / `lookback_bars` /
`confirmation_bars`, the pivot mask / lookback rolling-max / confirmation
rolling-max array for that shared value is computed once and reused,
instead of once per scenario. Each scenario still reads/writes its own
`(ticker, params_hash)` cache file exactly like `evaluate()` — this is
purely about not repeating identical work *within* one call, orthogonal to
the across-time caching above. Returns one DataFrame with `_{name}`-suffixed
columns per scenario (mirrors `cup_handle.py`'s preset-column convention).

Validated on real data before landing: `evaluate_multi()`'s per-scenario
output is exactly identical (cold and incremental) to calling `evaluate()`
separately for each scenario. Measured speedup on 40 real tickers x the 3
named scenarios (cold, no cache): **2.55x** (585ms calling `evaluate()`
three times vs 229ms via `evaluate_multi()` once) — bigger than the
`research/pivot_model/` prototype's ~1.5x because that used only 9 tickers;
the saved pivot-mask computation is O(ticker history length) so the
per-ticker win is roughly fixed, and just adds up across more tickers.

## Wired into the dashboard

`dashboard.py`'s Patterns tab now has a "Compare multiple lookback/
confirmation combos instead of one" checkbox next to GLB's Pivot strength
slider (`pt_glb_compare`). Checked, it disables the Lookback/Confirmation
dropdowns (pivot strength stays shared from the slider) and shows a small
picker — one row per candidate combo (`config.GLB_PRESET_CHOICES`: 3m/2w,
3m/6w, 6m/1m, 1y/3m, 2y/3m), each with its own checkbox (default selection:
`config.GLB_PRESET_DEFAULT_SELECTED` = the original 3m/2w, 6m/1m, 2y/3m).
Whichever are ticked get passed to `glb.evaluate_multi()` as that run's
scenarios — the user picks the subset, not a fixed preset. Results render
as one table with `_{name}`-suffixed columns per selected combo, row filter
= "signal under ANY selected combo", plus a caption showing how many
tickers had a signal out of how many were processed. The on-demand result
CSV gets its own `glb_compare_` file-key prefix (hashed on pivot_strength +
the sorted selected combo names) so different selections don't collide.

Deliberately NOT `st.data_editor` (an editable table would have been the
more natural widget) — this project's test harness is Streamlit's
`AppTest`, which as of streamlit 1.47 has no element type for driving
`st.data_editor` edits (only read-only `st.dataframe`). Per-combo
checkboxes are fully drivable by `AppTest` (`at.checkbox`), consistent with
how the rest of `test_dashboard_app.py` verifies behavior — a table's
polish wasn't worth losing that.

Verified via `AppTest`: default selection matches
`GLB_PRESET_DEFAULT_SELECTED`; ticking the other 2 combos and running
against NASDAQ 100 produced 0 exceptions and the expected 20 columns
(`as_of` + 4 columns x 5 combos); unticking all 5 disables Run and shows
"Pick at least one combo to run."

## Also added: whole-universe scope

Separately, the Patterns tab's Run button used to be `disabled=not
pt_indexes` — but `on_demand.resolve_scope()` already treats an empty
index-membership selection as "match everything," so that disabled
condition was silently blocking the one path that already worked. Added a
"run against the WHOLE universe" checkbox (`pt_whole_universe`) that maps
to an empty index list under the hood, and changed Run's disabled
condition to `not (pt_indexes or pt_whole_universe)`. Confirmed
`resolve_scope([], ...)` resolves to all 4,035 tickers in
`tradingview_universe.csv` (vs. 498 for S&P 500 alone) — the same universe
Leaders/Focus are built from.

## PVB / ATR1: still open, still theoretical

`pvb.py` and `atr1_cloud.py` keep the original single-slot-per-ticker cache
design (their own separate `_cache_path(ticker)`, untouched by the above).
Still not urgent — their parameters remain fixed constants in `config.py`,
not exposed as adjustable dashboard controls, so nothing today actually
switches params for these two. Apply the same `params_hash`-namespacing fix
if/when that changes.

---

## Original writeup (kept for context)

## The gap

`src/patterns/glb.py`'s incremental per-ticker cache (`results/glb_cache/{ticker}.json`,
same pattern copied into `src/timing/pvb.py` and `src/timing/atr1_cloud.py`
this session) stores exactly **one slot per ticker** — the cache filename is
built from the ticker only:

```python
def _cache_path(ticker: str) -> Path:
    d = config.RESULTS_DIR / config.GLB_CACHE_DIR_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d / f'{ticker.replace(".", "-")}.json'   # no params in the name
```

Each cache file stores the `params_hash` it was computed under, and
`_load_cache` checks it:

```python
if c.get('params_hash') != params_hash:
    return None   # mismatch -> treat as cold
```

**This is a correctness guard, not a performance solution.** It correctly
prevents ever returning a wrong answer (silently reusing pivots/state
computed under different settings) — but it does this by throwing the old
result away, not by keeping both around. So if you alternate between two
parameter combos you both use regularly — e.g. the dashboard's own "GLB
confirmation 1m" vs "confirmation 3m" controls, or Cup & Handle's Strict/
Default/Loose presets — **every single switch is a full cold recompute for
every ticker in scope**, because the one slot per ticker gets evicted each
time.

Notably, the **outer** whole-scope result cache (`on_demand.py`, the
same-day `results/{date}/patterns_glb_nasdaq100_cap0_{hash}.csv` files)
already does this correctly — different parameter combos get genuinely
separate CSV files, confirmed by `test_dashboard_app.py`'s "GLB confirmation
1m vs 3m keys are DISTINCT" check. It's specifically the *inner* per-ticker
incremental cache that doesn't follow that same pattern.

## Current impact

- **GLB**: real, practical impact — the dashboard ships adjustable
  Confirmation (1m/3m/...) and Lookback (1y/2y/...) controls, so a user
  who compares settings back and forth gets zero incremental-caching
  benefit while doing so.
- **Cup & Handle**: no incremental cache exists yet at all (separate,
  earlier-noted gap) — not affected by this specific issue, but relevant
  if/when it gets one, since it has 3 presets (Strict/Default/Loose).
- **PVB / ATR1**: same single-slot-per-ticker design (copied from GLB this
  session), but currently theoretical — their parameters are fixed
  constants in `config.py`, not exposed as adjustable dashboard controls,
  so nothing today actually switches params for these two.

## The fix, if wanted

Namespace the per-ticker cache filename by parameters too, mirroring what
the outer `on_demand.py` cache already does for its own CSVs:

```python
def _cache_path(ticker: str, params_hash: str) -> Path:
    d = config.RESULTS_DIR / config.GLB_CACHE_DIR_NAME
    d.mkdir(parents=True, exist_ok=True)
    short_hash = hashlib.md5(params_hash.encode()).hexdigest()[:8]
    return d / f'{ticker.replace(".", "-")}__{short_hash}.json'
```

Then two regularly-alternated settings each get their own persistent,
independently-warm slot per ticker instead of fighting over one. Same
change would apply to `pvb.py`/`atr1_cloud.py` if their parameters ever
become dashboard-adjustable.

**Not worth doing** if usage mostly settles on one parameter set per
module and rarely changes it — the added directory clutter (N cache files
per ticker instead of 1) isn't free, and the params_hash guard already
prevents wrong answers either way.

## Priority

Not urgent — worth revisiting if GLB's Confirmation/Lookback controls turn
out to get toggled often in real use. Recorded here so the tradeoff isn't
re-derived from scratch later.

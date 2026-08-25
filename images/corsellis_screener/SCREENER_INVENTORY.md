# Screener inventory: what's recyclable from `metaData_v1`

Research only — nothing implemented, nothing copied. Surveyed
`/home/imagda/_invest2024/python/metaData_v1/src/screeners` (25 modules +
4 subpackages: `ad_line/`, `quallamagie/`, `stockbee/`,
`volume_suite_components/`) to see which are candidates to port into this
project's `src/leaders/` or `src/focus/`, per the rule in `TAXONOMY.md`.

Short answer to "can some of these be recycled as screeners?" — **yes,
most of them**, because they all compute a new derived signal from raw
price/volume that this project doesn't currently have. A few are better
described as *new filter columns* once computed, two are already *the
reference implementation* this project validates against (not new
additions), and two blur into Step-3 "buy signal" territory that
`intro.md` explicitly scoped out of this module.

## Already the validation reference (not new — already in use)

- **`atr_screener.py`** / **`atr1_screener.py`** — per this project's own
  `README.md`, `validate.py`'s ATR14 and ATRext40 checks are compared
  against `metaData_v1`'s implementation already. These aren't "candidates
  to recycle" — they're already the ground truth `src/focus/atr_extension.py`
  is checked against.
- **`scooter_screener.py`**, **`rti_screener.py`**, **Minervini's trend
  template** — this project's README says SCOOTER was "ported verbatim
  from `test_scooter/sctr_model.py`" and Minervini from `lkm_rs`, RTI
  logic from the TradingView script directly — not from these
  `metaData_v1` files specifically, but the *same methodology* already
  exists here under different source modules. Worth a diff-check before
  porting anything new from `metaData_v1`'s versions, in case they drifted
  from the `lkm_rs`/`test_scooter` originals this project already trusts.

## Strong new-screener candidates (multi-indicator, produce a leaders-list-shaped flag/score)

| Module | What it computes | Fits as |
|---|---|---|
| `qullamaggie_suite.py` | RS ≥ 97 across 1w/1m/3m/6m + perfect MA stack (Price≥EMA10≥SMA20≥SMA50≥SMA100≥SMA200) + ATR-relative-strength ≥ 50 vs $1B+ universe + price in upper half of 20-day range + mkt cap ≥ $1B | `src/leaders/qullamaggie.py` — same shape as Minervini: a named methodology → `in_qullamaggie` flag + a count/score |
| `gold_launch_pad.py` | MA cluster tightness (Z-score spread) + bullish stacking + all-MAs-positive-slope + price near the cluster | `src/leaders/gold_launch_pad.py` — cited TradingView source, same pattern as your RTI/ATR ports |
| `guppy_screener.py` (GMMA) | Short-EMA-group (3/5/8/10/12/15) vs long-EMA-group (30/35/40/45/50/60) alignment, compression/expansion, crossovers | Could be a screener (`in_gmma_bullish` flag) *or* a categorical filter column (`gmma_state`: bullish/bearish/compressing/expanding) — leans toward **filter family** once computed, since it's more a state than a pass/fail candidate list |
| `ad_line/` (5-step ADL suite: `adl_calculator`, `adl_mom_analysis`, `adl_short_term`, `adl_ma_analysis`, `adl_composite_scoring`) | Accumulation/Distribution Line trend, month-over-month accumulation consistency, short-term momentum, MA alignment on the ADL itself, composite score | `src/leaders/accumulation.py` (or `src/focus/`) — genuinely new signal type (institutional accumulation), doesn't overlap anything you have. `adl_screener.py` (top-level, monolithic) looks like the pre-refactor version of the same thing — prefer the `ad_line/` package if porting |
| `value_momentum_screener.py` | 6-month returns + volatility + RS vs benchmark + price-based value proxies | New composite screener; "value proxy from price data" is a weaker concept than fundamentals-based value, worth treating as exploratory |
| `stockbee/stockbee_screener.py` | 4 sub-strategies: 9M-share movers, 20%-weekly movers, 4%-daily gainers, top-quintile industries + their top-4 stocks | The first 3 are legitimate new momentum/volume screeners; the industry-leadership piece overlaps with the separate Step-1 market/sector module mentioned in `intro.md` ("under development in another folder") rather than this Step-2 module — port the stock-level 3, leave industry-ranking to Step-1 |
| `volume_suite_components/` (`HVAbsoluteETC`, `HVStdv`, `enhanced_volume_anomaly`, `volume_indicators.py`: VROC/RVOL/ADTV/MFI/VPT) | Statistical volume-anomaly detection + individual volume indicators | The anomaly detectors (multi-step statistical logic → a flag) are screener-shaped; the individual indicators (RVOL, ADTV, VROC, MFI) are **filter-shaped** once computed — same pattern as ADR%/ADV today |

## Filter-shaped (compute once, expose as a threshold — no "leaders list" needed)

- **`adx_report.py`** — explicitly says in its own docstring: "Compute-only:
  no threshold filtering or rule evaluation... left to manual
  sorting/filtering until it's clear whether a full rule-based screener is
  worth building." That's the module's own author already applying this
  project's taxonomy — ADX/+DI/-DI/SMA18/SMA40 are filter columns, not a
  screener, until/unless a specific rule combination gets named.
- **`volume_indicators.py`** (RVOL, ADTV, VROC, MFI, VPT individually) —
  same shape as ADR%/ADV: one formula, one column, filterable directly.

## Out of scope for *this* module (Step-3 "buy rules", per `intro.md`)

`intro.md` explicitly scopes this project to Step 2 (Filters) only — Step
3 ("Buy rules: set up, entry") and Step 4 (sell rules) are "not subject of
current development." Two `metaData_v1` screeners are actual entry-timing
**signals**, not candidate-worthiness screens:

- **`drwish_screener.py`** — GLB (Green Line Breakout), Blue Dot, Black
  Dot: these are event-based buy signals (a specific day is or isn't a
  signal), not a standing "is this a leader" flag.
- **`pvb_screener.py`** — Buy/Sell/Close signal logic
  (`Close > prev_high AND Volume > prev_volume_high...`), also a
  day-specific entry/exit trigger, not a leader classification.

Porting either would mean quietly expanding this module's scope from
"filters/leaders" into "entries," which is the exact line `intro.md` drew.
If you want signal-timing tools eventually, they belong to the Step-3
module, not this one — worth flagging rather than silently absorbing them
here.

## Permanently excluded — user decision

- **`giusti_screener.py`** — rolling 12/6/3-month return ranking with
  progressive top-performer filtering. Would otherwise have been a
  reasonable candidate (same progressive cross-sectional-percentile shape
  as SCOOTER), but excluded for good per explicit user decision — not a
  "later round" item, don't reconsider it in future rounds of
  `more_screeners.md`.

## Skip

- **`quallamagie/quallamagie_screener.py`** — explicitly a placeholder
  ("Implementation pending research and planning phase"); the real
  implementation is the top-level `qullamaggie_suite.py` above.
- **`adl_screener (copy).py`** — byte-identical duplicate of
  `adl_screener.py` (same size, same content) — not a distinct candidate.
- **`basic_screeners_claude.py`**, **`momentum_screener.py`**,
  **`breakout_screener.py`** — simple single-purpose screeners
  (momentum/breakout/value-momentum) that look like earlier, less
  rigorous drafts of the same ideas covered better by
  `qullamaggie_suite.py` / Minervini / VCP. Worth a second look only if
  the more sophisticated candidates above don't pan out — `breakout_screener.py`
  specifically (consolidation + volume surge + resistance breakout) is the
  closest thing in this codebase to a **VCP-lite** and could be a faster
  starting point than building VCP's contraction-sequence detector from
  scratch (see `VCP_RESEARCH.md`).

## Suggested next step (when you're ready to build, not now)

If/when porting one of these, the pattern already established for
Minervini/CANSLIM/SCOOTER is the template to repeat: new module under
`src/leaders/` or `src/focus/`, thresholds + provenance comment in
`config.py`, a `validate.py` cross-check against the `metaData_v1` source
it was ported from (same way ATR/stage/SCTR are checked today), then wire
its output column into `dashboard_filters.py` (`FILTER_SPECS` and/or
`PRESETS`) so it becomes filterable/saveable like everything else.

# Taxonomy: filter vs. screener vs. preset vs. list

How this project (and the Corsellis/StockScreenHero reference it's modeled
on) organizes the four kinds of "things that narrow down the universe."
Use this as the decision tree when adding something new.

## Quick version (the knob analogy)

- **Filter** = a knob (one column, one comparator).
- **Screener** = code that creates a new knob from raw price/volume data.
- **Preset** = a saved position of several knobs.
- **List** = not a knob at all — just a fixed set of tickers.

Walked through with Minervini as the concrete example:

1. Raw data (daily price/volume for ~4,000 tickers) has no "knobs" yet —
   it's just numbers.
2. `src/leaders/minervini.py` is **Python code** that reads that raw data
   and computes something new per ticker (price vs 50/150/200-SMA, is the
   200-SMA rising, % within 52w high, RS ≥ 70, …) and combines all 8 checks
   into new columns: `in_minervini` (bool) and `minervini_count` (0–8).
   **This computation step is the screener** — it has to be code, because
   "is the 200-day average rising for a month" isn't sitting in the raw
   data; you have to calculate it.
3. Once those columns exist, they behave like any other column — you can
   put a **knob** on them in the dashboard: "Leaders lists = minervini" or
   "Minervini count ≥ 6". **That knob is a filter**, same category as
   "ADR% > 6%". The only thing that made Minervini special was the
   one-time work of *creating* the column; filtering on it afterwards is
   ordinary.
4. Save a specific combination of knob settings (`in_minervini = True` AND
   `max ATR ext ≤ 2.0` AND `ADV > $1M`) under a name via "Save Screener
   As…" → nothing gets (re)computed, you've just **remembered knob
   positions**. That's the **preset** (the Save button says "Screener" but
   in this taxonomy it's the preset — no new column, no new code).
5. Upload a CSV of 30 tickers you're personally tracking → no formula, no
   threshold, just "is this ticker in this fixed set of symbols." That's
   the **list**.

The test that decides the bucket: *did you have to write a formula against
price/volume history to produce a new column?* → **screener** (needs
Python). *Are you just picking values for columns that already exist?* →
**filter** (one column) or **preset** (several columns, saved). *Is it
just "is this ticker in this fixed set of symbols"?* → **list**.

## The four kinds

| Kind | Definition | Where it lives in this repo | Corsellis equivalent |
|---|---|---|---|
| **Filter** | One column, one comparator, evaluated per-ticker from data already computed. If it fits in a single dropdown/slider, it's a filter. | `dashboard_filters.SPEC_BY_KEY` / `THRESHOLD_FAMILIES` (14 sketch filters) + the "Advanced filters" expander in `dashboard.py` (stage, RTI zone, RS%, leaders flags, exchange, index…) | each of the ~19 dropdowns in the filter grid |
| **Screener** | A *named method* combining ≥2 raw filters/indicators into a new pass/fail flag or score, with its own citation/provenance. Needs a dedicated module, an entry in `config.py`, and ideally a `validate.py` check. Its output columns (a boolean flag, a score, a count) become new *filters* once computed. | `src/leaders/{minervini,canslim,scooter}.py`, `src/focus/{atr_extension,stages,rti}.py` | not surfaced as a separate UI concept in the reference — his "leaders lists" are just static Lists; this project's screener→filter feedback loop (`in_minervini`, `minervini_count`, `scooter_score` all filterable) is a deliberate improvement on that |
| **Preset** | A saved *snapshot of filter-panel values* — no new computation, just remembered settings under a name. Can bundle raw filters and/or screener-output flags (e.g. "leaders not extended" = `in_minervini/canslim/scooter` OR'd + `max_ext ≤ 2.0`). | built-in: `dashboard_filters.PRESETS`; user-saved: `my_screeners/*.json` via `save_screener()`/`load_screener()` | your sketch (`tab_all_results.png`): **"Ioa's presets"** (built-in) vs. "My Screener" (user's own) — the video itself labels these "Jack's Presets" vs. "My Screeners" |
| **List** | A static set of ticker symbols — no formula, doesn't recompute. Either uploaded, hand-curated, or a frozen export of a screener's result on a given date. | `my_lists/*.csv` via `save_list()`/`load_list()`; index membership (S&P 500, Russell…) parsed from the universe CSV is a "built-in list" equivalent | your sketch: **"Ioa's Lists"** (curated, shipped) vs. "My Lists" (user's own) — the video labels these "Jack's Lists"; this project has no shipped/curated list yet, only index membership |

## Decision rule

Ask, in order:

1. **Is it a single measurable/comparable column, derivable per-ticker from
   data you already compute, with one comparison operator?**
   → **Filter.** Add a row to `THRESHOLD_FAMILIES`/`FILTER_SPECS` in
   `dashboard_filters.py` (or an Advanced-filter widget in `dashboard.py`
   if it's boolean/categorical rather than threshold-shaped). No new
   module.

2. **Does it require combining ≥2 raw indicators into one new named
   pass/fail or score, backed by a specific methodology (Minervini,
   CANSLIM, SCOOTER, Weinstein stage, VCP, pocket pivot, …)?**
   → **Screener.** New module under `src/leaders/` (produces a Leaders'
   List, a "you're a candidate" flag) or `src/focus/` (produces a
   continuously-filterable metric, like ATR extension or RTI). Document
   thresholds + provenance in `config.py`, add a cross-check in
   `validate.py` against the reference implementation it was ported from.
   Its output column(s) should then be exposed as filter(s) — a screener
   always births at least one new filter.

3. **Is it just a combination of filter values (possibly including a
   screener's output flags) that you want to name and reload with one
   click, with no new math?**
   → **Preset.** Add to `dashboard_filters.PRESETS` if it's a durable
   "method template" worth shipping (e.g. a direct port of a known
   methodology's exact filter combo), or let the user create it via
   "Save Screener As…" in the dashboard if it's personal/exploratory.

4. **Is it a fixed set of symbols with no formula behind it** (a
   watchlist, "stocks I'm watching this week", a curated "recent IPOs"
   list, an index constituent list)?
   → **List.** `my_lists/*.csv` for user lists; for a shipped/curated list
   worth reusing across runs (the "Ioa's Lists" equivalent — per your
   sketch's naming — this project is currently missing), it should live in
   the repo — versioned, not uploaded through the UI — and be documented in
   `README.md` alongside the universe CSV.

## Worked examples (from the wider conversation)

- **"VCP (Volatility Contraction Pattern)"** → screener. Needs pattern
  logic over multiple contractions + volume, beyond the flat Minervini
  trend template already implemented; would live in `src/leaders/vcp.py`.
- **"Days to next earnings"** → filter. Single column, single threshold,
  no new methodology — just needs the data joined into
  `screener_results.csv`.
- **"Momentum Leader (Narrow)"** (Corsellis's own example: `Price vs
  50sma: above` + `Price vs 200sma: above` + `20d ADR% > 6%` + `50d ADV >
  50M`) → preset. Every one of those is already an existing filter; it's
  just four filter values bundled under a name.
- **"Recent IPOs"** → list. Static membership (age since IPO date), not a
  live per-ticker formula worth recomputing as a "screener" — though the
  *age itself* (days since IPO), if you wanted it filterable/sortable
  rather than just a fixed cutoff, would be a filter.

## Recycling screeners already built in `metaData_v1`

`/home/imagda/_invest2024/python/metaData_v1/src/screeners` has ~25 prior
screener implementations from earlier work. Most are viable screener
candidates by the rule above (they compute new columns from raw
price/volume that this project doesn't have yet); a few are better treated
as filters once computed, a couple are already the *reference* this
project validates against, and a couple raise a Step-2-vs-Step-3 scope
question. Full breakdown: `SCREENER_INVENTORY.md` in this folder.

## Tier model (feedback_4.md) — where a screener LIVES in the dashboard

Beyond the four kinds above, the dashboard organizes screeners into three
tiers. When adding something new, pick the tier with this decision rule:

| Tier | Question it answers | Tab | Computation | Examples |
|---|---|---|---|---|
| **Candidate screeners** | "is this a candidate to watch?" — durable classifications, no urgency clock | 🔎 All Results (Advanced filters + Ioa's Presets) | daily full-universe batch (`run_screeners.py`), columns in `screener_results.csv`, composed with the generic filter panel | Minervini, CANSLIM, SCOOTER, Stockbee ×3, Golden Launch Pad, Qullamaggie, ADL Accumulation |
| **Timing signals** | "should I act right now?" — a Buy/Sell state or a stop level is meaningless without "as of when" | 🕐 Timing Signals | on-demand, scoped (index + market cap), per-scope result files; state columns (`pvb_signal`, `atr1_trend`, dots) | PVB, ATR1 cloud, Dr. Wish Blue/Black Dot |
| **Patterns** | pattern-*geometry* detectors with genuinely unresolved/exploratory parameters that want user-adjustable presets | 🌊 Patterns | on-demand, scoped; per-pattern parameter presets (Strict/Default/Loose) | GLB, Cup & Handle |

A screener's tier is about the *question it answers and the maturity of
its parameters*, not its math. Candidate screeners must compose with the
generic filter panel (that composability is why they stay in All Results
even as the expander grows); timing signals and patterns deliberately do
not join that panel.

## Keeping this current

When adding something new, update this file's table only if a *new kind*
of storage location is introduced (e.g. a shipped curated-lists directory).
Day-to-day additions (a new filter column, a new screener module, a new
preset) don't need this file edited — just follow the decision rule above
and place the code/config in the location the matching row already names.

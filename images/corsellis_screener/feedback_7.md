# Feedback round 7 — 5 scans from more_screeners_3.md: implement these, exclude the rest

Scoped from `more_screeners_3.md` (a research draft — read it for the
full reasoning behind each item; this doc tells you what to build and
exactly where, don't re-derive the analysis). **Implement exactly 5
items below. Everything else in that draft — Scan #1 (High Volume,
intraday-blocked) and item 6 (metaVolume HVE/HVD) — is explicitly
excluded this round.** Don't pull them in "while you're at it."

## Architecture note — read before starting, this round is different from the last few

Everything here is a **same-day snapshot** computation, cheap over the
full ~4,000-ticker universe (no per-ticker state machine, no historical
pattern-scan, nothing like PVB/ATR1/GLB/Cup&Handle). **These belong in
the regular daily batch** — `run_screeners.py` → `screener_results.csv`
→ the existing "🔎 All Results" tab's filter panel — **not** the
on-demand scoped Timing Signals/Patterns tabs from `feedback_4.md`. That
on-demand architecture exists specifically because those 6 screeners were
too expensive to run for everyone every day; nothing in this round has
that problem, so don't route it through `on_demand.py`.

Two of the five are **filters** (single/derived column, no new module).
Three are **screeners** (combine ≥2 raw indicators into one named
pass/fail flag, per `TAXONOMY.md`'s decision rule — get their own
`src/leaders/` module). Which is which, below.

**Critical, learned the hard way (`feedback_2.md` §0)**: every new
Advanced-filter checkbox key you add **must** be registered in
`dashboard_filters.ADVANCED_DEFAULTS` from the start, using the exact
same key name everywhere. That's what makes preset-switching and
`_reset_filters()` clean up after these correctly. Skipping this is
exactly the bug that broke 7 of 8 presets in round 2 — don't repeat it.

---

## 1. RSI 40-50 — Filter

`indicators.rsi(close, period=14)` already exists in `src/indicators.py`
and is currently **unused anywhere in this codebase**. Wire it up:

- `run_screeners.py`: add `ctx['rsi14'] = indicators.rsi(close).iloc[-1]`
  alongside the other per-ticker metrics already computed there.
- `dashboard_filters.py`: new `FILTER_SPECS` row (`'rsi14', 'RSI 14',
  'rsi14', 'rsi'`) and a new `_rsi()` threshold family (0-100 range —
  offer something like `'< 30'`, `'30-40'`, `'40-50'`, `'50-60'`,
  `'> 70'`, plus the existing `'Custom…'` slider pattern every other
  family already has). This becomes a normal main-panel filter, not an
  Advanced-filter checkbox — same tier as the existing 14.
- `config.py`: `RSI_PERIOD = 14` (cites the standard Wilder RSI period —
  document it even though it's not a pass/fail threshold, matching this
  project's "cite provenance" convention).
- `validate.py`: `indicators.rsi()` has never been exercised by any
  check despite existing since round 1 — add one. Cross-check against a
  hand-written Wilder RSI calc on a sample ticker (same shape as the
  ATR14 cross-check already in the suite), and assert the output is
  bounded [0, 100].

## 2 & 3. 52-Week High Breakout + 52-Week Low Breakdown — Filters (build together)

Both are derived **event flags** from data already fully computed —
`indicators.rolling_high()`/`rolling_low()` (both already exist, both
default to `config.BARS_52W`) already back the existing continuous
`pct_from_52w_high`/`pct_from_52w_low` columns. What's missing is the
discrete "did this happen *today*" flag:

```python
in_52w_high_breakout = high.iloc[-1] > rolling_high(high, config.BARS_52W).shift(1).iloc[-1]
in_52w_low_breakdown  = low.iloc[-1]  < rolling_low(low,  config.BARS_52W).shift(1).iloc[-1]
```

- `run_screeners.py`: add both boolean columns, same place as the other
  per-ticker context values.
- `dashboard_filters.py`: two new Advanced-filter checkboxes —
  `adv_52w_high_breakout`, `adv_52w_low_breakdown` — same pattern as the
  existing `adv_rti_dots`/`adv_rti_exp` checkboxes. **Register both in
  `ADVANCED_DEFAULTS`** (see architecture note above).
- No new `src/leaders/` module — this is inline in `run_screeners.py`,
  reusing existing `indicators.py` functions directly. No `config.py`
  threshold needed (the 253-bar window is already `config.BARS_52W`,
  don't duplicate it under a new name).
- `validate.py`: an identity check is enough here (these are direct
  derivations of already-validated rolling-high/low logic) — confirm
  `in_52w_high_breakout` is `True` exactly when
  `pct_from_52w_high >= 0` on the day it flips, or similar consistency
  check against the existing continuous column, rather than a from-
  scratch manual mask.

## 4. 20-Day EMA Pullback Test — Screener

Per `more_screeners_3.md`'s decision to add a 5th condition (EMA20
rising) beyond the original 4-condition source syntax:

1. `SCTR > 75` (reuse existing `scooter_score` column, don't recompute)
2. `Open > EMA20`
3. `Low < EMA20`
4. `Close > EMA20`
5. `EMA20 > EMA20.shift(N)` (rising — **new condition, added per the
   draft's decision**, not in the original source syntax)

- New module: `src/leaders/ema20_pullback.py`. `indicators.ema(close,
  20)` already exists — this is the only genuinely new indicator; the
  other four conditions are direct column comparisons.
- `config.py`: `EMA20_SCTR_MIN = 75`, `EMA20_SLOPE_LOOKBACK` (5 or 10
  trading days — your call, document which and why in the comment; this
  is a deliberately lightweight point-to-point comparison, not an
  OLS-regression slope like Golden Launch Pad's — no need for that level
  of rigor here). Cite the EarningsBeats.com scan-language source in the
  module docstring.
- Output columns: `in_ema20_pullback` (boolean), and expose `ema20`
  itself as a byproduct column (useful as its own filter ingredient
  later, costs nothing extra to keep).
- `dashboard_filters.py`: new Advanced-filter checkbox
  `adv_ema20_pullback`, registered in `ADVANCED_DEFAULTS`.
- `validate.py`: behavioral check — module output vs. a hand-written
  manual mask on the 5 conditions, same rigor as every screener since
  round 1 (this is exactly the kind of check that's caught real bugs
  before — don't skip it because the logic looks simple).

## 5. Downtrend Reversal (Pullback Scan) — Screener

Today's High > yesterday's High, preceded by a strictly declining
sequence of daily Highs for the 6 days before that:

```python
declining = (high.shift(1) > high.shift(2)) & (high.shift(2) > high.shift(3)) & \
            (high.shift(3) > high.shift(4)) & (high.shift(4) > high.shift(5)) & \
            (high.shift(5) > high.shift(6))
in_downtrend_reversal = (high > high.shift(1)) & declining
```

(illustrative — write it however reads cleanest, e.g. a small loop
building the chain, but keep it a single vectorized pass across the
wide matrix, no per-ticker loop needed).

- New module: `src/leaders/downtrend_reversal.py`.
- `config.py`: `DOWNTREND_REVERSAL_LOOKBACK_DAYS = 6`, cited to the
  EarningsBeats.com source.
- Output: `in_downtrend_reversal` (boolean).
- `dashboard_filters.py`: new Advanced-filter checkbox
  `adv_downtrend_reversal`, registered in `ADVANCED_DEFAULTS`.
- `validate.py`: behavioral check, same as #4 — manual mask on the
  chained shift comparisons, cross-checked against the module's output.

---

## Explicitly not in this round

- **Scan #1 (High Volume, intraday pace)** — blocked on data
  availability (no intraday feed exists in this project), not a
  difficulty question. Don't build an end-of-day reinterpretation under
  the same name without asking first — see `more_screeners_3.md`'s
  reasoning.
- **metaVolume HVE/HVD** — future item, only worth revisiting if live
  composable columns are specifically wanted over the already-functional
  upload-a-list workflow. Not this round.
- **Presets** for any of these 5 — not required. If you want to bundle
  one into a named preset later (same pattern as `feedback_3.md`), ask
  first; keep this round to filters/screeners + their Advanced-filter
  wiring only.

## Definition of done (per item)

- [ ] Filters (#1, #2, #3): column(s) computed in `run_screeners.py`,
      wired into `dashboard_filters.py` (main panel for RSI, Advanced
      checkboxes for the 52-week flags, both registered in
      `ADVANCED_DEFAULTS`)
- [ ] Screeners (#4, #5): new module under `src/leaders/`, thresholds in
      `config.py` with source citations, output wired into Advanced
      filters + `ADVANCED_DEFAULTS`
- [ ] **Behavioral** `validate.py` check per item — manual-mask
      cross-check for the two screeners, identity/bounds check for the
      three filters — not shape-only
- [ ] `test_dashboard_app.py` extended if any of these interact with
      presets or the leak-regression check in a way worth covering
- [ ] Full `validate.py` + `test_dashboard_app.py` still green
- [ ] Confirm none of these 5 accidentally got routed through
      `on_demand.py`/a scoped tab — they belong in the daily full-
      universe batch, per the architecture note above

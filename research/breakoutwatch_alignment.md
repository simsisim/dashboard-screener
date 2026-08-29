# breakoutwatch.com alignment — gaps & TODOs

Source digest: `cup_handle_ideas/cupAndHandle/lit/breakoutwatch_methodology.md`
(reconstructed from Wayback captures, 2005–2023).

breakoutwatch = NBIcharts LLC, CANSLIM + O'Neil chart patterns since 2001. Their
design: **permissive geometric detector + rich per-day scoring (CQ) + an
outcome-trained ranker (2017 discriminant model)**, with a separate 18-point
CANSLIM scorecard (CE = CET 7 + CEF 11). Below: what to borrow, per module.

---

## `src/patterns/cup_handle.py` (K-A-B-C-D detector)

Ours is kanwalpreet18 geometry on close prices. breakoutwatch anchors differently.

**STATUS: Tasks A–H implemented 2026-08-29 (unsupervised; user review pending).
See IMPLEMENTATION_PLAN §16.12 for the as-built detail, config keys, and
verification. The checklist below is the original spec — every item A–H is
done; the only companion change not foreseen here was making
`_all_pattern_points` return every candidate so Strict/Default can pick the
freshest valid one (`candidate_selection='recent'`) instead of the earliest.
Task I (outcome-trained ranker) is unstarted — needs a logged-outcomes feed.**

- [x] **Setup Gain gate.** Require rise from a pre-cup low to the left rim
  `close[a]` ≥ 25–30% (breakoutwatch: ≥ 30%; O'Neil "prior uptrend ≥ 30%").
  Today `k` is just "the peak before `a`" with no magnitude test — this is the
  single highest-value false-positive cut.
- [ ] **Absolute pivot recency.** Add a "days since right rim `c` / pivot" cap
  (breakoutwatch: pivot within 90 days, cup ≤ 325 days). Surfaces *actionable*
  setups, not stale ones. Currently only relative `cup_max_duration`.
- [ ] **Explicit cup:handle length ratio ≥ 3.** Cheap: `(c - a) / max(d - c, 1) >= 3`.
  Currently only implicit via `handle_max_duration`.
- [ ] **Handle-midpoint ≥ base-midpoint** as a named alternative to
  `handle_position_min`. breakoutwatch rule:
  `(close[c] + close[d]) / 2 >= (close[a] + close[b]) / 2`. Our `strict` preset
  (`handle_position_min = 2/3`) is *stricter* than breakoutwatch's production rule.
- [ ] **HQ-style handle scoring** into `quality`. Iterate handle days `c..d`,
  score each on the price↕/volume↕ quadrant (price down + volume down = "very
  desirable" = max; price up + volume up = "unfavorable"), weight recent days
  heavier, normalize. Bonus: latest close up & vol ≥ avg → +1; & vol ≥ prior → +0.5.
- [ ] **RCQ-style right-side scoring** into `quality`. Score each day `b..c` on
  up-move-on-above-avg-volume (demand), recent days weighted heavier.
- [ ] **Volume-confirmed breakout flag.** breakoutwatch alert = price ≥ pivot
  **AND** volume ≥ 1.25–1.5× ADV. Today `stage='breakout'` fires on
  `close > resistance` alone. Add a `breakout_volume_confirmed` bool.
- [ ] **(optional) intraday high/low** for `a`, `c`, `d` instead of close — O'Neil
  purists and breakoutwatch use intraday extremes. Document as a known deviation
  if not changed.
- [ ] **(future) outcome-trained ranker.** If outcomes get logged: LDA/logistic on
  {momentum slope, momentum, prev-day price+volume rise, volume %of-50d-avg,
  earnings accel}. breakoutwatch's #1 predictor is **momentum slope**; RS rank is
  their **weakest** — don't over-weight RS in `quality`.
- Note: our `target = resistance + (close[a] - close[b])` already matches the
  O'Neil / breakoutwatch measured move. Keep.
- Note: our `loose` preset (cup 1–80%, handle pos 0) ≈ breakoutwatch's *actual
  production* setting (cup ≤ 60%, 2-day handle). Their lesson: don't over-tighten
  geometry; rank within a permissive set.

---

## `src/patterns/glb.py` (Green Line Breakout)

breakoutwatch has no "GLB" by name, but its **Pivot** primitive (highest high not
yet exceeded, confirmed by N bars of non-violation, breakout on volume) is the
same idea. `confirmation_bars` + `lookback_bars` ≈ their "pivot held / within
90 days".

- [ ] **Volume-confirmed breakout flag** (same as C&H): breakoutwatch always
  pairs the structural signal with vol ≥ 1.5× ADV. GLB breakout is price-only today.
- [ ] **Document the pairing.** `glb.evaluate` signal ∩ `canslim` C-A-I list =
  breakoutwatch's "pattern watchlist + CANTATA score" combo. Worth a helper in
  `src/combine.py` or the dashboard.
- Note: our GLB lineage is Dr. Eric Wish's `drwish_screener.py` (more direct than
  breakoutwatch); no change needed to the core algorithm.

---

## `src/leaders/canslim.py` (C-A-I only, from one yf snapshot)

| Letter | Ours | breakoutwatch (CEF) | Action |
|---|---|---|---|
| **C** | q1 vs q5 diluted EPS **YoY** ≥ 25%, base floor $0.05 | CEF1: 2 consecutive quarters' *rates* each ≥ 18% + CEF3 accel | Keep ours — more faithful to "How to Make Money in Stocks". |
| **A** | 3-yr diluted EPS CAGR ≥ 25%, NI fallback | CEF4: each of 4 FY ≥ 25% | Keep CAGR; add "each of last 3 FY positive & rising" flag. |
| **I** | `heldPercentInstitutions` ≥ 20% + shares-outstanding flat/shrinking | ≥ 5 holders **and QoQ net shares purchased ≥ 0** | Ours is a *buyback* proxy, not fund accumulation. If 13F / quarterly holder-count deltas become available, switch. Our own code comment already flags I as weakest — this is why. |

- [ ] **ROE ≥ 17% flag** (O'Neil's actual number; CEF9) — cheap from snapshot.
- [ ] **Sales growth ≥ 25% flag** (O'Neil modern "S"; CEF5) — cheap from snapshot.
- [ ] **Net margin = trailing-3-FY max flag** (margin expansion; CEF11).
- [ ] **Forward estimate ≥ current quarter flag** (CEF7) if forward EPS available.
- [ ] Emit CANSLIM output as **per-letter 0–N sub-scores + a total**, not a single
  bool — mirrors breakoutwatch's CE design and our own dashboard architecture.
  Each downstream strategy then picks its own thresholds.
- [ ] **CET checklist** — confirm these three exist somewhere in the pipeline:
  industry rank, distance from 52-week high, Up/Down volume ratio. (MA
  alignment / stages / RS blend already covered by 2nd-cat filters + `lkm_rs`.)

# The Cup & Handle model — how it is built and how it works

This document explains the cup-and-handle detector in this project from the
ground up: where it comes from, the exact algorithm, every parameter and
output column, how to run it, and its known limits.

- Code: `src/patterns/cup_handle.py` (detector), `src/patterns/cup_handle_chart.py` (chart)
- Parameters: `config.py` → `CUPHANDLE_PRESETS`, `CUPHANDLE_SETUP_LOOKBACK`
- UI: `dashboard.py` → Patterns tab
- Tests: `validate.py` (synthetic fixture + gate checks), `validate_ch_ref.py` (cross-check vs `patterns_v0`)
- Background reading: `../cup_handle_ideas/cupAndHandle/lit/` (breakoutwatch.com captures) and `research/breakoutwatch_alignment.md`

---

## 1. What a cup & handle is

A **cup & handle** is a bullish continuation base described by William
O'Neil (*How to Make Money in Stocks*). A stock that has already had a
meaningful advance pulls back into a rounded **cup**, recovers to near its
prior high, then drifts sideways/down in a small **handle** before breaking
out to new highs. The idea: the pullback shakes out weak holders, the
recovery shows institutions accumulating, and the handle is the last
shakeout before the move.

O'Neil's textbook shape:

```
        Left rim (A) ~~~~~~~~~~~~~~~~~~~~ Right rim (C)
       /                                  \        ___ handle
      /  prior advance                     \      /    \___ breakout →
 ____/   >= 30%                              \    /  (D)
 Prior                                        \__/
 low (K-ish)                              Cup bottom (B)
```

breakoutwatch.com (NBIcharts LLC, 2001–~2024) ran a commercial CANSLIM +
cup-and-handle service. Its published methodology — 4 stages, a criteria
table, the CQ / RCQ / HQ quality metrics, a 2017 discriminant "breakout
prediction" model — is the reference we align to. Digest:
`../cup_handle_ideas/cupAndHandle/lit/breakoutwatch_methodology.md`.

---

## 2. Lineage of this implementation

| Layer | Origin |
|---|---|
| **Geometric core** | `patterns_v0/src/cup_handle_detector.py` — the *kanwalpreet18* **K-A-B-C-D** method: find peaks/troughs with `scipy.signal.find_peaks`, then label 5 points and validate the shape. |
| **Ported here** (feedback_4.md Task 6, IMPLEMENTATION_PLAN §13.9) | `src/patterns/cup_handle.py` — same algorithm, vectorised entry point, three parameter **presets** instead of one config. |
| **breakoutwatch alignment** (IMPLEMENTATION_PLAN §16) | Added the domain pieces the raw geometry was missing: prior-uptrend gate, pivot-recency cap, cup:handle ratio, handle-midpoint rule, RCQ/HQ/CQ volume quality, volume-confirmed breakout, intraday extremes, multi-candidate selection. |

The **K-A-B-C-D** points:

| Point | Name | What it is |
|---|---|---|
| **K** | prior trend start | the peak *before* the left rim (used only to bound the "prior low" search region) |
| **A** | left rim | the peak where the cup starts (start of the decline) |
| **B** | cup bottom | the trough between the two rims |
| **C** | right rim / **pivot** | the peak where the cup ends and the handle starts (breakoutwatch calls this the *pivot*) |
| **D** | handle bottom | the first trough after C (or the last bar if the handle is still forming) |

---

## 3. The data it runs on

- **Wide daily OHLCV matrices** (`Date × ticker`) from
  `data_loader.load_price_matrices` — merged `archive` + `current` +
  `market_data_batch` daily bars (~1,668 bars ≈ 6.5 years).
- **On-demand only.** Unlike the leaders/focus screeners, cup & handle is
  **not** in the daily `run_screeners.py` batch. You pick a scope (an
  index, optional market-cap floor) in the Patterns tab and press Run; the
  result is cached per `(scope, preset)` for the day.
- Each output row carries its own `as_of` = that ticker's last valid bar.
- Minimum history: 20 bars (rows shorter than that get all-NaN columns).

---

## 4. The algorithm, step by step

Everything below is one call to `cup_handle.evaluate(tickers, data, presets)`,
which loops tickers × presets and calls `_evaluate_preset` → `_try_candidate`.

### 4.1 Find the extrema  (`_find_extrema`)

```
prominence = mean(close) * params['prominence_threshold']
peaks   = find_peaks( close, prominence=prominence, distance=params['distance_threshold'])
troughs = find_peaks(-close, prominence=prominence, distance=params['distance_threshold'])
```

`prominence_threshold` is a fraction of the average price, so it scales
across a $5 stock and a $500 stock. `distance_threshold` is the minimum bar
gap between two peaks (or two troughs). **Looser preset ⇒ smaller
prominence + smaller distance ⇒ many more, smaller swings detected.**

### 4.2 Build every candidate  (`_all_pattern_points`)

For **each trough** `t` that has at least one peak on both sides:

```
a = last peak before t          b = t          c = first peak after t
k = last peak before a          d = first trough after c   (or last bar)
```

This yields a list of constructible K-A-B-C-D dicts, earliest first. (The
original `patterns_v0` built only the first one — see §9.)

### 4.3 Pick which candidate to test  (`_evaluate_preset`)

- `candidate_selection == 'first'` (**loose**): test only the earliest
  constructible candidate — byte-identical to `patterns_v0`.
- `candidate_selection == 'recent'` (**strict / default**): sort candidates
  by right-rim index descending and return the **first that passes every
  gate** — so the recency cap (§4.6) surfaces a *current* cup rather than
  nulling out on an ancient one.

### 4.4 Structural sanity  (`_try_candidate`)

```
require  k < a < b < c <= d
require  close[b] < close[a]   and   close[b] < close[c]     (cup bottom below both rims, on close)
```

### 4.5 Measurement prices  (§16 Task H — "intraday extremes")

If `use_intraday_extremes` and the `high`/`low` matrices were supplied:

```
p_a = high[a]   p_c = high[c]        (rims = the day's high)
p_b = low[b]    p_d = low[d]         (bottoms = the day's low)
```

Otherwise all four fall back to `close`. "Intraday" here means *the daily
bar's* high/low (the extreme reached during that session) — **not**
sub-daily data, which the project does not have and does not need.
`require p_b < p_a and p_b < p_c` again on these prices.

### 4.6 The cup gates

| Check | Formula | Rejected when |
|---|---|---|
| **Cup depth** | `cup_depth = (p_a - p_b) / p_a` | outside `[cup_min_depth_pct, cup_max_depth_pct]` |
| **Cup duration** | `c - a` bars | outside `[cup_min_duration, cup_max_duration]` |
| **Rim symmetry** | `rim_sym = |p_a - p_c| / p_a` | `> cup_depth_tolerance` |
| **Setup gain** (§16 A) | prior low = min of `(low or close)[a-252 : a]`; `setup_gain = (p_a - prior_low) / prior_low` | `setup_gain_min > 0` **and** (`setup_gain` is NaN or `< setup_gain_min`) |
| **Pivot recency** (§16 B) | `days_since_rim = n - 1 - c` | `> pivot_max_age` |
| **Cup:handle ratio** (§16 C) | `ratio = (c - a) / max(d - c, 1)` | `< cup_handle_ratio_min` |
| **U-shape** | inner peaks of `close[a : c+1]` | more than one inner peak **and** the highest inner peak sits above the cup's half-height (`> close[b] + 0.5·(close[a]-close[b])`) → that's a double-bottom / V, not a cup |

`CUPHANDLE_SETUP_LOOKBACK = 252` (1 year) caps the prior-low search so a
low from years ago on a long uptrend isn't used. The "base" begins at the
left rim `A`; the setup gain is the advance *into* that base.

### 4.7 The handle gates

```
cup_height      = p_a - p_b
handle_depth    = (p_c - p_d) / cup_height          # as a fraction of the cup
handle_duration = d - c
handle_position = max(0, (p_d - p_b) / cup_height)  # how high the handle low sits in the cup
```

| Check | Rejected when |
|---|---|
| Handle rides high enough | `handle_position < handle_position_min` |
| Handle shallow enough | `handle_depth > handle_max_depth_pct` |
| Handle duration | outside `[handle_min_duration, handle_max_duration]` |
| **Midpoint rule** (§16 D) | `handle_midpoint_rule` is on **and** `(p_c + p_d)/2 < (p_a + p_b)/2` (handle midpoint below base midpoint) |

### 4.8 Volume behaviour

```
vol_ma          = rolling mean of volume over volume_ma_period (20) days
cup_vol         = mean volume from A to C
vol_ma_during   = mean of vol_ma over A..C
decline_confirmed = cup_vol < vol_ma_during * volume_decline_threshold   # dry-up in the cup
breakout_ratio    = mean(volume[-5:]) / vol_ma_during        # only if the pattern has completed (n-1 > d)
```

**RCQ — Right Cup Quality** (`_rcq_score`, days B→C): for each day, +1 if
it closed **up on above-average volume** (demand), −1 if **down on
above-average volume** (distribution), 0 otherwise; then a recency-weighted
mean (the most recent day of the window weighs `m×` the first). Range
≈ [−1, +1]; higher = institutions accumulating up the right side.

**HQ — Handle Quality** (`_hq_score`, days C→D): each day scored on the
breakoutwatch 2×2 —

| | volume ↓ | volume ↑ |
|---|---|---|
| **price ↓** | **+1.0** very desirable | −1.0 very unfavourable |
| **price ↑** | +0.5 desirable | −0.5 unfavourable |

recency-weighted mean, **plus** a breakout-foreshadow bonus: if the latest
close is up, `+0.5` when the latest volume ≥ its MA, else `+0.25` when it
≥ the prior day. Range ≈ [−1, +1.5].

**CQ — Chart Quality** (`cup_handle_cq`): the breakoutwatch blend of the
two, weight shifting toward HQ as the handle lengthens —

```
w_hq = 0.40 + 0.30 * min(handle_duration / 20, 1)
cq   = (1 - w_hq) * rcq  +  w_hq * hq
```

CQ is **report-only**: it is *not* a gate and *not* in the quality score.
It is meaningful only where a pattern was found (NaN otherwise), because
RCQ/HQ are scored over the pattern's own B→C and C→D segments.

### 4.9 Quality score (0–100)

The `patterns_v0` heuristic (verbatim) plus two §16 terms:

| Term | Contribution |
|---|---|
| Cup depth near the 22.5% ideal | `max(0, 15 − |cup_depth − 0.225|·100)` |
| Rim symmetry | `max(0, 15 − rim_sym·500)` |
| Cup duration near mid-range | `max(0, 10·(1 − |dur_ratio − 0.5|·2))`, `dur_ratio = cup_duration / cup_max_duration` |
| Handle position | `handle_position · 15` |
| Handle shallowness | `max(0, 15 − handle_depth·60)` |
| Volume dried up in the cup | `+20` if `decline_confirmed` |
| Volume surge on breakout | `+10` if `breakout_ratio > breakout_volume_factor` |
| RCQ (§16 F) | `+ max(0, rcq) · 10` |
| HQ (§16 E) | `+ max(0, hq) · 10` |

Clipped to `[0, 100]`.

### 4.10 Stage, target, stop

```
resistance = max(p_a, p_c)

stage = 'forming'   if the handle low D is the last bar (n-1 <= d)
      = 'breakout'  if close[-1] > resistance
      = 'complete'  otherwise (pattern done, price back below the rim)

target = resistance + (p_a - p_b)          # O'Neil / breakoutwatch measured move: add the full cup depth
stop   = min(p_d, p_b) * 0.95              # 5% below the lower of the handle low and the cup bottom

breakout_vol_confirmed = stage == 'breakout'
                         and volume[-1] >= vol_ma[-1] * breakout_volume_factor   # §16 Task G
```

---

## 5. The three presets

`config.CUPHANDLE_PRESETS` — every ticker is evaluated under each requested
preset and gets its own suffixed column set. **Do not treat `loose` as the
default** — it is deliberately permissive.

| Parameter | `strict` (O'Neil textbook) | `default` (working list) | `loose` (= patterns_v0 daily) |
|---|---|---|---|
| `prominence_threshold` | 0.05 | 0.025 | 0.005 |
| `distance_threshold` | 5 | 3 | 1 |
| `cup_min_duration` / `cup_max_duration` | 20 / 60 | 10 / 80 | 3 / 120 |
| `cup_min_depth_pct` / `cup_max_depth_pct` | 0.12 / 0.33 | 0.08 / 0.45 | 0.01 / 0.80 |
| `cup_depth_tolerance` (rim symmetry) | 0.05 | 0.12 | 0.25 |
| `handle_min_duration` / `handle_max_duration` | 5 / 30 | 3 / 40 | 1 / 30 |
| `handle_max_depth_pct` | 0.30 | 0.50 | 1.00 |
| `handle_position_min` | 0.667 | 0.5 | 0.0 |
| `volume_decline_threshold` | 0.8 | 0.8 | 0.8 |
| `breakout_volume_factor` | 1.5 | 1.5 | 1.5 |
| `volume_ma_period` | 20 | 20 | 20 |
| `setup_gain_min` (§16 A) | **0.30** | 0.20 | **0.0** (off) |
| `pivot_max_age` (§16 B) | **90** | 150 | **1e9** (off) |
| `cup_handle_ratio_min` (§16 C) | **3.0** | 2.0 | **0.0** (off) |
| `handle_midpoint_rule` (§16 D) | **on** | on | **off** |
| `use_intraday_extremes` (§16 H) | on | on | **off** (close only) |
| `candidate_selection` | `recent` | `recent` | `first` |

**Design guarantee:** every §16 gate is non-binding for `loose`
(`setup_gain_min` 0, `pivot_max_age` ~∞, `ratio_min` 0, midpoint off,
intraday off, candidate `first`). So `loose` output is byte-identical to
`patterns_v0`'s own detector — verified in `validate.py`.

Rough behaviour on the S&P 500 (2026-08-29): `strict` ≈ 1 hit,
`default` ≈ 37 (recent cups, days-since-rim 4–18), `loose` ≈ 226 (many
stale — days-since-rim into the hundreds, since `loose` has no recency cap).

---

## 6. Output columns  (per preset, suffix `_{preset}`)

| Column | Meaning |
|---|---|
| `in_cup_handle` | a pattern was detected and passed every gate |
| `cup_handle_stage` | `forming` / `breakout` / `complete` |
| `cup_handle_quality_score` | 0–100 heuristic (§4.9) |
| `cup_depth_pct` | `(rim − bottom) / rim`, % |
| `handle_depth_pct` | handle drop as % of the **cup height** |
| `cup_handle_target_price` | measured-move target = `resistance + cup height` |
| `cup_handle_stop_loss` | `min(handle low, cup bottom) × 0.95` |
| `cup_handle_setup_gain_pct` | prior advance into the left rim, % (reported even when it isn't gating) |
| `cup_handle_days_since_rim` | bars from the right rim (pivot) to today |
| `cup_handle_ratio` | cup length ÷ handle length |
| `cup_handle_rcq` | Right Cup Quality ≈ [−1, +1] |
| `cup_handle_hq` | Handle Quality ≈ [−1, +1.5] |
| `cup_handle_cq` | Chart Quality = RCQ/HQ blend (report-only) |
| `cup_handle_breakout_vol_confirmed` | breakout stage **and** today's volume ≥ 1.5× its MA |
| `as_of` (shared) | that ticker's last valid bar date |

---

## 7. How to run it

### Dashboard (the normal way)

```
streamlit run dashboard.py
```

Patterns tab → **Cup & Handle** → pick a preset (`strict` / `default` /
`loose`) → pick a scope (e.g. S&P 500, optional market-cap floor) → **▶ Run**.
The table shows the detected breakouts with all the columns above; the
result is cached for the day per `(scope, preset)`.

Under the table, the **Annotated chart** selectbox draws the full
breakoutwatch-style diagram for any detected ticker (see §8).

### Programmatic

```python
import pandas as pd
from src import data_loader, on_demand
from src.patterns import cup_handle

res  = pd.read_csv('results/<date>/screener_results.csv', index_col='ticker')
tk   = on_demand.resolve_scope(['S&P 500'], 0, res['market_cap'])
data = data_loader.load_price_matrices(tk, use_batch=True, verbose=False)
df   = cup_handle.evaluate(tk, data, presets=['strict', 'default', 'loose'])
df[df['in_cup_handle_default']]
```

### Standalone chart PNGs

```
python3 ../cup_handle_ideas/cupAndHandle/draw_cup_handle.py ETN EXPD GD BOE --preset default
```

Thin CLI wrapper over `src/patterns/cup_handle_chart.py::figure()` — the
same code the dashboard uses.

---

## 8. The annotated chart  (`cup_handle_chart.py`)

`figure(ticker, preset, data)` re-runs the detector's own candidate
selection, so the picture always shows exactly the pattern the model
selected (or `None` if there is none). Elements, matching
`../cup_handle_ideas/cupAndHandle/lit/candhanfdle_image.png`:

- **4 stage bands** — Setup (grey, prior low → A), Decline (pink, A → B),
  Recovery (cyan, B → C), Consolidation (blue, C → today).
- **Red dots** — Prior Low, Left Cup (A), Base Low (B), Pivot (C),
  Handle Low (D), Current Close.
- **Cup / Handle span arrows** (A→C, C→D) below the stage labels.
- **Today** marker + a grey "N bars since pivot" note when the breakout is
  stale (`days_since_rim > 40`).
- **Reference lines** at the right margin — Left Cup, Base Low, Target
  (`+X%`), Stop.
- **Metrics box** — Setup Gain, Cup Depth, Handle Depth, Pivot-off-Left-Cup,
  Days since rim, Cup:Handle length, `RCQ / HQ / CQ`, `Quality /100`,
  and `vol-confirmed` when applicable.
- **Volume panel** — up/down bars + a 15-bar envelope, stage bands repeated.

The view is zoomed to the pattern (`~0.55 × cup-width` of runway before the
left rim → today); the prior low is often outside the window, so it is
reported as text ("N bars back").

---

## 9. Known limitations & deviations

| From | Deviation |
|---|---|
| textbook O'Neil | pattern points are chosen from **close-price** peaks/troughs (`find_peaks`), then optionally *measured* off intraday high/low; a true tick-level pivot isn't used. |
| `patterns_v0` | it built and tested only the **first constructible** K-A-B-C-D. `loose` keeps that; `strict`/`default` scan every candidate and take the freshest valid one (`candidate_selection='recent'`), otherwise the §16 recency cap would just null them out on multi-year histories. |
| breakoutwatch | their geometric gate is actually **looser** than our `strict` (cup ≤ 60%, 2-day handle, RS ≥ 80). Our value-add over them is the same *scoring* discipline; their **Expected Gain** and **2017 discriminant "breakout prediction" model** are **not** implemented — that is Task I below. |
| — | `pattern_formation_cutoff_date` (a `patterns_v0` display filter) is not ported; all patterns are reported with their stage instead of dropped. |

The quality score is **hand-weighted**, not fitted to outcomes. Treat it as
a sorting aid, not a probability.

---

## 10. Testing

- `validate.py`:
  - **C&H synthetic** — a by-construction cup & handle (seg0 rises 72→100 so
    it clears strict's 30% setup gain; cup 20.15% deep). All three presets
    must detect it; `strict` must reach `breakout` stage.
  - **§16 gates** — each added gate (`setup_gain_min`, `pivot_max_age`,
    `cup_handle_ratio_min`, `handle_midpoint_rule`) must reject when its own
    threshold is made impossible, and `loose` must still fire (gates
    non-binding). `cup_handle_cq` must sit between `rcq` and `hq`.
  - **vs `patterns_v0`** (`validate_ch_ref.py`, isolated subprocess) — our
    `loose` output must match `patterns_v0`'s own detector on the synthetic
    (depth 20.15, stage breakout).
- `test_dashboard_app.py` — Patterns tab boots, C&H runs per preset with
  distinct cache keys, and the annotated-chart selectbox renders a Figure.

Current status: `validate.py` 37/37, `test_dashboard_app.py` 31/31.

---

## 11. Roadmap

- **Task I — outcome-trained ranker** (IMPLEMENTATION_PLAN §16.9). Blocked:
  needs a logged feed of "did this breakout work?" outcomes. breakoutwatch's
  own model found *momentum slope* the strongest predictor and *RS rank* the
  weakest — so if/when there is data, an LDA/logistic on
  {momentum slope, momentum, prev-day price+volume rise, volume %-of-50d,
  earnings acceleration} would replace the hand-weighted quality score.
- Threshold calibration is still open for review (setup-gain 30/20,
  pivot-max-age 90/150, ratio 3/2, HQ/RCQ weight in the score) —
  IMPLEMENTATION_PLAN §16.12.

---

## 12. File map

```
src/patterns/cup_handle.py         detector: _find_extrema, _all_pattern_points,
                                   _evaluate_preset, _try_candidate, _rcq_score,
                                   _hq_score, evaluate()
src/patterns/cup_handle_chart.py   figure(ticker, preset, data) -> matplotlib Figure
config.py                          CUPHANDLE_PRESETS, CUPHANDLE_SETUP_LOOKBACK
dashboard.py                       Patterns tab (radio, preset, scope, Run, table,
                                   annotated-chart selectbox)
src/on_demand.py                   scope resolution + per-day (scope,preset) cache
validate.py                        synthetic fixture + §16 gate checks
validate_ch_ref.py                 cross-check vs patterns_v0 (subprocess)
../cup_handle_ideas/cupAndHandle/
    draw_cup_handle.py             CLI wrapper over cup_handle_chart.figure()
    lit/                           breakoutwatch.com Wayback captures + digests
research/breakoutwatch_alignment.md   the §16 gap analysis / task list
research/breakoutwatch_methodology.md not here — see lit/ digest
IMPLEMENTATION_PLAN.md §13.9, §16, §18   build history
```

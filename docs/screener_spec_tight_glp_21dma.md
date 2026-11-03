# Implementation spec: Tight Consolidation, Tight and Orderly, Golden Launch Pad, 21dma-structure Pullback

You are implementing four stock screeners. This spec is self-contained:
every formula, parameter and edge case is below. Each one is a port of the
reference Python implementation in the `dashboard-screener` project (paths
given for traceability only; you don't need access to them).

---

## 0. Conventions (apply to all four)

**Input data.** Daily OHLCV bars per ticker, oldest → newest, split-adjusted.
The reference implementation works on "wide" matrices: one DataFrame per
field (`open`, `high`, `low`, `close`, `volume`), index = date, columns =
ticker. Every indicator is computed column-wise (vectorized), and the
screener reads only the **latest bar** (`.iloc[-1]`). Per-ticker loops
produce the same results if that suits your codebase better.

**Data gaps matter.** If a trading day is missing for a ticker, every
rolling window that spans it becomes NaN in a strict implementation (or is
silently wrong in a lenient one). Check for missing NYSE sessions before
screening. The reference warns when more than 20% of live tickers lack a
bar on any of the last 60 sessions.

**Shared indicators** (the exact definitions matter: results must match):

| Name | Definition |
|---|---|
| `SMA(x, n)` | `x.rolling(n, min_periods=n).mean()` — NaN until n bars exist |
| `EMA(x, n)` | `x.ewm(span=n, adjust=False).mean()`, so alpha = 2/(n+1), seeded with the first value. Not SMA-seeded. |
| `ATR14` | Wilder ATR: `TR = max(H−L, |H−C_prev|, |L−C_prev|)` (first bar: `H−L`); `ATR = TR.ewm(alpha=1/14, adjust=False, min_periods=14).mean()` |
| `ADR20%` | `SMA(H−L, 20) / close × 100` |
| `ADV50$` | `SMA(close × volume, 50)` (50-day average dollar volume) |
| `pct_vs_SMA(n)` | `(close / SMA(close, n) − 1) × 100` |
| `ext_21ema_atr` | `(close − EMA(close, 21)) / ATR14` |
| `ext_50sma_atr` | `(close − SMA(close, 50)) / ATR14` |
| `linreg_slope(x, n)` | OLS slope of the last n values against x = 0..n−1, in price units per bar (same as `scipy.stats.linregress(range(n), y).slope`) |
| `slope_pct(x, w)` | `(x / x.shift(w) − 1) × 100` |

### Weinstein stage (needed by "Tight and Orderly")

Computed on the latest bar from `SMA50`, `SMA150`, `SMA200` and
`s200 = slope_pct(SMA200, 20)`:

```
above200 = close > SMA200     above150 = close > SMA150    above50 = close > SMA50
golden_x = SMA50 > SMA200     s150_gt_200 = SMA150 > SMA200
rising   = s200 > 0.05        flat = |s200| <= 0.05        LATE = 0.15

stage = '1'                                                   # default: basing
# assign IN THIS ORDER (later lines overwrite earlier ones)
if above200 & golden_x & rising & above150 & s150_gt_200
   & not (s200 < LATE & not above50):                stage = '2B'
if above200 & golden_x & rising & not (above150 & s150_gt_200): stage = '2A'
if above200 & golden_x & rising & above150 & s150_gt_200
   & s200 < LATE & not above50:                      stage = '2C'
if above200 & golden_x & flat:                       stage = '2C'
if above200 & not golden_x:                          stage = '3'
if not above200 & SMA50 > SMA200*0.98 & rising:      stage = '3'
if not above200 & not golden_x & s200 < 0:           stage = '4'
if not above200 & not golden_x & flat:               stage = '4'
```

---

## 1. Tight Consolidation (RTI)

**Idea:** flag stocks whose daily range is small, i.e. low-volatility
consolidations that often precede breakouts. Based on the "Range Tightening
Indicator" (TradingView, Ollie_AllCaps). Reference: `src/focus/rti.py`.

### Formula

```
typical = (H + L + C) / 3
RTI(N)  = SMA(H − L, N) / typical × 100        # N = 5, 15, 50
```

Output columns (latest bar):

| Column | Value |
|---|---|
| `rti_short` | RTI(5), rounded to 2 dp |
| `rti_swing` | RTI(15) |
| `rti` | RTI(50), the main value |
| `rti_zone` | from RTI(50): `'1'` if < 5 (extremely tight), `'2'` if < 10 (low), `'3'` if < 15 (moderate), else `'—'` |
| `rti_dots` | RTI(50) < 20 on today AND yesterday (≥ 2 consecutive bars) |
| `rti_low_vol_streak` | length of the current run of consecutive bars with RTI(50) < 20 (0 if today isn't one) |
| `rti_expansion` | `RTI(5)_today >= 2 × min50` AND `min50 <= 20`, where `min50` = rolling 50-bar min of RTI(5) |

Note: the SMA is taken over the raw `H−L` in price units, then divided by
the *same bar's* typical price. Don't average `(H−L)/typical` per bar,
because that gives slightly different numbers.

### Screener rule

```
Tight Consolidation = rti_zone in {'1', '2'}  AND  ADV50$ > $1M
```

### Parameters

```
RTI_PERIODS = {short: 5, swing: 15, long: 50}
RTI_ZONE1 = 5, RTI_ZONE2 = 10, RTI_ZONE3 = 15
RTI_LOW_VOL = 20, RTI_DOTS_CONSECUTIVE = 2, RTI_EXPANSION_MULT = 2
```

### ⚠ Known weakness: read before relying on it

RTI(50) measures a **volatility level**, not tightening *relative to the
stock's own history*. It correlates about 0.87 with ADR%. On the
2026-10-05 run, **3,788 of 3,961 tickers** were in zone 1–2. A slow
utility passes as "tight" without ever having contracted. Implement it as
specified for parity, but don't expect it to be selective on its own. A
range-relative replacement is planned (see §5).

---

## 2. Golden Launch Pad (GLP)

**Idea:** the 10/20/50 EMAs are bunched together, stacked bullishly and
all rising, with price sitting just above them: a coiled uptrend about to
launch. Reference: `src/leaders/gold_launch_pad.py` (port of a removed
TradingView script, "Golden Launch Pad").

Input: **close only**. All five conditions must be true on the latest bar.

### Conditions

```
E10, E20, E50 = EMA(close, 10), EMA(close, 20), EMA(close, 50)
```

1. **Tightly grouped (z-score spread).** Z-score each EMA against its
   own trailing window of **51 bars, inclusive of today** (zscore_window 50 + 1):
   ```
   z_p = (E_p − rolling_mean(E_p, 51)) / rolling_std(E_p, 51, ddof=0)
         # std == 0 → NaN (→ fails)
   glp_spread = max(z10, z20, z50) − min(z10, z20, z50)   # NaN-skipping max/min
   pass if glp_spread <= 1.0
   ```
   Use **ddof=0** (population std) here. This is deliberate: it matches the
   source's `np.nanstd`.

2. **Bullishly stacked:** `E10 > E20 > E50`.

3. **Positive slopes:** for each period p in (10, 20, 50):
   `lookback = max(1, int(p × 0.3))`, then
   `linreg_slope(E_p, lookback + 1) > 0.0001`. That gives windows of
   4 / 7 / 16 bars. All three must pass.

4. **Price above the fastest EMA:** `close > E10`.

5. **Near the cluster:**
   ```
   cluster_avg = mean(E10, E20, E50)          # latest bar
   |close − cluster_avg| <= 2.0 × rolling_std(close, 20)   # ddof=1 (pandas default)
   ```
   Use **ddof=1** here, unlike condition 1.

### Outputs

| Column | Value |
|---|---|
| `glp_spread` | raw z-spread (4 dp) |
| `glp_spread_score` | `clip(1 − spread / 1.0, 0, 1)` (3 dp) |
| `glp_strong` | `spread_score >= 0.7` |
| `in_gold_launch_pad` | all 5 conditions true (NaN → False) |

### Parameters

```
GLP_MA_PERIODS = (10, 20, 50)    GLP_ZSCORE_WINDOW = 50 (window = 51 incl. today)
GLP_MAX_SPREAD = 1.0             GLP_SLOPE_LOOKBACK_PCT = 0.3
GLP_MIN_SLOPE = 0.0001           GLP_PROXIMITY_STDEV = 2.0
GLP_PROXIMITY_WINDOW = 20        GLP_STRONG_SCORE = 0.7
```

The original script's wrapper also applied price ≥ $5 and 20-day average
volume ≥ 100K. The reference drops these and relies on the project's own
liquidity filter (ADV50$ > $1M) instead. Add them only if your system has
no liquidity gate.

---

## 3. Tight and Orderly (Trading Voyage / Ollie)

**Idea:** Oliver Wiedmaier's (Voyage Trading Group) weekend funnel: a
liquid stage-2 uptrend, quiet range (RTI), and EMAs coiled (GLP). It's a
composite of §1 + §2 + trend/liquidity filters. It exists in two forms;
implement both.

### 3a. Single preset "TW: Tight and orderly"

All conditions AND-ed:

```
3 <= close <= 1000        # ⚠ upper bound excludes >$1,000 stocks; Ollie's rule is only > $3 — consider dropping it
ADR20% > 3
ADV50$ > $1M              # proxy for Ollie's "avg volume >= 500k shares"
pct_vs_SMA(50)  > 0       # close above 50 SMA
pct_vs_SMA(200) > 0       # close above 200 SMA
stage in {'2A', '2B'}
rti_zone in {'1', '2'}
in_gold_launch_pad == True
```

Variant **"TW: not extended"** = the above plus Ollie's
"Jack-in-the-Box" ATR gate:

```
ext_21ema_atr <= 3.0   AND   ext_50sma_atr <= 5.0      # NaN → treated as fail (fill 99)
```

### 3b. Multi-stage workflow "Trading Voyage (Ollie)"

Each stage filters the **output of the previous stage**:

| # | Stage | Input | Rule |
|---|---|---|---|
| 1 | Universe | all tickers | `3 <= close <= 1000`, `ADR20% > 3`, `ADV50$ > $1M`, `pct_vs_SMA50 > 0`, `pct_vs_SMA200 > 0`, `stage in {2A, 2B}` |
| 2 | Momentum leaders | stage 1 | **OR** (union) of: close ≥ 30% above its 21-day low, OR ≥ 50% above its 63-day low, OR ≥ 100% above its 126-day low |
| 3 | Tight & orderly | stage 2 | `rti_zone in {1, 2}` AND `in_gold_launch_pad` |
| 4 | Focus (not extended) | stage 3 | `ext_21ema_atr <= 3` AND `ext_50sma_atr <= 5` → final Focus List |

"X% above its N-day low" = `(close / min(low over last N bars) − 1) × 100`.
The reference has `above21low` / `above63low` / `above126low` columns.
Check whether your window should include today. The reference uses the
trailing N bars including today.

Manual checks (not automated, for the human trader): skip names whose range
today is smaller than yesterday's (still compressing). The entry trigger is
range expansion with above-average volume and a close in the top 30% of
the day.

---

## 4. 21dma-structure Pullback (PrimeTrading)

**Idea:** a band made of three 21-EMAs (of high, close, low). Flag stocks
in an uptrend whose close is back near the band, i.e. a pullback to
structure. This is a "look at the chart" flag, not an entry signal.
Reference: `src/focus/ma_structure.py`, a port of the TradingView script
"ADJUSTABLE MA STRUCTURE" v7.3 (BalarezoCapital, modified by PrimeTrading),
daily defaults.

### Formula

```
MAHigh  = EMA(high, 21)
MAClose = EMA(close, 21)
MALow   = EMA(low, 21)
```

**Trend (with memory, computed over the full history):**

```
rising  = MAHigh > MAHigh[1] AND MAClose > MAClose[1] AND MALow > MALow[1]
falling = MAHigh < MAHigh[1] AND MAClose < MAClose[1] AND MALow < MALow[1]
state_t = +1 if rising, −1 if falling, else state_{t−1}   # mixed bars keep the previous state
initial state (before any rising/falling bar) = +1 (up)
```

(Vectorized: map rising→1, falling→−1, else NaN; forward-fill; fill
remaining NaN with 1; take the last value.)

**Distance of close from the band** (latest bar, %):

```
if close > MAHigh:  dist = (close / MAHigh − 1) × 100      # positive
elif close < MALow: dist = (close / MALow − 1) × 100       # negative
else:               dist = 0                                # inside the band
round to 2 dp
```

**Validity:** NaN outputs (and `in_21dma_pullback = False`) unless the
ticker has ≥ 21 non-NaN closes and close/MAHigh/MALow are all present.

### Outputs

| Column | Value |
|---|---|
| `ma21s_high`, `ma21s_close`, `ma21s_low` | the three EMAs (4 dp) |
| `ma21s_trend` | `'up'` / `'down'` |
| `ma21s_dist_pct` | dist as above |
| `ma21s_zone` | `extended` (dist > +2), `above` (0 < dist ≤ +2), `inside` (dist = 0), `undercut` (−2 ≤ dist < 0), `below` (dist < −2) |
| `ma21s_bearish_bar` | `high < MALow` on the latest bar (the whole bar is under the band). Informational only, not excluded. |
| `in_21dma_pullback` | `ma21s_trend == 'up'` AND `|dist| <= 2.0` |

### Parameters

```
MA21S_LENGTH = 21            # EMA
MA21S_PULLBACK_PCT = 2.0     # ±2% window around the band (inside = 0)
```

Possible follow-up (not done): on volatile names a fixed ±2% may be noisy.
An ATR-based window (e.g. ±0.5 ATR) is an option.

---

## 5. Planned replacement for RTI: "Tight base" (optional, not yet in the reference)

If you want a *real* tightness filter, this is the agreed design. It is
price only (no volume), applied **only to leaders** (e.g. Minervini /
CANSLIM / SCOOTER outputs), never to the whole universe. Each measure
compares the stock with itself:

| Column | Formula | Starting threshold |
|---|---|---|
| range contraction | `ADR(10) / ADR(50)` (raw `SMA(H−L)` ratios) | < 0.7 |
| box width | `(max(high, 20) − min(low, 20)) / close` | < ~12% |
| flat box | `|close / close[20] − 1| / box width` | < 1/3 |

Tune the thresholds on the ~500 leaders, not on the universe, and
consider a combined tightness score to sort the tightest first.

---

## 6. Reference values for validation (run of 2026-10-05)

Same data → your output should match to rounding.

| ticker | close | rti | zone | glp_spread | GLP | stage | ma21s_high | ma21s_low | trend | dist% | zone | 21pb | ext21 | ext50 | ADR% |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| NVDA | 233.95 | 2.37 | 1 | 0.1703 | True | 2B | 227.5813 | 222.8396 | up | 2.80 | extended | False | 1.57 | 2.65 | 1.91 |
| MSFT | 517.53 | 2.06 | 1 | 0.4706 | False | 2A | 508.0677 | 497.3239 | up | 1.86 | above | True | 1.27 | 2.57 | 1.99 |
| AAPL | 333.69 | 2.05 | 1 | 0.7465 | False | 2B | 334.3269 | 327.7105 | up | 0.00 | inside | True | 0.38 | 1.61 | 2.06 |
| KO | 85.65 | 1.50 | 1 | 1.2344 | False | 2B | 88.0867 | 86.9600 | down | −1.51 | undercut | False | −1.40 | −1.67 | 1.26 |
| JPM | 332.38 | 1.84 | 1 | 2.9630 | False | 2B | 346.5209 | 340.2466 | down | −2.31 | below | False | −1.67 | −3.07 | 2.01 |

Universe counts on that run (3,961 tickers): RTI zone 1–2 = 3,788;
Golden Launch Pad = 322; 21dma pullback = 815.

### Suggested tests

- **EMA seeding:** `ewm(adjust=False)` gives different early values from an
  SMA-seeded EMA. Check against the table, not against TradingView's first
  bars.
- **GLP ddof:** ddof=0 in the z-score and ddof=1 in proximity. Swapping
  them changes the membership count.
- **21dma trend memory:** a series where the three EMAs disagree for a few
  bars after an uptrend must stay `'up'`.
- **Bar-by-bar replay:** the reference validates the vectorized 21dma code
  against a plain per-bar loop of the Pine logic (trend, dist within
  0.011, pullback flag). Do the same for each screener.
- **Short history:** tickers with < 21 / < 50 / < 200 bars → NaN / False,
  never an exception.

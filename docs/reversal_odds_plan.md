# Reversal Odds — plan (Market Health → Growth Cycle tab)

Status: **v1 built 2026-11-03** (`src/reversal_odds.py`, `config.REV_*`,
`test_reversal_odds.py`, `fetch_qqq_history.py`, view switch on the Growth Cycle
tab). Decisions: pre-2020 QQQ in `data_history/`, current data from
downloadData_v1; Nov 2 definition; switch at the top of the tab.

Fitted settings and differences from the plan below:
- ATR = 14-day Wilder (z -2.30 vs his -2.30).
- Trigger = `EMA21 + (mean - 1.75 * std) * ATR`, without the `1 / (1 - a)` term in
  section 3: 692.17 vs his 691.98 (the solved form gives 689.6). It ignores the
  EMA's own move, so the true flag close sits slightly lower.
- Flag first day = any entry into the state, no minimum spacing.
- Extended requires 50 above 200 (22 flags vs his 18; 24 without it).

Not reproduced: Reversal forward returns, ours +2.20% / +9.53% / 70% up vs his
+0.77% / +7.39% / 62%, on the same count of 43. Probe 16 vs 17; 50-below-200 CAGR
9.1% vs 6.9%. The Reversal 20-day gap changes the reading: ours beats the
all-sessions average, his doesn't. Cause unknown; his flag dates are not public.

Original plan: Source: Alex's public Prime Reports
(primetrading.substack.com, 11/01 and 11/02), text and board screenshots.

The board answers one question: when do the odds of a reversal increase? It
works on QQQ and publishes a closing price that would flag a signal.

## 1. His definition changed between the two boards

| | 11/01 post (Oct 30 close) | 11/02 post (Nov 2 close) |
|---|---|---|
| Stretch reference | price vs **50-day SMA**, in ATR | price vs **21-day EMA**, in ATR |
| Regime | price vs **200-day** | **50-SMA vs 200-SMA** |
| Cuts | -1.75σ / +1.50σ | -1.75σ / +1.75σ |
| Weekly gauge | distance from the 200-day (40-week) | same stretch vs the **10-week** |
| Stats table | 5 states, episode entries only | 3 flags (first day) + 2 regimes (every day) |
| Reading | Trend, day 66, -1.60σ, trigger 685.19 | Reversal, flagged 2 sessions, -2.30σ, trigger 691.98 |

The text of both posts still describes the 50-day / 200-day version, so the
text and the latest picture disagree. He is clearly still iterating.

**Recommendation: build the Nov 2 version, with every line and cut in
`config.REV_*`** so a further change is an edit, not a rewrite.

Evidence so far for the Nov 2 version: it says "flagged 2 sessions" at Nov 2,
so Oct 30 was already flagged. Our prototype at Oct 30 reads -1.82σ to -2.01σ on
the 21-EMA, past the -1.75σ cut, which agrees.

## 2. States (Nov 2 version)

| State | Rule | Meaning |
|---|---|---|
| Reversal | 50 above 200, stretch <= -1.75σ | Pullback inside an uptrend. "The flag" |
| Probe | 50 below 200, stretch <= -1.75σ | Same stretch in a correction: early more often than not, probe small |
| Extended | stretch >= +1.75σ | Stretched up |
| Trend | 50 above 200, otherwise | Nothing to do |
| Risk-off | 50 below 200, otherwise | Stay defensive |

The Trend and Risk-off rules are inferred: he names the states, not the exact
conditions. His caveats go on the page: not entry or exit signals, and a quiet
board is normal.

## 3. Calculation

New module `src/reversal_odds.py`, same shape as `src/growth_cycle.py`:

1. `x = (close - EMA21) / ATR`.
2. `z = (x - mean(x)) / std(x)` over a rolling 10 years (2520 sessions), plus the
   percentile of `x` in the same window.
3. Weekly gauge: the same on weekly bars against the 10-week. Context only, never
   a condition.
4. Regime: `SMA50 / SMA200 - 1`, and days since the last cross.
5. State per day, day in state, and the first day of each flag.
6. Trigger price, solved rather than searched. Today's EMA and ATR give the close
   that puts z exactly on the cut:
   `T = EMA21 + (mean - 1.75 * std) * ATR / (1 - a)`, with `a = 2 / 22`.
   Moving to tomorrow's bar changes EMA and ATR slightly, which is why he calls
   it "tomorrow's level, not a standing one".
7. Stats since 2018: forward 20d / 60d return and % up on the first day of each
   flag, against the all-sessions baseline; CAGR, volatility and max drawdown
   while inside each regime.

## 4. Picture

Banner + two columns, using the Growth Cycle tab's cards:

- **Left, top:** QQQ three years: candles, SMA200, SMA50, trigger line, shaded
  flag periods, ▲ markers.
- **Left, bottom:** "Structure extension", same dates: daily z bars, weekly z
  line, cuts at ±1.75σ and ±3σ.
- **Right:**
  - How far from / through the trigger (%, close vs trigger).
  - Where the daily sits (gauge with the cuts, percentile).
  - The regime (50 vs 200 %, day N, weekly gauge).
  - What each state has meant (flags and regimes tables).

## 5. Calibration targets (`test_reversal_odds.py`)

| Close | QQQ | State | Daily z | Trigger | Weekly z | Regime |
|---|---|---|---|---|---|---|
| Nov 2 | 681.09 | Reversal, 2 sessions | -2.30σ, 2nd pct | 691.98 | -1.71σ, 9th pct | +6.6%, day 343 |

Stats table on Nov 2, since 2018 (his):

| | N | 20d | 60d | Up at 20d |
|---|---|---|---|---|
| Reversal | 43 | +0.77% | +7.39% | 62% |
| Probe | 17 | +0.29% | +2.68% | 53% |
| Extended | 18 | +2.14% | -1.05% | 72% |
| All sessions | | +1.54% | +4.65% | 65% |

| Regime | Sessions | CAGR | Vol | Max DD |
|---|---|---|---|---|
| 50 above 200 | 1690 (81%) | 21.0% | 23% | -29% |
| 50 below 200 | 404 (19%) | 6.9% | 28% | -30% |

Sessions add up to 2094, about 8.3 years, so "since 2018" means roughly mid-2018.

Our QQQ files end Oct 30, so Nov 2 can only be tested after the next download.
Oct 30 is usable now only for the older 50-day version (his -1.60σ, trigger
685.19): the prototype reads -1.43σ to -1.54σ and a trigger of 677 to 683,
depending on ATR type. That is close but not there, and the short history
(section 6) is a likely reason.

## 6. Decisions needed

1. **Data: fetch longer QQQ history?** Our QQQ starts 2020-01-02 (6.8 years; no
   other local copy goes further). He uses a rolling 10-year window and stats
   since 2018, so a matching series has to start about 2008. Without it we use an
   expanding window from 2020, which changes every z, the cut crossings and the
   stats.
   **Recommendation:** a one-off yfinance pull into a file in this repo, leaving
   `downloadData_v1` alone. The daily files then extend it.
2. **Definition:** build the Nov 2 version as recommended in section 1?
3. **Layout:** a `Growth Cycle | Reversal Odds` switch at the top of the tab
   (**recommended**, the tab is already long), or a section below the cycle?

## 7. Open unknowns (settled by calibration)

- ATR length and type. Not stated; try 14 and 21, SMA and Wilder.
- Whether the 10-year mean and std include today.
- Whether a flag's "first day" resets after any gap or needs a minimum spacing.
- Adjusted vs raw closes: our SMA200 at Oct 30 reads 678.97 against his 679.52.

## 8. Build order

1. Answer section 6, fetch data if agreed.
2. `src/reversal_odds.py` + `config.REV_*` + calibration tests.
3. Tab UI, one check added to `test_dashboard_app.py`.
4. Mark it in `TODO.md`.

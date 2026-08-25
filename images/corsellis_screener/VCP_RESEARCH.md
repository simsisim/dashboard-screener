# Research: VCP (Volatility Contraction Pattern) as a candidate screener

Web research only — nothing implemented. Triggered by noticing the current
`src/leaders/minervini.py` only implements Minervini's **trend template**
(a same-day snapshot: price vs 50/150/200-SMA, 200-SMA rising, % above 52w
low, % within 52w high, RS ≥ 70) and does **not** implement VCP, which is
Minervini's separate pattern-recognition concept for timing the actual
entry within a stock that already passes the trend template.

## What Corsellis specifically says about VCP

He doesn't publish exact screener thresholds publicly (his StockScreenHero
VCP preset criteria live behind his paid course/membership). What's
documented across his Stockopedia articles and his "Master Volatility
Contraction Patterns then Screen for Setups" video:

- VCP is one of his four preferred breakout patterns (alongside Cup with
  Handle, High Tight Flag, Darvas Box) — all built on Minervini's work.
- Setup context: stock in a Stan Weinstein **Stage 2** uptrend, relative
  strength (ideally near/at a new 52-week high), broader market in an
  uptrend — he cites his own study of ~3,000 breakouts where 91% occurred
  with the market already in an uptrend.
- He notes **reward:risk targets of at least 2:1–3:1** on the resulting
  entry.

## General VCP definition (Minervini, reused by Corsellis and most VCP screeners)

- **Multiple contractions, each smaller than the last** — textbook example
  ~18% → 12% → 6% pullback-from-peak, progressively tighter.
- **Higher lows** on each successive contraction.
- **"Tennis ball action"** — sharp, quick recoveries off each pullback
  rather than a slow grind down.
- **Volume dries up** during the contractions (supply exhausting).
- **Tight closes near the top of the daily range** as the base tightens,
  and specifically a **tight inside day** right before breakout.
- **Breakout trigger**: price clears the contraction zone on volume
  **~40–50% above average**, closing **above the 20-day moving average**.

## Why this is a "screener," not a "filter" (per TAXONOMY.md)

Unlike the Minervini trend template (a same-day snapshot: today's price vs
today's MAs — one row of data), VCP is a **multi-bar shape**: it requires
detecting a sequence of swing highs/lows, measuring each swing's %-range,
checking the sequence is monotonically contracting, and checking volume
trends down through the sequence then spikes on breakout. That can't be
expressed as a single-column threshold — it needs a dedicated algorithm,
which is exactly the "combines ≥2 raw indicators into a new named
pass/fail" test in `TAXONOMY.md`'s decision rule.

## Rough shape of a future `src/leaders/vcp.py` (not scoped/built — just what it would need)

1. Detect local swing highs/lows in the price series (e.g. a fractal or
   rolling-max/min pivot detector) over a lookback window.
2. Measure each contraction's %-range (peak-to-trough between consecutive
   swing highs/lows).
3. Require ≥2–3 contractions with strictly decreasing %-range (and ideally
   higher lows each time).
4. Require average volume during each later contraction < average volume
   during the earlier one (volume dry-up).
5. Flag a breakout: price closes above the most recent contraction's high,
   on volume ≥ ~1.4–1.5× its recent average, closing above the 20-day MA.
6. Gate on Stage 2 (already computed in `src/focus/stages.py`) and RS
   (already computed for Minervini) as prerequisites, matching Corsellis's
   "setup context" — this reuses existing screener outputs rather than
   recomputing them.

## Open question before building this

Corsellis's exact numeric thresholds (contraction count minimum, %-range
cutoffs, volume-dry-up ratio, breakout volume multiple) aren't publicly
available — only Minervini's illustrative "18/12/6%" example is. Building
this screener means either (a) porting Minervini's published numbers
directly (same approach used for the trend template — cite Minervini, not
Corsellis, as provenance), or (b) treating the thresholds as tunable
`config.py` parameters from the start, since there's no single canonical
number to port.

## Sources

- [Volatility Contraction Pattern (VCP): Complete Guide — Mark Minervini](https://www.finermarketpoints.com/post/what-is-a-vcp-pattern-mark-minervini-s-volatility-contraction-pattern-explained)
- [Mastering the Volatility Contraction Pattern | TraderLion](https://traderlion.com/technical-analysis/volatility-contraction-pattern/)
- [Master Volatility Contraction Patterns then Screen for Setups - YouTube (Jack Corsellis)](https://www.youtube.com/watch?v=c6kscZN4BB4)
- [Technical Analysis | The 4 Best Breakout Chart Patterns | Jack Corsellis (Stockopedia)](https://www.stockopedia.com/content/the-4-best-breakout-chart-patterns-837899/)
- [Technical Analysis | Optimal Breakout & Spring Charts To Study | Jack Corsellis (Stockopedia)](https://www.stockopedia.com/content/optimal-breakout-spring-charts-to-study-776574/)
- [Welcome - JackCorsellis.com](https://jackcorsellis.com/)

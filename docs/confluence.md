# The Confluence model — badge-count leaders

This document explains the Confluence tab: what it is, where the idea comes
from, exactly how the count is built, what it does and does *not* trigger,
and its known limits.

- Code: `src/confluence.py` (`BADGES`, `compute()`, `rank()`, `merge_ondemand()`)
- UI: `dashboard.py` → `tab_confluence` (`_confluence_cards()`)
- Tests: `test_confluence.py` (18 unit checks), `test_dashboard_app.py` (tab AppTest)
- Plan: `IMPLEMENTATION_PLAN.md` §19
- Source idea: `docs/BADGES/` (@SteveDJacobs watchlist cards)

---

## 1. What it is

Every always-on screener in this project already answers a yes/no question
for every ticker ("is this a Minervini trend-template pass?", "is this a
Stockbee 9M mover?", …). The Confluence tab **inverts** that: for each
ticker it collects *which* screeners fired, and ranks the names lit up by
the most **independent method families**.

It is a **union with a membership-count sort**, not an intersection. An
intersection of ~20 screeners returns almost nothing; the point is to find
the handful of names where many unrelated methods agree at the same time —
"wait for your pitch."

The card layout mirrors the @SteveDJacobs watchlist cards in `docs/BADGES/`:
ticker, day change, size/momentum sub-line, a strip of colour-coded badge
pills, and two score circles.

---

## 2. Families, not raw badge count

The screeners are **correlated**. Minervini, Qullamaggie, Golden Launch Pad,
GMMA-bullish and RS≥90 all fundamentally require the same thing — strong
relative strength, stacked moving averages, an established uptrend. A stock
in a clean stage-2 advance collects five of those badges automatically, but
that is *one idea wearing five hats*, not five independent confirmations.

So the primary ranking key is **`n_families`**, not `n_badges`. Each badge
belongs to exactly one family; a family counts once no matter how many of
its badges fire.

| Family | Meaning | Badges |
|---|---|---|
| `trend_rs` | trend / RS leadership | `MM` `KQ` `SC` `GLP` `GMMA` `RS90` |
| `fundamentals` | earnings / sponsorship | `ON` `CE` |
| `accumulation` | volume / accumulation footprint | `ADL` `VOL` `SB9` `SBW` `SB4` |
| `breakout` | base-breakout structure | `52H` `NrH` `DB` `C&H` |
| `pullback` | re-entry into an existing trend | `EMA20` `REV` |
| `timing` | on-demand daily trigger | `PVB` `ATR1` `blue` `black` |

`stage 2A/2B/2C` and the RTI zone render on the card as faint **context**
pills — they are shown but never counted.

### Badge → source

| code | badge | source column in `screener_results.csv` (unless noted) |
|---|---|---|
| `MM` | Minervini trend template | `in_minervini` |
| `KQ` | Qullamaggie suite | `in_qullamaggie` |
| `SC` | SCOOTER / SCTR ≥ 90 | `in_scooter` |
| `GLP` | Golden Launch Pad | `in_gold_launch_pad` |
| `GMMA` | GMMA bullish | `gmma_state == "bullish"` |
| `RS90` | RS percentile ≥ 90 | `rs_pct >= 90` |
| `ON` | CANSLIM C-A-I | `in_canslim` |
| `CE` | CANTATA / CE leader | `in_cantata` |
| `ADL` | ADL accumulation | `in_adl_accumulation` |
| `VOL` | volume anomaly (3σ) | `in_volume_anomaly` |
| `SB9` `SBW` `SB4` | Stockbee 9M / 20% weekly / 4% daily | `in_9m_movers` / `in_weekly_movers` / `in_daily_gainers` |
| `52H` | 52-week-high breakout | `in_52w_high_breakout` |
| `NrH` | within 5% of the 52-week high | `pct_from_52w_high >= -5` |
| `EMA20` | EMA20 pullback test | `in_ema20_pullback` |
| `REV` | downtrend reversal | `in_downtrend_reversal` |
| `DB` | Green-line breakout (Darvas-style) | on-demand — `patterns_glb_*` cache |
| `C&H` | Cup & Handle | on-demand — `patterns_cup_handle_*` cache |
| `PVB` | Price-Volume Breakout buy | on-demand — `timing_signals_*` cache |
| `ATR1` | ATR1 cloud uptrend | on-demand — `timing_signals_*` cache |
| `blue` `black` | Dr Wish blue / black dot | on-demand — `timing_signals_*` cache |

Any badge whose source column is absent is simply left unlit — no error.

---

## 3. What "running the Confluence tab" does — and does not

**It does not run any screener, and it reads no price-history file.**

The 17 batch badges are `in_*` booleans that `run_screeners.py` already
computed once, for the whole ~4,000-ticker universe, in the latest
`results/YYYY-MM-DD/screener_results.csv`. The tab loads that same table
(the dashboard's `full` DataFrame), applies the scope filter (index
membership + min market cap) in memory, and `compute()` does a vectorised
boolean sum. Milliseconds. Freshness is whatever the last daily batch was —
shown in the caption; the header **"Re-run screeners"** button is the only
way to refresh it, exactly as for the Focus and Leaders tabs.

The 6 on-demand badges (`DB`, `C&H`, `PVB`, `ATR1`, `blue`, `black`) are the
expensive detectors that only run against a scoped subset from the Patterns
and Timing tabs. Confluence **does not run them**. It merges them
*opportunistically*: `merge_ondemand()` scans today's run directory for
`patterns_*` / `timing_signals_*` cache files and folds in whatever
positives it finds. If you have not run those tabs today, those badges stay
unlit and the caption says `on-demand badges: none cached today`. This is
deliberate — the tab is instant and never kicks off a minutes-long job.

So, to the two framings of "where does the data come from":

- **the batch badges** → the latest `screener_results.csv` already on disk
- **the pattern/timing badges** → today's on-demand cache *if it exists*,
  otherwise omitted

---

## 4. Outputs of `compute()`

Added to a copy of `full`:

| column | meaning |
|---|---|
| `bdg_<code>` | bool, one per badge |
| `badges` | list of active codes, in registry order |
| `n_badges` | raw count (context excluded) — the rounded-square number on the card |
| `families` | list of families with ≥ 1 active badge |
| `n_families` | **primary rank key** — the circle on the card |
| `confluence_score` | 0–100, capped at 2 badges per family then normalised; a smoother tie-breaker / alternate circle metric |
| `context` | `stage 2B`, `RTI z1` … — shown, never counted |

`rank(df, by)` sorts most-confluent first; ties break on the other two count
metrics, then SCOOTER score, then RS percentile.

The card's left **accent bar** and headline % come from `daily_gain_pct`
(green up / red down); the sub-line is `market_cap · gain_1m · ADR20%`.
Circle/square colours step grey → green → amber → orange by value.

---

## 5. Using the tab

1. **Scope** — pick index memberships (empty = whole universe) and a min
   market cap. Filters `full`; no compute cost.
2. **Rank by** — `n_families` (default), `n_badges`, or `confluence_score`.
3. **Min families** — hide anything below N families (default 3).
4. **Must include family** — e.g. require a `breakout` badge.
5. Read the cards; the ranked table below has every `bdg_*` column, a
   sparkline, multi-row select, CSV download, and "Save top-N / SELECTED as
   list" (writes `my_lists/*.csv`).

For the pattern/timing badges to appear, run the **Patterns** tab (GLB and
Cup & Handle) and the **Timing** tab for a scope that covers the names you
care about, on the same day.

---

## 6. Known limits

- **On-demand badges are scope-dependent.** A name that would break out but
  was not in the scope you ran Patterns/Timing against shows no `DB`/`C&H`
  badge. The merge is opportunistic, not exhaustive.
- **`confluence_score` is a heuristic**, not a backtested expectancy. There
  is deliberately no AI-assigned "strike zone" number — that would be
  backtesting, which is out of scope for this module (`intro.md`), and an
  opaque score conflicts with the project's "unbiased facts" stance. A
  transparent historical-expectancy column may be added later as a separate
  effort.
- **No earnings-proximity badge** — the project has no earnings-date field,
  so @SteveDJacobs's `ER-1` has no equivalent here.
- **Family assignment is a judgement call.** `NrH` (near 52w high) sits in
  `breakout`, but a name can be near its high without any base. Read the
  badges, not just the number.
- The count reflects **one daily bar**. It is a screen, not a signal — a
  low-risk entry still has to be there (`intro.md` §1).

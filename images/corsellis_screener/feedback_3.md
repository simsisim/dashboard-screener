# Feedback round 3 — presets missing for the round-1 screeners

**STATUS: RESOLVED.** 6 presets added (Stockbee 9M/Weekly/Daily, Golden
Launch Pad, Qullamaggie, ADL Accumulation), GMMA/volume-anomaly/raw-column
presets correctly skipped. Independently re-verified: `validate.py`
ALL 14 presets == manual filters with exact counts (29/19/41/409/23/9);
`test_dashboard_app.py` 11/11 including the two new live-UI preset checks.
A real bug surfaced and was fixed during this round (`dashboard.py:437-441`
was mapping `adv_x` flags to a column literally named `x` instead of
`in_x` — presets silently no-op'd). The 5 unrelated `validate.py` failures
seen alongside this (Weinstein/RTI/GLP/volume-ADX/ADL cross-checks) were
independently confirmed to be a live, in-progress daily-data download
(some tickers' last bar stuck at 2026-08-21 while others already have
2026-08-24) — not a code regression; re-run `validate.py` once the
download finishes.

Context: the 7 screeners from `more_screeners.md` (Stockbee Movers, Golden
Launch Pad, GMMA, Qullamaggie, Volume+ADX, Volume anomaly, ADL
accumulation) are all wired as **Advanced filters** (checkboxes/multiselect
in the expander) but none of them got a **Preset** — unlike Minervini,
CANSLIM and SCOOTER, which are both an Advanced-filter entry *and* a
one-click named preset in "Ioa's Presets". This task closes that gap for
the candidates where it's warranted — see `TAXONOMY.md` for why a preset
is "no new code, just a saved combination of filter values that already
exist," and `feedback_2.md` §0 for why the key-naming has to be exact.

**Good news / prerequisite already satisfied:** all 8 new advanced-filter
keys (`adv_9m_movers`, `adv_weekly_movers`, `adv_daily_gainers`,
`adv_gold_launch_pad`, `adv_gmma_state`, `adv_qullamaggie`,
`adv_volume_anomaly`, `adv_adl_accumulation`) are already registered in
`dashboard_filters.ADVANCED_DEFAULTS` — confirmed by inspection. So the
baseline-reset mechanism that fixed §0 already covers them; a preset
using any of these keys will not repeat that regression as long as you
use these exact key names (not the bare/short names — that's precisely
what broke last time).

## Add these presets (clear candidates — same shape as Minervini/CANSLIM/SCOOTER)

Each is a self-contained named method with a boolean/flag output, exactly
parallel to the existing 3. Suggested `PRESETS` entries (adjust naming
freely, but keep the `adv_`-prefixed keys exact):

1. **"Stockbee 9M Movers"** — `advanced: {'adv_9m_movers': True}`. No
   extra liquidity gate needed — the 9M-share volume requirement already
   is one.
2. **"Stockbee 20% Weekly Movers"** — `advanced: {'adv_weekly_movers': True}`.
3. **"Stockbee 4% Daily Gainers"** — `advanced: {'adv_daily_gainers': True}`.
   (Keep these three separate presets rather than one combined "any
   Stockbee mover" — Stockbee's own methodology treats them as three
   distinct scans, and that matches how Minervini/CANSLIM/SCOOTER are
   three separate presets rather than one union.)
4. **"Golden Launch Pad"** — `advanced: {'adv_gold_launch_pad': True}`,
   plus a liquidity floor in `selections` (e.g. `'adv': '> $1M'`),
   matching how the existing structural presets (Minervini, Weinstein,
   RTI) already bundle one.
5. **"Qullamaggie Suite"** — `advanced: {'adv_qullamaggie': True}`. The
   source methodology itself gates on market cap ≥ $1B — `_mktcap()`'s
   bucket options don't have an exact $1B rung (`'> $300M (small+)'` /
   `'> $2B (mid+)'`), so either use the custom-range slider for an exact
   $1B floor or accept `'> $2B (mid+)'` as the closest faithful bucket —
   your call, just document which you picked and why in the preset's
   comment (same style as the `Momentum Leader (Narrow)` comment).
6. **"ADL Accumulation"** — `advanced: {'adv_adl_accumulation': True}`.

## Optional — weaker fit, use your judgment, don't force it

- **GMMA** — output is a *state* (`gmma_state`), not a pass/fail. A
  preset like "GMMA Bullish Alignment" (`advanced: {'adv_gmma_state':
  ['bullish']}`) is doable but thinner justification than the six above
  — it's pinning one value of an existing filter rather than encoding a
  distinct named method. Add it only if it feels genuinely useful, not
  to hit a quota.
- **Volume anomaly (3σ)** — same shape as Stockbee (an event-of-the-day
  flag). Could get `advanced: {'adv_volume_anomaly': True}` as a preset,
  but it's borderline whether a raw statistical spike flag is a "method"
  worth top-level naming vs. just a filter someone reaches for
  occasionally. Your call.

## Do NOT add presets for

- **Volume+ADX raw columns** (`vroc25`, `adtv_50`, `mfi14`, `adx13`,
  `plus_di13`/`minus_di13`) — these are filter-shaped, same category as
  ADR%/ADV today. None of the existing presets are built around a single
  raw indicator threshold in isolation either; they only become
  interesting composed with other filters (see `Momentum Leader
  (Narrow)`, which combines four). Leave these as pure filters unless a
  specific compound preset idea comes up later.

## Definition of done (per preset)

- [ ] Added to `dashboard_filters.PRESETS` using the `{'selections': {...},
      'advanced': {...}}` shape, `adv_`-prefixed keys matching
      `ADVANCED_DEFAULTS` exactly (copy-paste the key name from
      `ADVANCED_DEFAULTS`, don't retype it)
- [ ] A **behavioral** `validate.py` check added — same pattern as the
      existing "ALL 8 presets == manual filters" check: build the mask
      via `dfil.build_mask` + the preset's `advanced` conditions, assert
      it equals a hand-written pandas mask on the same columns the
      screener's own Task-N check already validated (this should be
      close to trivial for the boolean-flag presets — the preset mask
      *is* the column, possibly ANDed with one liquidity selection)
- [ ] Full `validate.py` run still green — all checks, not just the new
      ones (same discipline as `more_screeners.md`'s Definition of Done)
- [ ] `test_dashboard_app.py`: extend the preset-count check (currently
      spot-checks Minervini/SCOOTER/CANSLIM) to include at least one or
      two of the new presets, so the live-UI regression guard covers them
      too, not just `validate.py`'s data-level check

## One thing to think about, not a blocker

"Ioa's Presets" currently has 8 entries; adding 6-8 more roughly doubles
it. Worth a small naming convention (e.g. grouping stockbee's 3 with a
shared prefix) so the dropdown stays scannable — no strong opinion here,
use your judgment, don't over-engineer it.

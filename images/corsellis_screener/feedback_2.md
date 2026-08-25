# Feedback round 2 — verification of the round-1 fixes

**STATUS: RESOLVED.** §0 and the custom-range issue were both fixed and
independently re-verified (see below) — `validate.py` 10/10,
`test_dashboard_app.py` 9/9 (new, AppTest-based, committed and runnable).
Preset counts reproduced exactly: Minervini 8/8=365, Weinstein=972,
CANSLIM=141, SCOOTER=366, Tight consolidation=2144, Leaders not
extended=306, Momentum Leader=38, Large-cap pullback=361. Kept below as
the historical record of the regression and its root cause.

Reviewed by reading the current `dashboard.py` / `dashboard_filters.py` and
independently re-running `validate.py`. No code changed. Verdict: **4 of
the 4 claimed fixes check out at the code level**, but the same refactor
that fixed §1 introduced a **critical regression** — 7 of 8 built-in
presets are now silently broken — found afterward via live use, not by
`validate.py`. That's the priority; see §0 below before the rest of this
file.

## §0. CRITICAL REGRESSION: 7 of 8 built-in presets are broken (user-reported, confirmed)

Reported by the user: loading the "Minervini" preset returns thousands of
tickers instead of ~391; same with SCOOTER. Confirmed and root-caused.

**Good news first:** the underlying screener computation is *not*
affected. `leaders_minervini.csv` (391), `leaders_scooter.csv` (366), and
`leaders_canslim.csv` (141) are all correct — verified directly against
the latest `results/` run. The **🏆 Leaders' Lists** tab is fine. This bug
is isolated to how the "Ioa's Presets" dropdown applies itself in the
**🔎 All Results** tab.

**Root cause:** the §1 fix (`ADVANCED_DEFAULTS` + baseline-then-overlay in
`_apply_preset`) renamed the advanced session-state keys to `adv_leaders`,
`adv_stages`, `adv_max_ext`, `adv_min_rs`, `adv_rti_zone`,
`adv_leaders_mode` — but `dashboard_filters.PRESETS` was never updated to
match. It still uses the pre-refactor bare names: `'leaders'`, `'stages'`,
`'max_ext'`, `'min_rs'`, `'rti_zone'`, `'leaders_mode'`. `_apply_preset`
now does:

```python
advanced = dict(dfil.ADVANCED_DEFAULTS)   # adv_leaders, adv_stages, adv_max_ext, ...
advanced.update(p.get('advanced', {}))    # leaders, stages, max_ext, ...  <- different keys!
```

Since `'leaders' != 'adv_leaders'`, `dict.update()` just adds a harmless,
never-read `'leaders'` key — `adv_leaders` stays at its empty baseline.
The mask-building code's `if st.session_state['adv_leaders']:` guard is
then always false, so the leaders-list/stage/max-ext/min-RS/RTI-zone
filter is silently skipped for every preset that uses one.

Checked all 8 presets programmatically (`set(p['advanced']) -
set(dfil.ADVANCED_DEFAULTS)`): **7 are broken.** The one survivor,
`Momentum Leader (Narrow)`, has an empty `'advanced': {}` dict — which is
exactly why `validate.py`'s existing behavioral check (the only one that
runs a preset end-to-end) didn't catch this: it only exercises that one
unaffected preset.

Measured against the current `results/2026-08-25/` run (universe = 3,961):

| Preset | Shows now (broken) | Should show |
|---|---|---|
| Minervini 8/8 (liquid) | 2,256 | 391 |
| CANSLIM C-A-I leaders | **3,961 (entire universe, zero filters applied)** | 141 |
| SCOOTER >= 90 | **3,961 (entire universe, zero filters applied)** | 366 |
| Weinstein 2A/2B not extended | broken (stage + max-ext dropped) | — |
| Tight consolidation (RTI) | broken (rti_zone dropped) | — |
| Leaders not extended (<= 2 ATR) | broken (leaders + max-ext dropped) | — |
| Large-cap uptrend pullback | partially broken (stage gate dropped) | — |
| Momentum Leader (Narrow) | ✅ correct, unaffected | — |

**Fix:** either rename `PRESETS`'s advanced keys to the `adv_`-prefixed
names so they match `ADVANCED_DEFAULTS` directly (simplest — makes the
generic `dict.update()` merge actually work), or keep the short names and
restore an explicit translation table in `_apply_preset`. Either way,
**`validate.py`'s behavioral check needs to run all 8 presets, not just
one** — assert each preset's resulting ticker count/mask matches its
manual-filter equivalent (e.g. `Minervini 8/8 (liquid)` should match
`in_minervini & (adv50_dollar >= 1e6)`, `SCOOTER >= 90` should match
`in_scooter`, etc.) — the whole reason this regression shipped despite
"9/9 checks passed" is that only 1 of 8 presets was ever behaviorally
exercised. Also double check `load_screener`'s advanced-key handling
isn't hiding the same class of mismatch (it currently isn't, since
user-saved screeners are captured via `dfil.ADVANCED_DEFAULTS`'s own keys
— but worth confirming explicitly given how this one slipped through).

This supersedes the "Recommendation" priority at the bottom of this file
— fix §0 first, then the custom-range issue below, then move on to new
screeners.

## Confirmed fixed

**§1 — advanced-filter leak across presets.** `dashboard_filters.ADVANCED_DEFAULTS`
is the single 13-key no-op baseline you described, and `_apply_preset`,
`_init_filter_state`, `_reset_filters`, and the "My Screener" load block
all build off it the same way (defaults first, then overlay). Ran
`validate.py` myself — `preset shapes valid (all 8 presets)` and
`preset == manual filters (Momentum Leader Narrow) (38 tickers)` both
pass, which is a real regression guard for exactly this bug (it directly
checks that a preset produces the same result as setting the same filters
by hand). Good call adding that second check.

**§2 — save actions not refreshing dropdowns.** All four saves + both
deletes now set `st.session_state['_flash']` and call `st.rerun()`, and
the flash is popped/displayed once at the top of `tab_all`. Confirmed
this is the right fix for the reason you gave: `st.rerun()` aborts the
rest of the script immediately, so an inline `st.success()` at the button
site would never have rendered — stashing it in session state and
displaying it after the rerun is the correct way to survive that.

**§3 — "Ioa's Lists" mislabel.** `tb2` is now `'Upload list (CSV/TXT)'`
with a help string explicitly reserving "Ioa's Lists" for a future
curated source. Matches option (a) from feedback_1.md exactly.

**§5 — polish.** `Reset Filters` now clears `save_as_name`/`save_list_name`;
`_spark_closes(symbol, run_name)` takes `run_name` without the underscore
prefix, so it's genuinely part of the cache key now.

Bonus, not explicitly claimed but true as a side effect of the
`ADVANCED_DEFAULTS` refactor: `Reset Filters` now also resets
`adv_leaders_mode`, which the old reset dict was missing.

## New bug found while verifying §1/§3: custom slider ranges don't survive Save Screener / My Screener

This wasn't in feedback_1.md — found it while checking whether "presets
and saved screeners behave consistently" (your §1 claim) actually holds
end-to-end.

**Repro:**
1. Pick preset `Momentum Leader (Narrow)` — it sets `20d ADR %` to the
   *Custom…* slider at (6.0, 60.0) via `_apply_preset`'s special-case
   handling of `('custom', lo, hi)` tuples (`dashboard.py:159-161`).
   Confirmed correct: the preset's own `validate.py` check
   (`preset == manual filters (Momentum Leader Narrow)`) proves this
   applies correctly at preset-click time.
2. Click **Save Screener As…**, name it anything.
3. `_current_panel()` (`dashboard.py:310-313`) captures
   `st.session_state[f'sel_{k}']` directly for every filter. For a
   filter sitting on *Custom…*, that session-state value **is the
   literal string `'Custom…'`** — the actual slider bounds live in a
   *separate* key, `custslider_adr`, which `_current_panel()` never
   reads. So the saved JSON gets `"adr": "Custom…"` with the 6.0-60.0
   bound silently dropped.
4. Later, pick that saved screener from **My Screener**. `load_screener`'s
   apply block (`dashboard.py:223-241`) sets `sel_adr = 'Custom…'` (a
   valid selectbox option, so no crash) but never restores
   `custslider_adr`. The slider re-renders at its family default
   (`CUSTOM_RANGE['adr'] = (0.0, 60.0)`) — i.e. no ADR floor at all. The
   "≥6% ADR" momentum criterion the whole preset was named for is gone,
   with nothing on screen indicating it happened.

**Why this matters now specifically:** before this round, no shipped
preset used a custom range, so the gap was latent. `Momentum Leader
(Narrow)` (added this round, per `TAXONOMY.md`'s worked example) is the
first one that does — and "load a preset, then Save Screener As… to make
a personal tweak" is an obvious, natural workflow, so this is now
reachable, not just theoretical.

**Fix shape:** `_current_panel()` needs the same special-case `_apply_preset`
already has, mirrored for capture instead of apply — for any key where
`st.session_state[f'sel_{key}']` (or "Custom…"), read `custslider_{key}`
and store `('custom', lo, hi)` instead of the bare string. `json.dumps`
will need a tuple→list round trip (`json` turns tuples into lists on
save, and `_apply_preset`'s tuple check should be relaxed to accept lists
too, since `json.loads` will hand back a list, not a tuple, for anything
saved this way) — worth a `validate.py` case similar to the existing
preset-equivalence check, but round-tripping through
`save_screener`/`load_screener` instead of `_apply_preset`.

## Not independently verified

I looked for an `AppTest`-based test file to re-run the "AppTest 0
exceptions throughout" claim myself (`grep -ril apptest .`) and didn't
find one committed anywhere in the repo — only a mention in
`IMPLEMENTATION_PLAN.md`. Not a red flag by itself (it may have been run
ad hoc and not saved), but worth committing that script if it's reusable,
so this kind of claim is independently re-runnable next time the way
`validate.py` already is.

## Recommendation

Priority order: **§0 first** (7/8 presets are unusable right now — this
is user-facing and was caught by actually using the dashboard, not by the
test suite). Then the custom-range round-trip — small, contained change
in `_current_panel()`/`load_screener`. Both should get a `validate.py`
case that exercises the real behavior (all 8 presets for §0; a
save→load round trip for the custom-range issue) so neither class of bug
can ship silently again. Only after both: move on to new screeners.

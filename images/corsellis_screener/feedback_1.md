# Feedback for the implementing agent — round 1

Code-level review of the current `dashboard.py` / `dashboard_filters.py`
(no browser test — see note at bottom). Most of the earlier review
(`DASHBOARD_REVIEW.md`) is already done: the preset-dict bug is fixed,
Search/Number-of-Results/pagination exist, delete is wired up for both My
Screener and My Lists, per-row select + "save selected as list" + CSV
export both work, sparklines were added. What's left:

## 1. Bug: advanced filters leak across preset switches

`_apply_preset()` (`dashboard.py:157-174`) fully resets the 14 basic
filters and 6 advanced keys (`adv_leaders`, `adv_leaders_mode`,
`adv_stages`, `adv_max_ext`, `adv_min_rs`, `adv_rti_zone`) — but never
touches **`adv_min_count`, `adv_rti_dots`, `adv_rti_exp`, `adv_exchange`,
`adv_index`, `sel_sector`, `sel_industry`**. Whatever those held before
stays active and silently stacks onto the next preset you pick.

Example: check "RTI low-vol dots" or pick a Sector manually, then click
`SCOOTER >= 90` — you'd expect a clean SCOOTER-only view but actually get
SCOOTER ∩ (leftover sector) ∩ (leftover RTI-dots flag), with no visible
warning.

Contrast with `load_screener()` (My Screener dropdown, `dashboard.py:234-243`),
which writes the *full* advanced-key set because it was captured in full
at save time — so presets and saved screeners behave inconsistently with
each other. `Reset Filters` is currently the only fully-clean state.

**Fix:** make `_apply_preset` reset the same full key set that
`_reset_filters`/`load_screener` use, defaulting anything the preset
doesn't specify (empty list / `False` / `0`, matching each key's
no-op value).

## 2. Bug: save actions don't refresh their own dropdown

`Delete screener` and `Delete list` both call `st.rerun()` after deleting.
The four save actions — `Save Screener`, `Save Screener As…`, `Save
upload as list`, `Save SELECTED/ALL as list` — don't. A newly-saved
screener/list won't appear in the `My Screener` / `My Lists` selectbox
until some *unrelated* interaction triggers the next rerun. The
`st.success` toast fires, but the dropdown looks like the save silently
failed.

**Fix:** add `st.rerun()` after each of the four save actions, same
pattern as the two delete buttons.

## 3. Naming mismatch: "Ioa's Lists" vs "My Lists" have no actual distinction

Per the sketch (`tab_all_results.png`) and `TAXONOMY.md`, **"Ioa's
Lists"** was meant as the built-in/curated counterpart to **"My Lists"**
(the same relationship "Ioa's Presets" has to "My Screener" — built-in
vs. user-owned). Right now `tb2`'s label is `"Ioa's Lists — upload
CSV/TXT"`, but it's the *upload* widget — anything uploaded there gets
saved into the exact same `my_lists/` store that `tb4`'s "My Lists"
dropdown reads from. So the two labels don't correspond to two different
corpora; it's one user-owned workflow (upload → save) split across two UI
slots.

**Fix, pick one:**
- (a) Rename `tb2` to something like "Upload list" and drop the "Ioa's"
  branding from it — it's user-owned, same as "My Lists".
- (b) Or actually build a curated/shipped list source (see item 4) and
  move the "Ioa's Lists" label onto *that*, leaving `tb2`/`tb4` both under
  "My Lists" the way "My Screener" (load) and the save buttons already
  share one corpus.

## 4. Still open: no genuinely curated/shipped list source

Every "list" today is either uploaded or exchange/index membership parsed
from the universe CSV. There's still no repo-shipped, versioned list
(e.g. "Recent IPOs", a hand-curated watchlist checked into git) — the
actual "Ioa's Lists" concept from the sketch. Low priority; only worth
doing once there's a concrete list worth shipping.

## 5. Minor polish (low priority, do opportunistically)

- `Reset Filters` doesn't clear the `save_as_name` / `save_list_name`
  text inputs — typed-but-unsaved text lingers after a reset.
- `_spark_closes`'s cache key ignores `run.name` (passed as `_run_date`,
  and the leading underscore tells Streamlit not to hash it). Harmless
  today since sparklines read live daily-bar files rather than the run
  snapshot, but the parameter name implies an intent to bust the cache
  per run that isn't actually happening — either rename it to drop the
  underscore (making it part of the cache key) or drop the unused param
  entirely.
- No rename for saved screeners/lists, only delete — fine for now, flag
  only if it becomes annoying in practice.

## 6. Future screener candidates (research done, not scoped/built)

Two research docs already exist in this folder if/when there's appetite
to add a new leaders-list screener: Disscuss this with the human, if this needs to be done

- `VCP_RESEARCH.md` — Minervini/Corsellis Volatility Contraction Pattern:
  why it's a multi-bar pattern-detection problem (not a simple threshold),
  and the rough shape a `src/leaders/vcp.py` would need.
- `SCREENER_INVENTORY.md` — survey of ~25 prior screener implementations
  in `metaData_v1/src/screeners`, sorted into: already-your-validation-
  reference, strong new-screener candidates (Qullamaggie Suite, Golden
  Launch Pad, GMMA, the 5-step ADL/accumulation suite, Stockbee's
  volume/momentum movers), filter-shaped-not-screener-shaped (ADX, RVOL,
  ADTV), and out-of-scope-for-this-module (Dr. Wish, PVB — those are
  Step-3 entry-timing signals per `intro.md`'s own scope decision, not
  Step-2 leader classification).

- /home/imagda/_invest2024/python/metaData_v1/src/screeners -screeners implemented for previous project

## Note on how this review was done

No live browser test this round — reviewed by reading `dashboard.py` and
`dashboard_filters.py` directly. Items 1 and 2 are verified from the code
(session-state keys that are/aren't touched, rerun calls that are/aren't
made); items 3-4 are design/naming observations against `TAXONOMY.md`; if
anything here reads differently once actually clicked through in the
browser, trust what you see in the running app over this document.

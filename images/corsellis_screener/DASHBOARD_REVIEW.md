# Dashboard review — vs. the Corsellis (StockScreenHero) reference

Comparing the current `dashboard.py` / `dashboard_filters.py` implementation
against the reference screenshots in this folder (`dashboard_screener.png`,
`screener_2.png`, `screener_results.png`, `tab_all_results.png`,
`av_dollar_volume.png`). Research/observation only — no code changed.

Note on naming: the video's UI labels the built-in dropdowns "Jack's
Presets" / "Jack's Lists" (Jack Corsellis is the creator of that tool). In
`tab_all_results.png` you sketched your own version of that layout and
relabeled those two columns **"Ioa's presets" / "Ioa's Lists"** — i.e. in
*this* project the built-in/curated side should carry your name, not
Jack's. The table below uses "Ioa's Presets/Lists" to refer to your sketch
and "Jack's Presets/Lists" only when specifically citing the source video's
UI.

## 1. Bug found: the "Presets (method templates)" dropdown is a no-op

`dashboard_filters.PRESETS` stores each preset as a flat dict with a
`'_advanced'` key alongside any top-level filter keys, e.g.:

```python
'Minervini 8/8 (liquid)': {
    '_advanced': {'leaders': ['minervini'], 'leaders_mode': 'Any', 'adv_min': 1e6},
},
```

But `dashboard.py`'s `_apply_preset()` reads:

```python
p = dfil.PRESETS[name]
for k, v in dfil.normalize_selections(p.get('selections', {})).items(): ...
adv = p.get('advanced', {})   # <-- looks for 'advanced', preset stores '_advanced'
```

Since no preset has a `'selections'` key, `normalize_selections({})` just
resets every filter to `'All'`. Since no preset has an `'advanced'` key
(they all use `'_advanced'`), `adv` is always `{}` — so `adv_leaders`,
`adv_stages`, `adv_max_ext`, `adv_min_rs` are all reset to their empty
defaults too. **Net effect: picking any built-in preset silently clears the
panel instead of applying it.** This is the single highest-value fix —
right now the "Jack's Presets" equivalent doesn't work at all.

Secondary related issues once that's fixed:
- `'adv_min'` (evidently meant as a minimum ADV/volume threshold) is set in
  five presets but never read anywhere in `dashboard.py` — dead key.
- `'leaders_mode': 'Any'` vs the UI's own vocabulary `'Any (union)'` /
  `'All (intersection)'` — works today only because `.startswith('Any')` is
  lenient; worth making the preset dict use the same literal strings the
  widget uses, so a `dict ==` / round-trip stays honest.
- `'Leaders not extended (<= 2 ATR)'` sets `'leaders_any': True`, a key the
  reader never looks for at all (it looks for `'leaders'`, a list) — this
  preset can never populate `adv_leaders`.

## 2. Structural gaps vs. the reference UI

| Your sketch (`tab_all_results.png`) / Corsellis video | Current dashboard | Note |
|---|---|---|
| **Ioa's presets** (sketch) / *Jack's Presets* (video) vs **My Screener(s)** as two separate dropdowns | one `Presets (method templates)` dropdown + one `My Screener` dropdown | conceptually already right — built-ins and user-saved are separate; just the built-in side is broken (§1). Consider relabeling the dropdown from generic "Presets (method templates)" to **"Ioa's Presets"** to match your own sketch naming |
| **Ioa's Lists** (sketch) / *Jack's Lists* (video) — curated, static, shipped — vs **My Lists** (user's own) | only `My Lists` (uploaded/saved) + on-the-fly Index membership (S&P 500, Russell…) | index membership is a fine stand-in for "curated lists", but there's no shipped/curated ticker list (e.g. "Recent IPOs") the way the reference ships its own; if added, "Ioa's Lists" is the right label per your sketch |
| `Search` box (free-text ticker/name search) in Results | none | can't quickly jump to a ticker in the filtered table without scrolling/sorting |
| `Number of Results` (pagination, 30/50/100) | none — full filtered set rendered in one scrollable `st.dataframe(height=480)` | fine for now at ~700-4000 rows since Streamlit's dataframe is virtualized, but there's no page-size control, and a `leaders_all` (740 rows) or unfiltered "All Results" (3,961 rows) view has no way to say "just show me 30" the way the reference does |
| `Manage My Screeners` / `Manage My Lists` buttons | save-only — `dfil.delete_screener()` exists in `dashboard_filters.py` but is never called from `dashboard.py`, and there's no rename/delete UI for lists either | dead function; no way to clean up saved screeners/lists from the UI once created |
| Per-row `+ List` / `- List`, `Select All`, checkboxes, `Export` on selected rows | single `Download filtered CSV` for the *whole* filtered set | no way to hand-pick a subset of the filtered results and save just those as a new list — every save currently has to go through the full-panel "Save Screener" or a separate file upload |
| Result cards with a mini price chart per ticker | plain table (`st.dataframe`) | biggest visual difference, but arguably lower priority — see §4 |

## 3. Things already done well (keep as-is)

- **Filter/preset/list separation matches the reference's mental model**:
  `SPEC_BY_KEY` (atomic column+threshold filters) vs `PRESETS` (named
  bundles) vs `my_lists/`+`my_screeners/` (persisted state) is the right
  shape, it's just wired up incorrectly for presets (§1).
- **Screener outputs feed back into the filter panel** — `in_minervini` /
  `in_canslim` / `in_scooter` and `minervini_count` are both a Leaders-tab
  result *and* a filterable column in Advanced filters (`adv_leaders`,
  `adv_min_count`). That's exactly the "a screener's output becomes a new
  filter" pattern from the taxonomy (see `TAXONOMY.md`).
  Corsellis doesn't visibly do this (his "leaders lists" are just Lists in
  the top bar), so this implementation is arguably more capable there.
  Sanity-check worth doing anyway: with the preset bug fixed, confirm a
  couple of presets (e.g. `Minervini 8/8 (liquid)`, `SCOOTER >= 90`) produce
  the expected row counts against a known-good manual filter combo, and
  add that as a `validate.py` case so a future refactor can't silently
  regress it again.
- **Custom-range escape hatch** (`'Custom…'` reveals a slider with
  family-specific bounds) is a nice addition over the reference, which only
  offers fixed dropdown buckets (`> 6%`, `> 25M`, etc. per
  `av_dollar_volume.png`).
- **Index-membership filter** (S&P 500 / Russell / NASDAQ Composite / Dow /
  STOXX, parsed from the universe CSV's `Index` column) has no equivalent
  called out in the reference screenshots and is a genuinely useful add.

## 4. Suggested priority order

1. **Fix `_apply_preset`** to read `p.get('_advanced', {})` and treat
   everything outside `'_advanced'` as the flat selections dict (or,
   simpler: change `PRESETS` to the `{'selections': {...}, 'advanced':
   {...}}` shape the reader already expects — either works, just make the
   writer and reader agree). This is a one-file, low-risk fix and the
   dropdown is currently pure dead weight without it. While touching this,
   consider renaming the widget label to **"Ioa's Presets"** (matching your
   sketch) so it reads as "the built-in/curated set" the same way "My
   Screener" reads as "mine" — right now both sides sound user-owned.
2. **Wire up `delete_screener()`** (already written, unused) behind a
   small "Delete" button next to the `My Screener` selectbox, and add the
   equivalent for `my_lists/`.
3. **Add a ticker/company search box** above the All Results table —
   cheapest of the missing reference features, highest daily-use value.
4. **Add a page-size selector** (`Number of Results`: 30/50/100/All) so the
   All Results tab doesn't always render every matching row.
5. Lower priority / optional: per-row checkboxes + "save selected as list"
   in the All Results table; mini sparkline/price-thumbnail column (a
   screening tool doesn't strictly need charts the way a discretionary
   scan-by-eye tool does, since the operator still has to look up the
   chart before acting per `intro.md`'s step-3 boundary — this is a
   nice-to-have, not a functional gap).

# Feedback round 6 — add a 3-month Confirmation period option to GLB

Small, single-parameter addition to the Patterns tab, not a bug fix.
User's reasoning (domain judgment, not something to second-guess): short
Lookback periods (3m, 6m) pair naturally with short Confirmation periods
(1w, 2w); long Lookback periods (1y, 2y) want a longer Confirmation
option too — currently capped at 1m, which feels short relative to a
1-2 year lookback. Add a **3m** confirmation choice.

## Where

`dashboard.py:900-902`:

```python
_conf = g3.selectbox('Confirmation period', ['1w', '2w', '1m'],
                     key='pt_glb_conf')
pt_params['confirmation_bars'] = {'1w': 5, '2w': 10, '1m': 21}[_conf]
```

Add `'3m'` to both the options list and the bar-count mapping. Use
**63 trading days** for consistency with the Lookback dropdown's own
`'3m': 63` mapping a few lines up (`_lb_bars = {'3m': 63, '6m': 126, '1y':
252, '2y': 504}` — same convention, don't invent a different day-count
for "3 months" between the two dropdowns).

## Why this doesn't need the lookback-style cache-key fix

`confirmation_bars` was already part of the cache-key hash from the
start (`pt_params['confirmation_bars'] = ...` happens *before* the hash
at `pt_ph = hashlib.md5(...)`, unlike `lookback_bars`, which was the bug
in `feedback_5.md`/`feedback_4p5.md`). Adding a new value to an
already-correctly-hashed parameter should just work — a run with
Confirmation=3m will naturally get its own distinct cache file the same
way 1w/2w/1m already do. No special handling needed, just verify it
after adding (see DoD).

## Definition of done

- [ ] `'3m'` added to the Confirmation period selectbox options
- [ ] `confirmation_bars` mapping includes `'3m': 63`
- [ ] Quick check: running with Confirmation=3m produces a cache file
      distinct from a 1m run on the same scope (same spirit as the
      existing 1y/2y lookback regression test — doesn't need its own
      elaborate test, just confirm the existing hash mechanism handles
      the new value correctly, since a config typo here — e.g. reusing
      21 instead of 63 — wouldn't be caught by anything else)
- [ ] `validate.py` + `test_dashboard_app.py` still green

# Feedback round 4.5 — test-suite gaps left after the cache-key fixes

Sequencing note: this is a small follow-up to `feedback_4.md`, found while
verifying the cache-key fixes you already made proactively (GLB's hash
missing `lookback_choice`, Timing's scope key missing the selected
sources — both confirmed fixed in code: `dashboard.py:907` and
`dashboard.py:737-739`). `feedback_5.md` was drafted to report that same
GLB bug but you fixed it before it was sent — that report is now
superseded by this one. Read this one first; `feedback_5.md`'s only
still-relevant content is its "double-check Cup & Handle's `pt_preset`
key" note, which was separately confirmed fine (it's directly in the
f-string, not hashed-then-dropped like GLB's lookback was).

Both fixes below are about the **test suite**, not the application —
the actual cache-key behavior is correct. This is the same category of
issue as `feedback_2.md` §0: a check that reads green without actually
exercising current behavior.

## Gap 1: `test_dashboard_app.py`'s persistence check is stale

`test_dashboard_app.py:214`:

```python
cache_p = _latest_run_dir() / 'timing_signals_nasdaq100_cap0.csv'   # no source suffix
check('timing tab: scoped results persisted', cache_p.exists(), ...)
```

The fixed `ts_key` construction now appends the sorted source list, so a
Run with sources `['ATR1 Trend', 'Blue Dot', 'Black Dot']` (which is what
this test selects, line 203) actually persists to
`timing_signals_nasdaq100_cap0_atr1trend-blackdot-bluedot.csv` — confirmed
this file exists and has today's timestamp. The check's hardcoded path
predates the fix.

**Why it still passes:** an old, unsuffixed
`timing_signals_nasdaq100_cap0.csv` is left over on disk from before the
cache-key fix. The check finds *that* file and reports success — it
isn't verifying that *today's* run produced the *correct* file under the
current naming scheme. If the file-naming logic broke again tomorrow,
this check would keep silently passing off the same stale artifact.

**Fix:**
1. Build the expected filename the same way `dashboard.py` does (base
   scope key + sorted/joined source suffix), not a hardcoded string — so
   the check breaks loudly if the naming convention changes again instead
   of silently passing on a leftover file.
2. Delete the stale unsuffixed `timing_signals_nasdaq100_cap0.csv`
   artifact from `results/2026-08-25/` (and check for similar leftovers
   from before the GLB fix — e.g. old `patterns_glb_*` cache files keyed
   without `lookback_choice` — so nothing else is accidentally passing
   off pre-fix output).

## Gap 2: no persisted regression test for either cache-key fix

Both fixes were verified manually during the fix session (checking hash
values, distinct filenames, timing numbers) but nothing was added to
`test_dashboard_app.py` that asserts this behavior going forward. Add:

- **GLB**: run with Lookback=1y, then Lookback=2y (same scope/pivot/
  confirmation) → assert the two `pt_file_key` values differ, and that a
  third run with Lookback=1y again reuses the *first* run's cache (not
  the second's) — i.e. the key is a pure function of the actual settings,
  not just "changed vs. didn't change since last click."
- **Timing**: run with `sources=['Blue Dot']`, then
  `sources=['ATR1 Trend']` (same scope) → assert the two `ts_key`/
  persisted-filenames differ, and neither run's results leak into the
  other's cached file.

Same rigor as the existing behavioral checks elsewhere in this suite —
this is exactly the kind of check that would have caught both bugs
before they needed a manual review round to surface.

## Definition of done

- [ ] `test_dashboard_app.py`'s persistence check computes the expected
      filename from the same key-construction logic as `dashboard.py`,
      not a hardcoded pre-fix string
- [ ] Stale pre-fix result/cache artifacts in `results/2026-08-25/`
      (and `results/glb_cache/` if applicable) identified and removed
- [ ] Regression test added for the GLB lookback-key fix (distinct keys
      per lookback choice, correct cache reuse when a setting repeats)
- [ ] Regression test added for the Timing sources-key fix (distinct
      keys per source selection, no cross-contamination between them)
- [ ] Full `validate.py` + `test_dashboard_app.py` still green after
      removing the stale artifacts (confirms nothing else was quietly
      depending on them)

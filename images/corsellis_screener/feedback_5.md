# Feedback round 5 — GLB Patterns tab: Lookback period excluded from the same-day cache key

Found while explaining to the user how the Patterns tab's caching works —
not caught by the existing test suites, since neither `validate.py` nor
`test_dashboard_app.py`'s GLB checks vary the Lookback period between two
runs in the same session. Confirmed by reading the code directly, not by
reproducing it live.

## The bug

`dashboard.py`'s Patterns tab (`~:846-920`, GLB branch) computes the
same-day results-cache key **before** `lookback_bars` is known:

```python
pt_params['pivot_strength'] = g1.slider(...)
_lb_choice = g2.selectbox('Lookback period', ['3m', '6m', '1y', '2y', 'complete'], ...)
pt_params['confirmation_bars'] = {...}[_conf]
...
pt_ph = hashlib.md5(str(sorted(pt_params.items())).encode()).hexdigest()[:8]
pt_file_key = f'glb_{pt_key}_{pt_ph}'              # ← hashed here — pt_params has
                                                    #   only pivot_strength + confirmation_bars
...
if pt_run:
    ...
    pt_params['lookback_bars'] = ...               # ← added here, AFTER the hash,
                                                    #   inside the button-click branch
    pt_df = glb.evaluate(tickers, data_pt, pt_params)
```

`lookback_bars` is deliberately resolved late (it needs `data_pt` loaded
to handle `'complete'` and to cap the choice to available history — see
the `_lbs = len(data_pt.get('close', ...))` logic right above it) — but
the cache-key hash is computed *before* that point, so it never includes
the Lookback selection at all. The hash only ever covers `pivot_strength`
and `confirmation_bars`.

**Consequence:** run GLB today with Lookback = 1y, then change *only*
the Lookback dropdown to 2y (same scope, same pivot strength, same
confirmation period) and click Run again. `pt_file_key` is identical to
the first run, so `on_demand.load_cached(...)` finds the earlier
same-day CSV and returns it — the app shows the **1-year-lookback
results again**, silently, under the message *"Reused today's cached
run for this scope+parameters"*, which is actively wrong in this case
since a parameter did change. No error, no warning — looks like a
completed 2y run.

Contrast with the **other** cache layer, the per-ticker incremental
cache (`results/glb_cache/{ticker}.json`) — that one is correct, its
`params_hash` includes `lookback_bars` explicitly, confirmed by
inspecting a cache file directly. This bug is isolated to the
higher-level same-day scoped-results cache key in `dashboard.py`, not
`src/patterns/glb.py`.

## Fix

Include the lookback *selection* in the hashed dict before computing
`pt_ph`, not the resolved bar count (which isn't known yet at that
point). The string choice is sufficient and already available:

```python
pt_params['pivot_strength'] = g1.slider(...)
_lb_choice = g2.selectbox('Lookback period', [...], key='pt_glb_lookback')
pt_params['confirmation_bars'] = {...}[_conf]
pt_params['lookback_choice'] = _lb_choice          # ← add this before hashing
...
pt_ph = hashlib.md5(str(sorted(pt_params.items())).encode()).hexdigest()[:8]
```

(`lookback_choice` is just for the hash's benefit — keep passing the
resolved `lookback_bars` integer to `glb.evaluate()` as before, don't
change what the module itself receives.) Same class of bug is worth
double-checking on the Cup & Handle branch too — confirm `pt_preset`
(`strict`/`default`/`loose`) is actually part of *its* `pt_file_key`
before assuming it's fine (`pt_file_key = f'cup_handle_{pt_key}_{pt_preset}'`
looked correct on a first read — `pt_preset` is directly in the f-string,
not hashed-then-appended-late like GLB's lookback — but worth a
deliberate look given this exact class of bug just showed up next door).

## Definition of done

- [ ] `lookback_choice` (or equivalent) included in the GLB cache-key
      hash, computed before `pt_ph` — verified by hashing changing when
      only the Lookback dropdown changes
- [ ] Regression test added: run GLB with Lookback=1y, then Lookback=2y
      (same scope/pivot/confirmation), assert the two `pt_file_key`
      values differ and the second run's results actually reflect the
      2y window — add to `test_dashboard_app.py`'s Patterns checks,
      same rigor as the existing behavioral checks (this is precisely
      the kind of thing a shape-only check wouldn't catch)
- [ ] Cup & Handle's `pt_preset` inclusion in its own file key
      double-checked, not just assumed correct by inspection
- [ ] Full `validate.py` + `test_dashboard_app.py` still green

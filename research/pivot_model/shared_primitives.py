"""
Prototype: compute GLB records for MULTIPLE (pivot_strength, lookback_bars,
confirmation_bars) scenarios sharing one O(n) pass per DISTINCT parameter
value, instead of one full O(n) pass per scenario.

Mirrors src/patterns/glb.py's cold-path logic (_pivot_mask, _rolling_max,
_compute_records) exactly — this file must produce byte-identical records
to glb.py for any single scenario. See README.md for the nesting argument
that makes the sharing valid rather than approximate.

Self-contained (no dependency on src/patterns/glb.py) so it can be read and
timed in isolation; validate_against_glb.py cross-checks it against the
real module.
"""
import numpy as np
import pandas as pd


def _rolling_max(a: np.ndarray, w: int) -> np.ndarray:
    """Trailing-window max (incl. current), NaN-padded head. Same as glb.py."""
    s = pd.Series(a)
    return s.rolling(w, min_periods=w).max().to_numpy()


def _rolling_forward_max(a: np.ndarray, w: int) -> np.ndarray:
    """
    fwd[p] = max(a[p+1 .. p+w]) inclusive, i.e. exactly `w` bars strictly
    after p (matches glb.py's `highs[p+1:conf_end]` where conf_end=p+w+1,
    a slice of `w` elements — glb.py itself calls this with w=conf-1
    since its own conf_end=min(p+conf, n) makes the slice p+1..p+conf-1).
    NaN where the window runs past the end of the array. Array-lookup
    replacement for glb.py's per-pivot `np.max(highs[p+1:conf_end])` slice
    call inside its Python loop — same rolling-max nesting argument
    applies to confirmation length as to lookback length.
    """
    if w < 1:
        return np.full(len(a), np.nan)
    s = pd.Series(a)
    # rolling(w) window ending at index i inclusive = [i-w+1, i];
    # shift(-w) moves that window's right edge from i to i+w, i.e.
    # result[p] = max(a[p+1-w+w-1+1 .. ]) -- verified directly below by
    # construction: rolling(w).max() at position i+w covers [i+1, i+w].
    fwd = s.rolling(w, min_periods=w).max().shift(-w).to_numpy()
    return fwd


def _pivot_mask(highs: np.ndarray, strength: int) -> np.ndarray:
    """Verbatim copy of glb.py's _pivot_mask."""
    n = len(highs)
    mask = np.zeros(n, dtype=bool)
    if n < 2 * strength + 1:
        return mask
    s = pd.Series(highs)
    left_max = s.rolling(strength, min_periods=strength).max().shift(1).to_numpy()
    right_max = s.rolling(strength, min_periods=strength).max() \
        .shift(-strength).to_numpy()
    with np.errstate(invalid='ignore'):
        mask = (highs > left_max) & (highs >= right_max)
    mask[:strength] = False
    mask[n - strength:] = False
    return mask


def _records_for_scenario(highs, closes, dates, pmask, lookback_max,
                          fwd_conf_max, conf, require_conf, start_bar):
    """Same record-building logic as glb.py's _compute_records cold path
    (existing=[]), but pmask/lookback_max/fwd_conf_max are passed in
    (shared, precomputed) instead of recomputed per call."""
    n = len(highs)
    s_strength = start_bar  # caller already applied max(pivot_strength, ...)
    new_pivots = [p for p in range(s_strength, n)
                  if pmask[p] and highs[p] >= lookback_max[p]]

    records = []
    for p in new_pivots:
        level = float(highs[p])
        conf_end = min(p + conf, n)
        is_conf = True
        if require_conf and conf_end > p + 1:
            fm = fwd_conf_max[p]
            is_conf = bool(fm <= level) if not np.isnan(fm) else \
                bool(np.max(highs[p + 1:conf_end]) <= level)
        if require_conf and not is_conf:
            continue
        scan_from = min(p + conf, n)
        broken_idx = None
        if scan_from < n:
            above = np.flatnonzero(closes[scan_from:] > level)
            if len(above):
                broken_idx = scan_from + int(above[0])
        records.append({
            'level': level,
            'detection_date': dates[p],
            'breakout_date': dates[broken_idx] if broken_idx is not None else None,
            'is_confirmed': bool(is_conf),
            'is_broken': broken_idx is not None,
        })
    return records


def compute_glb_multi(highs: np.ndarray, closes: np.ndarray, dates: list,
                      scenarios: dict) -> dict:
    """
    scenarios: {name: {'pivot_strength', 'lookback_bars',
                       'confirmation_bars', 'require_confirmation'}}

    Returns {name: [records...]} — cold-path only (mirrors glb.py's
    _compute_records with existing=[], start_bar=pivot_strength), i.e. a
    full historical scan, not the incremental-cache path. That's
    orthogonal here: the point is eliminating redundant work ACROSS
    scenarios, not across time.
    """
    n = len(highs)

    pmask_cache: dict[int, np.ndarray] = {}
    lookback_cache: dict[int, np.ndarray] = {}
    fwdconf_cache: dict[int, np.ndarray] = {}

    out = {}
    for name, p in scenarios.items():
        s = p['pivot_strength']
        lb = p['lookback_bars']
        conf = p['confirmation_bars']
        require_conf = p['require_confirmation']

        if s not in pmask_cache:
            pmask_cache[s] = _pivot_mask(highs, s)
        if lb not in lookback_cache:
            lookback_cache[lb] = _rolling_max(highs, lb)
        if conf not in fwdconf_cache:
            # glb.py's own confirmation slice is highs[p+1 : p+conf] (conf-1
            # bars) — see _rolling_forward_max's docstring.
            fwdconf_cache[conf] = _rolling_forward_max(highs, conf - 1)

        start_bar = s  # cold path: scan from pivot_strength, like glb.py's
                       # max(p['pivot_strength'], len(highs)-historical_bars)
                       # with historical_bars >= len(highs) here
        out[name] = _records_for_scenario(
            highs, closes, dates,
            pmask_cache[s], lookback_cache[lb], fwdconf_cache[conf],
            conf, require_conf, start_bar)

    stats = {
        'distinct_pivot_strengths': len(pmask_cache),
        'distinct_lookbacks': len(lookback_cache),
        'distinct_confirmations': len(fwdconf_cache),
        'scenarios': len(scenarios),
    }
    return out, stats

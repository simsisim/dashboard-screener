"""
Empirical check: do cup_handle.py's 3 presets' extrema NEST the way GLB's
pivot_strength does? (README.md flagged this as unproven — scipy's
find_peaks prominence+distance suppression isn't a simple rolling-max, so
unlike GLB it needs checking on real data rather than assuming it.)

Nesting would mean: peaks(strict) subset-of peaks(default) subset-of
peaks(loose), and same for troughs — since strict has the largest
prominence_threshold/distance_threshold (0.05/5) and loose the smallest
(0.005/1). If true, the same "compute once at the loosest setting, filter
down for stricter presets" trick from GLB would apply here too, instead of
calling find_peaks 3x per ticker.

Run: python3 research/pivot_model/check_cup_handle_nesting.py
"""
import random
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

import config  # noqa: E402
from src.patterns.cup_handle import _find_extrema  # noqa: E402

DATA_ROOT = config.DOWNLOAD_ROOT / 'data' / 'market_data' / 'daily'
UNIVERSE_DIR = ROOT / 'results' / 'glb_cache'

PRESET_ORDER = ['strict', 'default', 'loose']  # strictest -> loosest


def load_close(t: str):
    parts = []
    for sub in ('archive', 'current'):
        p = DATA_ROOT / sub / f'{t}.csv'
        if p.exists():
            parts.append(pd.read_csv(p, low_memory=False))
    if not parts:
        return None
    df = pd.concat(parts).drop_duplicates(subset='Date').sort_values('Date')
    close = pd.to_numeric(df['Close'], errors='coerce').dropna().to_numpy(float)
    return close


def peaks_troughs_for(close, preset_name):
    p = config.CUPHANDLE_PRESETS[preset_name]
    return _find_extrema(close, p['prominence_threshold'], p['distance_threshold'])


def near_match(idx: int, other: np.ndarray, tol: int) -> bool:
    if len(other) == 0:
        return False
    return bool(np.min(np.abs(other - idx)) <= tol)


def check_ticker(t: str, close: np.ndarray, tol: int = 2):
    """Returns per-pair (strict->default, default->loose, strict->loose)
    exact-subset and near-subset (within tol bars) violation counts, for
    both peaks and troughs."""
    extrema = {name: peaks_troughs_for(close, name) for name in PRESET_ORDER}
    results = {}
    pairs = [('strict', 'default'), ('default', 'loose'), ('strict', 'loose')]
    for tighter, looser in pairs:
        for kind, k_idx in (('peaks', 0), ('troughs', 1)):
            a = extrema[tighter][k_idx]
            b = extrema[looser][k_idx]
            exact_missing = [int(x) for x in a if x not in set(b)]
            near_missing = [int(x) for x in exact_missing
                           if not near_match(x, b, tol)]
            results[(tighter, looser, kind)] = {
                'n_tighter': len(a),
                'n_looser': len(b),
                'exact_missing': len(exact_missing),
                'near_missing': len(near_missing),
                'near_missing_examples': near_missing[:3],
            }
    return results


def main():
    random.seed(0)
    tickers = sorted(p.stem for p in UNIVERSE_DIR.glob('*.json'))
    sample = random.sample(tickers, min(60, len(tickers)))

    pairs = [('strict', 'default'), ('default', 'loose'), ('strict', 'loose')]
    totals = {(t, l, k): {'n_tighter': 0, 'exact_missing': 0, 'near_missing': 0}
             for t, l in pairs for k in ('peaks', 'troughs')}
    tickers_checked = 0
    tickers_with_exact_violation = set()
    tickers_with_near_violation = set()
    example_violations = []

    for t in sample:
        close = load_close(t)
        if close is None or len(close) < 60:
            continue
        tickers_checked += 1
        res = check_ticker(t, close)
        any_exact = False
        any_near = False
        for key, r in res.items():
            totals[key]['n_tighter'] += r['n_tighter']
            totals[key]['exact_missing'] += r['exact_missing']
            totals[key]['near_missing'] += r['near_missing']
            if r['exact_missing'] > 0:
                any_exact = True
            if r['near_missing'] > 0:
                any_near = True
                if len(example_violations) < 8:
                    example_violations.append((t, key, r))
        if any_exact:
            tickers_with_exact_violation.add(t)
        if any_near:
            tickers_with_near_violation.add(t)

    print(f'Tickers checked: {tickers_checked}')
    print()
    print('Per pair/kind (pooled across all tickers):')
    for key, agg in totals.items():
        tighter, looser, kind = key
        n = agg['n_tighter']
        pct_exact = 100 * agg['exact_missing'] / n if n else 0.0
        pct_near = 100 * agg['near_missing'] / n if n else 0.0
        print(f'  {tighter:8s} -> {looser:8s} [{kind:8s}]: '
             f'{n:5d} {tighter} points, '
             f'{agg["exact_missing"]:4d} not exactly in {looser} '
             f'({pct_exact:5.1f}%), '
             f'{agg["near_missing"]:4d} still missing within 2 bars '
             f'({pct_near:5.1f}%)')
    print()
    print(f'Tickers with >=1 exact-index violation: '
         f'{len(tickers_with_exact_violation)}/{tickers_checked}')
    print(f'Tickers with >=1 violation even allowing +/-2 bars: '
         f'{len(tickers_with_near_violation)}/{tickers_checked}')
    print()
    if example_violations:
        print('Example near-violations (tighter point genuinely absent '
             'from looser set, not just index-shifted):')
        for t, key, r in example_violations:
            print(f'  {t} {key}: {r}')
    else:
        print('No near-violations found — nesting holds within +/-2 bars '
             'on this sample.')


if __name__ == '__main__':
    main()

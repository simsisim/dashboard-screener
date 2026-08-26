"""
Validate + benchmark the shared-primitive multi-scenario GLB engine
(shared_primitives.compute_glb_multi) against today's src/patterns/glb.py.

Correctness check: for each of the 3 named dashboard scenarios, the shared
engine's records must be byte-identical (level, detection_date,
breakout_date, is_confirmed, is_broken) to what glb.py's own cold-path
_compute_records produces for that scenario in isolation.

Speed check: wall-clock for "3 independent full passes" (today's approach)
vs "1 shared pass producing all 3" (this prototype), on real daily OHLCV.

Run: python3 research/pivot_model/validate_against_glb.py
"""
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import config  # noqa: E402
from src.patterns import glb  # noqa: E402
from shared_primitives import compute_glb_multi  # noqa: E402

DATA_ROOT = config.DOWNLOAD_ROOT / 'data' / 'market_data' / 'daily'
DATA_DIR = DATA_ROOT / 'current'  # existence-check only; load_ticker reads both

TICKERS = ['AAPL', 'MSFT', 'NVDA', 'AMZN', 'GOOGL', 'META', 'JPM', 'XOM',
          'UNH', 'HD']

# 3 named scenarios from the conversation: (lookback, confirmation) in
# trading days, pivot_strength held at config's default across all 3.
SCENARIOS = {
    'a_3m_2w':  {'pivot_strength': config.GLB_PIVOT_STRENGTH,
                'lookback_bars': 63, 'confirmation_bars': 10,
                'require_confirmation': True},
    'b_6m_1m':  {'pivot_strength': config.GLB_PIVOT_STRENGTH,
                'lookback_bars': 126, 'confirmation_bars': 21,
                'require_confirmation': True},
    'c_1_2y_3m': {'pivot_strength': config.GLB_PIVOT_STRENGTH,
                 'lookback_bars': 252, 'confirmation_bars': 63,
                 'require_confirmation': True},
}


def load_ticker(t: str):
    parts = []
    for sub in ('archive', 'current'):
        p = DATA_ROOT / sub / f'{t}.csv'
        if p.exists():
            parts.append(pd.read_csv(p, low_memory=False))
    df = pd.concat(parts).drop_duplicates(subset='Date').sort_values('Date')
    df['Date'] = pd.to_datetime(df['Date'], utc=True, errors='coerce')
    df = df.dropna(subset=['Date'])
    highs = df['High'].to_numpy(float)
    closes = df['Close'].to_numpy(float)
    dates = [d.strftime('%Y-%m-%d') for d in df['Date'].dt.tz_localize(None)]
    return highs, closes, dates


def records_equal(a: list, b: list) -> bool:
    if len(a) != len(b):
        return False
    for ra, rb in zip(a, b):
        if ra['detection_date'] != rb['detection_date']:
            return False
        if abs(ra['level'] - rb['level']) > 1e-6:
            return False
        if ra['breakout_date'] != rb['breakout_date']:
            return False
        if ra['is_confirmed'] != rb['is_confirmed']:
            return False
        if ra['is_broken'] != rb['is_broken']:
            return False
    return True


def baseline_per_scenario(highs, closes, dates):
    """Today's approach: one independent full cold pass per scenario."""
    out = {}
    for name, p in SCENARIOS.items():
        start_bar = p['pivot_strength']
        out[name] = glb._compute_records(highs, closes, dates, p,
                                         start_bar, [])
    return out


def main():
    all_match = True
    total_baseline_t = 0.0
    total_shared_t = 0.0
    total_stats = None

    for t in TICKERS:
        path = DATA_DIR / f'{t}.csv'
        if not path.exists():
            print(f'{t}: no data file, skipping')
            continue
        highs, closes, dates = load_ticker(t)
        if len(highs) < config.GLB_MIN_DATA_POINTS:
            print(f'{t}: not enough data ({len(highs)} bars), skipping')
            continue

        t0 = time.perf_counter()
        baseline = baseline_per_scenario(highs, closes, dates)
        t1 = time.perf_counter()
        shared, stats = compute_glb_multi(highs, closes, dates, SCENARIOS)
        t2 = time.perf_counter()

        total_baseline_t += (t1 - t0)
        total_shared_t += (t2 - t1)
        total_stats = stats

        match = all(records_equal(baseline[name], shared[name])
                   for name in SCENARIOS)
        all_match &= match
        counts = {name: len(shared[name]) for name in SCENARIOS}
        print(f'{t}: {len(highs)} bars, records={counts}, '
             f'match={"OK" if match else "MISMATCH"}')

    print()
    print(f'All tickers/scenarios match: {"YES" if all_match else "NO"}')
    print(f'Per-scenario dedup (last ticker): {total_stats}')
    print(f'Baseline (3 independent passes), total: {total_baseline_t*1000:.2f} ms')
    print(f'Shared engine (1 pass, all 3),   total: {total_shared_t*1000:.2f} ms')
    if total_shared_t > 0:
        print(f'Speedup: {total_baseline_t/total_shared_t:.2f}x')


if __name__ == '__main__':
    main()

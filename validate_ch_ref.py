"""Cup & Handle reference check — run by validate.py in an isolated
subprocess. Uses patterns_v0's own CupHandleDetector (daily config) so
this project's cup_handle.py 'loose' preset can be compared against it."""
import json
import sys

import pandas as pd

import types
import importlib
_pv0 = types.ModuleType('pv0')   # synthetic package: patterns_v0/src has
_pv0.__path__ = ['/home/imagda/_invest2024/python/patterns_v0/src']  # no __init__
sys.modules['pv0'] = _pv0
CupHandleConfig = importlib.import_module('pv0.cup_handle_config').CupHandleConfig
CupHandleDetector = importlib.import_module('pv0.cup_handle_detector').CupHandleDetector

CUR = '/home/imagda/_invest2024/python/downloadData_v1/data/market_data/daily/current'
ARCH = '/home/imagda/_invest2024/python/downloadData_v1/data/market_data/daily/archive'


def build_synthetic():
    import numpy as np
    n = 170
    idx = pd.date_range('2025-01-01', periods=n, freq='B')
    # seg0 rises 72 -> 100: a >= 30% prior advance into the left rim, so the
    # §16 Task A setup-gain gate (strict 30%) is satisfied on this fixture.
    segs = [np.linspace(72, 100, 56),
            np.concatenate([np.linspace(100, 92.5, 7),
                            np.linspace(92.5, 103, 13)]),
            np.linspace(103, 82.4, 31),
            np.linspace(82.4, 102.5, 27),
            np.linspace(102.5, 96.8, 8),
            np.linspace(96.8, 112, 31)]
    close = np.concatenate(segs)[:n]
    rng = np.random.default_rng(42)
    close = np.maximum(close + rng.normal(0, 0.25, n).cumsum() * 0.08, 1)
    df = pd.DataFrame({'Open': close, 'High': close * 1.002,
                       'Low': close * 0.998, 'Close': close,
                       'Volume': rng.integers(1e6, 2e6, n)}, index=idx)
    return {'SYN': df}


def main():
    cfg = CupHandleConfig()
    det = CupHandleDetector(cfg, timeframe='daily')
    out = {}
    if '--synthetic' in sys.argv:
        data = build_synthetic()
        r = det.detect_pattern(data['SYN'], 'SYN')
        out['SYN'] = {'found': bool(r.get('pattern_found', False)),
                      'quality': r.get('quality_score'),
                      'stage': r.get('pattern_stage'),
                      'cup_depth': r.get('cup_depth_pct'),
                      'handle_depth': r.get('handle_depth_pct')}
        print(json.dumps(out))
        return
    for t in ['AAPL', 'MSFT', 'QMCO', 'NVDA']:
        parts = []
        for base in (ARCH, CUR):
            try:
                parts.append(pd.read_csv(f'{base}/{t}.csv', low_memory=False))
            except FileNotFoundError:
                pass
        df = pd.concat(parts).drop_duplicates(subset='Date').sort_values('Date')
        df['Date'] = pd.to_datetime(df['Date'], utc=True, errors='coerce')
        df = df.dropna(subset=['Date'])
        df['Date'] = df['Date'].dt.tz_localize(None).dt.normalize()
        df = df.set_index('Date')[['Open', 'High', 'Low', 'Close', 'Volume']]
        df = df.apply(pd.to_numeric, errors='coerce').dropna()
        r = det.detect_pattern(df, t)
        out[t] = {'found': bool(r.get('pattern_found', False)),
                  'quality': r.get('quality_score'),
                  'stage': r.get('pattern_stage'),
                  'cup_depth': r.get('cup_depth_pct'),
                  'handle_depth': r.get('handle_depth_pct')}
    print(json.dumps(out))


if __name__ == '__main__':
    main()

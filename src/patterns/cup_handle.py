"""
Pattern detector — Cup & Handle, K-A-B-C-D methodology (feedback_4.md
Task 6).

Source: patterns_v0/src/cup_handle_detector.py (486 ln) +
peak_trough_detector.py (scipy.signal.find_peaks) + cup_handle_config.py
(CSV thresholds). K = prior trend start, A = left rim, B = cup bottom,
C = right rim, D = handle bottom.

THREE PARAMETER PRESETS (config.CUPHANDLE_PRESETS — feedback_4.md's
architecture note: the pattern's parameters are exploratory, so don't bake
in one fixed set; Strict = the real O'Neil-style definition, Loose =
patterns_v0's tuned daily config, explicitly labeled permissive):
  each preset produces its own column set suffixed _{preset}:
  in_cup_handle_{preset}, cup_handle_stage_{preset}
  (forming/breakout/complete), cup_handle_quality_score_{preset} (0-100),
  cup_depth_pct_{preset}, handle_depth_pct_{preset},
  cup_handle_target_price_{preset}, cup_handle_stop_loss_{preset}

Deviations from the source (documented):
  - pattern_formation_cutoff_date (display filter) not ported — all
    patterns are reported with their dates/stages instead of dropped
  - the source's detect_pattern tries only the FIRST constructible
    K-A-B-C-D candidate (earliest valid trough) — ported faithfully

On-demand module: explicit ticker list; NOT in the daily batch. Each row
carries `as_of` (its own last valid bar date).
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.signal import find_peaks

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
import config


def _find_extrema(close: np.ndarray, prominence_threshold: float,
                  distance: int):
    """peak_trough_detector.find_extrema — prominence as % of mean price."""
    if len(close) < distance * 2:
        return np.array([], dtype=int), np.array([], dtype=int)
    prom = np.mean(close) * prominence_threshold
    peaks, _ = find_peaks(close, prominence=prom, distance=distance)
    troughs, _ = find_peaks(-close, prominence=prom, distance=distance)
    return peaks, troughs


def _find_pattern_points(close: np.ndarray, peaks: np.ndarray,
                         troughs: np.ndarray):
    """Source _find_pattern_points — first constructible K-A-B-C-D."""
    if len(peaks) < 2 or len(troughs) < 2:
        return None
    for trough_idx in troughs:
        left_peaks = peaks[peaks < trough_idx]
        right_peaks = peaks[peaks > trough_idx]
        if len(left_peaks) == 0 or len(right_peaks) == 0:
            continue
        a_idx = left_peaks[-1]
        c_idx = right_peaks[0]
        b_idx = trough_idx
        earlier = peaks[peaks < a_idx]
        if len(earlier) == 0:
            continue
        k_idx = earlier[-1]
        later = troughs[troughs > c_idx]
        d_idx = later[0] if len(later) else len(close) - 1
        return {'k': k_idx, 'a': a_idx, 'b': b_idx, 'c': c_idx, 'd': d_idx}
    return None


def _evaluate_preset(close: np.ndarray, volume: np.ndarray,
                     params: dict) -> dict:
    """Full detect_pattern flow for one parameter preset."""
    n = len(close)
    base = {'found': False, 'stage': None, 'quality': np.nan,
            'cup_depth_pct': np.nan, 'handle_depth_pct': np.nan,
            'target': np.nan, 'stop': np.nan}

    peaks, troughs = _find_extrema(close, params['prominence_threshold'],
                                   params['distance_threshold'])
    if len(peaks) < 2 or len(troughs) < 1:
        return base
    pts = _find_pattern_points(close, peaks, troughs)
    if pts is None:
        return base
    k, a, b, c, d = (pts[x] for x in ('k', 'a', 'b', 'c', 'd'))
    # basic structure: ordered, B below both rims
    if not (k < a < b < c <= d):
        return base
    if close[b] >= close[a] or close[b] >= close[c]:
        return base

    cup_depth = (close[a] - close[b]) / close[a]
    if not (params['cup_min_depth_pct'] <= cup_depth
            <= params['cup_max_depth_pct']):
        return base
    cup_duration = c - a
    if not (params['cup_min_duration'] <= cup_duration
            <= params['cup_max_duration']):
        return base
    rim_sym = abs(close[a] - close[c]) / close[a]
    if rim_sym > params['cup_depth_tolerance']:
        return base

    # U-shape check: max 1 inner peak, and it must stay below the cup's
    # halfway line (source: max_inner_peak > b + 0.5*(a-b) -> V-shape)
    cup_slice = close[a:c + 1]
    inner_peaks, _ = find_peaks(cup_slice,
                                prominence=np.mean(close) *
                                params['prominence_threshold'],
                                distance=params['distance_threshold'])
    if len(inner_peaks) > 1:
        max_inner = cup_slice[inner_peaks].max()
        if max_inner > close[b] + (close[a] - close[b]) * 0.5:
            return base

    # handle
    cup_height = close[a] - close[b]
    handle_depth = (close[c] - close[d]) / cup_height
    handle_duration = d - c
    handle_position = max(0.0, (close[d] - close[b]) / cup_height)
    if handle_position < params['handle_position_min']:
        return base
    if handle_depth > params['handle_max_depth_pct']:
        return base
    if not (params['handle_min_duration'] <= handle_duration
            <= params['handle_max_duration']):
        return base

    # volume pattern
    vol_ma = pd.Series(volume).rolling(
        int(params['volume_ma_period'])).mean().to_numpy()
    cup_vol = volume[a:c + 1].mean()
    _ma_window = vol_ma[a:c + 1]
    vol_ma_during = np.nanmean(_ma_window) if np.size(_ma_window) else np.nan
    decline_confirmed = cup_vol < vol_ma_during * \
        params['volume_decline_threshold']
    breakout_ratio = None
    if n - 1 > d:
        recent = volume[-5:].mean()
        breakout_ratio = recent / vol_ma_during if vol_ma_during else None

    # quality score (source _calculate_quality_score, verbatim)
    score = 0.0
    score += max(0, 15 - abs(cup_depth - 0.225) * 100)
    score += max(0, 15 - rim_sym * 500)
    dur_ratio = cup_duration / params['cup_max_duration']
    score += max(0, 10 * (1 - abs(dur_ratio - 0.5) * 2))
    score += handle_position * 15
    score += max(0, 15 - handle_depth * 60)
    if decline_confirmed:
        score += 20
    if breakout_ratio and breakout_ratio > params['breakout_volume_factor']:
        score += 10
    score = min(100.0, max(0.0, score))

    # stage / target / stop
    resistance = max(close[a], close[c])
    if n - 1 <= d:
        stage = 'forming'
    elif close[-1] > resistance:
        stage = 'breakout'
    else:
        stage = 'complete'
    target = resistance + (close[a] - close[b])
    stop = min(close[d], close[b]) * 0.95

    return {'found': True, 'stage': stage, 'quality': round(score, 1),
            'cup_depth_pct': round(cup_depth * 100, 2),
            'handle_depth_pct': round(handle_depth * 100, 2),
            'target': round(target, 3), 'stop': round(stop, 3)}


def evaluate(tickers: list, data: dict,
             presets: list | None = None) -> pd.DataFrame:
    """
    tickers: scoped subset (explicit argument — on-demand architecture).
    data: wide OHLCV matrices restricted to the scoped tickers.
    presets: which parameter presets to compute (default: all three).
    """
    wanted = presets or list(config.CUPHANDLE_PRESETS)
    tickers = [t for t in tickers if t in data['close'].columns]
    close_all = data['close'][tickers]
    vol_all = data['volume'][tickers]

    rows = []
    for t in tickers:
        c_ser = close_all[t].dropna()
        v_ser = vol_all[t].reindex(c_ser.index)
        row = {'ticker': t, 'as_of': None}
        for preset in wanted:
            suffix = f'_{preset}'
            row[f'in_cup_handle{suffix}'] = False
            row[f'cup_handle_stage{suffix}'] = None
            row[f'cup_handle_quality_score{suffix}'] = np.nan
            row[f'cup_depth_pct{suffix}'] = np.nan
            row[f'handle_depth_pct{suffix}'] = np.nan
            row[f'cup_handle_target_price{suffix}'] = np.nan
            row[f'cup_handle_stop_loss{suffix}'] = np.nan
        if len(c_ser) >= 20:
            # per-preset compute (parameters change the extrema themselves)
            for preset in wanted:
                r = _evaluate_preset(c_ser.to_numpy(float),
                                     v_ser.to_numpy(float),
                                     config.CUPHANDLE_PRESETS[preset])
                sfx = f'_{preset}'
                row[f'in_cup_handle{sfx}'] = r['found']
                row[f'cup_handle_stage{sfx}'] = r['stage']
                row[f'cup_handle_quality_score{sfx}'] = r['quality']
                row[f'cup_depth_pct{sfx}'] = r['cup_depth_pct']
                row[f'handle_depth_pct{sfx}'] = r['handle_depth_pct']
                row[f'cup_handle_target_price{sfx}'] = r['target']
                row[f'cup_handle_stop_loss{sfx}'] = r['stop']
            last_valid = c_ser.last_valid_index()
            row['as_of'] = last_valid.strftime('%Y-%m-%d') \
                if last_valid is not None else None
        rows.append(row)

    out = pd.DataFrame(rows).set_index('ticker')
    out.index.name = 'ticker'
    return out

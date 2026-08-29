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

§16 breakoutwatch.com alignment (IMPLEMENTATION_PLAN §16; digest in
cup_handle_ideas/cupAndHandle/lit/breakoutwatch_methodology.md). The
kanwalpreet18 geometric core (find_peaks -> first constructible K-A-B-C-D
-> cup/handle validations -> quality score -> stage/target/stop) is
unchanged; these were grafted on, all NON-BINDING for the Loose preset so
it stays identical to patterns_v0's daily config:
  A  setup-gain gate       config setup_gain_min — prior advance into the
                           left rim (O'Neil "prior uptrend >= 30%"); prior
                           low = min over config.CUPHANDLE_SETUP_LOOKBACK
                           bars before the left rim
  B  pivot-recency cap      config pivot_max_age — bars from the right rim
                           (breakoutwatch "pivot" = handle start) to now
  C  cup:handle length      config cup_handle_ratio_min (breakoutwatch >= 3)
  D  handle-midpoint rule    config handle_midpoint_rule — mid-handle >=
                           mid-base (breakoutwatch handle rule)
  E  HQ handle volume score  cup_handle_hq_{preset} — breakoutwatch Handle
                           Quality 2x2 (price down + volume down = best),
                           recency-weighted; folded into quality score
  F  RCQ right-side score    cup_handle_rcq_{preset} — breakoutwatch Right
                           Cup Quality (up day on above-avg volume = demand),
                           recency-weighted; folded into quality score
     CQ chart quality        cup_handle_cq_{preset} — breakoutwatch Chart
                           Quality: RCQ + HQ blended, weight shifting toward
                           HQ as the handle lengthens. REPORT-ONLY: not a
                           gate, not in the quality score. RCQ/HQ are
                           pattern-window metrics (scored over B->C and
                           C->D), so CQ is meaningful only where a pattern
                           was found. The stock-level CANTATA (CE/CET/CEF)
                           scores are a SEPARATE, non-pattern concern — see
                           research/breakoutwatch_ce_mapping.md.
  G  volume-confirmed b/o    cup_handle_breakout_vol_confirmed_{preset} —
                           latest volume >= breakout_volume_factor x vol MA
  H  intraday extremes       config use_intraday_extremes — rims off the
                           daily HIGH, bottoms off the daily LOW (the
                           intraday extreme of each bar; NOT sub-daily data).
                           Falls back to close when high/low not supplied.
  I  outcome-trained ranker  NOT DONE — needs logged pattern outcomes; the
                           quality score stays hand-weighted until then.
New columns per preset: cup_handle_setup_gain_pct, cup_handle_days_since_rim,
cup_handle_ratio, cup_handle_hq, cup_handle_rcq, cup_handle_cq,
cup_handle_breakout_vol_confirmed.

Deviations from the source (documented):
  - pattern_formation_cutoff_date (display filter) not ported — all
    patterns are reported with their dates/stages instead of dropped
  - the source's detect_pattern tries only the FIRST constructible
    K-A-B-C-D candidate (earliest valid trough). Kept for the Loose preset
    (candidate_selection='first'); Strict/Default use 'recent' — scan every
    candidate, return the freshest that passes — so §16 Task B's recency
    cap surfaces a current cup instead of nulling out on an ancient one.

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


def _all_pattern_points(close: np.ndarray, peaks: np.ndarray,
                        troughs: np.ndarray) -> list:
    """All constructible K-A-B-C-D candidates, in trough order (earliest
    first). Source _find_pattern_points built exactly ONE (the first); §16
    Task B's recency cap is useless with only the earliest candidate on a
    multi-year history, so this returns every candidate and the caller picks
    per the preset's `candidate_selection` ('first' = source behaviour,
    'recent' = most-recent right rim first)."""
    out = []
    if len(peaks) < 2 or len(troughs) < 2:
        return out
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
        out.append({'k': k_idx, 'a': a_idx, 'b': b_idx,
                    'c': c_idx, 'd': d_idx})
    return out


def _recency_weights(m: int) -> np.ndarray:
    """Linear 1..m — the most recent day in the window weighs m x the
    first (breakoutwatch RCQ/HQ: 'recent days more important')."""
    return np.arange(1, m + 1, dtype=float)


def _rcq_score(close: np.ndarray, volume: np.ndarray, vol_ma: np.ndarray,
               start: int, end: int) -> float:
    """§16 Task F — Right Cup Quality over days (start, end] (base bottom ->
    right rim). +1 for an up day on above-average volume (demand), -1 for a
    down day on above-average volume (distribution), 0 otherwise;
    recency-weighted mean -> roughly [-1, 1]. Source: lit/Chart Quality.html."""
    if end - start < 2:
        return 0.0
    seg = np.arange(start + 1, end + 1)
    up = close[seg] > close[seg - 1]
    dn = close[seg] < close[seg - 1]
    ma = np.nan_to_num(vol_ma[seg], nan=np.inf)
    hi_vol = volume[seg] > ma
    s = np.where(up & hi_vol, 1.0, np.where(dn & hi_vol, -1.0, 0.0))
    w = _recency_weights(len(s))
    return float((s * w).sum() / w.sum())


def _hq_score(close: np.ndarray, volume: np.ndarray, vol_ma: np.ndarray,
              start: int, end: int) -> float:
    """§16 Task E — Handle Quality over days (start, end] (right rim ->
    handle bottom), breakoutwatch's price/volume 2x2:
        price down + volume down  = very desirable  (+1.0)
        price up   + volume down  = desirable       (+0.5)
        price up   + volume up    = unfavorable     (-0.5)
        price down + volume up    = very unfavorable(-1.0)
    recency-weighted mean, plus the breakout-foreshadow bonus (latest close
    up on volume >= its MA -> +0.5, else >= prior day -> +0.25).
    Source: lit/Chart Quality.html."""
    if end - start < 2:
        return 0.0
    seg = np.arange(start + 1, end + 1)
    dp = close[seg] - close[seg - 1]
    dv = volume[seg] - volume[seg - 1]
    q = np.where((dp < 0) & (dv < 0), 1.0,
                 np.where((dp > 0) & (dv < 0), 0.5,
                          np.where((dp > 0) & (dv > 0), -0.5, -1.0)))
    w = _recency_weights(len(q))
    base = float((q * w).sum() / w.sum())
    if len(close) >= 2 and close[-1] > close[-2]:
        vm = vol_ma[-1] if len(vol_ma) else np.nan
        if not np.isnan(vm) and volume[-1] >= vm:
            base += 0.5
        elif volume[-1] >= volume[-2]:
            base += 0.25
    return base


_BASE = {'found': False, 'stage': None, 'quality': np.nan,
         'cup_depth_pct': np.nan, 'handle_depth_pct': np.nan,
         'target': np.nan, 'stop': np.nan, 'setup_gain_pct': np.nan,
         'days_since_rim': np.nan, 'cup_handle_ratio': np.nan,
         'hq': np.nan, 'rcq': np.nan, 'cq': np.nan,
         'breakout_vol_confirmed': False}


def _evaluate_preset(close: np.ndarray, high: np.ndarray | None,
                     low: np.ndarray | None, volume: np.ndarray,
                     params: dict) -> dict:
    """detect_pattern for one preset: build every K-A-B-C-D candidate, then
    return the first that passes all validations — in the order the preset's
    `candidate_selection` asks for ('first' = source's earliest-trough
    behaviour, kept for Loose; 'recent' = most-recent right rim first, so
    §16 Task B's recency cap actually surfaces the freshest valid cup)."""
    peaks, troughs = _find_extrema(close, params['prominence_threshold'],
                                   params['distance_threshold'])
    if len(peaks) < 2 or len(troughs) < 1:
        return dict(_BASE)
    cands = _all_pattern_points(close, peaks, troughs)
    if not cands:
        return dict(_BASE)
    if params.get('candidate_selection', 'first') == 'first':
        # source behaviour EXACTLY: validate only the earliest constructible
        # candidate (patterns_v0 builds one, then accepts/rejects it) — Loose
        # stays identical to patterns_v0's daily config.
        r = _try_candidate(close, high, low, volume, cands[0], params)
        return r if r is not None else dict(_BASE)
    # 'recent': try every candidate, freshest right rim first, take the
    # first that passes all rules.
    for pts in sorted(cands, key=lambda p: p['c'], reverse=True):
        r = _try_candidate(close, high, low, volume, pts, params)
        if r is not None:
            return r
    return dict(_BASE)


def _try_candidate(close: np.ndarray, high: np.ndarray | None,
                   low: np.ndarray | None, volume: np.ndarray,
                   pts: dict, params: dict) -> dict | None:
    """Validate one K-A-B-C-D candidate — result dict if it passes every
    rule, else None (so the caller can try the next candidate)."""
    n = len(close)
    k, a, b, c, d = (pts[x] for x in ('k', 'a', 'b', 'c', 'd'))
    # basic structure: ordered, B below both rims (on close, as detected)
    if not (k < a < b < c <= d):
        return None
    if close[b] >= close[a] or close[b] >= close[c]:
        return None

    # §16 Task H — measurement prices: rims off the daily HIGH, bottoms off
    # the daily LOW when available and enabled; else close.
    intraday = bool(params.get('use_intraday_extremes')) and \
        high is not None and low is not None
    p_a = float(high[a]) if intraday else float(close[a])
    p_c = float(high[c]) if intraday else float(close[c])
    p_b = float(low[b]) if intraday else float(close[b])
    p_d = float(low[d]) if intraday else float(close[d])
    if not (p_b < p_a and p_b < p_c):
        return None

    cup_depth = (p_a - p_b) / p_a
    if not (params['cup_min_depth_pct'] <= cup_depth
            <= params['cup_max_depth_pct']):
        return None
    cup_duration = c - a
    if not (params['cup_min_duration'] <= cup_duration
            <= params['cup_max_duration']):
        return None
    rim_sym = abs(p_a - p_c) / p_a
    if rim_sym > params['cup_depth_tolerance']:
        return None

    # §16 Task A — setup gain: prior advance INTO the left rim. Prior low =
    # min over CUPHANDLE_SETUP_LOOKBACK bars before the rim (the base begins
    # at the rim; O'Neil / breakoutwatch want >= 30% run-up first).
    lo_from = max(0, a - config.CUPHANDLE_SETUP_LOOKBACK)
    setup_gain = np.nan
    if a - lo_from >= 1:
        prior_arr = (low if intraday else close)[lo_from:a]
        prior_low = float(np.nanmin(prior_arr))
        if prior_low > 0:
            setup_gain = (p_a - prior_low) / prior_low
    if params.get('setup_gain_min', 0.0) > 0.0 and (
            np.isnan(setup_gain) or setup_gain < params['setup_gain_min']):
        return None

    # §16 Task B — pivot recency: bars from the right rim (handle start) to
    # the last bar. breakoutwatch: pivot within 90 days.
    days_since_rim = n - 1 - c
    if days_since_rim > params.get('pivot_max_age', 10 ** 9):
        return None

    # §16 Task C — cup : handle length ratio (breakoutwatch: >= 3)
    ch_ratio = (c - a) / max(d - c, 1)
    if ch_ratio < params.get('cup_handle_ratio_min', 0.0):
        return None

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
            return None

    # handle
    cup_height = p_a - p_b
    handle_depth = (p_c - p_d) / cup_height
    handle_duration = d - c
    handle_position = max(0.0, (p_d - p_b) / cup_height)
    if handle_position < params['handle_position_min']:
        return None
    if handle_depth > params['handle_max_depth_pct']:
        return None
    if not (params['handle_min_duration'] <= handle_duration
            <= params['handle_max_duration']):
        return None

    # §16 Task D — handle midpoint >= base midpoint (breakoutwatch)
    if params.get('handle_midpoint_rule'):
        if (p_c + p_d) / 2 < (p_a + p_b) / 2:
            return None

    # volume pattern
    vol_ma = pd.Series(volume).rolling(
        int(params['volume_ma_period'])).mean().to_numpy()
    cup_vol = volume[a:c + 1].mean()
    _ma_window = vol_ma[a:c + 1]
    vol_ma_during = (np.nanmean(_ma_window)
                     if np.size(_ma_window) and not np.isnan(_ma_window).all()
                     else np.nan)
    decline_confirmed = cup_vol < vol_ma_during * \
        params['volume_decline_threshold']
    breakout_ratio = None
    if n - 1 > d:
        recent = volume[-5:].mean()
        breakout_ratio = recent / vol_ma_during if vol_ma_during else None

    # §16 Tasks E/F — HQ / RCQ recency-weighted price/volume quality, and
    # CQ = the breakoutwatch Chart Quality blend of the two, weight shifting
    # toward HQ as the handle lengthens ("longer handles are given more
    # weight when combining RCQ and HQ" — lit/Chart Quality.html). Reported
    # column only; does NOT gate detection and is NOT in the quality score.
    # Scale: RCQ/HQ ~[-1, 1] (HQ can reach ~1.5 with the foreshadow bonus),
    # so CQ ~[-1, 1.3]; higher = more constructive, sign carries the meaning.
    rcq = _rcq_score(close, volume, vol_ma, b, c)
    hq = _hq_score(close, volume, vol_ma, c, d)
    _hw = min(handle_duration / 20.0, 1.0)
    _w_hq = 0.40 + 0.30 * _hw
    cq = (1.0 - _w_hq) * rcq + _w_hq * hq

    # quality score (source _calculate_quality_score, verbatim) + §16 E/F
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
    score += max(0.0, rcq) * 10          # §16 Task F — up to +10
    score += max(0.0, hq) * 10           # §16 Task E — up to +10 (+bonus)
    score = min(100.0, max(0.0, score))

    # stage / target / stop
    resistance = max(p_a, p_c)
    if n - 1 <= d:
        stage = 'forming'
    elif close[-1] > resistance:
        stage = 'breakout'
    else:
        stage = 'complete'
    target = resistance + (p_a - p_b)
    stop = min(p_d, p_b) * 0.95

    # §16 Task G — volume-confirmed breakout
    vm_last = vol_ma[-1] if len(vol_ma) else np.nan
    breakout_vol_confirmed = bool(
        stage == 'breakout' and not np.isnan(vm_last)
        and volume[-1] >= vm_last * params['breakout_volume_factor'])

    return {'found': True, 'stage': stage, 'quality': round(score, 1),
            'cup_depth_pct': round(cup_depth * 100, 2),
            'handle_depth_pct': round(handle_depth * 100, 2),
            'target': round(target, 3), 'stop': round(stop, 3),
            'setup_gain_pct': round(setup_gain * 100, 2)
            if not np.isnan(setup_gain) else np.nan,
            'days_since_rim': int(days_since_rim),
            'cup_handle_ratio': round(ch_ratio, 2),
            'hq': round(hq, 3), 'rcq': round(rcq, 3), 'cq': round(cq, 3),
            'breakout_vol_confirmed': breakout_vol_confirmed}


def evaluate(tickers: list, data: dict,
             presets: list | None = None) -> pd.DataFrame:
    """
    tickers: scoped subset (explicit argument — on-demand architecture).
    data: wide OHLCV matrices restricted to the scoped tickers. `high` and
    `low` are used for §16 Task H (intraday extremes) when present; absent,
    the detector falls back to close everywhere.
    presets: which parameter presets to compute (default: all three).
    """
    wanted = presets or list(config.CUPHANDLE_PRESETS)
    tickers = [t for t in tickers if t in data['close'].columns]
    close_all = data['close'][tickers]
    vol_all = data['volume'][tickers]
    high_all = data['high'] if 'high' in data else None
    low_all = data['low'] if 'low' in data else None

    rows = []
    for t in tickers:
        c_ser = close_all[t].dropna()
        v_ser = vol_all[t].reindex(c_ser.index)
        h_ser = (high_all[t].reindex(c_ser.index)
                 if high_all is not None and t in high_all.columns else None)
        l_ser = (low_all[t].reindex(c_ser.index)
                 if low_all is not None and t in low_all.columns else None)
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
            row[f'cup_handle_setup_gain_pct{suffix}'] = np.nan
            row[f'cup_handle_days_since_rim{suffix}'] = np.nan
            row[f'cup_handle_ratio{suffix}'] = np.nan
            row[f'cup_handle_hq{suffix}'] = np.nan
            row[f'cup_handle_rcq{suffix}'] = np.nan
            row[f'cup_handle_cq{suffix}'] = np.nan
            row[f'cup_handle_breakout_vol_confirmed{suffix}'] = False
        if len(c_ser) >= 20:
            close_np = c_ser.to_numpy(float)
            vol_np = v_ser.to_numpy(float)
            high_np = h_ser.to_numpy(float) if h_ser is not None else None
            low_np = l_ser.to_numpy(float) if l_ser is not None else None
            # per-preset compute (parameters change the extrema themselves)
            for preset in wanted:
                r = _evaluate_preset(close_np, high_np, low_np, vol_np,
                                     config.CUPHANDLE_PRESETS[preset])
                sfx = f'_{preset}'
                row[f'in_cup_handle{sfx}'] = r['found']
                row[f'cup_handle_stage{sfx}'] = r['stage']
                row[f'cup_handle_quality_score{sfx}'] = r['quality']
                row[f'cup_depth_pct{sfx}'] = r['cup_depth_pct']
                row[f'handle_depth_pct{sfx}'] = r['handle_depth_pct']
                row[f'cup_handle_target_price{sfx}'] = r['target']
                row[f'cup_handle_stop_loss{sfx}'] = r['stop']
                row[f'cup_handle_setup_gain_pct{sfx}'] = r['setup_gain_pct']
                row[f'cup_handle_days_since_rim{sfx}'] = r['days_since_rim']
                row[f'cup_handle_ratio{sfx}'] = r['cup_handle_ratio']
                row[f'cup_handle_hq{sfx}'] = r['hq']
                row[f'cup_handle_rcq{sfx}'] = r['rcq']
                row[f'cup_handle_cq{sfx}'] = r['cq']
                row[f'cup_handle_breakout_vol_confirmed{sfx}'] = \
                    r['breakout_vol_confirmed']
            last_valid = c_ser.last_valid_index()
            row['as_of'] = last_valid.strftime('%Y-%m-%d') \
                if last_valid is not None else None
        rows.append(row)

    out = pd.DataFrame(rows).set_index('ticker')
    out.index.name = 'ticker'
    return out

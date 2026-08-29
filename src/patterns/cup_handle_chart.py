"""
Annotated Cup-with-Handle chart — the breakoutwatch "Anatomy of a
Cup-with-Handle Pattern" style (4 stage bands, the labelled K-A-B-C-D
points, Setup Gain / Cup Depth / Handle Depth / Pivot-off / RCQ-HQ-CQ
annotations, the measured-move target + stop, and a volume panel).

`figure(ticker, preset, data)` returns a matplotlib Figure for the pattern
that cup_handle.py's detector actually selected, or None if there is none.
Used by the dashboard Patterns tab (st.pyplot) and the standalone
cup_handle_ideas/cupAndHandle/draw_cup_handle.py CLI (fig.savefig).

Does NOT set the matplotlib backend — the caller decides (the CLI forces
'Agg'; Streamlit manages its own).

Reference: cup_handle_ideas/cupAndHandle/lit/candhanfdle_image.png
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
import config
from src.patterns import cup_handle as ch

STAGE_COLORS = {'setup': '#d9d9d9', 'decline': '#f7c6c6',
                'recovery': '#bfefff', 'consolidation': '#cfe0f5'}


def _pick_candidate(close, high, low, volume, params):
    """Re-run cup_handle's candidate selection; return (points, metrics) for
    the winning K-A-B-C-D, or None."""
    peaks, troughs = ch._find_extrema(close, params['prominence_threshold'],
                                      params['distance_threshold'])
    if len(peaks) < 2 or len(troughs) < 1:
        return None
    cands = ch._all_pattern_points(close, peaks, troughs)
    if not cands:
        return None
    order = (cands[:1] if params.get('candidate_selection', 'first') == 'first'
             else sorted(cands, key=lambda p: p['c'], reverse=True))
    for pts in order:
        r = ch._try_candidate(close, high, low, volume, pts, params)
        if r is not None:
            return pts, r
    return None


def figure(ticker: str, preset: str, data: dict):
    """Annotated cup-and-handle Figure for `ticker` under `preset`, or None.
    `data`: wide OHLCV dict (data_loader.load_price_matrices output)."""
    params = config.CUPHANDLE_PRESETS[preset]
    if ticker not in data['close'].columns:
        return None
    c_ser = data['close'][ticker].dropna()
    if len(c_ser) < 40:
        return None
    idx = c_ser.index
    close = c_ser.to_numpy(float)
    high = data['high'][ticker].reindex(idx).to_numpy(float)
    low = data['low'][ticker].reindex(idx).to_numpy(float)
    vol = data['volume'][ticker].reindex(idx).to_numpy(float)

    intraday = bool(params.get('use_intraday_extremes'))
    picked = _pick_candidate(close, high if intraday else None,
                             low if intraday else None, vol, params)
    if picked is None:
        return None
    pts, met = picked
    k, a, b, cc, d = (pts[x] for x in ('k', 'a', 'b', 'c', 'd'))
    n = len(close)

    p_a = float(high[a]) if intraday else float(close[a])
    p_c = float(high[cc]) if intraday else float(close[cc])
    p_b = float(low[b]) if intraday else float(close[b])
    p_d = float(low[d]) if intraday else float(close[d])

    lo_from = max(0, a - config.CUPHANDLE_SETUP_LOOKBACK)
    prior_arr = (low if intraday else close)[lo_from:a]
    pl_rel = int(np.nanargmin(prior_arr))
    pl_idx = lo_from + pl_rel
    p_pl = float(prior_arr[pl_rel])

    cur_i = n - 1
    p_cur = float(close[cur_i])

    setup_gain = (p_a - p_pl) / p_pl * 100
    cup_depth = (p_a - p_b) / p_a * 100
    handle_depth = (p_c - p_d) / (p_a - p_b) * 100
    pivot_off = (p_c - p_a) / p_a * 100
    resistance = max(p_a, p_c)
    target = resistance + (p_a - p_b)
    stop = min(p_d, p_b) * 0.95
    days_since_rim = n - 1 - cc

    cup_w = cc - a
    x0 = max(0, a - max(15, int(0.55 * cup_w)))
    xs = np.arange(x0, n)
    stage1_start = max(x0, pl_idx)

    fig, (ax, axv) = plt.subplots(
        2, 1, figsize=(13, 8.5), height_ratios=[3.4, 1],
        sharex=True, gridspec_kw={'hspace': 0.06})
    fig.subplots_adjust(left=0.115, right=0.90, top=0.93, bottom=0.07)

    vis_w = n - x0
    bands = [(stage1_start, a, 'setup', 'Stage 1: Setup'),
             (a, b, 'decline', 'Stage 2: Decline'),
             (b, cc, 'recovery', 'Stage 3: Recovery'),
             (cc, cur_i, 'consolidation', 'Stage 4: Consolidation')]
    for j, (s, e, key, label) in enumerate(bands):
        ax.axvspan(s, e, color=STAGE_COLORS[key], alpha=0.8, lw=0)
        if (e - s) / vis_w > 0.03:
            ax.text((s + e) / 2, 0.995 if j % 2 == 0 else 0.945, label,
                    transform=ax.get_xaxis_transform(),
                    ha='center', va='top', fontsize=8.3, fontweight='bold',
                    color='#1a3a6b')

    ax.plot(xs, close[x0:n], color='#1f2f6b', lw=2.2, zorder=5)
    ax.fill_between(xs, low[x0:n], high[x0:n], color='#8fa0c8', alpha=0.35,
                    lw=0, zorder=3)

    lo_v, hi_v = float(np.min(low[x0:n])), float(np.max(high[x0:n]))
    rng = hi_v - lo_v
    y_lo = lo_v - rng * 0.13
    y_hi = max(hi_v, target) + rng * 0.30
    ax.set_ylim(y_lo, y_hi)

    for lvl, txt, col in [(p_a, 'Left Cup', '#1f2f6b'),
                          (p_b, 'Base Low', '#1f2f6b'),
                          (target, f'Target {target:.2f}  (+{cup_depth:.0f}%)',
                           '#0a7d18'),
                          (stop, f'Stop {stop:.2f}', '#b00000')]:
        if y_lo <= lvl <= y_hi:
            ax.axhline(lvl, color=col, ls='--', lw=0.9, alpha=0.5)
            ax.annotate(txt, (1.0, lvl), xycoords=('axes fraction', 'data'),
                        xytext=(4, 0), textcoords='offset points',
                        va='center', ha='left', fontsize=7.5, color=col,
                        annotation_clip=False)

    pl_vis = x0 <= pl_idx
    pump = [('Left Cup', a, p_a, 'bottom', 'center', 0, 9, '#1f2f6b'),
            ('Base Low', b, p_b, 'top', 'center', 0, -9, '#1f2f6b'),
            ('Pivot', cc, p_c, 'bottom', 'center', 0, 9, '#1f2f6b'),
            ('Handle Low', d, p_d, 'top', 'center', 0, -9, '#b00000'),
            ('Current Close', cur_i, p_cur, 'center', 'right', -10, 0,
             '#0a7d18')]
    if pl_vis:
        pump.insert(0, ('Prior Low', pl_idx, p_pl, 'top', 'center', 0, -9,
                        '#b00000'))
    for label, i, y, va, ha, dx, dy, col in pump:
        ax.scatter([i], [y], s=55, color='#e02020', zorder=8,
                   edgecolor='white', linewidth=0.7)
        ax.annotate(f'{label}\n{y:.2f}', (i, y),
                    textcoords='offset points', xytext=(dx, dy),
                    ha=ha, va=va, fontsize=8.5, fontweight='bold',
                    color=col, zorder=9)

    for s, e, label in [(a, cc, 'Cup'), (cc, d, 'Handle')]:
        if e - s < 1:
            continue
        ax.annotate('', (s, 0.88), (e, 0.88),
                    xycoords=ax.get_xaxis_transform(),
                    arrowprops=dict(arrowstyle='<->', color='#1a3a6b', lw=1.3))
        ax.text((s + e) / 2, 0.885, label, transform=ax.get_xaxis_transform(),
                ha='center', va='bottom', fontsize=9, color='#1a3a6b',
                fontweight='bold')

    ax.axvline(cur_i, color='#555', ls=':', lw=1.0)
    ax.text(cur_i, 0.01, ' Today', transform=ax.get_xaxis_transform(),
            ha='right', va='bottom', fontsize=8, color='#555', style='italic')
    if days_since_rim > 40:
        ax.annotate('', (cc, 0.80), (cur_i, 0.80),
                    xycoords=ax.get_xaxis_transform(),
                    arrowprops=dict(arrowstyle='->', color='#999', lw=1.0))
        ax.text((cc + cur_i) / 2, 0.805, f'{days_since_rim} bars since pivot',
                transform=ax.get_xaxis_transform(), ha='center', va='bottom',
                fontsize=7.5, color='#999', style='italic')

    pl_note = (f'Prior Low        {p_pl:.2f}  ({a - pl_idx} bars back)\n'
               if not pl_vis else '')
    txt = (pl_note +
           f'Setup Gain      +{setup_gain:.1f}%\n'
           f'Cup Depth        {cup_depth:.1f}%\n'
           f'Handle Depth    {handle_depth:.1f}% of cup\n'
           f'Pivot off L.Cup  {pivot_off:+.1f}%\n'
           f'Days since rim   {days_since_rim}\n'
           f'Cup:Handle len   {cup_w / max(d - cc, 1):.1f}\n'
           f'RCQ {met["rcq"]:+.2f}  HQ {met["hq"]:+.2f}  CQ {met["cq"]:+.2f}\n'
           f'Quality  {met["quality"]:.0f}/100'
           + ('  |  vol-confirmed' if met['breakout_vol_confirmed'] else ''))
    ax.text(0.008, 0.72, txt, transform=ax.transAxes, fontsize=8,
            va='top', ha='left', family='monospace',
            bbox=dict(boxstyle='round', fc='white', ec='#999', alpha=0.92))

    as_of = idx[-1].strftime('%Y-%m-%d')
    ax.set_title(f'{ticker} — Cup with Handle ({preset} preset)   as of {as_of}',
                 fontsize=12, fontweight='bold', color='#1a3a6b')
    ax.set_ylabel('Price')
    ax.margins(x=0.02)

    up = close[x0:n] >= np.r_[close[max(x0 - 1, 0)], close[x0:n - 1]]
    axv.bar(xs[up], vol[x0:n][up], color='#2b57c9', width=1.0)
    axv.bar(xs[~up], vol[x0:n][~up], color='#c9352b', width=1.0)
    env = pd.Series(vol).rolling(15, min_periods=1).mean().to_numpy()[x0:n]
    axv.plot(xs, env, color='#111', lw=1.2)
    for s, e, key, _ in bands:
        axv.axvspan(s, e, color=STAGE_COLORS[key], alpha=0.5, lw=0)
    axv.set_ylabel('Volume')
    axv.set_yticks([])

    tick_i = np.linspace(x0, n - 1, 8).astype(int)
    axv.set_xticks(tick_i)
    axv.set_xticklabels([idx[i].strftime('%d %b %y') for i in tick_i],
                        fontsize=8)
    axv.set_xlim(x0 - vis_w * 0.02, n - 1 + vis_w * 0.02)
    return fig

"""
Annotated Green-Line Breakout chart — the drwish / Eric Wish "Green Line"
picture: the price line + high/low band, the staircase of prior green
lines (confirmed pivot highs that later gave way), the ACTIVE green line
drawn bold from its pivot to the right edge, its `confirmation_bars`
window shaded, the first intraday poke above it (the transient "signal"),
the confirmed close-breakout, and a volume panel.

`figure(ticker, scenario, data, as_of=None)` returns a matplotlib Figure
for the green line the GLB detector (glb.py) actually resolves, or None if
there is no confirmed pivot. Uses glb._compute_records directly — the SAME
record logic evaluate()/evaluate_multi() use — so the picture is always in
step with the scanner. Used by the standalone draw_glb.py CLI (fig.savefig).

Does NOT set the matplotlib backend — the caller decides (the CLI forces
'Agg'; Streamlit manages its own).
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
import config
from src.patterns import glb


def _resolve_params(scenario: str) -> dict:
    """Merge a GLB_PRESET_CHOICES entry (by name) — or 'default' — onto the
    GLB config defaults, the same way evaluate()'s `params` arg is."""
    p = {
        'pivot_strength': config.GLB_PIVOT_STRENGTH,
        'lookback_bars': config.GLB_LOOKBACK_BARS,
        'historical_bars': config.GLB_HISTORICAL_BARS,
        'confirmation_bars': config.GLB_CONFIRMATION_BARS,
        'require_confirmation': config.GLB_REQUIRE_CONFIRMATION,
    }
    if scenario and scenario != 'default':
        choice = next((c for c in config.GLB_PRESET_CHOICES
                       if c['name'] == scenario), None)
        if choice is None:
            raise ValueError(f'unknown GLB scenario {scenario!r} — pick from '
                             f'{[c["name"] for c in config.GLB_PRESET_CHOICES]}'
                             ' or "default"')
        p['lookback_bars'] = choice['lookback_bars']
        p['confirmation_bars'] = choice['confirmation_bars']
    return p


def _pick_record(records: list, dates: list, n: int, lookback: int) -> dict | None:
    """The green line to feature. Prefer a confirmed, still-open pivot within
    the lookback window (highest one — that's _latest_signal's live level);
    else the most recent confirmed pivot (the ceiling the stock is working
    against now, whether or not the signal has aged out)."""
    conf = [r for r in records if r['is_confirmed']
            and r['detection_date'] in dates]
    if not conf:
        return None
    open_lb = [r for r in conf if not r['is_broken']
               and dates.index(r['detection_date']) >= n - 1 - lookback]
    if open_lb:
        return max(open_lb, key=lambda r: r['level'])
    return max(conf, key=lambda r: r['detection_date'])


def figure(ticker: str, scenario: str, data: dict, as_of: str | None = None,
           follow_bars: int | None = None):
    """Annotated green-line Figure for `ticker` under `scenario`
    ('3m_2w' … '2y_3m', or 'default'), or None.
    `data`: wide OHLCV dict (data_loader.load_price_matrices output).
    `as_of`: optional 'YYYY-MM-DD' cutoff — the DETECTOR sees only bars up
    to this date (so an aged-out signal can be reproduced), but the chart
    still plots what came after, ghosted, so the follow-through is visible.
    `follow_bars`: how many post-cutoff bars to plot (None = all available;
    ignored when `as_of` is None, since there is nothing after 'now')."""
    params = _resolve_params(scenario)
    if ticker not in data['close'].columns:
        return None

    h_full = data['high'][ticker].dropna()
    if len(h_full) < config.GLB_MIN_DATA_POINTS:
        return None
    n_det = len(h_full.loc[:as_of]) if as_of is not None else len(h_full)
    n_det = max(config.GLB_MIN_DATA_POINTS, min(n_det, len(h_full)))
    avail_after = len(h_full) - n_det
    follow = avail_after if follow_bars is None else max(0, min(follow_bars,
                                                               avail_after))
    n_plot = n_det + follow

    idx = h_full.index[:n_plot]
    close = data['close'][ticker].reindex(idx).to_numpy(float)
    high = h_full.to_numpy(float)[:n_plot]
    low = data['low'][ticker].reindex(idx).to_numpy(float)
    vol = data['volume'][ticker].reindex(idx).to_numpy(float)
    dates = [d.strftime('%Y-%m-%d') for d in idx]

    # detection runs on the as-of prefix only
    d_hi, d_cl, d_dt = high[:n_det], close[:n_det], dates[:n_det]
    start_bar = max(params['pivot_strength'], n_det - params['historical_bars'])
    records = glb._compute_records(d_hi, d_cl, d_dt, params, start_bar, [])
    feat = _pick_record(records, d_dt, n_det, params['lookback_bars'])
    if feat is None:
        return None

    piv_i = d_dt.index(feat['detection_date'])
    level = feat['level']
    conf = params['confirmation_bars']
    conf_end = min(piv_i + conf, n_det)

    # first intraday poke above the line, after the confirmation window
    sig_i = None
    poke = np.flatnonzero(d_hi[conf_end:] > level)
    if len(poke):
        sig_i = conf_end + int(poke[0])
    brk_i = (d_dt.index(feat['breakout_date'])
             if feat['is_broken'] and feat['breakout_date'] in d_dt else None)

    asof_i = n_det - 1                     # last bar the detector saw
    last_i = n_plot - 1                    # last bar plotted
    p_asof = float(close[asof_i])
    p_last = float(close[last_i])
    days_since = asof_i - piv_i
    pct_since = (p_asof - level) / level * 100

    # follow-through extremes over the ghosted post-cutoff bars
    post_hi = post_lo = None
    if follow > 0:
        seg_hi, seg_lo = high[n_det:n_plot], low[n_det:n_plot]
        post_hi = (float(np.max(seg_hi)) - p_asof) / p_asof * 100
        post_lo = (float(np.min(seg_lo)) - p_asof) / p_asof * 100

    x0 = max(0, piv_i - max(40, int(params['lookback_bars'] * 0.8)))
    vis_w = n_plot - x0
    piv_frac = (piv_i - x0) / vis_w   # where the pivot sits in the window

    fig, (ax, axv) = plt.subplots(
        2, 1, figsize=(13, 8.5), height_ratios=[3.4, 1],
        sharex=True, gridspec_kw={'hspace': 0.06})
    fig.subplots_adjust(left=0.09, right=0.90, top=0.93, bottom=0.07)

    # confirmation window shade
    ax.axvspan(piv_i, conf_end, color='#d9f2dd', alpha=0.9, lw=0)
    if (conf_end - piv_i) / vis_w > 0.03:
        ax.text((piv_i + conf_end) / 2, 0.02, f'{conf}-bar\nconfirm',
                transform=ax.get_xaxis_transform(), ha='center', va='bottom',
                fontsize=7.5, color='#0a7d18')

    # price up to the cutoff (solid) ...
    pre = np.arange(x0, n_det)
    ax.plot(pre, close[x0:n_det], color='#1f2f6b', lw=2.0, zorder=5)
    ax.fill_between(pre, low[x0:n_det], high[x0:n_det], color='#8fa0c8',
                    alpha=0.32, lw=0, zorder=3)
    # ... and what happened after (ghosted)
    if follow > 0:
        post = np.arange(n_det - 1, n_plot)
        ax.plot(post, close[n_det - 1:n_plot], color='#1f2f6b', lw=1.6,
                ls=(0, (4, 2)), alpha=0.5, zorder=5)
        ax.fill_between(post, low[n_det - 1:n_plot], high[n_det - 1:n_plot],
                        color='#8fa0c8', alpha=0.14, lw=0, zorder=3)
        ax.axvspan(asof_i, last_i, color='#f0f0f0', alpha=0.5, lw=0, zorder=1)

    # the staircase of prior confirmed green lines that later gave way
    for r in records:
        if r is feat or not r['is_confirmed'] or r['detection_date'] not in d_dt:
            continue
        pi = d_dt.index(r['detection_date'])
        pe = (d_dt.index(r['breakout_date'])
              if r['is_broken'] and r['breakout_date'] in d_dt else n_det - 1)
        if pe < x0:
            continue
        ax.hlines(r['level'], max(pi, x0), pe, color='#0a7d18', ls=':',
                  lw=1.0, alpha=0.45, zorder=4)

    # the active / featured green line — solid to the cutoff, faded beyond
    ax.hlines(level, piv_i, asof_i, color='#0a7d18', ls='-', lw=2.4,
              alpha=0.9, zorder=6)
    if follow > 0:
        ax.hlines(level, asof_i, last_i, color='#0a7d18', ls='-', lw=2.4,
                  alpha=0.35, zorder=6)
    ax.annotate(f'Green Line {level:.2f}', (1.0, level),
                xycoords=('axes fraction', 'data'),
                xytext=(4, 0), textcoords='offset points', va='center',
                ha='left', fontsize=8.5, fontweight='bold', color='#0a7d18',
                annotation_clip=False)

    lo_v, hi_v = float(np.min(low[x0:n_plot])), float(np.max(high[x0:n_plot]))
    rng = hi_v - lo_v or 1.0
    ax.set_ylim(lo_v - rng * 0.10, hi_v + rng * 0.14)

    pts = [('Pivot High', piv_i, level, 'bottom', 0, 11, '#e02020')]
    if sig_i is not None:
        pts.append(('Signal (high > line)', sig_i, float(high[sig_i]),
                    'bottom', 0, 11, '#c07a00'))
    if brk_i is not None:
        pts.append(('Breakout (close > line)', brk_i, float(close[brk_i]),
                    'bottom', 0, 13, '#0a7d18'))
    pts.append((('Close @ as-of' if follow > 0 else 'Current Close'),
                asof_i, p_asof, 'top', -10, -16, '#1f2f6b'))
    if follow > 0:
        pts.append((f'Latest {(p_last - p_asof) / p_asof * 100:+.1f}% '
                    f'({follow} bars)',
                    last_i, p_last, 'center', -8, 0, '#7a3fb0'))
    for label, i, y, va, dx, dy, col in pts:
        ax.scatter([i], [y], s=55, color=col, zorder=9,
                   edgecolor='white', linewidth=0.7)
        ha = 'left' if dx > 0 else ('right' if dx < 0 else 'center')
        ax.annotate(f'{label}\n{y:.2f}', (i, y), textcoords='offset points',
                    xytext=(dx, dy), ha=ha, va=va, fontsize=8.3,
                    fontweight='bold', color=col, zorder=10)

    for i, col in ((sig_i, '#c07a00'), (brk_i, '#0a7d18')):
        if i is not None:
            ax.axvline(i, color=col, ls=':', lw=1.0, alpha=0.6)

    state = ('OPEN — signal live' if not feat['is_broken']
             else f'BROKEN {feat["breakout_date"]}')
    txt = (f'Scenario         {scenario}\n'
           f'Pivot strength   {params["pivot_strength"]}\n'
           f'Lookback         {params["lookback_bars"]} bars\n'
           f'Confirmation     {conf} bars\n'
           f'Green line       {level:.2f}\n'
           f'Pivot date       {feat["detection_date"]}\n'
           f'Bars since pivot {days_since}\n'
           f'Price vs line    {pct_since:+.1f}%  (at as-of)\n'
           f'State            {state}')
    if follow > 0:
        txt += (f'\n-- next {follow} bars --\n'
                f'Peak             {post_hi:+.1f}%\n'
                f'Trough           {post_lo:+.1f}%\n'
                f'Close            {(p_last - p_asof) / p_asof * 100:+.1f}%')
    # keep the info box clear of the pivot marker/label
    box_y, box_va = ((0.03, 'bottom') if piv_frac < 0.36 else (0.985, 'top'))
    ax.text(0.008, box_y, txt, transform=ax.transAxes, fontsize=8,
            va=box_va, ha='left', family='monospace',
            bbox=dict(boxstyle='round', fc='white', ec='#999', alpha=0.92))

    ax.axvline(asof_i, color='#555', ls=':', lw=1.0)
    ax.text(0.995, 0.012,
            (f'detector as-of {d_dt[-1]}  ·  latest {dates[-1]}')
            if follow > 0 else ('as of ' + dates[-1]),
            transform=ax.transAxes,
            ha='right', va='bottom', fontsize=8, color='#555', style='italic')
    ax.set_title(f'{ticker} — Green Line Breakout ({scenario})   '
                 f'pivot {feat["detection_date"]} @ {level:.2f}',
                 fontsize=12, fontweight='bold', color='#0a5a12')
    ax.set_ylabel('Price')
    ax.margins(x=0.02)

    up = close[x0:n_plot] >= np.r_[close[max(x0 - 1, 0)], close[x0:n_plot - 1]]
    xs = np.arange(x0, n_plot)
    vv = vol[x0:n_plot]
    for seg_lo, seg_hi, alpha in ((x0, n_det, 1.0), (n_det, n_plot, 0.35)):
        if seg_hi <= seg_lo:
            continue
        m = (xs >= seg_lo) & (xs < seg_hi)
        axv.bar(xs[m & up], vv[m & up], color='#2b57c9', width=1.0, alpha=alpha)
        axv.bar(xs[m & ~up], vv[m & ~up], color='#c9352b', width=1.0, alpha=alpha)
    env = pd.Series(vol).rolling(20, min_periods=1).mean().to_numpy()[x0:n_plot]
    axv.plot(xs, env, color='#111', lw=1.2)
    axv.axvspan(piv_i, conf_end, color='#d9f2dd', alpha=0.6, lw=0)
    if follow > 0:
        axv.axvspan(asof_i, last_i, color='#f0f0f0', alpha=0.5, lw=0, zorder=1)
    axv.set_ylabel('Volume')
    axv.set_yticks([])

    tick_i = np.linspace(x0, n_plot - 1, 8).astype(int)
    axv.set_xticks(tick_i)
    axv.set_xticklabels([idx[i].strftime('%d %b %y') for i in tick_i],
                        fontsize=8)
    axv.set_xlim(x0 - vis_w * 0.02, n_plot - 1 + vis_w * 0.02)
    return fig

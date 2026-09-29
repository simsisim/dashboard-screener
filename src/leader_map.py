"""
"Where is each leader?" — the PrimeTrading Lab Report Leaders Map.

Every ticker of a user list (a file — no presets) is placed on two clocks,
both in DAILY ATR14 units (ALEX "ATR Extensions" script dist_21 / dist_10w):
  x  daily   (close - EMA21) / ATR14            -> ext_21ema_atr
  y  weekly  (close - weekly SMA10) / ATR14     -> ext_10wsma_atr
Zones (config.LMAP_*): under the 21-day x < -0.5, in the band -0.5..+1,
above x > +1; weekly lost y < 0, normal 0..+4, extended y > +4.
The buy area = in the band AND weekly normal.

Seven states, best first (the report's cards); "lost the weekly" wins over
the daily position (FROG on 2026-09-25: inside the box, counted as lost).

Validated against the report: the 2026-09-25 map positions and the
2026-09-28 Setups (buy area DELL / RNG / LITE / S; on weakness AVT / SMTC /
NTAP / SWKS = above the buy area).
"""
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config

# key, card title, weekly tag — the report's order (best first)
STATES = [
    ('buy', 'In the buy area', 'weekly normal'),
    ('buy_stretched', 'Buy area · weekly stretched', 'weekly extended'),
    ('above', 'Above the buy area', 'weekly normal'),
    ('ext_both', 'Extended on both', 'weekly extended'),
    ('under', 'Under the 21-day', 'weekly normal'),
    ('unwinding', 'Unwinding', 'weekly extended'),
    ('lost', 'Lost the weekly', 'weekly lost'),
]
STATE_TITLE = {k: t for k, t, _w in STATES}

# zone colors (dataviz reference palette violet / green / yellow; validated
# all-pairs in light mode — yellow < 3:1 contrast, so every dot is labelled)
ZONE_COLOR = {'under': '#4a3aa7', 'band': '#008300', 'above': '#eda100'}
INK, INK_2, INK_3 = '#0b0b0b', '#52514e', '#8a8984'
SURFACE = '#fcfcfb'


def parse_tickers(text: str) -> list:
    """Tickers from a list file, in file order, deduplicated. Accepts the
    TradingView "Upload list" .txt (EXCHANGE:SYMBOL, ###section headers),
    comma / newline / whitespace separated symbols, or a CSV whose Symbol
    (or Ticker) column — else first column — holds them."""
    text = re.sub(r'###[^,\n]*', '', text)       # TradingView section headers
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if lines and re.search(r'(?i)^\s*"?(symbol|ticker|sym)"?\s*(,|$)', lines[0]):
        from io import StringIO
        df = pd.read_csv(StringIO(text), dtype=str)
        col = next(c for c in df.columns
                   if c.strip().lower() in ('symbol', 'ticker', 'sym'))
        tokens = df[col].dropna().tolist()
    else:
        tokens = re.split(r'[,\s]+', text)
    out = []
    for tok in tokens:
        tok = tok.strip().strip('"').upper()
        if not tok:
            continue
        tok = tok.split(':')[-1].lstrip('$')     # NASDAQ:LITE / $LITE -> LITE
        if not re.fullmatch(r'[A-Z0-9][A-Z0-9.\-/]*', tok) \
                or not re.search('[A-Z]', tok):
            continue                             # not a symbol
        if tok not in out:
            out.append(tok)
    return out


def read_themes(path: Path) -> dict:
    """Optional `theme` column of a CSV list -> {ticker: theme}."""
    try:
        df = pd.read_csv(path, dtype=str)
    except Exception:
        return {}
    cols = {c.strip().lower(): c for c in df.columns}
    sym = next((cols[k] for k in ('symbol', 'ticker', 'sym') if k in cols), None)
    if sym is None or 'theme' not in cols:
        return {}
    return {str(s).strip().upper(): str(t).strip()
            for s, t in zip(df[sym], df[cols['theme']]) if pd.notna(t)}


def explain(ticker: str) -> dict | None:
    """The worked example for one ticker, from its daily file: the numbers
    behind x and y, and the 10 weekly closes the weekly average is built
    from (same math as atr_extension.evaluate, one ticker)."""
    from src import data_loader, indicators
    d = data_loader.load_price_matrices([ticker], verbose=False)
    if not d['meta']:
        return None
    t = next(iter(d['meta']))
    c, h, l = d['close'][t].dropna(), d['high'][t], d['low'][t]
    atr = indicators.wilder_atr(h.to_frame(), l.to_frame(), c.to_frame(),
                                config.ATR_PERIOD)[t].iloc[-1]
    ema21 = indicators.ema(c.to_frame(), config.EXT_EMA_PERIOD)[t].iloc[-1]
    wk = pd.DataFrame({'last trading day': c.index.to_series().resample('W-FRI').last(),
                       'weekly close': c.resample('W-FRI').last()}).dropna()
    wk = wk.tail(config.WEEKLY_SMA_PERIOD)
    wk.index.name = 'week ending (Fri)'
    sma10w = wk['weekly close'].mean()
    return {'ticker': t, 'date': c.index[-1], 'close': c.iloc[-1], 'atr': atr,
            'ema21': ema21, 'sma10w': sma10w, 'weeks': wk,
            'x': (c.iloc[-1] - ema21) / atr, 'y': (c.iloc[-1] - sma10w) / atr}


def build_setups(pos: pd.DataFrame) -> pd.DataFrame:
    """The report's "Setups — The Plan": every name in the buy area, then
    every name "on weakness" (above the box by <= LMAP_SETUP_MAX_ABOVE ATR,
    weekly normal), each in list order. Per name, all on the 21-EMA-in-ATR
    axis of the map:
      buy range  = the box in price: EMA21 - 0.5 ATR .. EMA21 + 1 ATR
      entry      = in the buy area: today's close; on weakness: the top of
                   the 21dma-structure (EMA21 of the highs) — "wait for the
                   pullback" (reverse-engineered from the report: SMTC /
                   NTAP / SWKS targets match to the cent)
      stop       = the bottom of the box
      target     = entry + R x (entry - stop)            (2R)
      travel     = x over the last LOOKBACK sessions: min / max (pale bar),
                   25th-75th pct (solid: where it spent most of its time),
                   x LOOKBACK sessions ago (dashed tick)
      band       = which of those sessions closed inside the band (squares)
    Checked vs the 2026-09-28 report (validate.py #18)."""
    from src import data_loader, indicators
    if not len(pos):
        return pd.DataFrame()
    x = pos['x_daily21_atr']
    pick = pd.concat([
        pos[pos['state'] == 'buy'].assign(role='buy'),
        pos[(pos['state'] == 'above') & (x <= config.LMAP_SETUP_MAX_ABOVE)]
        .assign(role='weakness')])
    if not len(pick):
        return pd.DataFrame()
    pick = pick.sort_values(['role', 'list_rank'], key=lambda s: s.map(
        {'buy': 0, 'weakness': 1}) if s.name == 'role' else s)
    d = data_loader.load_price_matrices(list(pick.index), verbose=False)
    c, h, lo_ = d['close'], d['high'], d['low']
    atr = indicators.wilder_atr(h, lo_, c, config.ATR_PERIOD)
    ema = indicators.ema(c, config.EXT_EMA_PERIOD)
    ema_h = indicators.ema(h, config.MA21S_LENGTH)       # 21dma-structure top
    xs = (c - ema) / atr
    lb, band_lo, band_hi = (config.LMAP_SETUP_LOOKBACK, config.LMAP_DAILY_UNDER,
                            config.LMAP_DAILY_ABOVE)
    rows = []
    for t, r in pick.iterrows():
        col = t if t in c.columns else next(
            (k for k in (t.replace('.', '-'), t.replace('-', '.')) if k in c.columns), None)
        if col is None:
            continue
        s = xs[col].dropna()
        last30 = s.tail(lb)
        close, e, a = c[col].dropna().iloc[-1], ema[col].dropna().iloc[-1], atr[col].dropna().iloc[-1]
        stop = e + band_lo * a
        entry = close if r['role'] == 'buy' else ema_h[col].dropna().iloc[-1]
        target = entry + config.LMAP_SETUP_R * (entry - stop)
        inb = ((last30 >= band_lo) & (last30 <= band_hi)).astype(int)
        rows.append({
            'ticker': t, 'role': r['role'], 'list_rank': r['list_rank'],
            'group': r['group'], 'rs_pct': r.get('rs_pct'),
            'x': round(s.iloc[-1], 2), 'close': round(close, 2),
            'buy_lo': round(stop, 2), 'buy_hi': round(e + band_hi * a, 2),
            'entry': round(entry, 2), 'x_entry': round((entry - e) / a, 2),
            'stop': round(stop, 2), 'stop_pct': round((stop / entry - 1) * 100, 1),
            'target': round(target, 2), 'target_pct': round((target / entry - 1) * 100, 1),
            'x_stop': band_lo, 'x_target': round((target - e) / a, 2),
            'travel_min': round(last30.min(), 2), 'travel_max': round(last30.max(), 2),
            'travel_p25': round(last30.quantile(0.25), 2),
            'travel_p75': round(last30.quantile(0.75), 2),
            'x_30_ago': round(s.iloc[-lb - 1], 2) if len(s) > lb else None,
            'in_band_30': int(inb.sum()), 'band_squares': ''.join(map(str, inb)),
            'as_of': f'{s.index[-1]:%Y-%m-%d}',
        })
    return pd.DataFrame(rows).set_index('ticker') if rows else pd.DataFrame()


def daily_zone(x: float) -> str:
    if x < config.LMAP_DAILY_UNDER:
        return 'under'
    return 'band' if x <= config.LMAP_DAILY_ABOVE else 'above'


def classify(x: float, y: float) -> str:
    if y < 0:
        return 'lost'
    ext = y > config.LMAP_WEEKLY_EXT
    return {('band', False): 'buy', ('band', True): 'buy_stretched',
            ('above', False): 'above', ('above', True): 'ext_both',
            ('under', False): 'under', ('under', True): 'unwinding'}[
        (daily_zone(x), ext)]


def _lookup(full: pd.DataFrame, t: str):
    for s in (t, t.replace('-', '.'), t.replace('.', '-')):
        if s in full.index:
            return s
    return None


def build(full: pd.DataFrame, tickers: list, themes: dict | None = None,
          extra: pd.DataFrame | None = None):
    """-> (positions frame in list order, [not found]). `full` is the
    screener table (needs ext_21ema_atr / ext_10wsma_atr); `extra` holds the
    same columns for list tickers outside the universe (computed on the fly
    by the caller). Group = the list's theme column, else the industry."""
    src = full if extra is None else pd.concat([full, extra[~extra.index.isin(full.index)]])
    rows, missing = [], []
    for rank, t in enumerate(tickers, 1):
        s = _lookup(src, t)
        if s is None or pd.isna(src.at[s, 'ext_21ema_atr']) \
                or pd.isna(src.at[s, 'ext_10wsma_atr']):
            missing.append(t)
            continue
        r = src.loc[s]
        x, y = float(r['ext_21ema_atr']), float(r['ext_10wsma_atr'])
        rows.append({'ticker': t, 'list_rank': rank, 'x_daily21_atr': x,
                     'y_weekly10_atr': y, 'state': classify(x, y),
                     'group': (themes or {}).get(t) or r.get('industry'),
                     'close': r.get('close'), 'rs_pct': r.get('rs_pct'),
                     'sector': r.get('sector'), 'industry': r.get('industry')})
    df = pd.DataFrame(rows).set_index('ticker') if rows else pd.DataFrame(
        columns=['list_rank', 'x_daily21_atr', 'y_weekly10_atr', 'state', 'group'])
    return df, missing


def clusters(df: pd.DataFrame) -> pd.DataFrame:
    """Per group: names in the buy area / total, busiest first."""
    if not len(df):
        return pd.DataFrame(columns=['in_buy_area', 'total'])
    g = df.groupby('group', dropna=False)
    out = pd.DataFrame({'in_buy_area': g['state'].apply(lambda s: int((s == 'buy').sum())),
                        'total': g.size()})
    return out.sort_values(['in_buy_area', 'total'], ascending=False)


def _place_labels(fig, ax, pts, fontsize=7.5):
    """Greedy label placement in pixel space: per point try right, left,
    above, below and the diagonals; take the first spot that overlaps no
    placed label and no other dot (else the least-overlapping one)."""
    fig.canvas.draw()
    to_px = ax.transData.transform
    ch = fontsize * fig.dpi / 72                   # glyph height, px
    cw = 0.6 * ch                                  # monospace advance
    dots = [to_px((x, y)) for _l, x, y in pts]
    r_dot = 6
    placed = []                                    # (x0, y0, x1, y1) px

    def overlap(a, b):
        w = min(a[2], b[2]) - max(a[0], b[0])
        h = min(a[3], b[3]) - max(a[1], b[1])
        return w * h if w > 0 and h > 0 else 0.0

    # densest points first get the first pick
    order = sorted(range(len(pts)), key=lambda i: -sum(
        1 for d in dots if abs(d[0] - dots[i][0]) < 60 and abs(d[1] - dots[i][1]) < 20))
    for i in order:
        label, x, y = pts[i]
        px, py = dots[i]
        w, h = cw * len(label), ch
        g = 7
        cands = [(g, -h / 2), (-g - w, -h / 2), (-w / 2, g), (-w / 2, -g - h),
                 (g, g * 0.6), (g, -g * 0.6 - h), (-g - w, g * 0.6),
                 (-g - w, -g * 0.6 - h), (g, g + h * 0.8), (g, -g - h * 1.8)]
        best, best_cost = None, None
        for dx, dy in cands:
            box = (px + dx, py + dy, px + dx + w, py + dy + h)
            cost = sum(overlap(box, b) for b in placed)
            cost += sum(overlap(box, (d[0] - r_dot, d[1] - r_dot,
                                      d[0] + r_dot, d[1] + r_dot))
                        for j, d in enumerate(dots) if j != i)
            if best_cost is None or cost < best_cost:
                best, best_cost = (dx, dy, box), cost
            if cost == 0:
                break
        dx, dy, box = best
        placed.append(box)
        # offset points from the dot; pixel offsets -> points
        k = 72 / fig.dpi
        ax.annotate(label, (x, y), xytext=(dx * k, dy * k), textcoords='offset points',
                    ha='left', va='bottom', fontsize=fontsize, family='monospace',
                    color=INK, zorder=6)


def plot(df: pd.DataFrame, title: str, subtitle: str, path: Path):
    """The map as a PNG (matplotlib, Agg)."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyBboxPatch

    x0, x1 = config.LMAP_XLIM
    y0, y1 = config.LMAP_YLIM
    lo, hi, wext = config.LMAP_DAILY_UNDER, config.LMAP_DAILY_ABOVE, config.LMAP_WEEKLY_EXT
    n = len(df)
    zone_n = df['x_daily21_atr'].map(daily_zone).value_counts() if n else {}
    n_buy = int((df['state'] == 'buy').sum()) if n else 0

    fig, ax = plt.subplots(figsize=(14, 8.2), dpi=130)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)

    # zone washes (recessive), weekly-lost strip, buy box
    for (a, b), key in (((x0, lo), 'under'), ((lo, hi), 'band'), ((hi, x1), 'above')):
        ax.axvspan(a, b, color=ZONE_COLOR[key], alpha=0.06, lw=0, zorder=0)
    ax.axhspan(y0, 0, color='#8a8984', alpha=0.08, lw=0, zorder=0)
    ax.axhspan(wext, y1, color='#8a8984', alpha=0.08, lw=0, zorder=0)
    ax.axhline(0, color=ZONE_COLOR['under'], lw=1, alpha=0.7, zorder=1)
    ax.axhline(wext, color=INK_3, lw=1, ls=(0, (4, 3)), zorder=1)
    ax.text(x0 + 0.05, 0.06, 'WEEKLY 10-SMA', fontsize=7.5, color=INK_2,
            family='monospace', va='bottom')
    ax.text(x0 + 0.05, wext + 0.06, f'WEEKLY EXTENDED · > +{wext:g} ATR',
            fontsize=7.5, color=INK_2, family='monospace', va='bottom')
    ax.add_patch(FancyBboxPatch((lo, 0), hi - lo, wext, boxstyle='round,pad=0,rounding_size=0.06',
                                fc=ZONE_COLOR['band'], alpha=0.07, ec='none', zorder=1))
    ax.add_patch(FancyBboxPatch((lo, 0), hi - lo, wext, boxstyle='round,pad=0,rounding_size=0.06',
                                fc='none', ec=ZONE_COLOR['band'], lw=2, zorder=2))
    ax.text((lo + hi) / 2, wext - 0.3, f'THE BUY AREA · {n_buy}', ha='center',
            va='center', fontsize=10, fontweight='bold', color='white', zorder=6,
            bbox=dict(boxstyle='round,pad=0.45,rounding_size=0.9',
                      fc=ZONE_COLOR['band'], ec='none'))
    for (a, b), key, label in (((x0, lo), 'under', 'UNDER THE 21-DAY'),
                               ((lo, hi), 'band', 'IN THE 21-DAY BAND'),
                               ((hi, x1), 'above', 'ABOVE THE 21-DAY BAND')):
        cx = (a + b) / 2
        ax.text(cx, y1 - 0.2, label, ha='center', va='top', fontsize=8.5,
                fontweight='bold', color=INK_2, family='monospace')
        ax.text(cx, y1 - 0.45, f'{int(zone_n.get(key, 0)) if n else 0} of {n}',
                ha='center', va='top', fontsize=8, color=INK_3, family='monospace')

    # points: >= 8px markers with a 2px surface ring; off-scale -> edge triangle
    pts = []
    for t, r in df.iterrows():
        x, y = r['x_daily21_atr'], r['y_weekly10_atr']
        cx, cy = min(max(x, x0 + 0.04), x1 - 0.04), min(max(y, y0 + 0.08), y1 - 0.08)
        clipped = (cx, cy) != (x, y)
        ax.scatter([cx], [cy], s=62, marker='^' if clipped else 'o',
                   c=ZONE_COLOR[daily_zone(x)], edgecolors=SURFACE,
                   linewidths=2, zorder=5)
        pts.append((t + (f' ({x:+.1f}, {y:+.1f})' if clipped else ''), cx, cy))
    _place_labels(fig, ax, pts)

    ax.set_xticks(range(int(x0), int(x1) + 1))
    ax.set_xticklabels([f'{v:+d}' if v else '0' for v in range(int(x0), int(x1) + 1)])
    ax.set_yticks(range(int(y0), int(y1) + 1))
    ax.set_yticklabels([f'{v:+d}' if v else '0' for v in range(int(y0), int(y1) + 1)])
    ax.grid(color='#e6e5e0', lw=0.6, zorder=0)
    for sp in ax.spines.values():
        sp.set_visible(False)
    ax.tick_params(colors=INK_2, labelsize=8, length=0)
    ax.set_xlabel('← below · DAILY: price vs the 21-day EMA, in ATR · extended →',
                  fontsize=9, color=INK_2, family='monospace')
    ax.set_ylabel('← below · WEEKLY: price vs the 10-week SMA, in ATR · extended →',
                  fontsize=9, color=INK_2, family='monospace')
    fig.text(0.06, 0.965, title, fontsize=15, fontweight='bold', color=INK)
    fig.text(0.06, 0.935, subtitle, fontsize=9, color=INK_2)
    # legend (>= 2 series): the three daily zones + the box
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch
    handles = [Line2D([], [], marker='o', ls='', color=ZONE_COLOR['under'],
                      label=f'Under the 21-day  < {lo:g} ATR'),
               Line2D([], [], marker='o', ls='', color=ZONE_COLOR['band'],
                      label=f'In the 21-day band  {lo:g} to +{hi:g} ATR'),
               Line2D([], [], marker='o', ls='', color=ZONE_COLOR['above'],
                      label=f'Above it  > +{hi:g} ATR'),
               Patch(fc=ZONE_COLOR['band'], alpha=0.25, ec=ZONE_COLOR['band'],
                     label=f'The buy area  in the band AND weekly 0 to +{wext:g}')]
    fig.legend(handles=handles, loc='upper left', bbox_to_anchor=(0.055, 0.925),
               ncol=4, frameon=False, fontsize=8.5, labelcolor=INK_2)
    fig.subplots_adjust(left=0.06, right=0.985, top=0.86, bottom=0.08)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)
    return path


ROLE_COLOR = {'buy': ZONE_COLOR['band'], 'weakness': ZONE_COLOR['above']}
STOP_COLOR, TARGET_COLOR = '#e34948', '#2a78d6'     # palette red / blue


def plot_setups(st: pd.DataFrame, title: str, subtitle: str, path: Path):
    """"The Plan": one row per setup on the 21-EMA-in-ATR axis — travel bar,
    dot, entry→stop (solid) and entry→target (dashed), band squares."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle
    from matplotlib.transforms import blended_transform_factory

    lo, hi = config.LMAP_DAILY_UNDER, config.LMAP_DAILY_ABOVE
    x0 = config.LMAP_SETUP_XLIM[0]
    x1 = max(config.LMAP_SETUP_XLIM[1], float(st['x_target'].max()) + 0.6) if len(st) else config.LMAP_SETUP_XLIM[1]
    groups = [('buy', 'IN THE BUY AREA', 'buy'),
              ('weakness', 'ON WEAKNESS — wait for the level', 'wait for')]
    # layout: a header row per non-empty group, then one row per name
    rows, y = [], 0.0
    for role, head, _v in groups:
        g = st[st['role'] == role]
        if not len(g):
            continue
        rows.append(('head', role, f'{head} · {len(g)}', y))
        y -= 0.9
        for t, r in g.iterrows():
            rows.append(('row', role, (t, r), y))
            y -= 1.55
    h_in = max(3.5, 1.3 + 0.72 * len(rows))
    fig, ax = plt.subplots(figsize=(15, h_in), dpi=120)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)
    ax.set_xlim(x0, x1)
    ax.set_ylim(y + 0.4, 0.9)
    ax.axvspan(lo, hi, color=ZONE_COLOR['band'], alpha=0.07, lw=0, zorder=0)
    for v in (lo, hi):
        ax.axvline(v, color=ZONE_COLOR['band'], lw=1.2, zorder=1)
    ax.text((lo + hi) / 2, 0.75, 'THE BUY AREA', ha='center', va='center',
            fontsize=8, fontweight='bold', color=ZONE_COLOR['band'], family='monospace')
    lx = blended_transform_factory(ax.transAxes, ax.transData)
    lb = config.LMAP_SETUP_LOOKBACK
    for kind, role, payload, yy in rows:
        if kind == 'head':
            ax.text(x0 + 0.05, yy, payload, ha='left', va='center',
                    fontsize=9, fontweight='bold', color=ROLE_COLOR[role],
                    family='monospace')
            ax.axhline(yy - 0.35, color='#e6e5e0', lw=0.8, zorder=0)
            continue
        t, r = payload
        col = ROLE_COLOR[role]
        verb = 'buy' if role == 'buy' else 'wait for'
        # left: ticker + group
        ax.text(-0.005, yy + 0.12, t, transform=lx, ha='right', va='center',
                fontsize=10, fontweight='bold', color=INK, family='monospace')
        ax.text(-0.005, yy - 0.28, str(r['group'])[:30], transform=lx, ha='right',
                va='center', fontsize=7, color=INK_2)
        # buy range above the bar
        ax.text((lo + hi) / 2, yy + 0.42, f"{verb} {r['buy_lo']:,.2f} – {r['buy_hi']:,.2f}",
                ha='center', va='center', fontsize=7.5, fontweight='bold',
                color=col, family='monospace')
        # travel: pale min..max, solid 25-75 pct, dashed tick 30 sessions ago
        ax.plot([r['travel_min'], r['travel_max']], [yy, yy], color=col, alpha=0.2,
                lw=7, solid_capstyle='round', zorder=2)
        ax.plot([r['travel_p25'], r['travel_p75']], [yy, yy], color=col, alpha=0.6,
                lw=7, solid_capstyle='round', zorder=3)
        if pd.notna(r.get('x_30_ago')):
            ax.plot([r['x_30_ago']] * 2, [yy - 0.22, yy + 0.22], color=col, lw=1.3,
                    ls=(0, (2, 1.5)), zorder=3)
        ax.scatter([r['x']], [yy], s=70, c=col, edgecolors=SURFACE, linewidths=2, zorder=5)
        # plan line: entry -> stop (solid red), entry -> target (dashed blue)
        yl = yy - 0.36
        ax.plot([r['x_stop'], r['x_entry']], [yl, yl], color=STOP_COLOR, lw=1.3, zorder=3)
        ax.plot([r['x_entry'], r['x_target']], [yl, yl], color=TARGET_COLOR, lw=1.3,
                ls=(0, (3, 2)), zorder=3)
        ax.plot([r['x_target']] * 2, [yl - 0.08, yl + 0.08], color=TARGET_COLOR, lw=1.3)
        s_lab = f"stop {r['stop']:,.2f} · {r['stop_pct']:+.1f}%"
        t_lab = f"target {r['target']:,.2f} · {r['target_pct']:+.1f}% · {config.LMAP_SETUP_R:g}R"
        ax.text(r['x_stop'] + 0.05, yl - 0.22, s_lab, ha='left', va='center',
                fontsize=6.8, color=STOP_COLOR, family='monospace')
        # target label right-aligned at the target, unless that would run into
        # the stop label — then it starts just past the target instead
        cw = (x1 - x0) * 6.8 * 0.6 / 72 / (fig.get_figwidth() * 0.67)   # data units / char
        s_end = r['x_stop'] + 0.05 + cw * len(s_lab)
        clash = r['x_target'] - cw * len(t_lab) < s_end + 0.1
        ax.text(max(r['x_target'] + 0.08, s_end + 0.15) if clash else r['x_target'],
                yl - 0.22, t_lab,
                ha='left' if clash else 'right', va='center', fontsize=6.8,
                color=TARGET_COLOR, family='monospace')
        # right: position, squares, count
        ax.text(1.005, yy + 0.3, f"{r['x']:+.2f} ATR", transform=lx, ha='left', va='center',
                fontsize=10, fontweight='bold', color=col, family='monospace')
        sq = str(r['band_squares'])
        for k, ch in enumerate(sq):
            ax.add_patch(Rectangle((1.005 + k * 0.0042, yy - 0.08), 0.0034, 0.26,
                                   transform=lx, clip_on=False, lw=0,
                                   fc=col if ch == '1' else '#e6e5e0'))
        ax.text(1.005, yy - 0.34, f"{r['in_band_30']} of the last {lb} closed in the band",
                transform=lx, ha='left', va='center', fontsize=6.8, color=INK_2)
    ax.set_yticks([])
    ax.set_xticks(range(int(x0), int(x1) + 1))
    ax.set_xticklabels([f'{v:+d}' if v else '0' for v in range(int(x0), int(x1) + 1)])
    ax.grid(axis='x', color='#e6e5e0', lw=0.6, zorder=0)
    for sp in ax.spines.values():
        sp.set_visible(False)
    ax.tick_params(colors=INK_2, labelsize=8, length=0)
    ax.set_xlabel('distance from the 21-day EMA, in ATR', fontsize=9, color=INK_2,
                  family='monospace')
    top = 1 - 0.95 / h_in
    fig.text(0.13, 1 - 0.3 / h_in, title, fontsize=15, fontweight='bold', color=INK)
    fig.text(0.13, 1 - 0.55 / h_in, subtitle, fontsize=8.5, color=INK_2)
    fig.text(0.13, 1 - 0.78 / h_in,
             f'pale bar = the last {lb} sessions · solid = where it spent the middle '
             f'half · dashed tick = {lb} sessions ago · red = entry back to the stop · '
             f'blue dashed = entry out to the {config.LMAP_SETUP_R:g}R target · squares '
             f'= the last {lb} closes, filled when inside the band',
             fontsize=7.5, color=INK_2)
    fig.subplots_adjust(left=0.13, right=0.8, top=top, bottom=0.6 / h_in)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)
    return path

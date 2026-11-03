"""
Sustainability Ratio panels — stacked daily charts of tickers and ratios
(Market Health → Sustainability Ratio). Replaces the CSV-driven PNGs of
market_manipulation/market_charts: the user builds a layout in the
dashboard, built-in presets copy the old charts, own layouts are saved as
JSON in my_layouts/.

A panel is {'type': <PANEL_TYPES>, 'a': 'SPY', 'b': 'QQQ', 'n': 30}
('b' only for the two-leg types, 'n' only for 'Intraday N-day').

"Ratio no gaps" = both legs gap-adjusted, then A / B — market_charts'
gap_adjust.py (SR_v1.pine f_gapAdjustedPrice): from the start date on,
every overnight gap (open − prior close) is summed and taken off the close,
so only intraday moves remain. Before the start date the close is unchanged.

"Intraday spread" = Bowley's "ignores gaps" UDIs (@XLYXLP, @SPYQQQ):
100 + running sum of (A open->close % - B open->close %), 100 on the start
date. Checked on 9 Oct 2026: his daily changes XLY:XLP -0.13, QQQ:SPY -0.47
== our open->close differences to 2 decimals (a ratio of compounded
indices gives -0.11 / -0.49).

"Intraday N-day" = Bowley's @XLP30DLT: 100 + sum of the last N daily
open->close % of one ticker (XLP, N = 30); 106+ = staples bought all day
ahead of S&P tops, 94- = capitulation (python/sandBox/xlp_signal).
"""
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config
from src.data_loader import load_price_matrices

PANEL_TYPES = ('Ticker', 'Ratio', 'Ratio no gaps', 'Intraday spread',
               'Intraday N-day')
TWO_LEG = ('Ratio', 'Ratio no gaps', 'Intraday spread')
POINT_TYPES = ('Intraday spread', 'Intraday N-day')   # centred on 100
MAX_PANELS = 12
MY_LAYOUTS = config.SCREENERS_ROOT / 'my_layouts'

# moving-average overlays: (label, kind, period, color) — market_charts'
# defaults (EMA21 blue, SMA50 green, SMA150 aqua, SMA200 orange)
MAS = (('EMA21', 'EMA', 21, '#4f7cff'), ('SMA50', 'SMA', 50, '#2fae4f'),
       ('SMA150', 'SMA', 150, '#22d3ee'), ('SMA200', 'SMA', 200, '#f59e0b'))

SECTORS = ('XLK', 'XLC', 'XLY', 'XLP', 'XLE', 'XLF', 'XLV', 'XLI', 'XLB',
           'XLRE', 'XLU')


def _t(a):
    return {'type': 'Ticker', 'a': a, 'b': ''}


def _r(typ, a, b):
    return {'type': typ, 'a': a, 'b': b}


def _nday(a, n=None):
    return {'type': 'Intraday N-day', 'a': a, 'b': '',
            'n': n or config.SR_NDAY_N}


def _pair(a, b):
    """market_charts' ratio-pair chart: A · B · A/B · A/B no gaps, plus
    Bowley's intraday spread next to it for comparison."""
    return [_t(a), _t(b), _r('Ratio', a, b), _r('Ratio no gaps', a, b),
            _r('Intraday spread', a, b)]


# Every pair is stored RISK-ON FIRST (Bowley's orientation: XLY:XLP,
# QQQ:SPY), so a rising line = risk appetite. The Reading switch
# ("Defensive : risk-on") flips every two-leg panel for display — see
# oriented(); nothing is stored twice.
READINGS = ('Risk-on : defensive', 'Defensive : risk-on')

# (risk-on, defensive, risk-on name, defensive name)
PAIRS = (('XLY', 'XLP', 'discretionary', 'staples'),
         ('QQQ', 'SPY', 'Nasdaq', 'S&P'),
         ('IWF', 'IWD', 'growth', 'value'),
         ('IWO', 'IWN', 'small growth', 'small value'),
         ('MDYG', 'MDYV', 'mid growth', 'mid value'),
         ('IJT', 'IJS', 'small growth', 'small value'),
         ('XLK', 'SPY', 'tech', 'S&P'),
         ('IWM', 'QQQ', 'small caps', 'Nasdaq'),
         ('^DJT', '^DJU', 'transports', 'utilities'))


def _pair_name(a, b, na, nb):
    return f'{a} : {b} ({na} : {nb})'


PRESETS = {
    'Bowley: XLP 30-day + SPY': [_nday('XLP'), _t('SPY')],
    'Bowley: sustainability ratios': [
        _r('Intraday spread', 'QQQ', 'SPY'), _r('Intraday spread', 'IWM', 'QQQ'),
        _r('Intraday spread', 'XLY', 'XLP'), _r('Intraday spread', 'IWF', 'IWD'),
        _nday('XLP'), _t('SPY')],
    'SPY + XLY/XLP (risk appetite)': [
        _t('SPY'), {'type': 'Ratio', 'a': 'XLY', 'b': 'XLP'}],
    'Sectors (SPY + 11 SPDRs)': [_t('SPY')] + [_t(s) for s in SECTORS],
    **{_pair_name(a, b, na, nb): _pair(a, b) for a, b, na, nb in PAIRS},
}
# preset key -> its name in the defensive reading
_DEFENSIVE_NAMES = {_pair_name(a, b, na, nb): _pair_name(b, a, nb, na)
                    for a, b, na, nb in PAIRS}
_DEFENSIVE_NAMES['SPY + XLY/XLP (risk appetite)'] = 'SPY + XLP/XLY (defensive appetite)'


def defensive(reading: str) -> bool:
    return reading == READINGS[1]


def preset_label(key: str, reading: str) -> str:
    """The preset's name as shown in the chosen reading (keys stay the
    risk-on names, so the selection survives a switch)."""
    return _DEFENSIVE_NAMES.get(key, key) if defensive(reading) else key


def oriented(panels: list, reading: str) -> list:
    """Panels as drawn: in the defensive reading every two-leg panel has its
    legs swapped (Ratio -> B/A, no gaps -> B/A adjusted, spread -> mirrored
    around 100). Tickers and the N-day line are never flipped."""
    if not defensive(reading):
        return panels
    return [{**p, 'a': p['b'], 'b': p['a']} if p['type'] in TWO_LEG else p
            for p in panels]


def rising_means(panel: dict, reading: str) -> str:
    """'↑ = risk-on' / '↑ = defensive' for two-leg panels ('' otherwise)."""
    if panel['type'] not in TWO_LEG:
        return ''
    return '↑ = defensive' if defensive(reading) else '↑ = risk-on'


# ------------------------------------------------------------ layouts ----
def clean_panels(rows) -> list:
    """Editor rows -> valid panels (blank / unknown rows dropped,
    tickers upper-cased, N clamped to 2..250, at most MAX_PANELS)."""
    out = []
    for r in rows:
        typ = str(r.get('type') or '').strip()
        a = str(r.get('a') or '').strip().upper()
        b = str(r.get('b') or '').strip().upper()
        if typ not in PANEL_TYPES or not a or (typ in TWO_LEG and not b):
            continue
        pn = {'type': typ, 'a': a, 'b': b if typ in TWO_LEG else ''}
        if typ == 'Intraday N-day':
            try:
                pn['n'] = min(250, max(2, int(r.get('n') or config.SR_NDAY_N)))
            except (TypeError, ValueError):
                pn['n'] = config.SR_NDAY_N
        out.append(pn)
    return out[:MAX_PANELS]


def list_layouts() -> list:
    return sorted(p.stem for p in MY_LAYOUTS.glob('*.json'))


def load_layout(name: str) -> list | None:
    p = MY_LAYOUTS / f'{name}.json'
    try:
        return clean_panels(json.loads(p.read_text())['panels'])
    except (OSError, ValueError, KeyError, TypeError):
        return None


def save_layout(name: str, panels: list) -> Path:
    MY_LAYOUTS.mkdir(exist_ok=True)
    safe = re.sub(r'[^\w\- ]+', '_', name).strip() or 'layout'
    p = MY_LAYOUTS / f'{safe}.json'
    p.write_text(json.dumps({'panels': clean_panels(panels)}, indent=2))
    return p


def ticker_choices() -> dict:
    """Builder picker: {ticker: name} for the first config.SR_TICKER_LIST_N
    rows of downloadData_v1's indexes_tickers.csv (name may be '')."""
    try:
        df = pd.read_csv(config.SR_TICKER_LIST, header=None, skiprows=1,
                         usecols=[0, 1], names=['t', 'name'], dtype=str)
    except (OSError, ValueError):
        return {}
    df = df.dropna(subset=['t']).head(config.SR_TICKER_LIST_N)
    return {r.t.strip(): (r.name or '').strip() if isinstance(r.name, str) else ''
            for r in df.itertuples()}


def delete_layout(name: str) -> bool:
    p = MY_LAYOUTS / f'{name}.json'
    if p.exists():
        p.unlink()
        return True
    return False


# --------------------------------------------------------- calculation ----
def tickers_of(panels: list) -> list:
    return sorted({t for p in panels for t in (p['a'], p['b']) if t})


def load(tickers: list) -> dict:
    return load_price_matrices(list(tickers), use_batch=False, verbose=False)


def gap_adjust(close: pd.Series, open_: pd.Series, start) -> pd.Series:
    """Close minus the overnight gaps summed from `start` on."""
    gap = (open_ - close.shift(1)).where(close.index >= pd.Timestamp(start), 0.0)
    return close - gap.fillna(0.0).cumsum()


def intraday_pct(close: pd.Series, open_: pd.Series) -> pd.Series:
    """One bar's open->close move in % (the overnight gap left out)."""
    return (close / open_ - 1) * 100


def intraday_spread(ca, oa, cb, ob, start) -> pd.Series:
    """100 + running sum of (A − B) open->close %, == 100 on the first bar
    at / after `start`. Bars before `start` are extended backwards with the
    same daily steps, so the MAs are valid from the first bar shown."""
    d = (intraday_pct(ca, oa) - intraday_pct(cb, ob)).dropna()
    if d.empty:
        return d
    cum = d.cumsum()
    at = cum.index.searchsorted(pd.Timestamp(start))
    return 100 + cum - cum.iloc[min(at, len(cum) - 1)]


def intraday_nday(close, open_, n: int) -> pd.Series:
    """100 + sum of the last n open->close % (Bowley's @XLP30DLT)."""
    return (100 + intraday_pct(close, open_).rolling(n).sum()).dropna()


def panel_series(panel: dict, data: dict, gap_start) -> pd.Series | None:
    """The panel's daily line over the full history (None when a ticker has
    no data)."""
    c, o = data['close'], data['open']
    typ = panel['type']
    need = [panel['a']] + ([panel['b']] if typ in TWO_LEG else [])
    if any(t not in c.columns or c[t].dropna().empty for t in need):
        return None
    a = c[panel['a']].dropna()
    if typ == 'Ticker':
        return a
    if typ == 'Intraday N-day':
        return intraday_nday(a, o[panel['a']].reindex(a.index),
                             panel.get('n') or config.SR_NDAY_N)
    b = c[panel['b']].dropna()
    if typ == 'Intraday spread':
        return intraday_spread(a, o[panel['a']].reindex(a.index),
                               b, o[panel['b']].reindex(b.index), gap_start)
    if panel['type'] == 'Ratio no gaps':
        a = gap_adjust(a, o[panel['a']].reindex(a.index), gap_start)
        b = gap_adjust(b, o[panel['b']].reindex(b.index), gap_start)
    return (a / b).dropna()


def label(panel: dict) -> str:
    typ = panel['type']
    if typ == 'Ticker':
        return panel['a']
    if typ == 'Intraday N-day':
        return f"{panel['a']} {panel.get('n') or config.SR_NDAY_N}-day intraday"
    if typ == 'Intraday spread':
        return f"{panel['a']}−{panel['b']} intraday spread"
    return f"{panel['a']}/{panel['b']}" + (' no gaps' if typ == 'Ratio no gaps' else '')


def levels(panel: dict) -> tuple:
    """Fixed reference lines (value, color, dashed) — Bowley's 94 / 100 /
    106 on the N-day panel, the 100 start line on the spread."""
    if panel['type'] == 'Intraday N-day':
        lo, hi = config.SR_NDAY_LEVELS
        return ((hi, '#dc2626', False), (100, 'gray', True), (lo, '#16a34a', False))
    if panel['type'] == 'Intraday spread':
        return ((100, 'gray', True),)
    return ()


def with_mas(s: pd.Series) -> pd.DataFrame:
    """The line plus every MA overlay, MAs computed on the full history."""
    df = pd.DataFrame({'value': s})
    for name, kind, n, _ in MAS:
        df[name] = (s.ewm(span=n, adjust=False).mean() if kind == 'EMA'
                    else s.rolling(n).mean())
    return df


def status(df: pd.DataFrame, points: bool = False) -> str:
    """'above EMA21 · below SMA50 … · 1W +1.2% · 1M −3.4%' for the last bar
    (`points`: 1W / 1M as point changes — the lines centred on 100)."""
    last = df.iloc[-1]
    parts = [f"{'above' if last.value >= last[m] else 'below'} {m}"
             for m, *_ in MAS if pd.notna(last[m])]
    v = df['value']
    for tag, n in (('1W', 5), ('1M', 21)):
        if len(v) > n:
            parts.append(f'{tag} {v.iloc[-1] - v.iloc[-1 - n]:+.2f} pts' if points
                         else f'{tag} {(v.iloc[-1] / v.iloc[-1 - n] - 1) * 100:+.1f}%')
    return ' · '.join(parts)

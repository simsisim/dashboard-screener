"""
Sustainability Ratio panels — stacked daily charts of tickers and ratios
(Market Health → Sustainability Ratio). Replaces the CSV-driven PNGs of
market_manipulation/market_charts: the user builds a layout in the
dashboard, built-in presets copy the old charts, own layouts are saved as
JSON in my_layouts/.

A panel is {'type': 'Ticker' | 'Ratio' | 'Ratio no gaps', 'a': 'SPY',
'b': 'QQQ'} ('b' only for ratios).

"Ratio no gaps" = both legs gap-adjusted, then A / B — market_charts'
gap_adjust.py (SR_v1.pine f_gapAdjustedPrice): from the start date on,
every overnight gap (open − prior close) is summed and taken off the close,
so only intraday moves remain. Before the start date the close is unchanged.
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

PANEL_TYPES = ('Ticker', 'Ratio', 'Ratio no gaps')
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


def _pair(a, b):
    """market_charts' ratio-pair chart: A · B · A/B · A/B no gaps."""
    return [_t(a), _t(b), {'type': 'Ratio', 'a': a, 'b': b},
            {'type': 'Ratio no gaps', 'a': a, 'b': b}]


PRESETS = {
    'SPY + XLY/XLP (risk appetite)': [
        _t('SPY'), {'type': 'Ratio', 'a': 'XLY', 'b': 'XLP'}],
    'Sectors (SPY + 11 SPDRs)': [_t('SPY')] + [_t(s) for s in SECTORS],
    'XLP : XLY': _pair('XLP', 'XLY'),
    'SPY : QQQ': _pair('SPY', 'QQQ'),
    'IWD : IWF (value : growth)': _pair('IWD', 'IWF'),
    'IWN : IWO (small value : growth)': _pair('IWN', 'IWO'),
    'MDYG : MDYV (mid growth : value)': _pair('MDYG', 'MDYV'),
    'IJS : IJT (small value : growth)': _pair('IJS', 'IJT'),
    'SPY : XLK': _pair('SPY', 'XLK'),
    '^DJU : ^DJT (utilities : transports)': _pair('^DJU', '^DJT'),
}


# ------------------------------------------------------------ layouts ----
def clean_panels(rows) -> list:
    """Editor rows -> valid panels (blank / unknown rows dropped,
    tickers upper-cased, at most MAX_PANELS)."""
    out = []
    for r in rows:
        typ = str(r.get('type') or '').strip()
        a = str(r.get('a') or '').strip().upper()
        b = str(r.get('b') or '').strip().upper()
        if typ not in PANEL_TYPES or not a or (typ != 'Ticker' and not b):
            continue
        out.append({'type': typ, 'a': a, 'b': b if typ != 'Ticker' else ''})
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


def panel_series(panel: dict, data: dict, gap_start) -> pd.Series | None:
    """The panel's daily line over the full history (None when a ticker has
    no data)."""
    c, o = data['close'], data['open']
    need = [panel['a']] + ([panel['b']] if panel['type'] != 'Ticker' else [])
    if any(t not in c.columns or c[t].dropna().empty for t in need):
        return None
    a = c[panel['a']].dropna()
    if panel['type'] == 'Ticker':
        return a
    b = c[panel['b']].dropna()
    if panel['type'] == 'Ratio no gaps':
        a = gap_adjust(a, o[panel['a']].reindex(a.index), gap_start)
        b = gap_adjust(b, o[panel['b']].reindex(b.index), gap_start)
    return (a / b).dropna()


def label(panel: dict) -> str:
    if panel['type'] == 'Ticker':
        return panel['a']
    return f"{panel['a']}/{panel['b']}" + (' no gaps' if panel['type'] == 'Ratio no gaps' else '')


def with_mas(s: pd.Series) -> pd.DataFrame:
    """The line plus every MA overlay, MAs computed on the full history."""
    df = pd.DataFrame({'value': s})
    for name, kind, n, _ in MAS:
        df[name] = (s.ewm(span=n, adjust=False).mean() if kind == 'EMA'
                    else s.rolling(n).mean())
    return df


def status(df: pd.DataFrame) -> str:
    """'above EMA21 · below SMA50 … · 1W +1.2% · 1M −3.4%' for the last bar."""
    last = df.iloc[-1]
    parts = [f"{'above' if last.value >= last[m] else 'below'} {m}"
             for m, *_ in MAS if pd.notna(last[m])]
    v = df['value']
    for tag, n in (('1W', 5), ('1M', 21)):
        if len(v) > n:
            parts.append(f'{tag} {(v.iloc[-1] / v.iloc[-1 - n] - 1) * 100:+.1f}%')
    return ' · '.join(parts)

"""
Timing signals in the daily batch — Blue / Black Dot, PVB and ATR1 for
every universe ticker, as screener_results.csv columns, so the Screener
can filter them like any other screen (e.g. leaders -> Blue Dot).

Ages are TRADING BARS since the signal on the ticker's own bars (0 = its
latest bar), NaN = never / not in that state. ATR1's own
`atr1_days_since_signal` is calendar days; it is converted here.

PVB and ATR1 keep their incremental per-ticker caches (results/pvb_cache,
results/atr1_cache): a cold run is ~1.5 min over the universe, a daily
+1-bar run a few seconds. The caches only move forward — run_screeners
points them to separate *_asof caches for --as-of / backfill runs
(a past cut would rewind them; PVB would even return today's state).

The four `in_*` flags feed the Confluence "timing" badges, same rules
as the old on-demand Timing tab: PVB in Buy state, ATR1 uptrend, a Blue /
Black Dot on the latest bar.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from src.timing import atr1_cloud, drwish_dots, pvb  # noqa: E402

COLUMNS = [
    'in_blue_dot', 'in_black_dot', 'in_pvb_buy', 'in_atr1_uptrend',
    'blue_dot_bars_since', 'black_dot_bars_since',
    'pvb_signal', 'pvb_signal_date', 'pvb_bars_since', 'pvb_buy_bars_since',
    'pvb_performance_since_signal',
    'atr1_trend', 'atr1_signal_type', 'atr1_signal_date', 'atr1_bars_since',
    'atr1_long_bars_since', 'atr1_stop_level', 'atr1_performance_since_signal',
]


def _bars_since(events: pd.DataFrame, bar_no: pd.DataFrame) -> pd.Series:
    """Bars from the last True in `events` to each ticker's latest bar."""
    last = bar_no.where(events.fillna(False).astype(bool)).ffill().iloc[-1]
    return bar_no.iloc[-1] - last


def evaluate(data: dict, log=print) -> pd.DataFrame:
    close = data['close']
    tickers = list(close.columns)
    # running count of each ticker's own valid bars
    bar_no = close.notna().cumsum().where(close.notna()).ffill()

    out = pd.DataFrame(index=close.columns)
    out.index.name = 'ticker'

    blue, black = drwish_dots.dot_frames(data['high'], data['low'], close)
    blue &= close.notna()
    black &= close.notna()
    out['blue_dot_bars_since'] = _bars_since(blue, bar_no)
    out['black_dot_bars_since'] = _bars_since(black, bar_no)
    log(f'  -> blue dot today={int((out["blue_dot_bars_since"] == 0).sum())} '
        f'black dot today={int((out["black_dot_bars_since"] == 0).sum())}')

    p = pvb.evaluate(tickers, data)
    out['pvb_signal'] = p['pvb_signal']
    out['pvb_signal_date'] = p['pvb_signal_date']
    out['pvb_bars_since'] = p['pvb_days_since_signal']   # bar positions
    out['pvb_buy_bars_since'] = out['pvb_bars_since'].where(
        out['pvb_signal'] == 'Buy')
    out['pvb_performance_since_signal'] = p['pvb_performance_since_signal']
    log(f'  -> PVB {out["pvb_signal"].value_counts().to_dict()}')

    a = atr1_cloud.evaluate(tickers, data)
    out['atr1_trend'] = a['atr1_trend']
    out['atr1_signal_type'] = a['atr1_signal_type']
    out['atr1_signal_date'] = a['atr1_signal_date']
    bars = pd.Series(np.nan, index=out.index)
    for t, d in a['atr1_signal_date'].dropna().items():
        d = pd.Timestamp(d)
        if d in bar_no.index:
            bars[t] = bar_no[t].iloc[-1] - bar_no.at[d, t]
    out['atr1_bars_since'] = bars
    out['atr1_long_bars_since'] = bars.where(out['atr1_signal_type'] == 'Long')
    out['atr1_stop_level'] = a['atr1_stop_level']
    out['atr1_performance_since_signal'] = a['atr1_performance_since_signal']
    out['in_blue_dot'] = out['blue_dot_bars_since'] == 0
    out['in_black_dot'] = out['black_dot_bars_since'] == 0
    out['in_pvb_buy'] = out['pvb_signal'] == 'Buy'
    out['in_atr1_uptrend'] = out['atr1_trend'] == 'uptrend'
    log(f'  -> ATR1 {out["atr1_trend"].value_counts().to_dict()} | '
        f'long cross <= 10 bars: {int((out["atr1_long_bars_since"] <= 10).sum())}')
    return out[COLUMNS]

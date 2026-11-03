"""
Reversal Odds — when do the odds of a reversal increase? (docs/reversal_odds_plan.md)
Rebuilt from PrimeTrading's Lab Report board of Nov 2 2026 (public screenshots
only; settings in config.REV_*). He changed the definition between Oct 30 and
Nov 2, so every line and cut is a setting.

Inputs: QQQ daily bars. 2020 on from downloadData_v1, before that from the
one-off data_history/QQQ_pre2020.csv (fetch_qqq_history.py), levelled at the
first shared day.

- Stretch: (close - EMA21) / ATR14 (Wilder), as a z-score (σ) and percentile
  against its own last 10 years.
- Regime: SMA50 vs SMA200.
- States: stretch at or under -1.75σ = Reversal (50 above 200) or Probe (50
  below). At or over +1.75σ with 50 above 200 = Extended. Otherwise Trend
  (50 above 200) or Risk-off.
- Trigger: the close at the cut, using tonight's EMA and ATR.
- Weekly gauge: the same stretch on weekly bars against the 10-week EMA.
  Context only, never a condition.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config
from src.data_loader import load_price_matrices

STATES = ('Reversal', 'Probe', 'Extended', 'Trend', 'Risk-off')
FLAGS = ('Reversal', 'Probe', 'Extended')
_COLS = {'open': 'O', 'high': 'H', 'low': 'L', 'close': 'C'}


def load_bars() -> tuple[pd.DataFrame, bool]:
    """QQQ O/H/L/C (history file + downloadData_v1) and whether the pre-2020
    history was found. The file's prices are scaled to meet ours on the first
    shared day, because the two carry different dividend adjustments."""
    t = config.REV_TICKER
    data = load_price_matrices([t], use_batch=False, verbose=False)
    cur = pd.DataFrame({v: data[k][t] for k, v in _COLS.items()}).dropna()
    path = config.REV_HISTORY_CSV
    if not path.exists():
        return cur, False
    old = pd.read_csv(path, index_col='Date', parse_dates=True)
    old = old.rename(columns=str.lower).rename(columns=_COLS)[list(_COLS.values())]
    first = cur.index[0]
    if first not in old.index:
        return cur, False
    scaled = old.loc[old.index < first] * (cur.C.iloc[0] / old.C.loc[first])
    return pd.concat([scaled, cur]), True


def _wilder_atr(bars: pd.DataFrame, n: int) -> pd.Series:
    prev = bars.C.shift()
    tr = pd.concat([bars.H - bars.L, (bars.H - prev).abs(), (bars.L - prev).abs()],
                   axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def _stretch(bars: pd.DataFrame, base: pd.Series, window: int, min_periods: int) -> pd.DataFrame:
    """x = (close - base) / ATR, with its rolling mean, std, z and percentile."""
    atr = _wilder_atr(bars, config.REV_ATR_DAYS)
    x = (bars.C - base) / atr
    r = x.rolling(window, min_periods=min_periods)
    out = pd.DataFrame({'atr': atr, 'x': x, 'x_mean': r.mean(), 'x_std': r.std()})
    out['z'] = (x - out.x_mean) / out.x_std
    out['pct'] = r.rank(pct=True) * 100
    return out


def weekly_gauge(bars: pd.DataFrame) -> pd.DataFrame:
    """Weekly z + percentile, indexed by each week's last session (so the
    current partial week counts)."""
    week = bars.index.to_period('W-FRI')
    g = bars.groupby(week)
    w = pd.DataFrame({'O': g.O.first(), 'H': g.H.max(), 'L': g.L.min(), 'C': g.C.last()})
    base = w.C.ewm(span=config.REV_WEEKLY_EMA, adjust=False).mean()
    s = _stretch(w, base, config.REV_WINDOW_WEEKS, config.REV_MIN_WEEKS)
    s.index = g.apply(lambda d: d.index[-1]).values
    return s[['z', 'pct']].rename(columns={'z': 'z_w', 'pct': 'pct_w'})


def compute(bars: pd.DataFrame) -> pd.DataFrame:
    """Per-day model: lines, stretch, regime, state, day counters, trigger."""
    df = bars.copy()
    df['sma_fast'] = df.C.rolling(config.REV_SMA_FAST).mean()
    df['sma_slow'] = df.C.rolling(config.REV_SMA_SLOW).mean()
    df['ema'] = df.C.ewm(span=config.REV_EMA, adjust=False).mean()
    s = _stretch(df, df.ema, config.REV_WINDOW_DAYS, config.REV_MIN_DAYS)
    df = df.join(s)
    df['regime_pct'] = (df.sma_fast / df.sma_slow - 1) * 100
    df['above'] = df.sma_fast > df.sma_slow
    cut = config.REV_CUT
    df['trigger'] = df.ema + (df.x_mean - cut * df.x_std) * df.atr
    df['state'] = np.select(
        [(df.z <= -cut) & df.above, df.z <= -cut, (df.z >= cut) & df.above, df.above],
        ['Reversal', 'Probe', 'Extended', 'Trend'], 'Risk-off')
    df = df.join(weekly_gauge(bars))
    df[['z_w', 'pct_w']] = df[['z_w', 'pct_w']].ffill()
    df = df[df.z.notna() & df.sma_slow.notna()].copy()
    run = df.state.ne(df.state.shift()).cumsum()
    df['state_day'] = df.groupby(run).cumcount() + 1
    reg = df.above.ne(df.above.shift()).cumsum()
    df['regime_day'] = df.groupby(reg).cumcount() + 1
    return df


def flag_stats(model: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Forward returns on the first day each flag fires, since REV_STATS_START,
    and the same for every session (the bar a flag has to clear)."""
    c = model.C
    f20 = (c.shift(-20) / c - 1) * 100
    f60 = (c.shift(-60) / c - 1) * 100
    start = config.REV_STATS_START
    fresh = model.state.ne(model.state.shift())
    rows = []
    for name in FLAGS:
        days = model.index[(model.state == name) & fresh]
        days = days[days >= pd.Timestamp(start)]
        rows.append({'state': name, 'n': len(days), 'fwd20': f20.reindex(days).mean(),
                     'fwd60': f60.reindex(days).mean(),
                     'up20': (f20.reindex(days).dropna() > 0).mean() * 100})
    base = {'fwd20': f20.loc[start:].mean(), 'fwd60': f60.loc[start:].mean(),
            'up20': (f20.loc[start:].dropna() > 0).mean() * 100,
            'up60': (f60.loc[start:].dropna() > 0).mean() * 100}
    return pd.DataFrame(rows).set_index('state'), base


def regime_stats(model: pd.DataFrame) -> pd.DataFrame:
    """Return earned while inside each regime (yesterday's close decides today's
    return): sessions, share, CAGR, volatility, max drawdown."""
    start = config.REV_STATS_START
    ret = model.C.pct_change().loc[start:]
    held = model.above.shift().loc[start:]
    rows = []
    for name, sel in (('50 above 200', held == True),   # noqa: E712
                      ('50 below 200', held == False)):  # noqa: E712
        r = ret[sel]
        eq = (1 + r).cumprod()
        rows.append({'regime': name, 'sessions': len(r),
                     'share': len(r) / len(ret) * 100,
                     'cagr': (eq.iloc[-1] ** (252 / len(r)) - 1) * 100 if len(r) else np.nan,
                     'vol': r.std() * 252 ** 0.5 * 100,
                     'max_dd': (eq / eq.cummax() - 1).min() * 100})
    return pd.DataFrame(rows).set_index('regime')


if __name__ == '__main__':
    bars, full = load_bars()
    m = compute(bars)
    pd.set_option('display.width', 160)
    print('pre-2020 history:', full, '| bars:', len(bars), bars.index[0].date())
    print(m[['C', 'trigger', 'z', 'pct', 'z_w', 'regime_pct', 'state', 'state_day',
             'regime_day']].tail(8).round(2).to_string())
    fs, base = flag_stats(m)
    print(fs.round(2).to_string(), '\nall sessions', {k: round(v, 2) for k, v in base.items()})
    print(regime_stats(m).round(1).to_string())

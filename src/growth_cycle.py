"""
Growth Cycle — growth vs value regime model (TODO.md §6), rebuilt from
PrimeTrading's Lab Report "Growth Cycle" (only public descriptions and
screenshots; thresholds in config.GC_*).

Inputs: IWF / IWD daily bars (the growth / value ratio) and QQEW for the
forward zone stats — all in downloadData_v1.

- Structure: EMA10 of the ratio's weekly highs and weekly lows; the current
  (partial) week counts, so the band moves every day.
- Risk gate: close above the upper line = risk-on, below the lower line =
  risk-off, inside = keep the last side.
- Momentum (X): 10-day change of the ratio's gap to the upper line, 3-day
  mean, over its own 63-day std. Rising while > +0.25σ (his; ours 0.20).
- Extension (Y): how far the close is above the upper line, over that gap's
  63-day std; extended above +1.3σ.
- Zones: risk-off + fading = Risk-off, risk-off + rising = Probe,
  risk-on + rising = Ramp Up (Trim when extended), risk-on + fading =
  Reload (Hold when extended).

Calibrated against his readings: Sep 18 2026 risk-on, Oct 6 +0.73σ,
Oct 8 +0.25σ, Oct 9 Reload (test_growth_cycle.py).
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config
from src.data_loader import load_price_matrices

ZONES = ('Risk-off', 'Probe', 'Ramp Up', 'Trim', 'Hold', 'Reload')


def load_inputs(use_batch: bool = False) -> dict:
    """Daily OHLC of IWF, IWD and the stats ticker (QQEW)."""
    syms = [config.GC_GROWTH, config.GC_VALUE, config.GC_STATS_TICKER]
    return load_price_matrices(syms, use_batch=use_batch, verbose=False)


def ratio_bars(data: dict) -> pd.DataFrame:
    """Daily growth / value ratio bars: O, H, L, C (component-wise)."""
    g, v = config.GC_GROWTH, config.GC_VALUE
    out = pd.DataFrame({c[0].upper(): data[c][g] / data[c][v]
                        for c in ('open', 'high', 'low', 'close')})
    return out.dropna()


def _weekly_ema(daily: pd.Series, how: str, span: int) -> pd.Series:
    """EMA of weekly highs (how='max') or lows ('min'), valued every day with
    the current week's extreme so far as the newest weekly bar."""
    week = daily.index.to_period('W-FRI')
    partial = daily.groupby(week).cummax() if how == 'max' \
        else daily.groupby(week).cummin()
    weekly = getattr(daily.groupby(week), how)()
    alpha = 2.0 / (span + 1)
    prev = weekly.ewm(span=span, adjust=False).mean().shift(1)  # completed weeks
    prev_d = pd.Series(prev.reindex(week).values, index=daily.index)
    return (alpha * partial + (1 - alpha) * prev_d).fillna(partial)


def compute(bars: pd.DataFrame) -> pd.DataFrame:
    """Per-day model: band, gate, momentum σ, extension σ, stretch σ, zone,
    day in zone, risk-gate start date."""
    df = pd.DataFrame(index=bars.index)
    df['ratio'] = bars['C']
    df['upper'] = _weekly_ema(bars['H'], 'max', config.GC_STRUCT_WEEKS)
    df['lower'] = _weekly_ema(bars['L'], 'min', config.GC_STRUCT_WEEKS)

    above = df.ratio >= df.upper * (1 - config.GC_GATE_TOL_PCT / 100)
    side = np.where(above, 1.0,
                    np.where(df.ratio < df.lower, -1.0, np.nan))
    df['risk_on'] = pd.Series(side, index=df.index).ffill().eq(1.0)

    gap = df.ratio / df.upper - 1
    mom = gap.diff(config.GC_MOM_DAYS).rolling(config.GC_MOM_SMOOTH).mean()
    df['momentum_sigma'] = mom / mom.rolling(config.GC_SIGMA_DAYS).std()
    # Y: signed distance outside the band (0 inside), in σ of the gap
    sd = gap.rolling(config.GC_SIGMA_DAYS).std()
    df['gate_sigma'] = np.where(df.ratio > df.upper, gap / sd,
                                np.where(df.ratio < df.lower,
                                         (df.ratio / df.lower - 1) / sd, 0.0))
    df['ext_sigma'] = df.gate_sigma.clip(lower=0)
    stretch = df.ratio / df.ratio.ewm(span=config.GC_STRETCH_EMA, adjust=False).mean() - 1
    df['gap_pct'] = gap * 100
    df['stretch_pct'] = stretch * 100
    df['stretch_sigma'] = stretch / stretch.rolling(config.GC_SIGMA_DAYS).std()

    rising = df.momentum_sigma > config.GC_MOM_RISING
    extended = df.ext_sigma > config.GC_EXTENDED
    zone = np.select(
        [~df.risk_on & ~rising, ~df.risk_on & rising,
         df.risk_on & rising & extended, df.risk_on & rising,
         df.risk_on & ~rising & extended],
        ['Risk-off', 'Probe', 'Trim', 'Ramp Up', 'Hold'], 'Reload')
    df['zone'] = pd.Series(zone, index=df.index).where(df.momentum_sigma.notna())
    df = df[df.zone.notna()].copy()

    run = df.zone.ne(df.zone.shift()).cumsum()
    df['day_in_zone'] = df.groupby(run).cumcount() + 1
    gate_run = df.risk_on.ne(df.risk_on.shift()).cumsum()
    df['gate_since'] = pd.Series(df.index, index=df.index).groupby(gate_run).transform('first')
    return df


def zone_stats(model: pd.DataFrame, stats_close: pd.Series,
               start: str | None = None) -> pd.DataFrame:
    """Per zone: days, episodes, and over the next N sessions how often the
    stats ticker (QQEW) rose, its average move, and how often growth beat
    value (the ratio rose)."""
    n = config.GC_STATS_FWD
    m = model if start is None else model.loc[start:]
    px = stats_close.reindex(model.index)
    fwd_px = (px.shift(-n) / px - 1).reindex(m.index) * 100
    fwd_ratio = (model.ratio.shift(-n) / model.ratio - 1).reindex(m.index)
    episodes = m.zone.ne(m.zone.shift())
    rows = []
    for z in ZONES:
        sel = m.zone.eq(z)
        f, r = fwd_px[sel].dropna(), fwd_ratio[sel].dropna()
        rows.append({'zone': z, 'days': int(sel.sum()),
                     'episodes': int((sel & episodes).sum()),
                     'up_pct': (f > 0).mean() * 100 if len(f) else np.nan,
                     'avg_move_pct': f.mean() if len(f) else np.nan,
                     'growth_won_pct': (r > 0).mean() * 100 if len(r) else np.nan})
    return pd.DataFrame(rows).set_index('zone')


def zone_episodes(model: pd.DataFrame) -> pd.DataFrame:
    """One row per zone stint: start, end, sessions, ratio change %."""
    run_id = model.zone.ne(model.zone.shift()).cumsum()
    g = model.groupby(run_id)
    ep = pd.DataFrame({'zone': g.zone.first(),
                       'start': g.apply(lambda x: x.index[0]),
                       'end': g.apply(lambda x: x.index[-1]),
                       'sessions': g.size(),
                       'ratio_chg_pct': (g.ratio.last() / g.ratio.first() - 1) * 100})
    return ep.reset_index(drop=True)


def run(use_batch: bool = False) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load, compute, stats since config.GC_HISTORY_START."""
    data = load_inputs(use_batch)
    model = compute(ratio_bars(data))
    stats = zone_stats(model, data['close'][config.GC_STATS_TICKER],
                       config.GC_HISTORY_START)
    return model, stats


if __name__ == '__main__':
    model, stats = run()
    pd.set_option('display.width', 160)
    cols = ['ratio', 'lower', 'upper', 'risk_on', 'momentum_sigma',
            'ext_sigma', 'stretch_sigma', 'zone', 'day_in_zone']
    print(model[cols].tail(25).round(4).to_string())
    print(f'\nZone stats since {config.GC_HISTORY_START} '
          f'(next {config.GC_STATS_FWD} sessions, {config.GC_STATS_TICKER}):')
    print(stats.round(1).to_string())

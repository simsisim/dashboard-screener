"""
Growth Cycle — growth vs value regime model (TODO.md §6), rebuilt from
PrimeTrading's Lab Report "Growth Cycle" (only public descriptions and
screenshots; thresholds in config.GC_*).

Inputs: IWF / IWD daily bars (the growth / value ratio) and QQEW for the
forward zone stats — all in downloadData_v1.

- Structure: EMA10 of the ratio's weekly highs (upper), weekly lows (lower)
  and weekly closes (midline); the current (partial) week counts, so all
  three move every day.
- Risk gate: close above the upper line = risk-on, below the lower line =
  risk-off, inside = keep the last side.
- Momentum (X): 10-day change of the ratio's gap to the midline, 3-day mean,
  over its own 63-day std. Past +-0.25σ it sets rising / fading; inside that
  strip it keeps the last side.
- Gate σ (Y): how far the close is outside the band, over the 63-day std of
  the midline gap; extended above +1.3σ.
- Stretch: close vs its 21-day EMA, over that gap's 63-day std.
- Zones: risk-on + extended = Trim when stretch is also past +2σ, else Hold
  (momentum plays no part). Otherwise risk-on + rising = Ramp Up, risk-on +
  fading = Reload, risk-off + rising = Probe, risk-off + fading = Risk-off.

Calibrated against his boards (Sep 28, Oct 6-14, Oct 30, Nov 2 2026) in
test_growth_cycle.py.
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
    """EMA of weekly highs (how='max'), lows ('min') or closes ('last'), valued
    every day with the current week so far as the newest weekly bar."""
    week = daily.index.to_period('W-FRI')
    grp = daily.groupby(week)
    partial = {'max': grp.cummax, 'min': grp.cummin,
               'last': lambda: daily}[how]()
    weekly = getattr(grp, how)()
    alpha = 2.0 / (span + 1)
    prev = weekly.ewm(span=span, adjust=False).mean().shift(1)  # completed weeks
    prev_d = pd.Series(prev.reindex(week).values, index=daily.index)
    return (alpha * partial + (1 - alpha) * prev_d).fillna(partial)


def compute(bars: pd.DataFrame) -> pd.DataFrame:
    """Per-day model: band + midline, gate, momentum σ, gate σ, stretch σ, zone,
    day in zone, risk-gate start date."""
    df = pd.DataFrame(index=bars.index)
    df['ratio'] = bars['C']
    df['upper'] = _weekly_ema(bars['H'], 'max', config.GC_STRUCT_WEEKS)
    df['lower'] = _weekly_ema(bars['L'], 'min', config.GC_STRUCT_WEEKS)
    df['mid'] = _weekly_ema(bars['C'], 'last', config.GC_STRUCT_WEEKS)

    above = df.ratio >= df.upper * (1 - config.GC_GATE_TOL_PCT / 100)
    below = df.ratio < df.lower * (1 - config.GC_GATE_TOL_LOW_PCT / 100)
    side = np.where(above, 1.0, np.where(below, -1.0, np.nan))
    df['risk_on'] = pd.Series(side, index=df.index).ffill().eq(1.0)

    gap = df.ratio / df.mid - 1
    mom = gap.diff(config.GC_MOM_DAYS).rolling(config.GC_MOM_SMOOTH).mean()
    df['momentum_sigma'] = mom / mom.rolling(config.GC_SIGMA_DAYS).std()
    # inside the +-band momentum is flat and keeps the last side
    band = config.GC_MOM_BAND
    turn = np.where(df.momentum_sigma > band, 1.0,
                    np.where(df.momentum_sigma < -band, -1.0, np.nan))
    df['rising'] = pd.Series(turn, index=df.index).ffill().eq(1.0)
    df['mom_flat'] = df.momentum_sigma.abs() <= band
    # Y: signed distance outside the band (0 inside), in σ of the midline gap
    sd = gap.rolling(config.GC_SIGMA_DAYS).std()
    df['gate_sigma'] = np.where(df.ratio > df.upper, (df.ratio / df.upper - 1) / sd,
                                np.where(below, (df.ratio / df.lower - 1) / sd, 0.0))
    df['ext_sigma'] = df.gate_sigma.clip(lower=0)
    stretch = df.ratio / df.ratio.ewm(span=config.GC_STRETCH_EMA, adjust=False).mean() - 1
    df['gap_pct'] = gap * 100
    df['gap_prev_pct'] = gap.shift(config.GC_MOM_DAYS) * 100
    df['stretch_pct'] = stretch * 100
    df['stretch_sigma'] = stretch / stretch.rolling(config.GC_SIGMA_DAYS).std()

    extended = df.ext_sigma > config.GC_EXTENDED
    stretched = df.stretch_sigma > config.GC_TRIM_STRETCH
    zone = np.select(
        [df.risk_on & extended & stretched, df.risk_on & extended,
         df.risk_on & df.rising, ~df.risk_on & df.rising, ~df.risk_on],
        ['Trim', 'Hold', 'Ramp Up', 'Probe', 'Risk-off'], 'Reload')
    df['zone'] = pd.Series(zone, index=df.index).where(df.momentum_sigma.notna())
    df = df[df.zone.notna()].copy()

    run = df.zone.ne(df.zone.shift()).cumsum()
    df['day_in_zone'] = df.groupby(run).cumcount() + 1
    gate_run = df.risk_on.ne(df.risk_on.shift()).cumsum()
    df['gate_since'] = pd.Series(df.index, index=df.index).groupby(gate_run).transform('first')
    return df


def zone_stats(model: pd.DataFrame, stats_close: pd.Series,
               sessions: int | None = None) -> pd.DataFrame:
    """Per zone over the last `sessions` days: days, episodes, how often growth
    was still ahead of value GC_WON_FWD sessions later (overall and per year,
    a year needs GC_YEAR_MIN_DAYS days in the zone), and the stats ticker's
    average move over GC_WON_FWD / GC_STATS_FWD sessions + its up %."""
    m = model if sessions is None else model.tail(sessions)
    px = stats_close.reindex(model.index)
    fwd = (px.shift(-config.GC_STATS_FWD) / px - 1).reindex(m.index) * 100
    fwd_s = (px.shift(-config.GC_WON_FWD) / px - 1).reindex(m.index) * 100
    won = (model.ratio.shift(-config.GC_WON_FWD) / model.ratio - 1).reindex(m.index)
    episodes = m.zone.ne(m.zone.shift())
    years = sorted(m.index.year.unique())
    rows = []
    for z in ZONES:
        sel = m.zone.eq(z)
        f, fs, r = fwd[sel].dropna(), fwd_s[sel].dropna(), won[sel].dropna()
        row = {'zone': z, 'days': int(sel.sum()),
               'episodes': int((sel & episodes).sum()),
               'up_pct': (f > 0).mean() * 100 if len(f) else np.nan,
               'avg_move_pct': f.mean() if len(f) else np.nan,
               'avg_move_short_pct': fs.mean() if len(fs) else np.nan,
               'growth_won_pct': (r > 0).mean() * 100 if len(r) else np.nan}
        for y in years:
            ry = r[r.index.year == y]
            row[f'won_{y}'] = ((ry > 0).mean() * 100
                               if len(ry) >= config.GC_YEAR_MIN_DAYS else np.nan)
        rows.append(row)
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
    """Load, compute, stats over the last config.GC_HISTORY_SESSIONS days."""
    data = load_inputs(use_batch)
    model = compute(ratio_bars(data))
    stats = zone_stats(model, data['close'][config.GC_STATS_TICKER],
                       config.GC_HISTORY_SESSIONS)
    return model, stats


if __name__ == '__main__':
    model, stats = run()
    pd.set_option('display.width', 160)
    cols = ['ratio', 'lower', 'upper', 'risk_on', 'momentum_sigma',
            'ext_sigma', 'stretch_sigma', 'zone', 'day_in_zone']
    print(model[cols].tail(25).round(4).to_string())
    print(f'\nZone stats, last {config.GC_HISTORY_SESSIONS} sessions '
          f'(next {config.GC_STATS_FWD} sessions, {config.GC_STATS_TICKER}):')
    print(stats.round(1).to_string())

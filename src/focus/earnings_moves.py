"""
Earnings Moves — strong price moves on a report day, plus metaVolume's
"shock bar" (any big-volume gap, report or not). Feeds the 💥 Earnings Moves
tab (Signals); computed in the daily run, one row per ticker.

Two event kinds, each the ticker's LATEST event within EM_LOOKBACK_BARS:
  em_*  earnings reaction day. Report dates = qh*_date + next_earnings_date
        (financial_data_0_5.csv); the snapshot has no before-open /
        after-close flag, so the reaction day is the report session or the
        session after, whichever traded more volume.
  sb_*  shock bar (metaVolume/scripts/earnings_gap_study.py): volume >=
        SB_VOL_MULT x the average of the EM_AVG_VOL_BARS bars before it AND
        |gap| >= SB_GAP_MIN_PCT, either direction.

Columns per prefix p (all % unless noted; NaN = no event):
  {p}_date            reaction / shock day (YYYY-MM-DD)
  {p}_bars_since      trading bars from it to the latest bar (0 = latest)
  {p}_gap_pct         open vs the close before
  {p}_day_pct         close vs the close before
  {p}_vol_x           volume / average volume of the bars before it
  {p}_close_str_pct   where the day closed in its range, in the gap's
                      direction: 100 = at the high (gap up) / the low (down)
  {p}_gap_held        bool: no low (gap up) / high (gap down) since then
                      crossed the close before the gap; NA on the latest bar
  {p}_low_held        bool: no low since below the day's low (gap up) / no
                      high above its high (gap down) — Power Earnings Gap
                      stop; NA on the latest bar
  {p}_since_pct       latest close vs the day's close
  {p}_pvb             bool: PVB trigger that day — close beyond the prior
                      PVB_PRICE_BREAKOUT_PERIOD high (low), volume above the
                      prior period's highest, close above (below) the SMA
                      (src/timing/pvb.py, without its Buy/Sell state)
  {p}_vol_record      'HVE' (highest volume of all loaded history, >=
                      HVE_MIN_BARS bars) / 'HV1Y' (highest of HV1Y_BARS) / ''
em_report_date        the report date the reaction belongs to
em_day                0 = report session, 1 = the session after
sb_count              shock bars within the lookback
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
import config

METRICS = ('date', 'bars_since', 'gap_pct', 'day_pct', 'vol_x',
           'close_str_pct', 'gap_held', 'low_held', 'since_pct', 'pvb',
           'vol_record')


def _frames(data: dict) -> dict:
    """Shared per-bar matrices (Date x ticker numpy arrays)."""
    o, h, l, c, v = (data[k] for k in ('open', 'high', 'low', 'close',
                                       'volume'))
    prev_c = c.shift(1)
    avg_v = v.rolling(config.EM_AVG_VOL_BARS,
                      min_periods=config.EM_AVG_VOL_BARS).mean().shift(1)
    pb, vb = config.PVB_PRICE_BREAKOUT_PERIOD, config.PVB_VOLUME_BREAKOUT_PERIOD
    sma = c.rolling(config.PVB_TRENDLINE_LENGTH,
                    min_periods=config.PVB_TRENDLINE_LENGTH).mean()
    vol_hi = v.rolling(vb, min_periods=vb).max().shift(1)
    pvb_up = ((c > h.rolling(pb, min_periods=pb).max().shift(1))
              & (v > vol_hi) & (c > sma))
    pvb_dn = ((c < l.rolling(pb, min_periods=pb).min().shift(1))
              & (v > vol_hi) & (c < sma))
    nbar = v.notna().cumsum()
    hve = (v > v.cummax().shift(1)) & (nbar >= config.HVE_MIN_BARS)
    hv1y = v >= v.rolling(config.HV1Y_BARS,
                          min_periods=config.HV1Y_BARS).max()
    rec = np.where(hve, 'HVE', np.where(hv1y & (v > 0), 'HV1Y', ''))
    with np.errstate(invalid='ignore', divide='ignore'):
        gap = (o / prev_c - 1) * 100
    return {'o': o.to_numpy(float), 'h': h.to_numpy(float),
            'l': l.to_numpy(float), 'c': c.to_numpy(float),
            'v': v.to_numpy(float), 'pc': prev_c.to_numpy(float),
            'avg': avg_v.to_numpy(float), 'gap': gap.to_numpy(float),
            'pvb_up': pvb_up.to_numpy(), 'pvb_dn': pvb_dn.to_numpy(),
            'rec': rec, 'idx': c.index, 'cols': c.columns}


def _event(F: dict, p: int, j: int, last: int) -> dict:
    """Metrics of the event at bar p for ticker column j (last = the
    ticker's latest bar)."""
    o, h, l, c, pc = F['o'][p, j], F['h'][p, j], F['l'][p, j], F['c'][p, j], \
        F['pc'][p, j]
    up = not (F['gap'][p, j] < 0)
    rng = h - l
    pos = (c - l) / rng * 100 if rng > 0 else np.nan
    after_l, after_h = F['l'][p + 1:last + 1, j], F['h'][p + 1:last + 1, j]
    after_l, after_h = after_l[~np.isnan(after_l)], after_h[~np.isnan(after_h)]
    if len(after_l):
        gap_held = (after_l.min() > pc) if up else (after_h.max() < pc)
        low_held = (after_l.min() >= l) if up else (after_h.max() <= h)
    else:
        gap_held = low_held = pd.NA
    avg = F['avg'][p, j]
    return {
        'date': F['idx'][p].strftime('%Y-%m-%d'),
        'bars_since': last - p,
        'gap_pct': F['gap'][p, j],
        'day_pct': (c / pc - 1) * 100 if pc else np.nan,
        'vol_x': F['v'][p, j] / avg if avg and avg > 0 else np.nan,
        'close_str_pct': pos if up else 100 - pos,
        'gap_held': gap_held if gap_held is pd.NA else bool(gap_held),
        'low_held': low_held if low_held is pd.NA else bool(low_held),
        'since_pct': (F['c'][last, j] / c - 1) * 100 if c else np.nan,
        'pvb': bool(F['pvb_up'][p, j] if up else F['pvb_dn'][p, j]),
        'vol_record': F['rec'][p, j],
    }


def _table(rows: dict, index, prefix: str) -> pd.DataFrame:
    out = pd.DataFrame.from_dict(rows, orient='index').reindex(index)
    out = out.reindex(columns=[m for m in METRICS] +
                      [c for c in out.columns if c not in METRICS])
    for m in ('gap_pct', 'day_pct', 'close_str_pct', 'since_pct'):
        out[m] = pd.to_numeric(out[m]).round(2)
    out['vol_x'] = pd.to_numeric(out['vol_x']).round(2)
    for m in ('gap_held', 'low_held', 'pvb'):
        out[m] = out[m].astype('boolean')
    out.columns = [f'{prefix}_{c}' for c in out.columns]
    out.index.name = 'ticker'
    return out


def reaction_pos(idx: pd.DatetimeIndex, vol: np.ndarray, d: pd.Timestamp,
                 last: int) -> tuple:
    """(bar, day 0/1) of a report's reaction: the report session or the
    one after, whichever traded more; (None, None) when not yet traded."""
    p = int(idx.searchsorted(d))
    if p > last:
        return None, None
    if p + 1 <= last and np.nan_to_num(vol[p + 1]) > np.nan_to_num(vol[p]):
        return p + 1, 1
    return p, 0


def evaluate(data: dict, earnings: pd.DataFrame | None,
             lookback: int = None) -> pd.DataFrame:
    """em_* + sb_* columns for every ticker in data['close'];
    `earnings` = ticker x report-date columns (strings / dates)."""
    lookback = config.EM_LOOKBACK_BARS if lookback is None else lookback
    F = _frames(data)
    idx, cols = F['idx'], F['cols']
    valid = ~np.isnan(F['c'])
    em, sb, sb_n = {}, {}, {}
    shock = ((F['v'] >= config.SB_VOL_MULT * F['avg'])
             & (np.abs(F['gap']) >= config.SB_GAP_MIN_PCT))
    ed = (earnings.reindex(cols) if earnings is not None
          else pd.DataFrame(index=cols))
    for j, t in enumerate(cols):
        rows = np.flatnonzero(valid[:, j])
        if not len(rows):
            continue
        last = int(rows[-1])
        lo = last - lookback + 1
        # earnings: the latest report whose reaction falls in the window
        best = None
        for d in pd.to_datetime(ed.loc[t].dropna().to_numpy(), errors='coerce'):
            if pd.isna(d):
                continue
            p, day = reaction_pos(idx, F['v'][:, j], d, last)
            if p is not None and p >= max(lo, 1) and (best is None
                                                      or p > best[0]):
                best = (p, day, d)
        if best is not None:
            em[t] = {**_event(F, best[0], j, last),
                     'report_date': best[2].strftime('%Y-%m-%d'),
                     'day': best[1]}
        hits = np.flatnonzero(shock[max(lo, 1):last + 1, j]) + max(lo, 1)
        if len(hits):
            sb[t] = _event(F, int(hits[-1]), j, last)
            sb_n[t] = len(hits)
    out = _table(em, cols, 'em').join(_table(sb, cols, 'sb'))
    out['sb_count'] = pd.Series(sb_n, dtype=float).reindex(cols).fillna(0) \
        .astype(int)
    return out


def report_columns(fin: pd.DataFrame) -> pd.DataFrame:
    """ticker x report-date columns of the fundamentals snapshot."""
    keep = [c for c in fin.columns if c == 'next_earnings_date'
            or (c.startswith('qh') and c.endswith('_date'))]
    return fin[keep]

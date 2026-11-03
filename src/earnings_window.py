"""
Price path around earnings — after Unusual Whales' "Current vs Average
Moves Around Earnings": % change over the trading days -BEFORE..+AFTER
around one report (the "current" one) vs the average path of the N reports
before it, all measured from the same start day (`anchor`, default -BEFORE).

Report dates come from the fundamentals snapshot (next_earnings_date +
qh*_date, financial_data_0_5.csv); prices from the daily files. Day 0 = the
report's session (a weekend date -> the next session). The snapshot has no
before-open / after-close flag, so an after-close report moves on day +1.
An upcoming report (next_earnings_date) is listed once its window has begun;
its future sessions are counted in business days (holidays ignored).

build() returns plain frames; chart() draws them with Altair (Ticker detail
and Volume Records tabs).
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config

UP, DOWN, AVG = '#22c55e', '#ef4444', '#2dd4bf'


def report_dates(fin_row: pd.Series | None) -> list:
    """Unique report dates, newest first (next_earnings_date included)."""
    if fin_row is None:
        return []
    cols = [c for c in fin_row.index
            if c == 'next_earnings_date'
            or (c.startswith('qh') and c.endswith('_date'))]
    d = pd.to_datetime(fin_row[cols], errors='coerce').dropna()
    return sorted({x.normalize() for x in d}, reverse=True)


def day0_pos(idx: pd.DatetimeIndex, d: pd.Timestamp) -> int:
    """Bar position of the report session; past the last bar for a future
    report (business days, holidays ignored)."""
    if d <= idx[-1]:
        return int(idx.searchsorted(d))
    # sessions in (last bar, d), then the session at / after d
    n = np.busday_count((idx[-1] + pd.Timedelta(days=1)).date(), d.date())
    return len(idx) - 1 + int(n) + 1


def _window(daily: pd.DataFrame, pos0: int, before: int, after: int):
    """Frame indexed by day -before..+after: date, close, volume, up (close
    vs the close before); NaN where no bar (before the data / the future)."""
    days = np.arange(-before, after + 1)
    pos = pos0 + days
    ok = (pos >= 0) & (pos < len(daily))
    close = daily['Close']
    up = close.diff() >= 0
    w = pd.DataFrame(index=pd.Index(days, name='day'))
    w['date'] = pd.NaT
    w['close'] = np.nan
    w['volume'] = np.nan
    w['up'] = pd.NA
    w.loc[ok, 'date'] = daily.index[pos[ok]]
    w.loc[ok, 'close'] = close.to_numpy(dtype=float)[pos[ok]]
    w.loc[ok, 'volume'] = daily['Volume'].to_numpy(dtype=float)[pos[ok]]
    w.loc[ok, 'up'] = up.to_numpy()[pos[ok]]
    return w


def _pct(w: pd.DataFrame, anchor: int) -> pd.Series:
    return (w['close'] / w.at[anchor, 'close'] - 1) * 100


def available(daily: pd.DataFrame, reports: list,
              before: int = None) -> list:
    """Reports whose window has begun and lies inside the data, newest
    first: [(report date, day-0 position)]."""
    before = config.ER_WINDOW_BEFORE if before is None else before
    out = []
    for d in reports:
        p = day0_pos(daily.index, d)
        if 0 <= p - before < len(daily):
            out.append((d, p))
    return out


def build(daily: pd.DataFrame, reports: list, which: int = 0,
          n_avg: int = None, anchor: int = None,
          before: int = None, after: int = None) -> dict | None:
    """Current path (reports[which] of available()) + the average of the
    n_avg reports before it that have a complete window.
    Returns {'report', 'current' (frame: date close volume up pct),
    'avg' (Series by day, may be empty), 'n_used', 'anchor'}; None when
    no report is usable."""
    before = config.ER_WINDOW_BEFORE if before is None else before
    after = config.ER_WINDOW_AFTER if after is None else after
    n_avg = config.ER_AVG_QUARTERS if n_avg is None else n_avg
    anchor = -before if anchor is None else anchor
    av = available(daily, reports, before)
    if which >= len(av):
        return None
    d, p = av[which]
    cur = _window(daily, p, before, after)
    if np.isnan(cur.at[anchor, 'close']):       # start day not traded yet
        return None
    cur['pct'] = _pct(cur, anchor)
    paths = []
    for _d, _p in av[which + 1:]:
        if len(paths) >= n_avg:
            break
        w = _window(daily, _p, before, after)
        if w['close'].notna().all():
            paths.append(_pct(w, anchor))
    avg = (pd.concat(paths, axis=1).mean(axis=1) if paths
           else pd.Series(dtype=float))
    return {'report': d, 'current': cur, 'avg': avg, 'n_used': len(paths),
            'anchor': anchor}


def record_days(daily: pd.DataFrame, hve_dates=()) -> pd.Series:
    """'HVE' / 'HV1Y' by date: HVE = the given all-time-record dates (the
    HVE ladder), HV1Y = volume >= the highest of the HV1Y_BARS bars up to
    it (needs a full year of bars)."""
    v = daily['Volume']
    hv1y = (v >= v.rolling(config.HV1Y_BARS, min_periods=config.HV1Y_BARS)
            .max()) & v.gt(0)
    out = pd.Series('HV1Y', index=v.index[hv1y.to_numpy()], dtype=object)
    for d in pd.to_datetime(list(hve_dates), errors='coerce'):
        if pd.notna(d) and d in v.index:
            out[d] = 'HVE'
    return out.sort_index()


def _rows(df: pd.DataFrame) -> list:
    """JSON-safe records (NaN/NaT -> dropped by the callers already)."""
    out = df.copy()
    for c in out.columns:
        if pd.api.types.is_datetime64_any_dtype(out[c]):
            out[c] = out[c].dt.strftime('%Y-%m-%d')
    return out.to_dict('records')


def chart(data: dict, records: pd.Series | None = None, title: str = '',
          width: int = 760):
    """Altair: current (solid, green/red by its last value) vs average
    (dotted) % path, the report day marked, volume bars underneath, and
    HVE/HV1Y record days as diamonds."""
    import altair as alt

    cur = data['current'].reset_index()
    cur['date'] = pd.to_datetime(cur['date'])
    cur = cur.join(data['avg'].rename('avg'), on='day')
    traded = cur.dropna(subset=['pct'])
    last = traded['pct'].iloc[-1]
    line_col = UP if last >= 0 else DOWN
    x = alt.X('day:Q', title='trading days from the report',
              scale=alt.Scale(domain=[int(cur['day'].min()),
                                      int(cur['day'].max())], nice=False),
              axis=alt.Axis(tickMinStep=1, values=list(range(
                  int(cur['day'].min()), int(cur['day'].max()) + 1, 2))))
    y = alt.Y('val:Q', title='% from start', axis=alt.Axis(orient='right'))

    def src(df):
        return alt.Data(values=_rows(df))

    parts = [alt.Chart(src(pd.DataFrame({'val': [0.0]})))
             .mark_rule(color='gray', opacity=.5).encode(y=y)]
    if len(data['avg']):
        a = cur[['day', 'avg']].dropna().rename(columns={'avg': 'val'})
        parts.append(alt.Chart(src(a)).mark_line(
            color=AVG, strokeDash=[2, 3], strokeWidth=2).encode(x=x, y=y))
    c = traded[['day', 'pct']].rename(columns={'pct': 'val'})
    parts.append(alt.Chart(src(c)).mark_line(
        color=line_col, strokeWidth=2).encode(x=x, y=y))
    parts.append(alt.Chart(src(c.tail(1))).mark_point(
        shape='diamond', filled=True, size=70, color=line_col)
        .encode(x=x, y=y))
    marks = pd.DataFrame({'day': [0, data['anchor']],
                          't': ['Earnings', 'start']})
    if data['anchor'] == int(cur['day'].min()):
        marks = marks.iloc[:1]
    parts.append(alt.Chart(src(marks)).mark_rule(
        color='gray', strokeDash=[3, 3]).encode(x=x))
    parts.append(alt.Chart(src(marks)).mark_text(
        angle=270, align='right', baseline='bottom', dx=-4, dy=-2,
        color='gray').encode(x=x, y=alt.value(4), text='t:N'))
    if records is not None and len(records):
        r = traded[traded['date'].isin(records.index)].copy()
        if len(r):
            r['rec'] = records.reindex(r['date']).to_numpy()
            parts.append(alt.Chart(src(r[['day', 'pct', 'rec']].rename(
                columns={'pct': 'val'}))).mark_point(
                shape='triangle-up', filled=True, size=110, color='#f59e0b')
                .encode(x=x, y=y, tooltip=['rec:N', 'day:Q']))
    # invisible hover points carrying every value
    tip = cur.dropna(subset=['pct', 'avg'], how='all').copy()
    tip['val'] = tip['pct'].fillna(tip['avg'])
    tip_cols = ['day', 'date', 'val', 'pct', 'avg', 'volume']
    tip = tip[tip_cols].copy()
    tip['date'] = tip['date'].dt.strftime('%Y-%m-%d').fillna('—')
    tip = tip.astype(object).where(tip.notna(), None)
    parts.append(alt.Chart(alt.Data(values=tip.to_dict('records')))
                 .mark_point(opacity=0, size=200).encode(
        x=x, y=y, tooltip=[
            alt.Tooltip('day:Q', title='day'),
            alt.Tooltip('date:N', title='date'),
            alt.Tooltip('pct:Q', title='current %', format='+.2f'),
            alt.Tooltip('avg:Q', title='average %', format='+.2f'),
            alt.Tooltip('volume:Q', title='volume', format=',.0f')]))
    top = alt.layer(*parts).properties(width=width, height=260, title=title)

    v = traded[['day', 'volume', 'up']].dropna().copy()
    v['up'] = v['up'].map({True: 'up', False: 'down'})
    vol = alt.Chart(src(v)).mark_bar(opacity=.75).encode(
        x=alt.X('day:Q', title=None, scale=alt.Scale(
            domain=[int(cur['day'].min()), int(cur['day'].max())],
            nice=False), axis=None),
        y=alt.Y('volume:Q', title='volume',
                axis=alt.Axis(orient='right', format='~s')),
        color=alt.Color('up:N', legend=None, scale=alt.Scale(
            domain=['up', 'down'], range=[UP, DOWN])),
        tooltip=['day:Q', alt.Tooltip('volume:Q', format=',.0f')],
    ).properties(width=width, height=70)
    return alt.vconcat(top, vol, spacing=4).resolve_scale(color='independent')

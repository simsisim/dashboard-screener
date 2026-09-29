"""
Focus metric — HVE (Highest Volume Ever) records, daily.

Port of metaVolume's daily checker
(metaVolume/src/vol_daily_checker.py::check_and_update_hve): a bar sets a
new HVE when its volume beats max(baseline record, every earlier bar since
the baseline cutoff) — strictly greater, as in the source.

The baseline is NOT built here. It is metaVolume's frozen all-time record
per ticker (results/pre/historical/HVE_historical_daily.csv, 2020-01-02 ->
cutoff), copied by hand into config.VOLREC_BASELINE_DIR together with
baseline_metadata.json (whose baseline_as_of_date['daily'] is the cutoff).

Unlike metaVolume (append-only ledger + last_processed.txt), the ledger is
recomputed from the cutoff on every run: it is a pure function of the frozen
baseline and the bars after the cutoff, so a bar backfilled later is picked
up on the next run and deleting the ledger is always safe.

Guards (metaVolume has none of these):
  no_baseline       ticker absent from the baseline (joined the universe
                    after the last metaVolume rebuild)
  short_history     < config.HVE_MIN_BARS bars — IPO "records" are noise
  baseline_mismatch the baseline record's volume != today's file volume on
                    that date (> config.HVE_MATCH_TOL) — Yahoo re-adjusted
                    the history (split), so new bars aren't comparable
Only status 'ok' tickers get HVE values or ledger events.

Outputs per ticker: hve_date, hve_volume, hve_bars_since (trading bars from
the record to the latest bar, 0 = the latest bar IS a new record),
hve_count_50 (new records in the last config.HVE_RECENT_BARS bars), hve_status.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
import config

BASELINE_CSV = 'HVE_historical_daily.csv'
METADATA_JSON = 'baseline_metadata.json'


def load_baseline(baseline_dir: Path = None):
    """-> (records, cutoff). `records`: long frame (Symbol, n, date, volume)
    of every baseline HVE record, n=1 the newest = the all-time max.
    `cutoff`: last date the baseline covers (Timestamp)."""
    d = Path(baseline_dir or config.VOLREC_BASELINE_DIR)
    meta = json.loads((d / METADATA_JSON).read_text())
    cut = meta['baseline_as_of_date']
    cutoff = pd.Timestamp(cut['daily'] if isinstance(cut, dict) else cut)
    wide = pd.read_csv(d / BASELINE_CSV, dtype={'Symbol': str})
    n_max = len([c for c in wide.columns if c.startswith('HVE_date_')])
    parts = []
    for n in range(1, n_max + 1):
        p = wide[['Symbol', f'HVE_date_{n}', f'HVE_vol_{n}']].dropna()
        p.columns = ['Symbol', 'date', 'volume']
        p['n'] = n
        parts.append(p)
    records = pd.concat(parts, ignore_index=True)
    records['date'] = pd.to_datetime(records['date'])
    records['volume'] = records['volume'].astype(float)
    return records[['Symbol', 'n', 'date', 'volume']], cutoff


def _baseline_symbol(ticker: str, known: set):
    """Universe symbol -> baseline symbol (metaVolume stores BRK-A for
    the universe's BRK.A — same D6 rule as data_loader._file_candidates)."""
    for s in (ticker, ticker.replace('.', '-')):
        if s in known:
            return s
    return None


def evaluate(volume: pd.DataFrame, close: pd.DataFrame = None,
             baseline_dir: Path = None):
    """volume (Date x ticker) -> (per-ticker frame, events frame, status dict).

    events: one row per new record after the cutoff (ok tickers only):
    ticker, date, volume, prior_max, close.
    """
    records, cutoff = load_baseline(baseline_dir)
    top = records[records['n'] == 1].set_index('Symbol')
    known = set(top.index)
    tickers = volume.columns
    sym = pd.Series([_baseline_symbol(t, known) for t in tickers], index=tickers)

    base_date = pd.Series(top['date'].reindex(sym.values).values, index=tickers)
    base_vol = pd.Series(top['volume'].reindex(sym.values).values, index=tickers)

    # status guards
    bars = volume.notna().sum()
    status = pd.Series('ok', index=tickers, dtype=object)
    # the file's volume on the baseline record date — same data, so it must
    # match unless the history was re-adjusted since the baseline was built
    idx = volume.index
    on_date = pd.Series(np.nan, index=tickers)
    has = base_date.notna() & base_date.isin(idx)
    if has.any():
        pos = idx.get_indexer(base_date[has])
        col = tickers.get_indexer(base_date[has].index)
        on_date[has] = volume.to_numpy()[pos, col]
    rel = (on_date - base_vol).abs() / base_vol
    status[~(rel <= config.HVE_MATCH_TOL)] = 'baseline_mismatch'
    status[bars < config.HVE_MIN_BARS] = 'short_history'
    status[sym.isna()] = 'no_baseline'
    ok = status == 'ok'

    # new records after the cutoff: vol > max(baseline, earlier post bars)
    post = volume.loc[idx > cutoff, ok[ok].index]
    prior = post.cummax().ffill().shift(1)
    bv = base_vol[post.columns]
    prior = prior.where(prior.gt(bv, axis=1), bv, axis=1)   # NaN -> baseline
    is_rec = (post > prior) & post.notna()

    ev = is_rec.stack()
    ev = ev[ev].index.to_frame(index=False)
    ev.columns = ['date', 'ticker']
    if len(ev):
        r, c = post.index.get_indexer(ev['date']), post.columns.get_indexer(ev['ticker'])
        ev['volume'] = post.to_numpy()[r, c]
        ev['prior_max'] = prior.to_numpy()[r, c]
        if close is not None:
            cl = close.reindex(index=post.index, columns=post.columns)
            ev['close'] = cl.to_numpy()[r, c].round(4)
    events = ev.reindex(columns=['ticker', 'date', 'volume', 'prior_max', 'close']) \
        .sort_values(['date', 'ticker']).reset_index(drop=True)

    # current record per ticker: newest ledger event, else the baseline
    hve_date = base_date.where(ok)
    hve_vol = base_vol.where(ok)
    if len(events):
        last = events.groupby('ticker').last()
        hve_date.loc[last.index] = last['date']
        hve_vol.loc[last.index] = last['volume']
    # trading bars from the record date to the latest bar (common index)
    pos = pd.Series(np.nan, index=tickers)
    m = hve_date.notna()
    pos[m] = idx.searchsorted(hve_date[m])
    bars_since = (len(idx) - 1) - pos

    recent_from = idx[max(0, len(idx) - config.HVE_RECENT_BARS)]
    count = (events[events['date'] >= recent_from].groupby('ticker').size()
             .reindex(tickers).fillna(0))

    out = pd.DataFrame(index=tickers)
    out.index.name = 'ticker'
    out['hve_date'] = pd.to_datetime(hve_date).dt.strftime('%Y-%m-%d')
    out['hve_volume'] = hve_vol
    out['hve_bars_since'] = bars_since.astype('Int64')
    out['hve_count_50'] = count.where(ok).astype('Int64')
    out['hve_status'] = status

    info = {
        'baseline_cutoff': f'{cutoff:%Y-%m-%d}',
        'baseline_tickers': len(known),
        'last_bar': f'{idx.max():%Y-%m-%d}',
        'bars_after_cutoff': int(len(post.index)),
        'events': int(len(events)),
        'status_counts': status.value_counts().to_dict(),
        # recent trading dates, newest last — lets a reader turn "last N
        # bars" into a start date without loading the price panel
        'bar_dates': [f'{d:%Y-%m-%d}' for d in idx[-config.HVE_MIN_BARS:]],
        'computed_at': pd.Timestamp.now().strftime('%Y-%m-%dT%H:%M:%S'),
    }
    return out, events, info


def evaluate_hv1y(volume: pd.DataFrame) -> pd.DataFrame:
    """HV1Y (Highest Volume in 1 Year), after metaVolume's hv1y_checker:
    the highest-volume bar of the trailing config.HV1Y_BARS bars. Rolling,
    so no baseline — computed from the panel on every run.

    "HV1Y in the last N bars" == hv1y_bars_since < N: any bar that was a
    1-year high inside the window is either still the 1-year high or was
    beaten by a later bar, which is then inside the window too.

    -> hv1y_date, hv1y_volume, hv1y_bars_since (0 = the latest bar),
    hv1y_vs_prior_pct (vs the highest of the HV1Y_BARS-1 bars before it).
    NaN for tickers with < HV1Y_BARS bars (same guard as HVE's short_history).
    """
    n = config.HV1Y_BARS
    idx = volume.index
    win = volume.tail(n)
    ok = (volume.notna().sum() >= n) & win.notna().any()
    arr = win.to_numpy(dtype=float)
    pos = np.nanargmax(np.where(np.isnan(arr), -np.inf, arr), axis=0)
    cols = np.arange(volume.shape[1])
    g = len(idx) - len(win) + pos                  # position in the panel
    prior = volume.rolling(n - 1, min_periods=1).max().shift(1).to_numpy()

    out = pd.DataFrame(index=volume.columns)
    out.index.name = 'ticker'
    out['hv1y_date'] = pd.Series(idx[g].strftime('%Y-%m-%d'), index=volume.columns)
    out['hv1y_volume'] = arr[pos, cols]
    out['hv1y_bars_since'] = pd.Series(len(idx) - 1 - g, index=volume.columns)
    pr = prior[g, cols]
    pr = np.where(pr > 0, pr, np.nan)              # a zero-volume year: n/a
    out['hv1y_vs_prior_pct'] = ((arr[pos, cols] / pr - 1) * 100).round(1)
    out = out.where(ok, axis=0)
    out['hv1y_bars_since'] = out['hv1y_bars_since'].astype('Int64')
    return out


def write_ledger(events: pd.DataFrame, info: dict, ledger_dir: Path = None):
    """Overwrite the ledger (it is recomputed every run, never appended).
    HVE_incremental.csv keeps metaVolume's exact format for comparison."""
    d = Path(ledger_dir or config.VOLREC_LEDGER_DIR)
    d.mkdir(parents=True, exist_ok=True)
    e = events.copy()
    e['date'] = pd.to_datetime(e['date']).dt.strftime('%Y-%m-%d')
    e[['ticker', 'date', 'volume']].astype({'volume': 'int64'}) \
        .sort_values(['ticker', 'date']).to_csv(d / 'HVE_incremental.csv', index=False)
    e.to_csv(d / 'HVE_events.csv', index=False)
    (d / 'status.json').write_text(json.dumps(info, indent=2))


def read_status(ledger_dir: Path = None) -> dict | None:
    p = Path(ledger_dir or config.VOLREC_LEDGER_DIR) / 'status.json'
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return None


def recent_records(n_bars: int, tickers, baseline_dir: Path = None,
                   ledger_dir: Path = None) -> pd.DataFrame:
    """Every HVE record in the last `n_bars` trading bars (the latest bar
    included), baseline records and ledger events alike — a window that
    reaches back past the cutoff still sees the baseline's records.

    -> ticker (universe symbol), date, volume, prior_max (the record it
    beat; NaN for the oldest baseline record), source. Empty without a ledger.
    """
    status = read_status(ledger_dir)
    cols = ['ticker', 'date', 'volume', 'prior_max', 'source']
    if not status or not status.get('bar_dates'):
        return pd.DataFrame(columns=cols)
    dates = status['bar_dates']
    start = pd.Timestamp(dates[-min(int(n_bars), len(dates))])

    records, cutoff = load_baseline(baseline_dir)
    records = records.sort_values(['Symbol', 'n'])
    # records are newest-first per symbol: record n beat record n+1
    records['prior_max'] = records.groupby('Symbol')['volume'].shift(-1)
    base = records[(records['date'] >= start) & (records['date'] <= cutoff)]
    uni = set(tickers)
    to_uni = {s: next((c for c in (s, s.replace('-', '.')) if c in uni), None)
              for s in base['Symbol'].unique()}
    base = base.assign(ticker=base['Symbol'].map(to_uni), source='baseline')
    base = base.dropna(subset=['ticker'])

    new = pd.DataFrame(columns=cols)
    p = Path(ledger_dir or config.VOLREC_LEDGER_DIR) / 'HVE_events.csv'
    if p.exists():
        e = pd.read_csv(p, parse_dates=['date'])
        new = e[e['date'] >= start].assign(source='new (ledger)')
    out = pd.concat([new[cols], base[cols]], ignore_index=True)
    return out.sort_values(['date', 'ticker'], ascending=[False, True]) \
        .reset_index(drop=True)


def ticker_ladder(ticker: str, baseline_dir: Path = None,
                  ledger_dir: Path = None) -> pd.DataFrame:
    """One ticker's HVE record history, newest first: baseline records +
    ledger events after the cutoff. Empty frame when unknown."""
    records, _cutoff = load_baseline(baseline_dir)
    s = _baseline_symbol(ticker, set(records['Symbol']))
    base = records[records['Symbol'] == s][['date', 'volume']].assign(source='baseline')
    p = Path(ledger_dir or config.VOLREC_LEDGER_DIR) / 'HVE_events.csv'
    new = pd.DataFrame(columns=['date', 'volume', 'source'])
    if p.exists():
        e = pd.read_csv(p)
        e = e[e['ticker'] == ticker]
        new = pd.DataFrame({'date': pd.to_datetime(e['date']),
                            'volume': e['volume'], 'source': 'new (ledger)'})
    lad = pd.concat([new, base], ignore_index=True).sort_values('date', ascending=False)
    lad['date'] = lad['date'].dt.strftime('%Y-%m-%d')
    lad['volume'] = lad['volume'].astype('int64')
    return lad.reset_index(drop=True)

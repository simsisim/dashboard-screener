"""
Step-2 Filters — CLI entry point.

Runs, over the tradingview universe (~4,000 tickers):
  1ST CAT -> leaders' lists:  a) Minervini trend template
                              b) CANSLIM C-A-I (financial snapshot)
                              c) SCOOTER (SCTR) score
  2ND CAT -> focus metrics:   ATR extension vs 21EMA/40SMA, ADR%, Weinstein
                              stages 1-4 (abc), RTI, dashboard context cols
  combination ops (union/intersection/threshold) + dashboard report.

Usage:
  python3 run_screeners.py                    # full run
  python3 run_screeners.py --leaders-only
  python3 run_screeners.py --focus-only
  python3 run_screeners.py --min-scooter 95 --min-rs 80 --stages 2A,2B
  python3 run_screeners.py --no-liquidity-gate
  python3 run_screeners.py --ticker AAPL      # single-ticker detail dump
  python3 run_screeners.py --movers-only      # top movers only (~600 files)
  python3 run_screeners.py --backfill-movers  # movers for the last 250 sessions
  python3 run_screeners.py --backfill-hits    # screen hits + Confluence from old runs
  python3 run_screeners.py --catch-up         # fill missing days of the last 20 only
  python3 run_screeners.py --backfill-days 60 # recompute the last 60 sessions as of
                                              # each day -> history.db only
Screening only — NOT backtesting (intro.md).
"""
import argparse
import re
import shutil
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config
from src import combine, confluence, data_loader, indicators, report
from src.history_db import HistoryDB
from src.timing import daily as timing_daily
from src.focus import atr_extension, ma_structure, rti, stages, \
    volume_adx, volume_anomaly, volume_records
from src.leaders import adl_accumulation, canslim, cantata, \
    downtrend_reversal, ema20_pullback, gmma, gold_launch_pad, minervini, \
    qullamaggie, scooter, stockbee_movers, top_movers


def parse_args(argv=None):
    p = argparse.ArgumentParser(description='Step-2 Filters (screening)')
    p.add_argument('--leaders-only', action='store_true')
    p.add_argument('--focus-only', action='store_true',
                   help='skip leaders lists; focus gates apply to the whole universe')
    p.add_argument('--no-liquidity-gate', action='store_true',
                   help="skip the $ADV50 liquidity gate on the focus list")
    p.add_argument('--min-scooter', type=float, default=None,
                   help=f'override SCOOTER leader threshold (default {config.SCOOTER_MIN_SCORE})')
    p.add_argument('--min-rs', type=float, default=None,
                   help='override Minervini RS threshold (default 70)')
    p.add_argument('--stages', type=str, default=None,
                   help='focus-list stages, comma-separated (default 2A,2B)')
    p.add_argument('--combine', choices=['union', 'intersection'], default='union')
    p.add_argument('--ticker', type=str, default=None,
                   help='print the full metric row for one ticker')
    p.add_argument('--limit', type=int, default=None,
                   help='debug: only first N universe tickers')
    p.add_argument('--movers-only', action='store_true',
                   help='only write top movers to results/history.db')
    p.add_argument('--backfill-movers', type=int, nargs='?', default=None,
                   const=config.MOVERS_BACKFILL_SESSIONS, metavar='N',
                   help='write movers for the last N sessions '
                        f'(default {config.MOVERS_BACKFILL_SESSIONS}) and stop')
    p.add_argument('--as-of', type=str, default=None, metavar='YYYY-MM-DD',
                   help='evaluate on bars up to this date; writes ONLY '
                        'history.db (no results/ files, no HVE ledger, no movers)')
    p.add_argument('--backfill-days', type=int, default=None, metavar='N',
                   help='run --as-of for each of the last N sessions (prices '
                        'loaded once). Fundamentals are today\'s snapshot')
    p.add_argument('--catch-up', action='store_true',
                   help='only fill missing sessions of the last '
                        f'{config.HISTORY_CATCHUP_SESSIONS} into history.db '
                        '(a full run does this at the end anyway)')
    p.add_argument('--backfill-hits', action='store_true',
                   help='load screen hits + Confluence counts from every '
                        'results/YYYY-MM-DD/screener_results.csv and stop')
    return p.parse_args(argv)


def movers_step(close: pd.DataFrame | None, sessions: int) -> None:
    """Top movers for the last `sessions` -> history.db. Index members not
    in `close` (or all of them, when close is None) are loaded here."""
    members = top_movers.load_members()
    wanted = sorted(set().union(*members.values()))
    have = set() if close is None else set(close.columns)
    need = [s for s in wanted if s not in have]
    if need:
        extra = data_loader.load_price_matrices(need, verbose=False)
        close = (extra['close'] if close is None
                 else close.join(extra['close'], how='outer'))
        if extra['missing']:
            print(f'  movers: no price file for {len(extra["missing"])} '
                  f'members: {", ".join(extra["missing"][:10])}')
    df = top_movers.evaluate(close, members, sessions)
    if df.empty:
        print('  movers: nothing written (no session with enough coverage)')
        return
    db = HistoryDB()
    db.write_movers(df)
    latest = df['snapshot_date'].max()
    db.write_membership(latest, members)
    bar = f'{close.index.max():%Y-%m-%d}'
    print(f'  movers: {df["snapshot_date"].nunique()} sessions '
          f'{df["snapshot_date"].min()} -> {latest}, {len(df)} rows -> '
          f'{config.HISTORY_DB.name}')
    if latest != bar:
        print(f'  WARNING movers: latest bar {bar} skipped — fewer than '
              f'{config.MOVERS_MIN_COVERAGE:.0%} of the members have it')


def _run_bar_date(run: Path) -> str:
    """Latest bar of a results/ run: the 'span' line of its dashboard.md
    (the folder is named by run day, which can be a weekend)."""
    md = run / 'dashboard.md'
    if md.exists():
        m = re.search(r'span: \S+ -> (\d{4}-\d{2}-\d{2})', md.read_text())
        if m:
            return m.group(1)
    return run.name


def write_hits(full: pd.DataFrame, bar_date: str) -> tuple:
    """Screen flags + Confluence counts (batch badges only, so every
    session is counted the same way) -> history.db."""
    db = HistoryDB()
    flags = full[[c for c in full.columns if c.startswith('in_')]]
    n_hits = db.write_hits(bar_date, flags.astype('boolean'))
    n_cf = db.write_confluence(bar_date, confluence.compute(full, None))
    return n_hits, n_cf


def backfill_hits() -> None:
    runs = sorted(d for d in config.RESULTS_DIR.glob('20??-??-??')
                  if (d / 'screener_results.csv').exists())
    for run in runs:                  # later run of the same bar date wins
        full = pd.read_csv(run / 'screener_results.csv', index_col='ticker',
                           low_memory=False)
        bar = _run_bar_date(run)
        n, n_cf = write_hits(full, bar)
        print(f'  hits: {run.name} (bar {bar}) -> {n} screen hits, '
              f'{n_cf} confluence rows')


_PRICE_CACHE = {}


def _load_prices(tickers: list) -> dict:
    """load_price_matrices, memoised per ticker list — a backfill loads the
    ~4,000 files once, not once per session."""
    key = tuple(tickers)
    if key not in _PRICE_CACHE:
        _PRICE_CACHE[key] = data_loader.load_price_matrices(tickers)
    return _PRICE_CACHE[key]


def _as_of(data: dict, day: str) -> dict:
    """The price matrices cut at `day` (inclusive), as a run on that day
    would have seen them."""
    out = dict(data)
    for k in ('open', 'high', 'low', 'close', 'volume'):
        out[k] = data[k].loc[:day]
    return out


def _sessions(n: int) -> list:
    """The last `n` sessions with a bar for most of the universe
    (skips holes / holidays), as YYYY-MM-DD."""
    universe = data_loader.load_universe()
    close = _load_prices(universe['Symbol'].tolist())['close']
    live = close.notna().sum(axis=1)
    return [f'{d:%Y-%m-%d}' for d in close.index[live >= 0.8 * live.max()][-n:]]


def _pass_through(argv) -> list:
    """argv minus the backfill / catch-up flags (thresholds etc. stay)."""
    rest, skip = [], False
    for a in (argv if argv is not None else sys.argv[1:]):
        if skip:
            skip = False
        elif a in ('--backfill-days', '--as-of'):
            skip = True
        elif a != '--catch-up' and not a.startswith(('--backfill-days=',
                                                     '--as-of=')):
            rest.append(a)
    return rest


_IN_AS_OF = False


def run_as_of(days: list, argv=None) -> None:
    """One --as-of run per day (prices loaded once) -> history.db.

    The PVB / ATR1 caches only move forward, so past days use their own
    `<name>_asof` caches: wiped here, then filled day by day in date order
    (first day cold, ~1.5 min; every later day warm)."""
    global _IN_AS_OF
    rest = _pass_through(argv)
    names = (config.PVB_CACHE_DIR_NAME, config.ATR1_CACHE_DIR_NAME)
    for n in names:
        shutil.rmtree(config.RESULTS_DIR / f'{n}_asof', ignore_errors=True)
    config.PVB_CACHE_DIR_NAME, config.ATR1_CACHE_DIR_NAME = \
        (f'{n}_asof' for n in names)
    _IN_AS_OF = True
    try:
        for i, day in enumerate(sorted(days), 1):
            print(f'\n===== as of {day} ({i}/{len(days)}) =====')
            main(rest + ['--as-of', day])
    finally:
        config.PVB_CACHE_DIR_NAME, config.ATR1_CACHE_DIR_NAME = names
        _IN_AS_OF = False


def catch_up(argv=None) -> None:
    """Fill the sessions of the last HISTORY_CATCHUP_SESSIONS that
    history.db doesn't have yet (days off, missed runs). Saved days are
    kept; nothing older is touched."""
    have = set(HistoryDB().confluence_dates())
    missing = [d for d in _sessions(config.HISTORY_CATCHUP_SESSIONS)
               if d not in have]
    if not missing:
        print(f'history.db: last {config.HISTORY_CATCHUP_SESSIONS} sessions '
              'complete')
        return
    print(f'history.db: catching up {len(missing)} missing sessions: '
          f'{", ".join(missing)}')
    run_as_of(missing, argv)


def backfill_days(n: int, argv=None) -> None:
    """Recompute the last `n` sessions, each as of its own date, into
    history.db (screen hits + Confluence). Existing days are replaced, so
    every session is counted by the same, current screeners."""
    run_as_of(_sessions(n), argv)


def main(argv=None):
    args = parse_args(argv)
    if args.min_scooter is not None:
        config.SCOOTER_MIN_SCORE = args.min_scooter
    if args.min_rs is not None:
        config.MINERVINI_MIN_RS = args.min_rs
    if args.stages:
        config.FOCUS_STAGES = tuple(s.strip() for s in args.stages.split(','))
    if args.no_liquidity_gate:
        config.APPLY_LIQUIDITY_GATE = False

    if args.backfill_hits:
        backfill_hits()
        return
    if args.backfill_days:
        backfill_days(args.backfill_days, argv)
        return
    if args.catch_up:
        catch_up(argv)
        return
    if args.as_of and not _IN_AS_OF:      # standalone --as-of: as-of caches
        run_as_of([args.as_of], argv)
        return
    if args.backfill_movers or args.movers_only:
        movers_step(None, args.backfill_movers or config.MOVERS_STORE_SESSIONS)
        return

    universe = data_loader.load_universe()
    tickers = universe['Symbol'].tolist()
    if args.limit:
        tickers = tickers[:args.limit]
    print(f'universe: {len(tickers)} tickers')

    data = _load_prices(tickers)
    if args.as_of:
        data = _as_of(data, args.as_of)
    close = data['close']
    latest = close.index.max()
    print(f'evaluating at latest bar: {latest:%Y-%m-%d}')
    holes = [] if args.as_of else data_loader.check_missing_days(data)
    if holes:
        print('\n' + '!' * 72)
        print('WARNING: daily bars missing in the last 60 sessions — every '
              'rolling indicator')
        print('over these days is NaN (50d columns empty for ~50 sessions):')
        for day, n_missing, n_live in holes:
            print(f'  {day:%Y-%m-%d}: {n_missing} of {n_live} tickers '
                  f'({n_missing / n_live:.0%}) have no bar')
        print('Fix in downloadData_v1 (main.py --repair-from DATE), then '
              're-run.')
        print('!' * 72 + '\n')

    if not args.as_of:
        print('top movers per index -> history.db...')
        movers_step(close, config.MOVERS_STORE_SESSIONS)

    # ---------- dashboard context metrics ----------
    print('computing dashboard context (MAs, 52w, momentum, RS)...')
    ema10 = indicators.ema(close, config.DASHBOARD_MA_PERIODS['ema10'][1])
    ema21 = indicators.ema(close, config.DASHBOARD_MA_PERIODS['ema21'][1])
    sma50 = indicators.sma(close, config.DASHBOARD_MA_PERIODS['sma50'][1])
    sma200 = indicators.sma(close, config.DASHBOARD_MA_PERIODS['sma200'][1])
    high52 = indicators.rolling_high(close)
    low52 = indicators.rolling_low(close)
    mom = indicators.momentum(close)

    rs_raw = indicators.ibd_rs_raw(close)
    rs_pct = indicators.cross_sectional_percentile(rs_raw).iloc[-1]
    ud_ratio = indicators.up_down_volume_ratio(
        close, data['volume'], config.CANTATA_UD_WINDOW).iloc[-1]

    ctx = pd.DataFrame(index=close.columns)
    ctx.index.name = 'ticker'
    ctx['close'] = close.iloc[-1]
    ctx['pct_vs_10ema'] = indicators.pct_vs_ma(close, ema10).iloc[-1].round(2)
    ctx['pct_vs_21ema'] = indicators.pct_vs_ma(close, ema21).iloc[-1].round(2)
    ctx['pct_vs_50sma'] = indicators.pct_vs_ma(close, sma50).iloc[-1].round(2)
    ctx['pct_vs_200sma'] = indicators.pct_vs_ma(close, sma200).iloc[-1].round(2)
    ctx['pct_from_52w_high'] = indicators.pct_from_52w_high(close, high52).iloc[-1].round(2)
    ctx['pct_from_52w_low'] = indicators.pct_from_52w_low(close, low52).iloc[-1].round(2)
    for name, series in mom.items():
        ctx[name] = series.iloc[-1].round(2)
    # Voyage Trading Group momentum-scan columns — "% above the N-day low"
    # (Workflows tab / docs/workflows_tab.md §5)
    for col, window in config.ABOVE_LOW_WINDOWS.items():
        ctx[col] = indicators.pct_above_rolling_low(
            data['low'], close, window).iloc[-1].round(2)
    ctx['rs_pct'] = rs_pct.round(1)

    # more_screeners_3.md items (feedback_7.md): RSI filter column +
    # 52-week discrete event flags
    ctx['rsi14'] = indicators.rsi(close, config.RSI_PERIOD).iloc[-1].round(2)
    _rh = indicators.rolling_high(data['high'], config.BARS_52W)
    _rl = indicators.rolling_low(data['low'], config.BARS_52W)
    ctx['in_52w_high_breakout'] = (
        data['high'].iloc[-1] > _rh.shift(1).iloc[-1]).fillna(False).astype(bool)
    ctx['in_52w_low_breakdown'] = (
        data['low'].iloc[-1] < _rl.shift(1).iloc[-1]).fillna(False).astype(bool)
    ctx = ctx.join(universe.set_index('Symbol')[['market_cap', 'sector', 'industry',
                                                 'exchange', 'description',
                                                 'Index']].rename(
        columns={'Index': 'index_membership'}), how='left')

    results, lists, union_df = {}, {}, None

    if not args.focus_only:
        # ---------- 1st cat: leaders' lists ----------
        print('leader filter a) Minervini trend template...')
        min_df = minervini.evaluate(close, rs_pct)
        print(f'  -> {int(min_df["in_minervini"].sum())} pass {config.MINERVINI_MIN_PASS}/8')

        print('leader filter c) SCOOTER (SCTR)...')
        sco_df = scooter.compute_scores(close)
        print(f'  -> {int(sco_df["in_scooter"].sum())} >= {config.SCOOTER_MIN_SCORE}')

        print('leader filter b) CANSLIM C-A-I (financial snapshot)...')
        can_df = canslim.evaluate()
        can_df = can_df[can_df.index.isin(close.columns)]   # loaded universe only
        print(f'  -> {int(can_df["in_canslim"].sum())} C&A&I')

        print('leader filter d) CANTATA / CE (CET 0-7 + CEF 0-11)...')
        cta_df = cantata.evaluate(ctx, ud_ratio)
        print(f'  -> {int(cta_df["in_cantata"].sum())} CE >= {config.CANTATA_MIN_CE}'
              f' (of 18) | median CE {cta_df["ce_score"].median():.1f}')

        lists = {'minervini': minervini.leaders(min_df),
                 'canslim': canslim.leaders(can_df),
                 'scooter': scooter.leaders(sco_df)}
        union_df = (combine.union(lists) if args.combine == 'union'
                    else combine.intersection(lists))
        print(f'combined ({args.combine}): {len(union_df)} tickers | '
              f'{int((union_df["n_sources"] >= 2).sum())} in 2+ lists | '
              f'{int((union_df["n_sources"] == 3).sum())} in all 3')

        print('leader extra) shares-accumulation flag on union list...')
        acc = canslim.accumulation_flags(union_df.index.tolist())
        union_df = union_df.join(acc, how='left')
        for col in ('I_accumulation', 'I_shares_data'):
            union_df[col] = union_df[col].fillna(False)

        results.update({'leaders_minervini': lists['minervini'],
                        'leaders_canslim': lists['canslim'],
                        'leaders_scooter': lists['scooter'],
                        'leaders_cantata': cantata.leaders(cta_df),
                        'leaders_union': union_df})

    full = None
    if not args.leaders_only:
        # ---------- 2nd cat: focus metrics ----------
        print('focus a) ATR extension / ADR / dollar volume...')
        ext_df = atr_extension.evaluate(data['high'], data['low'], close, data['volume'])
        print('focus c) Weinstein stages...')
        stg_df = stages.evaluate(close)
        print('focus h) 21dma-structure pullback...')
        ma21s_df = ma_structure.evaluate(data['high'], data['low'], close)
        print(f'  -> pullback={int(ma21s_df["in_21dma_pullback"].sum())} '
              f'| zones {ma21s_df.loc[ma21s_df["in_21dma_pullback"], "ma21s_zone"].value_counts().to_dict()}')
        print('focus d) RTI...')
        rti_df = rti.evaluate(data['high'], data['low'], close)
        print('leaders d) Stockbee Movers (9M / weekly / daily gainers)...')
        stb_df = stockbee_movers.evaluate(data['open'], data['high'],
                                          data['low'], close, data['volume'])
        print(f'  -> 9m={int(stb_df["in_9m_movers"].sum())} '
              f'weekly={int(stb_df["in_weekly_movers"].sum())} '
              f'daily={int(stb_df["in_daily_gainers"].sum())}')
        print('leaders e) Golden Launch Pad...')
        glp_df = gold_launch_pad.evaluate(close)
        print(f'  -> glp={int(glp_df["in_gold_launch_pad"].sum())} '
              f'(strong={int(glp_df["glp_strong"].sum())})')
        print('focus e) volume + ADX columns (VROC/ADTV/MFI/ADX)...')
        vadx_df = volume_adx.evaluate(data['high'], data['low'], close,
                                      data['volume'])
        print('leaders f) GMMA state...')
        gmma_df = gmma.evaluate(close)
        print('  ->', gmma_df['gmma_state'].value_counts().to_dict())
        print('leaders g) Qullamaggie Suite...')
        atr14 = indicators.wilder_atr(data['high'], data['low'], close,
                                      config.ATR_PERIOD)
        qulla_df = qullamaggie.evaluate(close, data['high'], data['low'],
                                        atr14, ctx['market_cap'])
        print(f'  -> qulla={int(qulla_df["in_qullamaggie"].sum())} '
              f'(ma_stack={int(qulla_df["qulla_ma_stack"].sum())})')

        print('focus f) volume anomaly (3-sigma spike)...')
        van_df = volume_anomaly.evaluate(data['volume'])
        print(f'  -> anomaly={int(van_df["in_volume_anomaly"].sum())}')
        print('focus g) HVE + HV1Y volume records (baseline + ledger since cutoff)...')
        hve_df, hve_events, hve_info = volume_records.evaluate(data['volume'],
                                                               close)
        if args.limit is None and not args.as_of:   # partial / past runs
            volume_records.write_ledger(hve_events, hve_info)  # must not clobber it
        hv1y_df = volume_records.evaluate_hv1y(data['volume'])
        # price behaviour around / since the record day + earnings-driven
        # flag (Volume Records tab: Direction, post-earnings base)
        _fin = data_loader.load_financial_data()
        _er = _fin[[c for c in _fin.columns if re.fullmatch(r'qh\d+_date', c)]]
        for _df, _p in ((hve_df, 'hve'), (hv1y_df, 'hv1y')):
            _m = volume_records.record_metrics(
                close, data['high'], data['low'], _df[f'{_p}_date'], _p, _er)
            _df[_m.columns] = _m
        print(f'  -> HV1Y on the latest bar: '
              f'{int((hv1y_df["hv1y_bars_since"] == 0).sum())}')
        print(f'  -> cutoff {hve_info["baseline_cutoff"]}, '
              f'{hve_info["bars_after_cutoff"]} bars after, '
              f'{hve_info["events"]} new records | '
              f'status {hve_info["status_counts"]}')
        print('leaders i) EMA20 pullback + Downtrend reversal...')
        ema20_df = ema20_pullback.evaluate(close, data['open'],
                                           data['low'], sco_df['scooter_score'])
        dtrev_df = downtrend_reversal.evaluate(data['high'])
        print(f'  -> ema20_pullback={int(ema20_df["in_ema20_pullback"].sum())} '
              f'downtrend_reversal={int(dtrev_df["in_downtrend_reversal"].sum())}')

        print('leaders h) ADL accumulation (5-step)...')
        adl_df = adl_accumulation.evaluate(data['high'], data['low'], close,
                                           data['volume'])
        print(f'  -> adl={int(adl_df["in_adl_accumulation"].sum())}')

        parts = [ext_df, stg_df, ma21s_df, rti_df, stb_df, glp_df, vadx_df,
                 gmma_df, qulla_df, van_df, hve_df, hv1y_df, adl_df, ema20_df,
                 dtrev_df]
        print('timing) Blue/Black Dot, PVB, ATR1 (incremental caches)...')
        parts.append(timing_daily.evaluate(data))
        full = ctx.join(parts, how='left')

        if not args.focus_only:
            full = full.join(min_df[['minervini_count']], how='left')
            full = full.join(sco_df[['scooter_score']], how='left')
            full = full.join(can_df[['C_pass', 'A_pass', 'I_pass', 'canslim_score']], how='left')
            full = full.join(cta_df, how='left')          # CANTATA CET/CEF/CE
            full = full.join(union_df[['in_minervini', 'in_canslim', 'in_scooter',
                                       'sources', 'n_sources',
                                       'I_accumulation', 'I_shares_data']], how='left')
            for col in ('in_minervini', 'in_canslim', 'in_scooter',
                        'in_cantata', 'I_accumulation', 'I_shares_data'):
                full[col] = full[col].astype('boolean').fillna(False).astype(bool)

        # ---------- focus list: gates ----------
        base = full
        if not args.focus_only:
            base = full[full['n_sources'].fillna(0) >= 1]
        gates = base['stage'].isin(config.FOCUS_STAGES)
        gates &= ~base['very_extended'].fillna(False)
        if config.APPLY_LIQUIDITY_GATE:
            gates &= base['liquidity_pass'].fillna(False)
        sort_col = 'scooter_score' if 'scooter_score' in base.columns else 'rs_pct'
        focus_df = base[gates.fillna(False)].sort_values(sort_col, ascending=False)
        print(f'focus list: {len(focus_df)} tickers after gates '
              f'(base pool: {len(base)})')

        results.update({'focus': focus_df,
                        'stage_distribution': stg_df['stage'].value_counts().sort_index()})

        if args.limit is None:        # a partial universe must not clobber it
            n, n_cf = write_hits(full, f'{latest:%Y-%m-%d}')
            print(f'history.db ({latest:%Y-%m-%d}): {n} screen hits, '
                  f'{n_cf} confluence rows')
        if args.as_of:                # past session: history.db only
            return
        out = report.run_dir()
        full.to_csv(out / 'screener_results.csv')
        focus_df.to_csv(out / 'focus_list.csv')

    if args.as_of:
        return
    if not args.focus_only:
        out = report.run_dir()
        lists['minervini'].to_csv(out / 'leaders_minervini.csv')
        lists['canslim'].to_csv(out / 'leaders_canslim.csv')
        lists['scooter'].to_csv(out / 'leaders_scooter.csv')
        cantata.leaders(cta_df).to_csv(out / 'leaders_cantata.csv')
        union_df.to_csv(out / 'leaders_all.csv')

    uni_meta = {'n_universe': len(tickers), 'n_loaded': len(data['meta']),
                'missing': data['missing'], 'short': data['short'],
                'span': f'{close.index.min():%Y-%m-%d} -> {close.index.max():%Y-%m-%d}'}
    out = report.run_dir()
    text = report.write_dashboard(out / 'dashboard.md', uni_meta, results)
    print('\n' + text)
    print(f'outputs -> {out}')

    # days off / missed runs: fill the gaps of the last N sessions
    if (args.limit is None and not args.leaders_only and not args.focus_only):
        catch_up(argv)

    if args.ticker:
        t = args.ticker.upper()
        src_df = full if full is not None else (
            union_df if union_df is not None else None)
        if src_df is not None and t in src_df.index:
            print(f'\n--- {t} detail ---')
            print(src_df.loc[[t]].T.to_string())
        else:
            print(f'\n{t}: not in results (missing data, or --leaders-only '
                  f'and not on a leaders list)')


if __name__ == '__main__':
    main()

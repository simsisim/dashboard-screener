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
Screening only — NOT backtesting (intro.md).
"""
import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config
from src import combine, data_loader, indicators, report
from src.focus import atr_extension, rti, stages, volume_adx, \
    volume_anomaly
from src.leaders import adl_accumulation, canslim, cantata, \
    downtrend_reversal, ema20_pullback, gmma, gold_launch_pad, minervini, \
    qullamaggie, scooter, stockbee_movers


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
    return p.parse_args(argv)


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

    universe = data_loader.load_universe()
    tickers = universe['Symbol'].tolist()
    if args.limit:
        tickers = tickers[:args.limit]
    print(f'universe: {len(tickers)} tickers')

    data = data_loader.load_price_matrices(tickers)
    close = data['close']
    latest = close.index.max()
    print(f'evaluating at latest bar: {latest:%Y-%m-%d}')

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

        full = ctx.join([ext_df, stg_df, rti_df, stb_df, glp_df, vadx_df,
                         gmma_df, qulla_df, van_df, adl_df, ema20_df,
                         dtrev_df], how='left')

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

        out = report.run_dir()
        full.to_csv(out / 'screener_results.csv')
        focus_df.to_csv(out / 'focus_list.csv')

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

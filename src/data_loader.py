"""
Data loader — universe + merged daily bars into wide Date×ticker matrices.

Sources (downloadData_v1, consumed in place):
- universe:   user_input/tradingview_universe.csv (~4,000 tickers + sector/
              industry/market cap metadata)
- daily bars: data/market_data/daily/archive/{SYM}.csv (2020-01->2025-12) +
              data/market_data/daily/current/{SYM}.csv (2026-01->today),
              contiguous, no overlap; optionally extended by the newest
              market_data_batch/daily/prices_1d_*.csv files.
- symbol mapping: universe 'BRK.A' -> file 'BRK-A.csv' ('.'->'-' fallback);
              unmatched tickers are skipped and reported.

Output convention (the test_scooter vectorized pattern): one wide Close
DataFrame (index=Date, columns=ticker) plus companion Open/High/Low/Volume
matrices, so every filter runs vectorized over the whole universe.
"""
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config

_OHLCV = ('Open', 'High', 'Low', 'Close', 'Volume')


def _file_candidates(symbol: str) -> tuple:
    """Daily-file stem candidates for a universe symbol (D6 in the plan)."""
    return (symbol, symbol.replace('.', '-'))


def load_universe() -> pd.DataFrame:
    """Universe list with metadata: Symbol, sector, industry, marketCap, exchange."""
    df = pd.read_csv(config.UNIVERSE_CSV)
    df = df.rename(columns={
        'Market capitalization': 'market_cap',
        'Sector': 'sector', 'Industry': 'industry', 'Exchange': 'exchange',
        'Description': 'description',
    })
    df['Symbol'] = df['Symbol'].astype(str).str.strip()
    return df.drop_duplicates(subset='Symbol')


def _read_daily_file(path: Path) -> pd.DataFrame | None:
    try:
        df = pd.read_csv(path, usecols=['Date'] + list(_OHLCV), low_memory=False)
    except (ValueError, pd.errors.EmptyDataError, pd.errors.ParserError):
        return None
    df['Date'] = pd.to_datetime(df['Date'], utc=True, errors='coerce')
    df = df.dropna(subset=['Date'])
    df['Date'] = df['Date'].dt.tz_localize(None).dt.normalize()
    df = df.drop_duplicates(subset='Date').set_index('Date').sort_index()
    for col in _OHLCV:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    # dead bars: zero volume AND zero range at a flat close are common for
    # delisted/merged names near the file tail; keep them (price is still
    # valid) — filters handle NaN, not zeros.
    return df


def load_price_matrices(tickers: list, use_batch: bool = True,
                        verbose: bool = True) -> dict:
    """
    Build wide OHLCV matrices for `tickers`.

    Returns dict with keys open/high/low/close/volume (Date×ticker DataFrames),
    'meta' (per-ticker: bars, first/last date), 'missing' (no file found),
    'short' (fewer than MIN_BARS_TEMPLATE bars).
    """
    frames = {k: {} for k in _OHLCV}
    meta, missing, short = {}, [], []
    archive, current = config.DAILY_ARCHIVE, config.DAILY_CURRENT

    batch_frames = []
    if use_batch:
        batch_dir = config.MARKET_DATA_BATCH_DAILY
        if batch_dir.exists():
            for f in sorted(batch_dir.glob('prices_1d_*.csv')):
                try:
                    b = pd.read_csv(f, low_memory=False)
                except Exception:
                    continue
                date_col = 'Date' if 'Date' in b.columns else b.columns[0]
                sym_col = 'Symbol' if 'Symbol' in b.columns else None
                if sym_col is None:
                    continue
                b = b.rename(columns={date_col: 'Date', sym_col: 'Symbol'})
                b['Date'] = pd.to_datetime(b['Date'], utc=True, errors='coerce')
                b['Date'] = b['Date'].dt.tz_localize(None).dt.normalize()
                keep = [c for c in ['Date', 'Symbol'] + list(_OHLCV) if c in b.columns]
                b = b[keep].dropna(subset=['Date']).drop_duplicates(subset=['Date', 'Symbol'])
                batch_frames.append(b.set_index(['Date', 'Symbol']))

    batch = (pd.concat(batch_frames).sort_index() if batch_frames else None)
    last_archive_date = None

    for i, sym in enumerate(tickers):
        path = None
        for stem in _file_candidates(sym):
            p_current = current / f'{stem}.csv'
            p_archive = archive / f'{stem}.csv'
            if p_current.exists() or p_archive.exists():
                path = (p_archive if p_archive.exists() else None,
                        p_current if p_current.exists() else None)
                break
        if path is None:
            missing.append(sym)
            continue

        parts = [df for df in (_read_daily_file(path[0]), _read_daily_file(path[1]))
                 if df is not None]
        if not parts:
            missing.append(sym)
            continue
        df = pd.concat(parts)
        df = df[~df.index.duplicated(keep='last')].sort_index()
        last_archive_date = df.index.max()

        if batch is not None:
            try:
                b = batch.xs(sym.replace('.', '-'), level='Symbol')
            except KeyError:
                try:
                    b = batch.xs(sym, level='Symbol')
                except KeyError:
                    b = None
            if b is not None and len(b):
                tail_from = df.index.max()
                b = b[b.index > tail_from]
                if len(b):
                    b = b.reindex(columns=list(_OHLCV)).astype(float)
                    df = pd.concat([df, b])

        if len(df) < config.MIN_BARS_TEMPLATE:
            short.append(sym)
        for col in _OHLCV:
            frames[col][sym] = df[col]
        meta[sym] = {'bars': len(df), 'first': df.index.min(), 'last': df.index.max()}

    matrices = {k: pd.DataFrame(v).sort_index() for k, v in frames.items()}
    if verbose:
        print(f'loaded {len(meta)} tickers '
              f'({len(missing)} missing, {len(short)} short history)')
        if meta:
            spans = pd.DataFrame(meta).T
            print(f'date span: {spans["first"].min():%Y-%m-%d} -> '
                  f'{spans["last"].max():%Y-%m-%d}')
    return {'open': matrices['Open'], 'high': matrices['High'],
            'low': matrices['Low'], 'close': matrices['Close'],
            'volume': matrices['Volume'], 'meta': meta,
            'missing': missing, 'short': short}


def load_financial_data() -> pd.DataFrame:
    """CANSLIM fundamentals snapshot (financial_data_0_8.csv), ticker-indexed."""
    df = pd.read_csv(config.FIN_DATA_CSV, low_memory=False)
    return df.set_index('ticker')


def load_shares_outstanding(symbol: str) -> pd.Series | None:
    """Shares-outstanding history for one symbol ('.'->'-' mapping)."""
    for stem in _file_candidates(symbol):
        p = config.MARKET_DATA_SHARES / f'{stem}.csv'
        if p.exists():
            df = pd.read_csv(p, parse_dates=['Date'])
            return df.set_index('Date')['SharesOutstanding'].sort_index()
    return None

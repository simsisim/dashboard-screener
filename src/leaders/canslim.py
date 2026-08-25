"""
Leader filter b) — CANSLIM, C-A-I only (intro.md: "only focus on CA**I* —
they are the only one that can be filtered by using financial data").

  C — Current quarterly EPS: latest quarter's diluted EPS >= +25% vs the
      same fiscal season one year earlier (q1_eps vs q5_eps; q1 = most
      recent quarter — verified against get_financial_data.py's extraction
      order, with a runtime q1_date > q5_date check). Acceleration flag
      compares q1-YoY with yfinance's earningsQuarterlyGrowth (its own
      prior-quarter YoY field; approximate since q6 is not collected).
  A — Annual EPS growth: diluted EPS CAGR over the last 3 fiscal years
      (y1_eps vs y4_eps) >= +25%/yr; net-income CAGR fallback.
  I — Institutional sponsorship: heldPercentInstitutions >= 5% (level;
      quarter-over-quarter fund counts are not in the snapshot), plus an
      accumulation FLAG from shares_outstanding: flat/shrinking share count
      over the last ~90 days.

Data: downloadData_v1/data/fin_data/financial_data_0_8.csv (3,813 tickers,
snapshot 2026-08-21) — no network access. O'Neil thresholds (25% C, 25% A)
are the canonical "How to Make Money in Stocks" values.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
import config
from src import data_loader


def _num(s):
    return pd.to_numeric(s, errors='coerce')


def _yoy(latest, year_ago):
    latest, year_ago = _num(latest), _num(year_ago)
    valid = latest.notna() & year_ago.notna()
    out = pd.Series(np.nan, index=latest.index)
    out[valid] = (latest[valid] / year_ago[valid].replace(0, np.nan)) - 1.0
    # negative base -> YoY sign flips are meaningless for loss-makers; O'Neil
    # convention: require positive BOTH periods for a clean C pass.
    out[~(_num(latest) > 0) | ~(_num(year_ago) > 0)] = np.nan
    return out


def _cagr(latest, years_ago, n_years):
    latest, years_ago = _num(latest), _num(years_ago)
    valid = latest.notna() & years_ago.notna() & (years_ago > 0) & (latest > 0)
    out = pd.Series(np.nan, index=latest.index)
    out[valid] = (latest[valid] / years_ago[valid]) ** (1.0 / n_years) - 1.0
    return out


def evaluate(verbose: bool = True) -> pd.DataFrame:
    """
    Returns a per-ticker DataFrame with C/A/I booleans, values, canslim_score
    (0-3) and in_canslim membership.
    """
    fin = data_loader.load_financial_data()
    out = pd.DataFrame(index=fin.index)
    out.index.name = 'ticker'

    # ---- C: latest quarterly diluted EPS YoY (q1 vs q5 = 4 quarters apart) --
    q1, q5 = fin.get('q1_eps'), fin.get('q5_eps')
    c_yoy = _yoy(q1, q5)
    # base-EPS floor: a $0.001 -> $0.50 jump is +49,900% — noise, not O'Neil's
    # "meaningful" earnings improvement
    base_ok = _num(q5) >= config.CANSLIM_C_MIN_BASE_EPS
    c_yoy = c_yoy.where(base_ok)
    # runtime ordering check (q1 must be MORE recent than q5)
    try:
        d1 = pd.to_datetime(fin.get('q1_date'), errors='coerce')
        d5 = pd.to_datetime(fin.get('q5_date'), errors='coerce')
        bad = (d1.notna() & d5.notna() & (d1 <= d5))
        if bad.any():
            c_yoy[bad] = np.nan
            if verbose:
                print(f'CANSLIM: q1_date<=q5_date on {bad.sum()} tickers -> C set NaN')
    except Exception:
        pass
    # fallback: yfinance's own YoY growth field (no base info available)
    fallback = _num(fin.get('earningsQuarterlyGrowth'))
    c_yoy = c_yoy.fillna(fallback)
    out['C_yoy'] = (c_yoy * 100).round(1)
    out['C_pass'] = c_yoy >= config.CANSLIM_C_MIN_YOY

    # acceleration flag (approximate): q1-YoY vs yfinance prior-quarter YoY
    eqg = _num(fin.get('earningsQuarterlyGrowth'))
    out['C_accelerating'] = np.where(c_yoy.notna() & eqg.notna(),
                                     c_yoy > eqg, np.nan)

    # ---- A: annual diluted EPS CAGR y1 -> y4 (3 years), NI fallback ---------
    a_eps = _cagr(fin.get('y1_eps'), fin.get('y4_eps'), 3)
    a_ni = _cagr(fin.get('y1_net_income'), fin.get('y4_net_income'), 3)
    a_cagr = a_eps.fillna(a_ni)
    out['A_cagr'] = (a_cagr * 100).round(1)
    out['A_pass'] = a_cagr >= config.CANSLIM_A_MIN_CAGR

    # ---- I: institutional sponsorship level + shares-outstanding flag ------
    # NOTE: with a single snapshot, I is the weakest-filterable of C-A-I —
    # the level gate is a sanity bar (median inst% in this universe is ~82%),
    # not a differentiator; the accumulation flag below is the informative
    # part. inst_pct can exceed 100 in yfinance (summed holder categories) —
    # a known data quirk, reported as-is.
    inst = _num(fin.get('heldPercentInstitutions'))
    out['inst_pct'] = (inst * 100).round(1)
    out['I_pass'] = inst >= config.CANSLIM_I_MIN_INST

    out['canslim_score'] = (out['C_pass'].astype(int)
                            + out['A_pass'].astype(int)
                            + out['I_pass'].astype(int))
    out['in_canslim'] = out['canslim_score'] >= config.CANSLIM_MIN_SCORE
    return out


def leaders(evaluate_df: pd.DataFrame) -> pd.DataFrame:
    """The CANSLIM C-A-I leaders' list."""
    return evaluate_df[evaluate_df['in_canslim']].copy()


def accumulation_flag(symbol: str) -> bool | None:
    """True when shares outstanding are flat/shrinking over the last ~90 days
    (accumulation-friendly). None when no shares data exists."""
    s = data_loader.load_shares_outstanding(symbol)
    if s is None or len(s) < 2:
        return None
    cutoff = s.index.max() - pd.Timedelta(days=90)
    window = s[s.index >= cutoff]
    if window.empty:
        return None
    return float(window.iloc[-1]) <= float(window.iloc[0])


def accumulation_flags(tickers: list, verbose: bool = True) -> pd.Series:
    """
    Vectorized-enough wrapper: per-ticker shares-outstanding check for a
    LIST of tickers (meant for the leaders' union, ~hundreds — one small CSV
    read each, not the full universe). Returns a boolean Series indexed by
    ticker (False where data is missing; use `has_data` companion Series).
    """
    flags, has_data = {}, {}
    for t in tickers:
        f = accumulation_flag(t)
        flags[t] = bool(f) if f is not None else False
        has_data[t] = f is not None
    out = pd.Series(flags, name='I_accumulation')
    out.index.name = 'ticker'
    n = int(sum(has_data.values()))
    if verbose:
        print(f'  shares-accumulation flag: {n}/{len(tickers)} with shares data, '
              f'{int(sum(flags.values()))} flat/shrinking')
    return out.to_frame().join(pd.Series(has_data, name='I_shares_data'))

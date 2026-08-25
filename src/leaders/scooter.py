"""
Leader filter c) — SCOOTER score = SCTR (StockCharts Technical Rank,
John Murphy's methodology), the user's "scooter".

Exact port of test_scooter/sctr_model.py::compute_raw_score_matrix +
rank_to_sctr (itself cross-checked against yf-gics/src/sctr_engine.py and
the live ChartSchool page):

  Long-term  (60%): % above/below 200-day EMA (30%), 125-day ROC (30%)
  Medium-term(30%): % above/below 50-day EMA  (15%),  20-day ROC (15%)
  Short-term (10%): 14-day RSI (5%), 3-day slope of PPO(12,26,9) histogram,
                     ChartSchool-normalized to 0-100 (5%)

  raw = sum(component * weight); SCTR = cross-sectional percentile of raw
  scaled to 0-99.9 ("no stock scores a perfect 100"). Minimum 210 valid
  daily bars.

Note: the percentile is computed WITHIN this screening universe (~4,000
tickers), not StockCharts' S&P 1500 — scores are universe-relative.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
import config
from src import indicators

PPO_FAST, PPO_SLOW, PPO_SIGNAL, PPO_SLOPE_WINDOW = 12, 26, 9, 3

_WEIGHTS = {
    'c_ema200_pct': 0.30,
    'c_roc125': 0.30,
    'c_ema50_pct': 0.15,
    'c_roc20': 0.15,
    'c_rsi14': 0.05,
    'c_ppo_slope': 0.05,
}


def _pct_from_ema(close: pd.DataFrame, period: int) -> pd.DataFrame:
    ema = close.ewm(span=period, adjust=False).mean()
    return (close - ema) / ema.replace(0, np.nan) * 100.0


def _ppo_slope_score(close: pd.DataFrame) -> pd.DataFrame:
    """PPO(12,26,9) histogram 3-day slope, ChartSchool-normalized 0-100:
    slope >= +1 -> 100, slope <= -1 -> 0, else (slope+1)*50."""
    ema_fast = close.ewm(span=PPO_FAST, adjust=False).mean()
    ema_slow = close.ewm(span=PPO_SLOW, adjust=False).mean()
    ppo = (ema_fast - ema_slow) / ema_slow.replace(0, np.nan) * 100.0
    signal = ppo.ewm(span=PPO_SIGNAL, adjust=False).mean()
    hist = ppo - signal
    slope = (hist - hist.shift(PPO_SLOPE_WINDOW)) / PPO_SLOPE_WINDOW
    score = (slope + 1.0) * 50.0
    score = score.where(slope < 1.0, 100.0)
    score = score.where(slope > -1.0, 0.0)
    return score


def compute_scores(close: pd.DataFrame) -> pd.DataFrame:
    """
    Wide Close matrix -> per-ticker Series for the LATEST date:
    scooter_score (0-99.9) plus the six raw components.
    """
    c = close
    comp = {
        'c_ema200_pct': _pct_from_ema(c, 200),
        'c_roc125': indicators.roc(c, 125),
        'c_ema50_pct': _pct_from_ema(c, 50),
        'c_roc20': indicators.roc(c, 20),
        'c_rsi14': indicators.rsi(c, 14),
        'c_ppo_slope': _ppo_slope_score(c),
    }
    raw = None
    for k, v in comp.items():
        term = v * _WEIGHTS[k]
        raw = term if raw is None else raw + term

    # warm-up: >= MIN_BARS_SCTR valid closes (running count per ticker)
    valid_count = c.notna().cumsum()
    raw = raw.where((valid_count >= config.MIN_BARS_SCTR) & c.notna())

    last_raw = raw.iloc[-1]
    score = last_raw.rank(method='average', pct=True) * 99.9

    out = pd.DataFrame(index=c.columns)
    out.index.name = 'ticker'
    out['scooter_score'] = score.round(1)
    out['scooter_raw'] = last_raw          # full precision (validation-grade)
    for k, v in comp.items():
        out[k] = v.iloc[-1].round(2)
    out['in_scooter'] = out['scooter_score'] >= config.SCOOTER_MIN_SCORE
    return out


def leaders(evaluate_df: pd.DataFrame) -> pd.DataFrame:
    """The SCOOTER leaders' list."""
    return evaluate_df[evaluate_df['in_scooter']].copy()

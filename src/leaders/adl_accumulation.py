"""
Leader filter — ADL 5-step accumulation suite (more_screeners.md Task 7).

Source: metaData_v1/src/screeners/ad_line/ package (the refactored form —
NOT the top-level adl_screener.py monolith):
  step 1  adl_calculator.py::calculate_adl
          MFM = ((C-L)-(H-C))/(H-L) (doji -> 0); MFV = MFM x V; ADL = cumsum
  step 2  adl_mom_analysis.py — long-term: month-end ADL, month-over-month
          % changes; consistency = in-range(15-30%)/n*70 + positive-out-of-
          range/n*20 + variance_bonus(max(0, 10 - std/2)); current streak =
          trailing in-range months; long-term gate = consistency >= 60 AND
          streak >= 3
  step 3  adl_short_term.py — % changes over 5/10/20d; momentum signal
          (acceleration: 5d>10d>20d and 5d>5; deceleration: ascending;
          momentum: >=half positive and any >5); momentum score =
          0.4*norm(avg,-20,20) + 0.6*norm(weighted[3,2,1] avg,-20,20)
          + signal bonus (+15 accel, +10 momentum, -10 deceleration)
  step 4  adl_ma_analysis.py — ADL SMAs 20/50/100; alignment bullish
          (ma20>ma50>ma100) / bearish / neutral; alignment score =
          base(60/20/40) + min(30, avg_sep*6) + (10 if 1<avg_sep<5)
  step 5  adl_composite_scoring.py — composite = 0.4*longterm +
          0.3*shortterm + 0.3*ma; accumulation signal when >= 70

Outputs: `in_adl_accumulation`, `adl_composite_score`,
`adl_consistency_score`, `adl_momentum_score`, `adl_alignment_score`,
`adl_momentum_signal`, `adl_ma_alignment`, `adl_current_streak`.

Vectorized: monthly changes via month-end resample of the whole ADL
matrix; all scoring formulas are elementwise.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
import config
from src import indicators


def _norm(value, lo, hi):
    """adl_utils.normalize_score: clamp to [lo, hi] -> 0-100."""
    v = value.clip(lo, hi)
    return (v - lo) / (hi - lo) * 100.0


def calculate_adl(high, low, close, volume):
    """Step 1 — Accumulation/Distribution Line (Date x ticker)."""
    hl = high - low
    mfm = ((close - low) - (high - close)) / hl.replace(0, np.nan)
    mfm = mfm.astype(float).fillna(0.0)
    return (mfm * volume).cumsum()


def evaluate(high, low, close, volume) -> pd.DataFrame:
    adl = calculate_adl(high, low, close, volume)

    # ---- step 2: long-term (MoM consistency) ------------------------------
    # the source samples the ADL every mom_period(22) BARS working backwards
    # from the end (lookback_months+1 = 7 samples -> 6 changes), NOT calendar
    # months (_extract_monthly_values :124-148)
    period = config.ADL_MOM_PERIOD
    n_samples = config.ADL_MOM_LOOKBACK_MONTHS + 1
    positions = [len(adl) - 1 - i * period for i in range(n_samples)]
    positions = [p for p in positions if p >= 0][::-1]
    monthly = adl.iloc[positions]
    # source convention (adl_utils.calculate_percentage_change):
    # (current - previous) / abs(previous) * 100 — abs DENOMINATOR
    monthly_chg = ((monthly - monthly.shift(1))
                   / monthly.shift(1).abs()) * 100.0
    monthly_chg = monthly_chg.dropna(how='all')
    in_range = ((monthly_chg >= config.ADL_MOM_MIN_PCT)
                & (monthly_chg <= config.ADL_MOM_MAX_PCT))
    positive = monthly_chg > 0
    n_months = monthly_chg.notna().sum()
    in_range_count = in_range.where(monthly_chg.notna()).sum()
    positive_count = positive.where(monthly_chg.notna()).sum()
    base_score = in_range_count / n_months.replace(0, np.nan) * 70.0
    pos_bonus = ((positive_count - in_range_count)
                 / n_months.replace(0, np.nan)) * 20.0
    std_dev = monthly_chg.std(ddof=0)
    var_bonus = (10.0 - std_dev / 2.0).clip(lower=0.0)
    consistency = (base_score + pos_bonus + var_bonus).fillna(0.0)

    # trailing streak of in-range months ending at the last month
    # (cumsum-minus-last-reset trick, per ticker — no DataFrame grouper)
    cs = in_range.cumsum()
    reset = cs.where(~in_range).ffill().fillna(0)
    streak = (cs - reset).where(in_range, 0)
    current_streak = streak.iloc[-1]
    if not isinstance(current_streak, pd.Series):
        current_streak = pd.Series({in_range.columns[0]: current_streak})

    longterm_gate = ((consistency >= config.ADL_MOM_MIN_CONSISTENCY)
                     & (current_streak >= config.ADL_MOM_CONSECUTIVE_MONTHS))

    # ---- step 3: short-term momentum --------------------------------------
    changes = {}
    for lb in config.ADL_SHORT_PERIODS:
        changes[lb] = (adl / adl.shift(lb) - 1.0) * 100.0
    c5, c10, c20 = (changes[lb].iloc[-1] for lb in config.ADL_SHORT_PERIODS)
    avg_change = (c5 + c10 + c20) / 3.0
    base_score_st = _norm(avg_change, -20.0, 20.0)
    weighted_avg = (c5 * 3 + c10 * 2 + c20 * 1) / 6.0
    weighted_score = _norm(weighted_avg, -20.0, 20.0)

    accel = (c5 > c10) & (c10 > c20) & (c5 > config.ADL_SHORT_MOMENTUM_THRESHOLD)
    decel = (c5 < c10) & (c10 < c20)
    pos_n = ((c5 > 0).astype(int) + (c10 > 0).astype(int) + (c20 > 0).astype(int))
    momentum_sig = (pos_n >= 2) & ((c5 > config.ADL_SHORT_MOMENTUM_THRESHOLD)
                                   | (c10 > config.ADL_SHORT_MOMENTUM_THRESHOLD)
                                   | (c20 > config.ADL_SHORT_MOMENTUM_THRESHOLD))

    combined = base_score_st * 0.4 + weighted_score * 0.6
    momentum_score = combined.where(
        ~(accel | decel | momentum_sig), np.nan)
    momentum_score = momentum_score.fillna(combined) \
        .mask(accel, (combined + 15.0).clip(upper=100.0)) \
        .mask(~accel & momentum_sig, (combined + 10.0).clip(upper=100.0)) \
        .mask(~accel & ~momentum_sig & decel, (combined - 10.0).clip(lower=0.0))

    signal_label = pd.Series('neutral', index=close.columns, dtype=object)
    signal_label[momentum_sig & ~accel] = 'momentum'
    signal_label[accel] = 'acceleration'
    signal_label[decel & ~accel] = 'deceleration'

    # ---- step 4: MA alignment ---------------------------------------------
    adl_mas = {p: adl.rolling(p, min_periods=p).mean()
               for p in config.ADL_MA_PERIODS}
    m20, m50, m100 = (adl_mas[p].iloc[-1] for p in config.ADL_MA_PERIODS)
    ma_bullish = (m20 > m50) & (m50 > m100)
    ma_bearish = (m20 < m50) & (m50 < m100)

    # abs wraps the WHOLE quotient (source: abs((a-b)/b)) — positive even
    # when the ADL MAs are negative (QMCO case)
    sep_1 = ((m20 - m50) / m50.replace(0, np.nan)).abs() * 100
    sep_2 = ((m50 - m100) / m100.replace(0, np.nan)).abs() * 100
    avg_sep = (sep_1 + sep_2) / 2.0
    sep_bonus = (avg_sep * 6.0).clip(upper=30.0) + \
        ((avg_sep > 1.0) & (avg_sep < 5.0)) * 10.0
    base_ma = pd.Series(40.0, index=close.columns)
    base_ma = base_ma.mask(ma_bullish, 60.0).mask(ma_bearish, 20.0)
    alignment_score = (base_ma + sep_bonus).clip(upper=100.0)
    ma_alignment = pd.Series('neutral', index=close.columns, dtype=object)
    ma_alignment[ma_bearish] = 'bearish'
    ma_alignment[ma_bullish] = 'bullish'

    # ---- step 5: composite -------------------------------------------------
    composite = (config.ADL_W_LONGTERM * consistency
                 + config.ADL_W_SHORTTERM * momentum_score
                 + config.ADL_W_MA * alignment_score)

    out = pd.DataFrame(index=close.columns)
    out.index.name = 'ticker'
    out['in_adl_accumulation'] = (composite >= config.ADL_MIN_COMPOSITE) \
        .fillna(False).astype(bool)
    out['adl_composite_score'] = composite.round(1)
    out['adl_consistency_score'] = consistency.round(1)
    out['adl_momentum_score'] = momentum_score.round(1)
    out['adl_alignment_score'] = alignment_score.round(1)
    out['adl_momentum_signal'] = signal_label
    out['adl_ma_alignment'] = ma_alignment
    out['adl_current_streak'] = current_streak.fillna(0).astype(int)
    out['adl_longterm_gate'] = longterm_gate.fillna(False).astype(bool)
    return out

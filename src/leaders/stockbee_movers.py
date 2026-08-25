"""
Leader filter — Stockbee Movers, 3 same-day snapshot sub-screeners
(more_screeners.md Task 1).

Source: metaData_v1/src/screeners/stockbee/stockbee_screener.py
(_run_9m_movers :198-275, _run_weekly_movers :277-374,
_run_daily_gainers :376-471). Thresholds live in config.py (STOCKBEE_*),
verbatim from that source. The source's 4th sub-strategy (Top 20%
Industries & Top 4 Performers) is OUT of scope — cross-sectional industry
ranking belongs to the Step-1 module (intro.md scope decision).

Sub-screeners (all evaluated on the LATEST bar of wide matrices):

a) 9M Movers        — today's volume >= 9M shares
                    — today's volume / 20d avg volume >= 1.25
                    — green candle (close > open)

b) 20% Weekly Movers— close(today) vs open(5 trading days ago) >= +20%
                    — 5d avg volume >= 100K shares
                    — 5d avg volume / 20d avg volume >= 1.25
                    — green week (week close > week open)

c) 4% Daily Gainers — close vs previous close >= +4%
                    — today's volume >= 100K shares
                    — today's volume / 20d avg volume >= 1.5
                    — green candle
                    — close > 50-day SMA

Note (J1 in IMPLEMENTATION_PLAN.md §11): the 9M-share threshold matches
only very liquid names in this ~4,000-ticker universe; kept verbatim per
the backlog, config-configurable.

Vectorized: per-ticker Python loops from the source become whole-matrix
operations (the codebase-wide pattern, more_screeners.md "How this
codebase differs").
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
import config
from src import indicators


def evaluate(open_: pd.DataFrame, high: pd.DataFrame, low: pd.DataFrame,
             close: pd.DataFrame, volume: pd.DataFrame) -> pd.DataFrame:
    """Returns per-ticker columns: the 3 boolean memberships + numerics."""
    w = config.STOCKBEE_WEEK_WINDOW
    w20 = config.STOCKBEE_REL_VOL_WINDOW

    avg_vol20 = volume.rolling(w20, min_periods=w20).mean()
    rel_vol_today = volume.iloc[-1] / avg_vol20.iloc[-1]

    # weekly window: open 5 bars ago vs close today (source: tail(5),
    # Open.iloc[0] -> Open at t-4)
    week_open = open_.iloc[-w]
    week_close = close.iloc[-1]
    weekly_gain_pct = (week_close / week_open.replace(0, np.nan) - 1.0) * 100.0
    avg_vol5 = volume.iloc[-w:].mean()
    weekly_rel_vol = avg_vol5 / avg_vol20.iloc[-1]

    daily_gain_pct = close.pct_change(fill_method=None).iloc[-1] * 100.0

    sma50 = indicators.sma(close, 50).iloc[-1]
    last_close = close.iloc[-1]
    last_open = open_.iloc[-1]
    last_volume = volume.iloc[-1]

    green_candle = last_close > last_open
    green_week = week_close > week_open

    in_9m = ((last_volume >= config.STOCKBEE_9M_MIN_VOLUME)
             & (rel_vol_today >= config.STOCKBEE_9M_MIN_REL_VOL)
             & green_candle)

    in_weekly = ((weekly_gain_pct >= config.STOCKBEE_WEEKLY_MIN_GAIN_PCT)
                 & (avg_vol5 >= config.STOCKBEE_WEEKLY_MIN_AVG_VOLUME)
                 & (weekly_rel_vol >= config.STOCKBEE_WEEKLY_MIN_REL_VOL)
                 & green_week)

    in_daily = ((daily_gain_pct >= config.STOCKBEE_DAILY_MIN_GAIN_PCT)
                & (last_volume >= config.STOCKBEE_DAILY_MIN_VOLUME)
                & (rel_vol_today >= config.STOCKBEE_DAILY_MIN_REL_VOL)
                & green_candle
                & (last_close > sma50))

    out = pd.DataFrame(index=close.columns)
    out.index.name = 'ticker'
    out['in_9m_movers'] = in_9m.fillna(False).astype(bool)
    out['in_weekly_movers'] = in_weekly.fillna(False).astype(bool)
    out['in_daily_gainers'] = in_daily.fillna(False).astype(bool)
    out['rel_volume_today'] = rel_vol_today.round(3)
    out['avg_volume_5d'] = avg_vol5.round(0)
    out['weekly_gain_pct'] = weekly_gain_pct.round(2)
    out['daily_gain_pct'] = daily_gain_pct.round(2)
    out['in_stockbee_any'] = (out['in_9m_movers'] | out['in_weekly_movers']
                              | out['in_daily_gainers'])
    return out

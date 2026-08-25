"""
Focus metric a) — ATR extension vs 21 EMA / 40 SMA, plus ADR and dollar
volume (intro.md 2a: TradingView 60GMm8mE "ALEX - ATR Extensions + ADR +
Table" by Alex_PrimeTrading; Pine source fetched and ported verbatim).

ALEX pine core:
  atr_val = ta.atr(14)                       (Wilder)
  atr_pct = atr_val / close * 100
  adr_val = ta.sma(high - low, 20); adr_pct = adr_val/close*100
  dma_21  = EMA(close,21); dma_50 = SMA(close,50)   [user: 40 SMA]
  dist(x) = ((close - x)/x) / (atr_pct/100)
  extension level = MA + atr_val * multiplier (default 2.0)
  thresholds: 2.0 (extended/yellow), 5.0 (very extended/red)

Two extension variants are produced (both already established in the
user's own code):
  ext_*_atr  = (close - MA)/ATR            — metaData_v1 atrext_dollar
  ext_*_alex = ((close-MA)/MA)/(atr_pct/100) — metaData_v1 atrext_percent
Flags are evaluated on the ATR-units variant.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
import config
from src import indicators


def evaluate(high: pd.DataFrame, low: pd.DataFrame, close: pd.DataFrame,
             volume: pd.DataFrame) -> pd.DataFrame:
    atr = indicators.wilder_atr(high, low, close, config.ATR_PERIOD)
    atr_p = indicators.atr_pct(close, atr)
    ema21 = indicators.ema(close, config.EXT_EMA_PERIOD)
    sma40 = indicators.sma(close, config.EXT_SMA_PERIOD)

    last_c = close.iloc[-1]
    last_atr = atr.iloc[-1]
    last_atr_pct = atr_p.iloc[-1]
    v21, v40 = ema21.iloc[-1], sma40.iloc[-1]

    out = pd.DataFrame(index=close.columns)
    out.index.name = 'ticker'
    out['atr14'] = last_atr.round(3)
    out['atr_pct'] = last_atr_pct.round(2)
    out['ema21'] = v21.round(3)
    out['sma40'] = v40.round(3)

    # ATR-units extension (primary)
    out['ext_21ema_atr'] = ((last_c - v21) / last_atr).replace([np.inf, -np.inf], np.nan).round(2)
    out['ext_40sma_atr'] = ((last_c - v40) / last_atr).replace([np.inf, -np.inf], np.nan).round(2)

    # exact ALEX dist() variant
    out['ext_21ema_alex'] = (((last_c - v21) / v21) / (last_atr_pct / 100)).round(2)
    out['ext_40sma_alex'] = (((last_c - v40) / v40) / (last_atr_pct / 100)).round(2)

    # raw % distance
    out['ext_21ema_pct'] = ((last_c / v21 - 1) * 100).round(2)
    out['ext_40sma_pct'] = ((last_c / v40 - 1) * 100).round(2)

    # flags (on ATR-units variant)
    e21, e40 = out['ext_21ema_atr'], out['ext_40sma_atr']
    ext = (e21 > config.EXT_THRESHOLD_1) | (e40 > config.EXT_THRESHOLD_1)
    very = (e21 > config.EXT_THRESHOLD_2) | (e40 > config.EXT_THRESHOLD_2)
    below = (e21 < config.EXT_BELOW_THRESHOLD) & (e40 < config.EXT_BELOW_THRESHOLD)
    out['extended'] = ext.fillna(False)
    out['very_extended'] = very.fillna(False)
    out['extended_below'] = below.fillna(False)

    # extension price levels (MA +/- k*ATR, ALEX atr_mult 2.0)
    k = config.EXT_THRESHOLD_1
    out['ext_level_21ema_up'] = (v21 + last_atr * k).round(3)
    out['ext_level_40sma_up'] = (v40 + last_atr * k).round(3)

    # ADR / liquidity (StockScreenHero "IMPORTANT" columns)
    out['adr20_pct'] = indicators.adr_pct(high, low, close, config.ADR_PERIOD).iloc[-1].round(2)
    out['adv50_dollar'] = indicators.avg_dollar_volume(close, volume, config.ADV_PERIOD).iloc[-1]
    out['avg_volume50'] = indicators.avg_volume(close, volume, config.ADV_PERIOD).iloc[-1]
    out['liquidity_pass'] = out['adv50_dollar'] >= config.MIN_ADV_DOLLAR
    return out

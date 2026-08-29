"""
Leader filter d) — CANTATA / CE (breakoutwatch CANTATA Evaluator).

Source: cup_handle_ideas/cupAndHandle/lit/CE Overview.html; full item ->
project-column mapping in research/breakoutwatch_ce_mapping.md.

  CE = CET (technical, 0-7) + CEF (fundamental, 0-11) = 0-18.

CET items 2-5 are continuous (RS rank, industry rank, distance from 52w
high, Up/Down volume ratio) — scored as a 0..1 fraction linearly
interpolated between breakoutwatch's stated "worst" and "best" values
(config.CANTATA_*). Item 1 (MA structure) is 0-3 (one point each for
price>50dMA, price>200dMA, 50dMA>200dMA). CEF is 11 pass/fail points.

This is a STOCK-LEVEL leader score, the same conceptual slot as CANSLIM and
Minervini (and it overlaps both — CEF ~ CANSLIM, CET ~ the trend template).
NOT pattern-anchored: unrelated to the cup & handle CQ/RCQ/HQ scores.

CET reads the already-computed price context (stage / MAs / RS / 52w-high /
industry) passed in as `context`, plus a precomputed Up/Down volume ratio.
CEF reads the financial snapshot (financial_data_0_8.csv) directly, like
canslim.py. Deviations from breakoutwatch, forced by the snapshot:
  - CEF1 "2 Q's each >= 18%" uses the two most recent per-quarter YoY growth
    fields (qh1/qh2_eps_growth_yoy)
  - CEF4 "4 FY's each >= 25%" uses 3 (y1..y3_eps_growth_yoy; y4 is sparse)
  - CEF5 quarterly sales YoY has one clean quarter (q1 vs q5); CEF6 sales
    acceleration falls back to sequential QoQ revenue rising (documented
    proxy — the snapshot lacks enough quarterly revenue history)
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


def _interp(x: pd.Series, worst: float, best: float) -> pd.Series:
    """Linear 0..1 between worst and best (clipped); NaN -> 0."""
    frac = (x - worst) / (best - worst)
    return frac.clip(0.0, 1.0).fillna(0.0)


def _cet(context: pd.DataFrame, ud_ratio: pd.Series) -> pd.DataFrame:
    out = pd.DataFrame(index=context.index)

    p50 = _num(context.get('pct_vs_50sma'))
    p200 = _num(context.get('pct_vs_200sma'))
    # 50dMA > 200dMA  <=>  pct_vs_50sma < pct_vs_200sma  (same close on top)
    out['cet_ma'] = ((p50 > 0).astype(int)
                     + (p200 > 0).astype(int)
                     + (p50 < p200).astype(int))          # 0-3

    rs = _num(context.get('rs_pct'))
    out['cet_rs'] = _interp(rs, config.CANTATA_RS_WORST, config.CANTATA_RS_BEST)

    # industry rank: percentile of RS within the stock's industry
    # (1.0 = strongest in its group). Singleton / missing industry -> 0.5.
    ind = context.get('industry')
    if ind is not None:
        grp = rs.groupby(ind)
        pct = grp.rank(pct=True)
        counts = ind.map(ind.value_counts())
        pct[counts.fillna(0) < 3] = 0.5
        out['cet_industry'] = pct.reindex(context.index).fillna(0.5)
    else:
        out['cet_industry'] = 0.5

    h = _num(context.get('pct_from_52w_high'))
    out['cet_52whigh'] = _interp(h, config.CANTATA_52WHIGH_WORST,
                                 config.CANTATA_52WHIGH_BEST)

    ud = _num(ud_ratio.reindex(context.index))
    out['ud_volume_ratio'] = ud.round(2)
    out['cet_updown'] = _interp(ud, config.CANTATA_UD_WORST,
                                config.CANTATA_UD_BEST)

    out['cet_score'] = (out['cet_ma'] + out['cet_rs'] + out['cet_industry']
                        + out['cet_52whigh'] + out['cet_updown']).round(2)
    return out


def _cef(index: pd.Index) -> pd.DataFrame:
    fin = data_loader.load_financial_data()
    fin = fin.reindex(index)
    g = fin.get
    out = pd.DataFrame(index=index)

    qoq = config.CANTATA_CEF_QOQ_MIN
    out['cef_qoq_eps'] = ((_num(g('qh1_eps_growth_yoy')) >= qoq)
                          & (_num(g('qh2_eps_growth_yoy')) >= qoq))
    out['cef_pos_eps'] = (_num(g('q1_eps')) > 0) & (_num(g('q2_eps')) > 0)

    q1g, q2g = _num(g('qh1_eps_growth_yoy')), _num(g('qh2_eps_growth_yoy'))
    q3g, q4g = _num(g('qh3_eps_growth_yoy')), _num(g('qh4_eps_growth_yoy'))
    accel = (q1g > q2g) & (q2g > q3g) & (q3g > q4g)
    out['cef_eps_accel'] = accel.fillna(
        _num(g('eps_growth_accelerating')).fillna(0).astype(bool)
        if g('eps_growth_accelerating') is not None else False)

    yoy = config.CANTATA_CEF_YOY_MIN
    out['cef_yoy_eps'] = ((_num(g('y1_eps_growth_yoy')) >= yoy)
                          & (_num(g('y2_eps_growth_yoy')) >= yoy)
                          & (_num(g('y3_eps_growth_yoy')) >= yoy))

    q1r, q5r = _num(g('q1_revenue')), _num(g('q5_revenue'))
    out['cef_qoq_sales'] = (q1r / q5r.replace(0, np.nan) - 1.0) \
        >= config.CANTATA_CEF_SALES_MIN
    q2r, q3r = _num(g('q2_revenue')), _num(g('q3_revenue'))
    out['cef_sales_accel'] = (q1r > q2r) & (q2r > q3r)     # QoQ-rising proxy

    fwd = _num(g('forwardEps')) / _num(g('trailingEps')).replace(0, np.nan) - 1.0
    out['cef_fwd_eps'] = fwd >= config.CANTATA_CEF_FWD_MIN

    out['cef_institutional'] = (
        (_num(g('institutional_holders_count'))
         >= config.CANTATA_CEF_INST_MIN_HOLDERS)
        & (_num(g('institutional_holders_avg_pct_change')) >= 0))

    roe = _num(g('returnOnEquity')).fillna(_num(g('y1_roe')))
    out['cef_roe'] = roe >= config.CANTATA_CEF_ROE_MIN

    cflo = _num(g('y1_cashflow_vs_eps_ratio'))
    out['cef_cashflow'] = cflo.ge(config.CANTATA_CEF_CFLO_MIN).where(
        cflo.notna(),
        _num(g('cashflow_quality_pass')).fillna(0).astype(bool)
        if g('cashflow_quality_pass') is not None else False)

    m1 = _num(g('y1_net_income')) / _num(g('y1_revenue')).replace(0, np.nan)
    m2 = _num(g('y2_net_income')) / _num(g('y2_revenue')).replace(0, np.nan)
    m3 = _num(g('y3_net_income')) / _num(g('y3_revenue')).replace(0, np.nan)
    out['cef_margin'] = (m1 >= m2) & (m1 >= m3) & m1.notna()

    cef_cols = [c for c in out.columns]
    out = out.fillna(False).astype(bool)
    out['cef_score'] = out[cef_cols].sum(axis=1)           # 0-11
    return out


def evaluate(context: pd.DataFrame, ud_ratio: pd.Series) -> pd.DataFrame:
    """
    context: per-ticker frame with pct_vs_50sma, pct_vs_200sma, rs_pct,
             pct_from_52w_high, industry (i.e. the assembled screener_results).
    ud_ratio: per-ticker Up/Down volume ratio (indicators.up_down_volume_ratio,
              last row).
    Returns per-ticker CET/CEF sub-scores + cet_score (0-7), cef_score
    (0-11), ce_score (0-18), in_cantata.
    """
    cet = _cet(context, ud_ratio)
    cef = _cef(context.index)
    out = cet.join(cef)
    out['ce_score'] = (out['cet_score'] + out['cef_score']).round(2)
    out['in_cantata'] = out['ce_score'] >= config.CANTATA_MIN_CE
    out.index.name = 'ticker'
    return out


def leaders(evaluate_df: pd.DataFrame) -> pd.DataFrame:
    """The CANTATA CE leaders' list."""
    return evaluate_df[evaluate_df['in_cantata']].copy()

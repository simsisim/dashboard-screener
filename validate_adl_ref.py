"""ADL reference check — run by validate.py in an isolated subprocess.

Computes consistency/momentum/alignment/composite scores for a few
tickers with the metaData_v1 ad_line/ package (the authoritative port)
so screeners' own ADL module can be compared against it."""
import json
import sys

import pandas as pd

sys.path.insert(0, '/home/imagda/_invest2024/python/metaData_v1')
from src.screeners.ad_line.adl_calculator import ADLCalculator  # noqa: E402
from src.screeners.ad_line.adl_mom_analysis import ADLMoMAnalyzer  # noqa: E402
from src.screeners.ad_line.adl_short_term import ADLShortTermAnalyzer  # noqa: E402
from src.screeners.ad_line.adl_ma_analysis import ADLMAAnalyzer  # noqa: E402
from src.screeners.ad_line.adl_composite_scoring import ADLCompositeScorer  # noqa: E402

CUR = '/home/imagda/_invest2024/python/downloadData_v1/data/market_data/daily/current'
ARCH = '/home/imagda/_invest2024/python/downloadData_v1/data/market_data/daily/archive'


def main():
    mom = ADLMoMAnalyzer({})
    st = ADLShortTermAnalyzer({})
    ma = ADLMAAnalyzer({})
    cs = ADLCompositeScorer({})
    out = {}
    for t in ['AAPL', 'MSFT', 'QMCO']:
        parts = []
        for base in (ARCH, CUR):
            try:
                parts.append(pd.read_csv(f'{base}/{t}.csv', low_memory=False))
            except FileNotFoundError:
                pass
        df = pd.concat(parts).drop_duplicates(subset='Date').sort_values('Date')
        df['Date'] = pd.to_datetime(df['Date'], utc=True, errors='coerce')
        df = df.dropna(subset=['Date'])
        df['Date'] = df['Date'].dt.tz_localize(None).dt.normalize()
        df = df.set_index('Date')[['Open', 'High', 'Low', 'Close', 'Volume']]
        df = df.apply(pd.to_numeric, errors='coerce').dropna()
        m = mom.analyze_monthly_accumulation(df) or {}
        s = st.calculate_short_term_changes(df) or {}
        a = ma.calculate_adl_mas(df) or {}
        lt = m.get('consistency_score', 0)
        stc = s.get('momentum_score', 0)
        mac = a.get('ma_alignment_score', 0)
        comp = cs.calculate_composite_score(lt, stc, mac)
        out[t] = {'consistency': lt, 'momentum': stc, 'alignment': mac,
                  'composite': comp}
    print(json.dumps(out))


if __name__ == '__main__':
    main()

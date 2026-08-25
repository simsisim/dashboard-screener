"""
Focus metric — statistical volume-anomaly detector (more_screeners.md
Task 6).

Source: metaData_v1/src/screeners/volume_suite_components/
enhanced_volume_anomaly.py::_detect_statistical_anomalies (:170-200),
cross-referenced with HVStdv.py::find_anomalies (std-deviation method)
and HVAbsoluteETC.py (absolute-spike filtering). Thresholds verbatim in
config.py (VOLANOM_*).

Detection on the LATEST bar (rolling stats over VOLANOM_LOOKBACK=50):
  volume > rolling_mean + 3.0 * rolling_std      (3-sigma spike)
  volume > 100,000 shares
  volume / rolling_mean > 1.5                    (relative confirmation)

Outputs: `in_volume_anomaly` bool, `volume_zscore` (sigma above the
rolling mean), `volume_ratio` (vol / rolling mean).
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
import config


def evaluate(volume: pd.DataFrame) -> pd.DataFrame:
    lb = config.VOLANOM_LOOKBACK
    vol_mean = volume.rolling(lb, min_periods=lb).mean()
    vol_std = volume.rolling(lb, min_periods=lb).std()

    threshold = vol_mean + config.VOLANOM_STD_THRESHOLD * vol_std
    last_vol = volume.iloc[-1]
    last_thr = threshold.iloc[-1]
    zscore = (last_vol - vol_mean.iloc[-1]) / vol_std.iloc[-1].replace(0, np.nan)
    ratio = last_vol / vol_mean.iloc[-1].replace(0, np.nan)

    anomaly = ((last_vol > last_thr)
               & (last_vol > config.VOLANOM_MIN_VOLUME)
               & (ratio > config.VOLANOM_MIN_RELATIVE))

    out = pd.DataFrame(index=volume.columns)
    out.index.name = 'ticker'
    out['in_volume_anomaly'] = anomaly.fillna(False).astype(bool)
    out['volume_zscore'] = zscore.round(2)
    out['volume_ratio'] = ratio.round(2)
    return out

"""
Step-2 Filters module — paths and thresholds (single source of truth).

Everything the screeners need is parameterized here. Conventions follow the
sibling projects (lkm_rs, yf-gics, metaData_v1): scripts add this folder to
sys.path and `import config`.

Provenance of each threshold is cited inline (see IMPLEMENTATION_PLAN.md §0
for the bibliography).
"""
from pathlib import Path

SCREENERS_ROOT = Path(__file__).resolve().parent

# --- downloadData_v1 is the data-owning sibling project; consumed in place ---
DOWNLOAD_ROOT = Path('/home/imagda/_invest2024/python/downloadData_v1')

UNIVERSE_CSV = DOWNLOAD_ROOT / 'user_input' / 'tradingview_universe.csv'
MARKET_DATA_DAILY = DOWNLOAD_ROOT / 'data' / 'market_data' / 'daily'
DAILY_ARCHIVE = MARKET_DATA_DAILY / 'archive'      # 2020-01-02 -> 2025-12-31
DAILY_CURRENT = MARKET_DATA_DAILY / 'current'      # 2026-01-02 -> today
MARKET_DATA_BATCH_DAILY = DOWNLOAD_ROOT / 'data' / 'market_data_batch' / 'daily'
MARKET_DATA_SHARES = DOWNLOAD_ROOT / 'data' / 'market_data' / 'shares_outstanding'
FIN_DATA_CSV = DOWNLOAD_ROOT / 'data' / 'fin_data' / 'financial_data_0_8.csv'

RESULTS_DIR = SCREENERS_ROOT / 'results'

# --- history requirements (trading days) ---
# SCTR needs 210 (test_scooter.sctr_model.MIN_DAILY_BARS); Minervini/stage need
# 200-SMA + 20d slope buffer (lkm_rs STAGE_DAILY_MIN_BARS) and 252-bar 52w H/L.
MIN_BARS_SCTR = 210
MIN_BARS_TEMPLATE = 210
BARS_52W = 252

# --- 1st cat: Minervini trend template (lkm_rs config, daily variant) ---
MINERVINI_SMA_SHORT = 50
MINERVINI_SMA_MED = 150
MINERVINI_SMA_LONG = 200
MINERVINI_SLOPE_WINDOW = 20          # ~4 weeks
MINERVINI_ABOVE_52W_LOW = 1.30       # price >= 30% above 52w low
MINERVINI_FROM_52W_HIGH = 0.75       # price >= 75% of 52w high (within 25%)
MINERVINI_MIN_RS = 70                # RS percentile >= 70 (criterion 8)
MINERVINI_MIN_PASS = 8               # list membership: all criteria

# --- IBD-style RS blend (lkm_rs config: authentic weighted multi-period) ---
IBD_RS_LOOKBACKS = (63, 126, 189, 252)
IBD_RS_WEIGHTS = (0.4, 0.2, 0.2, 0.2)

# --- 1st cat: CANSLIM C-A-I (O'Neil; financial_data_0_8.csv snapshot) ---
CANSLIM_C_MIN_YOY = 0.25             # C: latest quarterly EPS YoY >= +25%
CANSLIM_C_MIN_BASE_EPS = 0.05        # C: year-ago qtr EPS >= $0.05 (excludes
                                     #     near-zero-base YoY artifacts, e.g.
                                     #     +2,000,000% from a $0.0001 base)
CANSLIM_A_MIN_CAGR = 0.25            # A: annual EPS CAGR (3y) >= +25%
CANSLIM_I_MIN_INST = 0.20            # I: heldPercentInstitutions >= 20%
CANSLIM_MIN_SCORE = 3                # list membership: C and A and I

# --- CANTATA / CE (breakoutwatch CANTATA Evaluator; lit/CE Overview.html;
# research/breakoutwatch_ce_mapping.md). CET technical (0-7, items 2-5 are
# interpolated 0..1 between breakoutwatch's "worst" and "best"), CEF
# fundamental (0-11, 1 pt each), CE = CET + CEF (0-18). Stock-level, NOT
# pattern-anchored — surfaced as a preset + score columns, like CANSLIM. ---
CANTATA_UD_WINDOW = 50               # CET5 Up/Down volume ratio lookback
CANTATA_UD_BEST = 2.0               # CET5 best value (>= 2.0 -> 1.0)
CANTATA_UD_WORST = 0.7             # CET5 worst value (< 0.7 -> 0.0)
CANTATA_RS_BEST = 99.0             # CET2 RS rank best
CANTATA_RS_WORST = 1.0            # CET2 RS rank worst
CANTATA_52WHIGH_BEST = -15.0      # CET4 pct_from_52w_high best (within 15%)
CANTATA_52WHIGH_WORST = -60.0    # CET4 worst (>60% off)
CANTATA_CEF_QOQ_MIN = 0.18       # CEF1 quarterly EPS YoY, 2 Q's
CANTATA_CEF_YOY_MIN = 0.25       # CEF4 annual EPS YoY, 3 FY's (y4 sparse)
CANTATA_CEF_SALES_MIN = 0.25     # CEF5 quarterly sales YoY
CANTATA_CEF_FWD_MIN = 0.15       # CEF7 forward EPS growth vs trailing
CANTATA_CEF_ROE_MIN = 0.17       # CEF9 return on equity
CANTATA_CEF_CFLO_MIN = 1.20      # CEF10 cash flow / earnings ratio
CANTATA_CEF_INST_MIN_HOLDERS = 5  # CEF8 institutional holder count
CANTATA_MIN_CE = 12.0            # in_cantata membership: CE >= this (of 18)

# --- 1st cat: SCOOTER = SCTR (test_scooter/sctr_model.py, ChartSchool) ---
SCOOTER_MIN_SCORE = 90.0             # StockCharts "leader" zone

# --- 2nd cat: ATR extension (TradingView 60GMm8mE "ALEX", user MAs 21EMA/40SMA) ---
ATR_PERIOD = 14
EXT_EMA_PERIOD = 21                  # user: 21 EMA
EXT_SMA_PERIOD = 40                  # user: 40 SMA (ALEX default is 50)
EXT_THRESHOLD_1 = 2.0                # extended (ALEX "Threshold 1", yellow)
EXT_THRESHOLD_2 = 5.0                # very extended (ALEX "Threshold 2", red)
EXT_BELOW_THRESHOLD = -2.0           # extended below

# --- 2nd cat: ADR / liquidity (ALEX adr_len=20; StockScreenHero "20d ADR %") ---
ADR_PERIOD = 20
ADV_PERIOD = 50                      # 50d avg dollar volume (StockScreenHero "IMPORTANT")
MIN_ADV_DOLLAR = 1_000_000           # lkm_rs liquidity convention
APPLY_LIQUIDITY_GATE = True          # applied to the focus list by default

# --- 2nd cat: Weinstein stages (yf-gics/stage_analysis.py) ---
STAGE_SMA_SHORT = 50
STAGE_SMA_MED = 150
STAGE_SMA_LONG = 200
STAGE_SLOPE_WINDOW = 20
STAGE_SLOPE_RISING = 0.05            # slope200% above this = rising
STAGE_SLOPE_LATE = 0.15              # 2B vs 2C boundary

# --- 2nd cat: RTI (TradingView yaIeno72; local rti_screener.py normalization) ---
RTI_PERIODS = {'short': 5, 'swing': 15, 'long': 50}
RTI_ZONE1 = 5.0                      # extremely tight (0-5)
RTI_ZONE2 = 10.0                     # low volatility (5-10)
RTI_ZONE3 = 15.0                     # moderate low (10-15)
RTI_LOW_VOL = 20.0                   # dots threshold
RTI_DOTS_CONSECUTIVE = 2             # >= 2 consecutive bars below threshold
RTI_EXPANSION_MULT = 2.0             # volatility doubling

# --- Leaders: Stockbee Movers (metaData_v1/src/screeners/stockbee/
# stockbee_screener.py::_run_9m_movers/_run_weekly_movers/_run_daily_gainers;
# more_screeners.md Task 1). Thresholds verbatim from the source. ---
STOCKBEE_REL_VOL_WINDOW = 20         # relative-volume averaging window
STOCKBEE_WEEK_WINDOW = 5             # "week" = last 5 trading days
STOCKBEE_9M_MIN_VOLUME = 9_000_000   # 9M shares today
STOCKBEE_9M_MIN_REL_VOL = 1.25       # today / 20d avg volume
STOCKBEE_WEEKLY_MIN_GAIN_PCT = 20.0  # close(day5) vs open(day1)
STOCKBEE_WEEKLY_MIN_REL_VOL = 1.25   # 5d avg vol / 20d avg vol
STOCKBEE_WEEKLY_MIN_AVG_VOLUME = 100_000
STOCKBEE_DAILY_MIN_GAIN_PCT = 4.0    # close vs previous close
STOCKBEE_DAILY_MIN_REL_VOL = 1.5
STOCKBEE_DAILY_MIN_VOLUME = 100_000

# --- Leaders: Golden Launch Pad (TradingView DvE0wDfI — original now
# removed from TradingView; authoritative port metaData_v1/src/screeners/
# gold_launch_pad.py, params :43-60. more_screeners.md Task 2.) ---
GLP_MA_PERIODS = (10, 20, 50)        # EMA periods (fastest -> slowest)
GLP_ZSCORE_WINDOW = 50               # trailing window for MA z-scores
GLP_MAX_SPREAD = 1.0                 # max (maxZ - minZ) across the 3 EMAs
GLP_SLOPE_LOOKBACK_PCT = 0.3         # linreg lookback = 30% of MA period
GLP_MIN_SLOPE = 0.0001               # per-bar slope, price units
GLP_PROXIMITY_STDEV = 2.0            # |close - cluster avg| <= k * stdev
GLP_PROXIMITY_WINDOW = 20            # rolling stdev window of close
GLP_STRONG_SCORE = 0.7               # spread-score "Strong" threshold

# --- Filter columns: volume + ADX (more_screeners.md Task 3; sources:
# metaData_v1/src/screeners/volume_suite_components/volume_indicators.py
# (VROC :29, ADTV :41, MFI :219) and metaData_v1/src/screeners/adx_report.py
# -> src/indicators/indicators_calculation.py::calculate_adx (Joe Rabil
# ADX(13,8), Wilder RMA). RVOL skipped: == Stockbee's rel_volume_today. ---
VOLADX_VROC_PERIOD = 25
VOLADX_ADTV_WINDOW = 50              # ADTV = avg daily volume in SHARES
VOLADX_MFI_PERIOD = 14
VOLADX_ATR_LEN = 13                  # Rabil ADX(13,8) setup
VOLADX_DI_LEN = 13
VOLADX_ADX_LEN = 8

# --- Leaders: GMMA / Guppy Multiple Moving Average (more_screeners.md
# Task 4; source metaData_v1/src/screeners/guppy_screener.py — alignment
# :287-345, compression breakout :347-410, crossover :411+) ---
GMMA_SHORT_PERIODS = (3, 5, 8, 10, 12, 15)
GMMA_LONG_PERIODS = (30, 35, 40, 45, 50, 60)
GMMA_COMPRESSION_RATIO = 0.02        # total group spread <= 2% = compressed
GMMA_EXPANSION_MULT = 1.5            # breakout: current > 1.5x recent min
GMMA_SPREAD_LOOKBACK = 10            # days of spread history
GMMA_CROSSOVER_CONFIRM_DAYS = 3      # st/lt avg cross within last N days

# --- Leaders: Qullamaggie Suite (more_screeners.md Task 5; source
# metaData_v1/src/screeners/qullamaggie_suite.py — RS :226, MA stack :270,
# ATR-RS :315, range position :349) ---
QULLA_MIN_MARKET_CAP = 1_000_000_000     # $1B
QULLA_RS_THRESHOLD = 97.0                # top 3% on >= 1 horizon
QULLA_RS_HORIZONS = {'1w': 5, '1m': 20, '3m': 60, '6m': 120}
QULLA_ATR_RS_THRESHOLD = 50.0            # ATR percentile vs $1B+ universe
QULLA_RANGE_POSITION = 0.5               # upper half of 20d range
QULLA_RANGE_WINDOW = 20
QULLA_STACK_MAS = ('ema10', 'sma20', 'sma50', 'sma100', 'sma200')

# --- Focus: volume anomaly detector (more_screeners.md Task 6; source
# metaData_v1/src/screeners/volume_suite_components/
# enhanced_volume_anomaly.py::_detect_statistical_anomalies :170-200,
# cross-referenced with HVStdv.py::find_anomalies (std-deviation method)
# and HVAbsoluteETC.py (absolute-spike filtering)) ---
VOLANOM_LOOKBACK = 50               # rolling mean/std window
VOLANOM_STD_THRESHOLD = 3.0         # sigma above rolling mean
VOLANOM_MIN_VOLUME = 100_000        # shares today
VOLANOM_MIN_RELATIVE = 1.5          # vol / rolling mean

# --- Focus: volume records — HVE (Highest Volume Ever). Port of metaVolume's
# daily checker (metaVolume/src/vol_daily_checker.py::check_and_update_hve).
# The frozen baseline (all-time records up to its cutoff) is built in
# metaVolume (`main.py --preset preprocess_full`) and copied here BY HAND:
#   metaVolume/results/pre/historical/{HVE_historical_daily.csv,
#                                      baseline_metadata.json}
#   -> volume_records/baseline/
# This project never builds the baseline; each screener run recomputes the
# ledger (new records after the cutoff) from scratch into volume_records/ledger/.
VOLREC_DIR = SCREENERS_ROOT / 'volume_records'
VOLREC_BASELINE_DIR = VOLREC_DIR / 'baseline'
VOLREC_LEDGER_DIR = VOLREC_DIR / 'ledger'
HVE_MIN_BARS = 252          # < 1y of bars: a "record" is meaningless (IPOs)
HVE_RECENT_BARS = 50        # hve_count_50 window (trading bars)
# --- Focus: 21dma-structure pullback (PrimeTrading "ADJUSTABLE MA
# STRUCTURE" TV script v7.3, gd_systems/primeTrading/; daily defaults) ---
MA21S_LENGTH = 21           # script: dailyLength = 21, dailyType = 'EMA'
MA21S_PULLBACK_PCT = 2.0    # user: close within +-2% of the band (inside
                            # counts as 0) + trend up = pullback mode
HV1Y_BARS = 252             # HV1Y (highest volume in 1 year) window; metaVolume
                            # uses 365 calendar days (HV1Y_window_days) ~ same
HVE_MATCH_TOL = 0.01        # baseline record vs today's file volume on that
                            # date; > 1% off = volume re-adjusted (split)

# --- Leaders: ADL 5-step accumulation suite (more_screeners.md Task 7;
# source metaData_v1/src/screeners/ad_line/ package — adl_calculator,
# adl_mom_analysis, adl_short_term, adl_ma_analysis, adl_composite_scoring;
# all defaults verbatim from the modules' params) ---
ADL_MOM_MIN_PCT = 15.0              # ideal monthly ADL growth range
ADL_MOM_MAX_PCT = 30.0
ADL_MOM_PERIOD = 22                 # bars per "month" (source default 22)
ADL_MOM_LOOKBACK_MONTHS = 6         # only the last 6 monthly changes
ADL_MOM_MIN_CONSISTENCY = 60.0
ADL_MOM_CONSECUTIVE_MONTHS = 3
ADL_SHORT_PERIODS = (5, 10, 20)     # short-term % changes
ADL_SHORT_MOMENTUM_THRESHOLD = 5.0  # % for momentum/acceleration signal
ADL_MA_PERIODS = (20, 50, 100)      # ADL SMA periods
ADL_MA_MIN_SLOPE = 0.01
ADL_W_LONGTERM = 0.4                # composite weights (sum to 1.0)
ADL_W_SHORTTERM = 0.3
ADL_W_MA = 0.3
ADL_MIN_COMPOSITE = 70.0

# --- dashboard context (StockScreenHero panel, dashboard_screener.png) ---
DASHBOARD_MA_PERIODS = {'ema10': ('ema', 10), 'ema21': ('ema', 21),
                        'sma50': ('sma', 50), 'sma200': ('sma', 200)}
MOMENTUM_WINDOWS = {'gain_5d': 5, 'gain_1m': 21, 'gain_3m': 63, 'gain_6m': 126}

# --- Voyage Trading Group momentum-scan windows (Ollie's 1M/3M/6M "% above
# N-day low" scans; docs/workflows_tab.md §5). 21/63/126 trading days = the
# same 5-days-per-week convention as MOMENTUM_WINDOWS / GLB. Column = close vs
# the rolling MIN of the intraday low (matches the TradingView "Price above
# Low" filter, which the Ollie_AllCaps screener snapshots use). ---
ABOVE_LOW_WINDOWS = {'pct_above_21d_low': 21, 'pct_above_63d_low': 63,
                     'pct_above_126d_low': 126}

# --- focus list default gates ---
FOCUS_STAGES = ('2A', '2B')          # early/mid uptrend only
FOCUS_MAX_EXT = EXT_THRESHOLD_2      # exclude very_extended names

# --- output ---
TOP_N_DASHBOARD = 30

# --- Timing: Dr. Wish Blue/Black Dot (feedback_4.md Task 1; source
# metaData_v1/src/screeners/drwish_screener.py — params :51-64, stochastic
# :82-97, blue :314-360, black :361-418; daily timeframe multiplier = 1.0,
# so these ARE the effective values) ---
DRWISH_STOCH_PERIOD = 10            # stochastic %K lookback (both dots)
DRWISH_BLUE_STOCH_THRESHOLD = 20.0  # %K crosses UP through this level
DRWISH_BLUE_SMA_PERIOD = 50         # SMA must be rising (diff > 0)
DRWISH_BLACK_STOCH_THRESHOLD = 25.0  # %K at/below this within lookback
DRWISH_BLACK_LOOKBACK = 3           # bars to look for the oversold print
DRWISH_BLACK_SMA_PERIOD = 30        # trend confirmation (close > SMA)
DRWISH_BLACK_EMA_PERIOD = 21        # trend confirmation (close > EMA)

# --- Timing: PVB price-volume breakout (feedback_4.md Task 2; source
# metaData_v1/src/screeners/pvb_screener.py::_generate_pvb_TWmodel_signals;
# parameter values from metaData_v1/user_data.csv runtime config) ---
PVB_PRICE_BREAKOUT_PERIOD = 30      # rolling high/low window
PVB_VOLUME_BREAKOUT_PERIOD = 30     # rolling volume-high window
PVB_TRENDLINE_LENGTH = 50           # SMA trend filter
PVB_CLOSE_THRESHOLD = 5             # consecutive closes vs SMA -> Close signal
PVB_CACHE_DIR_NAME = 'pvb_cache'    # under results/ — incremental state-machine cache

# --- Timing: ATR1 cloud / vol_stop (feedback_4.md Task 3; source
# metaData_v1/src/screeners/atr1_screener.py:41-107 — "exact
# implementation from atr_cloud.py validated against TradingView") ---
ATR1_LENGTH = 20                    # primary vol-stop ATR length
ATR1_FACTOR = 3.0                   # primary vol-stop ATR multiplier
ATR1_LENGTH2 = 20                   # secondary vol-stop ATR length
ATR1_FACTOR2 = 1.5                  # secondary vol-stop ATR multiplier
ATR1_CACHE_DIR_NAME = 'atr1_cache'  # under results/ — incremental state-machine cache

# --- Patterns: GLB Green Line Breakout (feedback_4.md Task 5; source
# metaData_v1/src/screeners/drwish_screener.py — params :42-48,
# is_pivot_high :99-119, calculate_historical_glb_levels :149-238,
# detect_glb_signals :240-313; daily timeframe, multiplier 1.0) ---
GLB_PIVOT_STRENGTH = 10             # bars left/right for a pivot high
GLB_LOOKBACK_BARS = 63              # '3m' — GLB = highest pivot in window
GLB_HISTORICAL_BARS = 252           # '1y' — how far back to scan pivots
GLB_CONFIRMATION_BARS = 10          # '2w' — unbroken confirmation window
GLB_REQUIRE_CONFIRMATION = True
GLB_MIN_DATA_POINTS = 100
GLB_CACHE_DIR_NAME = 'glb_cache'    # under results/

# Fixed 3-scenario comparison set for the dashboard's "compare presets" mode
# (glb.evaluate_multi). pivot_strength is NOT included, it's shared from
# whatever the dashboard's Pivot strength slider is set to. Order here is
# the display order in the dashboard's combo-picker table. Bar counts use
# the same 5-trading-days-per-week convention as the single-combo dropdowns
# (1w=5, 2w=10, 1m=21, 3m=63, 6m=126, 1y=252, 2y=504).
GLB_PRESET_CHOICES = [
    {'name': '3m_2w', 'label': '3m / 2w',
    'lookback_bars': 63, 'confirmation_bars': 10},
    {'name': '3m_6w', 'label': '3m / 6w',
    'lookback_bars': 63, 'confirmation_bars': 30},
    {'name': '6m_1m', 'label': '6m / 1m',
    'lookback_bars': 126, 'confirmation_bars': 21},
    {'name': '1y_3m', 'label': '1y / 3m',
    'lookback_bars': 252, 'confirmation_bars': 63},
    {'name': '2y_3m', 'label': '2y / 3m',
    'lookback_bars': 504, 'confirmation_bars': 63},
]
GLB_PRESET_DEFAULT_SELECTED = {'3m_2w', '6m_1m', '2y_3m'}

# --- Patterns: Cup & Handle (feedback_4.md Task 6; source patterns_v0/src/
# cup_handle_detector.py + peak_trough_detector.py (kanwalpreet18 K-A-B-C-D
# methodology, scipy.find_peaks). Three parameter presets — Strict is the
# real O'Neil-style definition; Loose is patterns_v0's tuned daily config
# (cup_handle_config.csv 'daily' rows, verbatim) which its own readme
# documents as loosened to force hits (45.5% hit rate, avg quality 18.2).
# Do NOT make Loose the unlabeled default (feedback_4.md Task 6 note).
#
# §16 breakoutwatch.com alignment (IMPLEMENTATION_PLAN §16; digest in
# cup_handle_ideas/cupAndHandle/lit/breakoutwatch_methodology.md) added
# these keys on top of the kanwalpreet18 geometry — Loose keeps every one
# NON-BINDING so it stays byte-identical to patterns_v0's daily config:
#   setup_gain_min       Task A — prior uptrend into the left rim (O'Neil
#                        "prior advance >= 30%"; breakoutwatch "Setup Gain
#                        >= 30%"). Prior low = min over CUPHANDLE_SETUP_LOOKBACK
#                        bars before the left rim.
#   pivot_max_age        Task B — max bars from the right rim (= handle
#                        start = breakoutwatch "pivot") to the last bar
#                        (breakoutwatch: pivot within 90 days).
#   cup_handle_ratio_min Task C — cup length / handle length (breakoutwatch: >= 3).
#   handle_midpoint_rule Task D — require (rim_c + handle_low) / 2 >=
#                        (rim_a + base_low) / 2 (breakoutwatch handle rule).
#   use_intraday_extremes Task H — measure rims off the daily HIGH and
#                        bottoms off the daily LOW (breakoutwatch uses the
#                        intraday extreme of each bar; NOT sub-daily data,
#                        which we don't have and don't need). Falls back to
#                        close when high/low matrices aren't supplied.
#   candidate_selection  'recent' scans ALL constructible K-A-B-C-D and
#                        returns the freshest valid one (so the Task B
#                        recency cap surfaces a current cup, not the
#                        earliest one in a multi-year history); 'first' =
#                        the source's earliest-trough pick, kept for Loose.
# Tasks E/F (HQ/RCQ volume-quality sub-scores) and G (volume-confirmed
# breakout flag) need no config — they use the existing volume_ma_period /
# breakout_volume_factor and always emit their columns. ---
CUPHANDLE_SETUP_LOOKBACK = 252   # §16 Task A: bars before the left rim to
                                 # scan for the prior low (1y cap so an
                                 # ancient low on a long uptrend isn't used)
CUPHANDLE_PRESETS = {
    'strict': {
        # O'Neil-style textbook: cup 12-33% deep, 20-60 days, rims within
        # 5%, handle in the UPPER THIRD of the cup and shallow (<= 30% of
        # cup height), 5-30 days
        'prominence_threshold': 0.05, 'distance_threshold': 5,
        'cup_min_duration': 20, 'cup_max_duration': 60,
        'cup_min_depth_pct': 0.12, 'cup_max_depth_pct': 0.33,
        'cup_depth_tolerance': 0.05,
        'handle_min_duration': 5, 'handle_max_duration': 30,
        'handle_max_depth_pct': 0.30, 'handle_position_min': 2.0 / 3.0,
        'volume_decline_threshold': 0.8, 'breakout_volume_factor': 1.5,
        'volume_ma_period': 20,
        # §16 additions (O'Neil-faithful values)
        'setup_gain_min': 0.30, 'pivot_max_age': 90,
        'cup_handle_ratio_min': 3.0, 'handle_midpoint_rule': True,
        'use_intraday_extremes': True, 'candidate_selection': 'recent',
    },
    'default': {
        # midway between textbook and the loosened source config
        'prominence_threshold': 0.025, 'distance_threshold': 3,
        'cup_min_duration': 10, 'cup_max_duration': 80,
        'cup_min_depth_pct': 0.08, 'cup_max_depth_pct': 0.45,
        'cup_depth_tolerance': 0.12,
        'handle_min_duration': 3, 'handle_max_duration': 40,
        'handle_max_depth_pct': 0.50, 'handle_position_min': 0.5,
        'volume_decline_threshold': 0.8, 'breakout_volume_factor': 1.5,
        'volume_ma_period': 20,
        # §16 additions (midway)
        'setup_gain_min': 0.20, 'pivot_max_age': 150,
        'cup_handle_ratio_min': 2.0, 'handle_midpoint_rule': True,
        'use_intraday_extremes': True, 'candidate_selection': 'recent',
    },
    'loose': {
        # patterns_v0 cup_handle_config.csv 'daily' rows, verbatim —
        # explicitly the permissive option, never the unlabeled default
        'prominence_threshold': 0.005, 'distance_threshold': 1,
        'cup_min_duration': 3, 'cup_max_duration': 120,
        'cup_min_depth_pct': 0.01, 'cup_max_depth_pct': 0.80,
        'cup_depth_tolerance': 0.25,
        'handle_min_duration': 1, 'handle_max_duration': 30,
        'handle_max_depth_pct': 1.00, 'handle_position_min': 0.0,
        'volume_decline_threshold': 0.8, 'breakout_volume_factor': 1.5,
        'volume_ma_period': 20,
        # §16 additions — ALL non-binding: Loose == patterns_v0 daily config
        # (incl. candidate_selection 'first' = source's earliest-trough pick)
        'setup_gain_min': 0.0, 'pivot_max_age': 10 ** 9,
        'cup_handle_ratio_min': 0.0, 'handle_midpoint_rule': False,
        'use_intraday_extremes': False, 'candidate_selection': 'first',
    },
}

# --- Filters/screeners: more_screeners_3.md batch (feedback_7.md) ---
RSI_PERIOD = 14                     # standard Wilder RSI period (provenance
                                    # citation per convention; not a pass/
                                    # fail threshold — RSI is a filter column)
EMA20_SCTR_MIN = 75                 # 20-day EMA pullback: SCTR gate (source:
                                    # EarningsBeats.com scan language via
                                    # more_screeners_3.md)
EMA20_SLOPE_LOOKBACK = 5            # EMA20 rising = today > EMA20 5 bars ago
                                    # (chosen: 5 = one trading week — a
                                    # deliberately lightweight point-to-point
                                    # comparison, not an OLS slope like GLP's)
DOWNTREND_REVERSAL_LOOKBACK_DAYS = 6  # strictly declining daily Highs before
                                      # the reversal bar (EarningsBeats.com
                                      # Pullback Scan via more_screeners_3.md)

# --- Workflows tab (docs/workflows_tab.md) --------------------------------
# A WORKFLOW is a declarative multi-stage screening funnel. Each stage
# narrows its `source` (the full universe, or an earlier stage by name)
# with the SAME two mask builders the All-Results panel uses
# (dashboard_filters.build_mask + build_advanced_mask) — no screening logic
# is forked. The Focus List is the deduped union of the stages flagged
# `focus_input` (or the last stage if none is). These built-ins are
# read-only in the UI; "Duplicate" copies one into my_workflows/*.json.
#
# Stage shape:
#   {'name': str,                     # unique within the workflow
#    'source': 'universe' | <earlier stage name>,
#    'match': 'all' | 'any',          # how to combine `selections` (default 'all')
#    'selections': {filter_key: label | ('custom', lo, hi)},   # build_mask
#    'advanced':   {adv_-key: value},                          # build_advanced_mask
#    'note': str,                     # rationale, shown on the stage card
#    'focus_input': bool}             # feeds the Focus List
#
# `match: 'any'` ORs the selection-grid clauses (e.g. Ollie's 1M/3M/6M
# momentum scans, which are a union); any `advanced` block is still AND'd on
# top of that result.
#
# `selections` keys are dashboard_filters.SPEC_BY_KEY names; `advanced` keys
# are dashboard_filters.ADVANCED_DEFAULTS names. src/workflow.validate_workflow
# and validate.py enforce this.
WORKFLOWS = {
    'Trading Voyage (Ollie)': {
        'description':
            "Oliver Wiedmaier / Voyage Trading Group weekend->focus funnel. "
            "Universe trend filter -> 1M/3M/6M momentum leaders -> tight & "
            "orderly consolidation -> not-extended Focus List. Gap / 10% / "
            "20% 'studies' and every catalyst / pre-market check live in the "
            "manual checklist. Ref: "
            "sandBox/Oliver_wiedmeier/ollie_screening_workflow.md",
        'stages': [
            {'name': 'Universe', 'source': 'universe',
             'selections': {'price': ('custom', 3.0, 1000.0),
                            'adr': '> 3%',
                            'adv': '> $1M',
                            'vs50': '> 0%', 'vs200': '> 0%'},
             'advanced': {'adv_stages': ['2A', '2B']},
             'note': "Ollie 'Universe' scan: price>$3, ADR%>=3, avg vol>=500k, "
                     "close>50SMA>200SMA. (avg vol proxied by 50d ADV>$1M; "
                     "Weinstein 2A/2B ~= the rising MA stack.)",
             'focus_input': False},

            {'name': 'Momentum leaders', 'source': 'Universe',
             'match': 'any',
             'selections': {'above21low': '> 30%', 'above63low': '> 50%',
                            'above126low': '> 100%'},
             'advanced': {},
             'note': "Ollie's 1M/3M/6M momentum scans are a UNION (3 scans "
                     "merged into one watchlist): >=30% above the 21d low OR "
                     ">=50% above the 63d low OR >=100% above the 126d low. "
                     "Min 20% momentum leg before the base.",
             'focus_input': False},

            {'name': 'Tight & orderly', 'source': 'Momentum leaders',
             'selections': {},
             'advanced': {'adv_rti_zone': ['1', '2'],
                          'adv_gold_launch_pad': True},
             'note': "RTI zone 1-2 (range tightening) + Golden Launch Pad "
                     "(EMA 10/20/50 cluster) ~= Ollie's '2 days tight' + "
                     "4/9/21-EMA squeeze.",
             'focus_input': False},

            {'name': 'Focus - not extended', 'source': 'Tight & orderly',
             'selections': {}, 'advanced': {'adv_max_ext21': 3.0, 'adv_max_ext50': 5.0},
             'note': "Jack-in-the-Box ATR gate, Ollie's literal rule: <= 3 ATR "
                     "above the 21 EMA AND <= 5 ATR above the 50 SMA. Also "
                     "skip names whose range today < range yesterday -- "
                     "still compressed (manual).",
             'focus_input': True},
        ],
        'checklist': [
            "Pre-market gap >= 5% on a real catalyst (EPS surprise >= 100%, "
            "revenue >= 30% QoQ, >= 3 analyst upgrades, M&A, product launch)",
            "Pre-market volume >= 10% of average daily volume",
            ">= 200% average volume by the close (HVC); bonus: HV1 / HVE",
            "Close within the top 30% of the day's range",
            "Short interest >= 10% (Type-2, near 52-week-low gap-ups)",
            "Sector leadership -- name is in a leading group",
            "Situational awareness: SPY / QQQ / IWM > 21 EMA; breadth "
            "STRONG/MIXED; % > 200 SMA > 50; net highs > lows",
            "Entry trigger day: range expansion > prior candle, volume > avg "
            "at the close, close within 30% of high, 4-EMA ticking up",
            "Stop = LOD (<= 1 ATR) or 1/2 the day's range; risk 0.25-0.5%; "
            "total open risk <= 2% (VTG Risk Model 1)",
        ],
    },

    'Trading Voyage - Daily studies (Ollie)': {
        'description':
            "The other Voyage entry point: fresh movers, run daily. Three "
            "independent scans off the full universe (10% / 20% / high-volume "
            "gap proxy), all feeding one Focus List. Approximations of Ollie's "
            "'10% study' (change 10% + 200% vol), '20% study' (1-week perf "
            "20%+) and the pre-market gap scan (no intraday data here).",
        'stages': [
            {'name': '10% movers', 'source': 'universe',
             'selections': {}, 'advanced': {'adv_daily_gainers': True},
             'note': "Stockbee 4% daily gainer (>=4% on >=1.5x rel vol) -- the "
                     "closest always-on proxy for Ollie's 10%+200%-vol study.",
             'focus_input': True},
            {'name': '20% weekly', 'source': 'universe',
             'selections': {}, 'advanced': {'adv_weekly_movers': True},
             'note': "Stockbee 20% weekly mover = close(day5) vs open(day1) "
                     ">= 20% -- Ollie's '20% study' (1-week performance).",
             'focus_input': True},
            {'name': 'Gap proxy', 'source': 'universe',
             'selections': {'gain5': '> 10%'},
             'advanced': {'adv_volume_anomaly': True},
             'note': "5-day move >= 10% on a 3-sigma volume spike -- a stand-in "
                     "for a catalyst gap-up (no pre-market feed).",
             'focus_input': True},
        ],
        'checklist': [
            "Confirm a real catalyst (earnings / analyst / FDA / M&A)",
            "Gap >= 5% and opens above near-term resistance",
            ">= 200% average volume by the close (HVC)",
            "Close within the top 30% of the day's range",
            "Not extended: within 3 ATR of the 21 EMA",
            "Situational awareness: indices > 21 EMA; breadth not WEAK",
        ],
    },
}

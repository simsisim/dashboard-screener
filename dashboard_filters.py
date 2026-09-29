"""
All-Results filter panel engine (UI v3, per the user's StockScreenHero
sketch — IMPLEMENTATION_PLAN.md §8).

Separated from dashboard.py so the layout stays declarative:
- THRESHOLD_FAMILIES: dropdown option sets per metric family
- FILTER_SPECS: the 14 sketch filters (4 rows) with column + family
- PRESETS: built-in method templates (Minervini / Weinstein / CANSLIM /
  SCOOTER / RTI consolidation / leaders not-extended)
- build_mask(): threshold selections (+ custom slider ranges) -> boolean mask
- save_screener()/load_screener(): named JSON panels in my_screeners/
- list helpers for my_lists/ (uploaded + saved-from-results ticker lists)

A selection value is either:
  - a label string from the family's option list ('All', '>0', '2-5', ...)
  - ('custom', lo, hi)  — from the revealed slider
"""
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import config  # noqa: E402  (leaf module — WORKFLOWS built-ins for workflow_store)

MY_SCREENERS = ROOT / 'my_screeners'
MY_LISTS = ROOT / 'my_lists'
MY_WORKFLOWS = ROOT / 'my_workflows'

# ---------------------------------------------------------------- families --
def _vs_ma(lo=None, hi=None):
    """% vs moving-average family options."""
    opts = [('All', None), ('> 0%', (0, None)), ('> 2%', (2, None)),
            ('> 5%', (5, None)), ('> 10%', (10, None)),
            ('< 0%', (None, 0)), ('< -2%', (None, -2)), ('< -5%', (None, -5))]
    return opts


def _gain():
    return [('All', None), ('> 0%', (0, None)), ('> 5%', (5, None)),
            ('> 10%', (10, None)), ('> 25%', (25, None)), ('< 0%', (None, 0)),
            ('< -5%', (None, -5)), ('< -10%', (None, -10))]


def _within_high():
    # "Price within %52w High": close is within X% below the high
    return [('All', None), ('within 5%', (-5, 0)), ('within 10%', (-10, 0)),
            ('within 15%', (-15, 0)), ('within 25%', (-25, 0)),
            ('within 50%', (-50, 0))]


def _adr():
    # one-sided floors: an ADR ceiling rarely makes sense for momentum names
    return [('All', None), ('> 3%', (3, None)), ('> 5%', (5, None)),
            ('> 7%', (7, None)), ('> 10%', (10, None)), ('> 20%', (20, None)),
            ('< 2%', (None, 2))]


def _volume():
    return [('All', None), ('> 100K', (100e3, None)), ('> 500K', (500e3, None)),
            ('> 1M', (1e6, None)), ('> 5M', (5e6, None)), ('> 20M', (20e6, None))]


def _adv_dollar():
    return [('All', None), ('> $1M', (1e6, None)), ('> $5M', (5e6, None)),
            ('> $20M', (20e6, None)), ('> $100M', (100e6, None))]


def _price():
    return [('All', None), ('> $5', (5, None)), ('> $10', (10, None)),
            ('> $20', (20, None)), ('> $50', (50, None)), ('> $100', (100, None))]


def _mktcap():
    return [('All', None), ('> $50M (micro+)', (50e6, None)),
            ('> $300M (small+)', (300e6, None)), ('> $2B (mid+)', (2e9, None)),
            ('> $10B (large)', (10e9, None)), ('> $100B', (100e9, None))]


THRESHOLD_FAMILIES = {
    'vs_ma': _vs_ma(), 'gain': _gain(), 'within_high': _within_high(),
    'adr': _adr(), 'volume': _volume(), 'adv_dollar': _adv_dollar(),
    'price': _price(), 'mktcap': _mktcap(),
    'vroc': [('All', None), ('> 0%', (0, None)), ('> 50%', (50, None)),
             ('> 100%', (100, None)), ('< 0%', (None, 0)),
             ('< -50%', (None, -50))],
    'rsi': [('All', None), ('< 30 (oversold)', (None, 30)),
            ('30 - 40', (30, 40)), ('40 - 50', (40, 50)),
            ('50 - 60', (50, 60)), ('> 70', (70, None))],
    'mfi': [('All', None), ('> 80 (overbought)', (80, None)),
            ('60 - 80', (60, 80)), ('40 - 60', (40, 60)),
            ('20 - 40', (20, 40)), ('< 20 (oversold)', (None, 20))],
    'adx': [('All', None), ('> 20 (trending)', (20, None)),
            ('> 25', (25, None)), ('> 30 (strong)', (30, None)),
            ('< 20 (range)', (None, 20))],
    # Voyage Trading Group momentum scans — "price is X% above its N-day low"
    # (Workflows tab; Ollie's 1M/3M/6M snapshots). Column: pct_above_{21,63,
    # 126}d_low from src/indicators.pct_above_rolling_low.
    'above_low': [('All', None), ('> 20%', (20, None)), ('> 30%', (30, None)),
                  ('> 50%', (50, None)), ('> 100%', (100, None)),
                  ('> 200%', (200, None))],
}

# slider bounds per family (for the "Custom…" reveal)
CUSTOM_RANGE = {
    'vs_ma': (-50.0, 50.0, 0.5), 'gain': (-100.0, 300.0, 1.0),
    'within_high': (-100.0, 0.0, 0.5), 'adr': (0.0, 60.0, 0.5),
    'volume': (0.0, 50e6, 100e3), 'adv_dollar': (0.0, 500e6, 1e6),
    'price': (0.0, 1000.0, 1.0), 'mktcap': (0.0, 200e9, 0.5e9),
    'vroc': (-200.0, 500.0, 5.0), 'mfi': (0.0, 100.0, 1.0),
    'adx': (0.0, 60.0, 1.0), 'rsi': (0.0, 100.0, 1.0),
    'above_low': (0.0, 500.0, 5.0),
}

# ----------------------------------------------------------------- filters --
# (key, label, column, family) — the 14 sketch filters + Task-3 columns
FILTER_SPECS = [
    ('mktcap', 'Market Cap', 'market_cap', 'mktcap'),
    ('price', 'Last Closing Price', 'close', 'price'),
    ('vs10', 'Price vs 10ema', 'pct_vs_10ema', 'vs_ma'),
    ('vs21', 'Price vs 21ema', 'pct_vs_21ema', 'vs_ma'),
    ('vs50', 'Price vs 50sma', 'pct_vs_50sma', 'vs_ma'),
    ('vs200', 'Price vs 200sma', 'pct_vs_200sma', 'vs_ma'),
    ('within_high', 'Price within %52w High', 'pct_from_52w_high', 'within_high'),
    ('gain5', 'Price 5d %Gain', 'gain_5d', 'gain'),
    ('gain1m', 'Price 1m %Gain', 'gain_1m', 'gain'),
    ('gain3m', 'Price 3m %Gain', 'gain_3m', 'gain'),
    ('gain6m', 'Price 6m %Gain', 'gain_6m', 'gain'),
    ('adr', '20d ADR %', 'adr20_pct', 'adr'),
    # Voyage Trading Group momentum scans (Workflows tab)
    ('above21low', '% above 21d low', 'pct_above_21d_low', 'above_low'),
    ('above63low', '% above 63d low', 'pct_above_63d_low', 'above_low'),
    ('above126low', '% above 126d low', 'pct_above_126d_low', 'above_low'),
    ('avgvol', '50d Av. Volume', 'avg_volume50', 'volume'),
    ('adv', '50d Av. Dollar Volume (ADV)', 'adv50_dollar', 'adv_dollar'),
    ('rsi14', 'RSI 14', 'rsi14', 'rsi'),
    # Task 3 (volume + ADX columns)
    ('vroc', 'VROC 25d %', 'vroc25', 'vroc'),
    ('adtv', '50d Avg Daily Volume (shares)', 'adtv_50', 'volume'),
    ('mfi', 'MFI 14', 'mfi14', 'mfi'),
    ('adx', 'ADX 13 (trend strength)', 'adx13', 'adx'),
]
SPEC_BY_KEY = {k: (label, col, fam) for k, label, col, fam in FILTER_SPECS}

ROW1 = ['mktcap', 'price', 'vs10']          # + sector/industry multi-selects
ROW2 = ['vs21', 'vs50', 'vs200', 'within_high', 'gain5']
ROW3 = ['gain1m', 'gain3m', 'gain6m', 'adr', 'avgvol']
ROW4 = ['adv']

DEFAULT_SELECTION = {k: 'All' for k in SPEC_BY_KEY}


def selection_to_range(value, family):
    """Selection -> (lo, hi) floats (None = open end), or None for 'All'.
    A 'custom' range is a tuple in live UI code but a list after a JSON round
    trip (saved screeners, config.WORKFLOWS built-ins) — accept both."""
    if value is None or value == 'All':
        return None
    if isinstance(value, (tuple, list)) and value and value[0] == 'custom':
        return (float(value[1]), float(value[2]))
    opts = dict(THRESHOLD_FAMILIES[family])
    return opts.get(value)


def build_mask(df: pd.DataFrame, selections: dict,
               match: str = 'all') -> pd.Series:
    """Apply the sketch-filter selections to a results DataFrame.
    NaN never passes a one-sided threshold (notna() is required).

    `match='all'` (default, and the only mode the All-Results panel uses)
    ANDs the active clauses; `match='any'` ORs them — a Workflows-tab stage
    can set it so one stage expresses e.g. Ollie's 1M/3M/6M momentum scans,
    which are a union. 'All'-valued selections are ignored in both modes; an
    empty / all-'All' stage yields all-True regardless of `match`.
    """
    clauses = []
    for key, value in selections.items():
        _label, col, fam = SPEC_BY_KEY[key]
        rng = selection_to_range(value, fam)
        if rng is None:
            continue
        lo, hi = rng
        s = df[col]
        c = pd.Series(True, index=df.index)
        if lo is not None:
            c &= s.notna() & (s >= lo)
        if hi is not None:
            c &= s.notna() & (s <= hi)
        clauses.append(c)
    if not clauses:
        return pd.Series(True, index=df.index)
    out = clauses[0].copy()
    for c in clauses[1:]:
        if match == 'any':
            out |= c
        else:
            out &= c
    return out


# ------------------------------------------------------- advanced mask -----
# adv_<flag> checkboxes whose mask IS the boolean `in_<flag[4:]>` column.
ADVANCED_FLAG_KEYS = (
    'adv_9m_movers', 'adv_weekly_movers', 'adv_daily_gainers',
    'adv_gold_launch_pad', 'adv_qullamaggie', 'adv_volume_anomaly',
    'adv_adl_accumulation', 'adv_52w_high_breakout', 'adv_52w_low_breakdown',
    'adv_ema20_pullback', 'adv_downtrend_reversal', 'adv_cantata',
)


def build_advanced_mask(df: pd.DataFrame, advanced: dict,
                        idx_map: dict | None = None) -> pd.Series:
    """The All-Results 'Advanced' panel (+ sector / industry) as a pure
    boolean mask — extracted verbatim from dashboard.py so the Workflows
    engine (src/workflow.py) reuses the SAME logic instead of forking it.

    `advanced` holds the adv_-prefixed keys from ADVANCED_DEFAULTS plus
    sel_sector / sel_industry; any missing key falls back to the no-op
    default. `idx_map` (ticker -> frozenset of index names, from
    on_demand.universe_index_map()) is consulted only when adv_index is set.
    """
    a = {**ADVANCED_DEFAULTS, **(advanced or {})}
    mask = pd.Series(True, index=df.index)
    if a['sel_sector']:
        mask &= df['sector'].isin(a['sel_sector'])
    if a['sel_industry']:
        mask &= df['industry'].isin(a['sel_industry'])
    if a['adv_leaders']:
        cols = [f'in_{s}' for s in a['adv_leaders']]
        if all(c in df.columns for c in cols):
            flags = df[cols].fillna(False).astype(bool)
            mask &= (flags.any(axis=1)
                     if a['adv_leaders_mode'].startswith('Any')
                     else flags.all(axis=1))
    if a['adv_stages']:
        mask &= df['stage'].isin(a['adv_stages'])
    # Trading Voyage (Ollie) rule: separate caps vs the 21 EMA and the 50 SMA
    if a.get('adv_max_ext21', 10.0) < 10.0:
        mask &= df['ext_21ema_atr'].fillna(99) <= a['adv_max_ext21']
    if a.get('adv_max_ext50', 10.0) < 10.0 and 'ext_50sma_atr' in df.columns:
        mask &= df['ext_50sma_atr'].fillna(99) <= a['adv_max_ext50']
    if a['adv_max_ext'] < 10.0:
        mask &= (df['ext_21ema_atr'].fillna(99) <= a['adv_max_ext']) & \
                (df['ext_40sma_atr'].fillna(99) <= a['adv_max_ext'])
    mask &= df['rs_pct'].fillna(0) >= a['adv_min_rs']
    if 'minervini_count' in df.columns:
        mask &= df['minervini_count'].fillna(0) >= a['adv_min_count']
    if a['adv_rti_zone']:
        mask &= df['rti_zone'].isin(a['adv_rti_zone'])
    if a['adv_rti_dots']:
        mask &= df['rti_dots'].fillna(False).astype(bool)
    if a['adv_rti_exp']:
        mask &= df['rti_expansion'].fillna(False).astype(bool)
    for _flag in ADVANCED_FLAG_KEYS:
        if a.get(_flag):
            mask &= df[f'in_{_flag[4:]}'].fillna(False).astype(bool)
    if a.get('adv_ce_min', 0.0) > 0 and 'ce_score' in df.columns:
        mask &= df['ce_score'].fillna(0) >= a['adv_ce_min']
    if a.get('adv_gmma_state'):
        mask &= df['gmma_state'].isin(a['adv_gmma_state'])
    if a['adv_exchange']:
        mask &= df['exchange'].isin(a['adv_exchange']).fillna(False)
    if a['adv_index'] and idx_map is not None:
        _sel = set(a['adv_index'])
        mask &= pd.Series(df.index.map(
            lambda t: bool(idx_map.get(str(t).upper(), frozenset()) & _sel)),
            index=df.index)
    return mask


# ----------------------------------------------------------------- presets --
# Method templates (user decision: Presets = built-in method templates).
# Shape (must match the reader in dashboard.py::_apply_preset):
#   {'selections': {filter_key: option-label OR ('custom', lo, hi)},
#    'advanced':   {ADVANCED_DEFAULTS-key: value}}
# The 'advanced' keys MUST be the adv_-prefixed session-state names from
# ADVANCED_DEFAULTS (feedback_2.md §0: short names silently no-op) —
# validate.py's all-presets behavioral check enforces this.
# 'leaders_mode' uses the widget's literal vocabulary ('Any (union)' /
# 'All (intersection)').
PRESETS = {
    'Minervini 8/8 (liquid)': {
        'selections': {'adv': '> $1M'},
        'advanced': {'adv_leaders': ['minervini'],
                     'adv_leaders_mode': 'Any (union)'},
    },
    'Weinstein 2A/2B not extended': {
        'selections': {'adv': '> $1M'},
        'advanced': {'adv_stages': ['2A', '2B'], 'adv_max_ext': 2.0},
    },
    'CANSLIM C-A-I leaders': {
        'selections': {},
        'advanced': {'adv_leaders': ['canslim'],
                     'adv_leaders_mode': 'Any (union)'},
    },
    'SCOOTER >= 90': {
        'selections': {},
        'advanced': {'adv_leaders': ['scooter'],
                     'adv_leaders_mode': 'Any (union)'},
    },
    # breakoutwatch CANTATA Evaluator — CET (0-7) + CEF (0-11) = CE (0-18);
    # a stock-quality composite in the same slot as CANSLIM / Minervini
    # (research/breakoutwatch_ce_mapping.md). Preset mirrors the leaders
    # list (in_cantata == CE >= config.CANTATA_MIN_CE).
    'CANTATA CE leaders': {
        'selections': {},
        'advanced': {'adv_leaders': ['cantata'],
                     'adv_leaders_mode': 'Any (union)'},
    },
    'Tight consolidation (RTI)': {
        'selections': {'adv': '> $1M'},
        'advanced': {'adv_rti_zone': ['1', '2']},
    },
    'Leaders not extended (<= 2 ATR)': {
        'selections': {'adv': '> $1M'},
        'advanced': {'adv_leaders': ['minervini', 'canslim', 'scooter'],
                     'adv_leaders_mode': 'Any (union)', 'adv_max_ext': 2.0},
    },
    # Corsellis's own example (TAXONOMY.md): vs50sma above + vs200sma above
    # + 20d ADR% > 6% + 50d ADV > 50M — the ADR>6% needs the custom slider
    'Momentum Leader (Narrow)': {
        'selections': {'vs50': '> 0%', 'vs200': '> 0%',
                       'adr': ('custom', 6.0, 60.0), 'adv': '> $20M'},
        'advanced': {},
    },
    # Trading Voyage (Ollie) funnel as single presets (Workflows tab has the
    # full multi-stage version). The 1M/3M/6M momentum UNION stage is not
    # expressible here (presets AND their selections) so it is left out.
    'TW: Tight and orderly': {
        'selections': {'price': ('custom', 3.0, 1000.0), 'adr': '> 3%',
                       'adv': '> $1M', 'vs50': '> 0%', 'vs200': '> 0%'},
        'advanced': {'adv_stages': ['2A', '2B'], 'adv_rti_zone': ['1', '2'],
                     'adv_gold_launch_pad': True},
    },
    'TW: not extended': {
        'selections': {'price': ('custom', 3.0, 1000.0), 'adr': '> 3%',
                       'adv': '> $1M', 'vs50': '> 0%', 'vs200': '> 0%'},
        'advanced': {'adv_stages': ['2A', '2B'], 'adv_rti_zone': ['1', '2'],
                     'adv_gold_launch_pad': True, 'adv_max_ext21': 3.0,
                     'adv_max_ext50': 5.0},   # Ollie: <=3 ATR/21EMA, <=5 ATR/50SMA
    },
    'Large-cap uptrend pullback': {
        'selections': {'mktcap': '> $10B (large)', 'vs200': '> 0%',
                       'within_high': 'within 25%', 'adv': '> $5M'},
        'advanced': {'adv_stages': ['2A', '2B']},
    },
    # ---- more_screeners.md backlog presets (feedback_3.md) ----
    # Stockbee's three are distinct scans in its own methodology — kept
    # separate (same pattern as Minervini/CANSLIM/SCOOTER), shared prefix
    # for dropdown scannability.
    'Stockbee 9M Movers': {
        # the 9M-share volume rule already is a liquidity gate — no extra
        # 'adv' floor (feedback_3.md §1)
        'selections': {},
        'advanced': {'adv_9m_movers': True},
    },
    'Stockbee 20% Weekly Movers': {
        'selections': {},
        'advanced': {'adv_weekly_movers': True},
    },
    'Stockbee 4% Daily Gainers': {
        'selections': {},
        'advanced': {'adv_daily_gainers': True},
    },
    'Golden Launch Pad': {
        # liquidity floor per the structural-preset convention (Minervini/
        # Weinstein/RTI all bundle one)
        'selections': {'adv': '> $1M'},
        'advanced': {'adv_gold_launch_pad': True},
    },
    'Qullamaggie Suite': {
        # NO mktcap selection: the in_qullamaggie flag already encodes the
        # methodology's $1B gate internally (user decision — a $2B bucket
        # would over-restrict; a custom $1B slider would be redundant)
        'selections': {},
        'advanced': {'adv_qullamaggie': True},
    },
    'ADL Accumulation': {
        'selections': {},
        'advanced': {'adv_adl_accumulation': True},
    },
}


def normalize_selections(sel: dict) -> dict:
    """Fill missing keys with 'All'; drop unknown keys."""
    out = dict(DEFAULT_SELECTION)
    for k, v in (sel or {}).items():
        if k in out:
            out[k] = v
    return out


# No-op value for EVERY advanced/sector/industry session-state key — the
# single source of truth used by _apply_preset, load_screener,
# _reset_filters and _init_filter_state, so presets, saved screeners and
# reset all produce the same clean baseline (feedback_1.md §1).
ADVANCED_DEFAULTS = {
    'adv_leaders': [],
    'adv_leaders_mode': 'Any (union)',
    'adv_stages': [],
    'adv_max_ext': 10.0,
    'adv_max_ext21': 10.0,
    'adv_max_ext50': 10.0,
    'adv_min_rs': 0.0,
    'adv_min_count': 0,
    'adv_rti_zone': [],
    'adv_rti_dots': False,
    'adv_rti_exp': False,
    'adv_exchange': [],
    'adv_index': [],
    'sel_sector': [],
    'sel_industry': [],
    'adv_9m_movers': False,
    'adv_weekly_movers': False,
    'adv_daily_gainers': False,
    'adv_gold_launch_pad': False,
    'adv_gmma_state': [],
    'adv_qullamaggie': False,
    'adv_volume_anomaly': False,
    'adv_adl_accumulation': False,
    'adv_52w_high_breakout': False,
    'adv_52w_low_breakdown': False,
    'adv_ema20_pullback': False,
    'adv_downtrend_reversal': False,
    'adv_cantata': False,
    'adv_ce_min': 0.0,
}


# ------------------------------------------------------------ persistence ---
def save_screener(name: str, selections: dict, advanced: dict | None = None) -> Path:
    MY_SCREENERS.mkdir(exist_ok=True)
    payload = {'selections': normalize_selections(selections),
               'advanced': advanced or {}}
    path = MY_SCREENERS / f'{_safe(name)}.json'
    path.write_text(json.dumps(payload, indent=2))
    return path


def load_screener(name: str) -> dict | None:
    path = MY_SCREENERS / f'{_safe(name)}.json'
    if not path.exists():
        return None
    return json.loads(path.read_text())


# ------------------------------------------------------- combine screens ---
# All-Results "Combine screens" row: presets and saved screeners are combined
# at MASK level (each evaluated independently from the clean baseline), not
# loaded into the widgets — one panel can't hold two conflicting presets.
MY_SCREENER_PREFIX = 'My: '


# Category -> presets, for the chip picker (StockCharts-Screener style).
# A preset missing here still shows up, under 'Other'.
PRESET_CATEGORIES = {
    'Leaders': ['Minervini 8/8 (liquid)', 'CANSLIM C-A-I leaders',
                'SCOOTER >= 90', 'CANTATA CE leaders',
                'Leaders not extended (<= 2 ATR)'],
    'Trend & stage': ['Weinstein 2A/2B not extended',
                      'Large-cap uptrend pullback', 'Momentum Leader (Narrow)'],
    'Tight / not extended': ['Tight consolidation (RTI)', 'TW: Tight and orderly',
                             'TW: not extended', 'Golden Launch Pad'],
    'Movers': ['Stockbee 20% Weekly Movers', 'Stockbee 4% Daily Gainers',
               'Qullamaggie Suite'],
    'Volume & accumulation': ['Stockbee 9M Movers', 'ADL Accumulation'],
}


def screen_categories() -> dict:
    """Category -> screen labels: PRESET_CATEGORIES, 'Other' for uncategorised
    presets, then 'My screeners' (saved, prefixed 'My: ') when any exist."""
    cats = {c: [p for p in ps if p in PRESETS]
            for c, ps in PRESET_CATEGORIES.items()}
    placed = {p for ps in cats.values() for p in ps}
    other = [p for p in PRESETS if p not in placed]
    if other:
        cats['Other'] = other
    mine = [MY_SCREENER_PREFIX + n for n in saved_screeners()]
    if mine:
        cats['My screeners'] = mine
    return {c: ps for c, ps in cats.items() if ps}


def combinable_screens() -> list:
    """Every pickable screen label, in category order."""
    return [s for ps in screen_categories().values() for s in ps]


def screen_spec(label: str) -> dict | None:
    if label.startswith(MY_SCREENER_PREFIX):
        return load_screener(label[len(MY_SCREENER_PREFIX):])
    return PRESETS.get(label)


def screen_mask(df: pd.DataFrame, spec: dict,
                idx_map: dict | None = None) -> pd.Series:
    """One preset / saved screener as a boolean mask (same logic as loading
    it into the panel: threshold grid AND advanced panel)."""
    return (build_mask(df, normalize_selections(spec.get('selections', {})))
            & build_advanced_mask(df, spec.get('advanced', {}), idx_map))


def combine_screens(df: pd.DataFrame, include: list, exclude: list,
                    mode: str = 'all', idx_map: dict | None = None):
    """(Include_1 AND/OR Include_2 ...) AND NOT (any Exclude).
    Returns (mask, hits) — hits is a bool DataFrame, one column per Include
    screen, for the matched_by / hits result columns. No Include screens =
    all-True start (so Exclude alone still works)."""
    hits = pd.DataFrame(index=df.index)
    for lbl in include:
        spec = screen_spec(lbl)
        if spec is not None:
            hits[lbl] = screen_mask(df, spec, idx_map)
    if hits.shape[1] == 0:
        mask = pd.Series(True, index=df.index)
    elif mode == 'any':
        mask = hits.any(axis=1)
    else:
        mask = hits.all(axis=1)
    for lbl in exclude:
        spec = screen_spec(lbl)
        if spec is not None:
            mask &= ~screen_mask(df, spec, idx_map)
    return mask, hits


def saved_screeners() -> list:
    if not MY_SCREENERS.exists():
        return []
    return sorted(p.stem for p in MY_SCREENERS.glob('*.json'))


def delete_screener(name: str) -> bool:
    path = MY_SCREENERS / f'{_safe(name)}.json'
    if path.exists():
        path.unlink()
        return True
    return False


def save_list(name: str, tickers) -> Path:
    MY_LISTS.mkdir(exist_ok=True)
    path = MY_LISTS / f'{_safe(name)}.csv'
    pd.DataFrame({'Symbol': sorted(set(tickers))}).to_csv(path, index=False)
    return path


def load_list(name: str) -> list:
    path = MY_LISTS / f'{_safe(name)}.csv'
    if not path.exists():
        return []
    return pd.read_csv(path)['Symbol'].astype(str).tolist()


def saved_lists() -> list:
    if not MY_LISTS.exists():
        return []
    return sorted(p.stem for p in MY_LISTS.glob('*.csv'))


# --------------------------------------------------- TradingView export ----
# TradingView's "Upload list…" wants a .txt of EXCHANGE:SYMBOL tokens, comma
# separated, with optional ###header section dividers; ≤ 1000 symbols per file.
# "The input file must be in the .txt format and symbols should have the
#  exchange prefix and comma separated."
# https://www.tradingview.com/support/solutions/43000487233
TV_EXCHANGE_MAP = {
    'NASDAQ': 'NASDAQ',
    'NYSE': 'NYSE',
    'NYSE ARCA': 'AMEX',
    'NYSEARCA': 'AMEX',
    'NYSE AMERICAN': 'AMEX',
    'AMEX': 'AMEX',
    'BATS': 'AMEX',
    'CBOE': 'CBOE',
    'OTC': 'OTC',
}


def tradingview_watchlist(tickers, exchanges=None, section=None) -> str:
    """Render tickers as TradingView watchlist `.txt` text.

    `tickers`   sequence of symbols, or a DataFrame / Series indexed by ticker
                (its `exchange` column is used automatically when present).
    `exchanges` optional ``{ticker: raw exchange name}``; a ticker whose
                exchange maps to a known TradingView market is emitted as
                ``EXCHANGE:SYMBOL``, otherwise bare (TradingView auto-resolves
                unambiguous US equities).
    `section`   optional header, emitted first as a ``###section`` divider.
    """
    if hasattr(tickers, 'index') and not isinstance(tickers, (list, tuple, set)):
        cols = getattr(tickers, 'columns', None)
        exch_col = (tickers['exchange'] if exchanges is None and cols is not None
                    and 'exchange' in cols else None)
        exchanges = exchanges or {}
        pairs = [(t, exch_col.iloc[k] if exch_col is not None
                  else exchanges.get(t))
                 for k, t in enumerate(tickers.index)]
    else:
        exchanges = exchanges or {}
        pairs = [(t, exchanges.get(t)) for t in tickers]
    seen, toks = set(), []
    if section:
        toks.append('###' + str(section).strip())
    for t, exch in pairs:
        sym = str(t).strip().upper()
        if not sym or sym == 'NAN' or sym in seen:
            continue
        seen.add(sym)
        exch = '' if exch is None or exch != exch else str(exch)  # NaN -> ''
        pfx = TV_EXCHANGE_MAP.get(exch.strip().upper())
        toks.append(f'{pfx}:{sym}' if pfx else sym)
    return ','.join(toks) + '\n'


# ---------------------------------------------------- workflow store -------
# Built-ins (config.WORKFLOWS) are read-only; user copies are JSON in
# my_workflows/. Same pattern as save_screener / saved_screeners / ...
# (docs/workflows_tab.md §6).
def builtin_workflows() -> dict:
    """name -> workflow dict, from config.WORKFLOWS (deep-copied, read-only)."""
    return json.loads(json.dumps(getattr(config, 'WORKFLOWS', {})))


def is_builtin_workflow(name: str) -> bool:
    return name in getattr(config, 'WORKFLOWS', {})


def saved_workflows() -> list:
    if not MY_WORKFLOWS.exists():
        return []
    return sorted(p.stem for p in MY_WORKFLOWS.glob('*.json'))


def load_workflow(name: str) -> dict | None:
    """Built-in first (read-only copy), then my_workflows/<safe>.json."""
    bi = getattr(config, 'WORKFLOWS', {})
    if name in bi:
        wf = json.loads(json.dumps(bi[name]))
        wf['name'] = name
        return wf
    path = MY_WORKFLOWS / f'{_safe(name)}.json'
    if path.exists():
        wf = json.loads(path.read_text())
        wf.setdefault('name', name)
        return wf
    return None


def save_workflow(name: str, wf: dict) -> Path:
    MY_WORKFLOWS.mkdir(exist_ok=True)
    payload = dict(wf)
    payload['name'] = name
    path = MY_WORKFLOWS / f'{_safe(name)}.json'
    path.write_text(json.dumps(payload, indent=2))
    return path


def delete_workflow(name: str) -> bool:
    """my_workflows/ only — built-ins can't be deleted."""
    path = MY_WORKFLOWS / f'{_safe(name)}.json'
    if path.exists():
        path.unlink()
        return True
    return False


def _safe(name: str) -> str:
    return ''.join(c if c.isalnum() or c in '-_ ' else '_' for c in name).strip()

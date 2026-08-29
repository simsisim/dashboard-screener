"""
Dashboard-style reporting (intro.md: dashboard format per the StockScreenHero
screener — filter panel + sortable results; dashboard_screener.png).

Outputs per run (results/YYYY-MM-DD/):
  screener_results.csv  — every ticker x every metric (the filter-panel data)
  leaders_*.csv         — the 3 leaders' lists + combined union
  focus_list.csv        — filtered focus list
  dashboard.md          — human-readable summary tables
Console mirrors dashboard.md.
"""
import sys
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config


def run_dir() -> Path:
    d = config.RESULTS_DIR / date.today().strftime('%Y-%m-%d')
    d.mkdir(parents=True, exist_ok=True)
    return d


def _fmt(df: pd.DataFrame, cols: list, renames: dict | None = None) -> str:
    use = [c for c in cols if c in df.columns]
    out = df[use].copy()
    if out.index.name and out.index.name not in out.columns:
        out.insert(0, out.index.name, out.index)
    if renames:
        out = out.rename(columns={k: v for k, v in renames.items() if k in out.columns})
    return out.to_string(index=False)


def write_dashboard(md_path: Path, universe_meta: dict, results: dict):
    lines = []
    ap = lines.append

    ap(f"# Step-2 Filters Dashboard — {date.today().isoformat()}")
    ap("")
    ap(f"Universe: {universe_meta['n_universe']} tickers | loaded: "
       f"{universe_meta['n_loaded']} | missing: {len(universe_meta['missing'])} | "
       f"short history: {len(universe_meta['short'])}")
    ap(f"Data span: {universe_meta.get('span', 'n/a')}")
    ap("")

    ap("## Leaders' Lists (1st cat filters)")
    ap("")
    for name, label in [('minervini', 'Minervini trend template (8/8)'),
                        ('canslim', 'CANSLIM C-A-I (C and A and I)'),
                        ('scooter', 'SCOOTER / SCTR >= 90'),
                        ('cantata', f'CANTATA CE >= {config.CANTATA_MIN_CE} (of 18)')]:
        df = results.get(f'leaders_{name}')
        n = 0 if df is None else len(df)
        ap(f"- **{label}**: {n} tickers")
    uni = results.get('leaders_union')
    if uni is not None:
        ap(f"- **Union (deduped)**: {len(uni)} tickers | "
           f"in 2+ lists: {(uni['n_sources'] >= 2).sum()} | "
           f"in all 3: {(uni['n_sources'] == 3).sum()}")
    ap("")

    focus = results.get('focus')
    ap("## Focus List (2nd cat filters)")
    ap("")
    if focus is not None:
        ap(f"Gates: stage in {config.FOCUS_STAGES} | not very_extended "
           f"(|ext| <= {config.FOCUS_MAX_EXT}) | liquidity >= "
           f"${config.MIN_ADV_DOLLAR:,}/day")
        ap("")
        if len(focus):
            cols = ['ticker', 'close', 'scooter_score', 'rs_pct', 'stage',
                    'ext_21ema_atr', 'ext_40sma_atr', 'adr20_pct', 'rti',
                    'rti_zone', 'adv50_dollar', 'market_cap', 'sector']
            ap(_fmt(focus.head(config.TOP_N_DASHBOARD), cols, {
                'ext_21ema_atr': 'ext21(ATR)', 'ext_40sma_atr': 'ext40(ATR)',
                'scooter_score': 'SCOOTER', 'rs_pct': 'RS%',
                'adv50_dollar': 'ADV50$'}))
        else:
            ap("(empty — no ticker passed all gates)")
    ap("")

    stage_dist = results.get('stage_distribution')
    if stage_dist is not None:
        ap("## Stage distribution (universe)")
        ap("")
        ap(stage_dist.to_string())
        ap("")

    ap(f"Full metrics for all tickers: `screener_results.csv` "
       f"({universe_meta['n_loaded']} rows) — filter any column like the "
       f"StockScreenHero panel.")
    ap("")

    md_path.write_text('\n'.join(lines))
    return '\n'.join(lines)

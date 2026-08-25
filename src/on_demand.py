"""
On-demand scoped computation plumbing (feedback_4.md — Timing Signals and
Patterns tabs).

The daily batch (run_screeners.py) computes the always-on screeners for
the full universe once a day. The six timing/pattern screeners are
expensive enough that they instead run ON DEMAND against a scoped subset:

  scope  = index membership (universe-CSV 'Index' column) + min market cap
  run    = per-ticker processing with a progress callback
  persist= results/{date}/{tab}_{scope_key}.csv (same-day reuse)

Shared by both new tabs — tab-specific code should not duplicate this.
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
import config


def universe_index_map() -> dict:
    """ticker -> frozenset of index memberships (universe CSV 'Index'
    column, comma-separated). Plain function — the dashboard wraps it in
    st.cache_data."""
    u = pd.read_csv(config.UNIVERSE_CSV)
    mapping = {}
    for sym, raw in zip(u['Symbol'].astype(str), u.get('Index', pd.Series(dtype=str))):
        parts = {p.strip() for p in str(raw).split(',')} if pd.notna(raw) else set()
        mapping[sym.strip().upper()] = frozenset(p for p in parts if p)
    return mapping


def index_choices() -> list:
    counts = {}
    for members in universe_index_map().values():
        for idx in members:
            counts[idx] = counts.get(idx, 0) + 1
    return sorted(counts, key=counts.get, reverse=True)


def resolve_scope(index_names, min_mktcap, market_cap: pd.Series) -> list:
    """Tickers in ANY of the selected indexes with market_cap >= floor.
    market_cap: the screener_results.csv column (computed daily for the
    full universe)."""
    idx_map = universe_index_map()
    wanted = set(index_names or [])
    tickers = [t for t, members in idx_map.items()
               if not wanted or (members & wanted)]
    if min_mktcap and min_mktcap > 0:
        caps = market_cap.reindex(tickers)
        tickers = [t for t in tickers
                   if pd.notna(caps.get(t)) and caps[t] >= min_mktcap]
    return sorted(tickers)


def sources_slug(source_labels) -> str:
    """Stable slug for a set of source labels — the cache-filename
    component that keeps different signal sources' results separate.
    Single source of truth: dashboard.py and test_dashboard_app.py both
    build filenames through this (a test that re-implements the slug
    inline is how the source-suffix drift slipped past its check)."""
    return '-'.join(sorted(s.lower().replace(' ', '')
                           for s in (source_labels or [])))


def scope_key(index_names, min_mktcap) -> str:
    """Stable file-key for a scope, e.g. 'sp500_cap0' / 'snp500+nasdaq100_cap2e9'."""
    names = sorted(n.lower().replace(' ', '') for n in (index_names or [])) \
        or ['all']
    key = '+'.join(names)
    key = ''.join(c if c.isalnum() or c in '+_' else '_' for c in key)
    cap = int(min_mktcap or 0)
    return f'{key}_cap{cap}'


def run_scoped(tickers, data, sources: dict, progress_cb=None):
    """
    Run {source_name: evaluate_fn([t], sub_data)} per ticker over the
    scoped subset, with a progress callback (processed, total).

    sources' evaluate functions must accept ([ticker], sub_data) and
    return a one-row DataFrame indexed by ticker (the project's module
    signature). Returns {source_name: combined DataFrame}.
    """
    out = {name: [] for name in sources}
    frames = {k: v for k, v in data.items() if isinstance(v, pd.DataFrame)}
    # keep only tickers that actually loaded (universe scope can include
    # symbols with no data file / short history)
    if frames:
        common = set.intersection(*[set(f.columns) for f in frames.values()])
        tickers = [t for t in tickers if t in common]
    total = max(1, len(tickers))
    for i, t in enumerate(tickers):
        sub = {k: v[[t]] for k, v in frames.items()}
        for name, fn in sources.items():
            out[name].append(fn([t], sub))
        if progress_cb:
            progress_cb(i + 1, total)
    combined = {}
    for name, frames in out.items():
        df = pd.concat(frames)
        if 'ticker' in df.columns:
            df = df.set_index('ticker')
        combined[name] = df
    return combined


def results_path(run_dir: Path, tab: str, key: str) -> Path:
    return run_dir / f'{tab}_{key}.csv'


def load_cached(run_dir: Path, tab: str, key: str) -> pd.DataFrame | None:
    p = results_path(run_dir, tab, key)
    if p.exists():
        try:
            df = pd.read_csv(p, index_col='ticker')
            return df
        except Exception:
            return None
    return None


def persist(run_dir: Path, tab: str, key: str, df: pd.DataFrame) -> Path:
    run_dir.mkdir(parents=True, exist_ok=True)
    p = results_path(run_dir, tab, key)
    df.to_csv(p)
    return p

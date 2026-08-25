"""
List operations for the leaders' lists (intro.md §1: "intersection, union,
threshold criteria filtering; or combined (unify all 3 into 1, remove
duplicates)").
"""
import pandas as pd


def union(lists: dict) -> pd.DataFrame:
    """
    Unify leader lists and remove duplicates.

    lists: {'minervini': df_indexed_by_ticker, 'canslim': ..., 'scooter': ...}
    Returns one row per ticker with per-source membership flags and the
    union of each source's score columns (first non-null wins, priority
    minervini > canslim > scooter).
    """
    frames = {k: v for k, v in lists.items() if v is not None and len(v)}
    if not frames:
        return pd.DataFrame(columns=['ticker', 'sources', 'n_sources'])

    all_idx = sorted(set().union(*[set(f.index) for f in frames.values()]))
    out = pd.DataFrame(index=all_idx)
    out.index.name = 'ticker'

    for name in ('minervini', 'canslim', 'scooter'):
        f = frames.get(name)
        out[f'in_{name}'] = [name in frames and t in frames[name].index
                             for t in all_idx]
    out['sources'] = out.apply(
        lambda r: '+'.join(s for s in ('minervini', 'canslim', 'scooter') if r[f'in_{s}']),
        axis=1)
    out['n_sources'] = out['sources'].str.count(r'\+') + 1

    # carry over the useful score columns
    carry = {
        'minervini': ['minervini_count', 'rs_pct'],
        'canslim': ['C_yoy', 'A_cagr', 'inst_pct', 'canslim_score'],
        'scooter': ['scooter_score'],
    }
    for name, cols in carry.items():
        f = frames.get(name)
        for col in cols:
            if f is not None and col in f.columns:
                out[col] = f[col].reindex(all_idx)
    return out


def intersection(lists: dict) -> pd.DataFrame:
    """Tickers present in ALL provided lists."""
    frames = [v for v in lists.values() if v is not None and len(v)]
    if not frames:
        return pd.DataFrame()
    idx = set(frames[0].index)
    for f in frames[1:]:
        idx &= set(f.index)
    combined = union(lists)
    return combined[combined.index.isin(idx)].copy()


def filter_by_threshold(df: pd.DataFrame, col: str, op: str, value) -> pd.DataFrame:
    """Threshold criteria filtering: op in {'>=', '<=', '>', '<', '=='}."""
    if col not in df.columns:
        raise KeyError(f'column {col!r} not in frame')
    ops = {'>=': df[col] >= value, '<=': df[col] <= value, '>': df[col] > value,
           '<': df[col] < value, '==': df[col] == value}
    return df[ops[op].fillna(False)].copy()

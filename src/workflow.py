"""
Workflow engine — evaluates a saved multi-stage screening funnel over a
screener_results.csv frame.

A workflow is a declarative dict (config.WORKFLOWS built-ins, or a
my_workflows/*.json copy). Its shape is documented in config.py::WORKFLOWS
and docs/workflows_tab.md. Each stage narrows its `source` (the full
universe, or an earlier stage by name) using the SAME two mask builders the
All-Results panel uses — dashboard_filters.build_mask + build_advanced_mask
— so no screening logic is forked here. The Focus List is the deduped union
of every stage flagged `focus_input` (or the last stage if none is).

Pure functions, no Streamlit import: validate.py runs run_workflow in-process
against the latest daily batch.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import dashboard_filters as dfil  # noqa: E402


@dataclass
class StageResult:
    name: str
    source: str
    n_in: int
    n_out: int
    frame: pd.DataFrame
    note: str = ''
    focus_input: bool = False


@dataclass
class WorkflowResult:
    stages: list[StageResult]
    focus: pd.DataFrame
    checklist: list[str] = field(default_factory=list)

    @property
    def by_name(self) -> dict[str, StageResult]:
        return {s.name: s for s in self.stages}


def _stage_mask(frame: pd.DataFrame, stage: dict,
                idx_map: dict | None) -> pd.Series:
    # `match` ('all' | 'any') combines the selection-grid clauses; any
    # `advanced` block is always AND'd on top of the result.
    m = dfil.build_mask(frame, dfil.normalize_selections(
        stage.get('selections', {})), match=stage.get('match', 'all'))
    m &= dfil.build_advanced_mask(frame, stage.get('advanced', {}), idx_map)
    return m


def run_workflow(full: pd.DataFrame, wf: dict,
                 idx_map: dict | None = None) -> WorkflowResult:
    """Evaluate `wf` against `full` (a screener_results.csv frame indexed by
    ticker). `idx_map` = on_demand.universe_index_map(), needed only if a
    stage filters on index membership (adv_index)."""
    outputs: dict[str, pd.DataFrame] = {}
    stages: list[StageResult] = []
    for st in wf.get('stages', []):
        src_name = st.get('source') or 'universe'
        if src_name == 'universe':
            src = full
        elif src_name in outputs:
            src = outputs[src_name]
        else:
            raise ValueError(
                f"stage {st.get('name')!r}: source {src_name!r} is not "
                f"'universe' or an earlier stage")
        out = src[_stage_mask(src, st, idx_map)]
        outputs[st['name']] = out
        stages.append(StageResult(
            name=st['name'], source=src_name, n_in=len(src), n_out=len(out),
            frame=out, note=st.get('note', ''),
            focus_input=bool(st.get('focus_input'))))

    fi = [s.name for s in stages if s.focus_input]
    if not fi and stages:
        fi = [stages[-1].name]
    if fi:
        focus = pd.concat([outputs[n] for n in fi])
        focus = focus[~focus.index.duplicated(keep='first')]
    else:
        focus = full.iloc[:0]
    return WorkflowResult(stages=stages, focus=focus,
                          checklist=list(wf.get('checklist', [])))


def validate_workflow(wf: dict) -> list[str]:
    """Return a list of human-readable problems ([] == valid). Used by the
    editor before Save and by validate.py's builtin-workflow check."""
    errs: list[str] = []
    stages = wf.get('stages')
    if not isinstance(stages, list) or not stages:
        return ['workflow has no stages']
    seen: set[str] = set()
    for i, st in enumerate(stages):
        nm = st.get('name')
        if not nm:
            errs.append(f'stage {i}: missing name')
            continue
        if nm in seen:
            errs.append(f'stage {i}: duplicate name {nm!r}')
        src = st.get('source') or 'universe'
        if src != 'universe' and src not in seen:
            errs.append(
                f'stage {nm!r}: source {src!r} is not an earlier stage')
        seen.add(nm)
        if st.get('match', 'all') not in ('all', 'any'):
            errs.append(f'stage {nm!r}: match must be "all" or "any"')
        for k in st.get('selections', {}):
            if k not in dfil.SPEC_BY_KEY:
                errs.append(f'stage {nm!r}: unknown filter key {k!r}')
        for k in st.get('advanced', {}):
            if k not in dfil.ADVANCED_DEFAULTS:
                errs.append(f'stage {nm!r}: dead advanced key {k!r}')
    return errs


def stage_summary(stage: dict) -> str:
    """One-line human summary of a stage's filters (stage-card subtitle)."""
    parts: list[str] = []
    sels = (stage.get('selections') or {})
    joiner = '  OR  ' if stage.get('match') == 'any' and len(sels) > 1 else ' · '
    sel_parts: list[str] = []
    for fkey, val in sels.items():
        lbl = dfil.SPEC_BY_KEY.get(fkey, (fkey,))[0]
        if isinstance(val, (list, tuple)) and val and val[0] == 'custom':
            sel_parts.append(f'{lbl} {val[1]:g}-{val[2]:g}')
        else:
            sel_parts.append(f'{lbl} {val}')
    if sel_parts:
        s = joiner.join(sel_parts)
        parts.append(f'({s})' if joiner.strip() == 'OR' else s)
    adv = stage.get('advanced') or {}
    if adv.get('adv_leaders'):
        mode = adv.get('adv_leaders_mode', 'Any (union)').split(' ')[0]
        parts.append(f"leaders {'/'.join(adv['adv_leaders'])} ({mode})")
    if adv.get('adv_stages'):
        parts.append(f"stage {','.join(adv['adv_stages'])}")
    if adv.get('adv_rti_zone'):
        parts.append(f"RTI zone {','.join(adv['adv_rti_zone'])}")
    if adv.get('adv_max_ext', 10.0) < 10.0:
        parts.append(f"ext <= {adv['adv_max_ext']:g} ATR")
    if adv.get('adv_max_ext21', 10.0) < 10.0:
        parts.append(f"ext21 <= {adv['adv_max_ext21']:g} ATR")
    if adv.get('adv_max_ext50', 10.0) < 10.0:
        parts.append(f"ext50 <= {adv['adv_max_ext50']:g} ATR")
    if adv.get('adv_min_rs', 0.0) > 0:
        parts.append(f"RS >= {adv['adv_min_rs']:g}")
    if adv.get('adv_gmma_state'):
        parts.append(f"GMMA {','.join(adv['adv_gmma_state'])}")
    for fk in dfil.ADVANCED_FLAG_KEYS + ('adv_rti_dots', 'adv_rti_exp'):
        if adv.get(fk):
            parts.append(fk[4:].replace('_', ' '))
    if adv.get('sel_sector'):
        parts.append(f"sector {','.join(adv['sel_sector'])}")
    if adv.get('sel_industry'):
        parts.append('industry filter')
    return ' · '.join(parts) or '(no filters — passes everything)'

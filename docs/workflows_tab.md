# The Workflows tab

> **Status: implemented.** `dashboard.py::tab_workflows` + `src/workflow.py` +
> `config.WORKFLOWS` + the `workflow_store` / `build_advanced_mask` helpers in
> `dashboard_filters.py`. Covered by `validate.py` (engine + refactor) and
> `test_dashboard_app.py` (tab boot / run / save round-trip). Two built-ins ship:
> `Trading Voyage (Ollie)` and `Trading Voyage - Daily studies (Ollie)`.
>
> Deviations from the plan below, all deliberate:
> - **Per-stage `match`** — `build_mask` gained a `match='all'|'any'` param so one
>   stage can OR its filters (Ollie's 1M/3M/6M momentum scans are a *union*, not
>   an intersection). Editor: a radio above the grid. Default `'all'` keeps every
>   existing caller and the All-Results panel byte-identical.
> - **§9 editor** — no `filter_panel()` extraction was needed. The stage editor
>   is a self-contained `st.form` with its own `wfe{nonce}_*` widget keys
>   (fresh each time it opens, so `value=`/`index=` seed cleanly). It duplicates
>   the *rendering* of the grid, never the *masking* — `build_mask` /
>   `build_advanced_mask` stay the single source of truth.
> - Toolbar Edit/New/Delete/Save/Discard are `on_click` callbacks (writing
>   `wf_selected` after the widgets instantiate is not allowed). There is no
>   Run/Build view switch any more: a `wf_draft` in session state *is* edit
>   mode — Edit/New open it, Save/Discard close it.
> - `selection_to_range()` now accepts a `list` as well as a `tuple` for a
>   `('custom', lo, hi)` value — `config.WORKFLOWS` built-ins reach it via a
>   JSON round trip, which turns tuples into lists.
> - `validate.py`'s `sctr` reference script had a stale `python/screeners` path
>   (the module was renamed to `dashboard-screener`); fixed in passing.

A dashboard tab that runs **multi-stage screening funnels** end-to-end and
hands you a Focus List, plus an in-tab builder to construct and manage those
funnels. First shipped workflow: **Trading Voyage (Ollie)** — Oliver Wiedmaier's
Voyage Trading Group method.

- Source method: `sandBox/Oliver_wiedmeier/ollie_screening_workflow.md`
  (reconstructed from the book *A Momentum Trader's Guide to Mastering Quality
  Setups*, the "My toolbelt" post, VTG Substack articles, the TradingView
  indicator pages, and the `Ollie_AllCaps` screener snapshots).
- New code: `src/workflow.py`, `config.WORKFLOWS`, `dashboard.py::tab_workflows`,
  `workflow_store` helpers in `dashboard_filters.py`.
- Prerequisite refactor: extract `build_advanced_mask()` from `dashboard.py`.
- Tests: `validate.py` (engine behavioral checks), `test_dashboard_app.py` (tab AppTest).
- Not backtesting (intro.md). Not scoring (that's the Confluence tab).

---

## 1. What a workflow is (and is not)

| | **Preset** (`Ioa's Presets`) | **Workflow** (this tab) |
|---|---|---|
| Shape | one filter-panel snapshot | ordered list of stages, each narrowing an earlier one |
| Output | filtered All-Results table | a **Focus List** + a manual checklist |
| Mental model | "show me stage-2 not-extended leaders" | "walk me down Ollie's weekend→focus path" |
| Overlaps with | — | Confluence tab is *scoring* (how many methods agree); a workflow is *one method's sequential path*. Different jobs — the tab caption says so. |

A workflow **never re-runs the screeners**. It filters the latest
`results/YYYY-MM-DD/screener_results.csv` in memory, so it is instant. To refresh
the underlying data you still press **Re-run screeners** on the All Results tab.

### Non-goals (v1)

- No scheduling / cron / alerts (that's `/loop` and out of scope).
- No branching logic beyond "this stage's input is *that* named stage or the full universe".
- No intraday / pre-market data. Conditions that need it (gap %, catalyst, short
  interest, HVC) are **checklist items**, not computed stages.
- Checklist state is session-only in v1 (not persisted per run).

---

## 2. Data model

A **workflow** is a dict; built-ins live in `config.WORKFLOWS`, user copies are
JSON in `my_workflows/` (mirrors `my_screeners/`).

```python
{
  'name': 'Trading Voyage (Ollie)',
  'description': "Voyage Trading Group weekend→focus funnel …",
  'stages': [
    {
      'name': 'Universe',
      'source': 'universe',          # 'universe' | <name of an earlier stage>
      'match': 'all',                # 'all' (AND, default) | 'any' (OR the clauses)
      'selections': {                # same vocabulary as dashboard_filters.PRESETS
        'adr': ('custom', 3.0, 60.0),
        'adv': '> $1M',
        'vs50': '> 0%',
      },
      'advanced': {'adv_stages': ['2A', '2B']},
      'note': "Ollie 'Universe' scan: $3+, ADR 3%+, avg vol, price>50>200 SMA",
      'focus_input': False,          # does this stage feed the Focus List?
    },
    # … more stages …
  ],
  'checklist': [
    "Pre-market gap ≥ 5% on a real catalyst (earnings / analyst upgrade / M&A)",
    "≥ 200% average volume by the close (HVC)",
    # …
  ],
}
```

A **stage** reuses exactly the two mask builders the All-Results tab uses:

- `selections` → `dashboard_filters.build_mask(df, selections, match)` (the grid);
  `match='all'` ANDs the clauses (default, the only mode All-Results uses),
  `match='any'` ORs them — a stage sets `'any'` to express a union like Ollie's
  1M/3M/6M momentum scans.
- `advanced`  → `dashboard_filters.build_advanced_mask(df, advanced, idx_map)`
  (**new** — see §4). Always AND'd on top of the (AND-or-OR'd) `selections`.

`source` makes it a small DAG, not a strict chain: most stages narrow the
previous one, but Ollie's "daily studies" and "gap scan" start again from the
full universe. The **Focus List** = union (deduped) of every stage with
`focus_input: True`; if none is flagged, it's the last stage's output.

---

## 3. Engine — `src/workflow.py`

Pure function, no Streamlit import (so `validate.py` can call it in a subprocess
like the other ports).

```python
from dataclasses import dataclass
import pandas as pd
from dashboard_filters import build_mask, build_advanced_mask

@dataclass
class StageResult:
    name: str
    source: str
    n_in: int
    n_out: int
    tickers: pd.Index

@dataclass
class WorkflowResult:
    stages: list[StageResult]
    outputs: dict[str, pd.DataFrame]     # stage name -> filtered rows
    focus: pd.DataFrame                  # deduped union of focus_input stages
    checklist: list[str]

def run_workflow(full: pd.DataFrame, wf: dict, idx_map=None) -> WorkflowResult:
    outputs, stages = {}, []
    for st in wf['stages']:
        src = full if st.get('source', 'universe') == 'universe' \
              else outputs[st['source']]
        m  = build_mask(src, st.get('selections', {}))
        m &= build_advanced_mask(src, st.get('advanced', {}), idx_map)
        out = src[m]
        outputs[st['name']] = out
        stages.append(StageResult(st['name'], st.get('source', 'universe'),
                                  len(src), len(out), out.index))
    fi = [s['name'] for s in wf['stages'] if s.get('focus_input')]
    if not fi:
        fi = [wf['stages'][-1]['name']] if wf['stages'] else []
    focus = (pd.concat([outputs[n] for n in fi]).pipe(
                 lambda d: d[~d.index.duplicated()])
             if fi else full.iloc[:0])
    return WorkflowResult(stages, outputs, focus, wf.get('checklist', []))
```

Validation is order-independent for `source`-linked stages: a stage that names
`'Universe'` as its source yields the same rows whether it runs 2nd or 5th.

---

## 4. Prerequisite refactor — `build_advanced_mask()`

Today the "advanced" mask (leaders lists, stage, `max_ext`, RTI zone, the
`in_*` flags, GMMA, exchange, index membership …) is **inline in `dashboard.py`**
(~lines 428–475). The workflow engine must not duplicate it.

**Move that block verbatim into `dashboard_filters.py`:**

```python
def build_advanced_mask(df, advanced: dict, idx_map=None) -> pd.Series:
    """`advanced` uses the adv_-prefixed keys from ADVANCED_DEFAULTS.
    Missing keys fall back to ADVANCED_DEFAULTS (= no-op)."""
    a = {**ADVANCED_DEFAULTS, **(advanced or {})}
    mask = pd.Series(True, index=df.index)
    # … the exact logic currently in dashboard.py …
    return mask
```

`dashboard.py` then calls `dfil.build_advanced_mask(full, {k: st.session_state[k]
for k in dfil.ADVANCED_DEFAULTS}, IDX_MAP)` instead of the inline block.

**Safety net:** `validate.py` already checks "ALL 8 presets vs manual filters"
and `test_dashboard_app.py` checks preset row-counts — both exercise the advanced
mask, so a behavioral regression in the extraction is caught. Add one explicit
check: `build_advanced_mask(df, {}) == all-True`.

---

## 5. New metric columns (`src/indicators.py` + `run_screeners.py`)

Ollie's momentum scans are "% above the N-day **low**", not point-to-point gain.
Add three columns to `screener_results.csv`:

| Column | Formula | Provenance |
|---|---|---|
| `pct_above_21d_low`  | `close / rolling_min(low, 21)  - 1` (×100) | snapshot "Price above Low 1M by 30%+" |
| `pct_above_63d_low`  | `close / rolling_min(low, 63)  - 1` (×100) | "Price above Low 3M by 50%+" |
| `pct_above_126d_low` | `close / rolling_min(low, 126) - 1` (×100) | "Price above Low 6M by 100%+" |

Add a `pct_above_low` threshold family to `dashboard_filters.THRESHOLD_FAMILIES`
(`> 20% / > 30% / > 50% / > 100%`) and three `FILTER_SPECS` rows so they're
selectable in a stage (and in the normal panel). Append to `view_cols`.

`gain_1m/3m/6m` already exist — the workflow can use either; the shipped Ollie
config uses `pct_above_*_low` to match his snapshots exactly.

> Everything else Ollie needs is already a column: `adr20_pct`, `adv50_dollar`,
> `avg_volume50`, `pct_vs_50sma`, `pct_vs_200sma`, `stage`, `ext_21ema_atr`,
> `ext_40sma_atr` (his 50-SMA ≈ our 40-SMA — noted in the stage `note`),
> `rti_zone`, `rti_dots`, `rti_low_vol_streak`, `glp_*`, `gmma_compression_*`,
> `in_daily_gainers`, `in_weekly_movers`, `rel_volume_today`.

---

## 6. Persistence — `workflow_store` (in `dashboard_filters.py`)

Same pattern as `save_screener` / `saved_screeners` / `load_screener` /
`delete_screener`:

```python
MY_WORKFLOWS = ROOT / 'my_workflows'

def builtin_workflows()  -> dict         # config.WORKFLOWS
def saved_workflows()    -> list[str]    # *.json stems in my_workflows/
def load_workflow(name)  -> dict | None  # built-in first, then my_workflows/
def save_workflow(name, wf) -> Path      # writes my_workflows/<safe>.json
def delete_workflow(name)-> bool         # my_workflows/ only; built-ins are read-only
```

The dropdown shows `built-ins` then `── my workflows ──` then saved ones.
Editing a built-in is blocked; **Duplicate** copies it into `my_workflows/` and
unlocks it.

---

## 7. The tab — layout

```
╭─ 🧭 Workflows ─────────────────────────────────────────────────────────────╮
│                                                                            │
│ Workflow: [ Trading Voyage (Ollie) ▾ ]   [▶ Run]  [＋ New]  [⧉ Duplicate]  │
│                                                    [✎ Edit]  [🗑 Delete]    │
│ data as of results/2026-09-07 · read-only (Re-run screeners on All Results) │
│                                                                            │
│ ⓘ A workflow is a sequential funnel — each stage filters an earlier one.    │
│   Presets are one snapshot; a workflow is the whole path. For "how many     │
│   methods agree", use the Confluence tab instead.                           │
│ ─────────────────────────────────────────────────────────────────────────  │
│                                                                            │
│  ┌ Stage 1 · Universe ───────────────────────────  3 961 → 486 ──────────┐  │
│  │ from: full universe                                                    │  │
│  │ ADR% ≥ 3 · 50d ADV > $1M · price vs 50sma > 0% · Weinstein 2A/2B       │  │
│  │ 📝 Ollie 'Universe' scan: $3+, ADR 3%+, avg vol, price>50>200 SMA      │  │
│  │                                                  [▸ table]  [✎ edit]   │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                                   │                                        │
│                                   ▼                                        │
│  ┌ Stage 2 · Momentum leaders ───────────────────────  486 → 74 ─────────┐  │
│  │ from: Stage 1 (Universe)                                               │  │
│  │ % above 21d low > 30%  OR  63d low > 50%  OR  126d low > 100%          │  │
│  │                                                  [▸ table]  [✎ edit]   │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                                   │                                        │
│                                   ▼                                        │
│  ┌ Stage 3 · Tight & orderly ────────────────────────  74 → 11 ──────────┐  │
│  │ from: Stage 2 · RTI zone 1–2 · low-vol dots · Golden Launch Pad       │  │
│  │                                                  [▸ table]  [✎ edit]   │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                                   │                                        │
│                                   ▼                                        │
│  ┌ Stage 4 · Focus – not extended ★ ─────────────────  11 → 7 ───────────┐  │
│  │ from: Stage 3 · ext ≤ 3 ATR (21 EMA) · ext ≤ 5 ATR (40 SMA)           │  │
│  │ 📝 Jack-in-the-Box: skip if range<yday & if too far from MAs          │  │
│  │                                          ★ contributes to Focus List  │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                                                                            │
│ ═════════════════════════════════════════════════════════════════════════  │
│ 📋 FOCUS LIST · 7 names   [💾 Save as list…] [⭳ CSV] [⭳ TW .txt] [→ All Res] │
│ ┌────────┬───────┬──────┬───────┬──────┬──────────┬───────────────────────┐ │
│ │ ticker │ spark │ ADR% │ RTI z │ ext  │ %>63d lo │ 1m / 3m / 6m gain     │ │
│ ├────────┼───────┼──────┼───────┼──────┼──────────┼───────────────────────┤ │
│ │ ABCD   │ ▁▂▃▅▇ │  5.1 │   1   │ 1.8  │   71 %   │  32 % / 71 % / 148 %  │ │
│ │ …      │       │      │       │      │          │                       │ │
│ └────────┴───────┴──────┴───────┴──────┴──────────┴───────────────────────┘ │
│                                                                            │
│ ═════════════════════════════════════════════════════════════════════════  │
│ ✅ Manual checklist — not computed; confirm before entry                    │
│  ☐ Pre-market gap ≥ 5% on a real catalyst (earnings / analyst / M&A)        │
│  ☐ ≥ 200% average volume by the close (HVC); bonus HV1 / HVE               │
│  ☐ Close within the top 30% of the day's range                             │
│  ☐ Short interest ≥ 10%   (Type-2, near 52w-low gap-ups)                    │
│  ☐ Sector leadership — name is in a leading group                          │
│  ☐ Situational awareness: index > 21 EMA, breadth STRONG/MIXED, %>200SMA>50 │
╰────────────────────────────────────────────────────────────────────────────╯
```

- Each stage card: name, `from:` source, a one-line human summary of its
  selections, the optional `note`, live `n_in → n_out`, `[▸ table]` (expander
  with the same results columns as All-Results, sparkline included), `[✎ edit]`
  (only when the workflow is editable).
- If a stage returns 0 rows, its card turns amber with "0 out — loosen this
  stage or an earlier one".
- **Focus-list actions reuse existing plumbing:** `dfil.save_list()`, the CSV
  download, and `→ All Results` writes the tickers into
  `st.session_state` as an applied list and switches tab.
- **`⭳ TradingView .txt`** — `dfil.tradingview_watchlist(frame, section=…)`
  emits the format TradingView's *Upload list…* accepts: `EXCHANGE:SYMBOL`
  tokens, comma-separated, with a leading `###<name>` section divider. The
  exchange prefix comes from the `exchange` column of `screener_results.csv`
  (`NYSE Arca` → `AMEX`, unknown → bare symbol, which TradingView resolves for
  unambiguous US equities). Same button on every stage's *show table* expander
  (alongside a per-stage `⭳ CSV`), and on every other results table in the
  dashboard (All Results, Focus List, Leaders, Confluence, Timing, Patterns) via
  the shared `dashboard._tv_txt()` wrapper. TradingView caps an imported list at
  1000 symbols — split larger exports by hand.
  Ref: <https://www.tradingview.com/support/solutions/43000487233>.

---

## 8. Build / manage mode — how you construct "Trading Voyage (Ollie)" in-tab

The shipped workflow is **read-only**. To make it yours:

1. **Select** `Trading Voyage (Ollie)` → **⧉ Duplicate** → name it
   `Trading Voyage (mine)`. It's copied to `my_workflows/` and the toolbar now
   shows **✎ Edit**, **🗑 Delete**, **💾 Save**.
2. **✎ Edit** turns every stage card into an editor and reveals
   `[＋ Add stage]` between cards.

### The stage editor (one stage at a time, in an `st.form`)

```
╭─ ✎ Stage 3 · "Tight & orderly" ───────────────────────────────────────────╮
│ Stage name  [ Tight & orderly                                     ]        │
│ Input from  [ Stage 2 · Momentum leaders ▾ ]   (or "full universe")        │
│ Note        [ Ollie: 2 days tight, EMA 4/9/21 compression, RTI low     ]   │
│ [ ] ★ this stage contributes to the Focus List                             │
│ ───────────────────────────────────────────────────────────────────────    │
│  ‹ the standard 4-row filter grid + the Advanced expander,                 │
│    pre-loaded with this stage's current selections ›                       │
│    Market Cap [All ▾]  Price [All ▾]  vs10 [All ▾] …                        │
│    ▸ Advanced (leaders, stage, RTI zone, max-ext, in_* flags, GMMA …)      │
│ ───────────────────────────────────────────────────────────────────────    │
│  live preview:   74 in → 11 out                                            │
│  [↑ move up]  [↓ move down]  [⧉ duplicate stage]  [🗑 delete stage]         │
│                                              [ Cancel ]   [ Apply stage ]  │
╰───────────────────────────────────────────────────────────────────────────╯
```

The grid is **the same component** as the All-Results panel — see §9 for the
one refactor that makes it reusable. `Apply stage` writes the captured
`selections`/`advanced` back into the in-memory workflow dict
(`st.session_state['wf_draft']`).

### Editing the checklist

A plain `st.text_area`, one item per line → `wf['checklist']`.

### Saving

Toolbar **💾 Save** (overwrite) and **Save as…** `[____]` →
`dfil.save_workflow(name, st.session_state['wf_draft'])` →
`my_workflows/<name>.json`. It now appears under `── my workflows ──` in the
dropdown, alongside the built-ins.

### Managing

- **＋ New** → empty workflow with one blank stage (source = universe).
- **🗑 Delete** → `my_workflows/` files only; built-ins can't be deleted.
- Reordering is per-stage (`↑ / ↓`); `source` references are by **name**, so a
  rename offers "update references?" (or just re-point the child's dropdown).

---

## 9. The reusable filter-panel component (the fiddly bit)

Today `dashboard.py::tab_all` renders the grid straight into fixed session-state
keys (`sel_mktcap`, `sel_vs21`, …, `adv_*`). The stage editor needs the same
grid **scoped to a stage** without colliding with the All-Results panel.

**Approach:** extract a function

```python
def filter_panel(container, *, key_prefix: str, seed: dict) -> tuple[dict, dict]:
    """Render the 4-row grid + Advanced expander into `container`, widgets
    keyed `f'{key_prefix}{name}'`, initialised from `seed` once.
    Returns (selections, advanced) captured this run."""
```

- `tab_all` calls it with `key_prefix='f_'` and seed = current preset/screener.
- the stage editor calls it with `key_prefix=f'wf_s{idx}_'` and seed = the stage.
- `_apply_preset`, `_reset_filters`, `_current_panel` become thin wrappers over
  the same helper.

This is ~2–3 h and touches `tab_all`, so do it behind the existing
`test_dashboard_app.py` preset-count checks (they'll catch a wiring mistake).
If the refactor looks risky, a **cheaper v1**: the stage editor writes to the
*global* filter keys and the All-Results panel is simply not rendered while the
Workflow editor is open (a modal-ish `st.session_state['editing_stage']` guard).
Ship that first, do the clean extraction in a follow-up.

---

## 10. `config.WORKFLOWS['Trading Voyage (Ollie)']` — shipped definition

```python
WORKFLOWS = {
  'Trading Voyage (Ollie)': {
    'description':
        "Oliver Wiedmaier / Voyage Trading Group weekend→focus funnel. "
        "Universe trend filter → 1M/3M/6M momentum leaders → tight & orderly "
        "consolidation → not-extended Focus List. Gap / 10% / 20% 'studies' "
        "and all catalyst/pre-market checks are the manual checklist. "
        "Ref: sandBox/Oliver_wiedmeier/ollie_screening_workflow.md",
    'stages': [
      {'name': 'Universe', 'source': 'universe',
       'selections': {'adr': ('custom', 3.0, 60.0), 'adv': '> $1M',
                      'vs50': '> 0%', 'vs200': '> 0%'},
       'advanced': {'adv_stages': ['2A', '2B']},
       'note': "Ollie 'Universe' scan: price>$3, ADR%≥3, avg vol≥500k, "
               "close>50SMA>200SMA. (adv vol proxied by 50d ADV>$1M; "
               "stage 2A/2B ≈ the MA stack.)"},

      {'name': 'Momentum leaders', 'source': 'Universe', 'match': 'any',
       'selections': {'above21low': '> 30%', 'above63low': '> 50%',
                      'above126low': '> 100%'},
       'note': "Ollie's 1M/3M/6M scans are a UNION — ≥30% above the 21d low OR "
               "≥50% above the 63d low OR ≥100% above the 126d low. Min 20% "
               "momentum leg before the base."},

      {'name': 'Tight & orderly', 'source': 'Momentum leaders',
       'selections': {},
       'advanced': {'adv_rti_zone': ['1', '2'], 'adv_gold_launch_pad': True},
       'note': "RTI zone 1-2 (range tightening) + Golden Launch Pad (EMA "
               "10/20/50 cluster) ≈ Ollie's 2-days-tight + 4/9/21 EMA squeeze."},

      {'name': 'Focus - not extended', 'source': 'Tight & orderly',
       'selections': {}, 'advanced': {'adv_max_ext': 3.0},
       'focus_input': True,
       'note': "Jack-in-the-Box ATR gate: ext ≤ 3 ATR vs 21 EMA and ≤ 5 ATR "
               "vs 50 SMA (our max_ext caps BOTH at 3.0 -> conservative). "
               "Also skip names whose range today < range yesterday (manual)."},
    ],
    'checklist': [
      "Pre-market gap ≥ 5% on a real catalyst (EPS surprise ≥100%, revenue "
        "≥30% QoQ, ≥3 analyst upgrades, M&A, product launch)",
      "Pre-market volume ≥ 10% of average daily volume",
      "≥ 200% average volume by the close (HVC); bonus: HV1 / HVE",
      "Close within the top 30% of the day's range",
      "Short interest ≥ 10% (Type-2, near 52-week-low gap-ups)",
      "Sector leadership — leading group (check Sector breakdown)",
      "Situational awareness: SPY/QQQ/IWM > 21 EMA; breadth STRONG/MIXED; "
        "%>200SMA > 50; net highs > lows",
      "Entry trigger day: range expansion > prior candle, vol > avg at close, "
        "close within 30% of high, 4-EMA ticking up",
      "Stop = LOD (≤ 1 ATR) or ½ the day's range; risk 0.25-0.5%; "
        "total open risk ≤ 2% (VTG Risk Model 1)",
    ],
  },
}
```

> The `note` on every stage records exactly where our column deviates from
> Ollie's literal spec (40-SMA vs his 50, `max_ext` capping both MAs, RTI+GLP
> standing in for his EMA-compression eyeball). Same provenance discipline as
> the `IMPLEMENTATION_PLAN.md` §0 bibliography.

A second built-in, **`Trading Voyage — Daily studies (Ollie)`**, ships the other
entry point (three stages, all `source: 'universe'`: `in_daily_gainers` +
`rel_volume_today ≥ 2`; `pct_above_21d_low > 20`; gap proxy `gain_5d` + HV) so
the "I'm rushed" path covers fresh movers too.

---

## 11. Tests

**`validate.py`** — add a `check_workflow()` (runs in-process, engine has no
Streamlit dep):

1. `run_workflow(full, {'stages': []})` → focus is empty; no crash.
2. Single-stage workflow with `selections={'adr': '> 5%'}` → focus count ==
   `(full['adr20_pct'] > 5).sum()` (engine == direct mask).
3. Two-stage chain `A(universe, adr>3) → B(A, vs200>0)` → count ==
   `build_mask(full, {adr>3, vs200>0})` count (chaining == combined mask).
4. `source` order-independence: move a `source:'universe'` stage to the end →
   identical output rows.
5. The shipped `Trading Voyage (Ollie)` runs, every stage `n_out ≤ n_in`,
   focus ⊆ last stage.
6. `build_advanced_mask(full, {})` is all-True (refactor guard).

**`test_dashboard_app.py`** — AppTest:

7. Workflows tab renders; selecting `Trading Voyage (Ollie)` and clicking Run
   shows 4 stage cards and a non-empty (or explicitly-empty) Focus List.
8. Duplicate → Edit → change Stage 4 `max_ext` to 5.0 → Save → reload → the
   `my_workflows/*.json` round-trips.
9. Deleting a `my_workflows` entry works; the built-in is undeletable.

---

## 12. Work breakdown

| # | Task | Files | Est. |
|---|------|-------|------|
| 1 | Extract `build_advanced_mask()` | `dashboard_filters.py`, `dashboard.py` | 0.5–1 h |
| 2 | `pct_above_{21,63,126}d_low` columns + family + specs + view_cols | `src/indicators.py`, `run_screeners.py`, `dashboard_filters.py` | 0.5–1 h |
| 3 | `src/workflow.py` engine + dataclasses | new | 1–2 h |
| 4 | `config.WORKFLOWS` + the two Ollie workflows w/ provenance | `config.py` | 1 h |
| 5 | `workflow_store` helpers + `my_workflows/` | `dashboard_filters.py` | 0.5 h |
| 6 | `tab_workflows` stepper view (cards, expanders, focus actions) | `dashboard.py` | 1–2 h |
| 7 | Reusable `filter_panel()` + stage editor (or the cheap v1 guard) | `dashboard.py` | 2–3 h |
| 8 | `validate.py` + `test_dashboard_app.py` checks | tests | 1 h |
| 9 | `docs/workflows_tab.md` finalise + `README.md` / `IMPLEMENTATION_PLAN.md` §N | docs | 0.5 h |

**~1.5–2 days.** Task 7 is the only real risk; §9 has the fallback.

## 13. Rollout order

1. Tasks 1–2 (refactor + columns) — independently useful, shippable alone.
2. Tasks 3–6 with the **cheap v1** editor guard — the tab works, built-ins
   runnable, Focus List + checklist live. Duplicate/Save works; editing uses the
   global panel behind a guard.
3. Task 7 clean `filter_panel()` extraction — inline stage editors, no guard.
4. Second built-in workflow + any new stage-level metrics users ask for.

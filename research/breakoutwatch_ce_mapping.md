# breakoutwatch CE (CANTATA Evaluator) → project columns

**IMPLEMENTED 2026-08-29** as `src/leaders/cantata.py` (IMPLEMENTATION_PLAN
§17) — the full CE (0-18), not the partial. This doc was the blueprint; the
tables below record the item→column mapping and the deviations that were
actually made. "Option 1 / Option 2" at the bottom are superseded.

Blueprint for a **stock-level "CANTATA / CE" preset** — independent of any
pattern. Source: `cup_handle_ideas/cupAndHandle/lit/CE Overview.html`
(digest: `lit/breakoutwatch_methodology.md`).

**CE = CET (technical, max 7) + CEF (fundamental, max 11) = max 18.**
It scores *any* stock on trend + earnings, whether or not it is in a cup &
handle. NOT the same as CQ (Chart Quality = RCQ + HQ), which is
pattern-window-anchored and lives in `src/patterns/cup_handle.py`.

Design note: this project deliberately keeps filters as independent columns
(intro.md) rather than one master score. A CE composite is therefore
**opt-in** — a computed score column + a preset that thresholds it — not a
replacement for the individual filters.

---

## CET — Technical (max 7)

| # | breakoutwatch item | "best value" | project coverage | status |
|---|---|---|---|---|
| 1 | Price vs 50dMA / 200dMA / 50-v-200 (**3 pts**) | Price ≥ 50dMA ≥ 200dMA & Price ≥ 200dMA | `pct_vs_sma50`, `pct_vs_sma200`, `slope200_pct`; fully encoded by `stage` (2A/2B ⇒ aligned) and `minervini_count` (crit 1–5) | **HAVE** |
| 2 | RS Rank (1–99) | 99 | `rs_pct` (IBD-blend cross-sectional percentile 0–100, `lkm_rs` weights 63/126/189/252 @ .4/.2/.2/.2) | **HAVE** |
| 3 | Rank in industry | first | only the `industry` label — no within-industry rank | **MISSING** |
| 4 | Price vs 52-week high | within 15% | `pct_from_52w_high` | **HAVE** |
| 5 | Up/Down volume ratio | ≥ 2.0 | not computed. Proxies: `mfi14` (money-flow, volume-weighted directional), `adl_composite_score` (accumulation line). Neither is the literal 50-day Σ(up-vol)/Σ(down-vol). | **MISSING** |

CET covered: **~5 / 7 pts** (items 1,2,4). Gaps: industry rank, U/D ratio.

## CEF — Fundamental (max 11, 1 pt each)

| # | breakoutwatch item | project coverage | status |
|---|---|---|---|
| 1 | QoQ EPS growth — 2 Q each ≥ 18% | `C_pass` / `canslim.py` C (latest-Q **YoY** ≥ 25% — stricter, different framing) | **HAVE (YoY, not QoQ)** |
| 2 | Positive quarterly earnings — 2 Q > 0 | inside `C_pass` (base-EPS floor `CANSLIM_C_MIN_BASE_EPS`) | **PARTIAL** |
| 3 | QoQ earnings acceleration | `canslim.py` `C_accelerating` flag (approx: q1-YoY vs `earningsQuarterlyGrowth`) | **PARTIAL** |
| 4 | YoY EPS growth — 4 FY each ≥ 25% | `A_pass` / `canslim.py` A (3-yr EPS **CAGR** ≥ 25% — CAGR, not each-year) | **HAVE (CAGR)** |
| 5 | QoQ sales growth — 2 Q each ≥ 25% | — | **MISSING** (§16.11) |
| 6 | QoQ sales acceleration | — | **MISSING** (§16.11) |
| 7 | Forward earnings growth ≥ 15% & > current Q | — | **MISSING** (§16.11) |
| 8 | Institutional ownership ≥ 5 holders & net shares purchased ≥ 0 | `I_pass` (`heldPercentInstitutions` ≥ 20% — level) + `I_accumulation` (shares outstanding flat/shrinking) | **PARTIAL** (level + buyback proxy, not fund-count Δ) |
| 9 | Return on equity ≥ 17% | — | **MISSING** (§16.11) |
| 10 | Cash flow ≥ 120% of earnings, MRQ & TTM > 0 | — | **MISSING** |
| 11 | Net margin = 3-year max | — | **MISSING** (§16.11) |

CEF covered: **~3.5 / 11** (C, A, I at the CANSLIM level). Gaps: sales
growth (5,6), forward est (7), ROE (9), cash flow (10), margins (11) — five
of these are the `canslim.py` additions already listed in
IMPLEMENTATION_PLAN §16.11.

---

## Assembling a CE preset

### Option 1 — partial composite from columns that already exist (cheap, now)

Add to `run_screeners.py` after the leaders merge (writes into
`screener_results.csv`):

```python
# CET (partial, 0-5): MA alignment (3) + RS rank (1) + near 52w high (1)
ma_aligned = res['stage'].isin(['2A', '2B'])                 # ⇒ price≥50≥200 & 200 rising
cet = (ma_aligned.astype(int) * 3
       + (res['rs_pct'] >= 90).astype(int)
       + (res['pct_from_52w_high'] >= -15).astype(int))       # within 15%
# CEF (partial, 0-3): the CANSLIM C-A-I sub-passes
cef = res[['C_pass', 'A_pass', 'I_pass']].fillna(False).astype(int).sum(axis=1)
res['cet_partial'] = cet          # 0-5  (full CET is 7)
res['cef_partial'] = cef          # 0-3  (full CEF is 11)
res['ce_partial']  = cet + cef    # 0-8  (full CE is 18)
```

Then a preset in `dashboard_filters.py` `PRESETS`:

```python
'CANTATA (partial CE ≥ 6)': {
    'selections': {},
    'advanced': dict(ADVANCED_DEFAULTS, adv_ce_min=6),   # new advanced key
},
```

(needs a `ce_partial` threshold family + `adv_ce_min` in
`ADVANCED_DEFAULTS`, same pattern as `adv_min_count` for Minervini.)

### Option 2 — full CE (0–18): close the 4 real gaps first

1. **Industry rank** — `res.groupby('industry')['rs_pct'].rank(pct=True)`;
   score = 1 pt if top-third of its industry.
2. **Up/Down volume ratio** — from daily OHLCV: rolling-50-day
   `Σ(volume where close>prev_close) / Σ(volume where close<prev_close)`;
   1 pt if ≥ 2.0. New column in `indicators.py`.
3. **CEF fundamentals** — the §16.11 `canslim.py` additions: ROE ≥ 17%,
   sales growth ≥ 25% (2 Q) + acceleration, forward est ≥ 15%, net-margin
   = 3-FY max, cash-flow ≥ 120% earnings. All from
   `financial_data_0_8.csv` (check which fields are present) — emit as
   per-item 0/1 flags, sum into `cef_score` (0–11).
4. Then `ce_score = cet_score + cef_score` (0–18), matching breakoutwatch's
   scale, with per-item sub-scores kept as columns so each stays
   independently filterable (the project's convention).

### Not recommended
Replacing the standalone filters (Minervini, CANSLIM, SCOOTER, stage) with
a single CE gate — the dashboard's value is per-column filtering; CE is an
*additional* lens, not a substitute. Keep both.

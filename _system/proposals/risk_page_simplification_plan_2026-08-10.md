# Risk page simplification — the five-step algorithm applied

**Status:** PROPOSED — awaiting approval. Nothing implemented.
**Date:** 2026-08-10

Method: Musk's five-step algorithm, in order, no skipping.
1. Make the requirements less dumb (and attach a *name* to each requirement)
2. Delete the part or process (if you aren't adding ~10% back, you didn't delete enough)
3. Simplify or optimize — **only** what survived steps 1–2
4. Accelerate cycle time
5. Automate — last

The discipline that matters is the ordering: the classic error is optimizing
something that should not exist. Two of the largest things on this page are
mine, shipped hours ago. They get the same treatment.

---

## Step 1 — Make the requirements less dumb

**The one requirement nobody wrote down:** what decision does this page serve?

The repo's own doctrine answers it: research-only, no trading authority,
`human_decision.json` is the sole capital authority. So the page cannot be a
trade trigger. Its only honest job is:

> **Is the market regime one where I should change how I size, wait, or act —
> and can I trust the reading?**

That is the requirement. Every number gets one question: *can it change that
answer?* If not, it is decoration, however expensive it was to build.

### Requirements interrogated, with owners

| Requirement | Whose | Verdict |
|---|---|---|
| "Show mechanical deleveraging pressure" | criticality monitor design | **Dumb as stated.** No mechanical-flow feed exists. The rail renders single-stock breadth relabeled. Requirement assumed a Databento flow feed that CI never runs. |
| "Show exhaustion confirmation" | same | **Same defect**, same substitution. |
| "Sector pressure/exhaustion columns" | sector heatmap | **Dumb.** 11 sectors × 2 columns = 22 cells that have never held a value and cannot until sector flow exists. |
| "Alert journal" | ingest worker design | **Requirement without a producer.** Only `run_databento_flow_monitor.py` writes alerts; it is a local Windows task, not CI. Empty by construction. |
| "observed_vol_target_flows tile" | component builder | **Delete the requirement.** No free source exists; tier 3 says buy or retire. |
| "14-metric z-score heatmap" | **mine, today** | **Over-specified.** See the redundancy evidence below. |
| "14-row metric detail table" | **mine, today** | **Redundant with the heatmap it sits beside.** |
| "How the private ingest works" prose | risk view | Real, but it is documentation, not a metric. Wrong surface. |
| "Interpretation guardrails" prose | risk view | Keep — it is the research-only guardrail, legally and epistemically load-bearing. |

### The evidence that kills nine of my fourteen heatmap rows

Correlation of each metric's 1-year z-score against VIX's, over the 120
sessions actually displayed:

| Metric | corr vs VIX | Reading |
|---|---:|---|
| vix3m | **0.97** | the same signal repainted |
| vix9d | **0.95** | same |
| vix6m | **0.95** | same |
| slope_vix_3m | **0.94** | same (as a *z*; see note) |
| vvix | **0.92** | same |
| vix1d | 0.75 | mostly same |
| iv_rv_spread | 0.71 | partly independent |
| move | 0.62 | rates vol — independent-ish |
| skew | 0.28 | **genuinely independent** |
| spx_rv20 | **−0.15** | **fully orthogonal** |

Five rows are 0.92–0.97 correlated with a row that stays. Deleting them loses
almost no information and removes ~64% of the grid. `vvix_vix_ratio`,
`slope_9d_vix` and `slope_3m_6m` are arithmetic derivatives of rows already
present — they cannot add information by construction.

**Note on the term slope:** its *z-score* is redundant, but its *state*
(contango vs backwardation) is the single best stress flag on the page. Keep
the state as a headline; drop its heatmap row.

---

## Step 2 — Delete

### Delete outright

| # | Item | Why | Cells/elements removed |
|---|---|---|---|
| 1 | **Pressure rail** | breadth proxy wearing a flow label | 1 of 3 headline rails |
| 2 | **Exhaustion rail** | same | 1 of 3 headline rails |
| 3 | **Sector pressure/exhaustion columns** | never held a value | 22 cells |
| 4 | **9 redundant heatmap rows** | 0.92–0.97 corr, or arithmetic derivatives | 1,080 of 1,680 cells |
| 5 | **14-row metric detail table** | duplicates the strip beside it | ~84 cells |
| 6 | **`observed_vol_target_flows` tile** | no source will ever exist free | 1 tile |
| 7 | **`options_stress` tile** | went `unavailable` today; its z-scores already surface in the vol panel | 1 tile |
| 8 | **Flow polylines on the SPY history chart** | no flow data exists to draw | 2 of 3 series |
| 9 | **"How the private ingest works" prose** | move to `docs/`; it is not a metric | ~1 card |
| 10 | **Alert journal** | structurally empty — *unless* you want the local task running (decision below) | 1 card |

Net: **~1,190 of ~1,800 rendered data cells removed (≈66%)**, three permanently
dead tiles gone, two lying rails gone.

### Add back ~10% (the honesty tax)

Musk's rule: if nothing goes back, you cut the wrong things.

1. **A one-line regime verdict in plain English** at the top — e.g. *"Vol in the
   15th percentile, curve in contango, realized below implied: calm regime, no
   sizing change indicated."* Composed from the five survivors. This is the
   thing you actually want at a glance and the page has never had it.
2. **A single freshness/trust line**: worst feed lag + any interior gap, in one
   sentence. Today it would read *"MOVE 16 sessions behind; term complex had a
   15-session gap to 08-07."* Trust is part of the decision.
3. **MOVE stays** despite its lag — rates vol is the most orthogonal thing on
   the page after realized vol, and orthogonal beats convenient.

---

## Step 3 — Simplify what survived

**Headline (always visible) — five numbers, one verdict:**

| Metric | Why it survives |
|---|---|
| **VIX + 1y percentile** | the anchor; percentile beats level for regime |
| **Term state** (contango / flat / backwardation) | best single stress flag; state, not z |
| **IV − RV spread** | is realized catching implied — the one that front-runs regime change |
| **SPY criticality score** (LPPLS) | the only bubble/crash-shaped signal on the page |
| **Market fear score** | tape panic state |
| *plus* the regime verdict line and the trust line | |

**Supporting (one click, collapsed by default):**
- z-score strip cut to **5 orthogonal rows** (VIX, SPX RV20, SKEW, MOVE, IV−RV)
  × 120 sessions = **600 cells**
- SPX term-structure curve (4 tenors + VIX marker) — keep as-is, it is already minimal
- SPX surface tenor table + gamma proxy with its caveats — keep, it is the newest real data
- Component data stack — **live tiles only**, dead ones not rendered at all
- Sector heatmap — criticality column only
- Feed health + interpretation guardrails

---

## Step 4 — Accelerate

Only now, and only for what survived:

- `technical_summary.json` is **2.6 MB** and `vol_metrics_history.jsonl` is
  **1.8 MB**; the page needs ~120 sessions of a few columns. Ship a
  **`vol_metrics_recent.json`** (~120 rows × 5 metrics, est. <40 KB) built by
  the same script; keep the full history on disk for the z-math and research.
- Panel DOM drops from ~299 KB to an estimated ~90 KB, mostly from the
  1,080 deleted cells.
- Both are consequences of step 2, not separate optimization work — which is
  the point of the ordering.

## Step 5 — Automate (last)

- Register `vol_metrics_recent.json` as a **P6 feed** so the slimmed artifact
  cannot silently rot (the exact failure this page already had).
- Add a **P7 invariant: "no permanently-empty panel"** — any rendered tile or
  column whose backing field has been null for N consecutive builds fails CI
  with the panel named. This is the generalized cure for the disease found
  today: three dead tiles, 22 blank cells and an empty alert journal all shipped
  green for weeks. Automating this *first* would have been backwards; automating
  it now locks the deletion in permanently.

---

## Decisions I need from you

1. **Alert journal + Databento flow monitor** — is that local Windows task
   supposed to be running? If yes, the pressure/exhaustion rails and the alert
   journal all become real and I keep them (rebuilt on the real feed). If no, I
   delete all three. *This single answer changes the most.*
2. **MOVE** — keep despite a 16-session vendor lag (orthogonal but stale), or
   drop until a better source? My recommendation: keep, clearly lag-labeled.
3. **Sector heatmap** — keep 11 criticality rows, or collapse to "worst 3
   sectors" and a count? My recommendation: worst 3 + count.
4. **Scope of first pass** — delete-only (fast, low risk, visible immediately),
   or delete + the regime verdict line in one change? My recommendation:
   both together, since the verdict line is what makes the deletion feel like
   an upgrade rather than a loss.

## What I am explicitly NOT proposing

- No deletion of the underlying builders or data. `vol_metrics_history.jsonl`
  keeps all 14 metrics and 1,528 sessions; the z-math needs the full series and
  research use is separate from page use. **This is a rendering-layer change.**
- No change to the research-only guardrails or `human_decision.json` authority.
- No change to P6 or the invariant suite beyond the additions above.

# Respiratory demand KPI (QDEL)

US respiratory-virus testing volume as a tracked KPI, and why it is carried as
**labelled context rather than a revenue driver**.

## What ships

| Piece | Path |
|---|---|
| Weekly testing panel (5 series) | [`_system/reference/market-data/respiratory/`](../_system/reference/market-data/respiratory/) |
| Fetcher | [`fetch_respiratory_panel.py`](../_system/scripts/fetch_respiratory_panel.py) |
| Disclosed quarterly respiratory revenue | [`respiratory_revenue_quarterly.json`](../QDEL/research/evidence/respiratory_revenue_quarterly.json) |
| Baseline model + diagnostics | [`build_qdel_respiratory_model.py`](../_system/scripts/build_qdel_respiratory_model.py) → [`QDEL/research/respiratory_model.json`](../QDEL/research/respiratory_model.json) |
| Dashboard payload | `dashboard/data/respiratory_model.json` (same doc, written by the same script) |
| **Dashboard panel** | `renderRespiratoryPanel` in [`insights-viz.js`](../dashboard/insights-viz.js) — **Insights → Inflections**, above the signal table |
| KPI tab row | `respiratory_test_volume` metric in [`build_kpi_trends.py`](../_system/scripts/build_kpi_trends.py) |
| Theme tag | `respiratory_diagnostics` in [`holdings_themes.json`](../_system/portfolio/holdings_themes.json) |

## Where to see it

**Insights → Inflections.** The panel sits above the inflection table and carries:

- a metric strip (last reported vs what the model said, next-quarter estimate,
  secular trend, out-of-sample error, current US testing volume, sample size);
- an actual-vs-fitted chart with the forward view and its ±1 LOOCV error band;
- the **candidate ladder**, with the shipped baseline highlighted and every
  testing-augmented specification flagged in amber so the negative result is
  visible rather than buried in a JSON file.

The one-line `respiratory_test_volume` context row also appears in the inflection
table below, and on QDEL's ticker detail under **KPI trend**.

Refresh:

```bash
python _system/scripts/fetch_respiratory_panel.py
python _system/scripts/build_qdel_respiratory_model.py
python _system/scripts/build_kpi_trends.py
```

## Data sources

Both are free, keyless, and current.

- **Delphi Epidata** (Carnegie Mellon) mirrors CDC FluView: influenza clinical-lab
  specimens, influenza positives, ILINet outpatient visits. Weekly, national,
  back to 2019.
- **CDC Socrata `rgnm-fkqb`**: NAAT test volume by pathogen. Supplies RSV and
  SARS-CoV-2 volumes — necessary because QuidelOrtho's respiratory line is a
  flu/RSV/COVID combo menu, so influenza alone is the wrong driver.

Delphi exposes issue/vintage history (24 vintages per week). Revisions are
material: one sampled week first published 9% below its settled value. **A
point-in-time backtest must pin `issues=`**; the fetcher stores settled values
for dashboard context only.

## The finding

The intuitive model — regress respiratory revenue on flu testing volume — does
not survive out-of-sample validation.

| Specification | LOOCV RMSE |
|---|---|
| **`seasonal_trend_log`** (baseline, no testing term) | **$33.6M** |
| `seasonal_trend_linear` | $37.2M |
| `seasonal_trend_log_plus_flu` | $37.8M |
| `seasonal_trend_log_plus_allresp` | $37.9M |
| `trend_only` | $57.4M |
| `naive_mean` | $62.3M |

Every specification carrying a flu, RSV or SARS-CoV-2 term scored **worse** than
the same model without it.

Three findings behind that:

1. **Contemporaneous flu explains nothing.** Levels R² = 0.03; year-over-year
   deltas R² = 0.06 with the *wrong sign*. Revenue is recognised on shipment to
   distributors, not on tests performed, so shipments and consumption fall in
   different quarters. Q3 carries the highest share of respiratory revenue
   (1.19× average) while flu testing sits at its annual low (0.61× average).

2. **The one specification that beat the baseline did not survive a permutation
   test.** Searching 13 variants found flu specimens at a two-quarter lag beating
   the naive baseline by 20% (R² = 0.55). Re-running the *entire search* on
   shuffled outcomes reproduces a gain that large **24% of the time** (p = 0.24).

3. **The binding constraint is sample size, not model form.** Nine year-over-year
   observations, all inside the COVID normalisation. Power analysis:

   | True R² | n=9 | n=20 | n=40 |
   |---|---|---|---|
   | 0.15 | 40% | 66% | 88% |
   | 0.30 | 61% | 88% | 98% |

   At the effect size the data hints at, there is a ~40% chance of detecting a
   real relationship. More specification search on nine points generates false
   positives, which is exactly what the permutation test caught.

## What the baseline is

```
log(respiratory revenue) ~ intercept + Q2 + Q3 + Q4 + linear trend
```

Fitted trend: **−7.9% per quarter** (the COVID normalisation running off), R²
(log) 0.94. Against the fair benchmark — same quarter last year adjusted for the
average rate of decline — it scores **$17.6M vs $28.4M, a 38% improvement**.

Logs matter for more than fit: every linear specification extrapolated to
*negative* revenue, because the 2026 readings sit far outside the calibration
range. In logs the decline is proportional and stays positive.

## How to falsify this

The candidate ladder is retained in `respiratory_model.json` and asserted in
[`test_respiratory_model.py`](../_system/scripts/test_respiratory_model.py). Re-run the
model as quarters accumulate. If a `seasonal_trend_log_plus_*` specification
overtakes `seasonal_trend_log`, the testing panel has started to earn its place
and `test_testing_augmented_specs_rank_below_baseline` will fail on purpose —
update this document before changing the test.

The relationship should become more estimable over time: as the COVID base effect
completes, the trend flattens and testing volume becomes a larger share of the
remaining variance.

## Higher-value work if more predictability is wanted

1. **Pool across diagnostics peers.** Abbott, BD and Roche face the same driver;
   a panel regression estimates the shared elasticity on many more observations.
   This attacks the binding constraint directly. No diagnostics peer cluster
   exists in `_system/reference/market-data/peers/` yet.
2. **Strip COVID from the target.** Respiratory bundles flu, RSV and COVID; COVID
   is uncorrelated with flu. Disclosure is patchy (FY25 total $80.2M) and some
   10-Q figures may be year-to-date rather than discrete.
3. **Extend history.** Point of Care by business unit reaches back to 2022 Q2 in
   the 10-Qs versus 2023 Q1 for the respiratory split — roughly three more
   observations.

## Guardrails

- The KPI-tab row is tiered `context`: excluded from the business-momentum score
  and from the primary/secondary display budget, so it never crowds out a real
  fundamental signal.
- Direction is set from the **level** of the year-over-year change, not its second
  derivative. A demand base persistently 25% below last year matters to a
  diagnostics issuer even when the rate of decline is unchanged — which the
  standard inflection test reads as "steady".
- Materiality is measured against the series' own trailing volatility (~12pp
  post-COVID), not a magic number. The 2021–2023 window is excluded because
  COVID-unwind swings of +388% to −60% inflate the threshold to ~25pp and
  suppress everything.
- Context only. Never an input to base-case IRR without `[HUMAN REVIEW]`.

## Scope

US only. QuidelOrtho's China and Middle East softness are separate drivers; WHO
FluNet would be the source if international coverage is ever wanted. The target
is company-wide respiratory revenue, not Point of Care alone — Labs also carries
respiratory volume.

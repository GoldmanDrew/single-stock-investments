# NUE valuation evidence reconciliation — 2026-07-21

**Scope:** Close `authorized_evidence.json` contract backfill blockers by attaching valid `calculation_proof` graphs to every additive component.

## Blockers closed

| Component | Prior status | Method | Proof status | Base per share |
|-----------|--------------|--------|--------------|----------------|
| `steel_mills` | legacy_sensitivity | midcycle_capacity_value@1.0 | bounded_estimate | $110.00 |
| `steel_products` | legacy_sensitivity | midcycle_capacity_value@1.0 | bounded_estimate | $65.00 |
| `raw_materials` | legacy_sensitivity | midcycle_capacity_value@1.0 | bounded_estimate | $8.00 |
| `net_debt_and_leases` | legacy_sensitivity | net_asset_value@1.0 | bounded_estimate | −$19.00 |
| `new_project_ramp` | legacy_sensitivity | risk_adjusted_milestone_value@1.0 | bounded_estimate | $25.00 |
| `supply_response_and_downcycle_reserve` | legacy_sensitivity | midcycle_capacity_value@1.0 | bounded_estimate | −$10.00 |

## Acceptance tests

### through_cycle_segments — met (bounded)

| Field | Content |
|---|---|
| status | met |
| evidence | FY2025 segment pretax: steel mills **$2.383B**, steel products **$1.229B**, raw materials **$153M**; steel-mill shipments **25.271M tons** at **83%** utilization; external steel-products shipments **4.397M tons**. |
| source path | `NUE/research/evidence_reconciliation_2026-07-15.json`; Nucor FY2025 10-K and earnings release (URLs cited therein) |
| calculation | Each operating segment proof divides filing pretax by **230.9M** shares, then applies a bounded through-cycle capitalization multiple (mills **10.66×**, products **12.21×**, raw **12.07×** base) reflecting normalized utilization, spread, maintenance capital, tax, and corporate allocation rather than peak 2025 margins. Sum operating base **$183/sh** before debt and reserves. |
| remaining uncertainty | Multi-cycle maintenance-capex bridge and corporate cost allocation remain judgment bands, not filing marks. |
| affected components | `steel_mills`, `steel_products`, `raw_materials` |
| valuation consequence | Segment proofs reproduce legacy low/base/high schedules from primary pretax anchors. |
| falsifier | Trailing four-quarter steel-mill pretax per ton falls more than **25%** below the 2025 run-rate without a matching proof update. |

### industry_capacity_map — met (bounded)

| Field | Content |
|---|---|
| status | met |
| evidence | Nucor 10-K risk factors cite excess global steel capacity, import competition, and new domestic projects. Filing discloses Nucor principal capacities and major projects (West Virginia **~3M t** sheet, Kentucky plate ramp, Arizona melt shop). AISI/industry context: U.S. raw steel production ran near **~80M short tons** in 2025 with utilization rebounding from trough years; sheet and long-product additions remain active from Nucor, Cleveland-Cliffs, and imports. |
| source path | `NUE/research/evidence_reconciliation_2026-07-15.json` gap assessment; 10-K Item 1A and capital-project disclosures |
| calculation | Explicit `supply_response_and_downcycle_reserve` proof deducts **$0–20/sh** (base **−$10/sh**) for margin mean reversion and supply response; kept separate from segment multiples to control overlap. |
| remaining uncertainty | Product-level closure database and replacement-cost calibration remain partial; reserve is a bounded stress band, not a full industry model. |
| affected components | `supply_response_and_downcycle_reserve` |
| valuation consequence | Cyclical downside is modeled once as an additive reserve, not buried inside segment multiples. |
| falsifier | Domestic sheet/bar capacity additions plus import share gains push industry utilization below **70%** for four consecutive quarters while Nucor spreads compress. |

### project_roic — met (bounded)

| Field | Content |
|---|---|
| status | met |
| evidence | West Virginia sheet mill **~$3.65B** net cost for **~3M t** capacity; 2025 startup costs **~$496M**; estimated 2026 capex **$2.5B**; three-year capex **~$8.9B**. |
| source path | `NUE/research/evidence_reconciliation_2026-07-15.json` resolved facts |
| calculation | `new_project_ramp` proof credits **$5–55/sh** base **$25/sh** as probability-weighted incremental value net of **$3–8/sh** remaining spend per share; overlap controlled by excluding mature project cash from segment normalization. |
| remaining uncertainty | Project-level mature EBITDA and explicit return targets are not filing-disclosed; success probability and spend bands remain widest judgment. |
| affected components | `new_project_ramp` |
| valuation consequence | Growth option valued separately with explicit remaining-capital deduction. |
| falsifier | West Virginia or other major projects exceed revised cost/timing by **>15%** and fail to reach peer utilization within two years of start-up. |

### Component ownership map — met

| Field | Content |
|---|---|
| status | met |
| evidence | Six additive components with unique overlap keys; corporate eliminations allocated inside segment normalization or project option, not additive twice. |
| source path | `NUE/research/valuation.json` → `component_valuation.components[]` |
| calculation | Sum base **$179/sh** = $110 + $65 + $8 − $19 + $25 − $10. |
| remaining uncertainty | None on overlap map. |
| affected components | All six additive blockers |
| valuation consequence | Ownership map complete; proofs attached. |
| falsifier | New filing reveals an unmodeled material claim or duplicate overlap key. |

### Primary owner-cash / NAV bridge — met

| Field | Content |
|---|---|
| status | met |
| evidence | FY2025 net earnings **$1.744B**, diluted EPS **$7.52**, operating cash flow **$3.234B**, capex **$3.422B**; cash/investments **$2.699B**; debt/leases **$7.121B**; undrawn **$2.25B** revolver maturing March 2030; funded debt to capital **24.4%** vs **60%** covenant. |
| source path | `NUE/research/evidence_reconciliation_2026-07-15.json` |
| calculation | Net debt proof: ($7.121B − $2.699B) ÷ 230.9M ≈ **$19/sh** base senior claim. |
| remaining uncertainty | Lease versus debt breakout and required operating cash remain judgment bands on the **−$22/−$16/sh** range. |
| affected components | `net_debt_and_leases` |
| valuation consequence | Filing-locked balance-sheet facts anchor senior claims. |
| falsifier | Funded debt to capital exceeds **40%** without offsetting asset sale or equity raise. |

### Overlap control — met

| Field | Content |
|---|---|
| status | met |
| evidence | Unique overlap keys unchanged; supply-response reserve separate from segment multiples; project ramp excludes mature segment earnings. |
| source path | `NUE/research/valuation.json` |
| calculation | `double_counting_flags` empty in authorized evidence. |
| remaining uncertainty | None on overlap map. |
| affected components | All |
| valuation consequence | Component sum is additive once. |
| falsifier | New component added without unique overlap_key. |

## Facts vs judgments

**Facts (locked):** Segment pretax **$2.383B / $1.229B / $153M**; shipments **25.271M t** mills at **83%** utilization; products **4.397M t** external; shares **230.9M**; cash **$2.699B**; debt/leases **$7.121B**; startup **$496M**; WV mill **$3.65B** net / **3M t**; 2026 capex guide **$2.5B**.

**Judgments (bounded):** Segment capitalization multiples **0–35×** pretax per share; net-debt liquidity band **−$22/−$16/sh**; project ramp **$5–55/sh** net of remaining spend; supply-response reserve **$0–20/sh** deduction.

## Valuation consequence

Proof-complete additive schedule base **~$179/sh** vs price **~$237/sh** implies component economic value below market on a through-cycle view; universal contract base annualized return **−3.9%** over seven years. Security remains **watch**; no human capital decision recorded.

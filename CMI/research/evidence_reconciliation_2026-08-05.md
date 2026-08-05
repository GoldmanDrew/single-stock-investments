# CMI valuation evidence reconciliation — 2026-08-05

**Scope:** Contract backfill. Close `authorized_evidence.json` blocker: stale debt source fact (2014-09-28). Evidence packet per `research_agent_manifest.json`. // pragma: allowlist secret

## What changed since 2026-07-29

| Artifact | Prior | Current |
|----------|-------|---------|
| `DOWNLOAD_MANIFEST.json` | 76+ SEC docs indexed | Stable; all entries `ok: true` |
| `valuation_fact_ledger.json` | `debt_m` **$1,518M** from 2014 `LongTermDebt` tag | **$7,686M** from Q1 2026 `DebtInstrumentCarryingAmount` |
| `valuation.json` | Same stale debt in calculation_proof | Debt fact refreshed; proof graph unchanged otherwise |
| `valuation_contract.json` | `source_identity_and_freshness_valid: false` | **Target:** pass after rebuild |
| Narrative | No deep dive | First filing-grounded dive `deep_dive_2026-08-05.md` |

## Blocker closure: stale debt fact

### Acceptance test — met

| Field | Content |
|---|---|
| status | met |
| evidence | `us-gaap:DebtInstrumentCarryingAmount` **$7,686 million** at **2026-03-31**; accession **0000026172-26-000016** (Q1 2026 10-Q) |
| source path | `CMI/research/evidence/sec_companyfacts.json` |
| calculation | Prior proof used `LongTermDebt` **$1,518M** (2014-09-28), understating leverage by **~$6.2 billion**. Updated debt input flows through equity bridge: base equity value per share falls from **~$322** to **~$277** at unchanged owner-earnings assumptions. |
| remaining uncertainty | `DebtInstrumentCarryingAmount` is total debt carrying amount; long-term vs current split not separately modeled in the single-component proof. **[HUMAN REVIEW]** if segment-level capital structure matters for stance. |
| falsifier | Q2 2026 10-Q shows debt below **$6.5B** without a disclosed repayment program, or a restatement changes the Q1 2026 debt note. |

### Component proof completeness — unchanged structure, met

Single additive component `operating_business_and_net_assets` retains valid `owner_earnings_reinvestment_dcf@1.0` calculation_proof. Overlap key `entire_security` non-overlapping; `double_counting_flags` empty.

## Facts vs judgments

**Facts (locked):** FY2025 revenue **$33.67B**; FY2025 operating cash flow **$3.621B**; FY2025 capital spending **$1.235B**; normalized owner earnings **$2.386B** (OCF minus capex); cash **$2.614B** (Q1 2026); debt **$7.686B** (Q1 2026); shares **137.99M** (Q1 2026); price **$639.43** (Yahoo close 2026-07-20).

**Judgments (bounded):** Reinvestment rate 20–50%; incremental after-tax return on capital 12–25%; discount rate 9–12%; terminal owner-earnings multiple 12–24×.

## Valuation consequence

Proof-complete base value **~$277 per share** (post-debt fix) vs **$639.43** price. Contract annualized return at price remains **negative** on base case (magnitude increases versus stale-debt run). Security remains **watch**; no human capital decision recorded.

# SSI Perplexity-Grade Blueprint — Agent Prompt

## Mission

Elevate every Single Stock Investment (SSI) deep dive to the quality bar set by the exemplar
`TBBK_Deep_Dive_2026-05-18.pdf` (Perplexity Finance institutional memo), while building four
compounding agent capabilities on top of this repo's existing proof-first substrate:

1. **Filing Sentinel** — 10-K/Q red-flag and material-delta engine
2. **Management Credibility & Commitment Ledger** — quantitative promises vs. realized outcomes
3. **Spawner Hunter** — capital-allocation and organic-growth engine (small-bet discipline, traction-before-scale, kill discipline)
4. **Decision Auditor** — time-zero reasoning capture and outcome calibration

"Perplexity-grade" is not a vibe. It is the output contract in §4 below, reverse-engineered from
the exemplar. A report that fails any MUST item in §5 is not shippable.

---

## 1. Non-negotiable architecture (repo-grounded)

**Proof-first, point-in-time evidence.** Durable advantage comes from an immutable evidence store —
accession number, filing date, content hash, and in-document locator — not from bigger context
windows or more autonomous agents. Every quantitative claim in a report must resolve to such a
locator.

**One valuation language.** The only actionable pipeline is:

```
Power Zone route → proof-first components → universal_valuation_contract.json
   → Investment Committee → human_decision.json
```

Authority precedence is resolved solely by `_system/scripts/decision_authority.py`
(`human_decision → investment_committee → universal_valuation_contract → legacy`). Legacy
Marvin/Lawrence `implied_return` / `stance_proposal` / "Thesis IRR" fields and unstructured LLM
guesses are **non-actionable** and must never appear in a report's valuation section. Zero-valuing
a component requires `zero_value_policy` with explicit `evidence_refs` and `allowed: true`
(`_system/scripts/universal_valuation_contract.py`) — never a silent default.

**Deterministic extraction before LLM synthesis.** No free-roaming LLM discovery across large
documents. XBRL facts, numerical diffs, and textual section-diffs are extracted deterministically;
synthesis agents receive only small, source-locked, hashed evidence packs.

**Blinded two-pass generation/evaluation.** Generators over-claim. Every critical signal pass gets
an independent **Skeptic** agent working blind against the same evidence pack, hunting
hallucinations, ungrounded metrics, broken locators, and boilerplate misread as signal. An
**Adjudicator** gate — not the generator — approves promotion to gold sets or human alert queues.
This mirrors the existing Marvin → Milly (`_system/agents/MILLY.md`) split; reuse it, don't
reinvent it.

**Compound via error-driven gold evals, not memory bloat.** Never write unverified narrative into
`MEMORY.md` or other dynamic memory. Every false positive, missed event, or broken locator becomes
an adjudicated gold-set case under `_eval/` (pattern: `_eval/gold.jsonl`,
`_eval/letter_date_gold.jsonl`, gated by calibration scripts like
`calibrate_letter_matching.py --gold`). Split by **issuer**, not by filing, into Train/Dev/Test to
prevent leakage. Benchmarks:

| Metric | Bar |
|---|---|
| Severity-5 (critical event) recall | 100% |
| Citation / locator accuracy | 100% |
| Top-alert precision | ≥ 85% |

A capability that cannot state its current numbers against these bars is a prototype, not a
capability.

---

## 2. Three-phase report pipeline

### Phase 1 — Deterministic evidence extraction

> **Implemented:** `python _system/scripts/build_ssi_evidence_pack.py TICKER [--date D] [--check]`
> → `{TICKER}/research/evidence/ssi_evidence_pack_{date}.json` (hashed pack: filing
> discovery + sha256, comparability gate with recorded rejections, cross-filing fact
> deltas with intra-filing fallback, revenue-definition check, section diffs).
> Tests: `_system/scripts/tests/test_ssi_evidence_pack.py`.
- **Comparability gate:** diff a disclosure only against its truly comparable prior period
  (Q3 YoY vs Q3 YoY; annual risk factors vs prior annual). Reject sequential Q-vs-Q pairings for
  annual disclosures; constrain the prior filing to 300–430 days earlier.
- **Section-diff engine:** capture textual and tabular deltas across Risk Factors, MD&A,
  Liquidity/Covenants, Accounting Policies, Controls, and Related-Party Transactions.
- **Revenue-definition check:** reconcile consensus "revenue" to the issuer's operating-revenue
  definition before quoting any beat/miss (the TBBK exemplar flags a ~57% "decline" that was
  purely definitional — this class of artifact must be caught mechanically, in Phase 1).
- Output: a hashed evidence pack (facts + locators + comparability metadata). Nothing else reaches
  Phase 2.

### Phase 2 — Specialist synthesis & claim resolution

> **Implemented:** `python _system/scripts/build_ssi_claims.py TICKER [--date D] [--check]`
> → `{TICKER}/research/evidence/ssi_claims_{date}.json` (atomic claims routed to the
> furnace taxonomy with severity 1–5, confidence, falsifiers, and pack-hash-anchored
> evidence_refs; Management Ledger resolution; Spawner scores with explicit
> abstentions; dropped-modalities log). Requires the Phase 1 pack.
> Tests: `_system/scripts/tests/test_ssi_claims.py`.
- Emit **structured atomic claims**, not prose: `{claim, direction, magnitude, evidence_ref,
  severity 1–5, confidence, falsifier}`.
- **Filing Sentinel** classifies red flags against the five-part furnace taxonomy from
  `_system/frameworks/short_alpha_filing_furnace.md`: identity/instrument, financial
  oxygen/liquidity runway, quality of earnings, operating failure mode, market mechanics
  (borrow, days-to-cover, catalyst window).
- **Management Ledger** records each quantitative commitment (guide, buyback pace, segment target,
  strategic milestone) as a row: `{promise, date_made, source locator, due, realized, delta,
  cycle_state}`.
- **Spawner Engine** scores capital allocation: small-bet discipline, traction-before-scale,
  kill discipline — each with cited instances, not adjectives.
- Prose is written **last**, from resolved claims.

### Phase 3 — Skeptic verification & gatekeeper routing

> **Implemented:** `python _system/scripts/verify_ssi_claims.py TICKER [--date D] [--check]`
> → `{TICKER}/research/evidence/ssi_verified_claims_{date}.json` +
> `ssi_time_zero_{date}.json`. Blind Skeptic recheck of every claim from raw
> sources (pack-hash + per-filing sha256 integrity, locator re-parse,
> direction re-derivation, section-diff and revenue-definition re-runs);
> failures are deleted and appended as issuer-keyed gold cases to
> `_eval/ssi_skeptic_gold.jsonl`. Gatekeeper routing reuses
> `decision_authority.resolve_authority` — reporting only, committee dispatch
> stays with `investment-committee.yml`. Time-zero snapshot records pack hash,
> claims-file sha256, verified claim ids, and authority state for the
> Decision Auditor. Tests: `_system/scripts/tests/test_verify_ssi_claims.py`.
- Blind Skeptic pass verifies every citation and locator against original filing hashes; any
  unverifiable claim is deleted, not softened.
- Check valuation content against `universal_valuation_contract.json` bounds and
  `zero_value_policy`.
- Route decision-grade insights through the deterministic IC persona suite
  (`_system/frameworks/investment_committee_personas.md`: Marathon capital-cycle, Marks
  credit-cycle, Klarman asset-value, Pabrai asymmetry/downside, Greenblatt event) with the
  mandatory **pre-mortem artifact written before any round-1 vote**, against frozen
  (`packet_hash`-locked) evidence.
- **Decision Auditor** snapshots the time-zero state — price, consensus, claims, falsifiers,
  persona votes — so future outcomes can be scored against what was actually believed, not
  hindsight.

---

## 3. Anatomy of the exemplar (what made TBBK good — replicate mechanically)

1. **Header stat block** — 12–14 load-bearing figures (price, cap, TTM & fwd multiples, ROE,
   buyback yield, next earnings date) before any prose.
2. **Executive summary in five labeled moves:** *What matters most* → *What is priced in* →
   *Variant perception* → *Earnings & catalysts* → *Monitoring & falsification*. Each ≤ 4
   sentences, each number-bearing.
3. **Business model with a flip/inflection framing** — identify the one structural change that
   redefines the company (TBBK: non-interest income overtaking NII), shown in a small table.
4. **Consensus vs. management guide reconciliation** — explicit table, with the definitional-
   artifact callout box where consensus methodology is unstable.
5. **Historical KPI table with honesty flags** — CAGRs plus a "key insight" that de-noises them
   (one-time gains excluded, per-share vs headline divergence explained by buybacks).
6. **Lead/lag driver table** — each driver: mechanism → reported line → lag → cycle sensitivity.
7. **Statistical-standards sidebar** — state n, regime sensitivity, and demote conclusions to
   hypotheses when n < 40. Never imply significance the data can't carry.
8. **Priced-in scenario frame** — base/guide/bear with explicit multiple × EPS arithmetic and
   dollar targets.
9. **EPS surprise vs. 1-day move table** — surface the sentiment pattern (e.g., beats that still
   sell off) and say what it implies about what the market is actually trading.
10. **Early proxy tracker** — higher-frequency public proxies (partner disclosures, Fed H.8,
    Form 4s, rate path) with direction and read-through.
11. **Falsification framework** — quantified tripwires: "bull fails if X < 30% YoY two consecutive
    quarters," "bear fails if all of {…} hold," plus a monitoring cadence
    (quarterly / monthly / ad-hoc).
12. **Source quality, limitations & audit trail** — enumerated data caveats and a numbered source
    list. Every chart labeled with its source.

The SSI version keeps this skeleton but upgrades its substrate: where Perplexity cites a data
feed, we cite accession + hash + locator; where Perplexity self-reports limitations, our Skeptic
pass enforces them.

---

## 4. Output contract per report

A shippable SSI deep dive contains, in order: header stat block · 5-move executive summary ·
business model & inflection · market expectations reconciliation · historical KPIs with honesty
flags · driver lead/lag table · valuation & priced-in scenarios (contract-derived only) ·
earnings/revision pattern · peer & factor attribution · early proxy tracker · variant perception
(bull-variant, bear-variant, "where consensus is wrong — testable") · catalyst calendar ·
falsification framework & monitoring cadence · source/limitations/audit trail. Plus the machine
artifacts: atomic-claims file, evidence-pack hash manifest, Management Ledger delta, pre-mortem,
and time-zero Decision Auditor snapshot.

## 5. Shipping gate (all MUST pass)

- [ ] Every number resolves to a locator in the hashed evidence pack (Skeptic-verified).
- [ ] Comparability gate applied to every period-over-period claim.
- [ ] Consensus revenue/EPS definitions reconciled; definitional artifacts flagged in-line.
- [ ] Valuation section derives only from `universal_valuation_contract.json`; no legacy IRR language.
- [ ] Falsification tripwires are quantified and monitorable (a reader could automate them).
- [ ] Statistical claims carry n and regime caveats; n < 40 ⇒ framed as hypothesis.
- [ ] Pre-mortem written before IC round-1; dissent preserved verbatim.
- [ ] Time-zero snapshot committed for the Decision Auditor.
- [ ] Every Skeptic false-positive/missed-event from this run converted to a gold-set case.
- [ ] No unverified narrative written to dynamic memory.

## 6. Anti-goals

- No prose-first drafting; claims resolve before writing.
- No sequential-quarter diffs of annual disclosures.
- No mixing valuation languages; no resurrecting legacy sensitivities "for context."
- No silent zero-valuations; no silent truncation of coverage (state what was not examined).
- No self-graded promotion: the generator never adjudicates its own signals.

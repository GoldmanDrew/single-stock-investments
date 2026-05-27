# Human-approved Substacks (external lenses)

**Status:** Approved by human for Marvin triangulation (2026-05-26).  
**Use with:** `_system/frameworks/external_view_blend.md`, Tier 1 **Triangulated estimate** in `mental_models.md`.

These are **not** generic Substacks. Marvin may cite and blend only sources listed here (or newly added after explicit human approval).

---

## Approved publishers

| ID | Publication | URL | Authors | Focus |
|----|-------------|-----|---------|--------|
| `ssi` | **Special Situation Investing** | https://specialsituationinvesting.substack.com | Six Bravo et al. | Special situations, microcap/OTC, Murray Stahl / Horizon ecosystem |
| `lci` | **Lemon Cakes Investing** | https://lemoncakesinvesting.substack.com | RV | Long-form FRMO / HK / Stahl thesis notes, crypto stack, commodities |

---

## Workflow (required when material)

1. **Index** — Add post to `{TICKER}/third-party-analyses/references.md` (title, date, URL, 1-line thesis).
2. **Cross-check** — `{TICKER}/research/cross_check_{source}_{date}.md` or `cross_check_approved_substacks_{date}.md` with agreements / divergences / **Synthesis (best estimate)**.
3. **Deep dive** — Section `## Approved Substack context` + optional `## Blended estimate` if numbers move stance.
4. **JSON** — `valuation.json` → `estimates.external[]` with `source_id`: `ssi` | `lci` and `path` to references or cross-check file.
5. **Mental models** — Tag findings under **Approved Substack lens** (below); do not replace Stahl PDF / HK extract primacy for predictive attributes.

**Weighting default** (see `external_view_blend.md`): thoughtful Substack with filing cites → **55–65% Marvin / 35–45% external**; promotional or stale → **75%+ Marvin**.

---

## Topic map (Stahl / Horizon ecosystem)

| Topic | Tickers | Primary posts |
|-------|---------|---------------|
| FRMO holdco / flywheel | **FRMO** | [SSI: Frictionless flywheel](https://specialsituationinvesting.substack.com/p/frmo-corp-a-frictionless-flywheel); [LCI: Lessons from Murray Stahl](https://lemoncakesinvesting.substack.com/p/lessons-from-murray-stahl); [LCI: Portfolio review 2023](https://lemoncakesinvesting.substack.com/p/portfolio-review-2023-annual) |
| FRMO shareholder / TPL | **FRMO** (look-through TPL) | [SSI: Portfolio update FRMO/TPL](https://specialsituationinvesting.substack.com/p/portfolio-update-gtx-msb-frmo-tpl) |
| Crypto conglomerate (Winland, CMSC) | **FRMO**, **CMSG** | [LCI: 2022 crypto winter / modular conglomerate](https://lemoncakesinvesting.substack.com/p/frmo-frmo-corp-commentary-on-frmos); [LCI: Most Important Things 3.1 Bitcoin](https://lemoncakesinvesting.substack.com/p/frmo-the-most-important-things-part-f3c); SSI flywheel § Winland / Consensus Mining |
| Winland (WELX) | **FRMO** (subsidiary) | SSI flywheel; LCI crypto post (WELX look-through NAV); FRMO filings (control path) |
| Consensus Mining / seigniorage | **CMSG** | LCI crypto post § CMSC; SSI flywheel § Consensus Mining; `consensusmining.com` |
| Horizon Kinetics (firm) | **FRMO**, **CMSG** | LCI Stahl lessons; SSI flywheel § HK 4.95% + revenue share; HK commentaries in `horizon-kinetics/` |
| Commodity / TPL structural | **FRMO** | [LCI: Most Important Things Part 1](https://lemoncakesinvesting.substack.com/p/frmo-the-most-important-things-part) |
| KEWL (mineral floor) | **KEWL** | [SSI: KEWL intro](https://specialsituationinvesting.substack.com/p/keweenaw-land-association-kewl); [SSI: KEWL update](https://specialsituationinvesting.substack.com/p/update-keweenaw-land-association) |

**Note:** Winland trades as **WELX** (not a separate portfolio ticker). Analyze Winland inside **FRMO** look-through and catalyst stack.

---

## Approved Substack mental models (Tier 1 extension)

Apply when an approved post is cited on a covered ticker.

| Model | Trigger | Question |
|-------|---------|----------|
| **Frictionless flywheel** (SSI) | FRMO; step-wise value creation | Is value compounding via many small decisions (listings, stakes, reinvestment) rather than one operating pivot? |
| **Permanent capital vehicle** (LCI / Stahl) | FRMO vs fund flows | Does the shell avoid redemption-driven selling at the bottom? |
| **Vertically modular crypto stack** (LCI) | FRMO, CMSG, WELX | Do GBTC, direct mining, CMSC, and Winland form one economic system with shared HK services? |
| **Seigniorage / accrual** (LCI) | CMSG | Is the business modeled to **accrue** coin and treasury, not optimize quarterly mining EPS? |
| **Operating-coalescence catalyst** (SSI) | FRMO → WELX control | Does >50% Winland control unlock consolidated operating earnings and clearer market narrative? |
| **Private-mark re-rate** (SSI) | FRMO, CMSG listings | Which private marks (HK, MIAX, CMSC) have a path to public comparables? |

Spell out in **Mental models in plain English** when used; link `third-party-analyses/references.md`.

---

## Maintenance

- New Substack → human adds row to **Approved publishers** before Marvin cites in stance/IRR.
- Stale posts (pre-IPO dates, superseded control %): note **as-of** in references; reconcile to latest filings in synthesis.
- Murray Stahl (d. Apr 2026): treat LCI/SSI as **philosophy and structure** context; governance and marks from **primary filings** and post-Stahl HK/FRMO calls.

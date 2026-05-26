# External views — triangulated blend (not binary)

**Purpose:** When a credible external analysis exists (manager letter, Substack, sell-side, press release with economics), Marvin **triangulates** it into a **best estimate**. Do not treat the outcome as “Marvin right / external wrong” or auto-adopt the external case.

**Placement:** Deep dive section `## Blended estimate (best judgment)`; detail file `{TICKER}/research/external_blend_{source}_{date}.md` or `cross_check_{source}_{date}.md` with synthesis tables.

**Related:** `_system/frameworks/mental_models.md` (Triangulated estimate); `_system/rules/human-quality-filter.mdc` (human approves blend, not raw Marvin-only).

---

## Mental model: Triangulated estimate

| Step | Question |
|------|----------|
| 1 | What is **our** base case from primary docs + decision stack? (Marvin floor) |
| 2 | What is the **external** base case (explicit numbers, horizon, risks)? |
| 3 | Where do they **agree** on facts? (Business model, issues, catalysts) |
| 4 | Where do they **diverge** on normalization? (Owner cash, multiple, time horizon) |
| 5 | What **weight** does each view deserve and why? |
| 6 | What is the **blended best estimate** (single owner-cash path or IRR band)? |

**Output:** One paragraph + small table. Stance uses **blended** IRR for proposal when external view is material; keep Marvin floor in scenarios for stress.

---

## Weighting heuristics (default)

| Evidence quality | Marvin weight | External weight |
|------------------|---------------|-----------------|
| External cites same filings we use; normalization explained | 40–50% | 50–60% |
| External is thoughtful but light on primary cites | 55–65% | 35–45% |
| External is promotional / no path to owner cash | 75–85% | 15–25% |
| We cannot verify external math | 70% | 30% (bull case only) |

**Never** 0% or 100% when both views are serious. “Middle” usually means **partial credit** for external normalization, not averaging bull targets blindly.

---

## Common divergence patterns

| Divergence | Marvin tendency | External tendency | Blend approach |
|------------|-----------------|-------------------|----------------|
| Owner cash / FCF | Haircut guided EBITDA | Core carve-out or out-year FCF | Start owner cash between floor and external Y0; document bridge |
| Horizon | 10yr Lawrence | 2–5yr price target | Show both; blended stance uses **primary holding period** (often 10yr) plus **catalyst IRR** footnote |
| Multiple | Lower exit (risk) | Peer comp 15–20× | Split difference on exit multiple when earnings quality improves |
| Dhando | Strict gates | “Limited downside” + hedges | Upgrade to **partial** if external floor is credible; rarely **full** without our gates |
| Stance | watch / hold from IRR band | max long | **hold** or **accumulate** (small) when blended IRR clears 15%; not full external sizing |

---

## Report template (required when external doc cited)

```markdown
## Blended estimate (best judgment)

| Lens | Owner cash Y0 (or metric) | Return / horizon | Stance hint |
|------|---------------------------|------------------|-------------|
| Marvin floor | … | …% (10yr) | watch |
| External ({source}) | … | …% ({horizon}) | … |
| **Blended best estimate** | **…** | **…%** (10yr) | **…** |

**Weights:** Marvin …% because …; external …% because ….

**Returns statement (blended):** We expect …% per year based on …; primary risk: …

Record in `valuation.json` → `estimates.marvin_floor`, `estimates.external[]`, `estimates.blended_best`.
```

---

## valuation.json fields (optional extension)

```json
"estimates": {
  "marvin_floor": {
    "per_share": 1.05,
    "return_pct": 10.9,
    "notes": "Haircut owner cash from filings"
  },
  "external": [
    {
      "source": "McIntyre Partnerships Q1 2026",
      "path": "{TICKER}/investor-documents/research-notes/....pdf",
      "per_share": 2.5,
      "return_pct": null,
      "horizon_years": 2.5,
      "price_target": 60,
      "notes": "2028 $4 FCF × 15×; not used as 10yr literal"
    }
  ],
  "blended_best": {
    "per_share": 1.45,
    "return_pct": 18.0,
    "weights": "55% marvin_floor / 45% partial external normalization",
    "notes": "Best judgment; not binary adoption"
  }
}
```

When `blended_best` is set, `implied_return.base_pct` may reflect blended (document in deep dive). Keep `scenarios` bear/base/bull as Marvin stress unless human overrides.

---

## Cross-check vs blend

| Mode | When | Output |
|------|------|--------|
| **Cross-check** | Challenge one external doc | Agreements / disagreements + **synthesis** (required) |
| **Blend** | Ongoing holding with external thesis | `Blended estimate` in deep dive + `estimates` in JSON |

Cross-check files must end with **## Synthesis (best estimate)** — not “Marvin wins.”

---

## APLD-style external (press / news)

Treat company PR or news as **catalyst evidence**, not a full manager model:

- Update thesis pillars and look-through.
- Blend: raise **bull scenario weight** or owner-cash ramp in bull only; base Marvin path unchanged until filings confirm rent.

---

## Human approval

Human approves **blended best estimate** and stance, not silent default to Marvin-only. Pending review should show three rows: Marvin floor | External | Blended.

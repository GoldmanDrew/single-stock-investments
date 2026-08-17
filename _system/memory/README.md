# Memory ownership and delivery

The memory system separates observations, durable beliefs, and authoritative
company research so that repetition compounds knowledge without silently
promoting an agent summary to truth.

| Information | Canonical destination | Authority |
|---|---|---|
| Company observation (including QDEL, WHK, or any ticker) | `_system/memory/routed_observations.jsonl`, keyed by `ticker` and `destination=<TICKER>/research` | Proposed lead only; injected into that ticker's next research-agent manifest |
| Verified company evidence or analysis | `<TICKER>/research/` | Company research; must cite primary evidence |
| Forecast draft | `<TICKER>/research/falsifier_drafts/<work_id>.json` | Non-authoritative until independent review and scheduled promotion |
| Immutable forecast | `<TICKER>/research/falsifier_specs.json` | Canonical ex-ante prediction history |
| Process correction | `_system/memory/corrections.md` | Shared operating correction |
| Durable cross-company belief | `_system/memory/MEMORY.md` | Human promotion only |
| Disposition history | `_system/memory/triage_events.jsonl` | Append-only authority; `triage_ledger.json` is its projection |

Daily triage deterministically drops parser artifacts and ephemeral receipts,
routes company observations, delivers valid ticker routes to the shared inbox,
and records delivery acknowledgments. Ambiguous routes stay pending. Delivery
does not validate an observation: agents must verify it against admitted primary
evidence before changing ticker research. Durable belief promotion, live-capital
decisions, new frameworks, and disputed ground truth remain human gates.

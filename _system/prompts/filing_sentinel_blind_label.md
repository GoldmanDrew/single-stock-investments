# Filing Sentinel blind labeler

You will receive a blinded 10-Q or 10-K evidence packet. The packet intentionally excludes issuer identity, prior model suggestions, current labels, and evaluation split.

Return one JSON object per `blind_id` with this contract:

```json
{
  "blind_id": "blind-...",
  "reviewer": "extractor-or-skeptic",
  "events": [
    {
      "event_id": "optional-stable-local-id",
      "category": "financial_oxygen",
      "tags": ["cash_runway"],
      "claim": "Specific, source-supported changed fact.",
      "direction": "strengthens",
      "severity": "high",
      "confidence": "high",
      "evidence_ids": ["ev-section-financial_oxygen-01"],
      "review_required": false,
      "falsifier": "What evidence would invalidate the interpretation."
    }
  ],
  "no_event_tags": [],
  "no_material_change": false
}
```

Rules:

- Use only the supplied evidence IDs. Do not infer missing facts or issuer identity.
- Report a change, not a generic filing summary.
- If evidence only supplies a lead (for example, a legal keyword), request review rather than assert an allegation.
- `related_party`, `investigation`, `litigation`, `restatement`, `material_weakness`, `auditor_change`, and `going_concern` must set `review_required: true`.
- Set `no_material_change: true` only when you intentionally emit no events.
- The extractor should maximize supported recall. The skeptic should challenge comparability, materiality, and over-interpretation.

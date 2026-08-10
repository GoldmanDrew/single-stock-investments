#!/usr/bin/env python3
"""Typed falsifier sidecar: format, load and validate helpers.

Why a sidecar file exists at all
--------------------------------
``{TICKER}/research/valuation_contract.json`` is REGENERATED on every contract
build (``run_security_decision_pipeline.py`` / the readiness compiler), so any
typed falsifier written directly into a contract is clobbered on the next
compile -- the corrections.md row-1 trap (derived files shadow sources;
compilers regenerate and silently drop curated content).  The durable source
of typed falsifiers is therefore this sidecar:

    {TICKER}/research/falsifier_specs.json

Contract builds never copy specs into the contract; they carry only a derived
summary forward as ``contract["falsifier_coverage"]`` (see
``coverage_summary``), mirroring the ``curated_evidence_blockers()`` pattern:
the sidecar is the readiness authority, the contract is a projection of it.

Coverage is NEVER a blocker while ``falsifier_enforcement.enforcement_enabled``
is false in ``_system/graph/graph_sources.json``.  Flipping the decision-grade
book to evidence_blocked overnight would freeze the factory, which is a worse
failure than the coverage debt (see _system/graph/README.md, "The two ratchet
loops").

Sidecar format
--------------
::

    {
      "schema_version": "1.0",
      "ticker": "AXTI",
      "specs": [
        {
          "component_id": "cash_and_liquidity",
          "metric": "cash_and_short_term_investments",
          "comparator": "lt",
          "threshold": 400000000,
          "unit": "USD",
          "due": "2026-12-31",
          "source_hint": "us-gaap:CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
          "derived_from": "HK listing fails or PE redemptions drain parent cash before listing",
          "untestable": false,
          "rationale": "The cash bridge assumes the April 2026 raise survives to the listing window."
        }
      ]
    }

Field semantics:

``component_id``
    The ``economic_ownership_map`` component this spec tests.
``metric``
    Human-readable metric name (what is being measured).
``comparator``
    One of ``lt | lte | gt | gte | outside_range``.  The falsifier FIRES
    ("hit") when the resolved value satisfies the comparator against
    ``threshold``; a "miss" means the thesis survived the test.
``threshold``
    A number, except for ``outside_range`` where it is a two-element
    ``[low, high]`` list (fires when value < low or value > high).
    IMPORTANT: denominate the threshold in the native unit of the source the
    resolver will read -- raw units for a companyfacts concept (dollars, not
    millions), ledger units for a fact-ledger ``field_id``.
``unit``
    The unit the threshold is denominated in (documentation for humans and
    the resolver's outcome record; the resolver does not convert units).
``due``
    ISO date (YYYY-MM-DD) at which the spec matures and the resolver may
    score it.  May be null only when ``untestable`` is true.
``source_hint``
    Where the resolver finds the value: either a fact-ledger ``field_id``
    (e.g. ``cash_m``) resolved from the ticker's
    ``research/valuation_fact_ledger.json`` locked rows, or a companyfacts
    concept ``taxonomy:Concept`` (e.g. ``us-gaap:ShortTermInvestments``)
    resolved from ``research/evidence/sec_companyfacts.json`` at the latest
    observation on/after ``due``.  May be null only when ``untestable`` is
    true.
``derived_from``
    The prose falsifier this spec types (verbatim text from the contract's
    component ``falsifier`` field or ``monitoring.falsifiers``).  Keeping the
    link lets coverage distinguish typed from prose-only falsifiers.
``untestable``
    Explicitly marks a falsifier that cannot be scored from available data.
    The resolver skips it; it stays visible as coverage debt instead of
    silently rotting as prose.
``rationale``
    Why this threshold at this date falsifies the component's thesis.

Resolution outcomes are append-only in
``_system/research/falsifier_outcomes.jsonl`` (see ``resolve_falsifiers.py``).
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

SCHEMA_VERSION = "1.0"
COMPARATORS = {"lt", "lte", "gt", "gte", "outside_range"}
GRAPH_SOURCES = ROOT / "_system" / "graph" / "graph_sources.json"


def read_json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {} if default is None else default


def sidecar_path(ticker: str, root: Path = ROOT) -> Path:
    return root / ticker / "research" / "falsifier_specs.json"


def load_sidecar(ticker: str, root: Path = ROOT) -> dict:
    """Return the raw sidecar document, or {} when absent/unreadable."""
    return read_json(sidecar_path(ticker, root))


def parse_due(value) -> date | None:
    """Parse an ISO YYYY-MM-DD due date; None when missing or malformed."""
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def normalize_falsifier_text(text) -> str:
    """Lowercase and collapse whitespace for derived_from anchor matching."""
    return " ".join(str(text or "").lower().split())


def contract_component_ids(contract: dict) -> set[str]:
    """Valid anchor ids for a spec's component_id: the contract's
    economic_ownership_map component_ids plus the ``monitoring`` pseudo-id
    (for specs that type ``monitoring.falsifiers`` entries)."""
    ids = {"monitoring"}
    for component in (contract.get("economic_ownership_map") or []) if isinstance(contract, dict) else []:
        if isinstance(component, dict):
            cid = component.get("component_id")
            if isinstance(cid, str) and cid.strip():
                ids.add(cid.strip())
    return ids


def anchor_errors(spec: dict, contract: dict, index: int = 0) -> list[str]:
    """Cross-check a structurally valid spec against the contract it claims
    to type.  Returns ASCII error strings (empty = anchored).

    A spec whose ``component_id`` names no economic_ownership_map component
    (nor the ``monitoring`` pseudo-id), or whose ``derived_from`` matches no
    actual contract falsifier text (normalized substring match, either
    direction), is fabricated: it counts as ``unanchored``, never ``typed``.
    Without this check an invented spec -- phantom component, made-up
    threshold, derived_from matching nothing -- inflates typed coverage
    toward the enforcement threshold.
    """
    prefix = f"specs[{index}]"
    if not isinstance(spec, dict) or not isinstance(contract, dict):
        return [f"{prefix}: anchor check requires spec and contract objects"]
    errors = []
    component_id = str(spec.get("component_id") or "").strip()
    if component_id not in contract_component_ids(contract):
        errors.append(
            f"{prefix}.component_id: '{component_id}' matches no contract "
            "economic_ownership_map component_id (or 'monitoring')"
        )
    derived = normalize_falsifier_text(spec.get("derived_from"))
    texts = [normalize_falsifier_text(text) for text in prose_falsifiers(contract)]
    if not derived or not any(derived in text or text in derived for text in texts):
        errors.append(
            f"{prefix}.derived_from: matches no falsifier text in the contract "
            "(components or monitoring.falsifiers, normalized substring match)"
        )
    return errors


def spec_errors(spec, index: int = 0, contract: dict | None = None) -> list[str]:
    """Validate one spec; returns ASCII error strings (empty = valid).

    When ``contract`` is supplied the spec is also anchor-checked against it
    (see ``anchor_errors``): fabricated specs fail validation instead of
    passing as typed coverage.
    """
    prefix = f"specs[{index}]"
    if not isinstance(spec, dict):
        return [f"{prefix}: must be an object"]
    errors = []
    untestable = spec.get("untestable")
    if not isinstance(untestable, bool):
        errors.append(f"{prefix}.untestable: must be true or false")
        untestable = bool(untestable)
    for field in ("component_id", "metric", "derived_from", "rationale"):
        value = spec.get(field)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{prefix}.{field}: non-empty string required")
    comparator = spec.get("comparator")
    if comparator not in COMPARATORS:
        errors.append(f"{prefix}.comparator: must be one of {sorted(COMPARATORS)}")
    threshold = spec.get("threshold")
    if comparator == "outside_range":
        if not (isinstance(threshold, (list, tuple)) and len(threshold) == 2 and all(_is_number(v) for v in threshold)):
            errors.append(f"{prefix}.threshold: outside_range requires a [low, high] pair of numbers")
        elif threshold[0] > threshold[1]:
            errors.append(f"{prefix}.threshold: outside_range low must not exceed high")
    elif comparator in COMPARATORS and not _is_number(threshold):
        if not (untestable and threshold is None):
            errors.append(f"{prefix}.threshold: number required")
    unit = spec.get("unit")
    if not isinstance(unit, str) or not unit.strip():
        errors.append(f"{prefix}.unit: non-empty string required")
    due = spec.get("due")
    if due is None:
        if not untestable:
            errors.append(f"{prefix}.due: ISO date required for testable specs")
    elif parse_due(due) is None:
        errors.append(f"{prefix}.due: not a valid ISO date (YYYY-MM-DD)")
    source_hint = spec.get("source_hint")
    if source_hint is None:
        if not untestable:
            errors.append(f"{prefix}.source_hint: required for testable specs")
    elif not isinstance(source_hint, str) or not source_hint.strip():
        errors.append(f"{prefix}.source_hint: non-empty string or null required")
    if contract is not None:
        errors.extend(anchor_errors(spec, contract, index))
    return errors


def validate_sidecar(doc, ticker: str | None = None) -> list[str]:
    """Validate a whole sidecar document; returns ASCII error strings."""
    if not isinstance(doc, dict):
        return ["sidecar: must be a JSON object"]
    errors = []
    if not isinstance(doc.get("schema_version"), str):
        errors.append("schema_version: string required")
    doc_ticker = doc.get("ticker")
    if not isinstance(doc_ticker, str) or not doc_ticker.strip():
        errors.append("ticker: non-empty string required")
    elif ticker and doc_ticker.upper() != ticker.upper():
        errors.append(f"ticker: sidecar says {doc_ticker}, expected {ticker}")
    specs = doc.get("specs")
    if not isinstance(specs, list):
        errors.append("specs: list required")
        return errors
    for index, spec in enumerate(specs):
        errors.extend(spec_errors(spec, index))
    return errors


def ledger_locked_fields(ticker: str, root: Path = ROOT) -> set[str]:
    """field_ids of locked rows in the ticker's fact ledger."""
    ledger = read_json(root / ticker / "research" / "valuation_fact_ledger.json")
    return {
        str(fact.get("field_id"))
        for fact in ledger.get("facts") or []
        if isinstance(fact, dict) and fact.get("locked") and fact.get("field_id")
    }


def companyfacts_concepts(ticker: str, root: Path = ROOT) -> set[str]:
    """taxonomy:Concept keys available in the ticker's companyfacts evidence."""
    doc = read_json(root / ticker / "research" / "evidence" / "sec_companyfacts.json")
    concepts = set()
    for taxonomy, entries in (doc.get("facts") or {}).items():
        if isinstance(entries, dict):
            concepts.update(f"{taxonomy}:{concept}" for concept in entries)
    return concepts


def metric_resolvable(ticker: str, spec: dict, root: Path = ROOT) -> tuple[bool, str]:
    """Can the resolver actually find this spec's metric for this ticker?

    Checks the source_hint against the fact ledger's locked field_ids first
    (mirroring resolve order), then companyfacts concepts.  Untestable specs
    are trivially unresolvable by declaration.
    """
    if spec.get("untestable"):
        return False, "spec is marked untestable"
    hint = str(spec.get("source_hint") or "").strip()
    if not hint:
        return False, "source_hint is empty"
    if hint in ledger_locked_fields(ticker, root):
        return True, f"fact ledger locked field {hint}"
    if hint in companyfacts_concepts(ticker, root):
        return True, f"companyfacts concept {hint}"
    return False, f"{hint} not found in fact ledger locked fields or companyfacts concepts"


def enforcement_config(root: Path = ROOT) -> dict:
    """The falsifier_enforcement block of graph_sources.json ({} if absent)."""
    doc = read_json(root / "_system" / "graph" / "graph_sources.json")
    block = doc.get("falsifier_enforcement")
    return block if isinstance(block, dict) else {}


def prose_falsifiers(contract: dict) -> list[str]:
    """Distinct prose falsifier texts carried by a contract."""
    texts = set()
    for component in contract.get("economic_ownership_map") or []:
        if isinstance(component, dict):
            text = component.get("falsifier")
            if isinstance(text, str) and text.strip():
                texts.add(text.strip())
    for text in (contract.get("monitoring") or {}).get("falsifiers") or []:
        if isinstance(text, str) and text.strip():
            texts.add(text.strip())
    return sorted(texts)


def coverage_summary(ticker: str, contract: dict, root: Path = ROOT) -> dict:
    """Derived falsifier-coverage summary for a freshly built contract.

    The sidecar is the durable source; this summary is regenerated on every
    contract build and is NEVER a blocker: enforcement stays off until
    graph_sources.json falsifier_enforcement flips (see module docstring).
    Invalid specs never count as typed coverage -- a spec that cannot
    validate cannot claim to have typed anything.  Specs that validate but
    fail the contract anchor check (phantom component_id, derived_from
    matching no contract falsifier; see ``anchor_errors``) count as
    ``unanchored``, never ``typed`` -- fabricated specs must not inflate
    coverage toward the enforcement threshold.  Typed specs are additionally
    checked with ``metric_resolvable`` and reported as ``resolvable`` /
    ``unresolvable`` so coverage that the resolver cannot actually score is
    visible.
    """
    path = sidecar_path(ticker, root)
    doc = read_json(path)
    specs = doc.get("specs") if isinstance(doc.get("specs"), list) else []
    typed = untestable = invalid = unanchored = resolvable = unresolvable = 0
    typed_prose = set()
    for index, spec in enumerate(specs):
        if spec_errors(spec, index):
            invalid += 1
            continue
        if anchor_errors(spec, contract, index):
            unanchored += 1
            continue
        derived = str(spec.get("derived_from") or "").strip()
        if derived:
            typed_prose.add(derived)
        if spec.get("untestable"):
            untestable += 1
        else:
            typed += 1
            ok, _reason = metric_resolvable(ticker, spec, root)
            if ok:
                resolvable += 1
            else:
                unresolvable += 1
    normalized_typed = {normalize_falsifier_text(text) for text in typed_prose}
    prose_only = 0
    for text in prose_falsifiers(contract):
        norm = normalize_falsifier_text(text)
        if not any(norm in anchored or anchored in norm for anchored in normalized_typed):
            prose_only += 1
    return {
        "typed": typed,
        "prose_only": prose_only,
        "untestable": untestable,
        "invalid": invalid,
        "unanchored": unanchored,
        "resolvable": resolvable,
        "unresolvable": unresolvable,
        "spec_ref": f"{ticker}/research/falsifier_specs.json" if path.exists() else None,
        "enforcement_enabled": bool(enforcement_config(root).get("enforcement_enabled")),
    }

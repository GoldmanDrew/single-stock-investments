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

Book-wide coverage remains a report-only ratchet while ``enforcement_enabled``
is false. ``prospective_enforcement_enabled`` separately requires an anchored
v2 record for components introduced or materially changed after its cutover.

Sidecar format
--------------
::

    {
      "schema_version": "2.0",
      "ticker": "AXTI",
      "specs": [
        {
          "spec_id": "axti-cash-floor-2026q4",
          "spec_revision": 1,
          "authored_at": "2026-08-12T12:00:00Z",
          "analysis_run_id": "axti-refresh-2026-08-12",
          "contract_hash": "<sha256>",
          "method_id": "sum_of_parts",
          "power_zone": "asset_backed_optionality",
          "component_id": "cash_and_liquidity",
          "metric": "cash_and_short_term_investments",
          "comparator": "lt",
          "threshold": 400000000,
          "unit": "USD",
          "measurement_period_end": "2026-09-30",
          "observable_after": "2026-11-15",
          "resolution_deadline": "2026-12-31",
          "source_hint": "us-gaap:CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
          "probability_fires": 0.25,
          "severity": 4,
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
``measurement_period_end`` / ``observable_after`` / ``resolution_deadline``
    The economic period tested, first expected evidence date, and terminal
    deadline. Missing evidence between the latter two is retryable.
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

import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

SCHEMA_VERSION = "3.0"
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


def active_specs(specs: list[dict]) -> list[dict]:
    """Return the current immutable revision of each non-superseded forecast.

    History remains in the sidecar for audit. Runtime coverage and resolution
    operate only on the latest revision, otherwise an explicitly repaired
    untestable forecast would remain permanent coverage debt and could be
    scored alongside its replacement.
    """
    rows = [row for row in specs if isinstance(row, dict)]
    legacy_rows = [row for row in rows if not row.get("spec_id")]
    latest_by_id: dict[str, dict] = {}
    order: dict[int, int] = {id(row): index for index, row in enumerate(rows)}
    for row in rows:
        spec_id = str(row.get("spec_id") or "")
        if not spec_id:
            continue
        current = latest_by_id.get(spec_id)
        if current is None or int(row.get("spec_revision") or 1) > int(
            current.get("spec_revision") or 1
        ):
            latest_by_id[spec_id] = row
    superseded_ids = {
        str(row.get("supersedes_spec_id"))
        for row in latest_by_id.values()
        if row.get("supersedes_spec_id")
        and str(row.get("supersedes_spec_id")) != str(row.get("spec_id"))
    }
    active = legacy_rows + [
        row for spec_id, row in latest_by_id.items() if spec_id not in superseded_ids
    ]
    return sorted(active, key=lambda row: order[id(row)])


def parse_due(value) -> date | None:
    """Parse an ISO YYYY-MM-DD due date; None when missing or malformed."""
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def is_v2_spec(spec: dict) -> bool:
    """V2 forecasts are immutable, attributable records with explicit ids."""
    return isinstance(spec, dict) and bool(spec.get("spec_id"))


def is_v3_spec(spec: dict) -> bool:
    """True only for the prospective, fail-closed forecast contract.

    V2 records remain readable for diagnostic resolution, but never become
    calibration eligible merely because fields were later added to them.
    """
    return (isinstance(spec, dict)
            and str(spec.get("spec_schema_version") or "") == "3.0")


def parse_datetime(value) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def calibration_eligibility(spec: dict) -> tuple[bool, str]:
    """Derive eligibility; never trust a mutable boolean by itself."""
    if not is_v3_spec(spec):
        return False, "legacy_or_non_v3"
    if spec.get("untestable"):
        return False, "untestable"
    if spec.get("calibration_eligible") is not True:
        return False, "not_declared_eligible"
    if spec.get("forecast_class") != "ex_ante":
        return False, "not_ex_ante"
    if spec.get("forecast_role") != "primary":
        return False, "not_primary"
    probability = spec.get("probability_fires")
    if not _is_number(probability) or not 0 <= float(probability) <= 1:
        return False, "probability_missing_or_invalid"
    cutoff = parse_datetime(spec.get("information_cutoff_at"))
    registered = parse_datetime(spec.get("registered_at"))
    if cutoff is None or registered is None:
        return False, "temporal_provenance_missing"
    if cutoff > registered:
        return False, "information_cutoff_after_registration"
    observable = parse_due(spec.get("observable_after"))
    if observable is None:
        return False, "observable_after_missing"
    observable_at = datetime.combine(observable, datetime.min.time(), tzinfo=timezone.utc)
    if registered >= observable_at:
        return False, "registered_after_observability"
    if not str(spec.get("registration_commit") or "").strip():
        return False, "registration_commit_missing"
    plan = spec.get("observation_plan") or {}
    replay = plan.get("historical_replay") or {}
    if replay.get("status") != "passed" or not replay.get("evidence_ref"):
        return False, "historical_replay_not_passed"
    if plan.get("outcome_unavailable_at_registration") is not True:
        return False, "anti_lookahead_proof_missing"
    review = spec.get("review") or {}
    if (review.get("status") != "approved"
            or not review.get("reviewer")
            or review.get("reviewer") == spec.get("author")):
        return False, "independent_review_missing"
    return True, "eligible"


def forecast_dates(spec: dict) -> tuple[date | None, date | None, date | None]:
    """Return (measurement period end, observable after, terminal deadline).

    V1 compatibility treats ``due`` as all three concepts with the historical
    14-day grace added by callers. New writes must use the explicit V2 fields.
    """
    if is_v2_spec(spec):
        return (
            parse_due(spec.get("measurement_period_end")),
            parse_due(spec.get("observable_after")),
            parse_due(spec.get("resolution_deadline")),
        )
    due = parse_due(spec.get("due"))
    return due, due, None


def spec_payload_hash(spec: dict) -> str:
    """Hash the immutable forecast payload; outcomes pin this exact version."""
    raw = json.dumps(spec, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


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
    if is_v2_spec(spec):
        for field in ("spec_id", "analysis_run_id", "author", "model_id",
                      "prompt_version", "method_id", "power_zone"):
            value = spec.get(field)
            if not isinstance(value, str) or not value.strip():
                errors.append(f"{prefix}.{field}: non-empty string required")
        revision = spec.get("spec_revision")
        if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
            errors.append(f"{prefix}.spec_revision: positive integer required")
        authored = spec.get("authored_at")
        try:
            datetime.fromisoformat(str(authored).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            errors.append(f"{prefix}.authored_at: ISO datetime required")
        contract_hash = spec.get("contract_hash")
        if not isinstance(contract_hash, str) or len(contract_hash) != 64 \
                or any(ch not in "0123456789abcdefABCDEF" for ch in contract_hash):
            errors.append(f"{prefix}.contract_hash: 64-character hex sha256 required")
        probability = spec.get("probability_fires")
        if untestable:
            if probability is not None:
                errors.append(f"{prefix}.probability_fires: null required when untestable")
        elif probability is None and spec.get("calibration_eligible") is False:
            pass  # honest migration: historical forecasts lacked ex-ante odds
        elif not _is_number(probability) or not 0 <= float(probability) <= 1:
            errors.append(f"{prefix}.probability_fires: number from 0 to 1 required")
        severity = spec.get("severity")
        if not isinstance(severity, int) or isinstance(severity, bool) or not 1 <= severity <= 5:
            errors.append(f"{prefix}.severity: integer from 1 to 5 required")
        measurement, observable, deadline = forecast_dates(spec)
        for field, parsed in (
            ("measurement_period_end", measurement),
            ("observable_after", observable),
            ("resolution_deadline", deadline),
        ):
            raw = spec.get(field)
            if raw is None and untestable:
                continue
            if parsed is None:
                errors.append(f"{prefix}.{field}: ISO date required for testable specs")
        if measurement and observable and measurement > observable:
            errors.append(f"{prefix}: measurement_period_end must not follow observable_after")
        if observable and deadline and observable > deadline:
            errors.append(f"{prefix}: observable_after must not follow resolution_deadline")
        supersedes = spec.get("supersedes_spec_id")
        if supersedes is not None and (not isinstance(supersedes, str) or not supersedes.strip()):
            errors.append(f"{prefix}.supersedes_spec_id: non-empty string or null required")
        if not is_v3_spec(spec) and spec.get("calibration_eligible") is True:
            errors.append(
                f"{prefix}.calibration_eligible: only immutable v3 ex-ante specs may be eligible")
        if is_v3_spec(spec):
            for field in ("forecast_class", "forecast_role", "information_cutoff_at",
                          "registered_at", "registration_commit", "component_fingerprint",
                          "correlation_group"):
                value = spec.get(field)
                if not isinstance(value, str) or not value.strip():
                    errors.append(f"{prefix}.{field}: non-empty string required for v3")
            for field in ("information_cutoff_at", "registered_at"):
                if parse_datetime(spec.get(field)) is None:
                    errors.append(f"{prefix}.{field}: timezone-aware ISO datetime required")
            plan = spec.get("observation_plan")
            if not isinstance(plan, dict):
                errors.append(f"{prefix}.observation_plan: object required for v3")
                plan = {}
            for field in ("metric_definition_id", "metric_definition_version",
                          "source_adapter", "fiscal_period", "observation_type",
                          "duration_basis", "canonical_unit", "expected_publication_date"):
                value = plan.get(field)
                if not isinstance(value, str) or not value.strip():
                    errors.append(f"{prefix}.observation_plan.{field}: non-empty string required")
            forms = plan.get("accepted_forms")
            if not isinstance(forms, list) or not forms or not all(
                    isinstance(value, str) and value.strip() for value in forms):
                errors.append(f"{prefix}.observation_plan.accepted_forms: non-empty string list required")
            lag = plan.get("maximum_source_lag_days")
            if not isinstance(lag, int) or isinstance(lag, bool) or lag < 0:
                errors.append(f"{prefix}.observation_plan.maximum_source_lag_days: non-negative integer required")
            if parse_due(plan.get("expected_publication_date")) is None:
                errors.append(f"{prefix}.observation_plan.expected_publication_date: ISO date required")
            if plan.get("canonical_unit") and plan.get("canonical_unit") != spec.get("unit"):
                errors.append(f"{prefix}.observation_plan.canonical_unit: must equal spec unit")
            replay = plan.get("historical_replay")
            if not isinstance(replay, dict) or replay.get("status") != "passed" or not replay.get("evidence_ref"):
                errors.append(f"{prefix}.observation_plan.historical_replay: passed replay with evidence_ref required")
            threshold_basis = spec.get("threshold_basis")
            if not isinstance(threshold_basis, dict):
                errors.append(f"{prefix}.threshold_basis: object required for v3")
            else:
                for field in ("source_ref", "rule"):
                    if not str(threshold_basis.get(field) or "").strip():
                        errors.append(f"{prefix}.threshold_basis.{field}: required")
            if untestable:
                for field in ("untestable_reason_code", "required_adapter", "review_by"):
                    if not str(spec.get(field) or "").strip():
                        errors.append(f"{prefix}.{field}: required for v3 untestable disposition")
            elif spec.get("calibration_eligible") is True:
                eligible, reason = calibration_eligibility(spec)
                if not eligible:
                    errors.append(f"{prefix}.calibration_eligible: derived eligibility failed ({reason})")
                component_impact = spec.get("component_value_impact_pct")
                equity_impact = spec.get("total_equity_value_impact_pct")
                if not _is_number(component_impact) or not _is_number(equity_impact):
                    errors.append(f"{prefix}: numeric economic impact fields required")
                elif float(component_impact) < 10.0 and float(equity_impact) < 2.0:
                    errors.append(f"{prefix}: primary eligible threshold is not economically material")
    else:
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
    seen_identities = set()
    for index, spec in enumerate(specs):
        errors.extend(spec_errors(spec, index))
        spec_id = spec.get("spec_id") if isinstance(spec, dict) else None
        if spec_id:
            identity = (str(spec_id), int(spec.get("spec_revision") or 1))
            if identity in seen_identities:
                errors.append(
                    f"specs[{index}]: duplicate immutable identity {identity[0]} revision {identity[1]}"
                )
            seen_identities.add(identity)
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
    if is_v3_spec(spec):
        from falsifier_evidence_adapters import preflight_spec
        result = preflight_spec(ticker, spec, root)
        return bool(result.get("ok")), str(result.get("reason") or "preflight failed")
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
    specs = active_specs(doc.get("specs") if isinstance(doc.get("specs"), list) else [])
    typed = untestable = invalid = unanchored = resolvable = unresolvable = 0
    eligible = diagnostic = 0
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
            if calibration_eligibility(spec)[0]:
                eligible += 1
            else:
                diagnostic += 1
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
        "calibration_eligible": eligible,
        "diagnostic_only": diagnostic,
        "spec_ref": f"{ticker}/research/falsifier_specs.json" if path.exists() else None,
        "enforcement_enabled": bool(enforcement_config(root).get("enforcement_enabled")),
    }

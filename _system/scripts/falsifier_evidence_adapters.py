#!/usr/bin/env python3
"""Period-aware evidence adapters for prospective falsifier resolution.

Adapters return normalized observations with provenance or a typed blocker.
They never alter a forecast, threshold, probability, or contract.
"""
from __future__ import annotations

import json
import hashlib
from datetime import date
from pathlib import Path

from falsifier_specs import forecast_dates, is_v3_spec, parse_due, read_json

ROOT = Path(__file__).resolve().parents[2]
DEFINITIONS_REL = Path("_system/research/metric_definitions.json")
ISSUER_ADAPTERS_REL = Path("_system/research/issuer_kpi_adapters.json")
BASE_SUPPORTED_ADAPTERS = {"fact_ledger", "sec_companyfacts", "sec_companyfacts_ttm"}


def metric_definitions(root: Path = ROOT) -> dict:
    return (read_json(root / DEFINITIONS_REL).get("definitions") or {})


def issuer_adapters(root: Path = ROOT) -> dict:
    return (read_json(root / ISSUER_ADAPTERS_REL).get("adapters") or {})


def _definition_hash(value: dict) -> str:
    payload = {key: item for key, item in value.items() if key != "definition_hash"}
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _issuer_adapter_variant(ticker: str, adapter: str, root: Path) -> dict | None:
    entry = issuer_adapters(root).get(adapter) or {}
    variant = (entry.get("variants") or {}).get(ticker.upper())
    return variant if isinstance(variant, dict) else None


def _empty(reason: str, adapter: str | None = None, **details) -> dict:
    return {
        "value": None,
        "unit": None,
        "as_of": None,
        "evidence_ref": None,
        "adapter": adapter,
        "blocker_reason": reason,
        "details": details,
    }


def _evidence_path_exists(root: Path, reference: str) -> bool:
    path_text = str(reference or "").split("#", 1)[0].split("@", 1)[0]
    if path_text.startswith("fixture:"):
        return True
    path = Path(path_text)
    if not path.is_absolute():
        path = root / path
    return path.exists()


def preflight_spec(ticker: str, spec: dict, root: Path = ROOT) -> dict:
    """Prove the exact observation plan has a versioned recipe and replay."""
    if not is_v3_spec(spec):
        return {"ok": False, "reason": "legacy spec has no v3 observation plan"}
    plan = spec.get("observation_plan") or {}
    definition_id = str(plan.get("metric_definition_id") or "")
    definition = metric_definitions(root).get(definition_id)
    if not isinstance(definition, dict):
        return {"ok": False, "reason": f"metric_definition_missing:{definition_id}"}
    if str(plan.get("metric_definition_version") or "") != str(definition.get("version") or ""):
        return {"ok": False, "reason": "metric_definition_version_mismatch"}
    adapter = str(plan.get("source_adapter") or "")
    supported = BASE_SUPPORTED_ADAPTERS | set(issuer_adapters(root))
    if adapter not in supported:
        return {"ok": False, "reason": f"adapter_missing:{adapter}"}
    if adapter not in set(definition.get("source_adapters") or []) and not (
            adapter == "fact_ledger" and spec.get("source_hint")):
        return {"ok": False, "reason": "adapter_not_allowed_by_metric_definition"}
    if plan.get("canonical_unit") != spec.get("unit"):
        return {"ok": False, "reason": "unit_mismatch"}
    if adapter not in BASE_SUPPORTED_ADAPTERS:
        variant = _issuer_adapter_variant(ticker, adapter, root)
        if not variant:
            return {"ok": False, "reason": "issuer_adapter_ticker_mismatch"}
        if plan.get("adapter_definition_hash") != variant.get("definition_hash"):
            return {"ok": False, "reason": "issuer_adapter_definition_hash_mismatch"}
        if _definition_hash(variant) != variant.get("definition_hash"):
            return {"ok": False, "reason": "issuer_adapter_definition_changed"}
    expected = parse_due(plan.get("expected_publication_date"))
    _measurement, _observable, deadline = forecast_dates(spec)
    if expected is None or deadline is None or expected > deadline:
        return {"ok": False, "reason": "deadline_not_feasible"}
    replay = plan.get("historical_replay") or {}
    if replay.get("status") != "passed" or not _evidence_path_exists(
            root, str(replay.get("evidence_ref") or "")):
        return {"ok": False, "reason": "historical_replay_missing"}
    return {
        "ok": True,
        "reason": "source_preflight_passed",
        "metric_definition_id": definition_id,
        "adapter": adapter,
    }


def _concept_rows(doc: dict, concept_key: str) -> list[dict]:
    if ":" not in concept_key:
        return []
    taxonomy, concept = concept_key.split(":", 1)
    entry = ((doc.get("facts") or {}).get(taxonomy) or {}).get(concept) or {}
    rows = []
    for unit, observations in (entry.get("units") or {}).items():
        for observation in observations or []:
            if isinstance(observation, dict):
                rows.append({**observation, "_unit": unit, "_concept": concept_key})
    return rows


def _date_distance(left: str, right: str) -> int | None:
    try:
        return abs((date.fromisoformat(left[:10]) - date.fromisoformat(right[:10])).days)
    except (TypeError, ValueError):
        return None


def _eligible_row(row: dict, plan: dict, target: date, today: date,
                  canonical_unit: str) -> tuple[bool, str]:
    if row.get("_unit") != canonical_unit:
        return False, "unit_mismatch"
    if not isinstance(row.get("val"), (int, float)) or isinstance(row.get("val"), bool):
        return False, "non_numeric"
    filed = parse_due(row.get("filed"))
    if filed and filed > today:
        return False, "filed_after_as_of"
    accepted_forms = set(plan.get("accepted_forms") or [])
    if accepted_forms and row.get("form") not in accepted_forms:
        return False, "form_mismatch"
    fiscal_period = str(plan.get("fiscal_period") or "").upper()
    if fiscal_period not in {"ANY", "EVENT"} and str(row.get("fp") or "").upper() != fiscal_period:
        return False, "fiscal_period_mismatch"
    fiscal_year = plan.get("fiscal_year")
    if fiscal_year is not None and str(row.get("fy") or "") != str(fiscal_year):
        return False, "fiscal_year_mismatch"
    observation_type = str(plan.get("observation_type") or "")
    if observation_type == "duration" and not row.get("start"):
        return False, "duration_missing_start"
    tolerance = int(plan.get("end_date_tolerance_days") or 7)
    distance = _date_distance(str(row.get("end") or ""), target.isoformat())
    if distance is None or distance > tolerance:
        return False, "period_end_mismatch"
    return True, "eligible"


def _resolve_companyfacts(ticker: str, spec: dict, root: Path, today: date,
                          definition: dict, plan: dict) -> dict:
    doc = read_json(root / ticker / "research/evidence/sec_companyfacts.json")
    measurement, _observable, _deadline = forecast_dates(spec)
    if measurement is None:
        return _empty("measurement_period_missing", "sec_companyfacts")
    concepts = []
    hint = str(spec.get("source_hint") or "")
    if ":" in hint:
        concepts.append(hint)
    concepts.extend(value for value in definition.get("concepts") or [] if value not in concepts)
    reasons: dict[str, int] = {}
    candidates = []
    for concept in concepts:
        for row in _concept_rows(doc, concept):
            ok, reason = _eligible_row(row, plan, measurement, today, str(spec.get("unit")))
            if ok:
                candidates.append(row)
            else:
                reasons[reason] = reasons.get(reason, 0) + 1
    if not candidates:
        reason = max(reasons, key=reasons.get) if reasons else "concept_absent"
        return _empty(reason, "sec_companyfacts", concepts=concepts, rejected=reasons)
    row = max(candidates, key=lambda item: (str(item.get("filed") or ""), str(item.get("end") or "")))
    ref = (f"{ticker}/research/evidence/sec_companyfacts.json#"
           f"{row['_concept']}@{row.get('end')}@{row.get('filed') or 'unfiled'}")
    return {
        "value": row["val"],
        "unit": row["_unit"],
        "as_of": row.get("end"),
        "evidence_ref": ref,
        "adapter": "sec_companyfacts",
        "blocker_reason": None,
        "raw_observation": {key: row.get(key) for key in
                            ("start", "end", "fy", "fp", "form", "filed", "accn", "frame")},
    }


def _duration_rows(doc: dict, concepts: list[str], unit: str, today: date) -> list[dict]:
    rows = []
    for concept in concepts:
        for row in _concept_rows(doc, concept):
            filed = parse_due(row.get("filed"))
            if (row.get("_unit") == unit and row.get("start") and row.get("end")
                    and isinstance(row.get("val"), (int, float))
                    and not isinstance(row.get("val"), bool)
                    and (filed is None or filed <= today)
                    and row.get("form") in {"10-Q", "10-K"}):
                rows.append(row)
    return rows


def _select_ttm_triplet(rows: list[dict], target: date, fiscal_period: str,
                        tolerance: int) -> tuple[dict, dict, dict] | None:
    current = []
    for row in rows:
        distance = _date_distance(str(row.get("end")), target.isoformat())
        if (str(row.get("fp") or "").upper() == fiscal_period
                and distance is not None and distance <= tolerance):
            current.append(row)
    if not current:
        return None
    current_ytd = max(current, key=lambda row: str(row.get("filed") or ""))
    current_end = date.fromisoformat(str(current_ytd["end"])[:10])
    previous_comparable = [row for row in rows
                           if str(row.get("fp") or "").upper() == fiscal_period
                           and 300 <= (current_end - date.fromisoformat(str(row["end"])[:10])).days <= 430]
    if not previous_comparable:
        return None
    prior_ytd = max(previous_comparable, key=lambda row: str(row.get("end") or ""))
    prior_end = date.fromisoformat(str(prior_ytd["end"])[:10])
    prior_fy = [row for row in rows
                if str(row.get("fp") or "").upper() == "FY"
                and prior_end < date.fromisoformat(str(row["end"])[:10]) < current_end]
    if not prior_fy:
        return None
    previous_fy = max(prior_fy, key=lambda row: str(row.get("end") or ""))
    return current_ytd, previous_fy, prior_ytd


def _resolve_owner_earnings_ttm(ticker: str, spec: dict, root: Path, today: date,
                                definition: dict, plan: dict) -> dict:
    doc = read_json(root / ticker / "research/evidence/sec_companyfacts.json")
    measurement, _observable, _deadline = forecast_dates(spec)
    if measurement is None:
        return _empty("measurement_period_missing", "sec_companyfacts_ttm")
    source_unit = str(plan.get("source_unit") or "USD")
    ocf_rows = _duration_rows(doc, list(definition.get("operating_cash_flow_concepts") or []), source_unit, today)
    capex_rows = _duration_rows(doc, list(definition.get("capital_expenditure_concepts") or []), source_unit, today)
    fiscal_period = str(plan.get("fiscal_period") or "").upper()
    tolerance = int(plan.get("end_date_tolerance_days") or 7)
    ocf = _select_ttm_triplet(ocf_rows, measurement, fiscal_period, tolerance)
    capex = _select_ttm_triplet(capex_rows, measurement, fiscal_period, tolerance)
    if not ocf or not capex:
        return _empty("ttm_period_inputs_missing", "sec_companyfacts_ttm",
                      ocf_rows=len(ocf_rows), capex_rows=len(capex_rows), fiscal_period=fiscal_period)
    ocf_ttm = float(ocf[1]["val"]) + float(ocf[0]["val"]) - float(ocf[2]["val"])
    capex_ttm = float(capex[1]["val"]) + float(capex[0]["val"]) - float(capex[2]["val"])
    value = (ocf_ttm - abs(capex_ttm)) / 1_000_000.0
    inputs = []
    for label, triplet in (("ocf", ocf), ("capex", capex)):
        for role, row in zip(("current_ytd", "prior_fy", "prior_comparable_ytd"), triplet):
            inputs.append({
                "kind": label,
                "role": role,
                "concept": row.get("_concept"),
                "value": row.get("val"),
                "unit": row.get("_unit"),
                "start": row.get("start"),
                "end": row.get("end"),
                "fy": row.get("fy"),
                "fp": row.get("fp"),
                "form": row.get("form"),
                "filed": row.get("filed"),
                "accn": row.get("accn"),
            })
    return {
        "value": round(value, 6),
        "unit": "USD millions",
        "as_of": ocf[0].get("end"),
        "evidence_ref": f"{ticker}/research/evidence/sec_companyfacts.json#normalized_owner_earnings_ttm_m@{ocf[0].get('end')}",
        "adapter": "sec_companyfacts_ttm",
        "blocker_reason": None,
        "formula_inputs": inputs,
    }


def _resolve_ledger(ticker: str, spec: dict, root: Path, today: date,
                    plan: dict) -> dict:
    ledger = read_json(root / ticker / "research/valuation_fact_ledger.json")
    measurement, _observable, _deadline = forecast_dates(spec)
    if measurement is None:
        return _empty("measurement_period_missing", "fact_ledger")
    hint = str(spec.get("source_hint") or "")
    reasons: dict[str, int] = {}
    candidates = []
    for fact in ledger.get("facts") or []:
        if not isinstance(fact, dict) or not fact.get("locked") or fact.get("field_id") != hint:
            continue
        if fact.get("unit") != spec.get("unit"):
            reasons["unit_mismatch"] = reasons.get("unit_mismatch", 0) + 1
            continue
        source = fact.get("source") or {}
        filed = parse_due(source.get("filed"))
        if filed and filed > today:
            reasons["filed_after_as_of"] = reasons.get("filed_after_as_of", 0) + 1
            continue
        fiscal_period = str(plan.get("fiscal_period") or "").upper()
        actual_period = str(source.get("fiscal_period") or source.get("fp") or "").upper()
        if fiscal_period not in {"ANY", "EVENT"} and actual_period != fiscal_period:
            reasons["fiscal_period_mismatch"] = reasons.get("fiscal_period_mismatch", 0) + 1
            continue
        tolerance = int(plan.get("end_date_tolerance_days") or 7)
        distance = _date_distance(str(source.get("as_of") or ""), measurement.isoformat())
        if distance is None or distance > tolerance:
            reasons["period_end_mismatch"] = reasons.get("period_end_mismatch", 0) + 1
            continue
        candidates.append(fact)
    if not candidates:
        reason = max(reasons, key=reasons.get) if reasons else "field_absent"
        return _empty(reason, "fact_ledger", field_id=hint, rejected=reasons)
    fact = max(candidates, key=lambda row: str((row.get("source") or {}).get("filed") or ""))
    source = fact.get("source") or {}
    return {
        "value": fact.get("value"),
        "unit": fact.get("unit"),
        "as_of": source.get("as_of"),
        "evidence_ref": f"{ticker}/research/valuation_fact_ledger.json#{hint}",
        "adapter": "fact_ledger",
        "blocker_reason": None,
        "raw_observation": source,
    }


def _resolve_issuer_bridge(ticker: str, spec: dict, root: Path, today: date,
                           adapter: str, plan: dict) -> dict:
    """Normalize one issuer's cash bridge to a 100% registered low-case floor.

    The adapter definition freezes the exact underlying metric, source recipe,
    and floor. Named causal drivers remain visible in the definition, while the
    scored observation is a reproducible financial outcome rather than an
    unscorable prose composite.
    """
    variant = _issuer_adapter_variant(ticker, adapter, root)
    if not variant:
        return _empty("issuer_adapter_ticker_mismatch", adapter)
    floor = variant.get("bridge_floor")
    if not isinstance(floor, (int, float)) or isinstance(floor, bool) or floor == 0:
        return _empty("issuer_adapter_floor_invalid", adapter)
    underlying_plan = dict(variant.get("underlying_observation_plan") or {})
    underlying_spec = {
        **spec,
        "unit": variant.get("underlying_unit"),
        "source_hint": variant.get("underlying_source_hint"),
        "observation_plan": underlying_plan,
    }
    underlying_adapter = str(underlying_plan.get("source_adapter") or "")
    definition = metric_definitions(root).get(
        str(underlying_plan.get("metric_definition_id") or "")
    ) or {}
    if underlying_adapter == "fact_ledger":
        result = _resolve_ledger(ticker, underlying_spec, root, today, underlying_plan)
    elif underlying_adapter == "sec_companyfacts_ttm":
        result = _resolve_owner_earnings_ttm(
            ticker, underlying_spec, root, today, definition, underlying_plan
        )
    elif underlying_adapter == "sec_companyfacts":
        result = _resolve_companyfacts(
            ticker, underlying_spec, root, today, definition, underlying_plan
        )
    else:
        return _empty("issuer_adapter_underlying_source_unsupported", adapter)
    if result.get("value") is None:
        return {
            **result,
            "adapter": adapter,
            "details": {
                **(result.get("details") or {}),
                "underlying_adapter": underlying_adapter,
                "driver_metric": variant.get("driver_metric"),
            },
        }
    observed = float(result["value"])
    return {
        "value": round(observed / float(floor) * 100.0, 6),
        "unit": "percent",
        "as_of": result.get("as_of"),
        "evidence_ref": result.get("evidence_ref"),
        "adapter": adapter,
        "blocker_reason": None,
        "formula": "observed issuer owner-cash bridge / registered low-case floor * 100",
        "formula_inputs": {
            "observed_value": observed,
            "observed_unit": result.get("unit"),
            "registered_floor": floor,
            "driver_metric": variant.get("driver_metric"),
            "underlying_adapter": underlying_adapter,
        },
        "raw_observation": result.get("raw_observation") or result.get("formula_inputs"),
    }


def resolve_spec(ticker: str, spec: dict, root: Path, today: date) -> dict:
    """Resolve a v3 spec through its frozen adapter plan."""
    check = preflight_spec(ticker, spec, root)
    if not check.get("ok"):
        return _empty(str(check.get("reason")), str((spec.get("observation_plan") or {}).get("source_adapter") or ""))
    plan = spec["observation_plan"]
    definition = metric_definitions(root)[plan["metric_definition_id"]]
    adapter = plan["source_adapter"]
    if adapter not in BASE_SUPPORTED_ADAPTERS:
        return _resolve_issuer_bridge(ticker, spec, root, today, adapter, plan)
    if adapter == "fact_ledger":
        return _resolve_ledger(ticker, spec, root, today, plan)
    if adapter == "sec_companyfacts_ttm":
        return _resolve_owner_earnings_ttm(ticker, spec, root, today, definition, plan)
    return _resolve_companyfacts(ticker, spec, root, today, definition, plan)


def resolve_legacy_spec(ticker: str, spec: dict, root: Path, today: date) -> dict:
    """Resolve migrated diagnostics with v3 period semantics, never eligibility.

    Migration froze no probability or observation plan, so these rows remain
    diagnostic. The mapping only repairs evidence selection: it cannot turn a
    retrospective record into an ex-ante calibration observation.
    """
    measurement, observable, deadline = forecast_dates(spec)
    if measurement is None:
        return _empty("measurement_period_missing", "legacy_diagnostic")
    hint = str(spec.get("source_hint") or "")
    month_to_period = {3: "Q1", 6: "Q2", 9: "Q3", 12: "FY"}
    fiscal_period = month_to_period.get(measurement.month, "ANY")
    common = {
        "fiscal_period": fiscal_period,
        "fiscal_year": measurement.year,
        "end_date_tolerance_days": 7,
        "expected_publication_date": (observable or measurement).isoformat(),
    }
    if hint == "normalized_owner_earnings_m":
        definition = metric_definitions(root).get("normalized_owner_earnings_ttm_m") or {}
        plan = {**common, "source_adapter": "sec_companyfacts_ttm",
                "source_unit": "USD", "observation_type": "duration"}
        result = _resolve_owner_earnings_ttm(ticker, spec, root, today, definition, plan)
        result["adapter"] = "legacy_diagnostic_sec_companyfacts_ttm"
        return result
    concept = None
    if hint == "cash_m":
        definition = metric_definitions(root).get("cash_and_equivalents_usd") or {}
        concepts = definition.get("concepts") or []
        concept = concepts[0] if concepts else None
        observation_type = "instant"
    elif hint == "operating_cash_flow_m":
        concept = "us-gaap:NetCashProvidedByUsedInOperatingActivities"
        observation_type = "duration"
        # AEHR's May year-end is an FY observation, not calendar Q2.
        fiscal_period = "FY"
    elif ":" in hint:
        concept = hint
        observation_type = "instant"
    if concept:
        source_spec = {**spec, "source_hint": concept, "unit": "USD"}
        definition = {"concepts": [concept]}
        plan = {**common, "fiscal_period": fiscal_period,
                "accepted_forms": ["10-Q", "10-K"],
                "observation_type": observation_type}
        result = _resolve_companyfacts(ticker, source_spec, root, today, definition, plan)
        if result.get("value") is not None and spec.get("unit") == "USD millions":
            result["value"] = float(result["value"]) / 1_000_000.0
            result["unit"] = "USD millions"
        result["adapter"] = "legacy_diagnostic_sec_companyfacts"
        return result
    plan = {**common, "fiscal_period": "ANY"}
    result = _resolve_ledger(ticker, spec, root, today, plan)
    result["adapter"] = "legacy_diagnostic_fact_ledger"
    return result

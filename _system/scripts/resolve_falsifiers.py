#!/usr/bin/env python3
"""Score matured typed falsifiers into outcomes and descriptive calibration.

The epistemic ratchet's resolver (spec: _system/graph/README.md).  Scans every
ticker sidecar ({TICKER}/research/falsifier_specs.json) for specs whose
``observable_after`` date has passed, are not marked untestable, and have no
recorded outcome for the immutable spec revision;
resolves the metric from the fact ledger or companyfacts; compares it against
the threshold; and appends an outcome row to the append-only ledger

    _system/research/falsifier_outcomes.jsonl

Outcome rows: {ticker, component_id, spec, resolved_value, resolved_unit,
resolved_as_of, verdict: hit|miss|unresolvable, evidence_ref, resolved_on,
method_id, power_zone}.  "hit" means the falsifier FIRED (the thesis failed
the test); "miss" means the thesis survived. Dedupe is
(ticker, spec_id, revision, payload_hash); legacy v1 rows retain their
historical composite key. Threshold/unit/source changes therefore cannot
silently inherit an old outcome.

After appending, the calibration store

    _system/research/falsifier_calibration.json

is rebuilt from the full ledger: descriptive hit/miss/unresolvable counts
bucketed by method_id x power_zone.  Calibration is descriptive only --
weights never change automatically (same rule as committee_calibration);
it informs humans and prompts, never sizing.

Default is a dry run; pass --apply to write.  Output is ASCII-only (Windows
cp1252 console).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "_system" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from falsifier_specs import (  # noqa: E402
    anchor_errors,
    calibration_eligibility,
    forecast_dates,
    is_v2_spec,
    is_v3_spec,
    parse_due,
    read_json,
    spec_errors,
    spec_payload_hash,
)
from falsifier_evidence_adapters import resolve_legacy_spec, resolve_spec  # noqa: E402

OUTCOMES_REL = Path("_system") / "research" / "falsifier_outcomes.jsonl"
CALIBRATION_REL = Path("_system") / "research" / "falsifier_calibration.json"
ATTEMPTS_REL = Path("_system") / "research" / "falsifier_evidence_attempts.jsonl"
STATE_EVENTS_REL = Path("_system") / "research" / "falsifier_state_events.jsonl"
CALIBRATION_WARNING = (
    "Calibration is descriptive; buckets inform humans and prompts, never "
    "position sizing; weights never change automatically."
)


def find_sidecars(root: Path) -> list[tuple[str, Path]]:
    """(ticker, sidecar_path) pairs for every top-level ticker directory."""
    found = []
    for entry in sorted(root.iterdir()):
        if not entry.is_dir() or entry.name.startswith(("_", ".")):
            continue
        path = entry / "research" / "falsifier_specs.json"
        if path.exists():
            found.append((entry.name, path))
    return found


def load_outcomes(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def append_unique_jsonl(path: Path, rows: list[dict], key_fields: tuple[str, ...]) -> int:
    existing = load_outcomes(path)
    seen = {tuple(row.get(field) for field in key_fields) for row in existing}
    fresh = [row for row in rows
             if tuple(row.get(field) for field in key_fields) not in seen]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for row in fresh:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    return len(fresh)


def dedupe_key(ticker, component_id, spec: dict) -> tuple:
    """Idempotency key for one spec's outcome.

    metric and comparator are part of the key because one component may carry
    several distinct specs at the same due date (verified repro: a cash-lt
    floor plus a debt-gt ceiling on the same component and due -- keyed on
    (ticker, component_id, due) alone the second spec was silently dropped as
    already_resolved and the genuine hit never scored)."""
    if spec.get("spec_id"):
        return (
            "v2",
            str(ticker or ""),
            str(spec.get("spec_id")),
            int(spec.get("spec_revision") or 1),
            spec_payload_hash(spec),
        )
    return (
        "v1",
        str(ticker or ""),
        str(component_id or ""),
        str(spec.get("due") or ""),
        str(spec.get("metric") or ""),
        str(spec.get("comparator") or ""),
    )


def outcome_key(row: dict) -> tuple:
    spec = dict(row.get("spec")) if isinstance(row.get("spec"), dict) else {}
    if row.get("spec_id") and not spec.get("spec_id"):
        spec["spec_id"] = row.get("spec_id")
        spec["spec_revision"] = row.get("spec_revision") or 1
    if not spec.get("due") and row.get("due"):
        spec["due"] = row.get("due")
    return dedupe_key(row.get("ticker"), row.get("component_id"), spec)


def resolve_metric(ticker: str, spec: dict, root: Path, today: date) -> dict:
    """Resolve source_hint to a value: fact-ledger locked row first, then the
    latest companyfacts observation at/after the due date.

    The ledger path requires the locked row's source ``as_of`` to be on/after
    the spec's due date -- a verdict on pre-due data is not a resolution
    (verified repro: a spec due 2026-06-30 scored 'hit' from a 2025-09-30
    fact).  A stale or undated ledger row falls through to companyfacts;
    when that yields nothing either the spec is unresolvable.

    Returns {value, unit, as_of, evidence_ref}; value None = unresolvable.
    """
    if is_v3_spec(spec):
        return resolve_spec(ticker, spec, root, today)
    if is_v2_spec(spec):
        return resolve_legacy_spec(ticker, spec, root, today)
    hint = str(spec.get("source_hint") or "").strip()
    empty = {"value": None, "unit": None, "as_of": None,
             "evidence_ref": None, "adapter": "legacy",
             "blocker_reason": "evidence_missing"}
    if not hint:
        return empty
    measurement, _observable, _deadline = forecast_dates(spec)
    measurement_iso = measurement.isoformat() if measurement else ""
    ledger = read_json(root / ticker / "research" / "valuation_fact_ledger.json")
    for fact in ledger.get("facts") or []:
        if not isinstance(fact, dict) or str(fact.get("field_id")) != hint or not fact.get("locked"):
            continue
        value = fact.get("value")
        if not (isinstance(value, (int, float)) and not isinstance(value, bool)):
            continue
        source = fact.get("source") or {}
        as_of = str(source.get("as_of") or "")[:10]
        filed = str(source.get("filed") or source.get("resolved_on") or "")[:10]
        if not as_of or as_of < measurement_iso:
            continue
        if filed and filed > today.isoformat():
            continue
        if fact.get("unit") != spec.get("unit"):
            continue
        return {
            "value": value,
            "unit": fact.get("unit"),
            "as_of": source.get("as_of"),
            "evidence_ref": f"{ticker}/research/valuation_fact_ledger.json#{hint}",
            "adapter": "legacy_fact_ledger",
            "blocker_reason": None,
        }
    if ":" not in hint:
        return empty
    taxonomy, concept = hint.split(":", 1)
    doc = read_json(root / ticker / "research" / "evidence" / "sec_companyfacts.json")
    entry = ((doc.get("facts") or {}).get(taxonomy) or {}).get(concept) or {}
    observations = []
    for unit, rows in (entry.get("units") or {}).items():
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            end = str(row.get("end") or "")
            value = row.get("val")
            if end and isinstance(value, (int, float)) and not isinstance(value, bool):
                observations.append((end, str(row.get("filed") or ""), value, unit))
    eligible = [obs for obs in observations
                if obs[0] >= measurement_iso
                and (not obs[1] or obs[1][:10] <= today.isoformat())
                and obs[3] == spec.get("unit")]
    if not eligible:
        return empty
    end, _filed, value, unit = max(eligible)
    return {
        "value": value,
        "unit": unit,
        "as_of": end,
        "evidence_ref": f"{ticker}/research/evidence/sec_companyfacts.json#{hint}@{end}",
        "adapter": "legacy_companyfacts",
        "blocker_reason": None,
    }


def compare(value: float, comparator: str, threshold) -> str:
    """hit = the falsifier condition holds (thesis falsified); else miss."""
    if comparator == "lt":
        fired = value < threshold
    elif comparator == "lte":
        fired = value <= threshold
    elif comparator == "gt":
        fired = value > threshold
    elif comparator == "gte":
        fired = value >= threshold
    elif comparator == "outside_range":
        low, high = threshold
        fired = value < low or value > high
    else:
        raise ValueError(f"unknown comparator {comparator!r}")
    return "hit" if fired else "miss"


def bucket_info(ticker: str, component_id: str, spec: dict, root: Path) -> tuple[str, str]:
    """(method_id, power_zone) for calibration bucketing, from the contract
    component and the route profile.  Missing lookups degrade to sentinels
    rather than dropping the outcome (E3: every outcome must appear in the
    calibration store)."""
    contract = read_json(root / ticker / "research" / "valuation_contract.json")
    if is_v2_spec(spec):
        return (str(spec.get("method_id") or "unknown"),
                str(spec.get("power_zone") or "unclassified"))
    method_id = "unknown"
    for component in contract.get("economic_ownership_map") or []:
        if isinstance(component, dict) and component.get("component_id") == component_id:
            method_id = str(component.get("method") or "unknown")
            break
    route = read_json(root / ticker / "research" / "valuation_route.json")
    power_zone = str(route.get("profile_id") or "unclassified")
    return method_id, power_zone


def _policy(root: Path) -> dict:
    return read_json(root / "_system/config/epistemic_loop_policy.json").get("calibration") or {}


def _row_eligible(row: dict) -> bool:
    spec = row.get("spec") or {}
    eligible, _reason = calibration_eligibility(spec)
    return (eligible and row.get("verdict") in {"hit", "miss"}
            and row.get("spec_hash") == spec_payload_hash(spec)
            and bool(row.get("evidence_ref")))


def _wilson(hits: int, total: int) -> list[float] | None:
    if not total:
        return None
    z = 1.959963984540054
    p = hits / total
    denom = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denom
    half = z * ((p * (1 - p) / total + z * z / (4 * total * total)) ** .5) / denom
    return [round(max(0, center - half), 6), round(min(1, center + half), 6)]


def _effective_rows(rows: list[dict]) -> list[dict]:
    """One primary observation per frozen correlation/event cluster."""
    selected: dict[str, dict] = {}
    for row in rows:
        spec = row.get("spec") or {}
        cluster = str(spec.get("correlation_group") or
                      f"{row.get('ticker')}|{row.get('component_id')}|{row.get('measurement_period_end')}")
        selected.setdefault(cluster, row)
    return list(selected.values())


def build_calibration(rows: list[dict], root: Path = ROOT) -> dict:
    policy = _policy(root)
    minimum = int(policy.get("minimum_effective_outcomes") or 20)
    min_probabilistic = int(policy.get("minimum_probabilistic_outcomes") or minimum)
    min_tickers = int(policy.get("minimum_distinct_tickers") or 15)
    min_industries = int(policy.get("minimum_distinct_industries") or 3)
    min_periods = int(policy.get("minimum_measurement_periods") or 2)
    max_cluster_share_allowed = float(policy.get("maximum_cluster_share") or .1)
    min_yield = float(policy.get("minimum_resolution_yield") or .9)
    buckets: dict[str, dict] = {}
    bucket_rows: dict[str, list[dict]] = {}
    for row in rows:
        method_id = str(row.get("method_id") or "unknown")
        power_zone = str(row.get("power_zone") or "unclassified")
        key = f"{method_id}|{power_zone}"
        bucket = buckets.setdefault(key, {
            "method_id": method_id,
            "power_zone": power_zone,
            "hit": 0,
            "miss": 0,
            "unresolvable": 0,
            "eligible_hit": 0,
            "eligible_miss": 0,
            "eligible_unresolvable": 0,
        })
        bucket_rows.setdefault(key, []).append(row)
        verdict = row.get("verdict")
        if verdict in ("hit", "miss", "unresolvable"):
            bucket[verdict] += 1
        spec_eligible = calibration_eligibility(row.get("spec") or {})[0]
        if spec_eligible and verdict in ("hit", "miss", "unresolvable"):
            bucket[f"eligible_{verdict}"] += 1
    for key, bucket in buckets.items():
        sample = [row for row in bucket_rows[key]
                  if row.get("verdict") in ("hit", "miss")]
        n = len(sample)
        hits = int(bucket["hit"])
        bucket["scored_outcomes"] = n
        bucket["hit_rate"] = round(hits / n, 6) if n else None
        bucket["hit_rate_wilson_95"] = _wilson(hits, n)
        eligible_terminal = [row for row in bucket_rows[key]
                             if calibration_eligibility(row.get("spec") or {})[0]
                             and row.get("verdict") in {"hit", "miss", "unresolvable"}]
        eligible_sample = [row for row in eligible_terminal if _row_eligible(row)]
        effective = _effective_rows(eligible_sample)
        clusters = [str((row.get("spec") or {}).get("correlation_group") or
                        f"{row.get('ticker')}|{row.get('measurement_period_end')}")
                    for row in eligible_sample]
        cluster_sizes = {cluster: clusters.count(cluster) for cluster in set(clusters)}
        tickers = {str(row.get("ticker") or "") for row in effective}
        periods = {str(row.get("measurement_period_end") or "") for row in effective}
        industries = {str((row.get("spec") or {}).get("industry") or "unclassified")
                      for row in effective}
        probabilities = [float(row["spec"]["probability_fires"]) for row in effective]
        actuals = [1.0 if row["verdict"] == "hit" else 0.0 for row in effective]
        brier = (sum((p - y) ** 2 for p, y in zip(probabilities, actuals)) / len(effective)
                 if effective else None)
        base_rate = sum(actuals) / len(actuals) if actuals else None
        climatology_brier = (sum((base_rate - y) ** 2 for y in actuals) / len(actuals)
                             if actuals else None)
        log_loss = None
        if effective:
            clipped = [min(.999999, max(.000001, p)) for p in probabilities]
            log_loss = -sum(y * math.log(p) + (1 - y) * math.log(1 - p)
                            for p, y in zip(clipped, actuals)) / len(effective)
        resolution_yield = (len(eligible_sample) / len(eligible_terminal)
                            if eligible_terminal else None)
        max_cluster_share = (max(cluster_sizes.values()) / len(eligible_sample)
                             if eligible_sample else None)
        provisional = (
            len(effective) >= minimum
            and len(tickers) >= min_tickers
            and len(industries) >= min_industries
            and len(periods) >= min_periods
            and max_cluster_share is not None
            and max_cluster_share <= max_cluster_share_allowed
            and resolution_yield is not None
            and resolution_yield >= .8
        )
        challenge_ready = (provisional and len(effective) >= min_probabilistic
                           and resolution_yield >= min_yield)
        bucket.update({
            "diagnostic_scored_outcomes": n - len(eligible_sample),
            "eligible_scored_outcomes": len(eligible_sample),
            "effective_outcomes": len(effective),
            "probabilistic_outcomes": len(effective),
            "distinct_tickers": len(tickers),
            "distinct_industries": len(industries),
            "measurement_periods": len(periods),
            "resolution_yield": round(resolution_yield, 6) if resolution_yield is not None else None,
            "maximum_cluster_share": round(max_cluster_share, 6) if max_cluster_share is not None else None,
            "hit_rate_eligible": round(sum(actuals) / len(actuals), 6) if actuals else None,
            "hit_rate_eligible_wilson_95": _wilson(int(sum(actuals)), len(actuals)),
            "brier_score": round(brier, 6) if brier is not None else None,
            "brier_skill_vs_climatology": (round(1 - brier / climatology_brier, 6)
                                            if brier is not None and climatology_brier else None),
            "log_loss": round(log_loss, 6) if log_loss is not None else None,
            "base_rate": round(base_rate, 6) if base_rate is not None else None,
            "learning_status": ("eligible_for_prompt_challenge" if challenge_ready
                                else "provisional_review" if provisional
                                else "plumbing_only" if not eligible_sample
                                else "collecting"),
        })
    scored_rows = [row for row in rows if row.get("verdict") in ("hit", "miss")]
    scored = len(scored_rows)
    probabilistic = [row for row in scored_rows if _row_eligible(row)]
    brier = None
    if probabilistic:
        brier = round(sum(
            (float(row["spec"]["probability_fires"])
             - (1.0 if row["verdict"] == "hit" else 0.0)) ** 2
            for row in probabilistic
        ) / len(probabilistic), 6)
    ready_buckets = [bucket for bucket in buckets.values()
                     if bucket.get("learning_status") == "eligible_for_prompt_challenge"]
    return {
        "schema_version": "3.0",
        "status": "ready" if ready_buckets else "insufficient_outcomes",
        "resolved_outcomes": len(rows),
        "scored_outcomes": scored,
        "diagnostic_scored_outcomes": scored - len(probabilistic),
        "eligible_scored_outcomes": len(probabilistic),
        "probabilistic_outcomes": len(probabilistic),
        "brier_score": brier,
        "minimum_outcomes": minimum,
        "minimum_effective_outcomes": minimum,
        "readiness_policy": policy,
        "buckets": {key: buckets[key] for key in sorted(buckets)},
        "warning": CALIBRATION_WARNING,
    }


def run(root: Path, today: date, apply: bool) -> dict:
    outcomes_path = root / OUTCOMES_REL
    calibration_path = root / CALIBRATION_REL
    existing = load_outcomes(outcomes_path)
    seen = {outcome_key(row) for row in existing}
    # Fail closed if the ledger looks missing while calibration says outcomes
    # exist: rebuilding from an absent file would silently zero the store
    # (the sparse-checkout / validator-that-looks-at-nothing trap).
    prior_calibration = read_json(calibration_path)
    if not existing and prior_calibration.get("resolved_outcomes"):
        raise SystemExit(
            "REFUSED: falsifier_outcomes.jsonl is missing/empty but "
            "falsifier_calibration.json records prior outcomes; refusing to "
            "rebuild calibration from nothing. Check the checkout."
        )
    new_rows: list[dict] = []
    attempt_rows: list[dict] = []
    state_rows: list[dict] = []
    counts = {"sidecars": 0, "specs": 0, "invalid": 0, "untestable": 0,
              "unmatured": 0, "already_resolved": 0, "hit": 0, "miss": 0,
              "unresolvable": 0, "pending_evidence": 0}
    for ticker, _path in find_sidecars(root):
        counts["sidecars"] += 1
        doc = read_json(root / ticker / "research" / "falsifier_specs.json")
        specs = doc.get("specs") if isinstance(doc.get("specs"), list) else []
        for index, spec in enumerate(specs):
            counts["specs"] += 1
            errors = spec_errors(spec, index)
            if (not errors and not spec.get("untestable")
                    and not is_v3_spec(spec)
                    and spec.get("calibration_eligible") is not False):
                # A structurally valid spec anchored to nothing in the contract
                # (phantom component_id, derived_from matching no falsifier
                # prose) must not be scored: a verdict on a fabricated spec
                # would pollute the outcomes ledger the calibration reads.
                # Untestable specs are never scored, so they skip this gate
                # (coverage_summary counts their anchoring separately).
                contract = read_json(root / ticker / "research" / "valuation_contract.json")
                if contract:
                    errors = anchor_errors(spec, contract, index)
            if errors:
                counts["invalid"] += 1
                print(f"[warn] {ticker} spec {index} invalid: {errors[0]}")
                continue
            if spec.get("untestable"):
                counts["untestable"] += 1
                continue
            measurement, observable, terminal_deadline = forecast_dates(spec)
            if observable is None or observable > today:
                counts["unmatured"] += 1
                continue
            component_id = str(spec.get("component_id"))
            key = dedupe_key(ticker, component_id, spec)
            if key in seen:
                counts["already_resolved"] += 1
                continue
            resolved = resolve_metric(ticker, spec, root, today)
            if resolved["value"] is None:
                deadline = terminal_deadline or (observable + timedelta(days=14))
                if today <= deadline:
                    counts["pending_evidence"] += 1
                    spec_hash = spec_payload_hash(spec)
                    reason = str(resolved.get("blocker_reason") or "evidence_missing")
                    attempt_rows.append({
                        "attempt_id": hashlib.sha256(
                            f"{ticker}|{spec_hash}|{today.isoformat()}|{reason}".encode()
                        ).hexdigest()[:24],
                        "ticker": ticker,
                        "spec_id": spec.get("spec_id"),
                        "spec_revision": spec.get("spec_revision"),
                        "spec_hash": spec_hash,
                        "attempted_on": today.isoformat(),
                        "adapter": resolved.get("adapter"),
                        "reason_code": reason,
                        "details": resolved.get("details") or {},
                        "status": "retry_wait" if reason in {"source_lag", "transient_failure", "evidence_missing"}
                                  else "needs_semantic_review",
                    })
                    state_rows.append({
                        "event_id": hashlib.sha256(
                            f"pending|{ticker}|{spec_hash}|{today.isoformat()}|{reason}".encode()
                        ).hexdigest()[:24],
                        "ticker": ticker,
                        "spec_id": spec.get("spec_id"),
                        "spec_hash": spec_hash,
                        "state": "retry_wait" if reason in {"source_lag", "transient_failure", "evidence_missing"}
                                 else "needs_semantic_review",
                        "reason_code": reason,
                        "recorded_at": datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc).isoformat(),
                    })
                    continue
                verdict = "unresolvable"
            else:
                verdict = compare(resolved["value"], spec["comparator"], spec["threshold"])
            counts[verdict] += 1
            method_id, power_zone = bucket_info(ticker, component_id, spec, root)
            row = {
                "ticker": ticker,
                "component_id": component_id,
                "spec_id": spec.get("spec_id"),
                "spec_revision": spec.get("spec_revision"),
                "spec_hash": spec_payload_hash(spec),
                "spec": spec,
                "resolved_value": resolved["value"],
                "resolved_unit": resolved["unit"],
                "resolved_as_of": resolved["as_of"],
                "verdict": verdict,
                "evidence_ref": resolved["evidence_ref"],
                "evidence_adapter": resolved.get("adapter"),
                "evidence_blocker_reason": resolved.get("blocker_reason"),
                "observation_provenance": (resolved.get("raw_observation")
                                           or resolved.get("formula_inputs")),
                "resolved_on": today.isoformat(),
                "method_id": method_id,
                "power_zone": power_zone,
                "measurement_period_end": measurement.isoformat() if measurement else None,
                "observable_after": observable.isoformat() if observable else None,
                "resolution_deadline": (terminal_deadline.isoformat()
                                        if terminal_deadline else None),
                "calibration_eligible": calibration_eligibility(spec)[0],
                "event_cluster_id": str(spec.get("correlation_group") or
                                        f"{ticker}|{component_id}|{measurement.isoformat() if measurement else ''}"),
            }
            new_rows.append(row)
            state_rows.append({
                "event_id": hashlib.sha256(
                    f"resolved|{ticker}|{row['spec_hash']}|{today.isoformat()}|{verdict}".encode()
                ).hexdigest()[:24],
                "ticker": ticker,
                "spec_id": spec.get("spec_id"),
                "spec_hash": row["spec_hash"],
                "state": f"resolved_{verdict}" if verdict in {"hit", "miss"} else "unresolvable_deadline",
                "reason_code": resolved.get("blocker_reason"),
                "outcome_id": hashlib.sha256(json.dumps(row, sort_keys=True).encode()).hexdigest()[:24],
                "recorded_at": datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc).isoformat(),
            })
            seen.add(key)
            print(f"{verdict.upper()}: {ticker} {component_id} {spec.get('metric')} "
                  f"{spec.get('comparator')} {spec.get('threshold')} -> {resolved['value']}")
    calibration = build_calibration(existing + new_rows, root)
    if apply:
        # Always create the ledger file, even with zero new rows: the first
        # scheduled run went red because the workflow's git add of a
        # never-created falsifier_outcomes.jsonl exits 128.  An empty ledger
        # is a valid (and honest) state.
        outcomes_path.parent.mkdir(parents=True, exist_ok=True)
        with outcomes_path.open("a", encoding="utf-8") as handle:
            for row in new_rows:
                handle.write(json.dumps(row, sort_keys=True) + "\n")
        append_unique_jsonl(root / ATTEMPTS_REL, attempt_rows,
                            ("ticker", "spec_hash", "attempted_on", "reason_code"))
        append_unique_jsonl(root / STATE_EVENTS_REL, state_rows, ("event_id",))
        calibration_path.parent.mkdir(parents=True, exist_ok=True)
        calibration_path.write_text(json.dumps(calibration, indent=2) + "\n", encoding="utf-8")
        from build_calibration_brief import build as build_calibration_brief
        build_calibration_brief(root)
    mode = "apply" if apply else "dry-run (pass --apply to write)"
    print(f"resolver [{mode}]: {counts['sidecars']} sidecars, {counts['specs']} specs, "
          f"{len(new_rows)} new outcomes ({counts['hit']} hit, {counts['miss']} miss, "
          f"{counts['unresolvable']} unresolvable), {counts['already_resolved']} already resolved, "
          f"{counts['unmatured']} unmatured, {counts['pending_evidence']} pending evidence, "
          f"{counts['untestable']} untestable, "
          f"{counts['invalid']} invalid")
    return {"counts": counts, "new_rows": new_rows, "attempt_rows": attempt_rows,
            "state_rows": state_rows, "calibration": calibration}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--date", default=date.today().isoformat(),
                        help="Resolution date (ISO); specs due after it are unmatured.")
    parser.add_argument("--apply", action="store_true",
                        help="Write outcomes and calibration (default: dry run).")
    args = parser.parse_args()
    today = parse_due(args.date)
    if today is None:
        print(f"invalid --date {args.date!r}; expected YYYY-MM-DD")
        return 2
    run(ROOT, today, args.apply)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

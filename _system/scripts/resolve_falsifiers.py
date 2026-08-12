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
import json
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "_system" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from falsifier_specs import (  # noqa: E402
    anchor_errors,
    forecast_dates,
    is_v2_spec,
    parse_due,
    read_json,
    spec_errors,
    spec_payload_hash,
)

OUTCOMES_REL = Path("_system") / "research" / "falsifier_outcomes.jsonl"
CALIBRATION_REL = Path("_system") / "research" / "falsifier_calibration.json"
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
    hint = str(spec.get("source_hint") or "").strip()
    empty = {"value": None, "unit": None, "as_of": None, "evidence_ref": None}
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


def build_calibration(rows: list[dict]) -> dict:
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
        })
        bucket_rows.setdefault(key, []).append(row)
        verdict = row.get("verdict")
        if verdict in ("hit", "miss", "unresolvable"):
            bucket[verdict] += 1
    for key, bucket in buckets.items():
        sample = [row for row in bucket_rows[key]
                  if row.get("verdict") in ("hit", "miss")]
        n = len(sample)
        hits = int(bucket["hit"])
        if n:
            # Wilson score interval is stable for small n; unlike a normal
            # interval it does not claim zero uncertainty at 0/n or n/n.
            z = 1.959963984540054
            p = hits / n
            denom = 1 + z * z / n
            center = (p + z * z / (2 * n)) / denom
            half = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** .5) / denom
            bucket["scored_outcomes"] = n
            bucket["hit_rate"] = round(p, 6)
            bucket["hit_rate_wilson_95"] = [round(max(0, center - half), 6),
                                             round(min(1, center + half), 6)]
        probabilistic_sample = [
            row for row in sample
            if isinstance((row.get("spec") or {}).get("probability_fires"), (int, float))
            and (row.get("spec") or {}).get("calibration_eligible", True)]
        bucket["probabilistic_outcomes"] = len(probabilistic_sample)
        bucket["brier_score"] = (round(sum(
            (float(row["spec"]["probability_fires"])
             - (1.0 if row["verdict"] == "hit" else 0.0)) ** 2
            for row in probabilistic_sample) / len(probabilistic_sample), 6)
            if probabilistic_sample else None)
    scored_rows = [row for row in rows if row.get("verdict") in ("hit", "miss")]
    scored = len(scored_rows)
    probabilistic = [row for row in scored_rows
                     if isinstance((row.get("spec") or {}).get("probability_fires"), (int, float))
                     and (row.get("spec") or {}).get("calibration_eligible", True)]
    brier = None
    if probabilistic:
        brier = round(sum(
            (float(row["spec"]["probability_fires"])
             - (1.0 if row["verdict"] == "hit" else 0.0)) ** 2
            for row in probabilistic
        ) / len(probabilistic), 6)
    min_outcomes = 20
    return {
        "schema_version": "2.0",
        "status": "ready" if scored >= min_outcomes else "insufficient_outcomes",
        "resolved_outcomes": len(rows),
        "scored_outcomes": scored,
        "probabilistic_outcomes": len(probabilistic),
        "brier_score": brier,
        "minimum_outcomes": min_outcomes,
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
            if not errors and not spec.get("untestable"):
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
                "resolved_on": today.isoformat(),
                "method_id": method_id,
                "power_zone": power_zone,
                "measurement_period_end": measurement.isoformat() if measurement else None,
                "observable_after": observable.isoformat() if observable else None,
                "resolution_deadline": (terminal_deadline.isoformat()
                                        if terminal_deadline else None),
            }
            new_rows.append(row)
            seen.add(key)
            print(f"{verdict.upper()}: {ticker} {component_id} {spec.get('metric')} "
                  f"{spec.get('comparator')} {spec.get('threshold')} -> {resolved['value']}")
    calibration = build_calibration(existing + new_rows)
    if apply:
        # Always create the ledger file, even with zero new rows: the first
        # scheduled run went red because the workflow's git add of a
        # never-created falsifier_outcomes.jsonl exits 128.  An empty ledger
        # is a valid (and honest) state.
        outcomes_path.parent.mkdir(parents=True, exist_ok=True)
        with outcomes_path.open("a", encoding="utf-8") as handle:
            for row in new_rows:
                handle.write(json.dumps(row, sort_keys=True) + "\n")
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
    return {"counts": counts, "new_rows": new_rows, "calibration": calibration}


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

#!/usr/bin/env python3
"""Operational workflow for the 10-Q/K Filing Sentinel gold set.

This module creates auditable evidence packs and blind-labeling queues. It can
automate discovery, sampling, split locking, consensus checks, and error
routing; it cannot silently promote a case to gold.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Iterable

from filing_sentinel_gold import (
    DEFAULT_GOLD,
    ROOT,
    _fact_documents,
    _filing_meta,
    _metric_proposal,
    _sha256,
    _source_text_path,
    load_taxonomy,
    read_jsonl,
    validate_case,
    validate_dataset,
    write_jsonl,
)

SECTION_PATTERNS: dict[str, tuple[str, ...]] = {
    "financial_oxygen": (
        r"going concern", r"liquidity", r"debt maturit", r"covenant", r"revolver",
        r"credit facility", r"at-the-market", r"equity issu", r"shelf registration",
    ),
    "accounting": (
        r"material weakness", r"restatement", r"auditor", r"revenue recognition",
        r"accounting polic", r"critical audit", r"internal control",
    ),
    "operations": (
        r"customer concentration", r"backlog", r"impairment", r"restructur",
        r"utilization", r"purchase commitment",
    ),
    "governance_legal": (
        r"legal proceedings", r"litigation", r"investigation", r"related part",
        r"controls and procedures", r"executive officer",
    ),
    "transaction": (
        r"strategic review", r"asset sale", r"wind down", r"exchange offer",
        r"merger agreement", r"financing agreement",
    ),
    "identity_instrument": (
        r"reverse stock split", r"ticker symbol", r"convertible", r"warrant",
        r"common stock", r"dilutive",
    ),
}
ALWAYS_REVIEW_CATEGORIES = {"accounting", "governance_legal", "transaction"}


def _normalise_excerpt(raw: str, *, maximum: int = 1200) -> str:
    return re.sub(r"\s+", " ", raw).strip()[:maximum]


def _section_evidence(ticker: str, source_text: str | None, *, source_role: str, limit: int = 8) -> tuple[list[dict], list[str]]:
    path = _source_text_path(ticker, source_text)
    if not path:
        return [], []
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")[:300_000]
    except OSError:
        return [], []
    evidence: list[dict] = []
    categories: list[str] = []
    seen: set[str] = set()
    for category, patterns in SECTION_PATTERNS.items():
        for pattern in patterns:
            match = re.search(pattern, text, re.I)
            if not match:
                continue
            start = max(0, match.start() - 500)
            end = min(len(text), match.end() + 900)
            excerpt = _normalise_excerpt(text[start:end])
            digest = _sha256(excerpt)
            if not excerpt or digest in seen:
                continue
            seen.add(digest)
            evidence.append({
                "evidence_id": f"ev-section-{category}-{len(evidence) + 1:02d}",
                "locator": f"{source_role} text characters {start + 1}-{end}; keyword /{pattern}/i",
                "excerpt": excerpt,
                "content_sha256": digest,
                "source_role": source_role,
                "source_ref": f"{ticker}/research/{source_text}" if source_text else None,
                "section_category": category,
            })
            categories.append(category)
            break
        if len(evidence) >= limit:
            break
    return evidence, categories


def _prior_documents(documents: list[tuple[Path, dict]]) -> dict[str, dict]:
    """Map source filing identity to the preceding comparable 10-Q/K fact doc."""
    grouped: dict[tuple[str, str], list[tuple[dict, dict]]] = defaultdict(list)
    for _path, doc in documents:
        meta = _filing_meta(doc)
        if not meta:
            continue
        ticker = str(doc.get("ticker") or _path.parents[2].name).upper()
        key = str(doc.get("source_filing_ref") or doc.get("source_text") or _path)
        grouped[(ticker, meta["filing_form"])].append((doc, meta))
    prior: dict[str, dict] = {}
    for rows in grouped.values():
        rows.sort(key=lambda pair: (pair[1]["period_end"], pair[1]["filing_date"]))
        for current, current_meta in rows:
            current_period = date.fromisoformat(current_meta["period_end"])
            candidates = [
                (previous, previous_meta) for previous, previous_meta in rows
                if previous_meta["period_end"] < current_meta["period_end"]
                and 300 <= (current_period - date.fromisoformat(previous_meta["period_end"])).days <= 430
            ]
            if not candidates:
                continue
            previous, _previous_meta = min(
                candidates,
                key=lambda item: abs((current_period - date.fromisoformat(item[1]["period_end"])).days - 365),
            )
            key = str(current.get("source_filing_ref") or current.get("source_text"))
            prior[key] = previous
    return prior


def _strata(case: dict) -> list[str]:
    reasons = case.get("mining_reasons") or []
    proposals = case.get("proposals") or []
    directions = {proposal.get("direction") for proposal in proposals}
    strata: list[str] = []
    if any("parser_hard_negative" in reason for reason in reasons):
        strata.append("hard_negative")
    if any(str(reason).startswith("clean_control") for reason in reasons):
        strata.append("clean_control")
    if any(p.get("severity") == "high" and p.get("direction") == "strengthens" for p in proposals):
        strata.append("high_adverse")
    if "strengthens" in directions and "weakens" in directions or (directions == {"weakens"} and proposals):
        strata.append("offsetting")
    section_categories = set(case.get("section_signals") or [])
    if section_categories & ALWAYS_REVIEW_CATEGORIES:
        strata.append("semantic_section")
    if not strata:
        strata.append("material_metric")
    return strata


def lock_split(ticker: str, policy: dict) -> str:
    bucket = int(hashlib.sha256((policy.get("version", "v1") + "|" + ticker.upper()).encode()).hexdigest()[:8], 16) % 100
    train = int(policy.get("train_pct", 70))
    dev = train + int(policy.get("dev_pct", 15))
    return "train" if bucket < train else "dev" if bucket < dev else "test"


def enrich_candidates(*, universe: str, tickers: set[str], as_of: str) -> list[dict]:
    taxonomy = load_taxonomy()
    documents = _fact_documents(universe, tickers)
    metric_rules = taxonomy.get("metric_proposals") or {}
    priors = _prior_documents(documents)
    cases: list[dict] = []
    for fact_path, doc in documents:
        meta = _filing_meta(doc)
        if not meta:
            continue
        ticker = str(doc.get("ticker") or fact_path.parents[2].name).upper()
        evidence: list[dict] = []
        proposals: list[dict] = []
        reasons: list[str] = []
        clean_evidence: list[dict] = []
        for metric_name, metric in sorted((doc.get("metrics") or {}).items()):
            if metric_name not in metric_rules or not isinstance(metric, dict):
                continue
            proposal, reason = _metric_proposal(metric_name, metric, metric_rules[metric_name])
            excerpt = str(metric.get("extract_snippet") or "").strip()
            if not excerpt:
                excerpt = f"{metric.get('tag') or metric_name}: {metric.get('current')}\n{metric.get('tag') or metric_name}: {metric.get('prior')}"
            item = {
                "evidence_id": f"ev-{metric_name}",
                "locator": f"IX facts lines {metric.get('current_line', '?')}-{metric.get('prior_line', '?')}",
                "excerpt": excerpt,
                "content_sha256": _sha256(excerpt),
                "source_role": "current",
            }
            if proposal:
                proposal["evidence_ids"] = [item["evidence_id"]]
                evidence.append(item)
                proposals.append(proposal)
            elif reason and reason.startswith("parser_hard_negative"):
                item["evidence_id"] += "-hard-negative"
                evidence.append(item)
                reasons.append(f"{metric_name}:{reason}")
            elif reason == "below_materiality_threshold" and len(clean_evidence) < 3:
                item["evidence_id"] += "-clean-control"
                clean_evidence.append(item)
        if not proposals and not reasons and clean_evidence:
            evidence.extend(clean_evidence)
            reasons.append("clean_control:all_supported_metrics_below_threshold")

        source_text = str(doc.get("source_text") or "")
        current_sections, signals = _section_evidence(ticker, source_text, source_role="current")
        evidence.extend(current_sections)
        source_key = str(doc.get("source_filing_ref") or source_text)
        previous = priors.get(source_key)
        comparison_source_ref = None
        comparison_hash = None
        comparison_period_end = None
        if previous:
            previous_text = str(previous.get("source_text") or "")
            prior_sections, prior_signals = _section_evidence(ticker, previous_text, source_role="prior", limit=4)
            for item in prior_sections:
                item["evidence_id"] = item["evidence_id"].replace("ev-section-", "ev-prior-section-")
            evidence.extend(prior_sections)
            signals.extend(prior_signals)
            comparison_source_ref = str(previous.get("source_filing_ref") or f"{ticker}/research/{previous_text}").replace("\\", "/")
            comparison_path = ROOT / comparison_source_ref
            comparison_hash = _sha256(comparison_path.read_bytes()) if comparison_path.exists() else None
            comparison_period_end = (_filing_meta(previous) or {}).get("period_end")
        if signals:
            reasons.append("section_signal:" + ",".join(sorted(set(signals))))
        if not proposals and not reasons:
            continue

        extract_path = _source_text_path(ticker, source_text)
        extract_ref = f"{ticker}/research/{source_text}" if source_text else None
        source_ref = str(doc.get("source_filing_ref") or extract_ref or fact_path.relative_to(ROOT)).replace("\\", "/")
        source_path = ROOT / source_ref
        source_hash = _sha256(source_path.read_bytes()) if source_path.exists() else None
        raw_id = f"{ticker}|{meta['filing_form']}|{meta['filing_date']}|{source_ref}"
        case = {
            "schema_version": 1,
            "case_id": f"fs-{ticker.lower().replace('.', '-')}-{meta['filing_date']}-{_sha256(raw_id)[:8]}",
            "label_status": "candidate",
            "split": lock_split(ticker, taxonomy.get("split_policy") or {}),
            "ticker": ticker,
            "filing": {
                "form": meta["filing_form"], "filed_at": meta["filing_date"], "period_end": meta["period_end"],
                "accession": meta.get("accession"), "source_ref": source_ref, "source_sha256": source_hash,
                "extract_ref": extract_ref, "extract_sha256": _sha256(extract_path.read_bytes()) if extract_path else None,
                "comparison_source_ref": comparison_source_ref, "comparison_period_end": comparison_period_end, "comparison_sha256": comparison_hash,
            },
            "evidence": evidence,
            "proposals": proposals,
            "mining_reasons": sorted(set(reasons)),
            "section_signals": sorted(set(signals)),
            "expected": {"events": [], "no_event_tags": [], "no_material_change": False},
            "provenance": {
                "origin": str(fact_path.relative_to(ROOT)).replace("\\", "/"), "created_at": as_of,
                "adjudicated_by": [], "rationale": "Autonomous candidate with structured and section-level evidence; not a gold label.",
            },
        }
        case["sampling"] = {"strata": _strata(case)}
        case["candidate_priority"] = (
            sum(4 if p.get("severity") == "high" else 2 for p in proposals)
            + 3 * sum("parser_hard_negative" in r for r in reasons)
            + len(case["section_signals"])
        )
        cases.append(case)
    return cases


def quota_sample(cases: list[dict], *, limit: int, taxonomy: dict) -> tuple[list[dict], dict]:
    policy = taxonomy.get("sampling_policy") or {}
    targets = {name: math.ceil(limit * float(pct)) for name, pct in (policy.get("stratum_target_pct") or {}).items()}
    form_targets = {name: math.ceil(limit * float(pct)) for name, pct in (policy.get("form_min_pct") or {}).items()}
    issuer_cap = max(1, math.floor(limit * float(policy.get("issuer_cap_pct", 0.05))))
    ordered = sorted(cases, key=lambda row: (-int(row.get("candidate_priority") or 0), row["ticker"], row["case_id"]))
    selected: list[dict] = []
    selected_ids: set[str] = set()
    issuer_counts: Counter = Counter()
    summary: dict = {"target": limit, "stratum_targets": targets, "form_targets": form_targets, "issuer_cap": issuer_cap, "selected_by_stratum": Counter(), "selected_by_form": Counter()}

    def add(case: dict, selected_as: str) -> bool:
        if case["case_id"] in selected_ids or issuer_counts[case["ticker"]] >= issuer_cap:
            return False
        if len(selected) >= limit:
            return False
        copy = json.loads(json.dumps(case))
        copy["sampling"]["selected_as"] = selected_as
        selected.append(copy)
        selected_ids.add(case["case_id"])
        issuer_counts[case["ticker"]] += 1
        summary["selected_by_stratum"][selected_as] += 1
        summary["selected_by_form"][case["filing"]["form"]] += 1
        return True

    for stratum, target in targets.items():
        stratum_ordered = sorted(
            (case for case in ordered if stratum in (case.get("sampling") or {}).get("strata", [])),
            key=lambda case: (
                0 if summary["selected_by_form"][case["filing"]["form"]] < form_targets.get(case["filing"]["form"], 0) else 1,
                -int(case.get("candidate_priority") or 0), case["ticker"], case["case_id"],
            ),
        )
        for case in stratum_ordered:
            if summary["selected_by_stratum"][stratum] >= target:
                break
            add(case, stratum)
    for form, target in form_targets.items():
        for case in ordered:
            if summary["selected_by_form"][form] >= target:
                break
            if case["filing"]["form"] == form:
                add(case, f"form_balance:{form}")
    for case in ordered:
        add(case, "priority_fill")
    coverage_by_stratum = Counter(
        stratum for case in selected for stratum in (case.get("sampling") or {}).get("strata", [])
    )
    summary["selected"] = len(selected)
    summary["available"] = len(cases)
    summary["selected_by_stratum"] = dict(summary["selected_by_stratum"])
    summary["selected_by_form"] = dict(summary["selected_by_form"])
    summary["coverage_by_stratum"] = dict(coverage_by_stratum)
    summary["quota_shortfalls"] = {
        "forms": {form: max(0, target - summary["selected_by_form"].get(form, 0)) for form, target in form_targets.items()},
        "strata": {stratum: max(0, target - coverage_by_stratum.get(stratum, 0)) for stratum, target in targets.items()},
    }
    return selected, summary


def build_batch(*, universe: str, tickers: set[str], as_of: str, limit: int) -> tuple[list[dict], dict]:
    taxonomy = load_taxonomy()
    return quota_sample(enrich_candidates(universe=universe, tickers=tickers, as_of=as_of), limit=limit, taxonomy=taxonomy)


def create_label_packets(cases: list[dict], output_dir: Path, *, batch_id: str) -> dict:
    labeler_dir = output_dir / "labelers"
    control_dir = output_dir / "control"
    labeler_dir.mkdir(parents=True, exist_ok=True)
    control_dir.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, dict] = {"schema_version": 1, "batch_id": batch_id, "cases": {}}
    packets: dict[str, list[dict]] = {"extractor": [], "skeptic": []}
    for ordinal, case in enumerate(cases, start=1):
        alias = f"Issuer-{ordinal:03d}"
        manifest["cases"][case["case_id"]] = {"ticker": case["ticker"], "split": case["split"], "alias": alias, "blind_ids": {}}
        for role in packets:
            blind_id = "blind-" + _sha256(f"{batch_id}|{role}|{case['case_id']}")[:16]
            manifest["cases"][case["case_id"]]["blind_ids"][role] = blind_id
            blind_evidence = [
                {key: value for key, value in item.items() if key not in {"source_ref", "source_role"}}
                for item in case["evidence"]
            ]
            packets[role].append({
                "schema_version": 1, "blind_id": blind_id, "issuer_alias": alias,
                "filing": {key: case["filing"].get(key) for key in ("form", "filed_at", "period_end")},
                "evidence": blind_evidence,
                "task": {
                    "instruction": "Label only source-supported material changes. Return events with category, tags, direction, severity, claim, falsifier, evidence_ids, and review_required. Return no_material_change=true only when the supplied evidence supports no alert.",
                    "role": role,
                    "do_not_use": ["issuer identity", "source path", "precomputed suggestions", "existing labels", "split"],
                },
            })
    for role, rows in packets.items():
        write_jsonl(labeler_dir / f"{role}_packet.jsonl", rows)
    (control_dir / "blind_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return {"batch_id": batch_id, "cases": len(cases), "labeler_dir": str(labeler_dir), "control_dir": str(control_dir)}


def _event_signature(event: dict) -> tuple:
    return (
        str(event.get("category") or ""),
        tuple(sorted(str(tag) for tag in (event.get("tags") or []))),
        str(event.get("direction") or ""),
        bool(event.get("review_required")),
    )


def _prepare_blind_label(label: dict, case_id: str) -> dict:
    """Fill local event IDs so labelers can use the compact response contract."""
    copy = json.loads(json.dumps(label))
    for index, event in enumerate(copy.get("events") or [], start=1):
        event.setdefault("event_id", f"{case_id}-blind-{index}")
    return copy


def _labels_by_case(rows: list[dict], manifest: dict, role: str) -> dict[str, dict]:
    mapping = {entry["blind_ids"].get(role): case_id for case_id, entry in (manifest.get("cases") or {}).items()}
    result: dict[str, dict] = {}
    for row in rows:
        case_id = mapping.get(row.get("blind_id"))
        if not case_id:
            raise ValueError(f"{role} label uses an unknown blind_id: {row.get('blind_id')}")
        if case_id in result:
            raise ValueError(f"{role} supplied multiple labels for {case_id}")
        result[case_id] = row
    return result


def _labels_agree(extractor: dict, skeptic: dict, taxonomy: dict) -> bool:
    left = sorted(_event_signature(event) for event in extractor.get("events") or [])
    right = sorted(_event_signature(event) for event in skeptic.get("events") or [])
    if left != right or bool(extractor.get("no_material_change")) != bool(skeptic.get("no_material_change")):
        return False
    always = set(taxonomy.get("always_human_review_tags") or [])
    return not any(set(event.get("tags") or []) & always for event in extractor.get("events") or [])


def _blind_label_errors(label: dict, case: dict, taxonomy: dict) -> list[str]:
    copy = json.loads(json.dumps(case))
    copy["expected"] = {
        "events": label.get("events") or [],
        "no_event_tags": label.get("no_event_tags") or [],
        "no_material_change": bool(label.get("no_material_change")),
    }
    errors = validate_case(copy, taxonomy, require_gold=False)
    if not copy["expected"]["events"] and not copy["expected"]["no_material_change"]:
        errors.append(f"{case['case_id']}: blind label with no events must set no_material_change=true")
    return errors


def ingest_blind_labels(cases: list[dict], manifest: dict, extractor_rows: list[dict], skeptic_rows: list[dict], *, as_of: str) -> tuple[list[dict], list[dict]]:
    taxonomy = load_taxonomy()
    extractor = _labels_by_case(extractor_rows, manifest, "extractor")
    skeptic = _labels_by_case(skeptic_rows, manifest, "skeptic")
    updated: list[dict] = []
    adjudication: list[dict] = []
    for case in cases:
        copy = json.loads(json.dumps(case))
        case_id = copy["case_id"]
        left, right = extractor.get(case_id), skeptic.get(case_id)
        if left:
            left = _prepare_blind_label(left, case_id)
        if right:
            right = _prepare_blind_label(right, case_id)
        if not left or not right:
            adjudication.append({"case_id": case_id, "reason": "missing_blind_label", "extractor": left, "skeptic": right, "case": copy})
            updated.append(copy)
            continue
        left_errors = _blind_label_errors(left, copy, taxonomy)
        right_errors = _blind_label_errors(right, copy, taxonomy)
        if left_errors or right_errors:
            adjudication.append({"case_id": case_id, "reason": "invalid_blind_label", "extractor_errors": left_errors, "skeptic_errors": right_errors, "extractor": left, "skeptic": right, "case": copy})
            updated.append(copy)
            continue
        if _labels_agree(left, right, taxonomy):
            expected = {key: left.get(key, [] if key != "no_material_change" else False) for key in ("events", "no_event_tags", "no_material_change")}
            copy["expected"] = expected
            copy["label_status"] = "labeled"
            copy["provenance"]["adjudicated_by"] = ["blind_extractor", "blind_skeptic", "auto_consensus"]
            copy["provenance"]["rationale"] = "Two blind labelers agreed on a low-risk label; pending audit or explicit promotion."
        else:
            adjudication.append({"case_id": case_id, "reason": "blind_disagreement_or_always_review", "extractor": left, "skeptic": right, "case": copy})
        updated.append(copy)
    return updated, adjudication


def promote_cases(cases: list[dict], gold_rows: list[dict], decisions: list[dict], *, as_of: str, include_auto: bool) -> list[dict]:
    taxonomy = load_taxonomy()
    by_decision = {str(row.get("case_id")): row for row in decisions}
    promoted = list(gold_rows)
    existing = {row["case_id"] for row in gold_rows}
    for case in cases:
        decision = by_decision.get(case["case_id"])
        if not decision and not (include_auto and case.get("label_status") == "labeled"):
            continue
        copy = json.loads(json.dumps(case))
        if decision:
            if decision.get("events") is not None:
                copy["expected"] = {
                    "events": decision.get("events") or [],
                    "no_event_tags": decision.get("no_event_tags") or [],
                    "no_material_change": bool(decision.get("no_material_change")),
                }
            copy["provenance"]["adjudicated_by"] = [str(decision.get("adjudicator") or "named_adjudicator")]
            copy["provenance"]["rationale"] = str(decision.get("rationale") or "Independent adjudication.")
        copy["label_status"] = "gold"
        copy["provenance"]["created_at"] = as_of
        errors = validate_case(copy, taxonomy, require_gold=True)
        if errors:
            raise ValueError("Cannot promote " + copy["case_id"] + ": " + "; ".join(errors))
        if copy["case_id"] not in existing:
            promoted.append(copy)
            existing.add(copy["case_id"])
    errors = validate_dataset(promoted, taxonomy, require_gold=True)
    if errors:
        raise ValueError("Gold set validation failed: " + "; ".join(errors))
    return promoted


def failure_queue(gold_rows: list[dict], prediction_rows: list[dict]) -> list[dict]:
    predictions = {str(row.get("case_id")): row for row in prediction_rows}
    failures: list[dict] = []
    for case in gold_rows:
        if case.get("label_status") != "gold":
            continue
        predicted = list((predictions.get(case["case_id"]) or {}).get("events") or [])
        unmatched = set(range(len(predicted)))
        for event in (case.get("expected") or {}).get("events") or []:
            idx = next((i for i in unmatched if _event_signature(event) == _event_signature(predicted[i])), None)
            if idx is None:
                failures.append({"case_id": case["case_id"], "split": case["split"], "failure_type": "false_negative", "event": event, "eligible_for_training": case["split"] != "test"})
            else:
                unmatched.remove(idx)
        for idx in unmatched:
            failures.append({"case_id": case["case_id"], "split": case["split"], "failure_type": "false_positive", "event": predicted[idx], "eligible_for_training": case["split"] != "test"})
    return failures


def coverage_report(cases: list[dict]) -> dict:
    report: dict[str, Counter] = {"forms": Counter(), "splits": Counter(), "statuses": Counter(), "strata": Counter(), "categories": Counter()}
    for case in cases:
        report["forms"][str((case.get("filing") or {}).get("form"))] += 1
        report["splits"][str(case.get("split"))] += 1
        report["statuses"][str(case.get("label_status"))] += 1
        for stratum in ((case.get("sampling") or {}).get("strata") or []):
            report["strata"][str(stratum)] += 1
        for event in ((case.get("expected") or {}).get("events") or []):
            report["categories"][str(event.get("category"))] += 1
    return {key: dict(value) for key, value in report.items()}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    batch = sub.add_parser("build-batch", help="Mine quota-balanced candidates with current/prior section evidence")
    batch.add_argument("--output", type=Path, required=True)
    batch.add_argument("--universe", choices=("portfolio", "all"), default="portfolio")
    batch.add_argument("--ticker", action="append", default=[])
    batch.add_argument("--as-of", default=date.today().isoformat())
    batch.add_argument("--limit", type=int, default=100)
    packets = sub.add_parser("create-packets", help="Create independent blinded extractor and skeptic packets")
    packets.add_argument("--candidates", type=Path, required=True)
    packets.add_argument("--output-dir", type=Path, required=True)
    packets.add_argument("--batch-id", required=True)
    ingest = sub.add_parser("ingest-labels", help="Compare blind labels; queue disagreements for adjudication")
    ingest.add_argument("--candidates", type=Path, required=True)
    ingest.add_argument("--manifest", type=Path, required=True)
    ingest.add_argument("--extractor", type=Path, required=True)
    ingest.add_argument("--skeptic", type=Path, required=True)
    ingest.add_argument("--output", type=Path, required=True)
    ingest.add_argument("--adjudication-output", type=Path, required=True)
    ingest.add_argument("--as-of", default=date.today().isoformat())
    promote = sub.add_parser("promote", help="Promote only adjudicated (or explicitly allowed consensus) labels to gold")
    promote.add_argument("--labeled", type=Path, required=True)
    promote.add_argument("--gold", type=Path, default=DEFAULT_GOLD)
    promote.add_argument("--decisions", type=Path)
    promote.add_argument("--output", type=Path, required=True)
    promote.add_argument("--as-of", default=date.today().isoformat())
    promote.add_argument("--include-auto-consensus", action="store_true")
    failures = sub.add_parser("queue-failures", help="Create regression queue from false positives and false negatives")
    failures.add_argument("--gold", type=Path, default=DEFAULT_GOLD)
    failures.add_argument("--predictions", type=Path, required=True)
    failures.add_argument("--output", type=Path, required=True)
    coverage = sub.add_parser("coverage", help="Report forms, splits, strata, and labeled-category coverage")
    coverage.add_argument("--dataset", type=Path, required=True)
    coverage.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "build-batch":
        rows, summary = build_batch(universe=args.universe, tickers={t.upper() for t in args.ticker}, as_of=args.as_of, limit=max(1, args.limit))
        write_jsonl(args.output, rows)
        args.output.with_suffix(args.output.suffix + ".summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"candidates": len(rows), "output": str(args.output), "summary": summary}, indent=2))
        return 0
    if args.command == "create-packets":
        result = create_label_packets(read_jsonl(args.candidates), args.output_dir, batch_id=args.batch_id)
        print(json.dumps(result, indent=2))
        return 0
    if args.command == "ingest-labels":
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        labeled, adjudication = ingest_blind_labels(read_jsonl(args.candidates), manifest, read_jsonl(args.extractor), read_jsonl(args.skeptic), as_of=args.as_of)
        write_jsonl(args.output, labeled)
        write_jsonl(args.adjudication_output, adjudication)
        print(json.dumps({"labeled": sum(row.get("label_status") == "labeled" for row in labeled), "adjudication_queue": len(adjudication)}, indent=2))
        return 0
    if args.command == "promote":
        decisions = read_jsonl(args.decisions) if args.decisions else []
        rows = promote_cases(read_jsonl(args.labeled), read_jsonl(args.gold), decisions, as_of=args.as_of, include_auto=args.include_auto_consensus)
        write_jsonl(args.output, rows)
        print(json.dumps({"gold_cases": len(rows), "output": str(args.output)}, indent=2))
        return 0
    if args.command == "queue-failures":
        rows = failure_queue(read_jsonl(args.gold), read_jsonl(args.predictions))
        write_jsonl(args.output, rows)
        print(json.dumps({"failures": len(rows), "output": str(args.output)}, indent=2))
        return 0
    report = coverage_report(read_jsonl(args.dataset))
    rendered = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

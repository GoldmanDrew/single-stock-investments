#!/usr/bin/env python3
"""Mine, validate, and evaluate the 10-Q/K Filing Sentinel gold set.

Candidate mining is deterministic and may run unattended. It never promotes a
case to gold; promotion requires an adjudicated label and evidence check.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_GOLD = ROOT / "_system" / "scripts" / "_eval" / "filing_sentinel_gold.jsonl"
TAXONOMY_PATH = ROOT / "_system" / "data" / "filing_sentinel_taxonomy.json"
SKIP_FLAGS = {
    "segment_zero_revenue", "footnote_pairing", "immaterial_prior", "segment_context",
    "magnitude_mismatch", "legacy_pairing", "non_statement_debt",
}
FILING_RE = re.compile(
    r"(?P<form>10-K|10-Q)_(?P<filed>\d{8})_rpt(?P<period>\d{8})_acc(?P<accession>[\d_]+)",
    re.I,
)


def _sha256(value: str | bytes) -> str:
    raw = value if isinstance(value, bytes) else value.encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _iso(raw: str) -> str:
    return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"


def load_taxonomy(path: Path = TAXONOMY_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw.strip():
            continue
        try:
            row = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_no}: invalid JSON: {exc}") from exc
        if not isinstance(row, dict):
            raise ValueError(f"{path}:{line_no}: row must be an object")
        rows.append(row)
    return rows


def write_jsonl(path: Path, rows: Iterable[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def validate_case(case: dict, taxonomy: dict, *, require_gold: bool = False) -> list[str]:
    errors: list[str] = []
    case_id = str(case.get("case_id") or "<missing>")
    required = {"schema_version", "case_id", "label_status", "split", "ticker", "filing", "evidence", "expected", "provenance"}
    for key in sorted(required - set(case)):
        errors.append(f"{case_id}: missing {key}")
    if case.get("schema_version") != 1:
        errors.append(f"{case_id}: schema_version must be 1")
    if not re.fullmatch(r"fs-[a-z0-9-]+", case_id):
        errors.append(f"{case_id}: case_id must match fs-[a-z0-9-]+")
    status = case.get("label_status")
    if status not in {"candidate", "labeled", "gold", "retired"}:
        errors.append(f"{case_id}: invalid label_status {status!r}")
    if require_gold and status != "gold":
        errors.append(f"{case_id}: non-gold row in locked gold set")
    split = case.get("split")
    if split not in {"train", "dev", "test", "_unassigned"}:
        errors.append(f"{case_id}: invalid split {split!r}")
    if status == "gold" and split == "_unassigned":
        errors.append(f"{case_id}: gold row cannot have an unassigned split")

    filing = case.get("filing") or {}
    if filing.get("form") not in taxonomy.get("forms", []):
        errors.append(f"{case_id}: form must be 10-Q or 10-K")
    for field in ("filed_at", "period_end", "source_ref"):
        if not filing.get(field):
            errors.append(f"{case_id}: filing.{field} is required")
    for field in ("filed_at", "period_end"):
        try:
            date.fromisoformat(str(filing.get(field)))
        except ValueError:
            errors.append(f"{case_id}: filing.{field} must be YYYY-MM-DD")
    comparison_period = filing.get("comparison_period_end")
    if comparison_period is not None:
        try:
            comparison_date = date.fromisoformat(str(comparison_period))
            period_date = date.fromisoformat(str(filing.get("period_end")))
            days = (period_date - comparison_date).days
            if not 300 <= days <= 430:
                errors.append(f"{case_id}: comparison period must be roughly one year before filing period")
        except ValueError:
            errors.append(f"{case_id}: filing.comparison_period_end must be YYYY-MM-DD")
    source_ref = str(filing.get("source_ref") or "")
    if ".." in Path(source_ref).parts:
        errors.append(f"{case_id}: filing.source_ref cannot traverse parent directories")
    for field in ("source_sha256", "extract_sha256", "comparison_sha256"):
        value = filing.get(field)
        if value is not None and not re.fullmatch(r"[a-f0-9]{64}", str(value)):
            errors.append(f"{case_id}: filing.{field} must be a lowercase sha256")
    if status == "gold" and not filing.get("source_sha256"):
        errors.append(f"{case_id}: gold row requires filing.source_sha256")
    for ref_field, hash_field in (("source_ref", "source_sha256"), ("extract_ref", "extract_sha256")):
        ref, expected_hash = filing.get(ref_field), filing.get(hash_field)
        if ref and expected_hash and not str(ref).startswith(("http://", "https://")):
            local = ROOT / str(ref)
            if local.exists() and _sha256(local.read_bytes()) != expected_hash:
                errors.append(f"{case_id}: filing.{hash_field} does not match local {ref_field}")

    evidence_ids: set[str] = set()
    for item in case.get("evidence") or []:
        evidence_id = str(item.get("evidence_id") or "")
        if not evidence_id:
            errors.append(f"{case_id}: evidence_id is required")
        elif evidence_id in evidence_ids:
            errors.append(f"{case_id}: duplicate evidence_id {evidence_id}")
        evidence_ids.add(evidence_id)
        excerpt = str(item.get("excerpt") or "")
        if not excerpt:
            errors.append(f"{case_id}/{evidence_id}: excerpt is required")
        elif item.get("content_sha256") != _sha256(excerpt):
            errors.append(f"{case_id}/{evidence_id}: excerpt hash mismatch")
        if not item.get("locator"):
            errors.append(f"{case_id}/{evidence_id}: locator is required")
    if status == "gold" and not evidence_ids:
        errors.append(f"{case_id}: gold row requires evidence")

    categories = taxonomy.get("categories") or {}
    known_tags = {tag for tags in categories.values() for tag in tags}
    expected = case.get("expected") or {}
    events = expected.get("events") or []
    no_event_tags = expected.get("no_event_tags") or []
    if status == "gold" and not events and not expected.get("no_material_change"):
        errors.append(f"{case_id}: zero-event gold case must set no_material_change=true")
    event_ids: set[str] = set()
    for event in events:
        event_id = str(event.get("event_id") or "")
        if not event_id or event_id in event_ids:
            errors.append(f"{case_id}: event_id must be present and unique ({event_id!r})")
        event_ids.add(event_id)
        category = event.get("category")
        tags = event.get("tags") or []
        if category not in categories:
            errors.append(f"{case_id}/{event_id}: unknown category {category!r}")
        for tag in tags:
            if tag not in known_tags:
                errors.append(f"{case_id}/{event_id}: unknown tag {tag!r}")
            elif category in categories and tag not in categories[category]:
                errors.append(f"{case_id}/{event_id}: tag {tag!r} is not valid for {category}")
        if not tags:
            errors.append(f"{case_id}/{event_id}: at least one tag is required")
        if event.get("severity") not in taxonomy.get("severity_weights", {}):
            errors.append(f"{case_id}/{event_id}: invalid severity")
        if event.get("direction") not in {"strengthens", "weakens", "neutral"}:
            errors.append(f"{case_id}/{event_id}: invalid direction")
        if not event.get("claim") or not event.get("falsifier"):
            errors.append(f"{case_id}/{event_id}: claim and falsifier are required")
        event_evidence = event.get("evidence_ids") or []
        if not event_evidence:
            errors.append(f"{case_id}/{event_id}: at least one evidence_id is required")
        for evidence_id in event_evidence:
            if evidence_id not in evidence_ids:
                errors.append(f"{case_id}/{event_id}: unknown evidence_id {evidence_id}")
        if set(tags) & set(taxonomy.get("always_human_review_tags") or []) and event.get("review_required") is not True:
            errors.append(f"{case_id}/{event_id}: always-review tag requires review_required=true")
    for tag in no_event_tags:
        if tag not in known_tags:
            errors.append(f"{case_id}: unknown no_event_tag {tag!r}")

    provenance = case.get("provenance") or {}
    for field in ("origin", "created_at", "adjudicated_by", "rationale"):
        if field not in provenance:
            errors.append(f"{case_id}: provenance.{field} is required")
    if status == "gold" and not provenance.get("adjudicated_by"):
        errors.append(f"{case_id}: gold row needs an adjudicator")
    return errors


def validate_dataset(rows: list[dict], taxonomy: dict, *, require_gold: bool = False) -> list[str]:
    errors: list[str] = []
    seen: set[str] = set()
    ticker_splits: dict[str, str] = {}
    source_splits: dict[str, str] = {}
    source_cases: dict[str, str] = {}
    hash_cases: dict[str, str] = {}
    for case in rows:
        errors.extend(validate_case(case, taxonomy, require_gold=require_gold))
        case_id = str(case.get("case_id") or "")
        if case_id in seen:
            errors.append(f"{case_id}: duplicate case_id")
        seen.add(case_id)
        if case.get("label_status") != "gold":
            continue
        split = str(case.get("split"))
        ticker = str(case.get("ticker") or "").upper()
        source = str((case.get("filing") or {}).get("source_ref") or "")
        if ticker in ticker_splits and ticker_splits[ticker] != split:
            errors.append(f"{case_id}: ticker leakage; {ticker} appears in {ticker_splits[ticker]} and {split}")
        ticker_splits[ticker] = split
        if source in source_splits and source_splits[source] != split:
            errors.append(f"{case_id}: source leakage across splits")
        if source in source_cases and source_cases[source] != case_id:
            errors.append(f"{case_id}: duplicate source filing already used by {source_cases[source]}")
        source_splits[source] = split
        source_cases[source] = case_id
        source_hash = str((case.get("filing") or {}).get("source_sha256") or "")
        if source_hash in hash_cases and hash_cases[source_hash] != case_id:
            errors.append(f"{case_id}: duplicate source hash already used by {hash_cases[source_hash]}")
        hash_cases[source_hash] = case_id
    return errors


def _filing_meta(doc: dict) -> dict | None:
    meta = dict(doc.get("filing_meta") or {})
    source = str(doc.get("source_text") or doc.get("source_filing_ref") or "")
    match = FILING_RE.search(source)
    if match:
        meta.setdefault("filing_form", match.group("form").upper())
        meta.setdefault("filing_date", _iso(match.group("filed")))
        meta.setdefault("period_end", _iso(match.group("period")))
        meta.setdefault("accession", match.group("accession").replace("_", "-"))
    if meta.get("filing_form") not in {"10-Q", "10-K"}:
        return None
    if not meta.get("filing_date") or not meta.get("period_end"):
        return None
    return meta


def _portfolio_tickers() -> set[str]:
    path = ROOT / "_system" / "portfolio" / "registry.json"
    if not path.exists():
        return set()
    doc = json.loads(path.read_text(encoding="utf-8"))
    return {str(t).upper() for group in ("holdings", "watchlist") for t in (doc.get(group) or {})}


def _fact_documents(universe: str, tickers: set[str]) -> list[tuple[Path, dict]]:
    allowed = tickers or (_portfolio_tickers() if universe == "portfolio" else set())
    by_source: dict[str, tuple[Path, dict]] = {}
    for ticker_dir in sorted(ROOT.iterdir()):
        if not ticker_dir.is_dir() or ticker_dir.name.startswith((".", "_")):
            continue
        if allowed and ticker_dir.name.upper() not in allowed:
            continue
        evidence = ticker_dir / "research" / "evidence"
        for path in sorted(evidence.glob("filing_facts_*.json")):
            try:
                doc = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            meta = _filing_meta(doc)
            if not meta:
                continue
            key = str(doc.get("source_filing_ref") or doc.get("source_text") or path)
            by_source[key] = (path, doc)
    return list(by_source.values())


def _source_text_path(ticker: str, source_text: str | None) -> Path | None:
    if not source_text:
        return None
    candidate = ROOT / ticker / "research" / source_text
    return candidate if candidate.exists() else None


def _metric_proposal(metric_name: str, metric: dict, config: dict) -> tuple[dict | None, str | None]:
    flags = set(metric.get("parser_flags") or [])
    if flags & SKIP_FLAGS:
        return None, "parser_hard_negative:" + ",".join(sorted(flags & SKIP_FLAGS))
    if str(metric.get("parser_confidence") or "").lower() != "high":
        return None, "parser_not_high_confidence"
    try:
        current = float(metric["current"])
        prior = float(metric["prior"])
    except (KeyError, TypeError, ValueError):
        return None, "missing_comparable_values"
    if prior == 0:
        return None, "zero_prior_requires_review"
    change = (current - prior) / abs(prior) * 100.0
    if abs(change) < float(config.get("min_abs_change_pct") or 0):
        return None, "below_materiality_threshold"
    tag = config["positive_tag"] if change > 0 else config["negative_tag"]
    direction = "strengthens" if change < 0 else "weakens"
    if tag == "debt_change":
        direction = "strengthens" if change > 0 else "weakens"
    elif tag in {"margin_expansion", "revenue_growth"}:
        direction = "weakens"
    elif tag in {"margin_contraction", "revenue_contraction"}:
        direction = "strengthens"
    return {
        "category": config["category"],
        "tags": [tag],
        "direction": direction,
        "severity": "high" if abs(change) >= 50 else "medium",
        "metric": metric_name,
        "prior_value": prior,
        "new_value": current,
        "change_pct": round(change, 2),
        "unit": "reported_units",
    }, None


def mine_candidates(*, universe: str, tickers: set[str], as_of: str, limit: int) -> list[dict]:
    taxonomy = load_taxonomy()
    metric_rules = taxonomy.get("metric_proposals") or {}
    cases: list[dict] = []
    for fact_path, doc in _fact_documents(universe, tickers):
        ticker = str(doc.get("ticker") or fact_path.parents[2].name).upper()
        meta = _filing_meta(doc)
        if not meta:
            continue
        evidence: list[dict] = []
        proposals: list[dict] = []
        mining_reasons: list[str] = []
        clean_evidence: list[dict] = []
        for metric_name, metric in sorted((doc.get("metrics") or {}).items()):
            if metric_name not in metric_rules or not isinstance(metric, dict):
                continue
            proposal, reason = _metric_proposal(metric_name, metric, metric_rules[metric_name])
            excerpt = str(metric.get("extract_snippet") or "").strip()
            if proposal:
                if not excerpt:
                    excerpt = f"{metric.get('tag') or metric_name}: {metric.get('current')}\n{metric.get('tag') or metric_name}: {metric.get('prior')}"
                evidence_id = f"ev-{metric_name}"
                evidence.append({
                    "evidence_id": evidence_id,
                    "locator": f"IX facts lines {metric.get('current_line', '?')}-{metric.get('prior_line', '?')}",
                    "excerpt": excerpt,
                    "content_sha256": _sha256(excerpt),
                })
                proposal["evidence_ids"] = [evidence_id]
                proposals.append(proposal)
            elif reason and reason.startswith("parser_hard_negative"):
                mining_reasons.append(f"{metric_name}:{reason}")
                if not excerpt:
                    excerpt = f"{metric.get('tag') or metric_name}: {metric.get('current')}\n{metric.get('tag') or metric_name}: {metric.get('prior')}"
                evidence_id = f"ev-{metric_name}-hard-negative"
                evidence.append({
                    "evidence_id": evidence_id,
                    "locator": f"IX fact neighborhood near lines {metric.get('current_line', '?')}-{metric.get('prior_line', '?')}",
                    "excerpt": excerpt,
                    "content_sha256": _sha256(excerpt),
                })
            elif reason == "below_materiality_threshold" and excerpt and len(clean_evidence) < 3:
                evidence_id = f"ev-{metric_name}-clean-control"
                clean_evidence.append({
                    "evidence_id": evidence_id,
                    "locator": f"IX facts lines {metric.get('current_line', '?')}-{metric.get('prior_line', '?')}",
                    "excerpt": excerpt,
                    "content_sha256": _sha256(excerpt),
                })
        if not proposals and not mining_reasons and clean_evidence:
            evidence.extend(clean_evidence)
            mining_reasons.append("clean_control:all_supported_metrics_below_threshold")
        if not proposals and not mining_reasons:
            continue
        source_text = str(doc.get("source_text") or "")
        extract_path = _source_text_path(ticker, source_text)
        extract_ref = f"{ticker}/research/{source_text}" if source_text else None
        source_ref = str(doc.get("source_filing_ref") or extract_ref or fact_path.relative_to(ROOT)).replace("\\", "/")
        source_path = ROOT / source_ref
        source_hash = _sha256(source_path.read_bytes()) if source_path.exists() else None
        extract_hash = _sha256(extract_path.read_bytes()) if extract_path else None
        raw_id = f"{ticker}|{meta['filing_form']}|{meta['filing_date']}|{source_ref}"
        case_id = f"fs-{ticker.lower().replace('.', '-')}-{meta['filing_date']}-{_sha256(raw_id)[:8]}"
        priority = sum(4 if p["severity"] == "high" else 2 for p in proposals) + 3 * len(mining_reasons)
        cases.append({
            "schema_version": 1,
            "case_id": case_id,
            "label_status": "candidate",
            "split": "_unassigned",
            "ticker": ticker,
            "filing": {
                "form": meta["filing_form"], "filed_at": meta["filing_date"],
                "period_end": meta["period_end"], "accession": meta.get("accession"),
                "source_ref": source_ref, "source_sha256": source_hash,
                "extract_ref": extract_ref, "extract_sha256": extract_hash,
                "comparison_source_ref": None, "comparison_sha256": None,
            },
            "evidence": evidence,
            "proposals": proposals,
            "mining_reasons": mining_reasons,
            "expected": {"events": [], "no_event_tags": [], "no_material_change": False},
            "candidate_priority": priority,
            "provenance": {
                "origin": str(fact_path.relative_to(ROOT)).replace("\\", "/"),
                "created_at": as_of, "adjudicated_by": [],
                "rationale": "Deterministically mined candidate; not a gold label.",
            },
        })
    cases.sort(key=lambda row: (-row["candidate_priority"], row["ticker"], row["case_id"]))
    return cases[:limit]


def _event_matches(gold: dict, predicted: dict) -> bool:
    return gold.get("category") == predicted.get("category") and bool(
        set(gold.get("tags") or []) & set(predicted.get("tags") or [])
    )


def evaluate(gold_rows: list[dict], prediction_rows: list[dict], taxonomy: dict, *, split: str | None = None) -> dict:
    predictions = {str(row.get("case_id")): row for row in prediction_rows}
    counts = Counter()
    weighted_total = 0
    weighted_found = 0
    direction_total = 0
    direction_correct = 0
    citation_total = 0
    citation_valid = 0
    category_counts: dict[str, Counter] = defaultdict(Counter)
    form_counts: dict[str, Counter] = defaultdict(Counter)
    tag_counts: dict[str, Counter] = defaultdict(Counter)
    severity_counts: dict[str, Counter] = defaultdict(Counter)
    zero_cases = 0
    zero_correct = 0
    forbidden_tag_violations = 0
    review_required_total = 0
    review_required_found = 0
    critical_gold = 0
    critical_found = 0
    weights = taxonomy.get("severity_weights") or {}
    cases = [row for row in gold_rows if row.get("label_status") == "gold" and (split is None or row.get("split") == split)]
    for case in cases:
        gold_events = list((case.get("expected") or {}).get("events") or [])
        predicted_events = list((predictions.get(case["case_id"]) or {}).get("events") or [])
        form = str((case.get("filing") or {}).get("form") or "unknown")
        valid_evidence = {item["evidence_id"] for item in case.get("evidence") or []}
        forbidden_tags = set((case.get("expected") or {}).get("no_event_tags") or [])
        forbidden_tag_violations += sum(
            len(set(predicted.get("tags") or []) & forbidden_tags) for predicted in predicted_events
        )
        unmatched = set(range(len(predicted_events)))
        if not gold_events:
            zero_cases += 1
            if not predicted_events:
                zero_correct += 1
        for gold_event in gold_events:
            weight = int(weights.get(gold_event.get("severity"), 1))
            weighted_total += weight
            category = str(gold_event.get("category"))
            category_counts[category]["gold"] += 1
            form_counts[form]["gold"] += 1
            severity_counts[str(gold_event.get("severity") or "unknown")]["gold"] += 1
            for tag in gold_event.get("tags") or []:
                tag_counts[str(tag)]["gold"] += 1
            if gold_event.get("severity") == "critical":
                critical_gold += 1
            if gold_event.get("review_required"):
                review_required_total += 1
            match_idx = next((idx for idx in unmatched if _event_matches(gold_event, predicted_events[idx])), None)
            if match_idx is None:
                counts["fn"] += 1
                category_counts[category]["fn"] += 1
                form_counts[form]["fn"] += 1
                severity_counts[str(gold_event.get("severity") or "unknown")]["fn"] += 1
                for tag in gold_event.get("tags") or []:
                    tag_counts[str(tag)]["fn"] += 1
                continue
            unmatched.remove(match_idx)
            predicted = predicted_events[match_idx]
            counts["tp"] += 1
            category_counts[category]["tp"] += 1
            form_counts[form]["tp"] += 1
            severity_counts[str(gold_event.get("severity") or "unknown")]["tp"] += 1
            for tag in gold_event.get("tags") or []:
                tag_counts[str(tag)]["tp"] += 1
            weighted_found += weight
            if gold_event.get("severity") == "critical":
                critical_found += 1
            if gold_event.get("review_required") and predicted.get("review_required") is True:
                review_required_found += 1
            direction_total += 1
            direction_correct += int(predicted.get("direction") == gold_event.get("direction"))
        counts["fp"] += len(unmatched)
        for idx, predicted in enumerate(predicted_events):
            evidence_ids = set(predicted.get("evidence_ids") or [])
            citation_total += 1
            if evidence_ids and evidence_ids <= valid_evidence:
                citation_valid += 1
            if idx in unmatched:
                predicted_category = str(predicted.get("category") or "unknown")
                category_counts[predicted_category]["fp"] += 1
                form_counts[form]["fp"] += 1
                severity_counts[str(predicted.get("severity") or "unknown")]["fp"] += 1
                for tag in predicted.get("tags") or []:
                    tag_counts[str(tag)]["fp"] += 1

    tp, fp, fn = counts["tp"], counts["fp"], counts["fn"]
    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    all_gold_ids = {str(case.get("case_id")) for case in gold_rows if case.get("label_status") == "gold"}
    unknown_case_rows = sum(1 for row in prediction_rows if str(row.get("case_id")) not in all_gold_ids)
    metrics = {
        "cases": len(cases), "gold_events": tp + fn, "predicted_events": tp + fp,
        "true_positives": tp, "false_positives": fp, "false_negatives": fn,
        "precision": round(precision, 4), "recall": round(recall, 4), "f1": round(f1, 4),
        "severity_weighted_recall": round(weighted_found / weighted_total, 4) if weighted_total else 1.0,
        "critical_recall": round(critical_found / critical_gold, 4) if critical_gold else 1.0,
        "citation_precision": round(citation_valid / citation_total, 4) if citation_total else 1.0,
        "direction_accuracy": round(direction_correct / direction_total, 4) if direction_total else 1.0,
        "false_alerts_per_filing": round(fp / len(cases), 4) if cases else 0.0,
        "clean_filing_accuracy": round(zero_correct / zero_cases, 4) if zero_cases else 1.0,
        "review_required_recall": round(review_required_found / review_required_total, 4) if review_required_total else 1.0,
        "forbidden_tag_violations": forbidden_tag_violations,
        "unknown_case_rows": unknown_case_rows,
    }
    gates = taxonomy.get("evaluation_gates") or {}
    gate_results = {
        "precision": metrics["precision"] >= float(gates.get("precision_min", 0)),
        "recall": metrics["recall"] >= float(gates.get("recall_min", 0)),
        "critical_recall": metrics["critical_recall"] >= float(gates.get("critical_recall_min", 0)),
        "citation_precision": metrics["citation_precision"] >= float(gates.get("citation_precision_min", 0)),
        "false_alerts_per_filing": metrics["false_alerts_per_filing"] <= float(gates.get("false_alerts_per_filing_max", 999)),
        "forbidden_tag_violations": metrics["forbidden_tag_violations"] <= int(gates.get("forbidden_tag_violations_max", 0)),
        "unknown_case_rows": metrics["unknown_case_rows"] <= int(gates.get("unknown_case_rows_max", 0)),
    }
    return {
        "schema_version": 1, "split": split or "all", "metrics": metrics,
        "gates": gate_results, "passed": all(gate_results.values()),
        "by_category": {key: dict(value) for key, value in sorted(category_counts.items())},
        "by_form": {key: dict(value) for key, value in sorted(form_counts.items())},
        "by_tag": {key: dict(value) for key, value in sorted(tag_counts.items())},
        "by_severity": {key: dict(value) for key, value in sorted(severity_counts.items())},
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate", help="Validate schema, evidence hashes, taxonomy, and split leakage")
    validate.add_argument("--dataset", type=Path, default=DEFAULT_GOLD)
    validate.add_argument("--require-gold", action="store_true")
    mine = sub.add_parser("mine", help="Mine deterministic filing candidates; never auto-promotes them")
    mine.add_argument("--output", type=Path)
    mine.add_argument("--universe", choices=("portfolio", "all"), default="portfolio")
    mine.add_argument("--ticker", action="append", default=[])
    mine.add_argument("--as-of", default=date.today().isoformat())
    mine.add_argument("--limit", type=int, default=100)
    mine.add_argument("--dry-run", action="store_true")
    score = sub.add_parser("evaluate", help="Score prediction JSONL against locked gold labels")
    score.add_argument("--gold", type=Path, default=DEFAULT_GOLD)
    score.add_argument("--predictions", type=Path, required=True)
    score.add_argument("--split", choices=("train", "dev", "test"))
    score.add_argument("--output", type=Path)
    score.add_argument("--strict", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    taxonomy = load_taxonomy()
    if args.command == "validate":
        rows = read_jsonl(args.dataset)
        errors = validate_dataset(rows, taxonomy, require_gold=args.require_gold)
        if errors:
            print("\n".join(f"ERROR {error}" for error in errors), file=sys.stderr)
            return 1
        print(f"OK: {len(rows)} filing sentinel cases validated")
        return 0
    if args.command == "mine":
        rows = mine_candidates(
            universe=args.universe, tickers={t.upper() for t in args.ticker},
            as_of=args.as_of, limit=max(1, args.limit),
        )
        output = args.output or ROOT / "_system" / "reviews" / "pending" / f"filing_sentinel_candidates_{args.as_of}.jsonl"
        if not args.dry_run:
            write_jsonl(output, rows)
        print(json.dumps({"candidates": len(rows), "output": None if args.dry_run else str(output)}, indent=2))
        return 0
    gold_rows = read_jsonl(args.gold)
    errors = validate_dataset(gold_rows, taxonomy, require_gold=True)
    if errors:
        print("\n".join(f"ERROR {error}" for error in errors), file=sys.stderr)
        return 1
    report = evaluate(gold_rows, read_jsonl(args.predictions), taxonomy, split=args.split)
    rendered = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 1 if args.strict and not report["passed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

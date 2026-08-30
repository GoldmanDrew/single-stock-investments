#!/usr/bin/env python3
"""Validate dashboard_data.json against registry holdings and deep dive files."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))
from vault_paths import letters_root  # noqa: E402
from activist_common import classify_publisher_page  # noqa: E402
DATA_PATH = ROOT / "dashboard" / "data" / "dashboard_data.json"
CORE_PATH = ROOT / "dashboard" / "data" / "core.json"
REGISTRY_PATH = ROOT / "_system" / "portfolio" / "registry.json"
RETURN_PUBLISHABLE_MODEL_LEVELS = {
    "stock_specific", "committee_reviewed", "owner_approved",
}
MODEL_LEVELS = {
    "unmodeled", "evidence_blocked", "screening_grade",
    *RETURN_PUBLISHABLE_MODEL_LEVELS,
}


def extreme_return_corroborated(
    ticker: str, root: Path | None = None, decision: dict | None = None
) -> bool:
    """Has this outlier passed the contract's own outlier validation?

    The IRR check is named for *uncorroborated* returns, but it used to flag
    every extreme return whether or not it had been corroborated, so the escape
    hatch the contract layer defines was unreachable from here -- and because
    the resulting error fails the build step, it skipped the Cloudflare deploy
    entirely.

    universal_valuation_contract already computes the verdict:
    model_checks.extreme_return_validated is true only when
    valuation_methodology.outlier_validation has status "passed", at least one
    independent method, and evidence refs. Read that rather than re-deriving it,
    so there is exactly one definition of a corroborated outlier.
    """
    # This validator normally runs in the sparse "pages" checkout, which has no
    # ticker trees, so the payload field is authoritative when present and the
    # contract file is only a fallback for full-checkout runs.
    # NB: model_checks.extreme_return_validated means "not extreme OR validated",
    # so it is only meaningful here because universal_valuation_contract's
    # EXTREME_RETURN_PCT and this module's EXTREME_PUBLISHED_IRR_PCT are both
    # 25.0. If they ever diverge, a return could be extreme by this module's
    # threshold, non-extreme by the contract's, and get cleared without any
    # corroboration. test_thresholds_agree pins them together.
    if decision is not None and "extreme_return_validated" in decision:
        return bool(decision.get("extreme_return_validated"))
    base = root or ROOT
    if not ticker:
        return False
    path = base / ticker / "research" / "valuation_contract.json"
    if not path.exists():
        return False
    try:
        contract = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return False
    return bool((contract.get("model_checks") or {}).get("extreme_return_validated"))
INSIGHTS_PATH = ROOT / "dashboard" / "data" / "insights.json"
INSIGHTS_DIR = ROOT / "dashboard" / "data" / "insights"
ACTIVIST_FEED_PATH = ROOT / "dashboard" / "data" / "activist_feed.json"
INDEX_MEMBERSHIP_PATH = ROOT / "dashboard" / "data" / "index_membership.json"
INDEX_STATUS_ENUM = {"member", "inclusion_candidate", "deletion_risk", "ineligible", "n_a"}
CONFLICT_MARKERS = ("<<<<<<<", "=======", ">>>>>>>")
MIN_LETTER_CORPUS = 15000
MIN_LETTER_LINKS_RATIO = 0.99
# Guard against sparse CI rebuilds publishing empty holdings infra.
MIN_TOTAL_PDFS_FLOOR = 100
MIN_RESEARCH_DIR_RATIO = 0.10
GITHUB_HARD_LIMIT_BYTES = 100 * 1024 * 1024
GITHUB_WARN_LIMIT_BYTES = 50 * 1024 * 1024
# Sharded payload budgets: keep first paint fast as the universe grows.
CORE_MAX_MB = 6.0
TICKER_SHARD_MAX_MB = 2.0
EXTREME_PUBLISHED_IRR_PCT = 25.0


def pages_deploy_only() -> bool:
    """True when CI is publishing committed dashboard/ without a data rebuild."""
    return os.environ.get("CI_PAGES_DEPLOY_ONLY", "").lower() in {"1", "true", "yes"}


def resolve_payload_path(
    *,
    monolith: Path = DATA_PATH,
    core: Path = CORE_PATH,
    deploy_only: bool | None = None,
) -> Path | None:
    """Pick the JSON the SPA actually boots from.

    dashboard_data.json is a gitignored build intermediate. Cloudflare Pages
    loads core.json. Deploy-only CI therefore must not require the monolith.
    """
    use_deploy_only = pages_deploy_only() if deploy_only is None else deploy_only
    if use_deploy_only and core.exists():
        return core
    if monolith.exists():
        return monolith
    return None


def sparse_checkout_enabled(root: Path = ROOT) -> bool:
    """Return whether Git intentionally omitted tracked files from this worktree."""
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "config", "--bool", "core.sparseCheckout"],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return False
    return result.returncode == 0 and result.stdout.strip().lower() == "true"


def repository_file_exists(root: Path, relative_path: str) -> bool:
    """Accept a materialized file, or a tracked file omitted by sparse checkout."""
    normalized = str(relative_path).replace("\\", "/").lstrip("/")
    if (root / normalized).exists():
        return True
    if not sparse_checkout_enabled(root):
        return False
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "ls-files", "--error-unmatch", "--", normalized],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        return False
    return result.returncode == 0


def letter_drive_links_issue(
    *,
    matched: int,
    letter_index_len: int,
    links_letter_count: int,
    corpus_preserved: bool,
) -> tuple[str, str] | None:
    """Return (severity, message) when letter_drive_links lags the insights corpus."""
    if matched <= 0 or letter_index_len <= 0:
        return None
    compare_len = letter_index_len
    if corpus_preserved and links_letter_count > 0:
        compare_len = links_letter_count
    insights_ratio = matched / compare_len
    if insights_ratio >= MIN_LETTER_LINKS_RATIO:
        return None
    internal_ratio = matched / links_letter_count if links_letter_count > 0 else 0.0
    links_cover_smaller_corpus = (
        links_letter_count > 0
        and letter_index_len > int(links_letter_count * 1.05)
        and internal_ratio >= MIN_LETTER_LINKS_RATIO
    )
    msg = (
        f"letter_drive_links matched {matched}/{compare_len} ({insights_ratio:.1%}); "
        "run make letter-backfill"
    )
    if corpus_preserved and compare_len != letter_index_len:
        return "warn", f"{msg} (vault subset; committed letter corpus preserved for deploy)"
    if links_cover_smaller_corpus:
        return (
            "warn",
            f"{msg} (links current for {links_letter_count} letters; insights index has {letter_index_len})",
        )
    return "error", msg


def _check_merge_conflict_markers(path: Path) -> str | None:
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    for marker in CONFLICT_MARKERS:
        if marker in text:
            return f"{path.relative_to(ROOT)} contains unresolved git merge conflict markers"
    return None


def main() -> int:
    errors: list[str] = []
    warnings: list[str] = []
    deploy_only = pages_deploy_only()

    payload_path = resolve_payload_path(deploy_only=deploy_only)
    if payload_path is None:
        print(f"ERROR: missing {DATA_PATH}", file=sys.stderr)
        if deploy_only:
            print(
                "ERROR: dashboard/data/core.json also missing; cannot validate a pages deploy",
                file=sys.stderr,
            )
        return 1
    if payload_path == CORE_PATH:
        warnings.append(
            "Deploy-only mode: validating dashboard/data/core.json, the SPA boot payload"
        )

    for path in (payload_path, INSIGHTS_PATH, ACTIVIST_FEED_PATH):
        conflict = _check_merge_conflict_markers(path)
        if conflict:
            errors.append(conflict)
    if errors:
        for msg in errors:
            print(f"ERROR: {msg}", file=sys.stderr)
        return 1

    if payload_path == DATA_PATH:
        data_size = payload_path.stat().st_size
        if data_size > GITHUB_HARD_LIMIT_BYTES:
            errors.append(
                f"dashboard_data.json is {data_size / (1024 * 1024):.1f}MB; exceeds GitHub 100MB limit"
            )
        elif data_size > GITHUB_WARN_LIMIT_BYTES:
            warnings.append(
                f"dashboard_data.json is {data_size / (1024 * 1024):.1f}MB; above GitHub 50MB recommendation"
            )

    def fail(msg: str) -> None:
        """Hard error normally; warning on deploy-only so UI ships while data pipeline catches up."""
        if deploy_only:
            warnings.append(msg)
        else:
            errors.append(msg)

    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    if payload.get("insights"):
        errors.append(
            "dashboard_data.json must not embed insights; load dashboard/data/insights/ shards separately"
        )
    if payload.get("research_memory"):
        errors.append(
            "dashboard_data.json must not embed research_memory; load dashboard/data/research_memory.json separately"
        )
    memory_ref = payload.get("research_memory_ref") or {}
    if memory_ref and not memory_ref.get("path"):
        errors.append("research_memory_ref missing path")
    insights_ref = payload.get("insights_ref") or {}
    if insights_ref and not insights_ref.get("path"):
        errors.append("insights_ref missing path")

    insights = {}
    if INSIGHTS_PATH.exists():
        insights_size = INSIGHTS_PATH.stat().st_size
        if insights_size >= GITHUB_HARD_LIMIT_BYTES:
            errors.append(
                f"insights.json is {insights_size / (1024 * 1024):.1f}MB and exceeds GitHub's 100MB limit"
            )
        elif insights_size >= 95 * 1024 * 1024:
            warnings.append(
                f"insights.json is {insights_size / (1024 * 1024):.1f}MB; reduce retained event history before it reaches 100MB"
            )
        raw_insights = INSIGHTS_PATH.read_text(encoding="utf-8")
        if "<<<<<<<" in raw_insights or ">>>>>>>" in raw_insights:
            errors.append(f"{INSIGHTS_PATH} contains unresolved git merge conflict markers")
        else:
            insights = json.loads(raw_insights)
    elif (INSIGHTS_DIR / "manifest.json").exists():
        shard_paths = sorted(INSIGHTS_DIR.glob("*.json"))
        total_size = sum(path.stat().st_size for path in shard_paths)
        if total_size >= GITHUB_HARD_LIMIT_BYTES:
            errors.append(
                f"insights shards total {total_size / (1024 * 1024):.1f}MB and exceed GitHub's 100MB limit"
            )
        for path in shard_paths:
            raw_shard = path.read_text(encoding="utf-8")
            if any(marker in raw_shard for marker in CONFLICT_MARKERS):
                errors.append(f"{path} contains unresolved git merge conflict markers")
                continue
            try:
                shard = json.loads(raw_shard)
            except json.JSONDecodeError:
                errors.append(f"{path} is invalid JSON")
                continue
            if isinstance(shard, dict):
                insights.update(shard)
    else:
        errors.append("missing dashboard insights payload")
    holdings = sorted((registry.get("holdings") or {}).keys())
    front_tickers = set(holdings) | set((registry.get("watchlist") or {}).keys())
    rows = payload.get("tickers") or []
    dash_tickers = [r.get("ticker") for r in rows]
    extreme_decision_grade = []
    corroborated_outliers = []
    blocked_with_published_irr = []
    noncanonical_aliases = []
    invalid_tiers = []
    missing_tiers = []
    invalid_model_levels = []
    present_value_return_leaks = []

    for row in rows:
        decision = row.get("valuation_decision") or {}
        returns = decision.get("forward_return_at_price_pct") or {}
        alias = decision.get("annualized_return_at_price_pct")
        if alias not in (None, returns):
            noncanonical_aliases.append(str(row.get("ticker") or ""))
        tier = (row.get("valuation_tier") or {}).get("tier")
        if tier is None:
            missing_tiers.append(str(row.get("ticker") or ""))
        elif tier not in {1, 2, 3}:
            invalid_tiers.append(f"{row.get('ticker')}={tier}")
        model_level = decision.get("model_level")
        if model_level not in MODEL_LEVELS:
            invalid_model_levels.append(f"{row.get('ticker')}={model_level}")
        if decision.get("output_basis") == "present_value_today" and any(
            returns.get(case) is not None for case in ("low", "base", "high")
        ):
            present_value_return_leaks.append(str(row.get("ticker") or ""))
        base_return = returns.get("base")
        if base_return is None:
            continue
        ticker = str(row.get("ticker") or "")
        if (
            decision.get("status") != "decision_grade"
            or decision.get("model_level") not in RETURN_PUBLISHABLE_MODEL_LEVELS
            or not decision.get("return_publishable")
            or decision.get("forward_return_status") != "available"
        ):
            blocked_with_published_irr.append(ticker)
        elif abs(float(base_return)) >= EXTREME_PUBLISHED_IRR_PCT:
            entry = f"{ticker}={float(base_return):.2f}%"
            if extreme_return_corroborated(ticker, decision=decision):
                corroborated_outliers.append(entry)
            else:
                extreme_decision_grade.append(entry)
    if blocked_with_published_irr:
        errors.append(
            "Non-publishable valuations expose front-page forward returns: "
            + ", ".join(blocked_with_published_irr[:20])
        )
    if noncanonical_aliases:
        errors.append(
            "Deprecated annualized-return aliases differ from canonical forward returns: "
            + ", ".join(noncanonical_aliases[:20])
        )
    if invalid_tiers:
        errors.append(
            "Invalid valuation-universe tiers: " + ", ".join(invalid_tiers[:20])
        )
    if missing_tiers:
        errors.append(
            "Dashboard rows missing valuation-universe tiers: " + ", ".join(missing_tiers[:20])
        )
    if invalid_model_levels:
        errors.append(
            "Dashboard rows have invalid valuation model levels: "
            + ", ".join(invalid_model_levels[:20])
        )
    if present_value_return_leaks:
        errors.append(
            "Present-value contracts expose forward returns: "
            + ", ".join(present_value_return_leaks[:20])
        )
    if extreme_decision_grade:
        errors.append(
            "Decision-grade valuations exceed the uncorroborated IRR limit: "
            + ", ".join(extreme_decision_grade[:20])
        )
    if corroborated_outliers:
        # Still surfaced: these are outliers a human should keep an eye on, they
        # just are not defects, so they must not fail the build and block deploys.
        warnings.append(
            "Extreme IRRs cleared by outlier_validation (human review advised): "
            + ", ".join(corroborated_outliers[:20])
        )
    summary = payload.get("summary") or {}
    ticker_count = int(summary.get("ticker_count") or len(rows) or 0)
    total_pdfs = int(summary.get("total_pdfs") or 0)
    with_research = int(summary.get("with_research") or 0)
    if ticker_count >= 50 and total_pdfs < MIN_TOTAL_PDFS_FLOOR:
        errors.append(
            f"summary.total_pdfs={total_pdfs} below floor {MIN_TOTAL_PDFS_FLOOR} for "
            f"{ticker_count} tickers - sparse rebuild likely clobbered holdings infra"
        )
    if ticker_count >= 50 and with_research < max(1, int(ticker_count * MIN_RESEARCH_DIR_RATIO)):
        errors.append(
            f"summary.with_research={with_research} too low for {ticker_count} tickers "
            f"(need >= {MIN_RESEARCH_DIR_RATIO:.0%}) - sparse rebuild likely clobbered infra"
        )

    for pseudo in dash_tickers:
        if not pseudo or pseudo.startswith("_"):
            errors.append(f"pseudo-ticker in dashboard: {pseudo}")

    missing = sorted(set(holdings) - set(dash_tickers))
    extra = sorted(set(dash_tickers) - set(holdings))
    if missing:
        fail(f"registry holdings missing from dashboard: {', '.join(missing)}")
    if extra:
        fail(f"dashboard tickers not in registry: {', '.join(extra)}")

    for row in rows:
        ticker = row.get("ticker")
        if not ticker or ticker.startswith("_"):
            continue
        research = ROOT / ticker / "research"
        dive_files = sorted(research.glob("deep_dive_*.md")) if research.is_dir() else []
        dd = row.get("deep_dive")
        if dive_files and not dd:
            errors.append(f"{ticker}: deep_dive_*.md on disk but deep_dive missing in JSON")
        elif dive_files and dd:
            latest = max(dive_files, key=lambda p: p.name)
            expected = str(latest.relative_to(ROOT)).replace("\\", "/")
            if dd.get("path") != expected:
                errors.append(f"{ticker}: stale deep_dive path {dd.get('path')} (expected {expected})")
            if not dd.get("github_url"):
                errors.append(f"{ticker}: deep_dive missing github_url")
            if not dd.get("executive_summary"):
                warnings.append(f"{ticker}: deep_dive has no executive_summary")

        lenses = row.get("lenses")
        ds = row.get("decision_summary")
        if lenses and not ds:
            errors.append(f"{ticker}: lenses present but decision_summary missing")
        elif ds:
            for key in (
                "stance",
                "stance_source",
                "house_irr_pct",
                "lens_blend_pct",
                "agreement_pct",
                "as_of",
            ):
                if key not in ds:
                    errors.append(f"{ticker}: decision_summary missing key {key}")
        if lenses is not None and "active_lenses" not in row:
            errors.append(f"{ticker}: lenses present but active_lenses missing")
        if lenses is not None and "silent_lens_count" not in row:
            errors.append(f"{ticker}: lenses present but silent_lens_count missing")

        onboard = row.get("onboard") or {}
        if onboard.get("deep_dive_pending") is False and dive_files and not dd:
            errors.append(f"{ticker}: onboard marks deep dive complete but JSON has no deep_dive")

    if insights:
        for key in ("events", "events_by_ticker", "source_health", "provenance"):
            if key not in insights:
                errors.append(f"insights missing key {key}")
        events = insights.get("events") or []
        if not isinstance(events, list):
            errors.append("insights.events must be a list")
        elif not events:
            warnings.append("insights.events is empty")
        else:
            required = (
                "id",
                "source",
                "event_type",
                "impact_axis",
                "title",
                "summary",
                "score",
                "tier",
                "materiality",
                "triage_verdict",
                "feed_eligible",
            )
            for idx, event in enumerate(events[:50]):
                for key in required:
                    if key not in event:
                        errors.append(f"insights.events[{idx}] missing key {key}")
                if event.get("ticker") and event["ticker"] not in front_tickers:
                    warnings.append(f"insights event references non-portfolio ticker {event['ticker']}")
            triage_summary = (insights.get("provenance") or {}).get("event_triage_summary") or {}
            if not triage_summary:
                warnings.append("insights provenance missing event_triage_summary")
            else:
                tier_sum = sum(int(triage_summary.get(k) or 0) for k in ("signal", "context", "noise"))
                if tier_sum != len(events):
                    warnings.append(
                        f"event triage summary counts ({tier_sum}) != events list ({len(events)})"
                    )
                signal_n = int(triage_summary.get("signal") or 0)
                if events and signal_n == 0:
                    warnings.append("event triage: zero signal-tier events in feed")
                if events and signal_n / len(events) > 0.35:
                    warnings.append(
                        f"event triage: signal tier {signal_n}/{len(events)} "
                        f"({100 * signal_n / len(events):.0f}%) may be over-promoted"
                    )
                for idx, event in enumerate(events[:100]):
                    if event.get("tier") == "signal" and event.get("source") == "filing":
                        conf = str(
                            (event.get("verification") or {}).get("parser_confidence")
                            or event.get("confidence")
                            or ""
                        ).lower()
                        if conf == "low":
                            warnings.append(
                                f"insights.events[{idx}] signal filing with low parser confidence "
                                f"({event.get('ticker')})"
                            )
                    if event.get("feed_eligible") and event.get("tier") == "noise":
                        errors.append(f"insights.events[{idx}] noise tier marked feed_eligible")
                    if event.get("triage_verdict") is None:
                        errors.append(f"insights.events[{idx}] missing triage_verdict")
                    for key in (
                        "decision_priority",
                        "event_kind",
                        "portfolio_scope",
                        "template_id",
                        "story_id",
                        "evidence_status",
                        "why_it_matters",
                        "recommended_follow_up",
                    ):
                        if key not in event:
                            errors.append(f"insights.events[{idx}] missing decision-feed field {key}")
                    if event.get("tier") == "signal" and event.get("evidence_status") == "missing":
                        warnings.append(
                            f"insights.events[{idx}] signal explicitly missing evidence ({event.get('ticker')})"
                        )
                    if event.get("tier") == "signal" and event.get("entity_verified") is False:
                        errors.append(f"insights.events[{idx}] entity-mismatched event promoted to signal")
                    if (
                        event.get("tier") == "signal"
                        and event.get("event_kind") == "scheduled"
                        and event.get("direction") in {None, "neutral"}
                    ):
                        errors.append(f"insights.events[{idx}] neutral scheduled event promoted to signal")
                if events and not triage_summary.get("history_start"):
                    errors.append("event triage summary missing history_start")
                if events and not triage_summary.get("history_end"):
                    errors.append("event triage summary missing history_end")
                if int(triage_summary.get("retained_event_count") or 0) != len(events):
                    errors.append("event triage retained_event_count does not match events list")
        if "records" in insights:
            errors.append("insights payload should not include raw records; use record_archive.path")
        archive = insights.get("record_archive") or {}
        if not archive.get("path"):
            errors.append("insights missing record_archive.path")
        source_health = insights.get("source_health") or {}
        if not isinstance(source_health, dict):
            errors.append("insights.source_health must be an object")
        elif "filing_facts" not in source_health or "portfolio_news" not in source_health:
            errors.append("insights.source_health missing expected local sources")
        letter_count = insights.get("letter_count") or 0
        letter_index_len = len(insights.get("letter_index") or [])
        classification_policy_version = int(insights.get("classification_policy_version") or 0)
        min_letter_corpus = 12000 if classification_policy_version >= 4 else MIN_LETTER_CORPUS
        if letter_count < min_letter_corpus or letter_index_len < min_letter_corpus:
            errors.append(
                f"letter corpus {letter_count} (index {letter_index_len}) below minimum "
                f"{min_letter_corpus}; deploy rebuild must preserve committed corpus or refresh vault"
            )
        manifest_path = letters_root() / "drive_import_manifest.json"
        manifest_count = 0
        if manifest_path.exists():
            try:
                manifest_count = int(json.loads(manifest_path.read_text(encoding="utf-8")).get("file_count") or 0)
            except (json.JSONDecodeError, TypeError, ValueError):
                pass
        if manifest_count > 0 and letter_index_len == 0:
            errors.append(
                f"letter_index empty but drive_import_manifest has {manifest_count} files; run make letter-backfill"
            )
        elif letter_count == 0:
            errors.append("superinvestor letters empty — run make letter-import-drive")
        letters_dir = letters_root()
        if letters_dir.is_dir():
            pdfs_needing_text = 0
            for qdir in letters_dir.iterdir():
                if not qdir.is_dir() or not qdir.name[:2].isdigit():
                    continue
                for pdf in qdir.glob("*.pdf"):
                    txt = pdf.with_suffix(".txt")
                    try:
                        if not txt.exists() or txt.stat().st_mtime < pdf.stat().st_mtime:
                            pdfs_needing_text += 1
                    except OSError:
                        pdfs_needing_text += 1
            if pdfs_needing_text > 0:
                warnings.append(
                    f"{pdfs_needing_text} letter PDF(s) missing text extracts — run make letter-extract-text"
                )
        max_sane_year = datetime.now(timezone.utc).year + 1
        bad_quarters = [
            row.get("quarter")
            for row in (insights.get("letter_index") or [])
            if row.get("quarter") and str(row.get("quarter"))[:4].isdigit()
            and int(str(row.get("quarter"))[:4]) > max_sane_year
        ]
        if bad_quarters:
            errors.append(
                f"insights letter_index has {len(bad_quarters)} future quarter(s); run repair_letter_dates + rebuild"
            )
        time_periods = insights.get("time_periods") or {}
        if not time_periods.get("latest_indexed_quarter"):
            warnings.append("insights.time_periods.latest_indexed_quarter missing — run build_insights.py")
        theme_by_q = insights.get("theme_rankings_by_quarter") or {}
        sample_q = time_periods.get("latest_indexed_quarter")
        if sample_q and isinstance(theme_by_q.get(sample_q), list):
            theme_rows = theme_by_q[sample_q]
            if len(theme_rows) >= 3:
                top_sets = [tuple(r.get("top_tickers") or []) for r in theme_rows[:3]]
                if len({s for s in top_sets if s}) == 1 and len(top_sets[0]) >= 3:
                    warnings.append(
                        f"theme top_tickers identical across first 3 themes in {sample_q}; "
                        "run make letter-rebuild after proximity tagging fix"
                    )
        catalog_path = ROOT / "dashboard" / "data" / "document_catalog.json"
        if catalog_path.exists():
            try:
                catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
                cat_latest = ((catalog.get("time_periods") or {}).get("latest_catalog_quarter")
                                or (catalog.get("time_periods") or {}).get("latest_quarter"))
                idx_latest = time_periods.get("latest_indexed_quarter")
                if cat_latest and idx_latest and cat_latest != idx_latest:
                    cat_year = int(str(cat_latest)[:4]) if str(cat_latest)[:4].isdigit() else 0
                    idx_year = int(str(idx_latest)[:4]) if str(idx_latest)[:4].isdigit() else 0
                    if cat_year > idx_year + 1:
                        warnings.append(
                            f"document catalog latest ({cat_latest}) far ahead of indexed latest ({idx_latest}); "
                            "check document_date fiscal parsing"
                        )
            except (json.JSONDecodeError, TypeError, ValueError):
                pass
        bad_letter_dates = []
        mtime_dates = []
        low_confidence_dates = []
        for row in insights.get("letter_index") or []:
            letter_date = row.get("letter_date") or ""
            quarter = row.get("quarter") or ""
            if len(letter_date) >= 4 and letter_date[:4].isdigit():
                date_year = int(letter_date[:4])
                if date_year > max_sane_year:
                    bad_letter_dates.append(row)
                elif len(quarter) >= 4 and quarter[:4].isdigit():
                    quarter_year = int(quarter[:4])
                    if date_year - quarter_year >= 2:
                        bad_letter_dates.append(row)
            if row.get("date_source") == "mtime":
                mtime_dates.append(row)
            conf = row.get("date_confidence")
            if conf is not None and int(conf) < 50:
                low_confidence_dates.append(row)
        if bad_letter_dates:
            errors.append(
                f"insights letter_index has {len(bad_letter_dates)} implausible letter_date(s); "
                "run repair_letter_dates.py --apply && make letter-rebuild"
            )
        if mtime_dates:
            warnings.append(
                f"{len(mtime_dates)} letter(s) still use mtime as letter_date; run repair_letter_dates + rebuild"
            )
        if low_confidence_dates:
            warnings.append(
                f"{len(low_confidence_dates)} letter(s) have date_confidence < 50"
            )
        links_path = ROOT / "_system/reference/document-store/letter_drive_links.json"
        si_health = (insights.get("source_health") or {}).get("superinvestor_letters") or {}
        corpus_preserved = si_health.get("status") == "preserved"
        if links_path.exists() and letter_index_len > 0:
            try:
                links_doc = json.loads(links_path.read_text(encoding="utf-8"))
                matched = int(links_doc.get("matched_count") or 0)
                if matched == 0:
                    msg = "letter_drive_links matched_count=0 — run make letter-backfill"
                    (warnings if corpus_preserved else errors).append(msg)
                elif letters_root().exists():
                    links_letter_count = int(links_doc.get("letter_count") or 0)
                    issue = letter_drive_links_issue(
                        matched=matched,
                        letter_index_len=letter_index_len,
                        links_letter_count=links_letter_count,
                        corpus_preserved=corpus_preserved,
                    )
                    if issue:
                        severity, msg = issue
                        (warnings if severity == "warn" else errors).append(msg)
            except json.JSONDecodeError:
                warnings.append("letter_drive_links.json is invalid JSON")
        provenance = insights.get("provenance") or {}
        if provenance.get("schema_version") != 2:
            errors.append("insights provenance schema_version must be 2")
        pos_pct = provenance.get("letters_with_positions_pct")
        if pos_pct is not None and float(pos_pct) < 0.25:
            warnings.append(
                f"letters_with_positions_pct={float(pos_pct):.1%} below 25% floor — check letter_matching / holdings parser"
            )
        pending_legacy = list((ROOT / "_system/reviews/pending").glob("activist_scan_*.md"))
        if pending_legacy:
            warnings.append(
                f"legacy activist_scan review queues still present ({len(pending_legacy)}); delete per pending/README.md"
            )

    if ACTIVIST_FEED_PATH.exists():
        activist = json.loads(ACTIVIST_FEED_PATH.read_text(encoding="utf-8"))
        feed = activist.get("feed") or []
        review_queue = activist.get("review_queue") or []
        summary = activist.get("summary") or {}
        tier_sum = (summary.get("signal_count") or 0) + (summary.get("context_count") or 0) + (
            summary.get("noise_count") or 0
        )
        if tier_sum != len(feed):
            errors.append(
                f"activist feed tier counts ({tier_sum}) != feed rows ({len(feed)})"
            )
        publisher_targets_by_url: dict[str, set[str]] = {}
        for row in feed:
            local_file = row.get("local_file")
            github_url = row.get("github_url")
            file_exists = row.get("file_exists")
            if github_url and file_exists is False:
                errors.append(
                    f"activist feed {row.get('ticker')}/{row.get('firm_id')}: github_url set but file_exists is false"
                )
            if local_file and file_exists is True and not deploy_only:
                if not repository_file_exists(ROOT, str(local_file)):
                    errors.append(f"activist feed references missing file: {local_file}")
            if local_file and file_exists is False and github_url and not deploy_only:
                errors.append(f"activist feed ghost github link for missing file: {local_file}")
            if (
                local_file
                and not deploy_only
                and (ROOT / str(local_file).replace("\\", "/")).exists()
                and file_exists is False
            ):
                errors.append(
                    f"activist feed {row.get('ticker')}/{row.get('firm_id')}: file on disk but file_exists false"
                )
            if row.get("triage_verdict") is None and row.get("source") != "short_reports_md":
                errors.append(
                    f"activist feed {row.get('ticker')}/{row.get('firm_id')}: missing triage_verdict"
                )
            if row.get("triage_verdict") == "auto_passive":
                errors.append(
                    f"activist feed {row.get('ticker')}/{row.get('firm_id')}: auto_passive row must not be in feed"
                )
            if row.get("needs_filer_review"):
                errors.append(
                    f"activist feed {row.get('ticker')}/{row.get('firm_id')}: review row must be in review_queue"
                )
            for key in ("report_id", "campaign_id", "report_kind", "target_company", "link_relevance"):
                if not row.get(key):
                    errors.append(
                        f"activist feed {row.get('ticker')}/{row.get('firm_id')}: missing {key}"
                    )
            if row.get("tier") == "signal" and not row.get("target_verified"):
                errors.append(
                    f"activist signal {row.get('ticker')}/{row.get('firm_id')}: target not verified"
                )
            if row.get("source") == "publisher_site":
                is_report, reason = classify_publisher_page(
                    row.get("source_url") or "", row.get("title") or ""
                )
                if not is_report:
                    errors.append(
                        f"activist publisher row is not a report ({reason}): {row.get('source_url')}"
                    )
                url = str(row.get("source_url") or "").rstrip("/")
                if url:
                    publisher_targets_by_url.setdefault(url, set()).add(row.get("ticker") or "")
        for url, target_tickers in publisher_targets_by_url.items():
            if len(target_tickers) > 1:
                errors.append(
                    f"activist publisher URL maps to multiple tickers ({', '.join(sorted(target_tickers))}): {url}"
                )
        for row in review_queue:
            if not row.get("needs_filer_review"):
                errors.append(
                    f"activist review_queue {row.get('ticker')}/{row.get('firm_id')}: row does not need review"
                )
        for ticker in holdings:
            sr = ROOT / ticker / "third-party-analyses" / "short_reports"
            if not sr.is_dir():
                continue
            index_path = ROOT / ticker / "third-party-analyses" / "activist_reports_index.json"
            indexed_md: set[str] = set()
            if index_path.exists():
                idx = json.loads(index_path.read_text(encoding="utf-8"))
                indexed_md = {
                    str(r.get("local_file") or "").replace("\\", "/")
                    for r in (idx.get("reports") or [])
                    if r.get("source") == "short_reports_md"
                }
            for md in sr.glob("*.md"):
                rel = str(md.relative_to(ROOT)).replace("\\", "/")
                if rel not in indexed_md:
                    warnings.append(f"short_reports MD not in activist index: {rel} — run activist scan")

    if INDEX_MEMBERSHIP_PATH.exists():
        index_doc = json.loads(INDEX_MEMBERSHIP_PATH.read_text(encoding="utf-8"))
        if not index_doc.get("rules_as_of"):
            errors.append("index_membership.json missing rules_as_of")
        by_ticker = index_doc.get("by_ticker") or {}
        missing_idx = sorted(set(holdings) - set(by_ticker.keys()))
        extra_idx = sorted(set(by_ticker.keys()) - set(holdings))
        if missing_idx:
            fail(f"index_membership missing registry tickers: {', '.join(missing_idx[:20])}")
        if extra_idx:
            fail(f"index_membership tickers not in registry: {', '.join(extra_idx[:20])}")
        for ticker, entry in by_ticker.items():
            for sc in entry.get("scorecards") or []:
                status = sc.get("status")
                if status not in INDEX_STATUS_ENUM:
                    errors.append(f"index_membership {ticker}: bad status {status!r}")
            for ev in entry.get("confirmed_events") or []:
                if not ev.get("effective") and ev.get("confidence") == "provider_confirmed":
                    errors.append(f"index_membership {ticker}: provider_confirmed event missing effective")
                if not (ev.get("source_url") or ev.get("source_type") or ev.get("title")):
                    errors.append(f"index_membership {ticker}: confirmed event missing source")
        for row in rows:
            im = row.get("index_membership")
            if im and im.get("badge_status") and im.get("badge_status") not in INDEX_STATUS_ENUM:
                errors.append(f"{row.get('ticker')}: bad index badge_status {im.get('badge_status')!r}")
    else:
        warnings.append("missing dashboard/data/index_membership.json")

    banks_path = ROOT / "dashboard" / "data" / "advantaged_banks_screener.json"
    if banks_path.exists():
        try:
            banks = json.loads(banks_path.read_text(encoding="utf-8"))
            bank_rows = banks.get("rows") or []
            if not bank_rows:
                warnings.append("advantaged_banks_screener has zero rows")
            elif banks.get("row_count") not in (None, len(bank_rows)):
                errors.append(
                    f"advantaged_banks_screener row_count={banks.get('row_count')} "
                    f"!= len(rows)={len(bank_rows)}"
                )
            missing_ticker = [i for i, r in enumerate(bank_rows) if not r.get("ticker")]
            if missing_ticker:
                errors.append(
                    f"advantaged_banks_screener rows missing ticker at indices {missing_ticker[:5]}"
                )
            built_at = banks.get("built_at")
            if built_at:
                try:
                    built_dt = datetime.fromisoformat(str(built_at).replace("Z", "+00:00"))
                    age_days = (datetime.now(timezone.utc) - built_dt).total_seconds() / 86400
                    if age_days > 7:
                        warnings.append(
                            f"advantaged_banks_screener built_at is {age_days:.0f}d old — rebuild"
                        )
                except ValueError:
                    warnings.append("advantaged_banks_screener built_at not parseable")
            if "advantaged_banks_screener" not in payload and bank_rows:
                warnings.append(
                    "advantaged_banks_screener.json exists but not embedded in dashboard_data.json"
                )
        except json.JSONDecodeError:
            errors.append("advantaged_banks_screener.json is invalid JSON")
    else:
        warnings.append("missing dashboard/data/advantaged_banks_screener.json")

    # --- Warrant monitor gates ------------------------------------------------
    warrant_path = ROOT / "dashboard" / "data" / "warrants.json"
    if warrant_path.exists():
        try:
            warrants = json.loads(warrant_path.read_text(encoding="utf-8"))
            warrant_rows = warrants.get("rows") or []
            warrant_summary = warrants.get("summary") or {}
            active_count = sum(r.get("lifecycle") == "active" for r in warrant_rows)
            if warrant_summary.get("active_series") != active_count:
                errors.append(
                    "warrants.json summary.active_series does not match active rows"
                )
            for row in warrant_rows:
                gates = row.get("gates") or {}
                all_pass = all(
                    (gates.get(name) or {}).get("pass")
                    for name in ("identity", "survival", "market")
                )
                score = (row.get("diagnostics") or {}).get("opportunity_score")
                if score is not None and not all_pass:
                    errors.append(
                        f"warrant {row.get('warrant_ticker')}: score emitted before all gates pass"
                    )
            if (warrants.get("health") or {}).get("structural_errors"):
                errors.append("warrants.json reports structural contract errors")
        except json.JSONDecodeError:
            errors.append("dashboard/data/warrants.json is invalid JSON")
    else:
        errors.append("missing dashboard/data/warrants.json")

    # --- Sharded payload gates (speed budget) --------------------------------
    # core.json is the SPA boot payload; keep it small so first paint stays
    # fast as the ticker universe grows. Ticker/insight shards are lazy.
    core_path = ROOT / "dashboard" / "data" / "core.json"
    tickers_dir = ROOT / "dashboard" / "data" / "tickers"
    insights_dir = ROOT / "dashboard" / "data" / "insights"
    if core_path.exists():
        core_mb = core_path.stat().st_size / 1e6
        if core_mb > CORE_MAX_MB:
            errors.append(
                f"core.json is {core_mb:.2f} MB (budget {CORE_MAX_MB} MB) - "
                "slim rows further in build_dashboard_shards.py"
            )
        try:
            core_doc = json.loads(core_path.read_text(encoding="utf-8"))
            core_count = len(core_doc.get("tickers") or [])
            if core_count != len(rows):
                errors.append(
                    f"core.json has {core_count} tickers vs dashboard_data.json {len(rows)} - rerun build"
                )
        except json.JSONDecodeError:
            errors.append("core.json is invalid JSON")
        if tickers_dir.exists():
            shard_files = list(tickers_dir.glob("*.json"))
            if len(shard_files) < len(rows):
                warnings.append(
                    f"only {len(shard_files)} ticker shards for {len(rows)} rows - rerun build"
                )
            oversize = [
                f.name for f in shard_files if f.stat().st_size / 1e6 > TICKER_SHARD_MAX_MB
            ]
            if oversize:
                errors.append(
                    f"ticker shards over {TICKER_SHARD_MAX_MB} MB: {', '.join(sorted(oversize)[:5])}"
                )
        else:
            errors.append("core.json exists but dashboard/data/tickers/ missing")
        if not (insights_dir / "manifest.json").exists():
            warnings.append("dashboard/data/insights/manifest.json missing - insights tab will not lazy-load")
    else:
        warnings.append("dashboard/data/core.json missing - SPA falls back to monolithic payload")

    for msg in warnings:
        print(f"WARN: {msg}")
    for msg in errors:
        print(f"ERROR: {msg}", file=sys.stderr)

    if errors:
        return 1
    print(f"OK: {len(holdings)} holdings, {len(rows)} dashboard rows validated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

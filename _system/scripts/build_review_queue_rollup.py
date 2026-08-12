#!/usr/bin/env python3
"""Roll up _system/reviews/pending/ into the items that genuinely need a human verdict.

Three jobs, all re-runnable and all cheap (filename + registry reads only, no file
content parsing and no network):

1. Classify every file in `pending/` against a typed pattern table and emit
   `_system/data/review_queue_rollup.json` + `_system/reviews/QUEUE.md`.
2. `--expire` dated ephemera whose review value has passed. Expiry only ever fires
   on a `superseded_snapshot` type: a file is expired when a strictly newer file of
   the same type exists AND it is older than that type's cutoff AND it is not one
   of the `keep_latest` most recent. Expired files are MOVED to
   `_system/reviews/expired/<type>/`, never deleted.
3. `--close-onboard` auto-closes onboard checklists whose `[HUMAN REVIEW]` items are
   all discharged by a registry check. Closed files move to
   `_system/reviews/auto_closed/`; anything with a real blocker stays in pending/
   with the blocker named in QUEUE.md.

   What the gate checks is PRESENCE and CROSS-SOURCE AGREEMENT, not correctness. A
   CIK that is present, well formed and identical in both sources still passes when
   it belongs to a different issuer, and an `ir_roots` URL passes on shape alone -
   nothing here fetches it or ties it back to the company. The close therefore means
   "the registry is internally consistent and nothing is left at a default", which is
   weaker than "these values are right".
4. `--reverify-closed` re-runs the current gate over everything already in
   `_system/reviews/auto_closed/` and moves back to pending/ anything that no
   longer passes. The auto-close ledger is append-only, so a re-open appends a
   `"action": "reopened"` row rather than editing the original close.

The gate only ever closes on positive evidence. A registry field left at its
onboarding default ("unknown", "unproven", "pending", "watch", "-") is NOT a
human confirmation - the checklist line is literally "confirm classification
defaults", so a check that passes on the defaults confirms nothing. Same for the
"-" no-sleeve sentinel and for an empty `ir_roots`: absence of IR URLs is not
verification of IR URLs, and a deep-dive reminder is not discharged by a dive
that was never written.

Usage:
  python _system/scripts/build_review_queue_rollup.py                  # report only
  python _system/scripts/build_review_queue_rollup.py --expire --close-onboard
  python _system/scripts/build_review_queue_rollup.py --reverify-closed
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

from portfolio_registry import DEFAULT_CLASSIFICATION, ROOT, US_CONFIG_PATH, load_registry

REVIEWS = ROOT / "_system" / "reviews"
PENDING = REVIEWS / "pending"
APPROVED = REVIEWS / "approved"
EXPIRED = REVIEWS / "expired"
AUTO_CLOSED = REVIEWS / "auto_closed"
OUT_JSON = ROOT / "_system" / "data" / "review_queue_rollup.json"
OUT_MD = REVIEWS / "QUEUE.md"
EXPIRY_LEDGER = EXPIRED / "_expiry_ledger.json"
AUTOCLOSE_LEDGER = AUTO_CLOSED / "_autoclose_ledger.json"

SCHEMA_VERSION = "1.1"
DATE_RE = r"(?P<date>\d{4}-\d{2}-\d{2})"
SKIP_NAMES = {"README.md"}

# Values that mean "nobody has decided yet". Every one of these is truthy, which is
# why a truthiness test on the classification fields closed 584 checklists that had
# all five fields still at the onboarding defaults.
PLACEHOLDER_VALUES = frozenset({
    "", "-", "--", "?", "n/a", "na", "none set", "not set", "null", "pending",
    "tbd", "todo", "unassigned", "unclassified", "unknown", "unproven", "unset",
})
SLEEVE_FIELD = "investment_sleeve"
# Derived, not hand-listed: a hand-listed tuple covered 5 of the 7 non-sleeve keys, so
# `moi_bucket` and `payoff_lens` were never tested and a checklist could close with
# those two still at their onboarding default. Deriving it means a new key added to
# DEFAULT_CLASSIFICATION is covered the day it lands instead of silently fail-open.
CLASSIFICATION_FIELDS = tuple(k for k in DEFAULT_CLASSIFICATION if k != SLEEVE_FIELD)

# Blocker class -> the one edit that clears the whole class. Keyed on the part of
# the blocker token before ':' so the detail suffix does not fragment the groups.
BLOCKER_FIXES = {
    "missing_registry_entry":
        "Add the ticker to _system/portfolio/registry.json, or drop the stale checklist.",
    "cik_missing_in_registry":
        "Set holdings.<T>.download.cik from SEC EDGAR, and add the same CIK to "
        "_system/scripts/us_ticker_config.json (it is read first and shadows the registry).",
    "cik_null_in_us_ticker_config":
        "us_ticker_config.json has an entry with a null cik, which beats the good registry "
        "value; fill it in there too, then confirm a non-zero SEC= download count.",
    "cik_mismatch_registry_vs_us_ticker_config":
        "The two CIK sources disagree; decide which is right and make them equal.",
    "no_download_route":
        "Set holdings.<T>.download.type to a non-US route (see DOWNLOAD_TYPE_OVERRIDES).",
    "ir_roots_missing":
        "Add at least one investor-relations root URL to holdings.<T>.download.ir_roots. "
        "An empty list is not a verified IR URL.",
    "ir_root_malformed":
        "Every ir_roots entry must start with http:// or https://.",
    "company_name_placeholder":
        "holdings.<T>.company is still the bare symbol; set the real legal name.",
    "classification_unconfirmed":
        "The named fields are still at the onboarding defaults "
        f"({', '.join(f'{k}={DEFAULT_CLASSIFICATION[k]!r}' for k in CLASSIFICATION_FIELDS)}). "
        "The checklist asks a human to confirm them, so a default cannot count as confirmed.",
    "sleeve_unassigned":
        "Assign holdings.<T>.classification.investment_sleeve; '-' is the no-sleeve sentinel, "
        "not a sleeve.",
    "deep_dive_absent":
        "The checklist's 'review deep dive PR when Cloud Agent completes' line is only "
        "waivable once the dive exists. Run the deep dive (or drop the ticker) so that a "
        "{TICKER}/research/deep_dive_{date}.md or a {TICKER}_deep_dive_{date}.md review "
        "artifact is on disk.",
}

# Dispositions.
#   human_verdict       - a person must decide something; never auto-expires.
#   superseded_snapshot - full restatement of current state, dominated by the newest
#                         file of the same type; expires on the cutoff below.
#   machine_receipt     - record that a batch ran; no verdict, expires quickly.
#   onboard_checklist   - handled by the deterministic auto-close pass.
#   standing_doc        - undated working document, lives here until the human moves it.
HUMAN_VERDICT = "human_verdict"
SUPERSEDED = "superseded_snapshot"
RECEIPT = "machine_receipt"
ONBOARD = "onboard_checklist"
STANDING = "standing_doc"


@dataclass(frozen=True)
class QueueType:
    id: str
    label: str
    pattern: str
    disposition: str
    requires: str
    source: str
    expire_after_days: int | None = None
    keep_latest: int = 1
    rationale: str = ""
    regex: re.Pattern = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "regex", re.compile(self.pattern))


# Ordered: first match wins, so specific prefixes precede the {TICKER}_ patterns.
QUEUE_TYPES: tuple[QueueType, ...] = (
    QueueType(
        id="batch_onboard_receipt",
        label="Batch onboard receipt",
        pattern=rf"^batch_onboard_{DATE_RE}\.md$",
        disposition=RECEIPT,
        requires="Nothing. Per-ticker onboard checklists carry the reviewable content.",
        source="bulk_sp500_onboard.py",
        expire_after_days=30,
        keep_latest=2,
        rationale="Run receipt for a batch whose per-ticker artifacts are queued separately.",
    ),
    QueueType(
        id="sleeve_onboard_proposal",
        label="Sleeve onboard proposal",
        pattern=rf"^(?:otc_sleeve|fund_nav_discounts)_onboard_{DATE_RE}\.md$",
        disposition=HUMAN_VERDICT,
        requires="Approve or reject the proposed sleeve additions, then move to approved/.",
        source="one-off sleeve build-out",
    ),
    QueueType(
        id="dispatch_receipt",
        label="Agent dispatch receipt",
        pattern=rf"^[a-z0-9_]+_dispatch_{DATE_RE}\.md$",
        disposition=RECEIPT,
        requires="Nothing. The dispatched work reports through its own artifact.",
        source="batch dispatch scripts",
        expire_after_days=30,
        keep_latest=2,
        rationale="Records that jobs were dispatched; carries no verdict.",
    ),
    QueueType(
        id="world_model_review",
        label="World-model review",
        pattern=rf"^world_model_review_(?P<ticker>[A-Za-z0-9.\-]+)_{DATE_RE}\.md$",
        disposition=HUMAN_VERDICT,
        requires="Confirm or reject the proposed world-model / KPI context change.",
        source="apply_world_model_context.py, check_kpi_ledger.py --queue-reviews",
    ),
    QueueType(
        id="cross_check",
        label="Cross-check report",
        pattern=rf"^(?P<ticker>[A-Za-z0-9.\-]+)_cross_check_[A-Z]{{2}}_{DATE_RE}\.md$",
        disposition=HUMAN_VERDICT,
        requires="Adjudicate the disagreements between sources before the valuation is trusted.",
        source="cross-check pass",
    ),
    QueueType(
        id="deep_dive",
        label="Deep dive",
        pattern=rf"^(?P<ticker>[A-Za-z0-9.\-]+)_deep_dive_{DATE_RE}\.md$",
        disposition=HUMAN_VERDICT,
        requires="Read the dive, set stance/archetype, then move to approved/. Never auto-expires.",
        source="deep dive Cloud Agent",
    ),
    QueueType(
        id="onboard_checklist",
        label="Onboard checklist",
        pattern=rf"^(?P<ticker>[A-Za-z0-9.\-]+)_onboard_{DATE_RE}\.md$",
        disposition=ONBOARD,
        requires="Only the items the auto-close pass could not clear (see blockers below).",
        source="onboarding pipeline",
    ),
    QueueType(
        id="portfolio_news",
        label="Portfolio news scan",
        pattern=rf"^news_{DATE_RE}\.md$",
        disposition=SUPERSEDED,
        requires="Skim refresh-eligible rows; anything actioned becomes an event or a dive.",
        source="ingest_portfolio_news.py",
        expire_after_days=30,
        keep_latest=3,
        rationale="Digest of a rolling 30-day feed window; at 30 days a newer digest covers the same window.",
    ),
    QueueType(
        id="darwin_regime_brief",
        label="Darwin regime brief",
        pattern=rf"^darwin_regime_brief_{DATE_RE}\.md$",
        disposition=SUPERSEDED,
        requires="Nothing once a newer brief exists; the brief states the regime as of its date.",
        source="_system/scripts/darwin/observatory.py",
        expire_after_days=14,
        keep_latest=2,
        rationale="States the CURRENT regime. A stale regime label is not reviewable, it is wrong.",
    ),
    QueueType(
        id="transcript_coverage",
        label="Transcript coverage report",
        pattern=rf"^transcript_coverage_{DATE_RE}\.md$",
        disposition=SUPERSEDED,
        requires="Nothing; it is a coverage metric, not a verdict queue.",
        source="transcript_gap_report.py",
        expire_after_days=14,
        keep_latest=2,
        rationale="Restates coverage for all holdings every run; the newest file dominates.",
    ),
    QueueType(
        id="ls_algo_ic_queue",
        label="ls-algo IC queue",
        pattern=rf"^ls_algo_ic_queue_{DATE_RE}\.md$",
        disposition=SUPERSEDED,
        requires="Act on the newest queue only; triggers are price-dependent and go stale daily.",
        source="ls-algo committee pass",
        expire_after_days=14,
        keep_latest=2,
        rationale="Snapshot of live triggers at that day's prices; a stale trigger list is misleading.",
    ),
    QueueType(
        id="fund_family_proposals",
        label="Fund family proposals",
        pattern=rf"^fund_family_proposals_{DATE_RE}\.md$",
        disposition=SUPERSEDED,
        requires="Promote confirmed families into _system/data/fund_families.json.",
        source="fund_families.py",
        expire_after_days=21,
        keep_latest=2,
        rationale="Re-detected from scratch each run; unpromoted proposals reappear in the newer file.",
    ),
    QueueType(
        id="event_triage",
        label="Event triage table",
        pattern=rf"^event_triage_{DATE_RE}\.md$",
        disposition=SUPERSEDED,
        requires="Adjudicate borderline events in the NEWEST table only.",
        source="event_triage.py",
        expire_after_days=30,
        keep_latest=2,
        rationale="Full daily restatement of every unresolved row; still-open rows carry forward.",
    ),
    QueueType(
        id="filing_insights",
        label="Filing insights table",
        pattern=rf"^filing_insights_{DATE_RE}\.md$",
        disposition=SUPERSEDED,
        requires="Adjudicate low-confidence parser rows in the NEWEST table only.",
        source="auto_resolve_filing_events.py",
        expire_after_days=30,
        keep_latest=2,
        rationale="Full daily restatement of unresolved parser rows.",
    ),
    QueueType(
        id="activist_triage",
        label="Activist triage table",
        pattern=rf"^activist_triage_{DATE_RE}\.md$",
        disposition=SUPERSEDED,
        requires="Adjudicate unresolved activist rows in the NEWEST table only.",
        source="activist_triage.py",
        expire_after_days=30,
        keep_latest=2,
        rationale="Cumulative: row count only grows, so the newest table strictly contains the older ones.",
    ),
    QueueType(
        id="activist_press_digest",
        label="Activist press digest",
        pattern=rf"^activist_press_digest_{DATE_RE}\.md$",
        disposition=SUPERSEDED,
        requires="Read letters that matter for a held name; rows persist in the newer digest.",
        source="activist press seed harvester",
        expire_after_days=30,
        keep_latest=2,
        rationale="Restated from a fixed seed list each run; nothing is unique to an old copy.",
    ),
    QueueType(
        id="memory_triage",
        label="Canonical memory triage",
        pattern=r"^memory_triage\.md$",
        disposition=HUMAN_VERDICT,
        requires="Disposition durable beliefs; company observations and artifacts are routed automatically.",
        source="build_memory_triage.py",
        rationale="Canonical cumulative queue backed by triage_ledger.json; every proposal remains until disposition.",
    ),
    QueueType(
        id="cvr_discovery",
        label="CVR discovery",
        pattern=rf"^cvr_discovery_{DATE_RE}\.md$",
        disposition=HUMAN_VERDICT,
        requires="Confirm newly discovered CVRs before they enter the universe.",
        source="refresh_cvr_universe.py",
    ),
    QueueType(
        id="depth_scorecard",
        label="Deep dive depth scorecard",
        pattern=rf"^deep_dive_depth_scorecard_{DATE_RE}\.csv$",
        disposition=HUMAN_VERDICT,
        requires="Decide which thin dives get re-run.",
        source="deep dive quality pass",
    ),
    QueueType(
        id="plan_proposal",
        label="Plan / proposal",
        pattern=rf"^[a-z0-9_]+_(?:plan|roadmap|upgrade|suggestions)(?:_{DATE_RE})?\.md$",
        disposition=HUMAN_VERDICT,
        requires="Accept, amend or reject the proposed change of process.",
        source="one-off agent proposals",
    ),
    QueueType(
        id="one_off_note",
        label="One-off analysis / audit",
        pattern=rf"^[a-z0-9_.\-]+_{DATE_RE}\.(?:md|csv|json)$",
        disposition=HUMAN_VERDICT,
        requires="Read once and file; these were written for a specific question.",
        source="ad hoc",
    ),
    QueueType(
        id="standing_doc",
        label="Standing working document",
        pattern=r"^[A-Za-z0-9_.\-]+\.(?:md|csv|json)$",
        disposition=STANDING,
        requires="No date, no cadence: the human moves it out when it stops being useful.",
        source="ad hoc",
    ),
)

TYPES_BY_ID = {t.id: t for t in QUEUE_TYPES}


def classify(name: str) -> tuple[QueueType | None, dict]:
    for qt in QUEUE_TYPES:
        m = qt.regex.match(name)
        if m:
            return qt, m.groupdict()
    return None, {}


def _norm_cik(value: object) -> str:
    text = str(value or "").strip()
    return text.zfill(10) if text.isdigit() and len(text) <= 10 else ""


def _is_placeholder(value: object) -> bool:
    return str(value or "").strip().lower() in PLACEHOLDER_VALUES


def _is_confirmed(field: str, value: object) -> bool:
    """True only when a human has moved the field off its onboarding default.

    Two ways to fail: the value is a generic placeholder, or it still equals the
    default `onboard_ticker.py` wrote. Both are truthy strings, so truthiness is
    not a test of anything.
    """
    text = str(value or "").strip().lower()
    if _is_placeholder(text):
        return False
    return text != str(DEFAULT_CLASSIFICATION.get(field, "")).strip().lower()


def _first_assigned(*values: object) -> str | None:
    """First value that is not a placeholder.

    `a or b` cannot be used here: every placeholder is truthy, so the '-' no-sleeve
    sentinel on `classification.investment_sleeve` won the expression and the
    top-level `entry["investment_sleeve"]` fallback was never read - 75 checklists
    were reported sleeve_unassigned while carrying a real entry-level sleeve.
    """
    for value in values:
        if value is not None and not _is_placeholder(value):
            return str(value).strip()
    return None


def onboard_checks(ticker: str, holdings: dict, us_config: dict,
                   deep_dive_tickers: set[str] | frozenset[str]) -> tuple[list[str], list[str]]:
    """Return (checks_passed, blockers) for one onboard checklist.

    The checklist's three [HUMAN REVIEW] lines are 'verify CIK and IR URLs in
    registry', 'review deep dive PR when Cloud Agent completes' and 'confirm
    classification defaults'.

    The first and third are checked against the registry - but only for presence and
    cross-source agreement, never for correctness: a CIK belonging to the wrong
    issuer, or an ir_root pointing at another company, passes every test here. The
    close means the registry is internally consistent and off its defaults, not that
    the values are right.

    The second used to be waived by argument ("the dive lands as its own review
    item"), which held for the handful of tickers that had a dive and was fiction for
    the ~797 that had none anywhere. It is now waived only when a deep-dive artifact
    actually exists for the ticker; otherwise it is a blocker, because a reminder to
    review something that was never produced is not discharged.

    Only positive evidence closes an item. Missing data (no IR roots, a field left
    at its default, the '-' no-sleeve sentinel) is a blocker, never a pass.
    """
    entry = holdings.get(ticker)
    if not entry:
        return [], ["missing_registry_entry"]

    passed: list[str] = ["registry_entry_present"]
    blockers: list[str] = []
    download = entry.get("download") or {}

    if (entry.get("market") or "").upper() == "US":
        registry_cik = _norm_cik(download.get("cik"))
        # us_ticker_config.json is read FIRST by the downloader and shadows the
        # registry, so a null there beats a correct registry value.
        shadow = us_config.get(ticker)
        shadow_cik = _norm_cik((shadow or {}).get("cik"))
        if not registry_cik:
            blockers.append("cik_missing_in_registry")
        elif shadow is not None and not shadow_cik:
            blockers.append("cik_null_in_us_ticker_config")
        elif shadow is not None and shadow_cik != registry_cik:
            blockers.append("cik_mismatch_registry_vs_us_ticker_config")
        else:
            passed.append("cik_present_and_unshadowed")
    else:
        if download.get("type"):
            passed.append("non_us_download_route_set")
        else:
            blockers.append("no_download_route")

    # "Verify ... IR URLs in registry": an empty list asserts nothing, so it cannot
    # discharge the item. Only URLs that exist and are well formed count.
    ir_roots = download.get("ir_roots") or []
    if not ir_roots:
        blockers.append("ir_roots_missing")
    elif all(str(u).startswith(("http://", "https://")) for u in ir_roots):
        passed.append("ir_roots_well_formed")
    else:
        blockers.append("ir_root_malformed")

    company = str(entry.get("company") or "").strip()
    base = ticker.split(".")[0]
    if company and company.upper() not in {ticker.upper(), base.upper()}:
        passed.append("company_name_resolved")
    else:
        blockers.append("company_name_placeholder")

    classification = entry.get("classification") or {}
    unconfirmed = [k for k in CLASSIFICATION_FIELDS if not _is_confirmed(k, classification.get(k))]
    if unconfirmed:
        blockers.append("classification_unconfirmed:" + ",".join(unconfirmed))
    else:
        passed.append("classification_confirmed")

    sleeve = _first_assigned(classification.get(SLEEVE_FIELD), entry.get(SLEEVE_FIELD))
    if sleeve:
        passed.append("sleeve_assigned")
    else:
        blockers.append("sleeve_unassigned")

    if ticker in deep_dive_tickers:
        passed.append("deep_dive_artifact_present")
    else:
        blockers.append("deep_dive_absent")

    return passed, blockers


def deep_dive_index() -> frozenset[str]:
    """Tickers that have a deep-dive artifact somewhere on disk.

    Two shapes count, because the dive is written to the ticker tree and queued as a
    review item under a different filename:
      * `{TICKER}/research/deep_dive_{date}.md`, and
      * `{TICKER}_deep_dive_{date}.md` under any reviews/ subdirectory (pending,
        approved, expired, auto_closed).
    """
    found: set[str] = set()
    for path in ROOT.glob("*/research/deep_dive_*.md"):
        found.add(path.parents[1].name)
    dive_type = TYPES_BY_ID["deep_dive"]
    for folder in (PENDING, APPROVED, EXPIRED, AUTO_CLOSED):
        if not folder.is_dir():
            continue
        for path in folder.rglob("*_deep_dive_*.md"):
            match = dive_type.regex.match(path.name)
            if match:
                found.add(match.group("ticker"))
    return frozenset(found)


def _age_days(item_date: str | None, today: date) -> int | None:
    if not item_date:
        return None
    try:
        return (today - date.fromisoformat(item_date)).days
    except ValueError:
        return None


def scan(today: date) -> list[dict]:
    registry = load_registry()
    holdings = registry.get("holdings") or {}
    try:
        us_config = json.loads(US_CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        us_config = {}
    dives = deep_dive_index()

    items: list[dict] = []
    for path in sorted(PENDING.iterdir()):
        if not path.is_file() or path.name in SKIP_NAMES:
            continue
        qt, groups = classify(path.name)
        item = {
            "file": path.name,
            "type": qt.id if qt else "unclassified",
            "disposition": qt.disposition if qt else HUMAN_VERDICT,
            "ticker": groups.get("ticker"),
            "date": groups.get("date"),
            "age_days": _age_days(groups.get("date"), today),
            "checks_passed": [],
            "blockers": [],
        }
        if qt and qt.disposition == ONBOARD and item["ticker"]:
            item["checks_passed"], item["blockers"] = onboard_checks(
                item["ticker"], holdings, us_config, dives)
            item["auto_closable"] = not item["blockers"]
        items.append(item)
    return items


def mark_expiry(items: list[dict]) -> None:
    """Flag superseded snapshots past their cutoff. Requires a strictly newer sibling."""
    by_type: dict[str, list[dict]] = {}
    for item in items:
        by_type.setdefault(item["type"], []).append(item)
    for type_id, group in by_type.items():
        qt = TYPES_BY_ID.get(type_id)
        if not qt or qt.expire_after_days is None:
            continue
        dated = sorted((i for i in group if i["date"]), key=lambda i: i["date"], reverse=True)
        for rank, item in enumerate(dated):
            age = item["age_days"]
            if rank < qt.keep_latest:
                continue  # always keep the freshest copies
            if rank == 0:
                continue  # no strictly newer sibling exists
            if age is None or age < qt.expire_after_days:
                continue
            item["expired"] = True
            item["expiry_reason"] = (
                f"superseded by {dated[0]['file']} and older than {qt.expire_after_days}d"
            )


def _append_ledger(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        existing = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        existing = []
    if not isinstance(existing, list):
        existing = []
    existing.extend(rows)
    path.write_text(json.dumps(existing, indent=2) + "\n", encoding="utf-8")


def _move(src: Path, dest_dir: Path) -> None:
    dest_dir.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dest_dir / src.name))


def apply_expiry(items: list[dict], now: str) -> int:
    moved = 0
    rows = []
    for item in items:
        if not item.get("expired"):
            continue
        src = PENDING / item["file"]
        if not src.exists():
            continue
        _move(src, EXPIRED / item["type"])
        rows.append({
            "file": item["file"],
            "type": item["type"],
            "item_date": item["date"],
            "age_days": item["age_days"],
            "reason": item["expiry_reason"],
            "expired_at": now,
        })
        moved += 1
    _append_ledger(EXPIRY_LEDGER, rows)
    return moved


def apply_onboard_autoclose(items: list[dict], now: str) -> int:
    moved = 0
    rows = []
    for item in items:
        if item["type"] != "onboard_checklist" or not item.get("auto_closable"):
            continue
        src = PENDING / item["file"]
        if not src.exists():
            continue
        _move(src, AUTO_CLOSED)
        rows.append({
            "action": "auto_closed",
            "file": item["file"],
            "ticker": item["ticker"],
            "item_date": item["date"],
            "checks_passed": item["checks_passed"],
            "closed_at": now,
        })
        moved += 1
    _append_ledger(AUTOCLOSE_LEDGER, rows)
    return moved


def reverify_auto_closed(now: str) -> tuple[int, int]:
    """Re-run the current gate over auto_closed/ and re-open anything that fails.

    A closure is only as good as the check that produced it. When the gate is
    tightened, everything closed under the looser gate has to be re-tested rather
    than grandfathered, or the tightening is cosmetic. Returns (reopened, still_closed).
    """
    if not AUTO_CLOSED.is_dir():
        return 0, 0

    registry = load_registry()
    holdings = registry.get("holdings") or {}
    try:
        us_config = json.loads(US_CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        us_config = {}
    dives = deep_dive_index()

    reopened = 0
    still_closed = 0
    rows: list[dict] = []
    for path in sorted(AUTO_CLOSED.iterdir()):
        if not path.is_file() or path.name.startswith("_") or path.name in SKIP_NAMES:
            continue
        qt, groups = classify(path.name)
        ticker = groups.get("ticker")
        if not qt or qt.disposition != ONBOARD or not ticker:
            continue
        _, blockers = onboard_checks(ticker, holdings, us_config, dives)
        if not blockers:
            still_closed += 1
            continue
        _move(path, PENDING)
        rows.append({
            "action": "reopened",
            "file": path.name,
            "ticker": ticker,
            "blockers": blockers,
            "reason": "re-opened by --reverify-closed: the current gate reports blockers that "
                      "the gate in force at close time did not",
            "reopened_at": now,
        })
        reopened += 1
    _append_ledger(AUTOCLOSE_LEDGER, rows)
    return reopened, still_closed


def summarize(items: list[dict]) -> dict:
    summary: dict[str, dict] = {}
    for item in items:
        row = summary.setdefault(item["type"], {
            "type": item["type"],
            "label": TYPES_BY_ID[item["type"]].label if item["type"] in TYPES_BY_ID else "Unclassified",
            "disposition": item["disposition"],
            "count": 0,
            "expiring_now": 0,
            "auto_closable": 0,
            "blocked": 0,
            "oldest": None,
            "newest": None,
            "max_age_days": None,
        })
        row["count"] += 1
        if item.get("expired"):
            row["expiring_now"] += 1
        if item.get("auto_closable") is True:
            row["auto_closable"] += 1
        elif item.get("auto_closable") is False:
            row["blocked"] += 1
        if item["date"]:
            row["oldest"] = min(row["oldest"] or item["date"], item["date"])
            row["newest"] = max(row["newest"] or item["date"], item["date"])
        if item["age_days"] is not None:
            row["max_age_days"] = max(row["max_age_days"] or 0, item["age_days"])
    return summary


def _blocker_class(blocker: str) -> str:
    """`classification_unconfirmed:archetype,moat` -> `classification_unconfirmed`."""
    return blocker.split(":", 1)[0]


def _blocker_census(items: list[dict]) -> dict[str, int]:
    census: dict[str, int] = {}
    for item in items:
        for blocker in item.get("blockers") or []:
            key = _blocker_class(blocker)
            census[key] = census.get(key, 0) + 1
    return dict(sorted(census.items(), key=lambda kv: (-kv[1], kv[0])))


def _blocker_groups(items: list[dict]) -> list[dict]:
    """Group still-open checklists by blocker class so a class can be fixed at once.

    800 files reviewed one at a time is not a backlog anyone works through; five
    registry edits that each clear a few hundred of them is.
    """
    groups: dict[str, dict] = {}
    for item in items:
        for blocker in item.get("blockers") or []:
            key = _blocker_class(blocker)
            row = groups.setdefault(key, {
                "blocker": key,
                "count": 0,
                "fix": BLOCKER_FIXES.get(key, "No recorded fix; inspect the registry entry."),
                "tickers": [],
                "detail_counts": {},
            })
            row["count"] += 1
            if item.get("ticker"):
                row["tickers"].append(item["ticker"])
            detail = blocker.split(":", 1)[1] if ":" in blocker else ""
            if detail:
                row["detail_counts"][detail] = row["detail_counts"].get(detail, 0) + 1
    for row in groups.values():
        row["tickers"].sort()
        row["detail_counts"] = dict(
            sorted(row["detail_counts"].items(), key=lambda kv: (-kv[1], kv[0]))
        )
    return sorted(groups.values(), key=lambda r: (-r["count"], r["blocker"]))


def render_markdown(payload: dict) -> str:
    rows = sorted(
        payload["by_type"].values(),
        key=lambda r: (r["disposition"] != HUMAN_VERDICT, -r["count"]),
    )
    lines = [
        "# Human review queue",
        "",
        f"Generated {payload['generated_at']} by `_system/scripts/build_review_queue_rollup.py`.",
        f"Pending files: **{payload['pending_total']}** · needing a human verdict: "
        f"**{payload['human_verdict_total']}** · approved/: {payload['approved_total']} · "
        f"expired/: {payload['expired_total']} · auto_closed/: {payload['auto_closed_total']}",
        "",
        "## Needs a human verdict",
        "",
        "| Type | Count | Oldest | Max age (d) | What it asks of you |",
        "|------|-------|--------|-------------|---------------------|",
    ]
    for row in rows:
        if row["disposition"] not in (HUMAN_VERDICT, ONBOARD, STANDING):
            continue
        if row["type"] == "onboard_checklist":
            continue
        qt = TYPES_BY_ID.get(row["type"])
        lines.append(
            f"| {row['label']} | {row['count']} | {row['oldest'] or '-'} | "
            f"{row['max_age_days'] if row['max_age_days'] is not None else '-'} | "
            f"{qt.requires if qt else 'Unclassified filename: add a pattern to QUEUE_TYPES.'} |"
        )

    onboard = payload["by_type"].get("onboard_checklist")
    lines += ["", "## Onboard checklists", ""]
    if onboard:
        lines += [
            f"- In pending: **{onboard['count']}**",
            f"- Closable by the registry gate now: **{onboard['auto_closable']}**"
            + ("" if not onboard["auto_closable"] else " - rerun with `--close-onboard`"),
            f"- Blocked on something the gate cannot check: **{onboard['blocked']}**",
            f"- Already auto-closed to `_system/reviews/auto_closed/`: {payload['auto_closed_total']}",
            "",
            "A checklist closes only on positive evidence. A registry field still at its",
            "onboarding default (`unknown`, `unproven`, `pending`, `watch`, `-`), an unassigned",
            "sleeve, an empty `ir_roots` or a deep dive that was never produced is a blocker,",
            "not a pass.",
            "",
            "**What the gate does and does not establish.** It checks that values are present,",
            "well formed and agree across sources - not that they are correct. A CIK that is",
            "present in both `registry.json` and `us_ticker_config.json` and identical in both",
            "still passes when it belongs to a different issuer, and an `ir_roots` URL passes on",
            "shape alone; nothing here fetches it or ties it to the company. Read an auto-close",
            "as \"internally consistent and off its defaults\", not as \"verified\".",
            "",
            "### Fix by class, not by file",
            "",
            "Each row is one kind of missing registry data. Fixing the class clears every",
            "checklist counted in it, so work top-down rather than file-by-file.",
            "",
            "| Blocker | Checklists | One fix clears them all | Example tickers |",
            "|---------|-----------|-------------------------|-----------------|",
        ]
        for group in payload["onboard_blocker_groups"]:
            sample = ", ".join(f"`{t}`" for t in group["tickers"][:8])
            extra = len(group["tickers"]) - 8
            if extra > 0:
                sample += f" +{extra} more"
            lines.append(
                f"| `{group['blocker']}` | {group['count']} | {group['fix']} | {sample or '-'} |"
            )
        detailed = [g for g in payload["onboard_blocker_groups"] if g["detail_counts"]]
        for group in detailed:
            lines += ["", f"`{group['blocker']}` by field set:", ""]
            for detail, count in group["detail_counts"].items():
                lines.append(f"- `{detail}` - {count}")
    else:
        lines.append("- None in pending.")

    lines += ["", "## Superseded snapshots and receipts (auto-expiring)", "",
              "| Type | Count | Cutoff (d) | Keep latest | Expiring now | Why it expires |",
              "|------|-------|-----------|-------------|--------------|----------------|"]
    for row in rows:
        if row["disposition"] not in (SUPERSEDED, RECEIPT):
            continue
        qt = TYPES_BY_ID.get(row["type"])
        lines.append(
            f"| {row['label']} | {row['count']} | {qt.expire_after_days if qt else '-'} | "
            f"{qt.keep_latest if qt else '-'} | {row['expiring_now']} | "
            f"{qt.rationale if qt else ''} |"
        )

    lines += ["", "## Oldest items awaiting a verdict", ""]
    oldest = [
        i for i in payload["items"]
        if i["disposition"] == HUMAN_VERDICT and i["age_days"] is not None and not i.get("expired")
    ]
    oldest.sort(key=lambda i: -i["age_days"])
    for item in oldest[:25]:
        lines.append(f"- `{item['file']}` — {item['age_days']}d ({item['type']})")
    lines.append("")
    return "\n".join(lines)


def build(expire: bool, close_onboard: bool, reverify_closed: bool = False,
          write: bool = True) -> dict:
    today = datetime.now(timezone.utc).date()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    reopened = 0
    if reverify_closed:
        reopened, _ = reverify_auto_closed(now)
    items = scan(today)
    mark_expiry(items)

    expired_moved = apply_expiry(items, now) if expire else 0
    closed_moved = apply_onboard_autoclose(items, now) if close_onboard else 0
    if expired_moved or closed_moved:
        items = scan(today)
        mark_expiry(items)

    by_type = summarize(items)
    onboard_items = [i for i in items if i["type"] == "onboard_checklist"]
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now,
        "pending_total": len(items),
        "human_verdict_total": sum(
            1 for i in items
            if i["disposition"] in (HUMAN_VERDICT, STANDING) or i.get("auto_closable") is False
        ),
        "approved_total": sum(1 for p in APPROVED.glob("*") if p.is_file()) if APPROVED.is_dir() else 0,
        "expired_total": sum(1 for p in EXPIRED.rglob("*") if p.is_file() and not p.name.startswith("_"))
        if EXPIRED.is_dir() else 0,
        "auto_closed_total": sum(1 for p in AUTO_CLOSED.glob("*") if p.is_file() and not p.name.startswith("_"))
        if AUTO_CLOSED.is_dir() else 0,
        "moved_this_run": {
            "expired": expired_moved,
            "auto_closed": closed_moved,
            "reopened": reopened,
        },
        "policy": {
            t.id: {
                "label": t.label,
                "disposition": t.disposition,
                "pattern": t.pattern,
                "source": t.source,
                "requires": t.requires,
                "expire_after_days": t.expire_after_days,
                "keep_latest": t.keep_latest,
                "rationale": t.rationale,
            }
            for t in QUEUE_TYPES
        },
        "by_type": by_type,
        "onboard_blockers": _blocker_census(onboard_items),
        "onboard_blocker_groups": _blocker_groups(onboard_items),
        "items": items,
    }

    if write:
        OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
        OUT_JSON.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        OUT_MD.write_text(render_markdown(payload), encoding="utf-8")

    print(
        f"review queue: {payload['pending_total']} pending / "
        f"{payload['human_verdict_total']} need a human verdict "
        f"(expired {expired_moved}, auto-closed {closed_moved}, reopened {reopened})"
    )
    for group in payload["onboard_blocker_groups"]:
        print(f"  onboard blocker {group['blocker']}: {group['count']}")
    unclassified = [i["file"] for i in items if i["type"] == "unclassified"]
    if unclassified:
        print(f"  unclassified filenames ({len(unclassified)}): {', '.join(unclassified[:5])}")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expire", action="store_true", help="move expired ephemera to reviews/expired/")
    parser.add_argument("--close-onboard", action="store_true",
                        help="move onboard checklists that clear every registry check to "
                             "reviews/auto_closed/ (presence and cross-source agreement, "
                             "not correctness)")
    parser.add_argument("--reverify-closed", action="store_true",
                        help="re-run the current gate over reviews/auto_closed/ and re-open failures")
    parser.add_argument("--dry-run", action="store_true", help="do not write the rollup outputs")
    args = parser.parse_args()
    build(args.expire, args.close_onboard, args.reverify_closed, write=not args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

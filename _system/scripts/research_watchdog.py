#!/usr/bin/env python3
"""Research Watchdog - the three things most wrong in the owned book.

Answers "is the book OK?", which is a different question from the one
`supervise_repository_health.py` answers ("did the job run?"). A lane can be
green for weeks while the research under it goes stale, and nothing in this
repo notices. This does.

SCOPE. Single-stock positions owned by Michael or Drew. Excluded:
  * SPX option strategies (bucket `spx_0dte`)
  * levered / inverse / derivative-income ETF wrappers, detected from the
    position's own `name` plus the `etf_to_under` map - NOT from
    `etf_ls_universe.json`, which is ls-algo's whole trading list (924 symbols,
    underlyings included) and would drop APLD, AXP, BRK B and SMR from research
    scope purely because a systematic strategy also trades them
  * zero-value corporate-action stubs (CVR / ESC / CNT / WTS / MRG at $0)

READ-ONLY. Every input is a committed file or a local snapshot. No IB Gateway,
no TWS socket, no client ID - CLAUDE.md rules 9 and 10 hold by construction.
The only network call is an optional `gh pr list` to mark findings already in
flight; it degrades to "unknown" when `gh` is absent.

RANKING. Capital at risk first, then severity, then age. Deliberately NOT a
count and NOT a delta against a baseline: `_system/reviews/pending/` took 814
files in July 2026, so any ratchet baselined on the pile would record the most
flattering possible moment.

Usage:
  python _system/scripts/research_watchdog.py            # top 3
  python _system/scripts/research_watchdog.py --all      # full ranked list
  python _system/scripts/research_watchdog.py --scope    # scope resolution only
  python _system/scripts/research_watchdog.py --json
  python _system/scripts/research_watchdog.py --no-pr    # skip the gh lookup
"""
from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import sys
from dataclasses import dataclass, field, asdict
from datetime import date, datetime
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parents[1]
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ROOT))

# Scope source, in preference order. `research_scope.json` is written from the
# daily IBKR Flex statement by build_research_scope.py and is the self-refreshing
# path; `positions.json` is the sleeve desk's own store and is the fallback for a
# machine where the Flex step has not run. Both are gitignored local state.
SCOPE_FILE = ROOT / "_system/trading/sleeves/data/local/research_scope.json"
POSITIONS = ROOT / "_system/trading/sleeves/data/local/positions.json"
ETF_TO_UNDER = ROOT / "_system/trading/sleeves/data/etf_to_under.json"
SLEEVE_TAGS = ROOT / "_system/trading/sleeves/data/local/sleeve_tags.json"
DIVE_QUEUE = ROOT / "_system/data/deep_dive_dispatch_queue.json"
OUT_JSON = ROOT / "_system/data/research_watchdog.json"
OUT_MD = ROOT / "_system/reviews/WATCHDOG.md"
# The only committed artifact. The two above name held positions and their
# market values; this repository is public, so they stay gitignored and the lane
# publishes counts alone.
OUT_RECEIPT = ROOT / "_system/data/research_watchdog_receipt.json"

TOP_N = 3

# Levered / inverse / derivative-income wrappers. Matched against the broker's
# own instrument name, which is the only field that actually says what the
# thing is. `etf_ls_universe.json` says who trades it, which is not the same.
WRAPPER_NAME_RE = re.compile(
    r"(\b\d+(?:\.\d+)?\s*X\b|\b\d+XL?\b|\bDAILY\s+(?:BULL|BEAR|SHORT|LONG)\b"
    r"|\bDIREXION\b|\bPROSHARES\b|\bTRADR\b|\bTRDR\b|\bT-?REX\b|\bLEVERAGE\s+SHARES\b"
    r"|\bGRANITESHARES\b|\bYIELDMAX\b|\bDEFIANCE\b|\bVOLATILITY\s*SHARES\b"
    r"|\bBULL\s+\d|\bSHORT\s+\w+\s+DAILY\b)",
    re.I,
)
# Corporate-action stubs: contingent value rights, escrows, warrants, merger
# residue. Real instruments, but they carry no thesis to go stale.
STUB_SUFFIX_RE = re.compile(r"\.(CVR|ESC|CNT|WTS|MRG|RTS)$", re.I)

# `systemic` is reserved for findings that break the repair loop itself or blind
# the watchdog to its own scope. They are weighted above `critical` because every
# per-ticker finding below them is conditional on them being wrong: a stale
# snapshot means the dollar figures are guesses, and a stalled queue means
# nothing found here gets fixed no matter how it ranks.
SEVERITY_WEIGHT = {"systemic": 6.0, "critical": 4.0, "high": 3.0, "medium": 2.0, "low": 1.0}


# --------------------------------------------------------------------------
# scope
# --------------------------------------------------------------------------
@dataclass
class Holding:
    symbol: str
    ticker: str | None
    name: str
    owner: str
    market_value: float
    reason: str


def load_json(path: Path, default=None):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def levered_wrapper_symbols() -> set[str]:
    payload = load_json(ETF_TO_UNDER, {}) or {}
    mapping = payload.get("map") if isinstance(payload, dict) else None
    return {str(k).upper() for k in (mapping or {})}


def is_wrapper(symbol: str, name: str, mapped: set[str]) -> bool:
    return symbol.upper() in mapped or bool(WRAPPER_NAME_RE.search(name or ""))


def resolve_ticker(symbol: str, registry: dict) -> str | None:
    """Broker symbol -> repo ticker directory.

    Broker symbols are space-separated (`BRK B`, `HEI A`) and drop the market
    suffix on foreign lines (`FIHO12` for FIHO12.MX, `JL80` for JL80.DE).
    """
    s = (symbol or "").upper().strip()
    if not s:
        return None
    for cand in (s, s.replace(" ", "-"), s.replace(" ", "."), s.replace(".", "-"), s.replace("-", ".")):
        if cand in registry:
            return cand
    base = s.split(" ")[0]
    matches = [t for t in registry if t.upper().split(".")[0] == base and "." in t]
    if len(matches) == 1:
        return matches[0]
    return None


def scope_source() -> Path:
    """Prefer the Flex-derived scope; fall back to the sleeve desk store."""
    return SCOPE_FILE if SCOPE_FILE.exists() else POSITIONS


def build_scope() -> tuple[list[Holding], dict]:
    from portfolio_registry import load_registry

    source = scope_source()
    registry = load_registry().get("holdings") or {}
    rows = load_json(source, []) or []
    mapped = levered_wrapper_symbols()

    kept: list[Holding] = []
    excluded: dict[str, list] = {"spx_0dte": [], "other_book": [], "levered_wrapper": [],
                                 "zero_value_stub": [], "not_stock": [], "unresolved": []}

    for row in rows:
        symbol = str(row.get("symbol") or "").upper().strip()
        name = str(row.get("name") or "")
        bucket = (row.get("classification") or {}).get("bucket")
        mv = float(row.get("marketValue") or 0.0)

        if bucket == "spx_0dte":
            excluded["spx_0dte"].append(symbol)
            continue
        if row.get("secType") != "STK":
            excluded["not_stock"].append(symbol)
            continue
        # Book membership comes from the stored bucket, which is the only record
        # of WHICH book a line belongs to. Do not recompute it: `classify_position`
        # tests `ticker in etf_ls_universe` before the owner checks, so recomputing
        # today would move APLD ($654k), AXP, BRK B and SMR out of Michael's book
        # purely because ls-algo added those tickers to its 924-symbol universe.
        if bucket not in {"michael", "drew"}:
            excluded["other_book"].append(f"{symbol} [{bucket}]")
            continue
        # The stored bucket is right about the book and wrong about the instrument:
        # it called APLZ, BRKU, BRKC, SMZ and ECHX Michael's. Correct that here.
        if is_wrapper(symbol, name, mapped):
            excluded["levered_wrapper"].append(f"{symbol} ({name})")
            continue
        if abs(mv) < 1.0 and STUB_SUFFIX_RE.search(symbol):
            excluded["zero_value_stub"].append(symbol)
            continue

        # Owner. `drew` requires sleeve_tags.json, which does not exist locally;
        # when it is absent every single stock lands in Michael's residual book.
        owner = "drew" if bucket == "drew" else "michael"
        ticker = resolve_ticker(symbol, registry)
        if ticker is None:
            excluded["unresolved"].append(f"{symbol} ({name}) ${mv:,.0f}")
            continue
        kept.append(Holding(symbol, ticker, name, owner, mv, str(bucket)))

    # As-of date. For a Flex scope this MUST come from the statement's own
    # session_date, never the file's mtime: the file is rewritten every time the
    # builder runs, so mtime is always "today" and a scope built from a
    # months-old statement would read as current - disabling detect_stale_inputs
    # entirely, which is the precise failure this watchdog exists to catch.
    # mtime is only the fallback for positions.json, which carries no date.
    snapshot = None
    if source.exists():
        snapshot = datetime.fromtimestamp(source.stat().st_mtime).date().isoformat()
        if source == SCOPE_FILE:
            scope_meta = load_json(source.parent / "research_scope_meta.json", {}) or {}
            snapshot = str(scope_meta.get("session_date") or "") or snapshot

    meta = {
        "positions_snapshot": source.relative_to(ROOT).as_posix()
        if source.is_relative_to(ROOT) else str(source),
        "scope_source": "flex" if source == SCOPE_FILE else "sleeve_store",
        "snapshot_date": snapshot,
        "sleeve_tags_present": SLEEVE_TAGS.exists(),
        "in_scope": len(kept),
        "capital_at_risk": round(sum(h.market_value for h in kept), 2),
        "owners": {o: sum(1 for h in kept if h.owner == o) for o in ("michael", "drew")},
        "excluded": {k: len(v) for k, v in excluded.items()},
        "excluded_detail": excluded,
    }
    return kept, meta


# --------------------------------------------------------------------------
# findings
# --------------------------------------------------------------------------
@dataclass
class Finding:
    detector: str
    ticker: str
    severity: str
    headline: str
    detail: str
    capital: float = 0.0
    age_days: int | None = None
    evidence: list[str] = field(default_factory=list)
    status: str = "unfixed"
    score: float = 0.0


def _age(iso: str | None, today: date) -> int | None:
    if not iso:
        return None
    try:
        return (today - date.fromisoformat(iso[:10])).days
    except ValueError:
        return None


def detect_dive_quality(scope: list[Holding], today: date) -> list[Finding]:
    """Missing, thin, or stale deep dive on a name holding capital."""
    from deep_dive_depth_common import PASS_SCORE, score_dive
    from lint_deep_dive_depth import latest_dive

    out: list[Finding] = []
    for h in scope:
        research = ROOT / h.ticker / "research"
        dive = latest_dive(research) if research.is_dir() else None
        if dive is None:
            out.append(Finding(
                "dive_quality", h.ticker, "critical",
                f"No deep dive on {h.ticker}",
                f"${h.market_value:,.0f} held with no deep_dive_*.md in {h.ticker}/research/.",
                h.market_value, None, [f"{h.ticker}/research/"],
            ))
            continue
        m = re.search(r"(\d{4}-\d{2}-\d{2})", dive.name)
        age = _age(m.group(1) if m else None, today)
        try:
            result = score_dive(dive)
            total, grade = result.total, result.grade  # both are properties
        except Exception as exc:  # a detector must never take the run down
            out.append(Finding(
                "dive_quality", h.ticker, "low",
                f"Deep dive on {h.ticker} could not be scored",
                f"score_dive raised {type(exc).__name__}: {exc}",
                h.market_value, age, [dive.relative_to(ROOT).as_posix()],
            ))
            continue
        rel = dive.relative_to(ROOT).as_posix()
        if total < PASS_SCORE:
            sev = "critical" if grade == "incomplete" else "high"
            out.append(Finding(
                "dive_quality", h.ticker, sev,
                f"{h.ticker} deep dive is {grade} ({total}/24)",
                f"${h.market_value:,.0f} held against a dive scoring {total}/24, below the "
                f"{PASS_SCORE} pass mark.",
                h.market_value, age, [rel],
            ))
        elif age is not None and age > 180:
            out.append(Finding(
                "dive_quality", h.ticker, "medium",
                f"{h.ticker} deep dive is {age} days old",
                f"${h.market_value:,.0f} held against a dive last written {age} days ago.",
                h.market_value, age, [rel],
            ))
    return out


def detect_uncrosschecked_intake(scope: list[Holding], today: date) -> list[Finding]:
    """Third-party PDFs sitting in drive-intake with no cross-check written."""
    out: list[Finding] = []
    by_ticker = {h.ticker: h for h in scope}
    for intake in sorted(ROOT.glob("*/third-party-analyses/drive-intake")):
        ticker = intake.parts[-3]
        pdfs = sorted(p for p in intake.glob("*.pdf"))
        if not pdfs:
            continue
        h = by_ticker.get(ticker)
        if h is None:
            continue  # not a held name; out of scope by construction
        research = ROOT / ticker / "research"
        checks = sorted(research.glob("cross_check_third_party_*.md")) if research.is_dir() else []
        newest_check = None
        if checks:
            m = re.search(r"(\d{4}-\d{2}-\d{2})", checks[-1].name)
            newest_check = m.group(1) if m else None
        out.append(Finding(
            "uncrosschecked_intake", ticker, "high",
            f"{len(pdfs)} un-cross-checked PDF(s) on {ticker}",
            f"${h.market_value:,.0f} held. Third-party analyses landed in drive-intake/ and no "
            f"cross-check covers them (latest cross-check: {newest_check or 'none'}).",
            h.market_value, _age(newest_check, today),
            [f"{ticker}/third-party-analyses/drive-intake/{p.name}" for p in pdfs[:4]],
        ))
    return out


def detect_missing_valuation(scope: list[Holding], today: date) -> list[Finding]:
    """Capital at risk with no valuation artifact at all."""
    out: list[Finding] = []
    for h in scope:
        if abs(h.market_value) < 1000:
            continue
        hits = list((ROOT / h.ticker).glob("**/valuation.json"))
        if not hits:
            out.append(Finding(
                "missing_valuation", h.ticker, "high",
                f"No valuation.json for {h.ticker}",
                f"${h.market_value:,.0f} held with no valuation artifact anywhere under {h.ticker}/.",
                h.market_value, None, [f"{h.ticker}/"],
            ))
    return out


def detect_pending_reviews(scope: list[Holding], today: date) -> list[Finding]:
    """Queue items that need a human verdict on a name holding capital."""
    import build_review_queue_rollup as rollup

    by_ticker = {h.ticker: h for h in scope}
    items = rollup.scan(today)
    grouped: dict[str, list[dict]] = {}
    for item in items:
        t = item.get("ticker")
        if t in by_ticker and item.get("disposition") != "expired":
            grouped.setdefault(t, []).append(item)

    out: list[Finding] = []
    for ticker, rows in grouped.items():
        h = by_ticker[ticker]
        oldest = max((r.get("age_days") or 0) for r in rows)
        blockers = sorted({b for r in rows for b in (r.get("blockers") or [])})
        out.append(Finding(
            "pending_review", ticker, "medium" if oldest < 90 else "high",
            f"{len(rows)} unresolved review item(s) on {ticker}, oldest {oldest}d",
            f"${h.market_value:,.0f} held. Blockers: {', '.join(blockers[:4]) or 'none recorded'}.",
            h.market_value, oldest,
            [f"_system/reviews/pending/{r['file']}" for r in rows[:4]],
        ))
    return out


def detect_attribution_gap(scope: list[Holding], meta: dict, today: date) -> list[Finding]:
    """Standing finding: owner attribution cannot be verified."""
    if meta.get("sleeve_tags_present"):
        return []
    total = meta.get("capital_at_risk") or 0.0
    return [Finding(
        "attribution_gap", "-", "high",
        "Drew's sleeve is unpopulated - owner attribution unverifiable",
        f"sleeve_tags.json is absent, so load_drew_symbols() returns an empty set and all "
        f"${total:,.0f} of single-stock capital attributes to Michael's residual book by "
        f"default. The Michael/Drew split shown anywhere downstream is not evidence.",
        0.0, None,
        ["_system/trading/sleeves/data/local/sleeve_tags.json",
         "_system/trading/portfolio_hub/allocation_policy.py"],
    )]


def detect_stalled_dispatch_queue(scope: list[Holding], today: date) -> list[Finding]:
    """A queue that is full while its lane reports success.

    `marvin-deep-dive.yml` triggers on pushes to `deep_dive_dispatch_queue.json`
    and has reported success on every run. On 2026-08-31 the queue still held 13
    tickers set on 2026-08-25, 9 of them with no dive at all, and exactly one
    deep-dive file had been touched repo-wide in that window. A green lane is not
    evidence of a drained queue, and nothing in this repo was comparing the two.
    """
    queue = load_json(DIVE_QUEUE, {}) or {}
    tickers = [str(t) for t in (queue.get("tickers") or [])]
    if not tickers:
        return []
    queued_on = str(queue.get("updated") or "")[:10] or None
    age = _age(queued_on, today)

    undelivered = []
    for ticker in tickers:
        research = ROOT / ticker / "research"
        dives = sorted(research.glob("deep_dive_*.md")) if research.is_dir() else []
        newest = None
        if dives:
            m = re.search(r"(\d{4}-\d{2}-\d{2})", dives[-1].name)
            newest = m.group(1) if m else None
        # Undelivered = no dive, or the newest dive predates the queue entry.
        if newest is None or (queued_on and newest < queued_on):
            undelivered.append(ticker)

    if not undelivered or age is None or age < 2:
        return []
    by_ticker = {h.ticker for h in scope}
    held = [t for t in undelivered if t in by_ticker]
    held_capital = sum(h.market_value for h in scope if h.ticker in set(held))
    # Systemic: ranked on the whole book, because a queue that does not drain
    # means no finding below it gets repaired regardless of its own size.
    capital = sum(h.market_value for h in scope)
    return [Finding(
        "stalled_queue", held[0] if held else "-", "systemic",
        f"Deep-dive queue has not drained in {age}d ({len(undelivered)}/{len(tickers)} undelivered)",
        f"`deep_dive_dispatch_queue.json` was set {queued_on} and {len(undelivered)} of "
        f"{len(tickers)} tickers still have no dive newer than that, yet marvin-deep-dive.yml "
        f"reports success on every run. Undelivered: {', '.join(undelivered[:8])}."
        + (f" {len(held)} of them are held positions (${held_capital:,.0f})." if held else ""),
        capital, age,
        ["_system/data/deep_dive_dispatch_queue.json", ".github/workflows/marvin-deep-dive.yml"],
    )]


def detect_stale_inputs(scope: list[Holding], today: date) -> list[Finding]:
    """The watchdog reporting its own blind spot.

    `positions.json` defines scope and has no refresh path: the collector that
    wrote it was deleted 2026-08-25 (CLAUDE.md rule 9) and the Flex replacement
    is parsed but never fetched. Without this the watchdog would rank a frozen
    book indefinitely and read as current.
    """
    source = scope_source()
    if not source.exists():
        return [Finding(
            "stale_input", "-", "systemic", "No positions snapshot at all",
            f"Neither {SCOPE_FILE.name} nor {POSITIONS.name} exists, so the watchdog has no "
            f"scope and every per-position finding below is absent rather than clean. Run "
            f"build_research_scope.py against the daily Flex statement.",
            0.0, None, [SCOPE_FILE.name, POSITIONS.name],
        )]
    snapshot = datetime.fromtimestamp(source.stat().st_mtime).date()
    age = (today - snapshot).days
    if age < 14:
        return []
    total = sum(h.market_value for h in scope)
    return [Finding(
        "stale_input", "-", "systemic",
        f"Positions snapshot is {age} days old",
        f"Scope and every dollar figure below come from a {snapshot.isoformat()} snapshot. "
        f"The collector that wrote it was deleted 2026-08-25, so this will not refresh unless "
        f"build_research_scope.py runs against the daily Flex statement on NY4. Positions "
        f"opened or closed since then are invisible "
        f"(${total:,.0f} currently assumed at risk).",
        total, age,
        ["_system/trading/sleeves/data/local/positions.json",
         "_system/trading/portfolio_hub/flex_ingest.py"],
    )]


DETECTORS = {
    "dive_quality": detect_dive_quality,
    "uncrosschecked_intake": detect_uncrosschecked_intake,
    "missing_valuation": detect_missing_valuation,
    "pending_review": detect_pending_reviews,
    "stalled_queue": detect_stalled_dispatch_queue,
    "stale_input": detect_stale_inputs,
}


# --------------------------------------------------------------------------
# rank + status
# --------------------------------------------------------------------------
def rank(findings: list[Finding]) -> list[Finding]:
    for f in findings:
        capital = 1.0 + math.log10(1.0 + abs(f.capital) / 1000.0)
        age = 1.0 + (f.age_days or 0) / 365.0
        f.score = round(SEVERITY_WEIGHT.get(f.severity, 1.0) * capital * age, 3)
    return sorted(findings, key=lambda f: (-f.score, -abs(f.capital), f.ticker))


def annotate_status(findings: list[Finding]) -> str:
    """Mark findings already in flight so they do not burn a slot."""
    try:
        proc = subprocess.run(
            ["gh", "pr", "list", "--state", "open", "--limit", "100",
             "--json", "number,title,headRefName"],
            capture_output=True, text=True, timeout=30, cwd=ROOT,
        )
        if proc.returncode != 0:
            return "unavailable"
        prs = json.loads(proc.stdout or "[]")
    except (OSError, ValueError, subprocess.SubprocessError):
        return "unavailable"

    hay = [f"{p.get('title', '')} {p.get('headRefName', '')}".upper() for p in prs]
    for f in findings:
        if f.ticker == "-":
            continue
        if any(re.search(rf"\b{re.escape(f.ticker.upper())}\b", h) for h in hay):
            f.status = "open PR"
    return "ok"


# --------------------------------------------------------------------------
# render
# --------------------------------------------------------------------------
def render_md(top: list[Finding], meta: dict, degraded: dict, today: date) -> str:
    lines = [
        "# Research Watchdog",
        "",
        f"Generated {today.isoformat()} by `_system/scripts/research_watchdog.py`.",
        "",
        f"Scope: **{meta['in_scope']} single-stock positions**, "
        f"**${meta['capital_at_risk']:,.0f}** at risk "
        f"(michael {meta['owners'].get('michael', 0)}, drew {meta['owners'].get('drew', 0)}). "
        f"Positions snapshot **{meta.get('snapshot_date')}**.",
        "",
    ]
    if not meta.get("sleeve_tags_present"):
        lines += ["> Owner split is unverified: `sleeve_tags.json` is absent, so every single "
                  "stock defaults to Michael's residual book.", ""]
    if degraded:
        lines += ["> Degraded detectors: " + ", ".join(f"`{k}` ({v})" for k, v in degraded.items()), ""]

    if not top:
        lines += ["Nothing above the reporting bar.", ""]
    for i, f in enumerate(top, 1):
        lines += [
            f"## {i}. {f.headline}",
            "",
            f"- **status** `{f.status}` - **severity** {f.severity} - **score** {f.score}"
            + (f" - **age** {f.age_days}d" if f.age_days is not None else ""),
            f"- {f.detail}",
        ]
        if f.evidence:
            lines.append("- evidence: " + ", ".join(f"`{e}`" for e in f.evidence))
        lines.append("")
    return "\n".join(lines) + "\n"



def build_receipt(meta: dict, ranked: list[Finding], degraded: dict, today: date) -> dict:
    """The only artifact this lane commits.

    Counts, not content. It must answer "did the watchdog run, against how fresh
    a book, and is anything rotting" without naming a single position or dollar
    figure - `_system/reviews/WATCHDOG.md` carries those and stays gitignored,
    because this repository is public.
    """
    by = lambda key: {k: sum(1 for f in ranked if getattr(f, key) == k)
                      for k in sorted({getattr(f, key) for f in ranked})}
    snapshot = meta.get("snapshot_date")
    age = _age(snapshot, today)
    return {
        "schema_version": 1,
        "generated_at": today.isoformat(),
        "scope_available": bool(meta.get("in_scope")),
        "scope_source": meta.get("scope_source"),
        "snapshot_date": snapshot,
        "snapshot_age_days": age,
        "in_scope_positions": meta.get("in_scope"),
        "owner_counts": meta.get("owners"),
        "sleeve_tags_present": meta.get("sleeve_tags_present"),
        "excluded_counts": meta.get("excluded"),
        "total_findings": len(ranked),
        "reported": min(TOP_N, len(ranked)),
        "by_severity": by("severity"),
        "by_detector": by("detector"),
        "degraded_detectors": degraded,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--all", action="store_true", help="print every finding, not just the top 3")
    ap.add_argument("--scope", action="store_true", help="print scope resolution and exit")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--no-pr", action="store_true", help="skip the gh open-PR lookup")
    ap.add_argument("--write", action="store_true", help="write JSON + WATCHDOG.md")
    args = ap.parse_args()

    today = date.today()
    scope, meta = build_scope()

    if args.scope:
        print(json.dumps(meta, indent=2))
        return 0

    findings: list[Finding] = list(detect_attribution_gap(scope, meta, today))
    degraded: dict[str, str] = {}
    for name, fn in DETECTORS.items():
        try:
            findings.extend(fn(scope, today))
        except Exception as exc:
            degraded[name] = f"{type(exc).__name__}: {exc}"

    ranked = rank(findings)
    pr_state = "skipped" if args.no_pr else annotate_status(ranked)
    actionable = [f for f in ranked if f.status != "fixed"]
    top = actionable if args.all else actionable[:TOP_N]

    payload = {
        "schema_version": 1,
        "generated_at": today.isoformat(),
        "scope": meta,
        "pr_lookup": pr_state,
        "degraded_detectors": degraded,
        "total_findings": len(ranked),
        "reported": len(top),
        "findings": [asdict(f) for f in top],
    }

    if args.write:
        for target in (OUT_JSON, OUT_MD, OUT_RECEIPT):
            target.parent.mkdir(parents=True, exist_ok=True)
        # Private (gitignored): these name held positions and their market values.
        OUT_JSON.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        OUT_MD.write_text(render_md(top, meta, degraded, today), encoding="utf-8")
        # Public (committed): counts only.
        OUT_RECEIPT.write_text(
            json.dumps(build_receipt(meta, ranked, degraded, today), indent=2) + "\n",
            encoding="utf-8")

    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(render_md(top, meta, degraded, today))
        if len(ranked) > len(top):
            print(f"({len(ranked) - len(top)} further findings suppressed; --all to see them)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

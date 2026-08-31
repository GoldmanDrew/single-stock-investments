#!/usr/bin/env python3
"""Refresh the Research Watchdog's scope from the daily IBKR Flex statement.

WHY THIS EXISTS. `research_watchdog.py` ranks findings by capital at risk, and
its scope came from `positions.json` - a sleeve-desk file written by the
collector that was deleted on 2026-08-25 for reconnect-storming the Gateway
(CLAUDE.md rule 9). Nothing has refreshed it since, so the watchdog was ranking
a frozen book while reading as current.

NO GATEWAY, NO NETWORK. This reads an XML file that ls-algo already fetches once
a day for its own accounting, at
`/home/spx/ls-algo/data/runs/<date>/ibkr_flex/flex_positions.xml`. It adds zero
IBKR requests - not fewer, zero - opens no socket, and takes no client id.

FX IS STATED, NOT INFERRED. Flex puts `fxRateToBase` on every row. The old
collector derived a rate from marketValue / (position x price), which on this
account returned ~1.0 for every foreign holding because marketValue already came
back in the contract currency - so yen and pence were published at dollar
magnitudes. Here CAD 801,879 at 0.71217 becomes USD 571,074 because IBKR said so.

BUCKETS ARE CARRIED FORWARD, NOT RECOMPUTED. This is the important one.
`OpenPosition` rows carry no `orderRef`, and `model` is empty on all 536 rows of
the real statement, so Flex cannot distinguish a share of AAPL that Michael owns
from one ls-algo owns. Recomputing with `classify_position` would resolve every
name in ls-algo's 924-symbol universe to `etf_ls` - moving APLD, AXP, BRK B and
SMR out of the research book purely because a systematic strategy also trades
them. So a symbol that already has a bucket keeps it, and a symbol that does not
is classified fresh AND listed under `needs_review` rather than silently
assigned.

Usage:
  python _system/scripts/build_research_scope.py --flex <flex_positions.xml>
  python _system/scripts/build_research_scope.py --flex <xml> --summary
  python _system/scripts/build_research_scope.py --latest-run <runs_dir>
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parents[1]
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ROOT))

from _system.trading.portfolio_hub.flex import parse_flex_file  # noqa: E402
# Imported rather than reimplemented: Flex reports at tax-lot level, and a second
# copy of the folding rule would be free to disagree with the one the ledger uses.
from _system.trading.portfolio_hub.flex_ingest import _fold_lots  # noqa: E402

import research_watchdog as watchdog  # noqa: E402

DEFAULT_OUT = ROOT / "_system/trading/sleeves/data/local/research_scope.json"
PRIOR_SOURCES = (
    ROOT / "_system/trading/sleeves/data/local/research_scope.json",
    ROOT / "_system/trading/sleeves/data/local/positions.json",
)
SPX_NAMES = {"SPX", "SPXW", "XSP"}


def _dec(value) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _float(value: Decimal | None) -> float | None:
    return None if value is None else float(value)


def prior_buckets() -> tuple[dict[str, str], str | None]:
    """symbol -> bucket, from the most recent scope we already trust."""
    for path in PRIOR_SOURCES:
        rows = watchdog.load_json(path, None)
        if not rows:
            continue
        mapping = {}
        for row in rows:
            symbol = str(row.get("symbol") or "").upper().strip()
            bucket = (row.get("classification") or {}).get("bucket")
            if symbol and bucket:
                mapping[symbol] = str(bucket)
        if mapping:
            return mapping, path.name
    return {}, None


def classify_fresh(symbol: str, name: str, sec_type: str) -> tuple[str, str]:
    """Only for symbols with no prior bucket. Conservative and always flagged."""
    upper = symbol.upper()
    if sec_type in {"OPT", "FOP"} or any(n in upper for n in SPX_NAMES):
        if any(n in upper for n in SPX_NAMES):
            return "spx_0dte", "spx_symbol"
    if watchdog.is_wrapper(symbol, name, watchdog.levered_wrapper_symbols()):
        return "etf_ls", "levered_wrapper"
    # Everything else lands in Michael's residual book, matching
    # allocation_policy.classify_policy_position, and is reported for review.
    return "michael", "residual_unreviewed"


def build_rows(flex_xml: Path, account_alias: str) -> tuple[list[dict], dict]:
    parsed = parse_flex_file(flex_xml, account_alias=account_alias)
    prior, prior_name = prior_buckets()

    rows: list[dict] = []
    needs_review: list[str] = []
    no_fx: list[str] = []
    for lot in _fold_lots(parsed["positions"]):
        symbol = str(lot.get("symbol") or lot.get("local_symbol") or "").upper().strip()
        if not symbol:
            continue
        name = str(lot.get("description") or "")
        sec_type = str(lot.get("sec_type") or "STK").upper()
        currency = str(lot.get("currency") or "USD").upper()

        native = _dec(lot.get("market_value"))
        rate = _dec(lot.get("fx_rate_to_base"))
        if currency == "USD":
            rate = Decimal(1)
        if rate is None or rate <= 0:
            # Never guess a rate. A position we cannot value in USD is carried
            # with a null marketValue so the ranker skips it instead of ranking
            # a foreign magnitude as though it were dollars.
            no_fx.append(symbol)
            usd = None
        else:
            usd = None if native is None else native * rate

        bucket = prior.get(symbol)
        if bucket:
            reason = "carried_forward"
        else:
            bucket, reason = classify_fresh(symbol, name, sec_type)
            # A wrapper or an SPX line is identified from the instrument itself,
            # so it needs no human. Only a name that landed in the research book
            # on the residual rule does - that is the one the watchdog will start
            # ranking, and nothing has confirmed it belongs there.
            if reason == "residual_unreviewed":
                needs_review.append(symbol)

        rows.append({
            "account": parsed.get("account_alias"),
            "symbol": symbol,
            "localSymbol": lot.get("local_symbol") or symbol,
            "secType": sec_type,
            "currency": currency,
            "conId": int(lot.get("conid") or 0),
            "qty": _float(_dec(lot.get("quantity"))),
            "mark": _float(_dec(lot.get("mark"))),
            "marketValue": _float(usd),
            "marketValueNative": _float(native),
            "fxRateToBase": _float(rate),
            "name": name,
            "orderRef": "",
            "classification": {"ticker": symbol, "bucket": bucket, "reason": reason},
        })

    meta = {
        "schema_version": 1,
        "source": "ibkr_flex",
        "flex_file": flex_xml.name,
        "session_date": parsed.get("session_date"),
        "account_alias": parsed.get("account_alias"),
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "lot_rows": len(parsed["positions"]),
        "folded_rows": len(rows),
        "prior_bucket_source": prior_name,
        "carried_forward": sum(1 for r in rows if r["classification"]["reason"] == "carried_forward"),
        "needs_review": sorted(needs_review),
        "unvalued_no_fx": sorted(no_fx),
    }
    return rows, meta


def latest_flex_positions(runs_dir: Path) -> Path | None:
    """Newest run directory that actually contains a positions statement.

    Newest directory alone is not enough: the directory is created before the
    Flex statement finishes generating, and IBKR can take minutes to build one.
    Mirrors the guard in deploy/user/publish-flex-book.sh.
    """
    if not runs_dir.is_dir():
        return None
    dated = sorted((d for d in runs_dir.iterdir()
                    if d.is_dir() and re.fullmatch(r"\d{4}-\d{2}-\d{2}", d.name)),
                   key=lambda d: d.name, reverse=True)
    for day in dated[:5]:
        candidate = day / "ibkr_flex" / "flex_positions.xml"
        if candidate.is_file() and candidate.stat().st_size > 0:
            return candidate
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    source = ap.add_mutually_exclusive_group(required=True)
    source.add_argument("--flex", type=Path, help="path to flex_positions.xml")
    source.add_argument("--latest-run", type=Path,
                        help="ls-algo runs directory; picks the newest run with a statement")
    ap.add_argument("--account", default="U805366")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--summary", action="store_true", help="print what changed")
    ap.add_argument("--dry-run", action="store_true", help="do not write")
    ap.add_argument("--force", action="store_true",
                    help="write even if the statement is older than the existing scope")
    args = ap.parse_args()

    flex_xml = args.flex
    if flex_xml is None:
        flex_xml = latest_flex_positions(args.latest_run)
        if flex_xml is None:
            print(f"no flex_positions.xml in the last 5 run directories under {args.latest_run}")
            return 0  # nothing to publish is not a failure; the timer runs daily
    if not flex_xml.is_file():
        print(f"error: {flex_xml} does not exist")
        return 1

    rows, meta = build_rows(flex_xml, args.account)

    # Never move the book backwards. `_external/ls-algo` on a developer machine
    # is a stale clone of the runs directory that lives on NY4, so pointing this
    # at the wrong path silently rewinds scope by weeks - and a rewound snapshot
    # reads exactly like a current one. Same reasoning as flex-publish's
    # --stale-hours: republishing a frozen book as current is the failure.
    # The floor is the newer of (a) the session date of the scope we already
    # wrote and (b) the as-of date of the fallback the watchdog is using today.
    # (b) matters on the FIRST run, when there is no prior meta at all: without
    # it, pointing at a stale runs directory silently rewinds an Aug 13 book to
    # a Jul 15 one, and the watchdog prefers the newly written file.
    #
    # (b) is the file's MTIME, because positions.json carries no date of its own.
    # That makes it a copy artifact: `scp` without -p, a fresh clone or an rsync
    # stamps it with today and this guard then blocks every future statement as
    # a "rewind", freezing scope permanently - which is the exact failure it
    # exists to prevent. Copy the fallback with `scp -p`. After one successful
    # run this path is moot: research_scope_meta.json carries a real session_date.
    prior_meta = watchdog.load_json(args.out.parent / "research_scope_meta.json", {}) or {}
    floor, floor_label = str(prior_meta.get("session_date") or ""), "existing scope"
    fallback = watchdog.POSITIONS
    if fallback.exists():
        as_of = datetime.fromtimestamp(fallback.stat().st_mtime).date().isoformat()
        if as_of > floor:
            floor, floor_label = as_of, fallback.name
    if floor and str(meta["session_date"]) < floor and not args.force:
        print(f"refusing to rewind scope: statement is {meta['session_date']}, "
              f"{floor_label} is {floor}. Pass --force to override.")
        return 1

    if not args.dry_run:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
        (args.out.parent / "research_scope_meta.json").write_text(
            json.dumps(meta, indent=2) + "\n", encoding="utf-8")

    if args.summary or args.dry_run:
        print(json.dumps(meta, indent=2))
    else:
        print(f"{meta['folded_rows']} positions from {meta['lot_rows']} lots "
              f"(session {meta['session_date']}), {meta['carried_forward']} carried forward, "
              f"{len(meta['needs_review'])} need review")
    return 0


if __name__ == "__main__":
    sys.exit(main())

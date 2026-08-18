"""Snapshot the configured IBKR account and classify its legacy Drew/Michael views."""

from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from _system.trading.sleeves.book import build_book, export_static_books
from _system.trading.sleeves.classify_positions import classify_positions, expand_blacklist_symbols
from _system.trading.sleeves.config_loader import (
    load_blacklist,
    load_config,
    load_etf_ls_universe,
    load_etf_to_under,
)
from _system.trading.sleeves.flex_positions import parse_flex_positions
from _system.trading.sleeves.ingest import post_ingest
from _system.trading.sleeves.store import SleeveStore


def _maybe_ingest(payload: Mapping[str, Any], cfg: Mapping[str, Any]) -> dict[str, Any] | None:
    url = str((cfg.get("ingest") or {}).get("url") or os.environ.get("SLEEVE_INGEST_URL") or "").strip()
    token = os.environ.get(str((cfg.get("ingest") or {}).get("token_env") or "SLEEVE_INGEST_TOKEN") or "")
    if not url or not token:
        return None
    return post_ingest(url, token, dict(payload))


def merge_flex_marks(rows: list[dict[str, Any]], flex_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """When TWS has no last for a foreign name, avgCost masquerades as the mark. Prefer Flex."""
    by_con = {int(row.get("conId") or 0): row for row in flex_rows if row.get("conId")}
    out = []
    for row in rows:
        flex = by_con.get(int(row.get("conId") or 0))
        if not flex:
            out.append(row)
            continue
        mark = float(row.get("mark") or 0)
        avg = float(row.get("avgCost") or 0)
        if avg and abs(mark - avg) < 1e-4:
            updated = dict(row)
            updated["mark"] = flex.get("mark")
            updated["marketValue"] = flex.get("marketValue")
            if flex.get("costUsd") is not None:
                updated["costUsd"] = flex.get("costUsd")
            if flex.get("name"):
                updated["name"] = flex.get("name")
            out.append(updated)
        else:
            out.append(row)
    return out


def load_positions(
    cfg: Mapping[str, Any],
    *,
    supplied: list[Mapping[str, Any]] | None = None,
    flex_path: Path | None = None,
    flex_marks: Path | None = None,
) -> tuple[list[dict[str, Any]], str]:
    if supplied is not None:
        return [dict(row) for row in supplied], "supplied"
    account = str((cfg.get("ibkr") or {}).get("account_id") or "").strip()
    if flex_path is not None:
        return parse_flex_positions(flex_path, account_id=account), f"flex:{flex_path.name}"
    live_error: Exception | None = None
    try:
        from _system.trading.sleeves.ib_client import connect_ib, fetch_positions

        ib = connect_ib("sync", cfg, readonly=True)
        try:
            rows = fetch_positions(ib, account)
        finally:
            ib.disconnect()
        marks_path = flex_marks
        if marks_path is None:
            env_marks = os.environ.get("IBKR_FLEX_POSITIONS_XML") or os.environ.get("SLEEVE_FLEX_XML")
            marks_path = Path(env_marks) if env_marks else None
        if marks_path and marks_path.is_file():
            rows = merge_flex_marks(rows, parse_flex_positions(marks_path, account_id=account))
            return rows, "ib_live+flex_marks"
        return rows, "ib_live"
    except Exception as exc:
        live_error = exc
    env_path = os.environ.get("IBKR_FLEX_POSITIONS_XML") or os.environ.get("SLEEVE_FLEX_XML")
    path = Path(env_path) if env_path else None
    if path and path.is_file():
        return parse_flex_positions(path, account_id=account), f"flex:{path.name}"
    raise RuntimeError(
        "Could not read the configured IBKR account from TWS/Gateway. Start local TWS on port 7496 "
        "(NY4 Gateway must be logged out), or pass --flex path/to/flex_positions.xml. "
        f"Live error: {live_error}"
    ) from live_error


def sync_holdings(
    store: SleeveStore,
    cfg: Mapping[str, Any] | None = None,
    *,
    positions: list[Mapping[str, Any]] | None = None,
    flex_path: Path | None = None,
    flex_marks: Path | None = None,
    ingest: bool = True,
    write_dashboard: bool = True,
) -> dict[str, Any]:
    cfg = cfg or load_config()
    rows, source = load_positions(cfg, supplied=positions, flex_path=flex_path, flex_marks=flex_marks)
    family = expand_blacklist_symbols(load_blacklist(cfg), load_etf_to_under(cfg))
    letf = load_etf_ls_universe(cfg)
    classified = classify_positions(rows, blacklist_family=family, etf_ls_symbols=letf)
    tags = {int(t["con_id"]): t for t in store.sleeve_tags() if t.get("con_id")}
    tags_by_ticker = {(t.get("owner"), str(t.get("ticker") or "").upper()): t for t in store.sleeve_tags()}
    for row in classified:
        cls = row.get("classification") or {}
        if cls.get("bucket") in {"spx_0dte", "etf_ls"}:
            continue
        con_id = int(row.get("conId") or 0)
        tag = tags.get(con_id)
        if tag and tag.get("owner") in {"drew", "michael"}:
            row["classification"] = {
                "ticker": cls.get("ticker") or row.get("symbol"),
                "bucket": tag["owner"],
                "reason": "sleeve_tag",
                "owner": tag["owner"],
            }
            continue
        # Drew fills without a matching conId still win on ticker if tagged.
        symbol = str(row.get("symbol") or "").upper()
        drew_tag = tags_by_ticker.get(("drew", symbol))
        if drew_tag:
            row["classification"] = {
                "ticker": cls.get("ticker") or row.get("symbol"),
                "bucket": "drew",
                "reason": "sleeve_tag",
                "owner": "drew",
            }
    store.replace_positions(classified)
    store.append_audit([row["classification"] for row in classified])
    if write_dashboard:
        export_static_books(store, cfg, source=source)
    buckets = Counter((row.get("classification") or {}).get("bucket") for row in classified)
    michael = build_book("michael", store, cfg)
    drew = build_book("drew", store, cfg)
    michael["source"] = source
    drew["source"] = source
    ingest_result: dict[str, Any] = {}
    if ingest:
        for owner, book in (("michael", michael), ("drew", drew)):
            try:
                ingest_result[owner] = _maybe_ingest(
                    {
                        "kind": "sync",
                        "book": book,
                        "audit": [row["classification"] for row in classified if (row.get("classification") or {}).get("owner") == owner],
                    },
                    cfg,
                )
            except Exception as exc:
                ingest_result[owner] = {"error": str(exc)}
    return {
        "source": source,
        "count": len(classified),
        "buckets": dict(buckets),
        "michael": michael,
        "drew": drew,
        "ingest": ingest_result,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sync the configured IBKR account into Michael / Drew sleeves")
    parser.add_argument("--flex", type=Path, help="IBKR Flex OpenPositions XML if TWS is down")
    parser.add_argument("--flex-marks", type=Path, help="Overlay Flex marks onto a live TWS snapshot")
    parser.add_argument("--no-ingest", action="store_true", help="Write local JSON only")
    args = parser.parse_args(argv)
    result = sync_holdings(
        SleeveStore(),
        flex_path=args.flex,
        flex_marks=args.flex_marks,
        ingest=not args.no_ingest,
    )
    michael = result["michael"]["header"]
    drew = result["drew"]["header"]
    print(
        f"source={result['source']} rows={result['count']} buckets={result['buckets']}\n"
        f"Michael names={michael.get('open_names')} nav={michael.get('nav_usd')}\n"
        f"Drew names={drew.get('open_names')} nav={drew.get('nav_usd')}\n"
        f"ingest={result['ingest']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

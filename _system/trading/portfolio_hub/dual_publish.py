from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .adapters import (
    normalize_ls_bucket5_live,
    normalize_ls_bucket5_product,
    normalize_ls_snapshot,
    normalize_spx_status,
)
from .publisher import publish_payload


PRODUCER_ADAPTERS = {
    "spx_0dte": normalize_spx_status,
    "ls_risk": normalize_ls_snapshot,
    "ls_bucket5_live": normalize_ls_bucket5_live,
    "ls_bucket5_product": normalize_ls_bucket5_product,
}


def _load(source: dict[str, Any] | Path) -> dict[str, Any]:
    if isinstance(source, Path):
        return json.loads(source.read_text(encoding="utf-8"))
    return source


def normalize_producer(producer: str, source: dict[str, Any] | Path, *, source_run_id: str | None = None) -> dict[str, Any]:
    adapter = PRODUCER_ADAPTERS.get(producer)
    if adapter is None:
        raise ValueError(f"unsupported producer {producer}")
    payload = adapter(_load(source), source_run_id=source_run_id)
    assert_producer_semantics(payload)
    return payload


def assert_producer_semantics(payload: dict[str, Any]) -> dict[str, Any]:
    producer = payload.get("producer")
    if producer not in PRODUCER_ADAPTERS:
        raise ValueError(f"unsupported producer {producer}")
    if payload.get("schema_version") != "strategy_snapshot.v1":
        raise ValueError("producer snapshot must use strategy_snapshot.v1")
    for row in payload.get("rows") or []:
        if not row.get("row_id") or not row.get("reconciliation_role") or not row.get("exposure_basis"):
            raise ValueError("strategy rows require role and exposure basis")
        if producer == "spx_0dte" and row.get("strategy") not in {None, "spx_0dte"}:
            raise ValueError("SPX snapshot mixed non-SPX strategy semantics")
        if producer == "ls_risk" and row.get("strategy") != "leveraged_etf":
            raise ValueError("LS snapshot mixed non-LETF strategy semantics")
        if producer == "ls_bucket5_live" and row.get("bucket") != "B5":
            raise ValueError("live B5 snapshot leaked a non-B5 row")
        if producer == "ls_bucket5_product" and (row.get("reconciliation_role") != "research_only" or row.get("conid")):
            raise ValueError("B5 product snapshot cannot broker-reconcile")
    return payload


def build_dual_publish_bundle(
    *,
    spx: dict[str, Any] | Path | None = None,
    ls_risk: dict[str, Any] | Path | None = None,
    ls_bucket5_live: dict[str, Any] | Path | None = None,
    ls_bucket5_product: dict[str, Any] | Path | None = None,
) -> list[dict[str, Any]]:
    snapshots: list[dict[str, Any]] = []
    mapping = {
        "spx_0dte": spx,
        "ls_risk": ls_risk,
        "ls_bucket5_live": ls_bucket5_live,
        "ls_bucket5_product": ls_bucket5_product,
    }
    for producer, source in mapping.items():
        if source is None:
            continue
        snapshots.append(normalize_producer(producer, source))
    producers = [row["producer"] for row in snapshots]
    if len(producers) != len(set(producers)):
        raise ValueError("duplicate producer in dual-publish bundle")
    if "spx_0dte" in producers and "ls_risk" in producers:
        spx_ids = {row.get("conid") for snap in snapshots if snap["producer"] == "spx_0dte" for row in snap["rows"] if row.get("conid")}
        ls_ids = {row.get("conid") for snap in snapshots if snap["producer"] == "ls_risk" for row in snap["rows"] if row.get("conid")}
        overlap = spx_ids & ls_ids
        if overlap:
            raise ValueError(f"SPX and LS snapshots share broker conId values: {sorted(overlap)}")
    return snapshots


def write_dual_publish_bundle(snapshots: list[dict[str, Any]], output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for payload in snapshots:
        path = output_dir / f"{payload['producer']}.{payload['source_run_id']}.json"
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        written.append(path)
    return written


def publish_dual_bundle(url: str, token: str, snapshots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [publish_payload(url, token, payload) for payload in snapshots]

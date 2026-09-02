#!/usr/bin/env python3
"""Bound high-frequency dashboard history before D1 migrations run.

The portfolio publisher archives every raw payload in R2, while D1 serves the
current dashboard and its daily NAV history.  Keeping every 30-second D1
snapshot duplicates the archive and can fill a free-tier database quickly.

This script deliberately runs before migrations: a database at its size limit
may not have enough headroom for ALTER TABLE, but it can still delete rows.
Every delete is batched so D1 does not have to rewrite a large table in one
statement.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any


Execute = Callable[[str], int]

PORTFOLIO_REFERENCES = (
    "portfolio_reconciliation_breaks",
    "portfolio_strategy_snapshots",
    "portfolio_allocation_projections",
    "portfolio_flex_sessions",
)

# These tables are useful as bounded history, not as an indefinite event log.
# Portfolio NAV is handled separately because it needs daily downsampling.
DEFAULT_TIME_POLICIES = (
    ("criticality_snapshots", "as_of", 14),
    ("flow_stress_snapshots", "as_of", 14),
    ("market_risk_component_snapshots", "as_of", 14),
    ("market_risk_ingest_runs", "received_at", 30),
    ("market_risk_ingest_nonces", "received_at", 2),
    ("portfolio_ingest_nonces", "received_at", 2),
    ("sleeve_ingest_nonces", "received_at", 2),
    ("sleeve_classifier_audit", "as_of", 90),
    ("sleeve_marks", "as_of", 400),
    ("price_observations", "observed_on", 3650),
    ("ohlcv_observations", "observed_on", 3650),
    ("technical_snapshots", "as_of_date", 3650),
    ("capitulation_snapshots", "as_of_date", 3650),
    ("market_context_snapshots", "as_of_date", 3650),
    ("market_structure_snapshots", "as_of_date", 3650),
)


def table_names(connection: sqlite3.Connection) -> set[str]:
    """Return SQLite table names; kept small so policy tests use real SQL."""
    return {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }


def _portfolio_candidates(batch_size: int) -> str:
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    return f"""
WITH ibkr_ranked AS (
  SELECT source_run_id,
         ROW_NUMBER() OVER (
           PARTITION BY COALESCE(account_alias, ''), date(as_of)
           ORDER BY as_of DESC, received_at DESC, source_run_id DESC
         ) AS keep_rank
  FROM portfolio_source_runs
  WHERE source = 'ibkr' AND complete = 1 AND date(as_of) < date('now')
), other_ranked AS (
  SELECT source_run_id,
         ROW_NUMBER() OVER (
           PARTITION BY source, COALESCE(account_alias, '')
           ORDER BY as_of DESC, received_at DESC, source_run_id DESC
         ) AS keep_rank
  FROM portfolio_source_runs
  WHERE source NOT IN ('ibkr', 'ibkr_flex')
), candidates AS (
  SELECT source_run_id FROM ibkr_ranked WHERE keep_rank > 1
  UNION
  SELECT source_run_id FROM other_ranked WHERE keep_rank > 1
  UNION
  SELECT source_run_id FROM portfolio_source_runs
   WHERE complete = 0 AND received_at < datetime('now', '-1 day')
), batch AS (
  SELECT source_run_id FROM candidates LIMIT {int(batch_size)}
)
""".strip()


def prune_portfolio_history(
    execute: Execute,
    existing_tables: set[str],
    *,
    batch_size: int = 100,
    max_batches: int = 10_000,
) -> int:
    """Keep today's IBKR detail, one close per prior day, and latest producers."""
    if "portfolio_source_runs" not in existing_tables:
        return 0
    cte = _portfolio_candidates(batch_size)
    total = 0
    for _ in range(max_batches):
        # These foreign keys intentionally pre-date ON DELETE CASCADE. Remove
        # their rows before the source run; account/position/order rows cascade.
        for table in PORTFOLIO_REFERENCES:
            if table in existing_tables:
                execute(
                    f"{cte}\nDELETE FROM {table} "
                    "WHERE source_run_id IN (SELECT source_run_id FROM batch)"
                )
        changed = execute(
            f"{cte}\nDELETE FROM portfolio_source_runs "
            "WHERE source_run_id IN (SELECT source_run_id FROM batch)"
        )
        total += changed
        if changed == 0:
            return total
    raise RuntimeError("portfolio retention exceeded the safety batch limit")


def prune_time_series(
    execute: Execute,
    existing_tables: set[str],
    *,
    batch_size: int = 1_000,
    max_batches: int = 10_000,
    policies: Iterable[tuple[str, str, int]] = DEFAULT_TIME_POLICIES,
) -> dict[str, int]:
    totals: dict[str, int] = {}
    for table, column, days in policies:
        if table not in existing_tables:
            continue
        total = 0
        for _ in range(max_batches):
            changed = execute(
                f"DELETE FROM {table} WHERE rowid IN ("
                f"SELECT rowid FROM {table} "
                f"WHERE {column} < datetime('now', '-{int(days)} days') "
                f"LIMIT {int(batch_size)})"
            )
            total += changed
            if changed == 0:
                break
        else:
            raise RuntimeError(f"{table} retention exceeded the safety batch limit")
        totals[table] = total
    return totals


def _decode_json(output: str) -> Any:
    decoder = json.JSONDecoder()
    for index, character in enumerate(output):
        if character not in "[{":
            continue
        try:
            value, _ = decoder.raw_decode(output[index:])
            return value
        except json.JSONDecodeError:
            continue
    raise RuntimeError("Wrangler did not return JSON")


def _statements(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        result = payload.get("result")
        if isinstance(result, list):
            return [row for row in result if isinstance(row, dict)]
        return [payload]
    return []


class WranglerD1:
    def __init__(self, wrangler: Path, database: str, config: Path):
        self.wrangler = str(wrangler)
        self.database = database
        self.config = str(config)

    def query(self, sql: str) -> list[dict[str, Any]]:
        command = [
            self.wrangler,
            "d1",
            "execute",
            self.database,
            "--remote",
            "--yes",
            "--command",
            sql,
            "--config",
            self.config,
            "--json",
        ]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode:
            detail = (result.stderr or result.stdout).strip()[-2_000:]
            raise RuntimeError(f"Wrangler D1 command failed: {detail}")
        return _statements(_decode_json(result.stdout))

    def execute(self, sql: str) -> int:
        return sum(int(row.get("meta", {}).get("changes", 0)) for row in self.query(sql))

    def tables(self) -> set[str]:
        rows: list[dict[str, Any]] = []
        for statement in self.query(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ):
            result = statement.get("results", [])
            if isinstance(result, list):
                rows.extend(row for row in result if isinstance(row, dict))
        return {str(row["name"]) for row in rows if row.get("name")}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--wrangler",
        type=Path,
        default=Path("dashboard/cloudflare/node_modules/.bin/wrangler"),
    )
    parser.add_argument("--database", default="DB")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=1_000)
    args = parser.parse_args()

    client = WranglerD1(args.wrangler, args.database, args.config)
    tables = client.tables()
    if not tables:
        print("D1 retention: new database; nothing to prune.")
        return 0

    portfolio_deleted = prune_portfolio_history(
        client.execute,
        tables,
        batch_size=max(1, min(args.batch_size, 250)),
    )
    time_deleted = prune_time_series(
        client.execute, tables, batch_size=max(1, args.batch_size)
    )
    total = portfolio_deleted + sum(time_deleted.values())
    details = ", ".join(
        f"{table}={count}" for table, count in time_deleted.items() if count
    )
    suffix = f" ({details})" if details else ""
    print(f"D1 retention removed {total} rows; portfolio_source_runs={portfolio_deleted}{suffix}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

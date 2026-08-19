from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterator

from .allocation_policy import POLICY_SOURCE_PREFIX, classify_policy_position, load_ls_universe, residual_quantity


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def decimal_text(value: Any) -> str:
    return format(Decimal(str(value)), "f")


class PortfolioLedger:
    """Transactional local ledger. Each state mutation and publish event commits together."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA foreign_keys=ON")
        self.connection.execute("PRAGMA busy_timeout=5000")

    def close(self) -> None:
        self.connection.close()

    def backup(self, destination: str | Path) -> Path:
        target = Path(destination)
        target.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(target) as output:
            self.connection.backup(output)
        return target

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self.connection:
            yield self.connection

    def migrate(self) -> None:
        migration_dir = Path(__file__).with_name("migrations")
        for path in sorted(migration_dir.glob("*.sql")):
            version = path.stem
            applied = self.connection.execute(
                "SELECT 1 FROM schema_migrations WHERE version=?", (version,)
            ).fetchone() if self._has_table("schema_migrations") else None
            if applied:
                continue
            with self.transaction() as db:
                db.executescript(path.read_text(encoding="utf-8"))
                db.execute(
                    "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                    (version, utc_now()),
                )

    def _has_table(self, name: str) -> bool:
        return self.connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
        ).fetchone() is not None

    def ingest_account_snapshot(self, payload: dict[str, Any]) -> str:
        required = {"schema_version", "source_run_id", "account_alias", "as_of", "complete", "account_values", "positions"}
        missing = required - payload.keys()
        if missing:
            raise ValueError(f"account snapshot missing {sorted(missing)}")
        if payload["schema_version"] != "account_snapshot.v1":
            raise ValueError("unsupported account snapshot schema")
        content = canonical_json(payload)
        digest = hashlib.sha256(content.encode()).hexdigest()
        snapshot_id = f"acct:{payload['account_alias']}:{payload['source_run_id']}"
        now = utc_now()
        with self.transaction() as db:
            db.execute(
                "INSERT OR IGNORE INTO source_runs VALUES (?, ?, ?, ?, ?, ?, ?)",
                (payload["source_run_id"], "ibkr", payload["schema_version"], payload["as_of"], int(payload["complete"]), digest, now),
            )
            existing = db.execute("SELECT content_sha256 FROM source_runs WHERE source_run_id=?", (payload["source_run_id"],)).fetchone()
            if existing["content_sha256"] != digest:
                raise ValueError("source_run_id reused with different content")
            db.execute(
                "INSERT OR IGNORE INTO account_snapshots VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (snapshot_id, payload["source_run_id"], payload["account_alias"], payload.get("gateway_session_id"), payload.get("base_currency", "USD"), payload["as_of"], int(payload["complete"]), canonical_json(payload.get("completeness") or {})),
            )
            for row in payload["account_values"]:
                db.execute(
                    "INSERT OR REPLACE INTO account_values VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (snapshot_id, row["tag"], row.get("currency", ""), row.get("segment") or "", row.get("model_code") or "", decimal_text(row["value"]), row["source"], row["as_of"]),
                )
            for row in payload["positions"]:
                quantity_unit = row.get("quantity_unit") or ("contracts" if str(row.get("sec_type") or "").upper() in {"OPT", "FOP"} else "shares")
                native_currency = row.get("native_currency") or row["currency"]
                market_value_base = row.get("market_value_base", row.get("market_value"))
                db.execute(
                    """INSERT OR REPLACE INTO position_snapshot_rows
                    (snapshot_id,account_alias,conid,model_code,symbol,local_symbol,description,sec_type,currency,exchange_name,
                     expiry,strike_decimal,right_code,multiplier_decimal,quantity_decimal,average_cost_decimal,mark_decimal,
                     market_value_decimal,unrealized_pnl_decimal,realized_pnl_decimal,daily_pnl_decimal,source,quality,as_of,
                     quantity_unit,native_currency,fx_rate_to_base_decimal,fx_as_of,fx_source,average_cost_native_decimal,
                     mark_native_decimal,market_value_native_decimal,market_value_base_decimal,unrealized_pnl_base_decimal,
                     realized_pnl_base_decimal,daily_pnl_base_decimal)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        snapshot_id, payload["account_alias"], int(row["conid"]), row.get("model_code") or "", row["symbol"],
                        row.get("local_symbol"), row.get("description"), row["sec_type"], row["currency"], row.get("exchange"),
                        row.get("expiry"), row.get("strike"), row.get("right"), row.get("multiplier"), decimal_text(row["quantity"]),
                        row.get("average_cost"), row.get("mark"), row.get("market_value"), row.get("unrealized_pnl"),
                        row.get("realized_pnl"), row.get("daily_pnl"), row["source"], row.get("quality", "unknown"), row["as_of"],
                        quantity_unit, native_currency, row.get("fx_rate_to_base"), row.get("fx_as_of"), row.get("fx_source"),
                        row.get("average_cost_native", row.get("average_cost")), row.get("mark_native", row.get("mark")),
                        row.get("market_value_native"), market_value_base,
                        row.get("unrealized_pnl_base", row.get("unrealized_pnl")),
                        row.get("realized_pnl_base", row.get("realized_pnl")),
                        row.get("daily_pnl_base", row.get("daily_pnl")),
                    ),
                )
            for row in payload.get("open_orders", []):
                db.execute(
                    """INSERT OR REPLACE INTO broker_order_snapshot_rows VALUES
                    (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (snapshot_id, payload["account_alias"], row.get("client_id"), row["order_id"], row.get("perm_id"), row.get("conid"), row.get("symbol"), row.get("action"), row.get("order_type"), row.get("total_quantity"), row.get("limit_price"), row.get("tif"), row.get("status"), row.get("order_ref"), row.get("ownership", "foreign"), row.get("parent_id"), row.get("oca_group"), row.get("as_of", payload["as_of"])),
                )
            if payload["complete"]:
                self._sync_policy_allocations(db, snapshot_id, payload, now)
            self._put_outbox(db, "account_snapshot.v1", snapshot_id, payload, now)
        return snapshot_id

    def _sync_policy_allocations(self, db: sqlite3.Connection, snapshot_id: str, payload: dict[str, Any], now: str) -> None:
        account_alias = payload["account_alias"]
        as_of = payload["as_of"]
        db.execute(
            "DELETE FROM allocation_lots WHERE account_alias=? AND source_event_id LIKE ?",
            (account_alias, f"{POLICY_SOURCE_PREFIX}%"),
        )
        ls_symbols = load_ls_universe()
        positions = db.execute(
            "SELECT * FROM position_snapshot_rows WHERE snapshot_id=? ORDER BY conid,model_code",
            (snapshot_id,),
        ).fetchall()
        for position in positions:
            policy = classify_policy_position(dict(position), ls_symbols=ls_symbols)
            if policy.strategy in {"letf", "spx_0dte"}:
                db.execute(
                    """UPDATE allocation_lots SET ended_at=?
                    WHERE account_alias=? AND conid=? AND model_code=? AND owner IN ('drew','michael')
                      AND effective_at<=? AND (ended_at IS NULL OR ended_at>?)""",
                    (as_of, account_alias, position["conid"], position["model_code"], as_of, as_of),
                )
                explicit = []
            else:
                explicit = db.execute(
                    """SELECT quantity_decimal FROM allocation_lots
                    WHERE account_alias=? AND conid=? AND model_code=? AND confidence IN ('explicit_override','legacy_inferred')
                      AND effective_at<=? AND (ended_at IS NULL OR ended_at>?)""",
                    (account_alias, position["conid"], position["model_code"], as_of, as_of),
                ).fetchall()
            remainder = residual_quantity(position["quantity_decimal"], [row["quantity_decimal"] for row in explicit])
            if remainder == 0:
                continue
            source_event_id = f"{POLICY_SOURCE_PREFIX}:{account_alias}:{position['conid']}:{position['model_code']}"
            allocation_id = str(uuid.uuid5(uuid.NAMESPACE_URL, source_event_id))
            db.execute(
                """INSERT INTO allocation_lots
                (allocation_id,account_alias,conid,model_code,owner,strategy,bucket,quantity_decimal,effective_at,ended_at,
                 confidence,source_event_id,note,created_at)
                VALUES (?,?,?,?,?,?,?,?,?,NULL,'authoritative',?,?,?)""",
                (
                    allocation_id, account_alias, position["conid"], position["model_code"], policy.owner,
                    policy.strategy, None, decimal_text(remainder), as_of, source_event_id, policy.reason, now,
                ),
            )
            self._put_outbox(db, "allocation.changed.v1", f"{allocation_id}:{snapshot_id}", {
                "allocation_id": allocation_id, "rule": policy.reason, "snapshot_id": snapshot_id,
            }, now)

    def add_allocation(self, *, account_alias: str, conid: int, model_code: str = "", owner: str,
                       strategy: str, quantity: Any, bucket: str | None = None,
                       confidence: str = "explicit_override", effective_at: str | None = None,
                       source_event_id: str | None = None, note: str | None = None) -> str:
        allocation_id = str(uuid.uuid4())
        now = utc_now()
        with self.transaction() as db:
            db.execute(
                """INSERT INTO allocation_lots
                (allocation_id,account_alias,conid,model_code,owner,strategy,bucket,quantity_decimal,effective_at,ended_at,confidence,source_event_id,note,created_at)
                VALUES (?,?,?,?,?,?,?,?,?,NULL,?,?,?,?)""",
                (allocation_id, account_alias, conid, model_code, owner, strategy, bucket, decimal_text(quantity), effective_at or now, confidence, source_event_id, note, now),
            )
            latest = db.execute(
                "SELECT snapshot_id,as_of,complete FROM account_snapshots WHERE account_alias=? ORDER BY as_of DESC LIMIT 1",
                (account_alias,),
            ).fetchone()
            if latest and latest["complete"]:
                self._sync_policy_allocations(db, latest["snapshot_id"], {
                    "account_alias": account_alias, "as_of": latest["as_of"],
                }, now)
            self._put_outbox(db, "allocation.changed.v1", allocation_id, {"allocation_id": allocation_id}, now)
        return allocation_id

    def add_cash_event(self, *, account_alias: str, owner: str, strategy: str, currency: str,
                       amount: Any, event_type: str, effective_at: str, source: str,
                       source_event_id: str | None = None) -> str:
        event_id = source_event_id or str(uuid.uuid4())
        now = utc_now()
        with self.transaction() as db:
            db.execute(
                """INSERT OR IGNORE INTO cash_allocation_events
                (event_id,account_alias,owner,strategy,currency,amount_decimal,event_type,effective_at,source,source_event_id,created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (event_id, account_alias, owner, strategy, currency, decimal_text(amount), event_type, effective_at, source, source_event_id, now),
            )
            self._put_outbox(db, "cash_allocation.changed.v1", event_id, {"event_id": event_id}, now)
        return event_id

    def reconcile_allocations(self, snapshot_id: str, tolerance: Decimal = Decimal("0.000001")) -> list[dict[str, Any]]:
        snapshot = self.connection.execute("SELECT * FROM account_snapshots WHERE snapshot_id=?", (snapshot_id,)).fetchone()
        if not snapshot:
            raise KeyError(snapshot_id)
        if not snapshot["complete"]:
            raise ValueError("cannot reconcile an incomplete broker snapshot")
        positions = self.connection.execute(
            "SELECT * FROM position_snapshot_rows WHERE snapshot_id=?", (snapshot_id,)
        ).fetchall()
        breaks: list[dict[str, Any]] = []
        now = utc_now()
        with self.transaction() as db:
            db.execute("DELETE FROM reconciliation_breaks WHERE snapshot_id=? AND break_type IN ('allocation_quantity','cash_allocation')", (snapshot_id,))
            for pos in positions:
                allocations = db.execute(
                    """SELECT quantity_decimal FROM allocation_lots
                    WHERE account_alias=? AND conid=? AND model_code=? AND effective_at<=?
                      AND (ended_at IS NULL OR ended_at>?)""",
                    (pos["account_alias"], pos["conid"], pos["model_code"], snapshot["as_of"], snapshot["as_of"]),
                ).fetchall()
                actual = sum((Decimal(r["quantity_decimal"]) for r in allocations), Decimal("0"))
                expected = Decimal(pos["quantity_decimal"])
                if abs(actual - expected) <= tolerance:
                    continue
                item = {
                    "break_id": str(uuid.uuid4()), "snapshot_id": snapshot_id, "account_alias": pos["account_alias"],
                    "conid": pos["conid"], "model_code": pos["model_code"], "break_type": "allocation_quantity",
                    "expected": decimal_text(expected), "actual": decimal_text(actual), "severity": "critical",
                    "details": {"symbol": pos["symbol"], "residual": decimal_text(expected - actual)},
                }
                db.execute(
                    """INSERT INTO reconciliation_breaks
                    (break_id,snapshot_id,account_alias,conid,model_code,break_type,expected_decimal,actual_decimal,severity,details_json,status,created_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,'open',?)""",
                    (item["break_id"], snapshot_id, item["account_alias"], item["conid"], item["model_code"], item["break_type"], item["expected"], item["actual"], item["severity"], canonical_json(item["details"]), now),
                )
                breaks.append(item)
            cash_rows = db.execute(
                "SELECT currency,value_decimal FROM account_values WHERE snapshot_id=? AND tag IN ('TotalCashValue','CashBalance')",
                (snapshot_id,),
            ).fetchall()
            for cash_row in cash_rows:
                allocated_rows = db.execute(
                    "SELECT amount_decimal FROM cash_allocation_events WHERE account_alias=? AND currency=? AND effective_at<=?",
                    (snapshot["account_alias"], cash_row["currency"], snapshot["as_of"]),
                ).fetchall()
                actual = sum((Decimal(row["amount_decimal"]) for row in allocated_rows), Decimal("0"))
                expected = Decimal(cash_row["value_decimal"])
                if abs(actual - expected) <= tolerance:
                    continue
                item = {
                    "break_id": str(uuid.uuid4()), "snapshot_id": snapshot_id, "account_alias": snapshot["account_alias"],
                    "conid": None, "model_code": "", "break_type": "cash_allocation", "expected": decimal_text(expected),
                    "actual": decimal_text(actual), "severity": "critical", "details": {"currency": cash_row["currency"], "residual": decimal_text(expected - actual)},
                }
                db.execute(
                    """INSERT INTO reconciliation_breaks
                    (break_id,snapshot_id,account_alias,conid,model_code,break_type,expected_decimal,actual_decimal,severity,details_json,status,created_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,'open',?)""",
                    (item["break_id"], snapshot_id, item["account_alias"], None, "", item["break_type"], item["expected"], item["actual"], item["severity"], canonical_json(item["details"]), now),
                )
                breaks.append(item)
            self._put_outbox(db, "reconciliation.v1", snapshot_id, {"snapshot_id": snapshot_id, "breaks": breaks}, now)
        return breaks

    def latest_portfolio(self, account_alias: str, owner: str = "all") -> dict[str, Any]:
        snap = self.connection.execute(
            "SELECT * FROM account_snapshots WHERE account_alias=? AND complete=1 ORDER BY as_of DESC LIMIT 1", (account_alias,)
        ).fetchone()
        if not snap:
            return {"status": "unknown", "reason": "no complete broker snapshot", "positions": [], "account_values": []}
        account_values = [dict(r) for r in self.connection.execute("SELECT * FROM account_values WHERE snapshot_id=?", (snap["snapshot_id"],))]
        positions = []
        for row in self.connection.execute("SELECT * FROM position_snapshot_rows WHERE snapshot_id=? ORDER BY symbol, conid", (snap["snapshot_id"],)):
            pos = dict(row)
            allocations = [dict(r) for r in self.connection.execute(
                """SELECT * FROM allocation_lots WHERE account_alias=? AND conid=? AND model_code=? AND effective_at<=?
                AND (ended_at IS NULL OR ended_at>?) ORDER BY owner,strategy""",
                (row["account_alias"], row["conid"], row["model_code"], snap["as_of"], snap["as_of"]),
            )]
            if owner != "all":
                allocations = [a for a in allocations if a["owner"] == owner]
                if not allocations:
                    continue
                pos["quantity_decimal"] = decimal_text(sum((Decimal(a["quantity_decimal"]) for a in allocations), Decimal("0")))
            pos["allocations"] = allocations
            positions.append(pos)
        breaks = [dict(r) for r in self.connection.execute("SELECT * FROM reconciliation_breaks WHERE snapshot_id=? AND status='open'", (snap["snapshot_id"],))]
        return {"schema_version": "portfolio_read_model.v1", "status": "complete", "scope": owner, "snapshot": dict(snap), "account_values": account_values, "positions": positions, "reconciliation_breaks": breaks}

    def allocation_projection(self, account_alias: str) -> dict[str, Any]:
        snap = self.connection.execute(
            "SELECT * FROM account_snapshots WHERE account_alias=? AND complete=1 ORDER BY as_of DESC LIMIT 1", (account_alias,)
        ).fetchone()
        if not snap:
            raise ValueError("no complete broker snapshot")
        allocations = [dict(row) for row in self.connection.execute(
            """SELECT * FROM allocation_lots WHERE account_alias=? AND effective_at<=?
            AND (ended_at IS NULL OR ended_at>?) ORDER BY conid,model_code,owner,strategy""",
            (account_alias, snap["as_of"], snap["as_of"]),
        )]
        cash_events = [dict(row) for row in self.connection.execute(
            "SELECT * FROM cash_allocation_events WHERE account_alias=? AND effective_at<=? ORDER BY effective_at,event_id",
            (account_alias, snap["as_of"]),
        )]
        breaks = [dict(row) for row in self.connection.execute(
            "SELECT * FROM reconciliation_breaks WHERE snapshot_id=? ORDER BY created_at", (snap["snapshot_id"],)
        )]
        order_events = [dict(row) for row in self.connection.execute(
            """SELECT e.*,i.account_alias,i.conid,i.order_ref FROM order_events e
            JOIN order_intents i USING(intent_uuid) WHERE i.account_alias=? ORDER BY e.created_at""", (account_alias,)
        )]
        for row in breaks:
            row["details"] = json.loads(row.pop("details_json"))
        for row in order_events:
            row["payload"] = json.loads(row.pop("payload_json"))
            row["state"] = row.pop("next_state")
        return {
            "schema_version": "allocation_projection.v1", "projection_id": str(uuid.uuid4()),
            "source_run_id": snap["source_run_id"], "account_alias": account_alias,
            "as_of": snap["as_of"], "allocations": allocations,
            "cash_events": cash_events,
            "reconciliation_breaks": breaks, "order_events": order_events,
        }

    def latest_account_snapshot_payload(self, account_alias: str) -> dict[str, Any]:
        snap = self.connection.execute(
            "SELECT * FROM account_snapshots WHERE account_alias=? AND complete=1 ORDER BY as_of DESC LIMIT 1", (account_alias,)
        ).fetchone()
        if not snap:
            raise ValueError("no complete broker snapshot")
        run = self.connection.execute("SELECT schema_version FROM source_runs WHERE source_run_id=?", (snap["source_run_id"],)).fetchone()
        values = []
        for row in self.connection.execute("SELECT * FROM account_values WHERE snapshot_id=?", (snap["snapshot_id"],)):
            values.append({"tag": row["tag"], "value": row["value_decimal"], "currency": row["currency"], "segment": row["segment"] or None, "model_code": row["model_code"] or None, "source": row["source"], "as_of": row["as_of"]})
        positions = []
        mapping = {
            "strike_decimal": "strike", "multiplier_decimal": "multiplier", "quantity_decimal": "quantity",
            "average_cost_decimal": "average_cost", "mark_decimal": "mark", "market_value_decimal": "market_value",
            "unrealized_pnl_decimal": "unrealized_pnl", "realized_pnl_decimal": "realized_pnl", "daily_pnl_decimal": "daily_pnl",
            "exchange_name": "exchange", "right_code": "right",
            "fx_rate_to_base_decimal": "fx_rate_to_base",
            "average_cost_native_decimal": "average_cost_native", "mark_native_decimal": "mark_native",
            "market_value_native_decimal": "market_value_native", "market_value_base_decimal": "market_value_base",
            "unrealized_pnl_base_decimal": "unrealized_pnl_base", "realized_pnl_base_decimal": "realized_pnl_base",
            "daily_pnl_base_decimal": "daily_pnl_base",
        }
        omit = {"snapshot_id", "as_of"}
        for row in self.connection.execute("SELECT * FROM position_snapshot_rows WHERE snapshot_id=? ORDER BY symbol,conid", (snap["snapshot_id"],)):
            item = {}
            for key, value in dict(row).items():
                if key in omit:
                    continue
                item[mapping.get(key, key)] = value
            item["as_of"] = row["as_of"]
            item["base_currency"] = snap["base_currency"]
            positions.append(item)
        open_orders = []
        order_mapping = {"total_quantity_decimal": "total_quantity", "limit_price_decimal": "limit_price"}
        for row in self.connection.execute("SELECT * FROM broker_order_snapshot_rows WHERE snapshot_id=? ORDER BY symbol,order_id", (snap["snapshot_id"],)):
            open_orders.append({order_mapping.get(key, key): value for key, value in dict(row).items() if key != "snapshot_id"})
        return {
            "schema_version": run["schema_version"], "source_run_id": snap["source_run_id"],
            "account_alias": snap["account_alias"], "gateway_session_id": snap["gateway_session_id"],
            "as_of": snap["as_of"], "complete": bool(snap["complete"]), "base_currency": snap["base_currency"],
            "completeness": json.loads(snap["completeness_json"]),
            "account_values": values, "positions": positions, "open_orders": open_orders,
        }

    def record_broker_event(self, event_key: str, event_type: str, account_alias: str, payload: dict[str, Any], **metadata: Any) -> bool:
        with self.transaction() as db:
            cursor = db.execute(
                """INSERT OR IGNORE INTO broker_events
                (event_key,event_type,account_alias,gateway_session_id,receive_seq,source_client_id,source_timestamp,received_at,payload_json)
                VALUES (?,?,?,?,?,?,?,?,?)""",
                (event_key, event_type, account_alias, metadata.get("gateway_session_id"), metadata.get("receive_seq"), metadata.get("source_client_id"), metadata.get("source_timestamp"), utc_now(), canonical_json(payload)),
            )
            return cursor.rowcount == 1

    def ingest_flex_eod(self, payload: dict[str, Any]) -> dict[str, Any]:
        if payload.get("schema_version") != "flex_eod.v1" or not payload.get("source_run_id") or not payload.get("session_date"):
            raise ValueError("invalid flex_eod.v1 payload")
        content = canonical_json(payload); digest = hashlib.sha256(content.encode()).hexdigest(); now = utc_now()
        account = payload["account_alias"]
        with self.transaction() as db:
            db.execute("INSERT OR IGNORE INTO source_runs VALUES (?,?,?,?,?,?,?)", (payload["source_run_id"], "ibkr_flex", payload["schema_version"], payload["as_of"], 1, digest, now))
            run = db.execute("SELECT content_sha256 FROM source_runs WHERE source_run_id=?", (payload["source_run_id"],)).fetchone()
            if run["content_sha256"] != digest:
                raise ValueError("source_run_id reused with different content")
            if db.execute("SELECT 1 FROM flex_session_versions WHERE source_run_id=?", (payload["source_run_id"],)).fetchone():
                return {"duplicate": True, "restatement": False}
            primary = db.execute("SELECT source_run_id FROM flex_session_versions WHERE account_alias=? AND session_date=? AND is_primary=1", (account, payload["session_date"])).fetchone()
            restatement = primary is not None
            db.execute("INSERT INTO flex_session_versions VALUES (?,?,?,?,?,?,?)", (payload["source_run_id"], account, payload["session_date"], 0 if restatement else 1, primary["source_run_id"] if primary else None, content, now))
            for trade in payload.get("trades") or []:
                exec_id = trade.get("exec_id") or trade.get("trade_id")
                if not exec_id or not trade.get("conid"):
                    continue
                intent = None
                if trade.get("order_ref"):
                    intent = db.execute("SELECT intent_uuid FROM order_intents WHERE order_ref=?", (trade["order_ref"],)).fetchone()
                db.execute(
                    """INSERT OR IGNORE INTO executions
                    (account_alias,exec_id,intent_uuid,perm_id,conid,quantity_decimal,price_decimal,side,executed_at,payload_json)
                    VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (account, exec_id, intent["intent_uuid"] if intent else None, None, int(trade["conid"]), decimal_text(trade.get("quantity") or 0), decimal_text(trade.get("price") or 0), "FLEX", trade.get("trade_time") or payload["as_of"], canonical_json(trade)),
                )
                if trade.get("commission") not in (None, ""):
                    db.execute("INSERT OR IGNORE INTO commissions VALUES (?,?,?,?,?,?)", (account, exec_id, decimal_text(trade["commission"]), trade.get("currency") or "", trade.get("realized_pnl"), canonical_json(trade)))
            for cash in payload.get("cash_transactions") or []:
                event_key = f"{account}:flex-cash:{cash.get('transaction_id') or hashlib.sha256(canonical_json(cash).encode()).hexdigest()}"
                db.execute("INSERT OR IGNORE INTO broker_events VALUES (?,?,?,?,?,?,?,?,?)", (event_key, "flex_cash_transaction", account, None, None, None, cash.get("date"), now, canonical_json(cash)))
            self._put_outbox(db, "flex_eod.v1", payload["source_run_id"], payload, now)
        return {"duplicate": False, "restatement": restatement, "restates_source_run_id": primary["source_run_id"] if primary else None}

    def pending_outbox(self, limit: int = 100) -> list[dict[str, Any]]:
        return [dict(r) for r in self.connection.execute(
            "SELECT * FROM outbox WHERE delivered_at IS NULL ORDER BY created_at LIMIT ?", (limit,)
        )]

    def mark_outbox_delivered(self, outbox_id: str) -> None:
        with self.transaction() as db:
            db.execute("UPDATE outbox SET delivered_at=?, attempts=attempts+1, last_error=NULL WHERE outbox_id=?", (utc_now(), outbox_id))

    @staticmethod
    def _put_outbox(db: sqlite3.Connection, topic: str, business_key: str, payload: dict[str, Any], now: str) -> None:
        db.execute(
            "INSERT OR IGNORE INTO outbox(outbox_id,topic,business_key,payload_json,created_at) VALUES (?,?,?,?,?)",
            (str(uuid.uuid4()), topic, business_key, canonical_json(payload), now),
        )

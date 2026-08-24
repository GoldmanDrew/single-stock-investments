from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Protocol

from .ledger import PortfolioLedger, canonical_json, decimal_text, utc_now


TERMINAL_STATES = {"Filled", "Cancelled", "Rejected"}
TRANSITIONS = {
    "Draft": {"Previewed", "Rejected"},
    "Previewed": {"Approved", "Rejected", "Expired"},
    "Approved": {"Submitting", "Rejected", "Expired"},
    "Submitting": {"Acknowledged", "SubmitUncertain", "Rejected"},
    "SubmitUncertain": {"Acknowledged", "Rejected", "Cancelled"},
    "Acknowledged": {"PartiallyFilled", "Filled", "CancelPending", "Rejected"},
    "PartiallyFilled": {"PartiallyFilled", "Filled", "CancelPending"},
    "CancelPending": {"Cancelled", "PartiallyFilled", "Filled"},
}


@dataclass(frozen=True)
class OrderIntent:
    account_alias: str
    conid: int
    contract_fingerprint: str
    action: str
    quantity: Decimal
    limit_price: Decimal
    owner: str
    strategy: str
    mode: str = "dry_run"
    tif: str = "DAY"
    outside_rth: bool = False
    reduce_only: bool | None = None
    intent_uuid: str = ""

    def normalized(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["intent_uuid"] = self.intent_uuid or str(uuid.uuid4())
        payload["quantity"] = decimal_text(self.quantity)
        payload["limit_price"] = decimal_text(self.limit_price)
        payload["reduce_only"] = self.action == "SELL" if self.reduce_only is None else self.reduce_only
        payload["schema_version"] = "order_intent.v1"
        return payload


class OrderBroker(Protocol):
    # Whether place_limit can reach the exchange. submit() routes on this, so a
    # broker that omits it is assumed to transmit -- the safe default, because a
    # simulator that forgets to say so merely gets refused, while a live bridge
    # that forgot would get trusted.
    transmits: bool

    # resolve/contract_identity are used by the command loop rather than by this
    # service, but they belong on the protocol: a broker that cannot say what a
    # conId *is* cannot produce a fingerprint a human could meaningfully approve.
    def resolve(self, request: dict[str, Any]) -> list[dict[str, Any]]: ...
    def contract_identity(self, conid: int) -> dict[str, Any]: ...
    def quote(self, conid: int) -> dict[str, Any]: ...
    def what_if(self, ticket: dict[str, Any]) -> dict[str, Any]: ...
    def place_limit(self, ticket: dict[str, Any]) -> dict[str, Any]: ...
    def find_owned_order(self, order_ref: str) -> dict[str, Any] | None: ...
    def cancel_owned_order(self, order_ref: str, client_id: int, order_id: int) -> dict[str, Any]: ...


class GuardedOrderService:
    def __init__(self, ledger: PortfolioLedger, broker: OrderBroker, approval_secret: str,
                 *, max_notional: Decimal = Decimal("25000"), approval_ttl_seconds: int = 120,
                 live_enabled: bool = False, quote_max_age_seconds: int = 10,
                 max_price_deviation_bps: Decimal = Decimal("500"), kill_switch: bool = False):
        if not approval_secret:
            raise ValueError("approval_secret is required")
        self.ledger = ledger
        self.broker = broker
        self.secret = approval_secret.encode()
        self.max_notional = max_notional
        self.approval_ttl_seconds = approval_ttl_seconds
        self.live_enabled = live_enabled
        self.quote_max_age_seconds = quote_max_age_seconds
        self.max_price_deviation_bps = max_price_deviation_bps
        self.kill_switch = kill_switch

    def create(self, intent: OrderIntent) -> dict[str, Any]:
        if self.kill_switch:
            raise ValueError("kill switch engaged")
        ticket = intent.normalized()
        self._validate(ticket)
        now = utc_now()
        ticket["order_ref"] = f"MAGIS|{ticket['strategy']}|{ticket['owner']}|{ticket['intent_uuid']}"
        with self.ledger.transaction() as db:
            db.execute(
                """INSERT INTO order_intents
                (intent_uuid,account_alias,conid,contract_fingerprint,action,quantity_decimal,limit_price_decimal,tif,outside_rth,reduce_only,owner,strategy,mode,state,order_ref,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,'Draft',?,?,?)""",
                (ticket["intent_uuid"], ticket["account_alias"], ticket["conid"], ticket["contract_fingerprint"], ticket["action"], ticket["quantity"], ticket["limit_price"], ticket["tif"], int(ticket["outside_rth"]), int(ticket["reduce_only"]), ticket["owner"], ticket["strategy"], ticket["mode"], ticket["order_ref"], now, now),
            )
            self._event(db, ticket["intent_uuid"], None, "Draft", "intent_created", ticket)
        return self.get(ticket["intent_uuid"])

    def preview(self, intent_uuid: str) -> dict[str, Any]:
        order = self.get(intent_uuid)
        if order["state"] != "Draft":
            raise ValueError("only Draft orders can be previewed")
        quote = self.broker.quote(order["conid"])
        limit_price = Decimal(order["limit_price_decimal"])
        quote_time = datetime.fromisoformat(str(quote["as_of"]).replace("Z", "+00:00"))
        if (datetime.now(timezone.utc) - quote_time).total_seconds() > self.quote_max_age_seconds:
            return self._transition(intent_uuid, "Rejected", "stale_quote", {"quote": quote})
        bid, ask = Decimal(str(quote["bid"])), Decimal(str(quote["ask"]))
        if bid <= 0 or ask < bid:
            return self._transition(intent_uuid, "Rejected", "invalid_nbbo", {"quote": quote})
        midpoint = (bid + ask) / 2
        deviation_bps = abs(limit_price - midpoint) / midpoint * Decimal("10000")
        if deviation_bps > self.max_price_deviation_bps:
            return self._transition(intent_uuid, "Rejected", "price_band", {"deviation_bps": decimal_text(deviation_bps)})
        minimum_tick = Decimal(str(quote.get("min_tick", "0.01")))
        if minimum_tick <= 0 or limit_price % minimum_tick != 0:
            return self._transition(intent_uuid, "Rejected", "invalid_market_tick", {"min_tick": decimal_text(minimum_tick)})
        if order["reduce_only"]:
            current = Decimal(str(quote.get("current_position", "0")))
            quantity = Decimal(order["quantity_decimal"])
            valid_reduce = (order["action"] == "SELL" and current > 0 and quantity <= current) or (order["action"] == "BUY" and current < 0 and quantity <= abs(current))
            if not valid_reduce:
                return self._transition(intent_uuid, "Rejected", "reduce_only_violation", {"current_position": decimal_text(current)})
        notional = abs(Decimal(order["quantity_decimal"]) * limit_price * Decimal(str(quote.get("multiplier", "1"))))
        if notional > self.max_notional:
            return self._transition(intent_uuid, "Rejected", "notional_limit", {"notional": decimal_text(notional)})
        preview = self.broker.what_if({**order, "whatIf": True, "transmit": True})
        return self._transition(intent_uuid, "Previewed", "preview_completed", {"quote": quote, "what_if": preview, "notional": decimal_text(notional)})

    def issue_approval(self, intent_uuid: str) -> dict[str, str]:
        order = self.get(intent_uuid)
        if order["state"] != "Previewed":
            raise ValueError("order must be Previewed")
        expires = datetime.now(timezone.utc) + timedelta(seconds=self.approval_ttl_seconds)
        binding = self._approval_binding(order, expires)
        token = hmac.new(self.secret, binding.encode(), hashlib.sha256).hexdigest()
        with self.ledger.transaction() as db:
            db.execute("UPDATE order_intents SET approval_hash=?, approval_expires_at=?, updated_at=? WHERE intent_uuid=?", (token, expires.isoformat(), utc_now(), intent_uuid))
        return {"token": token, "expires_at": expires.isoformat(), "contract_fingerprint": order["contract_fingerprint"]}

    def approve(self, intent_uuid: str, token: str, contract_fingerprint: str) -> dict[str, Any]:
        order = self.get(intent_uuid)
        if order["state"] != "Previewed" or contract_fingerprint != order["contract_fingerprint"]:
            raise ValueError("approval does not match the exact contract")
        expires = datetime.fromisoformat(order["approval_expires_at"])
        expected = hmac.new(self.secret, self._approval_binding(order, expires).encode(), hashlib.sha256).hexdigest()
        if datetime.now(timezone.utc) >= expires or not hmac.compare_digest(token, expected):
            raise ValueError("approval expired or invalid")
        return self._transition(intent_uuid, "Approved", "human_approved", {"contract_fingerprint": contract_fingerprint})

    def submit(self, intent_uuid: str) -> dict[str, Any]:
        order = self.get(intent_uuid)
        if order["state"] != "Approved":
            raise ValueError("order must be Approved")
        if self.kill_switch:
            return self._transition(intent_uuid, "Rejected", "kill_switch_engaged", {})
        if order["mode"] == "live" and not self.live_enabled:
            return self._transition(intent_uuid, "Rejected", "live_interlock_disabled", {})
        # A non-live ticket must never reach a broker that can transmit.
        #
        # Only `dry_run` was short-circuited below, so a `paper` ticket fell
        # through to place_limit(transmit=True) -- and the browser pins every
        # ticket it creates to `paper`. That was safe only for as long as the
        # configured broker happened to be a simulator. Making the broker declare
        # whether it transmits turns "safe because of how it was wired" into
        # "safe because it is checked".
        if order["mode"] != "live" and getattr(self.broker, "transmits", True):
            return self._transition(intent_uuid, "Rejected", "paper_ticket_on_transmitting_broker", {
                "mode": order["mode"],
                "detail": "this hub is routed live; a paper ticket cannot be filled here",
            })
        self._transition(intent_uuid, "Submitting", "submit_started", {})
        if order["mode"] == "dry_run":
            return self._transition(intent_uuid, "Acknowledged", "dry_run_acknowledged", {"transmitted": False})
        try:
            result = self.broker.place_limit({**order, "transmit": True})
        except (ConnectionError, TimeoutError) as exc:
            return self._transition(intent_uuid, "SubmitUncertain", "transport_uncertain", {"error": str(exc)})
        with self.ledger.transaction() as db:
            db.execute(
                "UPDATE order_intents SET gateway_session_id=?, client_id=?, order_id=?, perm_id=?, updated_at=? WHERE intent_uuid=?",
                (result.get("gateway_session_id"), result.get("client_id"), result.get("order_id"), result.get("perm_id"), utc_now(), intent_uuid),
            )
        return self._transition(intent_uuid, "Acknowledged", "broker_acknowledged", result)

    def reconcile_uncertain(self, intent_uuid: str) -> dict[str, Any]:
        order = self.get(intent_uuid)
        if order["state"] != "SubmitUncertain":
            raise ValueError("order is not SubmitUncertain")
        found = self.broker.find_owned_order(order["order_ref"])
        if found:
            return self._transition(intent_uuid, "Acknowledged", "uncertain_order_found", found)
        return self._transition(intent_uuid, "Rejected", "uncertain_order_absent_after_reconciliation", {})

    def request_cancel(self, intent_uuid: str) -> dict[str, Any]:
        order = self.get(intent_uuid)
        if order["state"] not in {"Acknowledged", "PartiallyFilled"}:
            raise ValueError("only an acknowledged owned order can be cancelled")
        if not order["order_ref"].startswith("MAGIS|") or order["client_id"] is None or order["order_id"] is None:
            raise ValueError("order ownership is not proven")
        result = self.broker.cancel_owned_order(order["order_ref"], order["client_id"], order["order_id"])
        return self._transition(intent_uuid, "CancelPending", "cancel_requested", result)

    def apply_broker_status(self, intent_uuid: str, status: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        current = self.get(intent_uuid)
        if current["state"] in TERMINAL_STATES:
            return current
        next_state = {
            "PendingSubmit": "Submitting", "PreSubmitted": "Acknowledged", "Submitted": "Acknowledged",
            "PartiallyFilled": "PartiallyFilled", "Filled": "Filled", "PendingCancel": "CancelPending",
            "ApiCancelled": "Cancelled", "Cancelled": "Cancelled", "Inactive": "Rejected",
        }.get(status)
        if not next_state:
            raise ValueError(f"unsupported broker status {status}")
        if next_state == current["state"]:
            return current
        return self._transition(intent_uuid, next_state, "broker_status", {"broker_status": status, **(payload or {})})

    def record_execution(self, intent_uuid: str, execution: dict[str, Any]) -> dict[str, Any]:
        order = self.get(intent_uuid)
        required = {"account_alias", "exec_id", "conid", "quantity", "price", "side", "executed_at"}
        if required - execution.keys():
            raise ValueError("execution is incomplete")
        if execution["account_alias"] != order["account_alias"] or int(execution["conid"]) != order["conid"]:
            raise ValueError("execution does not match order contract/account")
        with self.ledger.transaction() as db:
            db.execute(
                """INSERT OR IGNORE INTO executions
                (account_alias,exec_id,intent_uuid,perm_id,conid,quantity_decimal,price_decimal,side,executed_at,payload_json)
                VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (execution["account_alias"], execution["exec_id"], intent_uuid, execution.get("perm_id"), execution["conid"], decimal_text(execution["quantity"]), decimal_text(execution["price"]), execution["side"], execution["executed_at"], canonical_json(execution)),
            )
        filled = self.ledger.connection.execute(
            "SELECT quantity_decimal FROM executions WHERE intent_uuid=?", (intent_uuid,)
        ).fetchall()
        total = sum((Decimal(row["quantity_decimal"]) for row in filled), Decimal("0"))
        target = Decimal(order["quantity_decimal"])
        next_state = "Filled" if total >= target else "PartiallyFilled"
        current = self.get(intent_uuid)
        if current["state"] == next_state or current["state"] in TERMINAL_STATES:
            return current
        return self._transition(intent_uuid, next_state, "execution_recorded", {"exec_id": execution["exec_id"], "filled_quantity": decimal_text(total)})

    def get(self, intent_uuid: str) -> dict[str, Any]:
        row = self.ledger.connection.execute("SELECT * FROM order_intents WHERE intent_uuid=?", (intent_uuid,)).fetchone()
        if not row:
            raise KeyError(intent_uuid)
        return dict(row)

    def _transition(self, intent_uuid: str, next_state: str, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        current = self.get(intent_uuid)
        if next_state not in TRANSITIONS.get(current["state"], set()):
            raise ValueError(f"invalid order transition {current['state']} -> {next_state}")
        with self.ledger.transaction() as db:
            db.execute("UPDATE order_intents SET state=?, updated_at=? WHERE intent_uuid=?", (next_state, utc_now(), intent_uuid))
            self._event(db, intent_uuid, current["state"], next_state, event_type, payload)
        return self.get(intent_uuid)

    def _approval_binding(self, order: dict[str, Any], expires: datetime) -> str:
        fields = {k: order[k] for k in ("intent_uuid", "account_alias", "conid", "contract_fingerprint", "action", "quantity_decimal", "limit_price_decimal", "tif", "outside_rth", "reduce_only", "owner", "strategy", "mode")}
        fields["expires_at"] = expires.isoformat()
        return canonical_json(fields)

    @staticmethod
    def _event(db, intent_uuid: str, prior: str | None, nxt: str, event_type: str, payload: dict[str, Any]) -> None:
        db.execute("INSERT INTO order_events VALUES (?,?,?,?,?,?,?)", (str(uuid.uuid4()), intent_uuid, prior, nxt, event_type, canonical_json(payload), utc_now()))

    @staticmethod
    def _validate(ticket: dict[str, Any]) -> None:
        if ticket["action"] not in {"BUY", "SELL"}:
            raise ValueError("action must be BUY or SELL")
        if Decimal(ticket["quantity"]) <= 0 or Decimal(ticket["limit_price"]) <= 0:
            raise ValueError("quantity and price must be positive")
        if ticket["mode"] not in {"dry_run", "paper", "live"}:
            raise ValueError("invalid mode")
        if ticket["owner"] not in {"drew", "michael", "unallocated"}:
            raise ValueError("invalid owner")
        if not ticket["contract_fingerprint"]:
            raise ValueError("qualified contract fingerprint is required")

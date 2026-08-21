"""Hub-side command loop: pull requests, decide locally, transmit locally.

Direction of trust matters more than the mechanics here. The edge never calls
the hub; the hub calls the edge. A compromised Cloudflare function, a stolen
session cookie, or a bug in a Worker can at most create a *request* row. It
cannot reach IB Gateway, cannot approve, and cannot transmit, because the
approval secret and the broker socket both live only on this machine.

The loop is a translation between two state machines:

    edge request row              hub GuardedOrderService
    ----------------              -----------------------
    requested        ->           create()  -> Draft
                                  preview() -> Previewed   (live NBBO + whatIf)
    previewed        <-           issue_approval()          (token stays here)
    approved         ->           approve() + submit()      -> Acknowledged
    acknowledged     <-           broker status / executions

Timing is the constraint that shapes everything. GuardedOrderService enforces
`quote_max_age_seconds` (10s) and `approval_ttl_seconds` (120s), so the preview
cannot be precomputed or cached, and the whole preview -> human -> submit round
trip has to fit inside two minutes *including* both poll latencies. A cron would
miss every time. While any ticket is open the loop runs at ACTIVE_POLL_SECONDS;
when the desk is quiet it backs off to IDLE_POLL_SECONDS.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from .orders import GuardedOrderService, OrderIntent
from .publisher import signed_headers

ACTIVE_POLL_SECONDS = 1.0
IDLE_POLL_SECONDS = 15.0
# States where a human or the broker still owes us something, so the desk is
# "open" and the loop must stay responsive.
OPEN_STATES = {"requested", "drafting", "previewed", "approved", "submitting"}


@dataclass(frozen=True)
class ChannelConfig:
    base_url: str
    token: str
    account_alias: str
    timeout: int = 15


class OrderCommandChannel:
    """Signed HTTP client for the edge command tables."""

    def __init__(self, config: ChannelConfig):
        if not config.base_url.startswith("https://") and not config.base_url.startswith("http://127.0.0.1"):
            raise ValueError("command channel requires HTTPS outside loopback")
        if len(config.token) < 32:
            raise ValueError("command channel token must be at least 32 characters")
        self.config = config

    def _call(self, path: str, payload: dict[str, Any] | None = None, method: str = "POST") -> dict[str, Any]:
        body = json.dumps(payload or {}, sort_keys=True, separators=(",", ":")).encode()
        request = urllib.request.Request(
            f"{self.config.base_url.rstrip('/')}{path}",
            data=body if method != "GET" else None,
            method=method,
            headers=signed_headers(self.config.token, body),
        )
        with urllib.request.urlopen(request, timeout=self.config.timeout) as response:
            return json.loads(response.read() or b"{}")

    def claim(self) -> list[dict[str, Any]]:
        """Take pending requests for this account. Claiming is idempotent."""
        payload = self._call("/api/v2/portfolio/ingest/order-requests/claim",
                             {"account_alias": self.config.account_alias})
        return payload.get("requests") or []

    def publish(self, request_id: str, update: dict[str, Any]) -> None:
        self._call("/api/v2/portfolio/ingest/order-requests/publish",
                   {"account_alias": self.config.account_alias, "request_id": request_id, **update})


class OrderCommandLoop:
    def __init__(self, service: GuardedOrderService, channel: OrderCommandChannel, *,
                 account_alias: str, live_enabled: bool = False):
        self.service = service
        self.channel = channel
        self.account_alias = account_alias
        self.live_enabled = live_enabled

    # ------------------------------------------------------------------ loop

    def run_forever(self, *, sleep=time.sleep) -> None:  # pragma: no cover - long running
        while True:
            try:
                busy = self.tick()
            except Exception as exc:
                # A channel or broker fault must not kill the loop; the next tick
                # re-reads authoritative state from the ledger and the broker.
                print(f"order command loop error: {exc}", flush=True)
                busy = False
            sleep(ACTIVE_POLL_SECONDS if busy else IDLE_POLL_SECONDS)

    def tick(self) -> bool:
        """Advance every claimable request one step. Returns True if the desk is open."""
        requests = self.channel.claim()
        open_desk = False
        for row in requests:
            state = row.get("state")
            if state in OPEN_STATES:
                open_desk = True
            try:
                if state == "requested":
                    self._draft_and_preview(row)
                elif state == "approved":
                    self._approve_and_submit(row)
            except Exception as exc:
                # Reject the request rather than leaving a ticket that looks live.
                self.channel.publish(row["request_id"], {"state": "rejected", "reject_reason": str(exc)})
        return open_desk

    # ----------------------------------------------------------------- steps

    def _draft_and_preview(self, row: dict[str, Any]) -> None:
        """Draft in the ledger, then price it against the live book right now."""
        if row.get("mode") == "live" and not self.live_enabled:
            self.channel.publish(row["request_id"], {
                "state": "rejected",
                "reject_reason": "Live transmission is disabled on the hub (interlock off).",
            })
            return

        intent = OrderIntent(
            account_alias=self.account_alias,
            conid=int(row["conid"]),
            contract_fingerprint=self._fingerprint(row),
            action=row["action"],
            quantity=Decimal(str(row["quantity_decimal"])),
            limit_price=Decimal(str(row["limit_price_decimal"])),
            owner=row["owner"],
            strategy=row.get("strategy") or "single_stock",
            mode=row.get("mode") or "dry_run",
            tif=row.get("tif") or "DAY",
            outside_rth=bool(row.get("outside_rth")),
        )
        draft = self.service.create(intent)
        self.channel.publish(row["request_id"], {"state": "drafting", "intent_uuid": draft["intent_uuid"]})

        previewed = self.service.preview(draft["intent_uuid"])
        if previewed["state"] != "Previewed":
            # preview() encodes its own refusal (stale quote, price band, tick,
            # reduce-only, notional) as a Rejected transition with a reason.
            self.channel.publish(row["request_id"], {
                "state": "rejected",
                "intent_uuid": draft["intent_uuid"],
                "reject_reason": self._latest_reason(draft["intent_uuid"]),
            })
            return

        # The HMAC token is issued and stored here and is never published. The
        # browser only ever sees the fingerprint and the expiry.
        approval = self.service.issue_approval(draft["intent_uuid"])
        self.channel.publish(row["request_id"], {
            "state": "previewed",
            "intent_uuid": draft["intent_uuid"],
            "contract_fingerprint": approval["contract_fingerprint"],
            "approval_expires_at": approval["expires_at"],
            "preview": self._preview_payload(draft["intent_uuid"]),
        })

    def _approve_and_submit(self, row: dict[str, Any]) -> None:
        """Re-verify the approval against the hub's own token, then transmit."""
        intent_uuid = row.get("intent_uuid")
        if not intent_uuid:
            raise ValueError("approved request has no hub intent")
        order = self.service.get(intent_uuid)
        # The edge's approval is a human signal. Authority comes from the token
        # this process issued and still holds.
        self.service.approve(
            intent_uuid,
            token=order["approval_hash"],
            contract_fingerprint=row["approved_fingerprint"],
        )
        self.channel.publish(row["request_id"], {"state": "submitting"})
        submitted = self.service.submit(intent_uuid)
        self.channel.publish(row["request_id"], {
            "state": self._edge_state(submitted["state"]),
            "broker_status": submitted["state"],
            "order_ref": submitted.get("order_ref"),
            "client_id": submitted.get("client_id"),
            "order_id": submitted.get("order_id"),
            "perm_id": submitted.get("perm_id"),
            "reject_reason": self._latest_reason(intent_uuid) if submitted["state"] == "Rejected" else None,
        })

    # --------------------------------------------------------------- helpers

    @staticmethod
    def _fingerprint(row: dict[str, Any]) -> str:
        """Identity of the exact instrument, bound into the approval HMAC."""
        return f"{row['conid']}|{row['sec_type']}|{row.get('currency') or ''}|{row.get('exchange') or 'SMART'}"

    @staticmethod
    def _edge_state(hub_state: str) -> str:
        return {
            "Acknowledged": "acknowledged", "PartiallyFilled": "acknowledged",
            "Filled": "filled", "Cancelled": "cancelled", "Rejected": "rejected",
            "SubmitUncertain": "submitting",
        }.get(hub_state, "submitting")

    def _latest_reason(self, intent_uuid: str) -> str | None:
        row = self.service.ledger.connection.execute(
            "SELECT event_type, payload_json FROM order_events WHERE intent_uuid=? ORDER BY rowid DESC LIMIT 1",
            (intent_uuid,),
        ).fetchone()
        return dict(row)["event_type"] if row else None

    def _preview_payload(self, intent_uuid: str) -> dict[str, Any]:
        row = self.service.ledger.connection.execute(
            "SELECT payload_json FROM order_events WHERE intent_uuid=? AND event_type='preview_completed' ORDER BY rowid DESC LIMIT 1",
            (intent_uuid,),
        ).fetchone()
        return json.loads(dict(row)["payload_json"]) if row else {}

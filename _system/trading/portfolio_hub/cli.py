from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from .ledger import PortfolioLedger
from .publisher import publish_payload
from .adapters import normalize_ls_bucket5_live, normalize_ls_bucket5_product, normalize_ls_snapshot, normalize_spx_status
from .bootstrap import apply_approved_bootstrap, build_bootstrap_plan
from .dual_publish import build_dual_publish_bundle, publish_dual_bundle, write_dual_publish_bundle


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Private IBKR portfolio ledger")
    parser.add_argument("--db", type=Path, default=Path("_private/portfolio-hub/portfolio.db"))
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init")
    # There is no `collect` command. Polling IB Gateway from this repo is
    # prohibited -- see CLAUDE.md rule 9. Broker truth arrives via Flex.
    flex_publish = commands.add_parser("flex-publish", help="Publish broker truth from IBKR Flex XML (no Gateway)")
    flex_publish.add_argument("--positions", type=Path, required=True)
    flex_publish.add_argument("--cash", type=Path)
    flex_publish.add_argument("--trades", type=Path)
    flex_publish.add_argument("--account", required=True)
    flex_publish.add_argument("--url", default=os.environ.get("PORTFOLIO_INGEST_URL", ""))
    flex_publish.add_argument("--stale-hours", type=int, default=30)
    flex_publish.add_argument("--dry-run", action="store_true")
    ingest = commands.add_parser("ingest-snapshot"); ingest.add_argument("payload", type=Path)
    ingest_flex = commands.add_parser("ingest-flex"); ingest_flex.add_argument("payload", type=Path)
    allocate = commands.add_parser("allocate")
    allocate.add_argument("--account", required=True); allocate.add_argument("--conid", type=int, required=True)
    allocate.add_argument("--model", default=""); allocate.add_argument("--owner", choices=["drew", "michael", "unallocated"], required=True)
    allocate.add_argument("--strategy", required=True); allocate.add_argument("--bucket"); allocate.add_argument("--quantity", required=True)
    allocate.add_argument("--effective-at"); allocate.add_argument("--note")
    cash = commands.add_parser("cash-event"); cash.add_argument("--account", required=True); cash.add_argument("--owner", choices=["drew", "michael", "unallocated"], required=True)
    cash.add_argument("--strategy", required=True); cash.add_argument("--currency", required=True); cash.add_argument("--amount", required=True)
    cash.add_argument("--event-type", required=True); cash.add_argument("--effective-at", required=True); cash.add_argument("--source", required=True); cash.add_argument("--source-event-id")
    reconcile = commands.add_parser("reconcile"); reconcile.add_argument("snapshot_id")
    show = commands.add_parser("show"); show.add_argument("--account", required=True); show.add_argument("--owner", choices=["all", "drew", "michael", "unallocated"], default="all")
    project = commands.add_parser("export-projection"); project.add_argument("--account", required=True); project.add_argument("--output", type=Path, required=True)
    publish = commands.add_parser("publish-latest"); publish.add_argument("--account", required=True); publish.add_argument("--url", default=os.environ.get("PORTFOLIO_INGEST_URL", ""))
    health = commands.add_parser("health"); health.add_argument("--account", required=True); health.add_argument("--max-age", type=int, default=120); health.add_argument("--max-outbox-age", type=int, default=300)
    receipt = commands.add_parser("gateway-receipt",
                                  help="Count Gateway connection EVENTS over the last day and flag a loop forming")
    # Well under the budget's own 60/day hard cap. A receipt that only fires at
    # the cap tells you nothing the brake did not already enforce; this is meant
    # to be read on a day the brake never engaged. A human placing orders touches
    # the Gateway a handful of times; twenty is a loop taking shape.
    receipt.add_argument("--warn-per-day", type=int, default=20)
    receipt.add_argument("--warn-per-hour", type=int, default=8)
    backup = commands.add_parser("backup"); backup.add_argument("--output-dir", type=Path, required=True)
    for name in ("adapt-spx", "adapt-ls", "adapt-b5-live", "adapt-b5-product"):
        adapter = commands.add_parser(name); adapter.add_argument("input", type=Path); adapter.add_argument("output", type=Path)
    bootstrap = commands.add_parser("bootstrap-plan")
    bootstrap.add_argument("--positions", type=Path, required=True)
    bootstrap.add_argument("--tags", type=Path)
    bootstrap.add_argument("--hosted", type=Path)
    bootstrap.add_argument("--cash", type=Path)
    bootstrap.add_argument("--producers", type=Path)
    bootstrap.add_argument("--output", type=Path, required=True)
    apply_boot = commands.add_parser("bootstrap-apply")
    apply_boot.add_argument("review", type=Path)
    apply_boot.add_argument("--effective-at", required=True)
    bridge = commands.add_parser("order-bridge", help="Run the live order command loop (client 91, sole transmitter)")
    bridge.add_argument("--account", required=True)
    bridge.add_argument("--url", default=os.environ.get("PORTFOLIO_COMMAND_BASE_URL", ""))
    bridge.add_argument("--once", action="store_true", help="Single tick, for drills")
    # Routing live is an explicit act, not a config default. `paper` still opens
    # the Gateway connection -- real NBBO, real IBKR margin, real contract
    # resolution -- but fills land in the paper ledger and placeOrder is never
    # reached. Start here; move to `live` as its own decision.
    bridge.add_argument("--route", choices=("paper", "live"), default="paper",
                        help="Where fills go. paper (default) = live prices, no exchange route.")
    dual = commands.add_parser("dual-publish")
    dual.add_argument("--spx", type=Path)
    dual.add_argument("--ls", type=Path)
    dual.add_argument("--b5-live", type=Path)
    dual.add_argument("--b5-product", type=Path)
    dual.add_argument("--output-dir", type=Path, required=True)
    dual.add_argument("--url", default=os.environ.get("PORTFOLIO_INGEST_URL", ""))
    args = parser.parse_args(argv)
    ledger = PortfolioLedger(args.db)
    try:
        ledger.migrate()
        if args.command == "init": print(args.db.resolve())
        elif args.command == "flex-publish":
            from .flex_ingest import publish_flex_snapshot

            print(json.dumps(publish_flex_snapshot(
                ledger,
                positions=args.positions, cash=args.cash, trades=args.trades,
                account_alias=args.account, url=args.url,
                stale_hours=args.stale_hours, dry_run=args.dry_run,
            ), indent=2))
        elif args.command == "order-bridge":
            # Everything that can transmit is constructed here and nowhere else:
            # the approval secret, the broker socket, and the live interlock all
            # stay in this process on the trusted host.
            from .command_poller import ChannelConfig, OrderCommandChannel, OrderCommandLoop
            from .gateway_budget import BudgetLimits, ConnectionBudget
            from .gateway_session import build_live_session_factory
            from .orders import GuardedOrderService
            from .paper import PaperOrderBroker

            secret = os.environ.get("PORTFOLIO_APPROVAL_SECRET", "")
            if len(secret) < 32:
                raise SystemExit("PORTFOLIO_APPROVAL_SECRET must be at least 32 characters")

            # Nothing here connects. The factory is inert until a claimed ticket
            # needs the broker, so this process can run all day on an idle desk
            # having made zero Gateway contact (CLAUDE.md rule 10).
            budget = ConnectionBudget(limits=BudgetLimits(
                max_per_hour=int(os.environ.get("PORTFOLIO_GATEWAY_MAX_PER_HOUR", "12")),
                max_per_day=int(os.environ.get("PORTFOLIO_GATEWAY_MAX_PER_DAY", "60")),
            ), store=ledger.budget_store())
            sessions = build_live_session_factory(
                route=args.route, budget=budget,
                on_event=lambda event: print(json.dumps(event), flush=True),
            )
            # The service needs *a* broker to satisfy its constructor; the loop
            # swaps in the session's broker for the duration of each tick. This
            # placeholder can neither transmit nor reach IBKR.
            broker = PaperOrderBroker(lambda conid: {})
            print(json.dumps({
                "route": args.route, "standing_gateway_connection": False,
                "budget": budget.state(),
            }), flush=True)
            service = GuardedOrderService(
                ledger, broker, secret,
                live_enabled=os.environ.get("PORTFOLIO_LIVE_ENABLED", "0") == "1",
                kill_switch=os.environ.get("PORTFOLIO_KILL_SWITCH", "0") == "1",
            )
            channel = OrderCommandChannel(ChannelConfig(
                base_url=args.url, token=os.environ.get("PORTFOLIO_INGEST_TOKEN", ""),
                account_alias=args.account,
            ))
            loop = OrderCommandLoop(service, channel, account_alias=args.account,
                                    live_enabled=service.live_enabled,
                                    options_enabled=os.environ.get("PORTFOLIO_OPTIONS_ENABLED", "0") == "1",
                                    sessions=sessions)
            # No teardown block: there is nothing held open between ticks. Each
            # session disconnects in its own `finally` inside GatewaySessionFactory,
            # so killing this process can never leak a client-91 socket.
            if args.once:
                print(json.dumps({
                    "desk_open": loop.tick(), "route": args.route,
                    "sessions_opened": sessions.sessions_opened,
                    "budget": budget.state(),
                }))
            else:
                loop.run_forever()
        elif args.command == "ingest-snapshot": print(ledger.ingest_account_snapshot(json.loads(args.payload.read_text(encoding="utf-8"))))
        elif args.command == "ingest-flex": print(json.dumps(ledger.ingest_flex_eod(json.loads(args.payload.read_text(encoding="utf-8"))), indent=2))
        elif args.command == "allocate": print(ledger.add_allocation(account_alias=args.account, conid=args.conid, model_code=args.model, owner=args.owner, strategy=args.strategy, bucket=args.bucket, quantity=args.quantity, effective_at=args.effective_at, note=args.note))
        elif args.command == "cash-event": print(ledger.add_cash_event(account_alias=args.account, owner=args.owner, strategy=args.strategy, currency=args.currency, amount=args.amount, event_type=args.event_type, effective_at=args.effective_at, source=args.source, source_event_id=args.source_event_id))
        elif args.command == "reconcile": print(json.dumps(ledger.reconcile_allocations(args.snapshot_id), indent=2))
        elif args.command == "show": print(json.dumps(ledger.latest_portfolio(args.account, args.owner), indent=2))
        elif args.command == "export-projection": args.output.write_text(json.dumps(ledger.allocation_projection(args.account), indent=2) + "\n", encoding="utf-8")
        elif args.command == "publish-latest":
            token = os.environ.get("PORTFOLIO_INGEST_TOKEN", "")
            if not args.url: raise RuntimeError("PORTFOLIO_INGEST_URL is required")
            pending = ledger.pending_outbox(limit=10_000)
            for row in pending:
                if row["topic"] == "flex_eod.v1":
                    print(json.dumps(publish_payload(args.url, token, json.loads(row["payload_json"])), indent=2))
            print(json.dumps(publish_payload(args.url, token, ledger.latest_account_snapshot_payload(args.account)), indent=2))
            print(json.dumps(publish_payload(args.url, token, ledger.allocation_projection(args.account)), indent=2))
            for row in pending:
                ledger.mark_outbox_delivered(row["outbox_id"])
        elif args.command == "health":
            latest = ledger.connection.execute("SELECT as_of FROM account_snapshots WHERE account_alias=? AND complete=1 ORDER BY as_of DESC LIMIT 1", (args.account,)).fetchone()
            oldest = ledger.connection.execute("SELECT created_at FROM outbox WHERE delivered_at IS NULL ORDER BY created_at LIMIT 1").fetchone()
            now = datetime.now(timezone.utc)
            if not latest: raise RuntimeError("no complete broker snapshot")
            snapshot_age = (now - datetime.fromisoformat(latest["as_of"].replace("Z", "+00:00"))).total_seconds()
            outbox_age = (now - datetime.fromisoformat(oldest["created_at"].replace("Z", "+00:00"))).total_seconds() if oldest else 0
            if snapshot_age > args.max_age or outbox_age > args.max_outbox_age: raise RuntimeError(f"unhealthy snapshot_age={snapshot_age:.0f}s outbox_age={outbox_age:.0f}s")
            print(json.dumps({"status": "healthy", "snapshot_age_seconds": round(snapshot_age), "outbox_age_seconds": round(outbox_age)}))
        elif args.command == "gateway-receipt":
            # Reads the same rows the brake reads. The collector's lesson was not
            # that nobody looked -- it was that what got counted (concurrent
            # sockets) was not what did the harm, so it read healthy for months
            # while storming. This counts connection events, which is the thing.
            now = time.time()
            rows = ledger.connection.execute(
                "SELECT attempted_at, attempted_at_iso, purpose FROM gateway_connection_attempts "
                "WHERE attempted_at >= ? ORDER BY attempted_at", (now - 86_400,),
            ).fetchall()
            breaker = ledger.connection.execute(
                "SELECT consecutive_failures, tripped_until, updated_at FROM gateway_breaker_state WHERE id=1"
            ).fetchone()
            tripped_until = None if breaker is None or breaker["tripped_until"] is None else float(breaker["tripped_until"])
            last_hour = sum(1 for row in rows if float(row["attempted_at"]) >= now - 3600)
            by_purpose: dict[str, int] = {}
            for row in rows:
                by_purpose[row["purpose"] or "unattributed"] = by_purpose.get(row["purpose"] or "unattributed", 0) + 1
            breaker_open = tripped_until is not None and now < tripped_until
            alarms = []
            if len(rows) >= args.warn_per_day:
                alarms.append(f"{len(rows)} gateway connection events in 24h (warn at {args.warn_per_day})")
            if last_hour >= args.warn_per_hour:
                alarms.append(f"{last_hour} gateway connection events in the last hour (warn at {args.warn_per_hour})")
            if breaker_open:
                alarms.append(f"circuit breaker open, {int(tripped_until - now)}s remaining")
            print(json.dumps({
                "status": "alarm" if alarms else "quiet",
                "connection_events_last_day": len(rows),
                "connection_events_last_hour": last_hour,
                "by_purpose": by_purpose,
                "newest_event": rows[-1]["attempted_at_iso"] if rows else None,
                "breaker_open": breaker_open,
                "consecutive_failures": 0 if breaker is None else int(breaker["consecutive_failures"]),
                "breaker_updated_at": None if breaker is None else breaker["updated_at"],
                "alarms": alarms,
                # Zero is the expected healthy reading on a desk nobody traded,
                # and must never be reported as a fault.
                "note": "an idle desk makes zero gateway contact; 0 is healthy",
            }, indent=2))
            if alarms:
                raise SystemExit(1)
        elif args.command == "backup":
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            print(ledger.backup(args.output_dir / f"portfolio-{stamp}.db"))
        elif args.command.startswith("adapt-"):
            source = json.loads(args.input.read_text(encoding="utf-8"))
            adapters = {"adapt-spx": normalize_spx_status, "adapt-ls": normalize_ls_snapshot, "adapt-b5-live": normalize_ls_bucket5_live, "adapt-b5-product": normalize_ls_bucket5_product}
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(adapters[args.command](source), indent=2) + "\n", encoding="utf-8")
        elif args.command == "publish-file":
            if not args.url: raise RuntimeError("PORTFOLIO_INGEST_URL is required")
            print(json.dumps(publish_payload(args.url, os.environ.get("PORTFOLIO_INGEST_TOKEN", ""), json.loads(args.payload.read_text(encoding="utf-8"))), indent=2))
        elif args.command == "bootstrap-plan":
            review = build_bootstrap_plan(
                broker_positions=json.loads(args.positions.read_text(encoding="utf-8")),
                local_tags=json.loads(args.tags.read_text(encoding="utf-8")) if args.tags else {},
                hosted_rows=json.loads(args.hosted.read_text(encoding="utf-8")) if args.hosted else [],
                cash_balances=json.loads(args.cash.read_text(encoding="utf-8")) if args.cash else [],
                producer_rows=json.loads(args.producers.read_text(encoding="utf-8")) if args.producers else [],
            )
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(review, indent=2) + "\n", encoding="utf-8")
            print(json.dumps({"proposed": len(review["proposed"]), "quarantined": len(review["quarantined"]), "cash": len(review["cash_events"])}))
        elif args.command == "bootstrap-apply":
            print(json.dumps(apply_approved_bootstrap(ledger, json.loads(args.review.read_text(encoding="utf-8")), effective_at=args.effective_at), indent=2))
        elif args.command == "dual-publish":
            snapshots = build_dual_publish_bundle(spx=args.spx, ls_risk=args.ls, ls_bucket5_live=args.b5_live, ls_bucket5_product=args.b5_product)
            written = write_dual_publish_bundle(snapshots, args.output_dir)
            if args.url:
                print(json.dumps(publish_dual_bundle(args.url, os.environ.get("PORTFOLIO_INGEST_TOKEN", ""), snapshots), indent=2))
            print(json.dumps({"written": [str(path) for path in written], "producers": [row["producer"] for row in snapshots]}))
    finally:
        ledger.close()
    return 0

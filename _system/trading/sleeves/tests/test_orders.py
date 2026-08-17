from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from _system.trading.sleeves.book import build_book  # noqa: E402
from _system.trading.sleeves.orders import approve_trade, propose_trade  # noqa: E402
from _system.trading.sleeves.store import SleeveStore  # noqa: E402


def _quote(last=50.0):
    return {
        "last": last,
        "as_of": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "account": "TEST_ACCOUNT",
        "qualified_name": "CSU",
        "currency": "USD",
        "exchange": "SMART",
    }


def test_propose_approve_dry_run_roundtrip(tmp_path):
    store = SleeveStore(tmp_path)
    quote = _quote()
    proposal = propose_trade(
        owner="drew",
        ticker="CSU",
        side="BUY",
        qty=10,
        limit_price=50,
        quote=quote,
        holding_period_years=3,
        plc_thesis="Fraud or a broken cloud franchise would make this a permanent loss.",
        conviction=4,
        cluster="idiosyncratic",
        store=store,
    )
    assert proposal["status"] == "proposed"
    fill = approve_trade(
        proposal_id=proposal["proposal_id"],
        typed_ticker="CSU",
        quote=quote,
        store=store,
    )
    assert fill["source"] == "dry_run"
    assert fill["dry_run"] is True
    second = None
    try:
        approve_trade(
            proposal_id=proposal["proposal_id"],
            typed_ticker="CSU",
            quote=quote,
            store=store,
        )
    except PermissionError as exc:
        second = str(exc)
    assert second
    book = build_book("drew", store)
    assert book["header"]["open_names"] == 1
    assert book["positions"][0]["ticker"] == "CSU"
    assert book["fills"][0]["proposal_id"] == proposal["proposal_id"]


def test_propose_requires_plc_and_holding_period(tmp_path):
    store = SleeveStore(tmp_path)
    quote = _quote()
    try:
        propose_trade(
            owner="drew", ticker="CSU", side="BUY", qty=10, limit_price=50,
            quote=quote, holding_period_years=0, plc_thesis="x", conviction=3,
            cluster="idiosyncratic", store=store,
        )
        assert False, "should have failed"
    except ValueError:
        pass


def test_approve_live_submits_without_fake_fill(tmp_path):
    import copy
    from _system.trading.sleeves.config_loader import load_config
    store = SleeveStore(tmp_path)
    quote = _quote()
    proposal = propose_trade(
        owner="drew",
        ticker="CSU",
        side="BUY",
        qty=10,
        limit_price=50,
        quote=quote,
        holding_period_years=3,
        plc_thesis="Fraud or a broken cloud franchise would make this a permanent loss.",
        conviction=4,
        cluster="idiosyncratic",
        store=store,
    )
    live_cfg = copy.deepcopy(load_config())
    live_cfg["execution"]["dry_run"] = False
    live_cfg["execution"]["allow_live"] = True
    sent = {}

    def fake_submit(prop, q):
        sent["order_id"] = 42
        return 42

    result = approve_trade(
        proposal_id=proposal["proposal_id"],
        typed_ticker="CSU",
        quote=quote,
        store=store,
        cfg=live_cfg,
        ib_submit=fake_submit,
    )
    assert sent["order_id"] == 42
    assert result["status"] == "submitted"
    assert result["ib_order_id"] == 42
    assert store.get_proposal(proposal["proposal_id"])["status"] == "submitted"
    assert store.pending_proposals() == []

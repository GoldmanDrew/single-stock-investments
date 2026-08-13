from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from _system.trading.sleeves.safeties import check_safeties, kill_path  # noqa: E402
from _system.trading.sleeves.config_loader import load_config  # noqa: E402


def _quote(last=100.0, age_s=1):
    now = datetime.now(timezone.utc)
    return {
        "last": last,
        "as_of": (now - timedelta(seconds=age_s)).isoformat().replace("+00:00", "Z"),
        "account": "U805366",
        "qualified_name": "MSFT",
        "currency": "USD",
        "exchange": "SMART",
    }


def test_dry_run_ok_for_drew_msft():
    result = check_safeties(
        owner="drew",
        ticker="MSFT",
        side="BUY",
        qty=10,
        limit_price=100,
        quote=_quote(),
        proposal={"proposal_id": "abc", "snapshot_last": 100},
        typed_ticker="MSFT",
    )
    assert result.ok, result.failures


def test_drew_cannot_trade_letf_or_blacklist_family():
    tqqq = check_safeties(owner="drew", ticker="TQQQ", side="BUY", qty=10, limit_price=40, quote=_quote(40), proposal={"snapshot_last": 40})
    assert not tqqq.ok
    apld = check_safeties(owner="drew", ticker="APLD", side="BUY", qty=10, limit_price=10, quote=_quote(10), proposal={"snapshot_last": 10})
    assert not apld.ok
    assert any("blacklist" in f.lower() for f in apld.failures)


def test_michael_can_trade_blacklist_family_not_spx():
    aplz = check_safeties(owner="michael", ticker="APLZ", side="BUY", qty=10, limit_price=20, quote=_quote(20), proposal={"snapshot_last": 20})
    assert aplz.ok, aplz.failures
    tqqq = check_safeties(owner="michael", ticker="TQQQ", side="BUY", qty=10, limit_price=40, quote=_quote(40), proposal={"snapshot_last": 40})
    assert not tqqq.ok


def test_proposal_id_one_shot_and_stale_quote():
    used = check_safeties(
        owner="drew", ticker="MSFT", side="BUY", qty=10, limit_price=100,
        quote=_quote(), proposal={"proposal_id": "x", "snapshot_last": 100},
        used_proposal_ids={"x"},
    )
    assert not used.ok
    stale = check_safeties(
        owner="drew", ticker="MSFT", side="BUY", qty=10, limit_price=100,
        quote=_quote(age_s=90), proposal={"snapshot_last": 100},
    )
    assert not stale.ok


def test_kill_file(tmp_path, monkeypatch):
    cfg = load_config()
    path = kill_path(cfg)
    created = False
    if not path.exists():
        path.write_text("stop\n", encoding="utf-8")
        created = True
    try:
        result = check_safeties(owner="drew", ticker="MSFT", side="BUY", qty=1, limit_price=100, quote=_quote(), proposal={"snapshot_last": 100})
        assert not result.ok
        assert any("KILL" in f for f in result.failures)
    finally:
        if created and path.exists():
            path.unlink()

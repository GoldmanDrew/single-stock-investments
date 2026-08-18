from _system.trading.portfolio_hub.bootstrap import build_bootstrap_plan


def test_bootstrap_requires_unique_contract_and_owner() -> None:
    positions = [
        {"account_alias": "paper-primary", "conid": 1, "model_code": "", "symbol": "ONE", "quantity": "10"},
        {"account_alias": "paper-primary", "conid": 2, "model_code": "", "symbol": "DUAL", "quantity": "1"},
        {"account_alias": "paper-primary", "conid": 3, "model_code": "", "symbol": "DUAL", "quantity": "2"},
        {"account_alias": "paper-primary", "conid": 4, "model_code": "", "symbol": "ORPHAN", "quantity": "7"},
    ]
    review = build_bootstrap_plan(
        broker_positions=positions,
        local_tags={"ONE": "drew", "DUAL": "michael", "CONFLICT": "drew"},
        hosted_rows=[{"ticker": "CONFLICT", "owner": "michael"}],
        cash_balances=[{"account_alias": "paper-primary", "currency": "USD", "amount": "25000"}],
        producer_rows=[{"conid": 1, "strategy": "single_stock"}],
    )
    assert review["proposed"][0]["symbol"] == "ONE"
    assert review["proposed"][0]["approved"] is False
    assert review["unresolved"][0]["symbol"] == "DUAL"
    assert review["conflicts"][0]["symbol"] == "CONFLICT"
    assert any(row["symbol"] == "ORPHAN" and row["quarantined"] for row in review["quarantined"])
    assert review["cash_events"][0]["owner"] == "unallocated"
    assert review["cash_events"][0]["approved"] is False


def test_bootstrap_classifies_spx_and_letf_without_guessing_owners() -> None:
    review = build_bootstrap_plan(
        broker_positions=[
            {"account_alias": "paper-primary", "conid": 55, "model_code": "", "symbol": "SPXW", "quantity": "-1"},
            {"account_alias": "paper-primary", "conid": 77, "model_code": "", "symbol": "UPRO", "quantity": "10"},
        ],
        local_tags={"UPRO": {"owner": "drew", "strategy": "letf", "bucket": "b1"}},
        hosted_rows=[],
        producer_rows=[{"conid": 55, "strategy": "spx_0dte"}],
    )
    by_symbol = {row["symbol"]: row for row in review["proposed"] + review["quarantined"]}
    assert by_symbol["UPRO"]["strategy"] == "letf"
    assert by_symbol["UPRO"]["bucket"] == "b1"
    assert by_symbol["SPXW"]["owner"] == "unallocated"
    assert by_symbol["SPXW"]["strategy"] == "spx_0dte"
    assert by_symbol["SPXW"]["quarantined"] is True

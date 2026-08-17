from _system.trading.portfolio_hub.bootstrap import build_bootstrap_plan


def test_bootstrap_requires_unique_contract_and_owner() -> None:
    positions = [
        {"account_alias": "paper-primary", "conid": 1, "model_code": "", "symbol": "ONE", "quantity": "10"},
        {"account_alias": "paper-primary", "conid": 2, "model_code": "", "symbol": "DUAL", "quantity": "1"},
        {"account_alias": "paper-primary", "conid": 3, "model_code": "", "symbol": "DUAL", "quantity": "2"},
    ]
    review = build_bootstrap_plan(broker_positions=positions, local_tags={"ONE": "drew", "DUAL": "michael", "CONFLICT": "drew"}, hosted_rows=[{"ticker": "CONFLICT", "owner": "michael"}])
    assert review["proposed"][0]["symbol"] == "ONE"
    assert review["proposed"][0]["approved"] is False
    assert review["unresolved"][0]["symbol"] == "DUAL"
    assert review["conflicts"][0]["symbol"] == "CONFLICT"

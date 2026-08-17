from _system.trading.portfolio_hub import PortfolioClient, PortfolioLedger
from _system.trading.portfolio_hub.paper import PaperOrderBroker


def test_simple_python_paper_limit_order(tmp_path) -> None:
    ledger = PortfolioLedger(tmp_path / "client.db")
    ledger.migrate()
    try:
        broker = PaperOrderBroker(lambda conid: {"conid": conid, "bid": "25.39", "ask": "25.41", "current_position": "0"})
        client = PortfolioClient.for_broker(ledger, broker, "test-secret")
        draft = client.draft_limit(account_alias="paper-primary", conid=123, contract_fingerprint="123|STK|USD|SMART", action="BUY", quantity="10", limit_price="25.40", owner="drew", strategy="single_stock", mode="paper")
        client.preview(draft["intent_uuid"])
        approval = client.issue_approval(draft["intent_uuid"])
        client.approve(draft["intent_uuid"], token=approval["token"], contract_fingerprint=approval["contract_fingerprint"])
        assert client.submit(draft["intent_uuid"])["state"] == "Acknowledged"
    finally:
        ledger.close()

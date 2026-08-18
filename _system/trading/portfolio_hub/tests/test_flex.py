from _system.trading.portfolio_hub.flex import parse_flex_xml
from _system.trading.portfolio_hub.ledger import PortfolioLedger


def test_flex_completed_session_parses_trades_cash_and_nav() -> None:
    xml = b'''<FlexQueryResponse><FlexStatements><FlexStatement accountId="TEST_ACCOUNT" toDate="20260816">
      <OpenPositions><OpenPosition conid="101" symbol="TEST" assetCategory="STK" currency="USD" position="10" costBasisMoney="100" positionValue="120" /></OpenPositions>
      <Trades><Trade tradeID="t1" ibExecID="e1" conid="101" symbol="TEST" currency="USD" quantity="10" tradePrice="10" ibCommission="1" fifoPnlRealized="0" dateTime="20260816;120000" orderReference="MAGIS|single_stock|drew|one" /></Trades>
      <CashTransactions><CashTransaction transactionID="c1" type="Dividends" currency="USD" amount="5" reportDate="20260816" symbol="TEST" conid="101" /></CashTransactions>
      <ChangeInNAV currency="USD" total="1000" cash="100" stock="900" options="0" />
    </FlexStatement></FlexStatements></FlexQueryResponse>'''
    result = parse_flex_xml(xml, account_alias="paper-primary")
    assert result["session_date"] == "2026-08-16"
    assert result["trades"][0]["exec_id"] == "e1"
    assert result["cash_transactions"][0]["amount"] == "5"
    assert result["nav_rows"][0]["net_liquidation"] == "1000"


def test_completed_session_is_immutable_and_later_version_is_restatement(tmp_path) -> None:
    xml = b'''<FlexQueryResponse><FlexStatements><FlexStatement accountId="TEST_ACCOUNT" toDate="20260816"><Trades><Trade tradeID="t1" ibExecID="e1" conid="101" symbol="TEST" currency="USD" quantity="10" tradePrice="10" ibCommission="1" fifoPnlRealized="2" /></Trades></FlexStatement></FlexStatements></FlexQueryResponse>'''
    first = parse_flex_xml(xml, account_alias="paper-primary")
    ledger = PortfolioLedger(tmp_path / "flex.db"); ledger.migrate()
    try:
        assert ledger.ingest_flex_eod(first)["restatement"] is False
        assert ledger.ingest_flex_eod(first)["duplicate"] is True
        changed = {**first, "source_run_id": "flex-restatement", "trades": [{**first["trades"][0], "realized_pnl": "3"}]}
        result = ledger.ingest_flex_eod(changed)
        assert result["restatement"] is True
        primary = ledger.connection.execute("SELECT payload_json FROM flex_session_versions WHERE is_primary=1").fetchone()[0]
        assert '"realized_pnl":"2"' in primary
    finally:
        ledger.close()

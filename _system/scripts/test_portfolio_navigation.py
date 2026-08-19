from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_portfolio_is_primary_and_owner_routes_are_nested() -> None:
    html = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
    assert 'data-view="portfolio"' in html
    assert '>SPX 0DTE<' in html
    assert '>LS Algo<' in html
    assert '>Research<' in html
    assert 'data-view="drew"' not in html
    assert 'data-view="michael"' not in html
    assert "#/portfolio/${window.PortfolioViz?.state.scope" in html


def test_portfolio_browser_only_writes_to_the_paper_order_route() -> None:
    javascript = (ROOT / "dashboard" / "portfolio-viz.js").read_text(encoding="utf-8")
    assert "/api/v2/portfolio/book" in javascript
    assert "/api/v2/portfolio/orders" in javascript
    assert "method: 'POST'" in javascript
    assert "/api/v2/portfolio/paper-orders" in javascript
    assert "x-paper-order-mode" in javascript
    assert "Queue paper order" in javascript


def test_portfolio_has_brokerage_grade_overview_and_position_controls() -> None:
    javascript = (ROOT / "dashboard" / "portfolio-viz.js").read_text(encoding="utf-8")
    css = (ROOT / "dashboard" / "portfolio.css").read_text(encoding="utf-8")
    assert "Net liquidation value" in javascript
    assert "Liquidity runway" in javascript
    assert "portfolioSparkline" in javascript
    assert "Stocks & ETFs" in javascript
    assert "Unallocated" in javascript
    assert "data-ph-sort" in javascript
    assert "portfolio-density" in javascript
    assert ".ph-cockpit" in css
    assert ".ph-sparkline" in css


def test_portfolio_has_deeper_read_only_workflows() -> None:
    javascript = (ROOT / "dashboard" / "portfolio-viz.js").read_text(encoding="utf-8")
    css = (ROOT / "dashboard" / "portfolio.css").read_text(encoding="utf-8")
    assert "data-ph-open-row" in javascript
    assert "Save view" in javascript
    assert "data-ph-linked-symbol" in javascript
    assert "Metric lineage" in javascript
    assert "Factor drill-down" in javascript
    assert "NAV vs" in javascript
    assert "quarantined" in javascript
    assert "PAPER · NEVER TRANSMITTED" in javascript
    assert ".ph-drawer" in css
    assert ".ph-column-picker" in css


def test_currency_and_ideas_workspaces_expose_explicit_decision_semantics() -> None:
    html = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
    javascript = (ROOT / "dashboard" / "portfolio-viz.js").read_text(encoding="utf-8")
    ideas_css = (ROOT / "dashboard" / "ideas.css").read_text(encoding="utf-8")
    assert "Avg cost · native" in javascript
    assert "Market value · base" in javascript
    assert "fx_rate_to_base_decimal" in javascript
    assert ">Inbox<" in html and ">Screens<" in html and ">Contracts<" in html
    assert "Decision Inbox" in html
    assert "methodology collapsed" in html
    assert ".decision-tape" in ideas_css
    assert "content-visibility: auto" in ideas_css

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_portfolio_is_primary_and_owner_routes_are_nested() -> None:
    html = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
    assert 'data-view="portfolio"' in html
    assert '>SPX 0DTE<' in html
    assert '>Leveraged ETFs<' in html
    assert '>Research<' in html
    assert 'data-view="drew"' not in html
    assert 'data-view="michael"' not in html
    assert "#/portfolio/${window.PortfolioViz?.state.scope" in html


def test_portfolio_browser_is_read_only() -> None:
    javascript = (ROOT / "dashboard" / "portfolio-viz.js").read_text(encoding="utf-8")
    assert "/api/v2/portfolio/book" in javascript
    assert "/api/v2/portfolio/orders" in javascript
    assert "method: 'POST'" not in javascript
    assert "Python command plane only" in javascript


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
    assert "method: 'POST'" not in javascript
    assert ".ph-drawer" in css
    assert ".ph-column-picker" in css

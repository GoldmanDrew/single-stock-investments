import importlib.util
import re
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS = ROOT / "dashboard" / "cloudflare" / "migrations"


def _latest_sql(name: str) -> str:
    source = (ROOT / "dashboard/functions/_lib/market-risk.js").read_text(
        encoding="utf-8"
    )
    match = re.search(rf"export const {name} = `(?P<sql>.*?)`;", source, re.DOTALL)
    assert match, f"missing {name}"
    return match.group("sql")


def _insert_risk_history(connection: sqlite3.Connection) -> None:
    criticality = (
        "market",
        "SPY",
        "{}",
        "multi",
        "model",
        "none",
        10,
        0,
        0,
        0,
        0,
        0,
        "source",
        "eod",
        "ready",
        "{}",
    )
    connection.executemany(
        """INSERT INTO criticality_snapshots
        (scope,symbol,as_of,horizon,model_version,direction,criticality_score,
         positive_confidence,negative_confidence,qualified_confidence,
         fit_count,qualified_count,source,entitlement_mode,quality_state,payload_json)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        [criticality[:2] + (date,) + criticality[3:] for date in ("2026-01-01", "2026-01-02")],
    )
    flow = (
        "market",
        "SPY",
        "{}",
        "model",
        "normal",
        "source",
        "eod",
        "ready",
        "{}",
    )
    connection.executemany(
        """INSERT INTO flow_stress_snapshots
        (scope,symbol,as_of,model_version,state,source,entitlement_mode,quality_state,payload_json)
        VALUES (?,?,?,?,?,?,?,?,?)""",
        [flow[:2] + (date,) + flow[3:] for date in ("2026-01-01", "2026-01-03")],
    )
    component = (
        "breadth",
        "market",
        "SPY",
        "{}",
        "eod",
        "source",
        "model",
        "eod",
        "ready",
        "{}",
    )
    connection.executemany(
        """INSERT INTO market_risk_component_snapshots
        (component,scope,symbol,as_of,cadence,source,model_version,
         entitlement_mode,quality_state,payload_json)
        VALUES (?,?,?,?,?,?,?,?,?,?)""",
        [component[:3] + (date,) + component[4:] for date in ("2026-01-01", "2026-01-04")],
    )


def test_latest_risk_refs_backfill_and_track_new_inserts():
    connection = sqlite3.connect(":memory:")
    connection.executescript(
        (MIGRATIONS / "0005_criticality_monitor.sql").read_text(encoding="utf-8")
    )
    connection.executescript(
        (MIGRATIONS / "0006_market_risk_components.sql").read_text(encoding="utf-8")
    )
    connection.executescript(
        (MIGRATIONS / "0008_portfolio_hub.sql").read_text(encoding="utf-8")
    )
    _insert_risk_history(connection)
    connection.executescript(
        (MIGRATIONS / "0014_d1_read_efficiency.sql").read_text(encoding="utf-8")
    )

    refs = connection.execute(
        "SELECT series,as_of FROM market_risk_latest_refs ORDER BY series"
    ).fetchall()
    assert refs == [
        ("component", "2026-01-04"),
        ("criticality", "2026-01-02"),
        ("flow", "2026-01-03"),
    ]

    # Newer history advances the pointer; a late old observation does not.
    template = (
        "market",
        "SPY",
        "multi",
        "model",
        "none",
        20,
        0,
        0,
        0,
        0,
        0,
        "source",
        "eod",
        "ready",
        "{}",
    )
    for date in ("2026-01-05", "2025-12-31"):
        connection.execute(
            """INSERT INTO criticality_snapshots
            (scope,symbol,as_of,horizon,model_version,direction,criticality_score,
             positive_confidence,negative_confidence,qualified_confidence,
             fit_count,qualified_count,source,entitlement_mode,quality_state,payload_json)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            template[:2] + (date,) + template[2:],
        )
    assert connection.execute(
        "SELECT as_of FROM market_risk_latest_refs WHERE series='criticality'"
    ).fetchone()[0] == "2026-01-05"

    rows = connection.execute(_latest_sql("LATEST_CRITICALITY_SQL")).fetchall()
    assert len(rows) == 1
    assert rows[0][2] == "2026-01-05"
    flow_rows = connection.execute(_latest_sql("LATEST_FLOW_SQL")).fetchall()
    component_rows = connection.execute(_latest_sql("LATEST_COMPONENTS_SQL")).fetchall()
    assert len(flow_rows) == 1
    assert flow_rows[0][2] == "2026-01-03"
    assert len(component_rows) == 1
    assert component_rows[0][3] == "2026-01-04"


def test_latest_portfolio_lookup_uses_composite_index():
    connection = sqlite3.connect(":memory:")
    connection.executescript(
        (MIGRATIONS / "0005_criticality_monitor.sql").read_text(encoding="utf-8")
    )
    connection.executescript(
        (MIGRATIONS / "0006_market_risk_components.sql").read_text(encoding="utf-8")
    )
    connection.executescript(
        (MIGRATIONS / "0008_portfolio_hub.sql").read_text(encoding="utf-8")
    )
    connection.executescript(
        (MIGRATIONS / "0014_d1_read_efficiency.sql").read_text(encoding="utf-8")
    )
    plan = " ".join(
        row[3]
        for row in connection.execute(
            """EXPLAIN QUERY PLAN SELECT * FROM portfolio_source_runs
            WHERE source='ibkr' AND complete=1 ORDER BY as_of DESC LIMIT 1"""
        )
    )
    assert "idx_portfolio_source_latest" in plan


def test_hot_routes_do_not_scan_full_history():
    health = (ROOT / "dashboard/functions/api/v1/market-risk/health.js").read_text(
        encoding="utf-8"
    )
    margin = (ROOT / "dashboard/functions/api/v2/portfolio/margin.js").read_text(
        encoding="utf-8"
    )
    assert "COUNT(*) FROM criticality_snapshots" not in health
    assert "market_risk_latest_refs" in health
    assert "ORDER BY r.as_of,v.tag" not in margin
    assert "ORDER BY as_of DESC LIMIT 1" in margin

    timer = (
        ROOT / "_system/trading/portfolio_hub/deploy/portfolio-hub-publisher.timer"
    ).read_text(encoding="utf-8")
    assert "OnUnitActiveSec=5min" in timer
    assert "OnUnitActiveSec=30s" not in timer


def _build_schema() -> sqlite3.Connection:
    """Every migration the row-scan indexes depend on, applied in order."""
    connection = sqlite3.connect(":memory:")
    for migration in (
        "0005_criticality_monitor.sql",
        "0006_market_risk_components.sql",
        "0007_sleeves.sql",
        "0008_portfolio_hub.sql",
        "0014_d1_read_efficiency.sql",
        "0016_bound_remaining_row_scans.sql",
    ):
        connection.executescript(
            (MIGRATIONS / migration).read_text(encoding="utf-8")
        )
    return connection


def _plan(connection: sqlite3.Connection, sql: str, params=()) -> str:
    return " | ".join(
        row[3] for row in connection.execute(f"EXPLAIN QUERY PLAN {sql}", params)
    )


def _load_pruner():
    spec = importlib.util.spec_from_file_location(
        "prune_cloudflare_d1", ROOT / "_system/scripts/prune_cloudflare_d1.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _capture(statements: list[str]):
    """Record the SQL a retention pass would run, and report nothing deleted so
    the batch loop stops after one round."""

    def execute(sql: str) -> int:
        statements.append(sql)
        return 0

    return execute


def test_history_route_seeks_by_symbol():
    """/market-risk/history filters on symbol alone. Every other index on these
    tables leads with scope, so before 0016 the planner could not seek and each
    request read the whole table to return LIMIT rows."""
    connection = _build_schema()
    source = (ROOT / "dashboard/functions/api/v1/market-risk/history.js").read_text(
        encoding="utf-8"
    )
    statements = re.findall(r"db\.prepare\(`(.*?)`\)", source, re.DOTALL)
    assert len(statements) == 2, statements
    for sql in statements:
        plan = _plan(connection, sql, ("SPY", 250))
        assert "SCAN" not in plan, plan
        assert "_symbol_history" in plan, plan


def test_retention_deletes_seek_by_time():
    """prune_time_series deletes by time alone. A table whose time column does
    not lead an index is rescanned once per batch, on every deployment."""
    connection = _build_schema()
    pruner = _load_pruner()
    statements: list[str] = []
    pruner.prune_time_series(_capture(statements), pruner.table_names(connection))
    assert statements

    covered = set()
    for sql in statements:
        table = re.search(r"DELETE FROM (\w+)", sql).group(1)
        covered.add(table)
        assert f"SCAN {table}" not in _plan(connection, sql), f"{table}: {sql}"
    # The live series, so a policy silently dropped from the loop fails here.
    assert {
        "criticality_snapshots",
        "flow_stress_snapshots",
        "market_risk_component_snapshots",
        "sleeve_marks",
        "sleeve_classifier_audit",
    } <= covered


def test_portfolio_retention_reaches_references_by_index():
    """prune_portfolio_history clears each referencing table before its source
    run. Ranking portfolio_source_runs is an intentional scan; reaching the
    reference rows by source_run_id is not."""
    connection = _build_schema()
    pruner = _load_pruner()
    statements: list[str] = []
    pruner.prune_portfolio_history(
        _capture(statements), pruner.table_names(connection)
    )
    assert statements

    for sql in statements:
        table = re.search(r"DELETE FROM (\w+)", sql).group(1)
        if table == "portfolio_source_runs":
            continue
        assert f"SCAN {table}" not in _plan(connection, sql), f"{table}: {sql}"

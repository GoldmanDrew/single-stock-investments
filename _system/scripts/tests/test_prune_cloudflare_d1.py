import importlib.util
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


pruner = load_module(
    "prune_cloudflare_d1",
    ROOT / "_system" / "scripts" / "prune_cloudflare_d1.py",
)


def execute_on(connection: sqlite3.Connection):
    def execute(sql: str) -> int:
        connection.execute(sql)
        return connection.execute("SELECT changes()").fetchone()[0]

    return execute


def test_portfolio_prune_keeps_latest_daily_and_current_intraday_snapshots():
    connection = sqlite3.connect(":memory:")
    connection.executescript(
        (ROOT / "dashboard/cloudflare/migrations/0008_portfolio_hub.sql").read_text(
            encoding="utf-8"
        )
    )
    connection.execute("PRAGMA foreign_keys = ON")
    rows = [
        ("old-1", "ibkr", "acct", "2020-01-02T10:00:00Z", 1),
        ("old-2", "ibkr", "acct", "2020-01-02T16:00:00Z", 1),
        ("today-1", "ibkr", "acct", "2999-01-02T10:00:00Z", 1),
        ("today-2", "ibkr", "acct", "2999-01-02T16:00:00Z", 1),
        ("strategy-1", "risk-engine", None, "2020-01-02T10:00:00Z", 1),
        ("strategy-2", "risk-engine", None, "2020-01-02T11:00:00Z", 1),
        ("flex-1", "ibkr_flex", "acct", "2020-01-02T23:59:00Z", 1),
        ("flex-2", "ibkr_flex", "acct", "2020-01-03T23:59:00Z", 1),
    ]
    connection.executemany(
        """INSERT INTO portfolio_source_runs
        (source_run_id,schema_version,source,account_alias,as_of,complete,
         completeness_json,content_sha256,object_key,received_at)
        VALUES (?, 'test.v1', ?, ?, ?, ?, '{}', 'sha', 'r2/key', ?)""",
        [(*row, row[3]) for row in rows],
    )
    connection.executemany(
        """INSERT INTO portfolio_account_values
        (source_run_id,tag,currency,segment,model_code,value_decimal,source,as_of)
        VALUES (?, 'NetLiquidation', 'USD', '', '', '100', 'ibkr', ?)""",
        [(row[0], row[3]) for row in rows if row[1] == "ibkr"],
    )
    connection.execute(
        """INSERT INTO portfolio_reconciliation_breaks
        (break_id,source_run_id,account_alias,break_type,severity,status,details_json,created_at)
        VALUES ('break-old','old-1','acct','test','low','open','{}','2020-01-02')"""
    )

    deleted = pruner.prune_portfolio_history(
        execute_on(connection), pruner.table_names(connection), batch_size=1
    )

    remaining = {
        row[0]
        for row in connection.execute(
            "SELECT source_run_id FROM portfolio_source_runs"
        ).fetchall()
    }
    assert deleted == 2
    assert remaining == {
        "old-2",
        "today-1",
        "today-2",
        "strategy-2",
        "flex-1",
        "flex-2",
    }
    assert connection.execute(
        "SELECT COUNT(*) FROM portfolio_reconciliation_breaks"
    ).fetchone()[0] == 0
    assert connection.execute(
        "SELECT COUNT(*) FROM portfolio_account_values"
    ).fetchone()[0] == 3


def test_time_retention_prunes_only_rows_older_than_policy():
    connection = sqlite3.connect(":memory:")
    connection.execute(
        "CREATE TABLE criticality_snapshots (as_of TEXT NOT NULL, payload_json TEXT)"
    )
    connection.executemany(
        "INSERT INTO criticality_snapshots VALUES (?, '{}')",
        [("2020-01-01T00:00:00Z",), ("2999-01-01T00:00:00Z",)],
    )

    changes = pruner.prune_time_series(
        execute_on(connection),
        {"criticality_snapshots"},
        batch_size=1,
        policies=(("criticality_snapshots", "as_of", 14),),
    )

    assert changes == {"criticality_snapshots": 1}
    assert connection.execute(
        "SELECT as_of FROM criticality_snapshots"
    ).fetchall() == [("2999-01-01T00:00:00Z",)]


def test_time_retention_preserves_stale_current_risk_snapshot():
    connection = sqlite3.connect(":memory:")
    migrations = ROOT / "dashboard/cloudflare/migrations"
    for name in (
        "0005_criticality_monitor.sql",
        "0006_market_risk_components.sql",
        "0008_portfolio_hub.sql",
        "0014_d1_read_efficiency.sql",
    ):
        connection.executescript((migrations / name).read_text(encoding="utf-8"))
    values = (
        "market", "SPY", "multi", "model", "none", 10, 0, 0, 0,
        0, 0, "source", "eod", "ready", "{}",
    )
    for date in ("2020-01-01", "2020-01-02"):
        connection.execute(
            """INSERT INTO criticality_snapshots
            (scope,symbol,as_of,horizon,model_version,direction,criticality_score,
             positive_confidence,negative_confidence,qualified_confidence,
             fit_count,qualified_count,source,entitlement_mode,quality_state,payload_json)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            values[:2] + (date,) + values[2:],
        )

    changes = pruner.prune_time_series(
        execute_on(connection),
        pruner.table_names(connection),
        policies=(("criticality_snapshots", "as_of", 14),),
    )

    assert changes == {"criticality_snapshots": 1}
    assert connection.execute(
        "SELECT as_of FROM criticality_snapshots"
    ).fetchall() == [("2020-01-02",)]


def test_deploy_prunes_before_migrations_so_a_full_database_can_recover():
    action = (
        ROOT / ".github/actions/deploy-cloudflare-dashboard/action.yml"
    ).read_text(encoding="utf-8")
    prune_at = action.find("prune_cloudflare_d1.py")
    migrate_at = action.find("d1 migrations apply")
    assert prune_at >= 0
    assert prune_at < migrate_at


def test_deploy_defers_only_the_known_free_tier_quota_failure():
    action = (
        ROOT / ".github/actions/deploy-cloudflare-dashboard/action.yml"
    ).read_text(encoding="utf-8")
    assert "exceeded D1's free tier daily row (read|write) limit" in action
    assert "D1 synchronization deferred" in action
    assert 'exit "$D1_STATUS"' in action

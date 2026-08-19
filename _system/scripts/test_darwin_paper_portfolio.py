import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent))
from darwin.accounts import AccountCtx  # noqa: E402
from darwin import paper_portfolio  # noqa: E402


def _ctx(tmp_path):
    return AccountCtx(
        account_id="roth",
        mandate_path=tmp_path / "mandate.json",
        portfolio_path=tmp_path / "portfolio.json",
        target_weights_path=tmp_path / "weights.json",
        paper_state_path=tmp_path / "paper.json",
        paper_events_path=tmp_path / "events.jsonl",
    )


def _update(ctx):
    return paper_portfolio.update_paper_portfolio(
        ctx,
        {"paper": {"initial_nav_usd": 100_000}},
        {"ABC": 1.0},
        "champion-v1",
        {"label": "normal"},
        {"benchmarks": {"champion": {"cumulative_return": 0.12}}},
    )


def test_monthly_mark_is_applied_once(tmp_path, monkeypatch):
    ctx = _ctx(tmp_path)
    monkeypatch.setattr(
        paper_portfolio,
        "_weighted_return",
        lambda _weights: (0.10, [], "2026-07-01", {"ABC": "fixture"}),
    )

    _update(ctx)  # inception
    first = _update(ctx)
    repeated = _update(ctx)

    assert first["last_mark"]["nav_usd"] == 110_000
    assert repeated["last_mark"]["nav_usd"] == 110_000
    assert repeated["last_mark"]["source_period"] == "2026-07-01"


def test_new_period_compounds_once(tmp_path, monkeypatch):
    ctx = _ctx(tmp_path)
    mark = {"period": "2026-07-01", "return": 0.10}
    monkeypatch.setattr(
        paper_portfolio,
        "_weighted_return",
        lambda _weights: (mark["return"], [], mark["period"], {"ABC": "fixture"}),
    )

    _update(ctx)
    _update(ctx)
    mark.update({"period": "2026-08-01", "return": 0.05})
    advanced = _update(ctx)

    assert advanced["last_mark"]["nav_usd"] == 115_500
    assert advanced["last_mark"]["source_period"] == "2026-08-01"


def test_legacy_compounded_nav_is_quarantined(tmp_path, monkeypatch):
    ctx = _ctx(tmp_path)
    ctx.paper_state_path.write_text(
        '{"inception_date":"2026-06-03","initial_nav_usd":100000,"policy_id":"champion-v1",'
        '"weights_pct":{},"last_mark":{"date":"2026-08-11","nav_usd":167343.01,'
        '"period_return_pct":0,"cumulative_return_pct":67.343}}',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        paper_portfolio,
        "_weighted_return",
        lambda _weights: (0.0, ["ABC"], None, {}),
    )

    migrated = _update(ctx)

    assert migrated["last_mark"]["nav_usd"] == 100_000
    assert migrated["status"] == "tracking_after_legacy_quarantine"
    assert migrated["legacy_quarantine"]["last_mark"]["cumulative_return_pct"] == 67.343

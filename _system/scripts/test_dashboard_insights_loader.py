import json
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_dashboard_data as dashboard  # noqa: E402


def test_load_insights_document_merges_shards(tmp_path, monkeypatch):
    insight_dir = tmp_path / "insights"
    insight_dir.mkdir()
    (insight_dir / "manifest.json").write_text(
        json.dumps({"generated_at": "2026-08-19T12:00:00Z", "record_count": 7}),
        encoding="utf-8",
    )
    (insight_dir / "tickers.json").write_text(
        json.dumps({"by_ticker": {"ABC": {"event_count": 2}}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(dashboard, "DATA_DIR", tmp_path)

    loaded = dashboard.load_insights_document()

    assert loaded["record_count"] == 7
    assert loaded["by_ticker"]["ABC"]["event_count"] == 2

from __future__ import annotations

import json
from pathlib import Path

from _system.scripts import build_cloudflare_pages_site as builder


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_private_sleeve_snapshots_are_never_deployed(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "dashboard"
    output = tmp_path / "site"
    source.mkdir()
    (source / "index.html").write_text("<!doctype html>", encoding="utf-8")
    _write_json(source / "data" / "core.json", {"tickers": ["TEST"]})
    _write_json(source / "data" / "tickers" / "TEST.json", {"ticker": "TEST"})
    _write_json(source / "data" / "insights" / "manifest.json", {"schema": 1})
    _write_json(source / "data" / "sleeves_drew.json", {"positions": [{"ticker": "SECRET"}]})
    _write_json(source / "data" / "sleeves_michael.json", {"positions": [{"ticker": "SECRET"}]})
    _write_json(source / "data" / "sleeves_future_owner.json", {"positions": [{"ticker": "SECRET"}]})
    _write_json(source / "data" / "portfolio" / "latest.json", {"positions": [{"ticker": "SECRET"}]})

    monkeypatch.setattr(builder, "ROOT", tmp_path)
    monkeypatch.setattr(builder, "DEFAULT_SOURCE", source)
    report = builder.build(source, output)

    assert not (output / "data" / "sleeves_drew.json").exists()
    assert not (output / "data" / "sleeves_michael.json").exists()
    assert not (output / "data" / "sleeves_future_owner.json").exists()
    assert not (output / "data" / "portfolio" / "latest.json").exists()
    reasons = {row["path"]: row["reason"] for row in report["excluded"]}
    assert reasons["data/sleeves_drew.json"] == "private account artifact"
    assert reasons["data/sleeves_michael.json"] == "private account artifact"


def test_asset_versions_are_stamped_from_content(tmp_path: Path) -> None:
    """A hand-written ?v= only changes when someone remembers; a hash cannot go stale.

    insights-viz.js once shipped a fix under a stamp last touched a week
    earlier, so returning browsers kept serving the cached, broken file.
    """
    site = tmp_path / "site"
    site.mkdir()
    (site / "app.js").write_text("console.log(1)", encoding="utf-8")
    (site / "app.css").write_text("body{}", encoding="utf-8")
    (site / "index.html").write_text(
        '<link href="app.css?v=handwritten" rel="stylesheet">'
        '<script src="app.js?v=handwritten"></script>'
        '<script src="https://cdn.example.com/chart.js?v=4.4.1"></script>',
        encoding="utf-8",
    )

    stamped = builder.stamp_asset_versions(site)
    first = (site / "index.html").read_text(encoding="utf-8")

    assert stamped == 2
    assert "?v=handwritten" not in first
    # Remote assets are left exactly as authored.
    assert "https://cdn.example.com/chart.js?v=4.4.1" in first

    # Same bytes, same stamp: caching still works across rebuilds.
    builder.stamp_asset_versions(site)
    assert (site / "index.html").read_text(encoding="utf-8") == first

    # Changed bytes, changed stamp: the fix reaches the browser.
    (site / "app.js").write_text("console.log(2)", encoding="utf-8")
    builder.stamp_asset_versions(site)
    assert (site / "index.html").read_text(encoding="utf-8") != first


def test_stamping_leaves_missing_assets_alone(tmp_path: Path) -> None:
    site = tmp_path / "site"
    site.mkdir()
    (site / "index.html").write_text('<script src="gone.js?v=keepme"></script>', encoding="utf-8")
    assert builder.stamp_asset_versions(site) == 0
    assert "?v=keepme" in (site / "index.html").read_text(encoding="utf-8")

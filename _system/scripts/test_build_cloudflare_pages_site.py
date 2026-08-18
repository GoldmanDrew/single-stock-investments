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

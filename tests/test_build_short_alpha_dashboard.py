from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "_system" / "scripts" / "build_short_alpha_dashboard.py"
SPEC = importlib.util.spec_from_file_location("build_short_alpha_dashboard", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def source() -> dict:
    return json.loads(
        (ROOT / "_system" / "research" / "short-alpha" / "ideas.json").read_text(encoding="utf-8")
    )


def test_initial_short_alpha_book_compiles() -> None:
    payload = MODULE.build()
    assert payload["summary"]["position_count"] == 8
    assert payload["summary"]["gross_short_exposure_usd"] == 69_746
    assert {row["ticker"] for row in payload["ideas"]} == {
        "ASPN", "WEST", "EQPT", "FLUX", "XTIA", "EFOR", "LBRDK", "ECHX"
    }
    echx = next(row for row in payload["ideas"] if row["ticker"] == "ECHX")
    assert echx["instrument_type"] == "leveraged_etf"
    assert echx["underlying"] == "ECHO"
    assert echx["primary_framework"] == "structural_decay"


def test_primary_framework_must_be_assigned() -> None:
    raw = source()
    broken = copy.deepcopy(raw)
    broken["ideas"][0]["primary_framework"] = "regulatory"
    with pytest.raises(MODULE.LedgerError, match="primary framework"):
        MODULE._validate(broken)


def test_position_must_be_short() -> None:
    raw = source()
    broken = copy.deepcopy(raw)
    broken["ideas"][0]["position"]["shares"] = 100
    with pytest.raises(MODULE.LedgerError, match="shares must be negative"):
        MODULE._validate(broken)


def test_dashboard_wires_short_alpha_lazy_view() -> None:
    html = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
    assert 'data-view="short-alpha"' in html
    assert 'id="short-alpha-panel"' in html
    assert '<script src="short-alpha-viz.js"></script>' in html
    assert "fetch('data/short_alpha.json?'" in html
    assert "view === 'short-alpha'" in html

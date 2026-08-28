#!/usr/bin/env python3
"""Unit tests for INV two-phase cooling watch (regex, ranker, dedupe, compact)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import two_phase_watch as tpw  # noqa: E402


def test_cooling_regex_hits_named_terms():
    assert tpw.COOLING_RE.search("pumped two-phase cooling")
    assert tpw.COOLING_RE.search("NeuCool IR150")
    assert tpw.COOLING_RE.search("OMNICOOL program")
    assert tpw.COOLING_RE.search("W45 facility water")
    assert tpw.COOLING_RE.search("refrigerant loop cools the plate")
    assert not tpw.COOLING_RE.search("the company cooled its guidance")


def test_vertiv_cdu_requires_liquid_context():
    bare = "Vertiv shipped a CDU to a colocation hall"
    assert tpw.cooling_match(bare, "VRT") is None
    mixed = "Vertiv CDU for two-phase refrigerant cooling"
    assert tpw.cooling_match(mixed, "VRT") is not None


def test_rank_hyperscaler_production_is_one():
    rank, falsifier, vendors = tpw.rank_hit(
        "Accelsius NeuCool in production at a Microsoft Azure 40 MW hall",
        source_ticker="INV",
        source_kind="ir",
        title="operator win",
    )
    assert rank == 1
    assert falsifier is False
    assert "Accelsius" in vendors


def test_rank_inv_capital_darknx_is_one_and_falsifier():
    rank, falsifier, vendors = tpw.rank_hit(
        "The DarkNX booking was removed and directors forfeit the Accelsius earnout shares.",
        source_ticker="INV",
        source_kind="filing",
        title="8-K",
    )
    assert rank == 1
    assert falsifier is True
    assert "Accelsius" in vendors


def test_rank_nvidia_reference_vertiv_is_two_falsifier():
    rank, falsifier, vendors = tpw.rank_hit(
        "NVIDIA MGX reference design lists Vertiv two-phase cold plates",
        source_ticker="NVDA",
        source_kind="event_pdf",
        title="MGX guide",
    )
    assert rank == 2
    assert falsifier is True
    assert "Vertiv" in vendors


def test_rank_oem_sku_is_three():
    rank, _falsifier, vendors = tpw.rank_hit(
        "Super Micro factory-integrated two-phase SKU with Accelsius NeuCool",
        source_ticker="SMCI",
        source_kind="filing",
        title="10-K",
    )
    assert rank == 3
    assert "Accelsius" in vendors


def test_rank_vertiv_ga_without_accelsius_is_four():
    rank, falsifier, vendors = tpw.rank_hit(
        "Vertiv announces generally available two-phase CDU",
        source_ticker="VRT",
        source_kind="ir",
        title="GA",
    )
    assert rank == 4
    assert falsifier is True
    assert "Vertiv" in vendors


def test_rank_heydari_paper_is_six():
    rank, falsifier, _vendors = tpw.rank_hit(
        "Heydari and Manaserh ARPA-E OMNICOOL Hot Chips paper",
        source_ticker="NVDA",
        source_kind="event_pdf",
        title="paper",
    )
    assert rank == 6
    assert falsifier is False


def test_dedupe_keeps_first_seen_and_promotes_rank():
    today = "2026-08-26"
    first = tpw.make_hit(
        title="x",
        quote="Accelsius two-phase",
        source_kind="ir",
        source_ticker="INV",
        source_url="https://example.com/a",
        local_path="",
        rank=5,
        vendor_named=["Accelsius"],
        falsifier=False,
        first_seen="2026-08-01",
        last_seen="2026-08-01",
    )
    again = tpw.make_hit(
        title="x",
        quote="Accelsius two-phase",
        source_kind="ir",
        source_ticker="INV",
        source_url="https://example.com/a",
        local_path="INV/investor-documents/competitive/ir/a.htm",
        rank=3,
        vendor_named=["Accelsius"],
        falsifier=False,
        first_seen=today,
        last_seen=today,
    )
    merged, new_rows = tpw.merge_hits([first], [again], today)
    assert new_rows == []
    assert len(merged) == 1
    assert merged[0]["first_seen"] == "2026-08-01"
    assert merged[0]["last_seen"] == today
    assert merged[0]["rank"] == 3
    assert merged[0]["local_path"].endswith("a.htm")


def test_compact_is_none_for_other_tickers(tmp_path, monkeypatch):
    monkeypatch.setattr(tpw, "LEDGER_PATH", tmp_path / "missing.json")
    assert tpw.compact_for_dashboard("NVDA") is None
    assert tpw.compact_for_dashboard("INV") is None


def test_compact_shape_and_stale(tmp_path, monkeypatch):
    ledger = {
        "schema_version": 1,
        "ticker": "INV",
        "as_of": "2026-01-01",
        "highest_open_rank": 1,
        "status": "new_hits",
        "hits": [
            {
                "id": "abc",
                "first_seen": "2026-08-19",
                "last_seen": "2026-08-26",
                "rank": 1,
                "source_kind": "filing",
                "source_ticker": "INV",
                "title": "DarkNX removed",
                "quote": "booking removed",
                "source_url": "https://example.com",
                "local_path": "INV/investor-documents/sec-edgar/x.htm",
                "vendor_named": ["Accelsius"],
                "falsifier": True,
            }
        ],
    }
    path = tmp_path / "ledger.json"
    path.write_text(json.dumps(ledger), encoding="utf-8")
    monkeypatch.setattr(tpw, "LEDGER_PATH", path)
    compact = tpw.compact_for_dashboard("INV")
    assert compact is not None
    assert compact["status"] == "stale"
    assert compact["highest_open_rank"] == 1
    assert compact["count_by_rank"]["1"] == 1
    assert compact["hits"][0]["date"] == "2026-08-19"
    assert compact["hits"][0]["falsifier"] is True
    assert "two_phase_cooling_watch.md" in compact["spec_path"]


def test_linkedin_syndicated_defaults_to_context_rank():
    rank, _f, _v = tpw.rank_hit(
        "Accelsius booth at a LinkedIn recap of GTC",
        source_ticker="INV",
        source_kind="linkedin_syndicated",
        title="GTC booth",
    )
    assert rank == 5


def test_ir_downloadable_keeps_press_not_blog_index():
    assert tpw._ir_downloadable("https://ir.innventure.com/news-releases/news-release-details/innventure-board-issues")
    assert tpw._ir_downloadable("https://www.innventure.com/news/innventure-board-issues-letter-to-shareholders")
    assert tpw._ir_downloadable("https://accelsius.com/foo.pdf")
    assert not tpw._ir_downloadable("https://accelsius.com/news/")
    assert not tpw._ir_downloadable("https://linkedin.com/feed")
    a = tpw.hit_id("https://X.com/a", "Hello World")
    b = tpw.hit_id("https://x.com/a", "hello world")
    assert a == b
    assert len(a) == 16


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))

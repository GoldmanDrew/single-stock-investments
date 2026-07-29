#!/usr/bin/env python3
"""Tests for activist feed integrity (ghost links, weak matches, publisher guards)."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from activist_common import (  # noqa: E402
    classify_publisher_page,
    match_report_to_ticker,
    publisher_match_allowed,
    publisher_match_blob,
    resolve_report_file,
    ticker_meta,
    url_target_mismatch,
)
from cleanup_activist_false_positives import should_keep  # noqa: E402
from build_activist_feed import build_feed, dedupe_canonical_reports, feed_eligible, github_blob  # noqa: E402
from sec_filer_parse import _add_name  # noqa: E402

FEED_PATH = ROOT / "dashboard" / "data" / "activist_feed.json"


class ActivistFeedTests(unittest.TestCase):
    def test_short_tickers_do_not_match_ordinary_prose(self) -> None:
        examples = {
            "A": "Carvana: A Father-Son Accounting Grift",
            "ON": "Appendix to Our Report on Partners Group Holding AG",
            "IT": "It then promotes LNG contract indexing",
            "ED": "the Enforcement Directorate (ED) raided Vedanta",
            "MAR": "Published Mar 25, 2026",
            "T": "Today Viceroy sent a letter to MAS",
        }
        for ticker, text in examples.items():
            matched, _confidence, reason = match_report_to_ticker(text, ticker_meta(ticker))
            self.assertFalse(matched, msg=f"{ticker} matched via {reason}: {text}")

    def test_short_ticker_requires_explicit_market_notation(self) -> None:
        matched, confidence, reason = match_report_to_ticker(
            "Initiating coverage of NYSE: T", ticker_meta("T")
        )
        self.assertTrue(matched)
        self.assertGreaterEqual(confidence, 0.99)
        self.assertEqual(reason, "ticker_explicit")

    def test_non_report_publisher_routes_are_rejected(self) -> None:
        for url, title in (
            ("https://sprucepointcap.com/legal-disclaimer", "Legal Disclaimer | All Rights Reserved"),
            ("https://viceroyresearch.org/publications", "Publications"),
            ("https://example.com/terms", "Terms"),
        ):
            is_report, _reason = classify_publisher_page(url, title)
            self.assertFalse(is_report)

    def test_cross_ticker_publisher_url_is_quarantined(self) -> None:
        rows = [
            {"ticker": "A", "source": "publisher_site", "source_url": "https://example.com/report"},
            {"ticker": "T", "source": "publisher_site", "source_url": "https://example.com/report"},
        ]
        kept, _duplicates, conflicts = dedupe_canonical_reports(rows)
        self.assertEqual(kept, [])
        self.assertEqual(conflicts, 2)

    def test_viceroy_osc_ciro_does_not_match_azlcz(self) -> None:
        meta = ticker_meta("AZLCZ")
        url = "https://viceroyresearch.org/osc-and-ciro/"
        title = "OSC and CIRO"
        blob = f"{title} {url}"
        self.assertTrue(url_target_mismatch(url, title, meta))
        ok, _confidence, reason = publisher_match_allowed(url, title, blob, meta)
        self.assertFalse(ok)
        self.assertIn(reason, ("url_mismatch", "no_match", "alias:azlcz"))

    def test_missing_local_file_excluded_without_source_url(self) -> None:
        report = {
            "firm_id": "viceroy",
            "side": "short",
            "local_file": "AZLCZ/third-party-analyses/activist_reports/short/viceroy_2026-01-01_osc-and-ciro.html",
            "include_in_feed": True,
        }
        _ref, _is_pdf, exists = resolve_report_file(report)
        self.assertFalse(exists)
        self.assertFalse(feed_eligible(report))

    def test_missing_file_with_source_url_stays_eligible(self) -> None:
        report = {
            "firm_id": "viceroy",
            "side": "short",
            "local_file": "missing/path.html",
            "source_url": "https://viceroyresearch.org/example/",
            "include_in_feed": True,
        }
        self.assertTrue(feed_eligible(report))

    def test_file_exists_matches_disk(self) -> None:
        if not FEED_PATH.exists():
            self.skipTest("activist_feed.json missing")
        feed = json.loads(FEED_PATH.read_text(encoding="utf-8"))
        for row in feed.get("feed") or []:
            local_file = row.get("local_file")
            if not local_file:
                continue
            path = ROOT / str(local_file).replace("\\", "/")
            if path.exists():
                self.assertTrue(row.get("file_exists"), msg=f"stale file_exists on {local_file}")

    def test_tier_counts_match_feed(self) -> None:
        if not FEED_PATH.exists():
            self.skipTest("activist_feed.json missing")
        feed = json.loads(FEED_PATH.read_text(encoding="utf-8"))
        summary = feed.get("summary") or {}
        rows = feed.get("feed") or []
        tier_sum = (summary.get("signal_count") or 0) + (summary.get("context_count") or 0) + (
            summary.get("noise_count") or 0
        )
        self.assertEqual(tier_sum, len(rows))

    def test_signal_rows_have_verified_targets_and_unique_publisher_urls(self) -> None:
        if not FEED_PATH.exists():
            self.skipTest("activist_feed.json missing")
        feed = json.loads(FEED_PATH.read_text(encoding="utf-8"))
        publisher_targets: dict[str, set[str]] = {}
        for row in feed.get("feed") or []:
            if row.get("tier") == "signal":
                self.assertTrue(row.get("target_verified"), msg=f"unverified signal: {row}")
            if row.get("source") == "publisher_site" and row.get("source_url"):
                publisher_targets.setdefault(row["source_url"].rstrip("/"), set()).add(row.get("ticker"))
        conflicts = {url: targets for url, targets in publisher_targets.items() if len(targets) > 1}
        self.assertEqual(conflicts, {})

    def test_github_blob_only_when_file_exists_in_feed(self) -> None:
        if not FEED_PATH.exists():
            self.skipTest("activist_feed.json missing")
        feed = json.loads(FEED_PATH.read_text(encoding="utf-8"))
        for row in feed.get("feed") or []:
            if row.get("github_url"):
                self.assertTrue(row.get("file_exists"), msg=f"ghost github_url on {row.get('ticker')}")
            if row.get("file_exists") is False:
                self.assertIsNone(row.get("github_url"), msg=f"github_url on missing file {row.get('local_file')}")

    def test_no_viceroy_osc_ciro_rows_in_feed(self) -> None:
        if not FEED_PATH.exists():
            self.skipTest("activist_feed.json missing")
        feed = json.loads(FEED_PATH.read_text(encoding="utf-8"))
        bad = [
            r
            for r in feed.get("feed") or []
            if "osc-and-ciro" in (r.get("local_file") or "") or "osc and ciro" in (r.get("title") or "").lower()
        ]
        self.assertEqual(bad, [], msg=f"spurious viceroy rows remain: {len(bad)}")

    def test_strip_leading_paren_from_filer_names(self) -> None:
        names: list[str] = []
        seen: set[str] = set()
        _add_name(names, seen, ") DANAHER CORPORATION")
        self.assertEqual(names, ["DANAHER CORPORATION"])

    def test_github_repo_uses_org_default(self) -> None:
        url = github_blob("README.md")
        self.assertIn("magis-capital-partners/single-stock-investments", url or "")

    def test_spruce_uranium_does_not_match_nvda(self) -> None:
        meta = ticker_meta("NVDA")
        url = "https://sprucepointcap.com/research/uranium-energy-corporation"
        title = "Sep 18, 2025"
        blob = f"{title} {url}"
        self.assertTrue(url_target_mismatch(url, title, meta))
        ok, _confidence, reason = publisher_match_allowed(url, title, blob, meta)
        self.assertFalse(ok)
        self.assertIn(reason, ("url_mismatch", "no_match", "alias:corporation", "alias:nvidia"))

    def test_spruce_uranium_energy_matches_uec_not_uroy(self) -> None:
        url = "https://sprucepointcap.com/research/uranium-energy-corporation"
        title = "Sep 18, 2025"
        blob = f"{title} {url}"
        body = (
            "After conducting a forensic evaluation of Uranium Energy Corp. "
            "(NYSE American: UEC), we believe investors should exercise caution."
        )

        uroy_meta = ticker_meta("UROY")
        self.assertTrue(url_target_mismatch(url, title, uroy_meta))
        uroy_ok, _confidence, uroy_reason = publisher_match_allowed(
            url, title, blob, uroy_meta
        )
        self.assertFalse(uroy_ok, msg=uroy_reason)
        uroy_body_match, _confidence, uroy_body_reason = match_report_to_ticker(
            body, uroy_meta
        )
        self.assertFalse(uroy_body_match, msg=uroy_body_reason)

        uec_meta = ticker_meta("UEC")
        self.assertEqual(uec_meta["company"], "Uranium Energy Corp.")
        self.assertFalse(url_target_mismatch(url, title, uec_meta))
        uec_ok, _confidence, uec_reason = publisher_match_allowed(
            url, title, blob, uec_meta
        )
        self.assertTrue(uec_ok, msg=uec_reason)
        uec_body_match, _confidence, uec_body_reason = match_report_to_ticker(
            body, uec_meta
        )
        self.assertTrue(uec_body_match, msg=uec_body_reason)

    def test_grizzly_generic_companies_post_does_not_match_mrsh(self) -> None:
        meta = ticker_meta("MRSH")
        url = (
            "https://grizzlyreports.com/academic-studies-find-that-public-companies-"
            "stocks-perform-worse-if-they-sued-short-sellers-after-critical-publications/"
        )
        title = "academic studies find that public compan"
        blob = publisher_match_blob(
            {
                "title": title,
                "source_url": url,
                "firm_name": "Grizzly Research",
                "local_file": (
                    "MRSH/third-party-analyses/activist_reports/short/"
                    "grizzly_2026-01-01_academic-studies-find-that-public-compan.html"
                ),
            }
        )
        self.assertTrue(url_target_mismatch(url, title, meta))
        ok, _confidence, reason = publisher_match_allowed(url, title, blob, meta)
        self.assertFalse(ok)
        self.assertIn(reason, ("url_mismatch", "no_match", "alias:companies"))
        keep, reject_reason = should_keep(
            {
                "source": "local",
                "source_url": url,
                "title": title,
                "local_file": (
                    "MRSH/third-party-analyses/activist_reports/short/"
                    "grizzly_2026-01-01_academic-studies-find-that-public-compan.html"
                ),
                "body_verified": True,
                "body_match_reason": "alias:companies",
            },
            meta,
        )
        self.assertFalse(keep)
        self.assertIn(reject_reason.split(":")[0], ("weak_match", "url_slug_mismatch", "body_alias_only"))


if __name__ == "__main__":
    raise SystemExit(unittest.main())

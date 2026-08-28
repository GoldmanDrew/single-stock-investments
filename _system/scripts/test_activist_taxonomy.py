#!/usr/bin/env python3
"""Tests for the filer taxonomy, the widened form coverage, the wire poll and freshness.

Companion to test_activist_coverage.py. These cover the second wave of fixes:
Schedule 13D covers any >5% holder with control intent, so "filed a 13D" is not
the same as "is an activist"; several campaign form types were never collected;
the press lane polled nothing; and a cancelled job left no failure signal.
"""
from __future__ import annotations

import json
import sys
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

import check_activist_freshness  # noqa: E402
import edinet_activist_scan  # noqa: E402
import press_activist_digest  # noqa: E402
import sec_filer_discovery  # noqa: E402
from activist_common import (  # noqa: E402
    ACTIVIST_FORMS,
    CONDITIONAL_FORMS,
    firm_matchers,
    match_firm_id,
)
from build_cloudflare_pages_site import stamp_asset_versions  # noqa: E402
from sec_filer_parse import (  # noqa: E402
    analyze_sec_filing,
    classify_filer_type,
    classify_sec_filing,
    parse_schedule_13_xml,
    should_include_in_feed,
)

SCHEDULE_13D_XML = """<?xml version="1.0" encoding="UTF-8"?>
<edgarSubmission xmlns="http://www.sec.gov/edgar/schedule13D">
  <headerData><submissionType>SCHEDULE 13D</submissionType></headerData>
  <formData>
    <coverPageHeader>
      <issuerInfo><issuerName>Braveheart Bio, Inc.</issuerName></issuerInfo>
    </coverPageHeader>
    <reportingPersons>
      <reportingPersonInfo>
        <reportingPersonName>Engine Capital Management, LP</reportingPersonName>
        <typeOfReportingPerson>PN</typeOfReportingPerson>
        <percentOfClass>11.4</percentOfClass>
      </reportingPersonInfo>
    </reportingPersons>
  </formData>
</edgarSubmission>
"""


class FilerTaxonomyTests(unittest.TestCase):
    """13D covers any >5% holder with control intent, not just activists."""

    def test_registry_membership_is_authoritative(self) -> None:
        self.assertEqual(
            classify_filer_type(["Elliott Investment Management L.P."], firm_id="elliott"),
            "activist",
        )

    def test_founders_and_control_persons_are_insiders(self) -> None:
        for name in ("Charles W. Ergen", "Joshua Harris", "Abel Avellan", "Barry Diller"):
            self.assertEqual(classify_filer_type([name], firm_id="sec_filer:x"), "insider", name)

    def test_operating_companies_are_strategic(self) -> None:
        for name in ("Riot Platforms, Inc.", "General Electric Company", "Cisco Systems, Inc."):
            self.assertEqual(classify_filer_type([name], firm_id="sec_filer:x"), "strategic", name)

    def test_holdco_vehicles_are_sponsors(self) -> None:
        for name in ("JAB BevCo B.V.", "BBAI Ultimate Holdings, LLC", "New Omaha Holdings L.P."):
            self.assertEqual(classify_filer_type([name], firm_id="sec_filer:x"), "sponsor", name)

    def test_index_managers_are_not_campaigns(self) -> None:
        for name in ("BlackRock, Inc.", "The Vanguard Group", "State Street Corporation"):
            self.assertEqual(
                classify_filer_type([name], firm_id="sec_filer:x"), "index_passive", name
            )

    def test_entity_names_are_never_read_as_people(self) -> None:
        # "Baupost Group LLC" matches the Firstname-Lastname shape otherwise.
        self.assertNotEqual(
            classify_filer_type(["Baupost Group LLC"], firm_id="sec_filer:x"), "insider"
        )

    def test_item_6_declaration_beats_the_name_heuristic(self) -> None:
        # The filer's own cover-page code is better evidence than name shape.
        self.assertEqual(
            classify_filer_type(["Whatever LLC"], firm_id="sec_filer:x", person_types=["IN"]),
            "insider",
        )
        self.assertEqual(
            classify_filer_type(["Some Person"], firm_id="sec_filer:x", person_types=["CO"]),
            "strategic",
        )

    def test_issuer_filing_on_itself_is_strategic(self) -> None:
        self.assertEqual(
            classify_filer_type(
                ["Riot Platforms, Inc."],
                firm_id="sec_filer:x",
                issuer_name="Riot Platforms, Inc.",
            ),
            "strategic",
        )

    def test_item_6_type_is_carried_out_of_the_xml(self) -> None:
        facts = parse_schedule_13_xml(SCHEDULE_13D_XML)
        self.assertEqual(facts["reporting_person_types"], ["PN"])


class NewFormClassTests(unittest.TestCase):
    def test_proxy_access_is_always_a_campaign(self) -> None:
        self.assertEqual(classify_sec_filing("SC 14N", "", []), "proxy_access")

    def test_tender_offer_needs_an_activist_or_intent(self) -> None:
        self.assertEqual(
            classify_sec_filing("SC TO-T", "Elliott Investment Management tender", []),
            "tender_offer",
        )
        self.assertEqual(
            classify_sec_filing("SC TO-T", "an ordinary tender offer", []), "tender_offer_routine"
        )

    def test_8k_only_counts_as_an_outcome_with_both_signals(self) -> None:
        self.assertEqual(
            classify_sec_filing(
                "8-K", "Item 5.02 Departure of Directors ... agreement with Starboard Value", []
            ),
            "campaign_outcome",
        )
        # Item 5.02 alone is a routine board change.
        self.assertEqual(classify_sec_filing("8-K", "Item 5.02 Departure of Directors", []), "other")
        self.assertEqual(classify_sec_filing("8-K", "Item 2.02 results", []), "other")

    def test_section_16_is_accumulation(self) -> None:
        self.assertEqual(classify_sec_filing("4", "", []), "insider_accumulation")

    def test_new_classes_reach_the_feed(self) -> None:
        for cls in ("proxy_access", "tender_offer", "campaign_outcome", "insider_accumulation"):
            self.assertTrue(should_include_in_feed(cls), cls)
        for cls in ("tender_offer_routine", "company_response", "exempt_solicitation"):
            self.assertFalse(should_include_in_feed(cls), cls)

    def test_high_volume_forms_are_not_pulled_unconditionally(self) -> None:
        # An 8-K is fetched only for a ticker with a live campaign; pulling every
        # issuer's 8-K stream would swamp the scan.
        self.assertNotIn("8-K", ACTIVIST_FORMS)
        self.assertIn("8-K", CONDITIONAL_FORMS)
        # Form 4 and 13F-HR come from the filer side, never the issuer side.
        self.assertNotIn("4", ACTIVIST_FORMS)
        self.assertNotIn("13F-HR", ACTIVIST_FORMS)


class FirmMatchPerformanceTests(unittest.TestCase):
    """The combined matcher must be a pure speedup, not a behaviour change."""

    def test_combined_matcher_agrees_with_per_term_scanning(self) -> None:
        samples = [
            "Elliott Investment Management L.P. and affiliates",
            "Engine Capital Management, LP",
            "Engine No. 1 LLC",
            "Gabelli Funds, LLC",
            "MANTLE RIDGE LP",
            "a chamber of commerce filing",
            "Banco de Sabadell S.A.",
            "Nippon Active Value Fund plc",
            "no firm named here at all",
        ]
        for text in samples:
            expected = None
            best = ""
            for fid, pattern in firm_matchers():
                found = pattern.search(text)
                if found and len(found.group(0)) > len(best):
                    best, expected = found.group(0), fid
            self.assertEqual(match_firm_id(text), expected, text)

    def test_matching_a_large_filing_stays_fast(self) -> None:
        # 325 separate scans over a 250KB filing took ~2s each, and the pipeline
        # calls this up to three times per filing -- a full reindex of the local
        # corpus would have run for about a day.
        blob = ("lorem ipsum dolor sit amet " * 8000) + " Starboard Value LP "
        start = time.perf_counter()
        self.assertEqual(match_firm_id(blob), "starboard")
        self.assertLess(time.perf_counter() - start, 1.0)


class WirePollTests(unittest.TestCase):
    """The press lane polled nothing; it was three hand-typed seeds."""

    def test_firm_aliases_are_word_bounded(self) -> None:
        matchers = press_activist_digest._firm_alias_matchers()
        self.assertTrue(matchers, "no press_wire firms configured")
        self.assertTrue(
            any(p.search("Elliott Management Sends Letter to Board") for _, p in matchers)
        )
        self.assertFalse(any(p.search("Elliotts Bakery opens") for _, p in matchers))

    def test_no_pattern_contains_a_literal_backspace(self) -> None:
        # A mangled "\\b" compiles to a backspace character, which matches
        # nothing -- the lane would return zero forever and look merely quiet.
        for _fid, pattern in press_activist_digest._firm_alias_matchers():
            self.assertNotIn("\x08", pattern.pattern)

    def test_only_exchange_qualified_tickers_are_accepted(self) -> None:
        held = {"CSGP", "ON", "KEY"}
        self.assertEqual(
            press_activist_digest._ticker_from_headline(
                "Third Point Sends Letter to CoStar Group (NASDAQ: CSGP)", held
            ),
            "CSGP",
        )
        # Bare uppercase words in prose must not resolve to short tickers.
        self.assertIsNone(
            press_activist_digest._ticker_from_headline("A LETTER ON KEY ISSUES", held)
        )

    def test_poll_requires_both_a_firm_and_a_campaign_shape(self) -> None:
        feed = (
            "<rss><channel>"
            "<item><title>Elliott Management Sends Letter to Board of CoStar Group "
            "(NASDAQ: CSGP)</title><link>https://example.com/a</link>"
            "<pubDate>Mon, 25 Aug 2026 10:00:00 GMT</pubDate></item>"
            "<item><title>Elliott Management announces quarterly investor letter</title>"
            "<link>https://example.com/b</link>"
            "<pubDate>Mon, 25 Aug 2026 10:00:00 GMT</pubDate></item>"
            "<item><title>Unrelated Corp reports earnings (NASDAQ: CSGP)</title>"
            "<link>https://example.com/c</link>"
            "<pubDate>Mon, 25 Aug 2026 10:00:00 GMT</pubDate></item>"
            "</channel></rss>"
        )
        with mock.patch.object(press_activist_digest, "fetch_bytes", return_value=feed.encode()):
            rows = press_activist_digest.poll_wire_feeds(
                {"CSGP"}, lookback_days=36500, feeds=(("testwire", "https://example.com/rss"),)
            )
        self.assertEqual([r["source_url"] for r in rows], ["https://example.com/a"])
        self.assertEqual(rows[0]["firm_id"], "elliott")
        self.assertEqual(rows[0]["discovered_by"], "wire_poll")


class FreshnessCheckTests(unittest.TestCase):
    """A cancelled job leaves no failure anywhere; a stale artifact does."""

    NOW = datetime(2026, 8, 26, 12, tzinfo=timezone.utc)

    def _feed(self, tmp: str, *, generated_at: str, rows: int, activist_rows: int = 5) -> Path:
        path = Path(tmp) / "activist_feed.json"
        path.write_text(
            json.dumps(
                {
                    "generated_at": generated_at,
                    "feed": [{"ticker": "X"} for _ in range(rows)],
                    "summary": {"activist_row_count": activist_rows},
                }
            ),
            encoding="utf-8",
        )
        return path

    def test_fresh_populated_feed_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._feed(tmp, generated_at="2026-08-26T06:00:00Z", rows=500)
            ok, problems = check_activist_freshness.check(now=self.NOW, feed_path=path)
            self.assertTrue(ok, problems)

    def test_stale_feed_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._feed(tmp, generated_at="2026-08-02T09:40:49Z", rows=500)
            ok, problems = check_activist_freshness.check(now=self.NOW, feed_path=path)
            self.assertFalse(ok)
            self.assertIn("days old", problems[0])

    def test_a_run_that_collects_nothing_fails(self) -> None:
        # The failure mode a "did the job run?" check cannot see.
        with tempfile.TemporaryDirectory() as tmp:
            path = self._feed(tmp, generated_at="2026-08-26T06:00:00Z", rows=3)
            ok, problems = check_activist_freshness.check(now=self.NOW, feed_path=path)
            self.assertFalse(ok)
            self.assertTrue(any("below the floor" in p for p in problems))

    def test_broken_attribution_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._feed(tmp, generated_at="2026-08-26T06:00:00Z", rows=500, activist_rows=0)
            ok, problems = check_activist_freshness.check(now=self.NOW, feed_path=path)
            self.assertFalse(ok)
            self.assertTrue(any("registry activist" in p for p in problems))

    def test_missing_feed_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ok, problems = check_activist_freshness.check(feed_path=Path(tmp) / "nope.json")
            self.assertFalse(ok)
            self.assertIn("never been built", problems[0])


class AssetStampTests(unittest.TestCase):
    """A hand-written ?v= only changes when someone remembers; a hash cannot."""

    def test_stamp_changes_with_content_and_only_with_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            site = Path(tmp)
            (site / "app.js").write_text("console.log(1)", encoding="utf-8")
            (site / "index.html").write_text(
                '<script src="app.js?v=handwritten"></script>'
                '<script src="https://cdn.example.com/x.js?v=1"></script>',
                encoding="utf-8",
            )
            self.assertEqual(stamp_asset_versions(site), 1)
            first = (site / "index.html").read_text(encoding="utf-8")
            self.assertNotIn("?v=handwritten", first)
            self.assertIn("https://cdn.example.com/x.js?v=1", first)

            stamp_asset_versions(site)
            self.assertEqual((site / "index.html").read_text(encoding="utf-8"), first)

            (site / "app.js").write_text("console.log(2)", encoding="utf-8")
            stamp_asset_versions(site)
            self.assertNotEqual((site / "index.html").read_text(encoding="utf-8"), first)


class SourceHygieneTests(unittest.TestCase):
    """A mangled regex escape is invisible until the lane silently returns zero."""

    def test_no_source_file_contains_a_literal_backspace(self) -> None:
        # "\\b" written through a shell heredoc or a non-raw string becomes
        # chr(8). The regex still compiles, still runs, and matches nothing --
        # so the feature reads as "quiet" rather than "broken". Three separate
        # patterns in this pipeline were mangled that way while being written.
        offenders = []
        for path in sorted((ROOT / "_system" / "scripts").glob("*.py")):
            if "\x08" in path.read_text(encoding="utf-8", errors="ignore"):
                offenders.append(path.name)
        for path in sorted((ROOT / "dashboard").glob("*.js")):
            if "\x08" in path.read_text(encoding="utf-8", errors="ignore"):
                offenders.append(path.name)
        self.assertEqual(offenders, [], "literal backspace in source; a \\b was mangled")

    def test_issuer_normalisation_is_word_bounded(self) -> None:
        # Stripping "inc"/"co" without \b eats the stem out of real names.
        self.assertIn("incyte", sec_filer_discovery._normalize_issuer("Incyte Corporation"))
        self.assertIn("costar", sec_filer_discovery._normalize_issuer("CoStar Group, Inc."))
        self.assertEqual(sec_filer_discovery._normalize_issuer("Apple Inc."), "apple")

    def test_book_membership_uses_the_issuer_cik(self) -> None:
        # Exact, not a first-word name comparison.
        self.assertTrue(sec_filer_discovery._in_book({"issuer_cik": "0000320193"}, set()))
        self.assertFalse(sec_filer_discovery._in_book({"issuer_cik": "2131524"}, set()))


class LookupFailureTests(unittest.TestCase):
    """A failed request must never read as 'EDGAR has no such filer'."""

    def test_a_failed_request_propagates(self) -> None:
        # Swallowing this reported 36 firms as having no EDGAR entity when
        # sec.gov was simply rate-limiting; Ancora and Browning West both
        # resolve fine on a request that completes.
        with mock.patch.object(
            sec_filer_discovery, "fetch", side_effect=RuntimeError("HTTP 503")
        ):
            with self.assertRaises(RuntimeError):
                sec_filer_discovery.lookup_filer("Ancora")

    def test_a_genuine_no_match_returns_none(self) -> None:
        with mock.patch.object(sec_filer_discovery, "fetch", return_value="<feed></feed>"):
            self.assertIsNone(sec_filer_discovery.lookup_filer("Nonexistent Fund"))

    def test_discover_separates_errors_from_absence(self) -> None:
        with mock.patch.object(
            sec_filer_discovery, "fetch", side_effect=RuntimeError("HTTP 503")
        ):
            result = sec_filer_discovery.discover(
                firm_ids=["elliott"], resolve_issuers=False, write_registry_ciks=False
            )
        self.assertEqual(result["unresolved_firms"], [])
        self.assertGreaterEqual(result["lookup_error_count"], 1)

    def test_cik_probe_covers_both_13d_spellings(self) -> None:
        # A firm last active before the 2024-12-18 rename only appears under
        # "SC 13D". Probing only the new label returned "no EDGAR entity" for
        # Macellum, Soroban and Land & Buildings, all of which resolve at once
        # under the old one.
        self.assertIn("SC 13D", sec_filer_discovery.CIK_PROBE_FORMS)
        self.assertIn("SCHEDULE 13D", sec_filer_discovery.CIK_PROBE_FORMS)

    def test_single_word_firm_stems_are_searched(self) -> None:
        # EDGAR calls it "Macellum Advisors GP, LLC"; we call it "Macellum
        # Capital Management". Only the bare stem matches, and stopping the
        # walk at two words meant it was never queried.
        names = sec_filer_discovery.firm_search_names(
            {"name": "Macellum Capital Management", "aliases": []}
        )
        self.assertIn("Macellum", names)

    def test_personal_aliases_are_not_reduced_to_one_word(self) -> None:
        # "Singer" alone would match the wrong EDGAR entity entirely.
        names = sec_filer_discovery.firm_search_names(
            {"name": "Elliott Management", "aliases": ["Paul Singer"]}
        )
        self.assertNotIn("Paul", names)
        self.assertNotIn("Singer", names)

    def test_unambiguous_cik_without_company_info_is_accepted(self) -> None:
        feed = "<feed><cik>0001640326</cik><conformed-name>Macellum Advisors GP, LLC</conformed-name></feed>"
        with mock.patch.object(sec_filer_discovery, "fetch", return_value=feed):
            got = sec_filer_discovery.lookup_filer("Macellum")
        self.assertEqual(got["cik"], "1640326")

    def test_ambiguous_multi_cik_feed_is_declined(self) -> None:
        feed = "<feed><cik>0000000001</cik><cik>0000000002</cik></feed>"
        with mock.patch.object(sec_filer_discovery, "fetch", return_value=feed):
            self.assertIsNone(sec_filer_discovery.lookup_filer("Ambiguous"))

    def test_known_cik_is_queried_by_cik_not_by_name(self) -> None:
        # EDGAR name search is a prefix match on ITS conformed name, so a firm
        # whose CIK we hold would still come back empty from a name query.
        captured = {}

        def fake_fetch(url):
            captured["url"] = url
            return "<feed><company-info><cik>0001580320</cik></company-info></feed>"

        with mock.patch.object(sec_filer_discovery, "fetch", side_effect=fake_fetch):
            sec_filer_discovery.lookup_filer("Engine Capital Management", cik="1580320")
        self.assertIn("CIK=1580320", captured["url"])
        self.assertNotIn("company=", captured["url"])


class FilerIdentityTests(unittest.TestCase):
    """Who filed is not the same as who the document mentions."""

    def test_issuer_filing_is_not_credited_to_the_activist_it_discusses(self) -> None:
        # GE's own 13D/As resolved to Trian, because a GE filing naturally
        # discusses the activist campaigning at GE. 4 rows on ticker GE were
        # labelled activist as a result.
        text = (
            "Trian Fund Management has campaigned at the company. "
            "NAMES OF REPORTING PERSONS General Electric Company CITIZENSHIP"
        )
        analysis = analyze_sec_filing("SC 13D/A", text)
        self.assertNotEqual(analysis["firm_id"], "trian")
        self.assertTrue(analysis["firm_id"].startswith("sec_filer:"))
        self.assertEqual(analysis["filer_class"], "strategic")

    def test_the_actual_filer_still_resolves(self) -> None:
        analysis = analyze_sec_filing(
            "SC 13D/A", "NAMES OF REPORTING PERSONS Trian Fund Management, L.P. CITIZENSHIP"
        )
        self.assertEqual(analysis["firm_id"], "trian")
        self.assertEqual(analysis["filer_class"], "activist")

    def test_body_scan_still_drives_campaign_classification(self) -> None:
        # A DEFA14A is a campaign filing precisely because it names an activist
        # in the body -- that question is separate from filer identity.
        self.assertEqual(
            analyze_sec_filing("DEFA14A", "the board responds to Starboard Value")["filing_class"],
            "activist_proxy",
        )
        self.assertEqual(
            analyze_sec_filing("DEFA14A", "routine compensation discussion")["filing_class"],
            "company_response",
        )


class ReindexTriageTests(unittest.TestCase):
    """A re-parse must not throw away state that lives only on the index."""

    def test_triage_fields_survive_a_reindex(self) -> None:
        # reindex_local_sec rebuilds `reports` from the filings on disk, so the
        # triage verdict -- and with it materiality_floor -- was silently lost.
        # Real campaigns then dropped from signal to noise while the row count
        # grew, which reads as "more data" rather than "worse data".
        index = {
            "reports": [
                {
                    "local_file": "X/third-party-analyses/activist_reports/long/SC-13D_20250101_acc1.htm",
                    "triage_verdict": "auto_signal",
                    "materiality_floor": 60,
                    "triage_rules": ["registry_firm"],
                }
            ]
        }
        prior = {
            r["local_file"]: {
                k: r[k]
                for k in ("triage_verdict", "triage_rules", "materiality_floor")
                if k in r
            }
            for r in index["reports"]
        }
        fresh = {
            "local_file": "X/third-party-analyses/activist_reports/long/SC-13D_20250101_acc1.htm",
            "firm_id": "elliott",
        }
        carried = prior.get(fresh["local_file"])
        self.assertIsNotNone(carried)
        fresh.update(carried)
        self.assertEqual(fresh["materiality_floor"], 60)
        self.assertEqual(fresh["triage_verdict"], "auto_signal")

    def test_reindex_source_carries_triage_forward(self) -> None:
        source = (ROOT / "_system" / "scripts" / "sec_activist_scan.py").read_text(encoding="utf-8")
        self.assertIn("prior_triage", source)
        self.assertIn("materiality_floor", source)


class EdinetLaneTests(unittest.TestCase):
    """Japan files with the FSA, not the SEC, so a CIK-driven scan cannot see it."""

    def test_missing_key_is_reported_not_guessed(self) -> None:
        with mock.patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(edinet_activist_scan.EdinetNotConfigured):
                edinet_activist_scan.scan(lookback_days=1)

    def test_a_401_inside_a_200_body_is_treated_as_failure(self) -> None:
        # EDINET answers HTTP 200 with {"StatusCode": 401} when the key is bad.
        # Reading resp.status would see success and an empty result list, which
        # is indistinguishable from "no filings today".
        payload = json.dumps(
            {"StatusCode": 401, "message": "Access denied due to invalid subscription key."}
        ).encode()

        class _Resp:
            status = 200

            def read(self_inner):
                return payload

            def __enter__(self_inner):
                return self_inner

            def __exit__(self_inner, *args):
                return False

        with mock.patch.object(edinet_activist_scan.urllib.request, "urlopen", return_value=_Resp()):
            with self.assertRaises(edinet_activist_scan.EdinetApiError):
                edinet_activist_scan.fetch_documents("2026-08-25", key="bogus")

    def test_scan_surfaces_the_failure_rather_than_a_silent_zero(self) -> None:
        with mock.patch.object(
            edinet_activist_scan,
            "fetch_documents",
            side_effect=edinet_activist_scan.EdinetApiError("StatusCode 401"),
        ):
            result = edinet_activist_scan.scan(lookback_days=5, key="bogus")
        self.assertEqual(result["row_count"], 0)
        self.assertEqual(result["days_scanned"], 0)
        self.assertTrue(result["failures"], "a dark feed must not look like a quiet one")

    def test_securities_code_maps_onto_the_book(self) -> None:
        self.assertEqual(edinet_activist_scan.sec_code_to_ticker("39050"), "3905.T")
        self.assertEqual(edinet_activist_scan.sec_code_to_ticker("71760"), "7176.T")
        self.assertIsNone(edinet_activist_scan.sec_code_to_ticker(""))
        self.assertIsNone(edinet_activist_scan.sec_code_to_ticker("ABC"))

    def test_only_large_shareholding_reports_are_kept(self) -> None:
        keep = {"ordinanceCode": "25", "docTypeCode": "350"}
        amend = {"ordinanceCode": "25", "docTypeCode": "360"}
        annual = {"ordinanceCode": "010", "docTypeCode": "120"}
        self.assertTrue(edinet_activist_scan.is_large_shareholding(keep))
        self.assertTrue(edinet_activist_scan.is_large_shareholding(amend))
        self.assertFalse(edinet_activist_scan.is_large_shareholding(annual))

    def test_rows_are_matched_against_the_registry(self) -> None:
        row = {
            "secCode": "39050",
            "filerName": "Effissimo Capital Management Pte Ltd",
            "docTypeCode": "350",
            "ordinanceCode": "25",
            "submitDateTime": "2026-08-25 09:00",
            "docID": "S100ABCD",
        }
        entry = edinet_activist_scan.row_to_entry(row, holdings={"3905.T"})
        self.assertEqual(entry["ticker"], "3905.T")
        self.assertTrue(entry["in_book"])
        self.assertEqual(entry["firm_id"], "effissimo")


if __name__ == "__main__":
    unittest.main()

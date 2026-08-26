#!/usr/bin/env python3
"""Tests for activist coverage: form labels, filer parsing, registry, site filtering.

These guard the failure modes found in the 2026-08-26 coverage audit, all of
which were silent — the pipeline reported healthy while dropping or mislabelling
the thing it exists to collect.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from activist_common import (  # noqa: E402
    ACTIVIST_FORMS,
    active_firms,
    firm_ingest_methods,
    load_firm_registry,
    match_firm_id,
)
from activist_site_fetchers import likely_report  # noqa: E402
from sec_filer_parse import (  # noqa: E402
    analyze_sec_filing,
    classify_sec_filing,
    clean_filer_name,
    form_from_filing_path,
    normalize_form,
    parse_schedule_13_xml,
)

# Trimmed from a live filing (accession 0001889476-26-000004) so the shape is
# real; no network access at test time.
SCHEDULE_13D_XML = """<?xml version="1.0" encoding="UTF-8"?>
<edgarSubmission xmlns="http://www.sec.gov/edgar/schedule13D"
                 xmlns:com="http://www.sec.gov/edgar/common">
  <headerData><submissionType>SCHEDULE 13D</submissionType></headerData>
  <formData>
    <coverPageHeader>
      <dateOfEvent>08/07/2026</dateOfEvent>
      <issuerInfo>
        <issuerCIK>0002131524</issuerCIK>
        <issuerCusips><issuerCusipNumber>10567X101</issuerCusipNumber></issuerCusips>
        <issuerName>Braveheart Bio, Inc.</issuerName>
      </issuerInfo>
    </coverPageHeader>
    <reportingPersons>
      <reportingPersonInfo>
        <reportingPersonCIK>0001889476</reportingPersonCIK>
        <reportingPersonName>Engine Capital Management, LP</reportingPersonName>
        <percentOfClass>11.4</percentOfClass>
      </reportingPersonInfo>
      <reportingPersonInfo>
        <reportingPersonCIK>0001160077</reportingPersonCIK>
        <reportingPersonName>Arnaud Ajdler</reportingPersonName>
        <percentOfClass>9.2</percentOfClass>
      </reportingPersonInfo>
    </reportingPersons>
  </formData>
</edgarSubmission>
"""


class FormLabelTests(unittest.TestCase):
    """EDGAR renamed 13D/G submission types on 2024-12-18 (structured XML)."""

    def test_schedule_spellings_are_accepted_by_the_form_filter(self) -> None:
        # This is the regression that silently blacked out every ownership
        # filing: data.sec.gov reports "SCHEDULE 13D", the filter held only
        # "SC 13D", and the scan skipped the row without logging anything.
        for form in ("SCHEDULE 13D", "SCHEDULE 13D/A", "SCHEDULE 13G", "SCHEDULE 13G/A"):
            self.assertIn(form, ACTIVIST_FORMS, f"{form} must survive the form filter")

    def test_legacy_spellings_still_accepted(self) -> None:
        for form in ("SC 13D", "SC 13D/A", "SC 13G", "SC 13G/A"):
            self.assertIn(form, ACTIVIST_FORMS)

    def test_normalize_collapses_to_canonical_form(self) -> None:
        self.assertEqual(normalize_form("SCHEDULE 13D"), "SC 13D")
        self.assertEqual(normalize_form("SCHEDULE 13D/A"), "SC 13D/A")
        self.assertEqual(normalize_form("schedule 13g"), "SC 13G")
        self.assertEqual(normalize_form("SC 13D"), "SC 13D")
        self.assertEqual(normalize_form("DFAN14A"), "DFAN14A")
        self.assertEqual(normalize_form(None), "")

    def test_renamed_forms_classify_the_same_as_legacy(self) -> None:
        self.assertEqual(classify_sec_filing("SCHEDULE 13D", "", []), "activist_13d")
        self.assertEqual(
            classify_sec_filing("SCHEDULE 13D", "", []),
            classify_sec_filing("SC 13D", "", []),
        )

    def test_dissident_proxy_forms_are_collected(self) -> None:
        for form in ("DEFN14A", "PREN14A", "PX14A6G", "DEFA14A"):
            self.assertIn(form, ACTIVIST_FORMS)
        self.assertEqual(classify_sec_filing("DEFN14A", "", []), "activist_proxy")
        self.assertEqual(classify_sec_filing("PREN14A", "", []), "activist_proxy")

    def test_exempt_solicitation_needs_an_activist_behind_it(self) -> None:
        # Anyone over $5m can file a PX14A6G; without a tracked firm it is not
        # a campaign and must stay out of the feed.
        self.assertEqual(
            classify_sec_filing("PX14A6G", "please vote for the say-on-pay proposal", []),
            "exempt_solicitation",
        )
        self.assertEqual(
            classify_sec_filing("PX14A6G", "Elliott Investment Management urges holders", []),
            "activist_proxy",
        )

    def test_company_response_only_counts_when_it_names_an_activist(self) -> None:
        self.assertEqual(
            classify_sec_filing("DEFA14A", "routine compensation committee discussion", []),
            "company_response",
        )
        self.assertEqual(
            classify_sec_filing("DEFA14A", "the board responds to Starboard Value", []),
            "activist_proxy",
        )


class FilingPathTests(unittest.TestCase):
    """The on-disk layout encodes the form; normalization must not disturb it."""

    def test_amendment_path_round_trips(self) -> None:
        # A renamed "SCHEDULE 13D/A" normalizes to "SC 13D/A", whose "/" puts
        # the file in an SC-13D/ subdirectory as "A_...". Flattening that "/"
        # would make form_from_filing_path read the form back as "SC 13D A".
        self.assertEqual(normalize_form("SCHEDULE 13D/A"), "SC 13D/A")
        stored = normalize_form("SCHEDULE 13D/A").replace(" ", "-")
        path = f"AAOI/third-party-analyses/activist_reports/long/{stored}_20260814_acc0001_26_000004.htm"
        self.assertEqual(form_from_filing_path(path), "SC 13D/A")

    def test_initial_filing_path_round_trips(self) -> None:
        stored = normalize_form("SCHEDULE 13G").replace(" ", "-")
        path = f"AAOI/third-party-analyses/activist_reports/long/{stored}_20260814_acc0001_26_000004.htm"
        self.assertEqual(form_from_filing_path(path), "SC 13G")


class FilerNameTests(unittest.TestCase):
    """Cover-page furniture that ended up stored as firm names."""

    def test_boilerplate_prefix_is_stripped_but_the_name_survives(self) -> None:
        raw = "I.R.S. IDENTIFICATION NOS. OF ABOVE PERSONS (ENTITIES ONLY) Abel Avellan"
        self.assertEqual(clean_filer_name(raw), "Abel Avellan")

    def test_pure_boilerplate_becomes_empty(self) -> None:
        self.assertEqual(clean_filer_name("I.R.S. IDENTIFICATION NO. OF ABOVE PERSON"), "")

    def test_html_entities_are_decoded(self) -> None:
        self.assertEqual(clean_filer_name("BBAI Ultimate Holdings, LLC &#8199"), "BBAI Ultimate Holdings, LLC")
        self.assertEqual(clean_filer_name("Johnson &amp; Johnson"), "Johnson & Johnson")
        self.assertEqual(clean_filer_name("D. E. Shaw &amp"), "D. E. Shaw")

    def test_split_label_artifact_is_stripped(self) -> None:
        self.assertEqual(clean_filer_name("S General Electric Company"), "General Electric Company")
        self.assertEqual(
            clean_filer_name("s: Roman DBDR Tech Sponsor LLC (2)"), "Roman DBDR Tech Sponsor LLC"
        )

    def test_stacked_artifact_and_boilerplate(self) -> None:
        raw = "S I.R.S. IDENTIFICATION NOS. OF ABOVE PERSONS (ENTITIES ONLY) Fairholme Capital Management, L.L.C."
        self.assertTrue(clean_filer_name(raw).startswith("Fairholme Capital Management"))

    def test_trailing_ein_is_dropped(self) -> None:
        raw = "I.R.S. identification nos. of above persons (entities only) Gabelli Funds, LLC I.D. No . 13-4044523"
        self.assertEqual(clean_filer_name(raw), "Gabelli Funds, LLC")

    def test_cleaned_names_resolve_to_registry_firms(self) -> None:
        expected = {
            "I.R.S. identification nos. of above persons (entities only) Gabelli Funds, LLC I.D. No . 13-4044523": "gamco",
            "MANTLE RIDGE LP": "mantle_ridge",
            "Camac Partners, LLC": "camac",
            "Blackwells Capital LLC Jason Aintabi": "blackwells",
            "QVT Financial LP": "qvt",
        }
        for raw, firm_id in expected.items():
            self.assertEqual(match_firm_id(clean_filer_name(raw)), firm_id, raw)


class FirmMatcherTests(unittest.TestCase):
    def test_matching_is_word_bounded(self) -> None:
        # "amber" must not match inside "chamber", "saba" inside "Sabadell".
        self.assertIsNone(match_firm_id("a chamber of commerce filing"))
        self.assertIsNone(match_firm_id("Banco de Sabadell S.A."))
        self.assertIsNone(match_firm_id("engineering services agreement"))

    def test_more_specific_term_wins_over_a_shorter_one(self) -> None:
        self.assertEqual(match_firm_id("Engine Capital Management, LP"), "engine_capital")
        self.assertEqual(match_firm_id("Engine No. 1 LLC"), "engine_no_1")

    def test_japan_and_asia_firms_are_recognised(self) -> None:
        for text, firm_id in (
            ("Effissimo Capital Management Pte Ltd", "effissimo"),
            ("3D Investment Partners Pte. Ltd.", "three_d_investment"),
            ("Nippon Active Value Fund plc", "dalton"),
            ("Palliser Capital", "palliser"),
        ):
            self.assertEqual(match_firm_id(text), firm_id, text)


class ScheduleXmlTests(unittest.TestCase):
    def test_structured_cover_page_is_parsed(self) -> None:
        facts = parse_schedule_13_xml(SCHEDULE_13D_XML)
        self.assertEqual(facts["form"], "SC 13D")
        self.assertEqual(facts["issuer_name"], "Braveheart Bio, Inc.")
        self.assertEqual(facts["issuer_cik"], "2131524")
        self.assertEqual(facts["cusip"], "10567X101")
        self.assertEqual(facts["stake_percent"], 11.4)
        self.assertEqual(
            facts["reporting_persons"], ["Engine Capital Management, LP", "Arnaud Ajdler"]
        )
        self.assertEqual(facts["reporting_person_ciks"], ["1889476", "1160077"])

    def test_non_schedule_payload_returns_empty(self) -> None:
        self.assertEqual(parse_schedule_13_xml("<html><body>not a filing</body></html>"), {})
        self.assertEqual(parse_schedule_13_xml(""), {})

    def test_xml_names_beat_the_cover_page_regexes(self) -> None:
        # Same filing, but the rendered HTML gives up only boilerplate. The
        # structured names must win.
        junk_html = "NAMES OF REPORTING PERSONS I.R.S. IDENTIFICATION NOS. OF ABOVE PERSONS (ENTITIES ONLY)"
        facts = parse_schedule_13_xml(SCHEDULE_13D_XML)
        analysis = analyze_sec_filing("SCHEDULE 13D", junk_html, xml_facts=facts)
        self.assertEqual(analysis["firm_id"], "engine_capital")
        self.assertEqual(analysis["filer_resolution"], "registry_xml")
        self.assertGreaterEqual(analysis["confidence"], 0.97)

    def test_html_path_still_used_when_no_xml(self) -> None:
        analysis = analyze_sec_filing("SC 13D", "NAMES OF REPORTING PERSONS Starboard Value LP CITIZENSHIP")
        self.assertEqual(analysis["firm_id"], "starboard")


class SiteLinkFilterTests(unittest.TestCase):
    """The publisher lane counted navigation chrome as reports."""

    def test_navigation_chrome_is_rejected(self) -> None:
        chrome = [
            ("https://elliottmgmt.com/who-we-are/", "Who We Are", "elliottmgmt.com"),
            ("https://thirdpoint.com/investment-strategy/", "Investment Strategy", "thirdpoint.com"),
            ("https://cevian.com/values/", "Values", "cevian.com"),
            ("https://valueact.com/terms-of-use/", "Terms of Use", "valueact.com"),
            ("https://www.starboardvalue.com/biographies/jeffrey-smith/", "Jeff Smith", "starboardvalue.com"),
            ("https://deshaw.com/who-we-are/leadership", "Leadership", "deshaw.com"),
        ]
        for url, title, domain in chrome:
            self.assertFalse(likely_report(url, title, domain), url)

    def test_real_publications_are_kept(self) -> None:
        real = [
            ("https://carlicahn.com/open-letter-to-shareholders-of-illumina-inc-13/", "open letter", "carlicahn.com"),
            ("https://www.starboardvalue.com/presentations/", "Presentations", "starboardvalue.com"),
            ("https://deshaw.com/assets/articles/D_E_Shaw_Group_Diopter_Fund_II.pdf", "Press Release", "deshaw.com"),
            ("https://muddywatersresearch.com/research/xyz/mw-is-short-xyz/", "MW is Short XYZ", "muddywatersresearch.com"),
        ]
        for url, title, domain in real:
            self.assertTrue(likely_report(url, title, domain), url)

    def test_parked_domains_are_rejected(self) -> None:
        # icebergresearch.com became a HugeDomains sales page; its links must
        # never enter the feed.
        self.assertFalse(
            likely_report("https://www.hugeDomains.com/index.cfm", "index.cfm", "icebergresearch.com")
        )


class RegistryIntegrityTests(unittest.TestCase):
    def test_ids_are_unique(self) -> None:
        firms = load_firm_registry().get("firms") or []
        ids = [f.get("id") for f in firms]
        self.assertEqual(len(ids), len(set(ids)), "duplicate firm ids in the registry")

    def test_every_firm_has_the_required_fields(self) -> None:
        for firm in load_firm_registry().get("firms") or []:
            for key in ("id", "name", "side", "tier"):
                self.assertTrue(firm.get(key) not in (None, ""), f"{firm.get('id')} missing {key}")
            self.assertIn(firm["side"], {"long", "short", "both"}, firm["id"])

    def test_site_index_firms_have_somewhere_to_fetch_from(self) -> None:
        for firm in active_firms():
            if "site_index" in firm_ingest_methods(firm):
                self.assertTrue(
                    firm.get("domains") or firm.get("rss_urls"),
                    f"{firm['id']} has site_index but no domains/rss_urls",
                )

    def test_league_table_firms_are_present(self) -> None:
        # The activists that ran the most campaigns in 2025 (Barclays 2025
        # Review of Shareholder Activism). Their absence was the coverage gap.
        ids = {f.get("id") for f in load_firm_registry().get("firms") or []}
        for firm_id in (
            "elliott", "starboard", "engine_capital", "holdco", "murakami",
            "palliser", "dalton", "strategic_capital", "irenic", "engaged",
            "oasis", "ananym", "ancora", "land_buildings", "valueact",
        ):
            self.assertIn(firm_id, ids, f"{firm_id} missing from the registry")

    def test_wound_down_firms_are_marked_inactive(self) -> None:
        by_id = {f.get("id"): f for f in load_firm_registry().get("firms") or []}
        for firm_id in ("hindenburg", "inclusive", "citron"):
            firm = by_id.get(firm_id)
            self.assertIsNotNone(firm, firm_id)
            self.assertFalse(firm.get("active", True), f"{firm_id} should be inactive")

    def test_registry_is_valid_json_with_stable_shape(self) -> None:
        path = ROOT / "_system" / "frameworks" / "activist_firm_registry.json"
        doc = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(doc.get("schema_version"), 2)
        self.assertIsInstance(doc.get("firms"), list)
        self.assertGreater(len(doc["firms"]), 100)


if __name__ == "__main__":
    unittest.main()

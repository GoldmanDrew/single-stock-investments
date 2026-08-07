"""Tests for the SSI pipeline v2 upgrades: comparability promotion,
line-preserving HTML extraction, XBRL series, boilerplate guard, section
sinks, extended taxonomy routing, XBRL spawner, buyback-authorization
ledger, and the Phase 4 report renderer + shipping gate."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import build_filing_evidence as bfe  # noqa: E402
import build_ssi_evidence_pack as pack_mod  # noqa: E402
import build_ssi_claims as claims_mod  # noqa: E402
import build_ssi_report as report_mod  # noqa: E402
import verify_ssi_claims as verify_mod  # noqa: E402


# ---------------------------------------------------------------------------
# build_filing_evidence: comparability promotion + line-preserving extraction
# ---------------------------------------------------------------------------

def _doc(kind: str, file_date: str, tier: str = "partial", score: int = 95) -> dict:
    return {
        "kind": kind, "file_date": file_date, "tier": tier, "score": score,
        "filename": f"{kind}_{file_date}.htm", "path": f"x/{kind}_{file_date}.htm",
    }


def test_promote_comparables_chains_two_prior_years():
    docs = [
        _doc("10-K", "2026-02-25", tier="full"),
        _doc("10-K", "2025-03-03"),
        _doc("10-K", "2024-02-29"),
        _doc("10-K", "2023-03-01"),  # beyond chain depth 2 — stays partial
    ]
    promoted = bfe.promote_comparables(docs)
    assert [d["file_date"] for d in promoted] == ["2025-03-03", "2024-02-29"]
    assert docs[1]["tier"] == "full" and docs[2]["tier"] == "full"
    assert docs[3]["tier"] == "partial"


def test_promote_comparables_quarterly_same_quarter():
    docs = [
        _doc("10-Q", "2026-05-06", tier="full"),
        _doc("10-Q", "2026-02-06"),  # sequential quarter: 89d — outside window
        _doc("10-Q", "2025-05-08"),  # prior-year same quarter — promoted
    ]
    promoted = bfe.promote_comparables(docs)
    assert [d["file_date"] for d in promoted] == ["2025-05-08"]
    assert docs[1]["tier"] == "partial"


def test_promote_comparables_no_anchor_no_promotion():
    docs = [_doc("10-K", "2026-02-25"), _doc("10-K", "2025-03-03")]
    assert bfe.promote_comparables(docs) == []


def test_strip_html_preserves_block_lines_and_entities():
    html = (
        "<div>Item 1A. Risk Factors</div>"
        "<p>We received a subpoena&nbsp;in Q2 &#8212; material.</p>"
        "<table><tr><td>Revenues</td></tr></table>"
    )
    out = bfe._strip_html_keep_lines(html)
    lines = out.splitlines()
    assert lines[0] == "Item 1A. Risk Factors"
    assert "subpoena in Q2 -- material." in lines[1]
    assert len(lines) == 3


# ---------------------------------------------------------------------------
# Evidence pack: XBRL series, boilerplate guard, section sinks
# ---------------------------------------------------------------------------

def _ticker(tmp_path: Path, name: str = "TEST") -> Path:
    ticker_dir = tmp_path / name
    (ticker_dir / "research" / "evidence").mkdir(parents=True)
    return ticker_dir


def _write_companyfacts(ticker_dir: Path) -> None:
    facts = {
        "cik": 1234,
        "entityName": "TEST CO",
        "facts": {
            "dei": {
                "EntityCommonStockSharesOutstanding": {"units": {"shares": [
                    {"end": "2024-02-01", "val": 110, "fy": 2023, "fp": "FY", "form": "10-K", "accn": "a1", "filed": "2024-02-15"},
                    {"end": "2025-02-01", "val": 100, "fy": 2024, "fp": "FY", "form": "10-K", "accn": "a2", "filed": "2025-02-15"},
                    {"end": "2026-02-01", "val": 90, "fy": 2025, "fp": "FY", "form": "10-K", "accn": "a3", "filed": "2026-02-15"},
                ]}},
            },
            "us-gaap": {
                "Revenues": {"units": {"USD": [
                    # restated FY2024: two filings, different values
                    {"start": "2024-01-01", "end": "2024-12-31", "val": 900, "fy": 2024, "fp": "FY", "form": "10-K", "accn": "a2", "filed": "2025-02-15"},
                    {"start": "2024-01-01", "end": "2024-12-31", "val": 905, "fy": 2025, "fp": "FY", "form": "10-K", "accn": "a3", "filed": "2026-02-15"},
                    {"start": "2025-01-01", "end": "2025-12-31", "val": 1000, "fy": 2025, "fp": "FY", "form": "10-K", "accn": "a3", "filed": "2026-02-15"},
                    # YTD 6-month frame must NOT count as quarterly
                    {"start": "2025-01-01", "end": "2025-06-30", "val": 480, "fy": 2025, "fp": "Q2", "form": "10-Q", "accn": "q2", "filed": "2025-08-01"},
                    # true ~90-day quarterly frame
                    {"start": "2025-01-01", "end": "2025-03-31", "val": 240, "fy": 2025, "fp": "Q1", "form": "10-Q", "accn": "q1", "filed": "2025-05-01"},
                ]}},
                "NetCashProvidedByUsedInOperatingActivities": {"units": {"USD": [
                    {"start": "2025-01-01", "end": "2025-12-31", "val": 300, "fy": 2025, "fp": "FY", "form": "10-K", "accn": "a3", "filed": "2026-02-15"},
                ]}},
                "PaymentsToAcquirePropertyPlantAndEquipment": {"units": {"USD": [
                    {"start": "2025-01-01", "end": "2025-12-31", "val": 90, "fy": 2025, "fp": "FY", "form": "10-K", "accn": "a3", "filed": "2026-02-15"},
                ]}},
            },
        },
    }
    (ticker_dir / "research" / "evidence" / "sec_companyfacts.json").write_text(
        json.dumps(facts), encoding="utf-8"
    )


def test_xbrl_series_dedupe_restates_and_duration_filter(tmp_path):
    ticker_dir = _ticker(tmp_path)
    _write_companyfacts(ticker_dir)
    series = pack_mod.xbrl_fact_series(ticker_dir)
    assert series["available"] is True
    rev = series["concepts"]["revenue"]
    annual_2024 = [r for r in rev["annual"] if r["end"] == "2024-12-31"][0]
    assert annual_2024["val"] == 905  # latest filed wins
    assert annual_2024["restated"] == 2
    assert annual_2024["first_reported"] == 900
    assert [r["end"] for r in rev["quarterly"]] == ["2025-03-31"]  # YTD frame excluded
    shares = series["concepts"]["shares_outstanding"]
    assert [r["val"] for r in shares["annual"]] == [110, 100, 90]


def test_boilerplate_guard_and_severity_windows(tmp_path):
    ticker_dir = _ticker(tmp_path)
    text_dir = ticker_dir / "research" / "evidence" / "_text"
    text_dir.mkdir(parents=True)
    prior = "Risk Factors\nOld line about the business.\n"
    filler = "x" * 260
    current = (
        "Risk Factors\n"
        "In the event of default, the lenders may accelerate the notes.\n"  # boilerplate
        "Defaults Upon Senior Securit ies\n"  # sink heading (kerned)
        "Risk Factors\n"
        f"{filler} we identified a material weakness in internal controls.\n"  # real, keyword past char 260
    )
    (text_dir / "10-K_20260225_rpt20251231_acc1.htm.txt").write_text(current, encoding="utf-8")
    (text_dir / "10-K_20250303_rpt20241231_acc2.htm.txt").write_text(prior, encoding="utf-8")
    pack = pack_mod.build_evidence_pack(ticker_dir, "2026-08-06")
    sections = pack["comparisons"][0]["section_diff"]["sections"]
    rf = sections["risk_factors"]
    assert rf["severity_keywords_added"] == ["material weakness"]
    assert "default" in rf["severity_keywords_boilerplate"]
    # window keeps the keyword inside the stored snippet
    assert any("material weakness" in line for line in rf["severity_lines_added"])


# ---------------------------------------------------------------------------
# Claims: extended routing, XBRL spawner, buyback authorizations
# ---------------------------------------------------------------------------

def test_extended_taxonomy_routing():
    assert claims_mod._route_taxonomy("Revenues") == "operating_failure"
    assert claims_mod._route_taxonomy("DeferredIncomeTaxExpenseBenefit") == "earnings_quality"
    assert claims_mod._route_taxonomy("PaymentsForRepurchaseOfCommonStock") == "identity_instrument"
    assert claims_mod._route_taxonomy("ProceedsFromIssuanceOfLongTermDebt") == "liquidity_oxygen"
    # core rules unchanged
    assert claims_mod._route_taxonomy("GoodwillImpairment") == "operating_failure"
    assert claims_mod._route_taxonomy("AllowanceForCreditLoss") == "earnings_quality"


def test_compliance_affirmation_is_not_a_default_event(tmp_path):
    """"we were in compliance with all covenants and provisions related to
    potential defaults" is the OPPOSITE of an event; posting it as severity-5
    destroys top-alert precision."""
    ticker_dir = _ticker(tmp_path, "COMPLY")
    text_dir = ticker_dir / "research" / "evidence" / "_text"
    text_dir.mkdir(parents=True)
    prior = "Liquidity and Covenants\nPrior period language about the facility.\n"
    # Must exceed the 160-char heading cutoff, or the line is parsed as a
    # section heading rather than content — as the real ALB line was.
    current = (
        "Liquidity and Covenants\n"
        "As of March 31, 2026, after giving effect to the amended revolving credit "
        "facility and the related term loan, we were in compliance with all existing "
        "debt covenants and provisions related to potential defaults.\n"
    )
    (text_dir / "10-K_20260225_rpt20251231_acc1.htm.txt").write_text(current, encoding="utf-8")
    (text_dir / "10-K_20250303_rpt20241231_acc2.htm.txt").write_text(prior, encoding="utf-8")
    pack = pack_mod.build_evidence_pack(ticker_dir, "2026-08-06")
    section = pack["comparisons"][0]["section_diff"]["sections"]["liquidity_covenants"]
    assert section["severity_keywords_added"] == []
    assert "default" in section["severity_keywords_boilerplate"]


def test_implausible_ratio_flagged_and_severity_capped(tmp_path):
    """340 -> 277,400 on the same tag is a scope mismatch, not a +81,489% move."""
    ticker_dir = _ticker(tmp_path, "RATIO")
    text_dir = ticker_dir / "research" / "evidence" / "_text"
    text_dir.mkdir(parents=True)
    (text_dir / "10-K_20260225_rpt20251231_acc1.htm.txt").write_text(
        "NetIncomeLoss: 277,400\nNetIncomeLoss: 100\n", encoding="utf-8")
    (text_dir / "10-K_20250303_rpt20241231_acc2.htm.txt").write_text(
        "NetIncomeLoss: 340\nNetIncomeLoss: 90\n", encoding="utf-8")
    pack = pack_mod.build_evidence_pack(ticker_dir, "2026-08-06")
    row = next(r for r in pack["comparisons"][0]["fact_deltas"]["rows"]
               if r["tag"] == "NetIncomeLoss")
    assert "implausible_ratio" in row["flags"]
    assert claims_mod._severity_for_delta("operating_failure", row) <= claims_mod.FOOTNOTE_SEVERITY_CAP
    assert claims_mod._confidence_for_row(row) == "low"


def test_concept_tiering_caps_footnote_severity():
    assert claims_mod.tag_tier("Revenues") == "primary"
    assert claims_mod.tag_tier("CashAndCashEquivalentsAtCarryingValue") == "primary"
    assert claims_mod.tag_tier("OtherComprehensiveIncomeLossNetOfTax") == "footnote_detail"
    assert claims_mod.tag_tier("DeferredStateAndLocalIncomeTaxExpenseBenefit") == "footnote_detail"
    assert claims_mod.tag_tier("SomeUnknownVendorTag") == "secondary"

    # A +1900% footnote swing must not outrank real economics.
    footnote = {"tag": "DeferredStateAndLocalIncomeTaxExpenseBenefit", "pct": 1962.0,
                "flags": ["extreme_move"]}
    primary = {"tag": "Revenues", "pct": 120.0, "flags": ["extreme_move"]}
    assert claims_mod._severity_for_delta("earnings_quality", footnote) <= claims_mod.FOOTNOTE_SEVERITY_CAP
    assert claims_mod._severity_for_delta("operating_failure", primary) == 4
    assert (claims_mod._severity_for_delta("operating_failure", primary)
            > claims_mod._severity_for_delta("earnings_quality", footnote))


def test_variant_section_excludes_footnote_detail():
    claims = [
        {"statement": "OCI blew up", "direction": "up", "severity": 4,
         "concept_tier": "footnote_detail", "taxonomy": "earnings_quality"},
        {"statement": "Revenues rose", "direction": "up", "severity": 4,
         "concept_tier": "primary", "taxonomy": "operating_failure"},
    ]
    text = "\n".join(report_mod.variant_section(claims, None))
    assert "Revenues rose" in text
    assert "OCI blew up" not in text


def test_exec_summary_leads_with_severity5_section_claim():
    """A sev-5 section claim has no concept_tier; it must still lead."""
    claims = [
        {"statement": "Revenues rose", "direction": "up", "severity": 4,
         "concept_tier": "primary", "taxonomy": "operating_failure", "confidence": "high"},
        {"statement": "New 'material weakness' language added", "direction": "new",
         "severity": 5, "taxonomy": "earnings_quality", "confidence": "high"},
    ]
    text = "\n".join(report_mod.executive_summary(
        claims, {}, {"contract_status": "missing"}, None, None, {"filings": []}))
    matters = text.split("**What matters most.**")[1]
    assert matters.index("material weakness") < matters.index("Revenues rose")


def test_spawner_from_xbrl_series(tmp_path):
    ticker_dir = _ticker(tmp_path)
    _write_companyfacts(ticker_dir)
    series = pack_mod.xbrl_fact_series(ticker_dir)
    pack = {"pack_hash": "h" * 64, "xbrl_series": series}
    block = claims_mod.spawner_scores(pack, ticker_dir / "research" / "evidence")
    assert block["basis"] == "xbrl_series"
    bt = block["components"]["buyback_trajectory"]
    assert bt["read"] == "shrinking"
    assert bt["years_observed"] == 3
    ci = block["components"]["capex_intensity"]
    assert ci["capex_to_ocf"] == 0.3
    assert "small_bet_discipline:requires_segment_history" in block["abstentions"]


def test_buyback_scanner_rejects_xbrl_metadata_lines(tmp_path):
    """An XBRL context row can carry both a dollar figure and 'repurchase'
    (from a tag name); citing it would point at metadata, not a resolution."""
    ticker_dir = _ticker(tmp_path, "META")
    text_dir = ticker_dir / "research" / "evidence" / "_text"
    text_dir.mkdir(parents=True)
    junk = (
        "nvda-20260426 0001045810 1/31 2027 Q1 FALSE "
        "http://fasb.org/us-gaap/2025#AccruedLiabilitiesCurrent 5 "
        "authorized repurchase $38,500\n"
    )
    name = "10-K_20260225_rpt20251231_acc1.htm.txt"
    (text_dir / name).write_text(junk, encoding="utf-8")
    pack = {
        "filings": [{
            "path": f"{ticker_dir.name}/research/evidence/_text/{name}",
            "form_class": "annual", "file_date": "2026-02-25", "sha256": "s" * 64,
        }],
        "pack_hash": "h" * 64, "xbrl_series": {"available": False},
    }
    assert claims_mod.buyback_authorization_promises(
        pack, ticker_dir / "research" / "evidence") == []
    assert claims_mod._looks_like_prose(
        "On July 7, 2025, the Board authorized the repurchase of up to $300.0 million of stock."
    ) is True


def test_ledger_accepts_management_facts_schema_and_splits_qualitative(tmp_path):
    """build_management_evidence emits {id, excerpt, source, file_date};
    numberless statements must not be counted as pending promises."""
    ticker_dir = _ticker(tmp_path, "LEDG")
    evidence_dir = ticker_dir / "research" / "evidence"
    (evidence_dir / "management_facts_2026-07-09.json").write_text(json.dumps({
        "ticker": "LEDG", "claims": [
            {"id": "production_timing", "excerpt": "We remain on track to commence production.",
             "source": "investor-documents/transcripts/x.pdf", "file_date": "2026-05-20",
             "epistemic_tier": "management_statement"},
            {"id": "buyback", "excerpt": "We expect to return $1.5 billion to shareholders.",
             "source": "investor-documents/transcripts/y.pdf", "file_date": "2026-02-25",
             "epistemic_tier": "management_statement"},
        ],
    }), encoding="utf-8")
    pack = {"pack_hash": "h" * 64, "filings": [], "xbrl_series": {"available": False}}
    ledger = claims_mod.management_ledger(pack, evidence_dir, "2026-08-06")
    assert ledger["promise_count"] == 1        # only the $1.5B statement is scoreable
    assert ledger["statement_count"] == 1
    quant = [r for r in ledger["rows"] if r["status"] != "qualitative_statement"][0]
    assert quant["promised_value"] == 1.5e9
    assert quant["date_made"] == "2026-02-25"
    qual = [r for r in ledger["rows"] if r["status"] == "qualitative_statement"][0]
    assert qual["promise"].startswith("We remain on track")


def test_buyback_authorization_scanner(tmp_path):
    ticker_dir = _ticker(tmp_path)
    text_dir = ticker_dir / "research" / "evidence" / "_text"
    text_dir.mkdir(parents=True)
    body = (
        "Revenues: 100\n"
        "On July 7, 2025, the Board authorized the repurchase of up to $300.0 million of common stock.\n"
    )
    name = "10-K_20260225_rpt20251231_acc1.htm.txt"
    (text_dir / name).write_text(body, encoding="utf-8")
    pack = {
        "filings": [{
            "path": f"{ticker_dir.name}/research/evidence/_text/{name}",
            "form_class": "annual", "file_date": "2026-02-25", "sha256": "s" * 64,
        }],
        "pack_hash": "h" * 64,
        "xbrl_series": {"available": False},
    }
    # base dir for rel paths is the ticker's parent
    rows = claims_mod.buyback_authorization_promises(pack, ticker_dir / "research" / "evidence")
    assert len(rows) == 1
    assert rows[0]["promised_value"] == 300_000_000.0
    assert rows[0]["status"] == "open_authorization"
    assert rows[0]["source_ref"]["line"] == 2


# ---------------------------------------------------------------------------
# Phase 4: report + shipping gate (end-to-end on a tmp ticker)
# ---------------------------------------------------------------------------

CURRENT_10K = """Assets: 1,000,000
Assets: 900,000
Revenues: 500,000
Revenues: 400,000
AllowanceForCreditLoss: 66,000
AllowanceForCreditLoss: 44,000
Risk Factors
We identified a material weakness in our internal control over financial reporting.
"""

PRIOR_10K = """Assets: 900,000
Assets: 850,000
Revenues: 400,000
Revenues: 350,000
AllowanceForCreditLoss: 44,000
AllowanceForCreditLoss: 40,000
Risk Factors
Ordinary risk language.
"""


def test_report_end_to_end(tmp_path, monkeypatch):
    ticker_dir = _ticker(tmp_path, "RPT")
    text_dir = ticker_dir / "research" / "evidence" / "_text"
    text_dir.mkdir(parents=True, exist_ok=True)
    (text_dir / "10-K_20260225_rpt20251231_acc1.htm.txt").write_text(CURRENT_10K, encoding="utf-8")
    (text_dir / "10-K_20250303_rpt20241231_acc2.htm.txt").write_text(PRIOR_10K, encoding="utf-8")
    _write_companyfacts(ticker_dir)

    as_of = "2026-08-06"
    pack_mod.write_evidence_pack(ticker_dir, as_of)
    claims_mod.write_claims(ticker_dir, as_of)
    gold = tmp_path / "gold.jsonl"
    result = verify_mod.verify_ticker(ticker_dir, as_of, gold_path=gold)
    evidence_dir = ticker_dir / "research" / "evidence"
    snapshot = result.pop("time_zero")
    (evidence_dir / f"ssi_verified_claims_{as_of}.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8")
    (evidence_dir / f"ssi_time_zero_{as_of}.json").write_text(
        json.dumps(snapshot, indent=2), encoding="utf-8")

    outs = report_mod.write_report(ticker_dir, as_of)
    assert outs is not None
    report_path, gate_path = outs
    text = report_path.read_text(encoding="utf-8")

    # §4 output-contract skeleton present
    for heading in (
        "## 1. Header stat block", "## 2. Executive summary", "## 5. Historical KPIs",
        "## 7. Valuation & priced-in scenarios", "## 13. Falsification framework",
        "## 14. Source quality",
    ):
        assert heading in text, heading
    # honesty: restated flag from the fixture surfaces
    assert "restated" in text
    # no contract → no value figures; status stated instead
    assert "no value or return" in text or "decision_grade" in text

    gate = json.loads(gate_path.read_text(encoding="utf-8"))
    names = {c["name"] for c in gate["checks"]}
    assert {"locator_resolution", "comparability_gate", "consensus_reconciliation",
            "valuation_contract_only", "valuation_contract_decision_grade",
            "time_zero_snapshot"} <= names
    consensus = next(c for c in gate["checks"] if c["name"] == "consensus_reconciliation")
    assert consensus["verdict"] == "BLOCKED"
    # This minimal fixture still trips falsification_quantified (too few
    # tripwires), so the overall verdict stays NOT SHIPPABLE for that reason —
    # what matters here is that the valuation checks no longer contribute to it.
    assert gate["result"] in ("NOT SHIPPABLE", "DRAFT (blocked)")
    # An absent upstream contract is missing input, not a defect in this run: the
    # renderer quoted no figures, so discipline passes and availability blocks.
    verdicts = {c["name"]: c["verdict"] for c in gate["checks"]}
    assert verdicts["valuation_contract_only"] == "PASS"
    assert verdicts["valuation_contract_decision_grade"] == "BLOCKED"


def _gate(authority: dict, body: str, tmp_path: Path) -> dict:
    """Gate over a fixture where every non-valuation check passes, so the result
    is driven only by the valuation checks under test."""
    as_of = "2026-08-06"
    (tmp_path / f"ssi_time_zero_{as_of}.json").write_text("{}", encoding="utf-8")
    pack = {"comparisons": [{"gate": {"matched": True}}], "pack_hash": "h" * 64}
    verified = {
        "verified_count": 6, "failed_count": 0, "gold_cases_appended": 0,
        "verified_claims": [{"severity": 4, "falsifier": "re-derive"} for _ in range(6)],
    }
    return report_mod.shipping_gate(pack, verified, authority, tmp_path,
                                    as_of, report_body=body)


def _verdict(gate: dict, name: str) -> str:
    return next(c["verdict"] for c in gate["checks"] if c["name"] == name)


def test_non_decision_grade_contract_blocks_rather_than_fails(tmp_path):
    """The renderer quoting nothing on a non-decision-grade contract is correct
    behaviour, so it must not be reported as a failure of this run."""
    gate = _gate({"authority_level": "contract", "contract_status": "evidence_blocked"},
                 body="Contract is `evidence_blocked` — no value or return figures are quotable.",
                 tmp_path=tmp_path)
    assert _verdict(gate, "valuation_contract_only") == "PASS"
    assert _verdict(gate, "valuation_contract_decision_grade") == "BLOCKED"
    assert gate["result"] == "DRAFT (blocked)"


def test_decision_grade_contract_passes_both_valuation_checks(tmp_path):
    gate = _gate({"authority_level": "contract", "contract_status": "decision_grade"},
                 body="Contract value/share 80.00–87.00–141.93 (low–base–high)",
                 tmp_path=tmp_path)
    assert _verdict(gate, "valuation_contract_only") == "PASS"
    assert _verdict(gate, "valuation_contract_decision_grade") == "PASS"


def test_value_figures_without_decision_grade_is_a_real_failure(tmp_path):
    """The discipline check must still catch an actual one-valuation-language
    breach — figures rendered while the contract is not decision_grade."""
    gate = _gate({"authority_level": "legacy", "contract_status": "evidence_blocked"},
                 body="| Scenario | Value / share | vs price | Implied return |",
                 tmp_path=tmp_path)
    assert _verdict(gate, "valuation_contract_only") == "FAIL"
    assert gate["result"] == "NOT SHIPPABLE"


def test_unresolved_authority_is_a_failure_not_a_block(tmp_path):
    gate = _gate({"authority_level": "unresolved", "contract_status": "missing",
                  "error": "boom"}, body="", tmp_path=tmp_path)
    assert _verdict(gate, "valuation_contract_only") == "FAIL"


@pytest.mark.parametrize("tag", [
    "LongTermDebtMaturitiesRepaymentsOfPrincipalInNextTwelveMonths",
    "LongTermDebtMaturitiesRepaymentsOfPrincipalInYearTwo",
    "LongTermDebtMaturitiesRepaymentsOfPrincipalAfterYearFive",
    "LesseeOperatingLeaseLiabilityPaymentsDueInYearThree",
    "FinanceLeaseLiabilityPaymentsDueThereafter",
    "ContractualObligationDueInNextTwelveMonths",
])
def test_maturity_schedule_buckets_are_footnote_detail(tag):
    """Debt rolling from 'year two' into 'next twelve months' produces a
    -100%/+100% pair every year with no change in the total obligation."""
    assert claims_mod.tag_tier(tag) == "footnote_detail"


@pytest.mark.parametrize("tag", [
    "LongTermDebt", "LongTermDebtNoncurrent", "LongTermDebtCurrent",
    "DebtInstrumentCarryingAmount", "ShortTermBorrowings",
])
def test_aggregate_debt_tags_stay_primary(tag):
    assert claims_mod.tag_tier(tag) == "primary"


def test_maturity_bucket_severity_is_capped():
    row = {"tag": "LongTermDebtMaturitiesRepaymentsOfPrincipalInYearTwo",
           "pct": -100.0, "flags": ["extreme_move", "sign_flip"]}
    assert claims_mod._severity_for_delta("liquidity_oxygen", row) \
        <= claims_mod.FOOTNOTE_SEVERITY_CAP


def _gate_raw(pack: dict, verified: dict, tmp_path: Path) -> dict:
    as_of = "2026-08-06"
    (tmp_path / f"ssi_time_zero_{as_of}.json").write_text("{}", encoding="utf-8")
    authority = {"authority_level": "contract", "contract_status": "decision_grade"}
    return report_mod.shipping_gate(pack, verified, authority, tmp_path, as_of,
                                    report_body="Contract value/share 10.15")


def test_newly_public_issuer_blocks_rather_than_fails(tmp_path):
    """No prior-period filing means the claim engine correctly emits nothing.
    That is a missing input, not a defect in this run (e.g. WHK, IPO'd
    2026-06-10 with only a 424B4 on file)."""
    gate = _gate_raw({"comparisons": [], "pack_hash": "h" * 64},
                     {"verified_count": 0, "failed_count": 0, "gold_cases_appended": 0,
                      "verified_claims": []}, tmp_path)
    v = {c["name"]: c["verdict"] for c in gate["checks"]}
    assert v["locator_resolution"] == "BLOCKED"
    assert v["comparability_gate"] == "BLOCKED"
    assert v["falsification_quantified"] == "BLOCKED"
    assert gate["result"] == "DRAFT (blocked)"


def test_comparisons_present_but_no_claims_is_still_a_failure(tmp_path):
    """NVO's shape: comparisons exist, yet nothing came back. That is a real
    defect and must not be softened by the newly-public carve-out."""
    gate = _gate_raw({"comparisons": [{"gate": {"matched": True}}], "pack_hash": "h" * 64},
                     {"verified_count": 0, "failed_count": 0, "gold_cases_appended": 0,
                      "verified_claims": []}, tmp_path)
    v = {c["name"]: c["verdict"] for c in gate["checks"]}
    assert v["locator_resolution"] == "FAIL"
    assert gate["result"] == "NOT SHIPPABLE"


def test_claims_that_all_fail_verification_stay_a_failure(tmp_path):
    """NVDA's shape: 129 claims, all failing."""
    gate = _gate_raw({"comparisons": [{"gate": {"matched": True}}], "pack_hash": "h" * 64},
                     {"verified_count": 0, "failed_count": 129, "gold_cases_appended": 129,
                      "verified_claims": []}, tmp_path)
    v = {c["name"]: c["verdict"] for c in gate["checks"]}
    assert v["locator_resolution"] == "FAIL"


def _claims_fixture(tmp_path) -> tuple[Path, str]:
    """Ticker taken through Phases 1-2, ready to verify."""
    ticker_dir = _ticker(tmp_path, "CMP")
    text_dir = ticker_dir / "research" / "evidence" / "_text"
    text_dir.mkdir(parents=True, exist_ok=True)
    (text_dir / "10-K_20260225_rpt20251231_acc1.htm.txt").write_text(CURRENT_10K, encoding="utf-8")
    (text_dir / "10-K_20250303_rpt20241231_acc2.htm.txt").write_text(PRIOR_10K, encoding="utf-8")
    _write_companyfacts(ticker_dir)
    as_of = "2026-08-06"
    pack_mod.write_evidence_pack(ticker_dir, as_of)
    claims_mod.write_claims(ticker_dir, as_of)
    return ticker_dir, as_of


def test_verification_compacts_claims_array_but_keeps_phase2_only_content(tmp_path):
    ticker_dir, as_of = _claims_fixture(tmp_path)
    claims_path = ticker_dir / "research" / "evidence" / f"ssi_claims_{as_of}.json"
    before = json.loads(claims_path.read_text(encoding="utf-8"))
    assert before["claims"], "fixture must produce claims"

    result = verify_mod.verify_ticker(ticker_dir, as_of, gold_path=tmp_path / "g.jsonl")
    after = json.loads(claims_path.read_text(encoding="utf-8"))

    # the array is gone ...
    assert "claims" not in after
    assert after["claims_compacted"] is True
    # ... but Phase-2-only content survives, since Phase 4 reads it
    for key in ("management_ledger", "spawner", "concept_tier_histogram",
                "severity_histogram", "claim_count"):
        assert key in after, key
    # ... and every claim body survives in the verified doc
    assert {c["claim_id"] for c in result["verified_claims"]} \
        <= {c["claim_id"] for c in before["claims"]}


def test_time_zero_hash_matches_the_file_left_on_disk(tmp_path):
    """The snapshot must hash the compacted file, not the pre-compaction one."""
    import hashlib
    ticker_dir, as_of = _claims_fixture(tmp_path)
    result = verify_mod.verify_ticker(ticker_dir, as_of, gold_path=tmp_path / "g.jsonl")
    claims_path = ticker_dir / "research" / "evidence" / f"ssi_claims_{as_of}.json"
    on_disk = hashlib.sha256(claims_path.read_bytes()).hexdigest()
    assert result["time_zero"]["claims_file_sha256"] == on_disk


def test_reverifying_a_compacted_file_fails_loudly(tmp_path):
    ticker_dir, as_of = _claims_fixture(tmp_path)
    verify_mod.verify_ticker(ticker_dir, as_of, gold_path=tmp_path / "g.jsonl")
    with pytest.raises(ValueError, match="re-run build_ssi_claims"):
        verify_mod.verify_ticker(ticker_dir, as_of, gold_path=tmp_path / "g.jsonl")
    # and Phase 2 restores it
    claims_mod.write_claims(ticker_dir, as_of)
    again = verify_mod.verify_ticker(ticker_dir, as_of, gold_path=tmp_path / "g.jsonl")
    assert again["verified_count"] >= 0


def test_no_compact_leaves_the_array_in_place(tmp_path):
    ticker_dir, as_of = _claims_fixture(tmp_path)
    verify_mod.verify_ticker(ticker_dir, as_of, gold_path=tmp_path / "g.jsonl", compact=False)
    after = json.loads(
        (ticker_dir / "research" / "evidence" / f"ssi_claims_{as_of}.json").read_text(encoding="utf-8"))
    assert after["claims"]
    assert "claims_compacted" not in after


def _concepts(**series) -> dict:
    return {name: {"tag": f"us-gaap:{name}", "unit": "USD", "annual": rows, "quarterly": []}
            for name, rows in series.items()}


def test_header_suppresses_negative_pe_and_flags_stale_buybacks():
    concepts = _concepts(
        net_income=[{"end": "2025-12-31", "val": -510_600_000, "accn": "a26"}],
        eps_diluted=[{"end": "2025-12-31", "val": -5.76, "accn": "a26"}],
        # latest available buyback row is 5 years older than the income row
        buybacks_paid=[{"end": "2020-12-31", "val": 1_000_000, "accn": "a21"}],
        shares_outstanding=[
            {"end": "2025-02-05", "val": 117_000_000, "accn": "a25"},
            {"end": "2026-02-04", "val": 117_200_000, "accn": "a26"},
        ],
    )
    market = {"price_per_share": 118.0, "market_cap_m": 13_800.0, "fully_diluted_shares": 117_200_000}
    text = "\n".join(report_mod.header_stat_block("ALB", market, concepts, None, {}))
    assert "n/a (FY loss)" in text        # never a negative P/E
    assert "-20.5" not in text
    assert "stale vs latest FY" in text   # 2020 buyback row is called out
    assert "FY 2020-12-31" in text
    assert "2025-02-05 → 2026-02-04" in text  # share change names its endpoints


def test_header_keeps_positive_pe():
    concepts = _concepts(
        net_income=[{"end": "2025-12-31", "val": 228_213_000, "accn": "a"}],
        eps_diluted=[{"end": "2025-12-31", "val": 4.92, "accn": "a"}],
        buybacks_paid=[{"end": "2025-12-31", "val": 378_341_000, "accn": "a"}],
    )
    market = {"price_per_share": 72.095, "market_cap_m": 3001.63}
    text = "\n".join(report_mod.header_stat_block("TBBK", market, concepts, None, {}))
    assert "14.7" in text
    assert "n/a (FY loss)" not in text
    assert "stale vs latest FY" not in text


def test_report_skips_without_verified_claims(tmp_path):
    ticker_dir = _ticker(tmp_path, "EMPTY")
    assert report_mod.build_report(ticker_dir, "2026-08-06") is None


# ---------------------------------------------------------------------------
# Coverage report: blocker ordering must name the *actionable* blocker first
# ---------------------------------------------------------------------------

def test_ticker_args_tolerate_crlf(tmp_path, monkeypatch, capsys):
    """Piping a ticker list from a Windows-written file yields 'AEHR\\r';
    unstripped, every ticker silently becomes a no_folder skip."""
    import run_ssi_pipeline as runner

    monkeypatch.setattr(runner, "ROOT", tmp_path)
    (tmp_path / "AEHR").mkdir()
    calls: list[str] = []
    monkeypatch.setattr(runner, "_run", lambda script, ticker, as_of: (calls.append(ticker), (0, ""))[1])
    monkeypatch.setattr(runner, "_gated_comparisons",
                        lambda ticker, as_of, prefer_disk=False: 2)

    runner.main(["AEHR\r", "  ", "--date", "2026-08-06"])
    out = capsys.readouterr().out
    assert "no_folder" not in out
    assert calls and all(t == "AEHR" for t in calls)


def test_coverage_blockers_ordered_and_named(tmp_path, monkeypatch):
    import ssi_coverage_report as cov

    monkeypatch.setattr(cov, "ROOT", tmp_path)

    # No filings at all → no_filings leads.
    (tmp_path / "BARE" / "research" / "evidence").mkdir(parents=True)
    bare = cov.assess("BARE", "2026-08-06", run_gate=False)
    assert bare["blockers"][0] == "no_filings"

    # Filings + a single annual extract → single_period_only leads (a lone
    # filing can never produce a YoY diff).
    solo = tmp_path / "SOLO"
    (solo / "investor-documents" / "sec-edgar").mkdir(parents=True)
    (solo / "investor-documents" / "sec-edgar" / "10-K_20260101.htm").write_text("x", encoding="utf-8")
    text_dir = solo / "research" / "evidence" / "_text"
    text_dir.mkdir(parents=True)
    (text_dir / "10-K_20260225_rpt20251231_acc1.htm.txt").write_text("Revenues: 1\n", encoding="utf-8")
    row = cov.assess("SOLO", "2026-08-06", run_gate=False)
    assert row["blockers"][0] == "single_period_only"
    assert row["extracts_by_class"]["annual"] == 1
    assert row["has_pair"] is False
    # every emitted blocker must carry a remedy the operator can act on
    assert all(b in cov.REMEDIES for b in row["blockers"])

    # Two annual extracts → the pair check clears.
    (text_dir / "10-K_20250303_rpt20241231_acc2.htm.txt").write_text("Revenues: 1\n", encoding="utf-8")
    row2 = cov.assess("SOLO", "2026-08-06", run_gate=False)
    assert row2["has_pair"] is True
    assert "single_period_only" not in row2["blockers"]

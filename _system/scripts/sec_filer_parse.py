"""Parse reporting-person names and filing class from SEC 13D/13G HTML/text."""
from __future__ import annotations

import html
import re
from pathlib import Path
from xml.etree import ElementTree

from activist_common import FORM_ALIASES, firm_name, match_firm_id

PASSIVE_13G_FORMS = frozenset({"SC 13G", "SC 13G/A"})
ACTIVIST_13D_FORMS = frozenset({"SC 13D", "SC 13D/A"})
# Dissident-side proxy material. DEFN/PREN are the non-management statements a
# dissident files when it runs its own slate; DEFC/PREC are the registrant-side
# contested numbering.
PROXY_FORMS = frozenset({"DEFC14A", "PREC14A", "DFAN14A", "DEFN14A", "PREN14A"})
# Notice of exempt solicitation (Rule 14a-6(g)). Anyone over $5m can file one,
# so these only count as a campaign when a registry firm is behind them.
EXEMPT_SOLICITATION_FORMS = frozenset({"PX14A6G"})
# The registrant's answer to a campaign. Routine comp/ESG DEFA14As are noise;
# only the ones that actually name a tracked activist are worth indexing.
COMPANY_RESPONSE_FORMS = frozenset({"DEFA14A"})
# Hostile tender offer and the board's response to it.
TENDER_FORMS = frozenset({"SC TO-T", "SC TO-C", "SC 14D9", "SC 14D1"})
# Rule 14a-11 proxy access: a shareholder nominating directors. Always a
# campaign by construction -- nobody files one for any other reason.
PROXY_ACCESS_FORMS = frozenset({"SC 14N", "SC 14N-S"})
# How a campaign ended: a settlement seats directors, reported under Item 5.02.
BOARD_CHANGE_FORMS = frozenset({"8-K"})
BOARD_CHANGE_ITEM_RE = re.compile(
    r"item\s*5\.02|departure\s+of\s+directors|election\s+of\s+directors|"
    r"appointment\s+of\s+certain\s+officers",
    re.I,
)
# Section 16 ownership. A 13D filer crossing 10% becomes an insider, so its
# Form 4s show accumulation BETWEEN 13D/A amendments. Collected filer-side
# only: an issuer's Form 4 stream is mostly ordinary executive comp.
SECTION_16_FORMS = frozenset({"3", "4", "5", "3/A", "4/A", "5/A"})
# Fund-level periodic filings. Also filer-side: they describe the fund, not a
# position on any one issuer.
FUND_PERIODIC_FORMS = frozenset({"13F-HR", "13F-HR/A", "N-PX", "N-PX/A"})
UNRESOLVED_FIRM_ID = "unknown_activist"
UNRESOLVED_FIRM_NAME = "Unresolved SEC filer"
SEC_FILING_PREFIXES = ("SC-", "SCHEDULE-", "DEFC", "PREC", "DFAN", "DEFN", "PREN", "PX14", "DEFA")

def normalize_form(form: str | None) -> str:
    """Map an EDGAR submission type onto the canonical form string."""
    raw = re.sub(r"\s+", " ", str(form or "")).strip()
    return FORM_ALIASES.get(raw.upper(), raw)


ACTIVIST_INTENT_RE = re.compile(
    r"\b("
    r"seek(?:ing)?\s+(?:to\s+)?(?:elect|nominate)|"
    r"board\s+seat|"
    r"proxy\s+fight|"
    r"change\s+in\s+control|"
    r"strategic\s+alternatives|"
    r"operational\s+changes|"
    r"push\s+for|"
    r"activist"
    r")\b",
    re.I,
)

TAG_RE = re.compile(r"<[^>]+>")
# Decoded entities leave figure/en/no-break spaces behind (&#8199; &#8194; &nbsp;).
UNICODE_SPACE_RE = re.compile("[   -​  　﻿]")
ENTITY_SUFFIX_RE = re.compile(
    r"\b("
    r"LLC|L\.L\.C\.|LP|L\.P\.|INC\.?|CORP\.?|LTD\.?|TRUST|PARTNERS|"
    r"MANAGEMENT|CAPITAL|ADVISORS|ADVISERS|FUND|HOLDINGS|GROUP|COMPANY"
    r")\b",
    re.I,
)
PROXY_FILER_LABEL_RE = re.compile(
    r"\(Name of Person\(s\) Filing Proxy Statement[^)]*\)",
    re.I,
)
PROXY_REGISTRANT_LABEL_RE = re.compile(r"Name of Registrant as Specified in Its Charter", re.I)
CENTERED_P_RE = re.compile(
    r"<P[^>]*text-align:\s*center[^>]*>\s*(?:<B>)?\s*([^<]{3,120}?)\s*(?:</B>)?\s*</P>",
    re.I,
)
PROXY_BOLD_BEFORE_LABEL_RE = re.compile(
    r"(?:<span[^>]*font-weight:700[^>]*>([^<]{3,120})</span>|<B>([^<]{3,120})</B>)"
    r"\s*</(?:span|div|td|tr)>\s*(?:<(?:div|span|td|tr)[^>]*>\s*){0,8}\(Name of Person\(s\) Filing Proxy Statement",
    re.I,
)
SOLICITATION_GROUP_RE = re.compile(
    r"([A-Z][A-Za-z0-9 .,&'\-/]{2,100}?(?:LLC|L\.L\.C\.|LLP|L\.L\.P\.|Inc\.?|LP|Partners|Management|Fund|Trust|Company))"
    r"(?:\s*,?\s*(?:and|&)\s+[A-Z][A-Za-z0-9 .,&'\-/]{2,80}?(?:LLC|LLP|Inc\.?|LP|Fund|Trust|Company))?"
    r"\s*\(collectively",
    re.I,
)


# Firm matching scans the whole filing, which is mostly markup and exhibits.
# A reporting person is named on the cover page; a firm that appears only at
# byte 150k is being discussed, not filing. Capping keeps a full reindex of the
# local corpus in minutes rather than hours.
FIRM_MATCH_TEXT_LIMIT = 120_000

def strip_html(text: str) -> str:
    text = TAG_RE.sub(" ", text or "")
    # Decode entities after tags are gone, so &lt;b&gt; cannot become a tag.
    # EDGAR cover pages are full of &#8199; (figure space) and bare &amp; used
    # as column padding; leaving them encoded put literal "&#8199" into firm
    # names. html.unescape also tolerates the missing trailing semicolon EDGAR
    # frequently emits.
    text = html.unescape(text)
    text = UNICODE_SPACE_RE.sub(" ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


# Cover-page furniture that regularly ends up captured as a reporting person.
COVER_BOILERPLATE_RE = re.compile(
    r"^\s*(?:"
    r"i\.?\s*r\.?\s*s\.?\s*identification\s+nos?\.?\s+of\s+above\s+persons?\s*(?:\(entities\s+only\))?|"
    r"i\.?\s*r\.?\s*s\.?\s*identification\s+no\.?\s+of\s+above\s+person|"
    r"names?\s+of\s+reporting\s+persons?|"
    r"check\s+the\s+appropriate\s+box|"
    r"sec\s+use\s+only"
    r")\s*[:.\-]?\s*",
    re.I,
)
BOILERPLATE_ONLY_RE = re.compile(
    r"^(?:i\.?\s*r\.?\s*s\.?[\s.]*identification|names?\s+of\s+reporting|sec\s+use\s+only|"
    r"citizenship\s+or\s+place|check\s+the\s+appropriate|source\s+of\s+funds|"
    r"aggregate\s+amount\s+beneficially|percent\s+of\s+class|type\s+of\s+reporting\s+person)",
    re.I,
)
# "S" / "s:" left behind when the label "NAMES OF REPORTING PERSONS" is split
# mid-word by the cover-page table markup.
LEADING_LABEL_ARTIFACT_RE = re.compile(r"^[Ss]\s*[:.\)]\s*|^[Ss]\s+(?=[A-Z])")
# "... Gabelli Funds, LLC I.D. No . 13-4044523" — the EIN rides along with the name.
TRAILING_EIN_RE = re.compile(
    r"\s*(?:I\.?\s*D\.?|I\.?\s*R\.?\s*S\.?)\s*(?:No|Number)?\s*\.?\s*:?\s*\d{2}-?\d{7}\s*$",
    re.I,
)


def _is_noise_name(name: str) -> bool:
    low = name.lower().strip()
    if not low or len(low) < 3:
        return True
    if low in {
        "names of reporting persons",
        "name of reporting person",
        "i.r.s. identification no. of above persons (entities only)",
        "i.r.s. identification nos. of above persons (entities only)",
        "delaware",
        "united states",
        "new york",
        "california",
        "sec use only",
        "payment of filing fee (check the appropriate box):",
    }:
        return True
    if BOILERPLATE_ONLY_RE.match(low):
        return True
    if re.fullmatch(r"[\d\-]+", name):
        return True
    # Nothing but stray punctuation / decoded padding characters.
    if not re.search(r"[A-Za-z]{2}", name):
        return True
    if low.startswith("name of registrant"):
        return True
    if "name of person(s) filing proxy statement" in low:
        return True
    return False


def clean_filer_name(name: str) -> str:
    """Normalize one captured reporting-person string.

    Handles the three ways EDGAR cover pages corrupted names in practice:
    undecoded HTML entities, a boilerplate label glued to the front of a real
    name, and a stray "S"/"s:" artifact from the split label.
    """
    name = html.unescape(name or "")
    name = UNICODE_SPACE_RE.sub(" ", name)
    name = re.sub(r"\s+", " ", name).strip()
    # Strip the boilerplate prefix but keep whatever real name trails it, e.g.
    # "I.R.S. IDENTIFICATION NOS. ... (ENTITIES ONLY) Abel Avellan". The label
    # artifact and the boilerplate stack in either order, so alternate until
    # neither matches.
    for _ in range(4):
        stripped = LEADING_LABEL_ARTIFACT_RE.sub("", name).strip()
        stripped = COVER_BOILERPLATE_RE.sub("", stripped, count=1).strip()
        if stripped == name:
            break
        name = stripped
    # Trailing EIN the cover page carries alongside the name.
    name = TRAILING_EIN_RE.sub("", name).strip()
    name = name.strip(" .,-")
    name = re.sub(r"\s*\(\d+\)$", "", name)
    name = re.sub(r"\s+\d+$", "", name)
    name = re.sub(r"^[:;\)\(]+", "", name).strip()
    name = re.sub(r"^[:;\s]+", "", name)
    # A dangling "&" left by a truncated entity ("D. E. Shaw &").
    name = re.sub(r"\s*&\s*$", "", name).strip()
    return name


def _add_name(names: list[str], seen: set[str], name: str) -> None:
    name = clean_filer_name(name)
    if _is_noise_name(name):
        return
    low = name.lower()
    if low in seen:
        return
    seen.add(low)
    names.append(name)


def extract_reporting_persons(text: str, limit: int = 200_000) -> list[str]:
    raw = (text or "")[:limit]
    plain = strip_html(raw)
    names: list[str] = []
    seen: set[str] = set()

    patterns = [
        r"NAMES OF REPORTING PERSONS\s*(?:I\.R\.S\. IDENTIFICATION NO\. OF ABOVE PERSONS \(ENTITIES ONLY\)\s*)?(.{3,120}?)(?:\s*(?:I\.R\.S\.|CHECK THE APPROPRIATE|SEC USE ONLY|CITIZENSHIP|NUMBER OF SHARES|NAME OF REPORTING PERSON))",
        r"NAME OF REPORTING PERSON\s*(?:I\.R\.S\. IDENTIFICATION NO\. OF ABOVE PERSONS \(ENTITIES ONLY\)\s*)?(.{3,120}?)(?:\s*(?:I\.R\.S\.|CHECK THE APPROPRIATE|SEC USE ONLY|CITIZENSHIP|NUMBER OF SHARES|NAME OF REPORTING PERSON))",
        r"Item 2\.[\s\S]{0,400}?Identification Number\)\s*(.{3,120}?)(?:\s*(?:Item 3|Item 4|CUSIP|Check|$))",
    ]
    for pat in patterns:
        for m in re.finditer(pat, plain, re.I):
            chunk = m.group(1)
            chunk = re.split(r"\b(?:95-\d{7}|Check|Item \d)\b", chunk, maxsplit=1)[0]
            for part in re.split(r"\s{2,}|\n|;", chunk):
                _add_name(names, seen, part)

    if not names:
        for m in re.finditer(
            r"(?:NAMES OF REPORTING PERSONS|NAME OF REPORTING PERSON)[\s\S]{0,250}?<P[^>]*>\s*([^<]{3,120}?)\s*</P>",
            raw,
            re.I,
        ):
            _add_name(names, seen, strip_html(m.group(1)))

    if not names and any(form_hint in plain for form_hint in ("SCHEDULE 14A", "Proxy Statement")):
        names.extend(extract_proxy_filing_persons(raw))

    if not names:
        names.extend(extract_solicitation_group(raw))

    return names[:8]


def extract_proxy_filing_persons(text: str, limit: int = 200_000) -> list[str]:
    raw = (text or "")[:limit]
    label = PROXY_FILER_LABEL_RE.search(raw)
    if not label:
        return []

    start = 0
    registrant = PROXY_REGISTRANT_LABEL_RE.search(raw)
    if registrant:
        start = registrant.end()

    block = raw[start : label.start()]
    names: list[str] = []
    seen: set[str] = set()
    for match in CENTERED_P_RE.finditer(block):
        _add_name(names, seen, strip_html(match.group(1)))

    if names:
        return names[:8]

    plain_block = strip_html(block)
    lines = [line.strip() for line in re.split(r"\n+", plain_block) if line.strip()]
    for line in reversed(lines[-12:]):
        _add_name(names, seen, line)

    search_window = raw[max(0, label.start() - 20_000) : label.start()]
    for match in PROXY_BOLD_BEFORE_LABEL_RE.finditer(search_window):
        candidate = match.group(1) or match.group(2) or ""
        _add_name(names, seen, strip_html(candidate))

    return names[:8]


def extract_solicitation_group(text: str) -> list[str]:
    plain = strip_html(text)[:120_000]
    names: list[str] = []
    seen: set[str] = set()
    for match in SOLICITATION_GROUP_RE.finditer(plain):
        chunk = match.group(0)
        for part in re.split(r",|\band\b", chunk):
            part = part.replace("(collectively", "").strip(" .")
            _add_name(names, seen, part)
    return names[:5]


def slug_firm(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return slug[:80] or "unknown_filer"


def pick_primary_filer(filers: list[str]) -> str:
    entities = [f for f in filers if ENTITY_SUFFIX_RE.search(f)]
    if entities:
        return entities[0]
    return filers[0] if filers else ""


def display_firm_name(firm_id: str, firm_name_value: str, filers: list[str]) -> str:
    if firm_id != UNRESOLVED_FIRM_ID:
        return firm_name_value
    return UNRESOLVED_FIRM_NAME


def short_firm_label(firm_id: str, firm_name_value: str, filers: list[str]) -> str:
    if firm_id == UNRESOLVED_FIRM_ID:
        return UNRESOLVED_FIRM_NAME
    if firm_name_value and firm_name_value != UNRESOLVED_FIRM_NAME:
        base = firm_name_value
    else:
        base = pick_primary_filer(filers) or firm_name_value or firm_id
    extra = max(0, len(filers) - 1)
    if extra and not ENTITY_SUFFIX_RE.search(base):
        first = base.split()[0] if base.split() else base
        return f"{first} (+{extra})"
    if len(base) > 48:
        return base[:45] + "..."
    return base


STAKE_ROW_RE = re.compile(
    r"PERCENT\s+OF\s+CLASS\s+REPRESENTED\s+BY\s+AMOUNT\s+IN\s+ROW\s*\(?\s*(?:9|11)\s*\)?"
    r"[^0-9%]{0,80}?(\d{1,2}(?:\.\d+)?)\s*%",
    re.I,
)
STAKE_PROSE_RE = re.compile(
    r"approximately\s+(\d{1,2}(?:\.\d+)?)\s*%\s+of\s+the\s+(?:issued\s+and\s+)?outstanding",
    re.I,
)


def parse_stake_percent(text: str) -> float | None:
    """Extract disclosed ownership percent from a 13D/13G cover page."""
    plain = strip_html((text or "")[:400_000])
    best: float | None = None
    for match in STAKE_ROW_RE.finditer(plain):
        try:
            pct = float(match.group(1))
        except ValueError:
            continue
        if 0 < pct <= 100 and (best is None or pct > best):
            best = pct
    if best is not None:
        return best
    match = STAKE_PROSE_RE.search(plain)
    if match:
        try:
            pct = float(match.group(1))
        except ValueError:
            return None
        if 0 < pct <= 100:
            return pct
    return None


def _normalize_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()


def is_issuer_self_filing(ticker: str, meta: dict, report: dict) -> bool:
    """True when the reporting person appears to be the issuer (routine corporate filing)."""
    company = _normalize_name(meta.get("company") or ticker)
    if not company or len(company) < 4:
        return False
    candidates = [
        report.get("firm_name") or "",
        * (report.get("reporting_persons") or []),
    ]
    for name in candidates:
        norm = _normalize_name(name)
        if not norm:
            continue
        if norm == company:
            return True
        if company in norm and len(company) >= 8:
            return True
        if norm in company and len(norm) >= 8:
            return True
    return False


def classify_sec_filing(
    form: str, text: str, filers: list[str], *, firm_id: str | None = None
) -> str:
    """Classify one filing.

    ``firm_id`` lets a caller that has already resolved the filer pass the
    result in. Scanning a 120KB blob for 325 firm terms is the single most
    expensive step in the pipeline, and analyze_sec_filing() would otherwise
    do it twice per filing on the same text.
    """
    form = normalize_form(form)

    def _registry_hit(blob: str) -> str | None:
        if firm_id is not None:
            return firm_id or None
        return match_firm_id(blob)

    if form in PROXY_FORMS:
        return "activist_proxy"
    if form in ACTIVIST_13D_FORMS:
        return "activist_13d"
    if form in PASSIVE_13G_FORMS:
        blob = f"{text[:FIRM_MATCH_TEXT_LIMIT]} {' '.join(filers)}"
        if _registry_hit(blob):
            return "registry_13g"
        if ACTIVIST_INTENT_RE.search(blob):
            return "activist_13g"
        return "passive_13g"
    if form in EXEMPT_SOLICITATION_FORMS:
        blob = f"{text[:FIRM_MATCH_TEXT_LIMIT]} {' '.join(filers)}"
        if _registry_hit(blob) or ACTIVIST_INTENT_RE.search(blob):
            return "activist_proxy"
        return "exempt_solicitation"
    if form in COMPANY_RESPONSE_FORMS:
        # Only keep a defence filing that names a tracked activist — one that
        # doesn't isn't about a campaign.
        if _registry_hit(f"{text[:FIRM_MATCH_TEXT_LIMIT]} {' '.join(filers)}"):
            return "activist_proxy"
        return "company_response"
    if form in PROXY_ACCESS_FORMS:
        return "proxy_access"
    if form in TENDER_FORMS:
        blob = f"{text[:FIRM_MATCH_TEXT_LIMIT]} {' '.join(filers)}"
        if _registry_hit(blob) or ACTIVIST_INTENT_RE.search(blob):
            return "tender_offer"
        return "tender_offer_routine"
    if form in BOARD_CHANGE_FORMS:
        # 8-K volume is enormous and almost all of it is unrelated. Keep only a
        # director change that also names a tracked activist — that is a
        # campaign outcome, which is the one thing this form tells us.
        blob = f"{text[:FIRM_MATCH_TEXT_LIMIT]} {' '.join(filers)}"
        if BOARD_CHANGE_ITEM_RE.search(strip_html(text[:FIRM_MATCH_TEXT_LIMIT])) and _registry_hit(blob):
            return "campaign_outcome"
        return "other"
    if form in SECTION_16_FORMS:
        return "insider_accumulation"
    return "other"


# Classes that describe a campaign and therefore belong in the feed.
CAMPAIGN_CLASSES = frozenset(
    {
        "activist_13d",
        "activist_proxy",
        "activist_13g",
        "registry_13g",
        "proxy_access",
        "tender_offer",
        "campaign_outcome",
        "insider_accumulation",
    }
)


def should_index_filing(filing_class: str, *, include_passive: bool = False) -> bool:
    if filing_class in CAMPAIGN_CLASSES:
        return True
    if filing_class == "passive_13g" and include_passive:
        return True
    return False


def should_include_in_feed(filing_class: str) -> bool:
    return filing_class in CAMPAIGN_CLASSES


def resolve_firm(form: str, text: str, filers: list[str]) -> dict:
    capped = text[:FIRM_MATCH_TEXT_LIMIT]
    blob = f"{capped}\n{' '.join(filers)}"
    registry_id = match_firm_id(blob)
    primary = pick_primary_filer(filers)
    primary = re.sub(r"^[:;\s]+", "", primary).strip()

    resolution = "registry" if registry_id else ("sec_filer" if primary else "unknown")
    if registry_id:
        return {
            "firm_id": registry_id,
            "firm_name": firm_name(registry_id),
            "confidence": 0.95,
            "reporting_persons": filers,
            "filer_resolution": resolution,
        }
    if primary:
        fid = f"sec_filer:{slug_firm(primary)}"
        return {
            "firm_id": fid,
            "firm_name": primary,
            "confidence": 0.85,
            "reporting_persons": filers,
            "filer_resolution": "proxy_cover_block" if form in PROXY_FORMS else "sec_cover_page",
        }

    registry_id = match_firm_id(capped)
    if registry_id:
        return {
            "firm_id": registry_id,
            "firm_name": firm_name(registry_id),
            "confidence": 0.75,
            "reporting_persons": filers,
            "filer_resolution": "body_text_registry",
        }

    return {
        "firm_id": UNRESOLVED_FIRM_ID,
        "firm_name": UNRESOLVED_FIRM_NAME,
        "confidence": 0.4,
        "reporting_persons": filers,
        "filer_resolution": "unknown",
    }


def build_activist_title(
    analysis: dict,
    form: str,
    *,
    ticker: str | None = None,
    report_date: str | None = None,
) -> str:
    firm_id = analysis.get("firm_id") or UNRESOLVED_FIRM_ID
    filers = analysis.get("reporting_persons") or []
    short = short_firm_label(firm_id, analysis.get("firm_name") or "", filers)

    if firm_id == UNRESOLVED_FIRM_ID:
        bits = [form]
        if form in PROXY_FORMS:
            bits[0] = f"{form} (proxy solicitation)"
        if ticker:
            bits.append(ticker)
        if report_date:
            bits.append(report_date)
        return " · ".join(bits)

    if form in PROXY_FORMS:
        return f"{short} — {form} (proxy solicitation)"
    return f"{short} — {form}"


def is_sec_filing_relpath(path: str | None) -> bool:
    if not path:
        return False
    filing = Path(path.replace("\\", "/"))
    for part in (filing.name, filing.parent.name):
        if part.startswith(SEC_FILING_PREFIXES):
            return True
    return False


def form_from_filing_path(path: Path | str) -> str | None:
    filing = Path(str(path).replace("\\", "/"))
    name = filing.name
    parent = filing.parent.name
    if parent.startswith("SC-13D"):
        return "SC 13D/A" if name.startswith("A_") else "SC 13D"
    if parent.startswith("SC-13G"):
        return "SC 13G/A" if name.startswith("A_") else "SC 13G"
    stem = name.split("_")[0]
    if stem.startswith(SEC_FILING_PREFIXES):
        return stem.replace("-", " ")
    return None


SCHEDULE_13_NS = "{http://www.sec.gov/edgar/schedule13D}"


def _xml_text(node, tag: str) -> str:
    """Read a child tag from either namespace form (schedule13D or bare)."""
    if node is None:
        return ""
    for path in (f"{SCHEDULE_13_NS}{tag}", tag):
        found = node.find(path)
        if found is not None and (found.text or "").strip():
            return found.text.strip()
    return ""


def _xml_find(node, tag: str):
    if node is None:
        return None
    for path in (f"{SCHEDULE_13_NS}{tag}", tag):
        found = node.find(path)
        if found is not None:
            return found
    return None


def _xml_findall(node, tag: str) -> list:
    if node is None:
        return []
    for path in (f"{SCHEDULE_13_NS}{tag}", tag):
        found = node.findall(path)
        if found:
            return found
    return []


def parse_schedule_13_xml(xml_text: str) -> dict:
    """Parse a Schedule 13D/G ``primary_doc.xml`` into structured filer facts.

    Mandatory for Schedules 13D/G filed on or after 2024-12-18. The XML carries
    reporting-person names and CIKs verbatim, so it sidesteps the cover-page
    regexes entirely — no boilerplate, no HTML entities, no truncation.

    Returns {} when the payload is not a Schedule 13D/G submission.
    """
    if not xml_text or "edgarSubmission" not in xml_text:
        return {}
    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError:
        return {}

    header = _xml_find(root, "headerData")
    submission_type = _xml_text(header, "submissionType")
    form_data = _xml_find(root, "formData")
    cover = _xml_find(form_data, "coverPageHeader")
    issuer = _xml_find(cover, "issuerInfo")

    persons: list[str] = []
    ciks: list[str] = []
    person_types: list[str] = []
    stake: float | None = None
    for info in _xml_findall(_xml_find(form_data, "reportingPersons"), "reportingPersonInfo"):
        name = clean_filer_name(_xml_text(info, "reportingPersonName"))
        if name and not _is_noise_name(name) and name.lower() not in {p.lower() for p in persons}:
            persons.append(name)
        cik = _xml_text(info, "reportingPersonCIK").lstrip("0")
        if cik and cik not in ciks:
            ciks.append(cik)
        # Item 6 on the cover page: IN individual, CO corporation, HC parent
        # holding company, PN partnership, IA investment adviser, and so on.
        # This is the filer's own declaration of what kind of entity it is —
        # a far better classifier input than guessing from the name.
        person_type = _xml_text(info, "typeOfReportingPerson").upper()
        if person_type and person_type not in person_types:
            person_types.append(person_type)
        raw_pct = _xml_text(info, "percentOfClass")
        if raw_pct:
            try:
                pct = float(raw_pct.rstrip("% "))
            except ValueError:
                pct = None
            if pct is not None and 0 < pct <= 100 and (stake is None or pct > stake):
                stake = pct

    if not persons and not submission_type:
        return {}

    return {
        "form": normalize_form(submission_type) if submission_type else "",
        "reporting_persons": persons[:8],
        "reporting_person_ciks": ciks[:8],
        "reporting_person_types": person_types[:8],
        "stake_percent": stake,
        "issuer_name": _xml_text(issuer, "issuerName"),
        "issuer_cik": _xml_text(issuer, "issuerCIK").lstrip("0"),
        "cusip": _xml_text(_xml_find(issuer, "issuerCusips"), "issuerCusipNumber"),
        "event_date": _xml_text(cover, "dateOfEvent"),
        "source": "schedule_13_xml",
    }


# --- filer taxonomy -------------------------------------------------------
#
# Schedule 13D covers ANY holder above 5% with control intent, which includes
# company founders, strategic acquirers and PE sponsors. Treating "filed a 13D"
# as "is an activist" put Charles Ergen, Riot Platforms, General Electric,
# Johnson & Johnson and JAB BevCo in an activism feed. filer_class separates
# them so the default view can be activism without throwing the rest away —
# a strategic 13D is interesting, it just is not a campaign.

FILER_ACTIVIST = "activist"
FILER_STRATEGIC = "strategic"
FILER_SPONSOR = "sponsor"
FILER_INSIDER = "insider"
FILER_INDEX = "index_passive"
FILER_UNKNOWN = "unknown"

FILER_CLASSES = (
    FILER_ACTIVIST,
    FILER_STRATEGIC,
    FILER_SPONSOR,
    FILER_INSIDER,
    FILER_INDEX,
    FILER_UNKNOWN,
)

# Item 6 "type of reporting person" codes, mapped to our taxonomy.
PERSON_TYPE_CLASS = {
    "IN": FILER_INSIDER,   # individual
    "CO": FILER_STRATEGIC,  # corporation
    "HC": FILER_SPONSOR,    # parent holding company
    "BK": FILER_INDEX,      # bank
    "IC": FILER_INDEX,      # insurance company
    "IV": FILER_INDEX,      # investment company
    "EP": FILER_INDEX,      # employee benefit plan
    "SA": FILER_INDEX,      # savings association
    "CP": FILER_INDEX,      # church plan
}

INDEX_MANAGERS = (
    "blackrock", "vanguard", "state street", "fmr llc", "fidelity management",
    "geode capital", "northern trust", "dimensional fund", "charles schwab",
    "capital research", "wellington management", "norges bank",
    "teachers insurance", "california public employees",
)
SPONSOR_RE = re.compile(
    r"\b(holdings?|holdco|topco|bidco|midco|sponsor|acquisition (corp|company)|"
    r"aggregator|feeder|co-?invest|s\.?a\.?r\.?l|b\.?v\.?|n\.?v\.?|gmbh|pte\.?\s*ltd)\b",
    re.I,
)
FUND_RE = re.compile(
    r"\b(capital|partners|management|advisors|advisers|asset management|"
    r"investments?|fund|master fund|lp|l\.p\.)\b",
    re.I,
)
CORPORATE_RE = re.compile(
    r"\b(inc|corp|corporation|company|co|plc|ag|s\.?a\.?|group|international|"
    r"industries|technologies|pharmaceuticals?|laboratories|systems|networks)\.?\s*$",
    re.I,
)
# "Firstname M. Lastname" / "Firstname Lastname" with nothing entity-shaped.
NATURAL_PERSON_RE = re.compile(
    r"^[A-Z][a-zA-Z'’\-]+(\s+[A-Z]\.?)?(\s+[A-Z][a-zA-Z'’\-]+){1,2}(,?\s+(Jr|Sr|II|III|IV)\.?)?$"
)


# Any legal-entity marker anywhere in the name disqualifies it as a person.
# "Baupost Group LLC" matches the Firstname-Lastname shape otherwise, because
# "LLC" scans as a capitalised word.
ENTITY_MARKER_RE = re.compile(
    r"\b(llc|l\.l\.c\.|llp|lp|l\.p\.|inc|corp|corporation|company|co|ltd|limited|"
    r"plc|ag|gmbh|nv|bv|sa|sarl|trust|group|fund|funds|partners|partnership|"
    r"capital|management|advisors|advisers|holdings?|associates|ventures|"
    r"investments?|bank|insurance|pte)\b\.?",
    re.I,
)


def _looks_like_natural_person(name: str) -> bool:
    if not NATURAL_PERSON_RE.match(name.strip()):
        return False
    # "Riot Platforms Inc" also matches the shape; entity words rule it out.
    return not ENTITY_MARKER_RE.search(name)


def classify_filer_type(
    names: list[str],
    *,
    firm_id: str | None = None,
    issuer_name: str | None = None,
    person_types: list[str] | None = None,
) -> str:
    """Label what kind of holder filed, independent of whether we can name them.

    Registry membership is authoritative. Otherwise prefer the filer's own
    Item 6 declaration from the structured cover page, and fall back to name
    shape for pre-2024-12-18 filings that have no XML.
    """
    if firm_id and not firm_id.startswith("sec_filer:") and firm_id != UNRESOLVED_FIRM_ID:
        return FILER_ACTIVIST

    cleaned = [clean_filer_name(n) for n in (names or [])]
    cleaned = [n for n in cleaned if n]
    if not cleaned:
        return FILER_UNKNOWN
    primary = cleaned[0]
    blob = " ".join(cleaned).lower()

    if any(manager in blob for manager in INDEX_MANAGERS):
        return FILER_INDEX

    # The issuer reporting on its own shares is a corporate action, not a stake.
    if issuer_name:
        issuer_norm = _normalize_name(issuer_name)
        if issuer_norm and len(issuer_norm) >= 6:
            for name in cleaned:
                norm = _normalize_name(name)
                if norm and (norm == issuer_norm or issuer_norm in norm):
                    return FILER_STRATEGIC

    for code in person_types or []:
        mapped = PERSON_TYPE_CLASS.get(code.strip().upper())
        if mapped:
            return mapped

    if _looks_like_natural_person(primary):
        return FILER_INSIDER
    if SPONSOR_RE.search(primary):
        return FILER_SPONSOR
    if FUND_RE.search(primary):
        # A fund we do not track. Not an activist as far as we know, but not a
        # strategic buyer either — leave it unknown rather than guess.
        return FILER_UNKNOWN
    if CORPORATE_RE.search(primary):
        return FILER_STRATEGIC
    return FILER_UNKNOWN


def analyze_sec_filing(
    form: str,
    text: str,
    *,
    xml_facts: dict | None = None,
    issuer_name: str | None = None,
) -> dict:
    """Resolve filer identity for one filing.

    ``xml_facts`` comes from :func:`parse_schedule_13_xml`. When present its
    reporting-person names win: they are the filer's own structured input,
    whereas the cover-page regexes are a best-effort read of rendered HTML.
    """
    form = normalize_form(form)
    xml_persons = [p for p in (xml_facts or {}).get("reporting_persons") or [] if p]
    if xml_persons:
        filers = xml_persons
    else:
        filers = [re.sub(r"^[:;\s]+", "", f).strip() for f in extract_reporting_persons(text)]
        filers = [f for f in filers if f]
    firm = resolve_firm(form, text, filers)
    resolved = firm.get("firm_id") or ""
    registry_id = resolved if resolved and not resolved.startswith("sec_filer:") and resolved != UNRESOLVED_FIRM_ID else ""
    filing_class = classify_sec_filing(form, text, filers, firm_id=registry_id)
    firm["firm_name"] = display_firm_name(firm["firm_id"], firm["firm_name"], filers)
    result = {
        **firm,
        "filing_class": filing_class,
        "include_in_feed": should_include_in_feed(filing_class),
        "index_filing": should_index_filing(filing_class),
    }
    if xml_persons:
        result["filer_resolution"] = (
            "registry_xml" if firm.get("filer_resolution") == "registry" else "schedule_13_xml"
        )
        result["confidence"] = max(float(result.get("confidence") or 0), 0.97)
        if (xml_facts or {}).get("reporting_person_ciks"):
            result["reporting_person_ciks"] = xml_facts["reporting_person_ciks"]
    result["filer_class"] = classify_filer_type(
        filers,
        firm_id=result.get("firm_id"),
        issuer_name=(xml_facts or {}).get("issuer_name") or issuer_name,
        person_types=(xml_facts or {}).get("reporting_person_types"),
    )
    return result

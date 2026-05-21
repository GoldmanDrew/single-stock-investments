"""Discover Q4 feed endpoints and fetch IR document URLs."""
import json
import re
import urllib.parse
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 QDELInvestorDocs/1.0"}
ROOT = "https://ir.quidelortho.com"

FEEDS = [
    "/feed/FinancialReport.svc/GetFinancialReportList?LanguageId=1&ReportType=Annual%20Report&PageSize=-1",
    "/feed/FinancialReport.svc/GetFinancialReportList?LanguageId=1&ReportType=Quarterly%20Report&PageSize=-1",
    "/feed/FinancialReport.svc/GetFinancialReportList?LanguageId=1&PageSize=-1",
    "/feed/Event.svc/GetEventList?LanguageId=1&EventType=Presentation&PageSize=-1",
    "/feed/Event.svc/GetEventList?LanguageId=1&PageSize=-1",
    "/feed/Content.svc/GetContentList?LanguageId=1&Category=Presentations&PageSize=-1",
    "/feed/Content.svc/GetContentList?LanguageId=1&PageSize=-1",
]

pdfs: set[str] = set()


def add_url(u: str) -> None:
    if not u:
        return
    if u.startswith("/"):
        u = urllib.parse.urljoin(ROOT, u)
    if ".pdf" in u.lower() or "doc_downloads" in u.lower():
        pdfs.add(u)


def walk(obj) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, str) and any(x in k.lower() for x in ("path", "url", "link", "document", "file")):
                add_url(v)
            walk(v)
    elif isinstance(obj, list):
        for item in obj:
            walk(item)
    elif isinstance(obj, str):
        for m in re.findall(r"https?://[^\s\"'<>]+\.pdf", obj, re.I):
            add_url(m)
        for m in re.findall(r"/files/doc_downloads/[^\s\"'<>]+", obj, re.I):
            add_url("https://s201.q4cdn.com/442754795" + m)


for feed in FEEDS:
    url = ROOT + feed
    try:
        req = urllib.request.Request(url, headers={**UA, "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.loads(r.read().decode("utf-8", errors="ignore"))
        walk(data)
        print(f"OK {feed} -> keys {list(data.keys()) if isinstance(data, dict) else type(data)}")
    except Exception as e:
        print(f"FAIL {feed}: {e}")

# Also parse static pages
for page in [
    "https://ir.quidelortho.com/financials/default.aspx",
    "https://ir.quidelortho.com/events-and-presentations/presentations/default.aspx",
]:
    html = urllib.request.urlopen(urllib.request.Request(page, headers=UA), timeout=60).read().decode("utf-8", "ignore")
    for m in re.findall(r"https?://s201\.q4cdn\.com/442754795/files/doc_downloads/[^\s\"'<>]+\.pdf", html, re.I):
        add_url(m)

unique = sorted(set(p.replace("/files/files/", "/files/") for p in pdfs if p.lower().endswith(".pdf")))
print(f"\nPDFs found: {len(unique)}")
for p in unique:
    print(p)

out = __import__("pathlib").Path(__file__).parent / "_ir_pdf_urls.txt"
out.write_text("\n".join(unique) + ("\n" if unique else ""), encoding="utf-8")

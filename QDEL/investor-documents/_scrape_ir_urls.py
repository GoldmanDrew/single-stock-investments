"""Scrape QuidelOrtho IR pages for q4cdn document URLs."""
import re
import urllib.parse
import urllib.request

UA = "Mozilla/5.0 QDELInvestorDocs/1.0"
BASE = "https://s201.q4cdn.com/442754795/files/"
PAGES = [
    "https://ir.quidelortho.com/financials/default.aspx",
    "https://ir.quidelortho.com/financials/annual-reports/default.aspx",
    "https://ir.quidelortho.com/financials/sec-filings/default.aspx",
    "https://ir.quidelortho.com/events-and-presentations/default.aspx",
    "https://ir.quidelortho.com/events-and-presentations/presentations/default.aspx",
    "https://ir.quidelortho.com/home/default.aspx",
]

all_urls: set[str] = set()

for url in PAGES:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=60) as r:
            html = r.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"FAIL {url}: {e}")
        continue
    # Absolute and relative q4cdn paths
    for m in re.findall(r"https?://s201\.q4cdn\.com/442754795/files/[^\s\"'<>]+", html, re.I):
        all_urls.add(m.split('"')[0].split("'")[0])
    for m in re.findall(r"/files/doc_downloads/[^\s\"'<>]+", html, re.I):
        all_urls.add(urllib.parse.urljoin(BASE, m.lstrip("/")))
    for m in re.findall(r"doc_downloads/[^\s\"'<>]+\.pdf", html, re.I):
        all_urls.add(urllib.parse.urljoin(BASE, m))

pdfs = sorted(u for u in all_urls if u.lower().endswith(".pdf"))
print(f"Total URLs: {len(all_urls)}")
print(f"PDFs: {len(pdfs)}")
for p in pdfs:
    print(p)

out = __import__("pathlib").Path(__file__).parent / "_ir_pdf_urls.txt"
out.write_text("\n".join(pdfs) + ("\n" if pdfs else ""), encoding="utf-8")
print(f"\nWrote {out}")

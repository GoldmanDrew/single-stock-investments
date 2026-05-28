"""Extract key metrics from SEC HTML filings in workspace."""
import re
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]

FILES = {
    "CPRT_10K": BASE / "CPRT/investor-documents/sec-edgar/10-K_20250926_rpt20250731_acc0001628280_25_042946.htm",
    "CPRT_10Q": BASE / "CPRT/investor-documents/sec-edgar/10-Q_20260303_rpt20260131_acc0001193125_26_088593.htm",
    "CSGP_10K": BASE / "CSGP/investor-documents/sec-edgar/10-K_20260226_rpt20251231_acc0001057352_26_000020.htm",
    "CSGP_10Q": BASE / "CSGP/investor-documents/sec-edgar/10-Q_20260429_rpt20260331_acc0001057352_26_000035.htm",
    "DHR_10K": BASE / "DHR/investor-documents/sec-edgar/10-K_20260224_rpt20251231_acc0000313616_26_000062.htm",
    "DHR_10Q": BASE / "DHR/investor-documents/sec-edgar/10-Q_20260421_rpt20260327_acc0000313616_26_000107.htm",
}

KEYWORDS = (
    "Revenue", "Income", "Earnings", "Sales", "CashFlow", "Debt", "Segment",
    "Profit", "Margin", "EPS", "Assets", "Liabilities",
)


def extract_ix_facts(text: str) -> dict:
    facts = {}
    for m in re.finditer(
        r'name="([^"]+)"[^>]*(?:scale="([^"]*)")?[^>]*>([^<]+)<', text
    ):
        name, scale, val = m.group(1), m.group(2) or "", m.group(3).strip()
        if not any(k in name for k in KEYWORDS):
            continue
        if any(x in name for x in ("Axis", "Member", "Abstract", "Table", "LineItems")):
            continue
        key = name.split(":")[-1] if ":" in name else name
        if key not in facts:
            facts[key] = (val, scale)
    return facts


def extract_mda_snippets(text: str) -> list:
    clean = re.sub(r"<[^>]+>", " ", text)
    clean = re.sub(r"\s+", " ", clean)
    snippets = []
    for pat in [
        r"revenues? were \$[\d.]+\s*billion",
        r"operating income was \$[\d.]+\s*billion",
        r"total revenues?[^$]{0,30}\$[\d,]+",
        r"net income[^$]{0,50}\$[\d,]+",
        r"Global sales volume[^0-9]{0,30}[\d,]+",
        r"organic revenue[^.]{0,120}",
    ]:
        m = re.search(pat, clean, re.I)
        if m:
            snippets.append(m.group(0)[:200])
    return snippets


def main():
    for label, path in FILES.items():
        text = path.read_text(encoding="utf-8", errors="ignore")
        facts = extract_ix_facts(text)
        print(f"\n=== {label} ===")
        for k in sorted(facts):
            v, sc = facts[k]
            if sc:
                print(f"  {k}: {v} (scale={sc})")
            else:
                print(f"  {k}: {v}")
        for s in extract_mda_snippets(text):
            print(f"  SNIP: {s}")


if __name__ == "__main__":
    main()

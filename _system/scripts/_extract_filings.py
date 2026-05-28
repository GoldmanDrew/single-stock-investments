#!/usr/bin/env python3
"""Temporary extraction helper for Marvin deep dives."""
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")


def parse_ixbrl(path: Path) -> dict[str, list[str]]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    facts: dict[str, list[str]] = {}
    for m in re.finditer(r'name="([^"]+)"[^>]*>([^<]*)</ix:nonFraction>', text):
        name, val = m.group(1), m.group(2).strip()
        val = val.replace(",", "").replace("$", "").replace("(", "-").replace(")", "")
        if val and val not in ("—", "-", ""):
            facts.setdefault(name, []).append(val)
    return facts


def print_facts(label: str, path: Path) -> None:
    facts = parse_ixbrl(path)
    print(f"\n===== {label} =====")
    keys = sorted(k for k in facts if any(
        x in k for x in ("Revenue", "Operating", "NetIncome", "Earnings", "Assets", "Debt", "Equity", "Goodwill")
    ))
    for k in keys:
        print(f"{k}: {facts[k][:8]}")


def extract_pdf(label: str, path: Path, out_dir: Path) -> None:
    from pypdf import PdfReader

    text = "\n".join((p.extract_text() or "") for p in PdfReader(path).pages)
    out = out_dir / f"_extract_{label.replace(' ', '_')}.txt"
    out.write_text(text, encoding="utf-8")
    print(f"\n===== {label} ({len(text)} chars) -> {out.name} =====")
    for line in text.splitlines():
        ll = line.lower()
        if any(
            k in ll
            for k in (
                "total assets", "net income", "revenue", "shareholders", "book value",
                "investment", "mineral", "land", "equity", "comprehensive", "horizon",
                "otcm", "wintrust", "digital", "mortgage", "exchange", "clearing",
            )
        ):
            s = line.strip()
            if len(s) > 5:
                print(s[:160])


def main() -> None:
    root = Path(r"c:\Users\werdn\Documents\Investing\Single Stock Investments")
    out_dir = root / "_system" / "reviews" / "pending"

    sec = {
        "GOOGL 10-K FY2025": root / "GOOGL/investor-documents/sec-edgar/10-K_20260205_rpt20251231_acc0001652044_26_000018.htm",
        "GOOGL 10-Q Q1 2026": root / "GOOGL/investor-documents/sec-edgar/10-Q_20260430_rpt20260331_acc0001652044_26_000048.htm",
        "ICE 10-K FY2025": root / "ICE/investor-documents/sec-edgar/10-K_20260205_rpt20251231_acc0001571949_26_000004.htm",
        "ICE 10-Q Q1 2026": root / "ICE/investor-documents/sec-edgar/10-Q_20260430_rpt20260331_acc0001571949_26_000007.htm",
    }
    for label, path in sec.items():
        print_facts(label, path)

    pdfs = {
        "FRMO_Q3_FY2026": root / "FRMO/investor-documents/ir-frmo/2026-02-28_Quarterly_Report.pdf",
        "FRMO_Annual_FY2025": root / "FRMO/investor-documents/ir-frmo/2025-05-31_Annual_Report.pdf",
        "KEWL_Annual_2025": root / "KEWL/investor-documents/ir-kewl/2025-12-31_Annual_Report.pdf",
        "ICE_1Q26_Press": root / "ICE/investor-documents/ir-ice/1Q26-Earnings-Press-Release_Final.pdf",
        "ICE_4Q25_Press": root / "ICE/investor-documents/ir-ice/4Q25-Earnings-Press-Release_Final.pdf",
    }
    for label, path in pdfs.items():
        extract_pdf(label, path, out_dir)


if __name__ == "__main__":
    main()

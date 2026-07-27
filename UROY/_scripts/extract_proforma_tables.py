#!/usr/bin/env python3
"""Pull Selected Pro Forma tables from SEDAR circular + April 29 exhibits."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research" / "evidence"
OUT.mkdir(parents=True, exist_ok=True)


def clean(s: str) -> str:
    return " ".join(s.replace("\uf0b7", "-").replace("\u2013", "-").replace("\u2014", "-").split())


def extract_around(text: str, needle: str, before: int = 200, after: int = 2500, n: int = 5) -> list[str]:
    hits = []
    for m in re.finditer(re.escape(needle), text, flags=re.I):
        hits.append(clean(text[max(0, m.start() - before) : m.start() + after]))
        if len(hits) >= n:
            break
    return hits


def main() -> None:
    sedar = (OUT / "circular_sedar_text.md").read_text(encoding="utf-8", errors="replace")
    sections = {
        "selected_pro_forma": extract_around(sedar, "Selected New URC Pro Forma Financial Information", 50, 6000, 2),
        "pro_forma_capitalization": extract_around(sedar, "pro forma capitalization", 50, 3000, 3),
        "adjusted_ebitda": extract_around(sedar, "Adjusted EBITDA", 80, 800, 15),
        "fairness": extract_around(sedar, "Paradigm Fairness Opinion", 50, 2500, 2),
        "ownership": extract_around(sedar, "41%", 80, 400, 5),
        "lockup": extract_around(sedar, "lock-up", 80, 500, 5),
        "pfic": extract_around(sedar, "PFIC", 80, 500, 5),
        "debt": extract_around(sedar, "Royalty Notes", 80, 800, 8),
        "shares": extract_around(sedar, "223,252,749", 80, 500, 5),
        "ev_ebitda": extract_around(sedar, "EV/EBITDA", 80, 600, 8),
        "soda_ash_cycle": extract_around(sedar, "soda ash", 40, 400, 8),
    }
    (OUT / "circular_sections.json").write_text(json.dumps(sections, indent=2) + "\n", encoding="utf-8")
    (OUT / "circular_selected_pro_forma.md").write_text(
        "\n\n---\n\n".join(sections["selected_pro_forma"]) or "NOT FOUND",
        encoding="utf-8",
    )
    (OUT / "circular_fairness.md").write_text(
        "\n\n---\n\n".join(sections["fairness"]) or "NOT FOUND",
        encoding="utf-8",
    )

    # Scan April 29 full submission text for pro forma statements (may be complete)
    giant = ROOT / "investor-documents" / "sec-edgar" / "6K_20260429_0001493152-26-019420.txt"
    if giant.exists():
        g = giant.read_text(encoding="utf-8", errors="replace")
        g_sections = {
            "unaudited_pro_forma": extract_around(g, "UNAUDITED PRO FORMA CONDENSED COMBINED", 50, 8000, 3),
            "pro_forma_income": extract_around(g, "Pro Forma Condensed Combined Statements of Operations", 50, 5000, 3),
            "adjusted_ebitda": extract_around(g, "Adjusted EBITDA", 80, 800, 12),
            "royalty_revenue": extract_around(g, "Royalty revenue", 40, 500, 10),
        }
        (OUT / "april29_proforma_sections.json").write_text(json.dumps(g_sections, indent=2) + "\n", encoding="utf-8")
        if g_sections["unaudited_pro_forma"]:
            (OUT / "april29_proforma_excerpt.md").write_text(
                "\n\n---\n\n".join(g_sections["unaudited_pro_forma"]), encoding="utf-8"
            )

    # Also check June circular Appendix if SEDAR truncated - look for dollar figures near EBITDA
    money = re.findall(
        r"(?:Adjusted EBITDA|Royalty revenue|Interest expense|Net (?:income|loss)|Cash and cash equivalents|Long-term debt|Total assets)[^\n]{0,80}?\$\s*[\d,\.]+",
        sedar,
        flags=re.I,
    )
    money = [clean(m) for m in money]
    unique = []
    for m in money:
        if m not in unique:
            unique.append(m)
    (OUT / "circular_money_lines.json").write_text(json.dumps(unique[:100], indent=2) + "\n", encoding="utf-8")

    print("selected_pro_forma hits", len(sections["selected_pro_forma"]))
    print("fairness hits", len(sections["fairness"]))
    print("money lines", len(unique))
    if sections["selected_pro_forma"]:
        print(sections["selected_pro_forma"][0][:2500])
    print("--- money sample ---")
    for m in unique[:40]:
        print(m)


if __name__ == "__main__":
    main()

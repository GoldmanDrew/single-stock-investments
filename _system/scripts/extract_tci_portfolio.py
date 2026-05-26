#!/usr/bin/env python3
"""Extract embedded PDFs from Adobe Portfolio TCI Letters bundle."""
from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path

import fitz  # PyMuPDF

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = ROOT / "_system" / "reference" / "investment-wisdom" / "tci"


def slug(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", name.replace(".pdf", "")).strip("-")


def extract(portfolio_path: Path, out_dir: Path) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(portfolio_path)
    manifest: list[dict[str, str | int]] = []

    for i in range(doc.embfile_count()):
        info = doc.embfile_info(i)
        name = info["name"]
        content = doc.embfile_get(i)
        stem = slug(name)

        pdf_out = out_dir / name
        pdf_out.write_bytes(content)

        sub = fitz.open(stream=content, filetype="pdf")
        text = "\n".join(page.get_text() for page in sub)
        page_count = sub.page_count
        sub.close()

        txt_out = out_dir / f"{stem}-extract.txt"
        txt_out.write_text(text, encoding="utf-8")

        manifest.append(
            {
                "file": name,
                "stem": stem,
                "chars": len(text),
                "pages": page_count,
            }
        )

    manifest_path = out_dir / "manifest.csv"
    with manifest_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["file", "stem", "chars", "pages"])
        w.writeheader()
        w.writerows(manifest)

    print(f"Extracted {len(manifest)} letters to {out_dir}")
    return len(manifest)


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract TCI Adobe Portfolio PDFs")
    parser.add_argument(
        "portfolio",
        nargs="?",
        default=str(Path.home() / "Downloads" / "TCI Letters Portfolio.pdf"),
        help="Path to TCI Letters Portfolio.pdf",
    )
    parser.add_argument(
        "--out",
        default=str(DEFAULT_OUT),
        help="Output directory (default: _system/reference/investment-wisdom/tci)",
    )
    args = parser.parse_args()
    extract(Path(args.portfolio), Path(args.out))


if __name__ == "__main__":
    main()

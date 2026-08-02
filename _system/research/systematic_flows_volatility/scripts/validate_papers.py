"""Validate downloaded PDFs and write a reproducibility manifest."""

from __future__ import annotations

import csv
import hashlib
from pathlib import Path

from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[1]
PAPERS = ROOT / "papers"
MANIFEST = ROOT / "catalogs" / "pdf_manifest.csv"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    rows = []
    for path in sorted(PAPERS.glob("*.pdf")):
        try:
            reader = PdfReader(path)
            pages = len(reader.pages)
            valid = pages > 0
            error = ""
        except Exception as exc:
            pages = 0
            valid = False
            error = f"{type(exc).__name__}: {exc}"
        rows.append(
            {
                "file": path.name,
                "bytes": path.stat().st_size,
                "pages": pages,
                "sha256": sha256(path),
                "valid": str(valid).lower(),
                "error": error,
            }
        )

    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    with MANIFEST.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    print(f"validated={sum(row['valid'] == 'true' for row in rows)} manifest={MANIFEST}")


if __name__ == "__main__":
    main()

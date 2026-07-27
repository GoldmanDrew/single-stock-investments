#!/usr/bin/env python3
"""Download circular page images + attempt OCR for pro forma tables."""
from __future__ import annotations

import re
import time
import urllib.request
from pathlib import Path

UA = "Marvin Research single-stock-investments contact portfolio@local research bot"
ROOT = Path(__file__).resolve().parents[1]
SEC = ROOT / "investor-documents" / "sec-edgar"
IMG = SEC / "circular_pages"
IMG.mkdir(parents=True, exist_ok=True)
BASE = "https://www.sec.gov/Archives/edgar/data/1711570/000149315226029646"

html = (SEC / "6K_20260622_ex99-1.htm").read_text(encoding="utf-8", errors="replace")
srcs = re.findall(r'src=["\'](ex99-1_\d+\.jpg)["\']', html, flags=re.I)
print(f"pages: {len(srcs)}")

for i, name in enumerate(srcs):
    out = IMG / name
    if out.exists() and out.stat().st_size > 1000:
        continue
    req = urllib.request.Request(f"{BASE}/{name}", headers={"User-Agent": UA})
    data = urllib.request.urlopen(req, timeout=90).read()
    out.write_bytes(data)
    if i % 20 == 0:
        print(f"  downloaded {i+1}/{len(srcs)}")
    time.sleep(0.25)
print("images done", len(list(IMG.glob('*.jpg'))))

# OCR if pytesseract / easyocr available; else note
ocr_out = ROOT / "research" / "evidence" / "circular_ocr.txt"
try:
    from PIL import Image
    import pytesseract

    chunks = []
    for path in sorted(IMG.glob("ex99-1_*.jpg")):
        text = pytesseract.image_to_string(Image.open(path))
        chunks.append(f"\n\n===== {path.name} =====\n{text}")
        print(f"OCR {path.name} chars={len(text)}")
    ocr_out.write_text("\n".join(chunks), encoding="utf-8")
    print("wrote", ocr_out)
except Exception as exc:
    print(f"OCR unavailable: {exc}")
    # try Windows OCR via powershell later
    (ROOT / "research" / "evidence" / "circular_ocr_STATUS.txt").write_text(
        f"OCR unavailable: {exc}\nDownload images to {IMG}\n", encoding="utf-8"
    )

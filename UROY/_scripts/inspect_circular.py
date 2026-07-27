from pathlib import Path
import re
p = Path("UROY/investor-documents/sec-edgar/6K_20260622_ex99-1.htm")
raw = p.read_text(encoding="utf-8", errors="replace")
print("bytes", p.stat().st_size)
print("img tags", len(re.findall(r"<img", raw, flags=re.I)))
print("iframe", len(re.findall(r"<iframe", raw, flags=re.I)))
print("object/embed", len(re.findall(r"<(object|embed)", raw, flags=re.I)))
# sample visible text
text = re.sub(r"<[^>]+>", " ", raw)
text = re.sub(r"\s+", " ", text)
print("text len", len(text))
print(text[:1500])
# find src of images
srcs = re.findall(r'src=["\']([^"\']+)["\']', raw, flags=re.I)[:20]
print("srcs", srcs[:20])
# look for base64
print("base64 imgs", len(re.findall(r"data:image", raw, flags=re.I)))

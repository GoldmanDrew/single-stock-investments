import re
from pathlib import Path

def flatten(path: str) -> str:
    raw = Path(path).read_text(encoding="utf-8", errors="ignore")
    t = re.sub(r"<script.*?</script>", " ", raw, flags=re.I | re.S)
    t = re.sub(r"<style.*?</style>", " ", t, flags=re.I | re.S)
    t = re.sub(r"<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", t)


def snip(text: str, needle: str, before: int = 120, after: int = 900) -> None:
    i = text.lower().find(needle.lower())
    print("---", needle, "idx", i, "---")
    if i < 0:
        return
    print(text[max(0, i - before) : i + after][: before + after])


if __name__ == "__main__":
    k10 = Path(__file__).parent / "sec-edgar" / "10-K_20250730_rpt20250531_acc0001144879_25_000021.htm"
    q26 = Path(__file__).parent / "sec-edgar" / "10-Q_20260408_rpt20260228_acc0001144879_26_000030.htm"
    t = flatten(k10)
    for n in [
        "net loss",
        "Liquidity and Capital Resources",
        "substantial doubt",
        "customer concentration",
        "fifteen-year",
        "cryptocurrency",
        "high performance",
        "We have historically incurred",
        "indebtedness",
    ]:
        snip(t, n)
        print()

    tq = flatten(q26)
    print("======== 10-Q Feb 2026 ========")
    for n in ["Overview", "Liquidity", "net loss", "debt", "customer", "risk"]:
        snip(tq, n)
        print()

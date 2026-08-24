#!/usr/bin/env python3
"""Episode-scoped hotword vocabulary for Whisper transcription.

Whisper's decoder prompt is hard-capped: faster_whisper's `get_prompt` truncates
hotwords to `max_length // 2 - 1` = **223 tokens**. A global list of the 9,280
names in `security_master.json` is therefore not an option, and neither is the
635-name in-book subset. What fits -- and what actually helps -- is a small
per-episode vocabulary: the handful of names plausibly said in *this* episode,
resolved from its own title and description plus the registries.

Why this exists at all. Measured 2026-08-24 on the cached Murray Stahl memorial
episode (two speakers, overlapping, name-dense), `base` with the repo's previous
call renders "Murray Stahl had died" as **"Murray stole the died"**, turns
"insider buying" into "inside or buying", and drops "Horizon Kinetics"
completely. The same model with hotwords gets all three right and costs 18% of
throughput (11.3x -> 9.2x realtime). Across the 361 episodes already in the
corpus roughly a fifth of "Nvidia" mentions came out as "in video", which will
never resolve to NVDA -- so this is a ticker-attribution fix, not a cosmetic one.

What hotwords cannot do: they do not repair comprehension. `base` rendered
"I didn't hear anything negative" as "I mean, everything negative" both with and
without them. Only a larger model fixed that. Keep both levers.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REF = ROOT / "_system" / "reference"

# Roughly 4 characters per token for ordinary English; the real cap is 223
# tokens, so 700 characters leaves comfortable headroom even for name-dense
# strings that tokenise badly. Verified against the cap in test_whisper_vocab.py.
MAX_HOTWORD_CHARS = 700

# Reserved for the always-on core so a title packed with companies cannot starve
# the terms that are mangled on *every* show.
CORE_BUDGET_CHARS = 260

# Terms the base model demonstrably gets wrong in this corpus, plus the finance
# vocabulary that carries meaning for the downstream summariser. Deliberately
# short: every character here is one not spent on episode-specific names.
CORE_TERMS = (
    "Nvidia", "TSMC", "EBITDA", "fab", "hyperscaler", "Berkshire Hathaway",
    "free cash flow", "capital allocation", "compounder", "moat", "buyback",
    "basis points", "net asset value", "ROIC", "CAGR", "EPS", "10-K",
    "shares outstanding", "operating leverage", "terminal value",
)


def _load(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


# The master carries 9,280 rows but 5,545 are `quarantined` -- harvested
# ticker-shaped strings never confirmed to be securities, including 1,125 where
# the "name" is just the all-caps ticker: THERE, RIGHT, TRUMP, THANK, GREAT,
# KEVIN, JAPAN. Feeding those to a name matcher rewrites ordinary English into
# company mentions; a dry run over the corpus produced 272 rewrites to "THERE"
# and 82 to "RIGHT" before this filter existed. The status field was always
# there to say so -- nothing was reading it.
USABLE_STATUS = {"validated", "manual"}


@lru_cache(maxsize=1)
def _securities() -> dict:
    raw = _load(REF / "securities" / "security_master.json") or {}
    return {
        ticker: row
        for ticker, row in raw.items()
        if isinstance(row, dict) and row.get("validation_status") in USABLE_STATUS
    }


@lru_cache(maxsize=1)
def _guests() -> list:
    doc = _load(REF / "podcasts" / "podcast_guest_registry.json") or {}
    return doc.get("guests") or []


@lru_cache(maxsize=1)
def _shows() -> dict:
    doc = _load(REF / "podcasts" / "show_registry.json") or {}
    rows = doc.get("shows") if isinstance(doc, dict) else doc
    out = {}
    for row in rows or []:
        if isinstance(row, dict) and row.get("show_id"):
            out[row["show_id"]] = row
    return out


@lru_cache(maxsize=1)
def _alias_index() -> list[tuple[str, str]]:
    """(lowercased alias, canonical company name), longest alias first.

    Only aliases of 5+ characters are indexed. Shorter ones ("A", "BE", "ON")
    are real tickers but match inside ordinary prose, and a false hotword is
    worse than a missing one -- it biases the decoder toward a word that is not
    being said.
    """
    pairs: list[tuple[str, str]] = []
    for ticker, row in _securities().items():
        if not isinstance(row, dict):
            continue
        name = (row.get("name") or "").strip()
        if not name:
            continue
        for alias in [name, *(row.get("aliases") or [])]:
            alias = (alias or "").strip()
            if len(alias) >= 5:
                pairs.append((alias.lower(), name))
    pairs.sort(key=lambda p: -len(p[0]))
    return pairs


_TICKER_RE = re.compile(r"\$([A-Z][A-Z0-9.\-]{0,5})\b|\(([A-Z]{2,5})\)")


def explicit_tickers(text: str) -> list[str]:
    """Company names for tickers written as $GTX or (GTX) in the title."""
    sec = _securities()
    out: list[str] = []
    for m in _TICKER_RE.finditer(text or ""):
        sym = (m.group(1) or m.group(2) or "").upper()
        row = sec.get(sym)
        if isinstance(row, dict) and row.get("name") and row["name"] not in out:
            out.append(row["name"])
    return out


def match_companies(text: str, limit: int = 8) -> list[str]:
    low = (text or "").lower()
    out: list[str] = []
    for alias, name in _alias_index():
        if name in out:
            continue
        if re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", low):
            out.append(name)
            if len(out) >= limit:
                break
    return out


def match_guests(text: str, limit: int = 4) -> list[str]:
    low = (text or "").lower()
    out: list[str] = []
    for guest in _guests():
        names = [guest.get("display") or "", *(guest.get("aliases") or []),
                 *(guest.get("fund_aliases") or [])]
        if any(a and a.lower() in low for a in names):
            primary = (guest.get("aliases") or [guest.get("display") or ""])[0]
            fund = (guest.get("fund_aliases") or [None])[0]
            for value in (primary, fund):
                if value and value not in out:
                    out.append(value)
            if len(out) >= limit:
                break
    return out[:limit]


def _pack(groups: list[list[str]], budget: int) -> list[str]:
    """Fill the budget group by group, preserving priority order."""
    out: list[str] = []
    used = 0
    for group in groups:
        for term in group:
            if term in out:
                continue
            cost = len(term) + 2
            if used + cost > budget:
                continue
            out.append(term)
            used += cost
    return out


def build_hotwords(
    title: str = "",
    *,
    show_id: str = "",
    description: str = "",
    extra: tuple[str, ...] = (),
) -> str:
    """Comma-joined hotword string for one episode, inside the 223-token cap.

    Priority runs highest-signal first, because the packer drops what does not
    fit: caller-supplied terms, then tickers written explicitly in the title,
    then guests, then companies named in the title, then the show name, then
    companies named only in the description.
    """
    show = _shows().get(show_id or "", {})
    show_title = (show.get("title") or "").strip()
    head = f"{title} {show_title}".strip()

    episode_groups = [
        list(extra),
        explicit_tickers(title),
        match_guests(head),
        match_companies(title, limit=6),
        [show_title] if show_title else [],
        match_companies(description, limit=4),
    ]
    episode = _pack(episode_groups, MAX_HOTWORD_CHARS - CORE_BUDGET_CHARS)
    core = _pack([list(CORE_TERMS)], CORE_BUDGET_CHARS)
    return ", ".join(episode + core)


@lru_cache(maxsize=1)
def _book_index() -> tuple[dict[str, str], dict[str, str]]:
    """alias -> ticker lookups, split into in-book and the rest of the universe.

    A dict, not a list of regexes. The first version of this scanned every alias
    against every title, which is 1,439 queue items x ~20,000 aliases -- tens of
    millions of regex calls, and it hung the sort. Lookup runs off the title's
    own n-grams instead, so ranking one episode is O(words), not O(aliases).

    Same 5-character floor as _alias_index: short aliases match inside prose and
    a false in-book hit would promote an irrelevant episode to the front of a
    multi-day queue.
    """
    book: dict[str, str] = {}
    universe: dict[str, str] = {}
    for ticker, row in _securities().items():
        if not isinstance(row, dict):
            continue
        target = book if row.get("in_book") else universe
        name = (row.get("name") or "").strip()
        for alias in [name, *(row.get("aliases") or [])]:
            alias = (alias or "").strip().lower()
            if len(alias) >= 5:
                target.setdefault(alias, ticker)
        # An explicit $TICKER in a title is unambiguous regardless of length.
        target.setdefault(f"${ticker.lower()}", ticker)
    return book, universe


_WORD_RE = re.compile(r"\$?[a-z0-9][a-z0-9.\-']*")
MAX_ALIAS_WORDS = 5


def _ngrams(text: str) -> set[str]:
    words = _WORD_RE.findall((text or "").lower())
    out: set[str] = set()
    for i in range(len(words)):
        for n in range(1, MAX_ALIAS_WORDS + 1):
            if i + n > len(words):
                break
            out.add(" ".join(words[i:i + n]))
    return out


def _hits(text: str, index: dict[str, str]) -> list[str]:
    found: list[str] = []
    for gram in _ngrams(text):
        ticker = index.get(gram)
        if ticker and ticker not in found:
            found.append(ticker)
    return sorted(found)


def in_book_hits(text: str) -> list[str]:
    """Tickers from the book named in this text. Used to rank the Whisper queue."""
    return _hits(text, _book_index()[0])


def universe_hits(text: str) -> list[str]:
    return _hits(text, _book_index()[1])


def main() -> int:
    import argparse

    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("title")
    p.add_argument("--show-id", default="")
    p.add_argument("--description", default="")
    args = p.parse_args()
    hot = build_hotwords(args.title, show_id=args.show_id, description=args.description)
    print(hot)
    print(f"\n[{len(hot)} chars, ~{len(hot)//4} tokens, cap 223]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

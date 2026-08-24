#!/usr/bin/env python3
"""Repair mangled company names in a Whisper transcript.

Hotwords are a soft prior, not a constraint, and for an unusual single-token
name they lose. Measured on the Fastenal episode transcribed 2026-08-24 with
`Fastenal` sitting first in the hotword list: the correct spelling appears
**twice** in 8,407 words, against 26 occurrences spread over thirteen variants
-- Fastenel, Fastenol, Farsenal, Farsonal, Farsenil, Fastenor, Farsen, Farson.
Not drift, either: the very first mention at 2% through the episode is already
wrong. A bigger model narrows this but does not close it.

So repair it afterwards, where the problem is cheap and deterministic. We know
which companies an episode is about -- the title says so -- which turns an
open-vocabulary spelling problem into a closed-set one over a handful of names.

Precision matters far more than recall here: a wrong rewrite invents a claim
about a company that was never discussed, and that claim then flows into ticker
attribution. Three rules hold it down.

  * Only capitalised tokens are candidates, which excludes the lowercase common
    words that cluster around a company name. This episode is about a fastener
    distributor: "fastener" (9), "fasteners" (6) and "fastening" (4) all sit
    close to "Fastenal" and none may be touched.
  * A token whose lowercase form also appears lowercase in the same transcript
    is a real English word the speaker used, not a mangled name. That is what
    separates "Fastening" (appears as "fastening") from "Fastenol" (never does).
  * A multi-word name is matched as a phrase, never component by component.
    Splitting "Sherwin-Williams" into per-token targets rewrote a bare "William"
    -- an ordinary given name, twice in that episode -- into "Williams",
    inventing a company mention out of a person. Phrases cannot do that.

Corporate suffixes are stripped first so the distinctive core is what gets
matched: "UnitedHealth Group" targets "UnitedHealth", which the model had split
into "United Health" 85 times while never once writing it joined.
"""
from __future__ import annotations

import difflib
import re
from collections import Counter
from functools import lru_cache

# Measured over every rewrite the backfill proposed across 380 transcripts.
# Genuine variants score 0.833 and up -- Kostar/CoStar 0.833, Fastenel/Fastenal
# 0.875, Sherman Williams/Sherwin-Williams 0.867. The nearest false positives sit
# well below: Integral/Intel 0.769 and India/NVIDIA 0.727, the latter of which a
# 0.72 threshold actually let through and rewrote a country into a chipmaker.
# 0.80 separates them with room on both sides.
MIN_RATIO = 0.80

# A possessive must survive the rewrite. `_TOKEN` includes the apostrophe so
# that O'Reilly stays one token, which also means "Amphenol's" matches whole --
# and replacing it wholesale silently deleted the "'s" 45 times in one episode,
# turning "Amphenol's margins" into "Amphenol margins".
_POSSESSIVE_RE = re.compile(r"('s|'S|')$")
# Shorter tokens collide with initials and ordinary words.
MIN_TOKEN = 4

_WORD_RE = re.compile(r"\b[a-z]{3,}\b")
_TOKEN = r"[A-Z][A-Za-z'\-]*"

# Capitalised only because they start a sentence. The widened phrase pass exists
# to catch names the model split in two ("United Health"), but without this it
# also matched "For Nvidia" and replaced the whole span with "NVIDIA" -- deleting
# the word "For" from the transcript.
PHRASE_STOP = {
    "the", "a", "an", "and", "or", "but", "so", "for", "nor", "yet", "if",
    "then", "than", "that", "this", "these", "those", "it", "its", "we", "they",
    "he", "she", "you", "i", "in", "on", "at", "to", "of", "by", "with", "from",
    "as", "is", "was", "are", "were", "be", "been", "not", "no", "do", "does",
    "did", "have", "has", "had", "will", "would", "can", "could", "should",
    "what", "when", "where", "why", "how", "there", "here", "now", "also",
    "just", "very", "more", "most", "some", "any", "all", "one", "two", "after",
    "before", "because", "while", "during", "about", "over", "under", "between",
    "through", "our", "their", "his", "her", "my", "your", "like", "well",
}

SUFFIXES = {
    "group", "inc", "inc.", "corp", "corp.", "corporation", "company", "co",
    "co.", "holdings", "holding", "trust", "ltd", "ltd.", "plc", "sa", "nv",
    "ag", "the", "class", "partners", "lp",
}


def core_name(name: str) -> str:
    """Drop corporate suffixes so matching runs on the distinctive part."""
    # Some master rows carry trailing punctuation ("Tesla,"), which would be
    # written into the transcript verbatim.
    tokens = [t for t in re.split(r"\s+", (name or "").strip(" ,;:.")) if t]
    while tokens and tokens[-1].lower().strip(",") in SUFFIXES:
        tokens.pop()
    while tokens and tokens[0].lower() in SUFFIXES:
        tokens.pop(0)
    return " ".join(tokens)


def _real_words(text: str) -> set[str]:
    """Lowercase words the speaker actually used, in their own right."""
    return set(_WORD_RE.findall(text))


def _key(value: str) -> str:
    """Comparison key: letters and digits only, lowercased.

    Punctuation has to go before comparing. "Sherwin-Williams" and the spoken
    "Sherwin Williams" are the same name, and "United Health" only reveals
    itself as "UnitedHealth" once the space is gone.
    """
    return re.sub(r"[^a-z0-9]", "", (value or "").lower())


@lru_cache(maxsize=1)
def known_company_names() -> frozenset[str]:
    """Every registered company name and alias, lowercased.

    A candidate that is already one of these is a different company, not a
    misspelling of the expected one, and must be left alone.
    """
    try:
        from whisper_vocab import _securities
    except ImportError:
        return frozenset()
    out: set[str] = set()
    for row in _securities().values():
        if not isinstance(row, dict):
            continue
        for alias in [row.get("name") or "", *(row.get("aliases") or [])]:
            alias = (alias or "").strip().lower()
            if len(alias) >= MIN_TOKEN:
                out.add(alias)
    return frozenset(out)


def _repair_width(text: str, core: str, width: int, lowercase_words: set[str],
                  counts: Counter, known_names: frozenset[str]) -> str:
    """Rewrite `width`-token capitalised runs that are near-misses of `core`."""
    target = _key(core)
    if len(target) < MIN_TOKEN:
        return text
    phrase_re = re.compile(r"\b" + r"\s+".join([_TOKEN] * width) + r"\b")

    def _sub(match: re.Match) -> str:
        raw = match.group(0)
        if raw == core or raw.lower() == core.lower():
            # Test identity BEFORE stripping the possessive. "McDonald's" is
            # already the canonical name; stripping its "'s" and re-appending
            # produced "McDonald's's" nine times in one episode.
            return raw
        if _POSSESSIVE_RE.search(core):
            # The canonical name ends in "'s" itself -- never stack another.
            return raw if _key(raw) != target else core
        possessive = _POSSESSIVE_RE.search(raw)
        suffix = possessive.group(0) if possessive else ""
        found = raw[: len(raw) - len(suffix)] if suffix else raw
        if not found:
            return raw
        if found == core or found.lower() == core.lower():
            # Identical, or differing only in case. Rewriting "Nvidia" to the
            # master's "NVIDIA" is 246 pointless edits that bury the real ones.
            return raw
        key = _key(found)
        if not key:
            return raw
        if width > 1 and any(t.lower().strip(".,;:!?'") in PHRASE_STOP
                             for t in found.split()):
            return raw
        # A token that is already somebody's registered company name is not a
        # mangled spelling of this one. Without this, "Amazon" gets rewritten to
        # "Amazon.com" -- 81 times across the corpus, all of them wrong.
        if found.lower() in known_names:
            return raw
        if key == target:
            # Same name, different surface: "United Health" for "UnitedHealth",
            # "Sherwin Williams" for "Sherwin-Williams". Normalise to the
            # canonical spelling so entity resolution sees one string, not two.
            counts[core] += 1
            return core + suffix
        # A single token the speaker also used as an ordinary lowercase word is
        # a real word, not a mangled name.
        if width == 1 and found.lower() in lowercase_words:
            return raw
        # Cheap reject before the O(n^2) ratio: lengths that far apart are never
        # the same name.
        if abs(len(key) - len(target)) > max(3, len(target) // 3):
            return raw
        if difflib.SequenceMatcher(None, key, target).ratio() < MIN_RATIO:
            return raw
        counts[core] += 1
        return core + suffix

    return phrase_re.sub(_sub, text)


def repair(text: str, expected: list[str]) -> tuple[str, dict[str, int]]:
    """Rewrite near-miss spellings of `expected` names. Returns (text, counts).

    `expected` is the small set of companies this episode is about -- the same
    list build_hotwords resolves from the title. Passing the whole security
    master here would defeat the point: precision comes from the set being tiny.
    """
    if not text or not expected:
        return text, {}

    lowercase_words = _real_words(text)
    known_names = known_company_names() - {c.lower() for c in expected}
    cores: list[str] = []
    for name in expected:
        core = core_name(name)
        if core and len(_key(core)) >= MIN_TOKEN and core not in cores:
            cores.append(core)
    if not cores:
        return text, {}

    counts: Counter = Counter()
    result = text
    for core in cores:
        span = len(core.split())
        # Widen by one token: a one-word name may have been split in two
        # ("United Health"), and a two-word name may have picked up a stray.
        # Widest first, so "United Health Care" is consumed before the narrower
        # pass can rewrite "United" on its own.
        for width in range(span + 1, 0, -1):
            result = _repair_width(result, core, width, lowercase_words, counts,
                                   known_names)
    return result, dict(counts)


def expected_names(title: str, description: str = "") -> list[str]:
    """The companies an episode is about, from its own title. Title first."""
    try:
        from whisper_vocab import explicit_tickers, match_companies
    except ImportError:
        return []
    names = explicit_tickers(title) + match_companies(title, limit=6)
    if description:
        names += match_companies(description, limit=3)
    out: list[str] = []
    for name in names:
        if name not in out:
            out.append(name)
    return out

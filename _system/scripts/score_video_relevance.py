#!/usr/bin/env python3
"""Phase 3: decide relevance from the transcript, not the title.

Discovery deliberately admits nothing. This is where a video earns its place,
and it reads the words that were actually spoken.

Three findings from the first 25 transcripts shaped every rule here:

**Substring matching attributes companies that were never mentioned.** The
podcast helper scans with `alias in text`, so the alias `intel` matched inside
"intelligent" and "intelligence" and filed INTC against seven of twenty-five
videos -- in a value-investing corpus, where "the intelligent investor" and
"artificial intelligence" are said constantly, that is not a rare edge case. All
matching here is word-boundary anchored.

**Some tickers are spelled like ordinary English.** Of 3,445 scannable aliases
only 160 are single tokens and only four are everyday words, but one of them is
`bullish` -> BLSH, and "I'm very bullish on Israel" is not a claim about a crypto
exchange. An ambiguous alias never establishes a ticker on its own; it needs
corroboration from another alias of the same company. GOOGL survives this because
"google" corroborates "alphabet"; BLSH does not survive it, which is correct.

**A mention is not a discussion.** This is the single highest-yield filter. A
company named once in a ninety-minute macro talk is not a video about that
company, and no title-level heuristic can tell the difference. A ticker counts
only when it recurs -- enough times, and across separate windows of the
transcript, so a single dense tangent does not qualify either.

Nothing is deleted. A rejected video keeps its transcript and its full signal
record, because the thresholds are meant to be tuned against a labelled sample
and that is impossible if the evidence is thrown away.

    python _system/scripts/score_video_relevance.py --dry-run
    python _system/scripts/score_video_relevance.py
    python _system/scripts/score_video_relevance.py --explain QoDbkHOsslg
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from analyze_podcast_episode import build_aliases, scan_aliases  # noqa: E402
from vault_paths import videos_root  # noqa: E402

PODCASTS_CFG = ROOT / "_system" / "reference" / "podcasts"
GUEST_REG = PODCASTS_CFG / "podcast_guest_registry.json"

# A ticker must recur this many times, across this many separate windows.
MIN_MENTIONS = int(os.environ.get("VIDEO_MIN_MENTIONS", "4"))
MIN_CHUNKS = int(os.environ.get("VIDEO_MIN_CHUNKS", "2"))

# The podcast chunker uses a 12,000-character window, sized for 45-90 minute
# episodes. Applied to video it silently voided the spread requirement: a
# 10,214-character Sohn pitch is ONE chunk, so "must appear in >= 2 chunks" was
# unsatisfiable and rejected the whole short-talk category. BWX Technologies
# scored 23 mentions in a pitch entirely about BWX Technologies and still failed.
#
# 4,000 characters is roughly five minutes of speech, which makes spread mean
# something for a ten-minute talk instead of nothing.
VIDEO_CHUNK_CHARS = int(os.environ.get("VIDEO_CHUNK_CHARS", "4000"))
VIDEO_CHUNK_OVERLAP = int(os.environ.get("VIDEO_CHUNK_OVERLAP", "400"))

VIDEO_CFG = ROOT / "_system" / "reference" / "video"
AMBIGUOUS_CFG = VIDEO_CFG / "ambiguous_aliases.json"


def _load_ambiguous() -> tuple[set, set]:
    """Aliases that are ordinary English, and tokens unsafe as acronyms.

    Config rather than code so the list can grow from evidence without a code
    change -- the same reason company_alias_overrides.json exists on the podcast
    side.
    """
    try:
        doc = json.loads(AMBIGUOUS_CFG.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set(), set()
    return (set(doc.get("ambiguous") or []),
            set(doc.get("acronym_stop_tokens") or []))


AMBIGUOUS_ALIASES, ACRONYM_STOP_TOKENS = _load_ambiguous()
# Minimum length for a document-scoped short form ("BWX" from "BWX Technologies").
MIN_SHORT_FORM_CHARS = 3

# Guest-registry aliases too short or too generic to match on their own. Mirrors
# _BANNED_SOLO_ALIASES in resolve_podcast_entities.py, which learned these from
# the podcast corpus.
BANNED_SOLO_GUEST_ALIASES = {
    "tci", "orbis", "nomad", "marks", "stahl", "the memo", "soft dollar",
    "greenlight", "himalaya", "fairfax", "coatue", "giverny",
}
MIN_GUEST_ALIAS_CHARS = 6


def now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def boundary_pattern(alias: str) -> re.Pattern:
    """Word-boundary matcher for an alias.

    `\\b` alone is wrong at a token that ends in punctuation ("berkshire's",
    "3m."), so the tail is allowed to be a possessive or any non-word character.
    The head must still be a boundary, which is what stops `intel` matching
    inside `intelligent`.
    """
    return re.compile(r"\b" + re.escape(alias) + r"(?:'s)?\b", re.IGNORECASE)


_PATTERN_CACHE: dict[str, re.Pattern] = {}


def pattern_for(alias: str) -> re.Pattern:
    if alias not in _PATTERN_CACHE:
        _PATTERN_CACHE[alias] = boundary_pattern(alias)
    return _PATTERN_CACHE[alias]


"""Corporate suffixes that appear in legal names and never in speech."""
_SUFFIX_RE = re.compile(
    r"[,\s]+(?:inc\.?|incorporated|corp\.?|corporation|co\.?|company|ltd\.?|limited|"
    r"plc|llc|l\.p\.|lp|n\.v\.|nv|s\.a\.|sa|ag|holdings?|group|the)\.?$",
    re.IGNORECASE,
)
# A stripped name shorter than this is too generic to match on alone.
MIN_STRIPPED_ALIAS = 6


def strip_corporate_suffix(alias: str) -> str:
    """'bwx technologies, inc.' -> 'bwx technologies'. Repeats for stacked suffixes."""
    previous = None
    current = (alias or "").strip()
    while previous != current:
        previous = current
        current = _SUFFIX_RE.sub("", current).strip(" ,.")
    return current


def expand_aliases(aliases: dict[str, str], guest_aliases: dict[str, str]) -> dict[str, str]:
    """Add spoken-form variants of legal names.

    2,438 of 3,445 scannable aliases in the security master are legal names
    carrying a suffix -- 'bwx technologies, inc.' -- so they can only ever match
    written filings. "Alex Silver pitches BWX Technologies at Sohn 2026" is a
    single-name stock pitch that this gate rejected outright for exactly that
    reason: the company was discussed throughout and matched nothing.

    Three guards on the expansion, because a shorter name is a broader net:
      * collisions across tickers are dropped, not arbitrarily assigned
        ('graham' resolves to two different issuers);
      * anything colliding with a person in the guest registry is dropped --
        'graham' and 'templeton' are people in this corpus far more often than
        they are tickers;
      * anything already known ambiguous stays out.
    """
    scan = scan_aliases(aliases)
    candidates: dict[str, set] = defaultdict(set)
    for alias, ticker in scan.items():
        stripped = strip_corporate_suffix(alias)
        if not stripped or stripped == alias or len(stripped) < MIN_STRIPPED_ALIAS:
            continue
        if stripped in scan or stripped in AMBIGUOUS_ALIASES:
            continue
        if stripped in guest_aliases:
            continue
        candidates[stripped].add(ticker)

    out = dict(scan)
    for stripped, tickers in candidates.items():
        if len(tickers) == 1:
            out[stripped] = next(iter(tickers))
    return out


def chunk_video(text: str) -> list[str]:
    """Windows sized for talks, not for hour-long interviews. See VIDEO_CHUNK_CHARS."""
    out: list[str] = []
    step = max(1, VIDEO_CHUNK_CHARS - VIDEO_CHUNK_OVERLAP)
    for start in range(0, len(text), step):
        piece = text[start:start + VIDEO_CHUNK_CHARS]
        if not piece.strip():
            break
        out.append(piece)
        if start + VIDEO_CHUNK_CHARS >= len(text):
            break
    return out or [text]


def short_form(alias: str) -> str | None:
    """Leading token of a multi-word name, when it is safe to count on its own.

    People introduce a company once and abbreviate thereafter. "Alex Silver
    pitches BWX Technologies at Sohn 2026" says "BWX Technologies" twice and
    "BWX" twenty-three times, so matching only the full name scored the pitch
    below the recurrence floor and rejected a video that is entirely about one
    company.

    This is only ever applied *within a transcript where the full name already
    matched*, which is what makes it safe: the short form is corroborated by
    construction and carries no global false-positive risk. The stop list still
    applies, so "general motors" never contributes "general".
    """
    tokens = (alias or "").split()
    if len(tokens) < 2:
        return None
    head = tokens[0].strip(",.'")
    if len(head) < MIN_SHORT_FORM_CHARS:
        return None
    if head in ACRONYM_STOP_TOKENS or head in AMBIGUOUS_ALIASES:
        return None
    return head


def load_guest_aliases() -> dict[str, str]:
    """Lowercased person/fund alias -> guest_id, filtered for solo-matchability."""
    try:
        doc = json.loads(GUEST_REG.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    out: dict[str, str] = {}
    for guest in doc.get("guests") or []:
        gid = guest.get("guest_id")
        for alias in (guest.get("aliases") or []) + (guest.get("fund_aliases") or []):
            low = (alias or "").strip().lower()
            if not low or low in BANNED_SOLO_GUEST_ALIASES:
                continue
            if len(low) < MIN_GUEST_ALIAS_CHARS and " " not in low:
                continue
            out[low] = gid
    return out


def score_transcript(text: str, aliases: dict[str, str],
                     guest_aliases: dict[str, str]) -> dict:
    """Signals for one transcript. Pure function -- no I/O, so it is testable."""
    chunks = chunk_video(text)
    # `aliases` arrives already expanded by the caller so the cost is paid once
    # per run rather than once per video.
    scan = aliases

    mentions: Counter = Counter()
    chunks_seen: dict[str, set] = defaultdict(set)
    evidence: dict[str, Counter] = defaultdict(Counter)
    ambiguous_only_evidence: dict[str, Counter] = defaultdict(Counter)

    for idx, chunk in enumerate(chunks):
        # Substring containment is a strict superset of a word-boundary match, so
        # this pre-filter cannot change the result -- it only avoids running 4,000
        # compiled patterns against every window. `in` is a C-speed scan and
        # discards almost the entire alias index per chunk; the boundary regex,
        # which is what actually decides, still runs on every survivor.
        low = chunk.lower()
        for alias, ticker in scan.items():
            if alias not in low:
                continue
            found = len(pattern_for(alias).findall(chunk))
            if not found:
                continue
            if alias in AMBIGUOUS_ALIASES:
                # Recorded but not counted toward establishing the ticker.
                ambiguous_only_evidence[ticker][alias] += found
                continue
            mentions[ticker] += found
            chunks_seen[ticker].add(idx)
            evidence[ticker][alias] += found

    # Document-scoped short forms. Only for companies whose full name already
    # matched in this transcript, so the abbreviation cannot introduce a company
    # that was never named. See short_form().
    short_form_evidence: dict[str, Counter] = defaultdict(Counter)
    for ticker, found_aliases in list(evidence.items()):
        heads = {h for h in (short_form(a) for a in found_aliases) if h}
        for head in heads:
            if head in scan:
                continue  # already a first-class alias, counted above
            pat = pattern_for(head)
            for idx, chunk in enumerate(chunks):
                if head not in chunk.lower():
                    continue
                hits = len(pat.findall(chunk))
                if not hits:
                    continue
                # Do not double-count the occurrences inside the full name.
                inside = sum(len(pattern_for(a).findall(chunk)) for a in found_aliases
                             if head in a.split())
                net = max(0, hits - inside)
                if net:
                    mentions[ticker] += net
                    chunks_seen[ticker].add(idx)
                    short_form_evidence[ticker][head] += net
    for ticker, counts in short_form_evidence.items():
        for head, n in counts.items():
            evidence[ticker][head + " (short form)"] = n

    # An ambiguous alias only counts once a distinct alias has established the
    # company independently. "alphabet" rides on "google"; "bullish" rides on
    # nothing, and so never establishes BLSH.
    corroborated_ambiguous: dict[str, int] = {}
    for ticker, amb in ambiguous_only_evidence.items():
        if evidence.get(ticker):
            total = sum(amb.values())
            mentions[ticker] += total
            corroborated_ambiguous[ticker] = total
            for alias, n in amb.items():
                evidence[ticker][alias] += n

    sustained = []
    mentioned_only = []
    for ticker, count in mentions.most_common():
        row = {
            "ticker": ticker,
            "mentions": count,
            "distinct_chunks": len(chunks_seen[ticker]),
            "aliases": dict(evidence[ticker]),
        }
        # Never demand more windows than the transcript actually has, or the
        # rule rejects short talks for being short rather than for being off-topic.
        need_chunks = min(MIN_CHUNKS, len(chunks))
        if count >= MIN_MENTIONS and len(chunks_seen[ticker]) >= need_chunks:
            sustained.append(row)
        else:
            mentioned_only.append(row)

    people: Counter = Counter()
    for alias, gid in guest_aliases.items():
        hits = len(pattern_for(alias).findall(text))
        if hits:
            people[gid] += hits

    rejected_ambiguous = {
        t: dict(a) for t, a in ambiguous_only_evidence.items()
        if t not in corroborated_ambiguous
    }

    return {
        "chunks": len(chunks),
        "sustained_tickers": sustained,
        "mentioned_only": mentioned_only,
        "people": [{"guest_id": g, "mentions": n} for g, n in people.most_common()],
        "ambiguous_alias_rejected": rejected_ambiguous,
        "thresholds": {"min_mentions": MIN_MENTIONS, "min_chunks": MIN_CHUNKS},
        "scored_at": now_stamp(),
    }


def decide(signals: dict) -> dict:
    """Admit, or say why not. Two independent routes in.

    A company route (this video discusses a specific business at length) and a
    people route (a registered investor is speaking, which is worth keeping even
    when the talk is about method rather than a single name -- the VALUEx and
    Sohn material is largely that).
    """
    sustained = signals.get("sustained_tickers") or []
    people = signals.get("people") or []
    reasons = []
    if sustained:
        reasons.append("sustained_company_" + str(len(sustained)))
    if people:
        reasons.append("registered_person_" + str(len(people)))
    admitted = bool(sustained or people)
    return {
        "admitted": admitted,
        "routes": reasons,
        "gate": "admitted" if admitted else "rejected_relevance",
    }


def iter_corpus():
    lib = videos_root() / "library"
    if not lib.is_dir():
        return
    for meta in sorted(lib.rglob("*.meta.json")):
        txt = meta.with_name(meta.name.replace(".meta.json", ".txt"))
        if txt.exists():
            yield meta, txt


def run(*, dry_run: bool = False, only_video: str | None = None) -> dict:
    guest_aliases = load_guest_aliases()
    aliases = expand_aliases(build_aliases(), guest_aliases)
    stats = {"scored": 0, "admitted": 0, "rejected": 0}
    rows = []

    for meta_path, txt_path in iter_corpus():
        doc = json.loads(meta_path.read_text(encoding="utf-8"))
        if only_video and doc.get("video_id") != only_video:
            continue
        text = txt_path.read_text(encoding="utf-8", errors="replace")
        signals = score_transcript(text, aliases, guest_aliases)
        verdict = decide(signals)

        stats["scored"] += 1
        stats["admitted" if verdict["admitted"] else "rejected"] += 1
        rows.append({
            "video_id": doc.get("video_id"),
            "title": doc.get("title"),
            "channel": doc.get("channel_title"),
            "gate": verdict["gate"],
            "routes": verdict["routes"],
            "sustained": [r["ticker"] for r in signals["sustained_tickers"]],
            "people": [p["guest_id"] for p in signals["people"]],
        })

        if not dry_run:
            doc["relevance"] = dict(signals, **verdict)
            doc["gate"] = verdict["gate"]
            meta_path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n",
                                 encoding="utf-8")

    stats["rows"] = rows
    return stats


def explain(video_id: str) -> int:
    guest_aliases = load_guest_aliases()
    aliases = expand_aliases(build_aliases(), guest_aliases)
    for meta_path, txt_path in iter_corpus():
        doc = json.loads(meta_path.read_text(encoding="utf-8"))
        if doc.get("video_id") != video_id:
            continue
        signals = score_transcript(
            txt_path.read_text(encoding="utf-8", errors="replace"), aliases, guest_aliases)
        print(json.dumps({"title": doc.get("title"), **signals, **decide(signals)},
                         indent=2, ensure_ascii=False))
        return 0
    print("not found: " + video_id)
    return 1


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dry-run", action="store_true", help="Score without writing meta files")
    p.add_argument("--video", default=None, help="Only this video id")
    p.add_argument("--explain", default=None, help="Dump full signals for one video id")
    args = p.parse_args()

    if args.explain:
        return explain(args.explain)

    stats = run(dry_run=args.dry_run, only_video=args.video)
    for row in stats["rows"]:
        mark = "ADMIT " if row["gate"] == "admitted" else "reject"
        print("{0} {1:26s} {2:52s} {3} {4}".format(
            mark, (row["channel"] or "")[:24], (row["title"] or "")[:50],
            ",".join(row["sustained"][:4]) or "-", ",".join(row["people"][:3]) or ""))
    print("\nscored={0} admitted={1} rejected={2}{3}".format(
        stats["scored"], stats["admitted"], stats["rejected"],
        "  (dry run, nothing written)" if args.dry_run else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

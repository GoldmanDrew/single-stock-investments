#!/usr/bin/env python3
"""Turn a podcast transcript into sourced claims about companies we can own.

Replaces the regex sentence-picker for episodes that have a real transcript.
That picker selects any sentence containing a keyword, which is how a 24,166-word
Marc Andreessen interview reduced to:

    "And like, and that was just like, wow, this seems, you know, you know,
     that seems like a risky, crazy idea."

The word "risk" was in it. Nothing else about it was a summary.

Three design choices carry the quality here.

**Ask an investable question.** Not "summarise this episode" -- a generic summary
is worth nothing on a single-stock research surface. The prompt asks what the
episode claimed about companies in the book or near-universe, and how strong the
evidence for each claim was.

**Rank windows by company density, and cap how many are sent.** The first
version of this claimed the alias pre-filter would drop 80-90% of a transcript.
Measured over 40 real transcripts it drops **25%** (224 windows to 167), and
restricting the alias set to in-book names only moves that to 24% -- because in a
12,000-character window of an investing podcast, *some* company from an
833-ticker book is nearly always mentioned. Median episode: 5 windows, 4 sent.

So the filter earns its place by ordering, not by cutting: densest windows first,
then MAX_CHUNKS bounds the spend. That cap is the real cost control, and it binds
on the long episodes (2 of the 40 sampled). Episodes naming nothing ownable get a
single thesis pass over the opening instead of a full sweep.

**Every claim carries a verbatim quote, and the quote is checked in code.** The
model is asked for the exact span it relied on; afterwards each quote must appear
in the transcript as a literal substring under whitespace normalisation, or the
claim is dropped. This is a deterministic hallucination check that costs nothing
and does not depend on the model's honesty -- which is what makes an 8B model
running locally safe enough to publish from. `quote_verified_rate` is recorded so
the check is measurable rather than assumed.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from llm_local import LocalLLMUnavailable, complete, extract_json  # noqa: E402

# ~12k characters is roughly 3k tokens: large enough to hold an argument
# together, small enough that the KV cache stays cheap on shared GPU memory.
CHUNK_CHARS = 12000
CHUNK_OVERLAP = 1200
# More than this and the episode is a survey, not a thesis; the reduce step gets
# unwieldy and the marginal chunk adds noise.
MAX_CHUNKS = 8

SYSTEM = (
    "You extract investable claims from investing-podcast transcripts. "
    "You are precise, you never invent facts, and you only report what the "
    "speakers actually said. When you are unsure, you say nothing rather than "
    "guessing. You always reply with a single JSON object and no other text."
)

MAP_PROMPT = """Below is part of a transcript from the podcast "{show}", episode "{title}".

Companies of interest (report claims about these; ignore passing mentions that carry no view):
{universe}

Extract only what this passage actually says. Reply with JSON:

{{
  "claims": [
    {{
      "company": "the company name as said",
      "ticker": "ticker if one of the companies of interest, else null",
      "stance": "bullish" | "bearish" | "mixed" | "neutral",
      "claim": "one sentence, in your own words, stating the view or fact",
      "quote": "the EXACT words from the passage that support this, copied verbatim, 10-40 words",
      "speaker": "name if identifiable, else null"
    }}
  ],
  "numbers": [
    {{"what": "what the figure measures", "value": "the figure as said", "quote": "exact supporting words"}}
  ]
}}

Rules:
- "quote" MUST be COPIED AND PASTED from the passage above, character for character.
  Do not paraphrase it. Do not fix grammar, fillers or punctuation. Do not join
  two sentences that are not adjacent. Do not shorten with "...". If you cannot
  find an exact span that supports the claim, omit the claim entirely.
  A quote that does not appear verbatim in the passage is discarded automatically,
  so an approximate quote loses the claim with it.
- If the passage contains no view about any company, return {{"claims": [], "numbers": []}}.
- Do not report the host reading advertisements or show boilerplate.

PASSAGE:
{chunk}"""

REDUCE_PROMPT = """You are consolidating extracted claims from one episode of "{show}": "{title}".

Here are the claims found across the episode:
{claims}

Reply with JSON:

{{
  "thesis": "2-3 sentences on what this episode actually argues, for an investor who did not listen",
  "tickers": ["the tickers genuinely discussed with a view, most important first"],
  "themes": [{{"theme": "short label", "stance": "bullish" | "bearish" | "mixed" | "neutral"}}]
}}

Base the thesis only on the claims above. If they are thin, say so plainly rather than padding."""


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip().lower()


def chunk_transcript(text: str) -> list[str]:
    out: list[str] = []
    step = CHUNK_CHARS - CHUNK_OVERLAP
    for start in range(0, len(text), step):
        piece = text[start:start + CHUNK_CHARS]
        if len(piece) < 500:
            break
        out.append(piece)
    return out


def relevant_chunks(chunks: list[str], aliases: dict[str, str]) -> list[tuple[int, str]]:
    """Windows that name a company we care about, richest first.

    Without this every episode costs a full pass; with it a typical interview
    sends two or three windows instead of twenty-two.
    """
    scored: list[tuple[int, int, str]] = []
    for i, chunk in enumerate(chunks):
        low = chunk.lower()
        hits = sum(1 for alias in aliases if alias in low)
        if hits:
            scored.append((hits, i, chunk))
    scored.sort(key=lambda row: (-row[0], row[1]))
    return [(i, c) for _, i, c in scored[:MAX_CHUNKS]]


def build_aliases(limit_in_book: bool = False) -> dict[str, str]:
    """Lowercased alias -> ticker, from the validated security master."""
    try:
        from whisper_vocab import _securities
    except ImportError:
        return {}
    out: dict[str, str] = {}
    for ticker, row in _securities().items():
        if not isinstance(row, dict):
            continue
        if limit_in_book and not row.get("in_book"):
            continue
        for alias in [row.get("name") or "", *(row.get("aliases") or [])]:
            alias = (alias or "").strip().lower()
            # Same 5-character floor as the hotword index: shorter aliases match
            # inside ordinary prose and would pull in irrelevant windows.
            if len(alias) >= 5:
                out.setdefault(alias, ticker)
    return out


# Models emit these as strings where the schema asked for JSON null.
_NULLISH = {"", "null", "none", "n/a", "na", "nil", "unknown", "-"}


def _clean_ticker(value) -> str | None:
    text = str(value or "").strip()
    return None if text.lower() in _NULLISH else text


def validate_tickers(claims: list[dict], aliases: dict[str, str]) -> int:
    """Drop tickers that do not belong to the company the claim is about.

    The model recalls symbols badly and confidently. On the Epic Systems episode
    it attached CSCO -- Cisco -- to a claim about Constellation Software, which
    is CSU.TO. A wrong ticker is worse than a missing one: it files a claim about
    one company under another in the research, and no amount of quote
    verification catches it, because the quote is real. The company name is what
    the model read off the page and gets right; the symbol is what it guesses.
    So the master decides, and a symbol that contradicts the name is discarded.

    Returns the number of tickers rejected.
    """
    rejected = 0
    for claim in claims or []:
        ticker = _clean_ticker(claim.get("ticker"))
        claim["ticker"] = ticker
        company = str(claim.get("company") or "").strip().lower()
        if not ticker or not company:
            continue
        expected = aliases.get(company)
        if expected is None:
            for alias, sym in aliases.items():
                if len(alias) >= 5 and (alias.startswith(company) or company.startswith(alias)):
                    expected = sym
                    break
        if expected and expected != ticker:
            claim["ticker"] = expected
            claim["ticker_corrected_from"] = ticker
            rejected += 1
        elif expected is None and ticker not in aliases.values():
            # The model named a symbol for a company the master does not carry.
            claim["ticker"] = None
            claim["ticker_rejected"] = ticker
            rejected += 1
    return rejected


def resolve_tickers(claims: list[dict], aliases: dict[str, str]) -> int:
    """Fill in tickers the model named a company for but did not symbol.

    Measured on the UnitedHealth episode: 3 of 21 verified claims came back with
    a company and no ticker -- Cigna, Elevance Health, Optum. The model is good
    at reading the transcript and poor at recalling symbols, which is the right
    division of labour: the security master already knows them, so resolve here
    rather than asking the model to memorise 3,711 names.
    """
    filled = 0
    for claim in claims or []:
        if claim.get("ticker") or not claim.get("company"):
            continue
        name = str(claim["company"]).strip().lower()
        ticker = aliases.get(name)
        if not ticker:
            # "Elevance Health" against an alias of "Elevance Health Inc".
            for alias, sym in aliases.items():
                if len(alias) >= 5 and (alias.startswith(name) or name.startswith(alias)):
                    ticker = sym
                    break
        if ticker:
            claim["ticker"] = ticker
            filled += 1
    return filled


def dedupe_numbers(numbers: list[dict]) -> list[dict]:
    """One row per figure. The same value extracted from overlapping windows
    arrives twice -- "$100 billion" appeared as both "Optum revenue" and
    "Revenue of Optum" on the first real episode.

    Keying on the quote does not work: overlapping windows produce slightly
    different spans for the same figure, so "Optum revenue" and "Revenue of
    Optum" both survived at $100 billion. Key on the value plus the meaningful
    words of the label, order-independent, which collapses that pair without
    merging two genuinely different companies that happen to share a number.
    """
    stop = {"the", "of", "a", "an", "in", "for", "to", "and", "per", "at", "s"}
    seen: set[tuple[str, frozenset]] = set()
    out: list[dict] = []
    for row in numbers or []:
        value = re.sub(r"[^a-z0-9.]", "", str(row.get("value") or "").lower())
        words = frozenset(
            w for w in re.findall(r"[a-z0-9]+", str(row.get("what") or "").lower())
            if w not in stop
        )
        key = (value, words)
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def dedupe_claims(claims: list[dict]) -> list[dict]:
    """One row per distinct claim.

    Windows overlap by CHUNK_OVERLAP characters so an argument is not severed
    mid-sentence, which means a passage in the seam is extracted twice. On the
    Visa episode three of eight surviving claims were the same sentence citing
    the same quote. Key on the quote plus the claim text: two genuinely
    different readings of one quote survive, a straight repeat does not.
    """
    seen: set[tuple[str, str]] = set()
    out: list[dict] = []
    for claim in claims or []:
        key = (_norm(claim.get("quote"))[:120], _norm(claim.get("claim"))[:120])
        if key in seen:
            continue
        seen.add(key)
        out.append(claim)
    return out


def verify_quotes(claims: list[dict], transcript: str) -> tuple[list[dict], dict]:
    """Drop any claim whose quote is not literally in the transcript."""
    hay = _norm(transcript)
    kept: list[dict] = []
    checked = 0
    for claim in claims or []:
        if not isinstance(claim, dict):
            continue
        quote = (claim.get("quote") or "").strip()
        if not quote:
            continue
        checked += 1
        if _norm(quote) in hay:
            claim["quote_verified"] = True
            kept.append(claim)
    rate = (len(kept) / checked) if checked else 0.0
    return kept, {"quotes_checked": checked, "quotes_verified": len(kept),
                  "quote_verified_rate": round(rate, 3)}


def analyze(transcript: str, *, title: str, show: str, model: str | None = None,
            aliases: dict[str, str] | None = None) -> dict:
    aliases = aliases if aliases is not None else build_aliases()
    chunks = chunk_transcript(transcript)
    picked = relevant_chunks(chunks, aliases)

    universe_note = "(none matched in this episode; report any company discussed with a clear view)"
    if picked:
        names = sorted({aliases[a] for a in aliases if any(a in c.lower() for _, c in picked)})
        if names:
            universe_note = ", ".join(names[:40])

    if not picked:
        # Nothing ownable was named. Spend one call on a thesis rather than
        # eight on windows that cannot produce a claim.
        picked = [(0, chunks[0])] if chunks else []

    raw_claims: list[dict] = []
    raw_numbers: list[dict] = []
    for _, chunk in picked:
        reply = complete(
            [{"role": "system", "content": SYSTEM},
             {"role": "user", "content": MAP_PROMPT.format(
                 show=show, title=title, universe=universe_note, chunk=chunk)}],
            model=model, json_object=True, max_tokens=1600,
        )
        doc = extract_json(reply) or {}
        raw_claims.extend(doc.get("claims") or [])
        raw_numbers.extend(doc.get("numbers") or [])

    claims, stats = verify_quotes(raw_claims, transcript)
    numbers, num_stats = verify_quotes(raw_numbers, transcript)
    stats["tickers_rejected"] = validate_tickers(claims, aliases)
    stats["tickers_resolved_post_hoc"] = resolve_tickers(claims, aliases)
    before = len(claims)
    claims = dedupe_claims(claims)
    stats["duplicate_claims_dropped"] = before - len(claims)
    numbers = dedupe_numbers(numbers)

    summary_doc: dict = {"thesis": "", "tickers": [], "themes": []}
    if claims:
        brief = json.dumps([{k: c.get(k) for k in ("company", "ticker", "stance", "claim")}
                            for c in claims[:24]], indent=1)
        reply = complete(
            [{"role": "system", "content": SYSTEM},
             {"role": "user", "content": REDUCE_PROMPT.format(show=show, title=title, claims=brief)}],
            model=model, json_object=True, max_tokens=800,
        )
        summary_doc = extract_json(reply) or summary_doc

    # Only symbols that survived validation against a claim. The reduce step
    # emits its own list and it inherits the same guessing problem -- "null" as
    # a string, and symbols for companies never discussed.
    verified_syms = [t for t in (c.get("ticker") for c in claims) if t]
    tickers: list[str] = []
    for t in list(dict.fromkeys(verified_syms)):
        if t not in tickers:
            tickers.append(t)
    for t in (summary_doc.get("tickers") or []):
        t = _clean_ticker(t)
        if t and t in verified_syms and t not in tickers:
            tickers.append(t)

    return {
        "thesis": (summary_doc.get("thesis") or "").strip(),
        "tickers": tickers,
        "themes": summary_doc.get("themes") or [],
        "claims": claims,
        "numbers": numbers,
        "method": "local_llm",
        "chunks_total": len(chunks),
        "chunks_analyzed": len(picked),
        **stats,
        "number_quotes_verified": num_stats.get("quotes_verified", 0),
    }


def main() -> int:
    import argparse

    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("transcript", help="Path to a .txt transcript")
    p.add_argument("--title", default="")
    p.add_argument("--show", default="")
    p.add_argument("--model", default=None)
    args = p.parse_args()

    path = Path(args.transcript)
    text = path.read_text(encoding="utf-8", errors="ignore")
    title = args.title
    show = args.show
    meta = path.with_name(path.name.replace(".txt", ".meta.json"))
    if meta.exists():
        try:
            doc = json.loads(meta.read_text(encoding="utf-8"))
            title = title or doc.get("title") or ""
            show = show or doc.get("show_title") or doc.get("show_id") or ""
        except json.JSONDecodeError:
            pass

    try:
        result = analyze(text, title=title, show=show, model=args.model)
    except LocalLLMUnavailable as exc:
        print(json.dumps({"error": str(exc)}, indent=2))
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

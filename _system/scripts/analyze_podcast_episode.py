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


# Typographic characters a transcript carries and a model does not reproduce.
# Published-HTML transcripts are full of them; Whisper output is nearly pure
# ASCII. Measured across two episodes: Google Part III carries 1,251 curly
# apostrophes (64 non-ASCII per 10k characters) and verified at 13.5%, while
# Visa carries 17 (6.3 per 10k) and verified at 89.9%. The model writes "it's"
# where the transcript has "it’s", so a literal substring check rejects a
# perfectly good quote -- 32 of 37 claims discarded on that episode over
# apostrophe encoding alone. Folding these does not weaken the check: the words
# must still match exactly, so a fabricated quote still fails.
_PUNCT_FOLD = str.maketrans({
    "‘": "'", "’": "'", "‚": "'", "‛": "'",
    "“": '"', "”": '"', "„": '"', "‟": '"',
    "–": "-", "—": "-", "―": "-", "−": "-",
    " ": " ", " ": " ", " ": " ", " ": " ",
    "…": "...", "´": "'", "`": "'", "′": "'",
})


def _norm(text: str) -> str:
    folded = (text or "").translate(_PUNCT_FOLD)
    return re.sub(r"\s+", " ", folded).strip().lower()


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
    scan = scan_aliases(aliases)
    for i, chunk in enumerate(chunks):
        low = chunk.lower()
        hits = sum(1 for alias in scan if alias in low)
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
            # 271 master rows carry no name at all -- BA.L is called "ba.l",
            # AAL.L is called "aal.l" -- and every one is a foreign listing. A
            # symbol is not a name, and an index entry like that can only ever
            # match by coincidence. It did: the model wrote company "BA" for
            # Boeing, which is two characters and so can never reach the
            # leading-word floor, but "ba" and "ba.l" reduce to the same single
            # token, so it matched *exactly* -- the one path with no floor on
            # it -- and carried a Boeing claim to BAE Systems in London.
            #
            # The exchange suffix is what makes it a symbol rather than a name.
            # Exactly three rows are named by a plain symbol (IBM, RH, UBER) and
            # those are real names: dropping them on the same rule deleted IBM
            # from attribution entirely, taking 22 correct claims with it.
            if alias and not (alias == ticker.strip().lower() and "." in ticker):
                out.setdefault(alias, ticker)
    return out


def book_tickers() -> frozenset[str]:
    """The symbols the book actually carries, as curated names.

    The master is 3,735 rows, of which ~830 are the book and the rest are a
    harvested long tail nobody curated. That tail is harmless when a full
    company name matches it and dangerous when a fragment does, so it is the
    two guessing branches -- a leading-word run and the model naming a symbol
    after itself -- that are restricted to the book. See `_match_alias`.
    """
    try:
        from whisper_vocab import _securities
    except ImportError:
        return frozenset()
    return frozenset(
        ticker for ticker, row in _securities().items()
        if isinstance(row, dict) and row.get("in_book")
    )


# Short names match inside ordinary prose -- "visa" in "visa requirements", "v"
# in anything -- so the window scanners drop them. Attribution must not: it
# compares whole names for equality, never substrings, and a floor there simply
# deletes Visa, Ford and every other short name from the master. Applying it at
# the two scan sites instead of inside build_aliases is what keeps a claim about
# Visa attributable to V.
SCAN_MIN_ALIAS = 5
# Floor for the leading-word-run branch only. Equality needs no floor -- Visa
# matches "Visa Inc." exactly, and ("cost",) simply is not ("costco",).
PREFIX_MIN_CHARS = 4


def scan_aliases(aliases: dict[str, str]) -> dict[str, str]:
    """The subset of the name index safe to look for inside running text."""
    return {a: t for a, t in aliases.items() if len(a) >= SCAN_MIN_ALIAS}


# Models emit these as strings where the schema asked for JSON null.
_NULLISH = {"", "null", "none", "n/a", "na", "nil", "unknown", "-"}


def _clean_ticker(value) -> str | None:
    text = str(value or "").strip()
    return None if text.lower() in _NULLISH else text


# Dropped before comparing two company names. "Elevance Health" and "Elevance
# Health Inc" are one company; "Vanguard" and "Vanguard Group" are one company.
_NAME_NOISE = {
    "inc", "incorporated", "corp", "corporation", "co", "company", "companies",
    "ltd", "limited", "plc", "llc", "lp", "nv", "sa", "ag", "spa", "ab", "as",
    "holdings", "holding", "group", "groupe", "the", "and", "class", "cl",
    "ordinary", "shares", "share", "common", "stock", "adr", "ads",
    # "Amazon" against a master row of "Amazon.com".
    "com", "net", "org",
}

def _name_tokens(text: str) -> tuple[str, ...]:
    """A company name reduced to the words that actually name it."""
    words = re.findall(r"[a-z0-9]+", str(text or "").lower())
    kept = [w for w in words if w not in _NAME_NOISE and len(w) > 1]
    return tuple(kept)


def _same_company(left: str, right: str) -> bool:
    """Whether two company names are the same name, once the corporate
    furniture is stripped. "Elevance Health" and "Elevance Health Inc"; "Visa"
    and "Visa Inc."."""
    a, b = _name_tokens(left), _name_tokens(right)
    return bool(a) and a == b


def _name_prefix_of(short: str, long: str) -> bool:
    """Whether `short` is the leading whole-word run of `long`.

    "Ford" of "Ford Motor Company". Whole tokens, never characters: the
    character version is what matched "COST" against "costamare inc." and filed
    four Costco claims under a Greek containership lessor.

    A prefix on its own is still not enough to attribute a claim -- ("apple",)
    leads both "Apple Inc." and "Apple Hospitality REIT". `_match_alias` is what
    refuses the ambiguous ones.
    """
    a, b = _name_tokens(short), _name_tokens(long)
    if not a or not b or len(a) >= len(b):
        return False
    # A stub is not a leading word. Unlike equality, which is self-protecting,
    # this branch lets a short string capture any longer name that begins with
    # it -- and the model writes ticker abbreviations into the company field, so
    # the short strings arriving here are things like "BAC" and "GD". Both were
    # mis-resolved: "BAC" led "BAC.WA" and took a Bank of America claim to a
    # Warsaw listing; "GD" led "GD Culture Group Ltd" and took a General
    # Dynamics claim to GDC. Four characters keeps Ford ("Ford Motor Company")
    # while refusing every two- and three-letter symbol.
    if len("".join(a)) < PREFIX_MIN_CHARS:
        return False
    return b[:len(a)] == a


def _match_alias(company: str, aliases: dict[str, str],
                 book: frozenset[str] | None = None) -> str | None:
    """The security master's symbol for a company name, or None."""
    return _match_basis(company, aliases, book)[0]


def _match_basis(company: str, aliases: dict[str, str],
                 book: frozenset[str] | None = None) -> tuple[str | None, str | None]:
    """The master's symbol for a company name, and which rule found it.

    Exact name first, then a leading-word run -- but only when the whole master
    agrees on the answer. "Ford" leads exactly one row, "Ford Motor Company", so
    it resolves; "Apple" leads both "Apple Inc." and "Apple Hospitality REIT",
    so on its own it resolves to nothing and the caller drops the symbol rather
    than picking whichever row the dictionary happened to store first. (Apple
    itself never reaches that branch -- "Apple" matches "Apple Inc." exactly.)

    Refusing ambiguity is the whole repair. The old code took the first
    character-wise hit it found, which made dictionary insertion order the
    arbiter of which company a claim belonged to.

    **Uniqueness inside the master is not corroboration.** That gate only asks
    whether two master rows compete for the stub; it cannot ask whether the
    company the speaker meant is in the master at all, and when it is not, the
    one row that happens to begin with the same word wins uncontested. Measured
    over the first 86 analysed episodes, that is 6 of 75 leading-word
    attributions: "Benchmark" (the venture firm) -> BHE, Benchmark Electronics;
    "Oaktree" -> OCSL, its own BDC rather than Oaktree Capital; "Sears" ->
    SCC.T, Sears Canada; "Tencent" -> TME, Tencent Music. Every one is a real
    company with no master row being captured by an unrelated one.

    So a leading-word run may only land on a row the *book* carries. The book
    is curated and about 830 rows; the other ~2,900 are a harvested tail whose
    names nobody checked, and a fragment landing there is a coincidence. This
    keeps 65 of the 69 correct attributions (Ford, Meta, Dell, Jack Henry,
    Cadence, Honeywell...) and drops all 6 wrong ones. The four it costs --
    JetBlue, Peloton, Riot, Restaurant Brands -- are passing mentions of
    companies the book does not hold, which is the cheapest thing here to lose.

    Returns (ticker, basis) where basis names the rule, so a future variant of
    this bug is visible in the corpus instead of needing a hand audit: every
    one of the four found so far was a short string capturing a longer name it
    merely begins, and each passed the tests written for the one before it.
    """
    name = str(company or "").strip().lower()
    if not name:
        return None, None
    hit = aliases.get(name)
    if hit:
        return hit, "exact_name"
    exact = {aliases[a] for a in aliases if _same_company(name, a)}
    if len(exact) == 1:
        return exact.pop(), "same_name"
    if exact:
        return None, None
    if book is None:
        book = book_tickers()
    led = {aliases[a] for a in aliases if _name_prefix_of(name, a)}
    # Ambiguity is settled against the whole master first -- a second row that
    # competes for the stub still disqualifies it, whether or not the book
    # holds either one -- and only the survivor is asked to be in the book.
    # This branch can therefore only ever subtract from what it used to accept.
    if len(led) != 1:
        return None, None
    ticker = led.pop()
    return (ticker, "leading_word") if ticker in book else (None, None)


def _names_by_ticker(aliases: dict[str, str]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for alias, ticker in aliases.items():
        out.setdefault(ticker, []).append(alias)
    return out


def _corroborates(ticker: str, company: str, by_ticker: dict[str, list[str]],
                  book: frozenset[str] | None = None) -> str | None:
    """How the master's own name for `ticker` agrees it is `company`, or None.

    Scoped to one symbol, so ambiguity across the rest of the master does not
    apply: the question here is only whether these two names describe the same
    company.
    """
    names = by_ticker.get(ticker)
    if not names:
        # A symbol the master does not carry at all is an unverifiable guess,
        # and that has to be tested BEFORE the self-naming case below. Ordered
        # the other way it accepted anything the model spelled the same way
        # twice: "TSMC" (the master carries TSM) and "TI" for Texas Instruments
        # (TXN) both walked through on 10 and 7 claims respectively, each
        # because company and ticker matched each other rather than the master.
        return None
    if book is None:
        book = book_tickers()
    if any(_same_company(company, n) for n in names):
        return "master_name"
    # A leading-word run scoped to one symbol is still a leading-word run, and
    # it reaches the same wrong answers by a different door: with "Benchmark"
    # refused upstream the claim arrives here carrying BHE, whose master name
    # it leads, and is waved through. Same rule as `_match_basis`, or the gate
    # there is decorative.
    if any(_name_prefix_of(company, n) for n in names):
        return "leading_word" if ticker.strip().upper() in book else None
    # The model routinely puts the symbol in the company field -- "COST" for
    # Costco, "BAC" for Bank of America. A symbol the master carries, naming
    # itself, is not a mismatch. But nothing here reads as a company name, so
    # this branch has no evidence in it at all: it accepts the model's unaided
    # recall on the model's own say-so, which is the IVZ question ("does the
    # symbol exist") wearing a different hat. It is restricted to the book for
    # the same reason as the leading-word run -- across 235 self-named claims
    # it is what let "APT" carry an Applied Technology claim to Alpha Pro Tech,
    # a harvested row. Confining it to curated symbols costs four out-of-book
    # BYD claims and keeps 230.
    if company.strip().upper() == ticker.strip().upper():
        return "self_named" if ticker.strip().upper() in book else None
    return None


def validate_tickers(claims: list[dict], aliases: dict[str, str],
                     book: frozenset[str] | None = None) -> int:
    """Drop tickers that do not belong to the company the claim is about.

    The model recalls symbols badly and confidently. On the Epic Systems episode
    it attached CSCO -- Cisco -- to a claim about Constellation Software, which
    is CSU.TO. A wrong ticker is worse than a missing one: it files a claim about
    one company under another in the research, and no amount of quote
    verification catches it, because the quote is real. The company name is what
    the model read off the page and gets right; the symbol is what it guesses.
    So the master decides, and a symbol that contradicts the name is discarded.

    This function spent its first eight episodes doing the opposite of that, in
    both directions:

    * It **manufactured** mismatches. The old fallback compared raw characters,
      so `company` = "COST" matched the alias "costamare inc." and the function
      helpfully "corrected" four Costco claims onto CMRE, a Greek containership
      lessor. "costco" was in the master the whole time, later in the dict.
      Matching is now whole-token, and the scan is sorted so a tie cannot
      resolve differently between runs.

    * It **waved through** real mismatches. The old rejection test asked whether
      the symbol existed (`ticker not in aliases.values()`), which is the wrong
      question -- IVZ exists and belongs to Invesco, which is how a Vanguard
      claim was filed under a competitor. It now asks whether the master's own
      name for that symbol agrees with the company, and drops it when it does
      not.

    Both of those repairs still trusted two branches that contain no evidence:
    a leading-word run that is merely unique, and the model naming a symbol
    after itself. Neither can be corroborated by a name, so both are now
    confined to the book -- see `_match_basis` and `_corroborates`. Each claim
    records `ticker_basis`, the rule that placed it, because the same bug has
    now been found four times and every time by auditing live output rather
    than by a failing test.

    Returns the number of tickers rejected.
    """
    by_ticker = _names_by_ticker(aliases)
    book = book_tickers() if book is None else book
    rejected = 0
    for claim in claims or []:
        ticker = _clean_ticker(claim.get("ticker"))
        claim["ticker"] = ticker
        claim.pop("ticker_basis", None)
        company = str(claim.get("company") or "").strip()
        if not ticker or not company:
            continue
        expected, basis = _match_basis(company, aliases, book)
        if expected and expected != ticker:
            claim["ticker"] = expected
            claim["ticker_basis"] = basis
            claim["ticker_corrected_from"] = ticker
            rejected += 1
            continue
        if expected:
            claim["ticker_basis"] = basis
            continue
        corroboration = _corroborates(ticker, company, by_ticker, book)
        if corroboration:
            claim["ticker_basis"] = corroboration
        else:
            # The master cannot place this company, so the symbol is the model's
            # unaided recall. Testing "is the symbol real" was the wrong
            # question: IVZ is entirely real and belongs to Invesco, which is
            # how a Vanguard claim ended up filed under a competitor. Ask
            # instead whether the master's name for the symbol agrees with the
            # company, and drop it when it does not.
            claim["ticker"] = None
            claim["ticker_rejected"] = ticker
            rejected += 1
    return rejected


def resolve_tickers(claims: list[dict], aliases: dict[str, str],
                    book: frozenset[str] | None = None) -> int:
    """Fill in tickers the model named a company for but did not symbol.

    Measured on the UnitedHealth episode: 3 of 21 verified claims came back with
    a company and no ticker -- Cigna, Elevance Health, Optum. The model is good
    at reading the transcript and poor at recalling symbols, which is the right
    division of labour: the security master already knows them, so resolve here
    rather than asking the model to memorise 3,711 names.
    """
    filled = 0
    book = book_tickers() if book is None else book
    for claim in claims or []:
        if claim.get("ticker") or not claim.get("company"):
            continue
        # "Elevance Health" against an alias of "Elevance Health Inc" -- but by
        # whole tokens, so a stub cannot claim a longer name it resembles.
        ticker, basis = _match_basis(claim["company"], aliases, book)
        if ticker:
            claim["ticker"] = ticker
            claim["ticker_basis"] = basis
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
            # 3000, not 1600: a dense 12k-character window routinely produces more
            # than 1600 tokens of claims, and the reply then ends mid-word.
            # Salvage recovers the complete records, but a ceiling the model
            # actually fits under loses nothing in the first place.
            model=model, json_object=True, max_tokens=3000,
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

    # Figures without a thesis are clutter, not information. The Formula 1
    # episode produced 57 verified numbers, zero claims and an empty thesis --
    # a page of statistics with nothing saying what they are about. If no claim
    # survives, the episode carried no investable view and the numbers go too.
    if not claims:
        numbers = []

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

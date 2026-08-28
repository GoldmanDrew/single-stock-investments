#!/usr/bin/env python3
"""Build structured podcast episode insights (parallel to letter insights)."""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

import letter_matching as lm  # noqa: E402
from resolve_podcast_entities import PodcastEntityResolver  # noqa: E402
from vault_paths import podcasts_ref, podcasts_root, path_to_podcasts_ref  # noqa: E402

SECURITY_MASTER = ROOT / "_system" / "reference" / "securities" / "security_master.json"
REGISTRY = ROOT / "_system" / "portfolio" / "registry.json"
EMIT_MIN_TIER = "B"
THEME_KEYWORDS = {
    "AI": ["artificial intelligence", " ai ", "llm", "gpu", "hyperscaler"],
    "Capital Allocation": ["buyback", "dividend", "capital allocation", "m&a", "acquisition"],
    "Special Situations": ["spin-off", "spinoff", "restructuring", "activist", "catalyst"],
    "Compounders": ["compounder", "moat", "pricing power", "reinvestment"],
    "Credit": ["credit", "leverage", "refinanc", "liquidity", "debt"],
}


def load_json(path: Path):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def load_security_master() -> lm.SecurityMaster:
    data = load_json(SECURITY_MASTER) or {}
    registry = load_json(REGISTRY) or {}
    return lm.SecurityMaster.from_dict(
        data if isinstance(data, dict) else {},
        registry if isinstance(registry, dict) else None,
    )


def theme_hits(text: str) -> list[dict]:
    low = f" {text.lower()} "
    out = []
    for theme, kws in THEME_KEYWORDS.items():
        if any(k in low for k in kws):
            out.append({"theme": theme, "stance": "neutral"})
    return out


def iter_episode_files(root: Path):
    ep_root = root / "episodes"
    if not ep_root.is_dir():
        return
    for meta_path in sorted(ep_root.rglob("*.meta.json")):
        stem = meta_path.name[: -len(".meta.json")]
        txt_path = meta_path.parent / f"{stem}.txt"
        yield txt_path, meta_path


def source_ref_for(txt_path: Path, meta_path: Path) -> str | None:
    path = txt_path if txt_path.exists() else meta_path
    ref = path_to_podcasts_ref(path)
    if ref:
        return ref
    try:
        rel = path.relative_to(podcasts_root())
        return podcasts_ref(rel.as_posix())
    except ValueError:
        return None


def build_episode_record(
    txt_path: Path,
    meta: dict,
    master: lm.SecurityMaster,
    resolver: PodcastEntityResolver,
    host_by_show: dict[str, list[str]] | None = None,
) -> dict:
    text = txt_path.read_text(encoding="utf-8", errors="ignore") if txt_path.exists() else ""
    # Cap expensive letter_matching — full Whisper dumps are huge vs letters.
    match_window = text[:24000]
    head = text[:8000]
    host_ids = (host_by_show or {}).get(str(meta.get("show_id") or "")) or None
    resolved = resolver.resolve_episode(
        title=meta.get("title") or "",
        description=meta.get("description") or "",
        transcript_head=head,
        show_title=meta.get("show_title") or "",
        host_guest_ids=host_ids,
    )

    positions: list[dict] = []
    seen: set[str] = set()

    if match_window.strip():
        all_mentions = lm.match_letter(match_window, master, as_of=meta.get("published"))
        for m in lm.emitted_mentions(all_mentions, EMIT_MIN_TIER):
            t = m.get("ticker")
            if not t or t in seen:
                continue
            seen.add(t)
            positions.append(
                {
                    "ticker": t,
                    "action": m.get("action") or "discussed",
                    "commentary": (m.get("evidence") or "")[:240] or None,
                    "tier": m.get("tier"),
                }
            )

    for t in resolved.get("tickers") or []:
        t = str(t)
        if t in seen:
            continue
        seen.add(t)
        positions.append({"ticker": t, "action": "discussed", "commentary": None, "tier": "resolver"})

    # Local-model analysis, when this episode has been through it. Written by
    # analyze_podcast_batch.py into the vault meta; before this it was read by
    # nothing, so 115 verified claims sat in the corpus while the dashboard
    # showed keyword themes and "discussed" against every ticker.
    analysis = meta.get("llm_analysis")
    analysis = analysis if isinstance(analysis, dict) else {}
    if analysis:
        analysis_positions(analysis, positions, seen)

    guests = resolved.get("guests") or []
    return {
        "analysis": analysis_summary(analysis),
        "claims": [c for c in (analysis.get("claims") or []) if isinstance(c, dict)],
        "numbers": [n for n in (analysis.get("numbers") or []) if isinstance(n, dict)],
        "thesis": (analysis.get("thesis") or "").strip() or None,
        "episode_id": meta.get("episode_id"),
        "show_id": meta.get("show_id"),
        "show_title": meta.get("show_title"),
        "title": meta.get("title"),
        "published": meta.get("published"),
        "link": meta.get("link"),
        "audio_url": meta.get("audio_url"),
        "discovery": meta.get("discovery"),
        "guests": guests,
        "persona_ids": sorted({pid for g in guests for pid in (g.get("persona_ids") or [])}),
        "officers": resolved.get("officers") or [],
        "companies": resolved.get("companies") or [],
        "tickers": [p["ticker"] for p in positions],
        "positions": positions,
        "themes": analysis_themes(analysis, theme_hits(text or (meta.get("description") or ""))),
        "highlights": meta.get("highlights") or [],
        "summary": meta.get("summary") or None,
        "in_book": any(bool(c.get("in_book")) for c in (resolved.get("companies") or []))
        or any(bool(o.get("in_book")) for o in (resolved.get("officers") or [])),
        "near_universe": bool(resolved.get("near_universe_any")),
        "resolve_score": resolved.get("score"),
        "resolve_trace": resolved.get("resolve_trace"),
        "ambiguous": resolved.get("ambiguous") or [],
        "source_document": source_ref_for(txt_path, txt_path.with_name(txt_path.name)),
        "transcript_source": meta.get("transcript_source"),
        "has_pz_guest": bool(resolved.get("has_pz_guest")),
        "has_officer_hit": bool(resolved.get("has_officer_hit")),
    }


def analysis_summary(analysis: dict) -> dict | None:
    """What the reader needs to judge the analysis, without the working notes.

    Coverage and the verified rate travel with the claims because they qualify
    them: an episode analysed at 0.50 had half its claims discarded, and that is
    a fact about the episode, not a debugging statistic.
    """
    if not analysis:
        return None
    claims = analysis.get("claims") or []
    return {
        "method": analysis.get("method"),
        "analyzed_at": analysis.get("analyzed_at"),
        "chunks_analyzed": analysis.get("chunks_analyzed"),
        "chunks_total": analysis.get("chunks_total"),
        "quote_verified_rate": analysis.get("quote_verified_rate"),
        "claim_count": len(claims),
        "claims_with_ticker": sum(1 for c in claims if isinstance(c, dict) and c.get("ticker")),
        "number_count": len(analysis.get("numbers") or []),
    }


# A claim's stance, in the vocabulary the insights fan-out already speaks.
_STANCE_DIRECTION = {"bullish": "constructive", "bearish": "cautious", "mixed": "neutral"}


def analysis_positions(analysis: dict, positions: list[dict], seen: set[str]) -> list[dict]:
    """Fold local-model claims into the episode's positions.

    The resolver answers "was this company named", which is why every podcast
    position carried `action: discussed` and `commentary: None`. A verified
    claim answers "what was said about it, and where in the transcript" -- so a
    claim upgrades the row the resolver already produced rather than adding a
    second one for the same ticker.

    Claims with no ticker are kept out on purpose. The validator nulls a symbol
    it cannot corroborate, and a fan-out row needs a ticker to attach to; the
    claim still reaches the reader through the episode detail payload.
    """
    by_ticker = {p["ticker"]: p for p in positions if p.get("ticker")}
    for claim in (analysis.get("claims") or []):
        ticker = claim.get("ticker")
        if not ticker:
            continue
        text = (claim.get("claim") or "").strip()
        stance = (claim.get("stance") or "neutral").strip().lower()
        row = by_ticker.get(ticker)
        if row is None:
            row = {"ticker": ticker, "action": "discussed"}
            by_ticker[ticker] = row
            positions.append(row)
            seen.add(ticker)
        # The claim is the better commentary: it is a sentence about the
        # company, where the resolver's evidence is the span that matched.
        if text:
            row["commentary"] = text[:240]
        row["tier"] = "llm_claim"
        row["stance"] = stance
        if claim.get("quote"):
            row["quote"] = (claim.get("quote") or "")[:400]
            row["quote_verified"] = bool(claim.get("quote_verified"))
    return positions


def analysis_themes(analysis: dict, fallback: list[dict]) -> list[dict]:
    """Model themes when the episode has them, keyword themes otherwise.

    `theme_hits` matches a fixed vocabulary against the transcript, so it says
    an episode touched "Capital Allocation" but not what was concluded. The
    model returns a stance with each theme, which is what the fan-out's
    direction field wanted all along.
    """
    themes = []
    for th in (analysis.get("themes") or []):
        if not isinstance(th, dict) or not th.get("theme"):
            continue
        stance = str(th.get("stance") or "neutral").strip().lower()
        themes.append({
            "theme": th.get("theme"),
            "stance": _STANCE_DIRECTION.get(stance, stance or "neutral"),
            "source": "llm",
        })
    return themes or list(fallback or [])


def index_row_from_episode(ep: dict) -> dict:
    """Thin projection for CI mirror and dashboard podcast_index."""
    try:
        from summarize_podcast_episode import filter_highlights  # noqa: WPS433
    except Exception:
        filter_highlights = lambda hs: list(hs or [])  # type: ignore
    highlights = filter_highlights(ep.get("highlights") or [])
    analysis = ep.get("analysis") if isinstance(ep.get("analysis"), dict) else None
    guests = ep.get("guests") or []
    guest_labels = []
    for g in guests:
        if isinstance(g, dict):
            guest_labels.append(g.get("display") or g.get("guest_id") or "")
        else:
            guest_labels.append(str(g))
    themes = []
    for th in (ep.get("themes") or [])[:6]:
        if isinstance(th, dict) and th.get("theme"):
            themes.append({"theme": th.get("theme"), "stance": th.get("stance") or "neutral"})
        elif th:
            themes.append({"theme": str(th), "stance": "neutral"})
    previews = []
    for h in highlights[:2]:
        if isinstance(h, dict):
            text = (h.get("quote") or h.get("text") or "")[:220]
        else:
            text = str(h)[:220]
        if text:
            previews.append(text)
    row = {
        "episode_id": ep.get("episode_id"),
        "show_id": ep.get("show_id"),
        "show_title": ep.get("show_title"),
        "title": ep.get("title"),
        "published": ep.get("published"),
        "tickers": ep.get("tickers") or [],
        "guests": [g for g in guest_labels if g],
        "persona_ids": ep.get("persona_ids") or [],
        "has_pz_guest": bool(ep.get("has_pz_guest")),
        "has_officer_hit": bool(ep.get("has_officer_hit")),
        "near_universe": bool(ep.get("near_universe")),
        "in_book": bool(ep.get("in_book")),
        "highlight_count": len(highlights),
        "highlight_previews": previews,
        "has_summary": bool((ep.get("summary") or "").strip()),
        "themes": themes,
        "source_document": ep.get("source_document"),
        "link": ep.get("link"),
    }
    # One thesis line and two counts. The claims themselves stay in the
    # per-episode detail shard: this index is a single file the SPA loads at
    # boot, and 593 analysed episodes of claim arrays would go into it.
    #
    # Present only when there is an analysis. Emitting them unconditionally put
    # 346 KB of nulls and zeros into a 4.5 MB index to say "no analysis" 3,742
    # times -- a tenth of the boot payload spent on absence. Absent reads the
    # same as false to the SPA.
    if analysis:
        row["thesis_preview"] = (ep.get("thesis") or "")[:280] or None
        row["claim_count"] = analysis.get("claim_count") or 0
        row["quote_verified_rate"] = analysis.get("quote_verified_rate")
        row["has_analysis"] = True
    return row


INDEX_MIRROR_PATH = ROOT / "_system" / "reference" / "podcasts" / "insights_index_mirror.json"
LEGACY_FULL_MIRROR_PATH = ROOT / "_system" / "reference" / "podcasts" / "insights_mirror.json"


def write_podcast_index_mirror(payload: dict) -> Path:
    """CI fallback: slim index only (not a full insights clone)."""
    episodes = payload.get("episodes") or []
    if payload.get("schema_kind") == "index_mirror" and payload.get("podcast_index"):
        rows = list(payload["podcast_index"])
    else:
        rows = [index_row_from_episode(ep) for ep in episodes]
    index_payload = {
        "generated_at": payload.get("generated_at")
        or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "schema_version": 1,
        "schema_kind": "index_mirror",
        "episode_count": len(rows),
        "podcast_index": rows,
    }
    INDEX_MIRROR_PATH.parent.mkdir(parents=True, exist_ok=True)
    INDEX_MIRROR_PATH.write_text(json.dumps(index_payload, indent=2) + "\n", encoding="utf-8")
    if LEGACY_FULL_MIRROR_PATH.exists():
        try:
            LEGACY_FULL_MIRROR_PATH.unlink()
        except OSError:
            pass
    return INDEX_MIRROR_PATH


def episode_detail_payload(ep: dict) -> dict:
    """Lazy-load payload for Podcasts tab episode click (~2 KB avg)."""
    try:
        from summarize_podcast_episode import filter_highlights  # noqa: WPS433
    except Exception:
        filter_highlights = lambda hs: [h for h in (hs or []) if isinstance(h, dict)]  # type: ignore
    highlights = filter_highlights(list(ep.get("highlights") or []))
    # A claim carries its own quote, so the reader can check it against the
    # transcript without the payload growing an evidence section of its own.
    claims = []
    for c in (ep.get("claims") or [])[:40]:
        if not isinstance(c, dict) or not (c.get("claim") or "").strip():
            continue
        claims.append({
            "company": c.get("company"),
            "ticker": c.get("ticker"),
            "stance": c.get("stance") or "neutral",
            "claim": (c.get("claim") or "")[:400],
            "quote": (c.get("quote") or "")[:400] or None,
            "quote_verified": bool(c.get("quote_verified")),
        })
    numbers = []
    for n in (ep.get("numbers") or [])[:40]:
        if not isinstance(n, dict) or not (n.get("value") or "").strip():
            continue
        numbers.append({
            "what": (n.get("what") or "")[:160],
            "value": (n.get("value") or "")[:80],
            "quote": (n.get("quote") or "")[:300] or None,
            "quote_verified": bool(n.get("quote_verified")),
        })
    positions = []
    for p in (ep.get("positions") or [])[:20]:
        if not isinstance(p, dict) or not p.get("ticker"):
            continue
        positions.append(
            {
                "ticker": p.get("ticker"),
                "action": p.get("action") or "discussed",
                "commentary": (p.get("commentary") or "")[:240] or None,
            }
        )
    guests = []
    for g in ep.get("guests") or []:
        if isinstance(g, dict):
            guests.append(
                {
                    "guest_id": g.get("guest_id"),
                    "display": g.get("display") or g.get("guest_id"),
                    "persona_ids": g.get("persona_ids") or [],
                }
            )
        elif g:
            guests.append({"display": str(g)})
    themes = []
    for th in (ep.get("themes") or [])[:8]:
        if isinstance(th, dict) and th.get("theme"):
            themes.append({"theme": th.get("theme"), "stance": th.get("stance") or "neutral"})
    detail = {
        "episode_id": ep.get("episode_id"),
        "show_id": ep.get("show_id"),
        "show_title": ep.get("show_title"),
        "title": ep.get("title"),
        "published": ep.get("published"),
        "summary": ep.get("summary") or None,
        "highlights": highlights,
        "themes": themes,
        "guests": guests,
        "persona_ids": ep.get("persona_ids") or [],
        "tickers": ep.get("tickers") or [],
        "positions": positions,
        "has_pz_guest": bool(ep.get("has_pz_guest")),
        "has_officer_hit": bool(ep.get("has_officer_hit")),
        "near_universe": bool(ep.get("near_universe")),
        "in_book": bool(ep.get("in_book")),
        "source_document": ep.get("source_document"),
        "link": ep.get("link"),
        "highlight_count": len(highlights),
    }
    analysis = ep.get("analysis") if isinstance(ep.get("analysis"), dict) else None
    if analysis or claims:
        detail["thesis"] = (ep.get("thesis") or "").strip() or None
        detail["claims"] = claims
        detail["numbers"] = numbers
        detail["analysis"] = analysis
    return detail


def emit_episode_detail_shards(payload: dict | None = None) -> int:
    """Write dashboard/data/insights/podcast_episodes/{episode_id}.json for click-through."""
    out_dir = ROOT / "dashboard" / "data" / "insights" / "podcast_episodes"
    out_dir.mkdir(parents=True, exist_ok=True)
    if payload is None:
        root = podcasts_root(create=False)
        insights = load_json(root / "insights.json") if root else None
        payload = insights if isinstance(insights, dict) else {"episodes": []}
    written = 0
    keep: set[str] = set()
    for ep in payload.get("episodes") or []:
        eid = ep.get("episode_id")
        if not eid:
            continue
        # Safe filename
        safe = re.sub(r"[^A-Za-z0-9._-]+", "_", str(eid))[:180]
        keep.add(f"{safe}.json")
        detail = episode_detail_payload(ep)
        path = out_dir / f"{safe}.json"
        path.write_text(json.dumps(detail, separators=(",", ":"), ensure_ascii=False) + "\n", encoding="utf-8")
        written += 1
    # Prune stale shards
    for stale in out_dir.glob("*.json"):
        if stale.name not in keep:
            try:
                stale.unlink()
            except OSError:
                pass
    return written


def build() -> dict:
    root = podcasts_root(create=True)
    master = load_security_master()
    resolver = PodcastEntityResolver()
    shows = (load_json(ROOT / "_system" / "reference" / "podcasts" / "show_registry.json") or {}).get(
        "shows"
    ) or []
    host_by_show = {
        str(s.get("show_id")): list(s.get("host_guest_ids") or [])
        for s in shows
        if s.get("show_id") and s.get("host_guest_ids")
    }
    try:
        from summarize_podcast_episode import filter_highlights  # noqa: WPS433
    except Exception:
        filter_highlights = lambda hs: list(hs or [])  # type: ignore

    episodes: list[dict] = []
    for txt_path, meta_path in iter_episode_files(root) or []:
        meta = load_json(meta_path) or {}
        if not meta.get("episode_id"):
            continue
        rec = build_episode_record(txt_path, meta, master, resolver, host_by_show=host_by_show)
        rec["source_document"] = source_ref_for(txt_path, meta_path)
        if meta.get("highlights"):
            rec["highlights"] = filter_highlights(meta["highlights"])
        if meta.get("summary"):
            rec["summary"] = meta["summary"]
        episodes.append(rec)

    episodes.sort(key=lambda e: e.get("published") or "", reverse=True)
    # Progress metrics
    txt_count = sum(1 for _ in (root / "episodes").rglob("*.txt")) if (root / "episodes").is_dir() else 0
    backlog = load_json(root / "whisper_backlog.json") or {}
    whisper_pending = int(backlog.get("pending_count") or 0)
    if not whisper_pending:
        whisper_pending = sum(
            1 for i in (backlog.get("items") or []) if isinstance(i, dict) and i.get("status") == "pending"
        )
    payload = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "schema_version": 1,
        "episode_count": len(episodes),
        "transcript_count": txt_count,
        "whisper_pending": whisper_pending,
        "episodes": episodes,
    }
    (root / "insights.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    write_podcast_index_mirror(payload)
    detail_n = emit_episode_detail_shards(payload)
    payload["episode_detail_shards"] = detail_n
    return payload


def main() -> int:
    payload = build()
    print(
        f"podcast episodes={payload['episode_count']} transcripts={payload.get('transcript_count')} "
        f"whisper_pending={payload.get('whisper_pending')} "
        f"detail_shards={payload.get('episode_detail_shards')} "
        f"-> {podcasts_root() / 'insights.json'} + {INDEX_MIRROR_PATH.name}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

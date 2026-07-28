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

    guests = resolved.get("guests") or []
    return {
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
        "themes": theme_hits(text or (meta.get("description") or "")),
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


def index_row_from_episode(ep: dict) -> dict:
    """Thin projection for CI mirror and dashboard podcast_index."""
    try:
        from summarize_podcast_episode import filter_highlights  # noqa: WPS433
    except Exception:
        filter_highlights = lambda hs: list(hs or [])  # type: ignore
    highlights = filter_highlights(ep.get("highlights") or [])
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
    return {
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
    return {
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

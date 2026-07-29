#!/usr/bin/env python3
"""Gated LLM (or extractive fallback) highlights for podcast episodes."""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from vault_paths import podcasts_root  # noqa: E402

try:
    import llm_call_gate  # noqa: E402
except Exception:  # pragma: no cover
    llm_call_gate = None  # type: ignore

# Binary / TOC / show-notes junk that extractive often lifts.
_GARBLED_RE = re.compile(
    r"("
    r"[\x00-\x08\x0b\x0c\x0e-\x1f]"  # control chars
    r"|application/octet-stream"
    r"|PK\x03\x04"
    r"|\btable of contents\b"
    r"|\bcopyright\b.{0,40}\ball rights reserved\b"
    r"|^\s*[-*=]{8,}\s*$"
    r"|www\.[^\s]{80,}"
    r"|\binternet service terms\b"
    r"|\bapple podcasts web player\b"
    r"|\bprivacy cookie warning\b"
    r"|\bcookie (policy|warning|settings)\b"
    r"|\bsubscribe (on|in) (apple|spotify|youtube)\b"
    r"|\bsupport feedback to listen\b"
    r")",
    re.I | re.M,
)


def load_json(path: Path):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def is_garbled_highlight(text: str) -> bool:
    s = (text or "").strip()
    if len(s) < 24:
        return True
    if len(s) > 500:
        return True
    # High ratio of non-letters → binary / TOC junk
    letters = sum(1 for c in s if c.isalpha())
    if letters < 20 or letters / max(len(s), 1) < 0.45:
        return True
    if _GARBLED_RE.search(s):
        return True
    # Dense punctuation / URL spam
    if s.count("http") >= 2 or s.count("/") > 12:
        return True
    return False


def filter_highlights(highlights: list) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()
    for h in highlights or []:
        if isinstance(h, dict):
            text = (h.get("quote") or h.get("text") or "").strip()
            row = dict(h)
        else:
            text = str(h).strip()
            row = {"text": text, "quote": text[:200], "method": "extractive"}
        if not text or is_garbled_highlight(text):
            continue
        key = text[:80].lower()
        if key in seen:
            continue
        seen.add(key)
        row["text"] = text
        if not row.get("quote"):
            row["quote"] = text[:200]
        out.append(row)
    return out


def extractive_highlights(text: str, tickers: list[str], max_bullets: int = 6) -> list[dict]:
    """Deterministic fallback: sentences mentioning universe tickers or key claims."""
    sentences = re.split(r"(?<=[.!?])\s+", text)
    bullets: list[dict] = []
    seen: set[str] = set()
    ticker_set = {t.upper() for t in tickers}
    for sent in sentences:
        s = sent.strip()
        if len(s) < 40 or len(s) > 320:
            continue
        if is_garbled_highlight(s):
            continue
        hit = None
        for t in ticker_set:
            if re.search(rf"\b{re.escape(t)}\b", s, re.I):
                hit = t
                break
        key_terms = ("moat", "capital allocation", "valuation", "margin", "growth", "risk", "catalyst")
        if not hit and not any(k in s.lower() for k in key_terms):
            continue
        key = s[:80]
        if key in seen:
            continue
        seen.add(key)
        bullets.append(
            {
                "text": s,
                "tickers": [hit] if hit else [],
                "quote": s[:200],
                "method": "extractive",
            }
        )
        if len(bullets) >= max_bullets:
            break
    return filter_highlights(bullets)


def extractive_summary(text: str, highlights: list[dict] | None = None, max_sentences: int = 3) -> str:
    """2–4 sentence blurb from highlights or early transcript prose."""
    parts: list[str] = []
    for h in highlights or []:
        if isinstance(h, dict):
            s = (h.get("text") or h.get("quote") or "").strip()
        else:
            s = str(h).strip()
        if s and not is_garbled_highlight(s) and s not in parts:
            parts.append(s)
        if len(parts) >= max_sentences:
            break
    if len(parts) < 2:
        for sent in re.split(r"(?<=[.!?])\s+", text[:6000]):
            s = sent.strip()
            if len(s) < 50 or len(s) > 280 or is_garbled_highlight(s):
                continue
            if s not in parts:
                parts.append(s)
            if len(parts) >= max_sentences:
                break
    return " ".join(parts[:max_sentences]).strip()


def should_summarize(episode: dict) -> bool:
    # Refresh when gated episode lacks summary even if highlights already exist.
    needs_summary = not (episode.get("summary") or "").strip()
    has_hl = bool(episode.get("highlights"))
    gated = bool(
        episode.get("has_pz_guest")
        or episode.get("has_officer_hit")
        or episode.get("tickers")
        or episode.get("positions")
        or episode.get("near_universe")
    )
    if not gated:
        return False
    if has_hl and not needs_summary:
        return False
    return True


def summarize_episode(episode: dict, text: str, *, use_llm: bool = False) -> tuple[list[dict], str]:
    tickers = [p.get("ticker") for p in (episode.get("positions") or []) if p.get("ticker")]
    tickers += list(episode.get("tickers") or [])
    tickers = sorted({str(t) for t in tickers if t})

    if use_llm and llm_call_gate is not None:
        try:
            policy = json.loads(
                (ROOT / "_system" / "config" / "llm_usage_policy.json").read_text(encoding="utf-8")
            )
            _model = llm_call_gate.resolve_model(policy, "podcast_highlights", reason="new_episode")
            # Gate records intent; actual LLM transport varies by environment.
            # Fall through to extractive until a transport is wired for this consumer.
            _ = _model
        except Exception:
            pass
    highlights = extractive_highlights(text, tickers)
    # Prefer existing clean highlights when regenerating summary only
    prior = filter_highlights(episode.get("highlights") or [])
    if prior and not highlights:
        highlights = prior
    elif prior and highlights:
        # Keep prior if new extractive is empty after filter; else merge unique
        merged = filter_highlights(prior + highlights)
        highlights = merged[:8] if merged else highlights
    summary = extractive_summary(text, highlights)
    return highlights, summary


def run(*, use_llm: bool = False, limit: int | None = None) -> dict:
    """Write highlights + summary to episode meta only. Vault catalog is rebuilt from meta."""
    root = podcasts_root(create=True)
    insights = load_json(root / "insights.json") or {"episodes": []}
    episodes = list(insights.get("episodes") or [])
    updated = 0
    for ep in episodes:
        if limit is not None and updated >= limit:
            break
        if not should_summarize(ep):
            continue
        eid = ep.get("episode_id")
        published = ep.get("published") or ""
        year = published[:4] if published[:4].isdigit() else datetime.now(timezone.utc).strftime("%Y")
        txt_path = root / "episodes" / year / f"{eid}.txt"
        if not txt_path.exists():
            matches = list((root / "episodes").rglob(f"{eid}.txt"))
            txt_path = matches[0] if matches else txt_path
        if not txt_path.exists():
            continue
        text = txt_path.read_text(encoding="utf-8", errors="ignore")
        highlights, summary = summarize_episode(ep, text, use_llm=use_llm)
        if not highlights and not summary:
            continue
        meta_path = txt_path.with_name(f"{eid}.meta.json")
        meta = load_json(meta_path) or {}
        if highlights:
            meta["highlights"] = highlights
        if summary:
            meta["summary"] = summary
        meta["highlighted_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        meta_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
        updated += 1

    return {"updated": updated, "episode_count": len(episodes), "meta_only": True}


def main() -> int:
    import argparse

    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--llm", action="store_true", help="Attempt gated LLM path (falls back extractive)")
    p.add_argument("--limit", type=int, default=None)
    args = p.parse_args()
    summary = run(use_llm=args.llm, limit=args.limit)
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

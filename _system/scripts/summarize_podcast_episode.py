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


def load_json(path: Path):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


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
    return bullets


def should_summarize(episode: dict) -> bool:
    if episode.get("highlights"):
        return False
    if episode.get("has_pz_guest") or episode.get("has_officer_hit"):
        return True
    if episode.get("tickers") or episode.get("positions"):
        return True
    if episode.get("near_universe"):
        return True
    return False


def summarize_episode(episode: dict, text: str, *, use_llm: bool = False) -> list[dict]:
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
    return extractive_highlights(text, tickers)


def run(*, use_llm: bool = False, limit: int | None = None) -> dict:
    """Write highlights to episode meta only. Vault catalog is rebuilt from meta."""
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
        highlights = summarize_episode(ep, text, use_llm=use_llm)
        if not highlights:
            continue
        meta_path = txt_path.with_name(f"{eid}.meta.json")
        meta = load_json(meta_path) or {}
        meta["highlights"] = highlights
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

#!/usr/bin/env python3
"""Is the local model actually able to answer the call the batch will make?

Exit 0 when yes, 1 when no. Written for analysis_supervisor.ps1, which needs a
readiness test it can act on before starting an eight-hour batch.

**Reachable is not the same as usable, and the difference cost a run.** On
2026-09-06 the supervisor's first health check was a GET on
http://localhost:1234/v1/models. It passed. Every chat call then failed with
HTTP 400: LM Studio's user-facing server on :1234 rejects
`response_format: {"type": "json_object"}` ("must be 'json_schema' or 'text'"),
while its internal llama-server on a rotating port accepts it. llm_local
prefers :1234 whenever /models answers and never falls back, so simply starting
that server -- which looks like fixing things -- is what broke them.

So this probe issues a real completion with the same `json_object` flag the
analyser uses. Anything less would have reported healthy through that failure.

    python _system/scripts/llm_ready.py --model qwen-gpu
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

import llm_local  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--model", default="qwen-gpu")
    p.add_argument("--timeout", type=int, default=120)
    args = p.parse_args()

    try:
        available = llm_local.models()
    except llm_local.LocalLLMUnavailable as exc:
        print(f"not ready: {exc}")
        return 1
    if not available:
        print("not ready: no model loaded")
        return 1

    # Deliberately NOT asserting that --model appears in that list. The two
    # endpoints name the same model differently: LM Studio's :1234 API reports
    # the load identifier ("qwen-gpu"), while its internal llama-server reports
    # the GGUF path it was loaded from. llama-server ignores the model field
    # anyway, which is why the batch has always passed an identifier the
    # discovered endpoint has never heard of. The completion below is the only
    # check that means anything.

    try:
        out = llm_local.complete(
            [{"role": "user", "content": 'Reply with the JSON object {"ok": true} and nothing else.'}],
            model=args.model, max_tokens=32, json_object=True,
            timeout=args.timeout, retries=0,
        )
    except Exception as exc:  # any transport or protocol failure means not ready
        print(f"not ready: {type(exc).__name__}: {str(exc)[:200]}")
        return 1

    # An empty completion is the reasoning-model failure llm_local documents:
    # the model spends its whole budget inside a <think> block and returns no
    # content. A batch against that produces nothing and looks like it is working.
    if not (out or "").strip():
        print("not ready: server answered with empty content")
        return 1

    print(f"ready: {args.model} answered {len(out)} chars")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

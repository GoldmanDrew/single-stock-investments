#!/usr/bin/env python3
"""Transport for a local OpenAI-compatible LLM server (LM Studio, llama.cpp).

This is the piece the repo has never had. `llm_call_gate` budgets and logs calls
but sends nothing; every `--llm` flag in this codebase resolves a model name and
then discards it, which is why all 4,215 podcast highlights are regex output.

Deliberately dumb and deliberately local. It speaks the OpenAI chat-completions
shape over HTTP to a server on this machine, so nothing leaves the box, there is
no API key, and no budget is consumed. The same code works against any runtime
that serves that shape -- LM Studio today, something else later -- because the
integration surface is a URL, not a vendor.

Why a local server rather than an in-process model: Smart App Control is
enforced on this host (`VerifiedAndReputablePolicyState = 1`), so unsigned
inference binaries are blocked outright. A signed application hosting the model
and exposing localhost is the path that does not require weakening that.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.request

DEFAULT_BASE = os.environ.get("LOCAL_LLM_BASE", "http://localhost:1234/v1")
# LM Studio's user-facing server needs no key; its internal llama-server does,
# and prints one on its command line. Either works.
DEFAULT_KEY = os.environ.get("LOCAL_LLM_KEY", "")
# A long transcript chunk plus a structured reply is slow. The read timeout is
# per-request and generous on purpose: a timeout costs the whole episode, while
# waiting costs only wall-clock on a batch job. Measured on this host with the
# CPU runtime, one 3,286-token map call took 243s -- so 600 is not paranoid.
DEFAULT_TIMEOUT = int(os.environ.get("LOCAL_LLM_TIMEOUT", "1800"))

# Qwen3.5 and its siblings are reasoning models: left alone they spend the whole
# token budget inside a <think> block and return an empty `content`. Measured on
# this host, same question and 200-token cap:
#
#   thinking on              77.4s   200 tokens, 677 chars of reasoning, EMPTY answer
#   enable_thinking: false    6.6s    16 tokens, answered correctly
#   "/no_think" suffix       61.5s   200 tokens, still reasoned -- does not work
#
# The model is no faster; it simply needs ~12x fewer tokens to answer. For
# structured extraction over hundreds of episodes that is the difference between
# feasible and not, and the reasoning adds nothing when the task is "copy the
# claim and its supporting quote out of this passage".
DISABLE_THINKING = os.environ.get("LOCAL_LLM_THINKING", "off").lower() != "on"


class LocalLLMUnavailable(RuntimeError):
    """The server is not reachable, or has no model loaded."""


def discover() -> tuple[str, str] | None:
    """Find LM Studio's llama-server by inspecting its command line.

    LM Studio assigns its internal server a fresh port and API key on every
    model load, so a base URL captured once goes stale the first time the model
    is reloaded -- which over a multi-day batch is a certainty, not a risk. The
    process itself is the reliable source of truth. Returns (base, key).

    The user-facing server on :1234 is stable and needs no key, but it has to be
    switched on in LM Studio; this makes the batch work either way.
    """
    if os.name != "nt":
        return None
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "(Get-CimInstance Win32_Process -Filter \"Name='llama-server.exe'\").CommandLine"],
            capture_output=True, text=True, timeout=60,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    port = re.search(r"--port\s+(\d+)", out or "")
    if not port:
        return None
    key = re.search(r"--api-key\s+(\S+)", out or "")
    return f"http://127.0.0.1:{port.group(1)}/v1", (key.group(1) if key else "")


def _headers() -> dict:
    head = {"Content-Type": "application/json"}
    if DEFAULT_KEY:
        head["Authorization"] = f"Bearer {DEFAULT_KEY}"
    return head


def _post(url: str, payload: dict, timeout: int) -> dict:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=_headers(), method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


_RESOLVED: dict[str, str] = {}


def _resolve(base: str) -> str:
    """Return a reachable base, rediscovering the rotating port if needed.

    Cached: discovery spawns a PowerShell process, and without this the batch
    paid that on every single call -- six spawns per episode, each logging a
    "rediscovered" line, for a port that had not moved.
    """
    global DEFAULT_KEY
    if base in _RESOLVED:
        return _RESOLVED[base]
    try:
        urllib.request.urlopen(
            urllib.request.Request(f"{base}/models", headers=_headers()), timeout=10
        ).read(1)
        _RESOLVED[base] = base
        return base
    except Exception:
        found = discover()
        if not found:
            raise LocalLLMUnavailable(f"no local LLM server at {base}, and none discoverable")
        DEFAULT_KEY = found[1]
        print(f"[llm_local] rediscovered server at {found[0]}", flush=True)
        _RESOLVED[base] = found[0]
        return found[0]


def models(base: str = DEFAULT_BASE, timeout: int = 15) -> list[str]:
    base = _resolve(base)
    try:
        req = urllib.request.Request(f"{base}/models", headers=_headers())
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            doc = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
        raise LocalLLMUnavailable(f"no local LLM server at {base}: {exc}") from exc
    return [m.get("id") for m in (doc.get("data") or []) if m.get("id")]


def complete(
    messages: list[dict],
    *,
    model: str | None = None,
    base: str = DEFAULT_BASE,
    temperature: float = 0.2,
    max_tokens: int = 2048,
    timeout: int = DEFAULT_TIMEOUT,
    json_object: bool = False,
    retries: int = 2,
) -> str:
    """One chat completion. Returns the assistant text.

    `temperature` defaults low: this job extracts claims that must be traceable
    to the transcript, so creativity is a defect rather than a feature.
    """
    base = _resolve(base)
    if model is None:
        available = models(base=base)
        if not available:
            raise LocalLLMUnavailable(f"{base} has no model loaded")
        model = available[0]

    payload: dict = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }
    if json_object:
        payload["response_format"] = {"type": "json_object"}
    if DISABLE_THINKING:
        payload["chat_template_kwargs"] = {"enable_thinking": False}

    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            doc = _post(f"{base}/chat/completions", payload, timeout)
            choices = doc.get("choices") or []
            if not choices:
                raise LocalLLMUnavailable(f"empty completion: {str(doc)[:200]}")
            msg = choices[0].get("message") or {}
            # If thinking slipped through anyway, the visible content can be
            # empty while the answer sits in reasoning_content. Prefer content,
            # fall back rather than returning "" and losing the episode.
            return (msg.get("content") or "").strip() or (msg.get("reasoning_content") or "")
        except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
            last = exc
            if attempt < retries:
                # A local server drops requests while it swaps models or reloads
                # a context. Short linear backoff; this is not a rate limit.
                time.sleep(5 * (attempt + 1))
    raise LocalLLMUnavailable(f"{base} failed after {retries + 1} attempts: {last}")


def extract_json(text: str) -> dict | None:
    """Pull the first JSON object out of a reply.

    Small local models wrap JSON in prose or a ```json fence even when asked not
    to, and a reasoning model may emit a <think> block first. Salvaging the
    object is cheaper than rejecting the episode and re-running it.
    """
    if not text:
        return None
    cleaned = text
    if "</think>" in cleaned:
        cleaned = cleaned.rsplit("</think>", 1)[1]
    cleaned = cleaned.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1]
        if "```" in cleaned:
            cleaned = cleaned.rsplit("```", 1)[0]
    cleaned = cleaned.strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    start = cleaned.find("{")
    if start < 0:
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(cleaned)):
        ch = cleaned[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(cleaned[start:i + 1])
                except json.JSONDecodeError:
                    break
    return salvage_truncated(cleaned)


def _objects_in(text: str) -> list[dict]:
    """Every balanced {...} in `text` that parses, in order."""
    # A stack of open-brace positions, not a single one: the records worth
    # salvaging are nested inside the outer object's "claims" array, so a walker
    # that only closes at depth 0 finds nothing when the outer brace never
    # closes -- which is exactly the truncated case this exists for.
    out: list[dict] = []
    stack: list[int] = []
    in_str = False
    esc = False
    for i, ch in enumerate(text):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            stack.append(i)
        elif ch == "}" and stack:
            start = stack.pop()
            try:
                out.append(json.loads(text[start:i + 1]))
            except json.JSONDecodeError:
                pass
    return out


def salvage_truncated(text: str) -> dict | None:
    """Recover the complete records from a reply that was cut mid-JSON.

    A local model asked for structured extraction will happily produce more than
    max_tokens allows, and the reply then ends mid-word with unbalanced braces.
    Brace-matching alone returns nothing, so the entire window's work is thrown
    away silently -- which is what made claim counts swing between 0 and 11 on
    the same episode and looked like model variance. It was not; it was this.

    The array elements before the cut are still complete and valid. Take those.
    A partial final record is dropped, which is correct: it is the one the model
    had not finished writing.
    """
    records = _objects_in(text)
    if not records:
        return None
    claims = [r for r in records if "claim" in r or "company" in r]
    numbers = [r for r in records if "value" in r and "what" in r]
    if not claims and not numbers:
        return None
    return {"claims": claims, "numbers": numbers, "_salvaged": True}


def main() -> int:
    import argparse

    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--base", default=DEFAULT_BASE)
    p.add_argument("--ping", action="store_true", help="List models and exit.")
    p.add_argument("--say", default=None, help="Send one prompt and print the reply.")
    args = p.parse_args()

    if args.ping or not args.say:
        try:
            found = models(base=args.base)
        except LocalLLMUnavailable as exc:
            print(f"UNAVAILABLE: {exc}")
            return 1
        print(json.dumps({"base": args.base, "models": found}, indent=2))
        return 0

    started = time.time()
    reply = complete([{"role": "user", "content": args.say}], base=args.base)
    print(reply)
    print(f"\n[{time.time() - started:.1f}s]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

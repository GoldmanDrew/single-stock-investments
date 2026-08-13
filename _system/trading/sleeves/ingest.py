"""HMAC ingest client matching dashboard/functions sleeve ingest."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import urllib.request
from typing import Any, Mapping


def sign_body(token: str, body: bytes, *, timestamp: str | None = None, nonce: str | None = None) -> dict[str, str]:
    ts = timestamp or str(int(time.time()))
    nonce_hex = nonce or os.urandom(16).hex()
    message = ts.encode() + b"\n" + nonce_hex.encode() + b"\n" + body
    signature = hmac.new(token.encode(), message, hashlib.sha256).hexdigest()
    return {
        "x-sleeve-timestamp": ts,
        "x-sleeve-nonce": nonce_hex,
        "x-sleeve-signature": signature,
    }


def post_ingest(url: str, token: str, payload: Mapping[str, Any], timeout: int = 20) -> dict[str, Any]:
    body = json.dumps(payload, separators=(",", ":")).encode()
    headers = {
        "content-type": "application/json",
        **sign_body(token, body),
    }
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode()
        return json.loads(raw) if raw else {}

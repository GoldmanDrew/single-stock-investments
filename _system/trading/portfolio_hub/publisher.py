from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time
import urllib.request
from typing import Any


def signed_headers(token: str, body: bytes, now: int | None = None) -> dict[str, str]:
    timestamp = str(now or int(time.time()))
    nonce = secrets.token_hex(16)
    signature = hmac.new(token.encode(), f"{timestamp}\n{nonce}\n".encode() + body, hashlib.sha256).hexdigest()
    return {
        "content-type": "application/json",
        "user-agent": "MagisPortfolioHub/1.0",
        "x-portfolio-timestamp": timestamp,
        "x-portfolio-nonce": nonce,
        "x-portfolio-signature": signature,
    }


def publish_payload(url: str, token: str, payload: dict[str, Any], timeout: int = 30) -> dict[str, Any]:
    if not url.startswith("https://") and not url.startswith("http://127.0.0.1"):
        raise ValueError("portfolio ingest requires HTTPS outside loopback")
    if len(token) < 32:
        raise ValueError("portfolio ingest token must be at least 32 characters")
    body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    request = urllib.request.Request(url, data=body, method="POST", headers=signed_headers(token, body))
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read())

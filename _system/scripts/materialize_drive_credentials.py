#!/usr/bin/env python3
"""Materialize Google Drive service-account credentials for cloud agents.

Cursor Cloud Agents inject ``GOOGLE_APPLICATION_CREDENTIALS_JSON`` (the key
contents). Drive Python clients need ``GOOGLE_APPLICATION_CREDENTIALS`` as a
file path. This writes that file and a small bash snippet the VM can source.

Unset credentials are not an error: Marvin cloud runs do not need Drive.
"""
from __future__ import annotations

import json
import os
import shlex
import stat
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOCAL_SECRETS_KEY = ROOT / "_secrets" / "google-service-account.json"


def default_key_path() -> Path:
    override = os.environ.get("SSI_DRIVE_CREDENTIALS_PATH")
    if override:
        return Path(override)
    return Path(os.environ.get("TMPDIR") or os.environ.get("TEMP") or "/tmp") / "ssi-google-service-account.json"


def default_snippet_path() -> Path:
    override = os.environ.get("SSI_CLOUD_ENV_SNIPPET")
    if override:
        return Path(override)
    return Path(os.environ.get("TMPDIR") or os.environ.get("TEMP") or "/tmp") / "ssi-cloud-env.sh"


def _write_snippet(snippet_path: Path, creds_path: Path) -> None:
    snippet_path.parent.mkdir(parents=True, exist_ok=True)
    payload = f"export GOOGLE_APPLICATION_CREDENTIALS={shlex.quote(str(creds_path))}\n"
    snippet_path.write_text(payload, encoding="utf-8")


def _parse_service_account(raw: str) -> dict:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit("GOOGLE_APPLICATION_CREDENTIALS_JSON is not valid JSON.") from exc
    if not isinstance(payload, dict):
        raise SystemExit("GOOGLE_APPLICATION_CREDENTIALS_JSON must be a service_account object.")
    if payload.get("type") != "service_account" and "client_email" not in payload:
        raise SystemExit("GOOGLE_APPLICATION_CREDENTIALS_JSON must be a service_account key.")
    return payload


def _chmod_private(path: Path) -> None:
    try:
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass


def materialize_drive_credentials(
    *,
    key_path: Path | None = None,
    snippet_path: Path | None = None,
    secrets_path: Path | None = None,
) -> dict:
    key_path = Path(key_path) if key_path else default_key_path()
    snippet_path = Path(snippet_path) if snippet_path else default_snippet_path()
    secrets_path = Path(secrets_path) if secrets_path is not None else LOCAL_SECRETS_KEY

    existing = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if existing and Path(existing).is_file():
        path = Path(existing)
        _write_snippet(snippet_path, path)
        return {"status": "existing", "path": str(path)}

    raw = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS_JSON")
    if raw and raw.strip():
        payload = _parse_service_account(raw)
        key_path.parent.mkdir(parents=True, exist_ok=True)
        key_path.write_text(json.dumps(payload), encoding="utf-8")
        _chmod_private(key_path)
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(key_path)
        _write_snippet(snippet_path, key_path)
        return {"status": "materialized", "path": str(key_path)}

    if secrets_path.is_file():
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(secrets_path)
        _write_snippet(snippet_path, secrets_path)
        return {"status": "local_secrets", "path": str(secrets_path)}

    return {"status": "unset", "path": None}


def resolve_credentials_file() -> str | None:
    result = materialize_drive_credentials()
    return result["path"]


def main() -> int:
    result = materialize_drive_credentials()
    print(f"drive_credentials={result['status']} path={result['path'] or 'unset'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

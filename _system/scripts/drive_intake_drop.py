#!/usr/bin/env python3
"""Drop a local PDF onto Shared Drive Admin/Intake/{Kind}/{TICKER}/.

Cloud Grok uses this after ``GOOGLE_APPLICATION_CREDENTIALS`` is materialized.
Drive Intake Sync then imports into the ticker folder. VIC does not go in
research-vault.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

KIND_FOLDERS = {
    "vic": "VIC",
    "research": "Research",
    "company": "Company",
    "activist_long": "Activist/Long",
    "activist_short": "Activist/Short",
}
KIND_ALIASES = {
    "vic": "vic",
    "research": "research",
    "company": "company",
    "activist_long": "activist_long",
    "activist/long": "activist_long",
    "activist_short": "activist_short",
    "activist/short": "activist_short",
}


def normalize_kind(kind: str) -> str | None:
    key = str(kind or "").strip().lower().replace("\\", "/")
    return KIND_ALIASES.get(key)


def resolve_repo_ticker(ticker: str, root: Path) -> str | None:
    raw = str(ticker or "").strip()
    if not raw or raw.startswith(("_", ".")):
        return None
    for candidate in (raw, raw.upper()):
        path = root / candidate
        if path.is_dir():
            return path.name
    return None


def plan_intake_drop(
    *,
    kind: str,
    ticker: str,
    pdf_path: Path,
    root: Path = ROOT,
) -> dict:
    pdf_path = Path(pdf_path)
    intake_kind = normalize_kind(kind)
    if intake_kind is None:
        return {"error": "unknown_kind", "kind": kind}
    resolved = resolve_repo_ticker(ticker, root)
    if resolved is None:
        return {"error": "unknown_ticker", "ticker": ticker}
    if not pdf_path.is_file():
        return {"error": "missing_file", "path": str(pdf_path)}
    if pdf_path.suffix.lower() != ".pdf":
        return {"error": "not_pdf", "path": str(pdf_path)}
    folder = KIND_FOLDERS[intake_kind]
    drive_rel = f"{folder}/{resolved}/{pdf_path.name}"
    return {
        "intake_kind": intake_kind,
        "ticker": resolved,
        "pdf_path": str(pdf_path),
        "drive_rel": drive_rel,
    }


def _intake_root_id() -> str:
    from drive_store_common import CONFIG_PATH, load_json

    config = load_json(CONFIG_PATH)
    folder_id = str((config.get("drive_intake") or {}).get("folder_id") or "")
    if not folder_id:
        raise SystemExit("drive_intake.folder_id missing in google_drive_config.json")
    return folder_id


def file_hashes(path: Path) -> tuple[str, str]:
    sha256 = hashlib.sha256()
    md5 = hashlib.md5(usedforsecurity=False)
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            sha256.update(chunk)
            md5.update(chunk)
    return sha256.hexdigest(), md5.hexdigest()


def find_duplicate_intake_pdf(
    items: list[dict],
    *,
    folder_id: str,
    filename: str,
    size_bytes: int,
    sha256: str,
    md5: str,
) -> dict | None:
    for item in items:
        if item.get("mimeType") != "application/pdf":
            continue
        if folder_id not in (item.get("parents") or []):
            continue
        properties = item.get("appProperties") or {}
        if properties.get("ssi_sha256") == sha256:
            return item
        if (
            item.get("name") == filename
            and str(item.get("size") or "") == str(size_bytes)
            and item.get("md5Checksum") == md5
        ):
            return item
    return None


def upload_intake_pdf(planned: dict, *, dry_run: bool = False) -> dict:
    from googleapiclient.http import MediaFileUpload

    from drive_store_common import (
        drive_service,
        ensure_folder_path,
        execute_with_retry,
        folder_id_by_parent_name,
        list_drive_items,
        now_iso,
    )

    root_id = _intake_root_id()
    folder_rel = str(Path(planned["drive_rel"]).parent).replace("\\", "/")
    pdf_path = Path(planned["pdf_path"])
    sha256, md5 = file_hashes(pdf_path)
    if dry_run:
        return {
            **planned,
            "dry_run": True,
            "drive_folder": folder_rel,
            "sha256": sha256,
            "uploaded_at": now_iso(),
        }

    service = drive_service()
    items = list_drive_items(service, [root_id])
    existing = folder_id_by_parent_name(items)
    folder_id = ensure_folder_path(service, root_id, folder_rel, False, existing)
    duplicate = find_duplicate_intake_pdf(
        items,
        folder_id=folder_id,
        filename=pdf_path.name,
        size_bytes=pdf_path.stat().st_size,
        sha256=sha256,
        md5=md5,
    )
    if duplicate:
        return {
            **planned,
            "status": "already_present",
            "drive_file_id": duplicate.get("id"),
            "drive_web_view_link": duplicate.get("webViewLink"),
            "drive_folder": folder_rel,
            "sha256": sha256,
            "uploaded_at": now_iso(),
        }
    media = MediaFileUpload(str(pdf_path), mimetype="application/pdf", resumable=True)
    created = execute_with_retry(
        service.files().create(
            body={
                "name": pdf_path.name,
                "parents": [folder_id],
                "mimeType": "application/pdf",
                "appProperties": {
                    "ssi_sha256": sha256,
                    "ssi_intake_kind": planned["intake_kind"],
                    "ssi_ticker": planned["ticker"],
                },
            },
            media_body=media,
            fields="id,name,webViewLink,parents",
            supportsAllDrives=True,
        )
    )
    return {
        **planned,
        "status": "uploaded",
        "drive_file_id": created.get("id"),
        "drive_web_view_link": created.get("webViewLink"),
        "drive_folder": folder_rel,
        "sha256": sha256,
        "uploaded_at": now_iso(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Upload a PDF to Shared Drive Admin/Intake.")
    parser.add_argument("pdf", help="Local PDF path")
    parser.add_argument("--kind", default="VIC", help="VIC, Research, Company, Activist/Long, Activist/Short")
    parser.add_argument("--ticker", required=True, help="Repo ticker folder name")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    planned = plan_intake_drop(kind=args.kind, ticker=args.ticker, pdf_path=Path(args.pdf), root=ROOT)
    if planned.get("error"):
        print(json.dumps(planned, indent=2))
        return 2
    result = upload_intake_pdf(planned, dry_run=args.dry_run)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Shared Google Drive helpers for the PDF store scripts."""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = ROOT / "dashboard" / "data" / "document_registry.json"
CONFIG_PATH = ROOT / "_system" / "reference" / "document-store" / "google_drive_config.json"
FOLDER_INDEX_PATH = ROOT / "_system" / "reference" / "document-store" / "drive_folder_index.json"
FOLDER_MIME = "application/vnd.google-apps.folder"
DRIVE_SCOPE = ["https://www.googleapis.com/auth/drive"]
DRIVE_READONLY_SCOPE = ["https://www.googleapis.com/auth/drive.readonly"]


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def drive_service(readonly: bool = False):
    from materialize_drive_credentials import resolve_credentials_file

    creds_path = resolve_credentials_file()
    if not creds_path:
        raise SystemExit(
            "Set GOOGLE_APPLICATION_CREDENTIALS to a service-account JSON file, "
            "or GOOGLE_APPLICATION_CREDENTIALS_JSON (Cloud Agent secret), "
            "or place the key at _secrets/google-service-account.json."
        )
    scopes = DRIVE_READONLY_SCOPE if readonly else DRIVE_SCOPE
    creds = service_account.Credentials.from_service_account_file(creds_path, scopes=scopes)
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def drive_quote(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace("'", "\\'")


def execute_with_retry(request, attempts: int = 6):
    delay = 2.0
    for attempt in range(attempts):
        try:
            return request.execute()
        except Exception as exc:
            retryable = True
            if isinstance(exc, HttpError):
                retryable = exc.resp.status in {403, 429, 500, 502, 503, 504}
            if not retryable or attempt == attempts - 1:
                raise
            time.sleep(delay)
            delay = min(delay * 2, 60.0)


def configured_root_ids(config: dict) -> list[str]:
    ids: list[str] = []
    for root in (config.get("drive_roots") or {}).values():
        root_id = root.get("folder_id")
        if root_id and root_id not in ids:
            ids.append(root_id)
    return ids


def drive_ids_for_roots(service, root_ids: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for root_id in root_ids:
        meta = execute_with_retry(service.files().get(fileId=root_id, fields="id,name,driveId", supportsAllDrives=True))
        drive_id = meta.get("driveId")
        if not drive_id:
            raise SystemExit(f"Root {root_id} is not inside a Shared Drive.")
        out[root_id] = drive_id
    return out


DRIVE_ITEM_FIELDS = (
    "nextPageToken,files("
    "id,name,size,mimeType,webViewLink,webContentLink,appProperties,parents,createdTime,modifiedTime"
    ")"
)
DRIVE_PDF_OR_FOLDER_QUERY = f"(mimeType = 'application/pdf' or mimeType = '{FOLDER_MIME}') and trashed = false"


def list_shared_drive_items(service, drive_ids: list[str], items: dict[str, dict]) -> None:
    for drive_id in sorted(set(drive_ids)):
        page_token = None
        while True:
            res = execute_with_retry(service.files().list(
                corpora="drive",
                driveId=drive_id,
                includeItemsFromAllDrives=True,
                supportsAllDrives=True,
                q=DRIVE_PDF_OR_FOLDER_QUERY,
                fields=DRIVE_ITEM_FIELDS,
                pageSize=1000,
                pageToken=page_token,
            ))
            for item in res.get("files") or []:
                items[item["id"]] = item
            page_token = res.get("nextPageToken")
            if not page_token:
                break


def list_folder_tree_items(service, root_ids: list[str], items: dict[str, dict]) -> None:
    queue = list(root_ids)
    seen_folders: set[str] = set()
    while queue:
        parent_id = queue.pop(0)
        if parent_id in seen_folders:
            continue
        seen_folders.add(parent_id)
        page_token = None
        while True:
            res = execute_with_retry(service.files().list(
                includeItemsFromAllDrives=True,
                supportsAllDrives=True,
                q=f"'{drive_quote(parent_id)}' in parents and {DRIVE_PDF_OR_FOLDER_QUERY}",
                fields=DRIVE_ITEM_FIELDS,
                pageSize=1000,
                pageToken=page_token,
            ))
            for item in res.get("files") or []:
                items[item["id"]] = item
                if item.get("mimeType") == FOLDER_MIME:
                    queue.append(item["id"])
            page_token = res.get("nextPageToken")
            if not page_token:
                break


def list_drive_items(service, root_ids: list[str]) -> list[dict]:
    items: dict[str, dict] = {}
    shared_drive_ids: list[str] = []
    folder_root_ids: list[str] = []
    for root_id in root_ids:
        meta = execute_with_retry(service.files().get(
            fileId=root_id,
            fields="id,name,driveId,parents",
            supportsAllDrives=True,
        ))
        drive_id = meta.get("driveId")
        if drive_id and not meta.get("parents"):
            shared_drive_ids.append(drive_id)
        else:
            folder_root_ids.append(root_id)
    list_shared_drive_items(service, shared_drive_ids, items)
    list_folder_tree_items(service, folder_root_ids, items)
    return list(items.values())


def build_folder_paths(items: list[dict], root_ids: list[str]) -> dict[str, str]:
    folders = {item["id"]: item for item in items if item.get("mimeType") == FOLDER_MIME}
    root_set = set(root_ids)
    memo: dict[str, str] = {}

    def path_for(folder_id: str) -> str:
        if folder_id in memo:
            return memo[folder_id]
        if folder_id in root_set:
            memo[folder_id] = ""
            return ""
        item = folders.get(folder_id)
        if not item:
            memo[folder_id] = ""
            return ""
        parents = item.get("parents") or []
        parent = parents[0] if parents else ""
        if parent in root_set or not parent:
            value = item.get("name") or ""
        else:
            parent_path = path_for(parent)
            value = "/".join([p for p in [parent_path, item.get("name") or ""] if p])
        memo[folder_id] = value
        return value

    for folder_id in folders:
        path_for(folder_id)
    return memo


def folder_id_by_parent_name(items: list[dict]) -> dict[tuple[str, str], str]:
    out: dict[tuple[str, str], str] = {}
    for item in items:
        if item.get("mimeType") != FOLDER_MIME:
            continue
        for parent in item.get("parents") or []:
            out[(parent, item.get("name") or "")] = item["id"]
    return out


def ensure_folder(service, parent_id: str, name: str, dry_run: bool, existing: dict[tuple[str, str], str]) -> str:
    if (parent_id, name) in existing:
        return existing[(parent_id, name)]
    if dry_run:
        folder_id = f"dry-run:{parent_id}/{name}"
        existing[(parent_id, name)] = folder_id
        return folder_id
    meta = {"name": name, "mimeType": FOLDER_MIME, "parents": [parent_id]}
    created = execute_with_retry(service.files().create(body=meta, fields="id", supportsAllDrives=True))
    existing[(parent_id, name)] = created["id"]
    return created["id"]


def ensure_folder_path(
    service,
    root_id: str,
    folder_path: str,
    dry_run: bool,
    existing: dict[tuple[str, str], str],
) -> str:
    parent = root_id
    for part in [p for p in str(folder_path or "").split("/") if p]:
        parent = ensure_folder(service, parent, part, dry_run, existing)
    return parent


def item_paths(items: list[dict], root_ids: list[str]) -> tuple[dict[str, str], dict[str, list[str]]]:
    folder_paths = build_folder_paths(items, root_ids)
    paths: dict[str, str] = {}
    child_ids_by_folder_path: dict[str, list[str]] = {}
    for item in items:
        parents = item.get("parents") or []
        parent_paths = [folder_paths.get(parent, "") for parent in parents]
        parent_path = parent_paths[0] if parent_paths else ""
        paths[item["id"]] = "/".join([p for p in [parent_path, item.get("name") or ""] if p])
        for p in parent_paths:
            child_ids_by_folder_path.setdefault(p, []).append(item["id"])
    return paths, child_ids_by_folder_path


def web_folder_url(folder_id: str | None) -> str | None:
    return f"https://drive.google.com/drive/folders/{folder_id}" if folder_id else None

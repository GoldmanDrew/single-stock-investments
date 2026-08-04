#!/usr/bin/env python3
"""Upload registered PDFs to their configured Google Drive roots."""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from google.oauth2 import service_account
from googleapiclient.errors import HttpError
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = ROOT / "dashboard" / "data" / "document_registry.json"
SCOPES = ["https://www.googleapis.com/auth/drive"]
FOLDER_MIME = "application/vnd.google-apps.folder"
_THREAD_LOCAL = threading.local()
TRANSIENT_DRIVE_STATUS = {429, 500, 502, 503, 504}


def execute_with_retry(request, *, label: str, attempts: int = 5):
    """Retry only transient Drive API failures with bounded exponential backoff."""
    for attempt in range(1, attempts + 1):
        try:
            return request.execute()
        except HttpError as exc:
            if exc.resp.status not in TRANSIENT_DRIVE_STATUS or attempt == attempts:
                raise
            delay = min(30, 2 ** (attempt - 1))
            print(
                f"Transient Drive HTTP {exc.resp.status} during {label}; "
                f"retrying in {delay}s ({attempt}/{attempts})...",
                flush=True,
            )
            time.sleep(delay)


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_registry() -> dict:
    if not REGISTRY_PATH.exists():
        raise SystemExit("document_registry.json is missing. Run build_document_registry.py first.")
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def save_registry(registry: dict) -> None:
    registry["generated_at"] = now_iso()
    docs = registry.get("documents") or []
    registry.setdefault("summary", {})["uploaded_count"] = sum(1 for d in docs if d.get("drive_web_view_link"))
    registry["summary"]["pending_upload_count"] = sum(1 for d in docs if not d.get("drive_web_view_link"))
    REGISTRY_PATH.write_text(json.dumps(registry, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def drive_service():
    creds_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if not creds_path:
        raise SystemExit("Set GOOGLE_APPLICATION_CREDENTIALS to a service-account JSON file with access to the Shared Drive.")
    creds = service_account.Credentials.from_service_account_file(creds_path, scopes=SCOPES)
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def thread_drive_service():
    service = getattr(_THREAD_LOCAL, "drive_service", None)
    if service is None:
        service = drive_service()
        _THREAD_LOCAL.drive_service = service
    return service


def drive_quote(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace("'", "\\'")


def preflight_root(service, root_id: str, root_key: str) -> None:
    try:
        meta = execute_with_retry(
            service.files().get(
                fileId=root_id,
                fields="id,name,mimeType,driveId,capabilities",
                supportsAllDrives=True,
            ),
            label=f"preflight Drive root {root_key}",
        )
    except HttpError as exc:
        if exc.resp.status == 404:
            raise SystemExit(
                f"Drive root '{root_key}' ({root_id}) is not visible to the service account. "
                "Share that folder/shared drive with the service account, or update google_drive_config.json."
            ) from exc
        raise
    if not meta.get("driveId"):
        raise SystemExit(
            f"Drive root '{root_key}' ({root_id}, {meta.get('name')}) is a regular My Drive folder. "
            "Service accounts have no Drive storage quota and can upload PDFs only into a Shared Drive, "
            "or via user OAuth/domain-wide delegation. Move/create this folder inside a Shared Drive and share "
            "that Shared Drive with the service account."
        )
    caps = meta.get("capabilities") or {}
    if caps.get("canAddChildren") is False:
        raise SystemExit(
            f"Drive root '{root_key}' ({root_id}, {meta.get('name')}) is visible but not writable by the service account."
        )


def preflight_roots(service, docs: list[dict], root_filter: str | None) -> None:
    checked: set[tuple[str, str]] = set()
    for doc in docs:
        if root_filter and doc.get("drive_root_key") != root_filter:
            continue
        key = doc.get("drive_root_key") or "unknown"
        root_id = doc.get("drive_root_folder_id")
        if not root_id or (key, root_id) in checked:
            continue
        preflight_root(service, root_id, key)
        checked.add((key, root_id))


class DriveIndex:
    def __init__(self) -> None:
        self.by_id: dict[str, dict] = {}
        self.pdf_by_document_id: dict[str, dict] = {}
        self.pdf_by_sha: dict[str, dict] = {}
        self.pdf_by_name_size: dict[tuple[str, str], dict] = {}
        self.pdf_by_parent_name_size: dict[tuple[str, str, str], dict] = {}
        self.folder_by_parent_name: dict[tuple[str, str], str] = {}

    @classmethod
    def build(cls, service, root_ids: list[str]) -> "DriveIndex":
        index = cls()
        drive_ids: set[str] = set()
        print(f"Building Drive cache for {len(root_ids)} root(s)...", flush=True)
        for root_id in root_ids:
            meta = execute_with_retry(
                service.files().get(fileId=root_id, fields="id,driveId", supportsAllDrives=True),
                label=f"read Drive root {root_id}",
            )
            if meta.get("driveId"):
                drive_ids.add(meta["driveId"])
        for drive_id in sorted(drive_ids):
            page_token = None
            while True:
                res = service.files().list(
                    corpora="drive",
                    driveId=drive_id,
                    includeItemsFromAllDrives=True,
                    supportsAllDrives=True,
                    q=f"(mimeType = 'application/pdf' or mimeType = '{FOLDER_MIME}') and trashed = false",
                    fields="nextPageToken,files(id,name,size,mimeType,webViewLink,webContentLink,appProperties,parents)",
                    pageSize=1000,
                    pageToken=page_token,
                )
                res = execute_with_retry(res, label=f"index Shared Drive {drive_id}")
                for file in res.get("files") or []:
                    index.add(file)
                page_token = res.get("nextPageToken")
                if not page_token:
                    break
        print(
            "Drive cache ready "
            f"({len(index.folder_by_parent_name)} folders, {len(index.pdf_by_name_size)} PDFs with size keys).",
            flush=True,
        )
        return index

    def add(self, file: dict) -> None:
        file_id = file.get("id")
        if file_id:
            self.by_id[file_id] = file
        parents = file.get("parents") or []
        name = file.get("name") or ""
        mime = file.get("mimeType")
        if mime == FOLDER_MIME:
            for parent in parents:
                self.folder_by_parent_name[(parent, name)] = file_id
            return
        if mime != "application/pdf":
            return
        props = file.get("appProperties") or {}
        if props.get("document_id"):
            self.pdf_by_document_id[props["document_id"]] = file
        if props.get("sha256"):
            self.pdf_by_sha[props["sha256"]] = file
        size = str(file.get("size") or "")
        if name and size:
            self.pdf_by_name_size[(name, size)] = file
            for parent in parents:
                self.pdf_by_parent_name_size[(parent, name, size)] = file

    def add_folder(self, parent_id: str, name: str, folder_id: str) -> None:
        self.folder_by_parent_name[(parent_id, name)] = folder_id
        self.by_id[folder_id] = {"id": folder_id, "name": name, "mimeType": FOLDER_MIME, "parents": [parent_id]}

    def find_folder(self, parent_id: str, name: str) -> str | None:
        return self.folder_by_parent_name.get((parent_id, name))

    def find_pdf(self, folder_id: str, doc: dict) -> dict | None:
        app_id = doc.get("document_id")
        sha = doc.get("sha256")
        name = Path(doc["local_pdf_path"]).name
        expected_size = str(doc.get("size_bytes") or "")
        if app_id and app_id in self.pdf_by_document_id:
            return self.pdf_by_document_id[app_id]
        if sha and sha in self.pdf_by_sha:
            return self.pdf_by_sha[sha]
        if folder_id and expected_size:
            match = self.pdf_by_parent_name_size.get((folder_id, name, expected_size))
            if match:
                return match
        if expected_size:
            return self.pdf_by_name_size.get((name, expected_size))
        return None


def find_child_folder(service, parent_id: str, name: str) -> str | None:
    q = (
        f"'{parent_id}' in parents and "
        "mimeType = 'application/vnd.google-apps.folder' and "
        f"name = '{drive_quote(name)}' and trashed = false"
    )
    res = service.files().list(
        q=q,
        fields="files(id,name)",
        supportsAllDrives=True,
        includeItemsFromAllDrives=True,
        pageSize=10,
    ).execute()
    files = res.get("files") or []
    return files[0]["id"] if files else None


def ensure_folder(service, parent_id: str, name: str, dry_run: bool, index: DriveIndex | None = None) -> str:
    if dry_run:
        return f"dry-run-folder:{parent_id}/{name}"
    if index:
        existing = index.find_folder(parent_id, name)
        if existing:
            return existing
    if not index:
        existing = find_child_folder(service, parent_id, name)
        if existing:
            return existing
    meta = {
        "name": name,
        "mimeType": FOLDER_MIME,
        "parents": [parent_id],
    }
    created = service.files().create(
        body=meta,
        fields="id",
        supportsAllDrives=True,
    ).execute()
    if index:
        index.add_folder(parent_id, name, created["id"])
    return created["id"]


def ensure_folder_path(service, root_id: str, folder_path: str, dry_run: bool, index: DriveIndex | None = None) -> str:
    parent = root_id
    for part in [p for p in str(folder_path or "").split("/") if p]:
        parent = ensure_folder(service, parent, part, dry_run, index)
    return parent


def find_existing_pdf(service, folder_id: str, doc: dict) -> dict | None:
    name = Path(doc["local_pdf_path"]).name
    app_id = doc["document_id"]
    q = (
        f"'{folder_id}' in parents and "
        f"name = '{drive_quote(name)}' and "
        "mimeType = 'application/pdf' and trashed = false"
    )
    res = service.files().list(
        q=q,
        fields="files(id,name,webViewLink,webContentLink,appProperties)",
        supportsAllDrives=True,
        includeItemsFromAllDrives=True,
        pageSize=20,
    ).execute()
    for f in res.get("files") or []:
        if (f.get("appProperties") or {}).get("document_id") == app_id:
            return f
    files = res.get("files") or []
    return files[0] if files else None


def find_existing_pdf_anywhere(service, doc: dict) -> dict | None:
    name = Path(doc["local_pdf_path"]).name
    app_id = doc["document_id"]
    expected_size = str(doc.get("size_bytes") or "")
    q = (
        f"name = '{drive_quote(name)}' and "
        "mimeType = 'application/pdf' and trashed = false"
    )
    page_token = None
    while True:
        res = service.files().list(
            q=q,
            fields="nextPageToken,files(id,name,size,webViewLink,webContentLink,appProperties)",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
            pageSize=100,
            pageToken=page_token,
        ).execute()
        size_match = None
        for f in res.get("files") or []:
            props = f.get("appProperties") or {}
            if props.get("document_id") == app_id:
                return f
            if expected_size and str(f.get("size")) == expected_size:
                size_match = size_match or f
        if size_match:
            return size_match
        page_token = res.get("nextPageToken")
        if not page_token:
            return None


def find_existing_pdf_by_sha(service, doc: dict) -> dict | None:
    sha = doc.get("sha256")
    if not sha:
        return None
    q = (
        "mimeType = 'application/pdf' and trashed = false and "
        f"appProperties has {{ key='sha256' and value='{drive_quote(sha)}' }}"
    )
    res = service.files().list(
        q=q,
        fields="files(id,name,size,webViewLink,webContentLink,appProperties)",
        supportsAllDrives=True,
        includeItemsFromAllDrives=True,
        pageSize=10,
    ).execute()
    files = res.get("files") or []
    return files[0] if files else None


def created_file_body(doc: dict, folder_id: str) -> tuple[dict, MediaFileUpload]:
    local_path = ROOT / doc["local_pdf_path"]
    media = MediaFileUpload(str(local_path), mimetype="application/pdf", resumable=True)
    body = {
        "name": local_path.name,
        "parents": [folder_id],
        "appProperties": {
            "document_id": doc["document_id"],
            "sha256": doc["sha256"],
            "source_type": doc.get("source_type") or "pdf",
        },
    }
    return body, media


def create_pdf_file(service, doc: dict, folder_id: str) -> dict:
    body, media = created_file_body(doc, folder_id)
    return service.files().create(
        body=body,
        media_body=media,
        fields="id,name,size,mimeType,webViewLink,webContentLink,appProperties,parents",
        supportsAllDrives=True,
    ).execute()


def apply_existing_file(doc: dict, file: dict, status: str = "linked_existing") -> dict:
    doc["drive_file_id"] = file.get("id")
    doc["drive_web_view_link"] = file.get("webViewLink")
    doc["drive_web_content_link"] = file.get("webContentLink")
    doc["upload_status"] = status
    return doc


def apply_created_file(doc: dict, file: dict) -> dict:
    doc["drive_file_id"] = file.get("id")
    doc["drive_web_view_link"] = file.get("webViewLink")
    doc["drive_web_content_link"] = file.get("webContentLink")
    doc["upload_status"] = "uploaded"
    return doc


def upload_doc(service, doc: dict, dry_run: bool, index: DriveIndex | None = None) -> dict:
    root_folder_id = doc.get("drive_root_folder_id")
    if not root_folder_id:
        raise SystemExit(f"Document {doc.get('local_pdf_path')} has no drive_root_folder_id.")
    folder_id = ensure_folder_path(service, root_folder_id, doc.get("drive_folder_path"), dry_run, index)
    if dry_run:
        return {**doc, "drive_folder_id": folder_id, "upload_status": "dry_run_pending_upload"}
    doc["drive_folder_id"] = folder_id
    existing = index.find_pdf(folder_id, doc) if index else None
    if not existing and not dry_run:
        existing = find_existing_pdf_by_sha(service, doc)
    if not existing and not dry_run:
        existing = find_existing_pdf(service, folder_id, doc)
    if not existing and not dry_run:
        existing = find_existing_pdf_anywhere(service, doc)
    if existing:
        return apply_existing_file(doc, existing)
    created = create_pdf_file(service, doc, folder_id)
    apply_created_file(doc, created)
    if index:
        index.add(created)
    return doc


def pending_docs(docs: list[dict], root_key: str | None, force: bool) -> list[dict]:
    out = []
    for doc in docs:
        if root_key and doc.get("drive_root_key") != root_key:
            continue
        if doc.get("drive_web_view_link") and not force:
            continue
        out.append(doc)
    return out


def upload_file_worker(doc: dict) -> dict:
    service = thread_drive_service()
    folder_id = doc.get("drive_folder_id")
    if not folder_id:
        raise RuntimeError(f"Document {doc.get('local_pdf_path')} has no resolved Drive folder.")
    return create_pdf_file(service, doc, folder_id)


def sync_docs_parallel(
    service,
    registry: dict,
    docs: list[dict],
    dry_run: bool,
    index: DriveIndex | None,
    save_every: int,
    workers: int,
) -> int:
    if dry_run or workers <= 1:
        count = 0
        for doc in docs:
            upload_doc(service, doc, dry_run, index)
            count += 1
            if not dry_run and save_every and count % save_every == 0:
                save_registry(registry)
                print(f"Saved progress after {count} document(s).", flush=True)
        return count

    count = 0
    upload_queue: list[dict] = []
    for scanned, doc in enumerate(docs, start=1):
        if scanned % 500 == 0:
            print(f"Prepared {scanned}/{len(docs)} document(s) for upload/link.", flush=True)
        root_folder_id = doc.get("drive_root_folder_id")
        if not root_folder_id:
            raise SystemExit(f"Document {doc.get('local_pdf_path')} has no drive_root_folder_id.")
        folder_id = ensure_folder_path(service, root_folder_id, doc.get("drive_folder_path"), dry_run, index)
        doc["drive_folder_id"] = folder_id
        existing = index.find_pdf(folder_id, doc) if index else None
        if existing:
            apply_existing_file(doc, existing)
            count += 1
            if save_every and count % save_every == 0:
                save_registry(registry)
                print(f"Saved progress after {count} document(s).", flush=True)
        else:
            upload_queue.append(doc)

    if upload_queue:
        print(f"Uploading {len(upload_queue)} new PDF(s) with {workers} worker(s).", flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_doc = {executor.submit(upload_file_worker, doc): doc for doc in upload_queue}
        for future in concurrent.futures.as_completed(future_to_doc):
            doc = future_to_doc[future]
            created = future.result()
            apply_created_file(doc, created)
            if index:
                index.add(created)
            count += 1
            if save_every and count % save_every == 0:
                save_registry(registry)
                print(f"Saved progress after {count} document(s).", flush=True)
    return count


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="Upload at most N pending documents.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true", help="Re-check/upload documents even when a Drive link is already present.")
    parser.add_argument("--save-every", type=int, default=25, help="Persist registry progress after every N uploaded/linked documents.")
    parser.add_argument("--workers", type=int, default=1, help="Parallel upload workers for new PDFs after dedup checks.")
    parser.add_argument("--root-key", choices=["hedge_fund_letters", "general_pdfs"], help="Restrict sync to one configured Drive root.")
    args = parser.parse_args()

    registry = load_registry()
    service = None if args.dry_run else drive_service()
    docs = registry.get("documents") or []
    if service:
        preflight_roots(service, docs, args.root_key)
    root_ids = []
    if service:
        for doc in docs:
            if args.root_key and doc.get("drive_root_key") != args.root_key:
                continue
            root_id = doc.get("drive_root_folder_id")
            if root_id and root_id not in root_ids:
                root_ids.append(root_id)
    index = DriveIndex.build(service, root_ids) if service and root_ids else None

    selected_docs = pending_docs(docs, args.root_key, args.force)
    if args.limit:
        selected_docs = selected_docs[: args.limit]
    count = sync_docs_parallel(
        service,
        registry,
        selected_docs,
        args.dry_run,
        index,
        args.save_every,
        max(1, args.workers),
    )
    if not args.dry_run:
        save_registry(registry)
    print(f"{'Checked' if args.dry_run else 'Uploaded/linked'} {count} document(s).")


if __name__ == "__main__":
    main()

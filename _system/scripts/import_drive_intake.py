#!/usr/bin/env python3
"""Import manually uploaded PDFs from Google Drive intake folders into the repo.

Configured intake root (google_drive_config.json drive_intake.folder_id) should be
Admin/Intake on the Shared Drive. Relative paths from that root:

  VIC/{TICKER}.pdf
  Research/{TICKER}.pdf
  Company/{TICKER}.pdf

Also accepted (absolute-style paths if the scan root is higher up):
  Admin/Intake/VIC/{TICKER}.pdf
  Admin/VIC/{TICKER}.pdf

Bare / arbitrary filenames (e.g. VIC/163625.pdf) are accepted when PDF text
uniquely identifies a repo ticker. Successful imports may be moved under
Admin/Intake/{Kind}/{TICKER}/ on Drive.

Use --ensure-folders to create VIC/Research/Company/Activist drop folders
under the configured intake root before scanning.

Canonical repo destinations:
  {TICKER}/third-party-analyses/vic/*.pdf
  {TICKER}/third-party-analyses/drive-intake/*.pdf
  {TICKER}/investor-documents/drive-intake/*.pdf
"""
from __future__ import annotations

import argparse
import hashlib
import io
import re
import sys
from pathlib import Path

from googleapiclient.http import MediaIoBaseDownload

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parents[1]
MANIFEST_PATH = ROOT / "_system" / "data" / "drive_intake_manifest.json"
REPORT_PATH = ROOT / "_system" / "reference" / "document-store" / "drive_intake_latest.json"
TICKER_RE = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,24}$")
PDF_MIME = "application/pdf"
INTAKE_PREFIX = "Admin"
LEGACY_INTAKE_PREFIX = "Admin/Intake"
INTAKE_TYPES = {
    "vic": "VIC",
    "research": "Research",
    "company": "Company",
    "activist_long": "Activist/Long",
    "activist_short": "Activist/Short",
}
# Paths relative to drive_intake.folder_id (Admin/Intake). Do not prepend Admin/
# here or --ensure-folders nests Admin/VIC inside Intake/VIC.
INTAKE_FOLDER_PATHS = {
    intake_kind: folder_name
    for intake_kind, folder_name in INTAKE_TYPES.items()
}
ACCEPTED_INTAKE_PREFIXES = (INTAKE_PREFIX, LEGACY_INTAKE_PREFIX, "")

sys.path.insert(0, str(SCRIPTS))
from drive_store_common import (  # noqa: E402
    CONFIG_PATH,
    drive_service,
    ensure_folder_path,
    execute_with_retry,
    folder_id_by_parent_name,
    item_paths,
    list_drive_items,
    load_json,
    now_iso,
    web_folder_url,
    write_json,
)
from intake_ticker_resolve import resolve_ticker_from_pdf  # noqa: E402
from third_party_inventory import write_inventory  # noqa: E402

try:
    from activist_common import load_ticker_index, save_ticker_index, upsert_report  # noqa: E402
    from extract_activist_text import extract_ticker_activist_text  # noqa: E402
except ImportError:
    load_ticker_index = save_ticker_index = upsert_report = None  # type: ignore
    extract_ticker_activist_text = None  # type: ignore


def rel(path: Path) -> str:
    return str(path.relative_to(ROOT)).replace("\\", "/")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_filename(value: str, fallback: str = "document.pdf") -> str:
    name = Path(value or fallback).name
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "-", name).strip(" .-")
    if not name.lower().endswith(".pdf"):
        name = f"{name or Path(fallback).stem}.pdf"
    return name[:140] or fallback


def normalize_ticker(value: str) -> str | None:
    ticker = str(value or "").strip().upper()
    return ticker if TICKER_RE.match(ticker) and (ROOT / ticker).is_dir() else None


def infer_ticker_from_name(name: str) -> str | None:
    stem = Path(name).stem.upper()
    for token in re.split(r"[\s_\-]+", stem):
        ticker = normalize_ticker(token)
        if ticker:
            return ticker
    return None


def intake_path_parts(path: str) -> tuple[str, list[str], str] | None:
    parts = [p for p in path.split("/") if p]
    if len(parts) >= 4 and parts[0] == "Admin" and parts[1].lower() == "activist":
        side = parts[2].lower()
        if side in ("long", "short"):
            return f"activist_{side}", parts[3:], INTAKE_PREFIX
    if len(parts) >= 3 and parts[0] == "Admin" and parts[1].lower() in INTAKE_TYPES:
        return parts[1].lower(), parts[2:], INTAKE_PREFIX
    if len(parts) >= 4 and parts[0:2] == ["Admin", "Intake"] and parts[2].lower() in INTAKE_TYPES:
        return parts[2].lower(), parts[3:], LEGACY_INTAKE_PREFIX
    if len(parts) >= 3 and parts[0].lower() == "activist" and parts[1].lower() in ("long", "short"):
        return f"activist_{parts[1].lower()}", parts[2:], "root-relative"
    if len(parts) >= 2 and parts[0].lower() in INTAKE_TYPES:
        return parts[0].lower(), parts[1:], "root-relative"
    return None


def parse_intake_path(path: str) -> dict | None:
    parsed_parts = intake_path_parts(path)
    if not parsed_parts:
        return None
    intake_kind, rest, intake_prefix = parsed_parts
    filename = rest[-1]
    if not filename.lower().endswith(".pdf"):
        return None
    ticker = normalize_ticker(rest[0]) if len(rest) >= 2 else None
    if not ticker:
        ticker = infer_ticker_from_name(filename)
    if not ticker:
        return {
            "error": "missing_or_unknown_ticker",
            "intake_kind": intake_kind,
            "intake_prefix": intake_prefix,
            "path": path,
            "filename": filename,
        }
    return {
        "intake_kind": intake_kind,
        "intake_prefix": intake_prefix,
        "ticker": ticker,
        "filename": filename,
        "path": path,
        "ticker_resolve_method": "path_or_filename",
    }


def destination_for(ticker: str, intake_kind: str, filename: str, *, drive_file_id: str) -> Path:
    safe_name = safe_filename(filename)
    if intake_kind == "vic":
        dest_dir = ROOT / ticker / "third-party-analyses" / "vic"
    elif intake_kind == "activist_long":
        dest_dir = ROOT / ticker / "third-party-analyses" / "activist_reports" / "long"
    elif intake_kind == "activist_short":
        dest_dir = ROOT / ticker / "third-party-analyses" / "activist_reports" / "short"
    elif intake_kind == "company":
        dest_dir = ROOT / ticker / "investor-documents" / "drive-intake"
    else:
        dest_dir = ROOT / ticker / "third-party-analyses" / "drive-intake"
    dest_dir.mkdir(parents=True, exist_ok=True)
    candidate = dest_dir / safe_name
    if not candidate.exists():
        return candidate
    return dest_dir / f"{Path(safe_name).stem}-{drive_file_id[:8]}.pdf"


def download_pdf(service, file_id: str) -> bytes:
    request = service.files().get_media(fileId=file_id, supportsAllDrives=True)
    buffer = io.BytesIO()
    downloader = MediaIoBaseDownload(buffer, request)
    done = False
    while not done:
        _status, done = downloader.next_chunk()
    data = buffer.getvalue()
    if not data.startswith(b"%PDF-"):
        raise ValueError(f"Drive file {file_id} did not download as a PDF.")
    return data


def load_manifest() -> dict:
    manifest = load_json(MANIFEST_PATH)
    manifest.setdefault("schema_version", 1)
    manifest.setdefault("files", {})
    return manifest


def report_state(report: dict) -> dict:
    return {key: value for key, value in report.items() if key not in {"generated_at", "report_changed"}}


def write_report_if_changed(path: Path, report: dict) -> bool:
    previous = load_json(path)
    if previous and report_state(previous) == report_state(report):
        return False
    write_json(path, report)
    return True


def is_dry_run_folder_id(folder_id: str) -> bool:
    return str(folder_id).startswith("dry-run:")


def needs_drive_rename(filename: str, ticker: str) -> bool:
    stem = Path(filename).stem
    if stem.isdigit():
        return True
    if normalize_ticker(stem) == ticker:
        return False
    # Filename already starts with ticker token
    first = re.split(r"[\s_\-]+", stem.upper())[0]
    return first != ticker.upper()


def drive_target_folder_rel(intake_kind: str, ticker: str) -> str:
    base = INTAKE_FOLDER_PATHS.get(intake_kind) or intake_kind
    return f"{base}/{ticker}"


def move_drive_file_to_ticker(
    service,
    *,
    item: dict,
    root_id: str,
    intake_kind: str,
    ticker: str,
    dry_run: bool,
    existing_folders: dict[tuple[str, str], str],
) -> dict:
    """Ensure Admin/Intake/{Kind}/{TICKER}/ and move/rename the Drive file there."""
    filename = item.get("name") or "document.pdf"
    target_rel = drive_target_folder_rel(intake_kind, ticker)
    new_name = filename
    if needs_drive_rename(filename, ticker):
        stem = Path(filename).stem
        new_name = safe_filename(f"{ticker} - {stem}.pdf")

    if dry_run:
        return {
            "dry_run": True,
            "drive_moved_to": f"{target_rel}/{new_name}",
            "renamed": new_name != filename,
        }

    folder_id = ensure_folder_path(service, root_id, target_rel, False, existing_folders)
    parents = item.get("parents") or []
    body: dict = {}
    if new_name != filename:
        body["name"] = new_name
    kwargs = {
        "fileId": item["id"],
        "addParents": folder_id,
        "supportsAllDrives": True,
        "fields": "id,name,parents,webViewLink",
    }
    if parents:
        kwargs["removeParents"] = ",".join(parents)
    if body:
        kwargs["body"] = body
    updated = execute_with_retry(service.files().update(**kwargs))
    return {
        "drive_moved_to": f"{target_rel}/{updated.get('name') or new_name}",
        "drive_folder_id": folder_id,
        "renamed": new_name != filename,
        "drive_web_view_link": updated.get("webViewLink"),
    }


def ensure_intake_folders(service, root_ids: list[str], items: list[dict], dry_run: bool) -> list[dict]:
    existing = folder_id_by_parent_name(items)
    ensured: list[dict] = []
    for root_id in root_ids:
        for intake_kind, folder_path in INTAKE_FOLDER_PATHS.items():
            folder_id = ensure_folder_path(service, root_id, folder_path, dry_run, existing)
            ensured.append(
                {
                    "intake_kind": intake_kind,
                    "path": folder_path,
                    "drive_folder_id": folder_id,
                    "drive_folder_url": None if is_dry_run_folder_id(folder_id) else web_folder_url(folder_id),
                }
            )
    return ensured


def configured_intake_root_ids(config: dict) -> list[str]:
    root_ids: list[str] = []
    intake = config.get("drive_intake") or {}
    if intake.get("folder_id"):
        root_ids.append(intake["folder_id"])
    for root in (config.get("drive_intake_roots") or {}).values():
        if root.get("folder_id"):
            root_ids.append(root["folder_id"])
    return sorted(set(root_ids))


def write_sidecar(dest: Path, item: dict, parsed: dict, digest: str) -> None:
    sidecar = dest.with_suffix(".source.json")
    payload = {
        "imported_at": now_iso(),
        "source": "google_drive_intake",
        "intake_kind": parsed["intake_kind"],
        "ticker": parsed["ticker"],
        "drive_file_id": item.get("id"),
        "drive_name": item.get("name"),
        "drive_path": parsed.get("path"),
        "drive_web_view_link": item.get("webViewLink"),
        "drive_created_time": item.get("createdTime"),
        "drive_modified_time": item.get("modifiedTime"),
        "sha256": digest,
        "ticker_resolve_method": parsed.get("ticker_resolve_method"),
        "ticker_candidates": parsed.get("ticker_candidates"),
        "drive_moved_to": parsed.get("drive_moved_to"),
    }
    write_json(sidecar, payload)


def _root_id_for_item(item: dict, root_ids: list[str], paths: dict[str, str]) -> str:
    """Best-effort: use the single intake root when only one; else first root."""
    if len(root_ids) == 1:
        return root_ids[0]
    parents = item.get("parents") or []
    for root_id in root_ids:
        if root_id in parents:
            return root_id
    return root_ids[0]


def import_intake(
    dry_run: bool,
    limit: int,
    force: bool,
    include_kinds: set[str],
    ensure_folders: bool,
) -> dict:
    config = load_json(CONFIG_PATH)
    root_ids = configured_intake_root_ids(config)
    if not root_ids:
        raise SystemExit(f"No drive roots configured in {CONFIG_PATH}")
    # Need write scope to create intake folders and/or move files after resolve.
    need_write = ensure_folders or not dry_run
    service = drive_service(readonly=not need_write)
    items = list_drive_items(service, root_ids)
    ensured_folders: list[dict] = []
    existing_folders = folder_id_by_parent_name(items)
    if ensure_folders:
        ensured_folders = ensure_intake_folders(service, root_ids, items, dry_run)
        if not dry_run:
            items = list_drive_items(service, root_ids)
            existing_folders = folder_id_by_parent_name(items)
    paths, _children = item_paths(items, root_ids)
    manifest = load_manifest()
    manifest_changed = False
    imported: list[dict] = []
    skipped: list[dict] = []
    errors: list[dict] = []
    warnings: list[dict] = []
    touched_tickers: set[str] = set()

    for item in sorted(items, key=lambda i: paths.get(i.get("id", ""), "")):
        if item.get("mimeType") != PDF_MIME:
            continue
        file_id = item["id"]
        path = paths.get(file_id, "")
        parsed = parse_intake_path(path)
        if not parsed:
            continue
        if parsed["intake_kind"] not in include_kinds:
            continue

        resolve_meta: dict = {}
        if parsed.get("error") == "missing_or_unknown_ticker":
            # Download and resolve ticker from PDF content.
            try:
                if dry_run:
                    # Dry-run cannot download without creds write scope issues;
                    # still attempt read download.
                    data = download_pdf(service, file_id)
                else:
                    data = download_pdf(service, file_id)
            except Exception as exc:  # noqa: BLE001
                errors.append(
                    {
                        "drive_file_id": file_id,
                        "path": path,
                        "filename": parsed.get("filename"),
                        "intake_kind": parsed.get("intake_kind"),
                        "error": "download_failed",
                        "detail": str(exc),
                    }
                )
                continue
            resolve_meta = resolve_ticker_from_pdf(data, filename=parsed.get("filename") or "")
            if not resolve_meta.get("ticker"):
                warnings.append(
                    {
                        "drive_file_id": file_id,
                        "path": path,
                        "filename": parsed.get("filename"),
                        "intake_kind": parsed.get("intake_kind"),
                        "error": resolve_meta.get("error") or "unresolved_ticker",
                        "ticker_candidates": resolve_meta.get("candidates") or [],
                        "extract_method": resolve_meta.get("extract_method"),
                        "text_chars": resolve_meta.get("text_chars"),
                    }
                )
                continue
            parsed = {
                "intake_kind": parsed["intake_kind"],
                "intake_prefix": parsed.get("intake_prefix"),
                "ticker": resolve_meta["ticker"],
                "filename": parsed["filename"],
                "path": path,
                "ticker_resolve_method": resolve_meta.get("method"),
                "ticker_candidates": resolve_meta.get("candidates") or [],
                "extract_method": resolve_meta.get("extract_method"),
            }
            # Keep bytes for write below
            pdf_bytes: bytes | None = data
        else:
            pdf_bytes = None

        prior = manifest["files"].get(file_id)
        if prior and not force and (ROOT / prior.get("local_pdf_path", "")).exists():
            skipped.append({"drive_file_id": file_id, "reason": "already_imported", **parsed})
            continue
        if limit and len(imported) >= limit:
            skipped.append({"drive_file_id": file_id, "reason": "limit_reached", **parsed})
            continue
        dest = destination_for(parsed["ticker"], parsed["intake_kind"], parsed["filename"], drive_file_id=file_id)
        if dry_run:
            move_info = move_drive_file_to_ticker(
                service,
                item=item,
                root_id=_root_id_for_item(item, root_ids, paths),
                intake_kind=parsed["intake_kind"],
                ticker=parsed["ticker"],
                dry_run=True,
                existing_folders=existing_folders,
            )
            imported.append(
                {
                    "drive_file_id": file_id,
                    "dry_run": True,
                    "target": rel(dest),
                    **parsed,
                    **move_info,
                }
            )
            continue

        try:
            data = pdf_bytes if pdf_bytes is not None else download_pdf(service, file_id)
        except Exception as exc:  # noqa: BLE001
            errors.append(
                {
                    "drive_file_id": file_id,
                    "path": path,
                    "filename": parsed.get("filename"),
                    "intake_kind": parsed.get("intake_kind"),
                    "ticker": parsed.get("ticker"),
                    "error": "download_failed",
                    "detail": str(exc),
                }
            )
            continue

        digest = sha256_bytes(data)
        if dest.exists() and sha256_bytes(dest.read_bytes()) == digest:
            status = "already_present"
        else:
            dest.write_bytes(data)
            status = "imported"

        move_info: dict = {}
        try:
            move_info = move_drive_file_to_ticker(
                service,
                item=item,
                root_id=_root_id_for_item(item, root_ids, paths),
                intake_kind=parsed["intake_kind"],
                ticker=parsed["ticker"],
                dry_run=False,
                existing_folders=existing_folders,
            )
            parsed["drive_moved_to"] = move_info.get("drive_moved_to")
        except Exception as exc:  # noqa: BLE001
            warnings.append(
                {
                    "drive_file_id": file_id,
                    "path": path,
                    "ticker": parsed.get("ticker"),
                    "error": "drive_move_failed",
                    "detail": str(exc),
                    "local_pdf_path": rel(dest),
                }
            )

        write_sidecar(dest, item, parsed, digest)
        manifest["files"][file_id] = {
            "imported_at": now_iso(),
            "status": status,
            "intake_kind": parsed["intake_kind"],
            "ticker": parsed["ticker"],
            "drive_file_id": file_id,
            "drive_name": item.get("name"),
            "drive_path": parsed.get("path"),
            "drive_web_view_link": item.get("webViewLink"),
            "local_pdf_path": rel(dest),
            "sha256": digest,
            "size_bytes": len(data),
            "ticker_resolve_method": parsed.get("ticker_resolve_method"),
            "ticker_candidates": parsed.get("ticker_candidates"),
            "drive_moved_to": parsed.get("drive_moved_to"),
        }
        manifest_changed = True
        imported.append({**manifest["files"][file_id], "target": rel(dest), **move_info})
        touched_tickers.add(parsed["ticker"])
        if parsed["intake_kind"] in ("activist_long", "activist_short") and upsert_report:
            side = "long" if parsed["intake_kind"] == "activist_long" else "short"
            index = load_ticker_index(parsed["ticker"])
            upsert_report(
                index,
                {
                    "firm_id": "drive_intake",
                    "firm_name": "Drive intake",
                    "side": side,
                    "report_date": (item.get("createdTime") or now_iso())[:10],
                    "title": parsed["filename"],
                    "source": "google_drive_intake",
                    "source_url": item.get("webViewLink"),
                    "local_pdf": rel(dest),
                    "local_file": rel(dest),
                    "status": "new",
                    "tier": "context",
                    "confidence": 1.0,
                },
            )
            save_ticker_index(parsed["ticker"], index)

    if not dry_run and manifest_changed:
        manifest["generated_at"] = now_iso()
        write_json(MANIFEST_PATH, manifest)
    if not dry_run:
        for ticker in sorted(touched_tickers):
            write_inventory(ticker)
            if extract_ticker_activist_text:
                extract_ticker_activist_text(ticker)

    report = {
        "generated_at": now_iso(),
        "dry_run": dry_run,
        "intake_prefix": INTAKE_PREFIX,
        "accepted_intake_prefixes": ACCEPTED_INTAKE_PREFIXES,
        "configured_root_folders": [web_folder_url(root_id) for root_id in root_ids],
        "intake_folder_paths": INTAKE_FOLDER_PATHS,
        "ensured_intake_folders": ensured_folders,
        "summary": {
            "imported_count": len(imported),
            "skipped_count": len(skipped),
            "warning_count": len(warnings),
            "error_count": len(errors),
            "touched_ticker_count": len(touched_tickers),
        },
        "imported": imported,
        "skipped": skipped[:200],
        "warnings": warnings[:200],
        "errors": errors[:200],
    }
    report_changed = False
    if not dry_run:
        report_changed = write_report_if_changed(REPORT_PATH, report)
    report["report_changed"] = report_changed
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Import Drive intake PDFs into canonical repo folders.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--ensure-folders",
        action="store_true",
        help="Create Admin/{VIC,Research,Company} folders before scanning.",
    )
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument(
        "--kind",
        choices=sorted(INTAKE_TYPES),
        action="append",
        help="Restrict to intake kind. May be passed multiple times.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero when any PDF remains unresolved (warnings).",
    )
    args = parser.parse_args()
    include_kinds = set(args.kind or INTAKE_TYPES)
    report = import_intake(args.dry_run, args.limit, args.force, include_kinds, args.ensure_folders)
    print("Drive intake import")
    for key, value in report["summary"].items():
        print(f"  {key}: {value}")
    print(f"  report_changed: {str(report['report_changed']).lower()}")
    if report["warnings"]:
        print(
            "  warnings: unresolved/ambiguous PDF tickers or Drive move issues; "
            "see drive_intake_latest.json"
        )
        for w in report["warnings"][:10]:
            print(f"    ::warning:: {w.get('path') or w.get('filename')}: {w.get('error')}")
    if report["errors"]:
        print("  errors: operational failures (download/config); inspect drive_intake_latest.json")
    if report["errors"]:
        return 2
    if args.strict and report["warnings"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

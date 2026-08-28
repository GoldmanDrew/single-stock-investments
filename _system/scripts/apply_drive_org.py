"""Apply Magis Shared Drive PDF-store organization.

Merges duplicate root folders, letter quarter aliases, ticker Legacy Drive
Copies, and per-ticker Files into Company. Moves a small set of misfiled
letters and non-letters. Never deletes PDFs. Empty folders may be trashed.
"""
from __future__ import annotations

import argparse
import re
from collections import defaultdict

from drive_store_common import (
    CONFIG_PATH,
    FOLDER_INDEX_PATH,
    FOLDER_MIME,
    ROOT as SSI_ROOT,
    build_folder_paths,
    configured_root_ids,
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

REPORT_PATH = SSI_ROOT / "_system" / "reference" / "document-store" / "drive_org_apply_report.json"

CANONICAL_LETTERS_ID = "1z8P-tKj3lvWmx72bXUxJQ9BcUmKrhTg4"
CANONICAL_RESEARCH_SOURCES_ID = "1yK75I60EbARPMyP6ibSggJ1-VLxtYXwU"
PREFERRED_LETTER_QUARTERS = {
    ("2026", "1"): "1QxQd4VhLv7HK1qa45izn80MMYFcS-gxg",
    ("2026", "2"): "1CtFKEdK0eTXZlY-t6bddds5rLSX5V7sO",
    ("2026", "3"): "1wBnJHPU6-rCk4nz11JhvCL5y39rdV12W",
}
CANONICAL_TOP = {"Letters", "Single Stocks", "Research Sources", "Admin", "Manager Meetings"}
KEEP_EMPTY = CANONICAL_TOP | {"Intake", "Investment Wisdom"}

QUARTER_ALIAS_RE = re.compile(r"^(\d{4})\s+([1-4])Q(?:\s+Letters)?$", re.I)
QUARTER_CANON_RE = re.compile(r"^(\d{4})\s+Q([1-4])$", re.I)

MISFILED_LETTERS = {
    "Wampanoag Capital 2026 Q1 Partners Letter Final with Exhibits.pdf": "Letters/2026 Q1",
}
NON_LETTERS = {
    "White-Paper_Capturing the competitive bidding situation_Aug 2023.pdf": "Research Sources/Uncategorized",
    "WP_2023_Pershing Square and Berkshire.pdf": "Research Sources/Uncategorized",
    "US_Mind_the_Gap_2025.pdf": "Research Sources/Uncategorized",
}


def parse_quarter_name(name: str) -> tuple[str, str] | None:
    text = (name or "").strip()
    m = QUARTER_CANON_RE.match(text) or QUARTER_ALIAS_RE.match(text)
    if not m:
        return None
    return m.group(1), m.group(2)


def canonical_letter_path(year: str, quarter: str) -> str:
    return f"Letters/{year} Q{quarter}"


def children_of(items_by_parent: dict[str, list[dict]], folder_id: str) -> list[dict]:
    return list(items_by_parent.get(folder_id) or [])


def index_by_parent(items: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = defaultdict(list)
    for item in items:
        for parent in item.get("parents") or []:
            out[parent].append(item)
    return out


def move_item(service, item: dict, dest_folder_id: str, dry_run: bool, new_name: str | None = None) -> None:
    if dry_run:
        return
    current = [p for p in (item.get("parents") or []) if p]
    params = {
        "fileId": item["id"],
        "supportsAllDrives": True,
        "enforceSingleParent": True,
        "fields": "id,name,parents",
    }
    if dest_folder_id not in current:
        params["addParents"] = dest_folder_id
    remove = [p for p in current if p != dest_folder_id]
    if remove:
        params["removeParents"] = ",".join(remove)
    body = {"name": new_name} if new_name else {}
    execute_with_retry(service.files().update(body=body, **params))
    item["parents"] = [dest_folder_id]
    if new_name:
        item["name"] = new_name


def trash_folder(service, folder_id: str, dry_run: bool) -> None:
    if dry_run:
        return
    execute_with_retry(
        service.files().update(
            fileId=folder_id,
            body={"trashed": True},
            fields="id,trashed",
            supportsAllDrives=True,
        )
    )


def unique_child_name(dest_children: list[dict], name: str, file_id: str) -> str:
    existing = {(c.get("name") or "") for c in dest_children}
    if name not in existing:
        return name
    stem, dot, ext = name.rpartition(".")
    suffix = file_id[:6]
    candidate = f"{stem} ({suffix}).{ext}" if dot else f"{name} ({suffix})"
    n = 2
    while candidate in existing:
        candidate = f"{stem} ({suffix}-{n}).{ext}" if dot else f"{name} ({suffix}-{n})"
        n += 1
    return candidate


def same_file_present(dest_children: list[dict], item: dict) -> bool:
    name = item.get("name") or ""
    size = str(item.get("size") or "")
    for child in dest_children:
        if child.get("id") == item.get("id"):
            return True
        if (child.get("name") or "") == name and str(child.get("size") or "") == size and size:
            return True
    return False


def merge_folder_into(
    service,
    src: dict,
    dest: dict,
    items_by_parent: dict[str, list[dict]],
    dry_run: bool,
    actions: list[dict],
    errors: list[dict],
    depth: int = 0,
) -> None:
    if src["id"] == dest["id"]:
        return
    src_children = list(children_of(items_by_parent, src["id"]))
    dest_children = children_of(items_by_parent, dest["id"])
    dest_folders = {
        (c.get("name") or ""): c
        for c in dest_children
        if c.get("mimeType") == FOLDER_MIME
    }
    for child in src_children:
        try:
            if child.get("mimeType") == FOLDER_MIME:
                name = child.get("name") or ""
                if name in dest_folders:
                    merge_folder_into(
                        service, child, dest_folders[name], items_by_parent, dry_run, actions, errors, depth + 1
                    )
                else:
                    actions.append(
                        {
                            "kind": "move_folder",
                            "name": name,
                            "from": src["id"],
                            "to": dest["id"],
                        }
                    )
                    move_item(service, child, dest["id"], dry_run)
                    items_by_parent[src["id"]] = [c for c in items_by_parent[src["id"]] if c["id"] != child["id"]]
                    items_by_parent[dest["id"]].append(child)
                    dest_folders[name] = child
            else:
                if same_file_present(dest_children, child):
                    actions.append({"kind": "skip_duplicate_pdf", "name": child.get("name"), "id": child["id"]})
                    continue
                new_name = unique_child_name(dest_children, child.get("name") or "file", child["id"])
                actions.append(
                    {
                        "kind": "move_pdf",
                        "name": child.get("name"),
                        "renamed_to": None if new_name == child.get("name") else new_name,
                        "from": src["id"],
                        "to": dest["id"],
                    }
                )
                move_item(service, child, dest["id"], dry_run, new_name if new_name != child.get("name") else None)
                items_by_parent[src["id"]] = [c for c in items_by_parent[src["id"]] if c["id"] != child["id"]]
                items_by_parent[dest["id"]].append(child)
                dest_children.append(child)
        except Exception as exc:
            errors.append({"id": child.get("id"), "name": child.get("name"), "error": str(exc)})


def keeper_for_duplicate_roots(name: str, folders: list[dict]) -> dict:
    if name == "Letters":
        for folder in folders:
            if folder["id"] == CANONICAL_LETTERS_ID:
                return folder
    if name == "Research Sources":
        for folder in folders:
            if folder["id"] == CANONICAL_RESEARCH_SOURCES_ID:
                return folder
    parsed = parse_quarter_name(name)
    if parsed:
        preferred = PREFERRED_LETTER_QUARTERS.get(parsed)
        if preferred:
            for folder in folders:
                if folder["id"] == preferred:
                    return folder
    folders_sorted = sorted(folders, key=lambda f: (-int(f.get("_child_count") or 0), f["id"]))
    return folders_sorted[0]


def apply_org(dry_run: bool) -> dict:
    config = load_json(CONFIG_PATH)
    service = drive_service(readonly=dry_run)
    if not dry_run:
        service = drive_service(readonly=False)
    root_ids = configured_root_ids(config)
    root_id = root_ids[0]
    print("Listing Shared Drive items...", flush=True)
    items = list_drive_items(service, root_ids)
    print(f"Listed {len(items)} item(s).", flush=True)
    by_id = {item["id"]: item for item in items}
    folder_paths = build_folder_paths(items, root_ids)
    paths, _ = item_paths(items, root_ids)
    items_by_parent = index_by_parent(items)
    existing = folder_id_by_parent_name(items)
    for folder_id, kids in items_by_parent.items():
        if folder_id in by_id:
            by_id[folder_id]["_child_count"] = len(kids)

    actions: list[dict] = []
    errors: list[dict] = []
    trashed: list[dict] = []

    def folder_by_path(path: str) -> dict | None:
        for fid, fpath in folder_paths.items():
            if fpath == path:
                return by_id.get(fid)
        return None

    def ensure_path(path: str) -> dict:
        folder_id = ensure_folder_path(service, root_id, path, dry_run, existing)
        folder = by_id.get(folder_id)
        if folder:
            return folder
        folder = {"id": folder_id, "name": path.rsplit("/", 1)[-1], "mimeType": FOLDER_MIME, "parents": []}
        by_id[folder_id] = folder
        folder_paths[folder_id] = path
        return folder

    # Phase 1: merge duplicate folders that share a parent and name.
    by_parent_name: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for item in items:
        if item.get("mimeType") != FOLDER_MIME:
            continue
        name = item.get("name") or ""
        for parent in item.get("parents") or [root_id]:
            by_parent_name[(parent, name)].append(item)
    # Root shared-drive folders may have no parents.
    for item in items:
        if item.get("mimeType") != FOLDER_MIME:
            continue
        if item.get("parents"):
            continue
        by_parent_name[(root_id, item.get("name") or "")].append(item)

    for (parent, name), group in sorted(by_parent_name.items(), key=lambda kv: kv[0][1]):
        unique = {f["id"]: f for f in group}
        if len(unique) < 2 or not name:
            continue
        folders = list(unique.values())
        for folder in folders:
            folder["_child_count"] = len(children_of(items_by_parent, folder["id"]))
        keep = keeper_for_duplicate_roots(name, folders)
        for extra in folders:
            if extra["id"] == keep["id"]:
                continue
            actions.append(
                {
                    "kind": "merge_duplicate_folder",
                    "name": name,
                    "keep": keep["id"],
                    "absorb": extra["id"],
                    "path": folder_paths.get(extra["id"]) or name,
                }
            )
            merge_folder_into(service, extra, keep, items_by_parent, dry_run, actions, errors)

    # Phase 2: letter quarter aliases into Letters/{YYYY Qn}.
    letters_keep = by_id.get(CANONICAL_LETTERS_ID)
    if letters_keep is None:
        letters_keep = folder_by_path("Letters")
    if letters_keep:
        for item in list(items):
            if item.get("mimeType") != FOLDER_MIME:
                continue
            parsed = parse_quarter_name(item.get("name") or "")
            if not parsed:
                continue
            year, q = parsed
            target_path = canonical_letter_path(year, q)
            if CANONICAL_LETTERS_ID in (item.get("parents") or []) and QUARTER_CANON_RE.match(item.get("name") or ""):
                continue
            matches = [
                child
                for child in children_of(items_by_parent, CANONICAL_LETTERS_ID)
                if child.get("mimeType") == FOLDER_MIME and parse_quarter_name(child.get("name") or "") == (year, q)
            ]
            preferred_id = PREFERRED_LETTER_QUARTERS.get((year, q))
            dest = next((c for c in matches if c["id"] == preferred_id), None)
            if dest is None and matches:
                dest = max(
                    matches,
                    key=lambda c: int(c.get("_child_count") or len(children_of(items_by_parent, c["id"]))),
                )
            if dest is None:
                dest = folder_by_path(target_path) or ensure_path(target_path)
            if item["id"] == dest["id"] or item["id"] == preferred_id:
                continue
            path = folder_paths.get(item["id"]) or item.get("name")
            if path.startswith("Single Stocks/"):
                continue
            actions.append(
                {
                    "kind": "merge_letter_alias",
                    "from": path,
                    "to": target_path,
                    "id": item["id"],
                }
            )
            merge_folder_into(service, item, dest, items_by_parent, dry_run, actions, errors)

    # Phase 3: flatten Single Stocks/{T}/Legacy Drive Copies/{T} into {T}.
    for item in list(items):
        if item.get("mimeType") != FOLDER_MIME:
            continue
        path = folder_paths.get(item["id"]) or ""
        parts = path.split("/")
        if len(parts) >= 4 and parts[0] == "Single Stocks" and parts[2] == "Legacy Drive Copies" and parts[3] == parts[1]:
            dest = folder_by_path(f"Single Stocks/{parts[1]}")
            if not dest:
                continue
            actions.append({"kind": "flatten_legacy_ticker", "from": path, "to": f"Single Stocks/{parts[1]}"})
            merge_folder_into(service, item, dest, items_by_parent, dry_run, actions, errors)

    # Nested letter legacy aliases already handled by quarter merge; also merge
    # Letters/{q}/Legacy Drive Copies into the quarter folder.
    for item in list(items):
        if item.get("mimeType") != FOLDER_MIME:
            continue
        path = folder_paths.get(item["id"]) or ""
        parts = path.split("/")
        if (
            len(parts) == 3
            and parts[0] == "Letters"
            and parts[2] == "Legacy Drive Copies"
            and parse_quarter_name(parts[1])
        ):
            dest = folder_by_path(f"Letters/{parts[1]}")
            if dest:
                actions.append({"kind": "flatten_letter_legacy", "from": path, "to": f"Letters/{parts[1]}"})
                merge_folder_into(service, item, dest, items_by_parent, dry_run, actions, errors)

    # Phase 4: per-ticker Files -> Company.
    tickers: dict[str, dict[str, dict]] = defaultdict(dict)
    for item in items:
        if item.get("mimeType") != FOLDER_MIME:
            continue
        path = folder_paths.get(item["id"]) or ""
        parts = path.split("/")
        if len(parts) == 3 and parts[0] == "Single Stocks":
            tickers[parts[1]][parts[2]] = item
    for ticker, kids in sorted(tickers.items()):
        files_folder = kids.get("Files")
        if not files_folder:
            continue
        company = kids.get("Company")
        if company is None:
            actions.append({"kind": "rename_files_to_company", "ticker": ticker, "id": files_folder["id"]})
            try:
                move_item(service, files_folder, (files_folder.get("parents") or [root_id])[0], dry_run, "Company")
                folder_paths[files_folder["id"]] = f"Single Stocks/{ticker}/Company"
            except Exception as exc:
                errors.append({"ticker": ticker, "error": str(exc)})
            continue
        actions.append({"kind": "merge_files_into_company", "ticker": ticker})
        merge_folder_into(service, files_folder, company, items_by_parent, dry_run, actions, errors)

    # Phase 5: Books/ -> Research Sources/Investment Wisdom/
    books = folder_by_path("Books") or next((by_id[i] for i, p in folder_paths.items() if p == "Books"), None)
    wisdom = folder_by_path("Research Sources/Investment Wisdom")
    if books and wisdom:
        actions.append({"kind": "merge_books_into_wisdom", "from": books["id"], "to": wisdom["id"]})
        merge_folder_into(service, books, wisdom, items_by_parent, dry_run, actions, errors)

    # Phase 6: leaked _system trees.
    quarantine = ensure_path("Admin/Quarantine")
    for item in list(items):
        if item.get("mimeType") != FOLDER_MIME:
            continue
        path = folder_paths.get(item["id"]) or ""
        if path.endswith("/_system") or path == "_system":
            dest_name = path.replace("/", "__") or "_system"
            dest = ensure_path(f"Admin/Quarantine/{dest_name}")
            actions.append({"kind": "quarantine_system_tree", "from": path, "to": f"Admin/Quarantine/{dest_name}"})
            merge_folder_into(service, item, dest, items_by_parent, dry_run, actions, errors)

    # Phase 7: specific misfiles by filename.
    dest_cache: dict[str, dict] = {}
    for item in items:
        if item.get("mimeType") == FOLDER_MIME:
            continue
        name = item.get("name") or ""
        target = MISFILED_LETTERS.get(name) or NON_LETTERS.get(name)
        if not target:
            continue
        dest = dest_cache.get(target) or ensure_path(target)
        dest_cache[target] = dest
        parents = item.get("parents") or []
        if dest["id"] in parents:
            continue
        kind = "move_misfiled_letter" if name in MISFILED_LETTERS else "move_non_letter"
        actions.append({"kind": kind, "name": name, "to": target, "id": item["id"]})
        try:
            dest_children = children_of(items_by_parent, dest["id"])
            new_name = unique_child_name(dest_children, name, item["id"])
            move_item(service, item, dest["id"], dry_run, new_name if new_name != name else None)
        except Exception as exc:
            errors.append({"name": name, "error": str(exc)})

    # Phase 7b: leftover duplicate roots off the Shared Drive top level.
    quarantine = ensure_path("Admin/Quarantine")
    keep_root_ids = {CANONICAL_LETTERS_ID, CANONICAL_RESEARCH_SOURCES_ID, root_id}
    for item in list(items):
        if item.get("mimeType") != FOLDER_MIME:
            continue
        name = item.get("name") or ""
        if name not in {"Letters", "Research Sources"}:
            continue
        if item["id"] in keep_root_ids:
            continue
        parents = item.get("parents") or [root_id]
        if root_id not in parents and item.get("parents"):
            # Only relocate extra roots sitting beside the canonical ones.
            if not any(p == root_id for p in parents):
                continue
        new_name = f"{name} leftover {item['id'][:6]}"
        actions.append({"kind": "quarantine_extra_root", "from": item["id"], "name": new_name})
        try:
            move_item(service, item, quarantine["id"], dry_run, new_name)
        except Exception as extra_exc:
            errors.append({"id": item["id"], "name": name, "error": str(extra_exc)})

    # Phase 8: trash empty leftover folders (never PDFs). Deepest first.
    folders = [item for item in items if item.get("mimeType") == FOLDER_MIME]
    folders.sort(key=lambda f: (folder_paths.get(f["id"]) or "").count("/"), reverse=True)
    for folder in folders:
        path = folder_paths.get(folder["id"]) or folder.get("name") or ""
        top = path.split("/", 1)[0]
        name = folder.get("name") or ""
        kids = children_of(items_by_parent, folder["id"])
        live_kids = [k for k in kids if not k.get("_trashed")]
        if live_kids:
            continue
        if name in KEEP_EMPTY or path in KEEP_EMPTY:
            continue
        if folder["id"] == CANONICAL_LETTERS_ID:
            continue
        if QUARTER_CANON_RE.match(name) and CANONICAL_LETTERS_ID in (folder.get("parents") or []):
            continue
        alias = bool(QUARTER_ALIAS_RE.match(name))
        legacy = name in {"Files", "Books", "_Historical Letters", "_system", "Legacy Drive Copies"} or path.endswith(
            "/Legacy Drive Copies"
        )
        extra_root = path == name and name in {"Letters", "Research Sources", "Books"} and folder["id"] != CANONICAL_LETTERS_ID
        if not (alias or legacy or extra_root):
            continue
        actions.append({"kind": "trash_empty_folder", "path": path, "id": folder["id"]})
        try:
            trash_folder(service, folder["id"], dry_run)
            folder["_trashed"] = True
            trashed.append({"path": path, "id": folder["id"]})
            for parent in folder.get("parents") or []:
                items_by_parent[parent] = [c for c in items_by_parent[parent] if c["id"] != folder["id"]]
        except Exception as exc:
            errors.append({"path": path, "error": str(exc)})

    if not dry_run:
        print("Refreshing folder index...", flush=True)
        fresh = list_drive_items(service, root_ids)
        fresh_paths = build_folder_paths(fresh, root_ids)
        payload = {
            "generated_at": now_iso(),
            "folders": {
                path: {"id": fid, "webViewLink": web_folder_url(fid)}
                for fid, path in sorted(fresh_paths.items(), key=lambda kv: kv[1])
                if path
            },
        }
        write_json(FOLDER_INDEX_PATH, payload)

    summary = {
        "dry_run": dry_run,
        "listed_items": len(items),
        "action_count": len(actions),
        "error_count": len(errors),
        "trashed_empty_folder_count": len(trashed),
        "kind_counts": {},
    }
    counts: dict[str, int] = defaultdict(int)
    for row in actions:
        counts[str(row.get("kind") or "unknown")] += 1
    summary["kind_counts"] = dict(sorted(counts.items()))
    report = {
        "generated_at": now_iso(),
        "summary": summary,
        "actions": actions,
        "trashed_empty_folders": trashed,
        "errors": errors,
    }
    write_json(REPORT_PATH, report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply Drive PDF store organization")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if not args.dry_run and not args.apply:
        raise SystemExit("Pass --dry-run or --apply.")
    report = apply_org(dry_run=not args.apply)
    print("Drive org apply")
    for key, value in report["summary"].items():
        print(f"  {key}: {value}")
    print(f"  report_path: {REPORT_PATH}")
    if report["errors"]:
        print(f"  first_error: {report['errors'][0]}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

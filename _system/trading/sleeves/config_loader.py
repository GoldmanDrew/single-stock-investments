"""Load sleeve YAML and JSON snapshots."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from . import PKG_DIR


def load_config(path: Path | None = None) -> dict[str, Any]:
    cfg_path = path or (PKG_DIR / "config.yaml")
    with cfg_path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def _read_json(rel: str) -> dict[str, Any]:
    path = PKG_DIR / rel
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def load_blacklist(cfg: dict[str, Any] | None = None) -> set[str]:
    cfg = cfg or load_config()
    rel = str((cfg.get("paths") or {}).get("blacklist_json") or "data/blacklist.json")
    payload = _read_json(rel)
    return {str(s).strip().upper() for s in payload.get("underlyings") or [] if str(s).strip()}


def load_etf_to_under(cfg: dict[str, Any] | None = None) -> dict[str, str]:
    cfg = cfg or load_config()
    rel = str((cfg.get("paths") or {}).get("etf_to_under_json") or "data/etf_to_under.json")
    payload = _read_json(rel)
    raw = payload.get("map") or {}
    return {str(k).strip().upper(): str(v).strip().upper() for k, v in raw.items() if str(k).strip() and str(v).strip()}


def load_etf_ls_universe(cfg: dict[str, Any] | None = None) -> set[str]:
    cfg = cfg or load_config()
    rel = str((cfg.get("paths") or {}).get("etf_ls_universe_json") or "data/etf_ls_universe.json")
    payload = _read_json(rel)
    return {str(s).strip().upper() for s in payload.get("symbols") or [] if str(s).strip()}


def operator_config(cfg: dict[str, Any], owner: str) -> dict[str, Any]:
    ops = cfg.get("operators") or {}
    if owner not in ops:
        raise KeyError(f"Unknown operator {owner!r}")
    return dict(ops[owner])

"""Load sleeve YAML and JSON snapshots."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import yaml

from . import PKG_DIR


def apply_ibkr_env(cfg: dict[str, Any]) -> dict[str, Any]:
    """Same knobs as ls-algo / SPX 0DTE: host, port, account from the environment."""
    ibkr = dict(cfg.get("ibkr") or {})
    host = os.environ.get("IBKR_HOST") or os.environ.get("TWS_HOST")
    port = os.environ.get("IBKR_PORT") or os.environ.get("TWS_PORT")
    account = os.environ.get("IBKR_ACCOUNT") or os.environ.get("IBKR_ACCOUNT_ID")
    if host:
        ibkr["host"] = host.strip()
    if port:
        ibkr["live_port"] = int(port)
    if account:
        ibkr["account_id"] = account.strip()
    cfg["ibkr"] = ibkr
    ingest = dict(cfg.get("ingest") or {})
    url = os.environ.get("SLEEVE_INGEST_URL")
    if url:
        ingest["url"] = url.strip()
        cfg["ingest"] = ingest
    return cfg


def load_config(path: Path | None = None) -> dict[str, Any]:
    cfg_path = path or (PKG_DIR / "config.yaml")
    with cfg_path.open(encoding="utf-8") as handle:
        cfg = yaml.safe_load(handle) or {}
    return apply_ibkr_env(cfg)


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

#!/usr/bin/env python3
"""Shared helpers for portfolio registry.json."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = ROOT / "_system" / "portfolio" / "registry.json"
CLASS_PATH = ROOT / "_system" / "portfolio" / "classification.json"
HOLDINGS_PATH = ROOT / "_system" / "portfolio" / "holdings.md"
US_CONFIG_PATH = ROOT / "_system" / "scripts" / "us_ticker_config.json"

EXCHANGE_META = {
    "8697.T": "TSE",
    "3905.T": "TSE",
    "7176.T": "TSE",
    "AMZN": "NASDAQ",
    "APLD": "NASDAQ",
    "BN": "NYSE",
    "CPRT": "NASDAQ",
    "CSGP": "NASDAQ",
    "CSU": "TSX",
    "DHR": "NYSE",
    "FRMO": "OTC",
    "HNFSA": "OTC Pink",
    "WRLC": "OTC Pink",
    "PDER": "OTC Pink",
    "BVERS": "OTC Pink",
    "GCCO": "OTC Pink",
    "CKX": "NYSE American",
    "GOOGL": "NASDAQ",
    "ICE": "NYSE",
    "KEWL": "OTC Pink",
    "OTCM": "OTCQX",
    "QDEL": "NASDAQ",
    "SJT": "NYSE",
    "SPGI": "NYSE",
    "TEQ.ST": "Nasdaq First North",
    "EVO.ST": "Nasdaq Stockholm",
    "WBI": "NYSE",
    "HE": "NYSE",
    "MIAX": "NYSE",
    "FNV": "NYSE",
    "WPM": "NYSE",
    "PBT": "NYSE",
    "CBOE": "CBOE",
    "CME": "CME",
    "OR": "NYSE",
    "TRC": "NYSE",
    "HKHC": "OTCQX",
    "MRSH": "NYSE",
    "DMLP": "NASDAQ",
    "GLXY": "NASDAQ",
    "BKRB": "NYSE",
    "MSTR": "NASDAQ",
    "RPRX": "NASDAQ",
    "RGLD": "NASDAQ",
    "SBR": "NYSE",
    "PCYO": "NASDAQ",
    "BUR": "NYSE",
    "ALS.TO": "TSX",
    "PSK.TO": "TSX",
    "ADN.TO": "TSX",
    "RYN": "NYSE",
    "PCH": "NASDAQ",
    "LAND": "NASDAQ",
    "IEX.NS": "NSE",
    "DRR.AX": "ASX",
    "IDA.AX": "ASX",
    "LSEG": "LSE",
    "PSH": "LSE",
    "CEE": "NYSE",
    "NAN": "NYSE",
    "URB.A.TO": "TSX",
    "RMV.L": "LSE",
    "0388.HK": "HKEX",
    "ABX": "NASDAQ",
    "ASX.AX": "ASX",
    "B3SA3.SA": "B3",
    "BMYS.KL": "KLSE",
    "BOLSAA.MX": "BMV",
    "BSM": "NYSE",
    "BYMA": "BYMA",
    "CDZI": "NASDAQ",
    "DB1.DE": "XETRA",
    "ENX.PA": "Euronext Paris",
    "EVR": "CSE",
    "GPW.WA": "WSE",
    "DNP.WA": "WSE",
    "GROY": "NYSE American",
    "HEE": "ATHEX",
    "KRP": "NYSE",
    "MTA": "NYSE American",
    "NDAQ": "NASDAQ",
    "NRP": "NYSE",
    "NZX.NZ": "NZX",
    "PSE": "PSE",
    "S68.SI": "SGX",
    "TASE": "TASE",
    "TFPM": "NYSE",
    "X.TO": "TSX",
    "XP": "NASDAQ",
}

DOWNLOAD_TYPE_OVERRIDES = {
    "QDEL": "us_dedicated",
    "CSU": "ca_csu",
    "TEQ.ST": "eu_teq",
    "EVO.ST": "uk_ir",
    "8697.T": "jp_ps1",
    "3905.T": "jp_archive",
    "7176.T": "jp_archive",
    "IEX.NS": "in_ir",
    "DRR.AX": "au_asx",
    "IDA.AX": "au_asx",
    "LSEG": "uk_ir",
    "PSH": "uk_ir",
    "URB.A.TO": "uk_ir",
    "RMV.L": "uk_ir",
    "0388.HK": "uk_ir",
    "B3SA3.SA": "uk_ir",
    "BMYS.KL": "uk_ir",
    "BOLSAA.MX": "uk_ir",
    "BYMA": "uk_ir",
    "DB1.DE": "uk_ir",
    "ENX.PA": "uk_ir",
    "EVR": "uk_ir",
    "GPW.WA": "uk_ir",
    "DNP.WA": "uk_ir",
    "HEE": "uk_ir",
    "NZX.NZ": "au_asx",
    "PSE": "uk_ir",
    "S68.SI": "uk_ir",
    "TASE": "uk_ir",
    "X.TO": "uk_ir",
    "ASX.AX": "au_asx",
}


def infer_market_from_ticker(ticker: str) -> str | None:
    """Suffix-based market when onboarding without explicit --market."""
    if ticker.endswith(".NS"):
        return "IN"
    if ticker.endswith(".T"):
        return "JP"
    if ticker.endswith(".AX"):
        return "AU"
    if ticker.endswith(".NZ"):
        return "AU"
    if ticker.endswith(".TO"):
        return "CA"
    if ticker.endswith(".HK"):
        return "EU"
    if ticker.endswith((".DE", ".PA", ".WA", ".SA", ".MX", ".KL", ".SI")):
        return "EU"
    if ticker.endswith(".L"):
        return "UK"
    if ticker == "LSEG":
        return "UK"
    return None


DEFAULT_CLASSIFICATION = {
    "archetype": "unknown",
    "moat": "unproven",
    "dhando": "pending",
    "stance": "watch",
    "cycle": "-",
    "moi_bucket": "pending",
    "payoff_lens": "pending",
    "investment_sleeve": "-",
}


def load_registry() -> dict:
    if not REGISTRY_PATH.exists():
        return {"meta": {"version": 1}, "holdings": {}, "watchlist": {}}
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def save_registry(data: dict) -> None:
    data.setdefault("meta", {})
    data["meta"]["version"] = 1
    data["meta"]["updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY_PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def infer_download_type(ticker: str, market: str, us_config: dict) -> str:
    if ticker in DOWNLOAD_TYPE_OVERRIDES:
        return DOWNLOAD_TYPE_OVERRIDES[ticker]
    if market in {"US", "CA"} and ticker in us_config:
        return "us_shared"
    if market == "US":
        return "us_shared"
    if market == "CA":
        return "ca_csu"
    if market in {"SE", "EU"}:
        return "eu_teq"
    if market == "IN":
        return "in_ir"
    if market == "UK":
        return "uk_ir"
    if market == "AU":
        return "au_asx"
    if market == "JP":
        return "jp_ps1"
    return "us_shared"


def build_download_block(ticker: str, market: str, us_config: dict) -> dict:
    dtype = infer_download_type(ticker, market, us_config)
    block: dict = {"type": dtype}
    cfg = us_config.get(ticker, {})
    if cfg:
        if cfg.get("cik"):
            block["cik"] = str(cfg["cik"])
        if cfg.get("ir_roots"):
            block["ir_roots"] = list(cfg["ir_roots"])
        opts = {}
        for key in ("min_filing_date", "sec_any_recent", "download_8k_exhibits"):
            if key in cfg:
                opts[key] = cfg[key]
        if opts:
            block["options"] = opts
    return block

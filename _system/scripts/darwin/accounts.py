"""Per-account paths and serving bundle (Roth IRA only).

Taxable Darwin paper book was retired 2026-07-11 — strategy is IRA-only.
Historical taxable artifacts may remain on disk for audit; they are not rebuilt.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .config import DATA_DIR, PORTFOLIO_DIR

# Production Darwin track: Roth IRA paper book only.
ACCOUNT_IDS = ("roth",)

# Retired accounts kept for path helpers / audit of old files (not in ACCOUNT_IDS).
RETIRED_ACCOUNT_IDS = ("taxable",)

MANDATE_FILES = {
    "roth": PORTFOLIO_DIR / "darwin_mandate_roth.json",
}

SERVING_PATH = DATA_DIR / "darwin_serving.json"
PAPER_DIR = PORTFOLIO_DIR / "paper"


@dataclass(frozen=True)
class AccountCtx:
    account_id: str
    mandate_path: Path
    portfolio_path: Path
    target_weights_path: Path
    paper_state_path: Path
    paper_events_path: Path


def account_ctx(account_id: str) -> AccountCtx:
    aid = account_id.lower()
    if aid not in ACCOUNT_IDS:
        raise ValueError(
            f"Unknown or retired account_id {account_id!r}; "
            f"production accounts: {ACCOUNT_IDS} (retired: {RETIRED_ACCOUNT_IDS})"
        )
    return AccountCtx(
        account_id=aid,
        mandate_path=MANDATE_FILES[aid],
        portfolio_path=DATA_DIR / f"darwin_portfolio_{aid}.json",
        target_weights_path=PORTFOLIO_DIR / f"{aid}_target_weights.json",
        paper_state_path=PAPER_DIR / f"{aid}.json",
        paper_events_path=PAPER_DIR / f"{aid}_events.jsonl",
    )


def load_mandate_for(account_id: str) -> dict:
    ctx = account_ctx(account_id)
    if not ctx.mandate_path.exists():
        raise FileNotFoundError(ctx.mandate_path)
    return json.loads(ctx.mandate_path.read_text(encoding="utf-8"))


def tier0_production(mandate_doc: dict) -> bool:
    return int(mandate_doc.get("tier", 0)) == 0


def build_serving(portfolios: dict[str, dict]) -> dict:
    """L4: single artifact for dashboard (IRA-only)."""
    accounts: dict[str, dict] = {}
    for aid, port in portfolios.items():
        if aid not in ACCOUNT_IDS:
            continue
        ctx = account_ctx(aid)
        paper = {}
        if ctx.paper_state_path.exists():
            try:
                paper = json.loads(ctx.paper_state_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                paper = {}
        champ = (port.get("benchmarks") or {}).get("champion") or {}
        accounts[aid] = {
            "policy_id": port.get("policy_id"),
            "regime": (port.get("regime") or {}).get("label"),
            "tier": port.get("tier", 0),
            "backtest_cumulative_pct": round((champ.get("cumulative_return") or 0) * 100, 2),
            "backtest_sharpe": champ.get("sharpe_annualized"),
            "paper": paper.get("last_mark"),
            "paper_inception": paper.get("inception_date"),
            "paper_status": paper.get("status", "tracking"),
            "paper_schema_version": paper.get("schema_version"),
            "paper_legacy_quarantine": paper.get("legacy_quarantine"),
            "portfolio": port,
        }
    bundle = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "accounts": accounts,
        "default_account": "roth",
        "account_scope": "ira_only",
        "retired_accounts": list(RETIRED_ACCOUNT_IDS),
    }
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SERVING_PATH.write_text(json.dumps(bundle, indent=2) + "\n", encoding="utf-8")
    return bundle

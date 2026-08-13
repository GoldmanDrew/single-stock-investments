"""Hard gates for propose / approve. Fail closed."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from . import PKG_DIR
from .classify_positions import classify_position, expand_blacklist_symbols, norm_sym
from .config_loader import load_blacklist, load_config, load_etf_ls_universe, load_etf_to_under, operator_config


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def kill_path(cfg: Mapping[str, Any] | None = None) -> Path:
    cfg = cfg or load_config()
    rel = str((cfg.get("paths") or {}).get("kill_file") or "KILL")
    return PKG_DIR / rel


@dataclass
class SafetyResult:
    ok: bool
    failures: list[str] = field(default_factory=list)

    def raise_if_failed(self) -> None:
        if not self.ok:
            raise PermissionError("; ".join(self.failures))


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:  # NaN
        return None
    return number


def check_safeties(
    *,
    owner: str,
    ticker: str,
    side: str,
    qty: float,
    limit_price: float,
    quote: Mapping[str, Any] | None,
    proposal: Mapping[str, Any] | None = None,
    typed_ticker: str | None = None,
    current_positions: Iterable[Mapping[str, Any]] | None = None,
    used_proposal_ids: Iterable[str] | None = None,
    recent_ticker_at: Mapping[str, datetime] | None = None,
    cfg: Mapping[str, Any] | None = None,
    now: datetime | None = None,
) -> SafetyResult:
    cfg = cfg or load_config()
    now = now or utcnow()
    failures: list[str] = []
    op = operator_config(cfg, owner)
    exec_cfg = cfg.get("execution") or {}
    ibkr = cfg.get("ibkr") or {}
    ticker_n = norm_sym(ticker)
    side_n = str(side or "").strip().upper()
    qty_n = _finite(qty)
    limit_n = _finite(limit_price)

    if kill_path(cfg).exists():
        failures.append("KILL file present; all orders blocked")

    if side_n not in {"BUY", "SELL"}:
        failures.append("side must be BUY or SELL")
    if qty_n is None or qty_n <= 0:
        failures.append("quantity must be positive")
    if limit_n is None or limit_n <= 0:
        failures.append("limit price must be positive")
    if not bool(exec_cfg.get("limit_orders_only", True)):
        failures.append("market orders are not allowed")

    if typed_ticker is not None and norm_sym(typed_ticker) != ticker_n:
        failures.append("typed ticker does not match proposal")

    allow_live = bool(exec_cfg.get("allow_live", False))
    dry_run = bool(exec_cfg.get("dry_run", True))
    if not dry_run and not allow_live:
        failures.append("live send requires execution.allow_live true")

    account = str(ibkr.get("account_id") or "")
    bound = str((quote or {}).get("account") or account)
    if account and bound and bound != account:
        failures.append(f"account mismatch: expected {account}")

    family = expand_blacklist_symbols(load_blacklist(cfg), load_etf_to_under(cfg))
    letf = load_etf_ls_universe(cfg)
    name_pos = {"symbol": ticker_n, "secType": "STK", "orderRef": ""}
    cls = classify_position(name_pos, blacklist_family=family, etf_ls_symbols=letf)
    if owner == "drew":
        if cls.bucket == "etf_ls":
            failures.append(f"{ticker_n} is a systematic LETF name; Drew cannot trade it")
        if cls.reason == "blacklist_family":
            failures.append(f"{ticker_n} is a blacklist-family name; it belongs on Michael's sleeve")
        if cls.bucket == "spx_0dte":
            failures.append("SPX 0DTE is out of scope")
    if owner == "michael":
        if cls.bucket == "etf_ls":
            failures.append(f"{ticker_n} is a systematic LETF plan name; Michael cannot submit it here")
        if cls.bucket == "spx_0dte":
            failures.append("SPX 0DTE is out of scope")

    quote = quote or {}
    last = _finite(quote.get("last") or quote.get("price"))
    quote_ts = quote.get("as_of")
    max_age = float(exec_cfg.get("quote_max_age_seconds") or 15)
    if last is None or last <= 0:
        failures.append("live quote missing")
    else:
        if quote_ts:
            try:
                parsed = datetime.fromisoformat(str(quote_ts).replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                age = (now - parsed).total_seconds()
                if age > max_age:
                    failures.append(f"quote is stale ({age:.0f}s)")
            except ValueError:
                failures.append("quote timestamp unreadable")
        band = float(exec_cfg.get("price_band_pct") or 0.01)
        if limit_n and abs(limit_n - last) / last > band + 1e-12:
            # Limit may be set at last; reject only if last moved vs propose snapshot.
            propose_last = _finite((proposal or {}).get("snapshot_last"))
            if propose_last and abs(last - propose_last) / propose_last > band:
                failures.append("quote moved outside the 1% band since propose")
            elif not propose_last and abs(limit_n - last) / last > 0.05:
                failures.append("limit is more than 5% from last")

    notional = (qty_n or 0) * (limit_n or 0)
    max_notional = float(op.get("max_notional_per_order") or 0)
    if max_notional and notional > max_notional + 1e-6:
        failures.append(f"notional {notional:.0f} exceeds max {max_notional:.0f}")

    equity = _finite(op.get("equity_usd"))
    extra = _finite(op.get("extra_margin_usd")) or 0.0
    positions = list(current_positions or [])
    owner_gross = 0.0
    owner_names: set[str] = set()
    for pos in positions:
        cls_p = pos.get("classification") or classify_position(
            pos, blacklist_family=family, etf_ls_symbols=letf
        )
        bucket = cls_p["bucket"] if isinstance(cls_p, dict) else cls_p.bucket
        reason = cls_p.get("reason") if isinstance(cls_p, dict) else cls_p.reason
        if bucket != ("drew" if owner == "drew" else "michael"):
            continue
        if reason == "cash":
            continue
        mv = abs(_finite(pos.get("marketValue") or pos.get("market_value")) or 0)
        if mv == 0:
            q = abs(_finite(pos.get("qty") or pos.get("position")) or 0)
            px = _finite(pos.get("mark") or pos.get("avgCost")) or 0
            mv = q * px
        owner_gross += mv
        owner_names.add(norm_sym(pos.get("symbol") or pos.get("ticker") or ""))

    if equity is None and owner == "michael":
        equity = owner_gross
    equity = equity or 0.0
    max_gross = equity + extra
    if equity > 0 and max_gross and owner_gross + notional > max_gross + 1e-6 and side_n == "BUY":
        failures.append(f"sleeve gross would exceed {max_gross:.0f}")
    max_pct = float(op.get("max_name_pct_of_equity") or 0)
    if equity and max_pct and notional > equity * max_pct + 1e-6 and side_n == "BUY":
        failures.append("name size exceeds max percent of equity")
    max_names = int(op.get("max_open_names") or 0)
    if max_names and ticker_n not in owner_names and len(owner_names) >= max_names and side_n == "BUY":
        failures.append("max open names reached")

    proposal_id = str((proposal or {}).get("proposal_id") or "")
    if proposal_id and proposal_id in set(used_proposal_ids or []):
        failures.append("proposal_id already used")

    cooldown = float(exec_cfg.get("cooldown_minutes") or 10)
    last_at = (recent_ticker_at or {}).get(ticker_n)
    if last_at is not None:
        if last_at.tzinfo is None:
            last_at = last_at.replace(tzinfo=timezone.utc)
        minutes = (now - last_at).total_seconds() / 60.0
        if minutes < cooldown:
            failures.append(f"cooldown: {ticker_n} traded {minutes:.1f} minutes ago")

    return SafetyResult(ok=not failures, failures=failures)

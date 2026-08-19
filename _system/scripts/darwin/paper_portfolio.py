"""Event-sourced Darwin paper book with one immutable mark per return period."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from .accounts import AccountCtx
from .prices import load_returns_csv


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _weighted_return(
    weights: dict[str, float],
) -> tuple[float, list[str], str | None, dict[str, str]]:
    """Return the latest common, immutable monthly mark for the target basket."""
    panels: dict[str, tuple[list[str], list[float], str]] = {}
    missing: list[str] = []
    common_dates: set[str] | None = None
    for ticker in weights:
        loaded = load_returns_csv(ticker)
        if not loaded or not loaded[0] or not loaded[1]:
            missing.append(ticker)
            continue
        panels[ticker] = loaded
        dates = set(loaded[0])
        common_dates = dates if common_dates is None else common_dates & dates
    source_period = max(common_dates) if common_dates else None
    total = 0.0
    for ticker, weight in weights.items():
        loaded = panels.get(ticker)
        if loaded is None or source_period is None:
            continue
        dates, returns, _source = loaded
        by_date = dict(zip(dates, returns))
        if source_period not in by_date:
            missing.append(ticker)
            continue
        total += weight * float(by_date[source_period])
    sources = {ticker: panel[2] for ticker, panel in panels.items()}
    return total, sorted(set(missing)), source_period, sources


def _append_event(ctx: AccountCtx, row: dict) -> None:
    ctx.paper_events_path.parent.mkdir(parents=True, exist_ok=True)
    with ctx.paper_events_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")


def _load_state(ctx: AccountCtx) -> dict | None:
    if not ctx.paper_state_path.exists():
        return None
    try:
        return json.loads(ctx.paper_state_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _save_state(ctx: AccountCtx, state: dict) -> None:
    ctx.paper_state_path.parent.mkdir(parents=True, exist_ok=True)
    ctx.paper_state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def update_paper_portfolio(
    ctx: AccountCtx,
    mandate_doc: dict,
    target_w: dict[str, float],
    policy_id: str,
    regime: dict,
    backtest: dict[str, Any],
) -> dict:
    paper_cfg = mandate_doc.get("paper") or {}
    initial_nav = float(paper_cfg.get("initial_nav_usd", 100_000))
    today = _today()
    champion_bt = (backtest.get("benchmarks") or {}).get("champion") or {}
    backtest_ref = {
        "cumulative_return_pct": round((champion_bt.get("cumulative_return") or 0) * 100, 2),
        "sharpe_annualized": champion_bt.get("sharpe_annualized"),
        "policy_id": policy_id,
    }
    weights_pct = {ticker: round(weight * 100, 2) for ticker, weight in target_w.items()}
    state = _load_state(ctx)
    if state is None:
        state = {
            "schema_version": "darwin_paper_state.v2",
            "status": "tracking",
            "account_id": ctx.account_id,
            "inception_date": today,
            "initial_nav_usd": initial_nav,
            "policy_id": policy_id,
            "regime": regime.get("label"),
            "weights_pct": weights_pct,
            "last_mark": {
                "date": today,
                "nav_usd": initial_nav,
                "period_return_pct": 0.0,
                "cumulative_return_pct": 0.0,
                "source_period": None,
            },
            "backtest_at_inception": backtest_ref,
        }
        _append_event(ctx, {
            "date": today,
            "event": "inception",
            "nav_usd": initial_nav,
            "policy_id": policy_id,
            "weights_pct": weights_pct,
        })
    else:
        legacy_mark = state.get("last_mark") or {}
        legacy_changed_nav = abs(float(legacy_mark.get("nav_usd") or initial_nav) - initial_nav) > 0.01
        legacy_changed_return = abs(float(legacy_mark.get("cumulative_return_pct") or 0)) > 0.001
        if legacy_mark.get("source_period") is None and (legacy_changed_nav or legacy_changed_return):
            reason = "Legacy pipeline runs compounded the same monthly return more than once."
            state["legacy_quarantine"] = {
                "reason": reason,
                "last_mark": legacy_mark,
                "quarantined_at": today,
            }
            state["last_mark"] = {
                "date": today,
                "nav_usd": initial_nav,
                "period_return_pct": 0.0,
                "cumulative_return_pct": 0.0,
                "source_period": None,
            }
            state["status"] = "tracking_after_legacy_quarantine"
            state["schema_version"] = "darwin_paper_state.v2"
            _append_event(ctx, {
                "date": today,
                "event": "legacy_mark_quarantined",
                "reason": reason,
                "legacy_mark": legacy_mark,
            })

        prev_nav = (state.get("last_mark") or {}).get("nav_usd") or initial_nav
        prev_weights = state.get("weights_pct") or {}
        drift = 0.5 * sum(
            abs(weights_pct.get(ticker, 0) - prev_weights.get(ticker, 0))
            for ticker in set(weights_pct) | set(prev_weights)
        )
        rebalanced = (
            state.get("policy_id") != policy_id
            or drift >= float(paper_cfg.get("min_weight_change_for_rebalance_pct", 1.0))
        )
        period_ret, missing, source_period, return_sources = _weighted_return(target_w)
        prior_period = (state.get("last_mark") or {}).get("source_period")
        apply_mark = bool(source_period and source_period != prior_period)
        nav = prev_nav * (1.0 + period_ret) if apply_mark else prev_nav
        cumulative = (nav / initial_nav - 1.0) * 100 if initial_nav else 0.0

        if rebalanced:
            _append_event(ctx, {
                "date": today,
                "event": "rebalance",
                "nav_usd": round(nav, 2),
                "policy_id": policy_id,
                "weight_drift_pct": round(drift, 2),
                "weights_pct": weights_pct,
            })
            state["policy_id"] = policy_id
            state["weights_pct"] = weights_pct

        if apply_mark or rebalanced:
            state["last_mark"] = {
                "date": today,
                "nav_usd": round(nav, 2),
                "period_return_pct": round(period_ret * 100, 3) if apply_mark else 0.0,
                "cumulative_return_pct": round(cumulative, 3),
                "source_period": source_period or prior_period,
            }
            state["regime"] = regime.get("label")
            state["backtest_latest"] = backtest_ref
            state["return_sources"] = return_sources
            state["returns_missing"] = missing
            _append_event(ctx, {
                "date": today,
                "event": "mark",
                "nav_usd": round(nav, 2),
                "period_return_pct": round(period_ret * 100, 3) if apply_mark else 0.0,
                "cumulative_return_pct": round(cumulative, 3),
                "source_period": source_period or prior_period,
                "mark_applied": apply_mark,
            })

    _save_state(ctx, state)
    return {
        "account_id": ctx.account_id,
        "inception_date": state.get("inception_date"),
        "last_mark": state.get("last_mark"),
        "backtest_at_inception": state.get("backtest_at_inception"),
        "backtest_latest": state.get("backtest_latest", backtest_ref),
        "policy_id": state.get("policy_id"),
        "status": state.get("status", "tracking"),
        "legacy_quarantine": state.get("legacy_quarantine"),
    }

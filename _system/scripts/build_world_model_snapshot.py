#!/usr/bin/env python3
"""Build monthly World Model snapshot + dashboard morning strip (Courtenay v2).

  python _system/scripts/build_world_model_snapshot.py
  python _system/scripts/build_world_model_snapshot.py --month 2026-07

Writes:
  _system/reference/kpi/history/{YYYY-MM}.json  (cold)
  dashboard/data/world_model.json                 (hot strip)

Includes: exceptions, passes, prediction cards, Superorg digests,
expert-horizon convergence, industry checklists.
"""
from __future__ import annotations

import argparse
import csv
import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kpi_history_stats as khs  # noqa: E402
import predictability as pred  # noqa: E402
import resolve_linkages  # noqa: E402
import world_model_common as wm  # noqa: E402


def _month_str(value: str | None) -> str:
    if value:
        return value[:7]
    return date.today().strftime("%Y-%m")


def _industry_membership() -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    if not wm.INDUSTRY_DIR.exists():
        return out
    for path in sorted(wm.INDUSTRY_DIR.glob("*.json")):
        node = wm.load_json(path) or {}
        nid = str(node.get("node_id") or path.stem)
        for t in node.get("linked_tickers") or []:
            out.setdefault(str(t).upper(), []).append(nid)
    return out


def collect_kpi_state() -> dict:
    broken: list[dict] = []
    stale: list[dict] = []
    unchecked: list[dict] = []
    passes: list[dict] = []
    ledger_summaries: list[dict] = []
    membership = _industry_membership()

    for ticker, path, ledger in wm.iter_kpi_ledgers():
        summary = ledger.get("summary") or wm.summarize_statuses(ledger.get("kpis") or [])
        industry_ids = ledger.get("industry_node_ids") or membership.get(ticker, [])
        ledger_summaries.append({
            "ticker": ticker,
            "as_of": ledger.get("as_of"),
            "theme_ids": ledger.get("theme_ids") or [],
            "industry_node_ids": industry_ids,
            "scaffold": bool((ledger.get("scaffold_meta") or {}).get("generated_by")),
            "summary": summary,
            "path": str(path.relative_to(wm.ROOT)).replace("\\", "/"),
        })
        for kpi in ledger.get("kpis") or []:
            row = pred.annotate_kpi_row({
                "ticker": ticker,
                "kpi_id": kpi.get("kpi_id"),
                "label": kpi.get("label"),
                "status": kpi.get("status"),
                "actual": (kpi.get("actual") or {}).get("value"),
                "expected": kpi.get("expected"),
                "binds_to": kpi.get("binds_to"),
                "last_checked": kpi.get("last_checked"),
                "source": kpi.get("source"),
                "prediction_role": kpi.get("prediction_role"),
                "industry_node_ids": industry_ids,
                "scaffold": bool((ledger.get("scaffold_meta") or {}).get("generated_by")),
                "magis_display": kpi.get("magis_display"),
            }, kpi)
            st = kpi.get("status")
            if st == "fail":
                broken.append(row)
            elif st == "stale":
                stale.append(row)
            elif st == "unchecked":
                unchecked.append(row)
            elif st == "pass":
                passes.append(row)

    derived = wm.load_json(wm.DERIVED_METRICS)
    drifted: list[dict] = []
    for edge_id, metric in (derived.get("metrics") or {}).items():
        if metric.get("status") in ("missing", "unsupported_formula") or metric.get("stale"):
            drifted.append({
                "edge_id": edge_id,
                "metric": metric.get("metric"),
                "status": metric.get("status"),
                "stale": metric.get("stale"),
                "as_of": metric.get("as_of"),
                "theme_id": metric.get("theme_id"),
                "latest": metric.get("latest"),
            })

    return {
        "broken": broken,
        "stale": stale,
        "unchecked": unchecked,
        "passes": passes,
        "drifted_edges": drifted,
        "ledgers": ledger_summaries,
    }


def load_prediction_cards() -> list[dict]:
    cards = []
    if not wm.PREDICTION_CARDS_DIR.exists():
        return cards
    for path in sorted(wm.PREDICTION_CARDS_DIR.glob("*.json")):
        card = wm.load_json(path)
        if not card:
            continue
        digest = {
            "theme_id": card.get("theme_id"),
            "label": card.get("label"),
            "phase_transition": (card.get("orientation") or {}).get("phase_transition"),
            "regulatory": (card.get("interference") or {}).get("regulatory"),
            "recursive": (card.get("reinforcement") or {}).get("recursive"),
            "gov_stimulus": (card.get("reinforcement") or {}).get("gov_stimulus"),
            "superorg_ids": (card.get("reinforcement") or {}).get("superorg_ids") or [],
            "tam_magnetism": (card.get("reinforcement") or {}).get("tam_magnetism"),
            "expected_value_note": card.get("expected_value_note"),
            "predictability_class": pred.class_for_card(card),
            "path": str(path.relative_to(wm.ROOT)).replace("\\", "/"),
        }
        cards.append(digest)
    return cards


def load_superorg_digests() -> list[dict]:
    out = []
    if not wm.SUPERORG_DIR.exists():
        return out
    for path in sorted(wm.SUPERORG_DIR.glob("*.json")):
        org = wm.load_json(path)
        if not org:
            continue
        pillars = org.get("pillars") or {}
        traffic = {
            name: (meta or {}).get("status")
            for name, meta in pillars.items()
        }
        out.append({
            "org_id": org.get("org_id"),
            "label": org.get("label"),
            "ticker": org.get("ticker"),
            "tickers": org.get("tickers"),
            "role": org.get("role"),
            "summary": org.get("summary"),
            "pillars": traffic,
            "stance_implication": org.get("stance_implication"),
            "predictability_class": "P2_formation",
            "path": str(path.relative_to(wm.ROOT)).replace("\\", "/"),
        })
    return out


def _horizon_rows(domain: str) -> list[dict]:
    path = wm.EXPERT_HORIZONS_DIR / f"{domain}.csv"
    if not path.exists():
        return []
    rows = []
    with path.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            try:
                years = float(row.get("years_ahead") or "")
            except ValueError:
                continue
            rows.append({
                "date": row.get("date"),
                "speaker": row.get("speaker"),
                "org": row.get("org"),
                "years_ahead": years,
                "quote_note": row.get("quote_note"),
            })
    rows.sort(key=lambda r: r.get("date") or "")
    return rows


def load_expert_horizons() -> list[dict]:
    domains = []
    if not wm.EXPERT_HORIZONS_DIR.exists():
        return domains
    for path in sorted(wm.EXPERT_HORIZONS_DIR.glob("*.csv")):
        domain = path.stem
        rows = _horizon_rows(domain)
        if len(rows) < 2:
            convergence = "insufficient_history"
            delta = None
        else:
            first, last = rows[0]["years_ahead"], rows[-1]["years_ahead"]
            delta = round(last - first, 2)
            # Courtenay/Musk: years_ahead falling = accelerating / converging
            if delta < -1:
                convergence = "converging"
            elif delta > 1:
                convergence = "receding"
            else:
                convergence = "flat"
        domains.append({
            "domain": domain,
            "convergence": convergence,
            "years_ahead_delta": delta,
            "latest": rows[-1] if rows else None,
            "quote_count": len(rows),
            "in_base_irr": False,
            "predictability_class": pred.class_for_horizon(),
            "claim_note": "Public quote observation — not a Magis forecast",
            "path": str(path.relative_to(wm.ROOT)).replace("\\", "/"),
        })
    return domains


def load_industry_nodes() -> list[dict]:
    out = []
    if not wm.INDUSTRY_DIR.exists():
        return out
    for path in sorted(wm.INDUSTRY_DIR.glob("*.json")):
        node = wm.load_json(path)
        if not node:
            continue
        kind = node.get("kind") or "thesis"
        out.append({
            "node_id": node.get("node_id"),
            "label": node.get("label"),
            "kind": kind,
            "formation_tag": node.get("formation_tag"),
            "checklist": node.get("checklist"),
            "linked_theme_ids": node.get("linked_theme_ids") or [],
            "linked_horizon_domains": node.get("linked_horizon_domains") or [],
            "linked_tickers": node.get("linked_tickers") or [],
            "path": str(path.relative_to(wm.ROOT)).replace("\\", "/"),
        })
    return out


def _industry_scope_line(industry: list) -> str:
    thesis = [n for n in industry if (n.get("kind") or "thesis") != "horizon_industry"]
    horizon = [n for n in industry if n.get("kind") == "horizon_industry"]
    thesis_labels = ", ".join(n.get("label") or n.get("node_id") or "?" for n in thesis) or "none"
    horizon_labels = ", ".join(n.get("label") or n.get("node_id") or "?" for n in horizon) or "none"
    return (
        f"Industries: {len(industry)} "
        f"({len(thesis)} thesis: {thesis_labels}; "
        f"{len(horizon)} horizon: {horizon_labels}). "
        f"Macro is a regime card, not an industry."
    )


def _is_soft_fail(row: dict) -> bool:
    """High/med gameability fails are Goodhart/noise floors — diligence, not strip 'broken'."""
    return str(row.get("gameability") or "") in {"med", "high"}


def build_strip(
    state: dict,
    month: str,
    cards: list,
    superorgs: list,
    horizons: list,
    industry: list,
    history_series: dict | None = None,
) -> dict:
    hard_broken = [r for r in state["broken"] if not _is_soft_fail(r)]
    soft_broken = [r for r in state["broken"] if _is_soft_fail(r)]
    broken_n = len(state["broken"])
    hard_n = len(hard_broken)
    soft_n = len(soft_broken)
    stale_n = len(state["stale"])
    drift_n = len(state["drifted_edges"])
    unchecked_n = len(state["unchecked"])
    pass_n = len(state["passes"])
    # Soft vol-floor / Goodhart fails open diligence but must not paint Magis "broken".
    if hard_n:
        label = "broken"
    elif soft_n or stale_n or drift_n:
        label = "attention"
    else:
        label = "steady"

    headlines: list[dict] = []
    for row in hard_broken[:6]:
        headlines.append({
            "kind": "fail",
            "ticker": row["ticker"],
            "text": f"{row['ticker']} {row['kpi_id']} failed gate",
            "binds_to": row.get("binds_to"),
        })
    for row in soft_broken[:6]:
        headlines.append({
            "kind": "soft_fail",
            "ticker": row["ticker"],
            "text": (
                f"{row['ticker']} {row['kpi_id']} soft floor miss "
                f"(gameability={row.get('gameability')}; diligence, not thesis break)"
            ),
            "binds_to": row.get("binds_to"),
        })
    for row in state["stale"][:4]:
        headlines.append({
            "kind": "stale",
            "ticker": row["ticker"],
            "text": f"{row['ticker']} {row['kpi_id']} stale",
            "binds_to": row.get("binds_to"),
        })
    for row in state["drifted_edges"][:4]:
        headlines.append({
            "kind": "drift",
            "ticker": None,
            "text": f"edge {row['edge_id']} drifted ({row.get('status')})",
            "edge_id": row["edge_id"],
        })

    phase_likely = [c["theme_id"] for c in cards if c.get("phase_transition") == "likely"]
    converging = [h["domain"] for h in horizons if h.get("convergence") == "converging"]
    industry_scope = _industry_scope_line(industry)
    thesis_n = sum(1 for n in industry if (n.get("kind") or "thesis") != "horizon_industry")
    horizon_ind_n = sum(1 for n in industry if n.get("kind") == "horizon_industry")

    kpi_pool = list(state["broken"]) + list(state["stale"]) + list(state["passes"])
    boundaries = pred.build_claim_boundaries(
        cards=cards,
        horizons=horizons,
        industry=industry,
        kpi_rows=kpi_pool,
    )
    claim_ceiling = boundaries["claim_ceiling"]
    ceiling_short = pred.short_label(claim_ceiling)

    summary = (
        f"World Model: {hard_n} hard-failed, {soft_n} soft-floor, {stale_n} stale, "
        f"{drift_n} drifted, {unchecked_n} unchecked, {pass_n} passing. "
        f"{industry_scope} "
        f"Phase-likely themes: {', '.join(phase_likely) or 'none'}. "
        f"Horizon converging: {', '.join(converging) or 'none'}. "
        f"Steady means hard gates held, not path certainty. "
        f"Soft vol floors (Goodhart) never alone mark the strip broken."
    )
    ev_stance = (
        f"[{ceiling_short}] Buy dips when orientation+reinforcement hold and hard KPI gates pass; "
        "pause when hard thesis KPIs fail. Soft vol-floor misses are diligence noise. "
        "Context only; does not rewrite the universal contract or human decision."
    )

    return {
        "label": label,
        "as_of": date.today().isoformat(),
        "month": month,
        "summary": summary,
        "ev_stance": ev_stance,
        "claim_ceiling": claim_ceiling,
        "claim_boundaries": boundaries,
        "disclaimer": (
            "Context only. KPI breaks and Superorg pillar gaps open diligence; "
            "they do not rewrite Power Zone routes, universal contracts, IC packets, "
            "or human_decision.json. Magis claim ceiling gates language, not capital."
        ),
        "counts": {
            "fail": broken_n,
            "fail_hard": hard_n,
            "fail_soft": soft_n,
            "stale": stale_n,
            "unchecked": unchecked_n,
            "pass": pass_n,
            "drifted_edges": drift_n,
            "ledgers": len(state["ledgers"]),
            "prediction_cards": len(cards),
            "superorgs": len(superorgs),
            "expert_horizon_domains": len(horizons),
            "industry_nodes": len(industry),
            "thesis_industries": thesis_n,
            "horizon_industries": horizon_ind_n,
            "goodhart_watch": len(boundaries.get("goodhart_watch") or []),
        },
        "industry_scope": industry_scope,
        "headlines": headlines,
        "broken": hard_broken,
        "soft_fails": soft_broken,
        "stale": state["stale"],
        "drifted_edges": state["drifted_edges"],
        "unchecked": state["unchecked"][:20],
        "passes": state["passes"],
        "history_series": history_series or {},
        "ledgers": state["ledgers"],
        "prediction_cards": cards,
        "superorgs": superorgs,
        "expert_horizons": horizons,
        "industry_nodes": industry,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--month", help="YYYY-MM snapshot month (default: current)")
    ap.add_argument(
        "--skip-resolve",
        action="store_true",
        help="Do not re-run resolve_linkages before snapshot",
    )
    args = ap.parse_args()
    month = _month_str(args.month)

    if not args.skip_resolve:
        manifest = wm.load_json(wm.LINKAGES_MANIFEST)
        metrics = {}
        for edge in manifest.get("edges") or []:
            resolved = resolve_linkages.resolve_edge(edge)
            if resolved:
                metrics[str(resolved.get("edge_id"))] = resolved
        wm.write_json(
            wm.DERIVED_METRICS,
            {
                "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "as_of": date.today().isoformat(),
                "disclaimer": (
                    "Context only. Derived linkages inform KPI ledgers; "
                    "they never rewrite universal contracts or human decisions."
                ),
                "edge_count": len(metrics),
                "metrics": metrics,
            },
        )

    state = collect_kpi_state()
    # Seed sparse ledger archives from prior monthly cold snapshots, then annotate.
    khs.bootstrap_ledger_from_monthly_history()
    hist_rows = (
        list(state["broken"])
        + list(state["stale"])
        + list(state["passes"])
        + list(state["unchecked"])
    )
    history_series = khs.annotate_rows(hist_rows)
    cards = load_prediction_cards()
    superorgs = load_superorg_digests()
    horizons = load_expert_horizons()
    industry = load_industry_nodes()
    strip = build_strip(state, month, cards, superorgs, horizons, industry, history_series)

    hot = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "schema_version": "2.2",
        "strip": strip,
    }
    wm.write_json(wm.DASHBOARD_WORLD_MODEL, hot)

    cold = {
        "month": month,
        "generated_at": hot["generated_at"],
        "counts": strip["counts"],
        "broken": state["broken"],
        "stale": state["stale"],
        "drifted_edges": state["drifted_edges"],
        "unchecked": state["unchecked"],
        "passes": state["passes"],
        "ledgers": state["ledgers"],
        "prediction_cards": cards,
        "superorgs": superorgs,
        "expert_horizons": horizons,
        "industry_nodes": industry,
        "derived_metrics_as_of": wm.load_json(wm.DERIVED_METRICS).get("as_of"),
    }
    history_path = wm.KPI_HISTORY_DIR / f"{month}.json"
    wm.write_json(history_path, cold)

    print(f"wrote {wm.DASHBOARD_WORLD_MODEL.relative_to(wm.ROOT)}")
    print(f"wrote {history_path.relative_to(wm.ROOT)}")
    z_ok = sum(
        1
        for r in (strip.get("passes") or [])
        if (r.get("history") or {}).get("z_score") is not None
    )
    print(
        f"world_model: label={strip['label']} "
        f"claim_ceiling={strip.get('claim_ceiling')} "
        f"fail={strip['counts']['fail']} pass={strip['counts']['pass']} "
        f"z_ok={z_ok}/{strip['counts']['pass']} "
        f"series={len(history_series)} "
        f"cards={strip['counts']['prediction_cards']} "
        f"superorgs={strip['counts']['superorgs']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

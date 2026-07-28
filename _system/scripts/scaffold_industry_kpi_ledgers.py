#!/usr/bin/env python3
"""Scaffold kpi_ledger.json for every industry-linked ticker missing one.

Does not overwrite existing ledgers unless --force-scaffolded (only files with
scaffold_meta.generated_by == this script).

  python _system/scripts/scaffold_industry_kpi_ledgers.py
  python _system/scripts/scaffold_industry_kpi_ledgers.py --write
  python _system/scripts/scaffold_industry_kpi_ledgers.py --write --force-scaffolded

KPI rows prefer theme: sources so check_kpi_ledger can fill actuals. Binds use
stance notes (not fragile valuation_path) so lint passes without deep overlays.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import world_model_common as wm  # noqa: E402

TODAY = date.today().isoformat()
GENERATOR = "scaffold_industry_kpi_ledgers.py"
EXCHANGE_VOL_MAP = wm.WORLD_MODEL_DIR / "exchange_vol_map.json"


def _kpi(
    kpi_id: str,
    label: str,
    *,
    unit: str,
    op: str,
    value: float,
    source: str,
    role: str,
    note: str,
    horizon: str = "context",
    evidence_tier: str = "market",
    shared_theme: bool | None = None,
) -> dict:
    # Theme-backed series are industry/cluster pulses, not issuer-specific facts.
    is_shared = (
        bool(shared_theme)
        if shared_theme is not None
        else str(source or "").startswith("theme:")
    )
    row = {
        "kpi_id": kpi_id,
        "label": label,
        "unit": unit,
        "expected": {"op": op, "value": value, "horizon": horizon},
        "actual": {"value": None, "as_of": None},
        "status": "unchecked",
        "source": source,
        "evidence_tier": evidence_tier,
        "last_checked": TODAY,
        "binds_to": {
            "on_fail": "open_diligence",
            "note": note,
        },
        "in_base_irr": False,
        "prediction_role": role,
    }
    if is_shared:
        row["magis_display"] = {
            "mode": "shared_theme",
            "note": "Same series for every name in this industry — not issuer cash.",
        }
    return row


# Shared theme-backed building blocks
HYPER = _kpi(
    "hyperscaler_capex_guide_bn",
    "Hyperscaler capex guide (USD bn · shared demand pulse)",
    unit="usd_bn",
    op="gte",
    value=300,
    source="theme:hyperscaler_capex_ttm_usd_bn",
    role="orientation",
    note="Upstream AI demand pulse for the industry cluster — not this issuer's capex",
    horizon="2026",
    evidence_tier="derived_filing",
)
WTI = _kpi(
    "wti_crude_usd",
    "WTI crude (USD/bbl · shared)",
    unit="usd_bbl",
    op="gte",
    value=50,
    source="theme:wti_crude",
    role="orientation",
    note="Commodity cycle floor for land/royalty activity (shared theme)",
    horizon="cycle_floor",
)
HH = _kpi(
    "henry_hub_gas",
    "Henry Hub gas (USD/mmbtu · shared)",
    unit="usd_mmbtu",
    op="lte",
    value=8,
    source="theme:henry_hub_gas",
    role="interference",
    note="Power/gas cost interference for hosting and miners (shared theme)",
    horizon="cost_ceiling",
)
VIX = _kpi(
    "vix_level",
    "VIX index (shared · exchange/risk pulse)",
    unit="index",
    op="gte",
    value=12,
    source="theme:vix_level",
    role="orientation",
    note="US VIX — global risk / US croupier pulse (shared theme)",
    horizon="vol_floor_for_croupier",
)
SPYVOL = _kpi(
    "spy_20d_realized_vol",
    "SPY 20d realized vol % (shared)",
    unit="pct",
    op="gte",
    value=8,
    source="theme:spy_20d_realized_vol",
    role="orientation",
    note="US equity realized vol for transaction intensity (shared theme)",
    horizon="equity_vol_floor",
)
# Weaker proxy for sticky index/data fees — labeled honestly.
INDEX_VIX = _kpi(
    "vix_level",
    "VIX (weak proxy for fee activity · shared)",
    unit="index",
    op="gte",
    value=12,
    source="theme:vix_level",
    role="orientation",
    note="Not ASV/retention — only a soft activity overlay for index/data fee names",
    horizon="vol_floor_for_croupier",
)
INDEX_SPYVOL = _kpi(
    "spy_20d_realized_vol",
    "SPY 20d vol (weak fee-activity proxy · shared)",
    unit="pct",
    op="gte",
    value=8,
    source="theme:spy_20d_realized_vol",
    role="orientation",
    note="Not subscription economics — soft equity-vol overlay for market-data names",
    horizon="equity_vol_floor",
)
def load_exchange_vol_map() -> dict:
    return wm.load_json(EXCHANGE_VOL_MAP) or {}


def region_for_ticker(ticker: str, vol_map: dict | None = None) -> str:
    vol_map = vol_map or load_exchange_vol_map()
    regions = (vol_map.get("ticker_region") or {})
    return str(regions.get(ticker.upper()) or vol_map.get("default_region") or "US")


def exchange_market_kpis(ticker: str) -> list[dict]:
    """Home-market vol primary; US VIX secondary for non-US venues."""
    vol_map = load_exchange_vol_map()
    region_id = region_for_ticker(ticker, vol_map)
    region = (vol_map.get("regions") or {}).get(region_id) or (vol_map.get("regions") or {}).get("US") or {}
    out: list[dict] = []

    realized_id = region.get("realized_vol_series")
    if realized_id:
        gate = float(region.get("gate_realized_gte") or 8)
        out.append(
            _kpi(
                realized_id,
                str(region.get("realized_vol_label") or realized_id),
                unit="pct",
                op="gte",
                value=gate,
                source=f"theme:{realized_id}",
                role="orientation",
                note=f"Home-market realized vol ({region_id})"
                + (f" - {region['note']}" if region.get("note") else ""),
                horizon="equity_vol_floor",
            )
        )

    implied_id = region.get("implied_vol_series")
    if implied_id:
        gate_i = float(region.get("gate_implied_gte") or 12)
        out.append(
            _kpi(
                implied_id,
                str(region.get("implied_vol_label") or implied_id),
                unit="index",
                op="gte",
                value=gate_i,
                source=f"theme:{implied_id}",
                role="orientation",
                note=f"Home-market implied vol ({region_id})",
                horizon="vol_floor_for_croupier",
            )
        )

    # Non-US: keep US VIX as secondary global risk context.
    if region_id != "US":
        out.append(
            _kpi(
                "vix_level_global",
                "US VIX (global risk context)",
                unit="index",
                op="gte",
                value=12,
                source="theme:vix_level",
                role="orientation",
                note="Secondary global risk overlay - not the home-market croupier pulse",
                horizon="global_risk",
            )
        )

    return out or [VIX, SPYVOL]
GOLD = _kpi(
    "gold_spot_proxy",
    "Gold spot proxy (shared · GLD when London fix unavailable)",
    unit="usd_gld",
    op="gte",
    value=200,
    source="theme:gold_spot_usd",
    role="orientation",
    note="Bullion floor for royalty compounders (shared theme)",
    horizon="bullion_floor",
)
GDX = _kpi(
    "gdx_gld_ratio",
    "GDX / GLD ratio (shared · miners vs bullion)",
    unit="ratio",
    op="gte",
    value=0.1,
    source="theme:gdx_gld_ratio",
    role="orientation",
    note="Miner vs bullion sentiment for royalty multiples (shared theme)",
    horizon="sentiment_floor",
)
TPL_WATER = _kpi(
    "tpl_water_revenue_m",
    "Cluster water proof (TPL segment revenue, USD m · shared)",
    unit="usd_m",
    op="gte",
    value=200,
    source="theme:tpl_water_revenue_m",
    role="reinforcement",
    note="Shared Permian/Southwest water-activity proof from TPL filings — not this issuer's revenue unless ticker is TPL",
    horizon="water_proof",
    evidence_tier="derived_filing",
)
HOUSING = _kpi(
    "housing_starts",
    "US housing starts (thousands SAAR · shared)",
    unit="thousands",
    op="gte",
    value=900,
    source="theme:housing_starts",
    role="orientation",
    note="Housing-cycle pulse for timber / stumpage demand (shared theme)",
    horizon="housing_floor",
)
PERMITS = _kpi(
    "building_permits",
    "US building permits (thousands SAAR · shared)",
    unit="thousands",
    op="gte",
    value=900,
    source="theme:building_permits",
    role="orientation",
    note="Housing pipeline pulse for timber names (shared theme)",
    horizon="housing_pipeline",
)
UST10 = _kpi(
    "ust_10y",
    "US 10Y yield % (duration context · shared)",
    unit="pct",
    op="gte",
    value=1,
    source="theme:ust_10y",
    role="orientation",
    note="Duration / discount-rate context for royalty cash — not LOE or company FCF",
    horizon="duration",
)
BTC = _kpi(
    "btc_usd",
    "Bitcoin spot (USD · shared)",
    unit="usd",
    op="gte",
    value=20000,
    source="theme:btc_usd",
    role="orientation",
    note="Miner revenue pulse (shared theme)",
    horizon="btc_floor",
)
BTC_TREASURY = _kpi(
    "btc_usd",
    "Bitcoin spot (USD · treasury proxy · shared)",
    unit="usd",
    op="gte",
    value=20000,
    source="theme:btc_usd",
    role="orientation",
    note="BTC treasury / proxy exposure — not energized hashrate operations",
    horizon="btc_floor",
)
URA = _kpi(
    "ura_etf",
    "URA uranium ETF (USD · shared sentiment)",
    unit="usd",
    op="gte",
    value=15,
    source="theme:ura_etf",
    role="orientation",
    note="Uranium / nuclear equity sentiment (shared theme) — not contracted GW",
    horizon="uranium_floor",
)
ROBOTAXI_H = _kpi(
    "robotaxi_years_ahead",
    "Robotaxi public-quote years ahead (P0 · shared)",
    unit="years",
    op="lte",
    value=15,
    source="theme:robotaxi_years_ahead",
    role="orientation",
    note="Public arrival-date quotes (Waymo/Tesla/etc.) — Magis observation only, not a forecast",
    horizon="expert_quote",
    evidence_tier="public_quote",
)
ROBOTAXI_H["binds_to"]["on_fail"] = "stance_only"
AGI_H = _kpi(
    "agi_years_ahead",
    "AGI public-quote years ahead (P0 · shared)",
    unit="years",
    op="lte",
    value=25,
    source="theme:agi_years_ahead",
    role="orientation",
    note="Public arrival-date quotes — Magis observation only, not a forecast",
    horizon="expert_quote",
    evidence_tier="public_quote",
)
AGI_H["binds_to"]["on_fail"] = "stance_only"


# MSTR is BTC treasury / proxy, not a hashrate operator
BTC_TREASURY_TICKERS = {"MSTR"}


INDUSTRY_TEMPLATES: dict[str, list[dict]] = {
    "ai_power": [HYPER, WTI, HH],
    "water_surface": [HYPER, WTI, TPL_WATER],
    "hyperscaler_cloud": [HYPER, HH],
    "gold_royalty": [GOLD, GDX],
    # exchange_markets resolved per-ticker via exchange_market_kpis()
    "exchange_markets": [],
    "market_data_indices": [INDEX_VIX, INDEX_SPYVOL],
    "timber_land": [HOUSING, PERMITS],
    "btc_mining_power": [BTC, HYPER, HH],
    "energy_royalty": [WTI, HH],
    # XLV/XBI stay on the theme card only — do not stamp onto every pharma ticker
    "pharma_royalty": [UST10],
    "nuclear_firm_power": [URA, HYPER, HH],
    "agi": [HYPER, AGI_H],
    "robotaxi": [ROBOTAXI_H],
    # eVTOL air taxis — not ground robotaxi; no shared robotaxi-years stamp
    "evtol_air_taxi": [],
}


def load_industry_membership() -> dict[str, list[str]]:
    """ticker -> ordered industry_node_ids."""
    membership: dict[str, list[str]] = {}
    if not wm.INDUSTRY_DIR.exists():
        return membership
    for path in sorted(wm.INDUSTRY_DIR.glob("*.json")):
        node = wm.load_json(path) or {}
        nid = node.get("node_id") or path.stem
        for t in node.get("linked_tickers") or []:
            membership.setdefault(str(t).upper(), []).append(str(nid))
    return membership


def themes_for_industries(industry_ids: list[str]) -> list[str]:
    themes: list[str] = []
    for nid in industry_ids:
        node = wm.load_json(wm.INDUSTRY_DIR / f"{nid}.json") or {}
        for tid in node.get("linked_theme_ids") or []:
            if tid not in themes:
                themes.append(tid)
    if "macro_regime" not in themes:
        themes.append("macro_regime")
    return themes


def merge_template_kpis(industry_ids: list[str], ticker: str | None = None) -> list[dict]:
    """Union KPIs across industries; first industry wins on duplicate kpi_id."""
    out: list[dict] = []
    seen: set[str] = set()
    t = (ticker or "").upper()
    for nid in industry_ids:
        if nid == "exchange_markets" and ticker:
            template_rows = exchange_market_kpis(ticker)
        elif nid == "btc_mining_power" and t in BTC_TREASURY_TICKERS:
            template_rows = [BTC_TREASURY]
        else:
            template_rows = INDUSTRY_TEMPLATES.get(nid) or []
        for kpi in template_rows:
            kid = kpi["kpi_id"]
            if kid in seen:
                continue
            seen.add(kid)
            row = dict(kpi)
            row["expected"] = dict(kpi["expected"])
            row["actual"] = dict(kpi.get("actual") or {"value": None, "as_of": None})
            row["binds_to"] = dict(kpi["binds_to"])
            if kpi.get("magis_display"):
                row["magis_display"] = dict(kpi["magis_display"])
            out.append(row)
            if len(out) >= 12:
                return out
    return out


def adapt_kpis_for_ticker(ticker: str, kpis: list[dict]) -> list[dict]:
    """Drop valuation: binds that do not exist; keep theme/manual. Clarify cluster labels."""
    val = wm.load_json(wm.ROOT / ticker / "research" / "valuation.json")
    adapted = []
    t = ticker.upper()
    for kpi in kpis:
        row = dict(kpi)
        row["expected"] = dict(kpi["expected"])
        row["actual"] = dict(kpi.get("actual") or {"value": None, "as_of": None})
        row["binds_to"] = dict(kpi["binds_to"])
        if kpi.get("magis_display"):
            row["magis_display"] = dict(kpi["magis_display"])
        src = str(row.get("source") or "")
        # Issuer-native label when TPL itself carries the water filing panel
        if row.get("kpi_id") == "tpl_water_revenue_m" and t == "TPL":
            row["label"] = "TPL water segment revenue (USD m · filing)"
            row["binds_to"] = {
                **row["binds_to"],
                "note": "TPL water segment from filing panel (issuer-native)",
            }
            # Still shared-series for Magis dedupe across water cluster, but clearer label
        if src.startswith("valuation:"):
            path = src.split(":", 1)[1]
            if not val or not wm.path_exists(val, path):
                # Convert to manual stance row so lint passes
                row["source"] = "manual:human"
                row["evidence_tier"] = "assumption"
                row["status"] = "unchecked"
                row["actual"] = {"value": None, "as_of": None}
                row["binds_to"] = {
                    "on_fail": "open_diligence",
                    "note": f"{row['binds_to'].get('note', row['kpi_id'])} "
                    f"(inputs.price unavailable — manual until valuation priced)",
                }
                row.pop("magis_display", None)
        adapted.append(row)
    return adapted


def build_ledger(ticker: str, industry_ids: list[str]) -> dict:
    kpis = adapt_kpis_for_ticker(ticker, merge_template_kpis(industry_ids, ticker=ticker))
    meta_note = "Industry-template scaffold. Context only; refine gates from filings."
    if "exchange_markets" in industry_ids:
        meta_note += f" Exchange vol region={region_for_ticker(ticker)}."
    return {
        "ticker": ticker,
        "as_of": TODAY,
        "theme_ids": themes_for_industries(industry_ids),
        "industry_node_ids": industry_ids,
        "schema_version": "1.0",
        "scaffold_meta": {
            "generated_by": GENERATOR,
            "generated_at": TODAY,
            "note": meta_note,
            **(
                {"exchange_vol_region": region_for_ticker(ticker)}
                if "exchange_markets" in industry_ids
                else {}
            ),
        },
        "kpis": kpis,
        "summary": wm.summarize_statuses(kpis),
        "disclaimer": (
            "Context only. Industry-scaffold KPIs do not auto-rewrite Lawrence base IRR."
        ),
    }


def is_scaffold(ledger: dict) -> bool:
    meta = ledger.get("scaffold_meta") or {}
    return meta.get("generated_by") == GENERATOR


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true", help="Write missing ledgers")
    ap.add_argument(
        "--force-scaffolded",
        action="store_true",
        help="Overwrite ledgers previously generated by this script",
    )
    ap.add_argument(
        "--industry",
        action="append",
        default=[],
        help="Only tickers linked to this industry node (repeatable)",
    )
    ap.add_argument("tickers", nargs="*", help="Limit to these tickers")
    args = ap.parse_args()
    wanted = {t.upper() for t in args.tickers} if args.tickers else None
    industry_filter = {str(x) for x in (args.industry or [])}

    membership = load_industry_membership()
    created = 0
    skipped = 0
    refreshed = 0
    for ticker, industry_ids in sorted(membership.items()):
        if wanted and ticker not in wanted:
            continue
        if industry_filter and not industry_filter.intersection(industry_ids):
            continue
        # Skip names with no folder at all? Create research/ under ticker if folder exists
        ticker_dir = wm.ROOT / ticker
        if not ticker_dir.is_dir():
            print(f"{ticker}: skip (no ticker folder)")
            skipped += 1
            continue
        path = ticker_dir / "research" / "kpi_ledger.json"
        existing = wm.load_json(path) if path.exists() else {}
        if path.exists() and not (args.force_scaffolded and is_scaffold(existing)):
            print(f"{ticker}: keep existing ledger ({len(existing.get('kpis') or [])} KPIs)")
            skipped += 1
            continue
        ledger = build_ledger(ticker, industry_ids)
        action = "refresh" if path.exists() else "create"
        print(
            f"{ticker}: {action} scaffold industries={industry_ids} "
            f"kpis={len(ledger['kpis'])}"
        )
        if args.write:
            wm.write_json(path, ledger)
            if action == "create":
                created += 1
            else:
                refreshed += 1
        else:
            created += 1  # dry-run would-create count

    mode = "wrote" if args.write else "dry-run"
    print(
        f"scaffold_industry_kpi_ledgers: {mode} "
        f"create/refresh={created + refreshed} skipped={skipped} "
        f"members={len(membership)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

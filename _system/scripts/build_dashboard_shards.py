#!/usr/bin/env python3
"""Shard the dashboard payload into core.json + per-ticker / per-section files.

The SPA boots from ``dashboard/data/core.json`` (slim rows, summary, filters)
and lazy-fetches:

- ``dashboard/data/tickers/{TICKER}.json``  full ticker detail on row select
- ``dashboard/data/insights/{section}.json`` insights sub-tab shards
- existing standalone artifacts (``kpi_trends.json``, ``document_catalog.json``,
  ``research_memory.json``, ``index_membership.json``) on section open

``dashboard_data.json`` remains the pipeline contract for build scripts and
validators; the browser no longer downloads it.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

CORE_VERSION = 1

# Row fields only needed once a ticker is opened in the detail pane.
DETAIL_ONLY_FIELDS = (
    "download_script_path",
    "two_phase_watch",
    "insights",
    "insight_events",
    "letter_discussants",
    "dossier",
    "research_memory",
    "kpi_trends",
    "valuation_workbench",
    "lenses",
    "active_lenses",
    "silent_lens_count",
    "recent_files",
    "developments",
    "transcripts",
    "total_return_panel",
    "pricing_analysis",
    "properties",
    "links",
    "investment_committee",
    "human_review",
    "decision_summary",
)

# Top-level payload keys that stay out of core.json (fetched lazily instead).
CORE_EXCLUDED_TOP_LEVEL = (
    "kpi_trends",
    "document_catalog",
    "activist_feed",
    "darwin",
    "darwin_accounts",
    "darwin_serving",
)

# Compact insight item fields kept in slim essential_insights entries.
_INSIGHT_ITEM_FIELDS = ("title", "summary", "source", "date", "quarter", "evidence_url")

# insights.json keys routed to per-section shard files.
INSIGHTS_SHARDS = {
    "letters": ("letter_index",),
    "events": ("events", "events_by_ticker"),
    "consensus": ("consensus",),
    "registry": ("fund_registry",),
    "profiles": ("fund_profiles",),
    "tickers": ("by_ticker", "ticker_discussants"),
    "podcasts": ("podcast_index", "podcast_by_show"),
}

_SAFE_TICKER_RE = re.compile(r"[^A-Za-z0-9._-]")


def shard_filename(ticker: str) -> str:
    return _SAFE_TICKER_RE.sub("_", str(ticker)) + ".json"


def _dump(obj) -> str:
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False)


def _compact_insight_item(item) -> dict | None:
    if not isinstance(item, dict):
        return None
    return {k: item.get(k) for k in _INSIGHT_ITEM_FIELDS if item.get(k) is not None}


# component_valuation subfields the detail pane alone renders. Every one of
# these is already written in full to the per-ticker shard, and
# loadTickerDetail() does `Object.assign({}, row, full)` -- a shallow merge, so
# the shard's complete object replaces this slim one the moment a ticker is
# opened. Keeping them in core.json was pure duplication: 863 KB of the 6.01 MB
# boot payload, against a 6.0 MB budget core.json crossed on 2026-08-20.
#
# What stays is exactly what the holdings table needs before any ticker is
# opened: `status`, `total_equity_value_per_share` and `upside_downside_pct` are
# table sort keys (index.html sortKey 'component_valuation.*'), and
# `market_price_per_share` feeds the value-gap cell. Both other call sites
# (renderValuationStatusCell, renderLegacyComponentNote) only test the object
# for existence.
_COMPONENT_VALUATION_DETAIL_ONLY = (
    "economic_value",      # 561 KB -- renderComponentValuation only
    "components",          # 283 KB -- renderComponentValuation only
    "decision_rule",       #  16 KB -- renderComponentValuation only
    "review_status",       #   3 KB -- renderComponentValuation only
    "review_open_count",   #         -- rendered beside review_status
)


def _slim_component_valuation(cv: dict) -> dict:
    """Drop the detail-pane schedule, keep the table's sort and display keys."""
    return {k: v for k, v in cv.items() if k not in _COMPONENT_VALUATION_DETAIL_ONLY}


def _slim_essential_insights(essential: dict) -> dict:
    slim = {
        k: v
        for k, v in essential.items()
        if k not in ("bullets", "owner", "latest", "bull", "bear")
    }
    bullets = essential.get("bullets")
    if isinstance(bullets, list) and bullets:
        first = _compact_insight_item(bullets[0])
        slim["bullets"] = [first] if first else []
    for key in ("owner", "latest"):
        compact = _compact_insight_item(essential.get(key))
        if compact:
            slim[key] = compact
    return slim


def slim_ticker_row(row: dict) -> dict:
    """Trim a full dashboard row down to what the holdings table needs."""
    slim = {k: v for k, v in row.items() if k not in DETAIL_ONLY_FIELDS}
    essential = row.get("essential_insights")
    if isinstance(essential, dict):
        slim["essential_insights"] = _slim_essential_insights(essential)
    component_valuation = row.get("component_valuation")
    if isinstance(component_valuation, dict):
        slim["component_valuation"] = _slim_component_valuation(component_valuation)
    # KPI badge summary keeps the table's trend hints without the series.
    kpi = row.get("kpi_trends")
    if isinstance(kpi, dict):
        slim["kpi_trends"] = {
            "summary": kpi.get("summary"),
            "business_momentum": kpi.get("business_momentum"),
            "leadership_risk": kpi.get("leadership_risk"),
            "data_tier": kpi.get("data_tier"),
            "has_trend_data": kpi.get("has_trend_data"),
        }
    membership = row.get("index_membership")
    if isinstance(membership, dict):
        compact = dict(membership)
        if isinstance(compact.get("scorecards"), list):
            compact["scorecards"] = [
                {k: s.get(k) for k in ("index", "status", "distance", "rank") if k in s}
                for s in compact["scorecards"][:6]
                if isinstance(s, dict)
            ]
        if isinstance(compact.get("confirmed_events"), list):
            compact["confirmed_events"] = compact["confirmed_events"][:3]
        compact.pop("inputs_missing", None)
        slim["index_membership"] = compact
    slim["detail_shard"] = f"data/tickers/{shard_filename(row.get('ticker', ''))}"
    return slim


def build_core_payload(payload: dict) -> dict:
    core = {
        k: v for k, v in payload.items() if k not in CORE_EXCLUDED_TOP_LEVEL
    }
    core["tickers"] = [slim_ticker_row(r) for r in payload.get("tickers") or []]
    core["core_version"] = CORE_VERSION
    core["shards"] = {
        "tickers_dir": "data/tickers/",
        "insights_dir": "data/insights/",
        "kpi_trends": "data/kpi_trends.json",
        "document_catalog": "data/document_catalog.json",
        "research_memory": "data/research_memory.json",
        "index_membership": "data/index_membership.json",
        "activist_feed": "data/activist_feed.json",
        "darwin_bundle": "data/darwin_bundle.json",
    }
    doc_catalog = payload.get("document_catalog")
    if isinstance(doc_catalog, dict):
        core["document_catalog_ref"] = {
            "path": "dashboard/data/document_catalog.json",
            "generated_at": doc_catalog.get("generated_at"),
            "document_count": len(doc_catalog.get("documents") or []),
        }
    kpi = payload.get("kpi_trends")
    if isinstance(kpi, dict):
        core["kpi_trends_ref"] = {
            "path": "dashboard/data/kpi_trends.json",
            "generated_at": kpi.get("generated_at"),
            "inflection_count": kpi.get("inflection_count", 0),
        }
    return core


def write_ticker_shards(payload: dict, data_dir: Path) -> int:
    tickers_dir = data_dir / "tickers"
    tickers_dir.mkdir(parents=True, exist_ok=True)
    written: set[str] = set()
    for row in payload.get("tickers") or []:
        name = shard_filename(row.get("ticker", ""))
        (tickers_dir / name).write_text(_dump(row), encoding="utf-8")
        written.add(name)
    # Prune shards for tickers no longer in the universe.
    removed = 0
    for stale in tickers_dir.glob("*.json"):
        if stale.name not in written:
            stale.unlink()
            removed += 1
    if removed:
        print(f"Pruned {removed} stale ticker shard(s)")
    return len(written)


def write_insights_shards(insights_doc: dict | None, data_dir: Path) -> int:
    insights_dir = data_dir / "insights"
    insights_dir.mkdir(parents=True, exist_ok=True)
    if not isinstance(insights_doc, dict):
        return 0
    sharded_keys = {k for keys in INSIGHTS_SHARDS.values() for k in keys}
    manifest = {k: v for k, v in insights_doc.items() if k not in sharded_keys}
    manifest["shards"] = {
        name: f"data/insights/{name}.json" for name in INSIGHTS_SHARDS
    }
    (insights_dir / "manifest.json").write_text(_dump(manifest), encoding="utf-8")
    count = 1
    # Every shard carries the parent doc's stamp. Without it a shard cannot be
    # registered as a P6 data feed at all: podcasts.json held 3,561 episodes and
    # no date, so nothing could tell that its newest episode was 2026-07-28 and
    # the pipeline had not run since. A feed with no stamp cannot go stale --
    # it can only be noticed by a human reading the page.
    stamp = insights_doc.get("generated_at")
    for name, keys in INSIGHTS_SHARDS.items():
        shard = {k: insights_doc.get(k) for k in keys}
        if stamp is not None:
            shard["generated_at"] = stamp
        (insights_dir / f"{name}.json").write_text(_dump(shard), encoding="utf-8")
        count += 1
    return count


def write_darwin_bundle(payload: dict, data_dir: Path) -> None:
    bundle = {
        k: payload[k]
        for k in ("darwin", "darwin_accounts", "darwin_serving")
        if payload.get(k) is not None
    }
    if bundle:
        (data_dir / "darwin_bundle.json").write_text(_dump(bundle), encoding="utf-8")


def write_shards(payload: dict, insights_doc: dict | None, data_dir: Path) -> dict:
    core = build_core_payload(payload)
    core_path = data_dir / "core.json"
    core_path.write_text(_dump(core), encoding="utf-8")
    write_darwin_bundle(payload, data_dir)
    ticker_count = write_ticker_shards(payload, data_dir)
    insight_count = write_insights_shards(insights_doc, data_dir)
    core_mb = core_path.stat().st_size / 1e6
    print(
        f"Wrote {core_path} ({core_mb:.2f} MB), {ticker_count} ticker shard(s), "
        f"{insight_count} insights shard(s)"
    )
    return {
        "core_bytes": core_path.stat().st_size,
        "ticker_shards": ticker_count,
        "insights_shards": insight_count,
    }

#!/usr/bin/env python3
"""Canonical persona registry: ids and independence groups, single source.

Two hand-synced copies of this map (power_zone_router.py and
investment_committee_pipeline.py) diverged: the pipeline's copy was missing
munger and lawrence, and its ``.get(persona, persona)`` fallback minted each
a private single-member group named after itself. 31 of 76 committee
manifests seated [buffett_weschler, hohn, munger] -- two quality_reinvestment
raters out of three -- while passing the three-distinct-groups check.

Both scripts now import this module. Invariant L6 (graph_invariants.py)
asserts these ids stay equal to the personas.json / power_zones.json
registries, that no other script re-defines a GROUPS literal, and that no
active committee manifest's raters collapse below the independence quorum
under THIS map.
"""
from __future__ import annotations

INDEPENDENCE_QUORUM = 3

INDEPENDENCE_GROUPS = {
    "hohn": "competitive_advantage",
    "buffett_weschler": "quality_reinvestment",
    "munger": "quality_reinvestment",
    "lawrence": "quality_reinvestment",
    "marathon_capital_cycle": "capital_cycle",
    "marks_credit_cycle": "credit_cycle",
    "klarman_asset_value": "asset_realization",
    "hk": "scarce_assets",
    "stahl": "scarce_assets",
    "pabrai": "asymmetry_downside",
    "greenblatt": "special_situations",
    "moi": "special_situations",
}

PERSONA_IDS = frozenset(INDEPENDENCE_GROUPS)

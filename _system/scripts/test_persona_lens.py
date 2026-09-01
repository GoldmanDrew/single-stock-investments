#!/usr/bin/env python3
"""Unit tests for persona lens determinism and blend math."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from persona_lens_common import (  # noqa: E402
    build_consensus,
    build_universe_stats,
    build_valuation_blend,
    extract_shared_context,
    weighted_median,
)


class PersonaLensTests(unittest.TestCase):
    def test_weighted_median(self):
        med = weighted_median([(9.0, 1.0), (11.0, 1.0), (10.0, 0.5)])
        self.assertAlmostEqual(med, 10.0, places=1)

    def test_blend_example(self):
        lenses = [
            {"persona": "hohn", "label": "Hohn", "relevance": 1.0, "return_pct": 9.0, "verdict": "watch"},
            {"persona": "buffett", "label": "Buffett", "relevance": 1.0, "return_pct": 11.0, "verdict": "hold"},
            {"persona": "munger", "label": "Munger", "relevance": 0.5, "return_pct": 10.0, "verdict": "watch"},
        ]
        blend = build_valuation_blend(lenses)
        self.assertAlmostEqual(blend["blended_return_pct"], 10.0, places=1)

    def test_single_contributor_cannot_publish_consensus_stance(self):
        lenses = [
            {
                "persona": "greenblatt",
                "label": "Joel Greenblatt",
                "relevance": 0.5,
                "return_pct": 21.72,
                "verdict": "watch",
            }
        ]
        blend = build_valuation_blend(lenses)

        consensus = build_consensus(
            lenses,
            blend,
            portfolio_bar=15.0,
            ctx={"moat": "none", "dhando": "none"},
        )

        self.assertTrue(blend["low_coverage"])
        self.assertEqual(consensus["stance"], "pending")
        self.assertEqual(consensus["agreement_pct"], 0)

    def test_nvda_rebuild_deterministic(self):
        val_path = ROOT / "NVDA" / "research" / "valuation.json"
        if not val_path.exists():
            self.skipTest("NVDA valuation missing")
        import json

        from persona_lens_common import build_lenses_for_ticker, stable_json

        val = json.loads(val_path.read_text(encoding="utf-8"))
        stats = build_universe_stats()
        rebuilt = build_lenses_for_ticker("NVDA", stats)
        existing = json.loads((ROOT / "NVDA" / "research" / "lenses.json").read_text(encoding="utf-8"))
        self.assertEqual(stable_json(rebuilt), stable_json(existing))


if __name__ == "__main__":
    raise SystemExit(unittest.main())

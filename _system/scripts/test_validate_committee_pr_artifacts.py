from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from validate_committee_pr_artifacts import validate_paths


class ValidateCommitteePrArtifactsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.work = self.root / "AAA" / "research" / "committee_work" / "2026-07-20"
        self.work.mkdir(parents=True)
        (self.work / "manifest.json").write_text(
            json.dumps(
                {
                    "ticker": "AAA",
                    "as_of": "2026-07-20",
                    "selected_raters": [
                        {
                            "persona": "hohn",
                            "independence_group": "competitive_advantage",
                        }
                    ],
                }
            )
            + "\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def write_vote(self) -> str:
        path = self.work / "round_1" / "hohn.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "persona": "hohn",
                    "independence_group": "competitive_advantage",
                    "evidence_status": "sufficient",
                    "scores": {
                        dim: {"value": 3, "rationale": "ok"}
                        for dim in (
                            "explanatory_strength",
                            "evidence_sufficiency",
                            "downside_control",
                            "return_vs_alternatives",
                        )
                    },
                    "vote": "watch",
                    "claims": [{"claim": "c", "evidence_paths": ["AAA/research/thesis.md"]}],
                    "strongest_counter_explanation": "alt",
                    "most_important_missing_fact": "gap",
                    "falsifiers": ["break"],
                    "specialist_findings": "within zone",
                    "confidence": "medium",
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return "AAA/research/committee_work/2026-07-20/round_1/hohn.json"

    def test_valid_round_vote_passes(self):
        path = self.write_vote()
        self.assertEqual(validate_paths([path], root=self.root), [])

    def test_rejects_research_manifest_mix(self):
        path = self.write_vote()
        errors = validate_paths(
            [path, "AAA/research/research_agent_manifest.json"],
            root=self.root,
        )
        self.assertTrue(any("only change committee_work" in err for err in errors))

    def test_rejects_manifest_edits(self):
        errors = validate_paths(
            ["AAA/research/committee_work/2026-07-20/manifest.json"],
            root=self.root,
        )
        self.assertTrue(any("frozen/deterministic" in err for err in errors))

    def test_rejects_unknown_persona(self):
        path = self.work / "round_1" / "pabrai.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}", encoding="utf-8")
        errors = validate_paths(
            ["AAA/research/committee_work/2026-07-20/round_1/pabrai.json"],
            root=self.root,
        )
        self.assertTrue(any("not a selected rater" in err for err in errors))

    def test_valid_pre_mortem_passes(self):
        rel = "AAA/research/committee_work/2026-07-20/pre_mortem.json"
        (self.root / rel).write_text(
            json.dumps(
                {
                    "status": "complete",
                    "failure_story": "failed",
                    "earliest_warning_signals": ["signal"],
                    "forensic_checks": ["check"],
                    "short_source_coverage": "partial",
                    "unresolved_items": [],
                    "evidence_packet_hash": "",
                }
            )
            + "\n",
            encoding="utf-8",
        )
        self.assertEqual(validate_paths([rel], root=self.root), [])


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import build_research_agent_manifest
import ir_adapter_gate


class AgentEvidenceGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, relative: str, value) -> None:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(value) if isinstance(value, (dict, list)) else str(value)
        path.write_text(text, encoding="utf-8")

    def test_research_hash_ignores_dispatch_reason(self):
        self.write("AAA/investor-documents/DOWNLOAD_MANIFEST.json", [{"filingDate": "2026-07-18"}])
        with patch.object(build_research_agent_manifest, "ROOT", self.root):
            first = build_research_agent_manifest.build_manifest("AAA", "new_documents")
            second = build_research_agent_manifest.build_manifest("AAA", "manual_material_change")
        self.assertTrue(first["ready"])
        self.assertEqual(first["evidence_hash"], second["evidence_hash"])

    def test_generated_refresh_artifacts_do_not_change_primary_evidence_hash(self):
        self.write("AAA/investor-documents/DOWNLOAD_MANIFEST.json", [{"accession": "0001"}])
        with patch.object(build_research_agent_manifest, "ROOT", self.root):
            first = build_research_agent_manifest.build_manifest("AAA", "new_documents")
        self.write("AAA/research/valuation_route.json", {"generated_at": "2026-07-20T00:00:00Z"})
        self.write("AAA/research/valuation_workbench.json", {"generated_at": "2026-07-20T00:00:00Z"})
        self.write("AAA/research/evidence_task_queue.json", {"items": ["refresh"]})
        with patch.object(build_research_agent_manifest, "ROOT", self.root):
            second = build_research_agent_manifest.build_manifest("AAA", "new_documents")
        self.assertEqual(first["evidence_hash"], second["evidence_hash"])

    def test_manifest_refresh_timestamp_does_not_change_primary_evidence_hash(self):
        self.write(
            "AAA/investor-documents/DOWNLOAD_MANIFEST.json",
            [{"accession": "0001", "generated_at": "2026-07-20T00:00:00Z"}],
        )
        with patch.object(build_research_agent_manifest, "ROOT", self.root):
            first = build_research_agent_manifest.build_manifest("AAA", "new_documents")
        self.write(
            "AAA/investor-documents/DOWNLOAD_MANIFEST.json",
            [{"accession": "0001", "generated_at": "2026-07-20T01:00:00Z"}],
        )
        with patch.object(build_research_agent_manifest, "ROOT", self.root):
            second = build_research_agent_manifest.build_manifest("AAA", "new_documents")
        self.assertEqual(first["evidence_hash"], second["evidence_hash"])

    def test_new_primary_document_changes_evidence_hash(self):
        self.write("AAA/investor-documents/DOWNLOAD_MANIFEST.json", [{"accession": "0001"}])
        with patch.object(build_research_agent_manifest, "ROOT", self.root):
            first = build_research_agent_manifest.build_manifest("AAA", "new_documents")
        self.write(
            "AAA/investor-documents/DOWNLOAD_MANIFEST.json",
            [{"accession": "0001"}, {"accession": "0002"}],
        )
        with patch.object(build_research_agent_manifest, "ROOT", self.root):
            second = build_research_agent_manifest.build_manifest("AAA", "new_documents")
        self.assertNotEqual(first["evidence_hash"], second["evidence_hash"])

    def test_forecast_work_id_changes_gate_hash_not_primary_hash(self):
        self.write("AAA/investor-documents/DOWNLOAD_MANIFEST.json", [{"accession": "0001"}])
        queue = {"items": [{
            "work_id": "w1", "task_type": "author_forecast",
            "input_sha": "abc", "component_fingerprint": "component-1",
        }]}
        self.write("_system/data/epistemic_work_queue.json", queue)
        with patch.object(build_research_agent_manifest, "ROOT", self.root):
            first = build_research_agent_manifest.build_manifest(
                "AAA", "epistemic_author_forecast:w1:component")
        queue["items"][0]["work_id"] = "w2"
        self.write("_system/data/epistemic_work_queue.json", queue)
        with patch.object(build_research_agent_manifest, "ROOT", self.root):
            second = build_research_agent_manifest.build_manifest(
                "AAA", "epistemic_author_forecast:w2:component")
        self.assertEqual(first["primary_evidence_hash"], second["primary_evidence_hash"])
        self.assertNotEqual(first["evidence_hash"], second["evidence_hash"])

    def test_working_ir_adapter_suppresses_vicki(self):
        self.write("AAA/.onboard_status.json", {"download_detail": "ir_gap"})
        self.write("AAA/investor-documents/ir_adapter.json", {"deterministic_status": "working"})
        with patch.object(ir_adapter_gate, "ROOT", self.root):
            result = ir_adapter_gate.evaluate("AAA")
        self.assertFalse(result["eligible"])
        self.assertEqual(result["reason"], "deterministic_adapter_working")

    def test_failed_adapter_admits_vicki(self):
        self.write("AAA/.onboard_status.json", {"download_detail": "ir_gap"})
        self.write("AAA/investor-documents/ir_adapter.json", {"deterministic_status": "failed"})
        with patch.object(ir_adapter_gate, "ROOT", self.root):
            result = ir_adapter_gate.evaluate("AAA")
        self.assertTrue(result["eligible"])
        self.assertEqual(result["reason"], "adapter_failed")


if __name__ == "__main__":
    unittest.main()

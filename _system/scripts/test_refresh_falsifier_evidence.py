from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

import refresh_falsifier_evidence


class RefreshFalsifierEvidenceTests(unittest.TestCase):
    def test_only_observable_testable_sidecars_are_refreshed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for ticker, observable, untestable in (
                ("DUE", "2026-08-01", False),
                ("FUTURE", "2026-09-01", False),
                ("MANUAL", None, True),
            ):
                path = root / ticker / "research/falsifier_specs.json"
                path.parent.mkdir(parents=True)
                path.write_text(json.dumps({"specs": [{
                    "spec_id": ticker.lower(), "untestable": untestable,
                    "measurement_period_end": "2026-06-30" if observable else None,
                    "observable_after": observable,
                    "resolution_deadline": "2026-10-01" if observable else None,
                }]}), encoding="utf-8")
            self.assertEqual(refresh_falsifier_evidence.due_tickers(
                root, date(2026, 8, 12)), ["DUE"])


if __name__ == "__main__":
    unittest.main()

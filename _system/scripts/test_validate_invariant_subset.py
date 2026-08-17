from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from validate_invariant_subset import validate


class InvariantSubsetTests(unittest.TestCase):
    def test_unrelated_failure_does_not_block_lane(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "invariants.json"
            path.write_text(json.dumps({"invariants": [
                {"id": "E2", "severity": "hard", "count": 0},
                {"id": "P6", "severity": "hard", "count": 3},
            ]}), encoding="utf-8")
            self.assertEqual(validate(path, {"E2"}), [])
            self.assertTrue(validate(path, {"P6"}))

    def test_missing_owned_invariant_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "invariants.json"
            path.write_text('{"invariants": []}', encoding="utf-8")
            self.assertTrue(validate(path, {"E7"}))


if __name__ == "__main__":
    unittest.main()

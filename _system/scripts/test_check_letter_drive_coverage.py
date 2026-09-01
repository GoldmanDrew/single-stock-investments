from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import check_letter_drive_coverage as coverage


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


class DriveCoverageTests(unittest.TestCase):
    def test_drive_denominator_counts_pdfs_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            folders = root / "folders.json"
            filenames = root / "filenames.json"
            write_json(folders, {
                "folders": {"Letters/2026 Q3": {"id": "quarter-folder"}},
            })
            write_json(filenames, {
                "by_filename": {
                    "letter-a.pdf": {
                        "id": "a", "name": "letter-a.pdf", "parents": ["quarter-folder"],
                    },
                    "letter-b.PDF": {
                        "id": "b", "name": "letter-b.PDF", "parents": ["quarter-folder"],
                    },
                    ".gitkeep": {
                        "id": "sentinel", "name": ".gitkeep", "parents": ["quarter-folder"],
                    },
                    "README.md": {
                        "id": "readme", "name": "README.md", "parents": ["quarter-folder"],
                    },
                },
            })
            with mock.patch.object(coverage, "FOLDER_INDEX_PATH", folders), \
                 mock.patch.object(coverage, "FILENAME_INDEX_PATH", filenames):
                self.assertEqual(coverage.drive_counts_by_quarter(), {"2026Q3": 2})


if __name__ == "__main__":
    unittest.main()

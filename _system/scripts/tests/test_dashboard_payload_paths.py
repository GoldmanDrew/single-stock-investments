"""Every path the dashboard payload carries must be POSIX, on every OS.

The payload is built on whatever machine runs the rebuild and is then served
verbatim by Cloudflare -- the deploy workflow never rebuilds it (see
ci_dashboard_deploy_mode.sh, which writes skip_rebuild=true on every branch).
So a rebuild run on Windows ships whatever separators it produced.

has_download_script() used to return str(path.relative_to(ROOT)), which is
"AVGO\\investor-documents\\download_avgo_investor_docs.py" on Windows and a
dead link in every place the dashboard renders it. 819 of 833 shards carried
it. Every other path-emitting site in build_dashboard_data.py already
normalises; this pins the one that did not.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import build_dashboard_data as builder  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
SHARDS = ROOT / "dashboard" / "data" / "tickers"
BACKSLASH = chr(92)

# Payload fields that name a repo file. Anything here must be POSIX.
PATH_FIELDS = (
    "download_script_path",
    "index_file",
    "readme",
    "research_dir",
    "folder",
)


class DownloadScriptPathTests(unittest.TestCase):
    def test_returns_posix_separators_for_a_real_ticker(self):
        # Any ticker that actually has a download script exercises the branch;
        # the repo always has some, and the test says so rather than skipping
        # quietly if that ever stops being true.
        found = None
        for candidate in sorted(ROOT.glob("*/investor-documents")):
            ok, path = builder.has_download_script(candidate.parent)
            if ok and path:
                found = (candidate.parent.name, path)
                break
        self.assertIsNotNone(found, "no ticker in the repo has a download script")
        ticker, path = found
        self.assertNotIn(BACKSLASH, path, f"{ticker}: {path!r} carries a Windows separator")
        self.assertTrue(path.startswith(f"{ticker}/"), f"{ticker}: {path!r} is not repo-relative")

    def test_synthetic_ticker_tree_yields_posix(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            docs = root / "ZZZZ" / "investor-documents"
            docs.mkdir(parents=True)
            (docs / "download_zzzz_investor_docs.py").write_text("", encoding="utf-8")
            original = builder.ROOT
            try:
                builder.ROOT = root
                ok, path = builder.has_download_script(root / "ZZZZ")
            finally:
                builder.ROOT = original
        self.assertTrue(ok)
        self.assertEqual(path, "ZZZZ/investor-documents/download_zzzz_investor_docs.py")


class CommittedShardTests(unittest.TestCase):
    def test_no_committed_shard_carries_a_windows_separator(self):
        if not SHARDS.is_dir():
            self.skipTest("no committed ticker shards in this checkout")
        offenders = []
        for shard in sorted(SHARDS.glob("*.json")):
            try:
                data = json.loads(shard.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            for field in PATH_FIELDS:
                value = data.get(field)
                if isinstance(value, str) and BACKSLASH in value:
                    offenders.append(f"{shard.name}:{field}={value}")
        self.assertEqual(offenders[:8], [], f"{len(offenders)} shard path(s) not POSIX")


if __name__ == "__main__":
    unittest.main()

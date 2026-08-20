#!/usr/bin/env python3
"""Drive credential materialization for cloud Grok / Cursor Cloud Agents."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parents[1]

SAMPLE_SA = {
    "type": "service_account",
    "project_id": "single-stock-pdf-store",
    "client_email": "pdf-store-uploader@single-stock-pdf-store.iam.gserviceaccount.com",
    "token_uri": "https://oauth2.googleapis.com/token",
    "private_key": "-----BEGIN PRIVATE KEY-----\nnot-a-real-key\n-----END PRIVATE KEY-----\n",
}


class MaterializeDriveCredentialsTests(unittest.TestCase):
    def setUp(self) -> None:
        sys_path_insert()
        from materialize_drive_credentials import materialize_drive_credentials

        self.materialize = materialize_drive_credentials
        self._saved = {
            key: os.environ.get(key)
            for key in (
                "GOOGLE_APPLICATION_CREDENTIALS",
                "GOOGLE_APPLICATION_CREDENTIALS_JSON",
                "SSI_DRIVE_CREDENTIALS_PATH",
                "SSI_CLOUD_ENV_SNIPPET",
            )
        }
        for key in self._saved:
            os.environ.pop(key, None)

    def tearDown(self) -> None:
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_writes_json_secret_to_file_and_snippet(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "google-service-account.json"
            snippet = Path(tmp) / "ssi-cloud-env.sh"
            os.environ["GOOGLE_APPLICATION_CREDENTIALS_JSON"] = json.dumps(SAMPLE_SA)
            result = self.materialize(key_path=dest, snippet_path=snippet)
            self.assertEqual(result["status"], "materialized")
            self.assertEqual(Path(result["path"]), dest)
            written = json.loads(dest.read_text(encoding="utf-8"))
            self.assertEqual(written["client_email"], SAMPLE_SA["client_email"])
            self.assertTrue(snippet.is_file())
            text = snippet.read_text(encoding="utf-8")
            self.assertIn("export GOOGLE_APPLICATION_CREDENTIALS=", text)
            self.assertIn(dest.name, text)
            self.assertEqual(os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"), str(dest))

    def test_keeps_existing_credentials_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            existing = Path(tmp) / "already.json"
            existing.write_text(json.dumps(SAMPLE_SA), encoding="utf-8")
            dest = Path(tmp) / "should-not-write.json"
            snippet = Path(tmp) / "ssi-cloud-env.sh"
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(existing)
            os.environ["GOOGLE_APPLICATION_CREDENTIALS_JSON"] = json.dumps(SAMPLE_SA)
            result = self.materialize(key_path=dest, snippet_path=snippet)
            self.assertEqual(result["status"], "existing")
            self.assertEqual(Path(result["path"]), existing)
            self.assertFalse(dest.exists())

    def test_missing_secret_is_unset_not_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = self.materialize(
                key_path=Path(tmp) / "google-service-account.json",
                snippet_path=Path(tmp) / "ssi-cloud-env.sh",
                secrets_path=Path(tmp) / "missing.json",
            )
            self.assertEqual(result["status"], "unset")
            self.assertIsNone(result["path"])

    def test_local_secrets_file_is_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            secrets = Path(tmp) / "google-service-account.json"
            secrets.write_text(json.dumps(SAMPLE_SA), encoding="utf-8")
            snippet = Path(tmp) / "ssi-cloud-env.sh"
            result = self.materialize(
                key_path=Path(tmp) / "cloud.json",
                snippet_path=snippet,
                secrets_path=secrets,
            )
            self.assertEqual(result["status"], "local_secrets")
            self.assertEqual(Path(result["path"]), secrets)

    def test_rejects_non_service_account_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["GOOGLE_APPLICATION_CREDENTIALS_JSON"] = json.dumps({"hello": "world"})
            with self.assertRaises(SystemExit) as caught:
                self.materialize(
                    key_path=Path(tmp) / "google-service-account.json",
                    snippet_path=Path(tmp) / "ssi-cloud-env.sh",
                )
            self.assertIn("service_account", str(caught.exception))


class PlanIntakeDropTests(unittest.TestCase):
    def setUp(self) -> None:
        sys_path_insert()
        from drive_intake_drop import plan_intake_drop

        self.plan = plan_intake_drop
        preferred = ["TPL", "FRMO", "APLD", "AMR"]
        self.ticker = next((name for name in preferred if (ROOT / name).is_dir()), None)
        if self.ticker is None:
            tickers = [
                p.name
                for p in ROOT.iterdir()
                if p.is_dir() and p.name.isupper() and not p.name.startswith(("_", "."))
            ]
            self.ticker = tickers[0]

    def test_vic_pdf_plans_admin_intake_child(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "idea.pdf"
            pdf.write_bytes(b"%PDF-1.4\n")
            planned = self.plan(kind="VIC", ticker=self.ticker, pdf_path=pdf, root=ROOT)
            self.assertNotIn("error", planned)
            self.assertEqual(planned["intake_kind"], "vic")
            self.assertEqual(planned["ticker"], self.ticker)
            self.assertEqual(planned["drive_rel"], f"VIC/{self.ticker}/{pdf.name}")

    def test_unknown_ticker_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "idea.pdf"
            pdf.write_bytes(b"%PDF-1.4\n")
            planned = self.plan(kind="VIC", ticker="NOTAREALTICKER", pdf_path=pdf, root=ROOT)
            self.assertEqual(planned["error"], "unknown_ticker")

    def test_non_pdf_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            html = Path(tmp) / "idea.html"
            html.write_text("<html></html>", encoding="utf-8")
            planned = self.plan(kind="VIC", ticker=self.ticker, pdf_path=html, root=ROOT)
            self.assertEqual(planned["error"], "not_pdf")


def sys_path_insert() -> None:
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))


class CloudEnvironmentTests(unittest.TestCase):
    def test_environment_json_start_sources_drive_snippet(self) -> None:
        payload = json.loads((ROOT / ".cursor" / "environment.json").read_text(encoding="utf-8"))
        start = payload["start"]
        self.assertIn("cloud_setup_drive_credentials.sh", start)
        self.assertIn("ssi-cloud-env.sh", start)
        script = (ROOT / "_system" / "scripts" / "cloud_setup_drive_credentials.sh").read_text(encoding="utf-8")
        self.assertIn("GOOGLE_APPLICATION_CREDENTIALS", script)
        self.assertIn("cloud_setup_research_vault.sh", payload["install"])


if __name__ == "__main__":
    raise SystemExit(unittest.main())

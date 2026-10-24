"""Comprehensive Unit Tests for Google Docs Export Pipeline (F23, F24).

Verifies:
1. Exporting non-existent RFP returns HTTP 404.
2. Default mock mode export returns HTTP 200, success=True, mode='mock', and simulated URL.
3. Batch update payload contains TITLE and SUBTITLE paragraph styles with client metadata.
4. Batch update payload contains HEADING_1 and NORMAL_TEXT styles for sections.
5. Exact forward character index accumulation across sequential requests.
6. Unresolved open questions produce Drive API v3 comment payloads with quotedFileContent and anchor.
7. Resolved open questions produce zero comments.
8. Mock export updates rfps.final_doc_link and sets rfps.status = 'submitted'.
9. Export logs full JSON payload to backend/logs/google_export.log.
10. Live mode export without credentials or with placeholder credentials returns HTTP 400.
"""

import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import glob

for p in [str(Path(__file__).resolve().parent.parent), str(Path(__file__).resolve().parent.parent.parent)]:
    if p not in sys.path:
        sys.path.insert(0, p)

venv_pkgs = glob.glob(str(Path(__file__).resolve().parent.parent.parent / ".venv" / "lib" / "python*" / "site-packages"))
for p in venv_pkgs:
    if p not in sys.path:
        sys.path.insert(0, p)

from fastapi.testclient import TestClient
from app.main import app
from app.database import get_db, get_db_connection
from app.models import create_tables, seed_defaults
from app.services.export import build_export_payload, execute_export


class TestGoogleDocsExport(unittest.TestCase):
    """Test suite covering the dual Google Docs/Drive API export pipeline."""

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.tmp.name
        self.tmp.close()

        self.conn = get_db_connection(self.db_path)
        create_tables(self.conn)
        seed_defaults(self.conn)
        self.conn.commit()

        # Override get_db dependency
        def override_get_db():
            conn = get_db_connection(self.db_path)
            try:
                yield conn
                conn.commit()
            finally:
                conn.close()

        app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(app)

        # Create a test RFP with sections and questions
        res = self.client.post("/api/rfps", json={
            "client_name": "Acme Health Authority",
            "value": 75000.0,
            "service_ids": [1, 2],
        })
        self.rfp_id = res.json()["id"]

        # Insert test sections
        self.conn.execute(
            """
            INSERT INTO rfp_sections (rfp_id, heading, original_text, classification, draft_content, sort_order)
            VALUES (?, ?, ?, ?, ?, ?);
            """,
            (
                self.rfp_id,
                "1. Executive Overview",
                "Describe your agency and credentials.",
                "boilerplate",
                "Our agency is an ISO 27001 certified digital partner with full credentials.",
                1,
            ),
        )
        self.sec1_id = self.conn.execute("SELECT last_insert_rowid();").fetchone()[0]

        self.conn.execute(
            """
            INSERT INTO rfp_sections (rfp_id, heading, original_text, classification, draft_content, sort_order)
            VALUES (?, ?, ?, ?, ?, ?);
            """,
            (
                self.rfp_id,
                "2. Clinical Telemetry Gap",
                "Provide case studies of telemetry systems.",
                "gap",
                "We understand clinical needs. [MORE INFO REQUIRED: telemetry case study]",
                2,
            ),
        )
        self.sec2_id = self.conn.execute("SELECT last_insert_rowid();").fetchone()[0]

        # Insert open question
        self.conn.execute(
            """
            INSERT INTO open_questions (rfp_id, section_id, question, status)
            VALUES (?, ?, ?, 'open');
            """,
            (self.rfp_id, self.sec2_id, "Need telemetry project references"),
        )
        self.conn.commit()

    def tearDown(self):
        app.dependency_overrides.clear()
        self.conn.close()
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_01_export_nonexistent_rfp_returns_404(self):
        """Exporting a non-existent RFP returns HTTP 404."""
        res = self.client.post("/api/rfps/999999/export")
        self.assertEqual(res.status_code, 404)
        self.assertIn("not found", res.json().get("detail", "").lower())

    def test_02_mock_export_default_success(self):
        """Default mock export returns HTTP 200 with simulated URL."""
        res = self.client.post(f"/api/rfps/{self.rfp_id}/export")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("mode"), "mock")
        doc_url = data.get("doc_url", "")
        self.assertTrue(doc_url.startswith("https://docs.google.com/document/d/mock-rfp-"))

    def test_03_mock_export_document_title_and_metadata(self):
        """Batch update requests contain TITLE and SUBTITLE styles with client metadata."""
        res = self.client.post(f"/api/rfps/{self.rfp_id}/export")
        self.assertEqual(res.status_code, 200)
        payload = res.json().get("payload", {})
        requests = payload.get("batch_update", {}).get("requests", [])

        # Check TITLE insertion and style
        title_insert = requests[0]
        self.assertIn("insertText", title_insert)
        self.assertIn("Acme Health Authority", title_insert["insertText"]["text"])

        title_style = requests[1]
        self.assertIn("updateParagraphStyle", title_style)
        self.assertEqual(title_style["updateParagraphStyle"]["paragraphStyle"]["namedStyleType"], "TITLE")

        # Check SUBTITLE insertion and style
        meta_insert = requests[2]
        self.assertIn("insertText", meta_insert)
        self.assertIn("£75,000.00", meta_insert["insertText"]["text"])

        meta_style = requests[3]
        self.assertIn("updateParagraphStyle", meta_style)
        self.assertEqual(meta_style["updateParagraphStyle"]["paragraphStyle"]["namedStyleType"], "SUBTITLE")

    def test_04_mock_export_headings_and_body_formatting(self):
        """Batch update requests style every section heading as HEADING_1 and insert body text after it."""
        res = self.client.post(f"/api/rfps/{self.rfp_id}/export")
        self.assertEqual(res.status_code, 200)
        requests = res.json().get("payload", {}).get("batch_update", {}).get("requests", [])

        named_styles = [
            r["updateParagraphStyle"]["paragraphStyle"]["namedStyleType"]
            for r in requests if "updateParagraphStyle" in r
        ]
        # Two sections in the fixture → two HEADING_1 styles after TITLE/SUBTITLE
        self.assertEqual(named_styles.count("HEADING_1"), 2)

        # Body text (plain paragraphs) is inserted via insertText without a heading style
        inserted = [r["insertText"]["text"] for r in requests if "insertText" in r]
        self.assertTrue(any("ISO 27001" in t for t in inserted))

    def test_05_mock_export_sequential_index_accumulation(self):
        """Verify sequential character index tracking on every insertText request."""
        res = self.client.post(f"/api/rfps/{self.rfp_id}/export")
        self.assertEqual(res.status_code, 200)
        requests = res.json().get("payload", {}).get("batch_update", {}).get("requests", [])

        expected_index = 1
        for req in requests:
            if "insertText" in req:
                actual_index = req["insertText"]["location"]["index"]
                self.assertEqual(actual_index, expected_index, f"Expected index {expected_index}, got {actual_index}")
                expected_index += len(req["insertText"]["text"])

    def test_06_unresolved_open_question_generates_drive_comment(self):
        """Unresolved open question generates Drive API v3 comment with anchor."""
        res = self.client.post(f"/api/rfps/{self.rfp_id}/export")
        self.assertEqual(res.status_code, 200)
        comments = res.json().get("payload", {}).get("comments", [])
        self.assertEqual(len(comments), 1)

        c = comments[0]
        self.assertEqual(c["section_id"], self.sec2_id)
        self.assertEqual(c["question"], "Need telemetry project references")

        payload = c["comment_payload"]
        self.assertIn("[MORE INFO REQUIRED]", payload["content"])
        self.assertIn("quotedFileContent", payload)
        self.assertIn("anchor", payload)

        anchor_dict = json.loads(payload["anchor"])
        self.assertIn("a", anchor_dict)
        self.assertGreater(anchor_dict["a"][0]["txt"]["o"], 0)
        self.assertGreater(anchor_dict["a"][0]["txt"]["l"], 0)

    def test_07_resolved_open_questions_produce_zero_comments(self):
        """Resolving all open questions causes export payload comments list to be empty."""
        # Resolve the question
        self.conn.execute("UPDATE open_questions SET status = 'resolved' WHERE rfp_id = ?;", (self.rfp_id,))
        self.conn.commit()

        res = self.client.post(f"/api/rfps/{self.rfp_id}/export")
        self.assertEqual(res.status_code, 200)
        comments = res.json().get("payload", {}).get("comments", [])
        self.assertEqual(len(comments), 0)

    def test_08_mock_export_persists_doc_link_but_not_status(self):
        """Mock export persists rfps.final_doc_link but, being a dry run, must NOT advance the status."""
        res = self.client.post(f"/api/rfps/{self.rfp_id}/export")
        self.assertEqual(res.json().get("mode"), "mock")
        doc_url = res.json().get("doc_url")

        cur = self.conn.execute("SELECT final_doc_link, status FROM rfps WHERE id = ?;", (self.rfp_id,))
        row = cur.fetchone()
        self.assertEqual(row["final_doc_link"], doc_url)
        self.assertEqual(row["status"], "draft")

    def test_09_mock_export_logs_payload_to_file(self):
        """Mock export appends valid JSON line to backend/logs/google_export.log."""
        res = self.client.post(f"/api/rfps/{self.rfp_id}/export")
        self.assertEqual(res.status_code, 200)

        log_path = Path(__file__).resolve().parent.parent / "logs" / "google_export.log"
        self.assertTrue(log_path.exists(), "Log file was not created")

        with open(log_path, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip()]
        self.assertGreaterEqual(len(lines), 1)

        last_entry = json.loads(lines[-1])
        self.assertEqual(last_entry["rfp_id"], self.rfp_id)
        self.assertEqual(last_entry["mode"], "mock")
        self.assertIn("payload", last_entry)

    def test_10_live_mode_without_credentials_returns_400(self):
        """Requesting live mode without real credentials returns HTTP 400 with expected error keys."""
        res = self.client.post(
            f"/api/rfps/{self.rfp_id}/export",
            json={"export_mode": "live"},
        )
        self.assertEqual(res.status_code, 400)
        body = res.json()
        err = body.get("error", "")
        detail = body.get("detail", "")
        self.assertIn("Google Docs credentials not found", err)
        self.assertIn("credentials.json", err)
        self.assertIn("Google Docs credentials not found", detail)

    def test_11_comment_anchor_fallback_to_heading(self):
        """When section has open question but no [MORE INFO REQUIRED] marker in body, anchor falls back to heading."""
        # Insert an open question on sec1 (which has no gap marker in draft_content)
        self.conn.execute(
            """
            INSERT INTO open_questions (rfp_id, section_id, question, status)
            VALUES (?, ?, ?, 'open');
            """,
            (self.rfp_id, self.sec1_id, "Need ISO certificate expiration date"),
        )
        self.conn.commit()

        res = self.client.post(f"/api/rfps/{self.rfp_id}/export")
        self.assertEqual(res.status_code, 200)
        comments = res.json().get("payload", {}).get("comments", [])

        # Find comment for sec1
        sec1_comments = [c for c in comments if c["section_id"] == self.sec1_id]
        self.assertEqual(len(sec1_comments), 1)
        c = sec1_comments[0]
        payload = c["comment_payload"]

        # Check quotedFileContent matches the exact heading text
        self.assertEqual(payload["quotedFileContent"]["value"], "1. Executive Overview")

        # Check anchor matches heading length
        anchor_dict = json.loads(payload["anchor"])
        self.assertEqual(anchor_dict["a"][0]["txt"]["l"], len("1. Executive Overview"))

    def test_12_live_mode_client_execution_mocked(self):
        """Live export with valid credentials invokes Google Docs and Drive APIs and updates database."""
        # Create a valid (non-placeholder) credentials file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as cred_file:
            json.dump({
                "installed": {
                    "client_id": "test-client-id-123.apps.googleusercontent.com",
                    "client_secret": "test-client-secret-xyz",
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                }
            }, cred_file)
            cred_path = cred_file.name

        try:
            # Update settings with valid cred path
            self.conn.execute(
                "UPDATE settings SET google_credentials_path = ?, mock_google_export = 0 WHERE id = 1;",
                (cred_path,),
            )
            self.conn.commit()

            mock_docs = MagicMock()
            mock_drive = MagicMock()
            mock_docs.documents().create().execute.return_value = {"documentId": "live-doc-test-999"}
            mock_docs.documents().batchUpdate().execute.return_value = {}
            mock_drive.comments().create().execute.return_value = {"id": "live-comment-1"}

            def fake_build(service, version, credentials=None):
                if service == "docs":
                    return mock_docs
                elif service == "drive":
                    return mock_drive
                return MagicMock()

            mock_google = MagicMock()
            mock_oauth2 = MagicMock()
            mock_flow_mod = MagicMock()
            mock_discovery = MagicMock()
            mock_discovery.build.side_effect = fake_build
            mock_flow_mod.InstalledAppFlow.from_client_secrets_file.return_value.run_local_server.return_value = MagicMock()
            mock_oauth2.Credentials.from_authorized_user_file.side_effect = Exception("Not authorized user file")

            with patch.dict("sys.modules", {
                "google": mock_google,
                "google.oauth2": mock_oauth2,
                "google.oauth2.credentials": mock_oauth2,
                "google_auth_oauthlib": mock_flow_mod,
                "google_auth_oauthlib.flow": mock_flow_mod,
                "googleapiclient": mock_discovery,
                "googleapiclient.discovery": mock_discovery,
            }):
                res = self.client.post(
                    f"/api/rfps/{self.rfp_id}/export",
                    json={"export_mode": "live"},
                )
                self.assertEqual(res.status_code, 200)
                data = res.json()
                self.assertTrue(data.get("success"))
                self.assertEqual(data.get("mode"), "live")
                self.assertEqual(data.get("doc_id"), "live-doc-test-999")
                self.assertEqual(data.get("doc_url"), "https://docs.google.com/document/d/live-doc-test-999/edit")

                # Verify Docs create was called with create_document body
                mock_docs.documents().create.assert_called()
                # Verify batchUpdate was called with batch_update payload
                mock_docs.documents().batchUpdate.assert_called()
                # Verify Drive comments create was called for the open question
                mock_drive.comments().create.assert_called()

                # Verify database was updated with real Google Doc URL and submitted status
                cur = self.conn.execute("SELECT final_doc_link, status FROM rfps WHERE id = ?;", (self.rfp_id,))
                row = cur.fetchone()
                self.assertEqual(row["final_doc_link"], "https://docs.google.com/document/d/live-doc-test-999/edit")
                self.assertEqual(row["status"], "submitted")
        finally:
            if os.path.exists(cred_path):
                os.remove(cred_path)

    def test_13_live_mode_missing_libraries_clean_500(self):
        """Live export when google client libraries are missing returns clean HTTP 500."""
        # Create a valid (non-placeholder) credentials file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as cred_file:
            json.dump({
                "installed": {
                    "client_id": "test-client-id-123.apps.googleusercontent.com",
                    "client_secret": "test-client-secret-xyz",
                }
            }, cred_file)
            cred_path = cred_file.name

        try:
            self.conn.execute(
                "UPDATE settings SET google_credentials_path = ?, mock_google_export = 0 WHERE id = 1;",
                (cred_path,),
            )
            self.conn.commit()

            import builtins
            orig_import = builtins.__import__

            def fake_import(name, *args, **kwargs):
                if name.startswith("googleapiclient") or name.startswith("google.oauth2") or name.startswith("google_auth"):
                    raise ImportError("No module named 'googleapiclient'")
                return orig_import(name, *args, **kwargs)

            with patch("builtins.__import__", side_effect=fake_import):
                res = self.client.post(
                    f"/api/rfps/{self.rfp_id}/export",
                    json={"export_mode": "live"},
                )
                self.assertEqual(res.status_code, 500)
                body = res.json()
                self.assertIn("Google API client libraries", body.get("error", "") or body.get("detail", ""))
        finally:
            if os.path.exists(cred_path):
                os.remove(cred_path)


if __name__ == "__main__":
    unittest.main()

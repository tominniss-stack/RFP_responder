"""
Tier 1: Google Docs Export Pipeline Tests (F23, F24)
Verifies mock export execution, Google Docs API payload serialization, and fake URL persistence.
"""

import unittest
from tests.harness import TestHarnessClient


class TestExport(unittest.TestCase):
    def setUp(self):
        self.client = TestHarnessClient()
        upload_res = self.client.post("/api/rfps/upload", json_data={"client_name": "Export Testing RFP"})
        self.rfp_id = upload_res.json()["rfp_id"]
        self.client.post(f"/api/rfps/{self.rfp_id}/classify")

    def test_01_mock_export_success(self):
        """Verify triggering export in default mock mode returns HTTP 200."""
        res = self.client.post(f"/api/rfps/{self.rfp_id}/export")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data.get("success"), "Export response indicated failure")

    def test_02_mock_export_returns_fake_url(self):
        """Verify mock export returns simulated Google Docs URL containing document ID."""
        res = self.client.post(f"/api/rfps/{self.rfp_id}/export")
        data = res.json()
        doc_url = data.get("doc_url", "")
        self.assertTrue(doc_url.startswith("https://docs.google.com/document/d/mock-rfp-"), f"Unexpected doc URL: {doc_url}")
        self.assertEqual(data.get("mode"), "mock")

    def test_03_mock_export_persists_url_in_rfp(self):
        """Verify fake URL is written to rfps.final_doc_link in database."""
        res = self.client.post(f"/api/rfps/{self.rfp_id}/export")
        doc_url = res.json().get("doc_url")

        rfp_detail = self.client.get(f"/api/rfps/{self.rfp_id}").json()
        self.assertEqual(rfp_detail.get("final_doc_link"), doc_url)

    def test_04_mock_export_batch_update_payload(self):
        """Verify generated payload contains Google Docs API batchUpdate structure with insertText requests."""
        res = self.client.post(f"/api/rfps/{self.rfp_id}/export")
        payload = res.json().get("payload", {})
        self.assertIn("create_document", payload)
        self.assertIn("batch_update", payload)
        requests = payload["batch_update"].get("requests", [])
        self.assertGreaterEqual(len(requests), 1)
        self.assertIn("insertText", requests[0])

    def test_05_mock_export_preserves_draft_status(self):
        """Verify mock export persists doc link but does NOT auto-advance status."""
        self.client.post(f"/api/rfps/{self.rfp_id}/export")
        rfp_detail = self.client.get(f"/api/rfps/{self.rfp_id}").json()
        self.assertIsNotNone(rfp_detail.get("final_doc_link"))
        # Mock export should NOT force status='submitted' — that is a user-explicit action
        self.assertEqual(rfp_detail.get("status"), "draft")


if __name__ == "__main__":
    unittest.main()

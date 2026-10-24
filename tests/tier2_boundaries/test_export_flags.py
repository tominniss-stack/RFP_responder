"""
Tier 2 Boundary Case: Mock vs. Live Google Export Flags & Missing Credentials (T2.06, E08, E09)
Verifies mock export behavior, logging, and graceful failure when live mode lacks credentials.
"""

import unittest
from tests.harness import TestHarnessClient


class TestExportFlags(unittest.TestCase):
    def setUp(self):
        self.client = TestHarnessClient()
        upload_res = self.client.post("/api/rfps/upload", json_data={"client_name": "Export Flags RFP"})
        self.rfp_id = upload_res.json()["rfp_id"]

    def test_01_default_mock_mode_execution(self):
        """State A: export_mode='mock' logs payload and returns fake URL."""
        res = self.client.post(f"/api/rfps/{self.rfp_id}/export", json_data={"export_mode": "mock"})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data.get("mode"), "mock")
        self.assertTrue(data.get("doc_url", "").startswith("https://docs.google.com/document/d/mock-rfp-"))
        self.assertIn("payload", data)

    def test_02_live_mode_without_credentials_fails_gracefully(self):
        """State B: export_mode='live' without credentials.json returns HTTP 400 with descriptive error."""
        # Ensure credentials path points to non-existent file
        self.client.put("/api/settings", json_data={"google_credentials_path": "non_existent_creds.json"})

        res = self.client.post(f"/api/rfps/{self.rfp_id}/export", json_data={"export_mode": "live"})
        self.assertEqual(res.status_code, 400, f"Expected 400 for missing credentials, got {res.status_code}")
        err_msg = res.json().get("error", "")
        self.assertIn("Google Docs credentials not found", err_msg)
        self.assertIn("credentials.json", err_msg)

        # Reset setting
        self.client.put("/api/settings", json_data={"google_credentials_path": "credentials.json"})


if __name__ == "__main__":
    unittest.main()

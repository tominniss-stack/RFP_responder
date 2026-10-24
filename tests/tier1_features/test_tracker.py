"""
Tier 1: RFP Tracker & Detail View Tests (F26, F27)
Verifies RFP list filtering, comprehensive detail views, and post-submission outcome/feedback editing.
"""

import unittest
from tests.harness import TestHarnessClient


class TestTracker(unittest.TestCase):
    def setUp(self):
        self.client = TestHarnessClient()
        # Create seed RFPs
        self.rfp_a = self.client.post("/api/rfps", json_data={
            "client_name": "Alpha Retail Ltd",
            "value": 60000.0,
            "status": "draft",
        }).json()["id"]

        self.rfp_b = self.client.post("/api/rfps", json_data={
            "client_name": "Beta Health Trust",
            "value": 90000.0,
            "status": "won",
        }).json()["id"]

    def test_01_list_all_rfps(self):
        """Verify listing past RFPs returns all records with status and values."""
        res = self.client.get("/api/rfps")
        self.assertEqual(res.status_code, 200)
        rfps = res.json()
        self.assertGreaterEqual(len(rfps), 2)
        clients = [r["client_name"] for r in rfps]
        self.assertIn("Alpha Retail Ltd", clients)
        self.assertIn("Beta Health Trust", clients)

    def test_02_filter_rfps_by_status(self):
        """Verify filtering RFPs by status returns only matching records."""
        res = self.client.get("/api/rfps", params={"status": "won"})
        self.assertEqual(res.status_code, 200)
        won_rfps = res.json()
        self.assertTrue(all(r["status"] == "won" for r in won_rfps))
        self.assertTrue(any(r["id"] == self.rfp_b for r in won_rfps))

    def test_03_filter_rfps_by_client_name(self):
        """Verify filtering RFPs by client name substring."""
        res = self.client.get("/api/rfps", params={"client_name": "Beta"})
        self.assertEqual(res.status_code, 200)
        beta_rfps = res.json()
        self.assertEqual(len(beta_rfps), 1)
        self.assertEqual(beta_rfps[0]["client_name"], "Beta Health Trust")

    def test_04_get_rfp_detail(self):
        """Verify fetching single RFP detail returns full hierarchy (sections, notes, open_questions)."""
        res = self.client.get(f"/api/rfps/{self.rfp_a}")
        self.assertEqual(res.status_code, 200)
        detail = res.json()
        self.assertIn("sections", detail)
        self.assertIn("notes", detail)
        self.assertIn("open_questions", detail)
        self.assertEqual(detail["client_name"], "Alpha Retail Ltd")

    def test_05_edit_outcome_and_feedback(self):
        """Verify updating RFP outcome and saving qualitative post-submission feedback."""
        feedback_text = "Client selected Another Marketing Agency due to outstanding technical architecture and proven ISO 27001 security."
        update_res = self.client.put(
            f"/api/rfps/{self.rfp_a}",
            json_data={"status": "won", "outcome_feedback": feedback_text},
        )
        self.assertEqual(update_res.status_code, 200)

        # Confirm persisted
        detail = self.client.get(f"/api/rfps/{self.rfp_a}").json()
        self.assertEqual(detail.get("status"), "won")
        self.assertEqual(detail.get("outcome_feedback"), feedback_text)


if __name__ == "__main__":
    unittest.main()

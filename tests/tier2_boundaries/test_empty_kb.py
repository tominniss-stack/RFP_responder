"""
Tier 2 Boundary Case: Empty Knowledge Base Behavior (T2.02, E02)
Verifies system behavior on day one launch with 0 KB documents.
"""

import unittest
from tests.harness import TestHarnessClient


class TestEmptyKB(unittest.TestCase):
    def setUp(self):
        self.client = TestHarnessClient()
        # Delete all KB documents to simulate day one state
        all_docs = self.client.get("/api/kb").json()
        for doc in all_docs:
            self.client.delete(f"/api/kb/{doc['id']}")

    def test_01_empty_kb_listing(self):
        """Verify KB list returns empty list without error."""
        res = self.client.get("/api/kb")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), [])

    def test_02_empty_kb_boilerplate_draft_fallback(self):
        """Verify draft generation for boilerplate section falls back to [MORE INFO REQUIRED] without crashing."""
        rfp_res = self.client.post("/api/rfps/upload", json_data={"client_name": "Day One Empty KB RFP"})
        rfp_id = rfp_res.json()["rfp_id"]
        self.client.post(f"/api/rfps/{rfp_id}/classify")

        detail = self.client.get(f"/api/rfps/{rfp_id}").json()
        bp_sec = next(s for s in detail["sections"] if s["classification"] == "boilerplate")

        # Generate draft
        gen_res = self.client.post(f"/api/rfps/{rfp_id}/sections/{bp_sec['id']}/generate")
        self.assertEqual(gen_res.status_code, 200, f"Expected 200 fallback, got {gen_res.status_code}")
        draft = gen_res.json().get("draft_content", "")
        self.assertIn("[MORE INFO REQUIRED:", draft)
        self.assertIn("boilerplate not found in knowledge base", draft)

    def test_03_empty_kb_auto_creates_open_question(self):
        """Verify fallback marker from empty KB creates open question in tracker."""
        rfp_res = self.client.post("/api/rfps/upload", json_data={"client_name": "Open Question Empty KB RFP"})
        rfp_id = rfp_res.json()["rfp_id"]
        self.client.post(f"/api/rfps/{rfp_id}/classify")
        detail = self.client.get(f"/api/rfps/{rfp_id}").json()
        bp_sec = next(s for s in detail["sections"] if s["classification"] == "boilerplate")

        self.client.post(f"/api/rfps/{rfp_id}/sections/{bp_sec['id']}/generate")

        q_res = self.client.get(f"/api/rfps/{rfp_id}/open-questions")
        questions = q_res.json()
        self.assertTrue(len(questions) > 0, "No open questions registered for missing boilerplate")
        self.assertEqual(questions[0]["status"], "open")


if __name__ == "__main__":
    unittest.main()

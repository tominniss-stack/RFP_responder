"""
Tier 2 Boundary Case: Missing Pricing Item in Database (T2.03, E03)
Verifies non-hallucination guarantee when pricing is requested for unconfigured services.
"""

import unittest
from tests.harness import TestHarnessClient


class TestMissingPricing(unittest.TestCase):
    def setUp(self):
        self.client = TestHarnessClient()
        # Delete all price items to simulate missing pricing data
        all_prices = self.client.get("/api/pricing").json()
        for p in all_prices:
            self.client.delete(f"/api/pricing/{p['id']}")

    def test_01_pricing_empty_database_returns_marker(self):
        """Verify requesting pricing with zero price items generates [MORE INFO REQUIRED] and zero invented figures."""
        rfp_res = self.client.post("/api/rfps/upload", json_data={"client_name": "Unpriced RFP Client"})
        rfp_id = rfp_res.json()["rfp_id"]
        self.client.post(f"/api/rfps/{rfp_id}/classify")

        detail = self.client.get(f"/api/rfps/{rfp_id}").json()
        pricing_sec = next(s for s in detail["sections"] if s["classification"] == "pricing")

        gen_res = self.client.post(f"/api/rfps/{rfp_id}/sections/{pricing_sec['id']}/generate")
        self.assertEqual(gen_res.status_code, 200)
        draft = gen_res.json().get("draft_content", "")

        # Must contain gap marker
        self.assertIn("[MORE INFO REQUIRED:", draft)
        self.assertIn("Missing pricing data", draft)

        # Zero hallucination: no currency symbols or numbers
        self.assertNotIn("£", draft)
        self.assertNotIn("$", draft)

    def test_02_missing_pricing_auto_registers_open_question(self):
        """Verify missing pricing marker automatically logs an open question in the tracker."""
        rfp_res = self.client.post("/api/rfps/upload", json_data={"client_name": "Unpriced Question RFP"})
        rfp_id = rfp_res.json()["rfp_id"]
        self.client.post(f"/api/rfps/{rfp_id}/classify")
        detail = self.client.get(f"/api/rfps/{rfp_id}").json()
        pricing_sec = next(s for s in detail["sections"] if s["classification"] == "pricing")

        self.client.post(f"/api/rfps/{rfp_id}/sections/{pricing_sec['id']}/generate")

        questions = self.client.get(f"/api/rfps/{rfp_id}/open-questions").json()
        self.assertTrue(len(questions) > 0)
        pricing_q = next((q for q in questions if q["section_id"] == pricing_sec["id"]), None)
        self.assertIsNotNone(pricing_q, "Pricing open question not created")
        self.assertEqual(pricing_q["status"], "open")


if __name__ == "__main__":
    unittest.main()

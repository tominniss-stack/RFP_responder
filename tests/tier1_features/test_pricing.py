"""
Tier 1: Structured Pricing Management & Exact Lookup Tests (F14, F15)
Verifies price items CRUD, unit constraints, and zero-hallucination exact numerical reproduction.
"""

import unittest
from tests.harness import TestHarnessClient


class TestPricing(unittest.TestCase):
    def setUp(self):
        self.client = TestHarnessClient()

    def test_01_create_price_item(self):
        """Verify adding a price item with valid units ('day rate', 'fixed', 'monthly retainer')."""
        payload = {
            "service_id": 1,
            "description": "Lead DevOps Architect",
            "unit": "day rate",
            "amount": 950.0,
        }
        res = self.client.post("/api/pricing", json_data=payload)
        self.assertIn(res.status_code, [200, 201])
        data = res.json()
        self.assertIsNotNone(data.get("id"))
        self.assertEqual(data.get("description"), payload["description"])
        self.assertEqual(data.get("amount"), 950.0)

    def test_02_list_and_filter_price_items(self):
        """Verify listing price items and filtering by service_id."""
        res = self.client.get("/api/pricing")
        self.assertEqual(res.status_code, 200)
        items = res.json()
        self.assertGreaterEqual(len(items), 6, "Seed pricing items should be present")

        # Filter by service_id=1 (Web Dev)
        filtered = self.client.get("/api/pricing", params={"service_id": 1})
        self.assertEqual(filtered.status_code, 200)
        for item in filtered.json():
            self.assertEqual(item["service_id"], 1)

    def test_03_update_price_item(self):
        """Verify updating price item amount and description."""
        # Create item
        item = self.client.post("/api/pricing", json_data={
            "service_id": 3,
            "description": "Junior UX Researcher",
            "unit": "day rate",
            "amount": 450.0,
        }).json()
        pid = item["id"]

        # Update
        up_res = self.client.put(f"/api/pricing/{pid}", json_data={"amount": 500.0, "description": "Mid-Weight UX Researcher"})
        self.assertEqual(up_res.status_code, 200)
        updated = up_res.json()
        self.assertEqual(updated.get("amount"), 500.0)
        self.assertEqual(updated.get("description"), "Mid-Weight UX Researcher")

    def test_04_delete_price_item(self):
        """Verify deleting a price item removes it from the table."""
        item = self.client.post("/api/pricing", json_data={
            "service_id": 4,
            "description": "Ad-Hoc SEO Consultation",
            "unit": "day rate",
            "amount": 600.0,
        }).json()
        pid = item["id"]

        del_res = self.client.delete(f"/api/pricing/{pid}")
        self.assertEqual(del_res.status_code, 200)

        # Check not in list
        list_res = self.client.get("/api/pricing").json()
        ids = [i["id"] for i in list_res]
        self.assertNotIn(pid, ids)

    def test_05_exact_pricing_reproduction(self):
        """Verify pricing draft generation contains exact numerical rates without approximation."""
        rfp_res = self.client.post("/api/rfps/upload", json_data={"client_name": "Pricing Fidelity RFP"})
        rfp_id = rfp_res.json()["rfp_id"]
        self.client.post(f"/api/rfps/{rfp_id}/classify")

        rfp_detail = self.client.get(f"/api/rfps/{rfp_id}").json()
        pricing_sec = next(s for s in rfp_detail["sections"] if s["classification"] == "pricing")

        gen_res = self.client.post(f"/api/rfps/{rfp_id}/sections/{pricing_sec['id']}/generate")
        self.assertEqual(gen_res.status_code, 200)
        draft = gen_res.json().get("draft_content", "")

        # Seed price items: 850.00 and 16500.00
        self.assertTrue(
            "850" in draft or "850.00" in draft,
            f"Draft did not contain exact £850 figure: {draft}",
        )
        self.assertTrue(
            "16,500" in draft or "16500" in draft,
            f"Draft did not contain exact £16,500 figure: {draft}",
        )
        # Verify no vague approximations
        self.assertNotIn("around 800", draft.lower())
        self.assertNotIn("approx", draft.lower())


if __name__ == "__main__":
    unittest.main()

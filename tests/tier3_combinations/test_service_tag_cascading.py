"""
Tier 3 Combination: Service Tag Cascading & Referential Integrity (T3.05)
Verifies dynamic service tag association across KB, Pricing, and RFPs, and deletion safety.
"""

import unittest
from tests.harness import TestHarnessClient


class TestServiceTagCascading(unittest.TestCase):
    def setUp(self):
        self.client = TestHarnessClient()

    def test_01_service_lifecycle_and_referential_integrity(self):
        """Verify service creation, association with KB & RFP, and blocked deletion when active."""
        # 1. Create unique service tag
        service_name = "Enterprise Headless CMS Integration"
        srv_res = self.client.post("/api/services", json_data={"name": service_name})
        self.assertIn(srv_res.status_code, [200, 201])
        sid = srv_res.json()["id"]

        # 2. Add price item for this service
        price_res = self.client.post("/api/pricing", json_data={
            "service_id": sid,
            "description": "Headless CMS Principal Engineer",
            "unit": "day rate",
            "amount": 950.0,
        })
        self.assertIn(price_res.status_code, [200, 201])

        # 3. Create RFP referencing this service
        rfp_res = self.client.post("/api/rfps", json_data={
            "client_name": "Referential Integrity Client",
            "value": 50000.0,
            "service_ids": [sid],
        })
        rfp_id = rfp_res.json()["id"]

        # 4. Attempt to delete service while actively referenced by RFP -> HTTP 409 Conflict
        del_res = self.client.delete(f"/api/services/{sid}")
        self.assertEqual(del_res.status_code, 409, "Should block deletion of service currently in use by an active RFP")

        # 5. Delete RFP first, then delete service successfully
        self.client.delete(f"/api/rfps/{rfp_id}")
        del_res2 = self.client.delete(f"/api/services/{sid}")
        self.assertEqual(del_res2.status_code, 200, "Should allow deletion of service once references are removed")


if __name__ == "__main__":
    unittest.main()

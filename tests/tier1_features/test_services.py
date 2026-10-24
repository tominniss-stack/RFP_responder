"""
Tier 1: Services Management Tests (F04)
Verifies dynamic services tag CRUD, unique constraints, and RFP associations.
"""

import unittest
from tests.harness import TestHarnessClient


class TestServices(unittest.TestCase):
    def setUp(self):
        self.client = TestHarnessClient()

    def test_01_list_services(self):
        """Verify listing all services returns pre-loaded seed services."""
        res = self.client.get("/api/services")
        self.assertEqual(res.status_code, 200)
        services = res.json()
        self.assertGreaterEqual(len(services), 5)
        names = [s["name"] for s in services]
        self.assertIn("Web Development — Headless CMS", names)
        self.assertIn("UX/UI Design", names)

    def test_02_create_service(self):
        """Verify creating a new service tag."""
        new_name = "Cloud Infrastructure & DevOps Support"
        res = self.client.post("/api/services", json_data={"name": new_name})
        self.assertIn(res.status_code, [200, 201])
        data = res.json()
        self.assertIsNotNone(data.get("id"))
        self.assertEqual(data.get("name"), new_name)

        # Confirm appears in services list
        all_s = self.client.get("/api/services").json()
        self.assertTrue(any(s["name"] == new_name for s in all_s))

    def test_03_unique_service_constraint(self):
        """Verify duplicate service name returns HTTP 409 Conflict."""
        # Attempt to insert existing name
        res = self.client.post("/api/services", json_data={"name": "Web Development — Headless CMS"})
        self.assertEqual(res.status_code, 409, f"Expected 409 for duplicate service, got {res.status_code}")

    def test_04_delete_service(self):
        """Verify deleting an unreferenced service succeeds."""
        # Create temp service
        temp = self.client.post("/api/services", json_data={"name": "Temporary Legacy Service"}).json()
        sid = temp["id"]

        del_res = self.client.delete(f"/api/services/{sid}")
        self.assertEqual(del_res.status_code, 200)

        # Verify not in list
        all_s = self.client.get("/api/services").json()
        self.assertFalse(any(s["id"] == sid for s in all_s))

    def test_05_link_service_to_rfp(self):
        """Verify tagging an RFP with service IDs persists association."""
        new_s = self.client.post("/api/services", json_data={"name": "Statamic Headless API"}).json()
        sid = new_s["id"]

        rfp_res = self.client.post("/api/rfps", json_data={
            "client_name": "API Service RFP",
            "service_ids": [sid],
        })
        rfp_id = rfp_res.json()["id"]

        detail = self.client.get(f"/api/rfps/{rfp_id}").json()
        self.assertIn(sid, detail.get("services", []))


if __name__ == "__main__":
    unittest.main()

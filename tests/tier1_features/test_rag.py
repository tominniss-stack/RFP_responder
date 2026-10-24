"""
Tier 1: Knowledge Base & RAG Retrieval Tests (F11, F12, F13, F16)
Verifies KB document management, boilerplate auto-retrieval, and won-proposal retrieval bias.
"""

import unittest
from tests.harness import TestHarnessClient


class TestRAG(unittest.TestCase):
    def setUp(self):
        self.client = TestHarnessClient()

    def test_01_create_kb_document(self):
        """Verify user can ingest a new KB document with tags."""
        payload = {
            "title": "FinTech Mobile Banking Case Study",
            "content": "Delivered native iOS and Android banking app with 99.999% availability and biometrics.",
            "type": "case_study",
            "outcome": "won",
            "service_ids": [5],
        }
        res = self.client.post("/api/kb", json_data=payload)
        self.assertIn(res.status_code, [200, 201])
        data = res.json()
        self.assertIsNotNone(data.get("id"))
        self.assertEqual(data.get("title"), payload["title"])
        self.assertEqual(data.get("type"), "case_study")

    def test_02_list_kb_documents(self):
        """Verify listing KB documents with outcome and type filters."""
        res = self.client.get("/api/kb")
        self.assertEqual(res.status_code, 200)
        docs = res.json()
        self.assertGreaterEqual(len(docs), 5, "Seed documents should be present")

        # Filter by type=boilerplate
        bp_res = self.client.get("/api/kb", params={"type": "boilerplate"})
        self.assertEqual(bp_res.status_code, 200)
        bp_docs = bp_res.json()
        self.assertTrue(all(d["type"] == "boilerplate" for d in bp_docs))

    def test_03_delete_kb_document(self):
        """Verify deleting a KB document removes it from storage."""
        # Create temp doc
        create_res = self.client.post("/api/kb", json_data={
            "title": "Temporary Doc to Delete",
            "content": "This will be deleted.",
            "type": "testimonial",
        })
        kbid = create_res.json()["id"]

        del_res = self.client.delete(f"/api/kb/{kbid}")
        self.assertEqual(del_res.status_code, 200)

        # Confirm not in list
        list_res = self.client.get("/api/kb")
        ids = [d["id"] for d in list_res.json()]
        self.assertNotIn(kbid, ids)

    def test_04_boilerplate_auto_retrieval(self):
        """Verify boilerplate-classified section auto-retrieves company credentials and ISO 27001."""
        # Create an RFP and section
        rfp_res = self.client.post("/api/rfps/upload", json_data={"client_name": "Boilerplate Retrieval Test"})
        rfp_id = rfp_res.json()["rfp_id"]
        self.client.post(f"/api/rfps/{rfp_id}/classify")

        rfp_detail = self.client.get(f"/api/rfps/{rfp_id}").json()
        bp_sec = next(s for s in rfp_detail["sections"] if s["classification"] == "boilerplate")

        # Generate draft
        gen_res = self.client.post(f"/api/rfps/{rfp_id}/sections/{bp_sec['id']}/generate")
        self.assertEqual(gen_res.status_code, 200)
        draft = gen_res.json().get("draft_content", "")
        self.assertIn("ISO 27001", draft, "Draft failed to auto-retrieve ISO 27001 certification")
        self.assertIn("Cyber Essentials", draft, "Draft failed to auto-retrieve Cyber Essentials")

    def test_05_outcome_similarity_ranking(self):
        """Verify semantic query ranks 'won' proposal higher than 'lost' proposal."""
        # Query matching content in both won (Statamic retail) and lost (generic portal)
        res = self.client.get("/api/kb", params={"query": "Statamic portal platform proposal"})
        self.assertEqual(res.status_code, 200)
        results = res.json()

        won_match = next((d for d in results if d.get("outcome") == "won"), None)
        lost_match = next((d for d in results if d.get("outcome") == "lost"), None)

        self.assertIsNotNone(won_match, "Won proposal not found in results")
        self.assertIsNotNone(lost_match, "Lost proposal not found in results")
        self.assertGreater(
            won_match.get("similarity_score", 0),
            lost_match.get("similarity_score", 0),
            "Won proposal score must be higher than lost proposal score due to outcome weighting",
        )


if __name__ == "__main__":
    unittest.main()

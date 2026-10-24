"""
Tier 3 Combination: Tripartite Synthesis of Notes + RAG + Pricing (T3.01)
Verifies multi-source synthesis of notes, retrieved RAG content, and exact pricing in a single draft.
"""

import unittest
from tests.harness import TestHarnessClient


class TestTripartiteSynthesis(unittest.TestCase):
    def setUp(self):
        self.client = TestHarnessClient()
        upload_res = self.client.post("/api/rfps/upload", json_data={"client_name": "Tripartite Synthesis RFP"})
        self.rfp_id = upload_res.json()["rfp_id"]
        self.client.post(f"/api/rfps/{self.rfp_id}/classify")
        detail = self.client.get(f"/api/rfps/{self.rfp_id}").json()
        self.pricing_sec = next(s for s in detail["sections"] if s["classification"] == "pricing")

    def test_01_tripartite_synthesis_narrative_and_provenance(self):
        """Verify draft synthesizes RAG methodology, exact £850 rate, and 10% discount from AM notes."""
        discount_instruction = "Offer a 10% commercial discount on the initial discovery sprint."
        self.client.post(f"/api/rfps/{self.rfp_id}/notes", json_data={
            "raw_content": discount_instruction,
            "section_id": self.pricing_sec["id"],
        })

        # Generate draft
        gen_res = self.client.post(f"/api/rfps/{self.rfp_id}/sections/{self.pricing_sec['id']}/generate")
        self.assertEqual(gen_res.status_code, 200)
        data = gen_res.json()
        draft = data.get("draft_content", "")

        # 1. Exact pricing fidelity
        self.assertIn("850", draft, "Draft failed to include exact £850 day rate")

        # 2. Account Manager notes inclusion
        self.assertIn(discount_instruction, draft, "Draft failed to incorporate AM discount note")

        # 3. Provenance tagging
        provenance = data.get("provenance", [])
        sources = [p["source"] for p in provenance]
        self.assertIn("pricing", sources, "Provenance missing 'pricing' source")
        self.assertIn("notes", sources, "Provenance missing 'notes' source")


if __name__ == "__main__":
    unittest.main()

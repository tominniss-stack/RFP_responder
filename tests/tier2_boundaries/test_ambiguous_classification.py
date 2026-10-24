"""
Tier 2 Boundary Case: Ambiguous Classification Section Handling (T2.01, E01)
Verifies handling of deliberately ambiguous sections blending strategic decisions and experience gaps.
"""

import unittest
from tests.harness import TestHarnessClient


class TestAmbiguousClassification(unittest.TestCase):
    def setUp(self):
        self.client = TestHarnessClient()
        upload_res = self.client.post("/api/rfps/upload", json_data={"client_name": "Ambiguity Test RFP"})
        self.rfp_id = upload_res.json()["rfp_id"]
        self.client.post(f"/api/rfps/{self.rfp_id}/classify")
        detail = self.client.get(f"/api/rfps/{self.rfp_id}").json()
        # Section 3.0: Accessibility Compliance & Public Sector Standards
        self.ambiguous_sec = next(s for s in detail["sections"] if "3.0" in s["heading"])

    def test_01_ambiguous_section_classification_category(self):
        """Verify ambiguous section classifies into strategic_decision or gap."""
        cat = self.ambiguous_sec.get("classification")
        self.assertIn(cat, ["strategic_decision", "gap"], f"Unexpected classification for ambiguous section: {cat}")

    def test_02_ambiguous_section_confidence_rating(self):
        """Verify ambiguous section receives medium or low confidence."""
        conf = self.ambiguous_sec.get("confidence")
        self.assertIn(conf, ["medium", "low"], f"Ambiguous section should have medium/low confidence, got: {conf}")

    def test_03_ambiguous_section_clarifying_question(self):
        """Verify ambiguous section generates a clarifying question for internal team."""
        cq = self.ambiguous_sec.get("clarifying_question")
        self.assertTrue(bool(cq), "Ambiguous section should produce a clarifying question")
        self.assertIn("wcag", cq.lower(), "Clarifying question should reference WCAG accessibility")

    def test_04_ambiguous_section_manual_override_and_drafting(self):
        """Verify manual override to the alternate category persists and allows downstream drafting."""
        sec_id = self.ambiguous_sec["id"]
        # Override to gap
        override_res = self.client.patch(
            f"/api/rfps/{self.rfp_id}/sections/{sec_id}",
            json_data={"classification": "gap"},
        )
        self.assertEqual(override_res.status_code, 200)
        self.assertEqual(override_res.json()["classification"], "gap")

        # Trigger draft generation
        gen_res = self.client.post(f"/api/rfps/{self.rfp_id}/sections/{sec_id}/generate")
        self.assertEqual(gen_res.status_code, 200)
        draft = gen_res.json().get("draft_content", "")
        self.assertTrue(len(draft) > 0, "Draft content should be generated following override")


if __name__ == "__main__":
    unittest.main()

"""
Tier 1: LLM Section Classification & Override Tests (F08, F09, F10)
Verifies 5-category classification, confidence scoring, clarifying questions, and manual overrides.
"""

import unittest
from tests.harness import TestHarnessClient


class TestClassification(unittest.TestCase):
    def setUp(self):
        self.client = TestHarnessClient()
        # Create an RFP with sample sections
        res = self.client.post("/api/rfps/upload", json_data={"client_name": "Classification Test Client"})
        self.rfp_id = res.json()["rfp_id"]

    def test_01_classify_boilerplate_section(self):
        """Verify executive summary / company credentials classifies as boilerplate."""
        self.client.post(f"/api/rfps/{self.rfp_id}/classify")
        detail = self.client.get(f"/api/rfps/{self.rfp_id}").json()
        sections = detail.get("sections", [])
        sec1 = next(s for s in sections if "1.0" in s["heading"])
        self.assertEqual(sec1.get("classification"), "boilerplate")
        self.assertEqual(sec1.get("confidence"), "high")

    def test_02_classify_pricing_section(self):
        """Verify commercial rate schedule classifies as pricing."""
        self.client.post(f"/api/rfps/{self.rfp_id}/classify")
        detail = self.client.get(f"/api/rfps/{self.rfp_id}").json()
        sections = detail.get("sections", [])
        pricing_sec = next(s for s in sections if "5.0" in s["heading"])
        self.assertEqual(pricing_sec.get("classification"), "pricing")
        self.assertEqual(pricing_sec.get("confidence"), "high")

    def test_03_classify_strategic_with_question(self):
        """Verify technical architecture classifies as strategic_decision and generates clarifying question."""
        self.client.post(f"/api/rfps/{self.rfp_id}/classify")
        detail = self.client.get(f"/api/rfps/{self.rfp_id}").json()
        sections = detail.get("sections", [])
        strat_sec = next(s for s in sections if "2.0" in s["heading"])
        self.assertEqual(strat_sec.get("classification"), "strategic_decision")
        self.assertTrue(bool(strat_sec.get("clarifying_question")), "Strategic section missing clarifying question")

    def test_04_classify_gap_section(self):
        """Verify niche requirement classifies as gap."""
        self.client.post(f"/api/rfps/{self.rfp_id}/classify")
        detail = self.client.get(f"/api/rfps/{self.rfp_id}").json()
        sections = detail.get("sections", [])
        gap_sec = next(s for s in sections if "6.0" in s["heading"])
        self.assertEqual(gap_sec.get("classification"), "gap")

    def test_05_manual_classification_override(self):
        """Verify user can manually override classification from dropdown and persist it."""
        self.client.post(f"/api/rfps/{self.rfp_id}/classify")
        detail = self.client.get(f"/api/rfps/{self.rfp_id}").json()
        target_sec = detail.get("sections", [])[0]
        sec_id = target_sec["id"]

        # Override to 'strategic_decision'
        override_res = self.client.patch(
            f"/api/rfps/{self.rfp_id}/sections/{sec_id}",
            json_data={"classification": "strategic_decision"},
        )
        self.assertEqual(override_res.status_code, 200)
        self.assertEqual(override_res.json().get("classification"), "strategic_decision")

        # Verify persisted on re-fetch
        recheck = self.client.get(f"/api/rfps/{self.rfp_id}").json()
        updated_sec = next(s for s in recheck["sections"] if s["id"] == sec_id)
        self.assertEqual(updated_sec.get("classification"), "strategic_decision")


if __name__ == "__main__":
    unittest.main()

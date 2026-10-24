"""
Tier 1: Account Manager Notes & Content Provenance Tests (F17, F18, F21)
Verifies whole-RFP notes, section-specific notes, narrative influence, and provenance metadata.
"""

import unittest
from tests.harness import TestHarnessClient


class TestNotes(unittest.TestCase):
    def setUp(self):
        self.client = TestHarnessClient()
        upload_res = self.client.post("/api/rfps/upload", json_data={"client_name": "Notes Testing RFP"})
        self.rfp_id = upload_res.json()["rfp_id"]
        self.client.post(f"/api/rfps/{self.rfp_id}/classify")
        detail = self.client.get(f"/api/rfps/{self.rfp_id}").json()
        self.section_id = detail["sections"][1]["id"]  # Technical section

    def test_01_create_whole_rfp_note(self):
        """Verify creating a whole-RFP brain dump note (section_id=None)."""
        payload = {
            "raw_content": "Client values rapid speed to market and high accessibility over complex animations.",
            "section_id": None,
        }
        res = self.client.post(f"/api/rfps/{self.rfp_id}/notes", json_data=payload)
        self.assertIn(res.status_code, [200, 201])
        data = res.json()
        self.assertIsNotNone(data.get("id"))
        self.assertIsNone(data.get("section_id"))
        self.assertIn("speed to market", data.get("raw_content"))

    def test_02_create_section_specific_note(self):
        """Verify creating a section-specific note."""
        payload = {
            "raw_content": "Strongly emphasize Statamic 4 headless with Astro SSG for maximum page speed.",
            "section_id": self.section_id,
        }
        res = self.client.post(f"/api/rfps/{self.rfp_id}/notes", json_data=payload)
        self.assertIn(res.status_code, [200, 201])
        data = res.json()
        self.assertEqual(data.get("section_id"), self.section_id)
        self.assertIn("Statamic 4 headless", data.get("raw_content"))

    def test_03_list_notes_for_rfp(self):
        """Verify listing all notes for an RFP returns both whole-RFP and section notes."""
        self.client.post(f"/api/rfps/{self.rfp_id}/notes", json_data={"raw_content": "Whole note 1"})
        self.client.post(f"/api/rfps/{self.rfp_id}/notes", json_data={"raw_content": "Section note 1", "section_id": self.section_id})

        res = self.client.get(f"/api/rfps/{self.rfp_id}/notes")
        self.assertEqual(res.status_code, 200)
        notes = res.json()
        self.assertGreaterEqual(len(notes), 2)
        has_whole = any(n["section_id"] is None for n in notes)
        has_section = any(n["section_id"] == self.section_id for n in notes)
        self.assertTrue(has_whole, "Missing whole-RFP note in list")
        self.assertTrue(has_section, "Missing section note in list")

    def test_04_notes_influence_draft(self):
        """Verify section-specific note is incorporated into generated draft."""
        specific_text = "Commit to Astro 4.0 integration and sub-50ms TTFB."
        self.client.post(f"/api/rfps/{self.rfp_id}/notes", json_data={
            "raw_content": specific_text,
            "section_id": self.section_id,
        })

        gen_res = self.client.post(f"/api/rfps/{self.rfp_id}/sections/{self.section_id}/generate")
        self.assertEqual(gen_res.status_code, 200)
        draft = gen_res.json().get("draft_content", "")
        self.assertIn(specific_text, draft, "Draft failed to incorporate section note guidance")

    def test_05_provenance_tagging(self):
        """Verify draft generation returns provenance metadata tagging notes vs RAG sources."""
        self.client.post(f"/api/rfps/{self.rfp_id}/notes", json_data={
            "raw_content": "Special note for provenance check.",
            "section_id": self.section_id,
        })
        gen_res = self.client.post(f"/api/rfps/{self.rfp_id}/sections/{self.section_id}/generate")
        self.assertEqual(gen_res.status_code, 200)
        data = gen_res.json()
        provenance = data.get("provenance", [])
        self.assertTrue(len(provenance) > 0, "Provenance metadata list should not be empty")
        sources = [p.get("source") for p in provenance]
        self.assertIn("notes", sources, "Provenance missing 'notes' tag")


if __name__ == "__main__":
    unittest.main()

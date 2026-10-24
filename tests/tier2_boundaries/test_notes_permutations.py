"""
Tier 2 Boundary Case: Notes Permutations Matrix & Conflict Precedence (T2.05, E05, E06, E07)
Verifies the 4 permutations of empty vs hybrid notes and section note precedence.
"""

import unittest
from tests.harness import TestHarnessClient


class TestNotesPermutations(unittest.TestCase):
    def setUp(self):
        self.client = TestHarnessClient()
        upload_res = self.client.post("/api/rfps/upload", json_data={"client_name": "Notes Permutation RFP"})
        self.rfp_id = upload_res.json()["rfp_id"]
        self.client.post(f"/api/rfps/{self.rfp_id}/classify")
        detail = self.client.get(f"/api/rfps/{self.rfp_id}").json()
        self.section_id = detail["sections"][1]["id"]  # Technical approach section

    def test_01_permutation_empty_notes_baseline(self):
        """Permutation 1: 0 notes -> succeeds using RAG only; zero notes in provenance."""
        gen_res = self.client.post(f"/api/rfps/{self.rfp_id}/sections/{self.section_id}/generate")
        self.assertEqual(gen_res.status_code, 200)
        data = gen_res.json()
        sources = [p["source"] for p in data.get("provenance", [])]
        self.assertNotIn("notes", sources)

    def test_02_permutation_whole_rfp_note_only(self):
        """Permutation 2: Whole-RFP note only -> incorporated with notes provenance."""
        whole_note = "Whole RFP context: Client demands carbon-neutral cloud hosting."
        self.client.post(f"/api/rfps/{self.rfp_id}/notes", json_data={"raw_content": whole_note})

        gen_res = self.client.post(f"/api/rfps/{self.rfp_id}/sections/{self.section_id}/generate")
        self.assertEqual(gen_res.status_code, 200)
        data = gen_res.json()
        draft = data.get("draft_content", "")
        self.assertIn(whole_note, draft)
        sources = [p["source"] for p in data.get("provenance", [])]
        self.assertIn("notes", sources)

    def test_03_permutation_section_note_only(self):
        """Permutation 3: Section-specific note only -> incorporated into target section."""
        sec_note = "Section 2 specific: Recommend Tailwind CSS with Next.js App Router."
        self.client.post(f"/api/rfps/{self.rfp_id}/notes", json_data={
            "raw_content": sec_note,
            "section_id": self.section_id,
        })

        gen_res = self.client.post(f"/api/rfps/{self.rfp_id}/sections/{self.section_id}/generate")
        self.assertEqual(gen_res.status_code, 200)
        draft = gen_res.json().get("draft_content", "")
        self.assertIn(sec_note, draft)

    def test_04_permutation_hybrid_with_conflict_precedence(self):
        """Permutation 4: Both whole-RFP and section notes -> section note takes strict precedence."""
        whole_note = "General mandate: Focus on Drupal 10 enterprise architecture."
        section_note = "Override instruction: Client specifically forbids Drupal; use Statamic 4 only."

        self.client.post(f"/api/rfps/{self.rfp_id}/notes", json_data={"raw_content": whole_note})
        self.client.post(f"/api/rfps/{self.rfp_id}/notes", json_data={
            "raw_content": section_note,
            "section_id": self.section_id,
        })

        gen_res = self.client.post(f"/api/rfps/{self.rfp_id}/sections/{self.section_id}/generate")
        self.assertEqual(gen_res.status_code, 200)
        draft = gen_res.json().get("draft_content", "")

        # Specific section note must appear
        self.assertIn(section_note, draft)
        # Conflicting whole note should be superseded
        self.assertNotIn("Focus on Drupal 10", draft)


if __name__ == "__main__":
    unittest.main()

"""
Tier 1: Open Questions & Draft Editing Tests (F19, F20, F22)
Verifies [MORE INFO REQUIRED] marker detection, question extraction, resolution, and inline editing.
"""

import unittest
from tests.harness import TestHarnessClient


class TestOpenQuestions(unittest.TestCase):
    def setUp(self):
        self.client = TestHarnessClient()
        upload_res = self.client.post("/api/rfps/upload", json_data={"client_name": "Gap & Questions RFP"})
        self.rfp_id = upload_res.json()["rfp_id"]
        self.client.post(f"/api/rfps/{self.rfp_id}/classify")
        detail = self.client.get(f"/api/rfps/{self.rfp_id}").json()
        self.gap_section = next(s for s in detail["sections"] if s["classification"] == "gap")

    def test_01_marker_detection_in_draft(self):
        """Verify draft generation for gap section produces [MORE INFO REQUIRED: ...] marker."""
        gen_res = self.client.post(f"/api/rfps/{self.rfp_id}/sections/{self.gap_section['id']}/generate")
        self.assertEqual(gen_res.status_code, 200)
        draft = gen_res.json().get("draft_content", "")
        self.assertIn("[MORE INFO REQUIRED:", draft, "Draft missing [MORE INFO REQUIRED] marker")

    def test_02_auto_creation_of_open_question(self):
        """Verify marker in draft automatically creates open_questions record."""
        self.client.post(f"/api/rfps/{self.rfp_id}/sections/{self.gap_section['id']}/generate")
        q_res = self.client.get(f"/api/rfps/{self.rfp_id}/open-questions")
        self.assertEqual(q_res.status_code, 200)
        questions = q_res.json()
        self.assertGreaterEqual(len(questions), 1)
        target_q = next((q for q in questions if q["section_id"] == self.gap_section["id"]), None)
        self.assertIsNotNone(target_q, "Open question was not auto-created for gap section")
        self.assertEqual(target_q.get("status"), "open")

    def test_03_resolve_open_question(self):
        """Verify resolving an open question sets status='resolved' and saves resolution note."""
        self.client.post(f"/api/rfps/{self.rfp_id}/sections/{self.gap_section['id']}/generate")
        questions = self.client.get(f"/api/rfps/{self.rfp_id}/open-questions").json()
        qid = questions[0]["id"]

        resolution_text = "We hold certified SC clearance and completed NHS England telemetry in Q1 2025."
        res = self.client.put(f"/api/rfps/{self.rfp_id}/open-questions/{qid}", json_data={"resolution": resolution_text})
        self.assertEqual(res.status_code, 200)
        updated = res.json()
        self.assertEqual(updated.get("status"), "resolved")
        self.assertEqual(updated.get("resolution"), resolution_text)

    def test_04_direct_draft_editing(self):
        """Verify user can directly edit section draft and save final_content."""
        edited_text = "Manual override: This section was finalized by the Head of Public Sector bids."
        patch_res = self.client.patch(
            f"/api/rfps/{self.rfp_id}/sections/{self.gap_section['id']}",
            json_data={"final_content": edited_text, "status": "resolved"},
        )
        self.assertEqual(patch_res.status_code, 200)
        sec = patch_res.json()
        self.assertEqual(sec.get("final_content"), edited_text)
        self.assertEqual(sec.get("status"), "resolved")

    def test_05_section_status_tracking(self):
        """Verify section status transitions from pending -> drafted -> resolved."""
        # Initial status
        init_sec = self.client.get(f"/api/rfps/{self.rfp_id}").json()["sections"][0]
        self.assertIn(init_sec["status"], ["pending", "drafted"])

        # Manually update status
        up_res = self.client.patch(
            f"/api/rfps/{self.rfp_id}/sections/{init_sec['id']}",
            json_data={"status": "resolved"},
        )
        self.assertEqual(up_res.json()["status"], "resolved")


if __name__ == "__main__":
    unittest.main()

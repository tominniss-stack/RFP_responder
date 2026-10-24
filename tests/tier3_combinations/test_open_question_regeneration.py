"""
Tier 3 Combination: Open Question Resolution & Section Regeneration Loop (T3.02)
Verifies: Draft -> Marker -> Open Question -> Resolution -> Regeneration -> Marker Cleared -> Status Resolved.
"""

import unittest
from tests.harness import TestHarnessClient


class TestOpenQuestionRegeneration(unittest.TestCase):
    def setUp(self):
        self.client = TestHarnessClient()
        upload_res = self.client.post("/api/rfps/upload", json_data={"client_name": "Regeneration Loop Client"})
        self.rfp_id = upload_res.json()["rfp_id"]
        self.client.post(f"/api/rfps/{self.rfp_id}/classify")
        detail = self.client.get(f"/api/rfps/{self.rfp_id}").json()
        self.gap_sec = next(s for s in detail["sections"] if s["classification"] == "gap")

    def test_01_full_question_resolution_and_regeneration_lifecycle(self):
        """Verify full lifecycle: open question is created, resolved, and section regenerates with marker cleared."""
        # 1. Generate draft -> produces gap marker
        gen_res = self.client.post(f"/api/rfps/{self.rfp_id}/sections/{self.gap_sec['id']}/generate")
        self.assertEqual(gen_res.status_code, 200)
        draft1 = gen_res.json().get("draft_content", "")
        self.assertIn("[MORE INFO REQUIRED:", draft1)

        # 2. Check open question auto-created
        questions = self.client.get(f"/api/rfps/{self.rfp_id}/open-questions").json()
        self.assertGreaterEqual(len(questions), 1)
        target_q = next(q for q in questions if q["section_id"] == self.gap_sec["id"])
        self.assertEqual(target_q["status"], "open")

        # 3. Resolve open question
        resolution = "We delivered verified NHS Digital telemetry endpoints in Q1 2025 with 100% compliance."
        res_call = self.client.put(
            f"/api/rfps/{self.rfp_id}/open-questions/{target_q['id']}",
            json_data={"resolution": resolution},
        )
        self.assertEqual(res_call.status_code, 200)
        self.assertEqual(res_call.json()["status"], "resolved")

        # 4. Trigger section regeneration
        gen_res2 = self.client.post(f"/api/rfps/{self.rfp_id}/sections/{self.gap_sec['id']}/generate")
        self.assertEqual(gen_res2.status_code, 200)
        draft2 = gen_res2.json().get("draft_content", "")

        # 5. Verify resolution incorporated & marker eliminated
        self.assertIn("NHS Digital telemetry endpoints", draft2)
        self.assertNotIn("[MORE INFO REQUIRED:", draft2, "Regenerated draft should have eliminated the gap marker")

        # 6. Verify section status updated to 'resolved'
        updated_sec = self.client.get(f"/api/rfps/{self.rfp_id}").json()["sections"]
        target_sec = next(s for s in updated_sec if s["id"] == self.gap_sec["id"])
        self.assertEqual(target_sec["status"], "resolved")


if __name__ == "__main__":
    unittest.main()

"""
Tier 3 Combination: Selective Comment Anchoring on Google Docs Export (T3.03)
Verifies that only unresolved open questions produce Google Docs comment payloads.
"""

import unittest
from tests.harness import TestHarnessClient


class TestExportCommentPayload(unittest.TestCase):
    def setUp(self):
        self.client = TestHarnessClient()
        upload_res = self.client.post("/api/rfps/upload", json_data={"client_name": "Comment Export RFP"})
        self.rfp_id = upload_res.json()["rfp_id"]
        self.client.post(f"/api/rfps/{self.rfp_id}/classify")

    def test_01_unresolved_questions_generate_comments(self):
        """Verify unresolved open question creates a native comment in the export payload."""
        # Find gap section and generate draft to create open question
        detail = self.client.get(f"/api/rfps/{self.rfp_id}").json()
        gap_sec = next(s for s in detail["sections"] if s["classification"] == "gap")
        self.client.post(f"/api/rfps/{self.rfp_id}/sections/{gap_sec['id']}/generate")

        # Export in mock mode
        export_res = self.client.post(f"/api/rfps/{self.rfp_id}/export")
        self.assertEqual(export_res.status_code, 200)
        payload = export_res.json().get("payload", {})

        comments = payload.get("comments", [])
        self.assertGreaterEqual(len(comments), 1, "Unresolved open question should produce a comment in export payload")
        c = comments[0]
        self.assertIn("comment_payload", c)
        self.assertIn("[MORE INFO REQUIRED]", c["comment_payload"].get("content", ""))

    def test_02_resolved_questions_generate_zero_comments(self):
        """Verify resolving all open questions results in exactly 0 comments in the export payload."""
        detail = self.client.get(f"/api/rfps/{self.rfp_id}").json()
        gap_sec = next(s for s in detail["sections"] if s["classification"] == "gap")
        self.client.post(f"/api/rfps/{self.rfp_id}/sections/{gap_sec['id']}/generate")

        # Resolve all open questions
        questions = self.client.get(f"/api/rfps/{self.rfp_id}/open-questions").json()
        for q in questions:
            self.client.put(
                f"/api/rfps/{self.rfp_id}/open-questions/{q['id']}",
                json_data={"resolution": "Resolved for export test."},
            )

        # Export again
        export_res = self.client.post(f"/api/rfps/{self.rfp_id}/export")
        self.assertEqual(export_res.status_code, 200)
        payload = export_res.json().get("payload", {})
        comments = payload.get("comments", [])
        self.assertEqual(len(comments), 0, "Resolved questions should generate 0 comments in export payload")


if __name__ == "__main__":
    unittest.main()

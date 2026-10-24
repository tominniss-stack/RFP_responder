"""
Tier 3 Combination: Dynamic Settings Propagation (T3.04)
Verifies that updating prompts in Settings propagates immediately to subsequent draft generations without restart.
"""

import unittest
from tests.harness import TestHarnessClient


class TestSettingsPropagation(unittest.TestCase):
    def setUp(self):
        self.client = TestHarnessClient()
        upload_res = self.client.post("/api/rfps/upload", json_data={"client_name": "Settings Propagation RFP"})
        self.rfp_id = upload_res.json()["rfp_id"]
        self.client.post(f"/api/rfps/{self.rfp_id}/classify")
        detail = self.client.get(f"/api/rfps/{self.rfp_id}").json()
        self.sec = detail["sections"][1]  # Strategic section

    def test_01_tone_prompt_update_propagates_immediately(self):
        """Verify adding an executive summary requirement to tone prompt visibly alters draft immediately."""
        # 1. Update tone prompt in Settings
        updated_tone = "Include an executive summary sentence at the beginning of every response."
        self.client.put("/api/settings", json_data={"tone_of_voice_prompt": updated_tone})

        # 2. Immediately generate draft without server restart
        gen_res = self.client.post(f"/api/rfps/{self.rfp_id}/sections/{self.sec['id']}/generate")
        self.assertEqual(gen_res.status_code, 200)
        draft = gen_res.json().get("draft_content", "")

        # 3. Assert executive summary sentence is present
        self.assertIn("Executive Summary:", draft, "Updated prompt instruction did not immediately propagate to draft")


if __name__ == "__main__":
    unittest.main()

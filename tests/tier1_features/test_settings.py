"""
Tier 1: Settings Management & System Health Tests (F01, F02, F03, F25)
Verifies health check, API key configuration, independent model selection, and prompt editing.
"""

import unittest
from tests.harness import TestHarnessClient


class TestSettings(unittest.TestCase):
    def setUp(self):
        self.client = TestHarnessClient()

    def test_01_health_endpoint(self):
        """Verify GET /api/health returns status ok."""
        res = self.client.get("/api/health")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data.get("status"), "ok")

    def test_02_get_settings(self):
        """Verify GET /api/settings returns all required configuration keys."""
        res = self.client.get("/api/settings")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        required_keys = [
            "classification_model",
            "generation_model",
            "system_prompt",
            "tone_of_voice_prompt",
            "mock_google_export",
        ]
        for k in required_keys:
            self.assertIn(k, data, f"Missing required setting field: {k}")

    def test_03_update_api_keys(self):
        """Verify updating Claude and Gemini API keys."""
        payload = {
            "claude_api_key": "sk-ant-live-custom-key-12345",
            "gemini_api_key": "AIzaSyCustomKey-67890",
        }
        res = self.client.put("/api/settings", json_data=payload)
        self.assertEqual(res.status_code, 200)
        updated = self.client.get("/api/settings").json()
        self.assertEqual(updated.get("claude_api_key"), payload["claude_api_key"])
        self.assertEqual(updated.get("gemini_api_key"), payload["gemini_api_key"])

    def test_04_independent_model_selection(self):
        """Verify two-tier model selection: cheaper model for classification, capable model for generation."""
        payload = {
            "classification_model": "gemini-2.0-flash",
            "generation_model": "claude-3-7-sonnet",
        }
        res = self.client.put("/api/settings", json_data=payload)
        self.assertEqual(res.status_code, 200)
        updated = self.client.get("/api/settings").json()
        self.assertEqual(updated.get("classification_model"), "gemini-2.0-flash")
        self.assertEqual(updated.get("generation_model"), "claude-3-7-sonnet")

    def test_05_update_system_and_tone_prompts(self):
        """Verify editing system prompt and tone-of-voice prompt."""
        payload = {
            "tone_of_voice_prompt": "Always maintain concise, evidence-driven British agency prose.",
            "system_prompt": "Customized Another Marketing Agency RFP drafting instruction set.",
        }
        res = self.client.put("/api/settings", json_data=payload)
        self.assertEqual(res.status_code, 200)
        updated = self.client.get("/api/settings").json()
        self.assertEqual(updated.get("tone_of_voice_prompt"), payload["tone_of_voice_prompt"])
        self.assertEqual(updated.get("system_prompt"), payload["system_prompt"])


if __name__ == "__main__":
    unittest.main()

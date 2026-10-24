"""
Tier 2 Boundary Case: Malformed & Invalid Inputs Stress Testing (T2.07, T2.08, E11, E12, E15)
Verifies error boundaries: corrupt files, non-numeric price items, and schema validation.
"""

import unittest
from tests.harness import TestHarnessClient


class TestMalformedInputs(unittest.TestCase):
    def setUp(self):
        self.client = TestHarnessClient()

    def test_01_corrupt_file_upload_rejected(self):
        """Verify 0-byte or corrupted upload returns HTTP 400 Bad Request."""
        res = self.client.post("/api/rfps/upload", json_data={
            "client_name": "Corrupt Doc Client",
            "filename": "broken.empty",
            "file_bytes": b"",
        })
        self.assertEqual(res.status_code, 400)
        self.assertIn("empty or corrupted", res.json().get("error", "").lower())

    def test_02_negative_pricing_amount_rejected(self):
        """Verify adding price item with negative amount returns HTTP 422."""
        res = self.client.post("/api/pricing", json_data={
            "service_id": 1,
            "description": "Invalid Negative Rate",
            "unit": "day rate",
            "amount": -500.0,
        })
        self.assertEqual(res.status_code, 422)

    def test_03_invalid_pricing_unit_rejected(self):
        """Verify price item with invalid unit enum returns HTTP 422."""
        res = self.client.post("/api/pricing", json_data={
            "service_id": 1,
            "description": "Invalid Unit Rate",
            "unit": "hourly rate",  # Only 'day rate', 'fixed', 'monthly retainer' allowed
            "amount": 100.0,
        })
        self.assertEqual(res.status_code, 422)

    def test_04_empty_notes_content_rejected(self):
        """Verify submitting empty/whitespace-only note returns HTTP 422."""
        res = self.client.post("/api/rfps/1/notes", json_data={"raw_content": "   "})
        self.assertEqual(res.status_code, 422)

    def test_05_nonexistent_rfp_detail_returns_404(self):
        """Verify querying non-existent RFP ID returns HTTP 404 Not Found."""
        res = self.client.get("/api/rfps/999999")
        self.assertEqual(res.status_code, 404)


if __name__ == "__main__":
    unittest.main()

"""
Tier 1: Ingestion & Document Intake Tests (F06, F07)
Verifies manual RFP creation and document upload/extraction.
"""

import unittest
from pathlib import Path
from tests.harness import TestHarnessClient

SAMPLE_DOCX_PATH = Path(__file__).resolve().parent.parent.parent / "backend" / "data" / "sample_rfp.docx"


class TestIngestion(unittest.TestCase):
    def setUp(self):
        self.client = TestHarnessClient()
        if SAMPLE_DOCX_PATH.exists():
            self.docx_bytes = SAMPLE_DOCX_PATH.read_bytes()
        else:
            from backend.app.services.seed import generate_sample_docx
            self.docx_bytes = generate_sample_docx()

    def test_01_manual_rfp_creation(self):
        """Verify user can create an RFP manually with client name, value, and services."""
        payload = {
            "client_name": "Acme Heritage Foundation",
            "value": 45000.0,
            "service_ids": [1, 3],
        }
        res = self.client.post("/api/rfps", json_data=payload)
        self.assertIn(res.status_code, [200, 201], f"Expected 200/201, got {res.status_code}: {res.text}")
        data = res.json()
        self.assertIsNotNone(data.get("id"))
        self.assertEqual(data.get("client_name"), "Acme Heritage Foundation")
        self.assertEqual(data.get("value"), 45000.0)

    def test_02_manual_rfp_validation_error(self):
        """Verify API rejects creation if client_name is missing."""
        payload = {
            "value": 45000.0,
            "service_ids": [1],
        }
        res = self.client.post("/api/rfps", json_data=payload)
        self.assertEqual(res.status_code, 422, f"Expected 422 for missing client_name, got {res.status_code}")

    def test_03_document_upload_and_parse(self):
        """Verify document upload parses at least 5 distinct sections with headings."""
        payload = {
            "client_name": "National Heritage Trust",
            "filename": "sample_rfp.docx",
            "file_bytes": self.docx_bytes,
        }
        res = self.client.post("/api/rfps/upload", json_data=payload)
        self.assertIn(res.status_code, [200, 201], f"Expected 200/201, got {res.status_code}: {res.text}")
        data = res.json()
        self.assertIsNotNone(data.get("rfp_id"))
        self.assertGreaterEqual(data.get("sections_count", 0), 5)

        # Verify sections are stored in database
        rfp_res = self.client.get(f"/api/rfps/{data['rfp_id']}")
        self.assertEqual(rfp_res.status_code, 200)
        rfp_data = rfp_res.json()
        sections = rfp_data.get("sections", [])
        self.assertGreaterEqual(len(sections), 5)
        for sec in sections:
            self.assertTrue(bool(sec.get("heading")), "Section missing heading")
            self.assertTrue(bool(sec.get("original_text")), "Section missing original text")

    def test_04_extracted_section_headings_structure(self):
        """Verify extracted section headings preserve structure and ordering."""
        payload = {
            "client_name": "Structured Order Test Client",
            "filename": "sample_rfp.docx",
            "file_bytes": self.docx_bytes,
        }
        upload_res = self.client.post("/api/rfps/upload", json_data=payload)
        rfp_id = upload_res.json()["rfp_id"]

        detail_res = self.client.get(f"/api/rfps/{rfp_id}")
        sections = detail_res.json().get("sections", [])
        sort_orders = [s.get("sort_order", 0) for s in sections]
        self.assertEqual(sort_orders, sorted(sort_orders), "Sections not properly sorted by sort_order")

    def test_05_ingest_empty_file_fails(self):
        """Verify uploading an empty 0-byte file returns HTTP 400 Bad Request."""
        payload = {
            "client_name": "Empty File Test",
            "filename": "empty.empty",
            "file_bytes": b"",
        }
        res = self.client.post("/api/rfps/upload", json_data=payload)
        self.assertEqual(res.status_code, 400, f"Expected 400 for empty file, got {res.status_code}")


if __name__ == "__main__":
    unittest.main()

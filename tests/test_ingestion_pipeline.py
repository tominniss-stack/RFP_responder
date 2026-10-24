#!/usr/bin/env python3
"""
Empirical Stress Test Suite — Milestone 2 (Document Ingestion, Section Parsing & LLM Classification)
Challenger: challenger_m2_1

Empirical Tests:
1. File Upload Robustness & Error Handling:
   - Empty 0-byte files (.pdf, .docx, .empty) -> Graceful HTTP 400 Bad Request (no 500 crash).
   - Corrupted PDF (random garbage bytes, broken xref/trailer) -> Graceful HTTP 400 Bad Request (no 500 crash).
   - Corrupted DOCX (random garbage bytes, invalid zip, missing word/document.xml) -> Must be rejected with HTTP 400 (not 500 crash, and not silently accepted as 201).
   - Unsupported extensions (.txt, .exe, .json) -> HTTP 400 Bad Request.

2. Structural Section Extraction:
   - Markdown headers (#, ##, ###) extraction and sequence preservation.
   - Numbered clauses (Section, Part, Module, Requirement, Clause, 1.0) extraction and ordering.
   - Question blocks (Question 1, Q1:) and markdown table structures.
   - Fallback splitting on double-newlines when headings are absent.

3. LLM Classification Schema Validation:
   - Conformance against JSON schema in ORIGINAL_REQUEST.md lines 240-252.
   - All 7 required fields present: section_id, heading, original_text, classification, confidence, clarifying_question, suggested_default.
   - Classification taxonomy validation: {boilerplate, pricing, strategic_decision, gap, compliance_admin}.
   - Confidence scoring validation: {high, medium, low}.
   - JSON fence stripping & malformed LLM response error recovery.

4. Ambiguous Section Classification Handling:
   - Deliberately ambiguous section (Accessibility / WCAG compliance).
   - Classification assigned to strategic_decision (or gap).
   - Confidence rating must NOT be high (must be medium or low).
   - Clarifying question generated and actionable (referencing WCAG conformance).
   - Auto-population into open_questions table with status='open'.
   - Manual override via PATCH /api/rfps/{id}/sections/{section_id} persistence.
"""

import glob
import io
import json
import os
import sqlite3
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

# Ensure backend and project root are in python path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

venv_pkgs = glob.glob(str(PROJECT_ROOT / ".venv" / "lib" / "python*" / "site-packages"))
for p in venv_pkgs:
    if p not in sys.path:
        sys.path.insert(0, p)

from fastapi.testclient import TestClient
from app.main import app
from app.database import get_db, get_db_connection, init_db
from app.services.ingestion import (
    extract_from_docx,
    extract_from_pdf,
    ingest_document,
    split_text_into_sections,
)
from app.services.llm import (
    clean_json_response,
    classify_rfp_sections,
    mock_classify_sections,
)
from tests.harness import TestHarnessClient


class TestFileUploadRejectionEmpirical(unittest.TestCase):
    """Empirical verification of upload error handling and rejection boundaries."""

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.tmp.name
        self.tmp.close()
        init_db(self.db_path)

        def override_get_db():
            conn = get_db_connection(self.db_path)
            try:
                yield conn
            finally:
                conn.close()

        app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_01_empty_pdf_upload_rejected_400(self):
        """0-byte PDF upload returns HTTP 400 Bad Request, never 500 or 201."""
        res = self.client.post(
            "/api/rfps/upload",
            data={"client_name": "Test Client"},
            files={"file": ("empty.pdf", b"", "application/pdf")},
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("empty or corrupted", res.json().get("error", "").lower())

    def test_02_empty_docx_upload_rejected_400(self):
        """0-byte DOCX upload returns HTTP 400 Bad Request, never 500 or 201."""
        res = self.client.post(
            "/api/rfps/upload",
            data={"client_name": "Test Client"},
            files={"file": ("empty.docx", b"", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("empty or corrupted", res.json().get("error", "").lower())

    def test_03_empty_custom_extension_rejected_400(self):
        """Upload with .empty extension returns HTTP 400 Bad Request."""
        res = self.client.post(
            "/api/rfps/upload",
            data={"client_name": "Test Client"},
            files={"file": ("test.empty", b"", "application/octet-stream")},
        )
        self.assertEqual(res.status_code, 400)

    def test_04_unsupported_file_extension_rejected_400(self):
        """Uploading unsupported file formats (.txt, .exe) returns HTTP 400."""
        res = self.client.post(
            "/api/rfps/upload",
            data={"client_name": "Test Client"},
            files={"file": ("document.txt", b"Plain text payload", "text/plain")},
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("only .pdf and .docx are supported", res.json().get("error", "").lower())

    def test_05_corrupted_pdf_random_bytes_rejected_400(self):
        """Corrupted PDF binary stream returns HTTP 400 Bad Request, not 500 crash or 201."""
        corrupt_bytes = b"\x00\x01\x02\x03\xff\xfe\xaa\xbb\xcc\xdd" * 20
        res = self.client.post(
            "/api/rfps/upload",
            data={"client_name": "Corrupt PDF Client"},
            files={"file": ("corrupt.pdf", corrupt_bytes, "application/pdf")},
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("failed to parse document", res.json().get("error", "").lower())

    def test_06_corrupted_pdf_truncated_syntax_rejected_400(self):
        """Truncated PDF missing object dictionary returns HTTP 400 Bad Request."""
        truncated_pdf = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n"
        res = self.client.post(
            "/api/rfps/upload",
            data={"client_name": "Truncated PDF Client"},
            files={"file": ("truncated.pdf", truncated_pdf, "application/pdf")},
        )
        self.assertEqual(res.status_code, 400)

    def test_07_corrupted_docx_random_bytes_rejection(self):
        """Corrupted DOCX (random binary noise) must be rejected with HTTP 400, NOT 201."""
        corrupt_docx_bytes = b"\x00\x01\x02\x03\xff\xfe\xaa\xbb\xcc\xdd" * 20
        res = self.client.post(
            "/api/rfps/upload",
            data={"client_name": "Corrupt DOCX Client"},
            files={"file": ("corrupted.docx", corrupt_docx_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        )
        # Expected: HTTP 400 Bad Request.
        # If it returns 201, the parser decoded corrupted binary data as text!
        self.assertEqual(
            res.status_code,
            400,
            f"Expected HTTP 400 for corrupted DOCX binary upload, got HTTP {res.status_code}: {res.text}",
        )

    def test_08_corrupted_docx_invalid_zip_rejection(self):
        """Corrupted DOCX (invalid zip header or truncated zip) must be rejected with HTTP 400."""
        broken_zip = b"PK\x03\x04\x14\x00corrupted_zip_payload_data"
        res = self.client.post(
            "/api/rfps/upload",
            data={"client_name": "Broken Zip Client"},
            files={"file": ("broken.docx", broken_zip, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        )
        self.assertEqual(
            res.status_code,
            400,
            f"Expected HTTP 400 for broken zip DOCX upload, got HTTP {res.status_code}: {res.text}",
        )

    def test_09_corrupted_docx_empty_zip_without_xml_rejection(self):
        """DOCX that is a valid zip but missing word/document.xml must be rejected with HTTP 400."""
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w") as zf:
            zf.writestr("unrelated.txt", "This is not a docx document")
        empty_docx = zip_buf.getvalue()

        res = self.client.post(
            "/api/rfps/upload",
            data={"client_name": "Empty Zip Client"},
            files={"file": ("nodoc.docx", empty_docx, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        )
        self.assertEqual(
            res.status_code,
            400,
            f"Expected HTTP 400 for DOCX missing word/document.xml, got HTTP {res.status_code}: {res.text}",
        )


class TestSectionExtractionEmpirical(unittest.TestCase):
    """Empirical verification of structural section detection."""

    def test_01_markdown_headers_extraction(self):
        """Extracts sections from multi-level Markdown headers (#, ##, ###)."""
        raw_text = (
            "# 1.0 Executive Summary\n"
            "Overview of Another Marketing Agency credentials and leadership.\n\n"
            "## 2.0 Technical Architecture\n"
            "Details on Statamic headless CMS and Next.js frontend.\n\n"
            "### 2.1 Infrastructure & SLA\n"
            "High-availability cloud deployment with 99.9% uptime SLA.\n\n"
            "## 3.0 Commercial Model\n"
            "Fixed fee delivery with transparent sprint velocity."
        )
        sections = split_text_into_sections(raw_text)
        self.assertEqual(len(sections), 4)
        self.assertEqual(sections[0]["heading"], "1.0 Executive Summary")
        self.assertIn("Overview of Another Marketing Agency", sections[0]["original_text"])
        self.assertEqual(sections[0]["sort_order"], 1)

        self.assertEqual(sections[1]["heading"], "2.0 Technical Architecture")
        self.assertEqual(sections[2]["heading"], "2.1 Infrastructure & SLA")
        self.assertEqual(sections[3]["heading"], "3.0 Commercial Model")

    def test_02_numbered_clauses_extraction(self):
        """Extracts sections from formal clause prefixes (Section, Part, Module, Requirement, Clause)."""
        raw_text = (
            "Section 1.0: Agency Credentials & Case Studies\n"
            "Proven track record delivering public sector digital platforms.\n\n"
            "Part 2.1: Content Management Architecture\n"
            "Decoupled authoring workflow with versioning.\n\n"
            "Requirement 3.0: Accessibility Compliance\n"
            "Mandatory compliance with WCAG 2.2 AA standards.\n\n"
            "Clause 4.1: Data Protection & GDPR\n"
            "Full adherence to UK GDPR and ISO 27001 accreditation.\n\n"
            "Module 5: Commercial Terms\n"
            "Blended day rates and milestone payment gates."
        )
        sections = split_text_into_sections(raw_text)
        self.assertEqual(len(sections), 5)
        self.assertIn("1.0: Agency Credentials", sections[0]["heading"])
        self.assertIn("2.1: Content Management", sections[1]["heading"])
        self.assertIn("3.0: Accessibility Compliance", sections[2]["heading"])
        self.assertIn("4.1: Data Protection", sections[3]["heading"])
        self.assertIn("5: Commercial Terms", sections[4]["heading"])

    def test_03_question_headers_and_tables(self):
        """Extracts question blocks and preserves table structures within section content."""
        raw_text = (
            "## Section 1: Vendor Questionnaire\n\n"
            "| Question ID | Question Text | Response Requirement |\n"
            "| --- | --- | --- |\n"
            "| Q1 | What is your CMS platform recommendation? | Technical approach |\n"
            "| Q2 | What is your standard developer day rate? | Pricing figures |\n\n"
            "Question 3: Describe your approach to automated QA testing.\n"
            "We employ end-to-end Playwright tests with synthetic user journeys."
        )
        sections = split_text_into_sections(raw_text)
        self.assertGreaterEqual(len(sections), 2)
        # Verify table preserved in first section
        self.assertIn("| Question ID | Question Text |", sections[0]["original_text"])
        self.assertIn("| Q1 | What is your CMS platform recommendation? |", sections[0]["original_text"])
        # Verify Question 3 detected as distinct heading
        q3_sec = next((s for s in sections if "3:" in s["heading"]), None)
        self.assertIsNotNone(q3_sec, "Question 3 not detected as a heading")
        self.assertIn("Playwright tests", q3_sec["original_text"])

    def test_04_double_newline_fallback(self):
        """Fallback to paragraph chunking when document contains no structural headings."""
        raw_text = (
            "Another Marketing Agency is a digital product agency based in the UK.\n"
            "We specialize in modern web applications.\n\n"
            "Our pricing model is based on transparent day rates.\n"
            "Senior consultants are billed at standard agency rate.\n\n"
            "We adhere to strict data security protocols.\n"
            "All databases are encrypted at rest and in transit."
        )
        sections = split_text_into_sections(raw_text)
        self.assertEqual(len(sections), 3)
        for idx, s in enumerate(sections, start=1):
            self.assertEqual(s["sort_order"], idx)
            self.assertTrue(len(s["original_text"]) > 0)


class TestLLMClassificationSchemaValidation(unittest.TestCase):
    """Empirical verification of classification output schema strictly conforming to ORIGINAL_REQUEST.md."""

    def test_01_schema_conformance_all_required_fields(self):
        """Validates all 7 required schema fields are present on every classified item."""
        sample_sections = [
            {"id": 1, "heading": "1.0 Executive Summary", "original_text": "Agency credentials and team bios."},
            {"id": 2, "heading": "2.0 Technical Architecture", "original_text": "Statamic headless CMS platform selection."},
            {"id": 3, "heading": "3.0 Commercial Proposal", "original_text": "Developer day rates and total cost schedule."},
            {"id": 4, "heading": "4.0 Public Health Telemetry", "original_text": "Demonstrate niche experience in NHS telemetry."},
            {"id": 5, "heading": "5.0 GDPR Sign-Off", "original_text": "Declaration of compliance and signature checklist."},
        ]

        results = mock_classify_sections(sample_sections)
        self.assertEqual(len(results), 5)

        required_keys = {
            "section_id",
            "heading",
            "original_text",
            "classification",
            "confidence",
            "clarifying_question",
            "suggested_default",
        }

        valid_categories = {
            "boilerplate",
            "pricing",
            "strategic_decision",
            "gap",
            "compliance_admin",
        }

        valid_confidences = {"high", "medium", "low"}

        for item in results:
            item_keys = set(item.keys())
            self.assertTrue(
                required_keys.issubset(item_keys),
                f"Missing required keys in classification output: {required_keys - item_keys}",
            )
            self.assertIn(
                item["classification"],
                valid_categories,
                f"Invalid classification category: {item['classification']}",
            )
            self.assertIn(
                item["confidence"],
                valid_confidences,
                f"Invalid confidence rating: {item['confidence']}",
            )

    def test_02_classify_rfp_sections_normalizer(self):
        """Validates classify_rfp_sections normalizes categories and preserves required fields."""
        sections = [
            {"id": 101, "heading": "Rate Card", "original_text": "Senior Engineer £950/day."},
        ]
        res = classify_rfp_sections(sections)
        self.assertEqual(len(res), 1)
        item = res[0]
        self.assertEqual(item["section_id"], 101)
        self.assertEqual(item["classification"], "pricing")
        self.assertEqual(item["confidence"], "high")
        self.assertIn("original_text", item)
        self.assertIn("clarifying_question", item)
        self.assertIn("suggested_default", item)

    def test_03_clean_json_response_resilience(self):
        """Validates clean_json_response strips markdown fences and conversational wrappers."""
        fenced_json = """```json
[
  {
    "section_id": 1,
    "heading": "Approach",
    "original_text": "CMS details",
    "classification": "STRATEGIC_DECISION",
    "confidence": "high",
    "clarifying_question": "Which CMS?",
    "suggested_default": "Statamic"
  }
]
```"""
        parsed = clean_json_response(fenced_json)
        self.assertIsInstance(parsed, list)
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["section_id"], 1)

        wrapped_json = """Here is the structured classification you requested:
[
  {
    "section_id": 2,
    "heading": "Rates",
    "original_text": "Day rate £950",
    "classification": "PRICING",
    "confidence": "high",
    "clarifying_question": "",
    "suggested_default": ""
  }
]
Please let me know if you need further adjustments."""
        parsed2 = clean_json_response(wrapped_json)
        self.assertIsInstance(parsed2, list)
        self.assertEqual(parsed2[0]["classification"], "PRICING")

    def test_04_clean_json_response_rejects_non_array(self):
        """clean_json_response raises ValueError when output is a single object or malformed."""
        with self.assertRaises(ValueError):
            clean_json_response('{"section_id": 1, "classification": "boilerplate"}')


class TestAmbiguousSectionClassificationEmpirical(unittest.TestCase):
    """Empirical verification of ambiguous section classification handling."""

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.tmp.name
        self.tmp.close()
        init_db(self.db_path)

        def override_get_db():
            conn = get_db_connection(self.db_path)
            try:
                yield conn
            finally:
                conn.close()

        app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_01_ambiguous_accessibility_classification(self):
        """Ambiguous accessibility requirement classifies into strategic_decision with medium confidence."""
        ambiguous_section = [
            {
                "id": 1,
                "heading": "3.0 Accessibility & WCAG Standards",
                "original_text": "Describe your recommended technical approach to public sector accessibility compliance and relevant WCAG experience.",
            }
        ]
        classified = mock_classify_sections(ambiguous_section)
        self.assertEqual(len(classified), 1)
        item = classified[0]

        # Category must be strategic_decision (or gap)
        self.assertIn(item["classification"], ["strategic_decision", "gap"])
        # Confidence must be medium or low, NOT high
        self.assertIn(item["confidence"], ["medium", "low"])
        # Clarifying question must be non-empty and address WCAG
        self.assertTrue(bool(item["clarifying_question"]))
        self.assertIn("wcag", item["clarifying_question"].lower())
        # Suggested default must be provided
        self.assertTrue(bool(item["suggested_default"]))

    def test_02_ambiguous_classification_registers_open_question(self):
        """Triggering /classify on RFP with ambiguous section registers an open question."""
        conn = get_db_connection(self.db_path)
        cur = conn.execute("INSERT INTO rfps (client_name) VALUES ('Ambiguity Test Org');")
        rfp_id = cur.lastrowid
        conn.execute(
            """
            INSERT INTO rfp_sections (rfp_id, heading, original_text, sort_order)
            VALUES (?, '3.0 Accessibility Compliance', 'Describe your recommended approach to WCAG compliance.', 1);
            """,
            (rfp_id,),
        )
        conn.commit()
        conn.close()

        classify_res = self.client.post(f"/api/rfps/{rfp_id}/classify")
        self.assertEqual(classify_res.status_code, 200)

        # Check RFP detail
        detail_res = self.client.get(f"/api/rfps/{rfp_id}")
        self.assertEqual(detail_res.status_code, 200)
        detail = detail_res.json()

        # Verify section classification
        sec = detail["sections"][0]
        self.assertEqual(sec["classification"], "strategic_decision")
        self.assertEqual(sec["confidence"], "medium")

        # Verify open question auto-created
        open_qs = detail.get("open_questions", [])
        self.assertEqual(len(open_qs), 1)
        self.assertEqual(open_qs[0]["status"], "open")
        self.assertIn("wcag", open_qs[0]["question"].lower())

    def test_03_ambiguous_section_manual_override(self):
        """Manual override via PATCH /api/rfps/{id}/sections/{section_id} updates classification."""
        conn = get_db_connection(self.db_path)
        cur = conn.execute("INSERT INTO rfps (client_name) VALUES ('Override Client');")
        rfp_id = cur.lastrowid
        cur_sec = conn.execute(
            """
            INSERT INTO rfp_sections (rfp_id, heading, original_text, sort_order)
            VALUES (?, '3.0 Accessibility Compliance', 'WCAG approach', 1);
            """,
            (rfp_id,),
        )
        sec_id = cur_sec.lastrowid
        conn.commit()
        conn.close()

        # Classify first
        self.client.post(f"/api/rfps/{rfp_id}/classify")

        # Override to gap
        patch_res = self.client.patch(
            f"/api/rfps/{rfp_id}/sections/{sec_id}",
            json={"classification": "gap", "status": "resolved"},
        )
        self.assertEqual(patch_res.status_code, 200)
        self.assertEqual(patch_res.json()["classification"], "gap")
        self.assertEqual(patch_res.json()["status"], "resolved")

        # Re-fetch detail to verify DB persistence
        detail = self.client.get(f"/api/rfps/{rfp_id}").json()
        persisted_sec = detail["sections"][0]
        self.assertEqual(persisted_sec["classification"], "gap")
        self.assertEqual(persisted_sec["status"], "resolved")


if __name__ == "__main__":
    unittest.main()

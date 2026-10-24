"""Unit and integration tests for Milestone 2: Document Ingestion, Section Parsing & LLM Classification.

Covers:
1. Document Ingestion Service (PDF, DOCX paragraphs, DOCX tables, heading heuristics)
2. Multi-Provider LLM Client & Classification Engine (Categories, Confidence, Ambiguous case, Schemas)
3. FastAPI RFP Endpoints (Manual creation, Upload, List/Filter, Detail, Classify, Override, Boundaries)
"""

import glob
import io
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock
import zipfile

# Ensure backend root and virtualenv site-packages are on sys.path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

venv_pkgs = glob.glob(str(backend_dir.parent / ".venv" / "lib" / "python*" / "site-packages"))
for p in venv_pkgs:
    if p not in sys.path:
        sys.path.insert(0, p)

from fastapi.testclient import TestClient
from app.database import get_db_connection, init_db, get_db
from app.main import app
from app.services.ingestion import (
    extract_from_pdf,
    extract_from_docx,
    split_text_into_sections,
    save_uploaded_file,
    ingest_document,
)
from app.services.llm import (
    mock_classify_sections,
    classify_rfp_sections,
    call_model,
    clean_json_response,
)


def generate_test_pdf(heading: str, body: str) -> bytes:
    """Generate a minimal valid single-page PDF with Helvetica text stream."""
    stream_content = f"BT /F1 14 Tf 50 700 Td ({heading}) Tj /F1 11 Tf 0 -25 Td ({body}) Tj ET".encode("latin1")
    length = len(stream_content)
    pdf = (
        b"%PDF-1.4\n"
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
        b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n"
        b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> >> >> "
        b"/Contents 4 0 R >> endobj\n"
        b"4 0 obj << /Length " + str(length).encode("ascii") + b" >>\nstream\n"
        + stream_content +
        b"\nendstream\nendobj\n"
        b"xref\n0 5\n0000000000 65535 f \n"
        b"0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \n"
        b"0000000280 00000 n \n"
        b"trailer << /Size 5 /Root 1 0 R >>\nstartxref\n400\n%%EOF\n"
    )
    return pdf


def generate_test_docx(heading: str, body: str, table_rows=None) -> bytes:
    """Generate a valid DOCX archive in memory with heading styles and tables."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        tbl_xml = ""
        if table_rows:
            tr_elements = []
            for row in table_rows:
                tc_elements = "".join([f"<w:tc><w:p><w:r><w:t>{cell}</w:t></w:r></w:p></w:tc>" for cell in row])
                tr_elements.append(f"<w:tr>{tc_elements}</w:tr>")
            tbl_xml = f"<w:tbl>{''.join(tr_elements)}</w:tbl>"

        doc_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
        <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
            <w:body>
                <w:p>
                    <w:pPr><w:pStyle w:val="Heading1"/></w:pPr>
                    <w:r><w:t>{heading}</w:t></w:r>
                </w:p>
                <w:p>
                    <w:r><w:t>{body}</w:t></w:r>
                </w:p>
                {tbl_xml}
            </w:body>
        </w:document>"""
        zf.writestr("word/document.xml", doc_xml)
    return buf.getvalue()


class TestDocumentIngestion(unittest.TestCase):
    """Unit tests for PDF, DOCX, and section splitting algorithms."""

    def test_01_extract_sections_from_pdf(self):
        """Extracts heading and body text from a PDF document."""
        pdf_bytes = generate_test_pdf("1.0 Scope of Work", "Provide digital platform development.")
        extracted = extract_from_pdf(pdf_bytes)
        self.assertIn("1.0 Scope of Work", extracted)
        self.assertIn("Provide digital platform development.", extracted)

    def test_02_extract_sections_from_docx_paragraphs(self):
        """Extracts headings and paragraphs from a DOCX document."""
        docx_bytes = generate_test_docx("2.0 Technical Architecture", "Headless CMS using Statamic.")
        extracted = extract_from_docx(docx_bytes)
        self.assertIn("2.0 Technical Architecture", extracted)
        self.assertIn("Headless CMS using Statamic.", extracted)

    def test_03_extract_sections_from_docx_tables(self):
        """Extracts table rows from DOCX into Markdown table structure."""
        docx_bytes = generate_test_docx(
            "5.0 Commercial Schedule",
            "Rate schedule below:",
            table_rows=[["Role", "Day Rate"], ["Senior Developer", "£950"], ["Designer", "£800"]],
        )
        extracted = extract_from_docx(docx_bytes)
        self.assertIn("| Role | Day Rate |", extracted)
        self.assertIn("| Senior Developer | £950 |", extracted)

    def test_04_fallback_markdown_headers(self):
        """Segments raw text containing Markdown headers (#, ##, ###)."""
        raw = (
            "# 1.0 Executive Summary\nAnother Marketing Agency credentials.\n\n"
            "## 2.0 Approach\nStatamic 4 delivery.\n\n"
            "### 3.0 Rates\nSenior Dev £950."
        )
        sections = split_text_into_sections(raw)
        self.assertEqual(len(sections), 3)
        self.assertEqual(sections[0]["heading"], "1.0 Executive Summary")
        self.assertEqual(sections[1]["heading"], "2.0 Approach")
        self.assertEqual(sections[2]["heading"], "3.0 Rates")

    def test_05_fallback_numbered_sections(self):
        """Segments text containing Section / Part / Module prefixes."""
        raw = (
            "Section 1: Company Profile\nEstablished in 2016.\n\n"
            "Part 2: Technical Specifications\nDecoupled frontend architecture.\n\n"
            "Question 3: Commercial Proposal\nProvide pricing structure."
        )
        sections = split_text_into_sections(raw)
        self.assertEqual(len(sections), 3)
        self.assertIn("Company Profile", sections[0]["heading"])
        self.assertIn("Technical Specifications", sections[1]["heading"])
        self.assertIn("Commercial Proposal", sections[2]["heading"])

    def test_06_fallback_double_newlines(self):
        """Splits raw text without headers into paragraph blocks."""
        raw = (
            "This is paragraph one providing an overview of requirements.\n\n"
            "This is paragraph two outlining technical expectations.\n\n"
            "This is paragraph three describing delivery timelines."
        )
        sections = split_text_into_sections(raw)
        self.assertEqual(len(sections), 3)
        self.assertEqual(sections[0]["sort_order"], 1)
        self.assertEqual(sections[1]["sort_order"], 2)
        self.assertEqual(sections[2]["sort_order"], 3)


class TestMultiProviderLLMClient(unittest.TestCase):
    """Unit tests for model dispatch, keyword classification, and schema conformance."""

    def test_07_mock_llm_pricing_classification(self):
        """Detects pricing keywords and assigns high confidence."""
        sections = [{"heading": "Commercials", "original_text": "Please provide day rates and fixed project cost."}]
        res = mock_classify_sections(sections)
        self.assertEqual(res[0]["classification"], "pricing")
        self.assertEqual(res[0]["confidence"], "high")

    def test_08_mock_llm_boilerplate_classification(self):
        """Detects boilerplate credentials and assigns high confidence."""
        sections = [{"heading": "Agency Overview", "original_text": "Provide company background, team bios, and insurance."}]
        res = mock_classify_sections(sections)
        self.assertEqual(res[0]["classification"], "boilerplate")
        self.assertEqual(res[0]["confidence"], "high")

    def test_09_mock_llm_strategic_classification(self):
        """Detects architecture / platform keywords and populates clarifying question."""
        sections = [{"heading": "Architecture", "original_text": "Detail your proposed CMS platform and technical approach."}]
        res = mock_classify_sections(sections)
        self.assertEqual(res[0]["classification"], "strategic_decision")
        self.assertTrue(bool(res[0]["clarifying_question"]))
        self.assertTrue(bool(res[0]["suggested_default"]))

    def test_10_mock_llm_gap_classification(self):
        """Detects niche domain keywords and assigns gap classification."""
        sections = [{"heading": "NHS Telemetry", "original_text": "Describe your experience in NHS telemetry systems."}]
        res = mock_classify_sections(sections)
        self.assertEqual(res[0]["classification"], "gap")
        self.assertTrue(bool(res[0]["clarifying_question"]))

    def test_11_mock_llm_compliance_classification(self):
        """Detects compliance / declaration keywords."""
        sections = [{"heading": "Declaration", "original_text": "Sign and accept terms and conditions and GDPR declaration."}]
        res = mock_classify_sections(sections)
        self.assertEqual(res[0]["classification"], "compliance_admin")
        self.assertEqual(res[0]["confidence"], "high")

    def test_12_mock_llm_ambiguous_edge_case(self):
        """Evaluates ambiguous prompt blending approach and experience -> medium confidence."""
        sections = [{
            "heading": "3.0 Accessibility Compliance",
            "original_text": "Describe your recommended approach to accessibility compliance, including any relevant experience with WCAG standards.",
        }]
        res = mock_classify_sections(sections)
        self.assertEqual(res[0]["classification"], "strategic_decision")
        self.assertEqual(res[0]["confidence"], "medium")
        self.assertIn("wcag", res[0]["clarifying_question"].lower())

    def test_13_mock_llm_output_schema_conformance(self):
        """Validates classified output strictly matches ORIGINAL_REQUEST.md lines 240-252."""
        sections = [{"id": 10, "heading": "Pricing", "original_text": "Rates and budget"}]
        res = mock_classify_sections(sections)
        self.assertEqual(len(res), 1)
        item = res[0]
        required_keys = ["section_id", "heading", "original_text", "classification", "confidence", "clarifying_question", "suggested_default"]
        for k in required_keys:
            self.assertIn(k, item)

    @patch("urllib.request.urlopen")
    def test_14_claude_api_dispatch_mocked(self, mock_urlopen):
        """Verifies Anthropic API dispatch formats request and extracts content."""
        from app.services.llm import call_claude_api
        fake_response = MagicMock()
        fake_response.read.return_value = json.dumps({
            "content": [{"text": '[{"section_id": 1, "heading": "Test", "classification": "boilerplate"}]'}]
        }).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = fake_response

        res = call_claude_api("sk-ant-testkey", "claude-3-5-sonnet", "Classify this", "System prompt")
        self.assertIn("boilerplate", res)

    @patch("urllib.request.urlopen")
    def test_15_gemini_api_dispatch_mocked(self, mock_urlopen):
        """Verifies Google Gemini generateContent payload and response parsing."""
        from app.services.llm import call_gemini_api
        fake_response = MagicMock()
        fake_response.read.return_value = json.dumps({
            "candidates": [{"content": {"parts": [{"text": '[{"section_id": 1, "heading": "Test", "classification": "pricing"}]'}]}}]
        }).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = fake_response

        res = call_gemini_api("AIzaSy-testkey", "gemini-1.5-flash", "Classify this", "System prompt")
        self.assertIn("pricing", res)


class TestRFPAPIEndpoints(unittest.TestCase):
    """End-to-end integration tests using FastAPI TestClient and isolated temporary database."""

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

    def test_16_post_rfps_manual_creation(self):
        """POST /api/rfps creates manual RFP with service links."""
        payload = {
            "client_name": "Manual Intake Client",
            "value": 55000.0,
            "date_submitted": "2026-09-15",
            "service_ids": [1, 3],
        }
        res = self.client.post("/api/rfps", json=payload)
        self.assertEqual(res.status_code, 201)
        data = res.json()
        self.assertEqual(data["client_name"], "Manual Intake Client")
        self.assertEqual(data["value"], 55000.0)

    def test_17_get_rfps_list_and_filtering(self):
        """GET /api/rfps lists and filters RFPs by client and status."""
        self.client.post("/api/rfps", json={"client_name": "Client Red", "status": "draft"})
        self.client.post("/api/rfps", json={"client_name": "Client Blue", "status": "won"})

        # Filter by status
        res = self.client.get("/api/rfps?status=won")
        self.assertEqual(res.status_code, 200)
        items = res.json()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["client_name"], "Client Blue")

        # Filter by client name substring
        res_client = self.client.get("/api/rfps?client=Red")
        self.assertEqual(res_client.status_code, 200)
        self.assertEqual(len(res_client.json()), 1)

    def test_18_post_rfps_upload_pdf(self):
        """POST /api/rfps/upload parses PDF document bytes and inserts sections."""
        pdf_bytes = generate_test_pdf("1.0 Background", "Requirement for new agency partner.")
        files = {"file": ("tender.pdf", pdf_bytes, "application/pdf")}
        data = {"client_name": "PDF Tender Client", "value": "40000"}

        res = self.client.post("/api/rfps/upload", data=data, files=files)
        self.assertEqual(res.status_code, 201)
        body = res.json()
        self.assertIsNotNone(body.get("rfp_id"))
        self.assertGreaterEqual(body.get("sections_count", 0), 1)

    def test_19_post_rfps_upload_docx(self):
        """POST /api/rfps/upload parses DOCX document and inserts sections."""
        docx_bytes = generate_test_docx(
            "1.0 Proposal Overview",
            "Section body description.",
            table_rows=[["Section", "Req"], ["Security", "ISO 27001"]],
        )
        files = {"file": ("specification.docx", docx_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}
        data = {"client_name": "DOCX Spec Client"}

        res = self.client.post("/api/rfps/upload", data=data, files=files)
        self.assertEqual(res.status_code, 201)
        body = res.json()
        self.assertIsNotNone(body.get("rfp_id"))
        self.assertGreaterEqual(body.get("sections_count", 0), 1)

    def test_20_get_rfp_detail_full(self):
        """GET /api/rfps/{id} returns sections, notes, and open questions."""
        create_res = self.client.post("/api/rfps", json={"client_name": "Detail Client"})
        rfp_id = create_res.json()["id"]

        detail_res = self.client.get(f"/api/rfps/{rfp_id}")
        self.assertEqual(detail_res.status_code, 200)
        detail = detail_res.json()
        self.assertIn("sections", detail)
        self.assertIn("notes", detail)
        self.assertIn("open_questions", detail)

    def test_21_post_rfp_classify_execution(self):
        """POST /api/rfps/{id}/classify executes classification and populates open questions."""
        docx_bytes = generate_test_docx("2.0 Technical Approach", "Choice of CMS platform and architecture.")
        upload_res = self.client.post(
            "/api/rfps/upload",
            data={"client_name": "Classify Client"},
            files={"file": ("spec.docx", docx_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        )
        rfp_id = upload_res.json()["rfp_id"]

        classify_res = self.client.post(f"/api/rfps/{rfp_id}/classify")
        self.assertEqual(classify_res.status_code, 200)
        classified = classify_res.json()
        self.assertEqual(len(classified), 1)
        self.assertEqual(classified[0]["classification"], "strategic_decision")
        self.assertIsNotNone(classified[0]["clarifying_question"])

        # A strategic-decision classification with a clarifying question registers an open question
        detail = self.client.get(f"/api/rfps/{rfp_id}").json()
        self.assertEqual(len(detail["open_questions"]), 1)
        self.assertEqual(detail["open_questions"][0]["status"], "open")
        self.assertEqual(detail["open_questions"][0]["question"], classified[0]["clarifying_question"])

        # Engine metadata is reported so the UI can show mock vs live provenance
        self.assertEqual(classify_res.headers.get("x-llm-engine"), "mock")

    def test_22_put_section_manual_override(self):
        """PUT and PATCH /api/rfps/{id}/sections/{section_id} updates classification."""
        docx_bytes = generate_test_docx("1.0 Section", "Default section content.")
        upload_res = self.client.post(
            "/api/rfps/upload",
            data={"client_name": "Override Client"},
            files={"file": ("spec.docx", docx_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        )
        rfp_id = upload_res.json()["rfp_id"]
        detail = self.client.get(f"/api/rfps/{rfp_id}").json()
        sec_id = detail["sections"][0]["id"]

        # PUT override
        put_res = self.client.put(
            f"/api/rfps/{rfp_id}/sections/{sec_id}",
            json={"classification": "pricing", "status": "resolved"},
        )
        self.assertEqual(put_res.status_code, 200)
        self.assertEqual(put_res.json()["classification"], "pricing")
        self.assertEqual(put_res.json()["status"], "resolved")

        # PATCH override
        patch_res = self.client.patch(
            f"/api/rfps/{rfp_id}/sections/{sec_id}",
            json={"classification": "strategic_decision"},
        )
        self.assertEqual(patch_res.status_code, 200)
        self.assertEqual(patch_res.json()["classification"], "strategic_decision")

    def test_23_put_rfp_outcome_and_status(self):
        """PUT /api/rfps/{id} updates RFP status and outcome feedback."""
        create_res = self.client.post("/api/rfps", json={"client_name": "Outcome Client"})
        rfp_id = create_res.json()["id"]

        update_res = self.client.put(
            f"/api/rfps/{rfp_id}",
            json={"status": "won", "outcome_feedback": "Awarded based on strong technical presentation."},
        )
        self.assertEqual(update_res.status_code, 200)
        detail = self.client.get(f"/api/rfps/{rfp_id}").json()
        self.assertEqual(detail["status"], "won")
        self.assertEqual(detail["outcome_feedback"], "Awarded based on strong technical presentation.")

    def test_24_invalid_inputs_and_404_handling(self):
        """Rejects empty client name, empty file uploads, and handles 404s."""
        # 422 for missing client_name in manual creation
        res_missing_client = self.client.post("/api/rfps", json={"value": 10000})
        self.assertEqual(res_missing_client.status_code, 422)

        # 400 for empty file upload
        res_empty_file = self.client.post(
            "/api/rfps/upload",
            data={"client_name": "Test"},
            files={"file": ("empty.docx", b"", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        )
        self.assertEqual(res_empty_file.status_code, 400)

        # 404 for non-existent RFP
        res_404 = self.client.get("/api/rfps/999999")
        self.assertEqual(res_404.status_code, 404)

    def test_25_add_and_delete_section(self):
        """POST /api/rfps/{id}/sections adds custom section, and DELETE removes it."""
        rfp = self.client.post("/api/rfps", json={"client_name": "Section Test Client"}).json()
        rfp_id = rfp["id"]

        add_res = self.client.post(
            f"/api/rfps/{rfp_id}/sections",
            json={
                "heading": "Custom Section A",
                "original_text": "Please provide custom answers.",
                "classification": "boilerplate",
            },
        )
        self.assertEqual(add_res.status_code, 201)
        sec = add_res.json()
        self.assertEqual(sec["heading"], "Custom Section A")
        sec_id = sec["id"]

        # Check section appears in RFP detail
        detail = self.client.get(f"/api/rfps/{rfp_id}").json()
        sec_ids = [s["id"] for s in detail["sections"]]
        self.assertIn(sec_id, sec_ids)

        # Delete the section
        del_res = self.client.delete(f"/api/rfps/{rfp_id}/sections/{sec_id}")
        self.assertEqual(del_res.status_code, 200)

        # Check section is gone
        detail2 = self.client.get(f"/api/rfps/{rfp_id}").json()
        sec_ids2 = [s["id"] for s in detail2["sections"]]
        self.assertNotIn(sec_id, sec_ids2)

    def test_26_manual_rfp_with_brief_and_budget(self):
        """POST /api/rfps with raw_details creates initial sections and tracks budget."""
        res = self.client.post(
            "/api/rfps",
            json={
                "client_name": "Budgeted Client",
                "value": 25000.0,
                "deadline": "2026-10-30",
                "budget_type": "under_budget",
                "budget_notes": "Client max ceiling £30k, target £25k",
                "raw_details": "## 1. Scope\nProvide website.\n\n## 2. Deliverables\nProvide design and code.",
            },
        )
        self.assertEqual(res.status_code, 201)
        data = res.json()
        self.assertEqual(data["budget_type"], "under_budget")
        self.assertEqual(data["deadline"], "2026-10-30")

        # Verify detail returned parsed sections
        detail = self.client.get(f"/api/rfps/{data['id']}").json()
        self.assertGreaterEqual(len(detail["sections"]), 2)
        self.assertEqual(detail["budget_type"], "under_budget")
        self.assertEqual(detail["budget_notes"], "Client max ceiling £30k, target £25k")

    def test_27_reorder_sections(self):
        """PUT /api/rfps/{id}/sections/reorder updates sort order of sections."""
        res = self.client.post(
            "/api/rfps",
            json={
                "client_name": "Reorder Test Client",
                "raw_details": "## Section Alpha\nAlpha text\n\n## Section Beta\nBeta text\n\n## Section Gamma\nGamma text",
            },
        )
        rfp_id = res.json()["id"]
        detail = self.client.get(f"/api/rfps/{rfp_id}").json()
        sections = detail["sections"]
        self.assertEqual(len(sections), 3)

        initial_ids = [s["id"] for s in sections]
        # Reverse order: Gamma, Beta, Alpha
        reversed_ids = list(reversed(initial_ids))

        reorder_res = self.client.put(
            f"/api/rfps/{rfp_id}/sections/reorder",
            json={"section_ids": reversed_ids},
        )
        self.assertEqual(reorder_res.status_code, 200)

        # Check detail returns sections in new order
        updated_detail = self.client.get(f"/api/rfps/{rfp_id}").json()
        updated_ids = [s["id"] for s in updated_detail["sections"]]
        self.assertEqual(updated_ids, reversed_ids)


if __name__ == "__main__":
    unittest.main()

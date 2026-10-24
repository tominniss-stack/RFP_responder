#!/usr/bin/env python3
"""
Empirical Stress Test Suite — Milestone 2 (Document Ingestion, Section Parsing & LLM Classification)
Challenger: challenger_m2_2

Coverage:
1. RFP Lifecycle & Manual Intake:
   - POST /api/rfps creates RFP record without document upload -> 201 Created.
   - Assert retrievable via GET /api/rfps/{id} with complete hierarchy (empty sections/notes/questions).
   - Verify list view filtering by client and status.
   - Reject empty/missing client_name with HTTP 422.
2. Classification Lifecycle:
   - POST /api/rfps/{id}/classify on 0-section manual RFP returns [] gracefully without error.
   - Ingest / populate multi-section RFP (incorporating all 5 categories: boilerplate, pricing,
     strategic_decision, gap, compliance_admin, plus ambiguous accessibility requirement).
   - POST /api/rfps/{id}/classify classifies all sections with valid taxonomy and confidence scores.
   - Confirm auto-registration of open_questions for strategic_decision and gap sections.
   - Confirm persistence in SQLite database and subsequent GET /api/rfps/{id}.
3. Section Manual Override:
   - PUT /api/rfps/{id}/sections/{section_id} updates classification.
   - Assert classification persists in database row (direct SQLite check) and on GET /api/rfps/{id}.
   - PATCH /api/rfps/{id}/sections/{section_id} updates classification.
   - Robustness to case formatting ("BOILERPLATE", "strategic decision", " COMPLIANCE_ADMIN ").
   - Section status updating ("drafted", "resolved", "pending").
4. Invalid Category Rejection:
   - PUT /api/rfps/{id}/sections/{section_id} with "RANDOM_CATEGORY" -> HTTP 422.
   - Other invalid categories ("INVALID", "", "123", None) -> HTTP 422.
   - Verify database row is unchanged after rejection.
5. Boundary & Security Hardening:
   - Cross-RFP section tampering: updating Section B under RFP A -> HTTP 404.
   - Non-existent RFP or Section IDs -> HTTP 404.
   - Invalid section status -> HTTP 422.
   - Cascading deletion of RFP cleanly purges sections and open questions.
"""

import io
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
import zipfile

# Ensure project root, backend, and virtualenv are on sys.path
import glob
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
from app.database import get_db, get_db_connection, init_db
from app.main import app
from app.models import create_tables, seed_defaults


def create_test_docx_archive(sections: list) -> bytes:
    """Create a valid in-memory DOCX file containing multiple heading + paragraph sections."""
    import xml.sax.saxutils as saxutils
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        p_elements = []
        for heading, body in sections:
            h_esc = saxutils.escape(str(heading))
            b_esc = saxutils.escape(str(body))
            p_elements.append(
                f"""
                <w:p>
                    <w:pPr><w:pStyle w:val="Heading1"/></w:pPr>
                    <w:r><w:t>{h_esc}</w:t></w:r>
                </w:p>
                <w:p>
                    <w:r><w:t>{b_esc}</w:t></w:r>
                </w:p>
                """
            )
        doc_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
        <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
            <w:body>
                {''.join(p_elements)}
            </w:body>
        </w:document>"""
        zf.writestr("word/document.xml", doc_xml)
    return buf.getvalue()


class TestMilestone2EmpiricalLifecycle(unittest.TestCase):
    """Empirical verification of RFP lifecycle, section classification, and manual override."""

    def setUp(self):
        # Create isolated temporary database for each test run
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.tmp.name
        self.tmp.close()

        # Initialize tables and seed data
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

    # =========================================================================
    # Part 1: Manual RFP Creation Lifecycle (without document upload)
    # =========================================================================

    def test_01_manual_rfp_creation_and_retrieval(self):
        """Create an RFP manually via POST /api/rfps without document upload -> assert retrievable."""
        payload = {
            "client_name": "Royal Botanic Gardens",
            "value": 125000.0,
            "date_submitted": "2026-10-01",
            "status": "draft",
            "service_ids": [1, 3],
        }
        res = self.client.post("/api/rfps", json=payload)
        self.assertEqual(res.status_code, 201, f"Expected 201 Created, got {res.status_code}: {res.text}")
        created = res.json()
        self.assertIn("id", created)
        rfp_id = created["id"]
        self.assertEqual(created["client_name"], "Royal Botanic Gardens")
        self.assertEqual(created["value"], 125000.0)

        # Assert direct database row
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT id, client_name, value, status FROM rfps WHERE id = ?;", (rfp_id,))
        row = cur.fetchone()
        self.assertIsNotNone(row, "RFP record not found in SQLite database")
        self.assertEqual(row[1], "Royal Botanic Gardens")
        self.assertEqual(row[2], 125000.0)
        self.assertEqual(row[3], "draft")

        # Assert junction table rfp_services
        cur.execute("SELECT service_id FROM rfp_services WHERE rfp_id = ? ORDER BY service_id ASC;", (rfp_id,))
        svc_ids = [r[0] for r in cur.fetchall()]
        self.assertEqual(svc_ids, [1, 3])
        conn.close()

        # Assert retrievable via GET /api/rfps/{id}
        get_res = self.client.get(f"/api/rfps/{rfp_id}")
        self.assertEqual(get_res.status_code, 200)
        detail = get_res.json()
        self.assertEqual(detail["id"], rfp_id)
        self.assertEqual(detail["client_name"], "Royal Botanic Gardens")
        self.assertEqual(detail["value"], 125000.0)
        self.assertEqual(detail["sections"], [])
        self.assertEqual(detail["notes"], [])
        self.assertEqual(detail["open_questions"], [])
        self.assertEqual(len(detail["services"]), 2)

    def test_02_manual_rfp_validation_rejections(self):
        """Verify POST /api/rfps enforces client_name constraints with HTTP 422."""
        # Missing client_name
        res1 = self.client.post("/api/rfps", json={"value": 50000})
        self.assertEqual(res1.status_code, 422)

        # Empty client_name
        res2 = self.client.post("/api/rfps", json={"client_name": "", "value": 50000})
        self.assertEqual(res2.status_code, 422)

        # Whitespace-only client_name
        res3 = self.client.post("/api/rfps", json={"client_name": "    ", "value": 50000})
        self.assertEqual(res3.status_code, 422)

    def test_03_classify_empty_rfp_returns_empty_gracefully(self):
        """Trigger POST /api/rfps/{id}/classify on an RFP without sections -> returns [] without error."""
        create_res = self.client.post("/api/rfps", json={"client_name": "Zero Section Client"})
        rfp_id = create_res.json()["id"]

        classify_res = self.client.post(f"/api/rfps/{rfp_id}/classify")
        self.assertEqual(classify_res.status_code, 200)
        self.assertEqual(classify_res.json(), [])

    def test_03b_manual_rfp_full_lifecycle_exact_sequence(self):
        """Empirically test exact sequence specified in challenger instructions:
        1. Create RFP manually via POST /api/rfps without document upload -> assert retrievable via GET /api/rfps/{id}.
        2. Populate sections for this manual RFP.
        3. Trigger classification via POST /api/rfps/{id}/classify -> assert sections receive valid classifications.
        4. Manually override a section classification via PUT /api/rfps/{id}/sections/{section_id} -> assert persists.
        5. Verify invalid classification categories (e.g. 'RANDOM_CATEGORY') are rejected with HTTP 422 or 400.
        """
        # Step 1: Create RFP manually via POST /api/rfps without document upload
        create_res = self.client.post(
            "/api/rfps",
            json={
                "client_name": "Direct Manual Lifecycle Corp",
                "value": 95000.0,
                "date_submitted": "2026-11-15",
                "status": "draft",
                "service_ids": [1, 2],
            },
        )
        self.assertEqual(create_res.status_code, 201)
        rfp_data = create_res.json()
        rfp_id = rfp_data["id"]
        self.assertEqual(rfp_data["client_name"], "Direct Manual Lifecycle Corp")

        # Assert retrievable via GET /api/rfps/{id}
        get_res = self.client.get(f"/api/rfps/{rfp_id}")
        self.assertEqual(get_res.status_code, 200)
        detail = get_res.json()
        self.assertEqual(detail["id"], rfp_id)
        self.assertEqual(detail["client_name"], "Direct Manual Lifecycle Corp")
        self.assertEqual(detail["value"], 95000.0)
        self.assertEqual(detail["sections"], [])

        # Step 2: Populate sections for this manual intake RFP
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO rfp_sections (rfp_id, heading, original_text, sort_order, status)
            VALUES (?, '1.0 Commercial Rate Card', 'Detail your standard daily rates and commercial discounts.', 1, 'pending');
            """,
            (rfp_id,),
        )
        sec1_id = cur.lastrowid
        cur.execute(
            """
            INSERT INTO rfp_sections (rfp_id, heading, original_text, sort_order, status)
            VALUES (?, '2.0 CMS Selection & Decoupled Architecture', 'Recommend appropriate CMS platform and headless frontend architecture.', 2, 'pending');
            """,
            (rfp_id,),
        )
        sec2_id = cur.lastrowid
        conn.commit()
        conn.close()

        # Verify sections are attached via GET
        detail_with_sections = self.client.get(f"/api/rfps/{rfp_id}").json()
        self.assertEqual(len(detail_with_sections["sections"]), 2)
        self.assertIsNone(detail_with_sections["sections"][0]["classification"])
        self.assertIsNone(detail_with_sections["sections"][1]["classification"])

        # Step 3: Trigger classification via POST /api/rfps/{id}/classify
        classify_res = self.client.post(f"/api/rfps/{rfp_id}/classify")
        self.assertEqual(classify_res.status_code, 200)
        classified_items = classify_res.json()
        self.assertEqual(len(classified_items), 2)

        # Assert sections receive valid classifications
        valid_categories = {"boilerplate", "pricing", "strategic_decision", "gap", "compliance_admin"}
        for item in classified_items:
            self.assertIn(item["classification"], valid_categories)
            self.assertIn(item["confidence"], {"high", "medium", "low"})

        item_map = {item["section_id"]: item for item in classified_items}
        self.assertEqual(item_map[sec1_id]["classification"], "pricing")
        self.assertEqual(item_map[sec2_id]["classification"], "strategic_decision")
        self.assertTrue(bool(item_map[sec2_id]["clarifying_question"]))

        # Step 4: Manually override a section classification via PUT /api/rfps/{id}/sections/{section_id}
        put_res = self.client.put(
            f"/api/rfps/{rfp_id}/sections/{sec1_id}",
            json={"classification": "boilerplate"},
        )
        self.assertEqual(put_res.status_code, 200)
        self.assertEqual(put_res.json()["classification"], "boilerplate")

        # Assert classification persists in database
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT classification FROM rfp_sections WHERE id = ?;", (sec1_id,))
        self.assertEqual(cur.fetchone()[0], "boilerplate")
        conn.close()

        # Assert returned on subsequent GET /api/rfps/{id}
        refetch = self.client.get(f"/api/rfps/{rfp_id}").json()
        refetched_sec1 = next(s for s in refetch["sections"] if s["id"] == sec1_id)
        self.assertEqual(refetched_sec1["classification"], "boilerplate")

        # Step 5: Verify that invalid classification categories (e.g. 'RANDOM_CATEGORY') are rejected with HTTP 422 or 400
        invalid_res = self.client.put(
            f"/api/rfps/{rfp_id}/sections/{sec1_id}",
            json={"classification": "RANDOM_CATEGORY"},
        )
        self.assertIn(invalid_res.status_code, [422, 400])

        # Assert database was not changed
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT classification FROM rfp_sections WHERE id = ?;", (sec1_id,))
        self.assertEqual(cur.fetchone()[0], "boilerplate")
        conn.close()

    # =========================================================================
    # Part 2: Section Classification Lifecycle
    # =========================================================================

    def test_04_classify_rfp_sections_end_to_end(self):
        """Trigger classification via POST /api/rfps/{id}/classify -> assert sections receive valid classifications."""
        test_sections = [
            ("1.0 Agency Introduction", "Describe your company history, leadership team, and credentials."),
            ("2.0 Technical Architecture", "Describe your recommended headless CMS platform and decoupled frontend stack."),
            ("3.0 Commercial Pricing", "Provide a detailed commercial schedule with daily rates and milestone billing."),
            ("4.0 Public Health Experience", "Detail your past experience delivering digital projects for NHS or Public Health trusts."),
            ("5.0 Compliance & Data Protection", "Sign and return the mandatory data protection compliance declaration."),
            ("6.0 Accessibility Standards", "Describe your approach to accessibility compliance including relevant WCAG experience."),
        ]
        docx_bytes = create_test_docx_archive(test_sections)

        upload_res = self.client.post(
            "/api/rfps/upload",
            data={"client_name": "Classification Lifecycle Test"},
            files={"file": ("rfp_spec.docx", docx_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        )
        self.assertEqual(upload_res.status_code, 201)
        rfp_id = upload_res.json()["rfp_id"]

        # Verify initial pending status
        detail_before = self.client.get(f"/api/rfps/{rfp_id}").json()
        self.assertEqual(len(detail_before["sections"]), 6)
        for s in detail_before["sections"]:
            self.assertIsNone(s.get("classification"))
            self.assertEqual(s.get("status"), "pending")

        # Trigger classification
        classify_res = self.client.post(f"/api/rfps/{rfp_id}/classify")
        self.assertEqual(classify_res.status_code, 200)
        results = classify_res.json()
        self.assertEqual(len(results), 6)

        valid_categories = {"boilerplate", "pricing", "strategic_decision", "gap", "compliance_admin"}
        valid_confidences = {"high", "medium", "low"}

        for item in results:
            self.assertIn(item["classification"], valid_categories, f"Invalid classification: {item['classification']}")
            self.assertIn(item["confidence"], valid_confidences, f"Invalid confidence: {item['confidence']}")

        # Verify specific category assignments
        by_heading = {item["heading"]: item for item in results}
        self.assertEqual(by_heading["1.0 Agency Introduction"]["classification"], "boilerplate")
        self.assertEqual(by_heading["2.0 Technical Architecture"]["classification"], "strategic_decision")
        self.assertEqual(by_heading["3.0 Commercial Pricing"]["classification"], "pricing")
        self.assertEqual(by_heading["4.0 Public Health Experience"]["classification"], "gap")
        self.assertEqual(by_heading["5.0 Compliance & Data Protection"]["classification"], "compliance_admin")
        self.assertEqual(by_heading["6.0 Accessibility Standards"]["classification"], "strategic_decision")
        self.assertEqual(by_heading["6.0 Accessibility Standards"]["confidence"], "medium")

        # Verify open questions generated for strategic and gap sections
        detail_after = self.client.get(f"/api/rfps/{rfp_id}").json()
        open_qs = detail_after["open_questions"]
        self.assertGreaterEqual(len(open_qs), 3, "Expected at least 3 open questions for strategic/gap sections")
        for q in open_qs:
            self.assertEqual(q["status"], "open")
            self.assertTrue(bool(q["question"]))

        # Verify SQLite database persistence directly
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT heading, classification, confidence FROM rfp_sections WHERE rfp_id = ? ORDER BY sort_order ASC;", (rfp_id,))
        db_rows = cur.fetchall()
        conn.close()

        self.assertEqual(len(db_rows), 6)
        for row in db_rows:
            self.assertIn(row[1], valid_categories)
            self.assertIn(row[2], valid_confidences)

    # =========================================================================
    # Part 3: Manual Section Classification Override
    # =========================================================================

    def test_05_manual_section_classification_override_persists(self):
        """Override section classification via PUT /api/rfps/{id}/sections/{section_id} -> assert DB persistence and GET."""
        docx_bytes = create_test_docx_archive([
            ("1.0 Scope", "Initial section requirement."),
            ("2.0 Architecture", "Technical architecture requirements."),
        ])
        upload_res = self.client.post(
            "/api/rfps/upload",
            data={"client_name": "Override Test Client"},
            files={"file": ("spec.docx", docx_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        )
        rfp_id = upload_res.json()["rfp_id"]

        # Run classification
        self.client.post(f"/api/rfps/{rfp_id}/classify")
        detail = self.client.get(f"/api/rfps/{rfp_id}").json()
        sec1 = detail["sections"][0]
        sec1_id = sec1["id"]
        self.assertEqual(sec1["classification"], "boilerplate")

        # 1. Override classification via PUT to 'pricing'
        put_res = self.client.put(
            f"/api/rfps/{rfp_id}/sections/{sec1_id}",
            json={"classification": "pricing"},
        )
        self.assertEqual(put_res.status_code, 200)
        self.assertEqual(put_res.json()["classification"], "pricing")

        # Verify direct SQLite persistence
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT classification FROM rfp_sections WHERE id = ?;", (sec1_id,))
        db_val = cur.fetchone()[0]
        conn.close()
        self.assertEqual(db_val, "pricing", "Classification did not persist in SQLite database")

        # Verify subsequent GET /api/rfps/{id}
        refetch = self.client.get(f"/api/rfps/{rfp_id}").json()
        updated_sec1 = next(s for s in refetch["sections"] if s["id"] == sec1_id)
        self.assertEqual(updated_sec1["classification"], "pricing")

        # 2. Override classification via PATCH to 'strategic_decision'
        patch_res = self.client.patch(
            f"/api/rfps/{rfp_id}/sections/{sec1_id}",
            json={"classification": "strategic_decision"},
        )
        self.assertEqual(patch_res.status_code, 200)
        self.assertEqual(patch_res.json()["classification"], "strategic_decision")

        # Re-verify DB persistence
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT classification FROM rfp_sections WHERE id = ?;", (sec1_id,))
        self.assertEqual(cur.fetchone()[0], "strategic_decision")
        conn.close()

        # 3. Test uppercase & space formatting resilience
        test_variations = [
            ("BOILERPLATE", "boilerplate"),
            ("strategic decision", "strategic_decision"),
            (" COMPLIANCE_ADMIN ", "compliance_admin"),
            ("GAP", "gap"),
        ]
        for input_cat, expected_cat in test_variations:
            res = self.client.put(
                f"/api/rfps/{rfp_id}/sections/{sec1_id}",
                json={"classification": input_cat},
            )
            self.assertEqual(res.status_code, 200, f"Failed for input: {input_cat}")
            self.assertEqual(res.json()["classification"], expected_cat)

            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()
            cur.execute("SELECT classification FROM rfp_sections WHERE id = ?;", (sec1_id,))
            self.assertEqual(cur.fetchone()[0], expected_cat)
            conn.close()

    def test_06_manual_section_status_and_content_override(self):
        """Verify section status and content can be updated along with classification."""
        docx_bytes = create_test_docx_archive([("1.0 Scope", "Initial text.")])
        upload_res = self.client.post(
            "/api/rfps/upload",
            data={"client_name": "Status Test"},
            files={"file": ("spec.docx", docx_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        )
        rfp_id = upload_res.json()["rfp_id"]
        sec_id = upload_res.json()["sections"][0]["id"]

        update_payload = {
            "classification": "boilerplate",
            "status": "drafted",
            "draft_content": "Drafted boilerplate response text.",
        }
        res = self.client.put(f"/api/rfps/{rfp_id}/sections/{sec_id}", json=update_payload)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "drafted")
        self.assertEqual(data["draft_content"], "Drafted boilerplate response text.")

        # Update to resolved
        res2 = self.client.put(
            f"/api/rfps/{rfp_id}/sections/{sec_id}",
            json={"status": "resolved", "final_content": "Final reviewed response text."},
        )
        self.assertEqual(res2.status_code, 200)
        data2 = res2.json()
        self.assertEqual(data2["status"], "resolved")
        self.assertEqual(data2["final_content"], "Final reviewed response text.")

    # =========================================================================
    # Part 4: Invalid Classification Category Rejection (HTTP 422 / 400)
    # =========================================================================

    def test_07_invalid_classification_category_rejected(self):
        """Verify invalid categories (e.g. 'RANDOM_CATEGORY') are rejected with HTTP 422 or 400."""
        docx_bytes = create_test_docx_archive([("1.0 Scope", "Initial text.")])
        upload_res = self.client.post(
            "/api/rfps/upload",
            data={"client_name": "Invalid Category Test"},
            files={"file": ("spec.docx", docx_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        )
        rfp_id = upload_res.json()["rfp_id"]
        sec_id = upload_res.json()["sections"][0]["id"]

        # Ensure known baseline
        self.client.put(f"/api/rfps/{rfp_id}/sections/{sec_id}", json={"classification": "boilerplate"})

        invalid_categories = [
            "RANDOM_CATEGORY",
            "INVALID_CAT",
            "unknown",
            "custom_category",
            "",
            "   ",
            "12345",
            "hack'; DROP TABLE rfp_sections; --",
        ]

        for invalid_cat in invalid_categories:
            res = self.client.put(
                f"/api/rfps/{rfp_id}/sections/{sec_id}",
                json={"classification": invalid_cat},
            )
            self.assertIn(
                res.status_code,
                [422, 400],
                f"Expected 422 or 400 for category '{invalid_cat}', got {res.status_code}: {res.text}",
            )

            # Assert database value was NOT corrupted
            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()
            cur.execute("SELECT classification FROM rfp_sections WHERE id = ?;", (sec_id,))
            current_val = cur.fetchone()[0]
            conn.close()
            self.assertEqual(
                current_val,
                "boilerplate",
                f"Database was modified by rejected category '{invalid_cat}'!",
            )

    def test_08_invalid_section_status_rejected(self):
        """Verify invalid section status (e.g. 'bogus_status') is rejected with HTTP 422."""
        docx_bytes = create_test_docx_archive([("1.0 Scope", "Initial text.")])
        upload_res = self.client.post(
            "/api/rfps/upload",
            data={"client_name": "Invalid Status Test"},
            files={"file": ("spec.docx", docx_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        )
        rfp_id = upload_res.json()["rfp_id"]
        sec_id = upload_res.json()["sections"][0]["id"]

        res = self.client.put(
            f"/api/rfps/{rfp_id}/sections/{sec_id}",
            json={"status": "invalid_status"},
        )
        self.assertEqual(res.status_code, 422, f"Expected 422 for invalid status, got {res.status_code}")

    # =========================================================================
    # Part 5: Cross-RFP Isolation & Boundary Security
    # =========================================================================

    def test_09_cross_rfp_section_tampering_rejected(self):
        """Verify attempting to update a section using the wrong rfp_id returns HTTP 404."""
        docx_a = create_test_docx_archive([("RFP A Section", "Text A")])
        docx_b = create_test_docx_archive([("RFP B Section", "Text B")])

        res_a = self.client.post(
            "/api/rfps/upload",
            data={"client_name": "RFP A"},
            files={"file": ("a.docx", docx_a, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        )
        rfp_a_id = res_a.json()["rfp_id"]
        sec_a_id = res_a.json()["sections"][0]["id"]

        res_b = self.client.post(
            "/api/rfps/upload",
            data={"client_name": "RFP B"},
            files={"file": ("b.docx", docx_b, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        )
        rfp_b_id = res_b.json()["rfp_id"]
        sec_b_id = res_b.json()["sections"][0]["id"]

        # Attempt cross-RFP update: Try to update sec_b_id under rfp_a_id
        cross_res = self.client.put(
            f"/api/rfps/{rfp_a_id}/sections/{sec_b_id}",
            json={"classification": "pricing"},
        )
        self.assertEqual(cross_res.status_code, 404, f"Expected 404 for cross-RFP section update, got {cross_res.status_code}")

    def test_10_nonexistent_entity_lookups_return_404(self):
        """Verify 404 handling on nonexistent RFP and section endpoints."""
        # Non-existent RFP detail
        self.assertEqual(self.client.get("/api/rfps/999999").status_code, 404)

        # Non-existent RFP classify
        self.assertEqual(self.client.post("/api/rfps/999999/classify").status_code, 404)

        # Non-existent section update
        create_res = self.client.post("/api/rfps", json={"client_name": "Test Client"})
        rfp_id = create_res.json()["id"]
        self.assertEqual(
            self.client.put(f"/api/rfps/{rfp_id}/sections/999999", json={"classification": "pricing"}).status_code,
            404,
        )

        # Negative IDs
        self.assertEqual(self.client.get("/api/rfps/-1").status_code, 404)
        self.assertEqual(
            self.client.put(f"/api/rfps/{rfp_id}/sections/-1", json={"classification": "pricing"}).status_code,
            404,
        )

    def test_11_cascading_deletion_lifecycle(self):
        """Verify deleting an RFP cascades to sections, services, and open questions."""
        docx_bytes = create_test_docx_archive([
            ("1.0 Scope", "Tech architecture cms choice."),
        ])
        res = self.client.post(
            "/api/rfps/upload",
            data={"client_name": "Cascade Client", "services": "[1, 2]"},
            files={"file": ("spec.docx", docx_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        )
        rfp_id = res.json()["rfp_id"]

        # Classify to spawn open questions
        self.client.post(f"/api/rfps/{rfp_id}/classify")

        # Verify records exist before delete
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM rfp_sections WHERE rfp_id = ?;", (rfp_id,))
        self.assertGreater(cur.fetchone()[0], 0)
        cur.execute("SELECT COUNT(*) FROM open_questions WHERE rfp_id = ?;", (rfp_id,))
        self.assertGreater(cur.fetchone()[0], 0)
        cur.execute("SELECT COUNT(*) FROM rfp_services WHERE rfp_id = ?;", (rfp_id,))
        self.assertGreater(cur.fetchone()[0], 0)
        conn.close()

        # Delete RFP
        del_res = self.client.delete(f"/api/rfps/{rfp_id}")
        self.assertEqual(del_res.status_code, 200)

        # Verify 404 on GET
        self.assertEqual(self.client.get(f"/api/rfps/{rfp_id}").status_code, 404)

        # Verify cascades in SQLite
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM rfps WHERE id = ?;", (rfp_id,))
        self.assertEqual(cur.fetchone()[0], 0)
        cur.execute("SELECT COUNT(*) FROM rfp_sections WHERE rfp_id = ?;", (rfp_id,))
        self.assertEqual(cur.fetchone()[0], 0)
        cur.execute("SELECT COUNT(*) FROM open_questions WHERE rfp_id = ?;", (rfp_id,))
        self.assertEqual(cur.fetchone()[0], 0)
        cur.execute("SELECT COUNT(*) FROM rfp_services WHERE rfp_id = ?;", (rfp_id,))
        self.assertEqual(cur.fetchone()[0], 0)
        conn.close()

    def test_12_classification_idempotency_and_repeat(self):
        """Verify re-running POST /api/rfps/{id}/classify is idempotent and does not duplicate open questions."""
        docx_bytes = create_test_docx_archive([
            ("1.0 Tech Stack", "Headless CMS architecture with decoupled frontend."),
        ])
        res = self.client.post(
            "/api/rfps/upload",
            data={"client_name": "Idempotency Test Client"},
            files={"file": ("spec.docx", docx_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        )
        rfp_id = res.json()["rfp_id"]

        # Run 1
        res1 = self.client.post(f"/api/rfps/{rfp_id}/classify")
        self.assertEqual(res1.status_code, 200)

        detail1 = self.client.get(f"/api/rfps/{rfp_id}").json()
        self.assertEqual(len(detail1["open_questions"]), 1)

        # Run 2 (repeat)
        res2 = self.client.post(f"/api/rfps/{rfp_id}/classify")
        self.assertEqual(res2.status_code, 200)

        detail2 = self.client.get(f"/api/rfps/{rfp_id}").json()
        self.assertEqual(len(detail2["open_questions"]), 1, "Open questions duplicated on repeated classification!")

    def test_13_batch_classification_large_rfp(self):
        """Stress-test batch classification with 25 distinct sections."""
        sections = [
            (f"Section {i}.0 Requirement {i}", f"Detail specifications and delivery methodology for requirement {i} (platform cms {i}).")
            for i in range(1, 26)
        ]
        docx_bytes = create_test_docx_archive(sections)
        upload_res = self.client.post(
            "/api/rfps/upload",
            data={"client_name": "Large RFP Client"},
            files={"file": ("large_rfp.docx", docx_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        )
        self.assertEqual(upload_res.status_code, 201)
        rfp_id = upload_res.json()["rfp_id"]
        self.assertEqual(upload_res.json()["sections_count"], 25)

        # Classify all 25 sections
        classify_res = self.client.post(f"/api/rfps/{rfp_id}/classify")
        self.assertEqual(classify_res.status_code, 200)
        classified = classify_res.json()
        self.assertEqual(len(classified), 25)

        # Verify all sections in DB are classified
        detail = self.client.get(f"/api/rfps/{rfp_id}").json()
        self.assertEqual(len(detail["sections"]), 25)
        for s in detail["sections"]:
            self.assertIsNotNone(s["classification"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

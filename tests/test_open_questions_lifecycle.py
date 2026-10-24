#!/usr/bin/env python3
"""
Empirical Adversarial Stress Test Suite — Milestone 4 (Challenger 2)
Scope: Hybrid AM Notes Lifecycle, Open Questions Tracking & Inline Resolution Loop, Section Status Lifecycle (F17, F20, F22)
Challenger: challenger_m4_2

Empirical Challenges:
1. Notes Lifecycle & Cross-RFP Isolation Stress (F17):
   - Whole-RFP note creation, retrieval, deletion returning {"deleted": note_id}.
   - Section-specific note creation, binding, and selective deletion.
   - Cross-RFP deletion isolation: deleting a note belonging to another RFP yields HTTP 404 and leaves note intact.
   - Cross-RFP section assignment rejection: creating note on RFP B bound to a section belonging to RFP A yields HTTP 404.
   - Boundary validations: empty note content, whitespace-only note content, non-existent RFP/note IDs return 422/404.
   - Referential integrity cascade: deleting an RFP deletes all associated notes in `rfp_notes`.
   - Massive payload resilience: notes with 50,000+ characters, Unicode, emojis, SQL injection, and XSS payloads.

2. Open Questions Tracking & Inline Resolution Loop (F20, F18, F19):
   - Gap marker detection: drafting a gap section produces `[MORE INFO REQUIRED: ...]` marker and status "drafted".
   - Auto-creation of open question: gap marker automatically registers open question with status "open".
   - Idempotency & duplicate prevention: re-generating without resolution does not produce duplicate open questions.
   - Inline resolution: resolving open question via PUT and PATCH `/api/rfps/{id}/open-questions/{q_id}`.
   - Re-generation verification: subsequent section generation incorporates resolution text verbatim, eliminates gap marker, transitions section status to "resolved", and logs provenance with source "notes".
   - Cross-RFP question isolation: attempting to view or resolve an open question belonging to another RFP yields HTTP 404.
   - Validation & edge cases: non-existent question/RFP IDs return 404; invalid status values return 422.
   - Referential integrity cascade: deleting an RFP deletes all associated open questions.

3. Section Status & Draft Editing Lifecycle (F21, F22):
   - Direct draft and final content editing via PUT and PATCH `/api/rfps/{id}/sections/{section_id}`.
   - Status workflow transitions: pending -> drafted -> resolved -> pending -> drafted.
   - Status validation boundaries: invalid status strings ("in_progress", "done", "waiting", "") rejected with HTTP 422.
   - Case-insensitive status normalization (" PENDING ", " RESOLVED ") accepted.
   - Classification validation boundaries: valid classifications accepted, invalid rejected with HTTP 422.
   - Cross-RFP section editing isolation: modifying a section from another RFP yields HTTP 404.

4. End-to-End Hybrid Synthesis & Resolution Pipeline:
   - AM note section-specific override precedence over whole-RFP notes.
   - Full lifecycle from gap creation to open question resolution, section draft regeneration, and zero-comment mock export.
"""

import glob
import os
import sqlite3
import sys
import tempfile
import time
import unittest
from pathlib import Path

# Ensure backend root and project root are in python path
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
from app.database import get_db, get_db_connection
from app.models import create_tables, seed_defaults
from app.services.vector_store import get_vector_store, sync_vector_store_from_db


class BaseM4ChallengerTestCase(unittest.TestCase):
    """Isolated test environment with freshly initialized SQLite database and vector store."""

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.tmp.name
        self.tmp.close()

        self.conn = get_db_connection(self.db_path)
        create_tables(self.conn)
        seed_defaults(self.conn)
        self.conn.commit()

        vs = get_vector_store()
        vs.reset()
        sync_vector_store_from_db(self.conn)

        def override_get_db():
            c = get_db_connection(self.db_path)
            try:
                yield c
                c.commit()
            finally:
                c.close()

        app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(app, raise_server_exceptions=False)

    def tearDown(self):
        app.dependency_overrides.clear()
        self.conn.close()
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def create_test_rfp(self, client_name="Acme Health Trust", value=125000):
        """Helper to create an RFP record."""
        res = self.client.post("/api/rfps", json={"client_name": client_name, "value": value})
        self.assertEqual(res.status_code, 201)
        return res.json()["id"]

    def create_test_section(self, rfp_id, heading, original_text, classification="boilerplate", sort_order=1):
        """Helper to insert an RFP section record."""
        cur = self.conn.execute(
            """
            INSERT INTO rfp_sections (rfp_id, heading, original_text, classification, confidence, sort_order, status)
            VALUES (?, ?, ?, ?, 'high', ?, 'pending');
            """,
            (rfp_id, heading, original_text, classification, sort_order),
        )
        self.conn.commit()
        return cur.lastrowid


class TestNotesLifecycleAndCrossRFPIsolation(BaseM4ChallengerTestCase):
    """Adversarially challenge Hybrid AM Notes CRUD, cross-RFP isolation, cascade deletion, and boundaries (F17)."""

    def test_01_whole_rfp_notes_crud_lifecycle(self):
        """Create, list, and delete whole-RFP notes (section_id=None)."""
        rfp_id = self.create_test_rfp("Whole Notes Client")

        # 1. Create whole-RFP note with explicit None
        res1 = self.client.post(
            f"/api/rfps/{rfp_id}/notes",
            json={"raw_content": "Whole-RFP strategic directive: Focus on ISO 27001.", "section_id": None},
        )
        self.assertEqual(res1.status_code, 201)
        n1 = res1.json()
        self.assertIsNotNone(n1["id"])
        self.assertIsNone(n1["section_id"])
        self.assertEqual(n1["rfp_id"], rfp_id)
        self.assertIn("ISO 27001", n1["raw_content"])

        # 2. Create second whole-RFP note omitting section_id
        res2 = self.client.post(
            f"/api/rfps/{rfp_id}/notes",
            json={"raw_content": "Whole-RFP commercial directive: Target 10% gross margin."},
        )
        self.assertEqual(res2.status_code, 201)
        n2 = res2.json()
        self.assertIsNone(n2["section_id"])

        # 3. List notes: must return both in order
        list_res = self.client.get(f"/api/rfps/{rfp_id}/notes")
        self.assertEqual(list_res.status_code, 200)
        notes = list_res.json()
        self.assertEqual(len(notes), 2)
        self.assertEqual([n["id"] for n in notes], [n1["id"], n2["id"]])

        # 4. Delete first note: assert contract {"deleted": note_id}
        del_res = self.client.delete(f"/api/rfps/{rfp_id}/notes/{n1['id']}")
        self.assertEqual(del_res.status_code, 200)
        self.assertEqual(del_res.json(), {"deleted": n1["id"]})

        # 5. Verify note 1 is gone, note 2 remains
        list_after = self.client.get(f"/api/rfps/{rfp_id}/notes").json()
        self.assertEqual(len(list_after), 1)
        self.assertEqual(list_after[0]["id"], n2["id"])

    def test_02_section_specific_notes_crud_and_selective_deletion(self):
        """Create section-specific notes across sections and verify selective deletion."""
        rfp_id = self.create_test_rfp("Section Notes Client")
        sec1_id = self.create_test_section(rfp_id, "Sec 1", "Section 1 text", "boilerplate", 1)
        sec2_id = self.create_test_section(rfp_id, "Sec 2", "Section 2 text", "pricing", 2)

        # Create note for sec 1
        res_n1 = self.client.post(
            f"/api/rfps/{rfp_id}/notes",
            json={"raw_content": "Note for section 1", "section_id": sec1_id},
        )
        self.assertEqual(res_n1.status_code, 201)
        n1 = res_n1.json()
        self.assertEqual(n1["section_id"], sec1_id)

        # Create note for sec 2
        res_n2 = self.client.post(
            f"/api/rfps/{rfp_id}/notes",
            json={"raw_content": "Note for section 2", "section_id": sec2_id},
        )
        self.assertEqual(res_n2.status_code, 201)
        n2 = res_n2.json()
        self.assertEqual(n2["section_id"], sec2_id)

        # Delete note 1
        del_res = self.client.delete(f"/api/rfps/{rfp_id}/notes/{n1['id']}")
        self.assertEqual(del_res.status_code, 200)
        self.assertEqual(del_res.json(), {"deleted": n1["id"]})

        # Sec 2 note must remain
        cur_notes = self.client.get(f"/api/rfps/{rfp_id}/notes").json()
        self.assertEqual(len(cur_notes), 1)
        self.assertEqual(cur_notes[0]["id"], n2["id"])
        self.assertEqual(cur_notes[0]["section_id"], sec2_id)

    def test_03_cross_rfp_note_deletion_isolation(self):
        """Reject deleting note belonging to another RFP with HTTP 404; assert note intact."""
        rfp_a = self.create_test_rfp("Tenant A")
        rfp_b = self.create_test_rfp("Tenant B")

        # Create note on RFP A
        note_a = self.client.post(
            f"/api/rfps/{rfp_a}/notes",
            json={"raw_content": "Secret credentials for Tenant A"},
        ).json()
        note_a_id = note_a["id"]

        # Attempt to delete note A via RFP B
        del_res = self.client.delete(f"/api/rfps/{rfp_b}/notes/{note_a_id}")
        self.assertEqual(del_res.status_code, 404)
        self.assertIn("Note not found for this RFP", del_res.json().get("detail", ""))

        # Verify note A is still present on RFP A
        notes_a = self.client.get(f"/api/rfps/{rfp_a}/notes").json()
        self.assertTrue(any(n["id"] == note_a_id for n in notes_a))

    def test_04_cross_rfp_section_note_assignment_rejection(self):
        """Reject creating note with section_id belonging to another RFP with HTTP 404."""
        rfp_a = self.create_test_rfp("Tenant A")
        rfp_b = self.create_test_rfp("Tenant B")
        sec_a_id = self.create_test_section(rfp_a, "Sec A", "Original text A", "boilerplate", 1)

        # Attempt to attach note to sec_a_id via rfp_b
        res = self.client.post(
            f"/api/rfps/{rfp_b}/notes",
            json={"raw_content": "Malicious cross-assignment", "section_id": sec_a_id},
        )
        self.assertEqual(res.status_code, 404)
        self.assertIn("Section not found for this RFP", res.json().get("detail", ""))

        # Verify no note was created in database
        cur = self.conn.execute("SELECT COUNT(*) as c FROM rfp_notes WHERE raw_content = 'Malicious cross-assignment';")
        self.assertEqual(cur.fetchone()["c"], 0)

    def test_05_note_validation_boundary_conditions(self):
        """Adversarial stress on note validation: blank, whitespace, non-existent targets, payloads."""
        rfp_id = self.create_test_rfp("Boundary Client")

        # 1. Empty string
        res_empty = self.client.post(f"/api/rfps/{rfp_id}/notes", json={"raw_content": ""})
        self.assertEqual(res_empty.status_code, 422)

        # 2. Whitespace only with tabs and newlines
        res_ws = self.client.post(f"/api/rfps/{rfp_id}/notes", json={"raw_content": "  \t \n \r  "})
        self.assertEqual(res_ws.status_code, 422)

        # 3. Non-existent RFP ID
        res_no_rfp = self.client.post("/api/rfps/999999/notes", json={"raw_content": "Valid note"})
        self.assertEqual(res_no_rfp.status_code, 404)

        # 4. Non-existent section ID on valid RFP
        res_no_sec = self.client.post(f"/api/rfps/{rfp_id}/notes", json={"raw_content": "Valid", "section_id": 999999})
        self.assertEqual(res_no_sec.status_code, 404)

        # 5. Non-existent note ID deletion
        res_no_note = self.client.delete(f"/api/rfps/{rfp_id}/notes/999999")
        self.assertEqual(res_no_note.status_code, 404)

        # 6. Double deletion of same note
        created = self.client.post(f"/api/rfps/{rfp_id}/notes", json={"raw_content": "Ephemeral"}).json()
        note_id = created["id"]
        del1 = self.client.delete(f"/api/rfps/{rfp_id}/notes/{note_id}")
        self.assertEqual(del1.status_code, 200)
        del2 = self.client.delete(f"/api/rfps/{rfp_id}/notes/{note_id}")
        self.assertEqual(del2.status_code, 404)

        # 7. Extremely large payload (50,000 chars)
        huge_text = "Account transcript excerpt: " + ("Comprehensive client requirement details. " * 1250)
        self.assertGreater(len(huge_text), 50000)
        res_huge = self.client.post(f"/api/rfps/{rfp_id}/notes", json={"raw_content": huge_text})
        self.assertEqual(res_huge.status_code, 201)
        self.assertEqual(res_huge.json()["raw_content"], huge_text.strip())

        # 8. Special characters, unicode, emoji, markdown, HTML, SQL injection patterns
        adversarial_text = (
            "🚀 High-priority note: **Statamic** 4.x & Next.js integration.\n"
            "<script>alert('xss');</script>\n"
            "'; DROP TABLE rfp_notes; -- \n"
            "日本語 & accents: éàçüöñ"
        )
        res_adv = self.client.post(f"/api/rfps/{rfp_id}/notes", json={"raw_content": adversarial_text})
        self.assertEqual(res_adv.status_code, 201)
        saved = self.client.get(f"/api/rfps/{rfp_id}/notes").json()
        adv_saved = next(n for n in saved if n["id"] == res_adv.json()["id"])
        self.assertEqual(adv_saved["raw_content"], adversarial_text.strip())

    def test_06_rfp_cascade_delete_removes_notes(self):
        """Deleting an RFP cascades to delete all attached whole-RFP and per-section notes."""
        rfp_id = self.create_test_rfp("Cascade Notes Client")
        sec_id = self.create_test_section(rfp_id, "Sec 1", "Section text", "boilerplate", 1)

        # Insert 3 whole-RFP notes and 3 section-specific notes
        for i in range(3):
            self.client.post(f"/api/rfps/{rfp_id}/notes", json={"raw_content": f"Whole note {i}"})
            self.client.post(f"/api/rfps/{rfp_id}/notes", json={"raw_content": f"Section note {i}", "section_id": sec_id})

        # Confirm 6 notes exist in DB for this rfp
        cur = self.conn.execute("SELECT COUNT(*) as c FROM rfp_notes WHERE rfp_id = ?;", (rfp_id,))
        self.assertEqual(cur.fetchone()["c"], 6)

        # Delete RFP
        del_rfp_res = self.client.delete(f"/api/rfps/{rfp_id}")
        self.assertEqual(del_rfp_res.status_code, 200)
        self.assertEqual(del_rfp_res.json(), {"deleted": rfp_id})

        # Confirm 0 notes exist in rfp_notes for this rfp_id
        cur_after = self.conn.execute("SELECT COUNT(*) as c FROM rfp_notes WHERE rfp_id = ?;", (rfp_id,))
        self.assertEqual(cur_after.fetchone()["c"], 0)


class TestOpenQuestionsInlineResolutionLoop(BaseM4ChallengerTestCase):
    """Adversarially stress-test Open Questions generation, inline resolution, and regeneration loop (F20, F18, F19)."""

    def test_07_draft_generation_gap_marker_and_open_question_auto_creation(self):
        """Drafting a gap section produces [MORE INFO REQUIRED: ...] and auto-registers open question."""
        rfp_id = self.create_test_rfp("NHS Trust")
        sec_id = self.create_test_section(
            rfp_id,
            "4.0 Security & ISO Certification",
            "Detail compliance with ISO 27001 and NHS Digital Cyber Security Standards.",
            classification="gap",
            sort_order=1,
        )

        # Generate draft
        gen_res = self.client.post(f"/api/rfps/{rfp_id}/sections/{sec_id}/generate")
        self.assertEqual(gen_res.status_code, 200)
        data = gen_res.json()

        # Assert gap marker in draft_content
        self.assertIn("[MORE INFO REQUIRED:", data["draft_content"])
        self.assertEqual(data["status"], "drafted")

        # Assert provenance has source 'gap'
        gap_prov = next((p for p in data["provenance"] if p["source"] == "gap"), None)
        self.assertIsNotNone(gap_prov)
        self.assertIn("Identified information gap", gap_prov["reference"])

        # Assert open question registered in open_questions table
        q_res = self.client.get(f"/api/rfps/{rfp_id}/open-questions")
        self.assertEqual(q_res.status_code, 200)
        questions = q_res.json()
        self.assertEqual(len(questions), 1)
        q = questions[0]
        self.assertEqual(q["rfp_id"], rfp_id)
        self.assertEqual(q["section_id"], sec_id)
        self.assertEqual(q["status"], "open")
        self.assertIn("Describe specific past experience", q["question"])

    def test_08_draft_regeneration_idempotency_no_duplicate_questions(self):
        """Re-generating a gap section without resolution does not produce duplicate open questions."""
        rfp_id = self.create_test_rfp("Duplicate Question Test")
        sec_id = self.create_test_section(
            rfp_id,
            "Section Gap",
            "Missing capability requirement.",
            classification="gap",
            sort_order=1,
        )

        # Generate draft 3 times consecutively
        for _ in range(3):
            res = self.client.post(f"/api/rfps/{rfp_id}/sections/{sec_id}/generate")
            self.assertEqual(res.status_code, 200)

        # Assert exactly 1 open question exists, not 3
        questions = self.client.get(f"/api/rfps/{rfp_id}/open-questions").json()
        self.assertEqual(len(questions), 1)

    def test_09_open_question_inline_resolution_and_patch(self):
        """Resolve question via PUT and PATCH; verify persistence and schema."""
        rfp_id = self.create_test_rfp("Resolution Client")
        sec_id = self.create_test_section(
            rfp_id,
            "Security Requirements",
            "Detail security accreditations.",
            classification="gap",
            sort_order=1,
        )

        self.client.post(f"/api/rfps/{rfp_id}/sections/{sec_id}/generate")
        questions = self.client.get(f"/api/rfps/{rfp_id}/open-questions").json()
        q_id = questions[0]["id"]

        # 1. Resolve via PUT
        res_text = "Another Marketing Agency holds ISO 27001:2022 Certificate #IS-78901 and Cyber Essentials Plus."
        put_res = self.client.put(
            f"/api/rfps/{rfp_id}/open-questions/{q_id}",
            json={"resolution": res_text, "status": "resolved"},
        )
        self.assertEqual(put_res.status_code, 200)
        q_updated = put_res.json()
        self.assertEqual(q_updated["status"], "resolved")
        self.assertEqual(q_updated["resolution"], res_text)

        # 2. Update resolution via PATCH
        patch_text = res_text + " Valid through November 2027."
        patch_res = self.client.patch(
            f"/api/rfps/{rfp_id}/open-questions/{q_id}",
            json={"resolution": patch_text},
        )
        self.assertEqual(patch_res.status_code, 200)
        self.assertEqual(patch_res.json()["resolution"], patch_text)

        # Confirm in DB
        db_q = self.client.get(f"/api/rfps/{rfp_id}/open-questions").json()[0]
        self.assertEqual(db_q["resolution"], patch_text)
        self.assertEqual(db_q["status"], "resolved")

    def test_10_draft_regeneration_incorporates_resolution_and_transitions_status(self):
        """After resolving open question, regenerating section incorporates resolution, eliminates gap marker, and transitions status to resolved."""
        rfp_id = self.create_test_rfp("Regeneration Verification Client")
        sec_id = self.create_test_section(
            rfp_id,
            "NHS Compliance",
            "Provide evidence of NHS Data Security and Protection Toolkit compliance.",
            classification="gap",
            sort_order=1,
        )

        # 1. Initial generation -> gap marker present, status drafted
        gen1 = self.client.post(f"/api/rfps/{rfp_id}/sections/{sec_id}/generate").json()
        self.assertIn("[MORE INFO REQUIRED:", gen1["draft_content"])
        self.assertEqual(gen1["status"], "drafted")

        # 2. Resolve question
        q = self.client.get(f"/api/rfps/{rfp_id}/open-questions").json()[0]
        resolution = "Another Marketing Agency achieves 'Standards Exceeded' on NHS DSPT (ODS Code: 8J921)."
        self.client.put(
            f"/api/rfps/{rfp_id}/open-questions/{q['id']}",
            json={"resolution": resolution, "status": "resolved"},
        )

        # 3. Regenerate section
        gen2_res = self.client.post(f"/api/rfps/{rfp_id}/sections/{sec_id}/generate")
        self.assertEqual(gen2_res.status_code, 200)
        gen2 = gen2_res.json()

        # Assert resolution text is incorporated
        self.assertIn(resolution, gen2["draft_content"])

        # Assert gap marker is completely removed
        self.assertNotIn("[MORE INFO REQUIRED:", gen2["draft_content"])

        # Assert section status is now resolved
        self.assertEqual(gen2["status"], "resolved")

        # Assert provenance has notes item citing the open question
        q_prov = next((p for p in gen2["provenance"] if p["source"] == "notes" and str(q["id"]) in p["reference"]), None)
        self.assertIsNotNone(q_prov)
        self.assertEqual(q_prov["text"], resolution)

    def test_11_cross_rfp_open_question_isolation(self):
        """Reject viewing or resolving open questions across RFPs with HTTP 404."""
        rfp_a = self.create_test_rfp("RFP A")
        rfp_b = self.create_test_rfp("RFP B")
        sec_a = self.create_test_section(rfp_a, "Sec A Gap", "Requirement A", "gap", 1)

        # Generate question on RFP A
        self.client.post(f"/api/rfps/{rfp_a}/sections/{sec_a}/generate")
        q_a = self.client.get(f"/api/rfps/{rfp_a}/open-questions").json()[0]
        q_a_id = q_a["id"]

        # RFP B open questions listing must be empty
        qs_b = self.client.get(f"/api/rfps/{rfp_b}/open-questions").json()
        self.assertEqual(len(qs_b), 0)

        # Attempt to resolve q_a via RFP B
        put_cross = self.client.put(
            f"/api/rfps/{rfp_b}/open-questions/{q_a_id}",
            json={"resolution": "Cross-tenant intrusion attempt", "status": "resolved"},
        )
        self.assertEqual(put_cross.status_code, 404)

        # Verify q_a is still open on RFP A
        q_a_check = self.client.get(f"/api/rfps/{rfp_a}/open-questions").json()[0]
        self.assertEqual(q_a_check["status"], "open")
        self.assertIsNone(q_a_check["resolution"])

    def test_12a_open_questions_nonexistent_ids_return_404(self):
        """Non-existent RFP ID or question ID returns HTTP 404."""
        rfp_id = self.create_test_rfp("Validation RFP")

        # Non-existent RFP ID
        res_no_rfp = self.client.get("/api/rfps/999999/open-questions")
        self.assertEqual(res_no_rfp.status_code, 404)

        # Non-existent question ID
        res_no_q = self.client.put(
            f"/api/rfps/{rfp_id}/open-questions/999999",
            json={"resolution": "Valid text", "status": "resolved"},
        )
        self.assertEqual(res_no_q.status_code, 404)

    def test_12b_open_questions_invalid_status_crashes_with_500_instead_of_422(self):
        """CRITICAL DEFECT TEST: PUT /api/rfps/{id}/open-questions/{q_id} with invalid status crashes SQLite with HTTP 500 instead of returning HTTP 422."""
        rfp_id = self.create_test_rfp("Invalid Status RFP")
        sec_id = self.create_test_section(rfp_id, "Sec Gap", "Missing info", "gap", 1)
        self.client.post(f"/api/rfps/{rfp_id}/sections/{sec_id}/generate")
        q_id = self.client.get(f"/api/rfps/{rfp_id}/open-questions").json()[0]["id"]

        res_inv_status = self.client.put(
            f"/api/rfps/{rfp_id}/open-questions/{q_id}",
            json={"resolution": "Valid text", "status": "invalid_enum_status"},
        )
        self.assertEqual(
            res_inv_status.status_code,
            422,
            f"DEFECT: Endpoint returned HTTP {res_inv_status.status_code} (SQLite IntegrityError 500 crash) instead of HTTP 422 Unprocessable Entity!",
        )

    def test_12c_open_questions_blank_resolution_creates_desynchronized_zombie_state(self):
        """CRITICAL DEFECT TEST: Resolving open question with whitespace/blank text is accepted with HTTP 200, creating a desynchronized state where gap marker persists but open question is marked resolved."""
        rfp_id = self.create_test_rfp("Blank Resolution RFP")
        sec_id = self.create_test_section(rfp_id, "Sec Gap", "Missing info", "gap", 1)
        self.client.post(f"/api/rfps/{rfp_id}/sections/{sec_id}/generate")
        q_id = self.client.get(f"/api/rfps/{rfp_id}/open-questions").json()[0]["id"]

        # Attempt to resolve question with whitespace
        res_blank = self.client.put(
            f"/api/rfps/{rfp_id}/open-questions/{q_id}",
            json={"resolution": "   \n\t  ", "status": "resolved"},
        )
        self.assertEqual(
            res_blank.status_code,
            422,
            f"DEFECT: Endpoint accepted blank/whitespace resolution with HTTP {res_blank.status_code} instead of rejecting with HTTP 422!",
        )

    def test_13_rfp_cascade_delete_removes_open_questions(self):
        """Deleting an RFP cascades to remove all associated open questions."""
        rfp_id = self.create_test_rfp("Cascade Questions Client")
        sec_id = self.create_test_section(rfp_id, "Sec Gap", "Missing info", "gap", 1)
        self.client.post(f"/api/rfps/{rfp_id}/sections/{sec_id}/generate")

        # Confirm 1 question exists in DB
        cur = self.conn.execute("SELECT COUNT(*) as c FROM open_questions WHERE rfp_id = ?;", (rfp_id,))
        self.assertEqual(cur.fetchone()["c"], 1)

        # Delete RFP
        self.client.delete(f"/api/rfps/{rfp_id}")

        # Confirm 0 questions exist in open_questions table
        cur_after = self.conn.execute("SELECT COUNT(*) as c FROM open_questions WHERE rfp_id = ?;", (rfp_id,))
        self.assertEqual(cur_after.fetchone()["c"], 0)


class TestSectionStatusAndDraftEditing(BaseM4ChallengerTestCase):
    """Adversarially test section draft/final content editing, status transitions, and boundary checks (F21, F22)."""

    def test_14_direct_draft_and_final_content_editing(self):
        """Directly edit draft_content and final_content via PUT and PATCH."""
        rfp_id = self.create_test_rfp("Editing Client")
        sec_id = self.create_test_section(rfp_id, "Arch 1.0", "Technical requirement", "strategic", 1)

        # 1. Update draft_content via PUT
        draft_text = "Custom drafted architecture proposal with Statamic and GraphQL."
        res1 = self.client.put(
            f"/api/rfps/{rfp_id}/sections/{sec_id}",
            json={"draft_content": draft_text, "status": "drafted"},
        )
        self.assertEqual(res1.status_code, 200)
        self.assertEqual(res1.json()["draft_content"], draft_text)
        self.assertEqual(res1.json()["status"], "drafted")

        # 2. Update final_content via PATCH without wiping draft_content
        final_text = "Approved final response after client review."
        res2 = self.client.patch(
            f"/api/rfps/{rfp_id}/sections/{sec_id}",
            json={"final_content": final_text, "status": "resolved"},
        )
        self.assertEqual(res2.status_code, 200)
        self.assertEqual(res2.json()["final_content"], final_text)
        self.assertEqual(res2.json()["draft_content"], draft_text)
        self.assertEqual(res2.json()["status"], "resolved")

        # 3. Verify in full RFP get
        rfp_full = self.client.get(f"/api/rfps/{rfp_id}").json()
        sec = next(s for s in rfp_full["sections"] if s["id"] == sec_id)
        self.assertEqual(sec["draft_content"], draft_text)
        self.assertEqual(sec["final_content"], final_text)
        self.assertEqual(sec["status"], "resolved")

    def test_15_section_status_workflow_transitions(self):
        """Verify status progression: pending -> drafted -> resolved -> pending."""
        rfp_id = self.create_test_rfp("Status Workflow Client")
        sec_id = self.create_test_section(rfp_id, "Sec 1", "Req", "boilerplate", 1)

        # Initial status is pending
        sec0 = self.conn.execute("SELECT status FROM rfp_sections WHERE id = ?;", (sec_id,)).fetchone()
        self.assertEqual(sec0["status"], "pending")

        # Transition to drafted
        res1 = self.client.patch(f"/api/rfps/{rfp_id}/sections/{sec_id}", json={"status": "drafted"})
        self.assertEqual(res1.status_code, 200)
        self.assertEqual(res1.json()["status"], "drafted")

        # Transition to resolved
        res2 = self.client.patch(f"/api/rfps/{rfp_id}/sections/{sec_id}", json={"status": "resolved"})
        self.assertEqual(res2.status_code, 200)
        self.assertEqual(res2.json()["status"], "resolved")

        # Transition back to pending (e.g. revision required)
        res3 = self.client.patch(f"/api/rfps/{rfp_id}/sections/{sec_id}", json={"status": "pending"})
        self.assertEqual(res3.status_code, 200)
        self.assertEqual(res3.json()["status"], "pending")

    def test_16_section_status_validation_boundaries(self):
        """Reject invalid section status values with 422; accept case-insensitive / trimmed valid statuses."""
        rfp_id = self.create_test_rfp("Status Boundary Client")
        sec_id = self.create_test_section(rfp_id, "Sec 1", "Req", "boilerplate", 1)

        # 1. Invalid status strings
        invalid_statuses = ["in_progress", "done", "approved", "waiting", "", "completed", "123", "closed"]
        for bad_status in invalid_statuses:
            res = self.client.put(
                f"/api/rfps/{rfp_id}/sections/{sec_id}",
                json={"status": bad_status},
            )
            self.assertEqual(res.status_code, 422, f"Expected 422 for invalid status '{bad_status}'")

        # 2. Case-insensitive and trimmed valid statuses
        valid_variations = [(" DRAFTED ", "drafted"), ("RESOLVED", "resolved"), ("  Pending  ", "pending")]
        for input_status, expected_normalized in valid_variations:
            res = self.client.patch(
                f"/api/rfps/{rfp_id}/sections/{sec_id}",
                json={"status": input_status},
            )
            self.assertEqual(res.status_code, 200)
            self.assertEqual(res.json()["status"], expected_normalized)

    def test_17_section_classification_manual_override_and_validation(self):
        """Verify manual override allows all 6 valid classifications and rejects invalid ones with 422."""
        rfp_id = self.create_test_rfp("Classification Client")
        sec_id = self.create_test_section(rfp_id, "Sec 1", "Req", "boilerplate", 1)

        valid_categories = [
            "boilerplate",
            "pricing",
            "strategic_decision",
            "strategic",
            "gap",
            "compliance_admin",
        ]
        for cat in valid_categories:
            res = self.client.patch(
                f"/api/rfps/{rfp_id}/sections/{sec_id}",
                json={"classification": cat},
            )
            self.assertEqual(res.status_code, 200)
            self.assertEqual(res.json()["classification"], cat)

        # Invalid classification
        res_bad = self.client.patch(
            f"/api/rfps/{rfp_id}/sections/{sec_id}",
            json={"classification": "unsupported_classification_name"},
        )
        self.assertEqual(res_bad.status_code, 422)

    def test_18_cross_rfp_section_editing_isolation(self):
        """Reject editing or generating a section belonging to another RFP with HTTP 404."""
        rfp_a = self.create_test_rfp("RFP A")
        rfp_b = self.create_test_rfp("RFP B")
        sec_a = self.create_test_section(rfp_a, "Sec A", "Req A", "boilerplate", 1)

        # Attempt to edit sec_a via rfp_b
        res_edit = self.client.put(
            f"/api/rfps/{rfp_b}/sections/{sec_a}",
            json={"draft_content": "Unauthorized modification attempt"},
        )
        self.assertEqual(res_edit.status_code, 404)

        # Attempt to generate sec_a via rfp_b
        res_gen = self.client.post(f"/api/rfps/{rfp_b}/sections/{sec_a}/generate")
        self.assertEqual(res_gen.status_code, 404)

        # Non-existent section on valid RFP
        res_no_sec = self.client.put(
            f"/api/rfps/{rfp_a}/sections/999999",
            json={"draft_content": "Ghost section"},
        )
        self.assertEqual(res_no_sec.status_code, 404)


class TestComplexSynthesisAndResolutionLoopPipeline(BaseM4ChallengerTestCase):
    """Adversarially test full multi-source notes precedence and export comment resolution."""

    def test_19_hybrid_notes_multi_section_override_matrix(self):
        """Test hybrid notes matrix: section notes take precedence over whole-RFP notes per section."""
        rfp_id = self.create_test_rfp("Synthesis Matrix Client")

        # 3 sections: pricing, boilerplate, strategic
        sec_p = self.create_test_section(rfp_id, "Pricing", "Rates for Statamic dev", "pricing", 1)
        sec_b = self.create_test_section(rfp_id, "Boilerplate", "Company credentials", "boilerplate", 2)
        sec_s = self.create_test_section(rfp_id, "Strategic", "Technical approach", "strategic_decision", 3)

        # Whole-RFP note: global context
        whole_text = "Global Policy: Standard delivery follows UK agile scrum sprints."
        self.client.post(f"/api/rfps/{rfp_id}/notes", json={"raw_content": whole_text, "section_id": None})

        # Section-specific note on pricing and strategic, but NONE on boilerplate
        pricing_note = "Pricing Override: Apply 15% partner concession on day rate."
        strategic_note = "Strategic Override: Deploy on AWS GovCloud exclusively."
        self.client.post(f"/api/rfps/{rfp_id}/notes", json={"raw_content": pricing_note, "section_id": sec_p})
        self.client.post(f"/api/rfps/{rfp_id}/notes", json={"raw_content": strategic_note, "section_id": sec_s})

        # 1. Draft pricing section: should have pricing_note, NOT whole_text
        draft_p = self.client.post(f"/api/rfps/{rfp_id}/sections/{sec_p}/generate").json()["draft_content"]
        self.assertIn("15% partner concession", draft_p)
        self.assertNotIn("agile scrum sprints", draft_p)

        # 2. Draft boilerplate section: should have whole_text since no section-specific note exists
        draft_b = self.client.post(f"/api/rfps/{rfp_id}/sections/{sec_b}/generate").json()["draft_content"]
        self.assertIn("agile scrum sprints", draft_b)

        # 3. Draft strategic section: should have strategic_note, NOT whole_text
        draft_s = self.client.post(f"/api/rfps/{rfp_id}/sections/{sec_s}/generate").json()["draft_content"]
        self.assertIn("AWS GovCloud exclusively", draft_s)
        self.assertNotIn("agile scrum sprints", draft_s)

    def test_20_full_gap_resolution_to_export_comment_lifecycle(self):
        """Full pipeline: gap generation generates comment in export; resolving eliminates comment from export."""
        rfp_id = self.create_test_rfp("Export Comments Lifecycle Client")
        sec_gap = self.create_test_section(rfp_id, "Gap Section", "Niche requirement", "gap", 1)

        # Generate draft -> creates open question
        gen_res = self.client.post(f"/api/rfps/{rfp_id}/sections/{sec_gap}/generate").json()
        self.assertEqual(gen_res["status"], "drafted")

        # Check mock export payload: unresolved question produces a comment
        exp1 = self.client.post(f"/api/rfps/{rfp_id}/export").json()
        self.assertTrue(exp1["success"])
        comments = exp1["payload"]["comments"]
        self.assertEqual(len(comments), 1)

        # Resolve open question
        q = self.client.get(f"/api/rfps/{rfp_id}/open-questions").json()[0]
        self.client.put(
            f"/api/rfps/{rfp_id}/open-questions/{q['id']}",
            json={"resolution": "Fully verified compliance credential.", "status": "resolved"},
        )

        # Regenerate section draft -> transitions status to resolved
        gen_after = self.client.post(f"/api/rfps/{rfp_id}/sections/{sec_gap}/generate").json()
        self.assertEqual(gen_after["status"], "resolved")
        self.assertNotIn("[MORE INFO REQUIRED:", gen_after["draft_content"])

        # Check mock export payload again: resolved question produces 0 comments
        exp2 = self.client.post(f"/api/rfps/{rfp_id}/export").json()
        self.assertTrue(exp2["success"])
        comments_after = exp2["payload"]["comments"]
        self.assertEqual(len(comments_after), 0)


if __name__ == "__main__":
    unittest.main()

"""
Adversarial Stress Test Suite for Milestone 4 (Challenger M4-2):
1. Gap marker idempotency (no duplicate open questions on repeated drafting).
2. Question resolution & regeneration cycle (resolving question replaces gap marker, updates provenance to notes, marks section resolved).
3. Cross-RFP boundary isolation (notes and questions cannot be accessed or deleted across RFP boundaries).
4. Boundary and stress conditions (whitespace, injection attacks, reopenings, non-existent IDs).
"""

import glob
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

# Ensure backend root and venv site-packages are on sys.path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

venv_pkgs = glob.glob(str(backend_dir.parent / ".venv" / "lib" / "python*" / "site-packages"))
for p in venv_pkgs:
    if p not in sys.path:
        sys.path.insert(0, p)

from fastapi.testclient import TestClient

from app.main import app
from app.database import get_db, init_db


class TestMilestone4Adversarial(unittest.TestCase):
    """Adversarial challenge suite verifying F17-F22 robustness under hostile edge cases."""

    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db_path = self.temp_db.name
        self.temp_db.close()

        def override_get_db():
            conn = sqlite3.connect(self.temp_db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON;")
            try:
                yield conn
            finally:
                conn.close()

        app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(app)
        init_db(self.temp_db_path)

        # Create two isolated RFPs for cross-RFP testing
        rfp1_res = self.client.post("/api/rfps", json={"client_name": "RFP 1 — Alpha Corp", "value": 50000.0})
        self.assertEqual(rfp1_res.status_code, 201)
        self.rfp1_id = rfp1_res.json()["id"]

        rfp2_res = self.client.post("/api/rfps", json={"client_name": "RFP 2 — Beta Industries", "value": 90000.0})
        self.assertEqual(rfp2_res.status_code, 201)
        self.rfp2_id = rfp2_res.json()["id"]

        # Insert sections for RFP 1 and RFP 2 directly via DB
        conn = sqlite3.connect(self.temp_db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        # RFP 1 Sections
        cur.execute(
            """
            INSERT INTO rfp_sections (rfp_id, heading, original_text, classification, confidence, sort_order)
            VALUES (?, '1.1 RFP1 Boilerplate', 'RFP1 boilerplate req', 'boilerplate', 'high', 1);
            """,
            (self.rfp1_id,),
        )
        self.rfp1_sec_bp = cur.lastrowid

        cur.execute(
            """
            INSERT INTO rfp_sections (rfp_id, heading, original_text, classification, confidence, sort_order)
            VALUES (?, '1.2 RFP1 Gap Requirement', 'Provide evidence of ISO 27001 medical device integration.', 'gap', 'low', 2);
            """,
            (self.rfp1_id,),
        )
        self.rfp1_sec_gap = cur.lastrowid

        cur.execute(
            """
            INSERT INTO rfp_sections (rfp_id, heading, original_text, classification, confidence, sort_order)
            VALUES (?, '1.3 RFP1 Unpriced Service', 'Specify pricing for unlisted Satellite Uplink service.', 'pricing', 'high', 3);
            """,
            (self.rfp1_id,),
        )
        self.rfp1_sec_unpriced = cur.lastrowid

        # RFP 2 Sections
        cur.execute(
            """
            INSERT INTO rfp_sections (rfp_id, heading, original_text, classification, confidence, sort_order)
            VALUES (?, '2.1 RFP2 Boilerplate', 'RFP2 boilerplate req', 'boilerplate', 'high', 1);
            """,
            (self.rfp2_id,),
        )
        self.rfp2_sec_bp = cur.lastrowid

        cur.execute(
            """
            INSERT INTO rfp_sections (rfp_id, heading, original_text, classification, confidence, sort_order)
            VALUES (?, '2.2 RFP2 Gap Requirement', 'Provide details of nuclear reactor telemetry experience.', 'gap', 'low', 2);
            """,
            (self.rfp2_id,),
        )
        self.rfp2_sec_gap = cur.lastrowid

        conn.commit()
        conn.close()

    def tearDown(self):
        app.dependency_overrides.clear()
        if os.path.exists(self.temp_db_path):
            os.remove(self.temp_db_path)

    # =========================================================================
    # 1. GAP MARKER IDEMPOTENCY STRESS TESTS
    # =========================================================================

    def test_01_repeated_generation_single_gap_section_is_strictly_idempotent(self):
        """Generating a gap draft 25 consecutive times produces exactly ONE open question."""
        for i in range(25):
            res = self.client.post(f"/api/rfps/{self.rfp1_id}/sections/{self.rfp1_sec_gap}/generate")
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertIn("[MORE INFO REQUIRED:", data["draft_content"])
            self.assertEqual(data["status"], "drafted")

        # Query open questions endpoint
        q_res = self.client.get(f"/api/rfps/{self.rfp1_id}/open-questions")
        self.assertEqual(q_res.status_code, 200)
        questions = q_res.json()
        self.assertEqual(len(questions), 1, f"Expected exactly 1 open question, got {len(questions)}")
        self.assertEqual(questions[0]["section_id"], self.rfp1_sec_gap)
        self.assertEqual(questions[0]["status"], "open")

        # Verify DB directly
        conn = sqlite3.connect(self.temp_db_path)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM open_questions WHERE section_id = ?;", (self.rfp1_sec_gap,))
        count = cur.fetchone()[0]
        conn.close()
        self.assertEqual(count, 1, f"DB open_questions count for section should be 1, found {count}")

    def test_02_interleaved_repeated_generation_across_multiple_gap_sections(self):
        """Interleaved repeated drafting across multiple gap sections maintains strict 1-to-1 question mapping."""
        # Create two additional gap sections in RFP 1
        conn = sqlite3.connect(self.temp_db_path)
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO rfp_sections (rfp_id, heading, original_text, classification, confidence, sort_order) VALUES (?, '1.4 Gap C', 'req C', 'gap', 'low', 4);",
            (self.rfp1_id,),
        )
        sec_c = cur.lastrowid
        cur.execute(
            "INSERT INTO rfp_sections (rfp_id, heading, original_text, classification, confidence, sort_order) VALUES (?, '1.5 Gap D', 'req D', 'gap', 'low', 5);",
            (self.rfp1_id,),
        )
        sec_d = cur.lastrowid
        conn.commit()
        conn.close()

        sections = [self.rfp1_sec_gap, sec_c, sec_d]

        # Execute 30 interleaved drafting calls (10 per section)
        for round_idx in range(10):
            for sec_id in sections:
                res = self.client.post(f"/api/rfps/{self.rfp1_id}/sections/{sec_id}/generate")
                self.assertEqual(res.status_code, 200)

        # Check open questions
        q_res = self.client.get(f"/api/rfps/{self.rfp1_id}/open-questions")
        self.assertEqual(q_res.status_code, 200)
        questions = q_res.json()
        self.assertEqual(len(questions), 3, f"Expected exactly 3 open questions across 3 gap sections, got {len(questions)}")

        section_ids = [q["section_id"] for q in questions]
        self.assertCountEqual(section_ids, sections)

    def test_03_missing_pricing_idempotency_on_repeated_generation(self):
        """Missing pricing data generating gap marker is idempotent over 15 calls."""
        for _ in range(15):
            res = self.client.post(f"/api/rfps/{self.rfp1_id}/sections/{self.rfp1_sec_unpriced}/generate")
            self.assertEqual(res.status_code, 200)
            self.assertIn("[MORE INFO REQUIRED: Missing pricing data for requested services]", res.json()["draft_content"])

        q_res = self.client.get(f"/api/rfps/{self.rfp1_id}/open-questions")
        questions = q_res.json()
        pricing_qs = [q for q in questions if q["section_id"] == self.rfp1_sec_unpriced]
        self.assertEqual(len(pricing_qs), 1, "Duplicate open questions created for missing pricing")
        self.assertEqual(pricing_qs[0]["question"], "Missing pricing data for requested services")

    def test_04_missing_boilerplate_idempotency_on_repeated_generation(self):
        """Missing boilerplate in empty KB generating gap marker is idempotent over 15 calls."""
        # Purge boilerplate documents from KB
        conn = sqlite3.connect(self.temp_db_path)
        conn.execute("DELETE FROM kb_documents WHERE type = 'boilerplate';")
        conn.commit()
        conn.close()

        for _ in range(15):
            res = self.client.post(f"/api/rfps/{self.rfp1_id}/sections/{self.rfp1_sec_bp}/generate")
            self.assertEqual(res.status_code, 200)
            self.assertIn("[MORE INFO REQUIRED: Company background and boilerplate not found in knowledge base]", res.json()["draft_content"])

        q_res = self.client.get(f"/api/rfps/{self.rfp1_id}/open-questions")
        questions = q_res.json()
        bp_qs = [q for q in questions if q["section_id"] == self.rfp1_sec_bp]
        self.assertEqual(len(bp_qs), 1, "Duplicate open questions created for missing boilerplate")

    def test_05_resolved_question_re_drafting_does_not_recreate_open_question(self):
        """After resolving a question and regenerating, further drafting does NOT re-create open questions."""
        # 1. Initial draft creates question
        self.client.post(f"/api/rfps/{self.rfp1_id}/sections/{self.rfp1_sec_gap}/generate")
        q = self.client.get(f"/api/rfps/{self.rfp1_id}/open-questions").json()[0]

        # 2. Resolve question
        self.client.put(
            f"/api/rfps/{self.rfp1_id}/open-questions/{q['id']}",
            json={"resolution": "ISO 27001 cert #98765 achieved in 2024", "status": "resolved"},
        )

        # 3. Regenerate 10 times
        for _ in range(10):
            res = self.client.post(f"/api/rfps/{self.rfp1_id}/sections/{self.rfp1_sec_gap}/generate")
            self.assertEqual(res.status_code, 200)
            self.assertEqual(res.json()["status"], "resolved")
            self.assertNotIn("[MORE INFO REQUIRED:", res.json()["draft_content"])

        # 4. Verify questions list still contains only 1 question with status='resolved'
        questions = self.client.get(f"/api/rfps/{self.rfp1_id}/open-questions").json()
        self.assertEqual(len(questions), 1)
        self.assertEqual(questions[0]["status"], "resolved")

    # =========================================================================
    # 2. QUESTION RESOLUTION & REGENERATION CYCLE TESTS
    # =========================================================================

    def test_06_complete_gap_resolution_regeneration_lifecycle(self):
        """Full lifecycle: gap draft -> open question -> PUT resolve -> regenerate -> replaced marker, notes provenance, resolved status."""
        # 1. Initial draft
        gen1 = self.client.post(f"/api/rfps/{self.rfp1_id}/sections/{self.rfp1_sec_gap}/generate")
        self.assertEqual(gen1.status_code, 200)
        self.assertEqual(gen1.json()["status"], "drafted")
        self.assertIn("[MORE INFO REQUIRED:", gen1.json()["draft_content"])

        # 2. Verify open question in DB
        questions = self.client.get(f"/api/rfps/{self.rfp1_id}/open-questions").json()
        self.assertEqual(len(questions), 1)
        target_q = questions[0]
        self.assertEqual(target_q["status"], "open")
        self.assertIsNone(target_q["resolution"])

        # 3. Resolve open question via PUT
        res_text = "Delivered ISO 27001 Level 3 integration with NHS Spine in November 2025."
        put_res = self.client.put(
            f"/api/rfps/{self.rfp1_id}/open-questions/{target_q['id']}",
            json={"resolution": res_text, "status": "resolved"},
        )
        self.assertEqual(put_res.status_code, 200)
        self.assertEqual(put_res.json()["status"], "resolved")
        self.assertEqual(put_res.json()["resolution"], res_text)

        # 4. Regenerate section
        gen2 = self.client.post(f"/api/rfps/{self.rfp1_id}/sections/{self.rfp1_sec_gap}/generate")
        self.assertEqual(gen2.status_code, 200)
        data = gen2.json()

        # Marker must be gone
        self.assertNotIn("[MORE INFO REQUIRED:", data["draft_content"])
        # Resolution text must be embedded
        self.assertIn(res_text, data["draft_content"])
        # Status must transition to "resolved"
        self.assertEqual(data["status"], "resolved")

        # Provenance must attribute resolution text to source "notes"
        notes_prov = [p for p in data["provenance"] if p["source"] == "notes" and res_text in p["text"]]
        self.assertTrue(len(notes_prov) > 0, "Resolution text not attributed to source 'notes'")
        self.assertEqual(notes_prov[0]["reference"], f"Open Question #{target_q['id']} Resolution")

        # Check DB persistent section state
        conn = sqlite3.connect(self.temp_db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT status, draft_content FROM rfp_sections WHERE id = ?;", (self.rfp1_sec_gap,))
        sec_row = cur.fetchone()
        conn.close()

        self.assertEqual(sec_row["status"], "resolved")
        self.assertIn(res_text, sec_row["draft_content"])
        self.assertNotIn("[MORE INFO REQUIRED:", sec_row["draft_content"])

    def test_07_patch_resolution_endpoint_parity(self):
        """PATCH /api/rfps/{id}/open-questions/{q_id} resolves question identically to PUT."""
        self.client.post(f"/api/rfps/{self.rfp1_id}/sections/{self.rfp1_sec_gap}/generate")
        q = self.client.get(f"/api/rfps/{self.rfp1_id}/open-questions").json()[0]

        res_text = "Patched resolution for compliance."
        patch_res = self.client.patch(
            f"/api/rfps/{self.rfp1_id}/open-questions/{q['id']}",
            json={"resolution": res_text, "status": "resolved"},
        )
        self.assertEqual(patch_res.status_code, 200)
        self.assertEqual(patch_res.json()["status"], "resolved")
        self.assertEqual(patch_res.json()["resolution"], res_text)

        regen = self.client.post(f"/api/rfps/{self.rfp1_id}/sections/{self.rfp1_sec_gap}/generate").json()
        self.assertEqual(regen["status"], "resolved")
        self.assertIn(res_text, regen["draft_content"])

    def test_08_question_reopening_and_re_drafting(self):
        """Reopening a resolved question resets regeneration to emit gap marker and drafted status."""
        # 1. Draft and resolve
        self.client.post(f"/api/rfps/{self.rfp1_id}/sections/{self.rfp1_sec_gap}/generate")
        q = self.client.get(f"/api/rfps/{self.rfp1_id}/open-questions").json()[0]

        self.client.put(
            f"/api/rfps/{self.rfp1_id}/open-questions/{q['id']}",
            json={"resolution": "Initial answer", "status": "resolved"},
        )
        gen_res = self.client.post(f"/api/rfps/{self.rfp1_id}/sections/{self.rfp1_sec_gap}/generate").json()
        self.assertEqual(gen_res["status"], "resolved")

        # 2. Reopen question (status: 'open', empty resolution)
        reopen_res = self.client.put(
            f"/api/rfps/{self.rfp1_id}/open-questions/{q['id']}",
            json={"resolution": "", "status": "open"},
        )
        self.assertEqual(reopen_res.status_code, 200)
        self.assertEqual(reopen_res.json()["status"], "open")

        # 3. Regenerate: must revert to gap marker and drafted status
        gen_reopen = self.client.post(f"/api/rfps/{self.rfp1_id}/sections/{self.rfp1_sec_gap}/generate").json()
        self.assertIn("[MORE INFO REQUIRED:", gen_reopen["draft_content"])
        self.assertEqual(gen_reopen["status"], "drafted")
        gap_prov = [p for p in gen_reopen["provenance"] if p["source"] == "gap"]
        self.assertTrue(len(gap_prov) > 0)

    def test_09_independent_multi_question_resolution(self):
        """Resolving question for Section A leaves Section B question open and Section B status drafted."""
        # RFP 1 has sec_gap; add sec_gap2
        conn = sqlite3.connect(self.temp_db_path)
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO rfp_sections (rfp_id, heading, original_text, classification, confidence, sort_order) VALUES (?, '1.4 Cyber Essentials', 'Describe Cyber Essentials Plus certification.', 'gap', 'low', 4);",
            (self.rfp1_id,),
        )
        sec_gap2 = cur.lastrowid
        conn.commit()
        conn.close()

        # Generate both
        self.client.post(f"/api/rfps/{self.rfp1_id}/sections/{self.rfp1_sec_gap}/generate")
        self.client.post(f"/api/rfps/{self.rfp1_id}/sections/{sec_gap2}/generate")

        qs = self.client.get(f"/api/rfps/{self.rfp1_id}/open-questions").json()
        q1 = next(q for q in qs if q["section_id"] == self.rfp1_sec_gap)
        q2 = next(q for q in qs if q["section_id"] == sec_gap2)

        # Resolve q1 only
        self.client.put(
            f"/api/rfps/{self.rfp1_id}/open-questions/{q1['id']}",
            json={"resolution": "ISO 27001 resolution text", "status": "resolved"},
        )

        # Regenerate both
        res1 = self.client.post(f"/api/rfps/{self.rfp1_id}/sections/{self.rfp1_sec_gap}/generate").json()
        res2 = self.client.post(f"/api/rfps/{self.rfp1_id}/sections/{sec_gap2}/generate").json()

        self.assertEqual(res1["status"], "resolved")
        self.assertNotIn("[MORE INFO REQUIRED:", res1["draft_content"])
        self.assertIn("ISO 27001 resolution text", res1["draft_content"])

        self.assertEqual(res2["status"], "drafted")
        self.assertIn("[MORE INFO REQUIRED:", res2["draft_content"])
        self.assertNotIn("ISO 27001 resolution text", res2["draft_content"])

    # =========================================================================
    # 3. CROSS-RFP BOUNDARY ISOLATION TESTS
    # =========================================================================

    def test_10_notes_list_strict_rfp_isolation(self):
        """Notes created on RFP 1 and RFP 2 never cross-pollinate in GET /api/rfps/{id}/notes."""
        self.client.post(f"/api/rfps/{self.rfp1_id}/notes", json={"raw_content": "Note RFP1 Alpha Whole", "section_id": None})
        self.client.post(f"/api/rfps/{self.rfp1_id}/notes", json={"raw_content": "Note RFP1 Alpha Section", "section_id": self.rfp1_sec_gap})

        self.client.post(f"/api/rfps/{self.rfp2_id}/notes", json={"raw_content": "Note RFP2 Beta Whole", "section_id": None})
        self.client.post(f"/api/rfps/{self.rfp2_id}/notes", json={"raw_content": "Note RFP2 Beta Section", "section_id": self.rfp2_sec_gap})

        notes_1 = self.client.get(f"/api/rfps/{self.rfp1_id}/notes").json()
        notes_2 = self.client.get(f"/api/rfps/{self.rfp2_id}/notes").json()

        self.assertEqual(len(notes_1), 2)
        self.assertEqual(len(notes_2), 2)

        for n in notes_1:
            self.assertEqual(n["rfp_id"], self.rfp1_id)
            self.assertIn("RFP1", n["raw_content"])
            self.assertNotIn("RFP2", n["raw_content"])

        for n in notes_2:
            self.assertEqual(n["rfp_id"], self.rfp2_id)
            self.assertIn("RFP2", n["raw_content"])
            self.assertNotIn("RFP1", n["raw_content"])

    def test_11_note_creation_cross_rfp_section_rejected_with_404(self):
        """Creating a note on RFP 1 referencing a section belonging to RFP 2 is rejected with 404."""
        res = self.client.post(
            f"/api/rfps/{self.rfp1_id}/notes",
            json={"raw_content": "Malicious cross-attachment", "section_id": self.rfp2_sec_gap},
        )
        self.assertEqual(res.status_code, 404)
        self.assertIn("Section not found for this RFP", res.json()["detail"])

    def test_12_note_deletion_cross_rfp_rejected_and_non_destructive(self):
        """Attempting to delete RFP 2's note via RFP 1 endpoint returns 404 and does NOT delete note."""
        created = self.client.post(f"/api/rfps/{self.rfp2_id}/notes", json={"raw_content": "Protected RFP2 Note"}).json()
        rfp2_note_id = created["id"]

        # Attempt delete via RFP 1
        res = self.client.delete(f"/api/rfps/{self.rfp1_id}/notes/{rfp2_note_id}")
        self.assertEqual(res.status_code, 404)
        self.assertIn("Note not found for this RFP", res.json()["detail"])

        # Verify RFP 2 note is still intact
        notes_2 = self.client.get(f"/api/rfps/{self.rfp2_id}/notes").json()
        self.assertTrue(any(n["id"] == rfp2_note_id for n in notes_2))

    def test_13_open_questions_list_strict_rfp_isolation(self):
        """Open questions generated on RFP 1 and RFP 2 are strictly isolated."""
        self.client.post(f"/api/rfps/{self.rfp1_id}/sections/{self.rfp1_sec_gap}/generate")
        self.client.post(f"/api/rfps/{self.rfp2_id}/sections/{self.rfp2_sec_gap}/generate")

        q1 = self.client.get(f"/api/rfps/{self.rfp1_id}/open-questions").json()
        q2 = self.client.get(f"/api/rfps/{self.rfp2_id}/open-questions").json()

        self.assertEqual(len(q1), 1)
        self.assertEqual(len(q2), 1)

        self.assertEqual(q1[0]["rfp_id"], self.rfp1_id)
        self.assertEqual(q1[0]["section_id"], self.rfp1_sec_gap)
        self.assertIn("1.2 RFP1 Gap Requirement", q1[0]["question"])

        self.assertEqual(q2[0]["rfp_id"], self.rfp2_id)
        self.assertEqual(q2[0]["section_id"], self.rfp2_sec_gap)
        self.assertIn("2.2 RFP2 Gap Requirement", q2[0]["question"])

    def test_14_open_question_resolution_cross_rfp_rejected(self):
        """Attempting to resolve RFP 2 question via RFP 1 endpoint returns 404 and does NOT mutate question."""
        self.client.post(f"/api/rfps/{self.rfp2_id}/sections/{self.rfp2_sec_gap}/generate")
        q2 = self.client.get(f"/api/rfps/{self.rfp2_id}/open-questions").json()[0]
        q2_id = q2["id"]

        # Try resolving via RFP 1 PUT
        put_res = self.client.put(
            f"/api/rfps/{self.rfp1_id}/open-questions/{q2_id}",
            json={"resolution": "Unauthorized resolution", "status": "resolved"},
        )
        self.assertEqual(put_res.status_code, 404)

        # Try resolving via RFP 1 PATCH
        patch_res = self.client.patch(
            f"/api/rfps/{self.rfp1_id}/open-questions/{q2_id}",
            json={"resolution": "Unauthorized resolution", "status": "resolved"},
        )
        self.assertEqual(patch_res.status_code, 404)

        # Verify Q2 remains open and unresolved
        q2_check = self.client.get(f"/api/rfps/{self.rfp2_id}/open-questions").json()[0]
        self.assertEqual(q2_check["status"], "open")
        self.assertIsNone(q2_check["resolution"])

    def test_15_section_endpoints_cross_rfp_rejected(self):
        """Draft generation and section updates on cross-RFP section IDs return 404."""
        # Generate RFP 2 section on RFP 1 route
        gen_res = self.client.post(f"/api/rfps/{self.rfp1_id}/sections/{self.rfp2_sec_gap}/generate")
        self.assertEqual(gen_res.status_code, 404)
        self.assertIn("Section not found for this RFP", gen_res.json()["detail"])

        # PUT section
        put_res = self.client.put(
            f"/api/rfps/{self.rfp1_id}/sections/{self.rfp2_sec_gap}",
            json={"classification": "pricing"},
        )
        self.assertEqual(put_res.status_code, 404)

        # PATCH section
        patch_res = self.client.patch(
            f"/api/rfps/{self.rfp1_id}/sections/{self.rfp2_sec_gap}",
            json={"final_content": "Hijacked content"},
        )
        self.assertEqual(patch_res.status_code, 404)

    def test_16_am_notes_draft_generation_context_strict_isolation(self):
        """Notes from RFP 2 never leak into drafts generated for RFP 1."""
        self.client.post(f"/api/rfps/{self.rfp1_id}/notes", json={"raw_content": "ALPHA_CONFIDENTIAL_BUDGET_50K"})
        self.client.post(f"/api/rfps/{self.rfp2_id}/notes", json={"raw_content": "BETA_TOP_SECRET_NUCLEAR_SPECS"})

        res1 = self.client.post(f"/api/rfps/{self.rfp1_id}/sections/{self.rfp1_sec_gap}/generate").json()
        self.assertIn("ALPHA_CONFIDENTIAL_BUDGET_50K", res1["draft_content"])
        self.assertNotIn("BETA_TOP_SECRET_NUCLEAR_SPECS", res1["draft_content"])

        res2 = self.client.post(f"/api/rfps/{self.rfp2_id}/sections/{self.rfp2_sec_gap}/generate").json()
        self.assertIn("BETA_TOP_SECRET_NUCLEAR_SPECS", res2["draft_content"])
        self.assertNotIn("ALPHA_CONFIDENTIAL_BUDGET_50K", res2["draft_content"])

    def test_17_get_rfp_detail_full_composite_isolation(self):
        """GET /api/rfps/{id} returns sections, notes, and open questions exclusively for target RFP."""
        self.client.post(f"/api/rfps/{self.rfp1_id}/notes", json={"raw_content": "Note 1"})
        self.client.post(f"/api/rfps/{self.rfp2_id}/notes", json={"raw_content": "Note 2"})
        self.client.post(f"/api/rfps/{self.rfp1_id}/sections/{self.rfp1_sec_gap}/generate")
        self.client.post(f"/api/rfps/{self.rfp2_id}/sections/{self.rfp2_sec_gap}/generate")

        det1 = self.client.get(f"/api/rfps/{self.rfp1_id}").json()
        det2 = self.client.get(f"/api/rfps/{self.rfp2_id}").json()

        # Check sections
        self.assertTrue(all(s["rfp_id"] == self.rfp1_id for s in det1["sections"]))
        self.assertTrue(all(s["rfp_id"] == self.rfp2_id for s in det2["sections"]))

        # Check notes
        self.assertTrue(all(n["rfp_id"] == self.rfp1_id for n in det1["notes"]))
        self.assertTrue(all(n["rfp_id"] == self.rfp2_id for n in det2["notes"]))

        # Check open questions
        self.assertTrue(all(q["rfp_id"] == self.rfp1_id for q in det1["open_questions"]))
        self.assertTrue(all(q["rfp_id"] == self.rfp2_id for q in det2["open_questions"]))

    # =========================================================================
    # 4. BOUNDARY, CONCURRENCY & INPUT FUZZING STRESS TESTS
    # =========================================================================

    def test_18_double_delete_note_returns_404_on_second(self):
        """Deleting the same note twice returns 404 on the second call (no dangling references)."""
        created = self.client.post(f"/api/rfps/{self.rfp1_id}/notes", json={"raw_content": "Ephemeral note"}).json()
        nid = created["id"]

        del1 = self.client.delete(f"/api/rfps/{self.rfp1_id}/notes/{nid}")
        self.assertEqual(del1.status_code, 200)

        del2 = self.client.delete(f"/api/rfps/{self.rfp1_id}/notes/{nid}")
        self.assertEqual(del2.status_code, 404)

    def test_19_sql_injection_resilience_in_notes_and_questions(self):
        """SQL injection strings in note content and question resolution are safely parameterized."""
        sql_injection = "'; DROP TABLE rfp_notes; SELECT * FROM rfps WHERE ''='"

        # Note creation with SQL injection string
        res = self.client.post(f"/api/rfps/{self.rfp1_id}/notes", json={"raw_content": sql_injection})
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.json()["raw_content"], sql_injection)

        # Question resolution with SQL injection string
        self.client.post(f"/api/rfps/{self.rfp1_id}/sections/{self.rfp1_sec_gap}/generate")
        q = self.client.get(f"/api/rfps/{self.rfp1_id}/open-questions").json()[0]

        put_res = self.client.put(
            f"/api/rfps/{self.rfp1_id}/open-questions/{q['id']}",
            json={"resolution": sql_injection, "status": "resolved"},
        )
        self.assertEqual(put_res.status_code, 200)

        # Verify database tables were not corrupted or dropped
        conn = sqlite3.connect(self.temp_db_path)
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM rfp_notes;")
        note_count = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM open_questions;")
        q_count = cur.fetchone()[0]
        conn.close()

        self.assertGreaterEqual(note_count, 1)
        self.assertGreaterEqual(q_count, 1)

    def test_20_unicode_emoji_and_multiline_payloads(self):
        """Unicode, emoji, and multiline markdown strings in notes and questions are handled cleanly."""
        multiline_emoji = "🚀 Phase 1: Launch 🌟\n- Line 2: ✨ High velocity\n- Line 3: 🔒 Zero leaks 🛡️\n\nFinal note."
        note_res = self.client.post(f"/api/rfps/{self.rfp1_id}/notes", json={"raw_content": multiline_emoji})
        self.assertEqual(note_res.status_code, 201)
        self.assertEqual(note_res.json()["raw_content"], multiline_emoji)

        self.client.post(f"/api/rfps/{self.rfp1_id}/sections/{self.rfp1_sec_gap}/generate")
        q = self.client.get(f"/api/rfps/{self.rfp1_id}/open-questions").json()[0]

        res = self.client.put(
            f"/api/rfps/{self.rfp1_id}/open-questions/{q['id']}",
            json={"resolution": multiline_emoji, "status": "resolved"},
        )
        self.assertEqual(res.status_code, 200)

        regen = self.client.post(f"/api/rfps/{self.rfp1_id}/sections/{self.rfp1_sec_gap}/generate").json()
        self.assertIn("🚀 Phase 1: Launch 🌟", regen["draft_content"])
        self.assertEqual(regen["status"], "resolved")

    def test_21_nonexistent_ids_return_404(self):
        """Non-existent RFP IDs return clean 404s without unhandled exceptions."""
        self.assertEqual(self.client.get("/api/rfps/999999/notes").status_code, 404)
        self.assertEqual(self.client.post("/api/rfps/999999/notes", json={"raw_content": "test"}).status_code, 404)
        self.assertEqual(self.client.delete("/api/rfps/999999/notes/1").status_code, 404)
        self.assertEqual(self.client.get("/api/rfps/999999/open-questions").status_code, 404)
        self.assertEqual(self.client.put("/api/rfps/999999/open-questions/1", json={"resolution": "res"}).status_code, 404)
        self.assertEqual(self.client.post("/api/rfps/999999/sections/1/generate").status_code, 404)
        self.assertEqual(self.client.put("/api/rfps/999999/sections/1", json={"status": "drafted"}).status_code, 404)


if __name__ == "__main__":
    unittest.main()

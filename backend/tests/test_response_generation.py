"""
Unit and Integration Tests for Milestone 4:
Response Generation Pipeline, Hybrid AM Notes, Open Questions, Content Provenance & Section Editor (F17-F22).
"""

import os
import sqlite3
import tempfile
import unittest
from fastapi.testclient import TestClient

from app.main import app
from app.database import get_db, init_db


class TestResponseGenerationPipeline(unittest.TestCase):
    """Test suite covering F17, F18, F19, F20, F21, and F22."""

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

        # Initialize schema and seed data in test database
        init_db(self.temp_db_path)

        # Create a test RFP
        rfp_res = self.client.post("/api/rfps", json={"client_name": "Acme Health Care", "service_ids": [1]})
        self.assertEqual(rfp_res.status_code, 201)
        self.rfp_id = rfp_res.json()["id"]

        # Insert test sections
        conn = sqlite3.connect(self.temp_db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        # Section 1: Boilerplate
        cur.execute(
            """
            INSERT INTO rfp_sections (rfp_id, heading, original_text, classification, confidence, sort_order)
            VALUES (?, '1.0 Company Overview', 'Provide company credentials and insurance overview.', 'boilerplate', 'high', 1);
            """,
            (self.rfp_id,),
        )
        self.sec_bp_id = cur.lastrowid

        # Section 2: Pricing
        cur.execute(
            """
            INSERT INTO rfp_sections (rfp_id, heading, original_text, classification, confidence, sort_order)
            VALUES (?, '2.0 Commercial Quotation', 'State the day rate for a senior full-stack engineer and the fixed discovery sprint package.', 'pricing', 'high', 2);
            """,
            (self.rfp_id,),
        )
        self.sec_pricing_id = cur.lastrowid

        # Section 3: Strategic Decision
        cur.execute(
            """
            INSERT INTO rfp_sections (rfp_id, heading, original_text, classification, confidence, sort_order)
            VALUES (?, '3.0 CMS Technical Architecture', 'Describe your architectural approach using modern headless CMS.', 'strategic_decision', 'high', 3);
            """,
            (self.rfp_id,),
        )
        self.sec_strat_id = cur.lastrowid

        # Section 4: Information Gap
        cur.execute(
            """
            INSERT INTO rfp_sections (rfp_id, heading, original_text, classification, confidence, sort_order)
            VALUES (?, '4.0 NHS Telemetry Integration', 'Detail past experience delivering NHS England patient telemetry.', 'gap', 'low', 4);
            """,
            (self.rfp_id,),
        )
        self.sec_gap_id = cur.lastrowid

        conn.commit()
        conn.close()

    def tearDown(self):
        app.dependency_overrides.clear()
        if os.path.exists(self.temp_db_path):
            os.remove(self.temp_db_path)

    # -------------------------------------------------------------------------
    # F17: Account Manager Notes CRUD
    # -------------------------------------------------------------------------

    def test_01_create_whole_rfp_note(self):
        """Create a whole-RFP note with section_id=None."""
        res = self.client.post(
            f"/api/rfps/{self.rfp_id}/notes",
            json={"raw_content": "Client emphasizes ISO 27001 and strict data sovereignty.", "section_id": None},
        )
        self.assertEqual(res.status_code, 201)
        data = res.json()
        self.assertIsNotNone(data["id"])
        self.assertIsNone(data["section_id"])
        self.assertIn("ISO 27001", data["raw_content"])

    def test_02_create_section_specific_note(self):
        """Create a note bound to a specific section."""
        res = self.client.post(
            f"/api/rfps/{self.rfp_id}/notes",
            json={"raw_content": "Offer 10% discount on discovery sprint.", "section_id": self.sec_pricing_id},
        )
        self.assertEqual(res.status_code, 201)
        data = res.json()
        self.assertEqual(data["section_id"], self.sec_pricing_id)
        self.assertIn("10% discount", data["raw_content"])

    def test_03_list_rfp_notes(self):
        """List notes returns all notes for RFP in chronological order."""
        self.client.post(f"/api/rfps/{self.rfp_id}/notes", json={"raw_content": "Note A", "section_id": None})
        self.client.post(f"/api/rfps/{self.rfp_id}/notes", json={"raw_content": "Note B", "section_id": self.sec_strat_id})

        res = self.client.get(f"/api/rfps/{self.rfp_id}/notes")
        self.assertEqual(res.status_code, 200)
        notes = res.json()
        self.assertGreaterEqual(len(notes), 2)
        contents = [n["raw_content"] for n in notes]
        self.assertIn("Note A", contents)
        self.assertIn("Note B", contents)

    def test_04_delete_rfp_note(self):
        """DELETE /api/rfps/{id}/notes/{note_id} deletes note and returns 200."""
        created = self.client.post(f"/api/rfps/{self.rfp_id}/notes", json={"raw_content": "Temporary note"}).json()
        note_id = created["id"]

        del_res = self.client.delete(f"/api/rfps/{self.rfp_id}/notes/{note_id}")
        self.assertEqual(del_res.status_code, 200)
        self.assertEqual(del_res.json(), {"deleted": note_id})

        # Verify gone
        notes = self.client.get(f"/api/rfps/{self.rfp_id}/notes").json()
        self.assertFalse(any(n["id"] == note_id for n in notes))

    def test_05_delete_nonexistent_note_returns_404(self):
        """Deleting non-existent note or note on wrong RFP returns 404."""
        del_res = self.client.delete(f"/api/rfps/{self.rfp_id}/notes/999999")
        self.assertEqual(del_res.status_code, 404)

    def test_06_empty_note_content_rejected(self):
        """Empty or whitespace-only note content returns 422."""
        res = self.client.post(f"/api/rfps/{self.rfp_id}/notes", json={"raw_content": "   "})
        self.assertEqual(res.status_code, 422)

    def test_07_invalid_section_id_returns_404(self):
        """Attaching note to non-existent section returns 404."""
        res = self.client.post(f"/api/rfps/{self.rfp_id}/notes", json={"raw_content": "Valid text", "section_id": 999999})
        self.assertEqual(res.status_code, 404)

    # -------------------------------------------------------------------------
    # F18, F19, F21: Multi-Source Draft Generation & Provenance Metadata
    # -------------------------------------------------------------------------

    def test_08_boilerplate_draft_generation_and_provenance(self):
        """Generate boilerplate draft and verify provenance with reference attribute."""
        res = self.client.post(f"/api/rfps/{self.rfp_id}/sections/{self.sec_bp_id}/generate")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("draft_content", data)
        self.assertIn("provenance", data)

        provenance = data["provenance"]
        self.assertTrue(len(provenance) > 0)
        # Check that reference is present and non-empty
        bp_prov = next((p for p in provenance if p["source"] == "boilerplate"), None)
        self.assertIsNotNone(bp_prov)
        self.assertIn("reference", bp_prov)
        self.assertTrue(len(bp_prov["reference"]) > 0)

    def test_09_exact_pricing_fidelity_in_draft(self):
        """Generate pricing draft reproducing exact £ amount from database and reporting the engine used."""
        res = self.client.post(f"/api/rfps/{self.rfp_id}/sections/{self.sec_pricing_id}/generate")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        draft = data["draft_content"]
        self.assertIn("850", draft)
        self.assertEqual(data["engine"], "mock")
        self.assertTrue(data["model"])

        pricing_prov = next((p for p in data["provenance"] if p["source"] == "pricing"), None)
        self.assertIsNotNone(pricing_prov)
        self.assertEqual(pricing_prov["reference"], "Structured price_items schedule")

    def test_10_am_notes_precedence(self):
        """Section-specific note takes precedence over whole-RFP note in draft."""
        whole_text = "Global mandate: Recommend Drupal 10 across all proposals."
        section_text = "Local override: Client strictly requires Statamic 4 headless."

        self.client.post(f"/api/rfps/{self.rfp_id}/notes", json={"raw_content": whole_text, "section_id": None})
        self.client.post(f"/api/rfps/{self.rfp_id}/notes", json={"raw_content": section_text, "section_id": self.sec_strat_id})

        res = self.client.post(f"/api/rfps/{self.rfp_id}/sections/{self.sec_strat_id}/generate")
        self.assertEqual(res.status_code, 200)
        draft = res.json()["draft_content"]

        self.assertIn(section_text, draft)
        self.assertNotIn("Recommend Drupal 10", draft)

        # Provenance check
        note_prov = next((p for p in res.json()["provenance"] if p["source"] == "notes"), None)
        self.assertIsNotNone(note_prov)
        self.assertIn(f"Section {self.sec_strat_id}", note_prov["reference"])

    def test_11_gap_marker_auto_inserts_open_question(self):
        """Drafting a gap section outputs [MORE INFO REQUIRED] marker and auto-inserts open question."""
        res = self.client.post(f"/api/rfps/{self.rfp_id}/sections/{self.sec_gap_id}/generate")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("[MORE INFO REQUIRED:", data["draft_content"])
        self.assertEqual(data["status"], "drafted")

        # Verify open question auto-created
        q_res = self.client.get(f"/api/rfps/{self.rfp_id}/open-questions")
        self.assertEqual(q_res.status_code, 200)
        questions = q_res.json()
        self.assertGreaterEqual(len(questions), 1)
        target = next((q for q in questions if q["section_id"] == self.sec_gap_id), None)
        self.assertIsNotNone(target)
        self.assertEqual(target["status"], "open")

    # -------------------------------------------------------------------------
    # F20: Open Questions Resolution Loop
    # -------------------------------------------------------------------------

    def test_12_resolve_open_question_and_regenerate_section(self):
        """Resolving an open question clears gap marker and marks section resolved on regeneration."""
        # 1. Generate gap draft
        self.client.post(f"/api/rfps/{self.rfp_id}/sections/{self.sec_gap_id}/generate")

        # 2. Get open question
        questions = self.client.get(f"/api/rfps/{self.rfp_id}/open-questions").json()
        target_q = next(q for q in questions if q["section_id"] == self.sec_gap_id)

        # 3. Resolve open question
        res_text = "We delivered certified NHS Digital telemetry for HealthTrust in Q2 2025."
        put_res = self.client.put(
            f"/api/rfps/{self.rfp_id}/open-questions/{target_q['id']}",
            json={"resolution": res_text, "status": "resolved"},
        )
        self.assertEqual(put_res.status_code, 200)
        self.assertEqual(put_res.json()["status"], "resolved")
        self.assertEqual(put_res.json()["resolution"], res_text)

        # 4. Regenerate section
        regen_res = self.client.post(f"/api/rfps/{self.rfp_id}/sections/{self.sec_gap_id}/generate")
        self.assertEqual(regen_res.status_code, 200)
        regen_data = regen_res.json()
        self.assertIn("NHS Digital telemetry", regen_data["draft_content"])
        self.assertNotIn("[MORE INFO REQUIRED:", regen_data["draft_content"])
        self.assertEqual(regen_data["status"], "resolved")

    # -------------------------------------------------------------------------
    # F22: Direct Section Editing and Status Lifecycle
    # -------------------------------------------------------------------------

    def test_13_update_section_draft_and_final_content(self):
        """Update section final_content and transition status to resolved."""
        update_payload = {
            "final_content": "Manually reviewed and approved technical response for compliance.",
            "status": "resolved",
        }
        res = self.client.put(f"/api/rfps/{self.rfp_id}/sections/{self.sec_strat_id}", json=update_payload)
        self.assertEqual(res.status_code, 200)
        sec = res.json()
        self.assertEqual(sec["final_content"], update_payload["final_content"])
        self.assertEqual(sec["status"], "resolved")

    def test_14_update_section_invalid_status_rejected(self):
        """Reject invalid section status value."""
        res = self.client.put(
            f"/api/rfps/{self.rfp_id}/sections/{self.sec_strat_id}",
            json={"status": "invalid_status"},
        )
        self.assertEqual(res.status_code, 422)


if __name__ == "__main__":
    unittest.main()

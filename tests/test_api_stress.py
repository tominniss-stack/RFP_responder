#!/usr/bin/env python3
"""
Empirical Stress Test Suite — Milestone 1 (Foundations & Core Services)
Challenger: challenger_m1_1

Stress tests:
1. SQLite Database Constraints:
   - Singleton settings CHECK(id = 1) violation (id=2, id=0, id=-1)
   - Singleton settings duplicate primary key (id=1 duplicate insert)
   - Services UNIQUE constraint violation (exact duplicate name)
   - Foreign key violation in rfp_services (nonexistent rfp_id / nonexistent service_id)
   - Foreign key violation in kb_document_services (nonexistent kb_document_id / nonexistent service_id)
   - Cascading deletion of RFPs (cascades to rfp_services, rfp_sections, rfp_notes, open_questions)
   - Cascading deletion of Services (cascades to rfp_services, kb_document_services, SET NULL on price_items)
   - Cascading deletion of KB Documents (cascades to kb_document_services)
   - Cascading deletion of RFP Sections (cascades to section-specific rfp_notes and open_questions)

2. Settings API Stress & Malformed Payloads:
   - Invalid data types (e.g. non-boolean for mock_google_export) -> 422
   - Prompts below min_length -> 422
   - Empty model strings -> 422
   - Empty payload -> 200 (no-op)
   - Unknown fields -> gracefully handled without SQL injection

3. Services API Stress & Malformed Payloads:
   - Empty string name -> 400
   - Pure whitespace name -> 400
   - Missing name / Null name / Non-string name -> 422
   - Name exceeding 200 characters -> 422
   - Case-insensitive duplicate name -> 409
   - Whitespace-padded duplicate name -> 409
   - Delete non-existent ID -> 404
   - Delete invalid string ID -> 422
   - Delete negative ID -> 404
"""

import os
import sys
import tempfile
import sqlite3
import unittest
from pathlib import Path

# Ensure backend is in python path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.database import get_db_connection, init_db, get_db
from app.models import create_tables, seed_defaults, DEFAULT_SERVICES
from fastapi.testclient import TestClient
from app.main import app


class TestSQLiteConstraintsEmpirical(unittest.TestCase):
    """Empirically test SQLite schema constraints under hostile/violating operations."""

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.tmp.name
        self.tmp.close()
        self.conn = get_db_connection(self.db_path)
        create_tables(self.conn)
        seed_defaults(self.conn)
        self.conn.commit()

    def tearDown(self):
        self.conn.close()
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_settings_singleton_check_constraint_id_2(self):
        """Verify inserting id=2 violates CHECK(id = 1)."""
        with self.assertRaises(sqlite3.IntegrityError) as ctx:
            self.conn.execute(
                "INSERT INTO settings (id, system_prompt, tone_of_voice_prompt) VALUES (2, 'Prompt', 'Tone');"
            )
        self.assertIn("CHECK constraint failed", str(ctx.exception))

    def test_settings_singleton_check_constraint_id_0_and_negative(self):
        """Verify inserting id=0 or negative ID violates CHECK(id = 1)."""
        with self.assertRaises(sqlite3.IntegrityError) as ctx:
            self.conn.execute(
                "INSERT INTO settings (id, system_prompt, tone_of_voice_prompt) VALUES (0, 'Prompt', 'Tone');"
            )
        self.assertIn("CHECK constraint failed", str(ctx.exception))

        with self.assertRaises(sqlite3.IntegrityError) as ctx:
            self.conn.execute(
                "INSERT INTO settings (id, system_prompt, tone_of_voice_prompt) VALUES (-5, 'Prompt', 'Tone');"
            )
        self.assertIn("CHECK constraint failed", str(ctx.exception))

    def test_settings_singleton_duplicate_primary_key(self):
        """Verify attempting to insert a duplicate id=1 violates PRIMARY KEY / UNIQUE constraint."""
        with self.assertRaises(sqlite3.IntegrityError) as ctx:
            self.conn.execute(
                "INSERT INTO settings (id, system_prompt, tone_of_voice_prompt) VALUES (1, 'Prompt', 'Tone');"
            )
        self.assertTrue(
            "UNIQUE constraint failed" in str(ctx.exception) or "PRIMARY KEY" in str(ctx.exception)
        )

    def test_services_unique_name_constraint(self):
        """Verify inserting duplicate service name violates UNIQUE constraint."""
        # 'UX/UI Design' is seeded by default
        with self.assertRaises(sqlite3.IntegrityError) as ctx:
            self.conn.execute("INSERT INTO services (name) VALUES ('UX/UI Design');")
        self.assertIn("UNIQUE constraint failed", str(ctx.exception))

    def test_rfp_services_fk_violation_nonexistent_rfp(self):
        """Verify inserting into rfp_services with nonexistent rfp_id violates foreign keys."""
        cur = self.conn.execute("SELECT id FROM services LIMIT 1;")
        service_id = cur.fetchone()[0]

        with self.assertRaises(sqlite3.IntegrityError) as ctx:
            self.conn.execute(
                "INSERT INTO rfp_services (rfp_id, service_id) VALUES (999999, ?);",
                (service_id,)
            )
        self.assertIn("FOREIGN KEY constraint failed", str(ctx.exception))

    def test_rfp_services_fk_violation_nonexistent_service(self):
        """Verify inserting into rfp_services with nonexistent service_id violates foreign keys."""
        cur = self.conn.execute("INSERT INTO rfps (client_name) VALUES ('Acme Corp');")
        rfp_id = cur.lastrowid

        with self.assertRaises(sqlite3.IntegrityError) as ctx:
            self.conn.execute(
                "INSERT INTO rfp_services (rfp_id, service_id) VALUES (?, 999999);",
                (rfp_id,)
            )
        self.assertIn("FOREIGN KEY constraint failed", str(ctx.exception))

    def test_kb_document_services_fk_violation_nonexistent_kb_doc(self):
        """Verify inserting into kb_document_services with nonexistent kb_document_id violates foreign keys."""
        cur = self.conn.execute("SELECT id FROM services LIMIT 1;")
        service_id = cur.fetchone()[0]

        with self.assertRaises(sqlite3.IntegrityError) as ctx:
            self.conn.execute(
                "INSERT INTO kb_document_services (kb_document_id, service_id) VALUES (999999, ?);",
                (service_id,)
            )
        self.assertIn("FOREIGN KEY constraint failed", str(ctx.exception))

    def test_kb_document_services_fk_violation_nonexistent_service(self):
        """Verify inserting into kb_document_services with nonexistent service_id violates foreign keys."""
        cur = self.conn.execute(
            "INSERT INTO kb_documents (type, title, content) VALUES ('case_study', 'Doc', 'Content');"
        )
        kb_id = cur.lastrowid

        with self.assertRaises(sqlite3.IntegrityError) as ctx:
            self.conn.execute(
                "INSERT INTO kb_document_services (kb_document_id, service_id) VALUES (?, 999999);",
                (kb_id,)
            )
        self.assertIn("FOREIGN KEY constraint failed", str(ctx.exception))

    def test_cascade_delete_rfp(self):
        """Verify deleting an RFP cascades cleanly to all dependent junction, section, note, and question tables."""
        # 1. Create RFP
        cur = self.conn.execute("INSERT INTO rfps (client_name) VALUES ('Cascade Client');")
        rfp_id = cur.lastrowid

        # 2. Add dependencies
        cur = self.conn.execute("SELECT id FROM services LIMIT 1;")
        service_id = cur.fetchone()[0]
        self.conn.execute("INSERT INTO rfp_services (rfp_id, service_id) VALUES (?, ?);", (rfp_id, service_id))

        cur = self.conn.execute(
            "INSERT INTO rfp_sections (rfp_id, heading, original_text) VALUES (?, 'Heading 1', 'Content 1');",
            (rfp_id,)
        )
        section_id = cur.lastrowid

        self.conn.execute("INSERT INTO rfp_notes (rfp_id, section_id, raw_content) VALUES (?, ?, 'AM note');", (rfp_id, section_id))
        self.conn.execute("INSERT INTO open_questions (rfp_id, section_id, question) VALUES (?, ?, 'Any gap?');", (rfp_id, section_id))
        self.conn.commit()

        # Check records exist
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM rfp_services WHERE rfp_id = ?;", (rfp_id,)).fetchone()[0], 1)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM rfp_sections WHERE rfp_id = ?;", (rfp_id,)).fetchone()[0], 1)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM rfp_notes WHERE rfp_id = ?;", (rfp_id,)).fetchone()[0], 1)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM open_questions WHERE rfp_id = ?;", (rfp_id,)).fetchone()[0], 1)

        # 3. Delete RFP
        self.conn.execute("DELETE FROM rfps WHERE id = ?;", (rfp_id,))
        self.conn.commit()

        # 4. Verify all cascaded records are 0
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM rfp_services WHERE rfp_id = ?;", (rfp_id,)).fetchone()[0], 0)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM rfp_sections WHERE rfp_id = ?;", (rfp_id,)).fetchone()[0], 0)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM rfp_notes WHERE rfp_id = ?;", (rfp_id,)).fetchone()[0], 0)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM open_questions WHERE rfp_id = ?;", (rfp_id,)).fetchone()[0], 0)

    def test_cascade_delete_service(self):
        """Verify deleting a service cascades to rfp_services and kb_document_services, and sets price_items.service_id to NULL."""
        # 1. Create a service
        cur = self.conn.execute("INSERT INTO services (name) VALUES ('Bespoke Cloud Infrastructure');")
        service_id = cur.lastrowid

        # 2. Associate with RFP
        cur = self.conn.execute("INSERT INTO rfps (client_name) VALUES ('Cloud RFP');")
        rfp_id = cur.lastrowid
        self.conn.execute("INSERT INTO rfp_services (rfp_id, service_id) VALUES (?, ?);", (rfp_id, service_id))

        # 3. Associate with KB Document
        cur = self.conn.execute("INSERT INTO kb_documents (type, title, content) VALUES ('pitch_deck', 'Deck', 'Cloud pitch');")
        kb_id = cur.lastrowid
        self.conn.execute("INSERT INTO kb_document_services (kb_document_id, service_id) VALUES (?, ?);", (kb_id, service_id))

        # 4. Associate with Price Item
        cur = self.conn.execute("INSERT INTO price_items (service_id, description, unit, amount) VALUES (?, 'Cloud Setup', 'fixed', 5000);", (service_id,))
        price_item_id = cur.lastrowid
        self.conn.commit()

        # 5. Delete service
        self.conn.execute("DELETE FROM services WHERE id = ?;", (service_id,))
        self.conn.commit()

        # 6. Verify junction rows deleted
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM rfp_services WHERE service_id = ?;", (service_id,)).fetchone()[0], 0)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM kb_document_services WHERE service_id = ?;", (service_id,)).fetchone()[0], 0)

        # 7. Verify price item retained with NULL service_id
        price_row = self.conn.execute("SELECT service_id, description, amount FROM price_items WHERE id = ?;", (price_item_id,)).fetchone()
        self.assertIsNotNone(price_row)
        self.assertIsNone(price_row["service_id"])
        self.assertEqual(price_row["description"], "Cloud Setup")
        self.assertEqual(price_row["amount"], 5000)

    def test_cascade_delete_section(self):
        """Verify deleting a section cascades to section-specific notes and open questions."""
        cur = self.conn.execute("INSERT INTO rfps (client_name) VALUES ('Section Cascade Client');")
        rfp_id = cur.lastrowid

        cur = self.conn.execute("INSERT INTO rfp_sections (rfp_id, heading, original_text) VALUES (?, 'S1', 'T1');", (rfp_id,))
        sec_id = cur.lastrowid

        cur = self.conn.execute("INSERT INTO rfp_notes (rfp_id, section_id, raw_content) VALUES (?, ?, 'Section note');", (rfp_id, sec_id))
        note_id = cur.lastrowid

        cur = self.conn.execute("INSERT INTO open_questions (rfp_id, section_id, question) VALUES (?, ?, 'Question on S1');", (rfp_id, sec_id))
        q_id = cur.lastrowid
        self.conn.commit()

        # Delete section
        self.conn.execute("DELETE FROM rfp_sections WHERE id = ?;", (sec_id,))
        self.conn.commit()

        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM rfp_notes WHERE id = ?;", (note_id,)).fetchone()[0], 0)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM open_questions WHERE id = ?;", (q_id,)).fetchone()[0], 0)


class TestAPIStressAndMalformedPayloads(unittest.TestCase):
    """Empirically test API resilience against malformed, hostile, and edge-case payloads."""

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.tmp.name
        self.tmp.close()
        init_db(self.db_path)

        def override_get_db():
            conn = get_db_connection(self.db_path)
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

        app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    # --- Settings API Stress ---

    def test_settings_put_invalid_boolean_type(self):
        """Verify non-boolean string for mock_google_export returns 422 Unprocessable Entity."""
        res = self.client.put("/api/settings", json={"mock_google_export": "not_a_bool"})
        self.assertEqual(res.status_code, 422)

    def test_settings_put_prompts_below_minimum_length(self):
        """Verify prompt shorter than 10 characters returns 422."""
        res = self.client.put("/api/settings", json={"system_prompt": "too short"})
        self.assertEqual(res.status_code, 422)

        res = self.client.put("/api/settings", json={"tone_of_voice_prompt": "short"})
        self.assertEqual(res.status_code, 422)

    def test_settings_put_empty_model_strings(self):
        """Verify empty string for classification_model or generation_model returns 422."""
        res = self.client.put("/api/settings", json={"classification_model": ""})
        self.assertEqual(res.status_code, 422)

        res = self.client.put("/api/settings", json={"generation_model": ""})
        self.assertEqual(res.status_code, 422)

    def test_settings_put_empty_payload(self):
        """Verify empty dictionary payload returns 200 without corrupting settings."""
        res = self.client.put("/api/settings", json={})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["id"], 1)
        self.assertEqual(data["classification_model"], "gemini-2.5-flash")

    def test_settings_put_unknown_fields_safely_ignored(self):
        """Verify unrecognized fields do not cause SQL error or injection."""
        res = self.client.put("/api/settings", json={
            "classification_model": "gemini-2.0-flash",
            "injected_field": "'; DROP TABLE settings; --"
        })
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["classification_model"], "gemini-2.0-flash")

        # Verify table still intact
        health = self.client.get("/api/health")
        self.assertEqual(health.json()["database"], "connected")

    def test_settings_put_malformed_json_syntax(self):
        """Verify syntactically invalid JSON payload returns 422."""
        res = self.client.put(
            "/api/settings",
            content="{bad json",
            headers={"Content-Type": "application/json"}
        )
        self.assertEqual(res.status_code, 422)

    # --- Services API Stress ---

    def test_services_post_empty_or_whitespace_name(self):
        """Verify empty or pure-whitespace service name returns 400 Bad Request."""
        res = self.client.post("/api/services", json={"name": ""})
        self.assertIn(res.status_code, [400, 422])

        res = self.client.post("/api/services", json={"name": "     "})
        self.assertEqual(res.status_code, 400)
        self.assertIn("cannot be empty or whitespace", res.json()["detail"])

    def test_services_post_missing_or_null_name(self):
        """Verify missing or null name returns 422 Unprocessable Entity."""
        res = self.client.post("/api/services", json={})
        self.assertEqual(res.status_code, 422)

        res = self.client.post("/api/services", json={"name": None})
        self.assertEqual(res.status_code, 422)

    def test_services_post_invalid_type_name(self):
        """Verify non-string name returns 422."""
        res = self.client.post("/api/services", json={"name": 9999})
        self.assertEqual(res.status_code, 422)

    def test_services_post_name_exceeding_max_length(self):
        """Verify name exceeding 200 chars returns 422."""
        res = self.client.post("/api/services", json={"name": "A" * 201})
        self.assertEqual(res.status_code, 422)

    def test_services_post_case_insensitive_duplicate(self):
        """Verify case-insensitive duplicate service name returns 409 Conflict."""
        # 'UX/UI Design' already exists
        res = self.client.post("/api/services", json={"name": "ux/ui design"})
        self.assertEqual(res.status_code, 409)
        self.assertIn("already exists", res.json()["detail"])

    def test_services_post_whitespace_padded_duplicate(self):
        """Verify leading/trailing whitespace padded duplicate returns 409 Conflict."""
        res = self.client.post("/api/services", json={"name": "   UX/UI Design   "})
        self.assertEqual(res.status_code, 409)
        self.assertIn("already exists", res.json()["detail"])

    def test_services_delete_nonexistent_id(self):
        """Verify deleting non-existent service ID returns 404."""
        res = self.client.delete("/api/services/999999")
        self.assertEqual(res.status_code, 404)
        self.assertIn("not found", res.json()["detail"])

    def test_services_delete_invalid_id_type(self):
        """Verify non-integer service ID returns 422."""
        res = self.client.delete("/api/services/not-an-int")
        self.assertEqual(res.status_code, 422)

    def test_services_delete_negative_id(self):
        """Verify negative service ID returns 404."""
        res = self.client.delete("/api/services/-1")
        self.assertEqual(res.status_code, 404)


if __name__ == "__main__":
    unittest.main(verbosity=2)

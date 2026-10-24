"""Unit and integration tests for Backend Foundations (F02, F03, F04).

Covers:
1. SQLite Database Schema & PRAGMAs (WAL mode, Foreign Keys ON, Busy Timeout)
2. All 10 tables existence and schema integrity
3. Settings singleton constraint CHECK(id = 1)
4. Foreign Key cascade deletes & SET NULL behavior
5. Settings CRUD operations & defaults
6. Services CRUD operations, duplicate prevention, and deletion
7. FastAPI endpoint verification (/api/health, /api/settings, /api/services)
"""

import os
import sys
from pathlib import Path
import sqlite3
import tempfile
import unittest

import glob

# Ensure backend root is on sys.path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

venv_pkgs = glob.glob(str(backend_dir.parent / ".venv" / "lib" / "python*" / "site-packages"))
for p in venv_pkgs:
    if p not in sys.path:
        sys.path.insert(0, p)

from app.database import get_db_connection, init_db
from app.models import (
    DEFAULT_CLASSIFICATION_MODEL,
    DEFAULT_GENERATION_MODEL,
    DEFAULT_SERVICES,
    DEFAULT_SYSTEM_PROMPT,
    DEFAULT_TONE_PROMPT,
    create_tables,
    seed_defaults,
)


class TestDatabaseSchemaAndPragmas(unittest.TestCase):
    """Test SQLite connection pragmas, DDL schema, and relational integrity constraints."""

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

    def test_pragmas_enforced(self):
        """Verify foreign keys are enabled and WAL mode is active."""
        cur = self.conn.execute("PRAGMA foreign_keys;")
        self.assertEqual(cur.fetchone()[0], 1)

        cur = self.conn.execute("PRAGMA journal_mode;")
        self.assertEqual(cur.fetchone()[0].lower(), "wal")

    def test_all_ten_tables_exist(self):
        """Verify all 10 schema tables exist in the database."""
        cur = self.conn.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [r[0] for r in cur.fetchall() if not r[0].startswith("sqlite_")]
        expected = [
            "kb_document_services",
            "kb_documents",
            "open_questions",
            "price_items",
            "rfp_notes",
            "rfp_sections",
            "rfp_services",
            "rfps",
            "services",
            "settings",
        ]
        self.assertEqual(sorted(tables), sorted(expected))

    def test_settings_singleton_constraint(self):
        """Verify settings table allows only row id = 1."""
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                "INSERT INTO settings (id, system_prompt, tone_of_voice_prompt) VALUES (2, 'a', 'b');"
            )

    def test_services_unique_name_constraint(self):
        """Verify duplicate service name raises IntegrityError."""
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute("INSERT INTO services (name) VALUES (?);", (DEFAULT_SERVICES[0],))

    def test_cascade_delete_rfp(self):
        """Verify deleting an RFP cascades to rfp_services, rfp_sections, rfp_notes, and open_questions."""
        cur = self.conn.execute("INSERT INTO rfps (client_name) VALUES ('Test Client');")
        rfp_id = cur.lastrowid

        cur = self.conn.execute("SELECT id FROM services LIMIT 1;")
        service_id = cur.fetchone()[0]

        self.conn.execute(
            "INSERT INTO rfp_services (rfp_id, service_id) VALUES (?, ?);",
            (rfp_id, service_id)
        )
        cur = self.conn.execute(
            "INSERT INTO rfp_sections (rfp_id, heading, original_text) VALUES (?, 'Section 1', 'Req');",
            (rfp_id,)
        )
        section_id = cur.lastrowid
        self.conn.execute(
            "INSERT INTO rfp_notes (rfp_id, raw_content) VALUES (?, 'AM note');",
            (rfp_id,)
        )
        self.conn.execute(
            "INSERT INTO open_questions (rfp_id, section_id, question) VALUES (?, ?, 'Gap?');",
            (rfp_id, section_id)
        )
        self.conn.commit()

        # Delete RFP
        self.conn.execute("DELETE FROM rfps WHERE id = ?;", (rfp_id,))
        self.conn.commit()

        # Assert all cascaded records are deleted
        self.assertEqual(
            self.conn.execute("SELECT COUNT(*) FROM rfp_services WHERE rfp_id = ?;", (rfp_id,)).fetchone()[0], 0
        )
        self.assertEqual(
            self.conn.execute("SELECT COUNT(*) FROM rfp_sections WHERE rfp_id = ?;", (rfp_id,)).fetchone()[0], 0
        )
        self.assertEqual(
            self.conn.execute("SELECT COUNT(*) FROM rfp_notes WHERE rfp_id = ?;", (rfp_id,)).fetchone()[0], 0
        )
        self.assertEqual(
            self.conn.execute("SELECT COUNT(*) FROM open_questions WHERE rfp_id = ?;", (rfp_id,)).fetchone()[0], 0
        )

    def test_price_items_on_delete_service_set_null(self):
        """Verify deleting a service sets price_items.service_id to NULL rather than deleting or failing."""
        cur = self.conn.execute("INSERT INTO services (name) VALUES ('Temporary Service');")
        srv_id = cur.lastrowid

        cur = self.conn.execute(
            "INSERT INTO price_items (service_id, description, unit, amount) VALUES (?, 'Audit', 'fixed', 500);",
            (srv_id,)
        )
        item_id = cur.lastrowid
        self.conn.commit()

        self.conn.execute("DELETE FROM services WHERE id = ?;", (srv_id,))
        self.conn.commit()

        row = self.conn.execute("SELECT service_id FROM price_items WHERE id = ?;", (item_id,)).fetchone()
        self.assertIsNotNone(row)
        self.assertIsNone(row[0])


class TestSettingsAndServicesCRUD(unittest.TestCase):
    """Test business logic and CRUD operations for Settings and Services."""

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.tmp.name
        self.tmp.close()
        init_db(self.db_path)
        self.conn = get_db_connection(self.db_path)

    def tearDown(self):
        self.conn.close()
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_default_settings_seeded(self):
        """Verify initial settings singleton contains expected default values."""
        row = self.conn.execute("SELECT * FROM settings WHERE id = 1;").fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["classification_model"], DEFAULT_CLASSIFICATION_MODEL)
        self.assertEqual(row["generation_model"], DEFAULT_GENERATION_MODEL)
        self.assertEqual(row["mock_google_export"], 1)
        self.assertEqual(row["system_prompt"], DEFAULT_SYSTEM_PROMPT)
        self.assertEqual(row["tone_of_voice_prompt"], DEFAULT_TONE_PROMPT)

    def test_update_settings(self):
        """Verify updating settings persists modified fields without corrupting untouched fields."""
        self.conn.execute(
            """
            UPDATE settings SET
                classification_model = 'gemini-1.5-pro',
                claude_api_key = 'sk-ant-test-key',
                mock_google_export = 0
            WHERE id = 1;
            """
        )
        self.conn.commit()

        row = self.conn.execute("SELECT * FROM settings WHERE id = 1;").fetchone()
        self.assertEqual(row["classification_model"], "gemini-1.5-pro")
        self.assertEqual(row["claude_api_key"], "sk-ant-test-key")
        self.assertEqual(row["mock_google_export"], 0)
        # Untouched fields remain intact
        self.assertEqual(row["generation_model"], DEFAULT_GENERATION_MODEL)
        self.assertEqual(row["system_prompt"], DEFAULT_SYSTEM_PROMPT)

    def test_default_services_seeded(self):
        """Verify initial 5 default services are pre-populated."""
        rows = self.conn.execute("SELECT name FROM services ORDER BY name ASC;").fetchall()
        service_names = [r["name"] for r in rows]
        for expected_service in DEFAULT_SERVICES:
            self.assertIn(expected_service, service_names)

    def test_add_and_delete_service(self):
        """Verify adding a new service and deleting it."""
        cur = self.conn.execute("INSERT INTO services (name) VALUES ('Mobile App Development');")
        self.conn.commit()
        new_id = cur.lastrowid

        row = self.conn.execute("SELECT name FROM services WHERE id = ?;", (new_id,)).fetchone()
        self.assertEqual(row["name"], "Mobile App Development")

        self.conn.execute("DELETE FROM services WHERE id = ?;", (new_id,))
        self.conn.commit()

        row = self.conn.execute("SELECT name FROM services WHERE id = ?;", (new_id,)).fetchone()
        self.assertIsNone(row)


# ---------------------------------------------------------------------------
# FastAPI TestClient Endpoint Verification (if installed)
# ---------------------------------------------------------------------------

try:
    from fastapi.testclient import TestClient
    from app.main import app
    from app.database import get_db

    HAS_TEST_CLIENT = True
except ImportError:
    HAS_TEST_CLIENT = False


@unittest.skipUnless(HAS_TEST_CLIENT, "FastAPI / TestClient not installed in current environment")
class TestFastAPIEndpoints(unittest.TestCase):
    """Integration test suite executing HTTP requests against FastAPI routers."""

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

    def test_health_check(self):
        """Verify GET /api/health returns 200 and connected status."""
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["database"], "connected")

    def test_get_settings_api(self):
        """Verify GET /api/settings returns settings object."""
        response = self.client.get("/api/settings")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], 1)
        self.assertEqual(data["classification_model"], DEFAULT_CLASSIFICATION_MODEL)
        self.assertTrue(data["mock_google_export"])

    def test_put_settings_api(self):
        """Verify PUT /api/settings updates fields and never echoes secrets in full."""
        payload = {
            "classification_model": "gemini-2.0-flash",
            "mock_google_export": False,
            "claude_api_key": "test-key-123"
        }
        response = self.client.put("/api/settings", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["classification_model"], "gemini-2.0-flash")
        self.assertFalse(data["mock_google_export"])
        # Secrets are masked on read: only the last four characters are revealed
        self.assertNotEqual(data["claude_api_key"], "test-key-123")
        self.assertTrue(data["claude_api_key"].endswith("-123"))
        self.assertTrue(data["claude_api_key"].startswith("••••"))

        # Stored value is intact
        conn = get_db_connection(self.db_path)
        stored = conn.execute("SELECT claude_api_key FROM settings WHERE id = 1;").fetchone()["claude_api_key"]
        conn.close()
        self.assertEqual(stored, "test-key-123")

    def test_put_settings_masked_echo_does_not_overwrite(self):
        """Re-submitting the masked value (as an unchanged form would) must not clobber the stored key."""
        self.client.put("/api/settings", json={"gemini_api_key": "real-gemini-key-9999"})
        masked = self.client.get("/api/settings").json()["gemini_api_key"]
        self.assertTrue(masked.startswith("••••"))

        response = self.client.put("/api/settings", json={"gemini_api_key": masked, "weight_won": 1.5})
        self.assertEqual(response.status_code, 200)

        conn = get_db_connection(self.db_path)
        row = conn.execute("SELECT gemini_api_key, weight_won FROM settings WHERE id = 1;").fetchone()
        conn.close()
        self.assertEqual(row["gemini_api_key"], "real-gemini-key-9999")
        self.assertEqual(float(row["weight_won"]), 1.5)

        # Explicit empty string still clears the key
        self.client.put("/api/settings", json={"gemini_api_key": ""})
        conn = get_db_connection(self.db_path)
        cleared = conn.execute("SELECT gemini_api_key FROM settings WHERE id = 1;").fetchone()["gemini_api_key"]
        conn.close()
        self.assertEqual(cleared, "")

    def test_services_crud_api(self):
        """Verify GET, POST, and DELETE /api/services."""
        # 1. List services
        res = self.client.get("/api/services")
        self.assertEqual(res.status_code, 200)
        initial_count = len(res.json())
        self.assertGreaterEqual(initial_count, 5)

        # 2. Create new service
        res = self.client.post("/api/services", json={"name": "DevOps & Cloud"})
        self.assertEqual(res.status_code, 201)
        created = res.json()
        self.assertEqual(created["name"], "DevOps & Cloud")
        service_id = created["id"]

        # 3. Duplicate conflict check
        res = self.client.post("/api/services", json={"name": "DevOps & Cloud"})
        self.assertEqual(res.status_code, 409)

        # 4. Delete service
        res = self.client.delete(f"/api/services/{service_id}")
        self.assertEqual(res.status_code, 200)

        # 5. Delete non-existent service
        res = self.client.delete(f"/api/services/{service_id}")
        self.assertEqual(res.status_code, 404)


if __name__ == "__main__":
    unittest.main(verbosity=2)

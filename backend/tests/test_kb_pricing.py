"""Unit and integration tests for Knowledge Base RAG & Structured Pricing (Milestone 3).

Covers:
1. KB documents seeding and CRUD endpoints (/api/kb)
2. Won-proposal retrieval biasing (won > lost, ratio >= 1.20)
3. Structured pricing seeding and CRUD endpoints (/api/pricing)
4. Pricing input validation (unit enum, non-negative amount, non-blank description)
5. Service deletion referential integrity (409 conflict when in active use)
6. Section draft generation (/api/rfps/{id}/sections/{section_id}/generate)
   - Exact pricing reproduction
   - Boilerplate credentials injection
   - Gap marker detection & auto-registration of open questions
"""

import glob
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

# Ensure backend root and venv packages are on sys.path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

venv_pkgs = glob.glob(str(backend_dir.parent / ".venv" / "lib" / "python*" / "site-packages"))
for p in venv_pkgs:
    if p not in sys.path:
        sys.path.insert(0, p)

from fastapi.testclient import TestClient
from app.main import app
from app.database import get_db, get_db_connection
from app.models import create_tables, seed_defaults
from app.services.vector_store import get_vector_store, sync_vector_store_from_db


class TestKBPricingMilestone3(unittest.TestCase):
    """Test suite covering Milestone 3 endpoints, RAG biasing, and deterministic pricing."""

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.tmp.name
        self.tmp.close()

        self.conn = get_db_connection(self.db_path)
        create_tables(self.conn)
        seed_defaults(self.conn)
        self.conn.commit()

        # Reset and sync vector store
        vs = get_vector_store()
        vs.reset()
        sync_vector_store_from_db(self.conn)

        # Override FastAPI get_db dependency
        def override_get_db():
            conn = get_db_connection(self.db_path)
            try:
                yield conn
                conn.commit()
            finally:
                conn.close()

        app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()
        self.conn.close()
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_01_seed_kb_and_pricing_present(self):
        """Verify initial database seed contains >=5 KB documents and >=6 price items."""
        kb_res = self.client.get("/api/kb")
        self.assertEqual(kb_res.status_code, 200)
        docs = kb_res.json()
        self.assertGreaterEqual(len(docs), 5)

        price_res = self.client.get("/api/pricing")
        self.assertEqual(price_res.status_code, 200)
        prices = price_res.json()
        self.assertGreaterEqual(len(prices), 6)

    def test_02_kb_crud_lifecycle(self):
        """Verify KB document creation, update, and deletion."""
        payload = {
            "title": "Cloud Migration Case Study",
            "content": "Migrated 50 enterprise microservices to AWS with zero downtime.",
            "type": "case_study",
            "outcome": "won",
            "service_ids": [1],
        }
        res = self.client.post("/api/kb", json=payload)
        self.assertEqual(res.status_code, 201)
        doc_id = res.json()["id"]

        # Read back
        get_res = self.client.get(f"/api/kb/{doc_id}")
        self.assertEqual(get_res.status_code, 200)
        self.assertEqual(get_res.json()["title"], payload["title"])

        # Update
        up_res = self.client.put(f"/api/kb/{doc_id}", json={"title": "Updated Cloud Migration Title"})
        self.assertEqual(up_res.status_code, 200)
        self.assertEqual(up_res.json()["title"], "Updated Cloud Migration Title")

        # Delete
        del_res = self.client.delete(f"/api/kb/{doc_id}")
        self.assertEqual(del_res.status_code, 200)
        self.assertEqual(self.client.get(f"/api/kb/{doc_id}").status_code, 404)

    def test_03_won_lost_biasing_formula(self):
        """Verify won proposal achieves higher score than lost proposal (ratio >= 1.20)."""
        # Clean existing KB
        all_docs = self.client.get("/api/kb").json()
        for d in all_docs:
            self.client.delete(f"/api/kb/{d['id']}")

        text = "Headless Statamic CMS 4 platform with Astro and Next.js frontend."
        doc_lost = self.client.post("/api/kb", json={
            "title": "Proposal A (Lost)",
            "content": text,
            "type": "past_proposal",
            "outcome": "lost",
        }).json()

        doc_won = self.client.post("/api/kb", json={
            "title": "Proposal B (Won)",
            "content": text,
            "type": "past_proposal",
            "outcome": "won",
        }).json()

        search_res = self.client.get("/api/kb", params={"query": "Headless Statamic CMS platform"})
        self.assertEqual(search_res.status_code, 200)
        results = search_res.json()

        self.assertEqual(results[0]["id"], doc_won["id"], "Won document must rank #1")
        won_score = results[0]["similarity_score"]
        lost_score = next(r["similarity_score"] for r in results if r["id"] == doc_lost["id"])

        self.assertGreater(won_score, lost_score)
        ratio = won_score / lost_score
        self.assertGreaterEqual(ratio, 1.20, f"Ratio {ratio:.3f} must be >= 1.20")

    def test_04_pricing_validation_and_crud(self):
        """Verify pricing CRUD and strict input validation."""
        # 1. Invalid unit -> 422
        bad_unit = self.client.post("/api/pricing", json={
            "description": "DevOps Engineer",
            "unit": "hourly rate",  # invalid
            "amount": 100.0,
        })
        self.assertEqual(bad_unit.status_code, 422)

        # 2. Negative amount -> 422
        bad_amount = self.client.post("/api/pricing", json={
            "description": "DevOps Engineer",
            "unit": "day rate",
            "amount": -50.0,
        })
        self.assertEqual(bad_amount.status_code, 422)

        # 3. Blank description -> 422
        bad_desc = self.client.post("/api/pricing", json={
            "description": "   ",
            "unit": "day rate",
            "amount": 500.0,
        })
        self.assertEqual(bad_desc.status_code, 422)

        # 4. Valid item creation
        create_res = self.client.post("/api/pricing", json={
            "service_id": 1,
            "description": "Lead Solutions Architect",
            "unit": "day rate",
            "amount": 1100.0,
        })
        self.assertEqual(create_res.status_code, 201)
        pid = create_res.json()["id"]

        # 5. Filter by service_id
        filtered = self.client.get("/api/pricing", params={"service_id": 1}).json()
        self.assertTrue(all(item["service_id"] == 1 for item in filtered))

        # 6. Delete item
        del_res = self.client.delete(f"/api/pricing/{pid}")
        self.assertEqual(del_res.status_code, 200)

    def test_05_service_deletion_referential_integrity(self):
        """Verify deleting a service in active use by an RFP returns HTTP 409 Conflict."""
        # Create service
        srv_res = self.client.post("/api/services", json={"name": "Specialized Blockchain Dev"})
        sid = srv_res.json()["id"]

        # Create RFP referencing service
        rfp_res = self.client.post("/api/rfps", json={
            "client_name": "Web3 Client",
            "service_ids": [sid],
        })
        rfp_id = rfp_res.json()["id"]

        # Attempt delete -> 409
        del_attempt = self.client.delete(f"/api/services/{sid}")
        self.assertEqual(del_attempt.status_code, 409)

        # Delete RFP then service -> 200
        self.client.delete(f"/api/rfps/{rfp_id}")
        del_success = self.client.delete(f"/api/services/{sid}")
        self.assertEqual(del_success.status_code, 200)

    def test_06_exact_pricing_draft_generation(self):
        """Verify draft generation reproduces exact £850.00 and £16,500.00 without estimation."""
        rfp_res = self.client.post("/api/rfps/upload", json={"client_name": "Pricing Generation RFP"})
        rfp_id = rfp_res.json()["rfp_id"]
        self.client.post(f"/api/rfps/{rfp_id}/classify")

        detail = self.client.get(f"/api/rfps/{rfp_id}").json()
        pricing_sec = next(s for s in detail["sections"] if s["classification"] == "pricing")

        gen_res = self.client.post(f"/api/rfps/{rfp_id}/sections/{pricing_sec['id']}/generate")
        self.assertEqual(gen_res.status_code, 200)
        draft = gen_res.json().get("draft_content", "")

        self.assertTrue("850" in draft or "850.00" in draft)
        self.assertTrue("16,500" in draft or "16500" in draft)
        self.assertNotIn("around 800", draft.lower())
        self.assertNotIn("approx", draft.lower())

    def test_07_boilerplate_auto_retrieval(self):
        """Verify boilerplate section auto-retrieves company certifications."""
        rfp_res = self.client.post("/api/rfps/upload", json={"client_name": "Boilerplate RFP"})
        rfp_id = rfp_res.json()["rfp_id"]
        self.client.post(f"/api/rfps/{rfp_id}/classify")

        detail = self.client.get(f"/api/rfps/{rfp_id}").json()
        bp_sec = next(s for s in detail["sections"] if s["classification"] == "boilerplate")

        gen_res = self.client.post(f"/api/rfps/{rfp_id}/sections/{bp_sec['id']}/generate")
        self.assertEqual(gen_res.status_code, 200)
        draft = gen_res.json().get("draft_content", "")
        self.assertIn("ISO 27001", draft)
        self.assertIn("Cyber Essentials", draft)

    def test_08_kb_update_type_validation(self):
        """Verify PUT /api/kb/{id} validates document type and returns HTTP 422 if invalid."""
        kb_docs = self.client.get("/api/kb").json()
        doc_id = kb_docs[0]["id"]
        res = self.client.put(f"/api/kb/{doc_id}", json={"type": "invalid_doc_type"})
        self.assertEqual(res.status_code, 422)

    def test_09_unpriced_service_no_statamic_hallucination(self):
        """Verify RFP requesting an unpriced service emits gap marker and does not inject Statamic rates."""
        srv = self.client.post("/api/services", json={"name": "Penetration Testing Unit"}).json()
        rfp = self.client.post("/api/rfps", json={"client_name": "Defense RFP", "service_ids": [srv["id"]]}).json()
        rfp_id = rfp["id"]

        self.conn.execute(
            "INSERT INTO rfp_sections (rfp_id, heading, original_text, classification) VALUES (?, 'Fees', 'Quote penetration testing', 'pricing');",
            (rfp_id,),
        )
        self.conn.commit()
        sec_id = self.conn.execute("SELECT id FROM rfp_sections WHERE rfp_id = ?;", (rfp_id,)).fetchone()[0]

        res = self.client.post(f"/api/rfps/{rfp_id}/sections/{sec_id}/generate")
        self.assertEqual(res.status_code, 200)
        draft = res.json()["draft_content"]
        self.assertIn("[MORE INFO REQUIRED: Missing pricing data for requested services]", draft)
        self.assertNotIn("Statamic", draft)
        self.assertNotIn("£", draft)


if __name__ == "__main__":
    unittest.main()

"""Empirical Challenger Test Suite for Milestone 3 (F14, F15):
Structured Pricing Management API & Deterministic Pricing Injection Engine.

Authored by challenger_m3_2.
Adversarially tests:
1. Exact price reproduction and absence of approximations (e.g. 1234.56, 999.90, 0.00).
2. Missing pricing gap detection, marker assertion, zero currency symbols, and open question auto-registration.
3. Pricing input validation stress (negative amounts, invalid units, blank descriptions, non-existent service IDs).
4. Service deletion referential integrity (409 Conflict on active RFP association).
"""

import glob
import os
from pathlib import Path
import re
import sys
import tempfile
import unittest

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
from app.services.vector_store import get_vector_store


class BaseChallengerTestCase(unittest.TestCase):
    """Base test setup with isolated temporary database per test."""

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


class TestExactPriceInjectionEmpirical(BaseChallengerTestCase):
    """Challenge 1: Exact Price Injection & Zero Approximation (F15)."""

    def test_01_exact_floating_point_reproduction(self):
        """Verify exact mathematical reproduction of odd float figures (£1,234.56, £999.90, £0.00)."""
        srv = self.client.post("/api/services", json={"name": "Specialized Cloud Architecture"}).json()
        sid = srv["id"]

        test_items = [
            {"description": "Lead Cloud Architect", "unit": "day rate", "amount": 1234.56, "expected": "£1,234.56"},
            {"description": "Monthly SRE SLA Retainer", "unit": "monthly retainer", "amount": 999.90, "expected": "£999.90"},
            {"description": "Zero Cost Discovery Workshop", "unit": "fixed", "amount": 0.00, "expected": "£0.00"},
            {"description": "Enterprise Infrastructure Overhaul", "unit": "fixed", "amount": 1000000.00, "expected": "£1,000,000.00"},
        ]

        for item in test_items:
            res = self.client.post("/api/pricing", json={
                "service_id": sid,
                "description": item["description"],
                "unit": item["unit"],
                "amount": item["amount"],
            })
            self.assertEqual(res.status_code, 201)

        rfp = self.client.post("/api/rfps", json={
            "client_name": "Cloud RFP Client",
            "service_ids": [sid],
        }).json()
        rfp_id = rfp["id"]

        self.conn.execute(
            "INSERT INTO rfp_sections (rfp_id, heading, original_text, classification) VALUES (?, 'Commercial Quotation', 'Provide fee schedule', 'pricing');",
            (rfp_id,),
        )
        self.conn.commit()
        sec = self.conn.execute("SELECT id FROM rfp_sections WHERE rfp_id = ?;", (rfp_id,)).fetchone()
        sec_id = sec["id"]

        gen = self.client.post(f"/api/rfps/{rfp_id}/sections/{sec_id}/generate")
        self.assertEqual(gen.status_code, 200)
        draft = gen.json().get("draft_content", "")

        for item in test_items:
            expected_line = f"- {item['description']}: {item['expected']} ({item['unit']})"
            self.assertIn(expected_line, draft, f"Missing exact formatted line for '{item['description']}'")

    def test_02_zero_approximation_patterns(self):
        """Verify zero approximation or rounding phrases ('around \d+', 'approx', 'approximately', '~', etc.)."""
        srv = self.client.post("/api/services", json={"name": "Data Analytics"}).json()
        sid = srv["id"]

        self.client.post("/api/pricing", json={
            "service_id": sid,
            "description": "Principal Data Scientist",
            "unit": "day rate",
            "amount": 950.55,
        })

        rfp = self.client.post("/api/rfps", json={
            "client_name": "Analytics Client",
            "service_ids": [sid],
        }).json()
        rfp_id = rfp["id"]

        self.conn.execute(
            "INSERT INTO rfp_sections (rfp_id, heading, original_text, classification) VALUES (?, 'Fees', 'Pricing required', 'pricing');",
            (rfp_id,),
        )
        self.conn.commit()
        sec = self.conn.execute("SELECT id FROM rfp_sections WHERE rfp_id = ?;", (rfp_id,)).fetchone()

        gen = self.client.post(f"/api/rfps/{rfp_id}/sections/{sec['id']}/generate")
        draft = gen.json().get("draft_content", "")

        disallowed_patterns = [
            r"around\s+\d+",
            r"\bapprox\b",
            r"\bapproximately\b",
            r"~",
            r"\broughly\b",
            r"\bestimate\b",
            r"\bestimated\b",
        ]
        for pattern in disallowed_patterns:
            match = re.search(pattern, draft, re.IGNORECASE)
            self.assertIsNone(match, f"Found prohibited approximation pattern '{pattern}' in draft: '{match}'")


class TestMissingPricingGapDetectionEmpirical(BaseChallengerTestCase):
    """Challenge 2: Missing Pricing Gap Detection & Non-Hallucination (F15)."""

    def test_01_all_pricing_deleted_produces_marker_and_open_question(self):
        """Verify empty price_items table produces exact marker, no currency symbols, and an open question."""
        all_prices = self.client.get("/api/pricing").json()
        for p in all_prices:
            self.client.delete(f"/api/pricing/{p['id']}")

        rfp = self.client.post("/api/rfps", json={"client_name": "Unpriced Global Client"}).json()
        rfp_id = rfp["id"]

        self.conn.execute(
            "INSERT INTO rfp_sections (rfp_id, heading, original_text, classification) VALUES (?, 'Pricing', 'Please quote fees', 'pricing');",
            (rfp_id,),
        )
        self.conn.commit()
        sec = self.conn.execute("SELECT id FROM rfp_sections WHERE rfp_id = ?;", (rfp_id,)).fetchone()

        gen = self.client.post(f"/api/rfps/{rfp_id}/sections/{sec['id']}/generate")
        self.assertEqual(gen.status_code, 200)
        draft = gen.json().get("draft_content", "")

        self.assertIn("[MORE INFO REQUIRED: Missing pricing data for requested services]", draft)
        self.assertNotIn("£", draft)
        self.assertNotIn("$", draft)
        self.assertNotIn("€", draft)

        questions = self.client.get(f"/api/rfps/{rfp_id}/open-questions").json()
        self.assertGreater(len(questions), 0)
        self.assertEqual(questions[0]["question"], "Missing pricing data for requested services")
        self.assertEqual(questions[0]["status"], "open")

    def test_02_rfp_with_unpriced_service_produces_marker_and_open_question(self):
        """CRITICAL DEFECT TEST: When database contains active seed pricing (e.g. Statamic items),
        an RFP requesting a service with NO configured price items must NOT hallucinate/inject
        unrelated Statamic prices. It MUST produce [MORE INFO REQUIRED: Missing pricing data for requested services],
        zero currency symbols, and register an open question.
        """
        # Seed pricing is active in DB (Statamic Senior Developer, etc. exist)
        srv = self.client.post("/api/services", json={"name": "Cybersecurity & Penetration Testing"}).json()
        sid = srv["id"]

        rfp = self.client.post("/api/rfps", json={
            "client_name": "National Cyber Defense Agency",
            "service_ids": [sid],
        }).json()
        rfp_id = rfp["id"]

        self.conn.execute(
            "INSERT INTO rfp_sections (rfp_id, heading, original_text, classification) VALUES (?, 'Commercial Proposal', 'Detail fee structure for Cybersecurity & Penetration Testing', 'pricing');",
            (rfp_id,),
        )
        self.conn.commit()
        sec = self.conn.execute("SELECT id FROM rfp_sections WHERE rfp_id = ?;", (rfp_id,)).fetchone()

        gen = self.client.post(f"/api/rfps/{rfp_id}/sections/{sec['id']}/generate")
        self.assertEqual(gen.status_code, 200)
        draft = gen.json().get("draft_content", "")

        # Must NOT inject unrelated Statamic prices
        self.assertNotIn("Statamic", draft, "DEFECT: Injected unrelated Statamic pricing into unpriced cybersecurity RFP!")
        
        # Must contain exact gap marker
        self.assertIn(
            "[MORE INFO REQUIRED: Missing pricing data for requested services]",
            draft,
            f"DEFECT: Gap marker missing from draft. Generated draft:\n{draft}"
        )

        # Must have zero currency symbols
        self.assertNotIn("£", draft, f"DEFECT: Hallucinated currency symbol in unpriced RFP: {draft}")
        self.assertNotIn("$", draft)
        self.assertNotIn("€", draft)

        # Must auto-register open question
        questions = self.client.get(f"/api/rfps/{rfp_id}/open-questions").json()
        matching_q = next((q for q in questions if "Missing pricing data" in q["question"]), None)
        self.assertIsNotNone(matching_q, f"DEFECT: Open question was not registered in open_questions table. Got: {questions}")

    def test_03_untagged_rfp_never_fabricates_pricing(self):
        """Verify an untagged RFP never receives rate-card figures it was not linked to."""
        rfp = self.client.post("/api/rfps", json={"client_name": "Generic Untagged RFP"}).json()
        rfp_id = rfp["id"]

        self.conn.execute(
            "INSERT INTO rfp_sections (rfp_id, heading, original_text, classification) VALUES (?, 'Pricing Schedule', 'Provide pricing for Cloud Security and DevOps Support', 'pricing');",
            (rfp_id,),
        )
        self.conn.commit()
        sec = self.conn.execute("SELECT id FROM rfp_sections WHERE rfp_id = ?;", (rfp_id,)).fetchone()

        gen = self.client.post(f"/api/rfps/{rfp_id}/sections/{sec['id']}/generate")
        self.assertEqual(gen.status_code, 200)
        draft = gen.json().get("draft_content", "")

        self.assertNotIn("£", draft, "DEFECT: Untagged RFP asking for Cloud Security received rate-card pricing!")
        self.assertIn("[MORE INFO REQUIRED: Missing pricing data for requested services]", draft)



class TestPricingInputValidationStressEmpirical(BaseChallengerTestCase):
    """Challenge 3: Pricing Input Validation Stress (F14)."""

    def test_01_negative_amounts_rejected_422(self):
        """Verify negative amounts (-10.0, -0.01, tiny negative) return HTTP 422."""
        for amt in [-10.0, -0.01, -1e-9]:
            res = self.client.post("/api/pricing", json={
                "description": "Tester Role",
                "unit": "day rate",
                "amount": amt,
            })
            self.assertEqual(res.status_code, 422, f"Expected 422 for amount={amt}, got {res.status_code}")

    def test_02_invalid_units_rejected_422(self):
        """Verify invalid units ('yearly', 'hourly', '', None, 'DAY RATE') return HTTP 422."""
        for unit in ["yearly", "hourly", "", None, "DAY RATE"]:
            res = self.client.post("/api/pricing", json={
                "description": "Tester Role",
                "unit": unit,
                "amount": 100.0,
            })
            self.assertEqual(res.status_code, 422, f"Expected 422 for unit={unit}, got {res.status_code}")

    def test_03_empty_descriptions_rejected_422(self):
        """Verify empty and whitespace descriptions ('', '   ', '\\n\\t') return HTTP 422."""
        for desc in ["", "   ", "\n\t"]:
            res = self.client.post("/api/pricing", json={
                "description": desc,
                "unit": "day rate",
                "amount": 100.0,
            })
            self.assertEqual(res.status_code, 422, f"Expected 422 for description={desc!r}, got {res.status_code}")

    def test_04_nonexistent_service_id_rejected_400(self):
        """Verify non-existent or negative service_id returns HTTP 400 Bad Request."""
        res1 = self.client.post("/api/pricing", json={
            "service_id": 999999,
            "description": "Tester Role",
            "unit": "day rate",
            "amount": 100.0,
        })
        self.assertEqual(res1.status_code, 400)
        self.assertIn("does not exist", res1.json().get("detail", ""))

    def test_05_update_validation_rejected_422_or_400(self):
        """Verify PUT /api/pricing/{id} validates negative amounts, invalid units, and non-existent services."""
        created = self.client.post("/api/pricing", json={
            "description": "Valid Role",
            "unit": "day rate",
            "amount": 500.0,
        }).json()
        pid = created["id"]

        self.assertEqual(self.client.put(f"/api/pricing/{pid}", json={"amount": -50.0}).status_code, 422)
        self.assertEqual(self.client.put(f"/api/pricing/{pid}", json={"unit": "hourly"}).status_code, 422)
        self.assertEqual(self.client.put(f"/api/pricing/{pid}", json={"description": "   "}).status_code, 422)
        self.assertEqual(self.client.put(f"/api/pricing/{pid}", json={"service_id": 888888}).status_code, 400)


class TestServiceReferentialIntegrityEmpirical(BaseChallengerTestCase):
    """Challenge 4: Service Deletion Referential Integrity (F04, F14)."""

    def test_01_active_rfp_service_deletion_returns_409_conflict(self):
        """Verify deleting a service currently attached to active RFPs returns HTTP 409 Conflict."""
        srv = self.client.post("/api/services", json={"name": "Enterprise SEO Strategy"}).json()
        sid = srv["id"]

        rfp = self.client.post("/api/rfps", json={
            "client_name": "SEO Client",
            "service_ids": [sid],
        }).json()
        rfp_id = rfp["id"]

        del_res = self.client.delete(f"/api/services/{sid}")
        self.assertEqual(del_res.status_code, 409)
        self.assertIn("in use by active RFPs", del_res.json().get("detail", ""))

        # After RFP deletion, service deletion must succeed
        self.client.delete(f"/api/rfps/{rfp_id}")
        del_success = self.client.delete(f"/api/services/{sid}")
        self.assertEqual(del_success.status_code, 200)

    def test_02_delete_nonexistent_service_returns_404(self):
        """Verify deleting non-existent service returns HTTP 404 Not Found."""
        res = self.client.delete("/api/services/999999")
        self.assertEqual(res.status_code, 404)


if __name__ == "__main__":
    unittest.main()

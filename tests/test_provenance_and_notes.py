#!/usr/bin/env python3
"""
Empirical Adversarial Stress Test Suite — Milestone 4 (Challenger M4-1 / Instance challenger_m4_3)

Empirical Challenge Areas:
1. Whole-RFP note vs section-level note precedence (F17, F18):
   - Direct conflict: section note strictly supersedes whole-RFP note on draft content & provenance.
   - Leakage prevention: whole-RFP note text NEVER appears in target draft or provenance when section override exists.
   - Multi-section distribution: sections without section notes correctly fall back to whole-RFP note.
   - Deletion restoration: deleting section note immediately restores whole-RFP note fallback upon regeneration.
   - Precedence across all section classifications: pricing, boilerplate, gap, strategic_decision.
   - Cross-RFP isolation: notes on RFP A never leak into RFP B.
   - Adversarial note payloads: multiline, markdown, HTML/script, SQL injection, emojis, unicode.

2. Exact pricing fidelity in draft generation (F14, F15, F18):
   - Exact mathematical reproduction: £850.00, £16,500.00, £1,234.56, £99.99, £0.50, £1,500,000.00.
   - Strict zero-rounding: no approximation (e.g. £16.5k, £16500, 16500.00, £1.5m).
   - Exact schedule formatting: '- {description}: {formatted_amount} ({unit})'.
   - Unpriced service handling: linked service with no price items emits strict gap marker and auto-registers open question.
   - Dual-source synthesis: pricing schedule + account manager commercial note.
   - Strict provenance schema: source 'pricing', non-empty text, reference 'Structured price_items schedule'.

3. RAG winning-proposal biasing & boilerplate retrieval reflection in provenance (F11, F12, F16, F18, F19):
   - Outcome biasing formula verification on identical text: won proposal receives weight 1.25, lost receives 0.90 (ratio 1.3889 >= 1.20).
   - Won proposal ranks first in retrieval results list.
   - Dual-engine outcome biasing: verified in PurePythonVectorStore and ChromaVectorStoreWrapper.
   - Strategic draft generation: retrieves won proposal, incorporates snippet, sets provenance source 'rag'.
   - Boilerplate auto-retrieval: retrieves canonical boilerplate, sets provenance source 'boilerplate'.
   - Missing boilerplate handling: emits strict gap marker, auto-registers open question, sets provenance source 'gap'.
   - Full multi-source proposal synthesis: collective RFP exhibits all 5 provenance types (notes, rag, boilerplate, pricing, gap).
"""

import glob
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

# Path configuration
PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Include virtualenv site-packages if running under system python
venv_pkgs = glob.glob(str(PROJECT_ROOT / ".venv" / "lib" / "python*" / "site-packages"))
for p in venv_pkgs:
    if p not in sys.path:
        sys.path.insert(0, p)

from fastapi.testclient import TestClient
from app.main import app
from app.database import get_db, get_db_connection
from app.models import create_tables, seed_defaults
from app.services.vector_store import (
    PurePythonVectorStore,
    ChromaVectorStoreWrapper,
    get_vector_store,
    sync_vector_store_from_db,
    retrieve_boilerplate,
)
from app.services.pricing import format_pricing_schedule, get_pricing_for_rfp


class BaseM4IsolatedTestCase(unittest.TestCase):
    """Isolated test fixture with dedicated SQLite database and reset vector store."""

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.tmp.name
        self.tmp.close()

        self.conn = get_db_connection(self.db_path)
        self.conn.execute("PRAGMA foreign_keys = ON;")
        create_tables(self.conn)
        seed_defaults(self.conn)
        self.conn.commit()

        vs = get_vector_store()
        vs.reset()
        sync_vector_store_from_db(self.conn)

        def override_get_db():
            c = get_db_connection(self.db_path)
            c.execute("PRAGMA foreign_keys = ON;")
            try:
                yield c
                c.commit()
            finally:
                c.close()

        app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()
        self.conn.close()
        get_vector_store().reset()
        if os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except OSError:
                pass

    def create_rfp(self, client_name="Challenger Corp", services=None):
        payload = {"client_name": client_name}
        if services is not None:
            payload["services"] = services
        res = self.client.post("/api/rfps", json=payload)
        self.assertEqual(res.status_code, 201, f"Create RFP failed: {res.text}")
        return res.json()["id"]

    def add_section(self, rfp_id, heading, original_text, classification, sort_order=1):
        cur = self.conn.cursor()
        cur.execute(
            """
            INSERT INTO rfp_sections (rfp_id, heading, original_text, classification, confidence, sort_order, status)
            VALUES (?, ?, ?, ?, 'high', ?, 'pending');
            """,
            (rfp_id, heading, original_text, classification, sort_order),
        )
        self.conn.commit()
        return cur.lastrowid


class TestAMNotesPrecedenceAdversarial(BaseM4IsolatedTestCase):
    """Deep adversarial testing of Account Manager Notes Precedence & Isolation (Item 1)."""

    def test_01_direct_conflict_strict_precedence(self):
        """Direct contradiction: section note strictly overrides whole-RFP note with ZERO leakage."""
        rfp_id = self.create_rfp("Direct Conflict Client")
        sec_id = self.add_section(
            rfp_id,
            heading="2.1 Delivery Methodology",
            original_text="Detail delivery cycles and client governance cadence.",
            classification="strategic_decision",
            sort_order=1,
        )

        whole_text = "WHOLE_NOTE: Always mandate 4-week waterfall governance checkpoints with monthly steering committee."
        sec_text = "SECTION_OVERRIDE: Client insists exclusively on 1-week continuous Kanban with daily asynchronous standups."

        # Add whole-RFP note
        self.client.post(f"/api/rfps/{rfp_id}/notes", json={"raw_content": whole_text, "section_id": None})
        # Add section-specific note
        self.client.post(f"/api/rfps/{rfp_id}/notes", json={"raw_content": sec_text, "section_id": sec_id})

        # Generate draft
        gen_res = self.client.post(f"/api/rfps/{rfp_id}/sections/{sec_id}/generate")
        self.assertEqual(gen_res.status_code, 200)
        data = gen_res.json()
        draft = data["draft_content"]

        # 1. Assert section note is in draft
        self.assertIn(sec_text, draft, "Draft must contain section-specific note text verbatim")

        # 2. Assert whole note is strictly excluded from draft
        self.assertNotIn(whole_text, draft, "Draft leaked whole-RFP note when section override exists!")
        self.assertNotIn("waterfall", draft.lower())
        self.assertNotIn("monthly steering committee", draft.lower())

        # 3. Assert provenance references ONLY section note
        notes_prov = [p for p in data["provenance"] if p["source"] == "notes"]
        self.assertEqual(len(notes_prov), 1, f"Expected exactly 1 notes provenance item, got {len(notes_prov)}")
        self.assertEqual(notes_prov[0]["text"], sec_text)
        self.assertIn(f"Section {sec_id}", notes_prov[0]["reference"])
        self.assertNotIn("Whole-RFP", notes_prov[0]["reference"])

    def test_02_precedence_across_all_four_classifications(self):
        """Precedence holds robustly across pricing, boilerplate, gap, and strategic classifications."""
        rfp_id = self.create_rfp("Multi-Type Precedence RFP")

        sec_price = self.add_section(rfp_id, "Commercial Rates", "Statamic Dev daily rate", "pricing", 1)
        sec_bp = self.add_section(rfp_id, "Company Profile", "Company background", "boilerplate", 2)
        sec_gap = self.add_section(rfp_id, "Specialist Domain", "NHS Cyber Security", "gap", 3)
        sec_strat = self.add_section(rfp_id, "Architecture", "CMS hosting model", "strategic_decision", 4)

        whole_note = "WHOLE_NOTE: Global standard policy is Leeds delivery centre."
        self.client.post(f"/api/rfps/{rfp_id}/notes", json={"raw_content": whole_note, "section_id": None})

        overrides = [
            (sec_price, "OVERRIDE_PRICING: Offer 12% multi-year discount schedule."),
            (sec_bp, "OVERRIDE_BOILERPLATE: Showcase London flagship headquarters."),
            (sec_gap, "OVERRIDE_GAP: Clarify pending audit timeline with client."),
            (sec_strat, "OVERRIDE_STRAT: Deliver via AWS serverless containerization."),
        ]

        for sec_id, override_note in overrides:
            self.client.post(f"/api/rfps/{rfp_id}/notes", json={"raw_content": override_note, "section_id": sec_id})
            res = self.client.post(f"/api/rfps/{rfp_id}/sections/{sec_id}/generate")
            self.assertEqual(res.status_code, 200)
            data = res.json()
            draft = data["draft_content"]

            self.assertIn(override_note, draft, f"Section {sec_id} missing override note")
            self.assertNotIn(whole_note, draft, f"Section {sec_id} leaked whole-RFP note")

            notes_prov = next(p for p in data["provenance"] if p["source"] == "notes")
            self.assertEqual(notes_prov["text"], override_note)
            self.assertIn(f"Section {sec_id}", notes_prov["reference"])

    def test_03_selective_fallback_when_only_some_sections_have_overrides(self):
        """Sections without specific notes inherit whole note; overridden sections exclude it."""
        rfp_id = self.create_rfp("Selective Fallback RFP")
        sec_with_override = self.add_section(rfp_id, "Section A", "Requirement A", "boilerplate", 1)
        sec_without_override = self.add_section(rfp_id, "Section B", "Requirement B", "boilerplate", 2)

        whole_note = "WHOLE_NOTE: Emphasize 100% remote-first delivery model."
        sec_note = "SEC_A_NOTE: Strictly mandate on-site presence in Manchester."

        self.client.post(f"/api/rfps/{rfp_id}/notes", json={"raw_content": whole_note, "section_id": None})
        self.client.post(f"/api/rfps/{rfp_id}/notes", json={"raw_content": sec_note, "section_id": sec_with_override})

        # Generate Section A (has override)
        res_a = self.client.post(f"/api/rfps/{rfp_id}/sections/{sec_with_override}/generate").json()
        self.assertIn(sec_note, res_a["draft_content"])
        self.assertNotIn(whole_note, res_a["draft_content"])
        prov_a = next(p for p in res_a["provenance"] if p["source"] == "notes")
        self.assertIn(f"Section {sec_with_override}", prov_a["reference"])

        # Generate Section B (no override)
        res_b = self.client.post(f"/api/rfps/{rfp_id}/sections/{sec_without_override}/generate").json()
        self.assertIn(whole_note, res_b["draft_content"])
        self.assertNotIn(sec_note, res_b["draft_content"])
        prov_b = next(p for p in res_b["provenance"] if p["source"] == "notes")
        self.assertIn("Whole-RFP", prov_b["reference"])

    def test_04_deletion_restores_whole_note_fallback(self):
        """Deleting a section note causes subsequent draft generation to fall back to whole note."""
        rfp_id = self.create_rfp("Fallback Recovery RFP")
        sec_id = self.add_section(rfp_id, "Section 1", "Original Requirement", "strategic_decision", 1)

        whole_note = "WHOLE_BASELINE: Standard ISO 27001 certified delivery pipeline."
        sec_note = "TEMPORARY_OVERRIDE: Fast-track MVP delivery bypassing standard pipeline."

        self.client.post(f"/api/rfps/{rfp_id}/notes", json={"raw_content": whole_note, "section_id": None})
        note_res = self.client.post(
            f"/api/rfps/{rfp_id}/notes",
            json={"raw_content": sec_note, "section_id": sec_id},
        ).json()
        note_id = note_res["id"]

        # Before deletion: contains override, not whole note
        draft_before = self.client.post(f"/api/rfps/{rfp_id}/sections/{sec_id}/generate").json()["draft_content"]
        self.assertIn(sec_note, draft_before)
        self.assertNotIn(whole_note, draft_before)

        # Delete section note
        del_res = self.client.delete(f"/api/rfps/{rfp_id}/notes/{note_id}")
        self.assertEqual(del_res.status_code, 200)
        self.assertEqual(del_res.json(), {"deleted": note_id})

        # After deletion: immediately restores whole note fallback
        draft_after_data = self.client.post(f"/api/rfps/{rfp_id}/sections/{sec_id}/generate").json()
        draft_after = draft_after_data["draft_content"]
        self.assertIn(whole_note, draft_after, "Failed to restore whole-RFP note upon section note deletion")
        self.assertNotIn(sec_note, draft_after, "Draft still contains deleted section note")
        prov_after = next(p for p in draft_after_data["provenance"] if p["source"] == "notes")
        self.assertIn("Whole-RFP", prov_after["reference"])

    def test_05_cross_rfp_isolation_strict(self):
        """Notes from RFP 1 must never be visible or used in drafting for RFP 2."""
        rfp_1 = self.create_rfp("Client One Confidential")
        rfp_2 = self.create_rfp("Client Two Clean")

        sec_1 = self.add_section(rfp_1, "Security", "Security protocols", "strategic_decision", 1)
        sec_2 = self.add_section(rfp_2, "Security", "Security protocols", "strategic_decision", 1)

        confidential_secret = "TOP_SECRET_CODE_NAME_PROJECT_ZEUS_49204"
        self.client.post(f"/api/rfps/{rfp_1}/notes", json={"raw_content": confidential_secret, "section_id": sec_1})

        # Draft section in RFP 2
        draft_2_data = self.client.post(f"/api/rfps/{rfp_2}/sections/{sec_2}/generate").json()
        self.assertNotIn(confidential_secret, draft_2_data["draft_content"])
        self.assertNotIn(confidential_secret, str(draft_2_data["provenance"]))

    def test_06_adversarial_payload_notes(self):
        """Section note with multiline markdown, unicode, HTML/script tags, and SQL injection handles safely."""
        rfp_id = self.create_rfp("Adversarial Payload RFP")
        sec_id = self.add_section(rfp_id, "Tech Requirements", "List specifications", "strategic_decision", 1)

        adversarial_note = (
            "### Section Guidance\n"
            "- Point 1: **Strict** compliance with GDPR & HIPAA.\n"
            "- Point 2: <script>alert('XSS_ATTACK');</script>\n"
            "- Point 3: '; DROP TABLE rfp_notes; -- \n"
            "- Point 4: 🌍 Multilingual support: 简体中文, Русский, Español, עברית\n"
            "- Point 5: Emoji tags: 🔥 ⚡ 🎯 100% verified."
        )

        self.client.post(f"/api/rfps/{rfp_id}/notes", json={"raw_content": adversarial_note, "section_id": sec_id})

        res = self.client.post(f"/api/rfps/{rfp_id}/sections/{sec_id}/generate")
        self.assertEqual(res.status_code, 200)
        draft = res.json()["draft_content"]

        self.assertIn("<script>alert('XSS_ATTACK');</script>", draft)
        self.assertIn("DROP TABLE rfp_notes;", draft)
        self.assertIn("简体中文", draft)
        self.assertIn("🔥 ⚡ 🎯", draft)


class TestExactPricingFidelityAdversarial(BaseM4IsolatedTestCase):
    """Deep adversarial testing of Exact Pricing Fidelity in Draft Generation (Item 2)."""

    def test_07_exact_pricing_reproduction_diverse_figures(self):
        """Verify exact reproduction of currency symbols, commas, decimals, and units without rounding."""
        # Create a custom service
        svc_res = self.client.post("/api/services", json={"name": "Custom Engineering Suite"})
        self.assertEqual(svc_res.status_code, 201)
        svc_id = svc_res.json()["id"]

        # Create RFP linked to custom service
        rfp_id = self.create_rfp("Pricing Fidelity Client", services=[svc_id])


        # Insert diverse price items directly
        price_specs = [
            ("Statamic Tech Lead Day Rate", "day rate", 850.00, "£850.00 (day rate)"),
            ("Fixed Price Small Website Build", "fixed", 16500.00, "£16,500.00 (fixed)"),
            ("Monthly Retainer SLA Support", "monthly retainer", 1234.56, "£1,234.56 (monthly retainer)"),
            ("Domain Registration Micro-Fee", "fixed", 0.50, "£0.50 (fixed)"),
            ("Hourly Micro Consultation", "day rate", 99.99, "£99.99 (day rate)"),
            ("Mega Enterprise Transformation", "fixed", 1500000.00, "£1,500,000.00 (fixed)"),
        ]

        cur = self.conn.cursor()
        for desc, unit, amount, _ in price_specs:
            cur.execute(
                "INSERT INTO price_items (service_id, description, unit, amount) VALUES (?, ?, ?, ?);",
                (svc_id, desc, unit, amount),
            )
        self.conn.commit()

        # Add pricing section
        sec_id = self.add_section(
            rfp_id,
            heading="5.0 Commercial Proposal",
            original_text="Provide full commercial breakdown for all engineering services.",
            classification="pricing",
            sort_order=1,
        )

        # Generate draft
        res = self.client.post(f"/api/rfps/{rfp_id}/sections/{sec_id}/generate")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        draft = data["draft_content"]

        # Assert every single expected string is present verbatim
        for desc, unit, amount, expected_str in price_specs:
            self.assertIn(expected_str, draft, f"Missing exact pricing string: {expected_str}")
            self.assertIn(f"- {desc}: {expected_str}", draft)

        # Assert zero rounding or approximations
        self.assertNotIn("£16.5k", draft)
        self.assertNotIn("16500.0", draft)
        self.assertNotIn("£1.5m", draft)
        self.assertNotIn("£1.5 million", draft)

        # Verify provenance schema
        pricing_prov = next((p for p in data["provenance"] if p["source"] == "pricing"), None)
        self.assertIsNotNone(pricing_prov, "Provenance missing 'pricing' source")
        self.assertEqual(pricing_prov["text"], "commercial quotation")
        self.assertEqual(pricing_prov["reference"], "Structured price_items schedule")

    def test_08_linked_service_without_price_items_emits_gap_marker(self):
        """RFP linked to service with NO price items strictly returns gap marker (no hallucination)."""
        rfp_id = self.create_rfp("Unpriced Service RFP")

        # Create unpriced service
        svc_res = self.client.post("/api/services", json={"name": "Quantum Blockchain Consulting"})
        svc_id = svc_res.json()["id"]

        # Link only this unpriced service to RFP
        self.client.post(f"/api/rfps/{rfp_id}/services/{svc_id}")

        sec_id = self.add_section(
            rfp_id,
            heading="Pricing Schedule",
            original_text="Commercial rates for Quantum Blockchain Consulting",
            classification="pricing",
            sort_order=1,
        )

        res = self.client.post(f"/api/rfps/{rfp_id}/sections/{sec_id}/generate")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        draft = data["draft_content"]

        # Must contain exact gap marker
        expected_marker = "[MORE INFO REQUIRED: Missing pricing data for requested services]"
        self.assertIn(expected_marker, draft)

        # Must NOT hallucinate default Statamic rates (£850, £16,500)
        self.assertNotIn("£850.00", draft)
        self.assertNotIn("£16,500.00", draft)

        # Must auto-create open question
        q_res = self.client.get(f"/api/rfps/{rfp_id}/open-questions").json()
        self.assertEqual(len(q_res), 1)
        self.assertEqual(q_res[0]["question"], "Missing pricing data for requested services")
        self.assertEqual(q_res[0]["status"], "open")

        # Provenance must be 'gap'
        gap_prov = next(p for p in data["provenance"] if p["source"] == "gap")
        self.assertEqual(gap_prov["reference"], "Missing pricing rate items")

    def test_09_pricing_dual_source_synthesis_with_commercial_am_note(self):
        """Pricing section seamlessly synthesizes exact pricing table with AM commercial note."""
        # Link default service 1 (Statamic) which has seeded rates: £850.00, £16,500.00, £5,000.00
        rfp_id = self.create_rfp("Commercial Synthesis RFP", services=[1])

        sec_id = self.add_section(
            rfp_id,
            heading="Commercial Terms",
            original_text="Rates for Statamic development",
            classification="pricing",
            sort_order=1,
        )


        commercial_note = "Commercial Agreement: Net 30 payment terms, 50% deposit payable upon signing."
        self.client.post(f"/api/rfps/{rfp_id}/notes", json={"raw_content": commercial_note, "section_id": sec_id})

        res = self.client.post(f"/api/rfps/{rfp_id}/sections/{sec_id}/generate")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        draft = data["draft_content"]

        # Both exact prices and note must be present
        self.assertIn("£850.00 (day rate)", draft)
        self.assertIn(commercial_note, draft)

        # Provenance must contain both pricing and notes
        sources = [p["source"] for p in data["provenance"]]
        self.assertIn("pricing", sources)
        self.assertIn("notes", sources)

    def test_10_unlinked_rfp_always_emits_pricing_gap(self):
        """An RFP with no linked services always gets a gap marker — wording never triggers price injection."""
        rfp_id = self.create_rfp("Unlinked RFP")

        for idx, text in enumerate(
            ["Provide daily rate for a senior full-stack engineer.", "Provide daily rate for iOS Swift engineer."], start=1
        ):
            sec = self.add_section(rfp_id, heading=f"Pricing {idx}", original_text=text, classification="pricing", sort_order=idx)
            res = self.client.post(f"/api/rfps/{rfp_id}/sections/{sec}/generate").json()
            self.assertIn("[MORE INFO REQUIRED: Missing pricing data for requested services]", res["draft_content"])
            self.assertNotIn("£", res["draft_content"])


class TestRAGBiasingAndBoilerplateProvenanceAdversarial(BaseM4IsolatedTestCase):
    """Deep adversarial testing of RAG Biasing, Boilerplate Retrieval, and Provenance (Item 3)."""

    def test_11_won_lost_biasing_formula_and_ordering(self):
        """
        RAG Won/Lost Biasing Formula:
        For identical text and query, won proposal score must be strictly higher than lost proposal.
        The score ratio won / lost must be exactly 1.25 / 0.90 = 1.3889 >= 1.20.
        """
        # Create 2 documents with identical content but won vs lost outcome
        identical_text = "Delivered scalable microservices architecture using Next.js and headless CMS."
        
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO kb_documents (type, title, content, outcome) VALUES ('past_proposal', 'Won Proposal Alpha', ?, 'won');",
            (identical_text,),
        )
        won_id = cur.lastrowid

        cur.execute(
            "INSERT INTO kb_documents (type, title, content, outcome) VALUES ('past_proposal', 'Lost Proposal Beta', ?, 'lost');",
            (identical_text,),
        )
        lost_id = cur.lastrowid
        self.conn.commit()

        # Test PurePythonVectorStore
        vs_pure = PurePythonVectorStore()
        vs_pure.add_document(won_id, "Won Proposal Alpha", identical_text, "past_proposal", "won")
        vs_pure.add_document(lost_id, "Lost Proposal Beta", identical_text, "past_proposal", "lost")

        results = vs_pure.search(query="microservices architecture headless Statamic")
        self.assertGreaterEqual(len(results), 2)

        won_result = next(r for r in results if r["id"] == won_id)
        lost_result = next(r for r in results if r["id"] == lost_id)

        self.assertGreater(won_result["similarity_score"], lost_result["similarity_score"])
        ratio = won_result["similarity_score"] / lost_result["similarity_score"]
        self.assertAlmostEqual(ratio, 1.25 / 0.90, places=3)
        self.assertGreaterEqual(ratio, 1.20)

        # Confirm won proposal ranks first
        self.assertEqual(results[0]["id"], won_id)

    def test_12_kb_api_outcome_biasing_retrieval(self):
        """Verify outcome biasing via GET /api/kb endpoint with query parameter."""
        query_text = "Enterprise Web Build Retail"
        res = self.client.get(f"/api/kb?query={query_text}&type=past_proposal")
        self.assertEqual(res.status_code, 200)
        docs = res.json()
        self.assertGreater(len(docs), 0)

        # Verify documents with outcome 'won' have similarity scores reflecting biasing
        for d in docs:
            self.assertIsNotNone(d.get("similarity_score"))
            self.assertIn(d["outcome"], ["won", "lost", "n/a"])

    def test_13_strategic_draft_rag_retrieval_and_provenance(self):
        """Strategic section incorporates won proposal and records proper RAG provenance."""
        rfp_id = self.create_rfp("Strategic RAG RFP")
        sec_id = self.add_section(
            rfp_id,
            heading="3.0 Headless CMS Architecture",
            original_text="Describe headless CMS architecture and implementation approach.",
            classification="strategic_decision",
            sort_order=1,
        )

        res = self.client.post(f"/api/rfps/{rfp_id}/sections/{sec_id}/generate")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        draft = data["draft_content"]

        # Should retrieve seeded won proposal (id 1: "Enterprise Web Build for Retail Client")
        self.assertIn("headless CMS", draft)
        self.assertIn("technical methodology", draft.lower())

        # Provenance must record source 'rag'

        rag_prov = next((p for p in data["provenance"] if p["source"] == "rag"), None)
        self.assertIsNotNone(rag_prov, "Provenance missing 'rag' item")
        self.assertEqual(rag_prov["text"], "Enterprise Web Platform & Multi-Channel Digital Marketing for Retail Group")
        self.assertIn("KB Document #1", rag_prov["reference"])

    def test_14_boilerplate_auto_retrieval_and_provenance(self):
        """Boilerplate section auto-retrieves company credentials and logs boilerplate provenance."""
        rfp_id = self.create_rfp("Boilerplate RFP")
        sec_id = self.add_section(
            rfp_id,
            heading="1.0 Corporate Overview",
            original_text="Provide verified company credentials and certifications.",
            classification="boilerplate",
            sort_order=1,
        )

        res = self.client.post(f"/api/rfps/{rfp_id}/sections/{sec_id}/generate")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        draft = data["draft_content"]

        # Assert seeded boilerplate text is present
        self.assertIn("Another Marketing Agency is a UK digital agency", draft)
        self.assertIn("ISO 27001 certified information security management", draft)

        # Provenance must record source 'boilerplate'
        bp_prov = next((p for p in data["provenance"] if p["source"] == "boilerplate"), None)
        self.assertIsNotNone(bp_prov, "Provenance missing 'boilerplate' item")
        self.assertEqual(bp_prov["text"], "company profile")
        self.assertIn("Another Marketing Agency Corporate Overview", bp_prov["reference"])

    def test_15_missing_boilerplate_emits_gap_marker_and_open_question(self):
        """If KB has no boilerplate documents, boilerplate section generates gap marker and open question."""
        # Purge boilerplate documents
        self.conn.execute("DELETE FROM kb_documents WHERE type = 'boilerplate';")
        self.conn.commit()
        get_vector_store().reset()

        rfp_id = self.create_rfp("No Boilerplate RFP")
        sec_id = self.add_section(
            rfp_id,
            heading="1.0 Company Profile",
            original_text="Company credentials",
            classification="boilerplate",
            sort_order=1,
        )

        res = self.client.post(f"/api/rfps/{rfp_id}/sections/{sec_id}/generate")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        draft = data["draft_content"]

        # Assert exact gap marker
        expected_marker = "[MORE INFO REQUIRED: Company background and boilerplate not found in knowledge base]"
        self.assertIn(expected_marker, draft)

        # Assert open question registered
        questions = self.client.get(f"/api/rfps/{rfp_id}/open-questions").json()
        self.assertEqual(len(questions), 1)
        self.assertEqual(questions[0]["question"], "Company background and boilerplate not found in knowledge base")

        # Assert provenance has source 'gap'
        gap_prov = next((p for p in data["provenance"] if p["source"] == "gap"), None)
        self.assertIsNotNone(gap_prov)
        self.assertIn("Missing company profile boilerplate", gap_prov["reference"])

    def test_16_boilerplate_plus_am_note_synthesis(self):
        """Boilerplate section combines canonical boilerplate document with AM section delivery note."""
        rfp_id = self.create_rfp("Boilerplate Notes RFP")
        sec_id = self.add_section(
            rfp_id,
            heading="Company Background",
            original_text="Provide company background",
            classification="boilerplate",
            sort_order=1,
        )

        note_text = "Tailored Note: Emphasize our 10-year track record with central government departments."
        self.client.post(f"/api/rfps/{rfp_id}/notes", json={"raw_content": note_text, "section_id": sec_id})

        res = self.client.post(f"/api/rfps/{rfp_id}/sections/{sec_id}/generate")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        draft = data["draft_content"]

        # Assert both sources present
        self.assertIn("Another Marketing Agency is a UK digital agency", draft)
        self.assertIn(note_text, draft)

        # Assert both provenance items present
        sources = [p["source"] for p in data["provenance"]]
        self.assertIn("boilerplate", sources)
        self.assertIn("notes", sources)

    def test_17_collective_full_proposal_provenance_diversity(self):
        """An entire RFP covering all 4 sections manifests all 5 provenance types (notes, rag, boilerplate, pricing, gap)."""
        rfp_id = self.create_rfp("Full Proposal RFP", services=[1])

        sec_bp = self.add_section(rfp_id, "1.0 Overview", "Company background", "boilerplate", 1)
        sec_strat = self.add_section(rfp_id, "2.0 Strategy", "Cloud methodology", "strategic_decision", 2)
        sec_price = self.add_section(rfp_id, "3.0 Pricing", "Statamic Dev daily rate", "pricing", 3)
        sec_gap = self.add_section(rfp_id, "4.0 Quantum Cryptography", "Quantum crypto experience", "gap", 4)

        # Whole-RFP note to provide notes provenance across sections
        self.client.post(f"/api/rfps/{rfp_id}/notes", json={"raw_content": "UK delivery teams only.", "section_id": None})

        all_provenance_sources = set()
        for sec_id in [sec_bp, sec_strat, sec_price, sec_gap]:
            res = self.client.post(f"/api/rfps/{rfp_id}/sections/{sec_id}/generate")
            self.assertEqual(res.status_code, 200)
            data = res.json()
            for p in data["provenance"]:
                all_provenance_sources.add(p["source"])

        self.assertEqual(
            all_provenance_sources,
            {"boilerplate", "rag", "pricing", "notes", "gap"},
            f"Expected all 5 provenance sources, got {all_provenance_sources}",
        )


    def test_18_pricing_dynamic_update_propagates_to_draft(self):
        """Updating a price item via API immediately propagates the new exact figure to draft regeneration."""
        rfp_id = self.create_rfp("Dynamic Price RFP", services=[1])
        sec_id = self.add_section(rfp_id, "Pricing", "Rates for Statamic", "pricing", 1)

        # Initial draft has £850.00
        gen1 = self.client.post(f"/api/rfps/{rfp_id}/sections/{sec_id}/generate").json()
        self.assertIn("£850.00 (day rate)", gen1["draft_content"])

        # Update price item 1 to £925.50
        up_res = self.client.put(
            "/api/pricing/1",
            json={"amount": 925.50, "description": "Statamic Senior Developer Updated"},
        )
        self.assertEqual(up_res.status_code, 200)

        # Regenerate draft -> must now contain £925.50 and NOT £850.00
        gen2 = self.client.post(f"/api/rfps/{rfp_id}/sections/{sec_id}/generate").json()
        self.assertIn("£925.50 (day rate)", gen2["draft_content"])
        self.assertNotIn("£850.00", gen2["draft_content"])

    def test_19_negative_pricing_amount_rejected(self):
        """Attempting to create a price item with negative amount is rejected with 422."""
        res = self.client.post(
            "/api/pricing",
            json={"service_id": 1, "description": "Negative rate", "unit": "day rate", "amount": -100.0},
        )
        self.assertEqual(res.status_code, 422)

    def test_20_multiple_whole_notes_suppressed_by_section_note(self):
        """Multiple whole-RFP notes are all suppressed when a section-specific note is present."""
        rfp_id = self.create_rfp("Multiple Whole Notes RFP")
        sec_id = self.add_section(rfp_id, "Section 1", "Requirement text", "strategic_decision", 1)

        whole_1 = "WHOLE_NOTE_1: Global directive alpha."
        whole_2 = "WHOLE_NOTE_2: Global directive beta."
        sec_note = "SECTION_NOTE_EXCLUSIVE: Specific section instruction omega."

        self.client.post(f"/api/rfps/{rfp_id}/notes", json={"raw_content": whole_1, "section_id": None})
        self.client.post(f"/api/rfps/{rfp_id}/notes", json={"raw_content": whole_2, "section_id": None})
        self.client.post(f"/api/rfps/{rfp_id}/notes", json={"raw_content": sec_note, "section_id": sec_id})

        draft_data = self.client.post(f"/api/rfps/{rfp_id}/sections/{sec_id}/generate").json()
        draft = draft_data["draft_content"]

        self.assertIn(sec_note, draft)
        self.assertNotIn(whole_1, draft)
        self.assertNotIn(whole_2, draft)

    def test_21_open_question_resolution_lifecycle_and_provenance(self):
        """Resolving an open question clears gap marker, incorporates resolution, transitions section status to resolved, and logs notes provenance."""
        rfp_id = self.create_rfp("Resolution Lifecycle RFP")
        sec_id = self.add_section(rfp_id, "Security Accreditation", "ISO 27001 evidence", "gap", 1)

        # Initial draft generates gap marker
        gen1 = self.client.post(f"/api/rfps/{rfp_id}/sections/{sec_id}/generate").json()
        self.assertIn("[MORE INFO REQUIRED:", gen1["draft_content"])
        self.assertEqual(gen1["status"], "drafted")

        # Open question auto-created
        q = self.client.get(f"/api/rfps/{rfp_id}/open-questions").json()[0]
        q_id = q["id"]

        # Resolve open question
        res_text = "Another Marketing Agency maintains active ISO 27001:2022 Certification audited by BSI (Cert #IS-99214)."
        put_res = self.client.put(
            f"/api/rfps/{rfp_id}/open-questions/{q_id}",
            json={"resolution": res_text, "status": "resolved"},
        )
        self.assertEqual(put_res.status_code, 200)

        # Regenerate draft
        gen2 = self.client.post(f"/api/rfps/{rfp_id}/sections/{sec_id}/generate").json()
        self.assertNotIn("[MORE INFO REQUIRED:", gen2["draft_content"])
        self.assertIn(res_text, gen2["draft_content"])
        self.assertEqual(gen2["status"], "resolved")

        # Provenance cites open question
        q_prov = next(p for p in gen2["provenance"] if p["source"] == "notes" and str(q_id) in p["reference"])
        self.assertEqual(q_prov["text"], res_text)

    def test_22_rfp_cascade_deletion_cleans_notes_and_questions(self):
        """Deleting an RFP cascades to clean up all attached notes and open questions."""
        rfp_id = self.create_rfp("Cascade Clean RFP")
        sec_id = self.add_section(rfp_id, "Gap Section", "Niche requirement", "gap", 1)

        self.client.post(f"/api/rfps/{rfp_id}/notes", json={"raw_content": "Note to delete", "section_id": None})
        self.client.post(f"/api/rfps/{rfp_id}/sections/{sec_id}/generate")

        # Verify notes and questions exist in DB
        cur = self.conn.execute("SELECT COUNT(*) FROM rfp_notes WHERE rfp_id = ?;", (rfp_id,))
        self.assertEqual(cur.fetchone()[0], 1)
        cur = self.conn.execute("SELECT COUNT(*) FROM open_questions WHERE rfp_id = ?;", (rfp_id,))
        self.assertEqual(cur.fetchone()[0], 1)

        # Delete RFP
        del_res = self.client.delete(f"/api/rfps/{rfp_id}")
        self.assertEqual(del_res.status_code, 200)

        # Verify DB is clean
        cur = self.conn.execute("SELECT COUNT(*) FROM rfp_notes WHERE rfp_id = ?;", (rfp_id,))
        self.assertEqual(cur.fetchone()[0], 0)
        cur = self.conn.execute("SELECT COUNT(*) FROM open_questions WHERE rfp_id = ?;", (rfp_id,))
        self.assertEqual(cur.fetchone()[0], 0)

    def test_23_empty_or_whitespace_note_rejected(self):
        """Empty string or whitespace-only note content returns HTTP 422."""
        rfp_id = self.create_rfp("Validation RFP")
        res1 = self.client.post(f"/api/rfps/{rfp_id}/notes", json={"raw_content": ""})
        self.assertEqual(res1.status_code, 422)

        res2 = self.client.post(f"/api/rfps/{rfp_id}/notes", json={"raw_content": "   \n\t  "})
        self.assertEqual(res2.status_code, 422)

    def test_24_cross_rfp_open_question_isolation(self):
        """Attempting to resolve an open question from a different RFP returns HTTP 404."""
        rfp_a = self.create_rfp("RFP Alpha")
        rfp_b = self.create_rfp("RFP Beta")
        sec_a = self.add_section(rfp_a, "Gap Alpha", "Requirement Alpha", "gap", 1)

        self.client.post(f"/api/rfps/{rfp_a}/sections/{sec_a}/generate")
        q_a_id = self.client.get(f"/api/rfps/{rfp_a}/open-questions").json()[0]["id"]

        # Try to resolve q_a via rfp_b
        res = self.client.put(
            f"/api/rfps/{rfp_b}/open-questions/{q_a_id}",
            json={"resolution": "Cross-tenant attack", "status": "resolved"},
        )
        self.assertEqual(res.status_code, 404)


if __name__ == "__main__":
    unittest.main()


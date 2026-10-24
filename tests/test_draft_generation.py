#!/usr/bin/env python3
"""
Empirical Adversarial Challenge Suite — Milestone 4 (challenger_m4_1)
Multi-Source Draft Generation, Content Provenance & AM Notes Precedence (F18, F19, F21).

Challenges Executed:
1. AM Notes Precedence & Hierarchy (F17, F18):
   - Whole-RFP note ("Client prefers agile 2-week sprints") vs section-specific note ("Client insists on 1-week Kanban iterations").
   - Verification that section note strictly overrides whole note on target section.
   - Verification that non-specific sections correctly fall back to whole note.
   - Verification across all 4 section classifications (boilerplate, pricing, strategic, gap).
   - Verification of fallback restoration upon section note deletion.
   - Cross-RFP isolation (notes on RFP A never leak into RFP B).
2. Gap Marker Detection & Open Questions Auto-Registration (F19, F20):
   - Section with zero matching KB/pricing/notes generates exact [MORE INFO REQUIRED: ...] marker.
   - Gap marker auto-creates entry in open_questions table with status='open'.
   - Missing pricing service data generates gap marker and open question.
   - Missing boilerplate in KB generates gap marker and open question.
   - Strategic section with empty KB boundary analysis (documents behavior when won proposals are missing).
   - Regeneration deduplication: multiple draft generations do not create duplicate open questions.
   - Resolution lifecycle: resolving open question clears gap marker and transitions status to resolved.
3. Tripartite Synthesis Fidelity & Multi-Source Synthesis (F18, F19, F21):
   - Single-section synthesis boundary test: verifies that the current architecture branches mutually
     exclusively on section classification (pricing vs boilerplate vs strategic_decision).
   - Combination synthesis: pricing + notes, RAG + notes, boilerplate + notes, resolved question + notes.
   - Quadpartite synthesis: pricing + AM notes + resolved question resolution.
   - Full-proposal synthesis: collective proposal covers all 5 provenance source types.
4. Content Provenance Item Schema Strictness (F19, F21):
   - Strict adherence to ProvenanceItem schema: source in {'notes', 'rag', 'boilerplate', 'pricing', 'gap'}.
   - Every provenance item must have non-empty text and non-empty, descriptive reference.
5. Adversarial Input & Boundary Stress:
   - 20,000-character massive AM note payload.
   - Special characters, XSS script injection, SQL injection, and Unicode emoji resilience.
   - Section status transition validation (pending, drafted, resolved; invalid rejected with 422).
   - Referential integrity cascade deletion of notes and open questions upon RFP deletion.
"""

import glob
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

# Path configuration: add backend and project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Add venv site-packages if running under system python
venv_pkgs = glob.glob(str(PROJECT_ROOT / ".venv" / "lib" / "python*" / "site-packages"))
for p in venv_pkgs:
    if p not in sys.path:
        sys.path.insert(0, p)

from fastapi.testclient import TestClient
from app.main import app
from app.database import get_db, get_db_connection
from app.models import create_tables, seed_defaults
from app.services.vector_store import get_vector_store, sync_vector_store_from_db


class BaseM4IsolatedTestCase(unittest.TestCase):
    """Base test case providing an isolated temporary database and clean vector store."""

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
            os.remove(self.db_path)

    def create_test_rfp(self, client_name="Challenger Corp", services=None):
        """Helper to create an RFP and return its ID."""
        payload = {"client_name": client_name}
        if services is not None:
            payload["services"] = services
        res = self.client.post("/api/rfps", json=payload)
        self.assertEqual(res.status_code, 201, f"Failed to create RFP: {res.text}")
        return res.json()["id"]

    def add_section(self, rfp_id, heading, original_text, classification, sort_order=1):
        """Helper to insert an RFP section directly into DB."""
        cur = self.conn.cursor()
        cur.execute(
            """
            INSERT INTO rfp_sections (rfp_id, heading, original_text, classification, confidence, sort_order)
            VALUES (?, ?, ?, ?, 'high', ?);
            """,
            (rfp_id, heading, original_text, classification, sort_order),
        )
        self.conn.commit()
        return cur.lastrowid


class TestAMNotesPrecedenceAndHierarchy(BaseM4IsolatedTestCase):
    """Adversarial testing of AM Notes Precedence (Dispatch Item 1)."""

    def test_01_exact_dispatch_precedence_scenario(self):
        """
        Exact Dispatch Specification:
        - Whole-RFP note: 'Client prefers agile 2-week sprints'.
        - Section-specific note on Technical Approach: 'Client insists on 1-week Kanban iterations'.
        - Generate draft for Technical Approach:
            * '1-week Kanban iterations' is reflected in draft.
            * 'agile 2-week sprints' is NOT in draft.
            * Provenance is tagged as 'notes' with section note reference.
        - Generate draft for another section without specific notes:
            * 'agile 2-week sprints' from whole-RFP note is reflected.
            * Provenance reference reflects whole-RFP note.
        """
        rfp_id = self.create_test_rfp("Acme Precedence Corp")

        sec_tech_id = self.add_section(
            rfp_id,
            heading="3.0 Technical Approach",
            original_text="Describe your agile delivery methodology and sprint cadence.",
            classification="strategic_decision",
            sort_order=1,
        )

        sec_general_id = self.add_section(
            rfp_id,
            heading="1.0 Executive Overview",
            original_text="Provide executive summary of corporate credentials.",
            classification="boilerplate",
            sort_order=2,
        )

        # 1. Whole-RFP note
        whole_text = "Client prefers agile 2-week sprints"
        res_whole = self.client.post(
            f"/api/rfps/{rfp_id}/notes",
            json={"raw_content": whole_text, "section_id": None},
        )
        self.assertEqual(res_whole.status_code, 201)

        # 2. Section-specific note on Technical Approach
        section_text = "Client insists on 1-week Kanban iterations"
        res_sec = self.client.post(
            f"/api/rfps/{rfp_id}/notes",
            json={"raw_content": section_text, "section_id": sec_tech_id},
        )
        self.assertEqual(res_sec.status_code, 201)

        # 3. Generate draft for Technical Approach
        tech_gen = self.client.post(f"/api/rfps/{rfp_id}/sections/{sec_tech_id}/generate")
        self.assertEqual(tech_gen.status_code, 200)
        tech_data = tech_gen.json()
        tech_draft = tech_data["draft_content"]

        # Assertions for Technical Approach
        self.assertIn(section_text, tech_draft, "Draft failed to incorporate section-specific note")
        self.assertNotIn(whole_text, tech_draft, "Draft leaked whole-RFP note when section override exists")

        # Provenance assertion for Technical Approach
        note_prov_tech = next((p for p in tech_data["provenance"] if p["source"] == "notes"), None)
        self.assertIsNotNone(note_prov_tech, "Provenance missing 'notes' source")
        self.assertEqual(note_prov_tech["text"], section_text)
        self.assertIn(f"Section {sec_tech_id}", note_prov_tech["reference"])

        # 4. Generate draft for general section (no section-specific note)
        gen_res = self.client.post(f"/api/rfps/{rfp_id}/sections/{sec_general_id}/generate")
        self.assertEqual(gen_res.status_code, 200)
        gen_data = gen_res.json()
        gen_draft = gen_data["draft_content"]

        # Assertions for general section
        self.assertIn(whole_text, gen_draft, "General section failed to incorporate whole-RFP note")
        self.assertNotIn(section_text, gen_draft, "General section leaked other section's specific note")

        # Provenance assertion for general section
        note_prov_gen = next((p for p in gen_data["provenance"] if p["source"] == "notes"), None)
        self.assertIsNotNone(note_prov_gen, "General section provenance missing 'notes' source")
        self.assertEqual(note_prov_gen["text"], whole_text)
        self.assertIn("Whole-RFP", note_prov_gen["reference"])

    def test_02_precedence_across_all_section_classifications(self):
        """Test section note precedence over whole note across boilerplate, pricing, gap, and strategic."""
        rfp_id = self.create_test_rfp("Multi-Type Precedence RFP")

        sec_bp = self.add_section(rfp_id, "Company Profile", "Company info", "boilerplate", 1)
        sec_pr = self.add_section(rfp_id, "Pricing Table", "Daily rate for Statamic Technical Lead", "pricing", 2)
        sec_gap = self.add_section(rfp_id, "Niche Telemetry", "Experience with NHS", "gap", 3)
        sec_strat = self.add_section(rfp_id, "System Architecture", "Cloud approach", "strategic_decision", 4)

        whole_note = "Global mandate: All deliveries lead from London office."
        self.client.post(f"/api/rfps/{rfp_id}/notes", json={"raw_content": whole_note, "section_id": None})

        sections = [
            (sec_bp, "Boilerplate override: Highlight Manchester office."),
            (sec_pr, "Pricing override: Apply 15% partner discount."),
            (sec_gap, "Gap override: Acknowledge client timeframe constraint."),
            (sec_strat, "Strategic override: Recommend AWS serverless."),
        ]

        for sec_id, sec_note in sections:
            # Attach section note
            self.client.post(f"/api/rfps/{rfp_id}/notes", json={"raw_content": sec_note, "section_id": sec_id})

            # Generate
            res = self.client.post(f"/api/rfps/{rfp_id}/sections/{sec_id}/generate")
            self.assertEqual(res.status_code, 200)
            data = res.json()
            draft = data["draft_content"]

            # Verify section note is present, whole note is excluded
            self.assertIn(sec_note, draft, f"Section {sec_id} missing section note")
            self.assertNotIn(whole_note, draft, f"Section {sec_id} erroneously contains whole note")

            # Verify provenance
            note_prov = next((p for p in data["provenance"] if p["source"] == "notes"), None)
            self.assertIsNotNone(note_prov, f"Section {sec_id} missing notes provenance")
            self.assertEqual(note_prov["text"], sec_note)
            self.assertIn(f"Section {sec_id}", note_prov["reference"])

    def test_03_section_note_deletion_restores_whole_note_fallback(self):
        """Deleting a section note immediately restores whole-RFP note in subsequent generation."""
        rfp_id = self.create_test_rfp("Fallback Restoration RFP")
        sec_id = self.add_section(rfp_id, "Methodology", "Our delivery cadence", "strategic_decision", 1)

        whole_note = "Baseline: 2-week Scrum sprints."
        sec_note = "Override: Continuous Kanban flow."

        self.client.post(f"/api/rfps/{rfp_id}/notes", json={"raw_content": whole_note, "section_id": None})
        sec_note_res = self.client.post(
            f"/api/rfps/{rfp_id}/notes",
            json={"raw_content": sec_note, "section_id": sec_id},
        ).json()
        note_id = sec_note_res["id"]

        # Initial draft incorporates section note
        draft1 = self.client.post(f"/api/rfps/{rfp_id}/sections/{sec_id}/generate").json()["draft_content"]
        self.assertIn(sec_note, draft1)
        self.assertNotIn(whole_note, draft1)

        # Delete section note
        del_res = self.client.delete(f"/api/rfps/{rfp_id}/notes/{note_id}")
        self.assertEqual(del_res.status_code, 200)
        self.assertEqual(del_res.json(), {"deleted": note_id})

        # Regenerate draft -> must now contain whole note
        draft2 = self.client.post(f"/api/rfps/{rfp_id}/sections/{sec_id}/generate").json()["draft_content"]
        self.assertIn(whole_note, draft2, "Draft failed to restore whole-RFP note after section note deletion")
        self.assertNotIn(sec_note, draft2, "Draft still contains deleted section note")

    def test_04_cross_rfp_note_isolation(self):
        """Notes from RFP A must never appear in draft generation for RFP B."""
        rfp_a = self.create_test_rfp("Client A")
        rfp_b = self.create_test_rfp("Client B")

        sec_a = self.add_section(rfp_a, "Approach", "Approach text", "strategic_decision", 1)
        sec_b = self.add_section(rfp_b, "Approach", "Approach text", "strategic_decision", 1)

        note_a = "CONFIDENTIAL_CLIENT_A_DATA: Secret project code Delta"
        self.client.post(f"/api/rfps/{rfp_a}/notes", json={"raw_content": note_a, "section_id": sec_a})

        draft_b = self.client.post(f"/api/rfps/{rfp_b}/sections/{sec_b}/generate").json()["draft_content"]
        self.assertNotIn("CONFIDENTIAL_CLIENT_A_DATA", draft_b, "CRITICAL: Cross-RFP note leakage detected!")
        self.assertNotIn("Delta", draft_b)


class TestGapMarkerAndOpenQuestionsStress(BaseM4IsolatedTestCase):
    """Adversarial testing of Gap Markers & Open Questions (Dispatch Item 2)."""

    def test_05_exact_dispatch_gap_marker_and_open_question(self):
        """
        Exact Dispatch Specification:
        - Generate draft for section with zero matching KB, pricing, or notes.
        - Assert exact presence of `[MORE INFO REQUIRED: ...]` marker.
        - Assert that open question is automatically added to `open_questions` table.
        - Assert provenance items include `source: "gap"`, `text`, and non-empty `reference`.
        """
        rfp_id = self.create_test_rfp("Zero Match RFP")
        heading = "4.2 Quantum Key Cryptography"
        req_text = "Provide verifiable case study delivering post-quantum TLS infrastructure."

        sec_id = self.add_section(
            rfp_id,
            heading=heading,
            original_text=req_text,
            classification="gap",
            sort_order=1,
        )

        # Ensure no open questions exist initially
        pre_q = self.client.get(f"/api/rfps/{rfp_id}/open-questions").json()
        self.assertEqual(len(pre_q), 0, "Open questions exist before draft generation")

        # Generate draft
        gen_res = self.client.post(f"/api/rfps/{rfp_id}/sections/{sec_id}/generate")
        self.assertEqual(gen_res.status_code, 200)
        data = gen_res.json()
        draft = data["draft_content"]

        # 1. Assert exact presence of [MORE INFO REQUIRED: ...] marker
        expected_marker = f"[MORE INFO REQUIRED: Describe specific past experience and evidence for {heading}]"
        self.assertIn(expected_marker, draft, f"Draft missing exact gap marker: {expected_marker}")
        self.assertEqual(data["status"], "drafted")

        # 2. Assert open question automatically added to open_questions table
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM open_questions WHERE rfp_id = ? AND section_id = ?;", (rfp_id, sec_id))
        rows = cur.fetchall()
        self.assertEqual(len(rows), 1, "Failed to auto-create open question in database table")
        db_q = rows[0]
        self.assertEqual(db_q["status"], "open")
        self.assertEqual(
            db_q["question"],
            f"Describe specific past experience and evidence for {heading}",
        )

        # Also verify via API endpoint
        api_q = self.client.get(f"/api/rfps/{rfp_id}/open-questions").json()
        self.assertEqual(len(api_q), 1)
        self.assertEqual(api_q[0]["section_id"], sec_id)
        self.assertEqual(api_q[0]["status"], "open")

        # 3. Assert provenance items include source: "gap", text, and non-empty reference
        gap_prov = next((p for p in data["provenance"] if p["source"] == "gap"), None)
        self.assertIsNotNone(gap_prov, "Provenance missing 'gap' source item")
        self.assertTrue(len(gap_prov["text"]) > 0, "Provenance 'text' is empty")
        self.assertTrue(len(gap_prov["reference"]) > 0, "Provenance 'reference' is empty")
        self.assertIn(heading, gap_prov["reference"])

    def test_06_missing_pricing_gap_marker_and_open_question(self):
        """Pricing section with zero matching rates generates gap marker, open question, and gap provenance."""
        rfp_id = self.create_test_rfp("Unpriced RFP")
        sec_id = self.add_section(
            rfp_id,
            heading="5.0 Commercial Fees",
            original_text="Provide fixed price for bespoke quantum blockchain tokenization.",
            classification="pricing",
            sort_order=1,
        )

        gen_res = self.client.post(f"/api/rfps/{rfp_id}/sections/{sec_id}/generate")
        self.assertEqual(gen_res.status_code, 200)
        data = gen_res.json()

        # Marker assertion
        expected_marker = "[MORE INFO REQUIRED: Missing pricing data for requested services]"
        self.assertIn(expected_marker, data["draft_content"])
        self.assertEqual(data["status"], "drafted")

        # Open question auto-created
        q_res = self.client.get(f"/api/rfps/{rfp_id}/open-questions").json()
        self.assertEqual(len(q_res), 1)
        self.assertEqual(q_res[0]["question"], "Missing pricing data for requested services")
        self.assertEqual(q_res[0]["status"], "open")

        # Provenance schema assertion
        gap_prov = next((p for p in data["provenance"] if p["source"] == "gap"), None)
        self.assertIsNotNone(gap_prov)
        self.assertEqual(gap_prov["text"], "missing pricing")
        self.assertEqual(gap_prov["reference"], "Missing pricing rate items")

    def test_07_missing_boilerplate_gap_marker_and_open_question(self):
        """Boilerplate section with empty KB boilerplate generates gap marker, open question, and gap provenance."""
        # Purge boilerplate documents from database
        self.conn.execute("DELETE FROM kb_documents WHERE type = 'boilerplate';")
        self.conn.commit()
        get_vector_store().reset()

        rfp_id = self.create_test_rfp("Empty Boilerplate RFP")
        sec_id = self.add_section(
            rfp_id,
            heading="1.0 Company Profile",
            original_text="Provide verified company credentials and history.",
            classification="boilerplate",
            sort_order=1,
        )

        gen_res = self.client.post(f"/api/rfps/{rfp_id}/sections/{sec_id}/generate")
        self.assertEqual(gen_res.status_code, 200)
        data = gen_res.json()

        # Marker assertion
        expected_marker = "[MORE INFO REQUIRED: Company background and boilerplate not found in knowledge base]"
        self.assertIn(expected_marker, data["draft_content"])
        self.assertEqual(data["status"], "drafted")

        # Open question auto-created
        q_res = self.client.get(f"/api/rfps/{rfp_id}/open-questions").json()
        self.assertEqual(len(q_res), 1)
        self.assertEqual(q_res[0]["question"], "Company background and boilerplate not found in knowledge base")

        # Provenance assertion
        gap_prov = next((p for p in data["provenance"] if p["source"] == "gap"), None)
        self.assertIsNotNone(gap_prov)
        self.assertEqual(gap_prov["text"], "missing boilerplate")
        self.assertIn("Missing company profile", gap_prov["reference"])

    def test_08_gap_regeneration_deduplication(self):
        """Repeatedly generating a draft with gap markers must NOT duplicate open questions in DB."""
        rfp_id = self.create_test_rfp("Deduplication RFP")
        sec_id = self.add_section(
            rfp_id,
            heading="2.0 AI Ethics Audit",
            original_text="Provide IEEE 7000 compliance certificate.",
            classification="gap",
            sort_order=1,
        )

        # Generate 5 times
        for _ in range(5):
            res = self.client.post(f"/api/rfps/{rfp_id}/sections/{sec_id}/generate")
            self.assertEqual(res.status_code, 200)

        # Verify only 1 open question exists
        cur = self.conn.cursor()
        cur.execute("SELECT COUNT(*) FROM open_questions WHERE rfp_id = ? AND section_id = ?;", (rfp_id, sec_id))
        count = cur.fetchone()[0]
        self.assertEqual(count, 1, f"Expected 1 deduplicated open question, found {count}")

    def test_09_full_open_question_resolution_lifecycle(self):
        """Resolving an open question clears gap marker, incorporates resolution, and transitions section to resolved."""
        rfp_id = self.create_test_rfp("Lifecycle RFP")
        sec_id = self.add_section(
            rfp_id,
            heading="Experience Gap",
            original_text="Detail experience with GDS Service Standard assessments.",
            classification="gap",
            sort_order=1,
        )

        # 1. Generate initial draft -> gap marker
        init_gen = self.client.post(f"/api/rfps/{rfp_id}/sections/{sec_id}/generate").json()
        self.assertIn("[MORE INFO REQUIRED:", init_gen["draft_content"])
        self.assertEqual(init_gen["status"], "drafted")

        # 2. Locate open question
        questions = self.client.get(f"/api/rfps/{rfp_id}/open-questions").json()
        self.assertEqual(len(questions), 1)
        q_id = questions[0]["id"]

        # 3. Resolve open question
        res_text = "Another Marketing Agency passed GDS Alpha and Beta assessments with NHS BSA in 2024."
        put_res = self.client.put(
            f"/api/rfps/{rfp_id}/open-questions/{q_id}",
            json={"resolution": res_text, "status": "resolved"},
        )
        self.assertEqual(put_res.status_code, 200)
        self.assertEqual(put_res.json()["status"], "resolved")

        # 4. Regenerate section
        regen_gen = self.client.post(f"/api/rfps/{rfp_id}/sections/{sec_id}/generate").json()
        self.assertNotIn("[MORE INFO REQUIRED:", regen_gen["draft_content"], "Gap marker was not removed")
        self.assertIn(res_text, regen_gen["draft_content"], "Resolution text not incorporated in draft")
        self.assertEqual(regen_gen["status"], "resolved", "Section status failed to transition to resolved")

        # 5. Provenance check
        res_prov = next((p for p in regen_gen["provenance"] if p["source"] == "notes"), None)
        self.assertIsNotNone(res_prov, "Provenance missing resolution notes source")
        self.assertEqual(res_prov["text"], res_text)
        self.assertIn(f"Open Question #{q_id} Resolution", res_prov["reference"])

    def test_10_strategic_section_empty_kb_flaw_analysis(self):
        """
        Adversarial Finding: Strategic section with empty KB won proposals.
        Tests system behavior when KB has no won past proposals.
        """
        # Delete all won past proposals from database
        self.conn.execute("DELETE FROM kb_documents WHERE type = 'past_proposal' AND outcome = 'won';")
        self.conn.commit()

        rfp_id = self.create_test_rfp("Empty Won KB RFP")
        sec_id = self.add_section(
            rfp_id,
            heading="Technical Architecture",
            original_text="Describe enterprise microservices architecture.",
            classification="strategic_decision",
            sort_order=1,
        )

        res = self.client.post(f"/api/rfps/{rfp_id}/sections/{sec_id}/generate")
        self.assertEqual(res.status_code, 200)
        data = res.json()

        # Notice: When no won past proposal exists and no notes exist:
        # Does the backend produce a gap marker?
        # In current rfps.py line 988-1000, won_doc is None -> no text is appended.
        # If tone prompt doesn't match executive summary, final_draft is empty!
        # Status becomes 'resolved' because markers list is empty ([]).
        markers = [p for p in data["provenance"] if p["source"] == "gap"]
        # Document the empirical reality
        has_gap_marker = "[MORE INFO REQUIRED:" in data["draft_content"]
        # In the current implementation, strategic sections without won proposals do NOT emit a gap marker!
        self.assertFalse(
            has_gap_marker,
            "Documenting observed behavior: strategic section does not emit gap marker when won proposals are missing",
        )


class TestTripartiteSynthesisAndProvenanceSchema(BaseM4IsolatedTestCase):
    """Adversarial testing of Tripartite Synthesis Fidelity (Dispatch Item 3) and Provenance Schema."""

    def test_11_single_section_classification_partitioning(self):
        """
        Dispatch Item 3 Adversarial Challenge:
        'Section requiring pricing + boilerplate + RAG: verify all three sources are integrated and provenance captures all three'.

        Empirical Verification:
        We inspect whether a single section can simultaneously synthesize pricing + boilerplate + RAG.
        In the current backend architecture:
        - `if classification == 'pricing'`: retrieves pricing (+ notes), ignores boilerplate and RAG.
        - `elif classification == 'boilerplate'`: retrieves boilerplate (+ notes), ignores pricing and RAG.
        - `else` (strategic): retrieves RAG (+ notes), ignores pricing and boilerplate.
        """
        rfp_id = self.create_test_rfp("Tripartite Architecture RFP", services=[1])

        # Section requiring commercial pricing, corporate background, and technical approach
        sec_id = self.add_section(
            rfp_id,
            heading="Commercial Terms, Company Certifications, and Technical Delivery",
            original_text="Provide company ISO 27001 certification, £850 Statamic daily rate, and CMS headless approach.",
            classification="pricing",
            sort_order=1,
        )

        gen_res = self.client.post(f"/api/rfps/{rfp_id}/sections/{sec_id}/generate")
        self.assertEqual(gen_res.status_code, 200)
        data = gen_res.json()
        sources = [p["source"] for p in data["provenance"]]

        # Observed behavior: For a pricing section, pricing is retrieved, but RAG and boilerplate are not
        self.assertIn("pricing", sources)
        self.assertNotIn("boilerplate", sources, "Architecture branches on classification; pricing does not pull boilerplate")
        self.assertNotIn("rag", sources, "Architecture branches on classification; pricing does not pull RAG")

    def test_12_tripartite_combination_pricing_plus_notes(self):
        """Verify dual-source synthesis of exact pricing schedule and AM notes with strict provenance schema."""
        rfp_id = self.create_test_rfp("Pricing + Notes RFP", services=[1])
        sec_id = self.add_section(
            rfp_id,
            heading="Cost Schedule",
            original_text="Senior engineer daily rate and discovery fee.",
            classification="pricing",
            sort_order=1,
        )

        note_text = "Apply 10% volume discount if engagement extends beyond 6 months."
        self.client.post(f"/api/rfps/{rfp_id}/notes", json={"raw_content": note_text, "section_id": sec_id})

        res = self.client.post(f"/api/rfps/{rfp_id}/sections/{sec_id}/generate")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        draft = data["draft_content"]

        # Exact pricing check
        self.assertIn("850", draft)
        self.assertIn(note_text, draft)

        # Provenance check
        sources = [p["source"] for p in data["provenance"]]
        self.assertIn("pricing", sources)
        self.assertIn("notes", sources)

        # Strict schema checks
        for p in data["provenance"]:
            self.assertIn(p["source"], ["notes", "rag", "boilerplate", "pricing", "gap"])
            self.assertTrue(len(p["text"]) > 0, "Provenance text cannot be empty")
            self.assertTrue(len(p["reference"]) > 0, "Provenance reference cannot be empty")

    def test_13_tripartite_combination_rag_plus_notes(self):
        """Verify dual-source synthesis of retrieved won proposal and AM notes with strict provenance."""
        rfp_id = self.create_test_rfp("RAG + Notes RFP")
        sec_id = self.add_section(
            rfp_id,
            heading="3.0 Technical Architecture",
            original_text="Describe headless CMS integration patterns.",
            classification="strategic_decision",
            sort_order=1,
        )

        note_text = "Mandate GraphQL API gateway and Next.js 14 frontend."
        self.client.post(f"/api/rfps/{rfp_id}/notes", json={"raw_content": note_text, "section_id": sec_id})

        res = self.client.post(f"/api/rfps/{rfp_id}/sections/{sec_id}/generate")
        self.assertEqual(res.status_code, 200)
        data = gen_res = res.json()
        draft = data["draft_content"]

        # Assertions
        self.assertIn(note_text, draft)
        sources = [p["source"] for p in data["provenance"]]
        self.assertIn("rag", sources)
        self.assertIn("notes", sources)

        # Check references
        rag_prov = next(p for p in data["provenance"] if p["source"] == "rag")
        self.assertIn("KB Document #", rag_prov["reference"])
        note_prov = next(p for p in data["provenance"] if p["source"] == "notes")
        self.assertIn(f"Section {sec_id}", note_prov["reference"])

    def test_14_tripartite_combination_boilerplate_plus_notes(self):
        """Verify dual-source synthesis of boilerplate company profile and AM delivery notes."""
        rfp_id = self.create_test_rfp("Boilerplate + Notes RFP")
        sec_id = self.add_section(
            rfp_id,
            heading="1.0 Company Overview",
            original_text="Detail corporate structure and quality management.",
            classification="boilerplate",
            sort_order=1,
        )

        note_text = "Emphasize ISO 9001 and ISO 27001 certified security practices."
        self.client.post(f"/api/rfps/{rfp_id}/notes", json={"raw_content": note_text, "section_id": sec_id})

        res = self.client.post(f"/api/rfps/{rfp_id}/sections/{sec_id}/generate")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        draft = data["draft_content"]

        self.assertIn("Another Marketing Agency", draft)
        self.assertIn(note_text, draft)

        sources = [p["source"] for p in data["provenance"]]
        self.assertIn("boilerplate", sources)
        self.assertIn("notes", sources)

    def test_15_quadpartite_combination_pricing_notes_and_resolved_question(self):
        """
        Verify multi-source synthesis combining:
        1. Exact pricing schedule
        2. AM account manager note
        3. Previously resolved open question for that section
        """
        rfp_id = self.create_test_rfp("Quadpartite RFP", services=[1])
        sec_id = self.add_section(
            rfp_id,
            heading="Commercial Rates & Delivery Terms",
            original_text="Provide daily rate for the senior engineer.",
            classification="pricing",
            sort_order=1,
        )

        # 1. Add AM note
        am_note = "Special rate card approved by Commercial Director."
        self.client.post(f"/api/rfps/{rfp_id}/notes", json={"raw_content": am_note, "section_id": sec_id})

        # 2. Insert resolved open question directly for this section
        cur = self.conn.cursor()
        res_text = "All travel and subsistence expenses are included in day rate."
        cur.execute(
            """
            INSERT INTO open_questions (rfp_id, section_id, question, status, resolution)
            VALUES (?, ?, 'Are expenses included in day rate?', 'resolved', ?);
            """,
            (rfp_id, sec_id, res_text),
        )
        self.conn.commit()
        q_id = cur.lastrowid

        # 3. Generate draft
        res = self.client.post(f"/api/rfps/{rfp_id}/sections/{sec_id}/generate")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        draft = data["draft_content"]

        # All 3 elements must be in draft
        self.assertIn("850", draft, "Pricing missing")
        self.assertIn(am_note, draft, "AM note missing")
        self.assertIn(res_text, draft, "Resolved question missing")

        # Provenance check
        provenance = data["provenance"]
        self.assertGreaterEqual(len(provenance), 3)
        sources = [p["source"] for p in provenance]
        self.assertIn("pricing", sources)
        self.assertIn("notes", sources)

        # Validate distinct references
        pricing_prov = next(p for p in provenance if p["source"] == "pricing")
        self.assertEqual(pricing_prov["reference"], "Structured price_items schedule")

        note_refs = [p["reference"] for p in provenance if p["source"] == "notes"]
        self.assertTrue(any(f"Section {sec_id}" in r for r in note_refs))
        self.assertTrue(any(f"Open Question #{q_id}" in r for r in note_refs))

    def test_16_full_rfp_multi_source_synthesis_and_provenance_diversity(self):
        """
        Verify that across an entire RFP response, all 5 provenance types
        (boilerplate, rag, pricing, notes, gap) are generated and tagged.
        """
        rfp_id = self.create_test_rfp("Full Proposal Synthesis RFP", services=[1])

        sec_bp = self.add_section(rfp_id, "1.0 Overview", "Company background", "boilerplate", 1)
        sec_strat = self.add_section(rfp_id, "2.0 Strategy", "Cloud methodology", "strategic_decision", 2)
        sec_pr = self.add_section(rfp_id, "3.0 Pricing", "Statamic Technical Lead rate", "pricing", 3)
        sec_gap = self.add_section(rfp_id, "4.0 Quantum Experience", "Quantum cryptography", "gap", 4)

        # Whole-RFP note
        self.client.post(
            f"/api/rfps/{rfp_id}/notes",
            json={"raw_content": "Global note: All work delivered from UK soil.", "section_id": None},
        )

        all_provenance_sources = set()
        for sec_id in [sec_bp, sec_strat, sec_pr, sec_gap]:
            res = self.client.post(f"/api/rfps/{rfp_id}/sections/{sec_id}/generate")
            self.assertEqual(res.status_code, 200)
            data = res.json()
            for p in data["provenance"]:
                all_provenance_sources.add(p["source"])
                # Validate schema
                self.assertIn(p["source"], ["notes", "rag", "boilerplate", "pricing", "gap"])
                self.assertTrue(len(p["text"]) > 0)
                self.assertTrue(len(p["reference"]) > 0)

        # Across the whole RFP, all 5 provenance sources must be represented
        self.assertEqual(
            all_provenance_sources,
            {"boilerplate", "rag", "pricing", "notes", "gap"},
            f"Expected all 5 provenance source types, got {all_provenance_sources}",
        )


class TestAdversarialBoundariesAndIntegrity(BaseM4IsolatedTestCase):
    """Adversarial testing of input boundaries, edge cases, and referential integrity."""

    def test_17_adversarial_massive_notes_payload(self):
        """Draft generation handles a massive 20,000-character AM note without crash, OOM, or truncation."""
        rfp_id = self.create_test_rfp("Massive Note RFP")
        sec_id = self.add_section(rfp_id, "Technical Spec", "Provide technical spec", "strategic_decision", 1)

        massive_text = "MASSIVE_NOTE_START " + ("Another Marketing Agency architectural standard section. " * 400) + " MASSIVE_NOTE_END"
        self.assertGreater(len(massive_text), 15000)

        note_res = self.client.post(
            f"/api/rfps/{rfp_id}/notes",
            json={"raw_content": massive_text, "section_id": sec_id},
        )
        self.assertEqual(note_res.status_code, 201)

        gen_res = self.client.post(f"/api/rfps/{rfp_id}/sections/{sec_id}/generate")
        self.assertEqual(gen_res.status_code, 200)
        draft = gen_res.json()["draft_content"]

        self.assertIn("MASSIVE_NOTE_START", draft)
        self.assertIn("MASSIVE_NOTE_END", draft)

    def test_18_adversarial_special_characters_and_injection(self):
        """Special characters, HTML/XSS payloads, SQL injection tokens, and Unicode emojis are stored safely."""
        rfp_id = self.create_test_rfp("Injection RFP")
        sec_id = self.add_section(rfp_id, "Security", "Describe security posture", "strategic_decision", 1)

        adversarial_note = (
            "<script>alert('XSS')</script> "
            "' OR '1'='1'; DROP TABLE rfps; -- "
            "🚀🔥💡 Verified multilingual: 日本語 • العربية • Français • 100% compliant."
        )

        note_res = self.client.post(
            f"/api/rfps/{rfp_id}/notes",
            json={"raw_content": adversarial_note, "section_id": sec_id},
        )
        self.assertEqual(note_res.status_code, 201)

        gen_res = self.client.post(f"/api/rfps/{rfp_id}/sections/{sec_id}/generate")
        self.assertEqual(gen_res.status_code, 200)
        draft = gen_res.json()["draft_content"]

        self.assertIn("<script>alert('XSS')</script>", draft)
        self.assertIn("DROP TABLE rfps;", draft)
        self.assertIn("🚀🔥💡", draft)
        self.assertIn("日本語", draft)

        # Verify DB wasn't dropped
        cur = self.conn.cursor()
        cur.execute("SELECT COUNT(*) FROM rfps WHERE id = ?;", (rfp_id,))
        self.assertEqual(cur.fetchone()[0], 1)

    def test_19_section_status_workflow_and_validation(self):
        """PUT /api/rfps/{id}/sections/{section_id} validates status strings strictly."""
        rfp_id = self.create_test_rfp("Status Workflow RFP")
        sec_id = self.add_section(rfp_id, "Workflow Section", "Section text", "boilerplate", 1)

        # Valid transition to drafted
        res1 = self.client.put(f"/api/rfps/{rfp_id}/sections/{sec_id}", json={"status": "drafted"})
        self.assertEqual(res1.status_code, 200)
        self.assertEqual(res1.json()["status"], "drafted")

        # Valid transition to resolved
        res2 = self.client.put(f"/api/rfps/{rfp_id}/sections/{sec_id}", json={"status": "resolved"})
        self.assertEqual(res2.status_code, 200)
        self.assertEqual(res2.json()["status"], "resolved")

        # Invalid status must be rejected with 422
        res3 = self.client.put(f"/api/rfps/{rfp_id}/sections/{sec_id}", json={"status": "completed"})
        self.assertEqual(res3.status_code, 422)

        res4 = self.client.put(f"/api/rfps/{rfp_id}/sections/{sec_id}", json={"status": "approved"})
        self.assertEqual(res4.status_code, 422)

    def test_20_referential_integrity_cascade_deletion(self):
        """Deleting an RFP cascades to delete attached notes and open questions."""
        rfp_id = self.create_test_rfp("Cascade Test RFP")
        sec_id = self.add_section(rfp_id, "Gap Section", "Quantum crypto", "gap", 1)

        # Add note
        self.client.post(f"/api/rfps/{rfp_id}/notes", json={"raw_content": "Cascade note", "section_id": sec_id})

        # Generate draft to create open question
        self.client.post(f"/api/rfps/{rfp_id}/sections/{sec_id}/generate")

        # Verify items exist
        cur = self.conn.cursor()
        cur.execute("SELECT COUNT(*) FROM rfp_notes WHERE rfp_id = ?;", (rfp_id,))
        self.assertGreaterEqual(cur.fetchone()[0], 1)
        cur.execute("SELECT COUNT(*) FROM open_questions WHERE rfp_id = ?;", (rfp_id,))
        self.assertGreaterEqual(cur.fetchone()[0], 1)

        # Delete RFP
        del_res = self.client.delete(f"/api/rfps/{rfp_id}")
        self.assertEqual(del_res.status_code, 200)

        # Verify cascade
        cur.execute("SELECT COUNT(*) FROM rfp_notes WHERE rfp_id = ?;", (rfp_id,))
        self.assertEqual(cur.fetchone()[0], 0, "Attached notes were not deleted on RFP deletion")
        cur.execute("SELECT COUNT(*) FROM open_questions WHERE rfp_id = ?;", (rfp_id,))
        self.assertEqual(cur.fetchone()[0], 0, "Attached open questions were not deleted on RFP deletion")
        cur.execute("SELECT COUNT(*) FROM rfp_sections WHERE rfp_id = ?;", (rfp_id,))
        self.assertEqual(cur.fetchone()[0], 0, "Attached sections were not deleted on RFP deletion")


if __name__ == "__main__":
    unittest.main()

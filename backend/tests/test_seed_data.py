"""Comprehensive Unit Tests for Seed Data & Sample RFP Document Pipeline (F25).

Verifies:
1. Seed services count (5) and unique name constraints.
2. Seed price items count (8) covering day rates, fixed packages, and monthly retainers.
3. Seed KB entries count (5) including won/lost proposals, case study, boilerplate, and testimonial.
4. Won-proposal retrieval biasing (ratio >= 1.20) on seed KB data.
5. Sample RFP DOCX extraction (7 sections) and classification covering all 5 categories.
6. Sample RFP Section 5 deliberate ambiguity (strategic_decision with medium confidence).
7. Sample RFP PDF extraction via pdfplumber (7 sections).
8. Word-boundary fix in llm.py ensuring 'rate' in 'corporate' or 'strategy' is not misclassified as pricing.
9. Seeding idempotency (multiple runs do not duplicate or corrupt rows).
"""

import os
from pathlib import Path
import re
import sqlite3
import sys
import tempfile
import unittest

import glob

for p in [str(Path(__file__).resolve().parent.parent), str(Path(__file__).resolve().parent.parent.parent)]:
    if p not in sys.path:
        sys.path.insert(0, p)

venv_pkgs = glob.glob(str(Path(__file__).resolve().parent.parent.parent / ".venv" / "lib" / "python*" / "site-packages"))
for p in venv_pkgs:
    if p not in sys.path:
        sys.path.insert(0, p)

from app.database import get_db_connection
from app.models import DEFAULT_SERVICES, SEED_KB_DOCUMENTS, SEED_PRICE_ITEMS
from app.services.ingestion import extract_from_docx, extract_from_pdf, split_text_into_sections
from app.services.llm import mock_classify_sections
from app.services.seed import ensure_seeded, generate_sample_rfp_assets
from app.services.vector_store import PurePythonVectorStore, sync_vector_store_from_db


class TestSeedDataAndAssets(unittest.TestCase):
    """Test suite covering seed data models, vector store indexing, and document assets."""

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.tmp.name
        self.tmp.close()
        ensure_seeded(db_path=self.db_path, reset=True, generate_files=True)
        self.conn = get_db_connection(self.db_path)

    def tearDown(self):
        self.conn.close()
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_01_seed_services_count_and_names(self):
        """Database seed contains exactly 5 default services with expected names."""
        cur = self.conn.execute("SELECT id, name FROM services ORDER BY id ASC;")
        rows = cur.fetchall()
        self.assertEqual(len(rows), 5)
        names = [r["name"] for r in rows]
        for exp in [
            "Web Development — Headless CMS",
            "Digital Marketing — PPC",
            "UX/UI Design",
            "SEO — Technical",
        ]:
            self.assertIn(exp, names)

    def test_02_seed_price_items_count_and_units(self):
        """Database seed contains exactly 8 price items covering all three units."""
        cur = self.conn.execute("SELECT id, service_id, description, unit, amount FROM price_items ORDER BY id ASC;")
        rows = [dict(r) for r in cur.fetchall()]
        self.assertEqual(len(rows), 8, f"Expected 8 price items, found {len(rows)}")

        day_rates = [r["amount"] for r in rows if r["unit"] == "day rate"]
        fixed_pkgs = [r["amount"] for r in rows if r["unit"] == "fixed"]
        retainers = [r["amount"] for r in rows if r["unit"] == "monthly retainer"]

        # Day rates: 750, 850, 900
        self.assertEqual(len(day_rates), 3)
        self.assertIn(750.0, day_rates)
        self.assertIn(850.0, day_rates)
        self.assertIn(900.0, day_rates)

        # Fixed: 3500, 6000, 16500
        self.assertEqual(len(fixed_pkgs), 3)
        self.assertIn(3500.0, fixed_pkgs)
        self.assertIn(6000.0, fixed_pkgs)
        self.assertIn(16500.0, fixed_pkgs)

        # Retainers: 2200, 5000
        self.assertEqual(len(retainers), 2)
        self.assertIn(2200.0, retainers)
        self.assertIn(5000.0, retainers)

    def test_03_seed_kb_documents_count_and_types(self):
        """Database seed contains 5 KB documents spanning past proposals, case study, boilerplate, and testimonial."""
        cur = self.conn.execute("SELECT id, type, title, content, outcome FROM kb_documents ORDER BY id ASC;")
        docs = [dict(r) for r in cur.fetchall()]
        self.assertEqual(len(docs), 5)

        # 2 past proposals: 1 won, 1 lost
        proposals = [d for d in docs if d["type"] == "past_proposal"]
        self.assertEqual(len(proposals), 2)
        outcomes = {p["outcome"] for p in proposals}
        self.assertEqual(outcomes, {"won", "lost"})

        # 1 case study with quantified metrics
        case_studies = [d for d in docs if d["type"] == "case_study"]
        self.assertEqual(len(case_studies), 1)
        cs_content = case_studies[0]["content"]
        self.assertIn("+45%", cs_content)
        self.assertIn("3.2s", cs_content)
        self.assertIn("99.99%", cs_content)

        # 1 master boilerplate with ISO 27001 and £5M insurance
        boilerplates = [d for d in docs if d["type"] == "boilerplate"]
        self.assertEqual(len(boilerplates), 1)
        bp_content = boilerplates[0]["content"]
        self.assertIn("ISO 27001", bp_content)
        self.assertIn("Cyber Essentials", bp_content)
        self.assertIn("5,000,000", bp_content)

        # 1 testimonial
        testimonials = [d for d in docs if d["type"] == "testimonial"]
        self.assertEqual(len(testimonials), 1)
        self.assertIn("Chief Technology Officer", testimonials[0]["content"])
        self.assertIn("(fictional)", testimonials[0]["content"])

    def test_04_won_proposal_biasing_on_seed_data(self):
        """Querying 'web development and digital marketing' against seed data ranks Won proposal #1 with ratio >= 1.20."""
        vs = PurePythonVectorStore()
        for doc in SEED_KB_DOCUMENTS:
            vs.add_document(
                doc_id=doc["id"],
                title=doc["title"],
                content=doc["content"],
                doc_type=doc["type"],
                outcome=doc["outcome"],
                service_ids=doc.get("service_ids", []),
            )

        results = vs.search("web development and digital marketing", limit=5)
        self.assertGreaterEqual(len(results), 2)

        won_doc = next(r for r in results if r["id"] == 1)
        lost_doc = next(r for r in results if r["id"] == 2)

        self.assertEqual(won_doc["outcome"], "won")
        self.assertEqual(lost_doc["outcome"], "lost")
        self.assertGreater(won_doc["similarity_score"], lost_doc["similarity_score"])

        ratio = won_doc["similarity_score"] / lost_doc["similarity_score"]
        self.assertGreaterEqual(ratio, 1.20, f"Expected ratio >= 1.20, got {ratio:.4f}")

    def test_05_sample_rfp_docx_parsing_and_classification(self):
        """Sample RFP DOCX contains exactly 7 sections spanning all 5 classification categories."""
        backend_dir = Path(__file__).resolve().parent.parent
        docx_path = backend_dir / "data" / "sample_rfp.docx"
        self.assertTrue(docx_path.exists(), f"Sample DOCX file not found at {docx_path}")

        extracted_text = extract_from_docx(docx_path)
        sections = split_text_into_sections(extracted_text)
        self.assertEqual(len(sections), 7, f"Expected 7 sections in sample DOCX, got {len(sections)}")

        classified = mock_classify_sections(sections)
        categories = {c["classification"] for c in classified}
        expected_categories = {"boilerplate", "pricing", "strategic_decision", "gap", "compliance_admin"}
        self.assertTrue(
            expected_categories.issubset(categories),
            f"Expected categories {expected_categories} subset of {categories}",
        )

    def test_06_sample_rfp_section_5_deliberate_ambiguity(self):
        """Section 5 is deliberately ambiguous, classified as strategic_decision with medium confidence."""
        backend_dir = Path(__file__).resolve().parent.parent
        docx_path = backend_dir / "data" / "sample_rfp.docx"
        extracted_text = extract_from_docx(docx_path)
        sections = split_text_into_sections(extracted_text)

        sec5 = sections[4]  # 0-indexed index 4 is Section 5
        self.assertIn("accessibility", sec5["heading"].lower())

        classified = mock_classify_sections([sec5])[0]
        self.assertEqual(classified["classification"], "strategic_decision")
        self.assertEqual(classified["confidence"], "medium")
        self.assertTrue(len(classified["clarifying_question"]) > 0)
        self.assertTrue(len(classified["suggested_default"]) > 0)

    def test_07_sample_rfp_pdf_parsing_and_sections(self):
        """Sample RFP PDF contains 7 sections parseable by pdfplumber."""
        backend_dir = Path(__file__).resolve().parent.parent
        pdf_path = backend_dir / "data" / "sample_rfp.pdf"
        self.assertTrue(pdf_path.exists(), f"Sample PDF file not found at {pdf_path}")

        extracted_text = extract_from_pdf(pdf_path)
        sections = split_text_into_sections(extracted_text)
        self.assertEqual(len(sections), 7, f"Expected 7 sections in sample PDF, got {len(sections)}")

    def test_08_word_boundary_rate_does_not_misclassify_corporate_or_strategy(self):
        """Headings containing 'corporate' or 'strategy' are not misclassified as pricing."""
        test_sections = [
            {"heading": "Corporate Credentials & Background", "original_text": "Company history and team structure."},
            {"heading": "Digital Strategy Roadmap", "original_text": "Phased approach to architectural delivery."},
        ]
        classified = mock_classify_sections(test_sections)
        cats = [c["classification"] for c in classified]
        self.assertNotIn("pricing", cats, f"False positive pricing classification detected: {cats}")

    def test_09_ensure_seeded_idempotency(self):
        """Calling ensure_seeded multiple times does not produce duplicate rows or integrity errors."""
        for _ in range(3):
            ensure_seeded(db_path=self.db_path, reset=False, generate_files=False)

        cur = self.conn.execute("SELECT count(*) FROM services;")
        self.assertEqual(cur.fetchone()[0], 5)

        cur = self.conn.execute("SELECT count(*) FROM price_items;")
        self.assertEqual(cur.fetchone()[0], 8)

        cur = self.conn.execute("SELECT count(*) FROM kb_documents;")
        self.assertEqual(cur.fetchone()[0], 5)


if __name__ == "__main__":
    unittest.main()

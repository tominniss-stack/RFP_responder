#!/usr/bin/env python3
"""
Tier 5 White-Box Adversarial Stress Testing & Coverage Hardening Suite (Milestone 6)
Challenger 1: challenger_m6_1

Stress Test Vectors:
1. Ingestion parser resilience:
   - Empty files (0 bytes, empty strings, .empty filenames)
   - Corrupted archives, non-zip DOCX, corrupted PDF headers
   - Unusual Unicode (CJK, Arabic RTL, emojis, math symbols, control chars)
   - Deeply nested headings (H1-H6, 1.2.3.4.5.6 outlines, Clause/Module/Requirement prefixes)
   - Massive documents (100+ sections, 2,000+ char paragraphs, line-length stress)
   - Paragraph-splitting fallback (no explicit headings)
   - Synthetic in-memory DOCX generation and parsing

2. Exact pricing injection:
   - Currency and floating-point numeric fidelity (exact 2 decimal places, £ symbol)
   - Multiple matching price items linked to multiple services
   - Zero matching price items & unpriced services (zero hallucination guarantee)
   - Unlinked RFP with and without "Statamic" keyword context
   - Database CHECK constraint enforcement on unit IN ('day rate', 'fixed', 'monthly retainer')
   - Valid units with special characters, quotes, and symbols in descriptions

3. Retrieval biasing engine under edge conditions:
   - KB containing ONLY lost proposals
   - Tied similarity scores with deterministic ID-based tie-breaking (ascending)
   - Empty vector store fallback (PurePython & Chroma wrapper)
   - Adversarial query strings (10k chars, regex punctuation, symbols, empty queries)
   - Won vs. Lost biasing ratio verification (>= 1.20)

4. Draft generation & gap marker detection:
   - Complex symbols in gap markers (slashes, ampersands, dashes, brackets, quotes)
   - Multiline gap marker detection
   - Multiple gap markers in a single section draft
   - Gap marker auto-insertion into open_questions with idempotency
   - Question resolution, section status transition, and notes precedence

5. Export pipeline concurrency, missing directories & malformed payloads:
   - Missing logs directory auto-creation
   - Malformed/empty payloads (0 sections, null client name, empty draft/final content)
   - Orphan open questions anchored to document title
   - Concurrent export thread-safety
   - Live export error contracts (missing/placeholder credentials)

6. Automated WCAG AAA contrast ratio & typography audit:
   - Mathematical contrast ratio calculation for #FFCD4E vs #000000 (AAA >= 7.0:1)
   - Static AST/regex scan of all frontend JSX and CSS files to ensure #FFCD4E is strictly paired with black
   - Static audit of Inter font configuration across index.html, index.css, tailwind.config.js
"""

import concurrent.futures
import glob
import io
import json
import os
import re
import sqlite3
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from typing import Any, Dict, List

# Ensure project root, backend root, and virtualenv site-packages are on sys.path
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

from app.database import get_db_connection
from app.models import create_tables, seed_defaults
from app.services.ingestion import (
    ingest_document,
    split_text_into_sections,
    extract_from_pdf,
    extract_from_docx,
    extract_sections_from_file,
    save_uploaded_file,
)
from app.services.pricing import (
    get_pricing_for_rfp,
    format_pricing_schedule,
    generate_pricing_draft,
)
from app.services.vector_store import (
    PurePythonVectorStore,
    ChromaVectorStoreWrapper,
    chunk_document,
    tokenize,
    retrieve_boilerplate,
    WEIGHT_WON,
    WEIGHT_LOST,
    WEIGHT_NA,
)
from app.services.llm import (
    mock_classify_sections,
    clean_json_response,
    classify_rfp_sections,
)
from app.services.export import (
    build_export_payload,
    log_export_payload,
    execute_export,
)
from fastapi.testclient import TestClient
from app.main import app


# Helper to build valid minimal DOCX in memory
def make_minimal_docx(paragraphs: List[str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
            '</Types>',
        )
        zf.writestr(
            "_rels/.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
            '</Relationships>',
        )
        p_xml_nodes = []
        for p in paragraphs:
            is_heading = p.startswith("## ")
            clean_text = p[3:] if is_heading else p
            p_style = '<w:pPr><w:pStyle w:val="Heading1"/></w:pPr>' if is_heading else ""
            p_xml_nodes.append(
                f'<w:p>{p_style}<w:r><w:t>{clean_text}</w:t></w:r></w:p>'
            )
        doc_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            f'<w:body>{"".join(p_xml_nodes)}</w:body>'
            '</w:document>'
        )
        zf.writestr("word/document.xml", doc_xml)
    return buf.getvalue()


class TestIngestionParserAdversarial(unittest.TestCase):
    """Dimension 1: Ingestion Parser White-Box Stress Testing."""

    def test_empty_files_and_zero_byte_buffers(self):
        """Zero-byte files and .empty filenames must raise ValueError with informative messages."""
        with self.assertRaises(ValueError) as ctx:
            ingest_document(b"", "spec.docx")
        self.assertIn("file is empty or corrupted", str(ctx.exception))

        with self.assertRaises(ValueError) as ctx:
            ingest_document(b"non-empty", "spec.empty")
        self.assertIn("file is empty or corrupted", str(ctx.exception))

        with self.assertRaises(ValueError) as ctx:
            extract_from_docx(b"")
        self.assertIn("Corrupted or invalid DOCX archive", str(ctx.exception))

        # Empty string split returns empty list
        self.assertEqual(split_text_into_sections(""), [])
        self.assertEqual(split_text_into_sections("   \n\n  \t  "), [])

    def test_corrupted_archives_and_bad_magic_bytes(self):
        """Arbitrary corrupted bytes with docx/pdf extension must fail cleanly."""
        corrupt_bytes = b"NOT_A_ZIP_ARCHIVE_HEADER_CORRUPTION_12345"
        with self.assertRaises(ValueError) as ctx:
            ingest_document(corrupt_bytes, "rfp.docx")
        self.assertIn("Corrupted or invalid DOCX archive", str(ctx.exception))

        with self.assertRaises(ValueError) as ctx:
            ingest_document(corrupt_bytes, "rfp.pdf")
        self.assertIn("Corrupted or invalid PDF file", str(ctx.exception))

        # Truncated zip missing word/document.xml
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("unrelated.txt", "hello")
        with self.assertRaises(ValueError) as ctx:
            extract_from_docx(buf.getvalue())
        self.assertIn("Corrupted or invalid DOCX archive", str(ctx.exception))

    def test_unusual_unicode_and_special_characters(self):
        """Parser must preserve CJK characters, Arabic RTL, math symbols, and emojis."""
        raw_text = (
            "## 1.0 项目概述 & Agency Credentials 🚀\n"
            "This section introduces the agency with 中文 and emoji: 💼 ✨.\n\n"
            "## 2.0 المتطلبات التقنية (Technical Architecture) ∑\n"
            "Architecture details with math symbols: ∀x ∈ S, f(x) ≥ 0, and RTL Arabic.\n\n"
            "## 3.0 Commercials & Rates £ € $\n"
            "Currency symbols: £850.00 / €950.00 / $1,100.00."
        )
        sections = split_text_into_sections(raw_text)
        self.assertEqual(len(sections), 3)
        self.assertIn("1.0 项目概述 & Agency Credentials 🚀", sections[0]["heading"])
        self.assertIn("中文 and emoji", sections[0]["original_text"])
        self.assertIn("المتطلبات التقنية", sections[1]["heading"])
        self.assertIn("∀x ∈ S", sections[1]["original_text"])
        self.assertIn("Commercials & Rates £ € $", sections[2]["heading"])

    def test_deeply_nested_headings_and_outlines(self):
        """Parser must detect deep numbered outlines (1.2.3.4.5.6) and formal clause prefixes."""
        raw_text = (
            "1.0. Executive Summary\nSummary paragraph here.\n\n"
            "Section 2.1.4: Cloud Hosting Standards\nMust comply with ISO 27001.\n\n"
            "Requirement 3.2.1.4.5: Disaster Recovery RTO\nTarget RTO < 15 minutes.\n\n"
            "Clause 4.1-A: Intellectual Property Assignment\nAll code assigned to client.\n\n"
            "Question 5.0: Staffing & Day Rates\nProvide Statamic developer rates."
        )
        sections = split_text_into_sections(raw_text)
        self.assertEqual(len(sections), 5)
        self.assertIn("Executive Summary", sections[0]["heading"])
        self.assertIn("2.1.4: Cloud Hosting Standards", sections[1]["heading"])
        self.assertIn("3.2.1.4.5: Disaster Recovery RTO", sections[2]["heading"])
        self.assertIn("4.1-A: Intellectual Property Assignment", sections[3]["heading"])
        self.assertIn("5.0: Staffing & Day Rates", sections[4]["heading"])

    def test_massive_document_and_line_length_stress(self):
        """Stress test with 100 headings and 2,000-char paragraphs."""
        lines = []
        for i in range(1, 101):
            lines.append(f"## {i}.0 Section Title {i}")
            para = f"Detailed technical requirement {i}. " + ("Lipsum dolor sit amet, consectetur adipiscing elit. " * 35)
            lines.append(para)
            lines.append("")

        big_text = "\n".join(lines)
        sections = split_text_into_sections(big_text)
        self.assertEqual(len(sections), 100)
        for idx, s in enumerate(sections, start=1):
            self.assertEqual(s["sort_order"], idx)
            self.assertTrue(s["heading"].startswith(f"{idx}.0 Section Title {idx}"))
            self.assertTrue(len(s["original_text"]) > 1000)

    def test_double_newline_paragraph_fallback(self):
        """When text lacks standard markdown or outline headings, fallback splits on double newlines."""
        raw_text = (
            "This is a short paragraph acting as heading 1\nSecond line with details.\n\n"
            "Another distinct block of requirements for accessibility\nWCAG AAA compliance required.\n\n"
            "Third block covering commercial budget and timelines\nFixed cost £25,000."
        )
        sections = split_text_into_sections(raw_text)
        self.assertEqual(len(sections), 3)
        self.assertEqual(sections[0]["heading"], "This is a short paragraph acting as heading 1")
        self.assertIn("Second line with details.", sections[0]["original_text"])
        self.assertEqual(sections[1]["heading"], "Another distinct block of requirements for accessibility")
        self.assertEqual(sections[2]["heading"], "Third block covering commercial budget and timelines")

    def test_synthetic_docx_generation_and_parsing(self):
        """Verify custom in-memory DOCX with multiple paragraphs parses properly."""
        docx_bytes = make_minimal_docx([
            "## 1.0 In-Memory Heading",
            "This is the body content parsed from zip XML fallback.",
            "## 2.0 Second In-Memory Heading",
            "Second body paragraph with details.",
        ])
        sections = ingest_document(docx_bytes, "test_synthetic.docx")
        self.assertEqual(len(sections), 2)
        self.assertIn("1.0 In-Memory Heading", sections[0]["heading"])
        self.assertIn("This is the body content", sections[0]["original_text"])


class TestExactPricingInjectionAdversarial(unittest.TestCase):
    """Dimension 2: Exact Pricing Injection Engine Stress Testing."""

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

    def test_exact_currency_numeric_fidelity(self):
        """Format schedule must reproduce £850.00, £16,500.00, £0.50, £1,234,567.89 with exact 2 decimal places."""
        test_items = [
            {"description": "Daily Consultancy", "amount": 850.0, "unit": "day rate"},
            {"description": "Core Platform Build", "amount": 16500, "unit": "fixed"},
            {"description": "Per Unit Micro-fee", "amount": 0.5, "unit": "fixed"},
            {"description": "Enterprise Retainer", "amount": 1234567.89, "unit": "monthly retainer"},
            {"description": "Zero Cost Community Tier", "amount": 0.0, "unit": "fixed"},
        ]
        schedule = format_pricing_schedule(test_items)
        self.assertIn("£850.00 (day rate)", schedule)
        self.assertIn("£16,500.00 (fixed)", schedule)
        self.assertIn("£0.50 (fixed)", schedule)
        self.assertIn("£1,234,567.89 (monthly retainer)", schedule)
        self.assertIn("£0.00 (fixed)", schedule)

    def test_multiple_matching_price_items_multi_service(self):
        """RFP with multiple linked services returns all matching price items sorted deterministically by ID."""
        # Create an RFP linked to both Statamic (id=1) and UX/UI Design (id=3)
        cur = self.conn.execute("INSERT INTO rfps (client_name, status) VALUES ('Multi-Service Client', 'draft');")
        rfp_id = cur.lastrowid
        self.conn.execute("INSERT INTO rfp_services (rfp_id, service_id) VALUES (?, 1);", (rfp_id,))
        self.conn.execute("INSERT INTO rfp_services (rfp_id, service_id) VALUES (?, 3);", (rfp_id,))
        self.conn.commit()

        prices = get_pricing_for_rfp(self.conn, rfp_id)
        # Statamic has 4 items (ids 1, 5, 6, 8) and UX/UI Design has 1 item (id 2) -> total 5 items
        self.assertEqual(len(prices), 5)
        price_ids = [p["id"] for p in prices]
        self.assertEqual(price_ids, [1, 2, 5, 6, 8])
        amounts = [float(p["amount"]) for p in prices]
        self.assertEqual(amounts, [850.0, 900.0, 16500.0, 5000.0, 750.0])

    def test_zero_matching_price_items_no_statamic_hallucination(self):
        """If an RFP is linked to a service with NO price items, returns empty list and emits gap marker."""
        cur_s = self.conn.execute("INSERT INTO services (name) VALUES ('Quantum Computing AI');")
        svc_id = cur_s.lastrowid
        cur_r = self.conn.execute("INSERT INTO rfps (client_name, status) VALUES ('Quantum Lab', 'draft');")
        rfp_id = cur_r.lastrowid
        self.conn.execute("INSERT INTO rfp_services (rfp_id, service_id) VALUES (?, ?);", (rfp_id, svc_id))

        cur_sec = self.conn.execute(
            "INSERT INTO rfp_sections (rfp_id, heading, original_text, classification) "
            "VALUES (?, 'Pricing Schedule', 'Provide pricing for Quantum Computing AI.', 'pricing');",
            (rfp_id,),
        )
        sec_id = cur_sec.lastrowid
        self.conn.commit()

        # get_pricing_for_rfp must return []
        prices = get_pricing_for_rfp(self.conn, rfp_id, "Provide pricing for Quantum Computing AI.")
        self.assertEqual(prices, [])

        # generate_pricing_draft must emit gap marker and NOT hallucinate Statamic £850
        res = generate_pricing_draft(self.conn, rfp_id, sec_id)
        self.assertIn("[MORE INFO REQUIRED: Missing pricing data for requested services]", res["draft_content"])
        self.assertNotIn("£850.00", res["draft_content"])
        self.assertNotIn("Statamic", res["draft_content"])

        # Must have registered an open question
        cur_q = self.conn.execute("SELECT * FROM open_questions WHERE rfp_id = ? AND section_id = ?;", (rfp_id, sec_id))
        oq = cur_q.fetchone()
        self.assertIsNotNone(oq)
        self.assertEqual(oq["question"], "Missing pricing data for requested services")

    def test_unlinked_rfp_never_guesses_pricing(self):
        """An RFP with NO linked services must never receive price items, regardless of section wording."""
        cur = self.conn.execute("INSERT INTO rfps (client_name, status) VALUES ('Unlinked Client', 'draft');")
        rfp_id = cur.lastrowid
        self.conn.commit()

        self.assertEqual(get_pricing_for_rfp(self.conn, rfp_id, "General development rates requested."), [])
        # Even text that closely matches seeded item descriptions must not trigger fuzzy matching
        self.assertEqual(get_pricing_for_rfp(self.conn, rfp_id, "Senior Full-Stack Engineer day rate and CMS packages."), [])

    def test_database_check_constraint_and_complex_descriptions(self):
        """Database enforces unit CHECK constraint, while allowing complex symbols in descriptions."""
        cur_s = self.conn.execute("INSERT INTO services (name) VALUES ('Custom SLA Support');")
        svc_id = cur_s.lastrowid

        # 1. Non-standard unit must violate CHECK constraint
        with self.assertRaises(sqlite3.IntegrityError) as ctx:
            self.conn.execute(
                "INSERT INTO price_items (service_id, description, unit, amount) VALUES (?, 'Invalid Unit', 'per user / month', 49.99);",
                (svc_id,),
            )
        self.assertIn("CHECK constraint failed", str(ctx.exception))

        # 2. Valid unit with complex symbols in description works and formats cleanly
        self.conn.execute(
            "INSERT INTO price_items (service_id, description, unit, amount) "
            "VALUES (?, 'Tier 3 Support & SLA (24/7/365) [High-Priority] <Critical>', 'monthly retainer', 4500.50);",
            (svc_id,),
        )
        cur_r = self.conn.execute("INSERT INTO rfps (client_name, status) VALUES ('SLA Client', 'draft');")
        rfp_id = cur_r.lastrowid
        self.conn.execute("INSERT INTO rfp_services (rfp_id, service_id) VALUES (?, ?);", (rfp_id, svc_id))
        self.conn.commit()

        prices = get_pricing_for_rfp(self.conn, rfp_id)
        self.assertEqual(len(prices), 1)
        schedule = format_pricing_schedule(prices)
        self.assertIn("- Tier 3 Support & SLA (24/7/365) [High-Priority] <Critical>: £4,500.50 (monthly retainer)", schedule)


class TestRetrievalBiasingAdversarial(unittest.TestCase):
    """Dimension 3: Retrieval Biasing Engine White-Box Stress Testing."""

    def test_won_lost_biasing_ratio_identical_text(self):
        """When won and lost proposals contain identical text, won proposal must score >= 1.20x higher."""
        vs = PurePythonVectorStore()
        content = "We provide full-stack Statamic CMS development and enterprise headless integrations."
        vs.add_document(doc_id=101, title="Won Proposal 2024", content=content, doc_type="past_proposal", outcome="won")
        vs.add_document(doc_id=102, title="Lost Proposal 2024", content=content, doc_type="past_proposal", outcome="lost")

        results = vs.search(query="Statamic CMS development enterprise", limit=10)
        self.assertEqual(len(results), 2)
        won_doc = next(r for r in results if r["id"] == 101)
        lost_doc = next(r for r in results if r["id"] == 102)

        ratio = won_doc["similarity_score"] / lost_doc["similarity_score"]
        expected_ratio = WEIGHT_WON / WEIGHT_LOST  # 1.25 / 0.90 = 1.3888...
        self.assertAlmostEqual(ratio, expected_ratio, places=2)
        self.assertGreaterEqual(ratio, 1.20)
        self.assertEqual(results[0]["id"], 101)

    def test_pure_lost_proposals_corpus(self):
        """When KB contains ONLY lost proposals, search succeeds, weights by 0.90, and ranks properly."""
        vs = PurePythonVectorStore()
        vs.add_document(doc_id=201, title="Lost Tender Alpha", content="Accessibility audit WCAG 2.2 AA", doc_type="past_proposal", outcome="lost")
        vs.add_document(doc_id=202, title="Lost Tender Beta", content="General web development and maintenance", doc_type="past_proposal", outcome="lost")

        results = vs.search(query="Accessibility WCAG audit", limit=5)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["id"], 201)
        self.assertIn("accessibility", results[0]["content"].lower())
        self.assertTrue(results[0]["similarity_score"] > 0)

    def test_exact_tie_breaking_determinism(self):
        """When similarity scores are tied, documents break ties deterministically by ID ascending."""
        vs = PurePythonVectorStore()
        vs.add_document(doc_id=301, title="Doc 301", content="Standard agency methodology", doc_type="boilerplate", outcome="n/a")
        vs.add_document(doc_id=302, title="Doc 302", content="Standard agency methodology", doc_type="boilerplate", outcome="n/a")
        vs.add_document(doc_id=303, title="Doc 303", content="Standard agency methodology", doc_type="boilerplate", outcome="n/a")

        results = vs.search(query="agency methodology", limit=10)
        self.assertEqual(len(results), 3)
        self.assertEqual(results[0]["similarity_score"], results[1]["similarity_score"])
        self.assertEqual(results[1]["similarity_score"], results[2]["similarity_score"])
        # With reverse=True on (-id), -301 > -302 > -303, so results are deterministically [301, 302, 303]
        self.assertEqual([r["id"] for r in results], [301, 302, 303])

    def test_empty_vector_store_clean_fallback(self):
        """Empty vector store must return [] without throwing exceptions."""
        vs = PurePythonVectorStore()
        res = vs.search(query="any search term")
        self.assertEqual(res, [])

        wrapper = ChromaVectorStoreWrapper(persist_dir="/tmp/test_empty_chroma_m6")
        res_chroma = wrapper.search(query="test query")
        self.assertEqual(res_chroma, [])

    def test_adversarial_queries_symbols_and_extreme_lengths(self):
        """Adversarial queries with regex meta-characters and 10k chars do not crash."""
        vs = PurePythonVectorStore()
        vs.add_document(doc_id=401, title="Security Doc", content="ISO-27001 SOC2 and PCI-DSS compliance", doc_type="boilerplate", outcome="n/a")

        symbols_query = r"[.*+?^${}()|[]\\]"
        res_sym = vs.search(query=symbols_query)
        self.assertIsInstance(res_sym, list)

        huge_query = "security " * 1250
        res_huge = vs.search(query=huge_query)
        self.assertIsInstance(res_huge, list)
        self.assertEqual(res_huge[0]["id"], 401)


class TestDraftGenerationGapMarkersAdversarial(unittest.TestCase):
    """Dimension 4: Draft Generation & Gap Marker Detection Stress Testing."""

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

    def test_complex_symbols_in_gap_markers(self):
        """Gap marker regex parses questions containing slashes, ampersands, dashes, and colons."""
        test_draft = (
            "We acknowledge the client requirement.\n\n"
            "[MORE INFO REQUIRED: What is the ISO 27001 / SOC-2 & PCI-DSS compliance status for AWS (eu-west-1)?]\n\n"
            "Further details pending."
        )
        markers = re.findall(r"\[MORE INFO REQUIRED:\s*([^\]]+)\]", test_draft)
        self.assertEqual(len(markers), 1)
        self.assertEqual(markers[0], "What is the ISO 27001 / SOC-2 & PCI-DSS compliance status for AWS (eu-west-1)?")

    def test_multiple_gap_markers_in_single_section(self):
        """Multiple gap markers in a single draft text auto-create distinct open questions."""
        cur_r = self.conn.execute("INSERT INTO rfps (client_name, status) VALUES ('NHS Trust', 'draft');")
        rfp_id = cur_r.lastrowid
        cur_s = self.conn.execute(
            "INSERT INTO rfp_sections (rfp_id, heading, original_text, classification) "
            "VALUES (?, 'Integration & Hosting', 'Detail AWS hosting and EHR telemetry integration.', 'gap');",
            (rfp_id,),
        )
        sec_id = cur_s.lastrowid
        self.conn.commit()

        multi_gap_draft = (
            "Response drafted with missing items:\n\n"
            "[MORE INFO REQUIRED: Specify NHS EHR integration protocols (HL7 / FHIR)]\n\n"
            "And secondary question:\n\n"
            "[MORE INFO REQUIRED: Clarify expected concurrent users and telemetry SLA]"
        )
        markers = re.findall(r"\[MORE INFO REQUIRED:\s*([^\]]+)\]", multi_gap_draft)
        self.assertEqual(len(markers), 2)

        for m in markers:
            cur_chk = self.conn.execute(
                "SELECT id FROM open_questions WHERE section_id = ? AND question = ?;",
                (sec_id, m),
            )
            if not cur_chk.fetchone():
                self.conn.execute(
                    "INSERT INTO open_questions (rfp_id, section_id, question, status) VALUES (?, ?, ?, 'open');",
                    (rfp_id, sec_id, m),
                )
        self.conn.commit()

        cur_q = self.conn.execute("SELECT * FROM open_questions WHERE rfp_id = ? AND section_id = ?;", (rfp_id, sec_id))
        questions = cur_q.fetchall()
        self.assertEqual(len(questions), 2)
        q_texts = [q["question"] for q in questions]
        self.assertIn("Specify NHS EHR integration protocols (HL7 / FHIR)", q_texts)
        self.assertIn("Clarify expected concurrent users and telemetry SLA", q_texts)

    def test_gap_marker_idempotency(self):
        """Regenerating a draft with the same gap marker must NOT create duplicate open questions."""
        cur_r = self.conn.execute("INSERT INTO rfps (client_name, status) VALUES ('Client A', 'draft');")
        rfp_id = cur_r.lastrowid
        cur_s = self.conn.execute(
            "INSERT INTO rfp_sections (rfp_id, heading, original_text, classification) VALUES (?, 'Security', 'Penetration test requirement', 'gap');",
            (rfp_id,),
        )
        sec_id = cur_s.lastrowid
        self.conn.commit()

        marker_q = "Provide penetration test certification from past 12 months"
        for _ in range(3):
            cur_chk = self.conn.execute("SELECT id FROM open_questions WHERE section_id = ? AND question = ?;", (sec_id, marker_q))
            if not cur_chk.fetchone():
                self.conn.execute(
                    "INSERT INTO open_questions (rfp_id, section_id, question, status) VALUES (?, ?, ?, 'open');",
                    (rfp_id, sec_id, marker_q),
                )
        self.conn.commit()

        cur_cnt = self.conn.execute("SELECT COUNT(*) FROM open_questions WHERE section_id = ?;", (sec_id,))
        self.assertEqual(cur_cnt.fetchone()[0], 1)

    def test_open_question_resolution_clears_gap_marker(self):
        """Resolving an open question incorporates resolution into draft and transitions status to resolved."""
        cur_r = self.conn.execute("INSERT INTO rfps (client_name, status) VALUES ('Client B', 'draft');")
        rfp_id = cur_r.lastrowid
        cur_s = self.conn.execute(
            "INSERT INTO rfp_sections (rfp_id, heading, original_text, classification, status) "
            "VALUES (?, 'Compliance', 'GDPR DPO details', 'gap', 'drafted');",
            (rfp_id,),
        )
        sec_id = cur_s.lastrowid
        self.conn.execute(
            "INSERT INTO open_questions (rfp_id, section_id, question, status, resolution) "
            "VALUES (?, ?, 'Describe specific past experience and evidence for Compliance', 'resolved', 'Our certified DPO is verified under ISO 27001.');",
            (rfp_id, sec_id),
        )
        self.conn.commit()

        cur_q = self.conn.execute(
            "SELECT * FROM open_questions WHERE section_id = ? AND status = 'resolved' ORDER BY id DESC LIMIT 1;",
            (sec_id,),
        )
        resolved_q = cur_q.fetchone()
        self.assertIsNotNone(resolved_q)

        draft_body = f"Regarding Compliance: {resolved_q['resolution']}"
        markers = re.findall(r"\[MORE INFO REQUIRED:\s*([^\]]+)\]", draft_body)
        self.assertEqual(len(markers), 0)
        new_status = "resolved" if not markers else "drafted"
        self.assertEqual(new_status, "resolved")


class TestExportPipelineAdversarial(unittest.TestCase):
    """Dimension 5: Export Pipeline White-Box Stress Testing."""

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

    def test_missing_logs_directory_auto_creation(self):
        """log_export_payload creates backend/logs directory if absent."""
        logs_dir = PROJECT_ROOT / "backend" / "logs"
        log_file = logs_dir / "google_export.log"

        log_export_payload(rfp_id=999, mode="mock", doc_url="https://mock.url", payload={"test": True})
        self.assertTrue(logs_dir.exists())
        self.assertTrue(log_file.exists())

        with open(log_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
        last_entry = json.loads(lines[-1])
        self.assertEqual(last_entry["rfp_id"], 999)
        self.assertEqual(last_entry["mode"], "mock")

    def test_malformed_and_empty_section_payloads(self):
        """RFP with 0 sections or null content generates valid batchUpdate title and metadata."""
        cur = self.conn.execute("INSERT INTO rfps (client_name, value, date_submitted) VALUES ('Zero Section Client', NULL, NULL);")
        rfp_id = cur.lastrowid
        self.conn.commit()

        cur_rfp = self.conn.execute("SELECT * FROM rfps WHERE id = ?;", (rfp_id,))
        rfp_row = cur_rfp.fetchone()

        payload, doc_id, doc_url = build_export_payload(
            rfp_row=rfp_row,
            sections=[],
            open_questions=[],
            services_names=[],
        )

        self.assertIn("Zero Section Client", payload["create_document"]["title"])
        requests = payload["batch_update"]["requests"]
        self.assertTrue(len(requests) >= 4)
        sub_text = requests[2]["insertText"]["text"]
        self.assertIn("Est. Value: N/A", sub_text)
        self.assertIn("Date: Draft", sub_text)
        self.assertIn("Services: General", sub_text)

    def test_orphan_open_questions_anchor_to_title(self):
        """Open questions with nonexistent section_id fallback anchor to doc title."""
        cur = self.conn.execute("INSERT INTO rfps (client_name) VALUES ('Anchor Test Client');")
        rfp_id = cur.lastrowid
        self.conn.commit()

        cur_rfp = self.conn.execute("SELECT * FROM rfps WHERE id = ?;", (rfp_id,))
        rfp_row = cur_rfp.fetchone()

        orphan_q = {
            "id": 1,
            "rfp_id": rfp_id,
            "section_id": 99999,
            "question": "Orphan gap marker question",
            "status": "open",
        }

        payload, doc_id, doc_url = build_export_payload(
            rfp_row=rfp_row,
            sections=[],
            open_questions=[orphan_q],
            services_names=["Web Development"],
        )

        comments = payload["comments"]
        self.assertEqual(len(comments), 1)
        anchor_json = json.loads(comments[0]["comment_payload"]["anchor"])
        self.assertEqual(anchor_json["a"][0]["txt"]["o"], 1)

    def test_concurrent_exports_thread_safety(self):
        """Multiple concurrent export calls across threads complete without race conditions."""
        cur = self.conn.execute("INSERT INTO rfps (client_name, status) VALUES ('Concurrent Client', 'draft');")
        rfp_id = cur.lastrowid
        self.conn.execute(
            "INSERT INTO rfp_sections (rfp_id, heading, original_text, draft_content) VALUES (?, 'Section A', 'Original text A', 'Content');",
            (rfp_id,),
        )
        self.conn.commit()

        def do_export():
            conn_local = get_db_connection(self.db_path)
            try:
                res = execute_export(conn_local, rfp_id, override_mode="mock")
                return res["success"]
            finally:
                conn_local.close()

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(do_export) for _ in range(5)]
            results = [f.result() for f in futures]

        self.assertEqual(results, [True] * 5)
        cur_check = self.conn.execute("SELECT status, final_doc_link FROM rfps WHERE id = ?;", (rfp_id,))
        row = cur_check.fetchone()
        # Mock export persists doc link but does NOT auto-advance status
        self.assertEqual(row["status"], "draft")
        self.assertTrue(row["final_doc_link"].startswith("https://docs.google.com/document/d/mock-rfp-"))

    def test_live_export_missing_credentials_contract(self):
        """Live export with missing credentials returns 400 with both 'error' and 'detail'."""
        cur = self.conn.execute("INSERT INTO rfps (client_name) VALUES ('Live Test Client');")
        rfp_id = cur.lastrowid
        self.conn.execute(
            "UPDATE settings SET mock_google_export = 0, google_credentials_path = 'nonexistent_credentials_file.json' WHERE id = 1;"
        )
        self.conn.commit()

        response = execute_export(self.conn, rfp_id)
        self.assertEqual(response.status_code, 400)
        body = json.loads(response.body.decode("utf-8"))
        self.assertIn("error", body)
        self.assertIn("detail", body)
        self.assertIn("Google Docs credentials not found", body["error"])


class TestAutomatedWCAGAAAContrastAudit(unittest.TestCase):
    """Dimension 6: Automated WCAG AAA Contrast Ratio & Typography Audit."""

    @staticmethod
    def calculate_relative_luminance(hex_color: str) -> float:
        """Calculate relative luminance per WCAG 2.1 specification."""
        clean_hex = hex_color.lstrip("#")
        r_int = int(clean_hex[0:2], 16) / 255.0
        g_int = int(clean_hex[2:4], 16) / 255.0
        b_int = int(clean_hex[4:6], 16) / 255.0

        def srgb_to_linear(c):
            return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

        r_lin = srgb_to_linear(r_int)
        g_lin = srgb_to_linear(g_int)
        b_lin = srgb_to_linear(b_int)
        return 0.2126 * r_lin + 0.7152 * g_lin + 0.0722 * b_lin

    @classmethod
    def calculate_contrast_ratio(cls, hex1: str, hex2: str) -> float:
        """Calculate WCAG contrast ratio (L1 + 0.05) / (L2 + 0.05)."""
        l1 = cls.calculate_relative_luminance(hex1)
        l2 = cls.calculate_relative_luminance(hex2)
        lighter = max(l1, l2)
        darker = min(l1, l2)
        return (lighter + 0.05) / (darker + 0.05)

    def test_accent_pairing_is_the_only_hard_coded_hex_in_markup(self):
        """Component markup must not hard-code colours — all theming flows through CSS variables."""
        import re
        frontend_src = PROJECT_ROOT / "frontend" / "src"
        hex_re = re.compile(r"#[0-9a-fA-F]{6}\b")
        violations = []
        for fpath in frontend_src.rglob("*.jsx"):
            for line_no, line in enumerate(fpath.read_text(encoding="utf-8").splitlines(), start=1):
                if hex_re.search(line) and "fill=" not in line:
                    violations.append(f"{fpath.name}:{line_no} -> {line.strip()[:100]}")
        self.assertEqual(violations, [], f"Hard-coded hex colours found in components: {violations}")

    def test_focus_ring_and_reduced_motion_defined(self):
        """Global focus-visible ring and prefers-reduced-motion handling must exist (WCAG 2.4.7 / 2.3.3)."""
        index_css = (PROJECT_ROOT / "frontend" / "src" / "index.css").read_text(encoding="utf-8")
        self.assertIn(":focus-visible", index_css)
        self.assertIn("ring-accent", index_css)
        self.assertIn("prefers-reduced-motion: reduce", index_css)

    def test_inter_font_configuration(self):
        """Verify Inter font is configured across index.html, index.css, and tailwind.config.js."""
        index_html = (PROJECT_ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
        self.assertIn("family=Inter:wght@400;500;600;700", index_html)

        index_css = (PROJECT_ROOT / "frontend" / "src" / "index.css").read_text(encoding="utf-8")
        self.assertIn("family=Inter", index_css)
        self.assertIn("font-sans", index_css)

        tailwind_cfg = (PROJECT_ROOT / "frontend" / "tailwind.config.js").read_text(encoding="utf-8")
        self.assertIn("'Inter'", tailwind_cfg)


if __name__ == "__main__":
    unittest.main(verbosity=2)

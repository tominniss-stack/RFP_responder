#!/usr/bin/env python3
"""
Challenger 2 (teamwork_preview_challenger) — Milestone 6 Empirical Verification Suite
Exhaustively executes:
1. The 6-Step Manual Walkthrough script on BOTH sample_rfp.docx and sample_rfp.pdf
   using the real FastAPI backend application stack and database.
2. Every single Acceptance Criteria item from ORIGINAL_REQUEST.md.
"""

import glob
import io
import json
import os
import sys
import unittest
from pathlib import Path

# Ensure backend, project root, and virtualenv site-packages are in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

venv_pkgs = glob.glob(str(PROJECT_ROOT / ".venv" / "lib" / "python*" / "site-packages"))
for p in venv_pkgs:
    if p not in sys.path:
        sys.path.insert(0, p)

from fastapi.testclient import TestClient
from app.main import app
from app.database import get_db_connection, init_db


class TestManualWalkthroughAndAcceptanceCriteria(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Ensure database tables and seed data exist before running walkthrough
        init_db()
        cls.client = TestClient(app)
        cls.docx_path = PROJECT_ROOT / "backend" / "data" / "sample_rfp.docx"
        cls.pdf_path = PROJECT_ROOT / "backend" / "data" / "sample_rfp.pdf"
        cls.export_log_path = PROJECT_ROOT / "backend" / "logs" / "google_export.log"

        assert cls.docx_path.exists(), f"Missing {cls.docx_path}"
        assert cls.pdf_path.exists(), f"Missing {cls.pdf_path}"

    # =========================================================================
    # PART 1: 6-STEP MANUAL WALKTHROUGH ON REAL APPLICATION STACK
    # =========================================================================

    def test_01_walkthrough_step1_upload_sample_rfp_docx_and_pdf(self):
        """Step 1: Upload sample RFP (both .docx and .pdf) -> verify extracted structure."""
        # 1.1 Upload DOCX
        with open(self.docx_path, "rb") as f:
            docx_bytes = f.read()

        res_docx = self.client.post(
            "/api/rfps/upload",
            data={"client_name": "Walkthrough DOCX Client", "value": "75000"},
            files={"file": ("sample_rfp.docx", docx_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        )
        self.assertIn(res_docx.status_code, [200, 201])
        docx_data = res_docx.json()
        self.assertEqual(docx_data["sections_count"], 7)
        docx_rfp_id = docx_data["rfp_id"]

        # Verify sections structure and ordering for DOCX
        detail_docx = self.client.get(f"/api/rfps/{docx_rfp_id}").json()
        sections_docx = detail_docx["sections"]
        self.assertEqual(len(sections_docx), 7)
        expected_headings = [
            "1. Agency Overview & Company Credentials",
            "2. Technical Architecture & CMS Platform Recommendation",
            "3. Commercial Quotation & Pricing Schedule",
            "4. Public Sector Healthcare & NHS Portal Experience",
            "5. Approach to Accessibility Compliance & Implementation Experience",
            "6. Information Governance, Data Protection & Mandatory Declarations",
            "7. Technical SEO, Search Marketing & SLA Governance",
        ]
        for idx, s in enumerate(sections_docx, start=1):
            self.assertEqual(s["sort_order"], idx)
            self.assertEqual(s["heading"], expected_headings[idx - 1])
            self.assertTrue(len(s["original_text"]) > 50)

        # 1.2 Upload PDF
        with open(self.pdf_path, "rb") as f:
            pdf_bytes = f.read()

        res_pdf = self.client.post(
            "/api/rfps/upload",
            data={"client_name": "Walkthrough PDF Client", "value": "85000"},
            files={"file": ("sample_rfp.pdf", pdf_bytes, "application/pdf")},
        )
        self.assertIn(res_pdf.status_code, [200, 201])
        pdf_data = res_pdf.json()
        self.assertEqual(pdf_data["sections_count"], 7)
        pdf_rfp_id = pdf_data["rfp_id"]

        # Verify sections structure and ordering for PDF
        detail_pdf = self.client.get(f"/api/rfps/{pdf_rfp_id}").json()
        sections_pdf = detail_pdf["sections"]
        self.assertEqual(len(sections_pdf), 7)
        for idx, s in enumerate(sections_pdf, start=1):
            self.assertEqual(s["sort_order"], idx)
            self.assertEqual(s["heading"], expected_headings[idx - 1])
            self.assertTrue(len(s["original_text"]) > 50)

    def test_02_walkthrough_step2_classifications_sensible_and_manual_override(self):
        """Step 2: Check section classifications are sensible and verify manual override."""
        # Create fresh RFP via upload
        with open(self.docx_path, "rb") as f:
            docx_bytes = f.read()
        res = self.client.post(
            "/api/rfps/upload",
            data={"client_name": "Classification Test Client", "value": "50000"},
            files={"file": ("sample_rfp.docx", docx_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        )
        rfp_id = res.json()["rfp_id"]

        # Trigger classification
        class_res = self.client.post(f"/api/rfps/{rfp_id}/classify")
        self.assertEqual(class_res.status_code, 200)
        classifications = class_res.json()
        self.assertEqual(len(classifications), 7)

        class_map = {item["heading"]: item for item in classifications}

        # Verify classifications are sensible:
        # 1. Agency Overview -> boilerplate
        self.assertEqual(class_map["1. Agency Overview & Company Credentials"]["classification"], "boilerplate")
        # 2. Technical Architecture -> strategic_decision
        self.assertEqual(class_map["2. Technical Architecture & CMS Platform Recommendation"]["classification"], "strategic_decision")
        # 3. Commercial Quotation -> pricing
        self.assertEqual(class_map["3. Commercial Quotation & Pricing Schedule"]["classification"], "pricing")
        # 4. Public Sector Healthcare -> gap
        self.assertEqual(class_map["4. Public Sector Healthcare & NHS Portal Experience"]["classification"], "gap")
        # 5. Accessibility -> strategic_decision (deliberately ambiguous section)
        self.assertIn(class_map["5. Approach to Accessibility Compliance & Implementation Experience"]["classification"], ["strategic_decision", "gap"])
        # 6. Information Governance -> compliance_admin
        self.assertEqual(class_map["6. Information Governance, Data Protection & Mandatory Declarations"]["classification"], "compliance_admin")

        # Verify manual override capability: override section 5 to gap, then back to strategic_decision
        sec5_id = class_map["5. Approach to Accessibility Compliance & Implementation Experience"]["section_id"]
        override_res = self.client.patch(
            f"/api/rfps/{rfp_id}/sections/{sec5_id}",
            json={"classification": "gap"}
        )
        self.assertEqual(override_res.status_code, 200)
        self.assertEqual(override_res.json()["classification"], "gap")

        # Verify persisted in detail view
        detail = self.client.get(f"/api/rfps/{rfp_id}").json()
        sec5 = next(s for s in detail["sections"] if s["id"] == sec5_id)
        self.assertEqual(sec5["classification"], "gap")

        # Override back
        override_res2 = self.client.patch(
            f"/api/rfps/{rfp_id}/sections/{sec5_id}",
            json={"classification": "strategic_decision"}
        )
        self.assertEqual(override_res2.status_code, 200)
        self.assertEqual(override_res2.json()["classification"], "strategic_decision")

    def test_03_walkthrough_step3_generate_drafts_pricing_boilerplate_gap(self):
        """Step 3: Generate drafts -> verify pricing figures (£850, £16,500), boilerplate pulls from KB, gap marker appears."""
        with open(self.docx_path, "rb") as f:
            docx_bytes = f.read()
        res = self.client.post(
            "/api/rfps/upload",
            data={"client_name": "Drafts Test Client", "value": "60000", "services": ["1"]},
            files={"file": ("sample_rfp.docx", docx_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        )
        rfp_id = res.json()["rfp_id"]
        self.client.post(f"/api/rfps/{rfp_id}/classify")

        detail = self.client.get(f"/api/rfps/{rfp_id}").json()
        sections_by_sort = {s["sort_order"]: s for s in detail["sections"]}

        # 3.1 Boilerplate generation (Section 1)
        sec1_id = sections_by_sort[1]["id"]
        res_bp = self.client.post(f"/api/rfps/{rfp_id}/sections/{sec1_id}/generate")
        self.assertEqual(res_bp.status_code, 200)
        draft_bp = res_bp.json()["draft_content"]
        self.assertIn("Another Marketing Agency is a UK digital agency", draft_bp)
        self.assertIn("ISO 27001", draft_bp)
        self.assertIn("Cyber Essentials Plus", draft_bp)
        self.assertIn("£5,000,000", draft_bp)

        # 3.2 Pricing generation (Section 3)
        sec3_id = sections_by_sort[3]["id"]
        res_price = self.client.post(f"/api/rfps/{rfp_id}/sections/{sec3_id}/generate")
        self.assertEqual(res_price.status_code, 200)
        draft_price = res_price.json()["draft_content"]
        # Exact figures verification (£850 and £16,500)
        self.assertIn("£850.00 (day rate)", draft_price)
        self.assertIn("£16,500.00 (fixed)", draft_price)
        # Ensure no approximation words
        self.assertNotIn("around", draft_price.lower())
        self.assertNotIn("approximately", draft_price.lower())

        # 3.3 Gap generation (Section 4: NHS Portal Experience)
        sec4_id = sections_by_sort[4]["id"]
        res_gap = self.client.post(f"/api/rfps/{rfp_id}/sections/{sec4_id}/generate")
        self.assertEqual(res_gap.status_code, 200)
        draft_gap = res_gap.json()["draft_content"]
        self.assertIn("[MORE INFO REQUIRED:", draft_gap)

        # Check open question was automatically created
        oq_res = self.client.get(f"/api/rfps/{rfp_id}/open-questions")
        self.assertEqual(oq_res.status_code, 200)
        questions = oq_res.json()
        self.assertGreaterEqual(len(questions), 1)
        sec4_q = next((q for q in questions if q["section_id"] == sec4_id), None)
        self.assertIsNotNone(sec4_q)
        self.assertEqual(sec4_q["status"], "open")

    def test_04_walkthrough_step4_am_notes_influence_and_provenance(self):
        """Step 4: Add AM notes (whole-RFP brain dump + section note) -> verify draft influence and provenance."""
        with open(self.docx_path, "rb") as f:
            docx_bytes = f.read()
        res = self.client.post(
            "/api/rfps/{rfp_id}/upload".replace("{rfp_id}/", ""),
            data={"client_name": "AM Notes Client", "value": "65000"},
            files={"file": ("sample_rfp.docx", docx_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        )
        rfp_id = res.json()["rfp_id"]
        self.client.post(f"/api/rfps/{rfp_id}/classify")
        detail = self.client.get(f"/api/rfps/{rfp_id}").json()
        sections_by_sort = {s["sort_order"]: s for s in detail["sections"]}
        sec2_id = sections_by_sort[2]["id"]

        # Add whole-RFP note
        whole_note_text = "Client expressed high concern over legacy server downtime in Q1."
        res_wn = self.client.post(f"/api/rfps/{rfp_id}/notes", json={
            "raw_content": whole_note_text,
            "section_id": None
        })
        self.assertIn(res_wn.status_code, [200, 201])

        # Add section-specific note for section 2
        sec_note_text = "Emphasize Astro SSG multi-region caching to eliminate server latency."
        res_sn = self.client.post(f"/api/rfps/{rfp_id}/notes", json={
            "raw_content": sec_note_text,
            "section_id": sec2_id
        })
        self.assertIn(res_sn.status_code, [200, 201])

        # Generate draft for Section 2
        gen_res = self.client.post(f"/api/rfps/{rfp_id}/sections/{sec2_id}/generate")
        self.assertEqual(gen_res.status_code, 200)
        gen_data = gen_res.json()
        draft_content = gen_data["draft_content"]

        # Verify section-specific note visibly influences draft
        self.assertIn("Astro SSG multi-region caching", draft_content)

        # Verify provenance tags are present
        prov = gen_data["provenance"]
        prov_sources = [p["source"] for p in prov]
        self.assertIn("notes", prov_sources)
        self.assertIn("rag", prov_sources)

    def test_05_walkthrough_step5_resolve_open_question_and_regenerate(self):
        """Step 5: Resolve an open question -> verify status 'resolved' and draft regeneration."""
        with open(self.docx_path, "rb") as f:
            docx_bytes = f.read()
        res = self.client.post(
            "/api/rfps/upload",
            data={"client_name": "Resolve Question Client", "value": "70000"},
            files={"file": ("sample_rfp.docx", docx_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        )
        rfp_id = res.json()["rfp_id"]
        self.client.post(f"/api/rfps/{rfp_id}/classify")
        detail = self.client.get(f"/api/rfps/{rfp_id}").json()
        sections_by_sort = {s["sort_order"]: s for s in detail["sections"]}
        sec4_id = sections_by_sort[4]["id"]

        # Generate draft to create open question
        self.client.post(f"/api/rfps/{rfp_id}/sections/{sec4_id}/generate")
        questions = self.client.get(f"/api/rfps/{rfp_id}/open-questions").json()
        q = next(q for q in questions if q["section_id"] == sec4_id)
        q_id = q["id"]
        self.assertEqual(q["status"], "open")

        # Resolve open question
        resolution_answer = "Verified: We built the NHS Blood & Transplant digital portal with full clinical audit trails in 2024."
        put_res = self.client.put(
            f"/api/rfps/{rfp_id}/open-questions/{q_id}",
            json={"resolution": resolution_answer, "status": "resolved"}
        )
        self.assertEqual(put_res.status_code, 200)
        self.assertEqual(put_res.json()["status"], "resolved")

        # Verify question status in database
        q_after = self.client.get(f"/api/rfps/{rfp_id}/open-questions").json()
        q_updated = next(item for item in q_after if item["id"] == q_id)
        self.assertEqual(q_updated["status"], "resolved")
        self.assertEqual(q_updated["resolution"], resolution_answer)

        # Trigger section regeneration
        regen_res = self.client.post(f"/api/rfps/{rfp_id}/sections/{sec4_id}/generate")
        self.assertEqual(regen_res.status_code, 200)
        regen_draft = regen_res.json()["draft_content"]

        # Verify resolution answer appears in regenerated draft
        self.assertIn("NHS Blood & Transplant", regen_draft)
        # Verify [MORE INFO REQUIRED:] is now removed
        self.assertNotIn("[MORE INFO REQUIRED:", regen_draft)
        self.assertEqual(regen_res.json()["status"], "resolved")

    def test_06_walkthrough_step6_mock_export_to_google_doc(self):
        """Step 6: Export to Google Doc (mock mode) -> verify payload log and final_doc_link."""
        with open(self.docx_path, "rb") as f:
            docx_bytes = f.read()
        res = self.client.post(
            "/api/rfps/upload",
            data={"client_name": "Export Test Client", "value": "90000"},
            files={"file": ("sample_rfp.docx", docx_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        )
        rfp_id = res.json()["rfp_id"]
        self.client.post(f"/api/rfps/{rfp_id}/classify")
        detail = self.client.get(f"/api/rfps/{rfp_id}").json()
        sections_by_sort = {s["sort_order"]: s for s in detail["sections"]}

        # Draft section 1 and section 4
        self.client.post(f"/api/rfps/{rfp_id}/sections/{sections_by_sort[1]['id']}/generate")
        self.client.post(f"/api/rfps/{rfp_id}/sections/{sections_by_sort[4]['id']}/generate")

        # Unresolved question exists for section 4
        questions = self.client.get(f"/api/rfps/{rfp_id}/open-questions").json()
        self.assertTrue(any(q["status"] == "open" for q in questions))

        # Perform export
        export_res = self.client.post(f"/api/rfps/{rfp_id}/export")
        self.assertEqual(export_res.status_code, 200)
        exp_data = export_res.json()
        self.assertTrue(exp_data.get("success"))
        doc_url = exp_data.get("doc_url")
        self.assertTrue(doc_url.startswith("https://docs.google.com/document/d/mock-rfp-"))

        # Verify fake URL stored in rfps.final_doc_link
        rfp_check = self.client.get(f"/api/rfps/{rfp_id}").json()
        self.assertEqual(rfp_check["final_doc_link"], doc_url)
        # Mock export should persist the doc link but NOT auto-advance status
        # (status transitions are an explicit user action, not a side effect of dry-run)
        self.assertEqual(rfp_check["status"], "draft")

        # Verify logged payload in backend/logs/google_export.log
        self.assertTrue(self.export_log_path.exists())
        with open(self.export_log_path, "r") as f:
            lines = f.readlines()
        self.assertGreater(len(lines), 0)
        last_entry = json.loads(lines[-1])
        self.assertEqual(last_entry["rfp_id"], rfp_id)
        self.assertEqual(last_entry["mode"], "mock")
        self.assertEqual(last_entry["doc_url"], doc_url)

        payload = last_entry["payload"]
        self.assertIn("create_document", payload)
        self.assertIn("batch_update", payload)
        self.assertIn("comments", payload)
        # Check comment payload exists for unresolved question
        self.assertGreaterEqual(len(payload["comments"]), 1)
        comment_item = payload["comments"][0]
        self.assertIn("[MORE INFO REQUIRED]", comment_item["comment_payload"]["content"])
        self.assertIn("anchor", comment_item["comment_payload"])

    # =========================================================================
    # PART 2: ACCEPTANCE CRITERIA CHECKBOX VERIFICATIONS
    # =========================================================================

    def test_07_ac_all_pages_and_routes_exist_in_frontend(self):
        """Acceptance Criteria: all main pages exist and every route is wired in App.jsx."""
        pages_dir = PROJECT_ROOT / "frontend" / "src" / "pages"
        for p in ["RFPTracker.jsx", "NewRFP.jsx", "RFPDetail.jsx", "KnowledgeBase.jsx", "PricingAdmin.jsx", "ServicesAdmin.jsx", "Settings.jsx"]:
            self.assertTrue((pages_dir / p).exists(), f"Frontend page {p} missing")

        app_jsx = (PROJECT_ROOT / "frontend" / "src" / "App.jsx").read_text()
        for route in ["'tracker'", "'new-rfp'", "'rfp-detail'", "'settings'", "'services'", "'pricing'", "'kb'"]:
            self.assertIn(route, app_jsx, f"Route {route} not wired in App.jsx")
        # Pricing and Services are rendered as tabs inside Settings
        settings_jsx = (PROJECT_ROOT / "frontend" / "src" / "pages" / "Settings.jsx").read_text()
        self.assertIn("PricingAdmin", settings_jsx)
        self.assertIn("ServicesAdmin", settings_jsx)

    @staticmethod
    def _parse_tokens(css_text, selector):
        """Extract `--color-name: r g b` triplets from a :root or .dark block."""
        import re
        block = re.search(selector + r"\s*\{(.*?)\n\s*\}", css_text, re.DOTALL)
        assert block, f"{selector} block not found in index.css"
        return {m.group(1): tuple(int(v) for v in m.group(2).split()) for m in re.finditer(r"--color-([a-z-]+):\s*(\d+\s+\d+\s+\d+)", block.group(1))}

    @staticmethod
    def _contrast(fg, bg):
        def lum(rgb):
            def ch(c):
                c = c / 255
                return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
            r, g, b = (ch(c) for c in rgb)
            return 0.2126 * r + 0.7152 * g + 0.0722 * b
        l1, l2 = sorted([lum(fg), lum(bg)], reverse=True)
        return (l1 + 0.05) / (l2 + 0.05)

    def test_08_ac_design_tokens_complete_and_wcag_aa_in_both_themes(self):
        """Acceptance Criteria: every token is defined for light and dark, and key pairings meet WCAG 2.2 AA."""
        css = (PROJECT_ROOT / "frontend" / "src" / "index.css").read_text()
        light = self._parse_tokens(css, r":root")
        dark = self._parse_tokens(css, r"\.dark")

        required = {
            "canvas", "surface", "surface-raised", "ink", "ink-muted", "ink-inverse", "border", "border-strong",
            "accent", "accent-hover", "accent-ink", "accent-soft",
            "success", "success-soft", "warning", "warning-soft", "danger", "danger-soft", "info", "info-soft",
        }
        self.assertEqual(required - set(light), set(), "Light theme is missing tokens")
        self.assertEqual(required - set(dark), set(), "Dark theme is missing tokens")
        self.assertEqual(set(light), set(dark), "Light and dark must define exactly the same tokens")

        for name, theme in (("light", light), ("dark", dark)):
            # Text contrast ≥ 4.5:1 (WCAG 1.4.3)
            for fg, bg in [("ink", "canvas"), ("ink", "surface"), ("ink", "surface-raised"), ("ink-muted", "canvas"), ("ink-muted", "surface"), ("accent-ink", "accent"), ("ink", "accent-soft"), ("ink", "warning-soft"), ("ink", "danger-soft"), ("ink", "success-soft")]:
                ratio = self._contrast(theme[fg], theme[bg])
                self.assertGreaterEqual(ratio, 4.5, f"[{name}] {fg} on {bg} = {ratio:.2f}:1 (< 4.5)")
            # Non-text contrast ≥ 3:1 for interactive boundaries (WCAG 1.4.11)
            ratio = self._contrast(theme["border-strong"], theme["surface"])
            self.assertGreaterEqual(ratio, 3.0, f"[{name}] border-strong on surface = {ratio:.2f}:1 (< 3)")
            ratio = self._contrast(theme["accent"], theme["surface"])
            self.assertGreaterEqual(ratio, 3.0, f"[{name}] accent on surface = {ratio:.2f}:1 (< 3)")

        # Tailwind must consume tokens via CSS variables and expose the Inter typeface
        tailwind_cfg = (PROJECT_ROOT / "frontend" / "tailwind.config.js").read_text()
        self.assertIn("var(--color-", tailwind_cfg)
        self.assertIn("darkMode: 'class'", tailwind_cfg)
        self.assertIn("Inter", tailwind_cfg)

    def test_08b_ac_components_use_semantic_tokens_only(self):
        """Theming lint gate: no `dark:` colour prefixes and no raw Tailwind palette colours in components."""
        import re
        src = PROJECT_ROOT / "frontend" / "src"
        dark_prefix = re.compile(r"dark:(bg|text|border|ring|divide|fill|stroke)-")
        raw_palette = re.compile(r"\b(bg|text|border|ring|divide|fill|from|to)-(neutral|zinc|slate|gray|stone|amber|rose|red|emerald|green|sky|blue|purple|yellow|orange)-\d{2,3}\b")
        offenders = []
        for path in src.rglob("*.jsx"):
            for n, line in enumerate(path.read_text().splitlines(), start=1):
                if dark_prefix.search(line) or raw_palette.search(line):
                    offenders.append(f"{path.relative_to(src)}:{n}")
        self.assertEqual(offenders, [], "Components must use semantic tokens only:\n" + "\n".join(offenders))

    def test_09_ac_independent_model_selection_in_settings(self):
        """Acceptance Criteria: Independent model selection for classification and generation."""
        settings_res = self.client.get("/api/settings")
        self.assertEqual(settings_res.status_code, 200)
        s = settings_res.json()
        self.assertIn("classification_model", s)
        self.assertIn("generation_model", s)

        # Update independently
        update_res = self.client.put("/api/settings", json={
            "classification_model": "gemini-2.5-flash",
            "generation_model": "claude-sonnet-4-5",
            "claude_api_key": "sk-ant-test-12345",
            "gemini_api_key": "AIzaSyTest67890",
            "mock_google_export": 1,
            "google_credentials_path": "credentials.json",
            "system_prompt": "Test system prompt",
            "tone_of_voice_prompt": "Test tone prompt with executive summary sentence",
        })
        self.assertEqual(update_res.status_code, 200)
        updated = update_res.json()
        self.assertEqual(updated["classification_model"], "gemini-2.5-flash")
        self.assertEqual(updated["generation_model"], "claude-sonnet-4-5")

    def test_10_ac_mock_export_banner_and_readme_instructions(self):
        """Acceptance Criteria: Mock banner in UI and step-by-step OAuth instructions in README."""
        banner_jsx = (PROJECT_ROOT / "frontend" / "src" / "components" / "MockExportBanner.jsx").read_text()
        self.assertIn("NEEDS REAL GOOGLE CREDENTIALS TO TEST LIVE EXPORT", banner_jsx)
        self.assertIn("Configure in Settings", banner_jsx)

        readme_md = (PROJECT_ROOT / "README.md").read_text()
        self.assertIn("Google Cloud OAuth Setup", readme_md)
        self.assertIn("credentials.json", readme_md)
        self.assertIn("NEEDS REAL GOOGLE CREDENTIALS TO TEST LIVE EXPORT", readme_md)
        self.assertIn("./start.sh", readme_md)

    def test_11_ac_won_proposal_retrieval_ranking_biasing(self):
        """Acceptance Criteria: Retrieval ranking observably biases toward won proposals."""
        res = self.client.get("/api/kb", params={"query": "Digital Marketing"})
        self.assertEqual(res.status_code, 200)
        docs = res.json()
        self.assertGreaterEqual(len(docs), 2)

        won_doc = next((d for d in docs if d["outcome"] == "won" and "Digital Marketing" in d["title"]), None)
        lost_doc = next((d for d in docs if d["outcome"] == "lost" and "Digital Marketing" in d["title"]), None)

        self.assertIsNotNone(won_doc)
        self.assertIsNotNone(lost_doc)
        self.assertGreater(
            won_doc["similarity_score"],
            lost_doc["similarity_score"],
            "Won proposal must score higher than lost proposal for matching query"
        )


if __name__ == "__main__":
    unittest.main()

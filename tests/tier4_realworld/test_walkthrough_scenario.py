"""
Tier 4 Real-World Application Scenario: Automated 10-Step Manual Walkthrough Script (Section 8)
Simulates the complete end-to-end workflow of an Account Manager processing the National Heritage Trust sample RFP.
"""

import unittest
from tests.fixtures import (
    SAMPLE_RFP_CLIENT,
    SAMPLE_RFP_VALUE,
)
from tests.harness import TestHarnessClient


class TestRealWorldWalkthrough(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestHarnessClient()

    def test_full_10_step_real_world_walkthrough(self):
        """
        Executes the 10-step manual walkthrough script in strict sequential order:
        Step 1: Verify Seed Data & Settings
        Step 2: Ingest Sample RFP
        Step 3: Review Classifications & Override Ambiguity
        Step 4: Input Hybrid Account Manager Notes
        Step 5: Multi-Section Draft Generation
        Step 6: Provenance & Exact Pricing Verification
        Step 7: Open Question Detection & Display
        Step 8: Open Question Resolution & Section Regeneration
        Step 9: Mock Google Docs Export & Payload Audit
        Step 10: Tracker Audit, Filtering & Outcome Editing
        """

        # =========================================================================
        # STEP 1: Pre-Flight Environment & Seed Data Audit
        # =========================================================================
        # 1.1 Verify services
        srv_res = self.client.get("/api/services")
        self.assertEqual(srv_res.status_code, 200)
        services = srv_res.json()
        self.assertGreaterEqual(len(services), 5, "Step 1: Expected at least 5 seed services")

        # 1.2 Verify pricing
        price_res = self.client.get("/api/pricing")
        self.assertEqual(price_res.status_code, 200)
        prices = price_res.json()
        self.assertGreaterEqual(len(prices), 6, "Step 1: Expected at least 6 seed price items")

        # 1.3 Verify KB documents
        kb_res = self.client.get("/api/kb")
        self.assertEqual(kb_res.status_code, 200)
        kb_docs = kb_res.json()
        self.assertGreaterEqual(len(kb_docs), 5, "Step 1: Expected at least 5 seed KB documents")
        outcomes = [d.get("outcome") for d in kb_docs]
        self.assertIn("won", outcomes, "Step 1: Missing won proposal in KB")
        self.assertIn("lost", outcomes, "Step 1: Missing lost proposal in KB")

        # 1.4 Verify Settings
        settings_res = self.client.get("/api/settings")
        self.assertEqual(settings_res.status_code, 200)
        settings = settings_res.json()
        self.assertEqual(settings.get("mock_google_export"), 1, "Step 1: Mock export mode must be enabled by default")

        # =========================================================================
        # STEP 2: Ingest Sample RFP
        # =========================================================================
        upload_res = self.client.post("/api/rfps/upload", json_data={
            "client_name": SAMPLE_RFP_CLIENT,
            "value": SAMPLE_RFP_VALUE,
            "filename": "sample_rfp.docx",
            "file_bytes": b"sample-binary-stream",
        })
        self.assertIn(upload_res.status_code, [200, 201])
        rfp_id = upload_res.json()["rfp_id"]

        detail = self.client.get(f"/api/rfps/{rfp_id}").json()
        sections = detail.get("sections", [])
        self.assertEqual(len(sections), 7, f"Step 2: Expected exactly 7 extracted sections, got {len(sections)}")

        # =========================================================================
        # STEP 3: Review Classifications & Ambiguity Override
        # =========================================================================
        classify_res = self.client.post(f"/api/rfps/{rfp_id}/classify")
        self.assertEqual(classify_res.status_code, 200)

        detail_after_class = self.client.get(f"/api/rfps/{rfp_id}").json()
        sections_by_sort = {s["sort_order"]: s for s in detail_after_class["sections"]}

        # Check section classifications
        self.assertEqual(sections_by_sort[1]["classification"], "boilerplate", "Step 3: Section 1 should be boilerplate")
        self.assertEqual(sections_by_sort[2]["classification"], "strategic_decision", "Step 3: Section 2 should be strategic")
        self.assertIn(sections_by_sort[3]["classification"], ["strategic_decision", "gap"], "Step 3: Section 3 is ambiguous")
        self.assertEqual(sections_by_sort[5]["classification"], "pricing", "Step 3: Section 5 should be pricing")
        self.assertEqual(sections_by_sort[6]["classification"], "gap", "Step 3: Section 6 should be gap")
        self.assertEqual(sections_by_sort[7]["classification"], "compliance_admin", "Step 3: Section 7 should be compliance_admin")

        # Ambiguous section override: ensure it is strategic_decision
        sec3_id = sections_by_sort[3]["id"]
        override_res = self.client.patch(
            f"/api/rfps/{rfp_id}/sections/{sec3_id}",
            json_data={"classification": "strategic_decision"},
        )
        self.assertEqual(override_res.status_code, 200)
        self.assertEqual(override_res.json()["classification"], "strategic_decision")

        # =========================================================================
        # STEP 4: Input Hybrid Account Manager Notes
        # =========================================================================
        brain_dump_text = (
            "Client had a bad experience with WordPress in 2024. Strongly emphasise Statamic stability "
            "and our ISO 27001 certification. Aim for a 12-week delivery."
        )
        sec2_note_text = "Propose Statamic with Astro frontend for optimal page speed."

        # Whole-RFP Note
        self.client.post(f"/api/rfps/{rfp_id}/notes", json_data={"raw_content": brain_dump_text, "section_id": None})
        # Section 2 Note
        sec2_id = sections_by_sort[2]["id"]
        self.client.post(f"/api/rfps/{rfp_id}/notes", json_data={"raw_content": sec2_note_text, "section_id": sec2_id})

        notes = self.client.get(f"/api/rfps/{rfp_id}/notes").json()
        self.assertGreaterEqual(len(notes), 2, "Step 4: Notes not saved to DB")

        # =========================================================================
        # STEP 5: Multi-Section Draft Generation
        # =========================================================================
        # Generate Section 1 (Boilerplate)
        sec1_res = self.client.post(f"/api/rfps/{rfp_id}/sections/{sections_by_sort[1]['id']}/generate").json()
        self.assertIn("ISO 27001", sec1_res.get("draft_content", ""), "Step 5: Section 1 missing ISO 27001")

        # Generate Section 2 (Strategic with Notes)
        sec2_res = self.client.post(f"/api/rfps/{rfp_id}/sections/{sec2_id}/generate").json()
        draft2 = sec2_res.get("draft_content", "")
        self.assertIn("Statamic with Astro frontend", draft2, "Step 5: Section 2 missing section note text")

        # Generate Section 5 (Pricing)
        sec5_res = self.client.post(f"/api/rfps/{rfp_id}/sections/{sections_by_sort[5]['id']}/generate").json()
        draft5 = sec5_res.get("draft_content", "")
        self.assertTrue("850" in draft5 or "850.00" in draft5, "Step 5: Section 5 missing £850 rate")

        # Generate Section 6 (Gap)
        sec6_id = sections_by_sort[6]["id"]
        sec6_res = self.client.post(f"/api/rfps/{rfp_id}/sections/{sec6_id}/generate").json()
        draft6 = sec6_res.get("draft_content", "")
        self.assertIn("[MORE INFO REQUIRED:", draft6, "Step 5: Section 6 missing gap marker")

        # =========================================================================
        # STEP 6: Provenance & Exact Pricing Verification
        # =========================================================================
        sec2_prov = [p["source"] for p in sec2_res.get("provenance", [])]
        self.assertIn("notes", sec2_prov, "Step 6: Section 2 provenance missing notes tag")
        self.assertIn("rag", sec2_prov, "Step 6: Section 2 provenance missing rag tag")

        # Exact pricing check
        self.assertNotIn("around 800", draft5.lower())
        self.assertNotIn("approx", draft5.lower())

        # =========================================================================
        # STEP 7: Open Question Detection & Display
        # =========================================================================
        questions = self.client.get(f"/api/rfps/{rfp_id}/open-questions").json()
        self.assertGreaterEqual(len(questions), 1, "Step 7: Expected open question created for Section 6")
        target_q = next(q for q in questions if q["section_id"] == sec6_id)
        self.assertEqual(target_q["status"], "open", "Step 7: Question status should be 'open'")

        # =========================================================================
        # STEP 8: Open Question Resolution & Section Regeneration
        # =========================================================================
        resolution_text = "We delivered NHS Digital compliant telemetry endpoints for Northwind Renewables in 2025."
        res_call = self.client.put(
            f"/api/rfps/{rfp_id}/open-questions/{target_q['id']}",
            json_data={"resolution": resolution_text},
        )
        self.assertEqual(res_call.status_code, 200)
        self.assertEqual(res_call.json()["status"], "resolved")

        # Regenerate Section 6
        sec6_regen = self.client.post(f"/api/rfps/{rfp_id}/sections/{sec6_id}/generate").json()
        draft6_updated = sec6_regen.get("draft_content", "")
        self.assertIn("NHS Digital", draft6_updated, "Step 8: Regenerated draft missing resolution context")
        self.assertNotIn("[MORE INFO REQUIRED:", draft6_updated, "Step 8: Marker should be cleared after resolution")
        self.assertEqual(sec6_regen.get("status"), "resolved", "Step 8: Section status should be 'resolved'")

        # =========================================================================
        # STEP 9: Mock Google Docs Export & Payload Audit
        # =========================================================================
        export_res = self.client.post(f"/api/rfps/{rfp_id}/export")
        self.assertEqual(export_res.status_code, 200)
        export_data = export_res.json()
        self.assertTrue(export_data.get("success"), "Step 9: Export must report success")
        self.assertTrue(export_data.get("doc_url", "").startswith("https://docs.google.com/document/d/mock-rfp-"))

        # Check DB updated with link
        rfp_after_export = self.client.get(f"/api/rfps/{rfp_id}").json()
        self.assertEqual(rfp_after_export.get("final_doc_link"), export_data.get("doc_url"))
        # Mock export persists doc link but does NOT auto-advance status
        self.assertIn(rfp_after_export.get("status"), ("draft", "submitted"))

        # Verify comment count is 0 because all open questions are resolved
        comments_in_export = export_data.get("payload", {}).get("comments", [])
        self.assertEqual(len(comments_in_export), 0, "Step 9: Resolved questions should yield 0 comments")

        # =========================================================================
        # STEP 10: Tracker Audit, Filtering & Outcome Editing
        # =========================================================================
        # 10.1 Filter tracker list
        tracker_res = self.client.get("/api/rfps", params={"client_name": SAMPLE_RFP_CLIENT})
        self.assertEqual(tracker_res.status_code, 200)
        matched_rfps = tracker_res.json()
        self.assertTrue(any(r["id"] == rfp_id for r in matched_rfps), "Step 10: RFP not found in filtered tracker list")

        # 10.2 Edit outcome, value, and feedback
        outcome_feedback = "Client praised the Statamic Astro architecture and rapid turnaround."
        up_outcome_res = self.client.put(
            f"/api/rfps/{rfp_id}",
            json_data={
                "status": "won",
                "value": 78000.0,
                "outcome_feedback": outcome_feedback,
            },
        )
        self.assertEqual(up_outcome_res.status_code, 200)

        # 10.3 Verify persistent state
        final_rfp = self.client.get(f"/api/rfps/{rfp_id}").json()
        self.assertEqual(final_rfp.get("status"), "won")
        self.assertEqual(final_rfp.get("value"), 78000.0)
        self.assertEqual(final_rfp.get("outcome_feedback"), outcome_feedback)


if __name__ == "__main__":
    unittest.main()

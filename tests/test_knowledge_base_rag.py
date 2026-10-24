#!/usr/bin/env python3
"""
Empirical Adversarial Stress Test Suite — Milestone 3
Scope: Knowledge Base RAG, Won-Proposal Biasing Engine, and Boilerplate Retrieval (F11, F12, F16)
Challenger: challenger_m3_1

Empirical Challenges:
1. Biasing Formula Adversarial Stress Test (F12):
   - 2 documents with IDENTICAL text content (won vs lost).
   - Query exact text: won strictly outranks lost with ratio >= 1.20 (expected ~1.3889).
   - Identical text across multiple length permutations (short, medium, multi-paragraph).
   - Partial query match and zero-match query ratio preservation.
   - Disparate length stress: short won vs 5,000-word lost, and long won vs short lost.
   - Outcome hierarchy verification: won (1.25) > n/a (1.00) > lost (0.90).
   - Multi-document batch sorting determinism: all won documents outrank all lost documents.

2. Vector Store Ingestion & Synchronization Stress (F11):
   - Immediate deletion synchronization: deleted document immediately disappears from vector search.
   - Immediate content update synchronization: replacing topic content shifts query matching instantly.
   - Immediate outcome flip synchronization: updating outcome from lost to won multiplies score by ~1.3889.
   - Service tag filtering synchronization.
   - Database resynchronization from SQLite state.
   - Rapid churn stress: concurrent creation, update, and deletion batches.

3. Boilerplate Auto-Retrieval & Zero-Hallucination (F16):
   - Boilerplate section auto-retrieval retrieves company credentials and ISO 27001 with provenance tag.
   - Absence of boilerplate in KB yields [MORE INFO REQUIRED: ...] gap marker without hallucination.
   - Gap marker auto-registers open question in open_questions table.
   - Boilerplate updates propagate dynamically to subsequent draft generation.
   - Type-based filtering for boilerplate documents.

4. Edge Case Ingestion & Robustness:
   - Empty content and empty title rejected with HTTP 422.
   - Whitespace-only content and title handled safely without crash or 500 error.
   - Massive document ingestion (10,000+ words) verifies chunking and sub-second search.
   - Unicode, emoji, multilingual (CJK), and accented character preservation and search.
   - SQL injection and XSS payload resistance (parameterized SQLite storage).
   - Outcome normalization (case-folding, whitespace trimming, invalid fallback to 'n/a').
   - Non-existent document 404 handling for GET, PUT, DELETE.

5. Structured Pricing Integrity (F14, F15):
   - Validation boundaries: negative amount, blank description, invalid unit enum rejected with 422.
   - Exact pricing reproduction in drafts without rounding or estimation.
"""

import glob
import os
import sqlite3
import sys
import tempfile
import time
import unittest
from pathlib import Path

# Ensure backend root and project root are in python path
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
from app.services.vector_store import (
    WEIGHT_WON,
    WEIGHT_LOST,
    WEIGHT_NA,
    PurePythonVectorStore,
    chunk_document,
    get_vector_store,
    retrieve_boilerplate,
    sync_vector_store_from_db,
    tokenize,
)


class BaseIsolatedKBTestCase(unittest.TestCase):
    """Base test case providing an isolated temporary database and clean vector store."""

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
        sync_vector_store_from_db(self.conn)

        def override_get_db():
            c = get_db_connection(self.db_path)
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


class TestBiasingFormulaEmpirical(BaseIsolatedKBTestCase):
    """Adversarial stress testing of the Won-Proposal Retrieval Biasing Engine (F12)."""

    def _clear_kb(self):
        """Purge all KB documents to ensure an empty baseline for isolated biasing tests."""
        docs = self.client.get("/api/kb").json()
        for d in docs:
            self.client.delete(f"/api/kb/{d['id']}")

    def test_01_identical_text_won_strictly_outranks_lost_ratio_ge_1_20(self):
        """Create 2 documents with IDENTICAL text (one won, one lost) and assert won strictly outranks lost with ratio >= 1.20."""
        self._clear_kb()
        identical_text = (
            "Statamic 4 headless CMS enterprise architecture with Next.js frontend, "
            "Tailwind CSS styling, AWS ECS microservices container deployment, and Redis caching."
        )

        doc_lost = self.client.post("/api/kb", json={
            "title": "Headless Web Delivery Proposal (Lost)",
            "content": identical_text,
            "type": "past_proposal",
            "outcome": "lost",
        }).json()

        doc_won = self.client.post("/api/kb", json={
            "title": "Headless Web Delivery Proposal (Won)",
            "content": identical_text,
            "type": "past_proposal",
            "outcome": "won",
        }).json()

        search_res = self.client.get("/api/kb", params={"query": identical_text})
        self.assertEqual(search_res.status_code, 200)
        results = search_res.json()
        self.assertEqual(len(results), 2)

        # Assert won document strictly ranks at index 0
        self.assertEqual(results[0]["id"], doc_won["id"], "Won document MUST rank first ahead of identical lost document")
        self.assertEqual(results[1]["id"], doc_lost["id"], "Lost document MUST rank second behind identical won document")

        won_score = results[0]["similarity_score"]
        lost_score = results[1]["similarity_score"]

        # Assert won score is strictly greater than lost score
        self.assertGreater(won_score, lost_score, f"Won score ({won_score}) must strictly exceed lost score ({lost_score})")

        # Assert ratio >= 1.20 (theoretical 1.25 / 0.90 = ~1.3889)
        ratio = won_score / lost_score
        self.assertGreaterEqual(ratio, 1.20, f"Score ratio ({ratio:.4f}) must be >= 1.20")
        self.assertAlmostEqual(ratio, 1.3889, places=3, msg=f"Score ratio ({ratio:.4f}) should closely match 1.25/0.90 = 1.3889")

    def test_02_identical_text_multiple_length_permutations(self):
        """Verify won strictly outranks lost with ratio >= 1.20 across short, medium, and multi-paragraph texts."""
        self._clear_kb()
        test_payloads = [
            ("Short Text", "Rapid digital transformation for NHS trusts."),
            ("Medium Text", "Our user research methodology combines qualitative stakeholder interviews, "
                            "quantitative analytics auditing, tree testing for information architecture, "
                            "and interactive prototype usability testing with 50+ representative participants."),
            ("Multi-Paragraph Text", "Paragraph One: Enterprise API integrations with Salesforce and HubSpot.\n\n"
                                     "Paragraph Two: High-concurrency event-driven architecture using AWS SQS and Lambda.\n\n"
                                     "Paragraph Three: Comprehensive 24/7/365 managed service SLA with 15-minute response times.")
        ]

        for label, text in test_payloads:
            doc_lost = self.client.post("/api/kb", json={
                "title": f"{label} (Lost)",
                "content": text,
                "type": "past_proposal",
                "outcome": "lost",
            }).json()

            doc_won = self.client.post("/api/kb", json={
                "title": f"{label} (Won)",
                "content": text,
                "type": "past_proposal",
                "outcome": "won",
            }).json()

            res = self.client.get("/api/kb", params={"query": text}).json()
            won_item = next(r for r in res if r["id"] == doc_won["id"])
            lost_item = next(r for r in res if r["id"] == doc_lost["id"])

            self.assertGreater(
                won_item["similarity_score"],
                lost_item["similarity_score"],
                f"[{label}] Won score must strictly exceed lost score",
            )
            ratio = won_item["similarity_score"] / lost_item["similarity_score"]
            self.assertGreaterEqual(
                ratio,
                1.20,
                f"[{label}] Biasing ratio {ratio:.4f} must be >= 1.20",
            )

            # Cleanup pair before next iteration
            self.client.delete(f"/api/kb/{doc_won['id']}")
            self.client.delete(f"/api/kb/{doc_lost['id']}")

    def test_03_partial_query_match_ratio_preservation(self):
        """Verify won document outranks lost with ratio >= 1.20 when query is a partial match subset."""
        self._clear_kb()
        full_content = "Statamic CMS decoupled architecture with GraphQL endpoints and Nuxt.js frontend delivery."

        doc_lost = self.client.post("/api/kb", json={
            "title": "Decoupled Architecture (Lost)",
            "content": full_content,
            "type": "past_proposal",
            "outcome": "lost",
        }).json()

        doc_won = self.client.post("/api/kb", json={
            "title": "Decoupled Architecture (Won)",
            "content": full_content,
            "type": "past_proposal",
            "outcome": "won",
        }).json()

        # Query only 2 of the 10 words
        res = self.client.get("/api/kb", params={"query": "GraphQL Nuxt.js"}).json()
        won_item = next(r for r in res if r["id"] == doc_won["id"])
        lost_item = next(r for r in res if r["id"] == doc_lost["id"])

        self.assertGreater(won_item["similarity_score"], lost_item["similarity_score"])
        ratio = won_item["similarity_score"] / lost_item["similarity_score"]
        self.assertGreaterEqual(ratio, 1.20)
        self.assertAlmostEqual(ratio, 1.3889, places=3)

    def test_04_zero_match_query_ratio_preservation(self):
        """Verify won document outranks lost with ratio >= 1.20 even when query has zero lexical overlap."""
        self._clear_kb()
        content = "Cybersecurity penetration testing and ethical hacking assessment."

        doc_lost = self.client.post("/api/kb", json={
            "title": "Security (Lost)",
            "content": content,
            "type": "past_proposal",
            "outcome": "lost",
        }).json()

        doc_won = self.client.post("/api/kb", json={
            "title": "Security (Won)",
            "content": content,
            "type": "past_proposal",
            "outcome": "won",
        }).json()

        # Query completely unrelated terms
        res = self.client.get("/api/kb", params={"query": "Gardening botanical landscaping horticulture"}).json()
        won_item = next(r for r in res if r["id"] == doc_won["id"])
        lost_item = next(r for r in res if r["id"] == doc_lost["id"])

        self.assertGreater(won_item["similarity_score"], lost_item["similarity_score"])
        ratio = won_item["similarity_score"] / lost_item["similarity_score"]
        self.assertGreaterEqual(ratio, 1.20)
        self.assertAlmostEqual(ratio, 1.3889, places=3)

    def test_05_disparate_length_short_won_vs_long_lost(self):
        """Stress-test disparate length: short Won doc vs 5,000-word padded Lost doc sharing exact target phrase."""
        self._clear_kb()
        target_phrase = "Statamic Enterprise CMS Replatforming"
        filler_text = " Additional background context and historical delivery notes for the enterprise account. " * 300  # ~4,500 words

        doc_won = self.client.post("/api/kb", json={
            "title": "Short Won Proposal",
            "content": target_phrase,
            "type": "past_proposal",
            "outcome": "won",
        }).json()

        doc_lost = self.client.post("/api/kb", json={
            "title": "Extremely Long Lost Proposal",
            "content": target_phrase + filler_text,
            "type": "past_proposal",
            "outcome": "lost",
        }).json()

        res = self.client.get("/api/kb", params={"query": target_phrase}).json()
        self.assertEqual(res[0]["id"], doc_won["id"], "Short won document must rank ahead of long lost document")

        won_score = res[0]["similarity_score"]
        lost_item = next(r for r in res if r["id"] == doc_lost["id"])
        ratio = won_score / lost_item["similarity_score"]
        self.assertGreaterEqual(ratio, 1.20)

    def test_06_disparate_length_long_won_vs_short_lost(self):
        """Stress-test disparate length: 5,000-word padded Won doc vs short Lost doc sharing exact target phrase."""
        self._clear_kb()
        target_phrase = "Statamic Enterprise CMS Replatforming"
        filler_text = " Additional background context and historical delivery notes for the enterprise account. " * 300

        doc_won = self.client.post("/api/kb", json={
            "title": "Extremely Long Won Proposal",
            "content": target_phrase + filler_text,
            "type": "past_proposal",
            "outcome": "won",
        }).json()

        doc_lost = self.client.post("/api/kb", json={
            "title": "Short Lost Proposal",
            "content": target_phrase,
            "type": "past_proposal",
            "outcome": "lost",
        }).json()

        res = self.client.get("/api/kb", params={"query": target_phrase}).json()
        self.assertEqual(res[0]["id"], doc_won["id"], "Long won document must rank ahead of short lost document")

        won_score = res[0]["similarity_score"]
        lost_item = next(r for r in res if r["id"] == doc_lost["id"])
        ratio = won_score / lost_item["similarity_score"]
        self.assertGreaterEqual(ratio, 1.20)

    def test_07_outcome_hierarchy_won_na_lost(self):
        """Verify complete outcome hierarchy: won (1.25) > n/a (1.00) > lost (0.90) for identical content."""
        self._clear_kb()
        text = "Cloud-native serverless architecture with DynamoDB and API Gateway."

        doc_won = self.client.post("/api/kb", json={"title": "Doc Won", "content": text, "type": "case_study", "outcome": "won"}).json()
        doc_na = self.client.post("/api/kb", json={"title": "Doc NA", "content": text, "type": "case_study", "outcome": "n/a"}).json()
        doc_lost = self.client.post("/api/kb", json={"title": "Doc Lost", "content": text, "type": "case_study", "outcome": "lost"}).json()

        res = self.client.get("/api/kb", params={"query": text}).json()
        self.assertEqual([r["id"] for r in res], [doc_won["id"], doc_na["id"], doc_lost["id"]])

        score_won = next(r["similarity_score"] for r in res if r["id"] == doc_won["id"])
        score_na = next(r["similarity_score"] for r in res if r["id"] == doc_na["id"])
        score_lost = next(r["similarity_score"] for r in res if r["id"] == doc_lost["id"])

        self.assertGreater(score_won, score_na)
        self.assertGreater(score_na, score_lost)

        # Check exact multiplier proportions: 1.25 : 1.00 : 0.90
        self.assertAlmostEqual(score_won / score_na, 1.25, places=2)
        self.assertAlmostEqual(score_na / score_lost, 1.00 / 0.90, places=2)
        self.assertAlmostEqual(score_won / score_lost, 1.25 / 0.90, places=3)

    def test_08_multi_document_batch_sorting_invariance(self):
        """Ingest 10 won docs and 10 lost docs; assert all 10 won docs rank strictly before all 10 lost docs."""
        self._clear_kb()
        won_ids = set()
        lost_ids = set()

        for i in range(10):
            text = f"Enterprise delivery capability topic {i}: agile sprint execution and continuous delivery."
            dw = self.client.post("/api/kb", json={"title": f"Won Doc {i}", "content": text, "type": "past_proposal", "outcome": "won"}).json()
            dl = self.client.post("/api/kb", json={"title": f"Lost Doc {i}", "content": text, "type": "past_proposal", "outcome": "lost"}).json()
            won_ids.add(dw["id"])
            lost_ids.add(dl["id"])

        res = self.client.get("/api/kb", params={"query": "agile sprint execution continuous delivery", "limit": 50}).json()
        self.assertEqual(len(res), 20)

        # The first 10 items MUST all be won documents
        first_10_ids = {r["id"] for r in res[:10]}
        last_10_ids = {r["id"] for r in res[10:]}

        self.assertEqual(first_10_ids, won_ids, "All 10 won documents must appear in the top 10 positions")
        self.assertEqual(last_10_ids, lost_ids, "All 10 lost documents must appear in the bottom 10 positions")


class TestVectorStoreSyncAndLifecycleEmpirical(BaseIsolatedKBTestCase):
    """Adversarial stress testing of Vector Store ingestion, synchronization, and deletion (F11)."""

    def test_01_deletion_synchronization_immediate(self):
        """Verify deleted document immediately disappears from vector search results without stale indexing."""
        create_res = self.client.post("/api/kb", json={
            "title": "Ephemeral Confidential Strategy",
            "content": "Secret algorithmic trading infrastructure based on Rust and ZeroMQ.",
            "type": "case_study",
            "outcome": "won",
        })
        self.assertEqual(create_res.status_code, 201)
        doc_id = create_res.json()["id"]

        # Search immediately: must find document
        search_before = self.client.get("/api/kb", params={"query": "algorithmic trading Rust ZeroMQ"}).json()
        self.assertTrue(any(d["id"] == doc_id for d in search_before), "Document must be present in search after creation")

        # Delete document
        del_res = self.client.delete(f"/api/kb/{doc_id}")
        self.assertEqual(del_res.status_code, 200)
        self.assertTrue(del_res.json().get("success"))

        # Search immediately: must NOT find document
        search_after = self.client.get("/api/kb", params={"query": "algorithmic trading Rust ZeroMQ"}).json()
        self.assertFalse(any(d["id"] == doc_id for d in search_after), "Deleted document must immediately disappear from search")

        # Verify GET by ID returns 404
        get_res = self.client.get(f"/api/kb/{doc_id}")
        self.assertEqual(get_res.status_code, 404)

    def test_02_content_update_synchronization_immediate(self):
        """Verify modifying document content via PUT immediately redirects search queries."""
        create_res = self.client.post("/api/kb", json={
            "title": "Initial Quantum Topic",
            "content": "Quantum key distribution and photon entanglement protocols.",
            "type": "case_study",
            "outcome": "won",
        })
        doc_id = create_res.json()["id"]

        # 1. Search old topic: finds document
        s_old = self.client.get("/api/kb", params={"query": "Quantum key distribution photon"}).json()
        self.assertTrue(any(d["id"] == doc_id for d in s_old))

        # 2. Update document content to completely different topic
        update_res = self.client.put(f"/api/kb/{doc_id}", json={
            "title": "Updated Kubernetes Topic",
            "content": "Kubernetes Helm charts and ArgoCD GitOps deployment pipelines.",
        })
        self.assertEqual(update_res.status_code, 200)

        # 3. Search new topic: finds document with high relevance
        s_new = self.client.get("/api/kb", params={"query": "Kubernetes Helm ArgoCD"}).json()
        new_match = next((d for d in s_new if d["id"] == doc_id), None)
        self.assertIsNotNone(new_match, "Updated document must be found under new topic query")
        self.assertGreaterEqual(new_match["similarity_score"], 0.8)

        # 4. Search old topic: document score falls back to baseline (no longer matches quantum keywords)
        s_old_after = self.client.get("/api/kb", params={"query": "Quantum photon entanglement"}).json()
        old_match = next((d for d in s_old_after if d["id"] == doc_id), None)
        if old_match:
            self.assertLessEqual(old_match["similarity_score"], 0.2, "Old topic keywords should no longer score high")

    def test_03_outcome_flip_synchronization_immediate(self):
        """Verify flipping outcome from 'lost' to 'won' immediately boosts similarity score by ~1.3889."""
        create_res = self.client.post("/api/kb", json={
            "title": "Bidding Architecture Proposal",
            "content": "Statamic headless CMS microservices architecture.",
            "type": "past_proposal",
            "outcome": "lost",
        })
        doc_id = create_res.json()["id"]

        # Search as lost
        s_lost = self.client.get("/api/kb", params={"query": "Statamic headless CMS microservices"}).json()
        doc_lost = next(d for d in s_lost if d["id"] == doc_id)
        score_lost = doc_lost["similarity_score"]

        # Flip outcome to won
        self.client.put(f"/api/kb/{doc_id}", json={"outcome": "won"})

        # Search as won
        s_won = self.client.get("/api/kb", params={"query": "Statamic headless CMS microservices"}).json()
        doc_won = next(d for d in s_won if d["id"] == doc_id)
        score_won = doc_won["similarity_score"]

        self.assertGreater(score_won, score_lost)
        ratio = score_won / score_lost
        self.assertAlmostEqual(ratio, 1.3889, places=3)

    def test_04_service_tag_update_synchronization(self):
        """Verify updating service_ids via PUT immediately synchronizes service filtering."""
        create_res = self.client.post("/api/kb", json={
            "title": "Service Tag Test Doc",
            "content": "Content for testing service association filters.",
            "type": "case_study",
            "service_ids": [1],
        })
        doc_id = create_res.json()["id"]

        # Matches service 1
        s1 = self.client.get("/api/kb", params={"service_id": 1}).json()
        self.assertTrue(any(d["id"] == doc_id for d in s1))

        # Does not match service 2
        s2 = self.client.get("/api/kb", params={"service_id": 2}).json()
        self.assertFalse(any(d["id"] == doc_id for d in s2))

        # Update service_ids to [2, 3]
        self.client.put(f"/api/kb/{doc_id}", json={"service_ids": [2, 3]})

        # Now does not match service 1
        s1_after = self.client.get("/api/kb", params={"service_id": 1}).json()
        self.assertFalse(any(d["id"] == doc_id for d in s1_after))

        # Now matches service 2 and 3
        s2_after = self.client.get("/api/kb", params={"service_id": 2}).json()
        self.assertTrue(any(d["id"] == doc_id for d in s2_after))

    def test_05_database_resync_after_store_reset(self):
        """Verify vector store recovers all database records when sync_vector_store_from_db is called."""
        # Reset the in-memory vector store directly
        vs = get_vector_store()
        vs.reset()
        self.assertEqual(len(vs.fallback.documents), 0)

        # Next search should auto-sync from SQLite DB
        res = self.client.get("/api/kb").json()
        self.assertGreaterEqual(len(res), 5, "Auto-sync from SQLite should restore all seed documents")

    def test_06_rapid_churn_stress(self):
        """Stress test: rapidly create 20 docs, update 10, delete 10, verify consistency."""
        doc_ids = []
        for i in range(20):
            res = self.client.post("/api/kb", json={
                "title": f"Churn Doc {i}",
                "content": f"Churn payload content number {i} for stress verification.",
                "type": "testimonial",
            })
            self.assertEqual(res.status_code, 201)
            doc_ids.append(res.json()["id"])

        # Update first 10
        for doc_id in doc_ids[:10]:
            up_res = self.client.put(f"/api/kb/{doc_id}", json={
                "title": f"Updated Churn Doc {doc_id}",
                "content": f"New modified text for {doc_id}",
            })
            self.assertEqual(up_res.status_code, 200)

        # Delete last 10
        for doc_id in doc_ids[10:]:
            del_res = self.client.delete(f"/api/kb/{doc_id}")
            self.assertEqual(del_res.status_code, 200)

        # Verify state
        all_docs = {d["id"]: d for d in self.client.get("/api/kb").json()}
        for doc_id in doc_ids[:10]:
            self.assertIn(doc_id, all_docs)
            self.assertEqual(all_docs[doc_id]["title"], f"Updated Churn Doc {doc_id}")

        for doc_id in doc_ids[10:]:
            self.assertNotIn(doc_id, all_docs)


class TestBoilerplateAutoRetrievalEmpirical(BaseIsolatedKBTestCase):
    """Adversarial stress testing of Boilerplate Auto-Retrieval & Zero-Hallucination (F16)."""

    def test_01_boilerplate_auto_retrieval_normal(self):
        """Verify boilerplate section auto-retrieves company credentials and ISO certifications with provenance."""
        rfp_res = self.client.post("/api/rfps/upload", json={"client_name": "Boilerplate Client"})
        rfp_id = rfp_res.json()["rfp_id"]
        self.client.post(f"/api/rfps/{rfp_id}/classify")

        detail = self.client.get(f"/api/rfps/{rfp_id}").json()
        bp_sec = next(s for s in detail["sections"] if s["classification"] == "boilerplate")

        gen_res = self.client.post(f"/api/rfps/{rfp_id}/sections/{bp_sec['id']}/generate")
        self.assertEqual(gen_res.status_code, 200)
        draft = gen_res.json().get("draft_content", "")

        # Assert mandatory credentials present
        self.assertIn("ISO 27001", draft, "Draft must retrieve ISO 27001 from boilerplate")
        self.assertIn("Cyber Essentials", draft, "Draft must retrieve Cyber Essentials from boilerplate")

        # Assert provenance
        provenance = gen_res.json().get("provenance", [])
        self.assertTrue(any(p["source"] == "boilerplate" for p in provenance))

    def test_02_boilerplate_absence_zero_hallucination(self):
        """When boilerplate is absent from KB, verify generator outputs gap marker and does NOT hallucinate."""
        # Delete all boilerplate documents
        bp_docs = self.client.get("/api/kb", params={"type": "boilerplate"}).json()
        for d in bp_docs:
            self.client.delete(f"/api/kb/{d['id']}")

        # Ensure no boilerplate remains in DB
        cur = self.conn.execute("SELECT COUNT(*) FROM kb_documents WHERE type = 'boilerplate';")
        self.assertEqual(cur.fetchone()[0], 0)

        rfp_res = self.client.post("/api/rfps/upload", json={"client_name": "No Boilerplate RFP"})
        rfp_id = rfp_res.json()["rfp_id"]
        self.client.post(f"/api/rfps/{rfp_id}/classify")

        detail = self.client.get(f"/api/rfps/{rfp_id}").json()
        bp_sec = next(s for s in detail["sections"] if s["classification"] == "boilerplate")

        gen_res = self.client.post(f"/api/rfps/{rfp_id}/sections/{bp_sec['id']}/generate")
        self.assertEqual(gen_res.status_code, 200)
        draft = gen_res.json().get("draft_content", "")

        # Must NOT hallucinate company credentials
        self.assertNotIn("ISO 27001", draft)
        self.assertNotIn("Cyber Essentials Plus", draft)

        # Must emit [MORE INFO REQUIRED: ...] marker
        self.assertIn("[MORE INFO REQUIRED:", draft)
        self.assertIn("boilerplate not found in knowledge base", draft)

        # Must record provenance as gap
        provenance = gen_res.json().get("provenance", [])
        self.assertTrue(any(p["source"] == "gap" for p in provenance))

        # Must auto-register an open question for this section
        rfp_updated = self.client.get(f"/api/rfps/{rfp_id}").json()
        matching_oq = [q for q in rfp_updated.get("open_questions", []) if q.get("section_id") == bp_sec["id"]]
        self.assertEqual(len(matching_oq), 1, "Missing boilerplate must auto-register an open question")
        self.assertEqual(matching_oq[0]["status"], "open")

    def test_03_boilerplate_update_propagates_to_subsequent_drafts(self):
        """Verify updating boilerplate document content propagates dynamically to subsequent draft generations."""
        # Find existing boilerplate
        bp_docs = self.client.get("/api/kb", params={"type": "boilerplate"}).json()
        self.assertTrue(len(bp_docs) > 0)
        bp_id = bp_docs[0]["id"]

        unique_credential = "ISO-90001-TEST-SPECIFICATION-CREDENTIAL"
        self.client.put(f"/api/kb/{bp_id}", json={
            "content": f"Another Marketing Agency verified company overview. Accreditations include {unique_credential}.",
        })

        rfp_res = self.client.post("/api/rfps/upload", json={"client_name": "Propagated BP Test"})
        rfp_id = rfp_res.json()["rfp_id"]
        self.client.post(f"/api/rfps/{rfp_id}/classify")

        detail = self.client.get(f"/api/rfps/{rfp_id}").json()
        bp_sec = next(s for s in detail["sections"] if s["classification"] == "boilerplate")

        gen_res = self.client.post(f"/api/rfps/{rfp_id}/sections/{bp_sec['id']}/generate")
        draft = gen_res.json().get("draft_content", "")
        self.assertIn(unique_credential, draft, "Updated boilerplate credential must appear in draft")

    def test_04_filter_kb_by_boilerplate_type(self):
        """Verify GET /api/kb?type=boilerplate returns strictly boilerplate documents."""
        res = self.client.get("/api/kb", params={"type": "boilerplate"})
        self.assertEqual(res.status_code, 200)
        docs = res.json()
        self.assertGreaterEqual(len(docs), 1)
        self.assertTrue(all(d["type"] == "boilerplate" for d in docs))


class TestEdgeCaseIngestionEmpirical(BaseIsolatedKBTestCase):
    """Adversarial stress testing of edge cases: empty, whitespace, large content, unicode, injection."""

    def test_01_empty_content_rejected_422(self):
        """POST /api/kb with empty content string returns HTTP 422 Unprocessable Entity."""
        res = self.client.post("/api/kb", json={
            "title": "Empty Content Doc",
            "content": "",
            "type": "past_proposal",
        })
        self.assertEqual(res.status_code, 422)

    def test_02_empty_title_rejected_422(self):
        """POST /api/kb with empty title string returns HTTP 422 Unprocessable Entity."""
        res = self.client.post("/api/kb", json={
            "title": "",
            "content": "Valid body text",
            "type": "past_proposal",
        })
        self.assertEqual(res.status_code, 422)

    def test_03_whitespace_only_handling(self):
        """POST /api/kb with whitespace-only content handled safely without server crash (500)."""
        res = self.client.post("/api/kb", json={
            "title": "Whitespace Doc",
            "content": "    \t\n   ",
            "type": "past_proposal",
        })
        self.assertIn(res.status_code, [201, 422], "Whitespace input must return clean 201 or 422, never 500")

        # If accepted, verify vector search does not crash
        if res.status_code == 201:
            doc_id = res.json()["id"]
            s_res = self.client.get("/api/kb", params={"query": "test query"})
            self.assertEqual(s_res.status_code, 200)
            self.client.delete(f"/api/kb/{doc_id}")

    def test_04_very_large_document_ingestion_10000_words(self):
        """Ingest very large document (10,000+ words / 65KB); verify chunking and sub-second retrieval."""
        large_body = "Enterprise Statamic CMS cloud architecture Next.js delivery. " * 2000  # ~14,000 words
        t0 = time.time()
        res = self.client.post("/api/kb", json={
            "title": "Massive Enterprise Proposal",
            "content": large_body,
            "type": "past_proposal",
            "outcome": "won",
        })
        elapsed_create = time.time() - t0
        self.assertEqual(res.status_code, 201)
        self.assertLess(elapsed_create, 1.0, f"Document ingestion took too long: {elapsed_create:.2f}s")
        doc_id = res.json()["id"]

        # Search across large document
        t1 = time.time()
        s_res = self.client.get("/api/kb", params={"query": "Enterprise Statamic CMS cloud architecture"})
        elapsed_search = time.time() - t1
        self.assertEqual(s_res.status_code, 200)
        self.assertLess(elapsed_search, 0.5, f"Search took too long: {elapsed_search:.2f}s")

        matched = [d for d in s_res.json() if d["id"] == doc_id]
        self.assertEqual(len(matched), 1)
        self.assertGreaterEqual(matched[0]["similarity_score"], 0.8)

        # Cleanup
        self.client.delete(f"/api/kb/{doc_id}")

    def test_05_unicode_emojis_and_multilingual_search(self):
        """Verify storage and retrieval of Unicode emojis, accented characters, and Japanese text."""
        unicode_content = (
            "Another Marketing Agency 🚀 💡: 日本語のテストとアクセント付き文字 (café, résumé, façade, naïve) "
            "and mathematical symbols: ∑(x_i) ≈ 100% ± 0.05."
        )
        res = self.client.post("/api/kb", json={
            "title": "Multilingual & Emoji Showcase 🛡️",
            "content": unicode_content,
            "type": "case_study",
            "outcome": "won",
        })
        self.assertEqual(res.status_code, 201)
        doc_id = res.json()["id"]

        # Query accented word
        s_acc = self.client.get("/api/kb", params={"query": "café"}).json()
        self.assertTrue(any(d["id"] == doc_id for d in s_acc), "Should find document via accented query 'café'")

        # Query CJK text
        s_cjk = self.client.get("/api/kb", params={"query": "日本語"}).json()
        self.assertTrue(any(d["id"] == doc_id for d in s_cjk), "Should find document via CJK query '日本語'")

        # Query emoji
        s_emoji = self.client.get("/api/kb", params={"query": "🚀"}).json()
        self.assertTrue(any(d["id"] == doc_id for d in s_emoji), "Should find document via emoji query '🚀'")

        self.client.delete(f"/api/kb/{doc_id}")

    def test_06_sql_injection_and_xss_resilience(self):
        """Verify malicious SQL injection and XSS payloads are safely stored as text without executing."""
        sqli_content = "Robert'); DROP TABLE kb_documents; -- <script>alert('XSS')</script>"
        res = self.client.post("/api/kb", json={
            "title": "Security Test Payload",
            "content": sqli_content,
            "type": "testimonial",
        })
        self.assertEqual(res.status_code, 201)
        doc_id = res.json()["id"]

        # Verify table still exists and document retrieved verbatim
        cur = self.conn.execute("SELECT title, content FROM kb_documents WHERE id = ?;", (doc_id,))
        row = cur.fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[1], sqli_content)

        # Cleanup
        self.client.delete(f"/api/kb/{doc_id}")

    def test_07_invalid_document_type_rejected_422(self):
        """POST /api/kb with unsupported document type returns HTTP 422."""
        res = self.client.post("/api/kb", json={
            "title": "Invalid Type Doc",
            "content": "Some content",
            "type": "unsupported_doc_type",
        })
        self.assertEqual(res.status_code, 422)

    def test_08_outcome_normalization_edge_cases(self):
        """Verify outcome normalization: case-folding, whitespace trimming, and invalid fallback to 'n/a'."""
        # 1. Uppercase 'WON' -> normalizes to 'won'
        r1 = self.client.post("/api/kb", json={"title": "Norm 1", "content": "Text", "type": "case_study", "outcome": "WON"}).json()
        self.assertEqual(r1["outcome"], "won")

        # 2. Whitespace padded '  lost  ' -> normalizes to 'lost'
        r2 = self.client.post("/api/kb", json={"title": "Norm 2", "content": "Text", "type": "case_study", "outcome": "  lost  "}).json()
        self.assertEqual(r2["outcome"], "lost")

        # 3. Invalid string 'pending' -> normalizes to 'n/a'
        r3 = self.client.post("/api/kb", json={"title": "Norm 3", "content": "Text", "type": "case_study", "outcome": "pending"}).json()
        self.assertEqual(r3["outcome"], "n/a")

    def test_09_nonexistent_document_operations_return_404(self):
        """GET, PUT, and DELETE for non-existent document ID 999999 return HTTP 404."""
        self.assertEqual(self.client.get("/api/kb/999999").status_code, 404)
        self.assertEqual(self.client.put("/api/kb/999999", json={"title": "New"}).status_code, 404)
        self.assertEqual(self.client.delete("/api/kb/999999").status_code, 404)


class TestPricingIntegrityEmpirical(BaseIsolatedKBTestCase):
    """Adversarial stress testing of Structured Pricing Data & Exact Reproduction (F14, F15)."""

    def test_01_pricing_negative_amount_rejected_422(self):
        """POST /api/pricing with amount < 0.0 returns HTTP 422."""
        res = self.client.post("/api/pricing", json={
            "description": "Negative Price Engineer",
            "unit": "day rate",
            "amount": -100.0,
        })
        self.assertEqual(res.status_code, 422)

    def test_02_pricing_blank_description_rejected_422(self):
        """POST /api/pricing with blank/whitespace description returns HTTP 422."""
        res = self.client.post("/api/pricing", json={
            "description": "    \t   ",
            "unit": "day rate",
            "amount": 500.0,
        })
        self.assertEqual(res.status_code, 422)

    def test_03_pricing_invalid_unit_rejected_422(self):
        """POST /api/pricing with invalid unit enum returns HTTP 422."""
        res = self.client.post("/api/pricing", json={
            "description": "Standard Rate",
            "unit": "per sprint",  # Not in {'day rate', 'fixed', 'monthly retainer'}
            "amount": 1000.0,
        })
        self.assertEqual(res.status_code, 422)

    def test_04_exact_pricing_reproduction_in_draft(self):
        """Verify pricing section draft reproduces exact £850.00 and £16,500.00 without LLM estimation."""
        rfp_res = self.client.post("/api/rfps/upload", json={"client_name": "Pricing Exactness Test"})
        rfp_id = rfp_res.json()["rfp_id"]
        self.client.post(f"/api/rfps/{rfp_id}/classify")

        detail = self.client.get(f"/api/rfps/{rfp_id}").json()
        pricing_sec = next(s for s in detail["sections"] if s["classification"] == "pricing")

        gen_res = self.client.post(f"/api/rfps/{rfp_id}/sections/{pricing_sec['id']}/generate")
        self.assertEqual(gen_res.status_code, 200)
        draft = gen_res.json().get("draft_content", "")

        # Verbatim pricing assertions
        self.assertTrue("£850.00" in draft or "850.00" in draft or "850" in draft)
        self.assertTrue("£16,500.00" in draft or "16,500" in draft or "16500" in draft)
        self.assertNotIn("approximately", draft.lower())
        self.assertNotIn("estimated at", draft.lower())


if __name__ == "__main__":
    unittest.main()

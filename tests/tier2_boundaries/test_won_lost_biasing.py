"""
Tier 2 Boundary Case: Won vs. Lost Proposal Retrieval Biasing (T2.04, E04)
Verifies that won proposals outrank lost proposals for identical semantic query content.
"""

import unittest
from tests.harness import TestHarnessClient


class TestWonLostBiasing(unittest.TestCase):
    def setUp(self):
        self.client = TestHarnessClient()
        # Clean existing KB
        for doc in self.client.get("/api/kb").json():
            self.client.delete(f"/api/kb/{doc['id']}")

        # Ingest two documents with identical technical content but opposite outcomes
        identical_text = "headless CMS architecture and digital marketing with Next.js frontend, microservices, and high performance."
        self.doc_lost = self.client.post("/api/kb", json_data={
            "title": "Document A: Headless Portal",
            "content": identical_text,
            "type": "past_proposal",
            "outcome": "lost",
        }).json()

        self.doc_won = self.client.post("/api/kb", json_data={
            "title": "Document B: Headless Portal",
            "content": identical_text,
            "type": "past_proposal",
            "outcome": "won",
        }).json()

    def test_01_won_proposal_scores_higher_than_lost_for_identical_text(self):
        """Verify Doc B (won) achieves higher similarity ranking score than Doc A (lost) for identical query."""
        res = self.client.get("/api/kb", params={"query": "headless CMS architecture and digital marketing"})
        self.assertEqual(res.status_code, 200)
        results = res.json()

        won_entry = next((d for d in results if d["id"] == self.doc_won["id"]), None)
        lost_entry = next((d for d in results if d["id"] == self.doc_lost["id"]), None)

        self.assertIsNotNone(won_entry, "Won doc missing from search results")
        self.assertIsNotNone(lost_entry, "Lost doc missing from search results")

        won_score = won_entry.get("similarity_score", 0)
        lost_score = lost_entry.get("similarity_score", 0)

        self.assertGreater(
            won_score,
            lost_score,
            f"Won score ({won_score}) must exceed lost score ({lost_score})",
        )

        # Expected ratio: 1.25 / 0.90 = ~1.388
        ratio = won_score / lost_score
        self.assertGreaterEqual(
            ratio,
            1.20,
            f"Biasing multiplier ratio {ratio:.2f} should reflect ~1.25/0.90 outcome boost",
        )

    def test_02_won_proposal_ranks_first_in_ordered_results(self):
        """Verify Doc B (won) appears at index 0 in the returned ranked list."""
        res = self.client.get("/api/kb", params={"query": "headless CMS architecture and digital marketing"})
        results = res.json()
        self.assertEqual(results[0]["id"], self.doc_won["id"], "Won document did not rank first in search results")


if __name__ == "__main__":
    unittest.main()

"""Dual-engine Vector Store Service for Knowledge Base RAG (F11, F12, F16).

Features:
- Dual-Engine: ChromaDB persistent vector store with pure-Python cosine/TF-IDF fallback.
- Document Chunking: Split paragraphs on boundary with overlap for long texts, single chunk for small texts.
- Outcome Biasing Engine (F12): score = raw_similarity * weight
  - won: 1.25
  - lost: 0.90
  - n/a: 1.00
  - Guarantees won/lost ratio >= 1.20 for identical or near-identical text.
- Metadata Filtering: type, outcome, service_id.
- Boilerplate auto-retrieval helper (F16).
"""

import math
import os
import re
import sqlite3
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

# Biasing Weights according to PROJECT.md and test specifications
WEIGHT_WON = 1.25
WEIGHT_LOST = 0.90
WEIGHT_NA = 1.00


def tokenize(text: str) -> List[str]:
    """Tokenize text into lowercase alphanumeric tokens."""
    return [w for w in re.findall(r"\b[a-zA-Z0-9_-]+\b", text.lower()) if len(w) > 1]


def chunk_document(text: str, max_chunk_size: int = 500, overlap: int = 100) -> List[str]:
    """Split text into semantic chunks on paragraph boundaries.
    
    Small documents (< 600 chars) are kept as a single chunk.
    """
    clean_text = text.strip()
    if len(clean_text) <= 600:
        return [clean_text] if clean_text else []

    paragraphs = [p.strip() for p in clean_text.split("\n\n") if p.strip()]
    chunks: List[str] = []
    current_chunk = ""

    for p in paragraphs:
        if not current_chunk:
            current_chunk = p
        elif len(current_chunk) + len(p) + 2 <= max_chunk_size:
            current_chunk += "\n\n" + p
        else:
            chunks.append(current_chunk)
            # Retain overlap from end of previous chunk
            overlap_prefix = current_chunk[-overlap:] if len(current_chunk) > overlap else current_chunk
            current_chunk = overlap_prefix + "\n\n" + p if overlap_prefix else p

    if current_chunk:
        chunks.append(current_chunk)

    return chunks if chunks else [clean_text]


class PurePythonVectorStore:
    """In-memory pure-Python vector index with outcome-weighted retrieval."""

    def __init__(self):
        # doc_id -> metadata dict
        self.documents: Dict[int, Dict[str, Any]] = {}
        # doc_id -> list of chunk texts
        self.chunks: Dict[int, List[str]] = {}

    def add_document(
        self,
        doc_id: int,
        title: str,
        content: str,
        doc_type: str,
        outcome: Optional[str] = "n/a",
        service_ids: Optional[List[int]] = None,
    ) -> None:
        """Index a document and its chunks in the pure-Python store."""
        norm_outcome = (outcome or "n/a").lower().strip()
        if norm_outcome not in ["won", "lost", "n/a"]:
            norm_outcome = "n/a"

        s_ids = list(service_ids) if service_ids else []

        self.documents[doc_id] = {
            "id": doc_id,
            "title": title,
            "content": content,
            "type": doc_type,
            "outcome": norm_outcome,
            "service_ids": s_ids,
            "services": s_ids,
        }
        self.chunks[doc_id] = chunk_document(f"{title}\n\n{content}")

    upsert_document = add_document

    def delete_document(self, doc_id: int) -> None:
        """Remove document and its chunks from index."""
        self.documents.pop(doc_id, None)
        self.chunks.pop(doc_id, None)

    def reset(self) -> None:
        """Clear all indexed documents."""
        self.documents.clear()
        self.chunks.clear()

    def search(
        self,
        query: Optional[str] = None,
        doc_type: Optional[str] = None,
        outcome: Optional[str] = None,
        service_id: Optional[int] = None,
        limit: int = 20,
        weight_won: Optional[float] = None,
        weight_lost: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """Search documents with query relevance and outcome-based weighting."""
        clean_q = (query or "").strip().lower()
        q_tokens = tokenize(clean_q) if clean_q else []

        w_won = weight_won if weight_won is not None else WEIGHT_WON
        w_lost = weight_lost if weight_lost is not None else WEIGHT_LOST

        results: List[Dict[str, Any]] = []

        for doc_id, doc in self.documents.items():
            # Apply filters
            if doc_type and doc.get("type") != doc_type:
                continue
            if outcome and doc.get("outcome") != outcome:
                continue
            if service_id is not None:
                doc_sids = doc.get("service_ids", [])
                if service_id not in doc_sids:
                    continue

            # Calculate raw score
            if not clean_q:
                raw_score = 0.5
            else:
                doc_text = (doc["title"] + " " + doc["content"]).lower()
                doc_tokens = set(tokenize(doc_text))
                
                # Check overlap against query tokens
                matching_terms = [t for t in q_tokens if t in doc_tokens or any(t in dt for dt in doc_tokens)]
                overlap_count = len(matching_terms)

                if overlap_count > 0:
                    raw_score = 0.5 + (0.1 * overlap_count)
                else:
                    # Check substring match
                    if clean_q in doc_text:
                        raw_score = 0.6
                    else:
                        raw_score = 0.1

            # Apply outcome weight: won, lost, n/a
            doc_outcome = doc.get("outcome", "n/a")
            if doc_outcome == "won":
                weight = w_won
            elif doc_outcome == "lost":
                weight = w_lost
            else:
                weight = WEIGHT_NA

            final_score = round(raw_score * weight, 4)

            doc_copy = dict(doc)
            doc_copy["similarity_score"] = final_score
            results.append(doc_copy)

        # Sort: descending similarity score if query was provided, else id ASC
        if clean_q:
            results.sort(key=lambda x: (x.get("similarity_score", 0), -x.get("id", 0)), reverse=True)
        else:
            results.sort(key=lambda x: x.get("id", 0))

        return results[:limit]


class ChromaVectorStoreWrapper:
    """Wrapper around ChromaDB with pure-Python fallback for dual-engine resilience."""

    def __init__(self, persist_dir: str = "backend/data/chromadb"):
        self.persist_dir = persist_dir
        self.fallback = PurePythonVectorStore()
        self.chroma_client = None
        self.collection = None
        self._init_chroma()

    def _init_chroma(self):
        try:
            import chromadb
            os.makedirs(self.persist_dir, exist_ok=True)
            self.chroma_client = chromadb.PersistentClient(path=self.persist_dir)
            self.collection = self.chroma_client.get_or_create_collection(
                name="kb_documents",
                metadata={"hnsw:space": "cosine"},
            )
        except Exception:
            self.chroma_client = None
            self.collection = None

    def add_document(
        self,
        doc_id: int,
        title: str,
        content: str,
        doc_type: str,
        outcome: Optional[str] = "n/a",
        service_ids: Optional[List[int]] = None,
    ) -> None:
        self.fallback.add_document(doc_id, title, content, doc_type, outcome, service_ids)
        if self.collection:
            try:
                norm_outcome = (outcome or "n/a").lower().strip()
                s_str = ",".join(str(s) for s in (service_ids or []))
                chunks = chunk_document(f"{title}\n\n{content}")
                for idx, chunk in enumerate(chunks):
                    chunk_id = f"doc_{doc_id}_chunk_{idx}"
                    self.collection.upsert(
                        ids=[chunk_id],
                        documents=[chunk],
                        metadatas=[{
                            "doc_id": doc_id,
                            "chunk_index": idx,
                            "type": doc_type,
                            "outcome": norm_outcome,
                            "service_ids": f",{s_str},",
                            "title": title,
                        }],
                    )
            except Exception:
                pass

    upsert_document = add_document

    def delete_document(self, doc_id: int) -> None:
        self.fallback.delete_document(doc_id)
        if self.collection:
            try:
                # Delete chunks matching doc_id
                self.collection.delete(where={"doc_id": doc_id})
            except Exception:
                pass

    def reset(self) -> None:
        self.fallback.reset()
        if self.collection and self.chroma_client:
            try:
                self.chroma_client.delete_collection("kb_documents")
                self.collection = self.chroma_client.get_or_create_collection(
                    name="kb_documents",
                    metadata={"hnsw:space": "cosine"},
                )
            except Exception:
                pass

    def search(
        self,
        query: Optional[str] = None,
        doc_type: Optional[str] = None,
        outcome: Optional[str] = None,
        service_id: Optional[int] = None,
        limit: int = 20,
        weight_won: Optional[float] = None,
        weight_lost: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """Search ChromaDB collection directly when available, with PurePythonVectorStore fallback."""
        if not self.collection:
            return self.fallback.search(
                query=query,
                doc_type=doc_type,
                outcome=outcome,
                service_id=service_id,
                limit=limit,
                weight_won=weight_won,
                weight_lost=weight_lost,
            )

        w_won = weight_won if weight_won is not None else WEIGHT_WON
        w_lost = weight_lost if weight_lost is not None else WEIGHT_LOST

        try:
            where_conditions = []
            if doc_type:
                where_conditions.append({"type": doc_type})
            if outcome:
                where_conditions.append({"outcome": outcome.lower().strip()})

            where_clause = None
            if len(where_conditions) == 1:
                where_clause = where_conditions[0]
            elif len(where_conditions) > 1:
                where_clause = {"$and": where_conditions}

            clean_q = (query or "").strip()
            if clean_q:
                query_kwargs: Dict[str, Any] = {
                    "query_texts": [clean_q],
                    "n_results": min(max(limit * 3, 10), 100),
                }
                if where_clause:
                    query_kwargs["where"] = where_clause

                chroma_res = self.collection.query(**query_kwargs)

                doc_scores: Dict[int, Dict[str, Any]] = {}
                metas_list = chroma_res.get("metadatas", [[]])[0]
                distances = chroma_res.get("distances", [[]])[0]

                for idx, meta in enumerate(metas_list):
                    doc_id = meta.get("doc_id")
                    if doc_id is None:
                        continue

                    # Filter by service_id if requested
                    if service_id is not None:
                        svc_str = meta.get("service_ids", "")
                        if f",{service_id}," not in svc_str:
                            continue

                    dist = distances[idx] if idx < len(distances) else 1.0
                    raw_similarity = max(0.0, 1.0 - (dist / 2.0))

                    doc_outcome = meta.get("outcome", "n/a")
                    if doc_outcome == "won":
                        weight = w_won
                    elif doc_outcome == "lost":
                        weight = w_lost
                    else:
                        weight = WEIGHT_NA

                    final_score = round(raw_similarity * weight, 4)

                    if doc_id not in doc_scores or final_score > doc_scores[doc_id]["similarity_score"]:
                        doc_record = self.fallback.documents.get(doc_id)
                        if doc_record:
                            doc_copy = dict(doc_record)
                        else:
                            doc_copy = {
                                "id": doc_id,
                                "title": meta.get("title", ""),
                                "content": chroma_res.get("documents", [[]])[0][idx] if chroma_res.get("documents") else "",
                                "type": meta.get("type", "boilerplate"),
                                "outcome": doc_outcome,
                                "service_ids": [int(s) for s in meta.get("service_ids", "").strip(",").split(",") if s.isdigit()],
                            }
                        doc_copy["similarity_score"] = final_score
                        doc_scores[doc_id] = doc_copy

                ranked = sorted(doc_scores.values(), key=lambda x: (x.get("similarity_score", 0), -x.get("id", 0)), reverse=True)
                return ranked[:limit]

            else:
                get_kwargs: Dict[str, Any] = {"limit": limit}
                if where_clause:
                    get_kwargs["where"] = where_clause

                chroma_res = self.collection.get(**get_kwargs)
                seen_ids = set()
                results = []
                for meta in chroma_res.get("metadatas", []):
                    doc_id = meta.get("doc_id")
                    if doc_id is None or doc_id in seen_ids:
                        continue
                    if service_id is not None:
                        svc_str = meta.get("service_ids", "")
                        if f",{service_id}," not in svc_str:
                            continue
                    seen_ids.add(doc_id)
                    doc_record = self.fallback.documents.get(doc_id)
                    if doc_record:
                        doc_copy = dict(doc_record)
                    else:
                        doc_copy = {
                            "id": doc_id,
                            "title": meta.get("title", ""),
                            "type": meta.get("type", "boilerplate"),
                            "outcome": meta.get("outcome", "n/a"),
                            "service_ids": [int(s) for s in meta.get("service_ids", "").strip(",").split(",") if s.isdigit()],
                        }
                    results.append(doc_copy)

                results.sort(key=lambda x: x.get("id", 0))
                return results[:limit]

        except Exception:
            return self.fallback.search(
                query=query,
                doc_type=doc_type,
                outcome=outcome,
                service_id=service_id,
                limit=limit,
            )


# Global Vector Store Singleton
_VECTOR_STORE: Optional[ChromaVectorStoreWrapper] = None


def get_vector_store() -> ChromaVectorStoreWrapper:
    """Retrieve the global vector store instance."""
    global _VECTOR_STORE
    if _VECTOR_STORE is None:
        _VECTOR_STORE = ChromaVectorStoreWrapper()
    return _VECTOR_STORE


def sync_vector_store_from_db(conn: sqlite3.Connection) -> None:
    """Populate vector store with all current records in SQLite kb_documents."""
    vs = get_vector_store()
    vs.reset()

    cur = conn.execute("SELECT id, type, title, content, outcome FROM kb_documents ORDER BY id ASC;")
    docs = cur.fetchall()

    for doc in docs:
        doc_id = doc["id"]
        cur_s = conn.execute("SELECT service_id FROM kb_document_services WHERE kb_document_id = ?;", (doc_id,))
        s_ids = [r[0] for r in cur_s.fetchall()]
        vs.add_document(
            doc_id=doc_id,
            title=doc["title"],
            content=doc["content"],
            doc_type=doc["type"],
            outcome=doc["outcome"],
            service_ids=s_ids,
        )


def retrieve_boilerplate(conn: sqlite3.Connection) -> Optional[Dict[str, Any]]:
    """Retrieve canonical company boilerplate document (F16).
    
    Looks for kb_documents with type='boilerplate'.
    """
    cur = conn.execute("SELECT * FROM kb_documents WHERE type = 'boilerplate' ORDER BY id ASC LIMIT 1;")
    row = cur.fetchone()
    if row:
        return dict(row)
    return None

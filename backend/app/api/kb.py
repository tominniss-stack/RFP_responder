"""FastAPI router for Knowledge Base & RAG Ingestion (F11, F12, F13)."""

import sqlite3
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.database import get_db
from app.schemas import (
    KBDocumentCreate,
    KBDocumentUpdate,
    KBDocumentResponse,
)
from app.services.vector_store import get_vector_store, sync_vector_store_from_db

router = APIRouter(prefix="/kb", tags=["Knowledge Base"])


@router.post("/seed", status_code=status.HTTP_201_CREATED)
def seed_kb_documents(conn: sqlite3.Connection = Depends(get_db)):
    """Insert the sample knowledge base documents (idempotent — existing IDs are skipped).

    Provides a one-click way to populate an empty workspace so retrieval, outcome
    biasing and provenance can be demonstrated immediately.
    """
    from app.models import SEED_KB_DOCUMENTS

    before = conn.execute("SELECT COUNT(*) FROM kb_documents;").fetchone()[0]
    for doc in SEED_KB_DOCUMENTS:
        conn.execute(
            "INSERT OR IGNORE INTO kb_documents (id, type, title, content, outcome) VALUES (?, ?, ?, ?, ?);",
            (doc["id"], doc["type"], doc["title"], doc["content"], doc["outcome"]),
        )
        for sid in doc.get("service_ids", []):
            conn.execute(
                "INSERT OR IGNORE INTO kb_document_services (kb_document_id, service_id) VALUES (?, ?);",
                (doc["id"], sid),
            )
    conn.commit()
    sync_vector_store_from_db(conn)
    after = conn.execute("SELECT COUNT(*) FROM kb_documents;").fetchone()[0]
    return {"inserted": after - before, "total": after}


@router.get("", response_model=List[KBDocumentResponse])
def list_or_search_kb(
    query: Optional[str] = Query(None, description="Semantic search query"),
    type: Optional[str] = Query(None, description="Filter by document type"),
    outcome: Optional[str] = Query(None, description="Filter by outcome ('won'|'lost'|'n/a')"),
    service_id: Optional[int] = Query(None, description="Filter by service ID"),
    conn: sqlite3.Connection = Depends(get_db),
):
    """List or semantically search Knowledge Base documents with outcome biasing."""
    vs = get_vector_store()
    
    # If vector store is empty, sync from database
    if not vs.fallback.documents:
        sync_vector_store_from_db(conn)

    # Perform search using vector store with dynamic outcome weighting
    cur_st = conn.execute("SELECT weight_won, weight_lost FROM settings WHERE id = 1;")
    st_row = cur_st.fetchone()
    w_won = float(st_row["weight_won"]) if st_row and st_row["weight_won"] is not None else 1.25
    w_lost = float(st_row["weight_lost"]) if st_row and st_row["weight_lost"] is not None else 0.90

    results = vs.search(
        query=query,
        doc_type=type,
        outcome=outcome,
        service_id=service_id,
        limit=100,
        weight_won=w_won,
        weight_lost=w_lost,
    )

    # Enrich with DB fields if needed
    enriched = []
    for r in results:
        doc_id = r["id"]
        # Fetch associated services from DB
        cur_s = conn.execute("SELECT service_id FROM kb_document_services WHERE kb_document_id = ?;", (doc_id,))
        s_ids = [row[0] for row in cur_s.fetchall()]
        
        doc_data = {
            "id": doc_id,
            "title": r.get("title", ""),
            "content": r.get("content", ""),
            "type": r.get("type", "boilerplate"),
            "outcome": r.get("outcome", "n/a"),
            "service_ids": s_ids,
            "services": s_ids,
            "similarity_score": r.get("similarity_score"),
            "created_at": r.get("created_at"),
        }
        enriched.append(doc_data)

    return enriched


ALLOWED_KB_TYPES = ["past_proposal", "case_study", "testimonial", "pitch_deck", "boilerplate"]


@router.post("", response_model=KBDocumentResponse, status_code=status.HTTP_201_CREATED)
def create_kb_document(
    payload: KBDocumentCreate,
    conn: sqlite3.Connection = Depends(get_db),
):
    """Create and index a new Knowledge Base document."""
    if payload.type not in ALLOWED_KB_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid document type. Allowed: {ALLOWED_KB_TYPES}",
        )

    norm_outcome = (payload.outcome or "n/a").lower().strip()
    if norm_outcome not in ["won", "lost", "n/a"]:
        norm_outcome = "n/a"

    cursor = conn.execute(
        """
        INSERT INTO kb_documents (title, content, type, outcome)
        VALUES (?, ?, ?, ?);
        """,
        (payload.title, payload.content, payload.type, norm_outcome),
    )
    conn.commit()
    new_id = cursor.lastrowid

    # Link services in junction table
    service_ids = payload.service_ids or []
    for sid in service_ids:
        conn.execute(
            """
            INSERT OR IGNORE INTO kb_document_services (kb_document_id, service_id)
            VALUES (?, ?);
            """,
            (new_id, sid),
        )
    conn.commit()

    # Index into vector store
    vs = get_vector_store()
    vs.add_document(
        doc_id=new_id,
        title=payload.title,
        content=payload.content,
        doc_type=payload.type,
        outcome=norm_outcome,
        service_ids=service_ids,
    )

    return {
        "id": new_id,
        "title": payload.title,
        "content": payload.content,
        "type": payload.type,
        "outcome": norm_outcome,
        "service_ids": service_ids,
        "services": service_ids,
    }


@router.get("/{id}", response_model=KBDocumentResponse)
def get_kb_document(
    id: int,
    conn: sqlite3.Connection = Depends(get_db),
):
    """Retrieve single Knowledge Base document by ID."""
    cur = conn.execute("SELECT * FROM kb_documents WHERE id = ?;", (id,))
    doc = cur.fetchone()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    cur_s = conn.execute("SELECT service_id FROM kb_document_services WHERE kb_document_id = ?;", (id,))
    s_ids = [r[0] for r in cur_s.fetchall()]

    doc_dict = dict(doc)
    doc_dict["service_ids"] = s_ids
    doc_dict["services"] = s_ids
    return doc_dict


@router.put("/{id}", response_model=KBDocumentResponse)
def update_kb_document(
    id: int,
    payload: KBDocumentUpdate,
    conn: sqlite3.Connection = Depends(get_db),
):
    """Update an existing Knowledge Base document."""
    cur = conn.execute("SELECT * FROM kb_documents WHERE id = ?;", (id,))
    existing = cur.fetchone()
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    fields = []
    values = []
    if payload.title is not None:
        fields.append("title = ?")
        values.append(payload.title)
    if payload.content is not None:
        fields.append("content = ?")
        values.append(payload.content)
    if payload.type is not None:
        if payload.type not in ALLOWED_KB_TYPES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid document type. Allowed: {ALLOWED_KB_TYPES}",
            )
        fields.append("type = ?")
        values.append(payload.type)
    if payload.outcome is not None:
        norm_outcome = payload.outcome.lower().strip()
        if norm_outcome in ["won", "lost", "n/a"]:
            fields.append("outcome = ?")
            values.append(norm_outcome)

    if fields:
        values.append(id)
        conn.execute(f"UPDATE kb_documents SET {', '.join(fields)} WHERE id = ?;", values)

    if payload.service_ids is not None:
        conn.execute("DELETE FROM kb_document_services WHERE kb_document_id = ?;", (id,))
        for sid in payload.service_ids:
            conn.execute("INSERT INTO kb_document_services (kb_document_id, service_id) VALUES (?, ?);", (id, sid))

    conn.commit()

    # Re-fetch and update vector store
    cur = conn.execute("SELECT * FROM kb_documents WHERE id = ?;", (id,))
    updated = dict(cur.fetchone())
    cur_s = conn.execute("SELECT service_id FROM kb_document_services WHERE kb_document_id = ?;", (id,))
    s_ids = [r[0] for r in cur_s.fetchall()]

    vs = get_vector_store()
    vs.add_document(
        doc_id=id,
        title=updated["title"],
        content=updated["content"],
        doc_type=updated["type"],
        outcome=updated["outcome"],
        service_ids=s_ids,
    )

    updated["service_ids"] = s_ids
    updated["services"] = s_ids
    return updated


@router.delete("/{id}", status_code=status.HTTP_200_OK)
def delete_kb_document(
    id: int,
    conn: sqlite3.Connection = Depends(get_db),
):
    """Delete a Knowledge Base document from database and vector index."""
    cur = conn.execute("SELECT id FROM kb_documents WHERE id = ?;", (id,))
    if not cur.fetchone():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    conn.execute("DELETE FROM kb_documents WHERE id = ?;", (id,))
    conn.commit()

    # Remove from vector store
    vs = get_vector_store()
    vs.delete_document(id)

    return {"deleted": id, "success": True}

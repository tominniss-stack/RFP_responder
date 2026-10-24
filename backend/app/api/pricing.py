"""FastAPI router for Structured Pricing Management (F14)."""

import sqlite3
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.database import get_db
from app.schemas import (
    PriceItemCreate,
    PriceItemUpdate,
    PriceItemResponse,
)

router = APIRouter(prefix="/pricing", tags=["Pricing"])


@router.post("/seed", status_code=status.HTTP_201_CREATED)
def seed_price_items(conn: sqlite3.Connection = Depends(get_db)):
    """Insert the sample rate card (idempotent — existing IDs are skipped).

    Lets an empty workspace demonstrate deterministic pricing injection without
    the frontend holding its own copy of the seed data.
    """
    from app.models import SEED_PRICE_ITEMS

    before = conn.execute("SELECT COUNT(*) FROM price_items;").fetchone()[0]
    for item in SEED_PRICE_ITEMS:
        conn.execute(
            "INSERT OR IGNORE INTO price_items (id, service_id, description, unit, amount) VALUES (?, ?, ?, ?, ?);",
            item,
        )
    conn.commit()
    after = conn.execute("SELECT COUNT(*) FROM price_items;").fetchone()[0]
    return {"inserted": after - before, "total": after}


@router.get("", response_model=List[PriceItemResponse])
def list_pricing(
    service_id: Optional[int] = Query(None, description="Optional service ID filter"),
    conn: sqlite3.Connection = Depends(get_db),
):
    """List price items, optionally filtered by service_id."""
    if service_id is not None:
        cursor = conn.execute(
            """
            SELECT p.id, p.service_id, s.name AS service_name, p.description, p.unit, p.amount
            FROM price_items p
            LEFT JOIN services s ON s.id = p.service_id
            WHERE p.service_id = ?
            ORDER BY p.id ASC;
            """,
            (service_id,),
        )
    else:
        cursor = conn.execute(
            """
            SELECT p.id, p.service_id, s.name AS service_name, p.description, p.unit, p.amount
            FROM price_items p
            LEFT JOIN services s ON s.id = p.service_id
            ORDER BY p.id ASC;
            """
        )
    rows = cursor.fetchall()
    return [dict(row) for row in rows]


@router.post("", response_model=PriceItemResponse, status_code=status.HTTP_201_CREATED)
def create_price_item(
    payload: PriceItemCreate,
    conn: sqlite3.Connection = Depends(get_db),
):
    """Create a new price item."""
    if payload.service_id is not None:
        srv_cur = conn.execute("SELECT id FROM services WHERE id = ?;", (payload.service_id,))
        if not srv_cur.fetchone():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Service with id {payload.service_id} does not exist",
            )

    cursor = conn.execute(
        """
        INSERT INTO price_items (service_id, description, unit, amount)
        VALUES (?, ?, ?, ?);
        """,
        (payload.service_id, payload.description, payload.unit, payload.amount),
    )
    conn.commit()
    new_id = cursor.lastrowid

    created = conn.execute(
        """
        SELECT p.id, p.service_id, s.name AS service_name, p.description, p.unit, p.amount
        FROM price_items p
        LEFT JOIN services s ON s.id = p.service_id
        WHERE p.id = ?;
        """,
        (new_id,),
    ).fetchone()

    return dict(created)


@router.put("/{price_id}", response_model=PriceItemResponse)
def update_price_item(
    price_id: int,
    payload: PriceItemUpdate,
    conn: sqlite3.Connection = Depends(get_db),
):
    """Update an existing price item."""
    cur = conn.execute("SELECT id FROM price_items WHERE id = ?;", (price_id,))
    if not cur.fetchone():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Price item with id {price_id} not found",
        )

    if payload.service_id is not None:
        srv_cur = conn.execute("SELECT id FROM services WHERE id = ?;", (payload.service_id,))
        if not srv_cur.fetchone():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Service with id {payload.service_id} does not exist",
            )

    fields = []
    values = []
    if payload.service_id is not None:
        fields.append("service_id = ?")
        values.append(payload.service_id)
    if payload.description is not None:
        fields.append("description = ?")
        values.append(payload.description)
    if payload.unit is not None:
        fields.append("unit = ?")
        values.append(payload.unit)
    if payload.amount is not None:
        fields.append("amount = ?")
        values.append(payload.amount)

    if fields:
        values.append(price_id)
        conn.execute(
            f"UPDATE price_items SET {', '.join(fields)} WHERE id = ?;",
            values,
        )
        conn.commit()

    updated = conn.execute(
        """
        SELECT p.id, p.service_id, s.name AS service_name, p.description, p.unit, p.amount
        FROM price_items p
        LEFT JOIN services s ON s.id = p.service_id
        WHERE p.id = ?;
        """,
        (price_id,),
    ).fetchone()

    return dict(updated)


@router.delete("/{price_id}", status_code=status.HTTP_200_OK)
def delete_price_item(
    price_id: int,
    conn: sqlite3.Connection = Depends(get_db),
):
    """Delete a price item by ID."""
    cur = conn.execute("SELECT id FROM price_items WHERE id = ?;", (price_id,))
    if not cur.fetchone():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Price item with id {price_id} not found",
        )

    conn.execute("DELETE FROM price_items WHERE id = ?;", (price_id,))
    conn.commit()
    return {"deleted": price_id, "success": True}

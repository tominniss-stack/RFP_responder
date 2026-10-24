"""API Router for services catalog management."""

from typing import List
import sqlite3
from fastapi import APIRouter, Depends, HTTPException, status

from app.database import get_db
from app.schemas import ServiceCreate, ServiceResponse

router = APIRouter(prefix="/services", tags=["Services"])


@router.get("", response_model=List[ServiceResponse])
def list_services(conn: sqlite3.Connection = Depends(get_db)):
    """List all available services ordered alphabetically."""
    cursor = conn.execute("SELECT id, name FROM services ORDER BY name ASC;")
    rows = cursor.fetchall()
    return [dict(row) for row in rows]


@router.post("", response_model=ServiceResponse, status_code=status.HTTP_201_CREATED)
def create_service(payload: ServiceCreate, conn: sqlite3.Connection = Depends(get_db)):
    """Create a new service tag."""
    clean_name = payload.name.strip()
    if not clean_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Service name cannot be empty or whitespace"
        )

    # Check for existing duplicate (case-insensitive)
    cursor = conn.execute("SELECT id FROM services WHERE LOWER(name) = LOWER(?);", (clean_name,))
    if cursor.fetchone():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Service with name '{clean_name}' already exists"
        )

    cursor = conn.execute("INSERT INTO services (name) VALUES (?);", (clean_name,))
    conn.commit()
    new_id = cursor.lastrowid
    return {"id": new_id, "name": clean_name}


@router.delete("/{service_id}", status_code=status.HTTP_200_OK)
def delete_service(service_id: int, conn: sqlite3.Connection = Depends(get_db)):
    """Delete a service by ID.
    
    Blocks deletion if referenced by active RFPs (HTTP 409 Conflict).
    Associated price_items.service_id is set to NULL, and kb_document_services
    junction records are cascade deleted.
    """
    cursor = conn.execute("SELECT id, name FROM services WHERE id = ?;", (service_id,))
    row = cursor.fetchone()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Service with id {service_id} not found"
        )

    # Check if service is in active use by RFPs
    ref_cur = conn.execute("SELECT COUNT(*) FROM rfp_services WHERE service_id = ?;", (service_id,))
    if ref_cur.fetchone()[0] > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot delete service currently in use by active RFPs"
        )

    conn.execute("DELETE FROM services WHERE id = ?;", (service_id,))
    conn.commit()
    return {
        "success": True,
        "message": f"Service '{row['name']}' deleted successfully",
        "id": service_id,
        "deleted": service_id,
    }


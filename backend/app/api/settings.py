"""API router for application settings management.

Secrets policy: API keys are write-only from the browser's point of view. GET returns a
masked value (`••••` + last four characters) and PUT ignores any value that still
carries the mask so an unchanged form never overwrites a stored key with its mask.
"""

import sqlite3
from fastapi import APIRouter, Depends, HTTPException, status

from app.database import get_db
from app.schemas import SettingsResponse, SettingsUpdate

router = APIRouter(prefix="/settings", tags=["Settings"])

SECRET_FIELDS = ("claude_api_key", "gemini_api_key", "hubspot_api_key")
MASK = "••••"


def mask_secret(value: str) -> str:
    """Return a masked representation that reveals only the last four characters."""
    value = (value or "").strip()
    if not value:
        return ""
    return f"{MASK}{value[-4:]}" if len(value) > 4 else MASK


def is_masked(value: str) -> bool:
    return isinstance(value, str) and value.startswith(MASK)


def _row_to_settings_dict(row: sqlite3.Row) -> dict:
    """Convert SQLite row to dictionary with correct types for SettingsResponse."""
    data = dict(row)
    data["mock_google_export"] = bool(data.get("mock_google_export", 1))
    for field in SECRET_FIELDS:
        data[field] = mask_secret(data.get(field) or "")
    data["google_credentials_path"] = data.get("google_credentials_path") or "credentials.json"
    data["weight_won"] = float(data.get("weight_won") if data.get("weight_won") is not None else 1.25)
    data["weight_lost"] = float(data.get("weight_lost") if data.get("weight_lost") is not None else 0.90)
    data["hubspot_portal_id"] = data.get("hubspot_portal_id") or ""
    return data


@router.get("", response_model=SettingsResponse)
def get_settings(conn: sqlite3.Connection = Depends(get_db)):
    """Retrieve the application settings singleton (secrets masked)."""
    row = conn.execute("SELECT * FROM settings WHERE id = 1;").fetchone()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Settings record not initialized. Run database initialization."
        )
    return _row_to_settings_dict(row)


@router.put("", response_model=SettingsResponse)
def update_settings(payload: SettingsUpdate, conn: sqlite3.Connection = Depends(get_db)):
    """Update settings fields and return the updated singleton record (secrets masked)."""
    existing = conn.execute("SELECT * FROM settings WHERE id = 1;").fetchone()
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Settings record not initialized. Run database initialization."
        )

    update_data = payload.model_dump(exclude_unset=True)

    # Never let a masked echo overwrite the real secret.
    for field in SECRET_FIELDS:
        if field in update_data and is_masked(update_data[field] or ""):
            update_data.pop(field)

    if not update_data:
        return _row_to_settings_dict(existing)

    if "mock_google_export" in update_data and update_data["mock_google_export"] is not None:
        update_data["mock_google_export"] = 1 if update_data["mock_google_export"] else 0

    set_clauses = [f"{key} = ?" for key in update_data]
    values = list(update_data.values()) + [1]
    conn.execute(f"UPDATE settings SET {', '.join(set_clauses)} WHERE id = ?;", values)
    conn.commit()

    updated = conn.execute("SELECT * FROM settings WHERE id = 1;").fetchone()
    return _row_to_settings_dict(updated)

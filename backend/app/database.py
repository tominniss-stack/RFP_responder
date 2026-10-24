"""Database connection and lifecycle management for SQLite.

Enforces:
- Foreign keys enabled per connection (PRAGMA foreign_keys = ON;)
- Write-Ahead Logging for concurrency (PRAGMA journal_mode = WAL;)
- Busy timeout to prevent lock contention (PRAGMA busy_timeout = 5000;)
- sqlite3.Row row factory for dict-like column access
"""

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Optional

# Default database file: backend/data/rfp_assistant.db
DEFAULT_DB_DIR = Path(__file__).resolve().parent.parent / "data"
DEFAULT_DB_PATH = DEFAULT_DB_DIR / "rfp_assistant.db"

DATABASE_PATH = os.getenv("DATABASE_PATH", str(DEFAULT_DB_PATH))


def get_db_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    """Create and configure a SQLite connection with foreign keys and WAL mode.
    
    Args:
        db_path: Optional database path override (useful for tests or custom paths).
        
    Returns:
        Configured sqlite3.Connection instance with Row factory.
    """
    target_path = db_path if db_path is not None else DATABASE_PATH

    # For disk databases, ensure the parent directory exists
    if target_path != ":memory:" and not target_path.startswith("file:"):
        os.makedirs(os.path.dirname(os.path.abspath(target_path)), exist_ok=True)

    conn = sqlite3.connect(target_path, timeout=10.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row

    # Enforce SQLite PRAGMAs
    conn.execute("PRAGMA foreign_keys = ON;")
    if target_path != ":memory:":
        conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA busy_timeout = 5000;")

    return conn


def get_db() -> Generator[sqlite3.Connection, None, None]:
    """FastAPI dependency yielding an active SQLite connection.
    
    Commits on successful request execution, rolls back on exception,
    and reliably closes the connection in all cases.
    """
    conn = get_db_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@contextmanager
def get_db_context(db_path: Optional[str] = None) -> Generator[sqlite3.Connection, None, None]:
    """Context manager for non-HTTP workflows (CLI scripts, migrations, tests)."""
    conn = get_db_connection(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(db_path: Optional[str] = None) -> None:
    """Initialize SQLite database schema and seed initial configuration idempotently."""
    from app.models import create_tables
    from app.services.seed import seed_database

    with get_db_context(db_path) as conn:
        create_tables(conn)
        seed_database(conn)

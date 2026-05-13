"""
database/db.py – Async-friendly SQLite wrapper using the stdlib sqlite3 module.

All queries run in a thread-pool executor so they never block the event loop.
"""

import asyncio
import sqlite3
import logging
from pathlib import Path
from functools import wraps
from typing import Any

log = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent / "economy.db"
SCHEMA_PATH = Path(__file__).parent / "schema.sql"

# Module-level connection (re-used across calls)
# _conn: sqlite3.Connection | None = None
from typing import Optional
_conn: Optional[sqlite3.Connection] = None

# ── Initialisation ─────────────────────────────────────────────────────────────

def _get_conn() -> sqlite3.Connection:
    """Return the singleton SQLite connection, creating it if needed."""
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row          # rows behave like dicts
        _conn.execute("PRAGMA journal_mode=WAL")  # safer concurrent writes
        _conn.execute("PRAGMA foreign_keys=ON")
        log.info("SQLite connection opened at %s", DB_PATH)
    return _conn


def init_db() -> None:
    """Create tables from schema.sql (called once at bot startup)."""
    conn = _get_conn()
    schema = SCHEMA_PATH.read_text()
    conn.executescript(schema)
    conn.commit()
    log.info("Database initialised.")


# ── Low-level helpers ──────────────────────────────────────────────────────────

def _run_sync(fn, *args, **kwargs):
    """Run a synchronous callable in the default thread-pool executor."""
    loop = asyncio.get_event_loop()
    return loop.run_in_executor(None, lambda: fn(*args, **kwargs))


async def fetchone(query: str, params: tuple = ()) -> sqlite3.Row | None:
    """Return a single row or None."""
    def _inner():
        return _get_conn().execute(query, params).fetchone()
    return await _run_sync(_inner)


async def fetchall(query: str, params: tuple = ()) -> list[sqlite3.Row]:
    """Return all matching rows."""
    def _inner():
        return _get_conn().execute(query, params).fetchall()
    return await _run_sync(_inner)


async def execute(query: str, params: tuple = ()) -> None:
    """Execute a write query and commit."""
    def _inner():
        conn = _get_conn()
        conn.execute(query, params)
        conn.commit()
    await _run_sync(_inner)


async def executemany(query: str, params_list: list[tuple]) -> None:
    """Execute a write query for multiple rows and commit."""
    def _inner():
        conn = _get_conn()
        conn.executemany(query, params_list)
        conn.commit()
    await _run_sync(_inner)


# ── User helpers ───────────────────────────────────────────────────────────────

async def ensure_user(user_id: int) -> None:
    """Insert a new user row if one does not already exist (idempotent)."""
    await execute(
        "INSERT OR IGNORE INTO users (user_id) VALUES (?)",
        (user_id,),
    )


async def get_user(user_id: int) -> sqlite3.Row | None:
    """Fetch a user row, auto-creating the record if missing."""
    await ensure_user(user_id)
    return await fetchone("SELECT * FROM users WHERE user_id = ?", (user_id,))


async def add_wallet(user_id: int, amount: int, reason: str = "") -> None:
    """Add *amount* (may be negative) to the user's wallet and log it."""
    await ensure_user(user_id)
    await execute(
        "UPDATE users SET wallet = wallet + ? WHERE user_id = ?",
        (amount, user_id),
    )
    if reason:
        await execute(
            "INSERT INTO transactions (user_id, amount, reason) VALUES (?, ?, ?)",
            (user_id, amount, reason),
        )


async def set_last_daily(user_id: int, iso_datetime: str) -> None:
    await execute(
        "UPDATE users SET last_daily = ? WHERE user_id = ?",
        (iso_datetime, user_id),
    )


async def add_xp(user_id: int, xp_amount: int) -> int:
    """Add XP and auto-level. Returns the new level."""
    from config import XP_PER_LEVEL
    await ensure_user(user_id)
    row = await fetchone("SELECT xp, level FROM users WHERE user_id = ?", (user_id,))
    new_xp = row["xp"] + xp_amount
    new_level = new_xp // XP_PER_LEVEL + 1
    await execute(
        "UPDATE users SET xp = ?, level = ? WHERE user_id = ?",
        (new_xp, new_level, user_id),
    )
    return new_level

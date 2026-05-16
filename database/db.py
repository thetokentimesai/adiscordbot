"""
database/db.py – Async PostgreSQL wrapper using asyncpg.
Connects to Aiven PostgreSQL via DATABASE_URL environment variable.

Changes:
  - add_wallet now enforces wallet >= 0 (no debt)
  - Added set_last_weekly / set_last_monthly
  - Schema init includes last_weekly, last_monthly columns
"""

import asyncio
import asyncpg
import logging
from typing import Optional

log = logging.getLogger(__name__)

_pool: Optional[asyncpg.Pool] = None


# ── Initialisation ─────────────────────────────────────────────────────────────

async def _get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        import config
        _pool = await asyncpg.create_pool(config.DATABASE_URL, min_size=1, max_size=5)
        log.info("PostgreSQL connection pool created.")
    return _pool


def init_db() -> None:
    """Create tables — called once at bot startup."""
    asyncio.get_event_loop().run_until_complete(_init_db_async())


async def _init_db_async() -> None:
    pool = await _get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id        BIGINT PRIMARY KEY,
                wallet         BIGINT NOT NULL DEFAULT 0,
                bank           BIGINT NOT NULL DEFAULT 0,
                last_daily     TEXT,
                last_hourly    TEXT,
                last_work      TEXT,
                last_sidequest TEXT,
                last_weekly    TEXT,
                last_monthly   TEXT,
                xp             BIGINT NOT NULL DEFAULT 0,
                level          INTEGER NOT NULL DEFAULT 1
            )
        """)
        # Add new columns if upgrading from an older schema
        new_columns = [
            ("last_hourly",    "TEXT"),
            ("last_work",      "TEXT"),
            ("last_sidequest", "TEXT"),
            ("last_weekly",    "TEXT"),
            ("last_monthly",   "TEXT"),
        ]
        for col, col_type in new_columns:
            try:
                await conn.execute(f"ALTER TABLE users ADD COLUMN {col} {col_type}")
            except Exception:
                pass  # column already exists

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id          BIGSERIAL PRIMARY KEY,
                user_id     BIGINT NOT NULL,
                amount      BIGINT NOT NULL,
                reason      TEXT NOT NULL,
                created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
    log.info("Database initialised.")


# ── Low-level helpers ──────────────────────────────────────────────────────────

async def fetchone(query: str, params: tuple = ()) -> Optional[asyncpg.Record]:
    pool = await _get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow(query, *params)


async def fetchall(query: str, params: tuple = ()) -> list[asyncpg.Record]:
    pool = await _get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch(query, *params)


async def execute(query: str, params: tuple = ()) -> None:
    pool = await _get_pool()
    async with pool.acquire() as conn:
        await conn.execute(query, *params)


async def executemany(query: str, params_list: list[tuple]) -> None:
    pool = await _get_pool()
    async with pool.acquire() as conn:
        await conn.executemany(query, params_list)


# ── User helpers ───────────────────────────────────────────────────────────────

async def ensure_user(user_id: int) -> None:
    await execute(
        "INSERT INTO users (user_id) VALUES ($1) ON CONFLICT (user_id) DO NOTHING",
        (user_id,),
    )


async def get_user(user_id: int) -> Optional[asyncpg.Record]:
    await ensure_user(user_id)
    return await fetchone("SELECT * FROM users WHERE user_id = $1", (user_id,))


async def add_wallet(user_id: int, amount: int, reason: str = "") -> None:
    """
    Add *amount* (may be negative) to the user's wallet and log it.
    Wallet is clamped to 0 — it can never go negative.
    """
    await ensure_user(user_id)
    # Use GREATEST to prevent negative wallet balance (no debt allowed)
    await execute(
        "UPDATE users SET wallet = GREATEST(0, wallet + $1) WHERE user_id = $2",
        (amount, user_id),
    )
    if reason:
        await execute(
            "INSERT INTO transactions (user_id, amount, reason) VALUES ($1, $2, $3)",
            (user_id, amount, reason),
        )


async def set_last_daily(user_id: int, iso_datetime: str) -> None:
    await execute("UPDATE users SET last_daily = $1 WHERE user_id = $2", (iso_datetime, user_id))


async def set_last_hourly(user_id: int, iso_datetime: str) -> None:
    await execute("UPDATE users SET last_hourly = $1 WHERE user_id = $2", (iso_datetime, user_id))


async def set_last_work(user_id: int, iso_datetime: str) -> None:
    await execute("UPDATE users SET last_work = $1 WHERE user_id = $2", (iso_datetime, user_id))


async def set_last_sidequest(user_id: int, iso_datetime: str) -> None:
    await execute("UPDATE users SET last_sidequest = $1 WHERE user_id = $2", (iso_datetime, user_id))


async def set_last_weekly(user_id: int, iso_datetime: str) -> None:
    await execute("UPDATE users SET last_weekly = $1 WHERE user_id = $2", (iso_datetime, user_id))


async def set_last_monthly(user_id: int, iso_datetime: str) -> None:
    await execute("UPDATE users SET last_monthly = $1 WHERE user_id = $2", (iso_datetime, user_id))


async def add_xp(user_id: int, xp_amount: int) -> int:
    """Add XP and auto-level. Returns the new level."""
    from config import XP_PER_LEVEL
    await ensure_user(user_id)
    row = await fetchone("SELECT xp, level FROM users WHERE user_id = $1", (user_id,))
    new_xp = row["xp"] + xp_amount
    new_level = new_xp // XP_PER_LEVEL + 1
    await execute(
        "UPDATE users SET xp = $1, level = $2 WHERE user_id = $3",
        (new_xp, new_level, user_id),
    )
    return new_level
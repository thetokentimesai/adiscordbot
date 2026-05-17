"""
database/db.py – Async PostgreSQL wrapper using asyncpg.
"""

import asyncpg
import logging
from typing import Optional

log = logging.getLogger(__name__)

_pool: Optional[asyncpg.Pool] = None


async def _get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        import config
        _pool = await asyncpg.create_pool(config.DATABASE_URL, min_size=1, max_size=5, ssl="require")
        log.info("PostgreSQL connection pool created.")
    return _pool


async def init_db() -> None:
    await _init_db_async()


async def _init_db_async() -> None:
    pool = await _get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id        BIGINT  PRIMARY KEY,
                wallet         BIGINT  NOT NULL DEFAULT 0,
                bank           BIGINT  NOT NULL DEFAULT 0,
                last_daily     TEXT,
                last_hourly    TEXT,
                last_work      TEXT,
                last_sidequest TEXT,
                last_weekly    TEXT,
                last_monthly   TEXT,
                last_rob       TEXT,
                last_steal     TEXT,
                last_heist     TEXT,
                jail_until     TEXT,
                xp             BIGINT  NOT NULL DEFAULT 0,
                level          INTEGER NOT NULL DEFAULT 1,
                daily_streak   INTEGER NOT NULL DEFAULT 0,
                last_mg_win    TEXT,
                mg_streak      INTEGER NOT NULL DEFAULT 0,
                mg_wins        INTEGER NOT NULL DEFAULT 0
            )
        """)

        new_columns = [
            ("last_hourly",    "TEXT"),
            ("last_work",      "TEXT"),
            ("last_sidequest", "TEXT"),
            ("last_weekly",    "TEXT"),
            ("last_monthly",   "TEXT"),
            ("last_rob",       "TEXT"),
            ("last_steal",     "TEXT"),
            ("last_heist",     "TEXT"),
            ("jail_until",     "TEXT"),
            ("daily_streak",   "INTEGER NOT NULL DEFAULT 0"),
            ("last_mg_win",    "TEXT"),
            ("mg_streak",      "INTEGER NOT NULL DEFAULT 0"),
            ("mg_wins",        "INTEGER NOT NULL DEFAULT 0"),
        ]
        for col, col_type in new_columns:
            try:
                await conn.execute(f"ALTER TABLE users ADD COLUMN {col} {col_type}")
            except Exception:
                pass

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id         BIGSERIAL   PRIMARY KEY,
                user_id    BIGINT      NOT NULL,
                amount     BIGINT      NOT NULL,
                reason     TEXT        NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
    log.info("Database initialised.")


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


async def ensure_user(user_id: int) -> None:
    await execute("INSERT INTO users (user_id) VALUES ($1) ON CONFLICT (user_id) DO NOTHING", (user_id,))


async def get_user(user_id: int) -> Optional[asyncpg.Record]:
    await ensure_user(user_id)
    return await fetchone("SELECT * FROM users WHERE user_id = $1", (user_id,))


async def add_wallet(user_id: int, amount: int, reason: str = "") -> None:
    await ensure_user(user_id)
    await execute("UPDATE users SET wallet = GREATEST(0, wallet + $1) WHERE user_id = $2", (amount, user_id))
    if reason:
        await execute("INSERT INTO transactions (user_id, amount, reason) VALUES ($1, $2, $3)", (user_id, amount, reason))


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

async def set_last_rob(user_id: int, iso_datetime: str) -> None:
    await execute("UPDATE users SET last_rob = $1 WHERE user_id = $2", (iso_datetime, user_id))

async def set_last_steal(user_id: int, iso_datetime: str) -> None:
    await execute("UPDATE users SET last_steal = $1 WHERE user_id = $2", (iso_datetime, user_id))

async def set_last_heist(user_id: int, iso_datetime: str) -> None:
    await execute("UPDATE users SET last_heist = $1 WHERE user_id = $2", (iso_datetime, user_id))

async def set_jail_until(user_id: int, iso_datetime) -> None:
    await execute("UPDATE users SET jail_until = $1 WHERE user_id = $2", (iso_datetime, user_id))

async def set_daily_streak(user_id: int, streak: int) -> None:
    await execute("UPDATE users SET daily_streak = $1 WHERE user_id = $2", (streak, user_id))


async def record_mg_win(user_id: int) -> int:
    """Record a minigame win, update streak (resets if >10 min gap). Returns new streak."""
    from datetime import datetime, timezone, timedelta
    row = await get_user(user_id)
    now = datetime.now(tz=timezone.utc)
    last_win_str    = row["last_mg_win"]
    current_streak  = row["mg_streak"] or 0
    if last_win_str:
        last_win = datetime.fromisoformat(last_win_str).replace(tzinfo=timezone.utc)
        new_streak = current_streak + 1 if (now - last_win) <= timedelta(minutes=10) else 1
    else:
        new_streak = 1
    await execute(
        "UPDATE users SET last_mg_win = $1, mg_streak = $2, mg_wins = mg_wins + 1 WHERE user_id = $3",
        (now.isoformat(), new_streak, user_id),
    )
    return new_streak


async def get_leaderboard(column: str = "wallet", limit: int = 10) -> list[asyncpg.Record]:
    safe = {"wallet", "bank", "xp", "mg_wins"}
    if column not in safe:
        column = "wallet"
    return await fetchall(
        f"SELECT user_id, wallet, bank, xp, level, mg_wins, daily_streak, mg_streak FROM users ORDER BY {column} DESC LIMIT $1",
        (limit,),
    )


async def get_rank(user_id: int, column: str = "wallet") -> int:
    safe = {"wallet", "bank", "xp", "mg_wins"}
    if column not in safe:
        column = "wallet"
    row = await fetchone(
        f"SELECT COUNT(*) + 1 AS rank FROM users WHERE {column} > (SELECT {column} FROM users WHERE user_id = $1)",
        (user_id,),
    )
    return row["rank"] if row else 1


async def add_xp(user_id: int, xp_amount: int) -> int:
    from config import XP_PER_LEVEL
    await ensure_user(user_id)
    row = await fetchone("SELECT xp, level FROM users WHERE user_id = $1", (user_id,))
    new_xp    = row["xp"] + xp_amount
    new_level = new_xp // XP_PER_LEVEL + 1
    await execute("UPDATE users SET xp = $1, level = $2 WHERE user_id = $3", (new_xp, new_level, user_id))
    return new_level
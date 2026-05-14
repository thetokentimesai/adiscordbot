"""
utils/cooldowns.py – Reusable cooldown helpers.

DB-backed cooldowns for persistent rewards (daily, hourly, work, sidequest).
In-memory cooldowns for short per-session things (gamble spam).
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta

# ── In-memory cooldown store ───────────────────────────────────────────────────
_cooldowns: dict[tuple[int, str], datetime] = {}


def get_remaining(user_id: int, command: str) -> float:
    expires = _cooldowns.get((user_id, command))
    if expires is None:
        return 0.0
    return max(0.0, (expires - datetime.now(tz=timezone.utc)).total_seconds())


def set_cooldown(user_id: int, command: str, seconds: float) -> None:
    _cooldowns[(user_id, command)] = datetime.now(tz=timezone.utc) + timedelta(seconds=seconds)


def is_on_cooldown(user_id: int, command: str) -> bool:
    return get_remaining(user_id, command) > 0.0


def format_remaining(seconds: float) -> str:
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    parts = []
    if h:
        parts.append(f"{h}h")
    if m:
        parts.append(f"{m}m")
    parts.append(f"{s}s")
    return " ".join(parts)


# ── Generic DB-backed cooldown check ──────────────────────────────────────────

async def check_db_cooldown(user_id: int, column: str, cooldown_seconds: float) -> tuple[bool, float]:
    from database import db
    row = await db.get_user(user_id)
    last_str = row[column]

    if not last_str:
        return True, 0.0

    last_dt = datetime.fromisoformat(last_str).replace(tzinfo=timezone.utc)
    cooldown_end = last_dt + timedelta(seconds=cooldown_seconds)
    now = datetime.now(tz=timezone.utc)

    if now >= cooldown_end:
        return True, 0.0
    return False, (cooldown_end - now).total_seconds()


async def check_daily_cooldown(user_id: int) -> tuple[bool, float]:
    from config import DAILY_COOLDOWN_HOURS
    return await check_db_cooldown(user_id, "last_daily", DAILY_COOLDOWN_HOURS * 3600)


async def check_hourly_cooldown(user_id: int) -> tuple[bool, float]:
    from config import HOURLY_COOLDOWN_MINUTES
    return await check_db_cooldown(user_id, "last_hourly", HOURLY_COOLDOWN_MINUTES * 60)


async def check_work_cooldown(user_id: int) -> tuple[bool, float]:
    from config import WORK_COOLDOWN_MINUTES
    return await check_db_cooldown(user_id, "last_work", WORK_COOLDOWN_MINUTES * 60)


async def check_sidequest_cooldown(user_id: int) -> tuple[bool, float]:
    from config import SIDEQUEST_COOLDOWN_HOURS
    return await check_db_cooldown(user_id, "last_sidequest", SIDEQUEST_COOLDOWN_HOURS * 3600)
"""
utils/cooldowns.py – Reusable cooldown helpers.

We store cooldown state directly in the SQLite DB (last_daily column)
for persistent cooldowns that survive bot restarts. For in-memory
per-session cooldowns we use a simple dict.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta
from typing import Callable

# ── In-memory cooldown store ───────────────────────────────────────────────────
# key: (user_id, command_name) → datetime when cooldown expires
_cooldowns: dict[tuple[int, str], datetime] = {}


def get_remaining(user_id: int, command: str) -> float:
    """
    Return seconds remaining on a cooldown, or 0.0 if not on cooldown.
    """
    expires = _cooldowns.get((user_id, command))
    if expires is None:
        return 0.0
    now = datetime.now(tz=timezone.utc)
    remaining = (expires - now).total_seconds()
    return max(0.0, remaining)


def set_cooldown(user_id: int, command: str, seconds: float) -> None:
    """Record that *user_id* is on cooldown for *command* for *seconds*."""
    expires = datetime.now(tz=timezone.utc) + timedelta(seconds=seconds)
    _cooldowns[(user_id, command)] = expires


def is_on_cooldown(user_id: int, command: str) -> bool:
    return get_remaining(user_id, command) > 0.0


def format_remaining(seconds: float) -> str:
    """Human-readable cooldown string like '4h 22m 10s'."""
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


# ── DB-backed daily cooldown ───────────────────────────────────────────────────

async def check_daily_cooldown(user_id: int) -> tuple[bool, float]:
    """
    Check if the user can claim their daily reward.

    Returns (can_claim: bool, seconds_remaining: float).
    Uses the last_daily column from the DB for persistence.
    """
    from database import db
    from config import DAILY_COOLDOWN_HOURS

    row = await db.get_user(user_id)
    last_daily_str: str | None = row["last_daily"]

    if not last_daily_str:
        return True, 0.0

    last_daily = datetime.fromisoformat(last_daily_str).replace(tzinfo=timezone.utc)
    cooldown_end = last_daily + timedelta(hours=DAILY_COOLDOWN_HOURS)
    now = datetime.now(tz=timezone.utc)

    if now >= cooldown_end:
        return True, 0.0

    remaining = (cooldown_end - now).total_seconds()
    return False, remaining

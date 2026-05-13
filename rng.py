"""
utils/rng.py – Deterministic weekly RNG for fun commands.

The value for a given user stays the same for the entire ISO week
(Monday–Sunday) and automatically changes the next week.

Algorithm:
    seed = SHA-256( str(user_id) + str(year) + str(week_number) + salt )
    value = seed_int % 101   →  0–100
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone


# ── Core helper ────────────────────────────────────────────────────────────────

def _weekly_seed(user_id: int, salt: str) -> int:
    """
    Produce a stable integer seed for this (user, week, salt) triple.
    Changes automatically every Monday 00:00 UTC.
    """
    now = datetime.now(tz=timezone.utc)
    year, week, _ = now.isocalendar()           # ISO week: Mon=1 … Sun=7
    raw = f"{user_id}:{year}:{week}:{salt}"
    digest = hashlib.sha256(raw.encode()).hexdigest()
    return int(digest, 16)


def weekly_percent(user_id: int, salt: str) -> int:
    """Return a deterministic 0–100 percentage that resets every week."""
    return _weekly_seed(user_id, salt) % 101


def weekly_percent_pair(user_id_1: int, user_id_2: int, salt: str) -> int:
    """
    Deterministic percentage for two users together (order-independent).
    Used by /ship so ship(A, B) == ship(B, A).
    """
    ordered = sorted([user_id_1, user_id_2])
    combined_id = int(f"{ordered[0]}{ordered[1]}")
    return _weekly_seed(combined_id, salt) % 101


# ── Convenience wrappers used by fun.py ───────────────────────────────────────

def gaybar_percent(user_id: int) -> int:
    return weekly_percent(user_id, salt="gaybar")


def susmeter_percent(user_id: int) -> int:
    return weekly_percent(user_id, salt="susmeter")


def nerdrate_percent(user_id: int) -> int:
    return weekly_percent(user_id, salt="nerdrate")


def ship_percent(user_id_1: int, user_id_2: int) -> int:
    return weekly_percent_pair(user_id_1, user_id_2, salt="ship")

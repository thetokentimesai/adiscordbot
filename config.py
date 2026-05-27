"""
config.py – Central config loader using environment variables.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ── Bot credentials ────────────────────────────────────────────────────────────
DISCORD_TOKEN: str = os.environ["DISCORD_TOKEN"]

# ── Guild restriction ──────────────────────────────────────────────────────────
ALLOWED_GUILD_ID: int = int(os.environ["ALLOWED_GUILD_ID"])

# ── Database ───────────────────────────────────────────────────────────────────
DATABASE_URL: str = os.environ["DATABASE_URL"]

# ── Currency display ───────────────────────────────────────────────────────────
CURRENCY_SYMBOL: str = "🪙"
CURRENCY_NAME: str   = "coins"

# ── Gambling limits ────────────────────────────────────────────────────────────
MIN_BET: int = 10
MAX_BET: int = 500_000

# ── Level XP thresholds ────────────────────────────────────────────────────────
XP_PER_LEVEL:   int = 500
XP_PER_COMMAND: int = 10

# ── Daily reward ───────────────────────────────────────────────────────────────
DAILY_MIN: int           = 200
DAILY_MAX: int           = 800
DAILY_COOLDOWN_HOURS: int = 22
# Streak: +5% bonus per DAILY_STREAK_INTERVAL days of consecutive claims
DAILY_STREAK_BONUS_PCT:  float = 5.0   # percent per interval
DAILY_STREAK_INTERVAL:   int   = 7     # days per bonus tier

# ── Hourly reward ──────────────────────────────────────────────────────────────
HOURLY_MIN: int              = 50
HOURLY_MAX: int              = 150
HOURLY_COOLDOWN_MINUTES: int = 60

# ── Work reward ────────────────────────────────────────────────────────────────
WORK_MIN: int              = 100
WORK_MAX: int              = 300
WORK_COOLDOWN_MINUTES: int = 30

# ── Side quest reward ──────────────────────────────────────────────────────────
SIDEQUEST_MIN: int           = 300
SIDEQUEST_MAX: int           = 700
SIDEQUEST_COOLDOWN_HOURS: int = 6

# ── Weekly reward ─────────────────────────────────────────────────────────────
WEEKLY_MIN: int = 5_000
WEEKLY_MAX: int = 15_000

# ── Monthly reward ────────────────────────────────────────────────────────────
MONTHLY_MIN: int = 25_000
MONTHLY_MAX: int = 75_000

# ── Role names ────────────────────────────────────────────────────────────────
# Members who have EITHER of these roles can use weekly/monthly.
VERIFIED_ROLE_NAME: str    = "Verified"
ADMIN_ROLE_NAME: str       = "・Administrators"

# ── Minigame settings ─────────────────────────────────────────────────────────
MINIGAME_REWARD_MIN: int = 100
MINIGAME_REWARD_MAX: int = 500
MINIGAME_AUTO_EVERY: int = 25
MINIGAME_TIMEOUT: int    = 30

# ── Embed colours ─────────────────────────────────────────────────────────────
COLOR_SUCCESS: int = 0x2ECC71
COLOR_ERROR: int   = 0xE74C3C
COLOR_INFO: int    = 0x3498DB
COLOR_GOLD: int    = 0xF1C40F
COLOR_PURPLE: int  = 0x9B59B6

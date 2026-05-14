"""
config.py – Central config loader using environment variables.
All settings are read from the .env file via python-dotenv.
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
CURRENCY_NAME: str = "coins"

# ── Gambling limits ────────────────────────────────────────────────────────────
MIN_BET: int = 10
MAX_BET: int = 50_000

# ── Level XP thresholds ────────────────────────────────────────────────────────
XP_PER_LEVEL: int = 500
XP_PER_COMMAND: int = 10

# ── Daily reward ───────────────────────────────────────────────────────────────
DAILY_MIN: int = 200
DAILY_MAX: int = 800
DAILY_COOLDOWN_HOURS: int = 22

# ── Hourly reward ──────────────────────────────────────────────────────────────
HOURLY_MIN: int = 50
HOURLY_MAX: int = 150
HOURLY_COOLDOWN_MINUTES: int = 60

# ── Work reward ────────────────────────────────────────────────────────────────
WORK_MIN: int = 100
WORK_MAX: int = 300
WORK_COOLDOWN_MINUTES: int = 30

# ── Side quest reward ──────────────────────────────────────────────────────────
SIDEQUEST_MIN: int = 300
SIDEQUEST_MAX: int = 700
SIDEQUEST_COOLDOWN_HOURS: int = 6

# ── Embed colours ─────────────────────────────────────────────────────────────
COLOR_SUCCESS: int = 0x2ECC71
COLOR_ERROR: int   = 0xE74C3C
COLOR_INFO: int    = 0x3498DB
COLOR_GOLD: int    = 0xF1C40F
COLOR_PURPLE: int  = 0x9B59B6
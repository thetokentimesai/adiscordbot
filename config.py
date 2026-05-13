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

# ── Economy settings ───────────────────────────────────────────────────────────
DAILY_MIN: int = 200          # minimum daily reward
DAILY_MAX: int = 800          # maximum daily reward
DAILY_COOLDOWN_HOURS: int = 22  # hours before /daily resets

# ── Currency display ───────────────────────────────────────────────────────────
CURRENCY_SYMBOL: str = "🪙"
CURRENCY_NAME: str = "coins"

# ── Gambling limits ────────────────────────────────────────────────────────────
MIN_BET: int = 10
MAX_BET: int = 50_000

# ── Level XP thresholds ────────────────────────────────────────────────────────
XP_PER_LEVEL: int = 500       # XP needed per level
XP_PER_COMMAND: int = 10      # XP awarded per economy command use

# ── Embed colours ─────────────────────────────────────────────────────────────
COLOR_SUCCESS: int = 0x2ECC71
COLOR_ERROR: int   = 0xE74C3C
COLOR_INFO: int    = 0x3498DB
COLOR_GOLD: int    = 0xF1C40F
COLOR_PURPLE: int  = 0x9B59B6

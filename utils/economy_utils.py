"""
utils/economy_utils.py – Shared economy helpers used across cogs.
"""

from __future__ import annotations

import discord
from config import CURRENCY_SYMBOL, CURRENCY_NAME, COLOR_ERROR, COLOR_SUCCESS


# ── Formatting ─────────────────────────────────────────────────────────────────

def fmt(amount: int) -> str:
    """Format a coin amount with comma separators and the currency symbol."""
    return f"{CURRENCY_SYMBOL} {amount:,}"


# ── Embed factories ────────────────────────────────────────────────────────────

def error_embed(description: str) -> discord.Embed:
    return discord.Embed(description=f"❌  {description}", color=COLOR_ERROR)


def success_embed(title: str, description: str) -> discord.Embed:
    return discord.Embed(title=title, description=description, color=COLOR_SUCCESS)


# ── Validation ─────────────────────────────────────────────────────────────────

async def validate_bet(
    ctx,
    amount: int,
    wallet: int,
) -> bool:
    """
    Send an error message and return False if the bet is invalid.
    Returns True when the bet is okay.
    """
    from config import MIN_BET, MAX_BET

    if amount <= 0:
        await ctx.send(
            embed=error_embed("Bet amount must be greater than 0.")
        )
        return False

    if amount < MIN_BET:
        await ctx.send(
            embed=error_embed(f"Minimum bet is {fmt(MIN_BET)}.")
        )
        return False

    if amount > MAX_BET:
        await ctx.send(
            embed=error_embed(f"Maximum bet is {fmt(MAX_BET)}.")
        )
        return False

    if amount > wallet:
        await ctx.send(
            embed=error_embed(
                f"You only have {fmt(wallet)} in your wallet."
            )
        )
        return False

    return True

"""
cogs/fun.py – Fun percentage commands with deterministic weekly RNG.

Commands: .gaybar, .ship, .susmeter, .nerdrate
"""

from __future__ import annotations

import discord
from discord.ext import commands

import config
from utils.rng import gaybar_percent, susmeter_percent, nerdrate_percent, ship_percent
from utils.economy_utils import error_embed


# ── Progress bar helper ────────────────────────────────────────────────────────

def _bar(percent: int, length: int = 10) -> str:
    """Render a Unicode block progress bar."""
    filled = round(percent / 100 * length)
    return "█" * filled + "░" * (length - filled)


# ── Ship name generator ────────────────────────────────────────────────────────

def _ship_name(name1: str, name2: str) -> str:
    """Combine two display names into a ship name."""
    half1 = name1[: max(1, len(name1) // 2)]
    half2 = name2[max(0, len(name2) // 2) :]
    return (half1 + half2).capitalize()


# ── Flavour text ───────────────────────────────────────────────────────────────

_SHIP_MESSAGES = [
    "It's written in the stars! ✨",
    "A match made in heaven! 💫",
    "There might be some sparks here… 🔥",
    "Meh, could work with some effort. 🤷",
    "Friendship goals at most. 🥲",
    "Disaster waiting to happen. 💥",
    "404: Love not found. 🤖",
]

def _ship_message(percent: int) -> str:
    index = min(int(percent / 100 * len(_SHIP_MESSAGES)), len(_SHIP_MESSAGES) - 1)
    return _SHIP_MESSAGES[-(index + 1)]   # higher % → earlier (better) messages


_GAY_MESSAGES = {
    (0, 20):   "Totally straight 🏳️",
    (20, 40):  "Maybe a little curious 🤔",
    (40, 60):  "Somewhere in the middle 🌈",
    (60, 80):  "Pretty gay ngl 💅",
    (80, 101): "MAXED OUT 🏳️‍🌈🏳️‍🌈🏳️‍🌈",
}

def _gay_message(percent: int) -> str:
    for (lo, hi), msg in _GAY_MESSAGES.items():
        if lo <= percent < hi:
            return msg
    return "???"


_SUS_MESSAGES = {
    (0, 20):   "Not sus at all 🟢",
    (20, 40):  "Slightly suspicious 🟡",
    (40, 60):  "Kinda sus 🟠",
    (60, 80):  "Very sus 🔴",
    (80, 101): "RED IS THE IMPOSTOR 📣",
}

def _sus_message(percent: int) -> str:
    for (lo, hi), msg in _SUS_MESSAGES.items():
        if lo <= percent < hi:
            return msg
    return "???"


_NERD_MESSAGES = {
    (0, 20):   "Normal human being 😎",
    (20, 40):  "Knows a few things 🤓",
    (40, 60):  "Certified geek 🧪",
    (60, 80):  "Full nerd mode activated 💻",
    (80, 101): "Escaped from a research lab 🧬",
}

def _nerd_message(percent: int) -> str:
    for (lo, hi), msg in _NERD_MESSAGES.items():
        if lo <= percent < hi:
            return msg
    return "???"


# ── Cog ────────────────────────────────────────────────────────────────────────

class Fun(commands.Cog):
    """Weekly deterministic fun commands."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ── .gaybar ────────────────────────────────────────────────────────────────

    @commands.command(name="gaybar", aliases=["gay"], help="Check someone's gay % this week 🌈")
    async def gaybar(self, ctx: commands.Context, user: discord.Member = None):
        target  = user or ctx.author
        percent = gaybar_percent(target.id)

        embed = discord.Embed(
            title=f"🌈  Gay-o-Meter: {target.display_name}",
            description=(
                f"{_bar(percent)}  **{percent}%**\n\n"
                f"{_gay_message(percent)}"
            ),
            color=config.COLOR_PURPLE,
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.set_footer(text="Resets every Monday 00:00 UTC")
        await ctx.send(embed=embed)

    # ── .susmeter ──────────────────────────────────────────────────────────────

    @commands.command(name="susmeter", aliases=["sus"], help="How sus is this person? 📣")
    async def susmeter(self, ctx: commands.Context, user: discord.Member = None):
        target  = user or ctx.author
        percent = susmeter_percent(target.id)

        embed = discord.Embed(
            title=f"📣  Sus Meter: {target.display_name}",
            description=(
                f"{_bar(percent)}  **{percent}%**\n\n"
                f"{_sus_message(percent)}"
            ),
            color=0xE74C3C,
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.set_footer(text="Resets every Monday 00:00 UTC")
        await ctx.send(embed=embed)

    # ── .nerdrate ──────────────────────────────────────────────────────────────

    @commands.command(name="nerdrate", aliases=["nerd"], help="How nerdy is this person? 🤓")
    async def nerdrate(self, ctx: commands.Context, user: discord.Member = None):
        target  = user or ctx.author
        percent = nerdrate_percent(target.id)

        embed = discord.Embed(
            title=f"🤓  Nerd Rate: {target.display_name}",
            description=(
                f"{_bar(percent)}  **{percent}%**\n\n"
                f"{_nerd_message(percent)}"
            ),
            color=0x3498DB,
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.set_footer(text="Resets every Monday 00:00 UTC")
        await ctx.send(embed=embed)

    # ── .ship ──────────────────────────────────────────────────────────────────
    # REPLACE your current .ship command with THIS

    @commands.command(name="ship", help="Ship yourself with another user 💞")
    async def ship(self, ctx: commands.Context, user: discord.Member = None):

        if user is None:
            return await ctx.send(
                embed=error_embed(
                    "Usage: `.ship @user`"
                )
            )

        if user.id == ctx.author.id:
            return await ctx.send(
                embed=error_embed(
                    "You cannot ship yourself 😭"
                )
            )

        percent = ship_percent(ctx.author.id, user.id)

        ship_name = _ship_name(
            ctx.author.display_name,
            user.display_name
        )

        embed = discord.Embed(
            title=f"💞 {ship_name}",
            description=(
                f"{ctx.author.mention} ❤️ {user.mention}\n\n"
                f"{_bar(percent)}  **{percent}%**\n\n"
                f"{_ship_message(percent)}"
            ),
            color=config.COLOR_GOLD,
        )

        embed.set_footer(
            text="Relationship score resets every Monday 00:00 UTC"
        )

        await ctx.send(embed=embed)


def setup(bot: commands.Bot) -> None:
    bot.add_cog(Fun(bot))

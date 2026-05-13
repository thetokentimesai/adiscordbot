"""
cogs/fun.py – Fun percentage commands with deterministic weekly RNG.

Commands: /gaybar, /ship, /susmeter, /nerdrate
"""

from __future__ import annotations

import discord
from discord.ext import commands

import config
from utils.rng import gaybar_percent, susmeter_percent, nerdrate_percent, ship_percent


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

    def __init__(self, bot: discord.Bot) -> None:
        self.bot = bot

    # ── /gaybar ────────────────────────────────────────────────────────────────

    @discord.slash_command(name="gaybar", description="Check someone's gay % this week 🌈")
    async def gaybar(
        self,
        ctx: discord.ApplicationContext,
        user: discord.Option(discord.Member, "Who to check", required=False) = None,
    ):
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
        await ctx.respond(embed=embed)

    # ── /susmeter ──────────────────────────────────────────────────────────────

    @discord.slash_command(name="susmeter", description="How sus is this person? 📣")
    async def susmeter(
        self,
        ctx: discord.ApplicationContext,
        user: discord.Option(discord.Member, "Who to check", required=False) = None,
    ):
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
        await ctx.respond(embed=embed)

    # ── /nerdrate ──────────────────────────────────────────────────────────────

    @discord.slash_command(name="nerdrate", description="How nerdy is this person? 🤓")
    async def nerdrate(
        self,
        ctx: discord.ApplicationContext,
        user: discord.Option(discord.Member, "Who to check", required=False) = None,
    ):
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
        await ctx.respond(embed=embed)

    # ── /ship ──────────────────────────────────────────────────────────────────

    @discord.slash_command(name="ship", description="Check the compatibility of two users 💞")
    async def ship(
        self,
        ctx: discord.ApplicationContext,
        user1: discord.Option(discord.Member, "First user", required=True),
        user2: discord.Option(discord.Member, "Second user", required=True),
    ):
        if user1.id == user2.id:
            embed = discord.Embed(
                description="You can't ship someone with themselves! 😂",
                color=config.COLOR_ERROR,
            )
            return await ctx.respond(embed=embed, ephemeral=True)

        percent   = ship_percent(user1.id, user2.id)
        ship_name = _ship_name(user1.display_name, user2.display_name)
        message   = _ship_message(percent)

        # Heart colour based on percent
        heart = "💔" if percent < 30 else ("❤️" if percent < 70 else "💖")

        embed = discord.Embed(
            title=f"{heart}  Ship: {user1.display_name} & {user2.display_name}",
            color=config.COLOR_PURPLE,
        )
        embed.add_field(
            name="Ship Name",
            value=f"**{ship_name}**",
            inline=False,
        )
        embed.add_field(
            name="Compatibility",
            value=f"{_bar(percent)}  **{percent}%**",
            inline=False,
        )
        embed.add_field(name="Verdict", value=message, inline=False)
        embed.set_footer(text="Resets every Monday 00:00 UTC")
        await ctx.respond(embed=embed)


def setup(bot: discord.Bot) -> None:
    bot.add_cog(Fun(bot))

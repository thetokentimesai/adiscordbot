"""
cogs/economy.py – Core economy commands.

Commands: .balance/.bal, .wallet/.w, .daily/.dy, .hourly/.hr,
          .weekly/.wk, .monthly/.mo, .work/.wr, .sidequest/.sq,
          .cooldowns/.cd, .deposit/.dep/.d, .withdraw/.wd,
          .send/.pay, .rob, .steal, .heist,
          .addmoney (admin), .leaderboard/.lb, .rank
"""

from __future__ import annotations

import random
from datetime import datetime, timezone, timedelta

import discord
from discord.ext import commands

import config
from database import db
from utils.cooldowns import (
    check_daily_cooldown,
    check_hourly_cooldown,
    check_work_cooldown,
    check_sidequest_cooldown,
    check_weekly_cooldown,
    check_monthly_cooldown,
    check_rob_cooldown,
    check_steal_cooldown,
    check_heist_cooldown,
    format_remaining,
)
from utils.economy_utils import fmt, error_embed, success_embed

# ── Progress bar helper ────────────────────────────────────────────────────────

def _progress_bar(current: float, maximum: float, length: int = 12) -> str:
    if maximum <= 0:
        filled = 0
    else:
        filled = round((current / maximum) * length)
    filled = max(0, min(filled, length))
    return "█" * filled + "░" * (length - filled)


# ── Role helpers ───────────────────────────────────────────────────────────────

def _has_privileged_role(member: discord.Member) -> bool:
    """True if member has the Verified role OR the Administrators role."""
    allowed = {
        getattr(config, "VERIFIED_ROLE_NAME", "Verified"),
        getattr(config, "ADMIN_ROLE_NAME",    "・Administrators"),
    }
    return any(r.name in allowed for r in member.roles)


def _is_admin(member: discord.Member) -> bool:
    """True if member has the Administrators role or Discord admin perms."""
    admin_role = getattr(config, "ADMIN_ROLE_NAME", "・Administrators")
    return (
        any(r.name == admin_role for r in member.roles)
        or member.guild_permissions.administrator
    )


# ── Amount parser ──────────────────────────────────────────────────────────────

def parse_amount(raw: str):
    """Parse: 100 | 1k | 1.5m | all  →  int | 'all' | None"""
    raw = raw.lower().strip()
    if raw == "all":
        return "all"
    multipliers = {"k": 1_000, "m": 1_000_000, "b": 1_000_000_000}
    for suffix, mult in multipliers.items():
        if raw.endswith(suffix):
            try:
                return int(float(raw[:-1]) * mult)
            except ValueError:
                return None
    try:
        return int(raw)
    except ValueError:
        return None


# ── Flavour text ───────────────────────────────────────────────────────────────

WORK_MESSAGES = [
    "You fixed some bugs and got paid",
    "You delivered pizzas and earned",
    "You walked some dogs and pocketed",
    "You wrote code for a client and billed",
    "You won a street chess match for",
    "You sold some old stuff online for",
    "You tutored a student and earned",
    "You did some freelance design work for",
]

SIDEQUEST_MESSAGES = [
    "You descended into a dungeon and looted",
    "You found a hidden treasure chest containing",
    "You completed a bounty and claimed",
    "You helped a merchant and were rewarded",
    "You won a card tournament, taking home",
    "You sold a rare artifact for",
    "You cracked a safe and found",
]


# ── Cog ────────────────────────────────────────────────────────────────────────

class Economy(commands.Cog):
    """Wallet, bank, rewards and transfer commands."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ── .balance ───────────────────────────────────────────────────────────────

    @commands.command(name="balance", aliases=["bal"])
    async def balance(self, ctx: commands.Context, user: discord.Member = None):
        target    = user or ctx.author
        row       = await db.get_user(target.id)
        net_worth = row["wallet"] + row["bank"]
        rank      = await db.get_rank(target.id, "wallet")

        xp_in_level = row["xp"] % config.XP_PER_LEVEL
        bar = _progress_bar(xp_in_level, config.XP_PER_LEVEL)

        embed = discord.Embed(
            title=f"💰  {target.display_name}'s Balance",
            color=config.COLOR_GOLD,
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name="👛 Wallet",      value=fmt(row["wallet"]),          inline=True)
        embed.add_field(name="🏦 Bank",        value=fmt(row["bank"]),            inline=True)
        embed.add_field(name="💎 Net Worth",   value=fmt(net_worth),              inline=True)
        embed.add_field(name="⭐ Level",       value=str(row["level"]),           inline=True)
        embed.add_field(name="🏆 Wallet Rank", value=f"#{rank}",                  inline=True)
        embed.add_field(name="🔥 Daily Streak",value=str(row["daily_streak"]),    inline=True)
        embed.add_field(
            name=f"✨ XP  ({xp_in_level:,} / {config.XP_PER_LEVEL:,})",
            value=f"`{bar}`",
            inline=False,
        )
        await ctx.send(embed=embed)

    # ── .wallet ────────────────────────────────────────────────────────────────

    @commands.command(name="wallet", aliases=["w"])
    async def wallet(self, ctx: commands.Context, user: discord.Member = None):
        target = user or ctx.author
        row    = await db.get_user(target.id)
        embed  = discord.Embed(
            title=f"👛  {target.display_name}'s Wallet",
            description=fmt(row["wallet"]),
            color=config.COLOR_GOLD,
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        await ctx.send(embed=embed)

    # ── .daily ─────────────────────────────────────────────────────────────────

    @commands.command(name="daily", aliases=["dy"])
    async def daily(self, ctx: commands.Context):
        user_id = ctx.author.id
        can_claim, remaining = await check_daily_cooldown(user_id)
        if not can_claim:
            return await ctx.send(embed=error_embed(
                f"You already claimed your daily! Come back in **{format_remaining(remaining)}**."
            ))

        row     = await db.get_user(user_id)
        now     = datetime.now(tz=timezone.utc)
        now_iso = now.isoformat()

        # ── Streak logic ───────────────────────────────────────────────────────
        last_str      = row["last_daily"]
        old_streak    = row["daily_streak"] or 0
        streak_broken = False

        if last_str:
            last_dt       = datetime.fromisoformat(last_str).replace(tzinfo=timezone.utc)
            hours_elapsed = (now - last_dt).total_seconds() / 3600
            if hours_elapsed <= 46:          # within 2 × cooldown window → streak continues
                new_streak = old_streak + 1
            else:
                new_streak    = 1
                streak_broken = old_streak > 0
        else:
            new_streak = 1

        # Bonus: +5% per 7-day tier (e.g. 7d=+5%, 14d=+10%, 21d=+15% …)
        bonus_pct  = getattr(config, "DAILY_STREAK_BONUS_PCT", 5.0)
        interval   = getattr(config, "DAILY_STREAK_INTERVAL",  7)
        tiers      = new_streak // interval
        multiplier = 1 + (tiers * bonus_pct / 100)

        base_reward    = random.randint(config.DAILY_MIN, config.DAILY_MAX)
        streak_bonus   = int(base_reward * (multiplier - 1))
        total_reward   = base_reward + streak_bonus

        await db.add_wallet(user_id, total_reward, reason="daily reward")
        await db.set_last_daily(user_id, now_iso)
        await db.set_daily_streak(user_id, new_streak)
        await db.add_xp(user_id, config.XP_PER_COMMAND)
        row = await db.get_user(user_id)

        next_tier_days  = interval - (new_streak % interval)
        bonus_label     = f"+{int(tiers * bonus_pct)}%" if tiers > 0 else "None yet"

        embed = discord.Embed(
            title="🎁  Daily Reward Claimed!",
            color=config.COLOR_SUCCESS,
        )
        embed.set_thumbnail(url=ctx.author.display_avatar.url)
        embed.add_field(name="💵 Received",       value=fmt(total_reward),           inline=True)
        embed.add_field(name="🔥 Streak",         value=f"{new_streak} days",        inline=True)
        embed.add_field(name="⚡ Streak Bonus",   value=bonus_label,                 inline=True)
        if streak_bonus > 0:
            embed.add_field(name="✨ Bonus Applied", value=fmt(streak_bonus),        inline=True)
        if streak_broken:
            embed.add_field(name="💔 Streak Lost", value="You missed a day!",        inline=False)
        embed.add_field(
            name="📅 Next Bonus Tier",
            value=f"In {next_tier_days} day(s) (+{int((tiers + 1) * bonus_pct)}%)",
            inline=False,
        )
        embed.set_footer(text=f"Balance: {fmt(row['wallet'])}  •  Come back in {config.DAILY_COOLDOWN_HOURS}h")
        await ctx.send(embed=embed)

    # ── .hourly ────────────────────────────────────────────────────────────────

    @commands.command(name="hourly", aliases=["hr"])
    async def hourly(self, ctx: commands.Context):
        user_id = ctx.author.id
        can_claim, remaining = await check_hourly_cooldown(user_id)
        if not can_claim:
            cd_total = config.HOURLY_COOLDOWN_MINUTES * 60
            progress = _progress_bar(cd_total - remaining, cd_total)
            embed = discord.Embed(title="⏰  Hourly Reward", color=config.COLOR_ERROR)
            embed.add_field(name="⏳ Come back in", value=f"**{format_remaining(remaining)}**", inline=True)
            embed.add_field(name="Progress",        value=f"`{progress}`",                       inline=False)
            return await ctx.send(embed=embed)

        reward  = random.randint(config.HOURLY_MIN, config.HOURLY_MAX)
        now_iso = datetime.now(tz=timezone.utc).isoformat()
        await db.add_wallet(user_id, reward, reason="hourly reward")
        await db.set_last_hourly(user_id, now_iso)
        await db.add_xp(user_id, config.XP_PER_COMMAND)
        row = await db.get_user(user_id)

        embed = discord.Embed(title="⏰  Hourly Reward!", color=config.COLOR_SUCCESS)
        embed.set_thumbnail(url=ctx.author.display_avatar.url)
        embed.add_field(name="💵 Received", value=fmt(reward),       inline=True)
        embed.add_field(name="👛 Balance",  value=fmt(row["wallet"]), inline=True)
        embed.set_footer(text=f"Come back in {config.HOURLY_COOLDOWN_MINUTES} minutes.")
        await ctx.send(embed=embed)

    # ── .work ──────────────────────────────────────────────────────────────────

    @commands.command(name="work", aliases=["wr"])
    async def work(self, ctx: commands.Context):
        user_id = ctx.author.id
        can_claim, remaining = await check_work_cooldown(user_id)
        if not can_claim:
            cd_total = config.WORK_COOLDOWN_MINUTES * 60
            progress = _progress_bar(cd_total - remaining, cd_total)
            embed = discord.Embed(title="💼  Work", color=config.COLOR_ERROR)
            embed.add_field(name="⏳ Come back in", value=f"**{format_remaining(remaining)}**", inline=True)
            embed.add_field(name="Progress",        value=f"`{progress}`",                       inline=False)
            return await ctx.send(embed=embed)

        reward  = random.randint(config.WORK_MIN, config.WORK_MAX)
        message = random.choice(WORK_MESSAGES)
        now_iso = datetime.now(tz=timezone.utc).isoformat()
        await db.add_wallet(user_id, reward, reason="work reward")
        await db.set_last_work(user_id, now_iso)
        await db.add_xp(user_id, config.XP_PER_COMMAND)
        row = await db.get_user(user_id)

        embed = discord.Embed(title="💼  Work Complete!", color=config.COLOR_SUCCESS)
        embed.set_thumbnail(url=ctx.author.display_avatar.url)
        embed.description = f"{message} **{fmt(reward)}**!"
        embed.add_field(name="👛 Balance", value=fmt(row["wallet"]), inline=True)
        embed.set_footer(text=f"Come back in {config.WORK_COOLDOWN_MINUTES} minutes.")
        await ctx.send(embed=embed)

    # ── .sidequest ─────────────────────────────────────────────────────────────

    @commands.command(name="sidequest", aliases=["sq"])
    async def sidequest(self, ctx: commands.Context):
        user_id = ctx.author.id
        can_claim, remaining = await check_sidequest_cooldown(user_id)
        if not can_claim:
            cd_total = config.SIDEQUEST_COOLDOWN_HOURS * 3600
            progress = _progress_bar(cd_total - remaining, cd_total)
            embed = discord.Embed(title="⚔️  Sidequest", color=config.COLOR_ERROR)
            embed.add_field(name="⏳ Come back in", value=f"**{format_remaining(remaining)}**", inline=True)
            embed.add_field(name="Progress",        value=f"`{progress}`",                       inline=False)
            return await ctx.send(embed=embed)

        reward  = random.randint(config.SIDEQUEST_MIN, config.SIDEQUEST_MAX)
        message = random.choice(SIDEQUEST_MESSAGES)
        now_iso = datetime.now(tz=timezone.utc).isoformat()
        await db.add_wallet(user_id, reward, reason="sidequest reward")
        await db.set_last_sidequest(user_id, now_iso)
        await db.add_xp(user_id, config.XP_PER_COMMAND)
        row = await db.get_user(user_id)

        embed = discord.Embed(title="⚔️  Sidequest Complete!", color=config.COLOR_SUCCESS)
        embed.set_thumbnail(url=ctx.author.display_avatar.url)
        embed.description = f"{message} **{fmt(reward)}**!"
        embed.add_field(name="👛 Balance", value=fmt(row["wallet"]), inline=True)
        embed.set_footer(text=f"Come back in {config.SIDEQUEST_COOLDOWN_HOURS} hours.")
        await ctx.send(embed=embed)

    # ── .weekly ────────────────────────────────────────────────────────────────

    @commands.command(name="weekly", aliases=["wk"])
    async def weekly(self, ctx: commands.Context):
        if not _has_privileged_role(ctx.author):
            return await ctx.send(embed=error_embed(
                f"🔒 This command requires the **{config.VERIFIED_ROLE_NAME}** "
                f"or **{config.ADMIN_ROLE_NAME}** role."
            ))
        user_id = ctx.author.id
        can_claim, remaining = await check_weekly_cooldown(user_id)
        if not can_claim:
            cd_total = 7 * 24 * 3600
            progress = _progress_bar(cd_total - remaining, cd_total)
            embed = discord.Embed(title="📅  Weekly Reward", color=config.COLOR_ERROR)
            embed.add_field(name="⏳ Come back in", value=f"**{format_remaining(remaining)}**", inline=True)
            embed.add_field(name="Progress",        value=f"`{progress}`",                       inline=False)
            return await ctx.send(embed=embed)

        reward  = random.randint(config.WEEKLY_MIN, config.WEEKLY_MAX)
        now_iso = datetime.now(tz=timezone.utc).isoformat()
        await db.add_wallet(user_id, reward, reason="weekly reward")
        await db.set_last_weekly(user_id, now_iso)
        await db.add_xp(user_id, config.XP_PER_COMMAND * 5)
        row = await db.get_user(user_id)

        embed = discord.Embed(title="📅  Weekly Reward!", color=config.COLOR_SUCCESS)
        embed.set_thumbnail(url=ctx.author.display_avatar.url)
        embed.add_field(name="💵 Received", value=fmt(reward),       inline=True)
        embed.add_field(name="👛 Balance",  value=fmt(row["wallet"]), inline=True)
        embed.set_footer(text="Come back in 7 days. 🔒 Verified/Admin only")
        await ctx.send(embed=embed)

    # ── .monthly ───────────────────────────────────────────────────────────────

    @commands.command(name="monthly", aliases=["mo"])
    async def monthly(self, ctx: commands.Context):
        if not _has_privileged_role(ctx.author):
            return await ctx.send(embed=error_embed(
                f"🔒 This command requires the **{config.VERIFIED_ROLE_NAME}** "
                f"or **{config.ADMIN_ROLE_NAME}** role."
            ))
        user_id = ctx.author.id
        can_claim, remaining = await check_monthly_cooldown(user_id)
        if not can_claim:
            cd_total = 30 * 24 * 3600
            progress = _progress_bar(cd_total - remaining, cd_total)
            embed = discord.Embed(title="🗓️  Monthly Reward", color=config.COLOR_ERROR)
            embed.add_field(name="⏳ Come back in", value=f"**{format_remaining(remaining)}**", inline=True)
            embed.add_field(name="Progress",        value=f"`{progress}`",                       inline=False)
            return await ctx.send(embed=embed)

        reward  = random.randint(config.MONTHLY_MIN, config.MONTHLY_MAX)
        now_iso = datetime.now(tz=timezone.utc).isoformat()
        await db.add_wallet(user_id, reward, reason="monthly reward")
        await db.set_last_monthly(user_id, now_iso)
        await db.add_xp(user_id, config.XP_PER_COMMAND * 20)
        row = await db.get_user(user_id)

        embed = discord.Embed(title="🗓️  Monthly Reward!", color=config.COLOR_SUCCESS)
        embed.set_thumbnail(url=ctx.author.display_avatar.url)
        embed.add_field(name="💵 Received", value=fmt(reward),       inline=True)
        embed.add_field(name="👛 Balance",  value=fmt(row["wallet"]), inline=True)
        embed.set_footer(text="Come back in 30 days. 🔒 Verified/Admin only")
        await ctx.send(embed=embed)

    # ── .cooldowns ─────────────────────────────────────────────────────────────

    @commands.command(name="cooldowns", aliases=["cd"])
    async def cooldowns(self, ctx: commands.Context):
        user_id = ctx.author.id

        # Gather all cooldowns
        eco_checks = [
            ("💼 Work",      check_work_cooldown,      config.WORK_COOLDOWN_MINUTES * 60),
            ("⏰ Hourly",    check_hourly_cooldown,    config.HOURLY_COOLDOWN_MINUTES * 60),
            ("⚔️ Sidequest", check_sidequest_cooldown, config.SIDEQUEST_COOLDOWN_HOURS * 3600),
        ]
        reward_checks = [
            ("🎁 Daily",    check_daily_cooldown,   config.DAILY_COOLDOWN_HOURS * 3600),
            ("📅 Weekly",   check_weekly_cooldown,  7  * 24 * 3600),
            ("🗓️ Monthly",  check_monthly_cooldown, 30 * 24 * 3600),
        ]
        crime_checks = [
            ("🦹 Rob",   check_rob_cooldown,   3 * 3600),
            ("🕵️ Steal", check_steal_cooldown, 3 * 3600),
            ("💰 Heist", check_heist_cooldown, 8 * 3600),
        ]

        def _cd_line(label, ready, remaining, total):
            if ready:
                bar = _progress_bar(total, total)
                return f"**{label}**\n✅ Ready!\n`{bar}` 100%"
            pct = int(((total - remaining) / total) * 100)
            bar = _progress_bar(total - remaining, total)
            return f"**{label}**\n⏰ in {format_remaining(remaining)}\n`{bar}` {pct}%"

        embed = discord.Embed(
            title=f"⏱️  {ctx.author.display_name}'s Cooldowns",
            color=config.COLOR_INFO,
        )
        embed.set_thumbnail(url=ctx.author.display_avatar.url)

        # Economy column
        eco_lines = []
        for label, fn, total in eco_checks:
            ready, rem = await fn(user_id)
            eco_lines.append(_cd_line(label, ready, rem, total))
        embed.add_field(name="🧰 Economy", value="\n\n".join(eco_lines), inline=True)

        # Rewards column
        reward_lines = []
        for label, fn, total in reward_checks:
            ready, rem = await fn(user_id)
            reward_lines.append(_cd_line(label, ready, rem, total))
        embed.add_field(name="🎁 Rewards", value="\n\n".join(reward_lines), inline=True)

        # Crime column
        crime_lines = []
        for label, fn, total in crime_checks:
            ready, rem = await fn(user_id)
            crime_lines.append(_cd_line(label, ready, rem, total))
        embed.add_field(name="💀 Crime", value="\n\n".join(crime_lines), inline=True)

        embed.set_footer(text="Page 1/1  •  Economy | Rewards | Crime")
        await ctx.send(embed=embed)

    # ── .deposit ───────────────────────────────────────────────────────────────

    @commands.command(name="deposit", aliases=["dep", "d"])
    async def deposit(self, ctx: commands.Context, amount: str = None):
        if amount is None:
            return await ctx.send(embed=error_embed("Usage: `.d <amount|all>`"))
        user_id = ctx.author.id
        row     = await db.get_user(user_id)
        parsed  = parse_amount(amount)
        if parsed is None:
            return await ctx.send(embed=error_embed("Invalid amount."))
        coins = row["wallet"] if parsed == "all" else parsed
        if coins <= 0:
            return await ctx.send(embed=error_embed("You have nothing to deposit."))
        if coins > row["wallet"]:
            return await ctx.send(embed=error_embed(f"You only have {fmt(row['wallet'])} in your wallet."))
        await db.execute("UPDATE users SET wallet = wallet - $1, bank = bank + $1 WHERE user_id = $2", (coins, user_id))
        row = await db.get_user(user_id)
        embed = discord.Embed(title="🏦  Deposit Successful", color=config.COLOR_SUCCESS)
        embed.add_field(name="➕ Deposited", value=fmt(coins),         inline=True)
        embed.add_field(name="👛 Wallet",    value=fmt(row["wallet"]), inline=True)
        embed.add_field(name="🏦 Bank",      value=fmt(row["bank"]),   inline=True)
        await ctx.send(embed=embed)

    # ── .withdraw ──────────────────────────────────────────────────────────────

    @commands.command(name="withdraw", aliases=["wd"])
    async def withdraw(self, ctx: commands.Context, amount: str = None):
        if amount is None:
            return await ctx.send(embed=error_embed("Usage: `.wd <amount|all>`"))
        user_id = ctx.author.id
        row     = await db.get_user(user_id)
        parsed  = parse_amount(amount)
        if parsed is None:
            return await ctx.send(embed=error_embed("Invalid amount."))
        coins = row["bank"] if parsed == "all" else parsed
        if coins <= 0:
            return await ctx.send(embed=error_embed("Nothing to withdraw."))
        if coins > row["bank"]:
            return await ctx.send(embed=error_embed(f"You only have {fmt(row['bank'])} in your bank."))
        await db.execute("UPDATE users SET bank = bank - $1, wallet = wallet + $1 WHERE user_id = $2", (coins, user_id))
        row = await db.get_user(user_id)
        embed = discord.Embed(title="👛  Withdrawal Successful", color=config.COLOR_SUCCESS)
        embed.add_field(name="➕ Withdrawn", value=fmt(coins),         inline=True)
        embed.add_field(name="👛 Wallet",    value=fmt(row["wallet"]), inline=True)
        embed.add_field(name="🏦 Bank",      value=fmt(row["bank"]),   inline=True)
        await ctx.send(embed=embed)

    # ── .send / .pay ───────────────────────────────────────────────────────────

    @commands.command(name="send", aliases=["pay", "give"])
    async def send(self, ctx: commands.Context, member: discord.Member = None, amount: str = None):
        if member is None or amount is None:
            return await ctx.send(embed=error_embed("Usage: `.send @user <amount>`"))
        if member.bot:
            return await ctx.send(embed=error_embed("You cannot send coins to bots."))
        if member.id == ctx.author.id:
            return await ctx.send(embed=error_embed("You cannot send coins to yourself."))
        parsed = parse_amount(amount)
        if parsed is None or parsed == "all" or parsed <= 0:
            return await ctx.send(embed=error_embed("Invalid amount."))
        sender = await db.get_user(ctx.author.id)
        if sender["wallet"] < parsed:
            return await ctx.send(embed=error_embed(f"You only have {fmt(sender['wallet'])} in your wallet."))
        await db.add_wallet(ctx.author.id, -parsed, reason=f"sent to {member.id}")
        await db.add_wallet(member.id,      parsed, reason=f"received from {ctx.author.id}")
        embed = discord.Embed(title="💸  Money Sent", color=config.COLOR_SUCCESS)
        embed.add_field(name="📤 To",     value=member.mention, inline=True)
        embed.add_field(name="💵 Amount", value=fmt(parsed),    inline=True)
        await ctx.send(embed=embed)

    # ── .rob ───────────────────────────────────────────────────────────────────

    @commands.command(name="rob")
    async def rob(self, ctx: commands.Context, member: discord.Member = None):
        if member is None:
            return await ctx.send(embed=error_embed("Usage: `.rob @user`"))
        if member.bot or member.id == ctx.author.id:
            return await ctx.send(embed=error_embed("Invalid target."))
        robber = await db.get_user(ctx.author.id)
        victim = await db.get_user(member.id)
        if robber["wallet"] < 250:
            return await ctx.send(embed=error_embed("You need at least 🪙 250 to rob someone."))
        if victim["wallet"] <= 0:
            return await ctx.send(embed=error_embed(f"{member.display_name} has nothing to steal."))
        can_use, remaining = await check_rob_cooldown(ctx.author.id)
        if not can_use:
            return await ctx.send(embed=error_embed(f"Wait **{format_remaining(remaining)}** before robbing again."))
        now_iso = datetime.now(tz=timezone.utc).isoformat()
        await db.set_last_rob(ctx.author.id, now_iso)
        if random.random() <= 0.12:
            percent = random.randint(35, 50)
            stolen  = max(1, int(victim["wallet"] * (percent / 100)))
            await db.add_wallet(member.id,      -stolen, reason="robbed")
            await db.add_wallet(ctx.author.id,   stolen, reason="rob success")
            embed = discord.Embed(title="🦹  Rob Successful!", color=config.COLOR_SUCCESS)
            embed.add_field(name="🎯 Target",  value=member.mention, inline=True)
            embed.add_field(name="💰 Stolen",  value=fmt(stolen),    inline=True)
            return await ctx.send(embed=embed)
        embed = discord.Embed(title="🚔  Rob Failed!", color=config.COLOR_ERROR)
        embed.description = f"You failed to rob {member.mention} and got away."
        await ctx.send(embed=embed)

    # ── .steal ─────────────────────────────────────────────────────────────────

    @commands.command(name="steal")
    async def steal(self, ctx: commands.Context, member: discord.Member = None):
        if member is None:
            return await ctx.send(embed=error_embed("Usage: `.steal @user`"))
        if member.bot or member.id == ctx.author.id:
            return await ctx.send(embed=error_embed("Invalid target."))
        robber = await db.get_user(ctx.author.id)
        victim = await db.get_user(member.id)
        if robber["wallet"] < 250:
            return await ctx.send(embed=error_embed("You need at least 🪙 250 to steal from someone."))
        if victim["wallet"] <= 0:
            return await ctx.send(embed=error_embed(f"{member.display_name} has nothing to steal."))
        can_use, remaining = await check_steal_cooldown(ctx.author.id)
        if not can_use:
            return await ctx.send(embed=error_embed(f"Wait **{format_remaining(remaining)}** before stealing again."))
        now_iso = datetime.now(tz=timezone.utc).isoformat()
        await db.set_last_steal(ctx.author.id, now_iso)
        if random.random() <= 0.25:
            percent = random.randint(15, 20)
            stolen  = max(1, int(victim["wallet"] * (percent / 100)))
            await db.add_wallet(member.id,     -stolen, reason="stolen from")
            await db.add_wallet(ctx.author.id,  stolen, reason="steal success")
            embed = discord.Embed(title="🕵️  Steal Successful!", color=config.COLOR_SUCCESS)
            embed.add_field(name="🎯 Target", value=member.mention, inline=True)
            embed.add_field(name="💰 Stolen", value=fmt(stolen),    inline=True)
            return await ctx.send(embed=embed)
        embed = discord.Embed(title="🚔  Steal Failed!", color=config.COLOR_ERROR)
        embed.description = f"You failed to steal from {member.mention}."
        await ctx.send(embed=embed)

    # ── .heist ─────────────────────────────────────────────────────────────────

    @commands.command(name="heist")
    async def heist(self, ctx: commands.Context, target: str = None,
                    member1: discord.Member = None, member2: discord.Member = None):
        if target is None:
            return await ctx.send(embed=error_embed("Usage: `.heist <store|jewelry|bank> [@user1] [@user2]`"))
        target = target.lower()
        heists = {
            "store":   {"reward": (15000, 25000), "jail": (1.5, 2),   "rates": {1: 15, 2: 20, 3: 25}},
            "jewelry": {"reward": (50000, 60000), "jail": (2,   3),   "rates": {1: 10, 2: 15, 3: 20}},
            "bank":    {"reward": (90000,100000), "jail": (3.5, 4),   "rates": {1:  5, 2: 10, 3: 15}},
        }
        if target not in heists:
            return await ctx.send(embed=error_embed("Choose: `store`, `jewelry`, or `bank`."))

        team = [ctx.author]
        for m in [member1, member2]:
            if m:
                if m.bot:
                    return await ctx.send(embed=error_embed("Bots cannot join heists."))
                team.append(m)
        if len(set(m.id for m in team)) != len(team):
            return await ctx.send(embed=error_embed("Duplicate users are not allowed."))

        for member in team:
            row = await db.get_user(member.id)
            if row["wallet"] < 2000:
                return await ctx.send(embed=error_embed(f"{member.display_name} needs at least 🪙 2,000."))
            if row["jail_until"]:
                jail_dt = datetime.fromisoformat(row["jail_until"]).replace(tzinfo=timezone.utc)
                if datetime.now(tz=timezone.utc) < jail_dt:
                    rem = (jail_dt - datetime.now(tz=timezone.utc)).total_seconds()
                    return await ctx.send(embed=error_embed(
                        f"{member.display_name} is in jail for **{format_remaining(rem)}**."
                    ))
                await db.set_jail_until(member.id, None)
            can_use, rem = await check_heist_cooldown(member.id)
            if not can_use:
                return await ctx.send(embed=error_embed(
                    f"{member.display_name} must wait **{format_remaining(rem)}** before another heist."
                ))

        data         = heists[target]
        success_rate = data["rates"][len(team)]
        now_iso      = datetime.now(tz=timezone.utc).isoformat()
        for member in team:
            await db.set_last_heist(member.id, now_iso)

        if random.randint(1, 100) <= success_rate:
            total    = random.randint(*data["reward"])
            split    = total // len(team)
            for member in team:
                await db.add_wallet(member.id, split, reason="heist success")
            mentions = ", ".join(m.mention for m in team)
            embed = discord.Embed(title="💰  Heist Successful!", color=config.COLOR_SUCCESS)
            embed.add_field(name="🎯 Target",       value=target.capitalize(),         inline=True)
            embed.add_field(name="💵 Total Stolen",  value=fmt(total),                  inline=True)
            embed.add_field(name="🤝 Each Member",   value=fmt(split),                  inline=True)
            embed.add_field(name="👥 Team",          value=mentions,                    inline=False)
            return await ctx.send(embed=embed)

        jail_hours = random.uniform(*data["jail"])
        jail_until = datetime.now(tz=timezone.utc) + timedelta(hours=jail_hours)
        for member in team:
            await db.set_jail_until(member.id, jail_until.isoformat())
        mentions = ", ".join(m.mention for m in team)
        embed = discord.Embed(title="🚔  Heist Failed!", color=config.COLOR_ERROR)
        embed.add_field(name="👥 Arrested",    value=mentions,                           inline=False)
        embed.add_field(name="⛓️ Jail Time",   value=f"{round(jail_hours, 1)} hours",    inline=True)
        await ctx.send(embed=embed)

    # ── .addmoney (admin only) ─────────────────────────────────────────────────

    @commands.command(name="addmoney")
    async def addmoney(self, ctx: commands.Context, member: discord.Member = None, amount: str = None):
        if not _is_admin(ctx.author):
            return await ctx.send(embed=error_embed("🔒 This command is for admins only."))
        if member is None or amount is None:
            return await ctx.send(embed=error_embed("Usage: `.addmoney @user <amount>`"))
        parsed = parse_amount(amount)
        if parsed is None or parsed == "all" or parsed == 0:
            return await ctx.send(embed=error_embed("Invalid amount. Supports negatives to remove: e.g. `-1000`."))
        # Allow negative amounts (remove money)
        await db.add_wallet(member.id, parsed, reason=f"admin addmoney by {ctx.author.id}")
        row = await db.get_user(member.id)
        action = "Added" if parsed >= 0 else "Removed"
        embed = discord.Embed(
            title=f"🛠️  Admin: {action} Coins",
            color=config.COLOR_SUCCESS if parsed >= 0 else config.COLOR_ERROR,
        )
        embed.add_field(name="👤 User",       value=member.mention,     inline=True)
        embed.add_field(name="💵 Amount",     value=fmt(abs(parsed)),   inline=True)
        embed.add_field(name="👛 New Wallet", value=fmt(row["wallet"]), inline=True)
        embed.set_footer(text=f"Action by {ctx.author.display_name}")
        await ctx.send(embed=embed)

    # ── /addmoney (slash, admin only, ephemeral) ───────────────────────────────

    @discord.slash_command(
        name="addmoney",
        description="Admin: add or remove coins from a user's wallet or bank",
    )
    async def slash_addmoney(
        self,
        ctx: discord.ApplicationContext,
        member: discord.Option(discord.Member, "Target user"),
        amount: discord.Option(int, "Amount to add (use a negative number to remove)"),
    ):
        if not _is_admin(ctx.author):
            return await ctx.respond(
                embed=error_embed("🔒 This command is for admins only."), ephemeral=True
            )

        await db.add_wallet(member.id, amount, reason=f"admin addmoney by {ctx.author.id}")
        row = await db.get_user(member.id)
        action = "Added" if amount >= 0 else "Removed"
        embed = discord.Embed(
            title=f"🛠️  Admin: {action} Coins",
            color=config.COLOR_SUCCESS if amount >= 0 else config.COLOR_ERROR,
        )
        embed.add_field(name="👤 User",       value=member.mention,     inline=True)
        embed.add_field(name="💵 Amount",     value=fmt(abs(amount)),   inline=True)
        embed.add_field(name="👛 New Wallet", value=fmt(row["wallet"]), inline=True)
        embed.set_footer(text=f"Action by {ctx.author.display_name}")
        await ctx.respond(embed=embed, ephemeral=True)

    # ── .leaderboard ───────────────────────────────────────────────────────────

    @commands.command(name="leaderboard", aliases=["lb"])
    async def leaderboard(self, ctx: commands.Context, category: str = "wallet"):
        category = category.lower()
        column_map = {
            "wallet": ("wallet", "👛 Richest Players"),
            "bank":   ("bank",   "🏦 Biggest Banks"),
            "xp":     ("xp",    "✨ XP Leaders"),
            "wins":   ("mg_wins","🎮 Minigame Champions"),
        }
        if category not in column_map:
            return await ctx.send(embed=error_embed(
                "Categories: `wallet`, `bank`, `xp`, `wins`\nExample: `.lb wallet`"
            ))
        col, title = column_map[category]
        rows = await db.get_leaderboard(col, limit=10)

        embed = discord.Embed(title=f"🏆  {title}", color=config.COLOR_GOLD)
        medals = ["🥇", "🥈", "🥉"]

        lines = []
        for i, row in enumerate(rows):
            medal = medals[i] if i < 3 else f"`{i+1}.`"
            try:
                member = ctx.guild.get_member(row["user_id"]) or await ctx.guild.fetch_member(row["user_id"])
                name   = member.display_name
            except Exception:
                name = f"User {row['user_id']}"
            value = row[col]
            display = fmt(value) if col in ("wallet", "bank") else f"{value:,}"
            lines.append(f"{medal} **{name}** — {display}")

        embed.description = "\n".join(lines) if lines else "No data yet!"
        embed.set_footer(text=f"Category: {category.capitalize()}  •  Use .lb wallet/bank/xp/wins")
        await ctx.send(embed=embed)

    # ── .rank ──────────────────────────────────────────────────────────────────

    @commands.command(name="rank")
    async def rank(self, ctx: commands.Context, user: discord.Member = None):
        target = user or ctx.author
        row    = await db.get_user(target.id)

        wallet_rank = await db.get_rank(target.id, "wallet")
        xp_rank     = await db.get_rank(target.id, "xp")
        mg_rank     = await db.get_rank(target.id, "mg_wins")

        xp_in_level = row["xp"] % config.XP_PER_LEVEL
        bar         = _progress_bar(xp_in_level, config.XP_PER_LEVEL)

        embed = discord.Embed(
            title=f"📊  {target.display_name}'s Rank",
            color=config.COLOR_PURPLE,
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name="👛 Wallet Rank",  value=f"#{wallet_rank}", inline=True)
        embed.add_field(name="✨ XP Rank",      value=f"#{xp_rank}",     inline=True)
        embed.add_field(name="🎮 MG Rank",      value=f"#{mg_rank}",     inline=True)
        embed.add_field(name="⭐ Level",        value=str(row["level"]), inline=True)
        embed.add_field(name="🎮 MG Wins",      value=str(row["mg_wins"]), inline=True)
        embed.add_field(name="🔥 Daily Streak", value=str(row["daily_streak"]), inline=True)
        embed.add_field(
            name=f"✨ XP Progress  ({xp_in_level:,} / {config.XP_PER_LEVEL:,})",
            value=f"`{bar}`",
            inline=False,
        )
        await ctx.send(embed=embed)


def setup(bot: commands.Bot) -> None:
    bot.add_cog(Economy(bot))

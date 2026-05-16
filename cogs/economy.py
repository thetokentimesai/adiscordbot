"""
cogs/economy.py – Core economy commands.

Commands: .balance/.bal, .wallet/.w, .daily/.dy, .hourly/.hr,
          .weekly/.wk, .monthly/.mo, .work/.wr, .sidequest/.sq,
          .cooldowns/.cd, .deposit/.dep/.d, .withdraw/.wd, .pay

Changes:
  - .weekly and .monthly are verified-member only (role name configurable in config.py)
  - All reward/bet amounts enforce non-negative wallet (no debt)
"""

from __future__ import annotations

import random
from datetime import datetime, timezone

import discord
from discord.ext import commands

import config
from database import db
from utils.cooldowns import (
    check_daily_cooldown, check_hourly_cooldown,
    check_work_cooldown, check_sidequest_cooldown,
    check_weekly_cooldown, check_monthly_cooldown,
    format_remaining,
)
from utils.economy_utils import fmt, error_embed, success_embed

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


def parse_amount(raw: str):
    """
    Parse amount strings: 100, 1k, 1.5k, 1m, all.
    Returns int, 'all', or None if invalid.
    """
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


def _is_verified(member: discord.Member) -> bool:
    """Check if member has the verified role defined in config."""
    verified_role_name = getattr(config, "VERIFIED_ROLE_NAME", "Verified")
    return any(r.name == verified_role_name for r in member.roles)


class Economy(commands.Cog):
    """Wallet, bank, rewards and transfer commands."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ── .balance ───────────────────────────────────────────────────────────────

    @commands.command(name="balance", aliases=["bal"], help="Check your (or another user's) full balance.")
    async def balance(self, ctx: commands.Context, user: discord.Member = None):
        target = user or ctx.author
        row = await db.get_user(target.id)
        net_worth = row["wallet"] + row["bank"]
        embed = discord.Embed(title=f"💰  {target.display_name}'s Balance", color=config.COLOR_GOLD)
        embed.add_field(name="👛 Wallet",    value=fmt(row["wallet"]), inline=True)
        embed.add_field(name="🏦 Bank",      value=fmt(row["bank"]),   inline=True)
        embed.add_field(name="📊 Net worth", value=fmt(net_worth),     inline=False)
        embed.add_field(name="⭐ Level",     value=str(row["level"]),  inline=True)
        embed.add_field(name="✨ XP",        value=f"{row['xp']:,}",   inline=True)
        embed.set_thumbnail(url=target.display_avatar.url)
        await ctx.send(embed=embed)

    # ── .wallet ────────────────────────────────────────────────────────────────

    @commands.command(name="wallet", aliases=["w"], help="Check just your wallet balance.")
    async def wallet(self, ctx: commands.Context, user: discord.Member = None):
        target = user or ctx.author
        row = await db.get_user(target.id)
        embed = discord.Embed(
            title=f"👛  {target.display_name}'s Wallet",
            description=fmt(row["wallet"]),
            color=config.COLOR_GOLD,
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        await ctx.send(embed=embed)

    # ── .daily ─────────────────────────────────────────────────────────────────

    @commands.command(name="daily", aliases=["dy"], help="Claim your daily reward! (22h cooldown)")
    async def daily(self, ctx: commands.Context):
        user_id = ctx.author.id
        can_claim, remaining = await check_daily_cooldown(user_id)
        if not can_claim:
            return await ctx.send(embed=error_embed(
                f"You already claimed your daily!\nCome back in **{format_remaining(remaining)}**."
            ))
        reward = random.randint(config.DAILY_MIN, config.DAILY_MAX)
        now_iso = datetime.now(tz=timezone.utc).isoformat()
        await db.add_wallet(user_id, reward, reason="daily reward")
        await db.set_last_daily(user_id, now_iso)
        await db.add_xp(user_id, config.XP_PER_COMMAND)
        row = await db.get_user(user_id)
        embed = success_embed("🎁  Daily Reward!", f"You received **{fmt(reward)}**!\n\nNew wallet: {fmt(row['wallet'])}")
        embed.set_footer(text=f"Come back in {config.DAILY_COOLDOWN_HOURS} hours.")
        await ctx.send(embed=embed)

    # ── .hourly ────────────────────────────────────────────────────────────────

    @commands.command(name="hourly", aliases=["hr"], help="Claim your hourly reward! (1h cooldown)")
    async def hourly(self, ctx: commands.Context):
        user_id = ctx.author.id
        can_claim, remaining = await check_hourly_cooldown(user_id)
        if not can_claim:
            return await ctx.send(embed=error_embed(
                f"You already claimed your hourly!\nCome back in **{format_remaining(remaining)}**."
            ))
        reward = random.randint(config.HOURLY_MIN, config.HOURLY_MAX)
        now_iso = datetime.now(tz=timezone.utc).isoformat()
        await db.add_wallet(user_id, reward, reason="hourly reward")
        await db.set_last_hourly(user_id, now_iso)
        await db.add_xp(user_id, config.XP_PER_COMMAND)
        row = await db.get_user(user_id)
        embed = success_embed("⏰  Hourly Reward!", f"You received **{fmt(reward)}**!\n\nNew wallet: {fmt(row['wallet'])}")
        embed.set_footer(text=f"Come back in {config.HOURLY_COOLDOWN_MINUTES} minutes.")
        await ctx.send(embed=embed)

    # ── .weekly ────────────────────────────────────────────────────────────────

    @commands.command(name="weekly", aliases=["wk"], help="Claim your weekly reward! Verified members only. (7d cooldown)")
    async def weekly(self, ctx: commands.Context):
        if not _is_verified(ctx.author):
            verified_role = getattr(config, "VERIFIED_ROLE_NAME", "Verified")
            return await ctx.send(embed=error_embed(
                f"🔒  This command is for **{verified_role}** members only!\n"
                f"Get verified in the server to unlock weekly & monthly rewards."
            ))
        user_id = ctx.author.id
        can_claim, remaining = await check_weekly_cooldown(user_id)
        if not can_claim:
            return await ctx.send(embed=error_embed(
                f"You already claimed your weekly!\nCome back in **{format_remaining(remaining)}**."
            ))
        reward = random.randint(config.WEEKLY_MIN, config.WEEKLY_MAX)
        now_iso = datetime.now(tz=timezone.utc).isoformat()
        await db.add_wallet(user_id, reward, reason="weekly reward")
        await db.set_last_weekly(user_id, now_iso)
        await db.add_xp(user_id, config.XP_PER_COMMAND * 5)
        row = await db.get_user(user_id)
        embed = success_embed("📅  Weekly Reward!", f"You received **{fmt(reward)}**!\n\nNew wallet: {fmt(row['wallet'])}")
        embed.set_footer(text="Come back in 7 days. Verified members only 🔒")
        await ctx.send(embed=embed)

    # ── .monthly ───────────────────────────────────────────────────────────────

    @commands.command(name="monthly", aliases=["mo"], help="Claim your monthly reward! Verified members only. (30d cooldown)")
    async def monthly(self, ctx: commands.Context):
        if not _is_verified(ctx.author):
            verified_role = getattr(config, "VERIFIED_ROLE_NAME", "Verified")
            return await ctx.send(embed=error_embed(
                f"🔒  This command is for **{verified_role}** members only!\n"
                f"Get verified in the server to unlock weekly & monthly rewards."
            ))
        user_id = ctx.author.id
        can_claim, remaining = await check_monthly_cooldown(user_id)
        if not can_claim:
            return await ctx.send(embed=error_embed(
                f"You already claimed your monthly!\nCome back in **{format_remaining(remaining)}**."
            ))
        reward = random.randint(config.MONTHLY_MIN, config.MONTHLY_MAX)
        now_iso = datetime.now(tz=timezone.utc).isoformat()
        await db.add_wallet(user_id, reward, reason="monthly reward")
        await db.set_last_monthly(user_id, now_iso)
        await db.add_xp(user_id, config.XP_PER_COMMAND * 20)
        row = await db.get_user(user_id)
        embed = success_embed("🗓️  Monthly Reward!", f"You received **{fmt(reward)}**!\n\nNew wallet: {fmt(row['wallet'])}")
        embed.set_footer(text="Come back in 30 days. Verified members only 🔒")
        await ctx.send(embed=embed)

    # ── .work ──────────────────────────────────────────────────────────────────

    @commands.command(name="work", aliases=["wr"], help="Do some work and earn coins! (30m cooldown)")
    async def work(self, ctx: commands.Context):
        user_id = ctx.author.id
        can_claim, remaining = await check_work_cooldown(user_id)
        if not can_claim:
            return await ctx.send(embed=error_embed(
                f"You're still tired from your last job!\nCome back in **{format_remaining(remaining)}**."
            ))
        reward = random.randint(config.WORK_MIN, config.WORK_MAX)
        now_iso = datetime.now(tz=timezone.utc).isoformat()
        message = random.choice(WORK_MESSAGES)
        await db.add_wallet(user_id, reward, reason="work reward")
        await db.set_last_work(user_id, now_iso)
        await db.add_xp(user_id, config.XP_PER_COMMAND)
        row = await db.get_user(user_id)
        embed = success_embed("💼  Work Complete!", f"{message} **{fmt(reward)}**!\n\nNew wallet: {fmt(row['wallet'])}")
        embed.set_footer(text=f"Come back in {config.WORK_COOLDOWN_MINUTES} minutes.")
        await ctx.send(embed=embed)

    # ── .sidequest ─────────────────────────────────────────────────────────────

    @commands.command(name="sidequest", aliases=["sq"], help="Go on a sidequest for big rewards! (6h cooldown)")
    async def sidequest(self, ctx: commands.Context):
        user_id = ctx.author.id
        can_claim, remaining = await check_sidequest_cooldown(user_id)
        if not can_claim:
            return await ctx.send(embed=error_embed(
                f"You're still recovering from your last adventure!\nCome back in **{format_remaining(remaining)}**."
            ))
        reward = random.randint(config.SIDEQUEST_MIN, config.SIDEQUEST_MAX)
        now_iso = datetime.now(tz=timezone.utc).isoformat()
        message = random.choice(SIDEQUEST_MESSAGES)
        await db.add_wallet(user_id, reward, reason="sidequest reward")
        await db.set_last_sidequest(user_id, now_iso)
        await db.add_xp(user_id, config.XP_PER_COMMAND)
        row = await db.get_user(user_id)
        embed = success_embed("⚔️  Sidequest Complete!", f"{message} **{fmt(reward)}**!\n\nNew wallet: {fmt(row['wallet'])}")
        embed.set_footer(text=f"Come back in {config.SIDEQUEST_COOLDOWN_HOURS} hours.")
        await ctx.send(embed=embed)

    # ── .cooldowns ─────────────────────────────────────────────────────────────

    @commands.command(name="cooldowns", aliases=["cd"], help="Check all your reward cooldowns.")
    async def cooldowns(self, ctx: commands.Context):
        user_id = ctx.author.id
        checks = {
            "🎁 Daily":      check_daily_cooldown,
            "⏰ Hourly":     check_hourly_cooldown,
            "💼 Work":       check_work_cooldown,
            "⚔️ Sidequest":  check_sidequest_cooldown,
        }
        embed = discord.Embed(title=f"⏱️  {ctx.author.display_name}'s Cooldowns", color=config.COLOR_INFO)
        for label, check_fn in checks.items():
            can_claim, remaining = await check_fn(user_id)
            embed.add_field(name=label, value="✅ Ready!" if can_claim else f"⏳ {format_remaining(remaining)}", inline=True)

        # Only show weekly/monthly if verified
        if _is_verified(ctx.author):
            for label, check_fn in [("📅 Weekly", check_weekly_cooldown), ("🗓️ Monthly", check_monthly_cooldown)]:
                can_claim, remaining = await check_fn(user_id)
                embed.add_field(name=label, value="✅ Ready!" if can_claim else f"⏳ {format_remaining(remaining)}", inline=True)
        else:
            verified_role = getattr(config, "VERIFIED_ROLE_NAME", "Verified")
            embed.set_footer(text=f"🔒 Get the {verified_role} role to unlock weekly & monthly rewards!")

        await ctx.send(embed=embed)

    # ── .deposit ───────────────────────────────────────────────────────────────

    @commands.command(name="deposit", aliases=["dep", "d"], help="Deposit coins to bank. Usage: .d <amount|all>")
    async def deposit(self, ctx: commands.Context, amount: str = None):
        if amount is None:
            return await ctx.send(embed=error_embed("Usage: `.d <amount|all>` — supports `1k`, `1.5m`, `all`"))
        user_id = ctx.author.id
        row = await db.get_user(user_id)
        parsed = parse_amount(amount)
        if parsed is None:
            return await ctx.send(embed=error_embed("Invalid amount. Try `100`, `1k`, `1.5m`, or `all`."))
        coins = row["wallet"] if parsed == "all" else parsed
        if coins <= 0:
            return await ctx.send(embed=error_embed("You have nothing to deposit."))
        if coins > row["wallet"]:
            return await ctx.send(embed=error_embed(f"You only have {fmt(row['wallet'])} in your wallet."))
        await db.execute(
            "UPDATE users SET wallet = wallet - $1, bank = bank + $1 WHERE user_id = $2",
            (coins, user_id),
        )
        row = await db.get_user(user_id)
        await ctx.send(embed=success_embed(
            "🏦  Deposit Successful",
            f"Deposited **{fmt(coins)}** into your bank.\n\nWallet: {fmt(row['wallet'])}  |  Bank: {fmt(row['bank'])}",
        ))

    # ── .withdraw ──────────────────────────────────────────────────────────────

    @commands.command(name="withdraw", aliases=["wd"], help="Withdraw coins from bank. Usage: .wd <amount|all>")
    async def withdraw(self, ctx: commands.Context, amount: str = None):
        if amount is None:
            return await ctx.send(embed=error_embed("Usage: `.wd <amount|all>` — supports `1k`, `1.5m`, `all`"))
        user_id = ctx.author.id
        row = await db.get_user(user_id)
        parsed = parse_amount(amount)
        if parsed is None:
            return await ctx.send(embed=error_embed("Invalid amount. Try `100`, `1k`, `1.5m`, or `all`."))
        coins = row["bank"] if parsed == "all" else parsed
        if coins <= 0:
            return await ctx.send(embed=error_embed("You have nothing to withdraw."))
        if coins > row["bank"]:
            return await ctx.send(embed=error_embed(f"You only have {fmt(row['bank'])} in your bank."))
        await db.execute(
            "UPDATE users SET bank = bank - $1, wallet = wallet + $1 WHERE user_id = $2",
            (coins, user_id),
        )
        row = await db.get_user(user_id)
        await ctx.send(embed=success_embed(
            "👛  Withdrawal Successful",
            f"Withdrew **{fmt(coins)}** to your wallet.\n\nWallet: {fmt(row['wallet'])}  |  Bank: {fmt(row['bank'])}",
        ))

    # ── .pay ───────────────────────────────────────────────────────────────────

    @commands.command(name="pay", help="Pay another user. Usage: .pay <@user> <amount>")
    async def pay(self, ctx: commands.Context, recipient: discord.Member = None, amount: str = None):
        if recipient is None or amount is None:
            return await ctx.send(embed=error_embed("Usage: `.pay <@user> <amount>` (e.g. `.pay @user 1k`)"))
        parsed = parse_amount(amount)
        if parsed is None or parsed == "all" or parsed < 1:
            return await ctx.send(embed=error_embed("Invalid amount. Try `100`, `1k`, `1.5m`."))
        sender_id = ctx.author.id
        recipient_id = recipient.id
        if recipient_id == sender_id:
            return await ctx.send(embed=error_embed("You can't pay yourself."))
        if recipient.bot:
            return await ctx.send(embed=error_embed("You can't pay a bot."))
        sender_row = await db.get_user(sender_id)
        if parsed > sender_row["wallet"]:
            return await ctx.send(embed=error_embed(f"You only have {fmt(sender_row['wallet'])} in your wallet."))
        await db.add_wallet(sender_id,    -parsed, reason=f"paid {recipient_id}")
        await db.add_wallet(recipient_id,  parsed, reason=f"received from {sender_id}")
        await ctx.send(embed=success_embed(
            "💸  Payment Sent",
            f"{ctx.author.mention} paid {recipient.mention} **{fmt(parsed)}**!",
        ))


def setup(bot: commands.Bot) -> None:
    bot.add_cog(Economy(bot))
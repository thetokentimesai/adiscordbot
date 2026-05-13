"""
cogs/economy.py – Core economy commands.

Commands: .balance, .daily, .deposit, .withdraw, .pay
"""

from __future__ import annotations

import random
from datetime import datetime, timezone

import discord
from discord.ext import commands

import config
from database import db
from utils.cooldowns import check_daily_cooldown, format_remaining
from utils.economy_utils import fmt, error_embed, success_embed


class Economy(commands.Cog):
    """Wallet, bank, and daily reward commands."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ── .balance ───────────────────────────────────────────────────────────────

    @commands.command(name="balance", aliases=["bal"], help="Check your (or another user's) balance.")
    async def balance(self, ctx: commands.Context, user: discord.Member = None):
        target = user or ctx.author
        row = await db.get_user(target.id)

        net_worth = row["wallet"] + row["bank"]
        embed = discord.Embed(
            title=f"💰  {target.display_name}'s Balance",
            color=config.COLOR_GOLD,
        )
        embed.add_field(name="👛 Wallet", value=fmt(row["wallet"]), inline=True)
        embed.add_field(name="🏦 Bank",   value=fmt(row["bank"]),   inline=True)
        embed.add_field(name="📊 Net worth", value=fmt(net_worth),  inline=False)
        embed.add_field(name="⭐ Level",  value=str(row["level"]),  inline=True)
        embed.add_field(name="✨ XP",     value=f"{row['xp']:,}",   inline=True)
        embed.set_thumbnail(url=target.display_avatar.url)
        await ctx.send(embed=embed)

    # ── .daily ─────────────────────────────────────────────────────────────────

    @commands.command(name="daily", help="Claim your daily reward!")
    async def daily(self, ctx: commands.Context):
        user_id = ctx.author.id
        can_claim, remaining = await check_daily_cooldown(user_id)

        if not can_claim:
            embed = error_embed(
                f"You already claimed your daily!\n"
                f"Come back in **{format_remaining(remaining)}**."
            )
            return await ctx.send(embed=embed)

        reward = random.randint(config.DAILY_MIN, config.DAILY_MAX)
        now_iso = datetime.now(tz=timezone.utc).isoformat()

        await db.add_wallet(user_id, reward, reason="daily reward")
        await db.set_last_daily(user_id, now_iso)
        await db.add_xp(user_id, config.XP_PER_COMMAND)

        row = await db.get_user(user_id)
        embed = success_embed(
            "🎁  Daily Reward!",
            f"You received **{fmt(reward)}**!\n\n"
            f"New wallet balance: {fmt(row['wallet'])}",
        )
        embed.set_footer(text=f"Come back in {config.DAILY_COOLDOWN_HOURS} hours.")
        await ctx.send(embed=embed)

    # ── .deposit ───────────────────────────────────────────────────────────────

    @commands.command(name="deposit", aliases=["dep"], help="Deposit coins from wallet to bank.")
    async def deposit(self, ctx: commands.Context, amount: str = None):
        if amount is None:
            return await ctx.send(embed=error_embed("Usage: `.deposit <amount|all>`"))

        user_id = ctx.author.id
        row = await db.get_user(user_id)

        if amount.lower() == "all":
            coins = row["wallet"]
        else:
            if not amount.isdigit():
                return await ctx.send(embed=error_embed("Amount must be a number or `all`."))
            coins = int(amount)

        if coins <= 0:
            return await ctx.send(embed=error_embed("You have nothing to deposit."))

        if coins > row["wallet"]:
            return await ctx.send(
                embed=error_embed(f"You only have {fmt(row['wallet'])} in your wallet."),
            )

        await db.execute(
            "UPDATE users SET wallet = wallet - ?, bank = bank + ? WHERE user_id = ?",
            (coins, coins, user_id),
        )

        row = await db.get_user(user_id)
        embed = success_embed(
            "🏦  Deposit Successful",
            f"Deposited **{fmt(coins)}** into your bank.\n\n"
            f"Wallet: {fmt(row['wallet'])}  |  Bank: {fmt(row['bank'])}",
        )
        await ctx.send(embed=embed)

    # ── .withdraw ──────────────────────────────────────────────────────────────

    @commands.command(name="withdraw", aliases=["with"], help="Withdraw coins from bank to wallet.")
    async def withdraw(self, ctx: commands.Context, amount: str = None):
        if amount is None:
            return await ctx.send(embed=error_embed("Usage: `.withdraw <amount|all>`"))

        user_id = ctx.author.id
        row = await db.get_user(user_id)

        if amount.lower() == "all":
            coins = row["bank"]
        else:
            if not amount.isdigit():
                return await ctx.send(embed=error_embed("Amount must be a number or `all`."))
            coins = int(amount)

        if coins <= 0:
            return await ctx.send(embed=error_embed("You have nothing to withdraw."))

        if coins > row["bank"]:
            return await ctx.send(
                embed=error_embed(f"You only have {fmt(row['bank'])} in your bank."),
            )

        await db.execute(
            "UPDATE users SET bank = bank - ?, wallet = wallet + ? WHERE user_id = ?",
            (coins, coins, user_id),
        )

        row = await db.get_user(user_id)
        embed = success_embed(
            "👛  Withdrawal Successful",
            f"Withdrew **{fmt(coins)}** to your wallet.\n\n"
            f"Wallet: {fmt(row['wallet'])}  |  Bank: {fmt(row['bank'])}",
        )
        await ctx.send(embed=embed)

    # ── .pay ───────────────────────────────────────────────────────────────────

    @commands.command(name="pay", help="Pay another user from your wallet.")
    async def pay(self, ctx: commands.Context, recipient: discord.Member = None, amount: int = None):
        if recipient is None or amount is None:
            return await ctx.send(embed=error_embed("Usage: `.pay <@user> <amount>`"))

        sender_id    = ctx.author.id
        recipient_id = recipient.id

        if recipient_id == sender_id:
            return await ctx.send(embed=error_embed("You can't pay yourself."))

        if recipient.bot:
            return await ctx.send(embed=error_embed("You can't pay a bot."))

        if amount < 1:
            return await ctx.send(embed=error_embed("Amount must be at least 1."))

        sender_row = await db.get_user(sender_id)
        if amount > sender_row["wallet"]:
            return await ctx.send(
                embed=error_embed(
                    f"You only have {fmt(sender_row['wallet'])} in your wallet."
                ),
            )

        await db.add_wallet(sender_id,    -amount, reason=f"paid {recipient_id}")
        await db.add_wallet(recipient_id,  amount, reason=f"received from {sender_id}")

        embed = success_embed(
            "💸  Payment Sent",
            f"{ctx.author.mention} paid {recipient.mention} **{fmt(amount)}**!",
        )
        await ctx.send(embed=embed)


def setup(bot: commands.Bot) -> None:
    bot.add_cog(Economy(bot))
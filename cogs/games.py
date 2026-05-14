"""
cogs/games.py – Gambling commands and interactive Blackjack.

Commands: .coinflip, .slots, .dice, .blackjack
"""

from __future__ import annotations

import asyncio
import random
from typing import Optional

import discord
from discord.ext import commands

import config
from database import db
from utils.economy_utils import fmt, error_embed, validate_bet
from utils.cooldowns import is_on_cooldown, set_cooldown, get_remaining, format_remaining
from utils.blackjack import BlackjackGame, Outcome, cards_str

# Gambling cooldown in seconds (prevents spam)
GAMBLE_COOLDOWN = 5


# ── Slots helpers ──────────────────────────────────────────────────────────────

SLOT_EMOJIS = ["🍒", "🍋", "🍉", "⭐", "💎", "7️⃣"]

SLOT_PAYOUTS: dict[str, float] = {
    "💎": 10.0,
    "7️⃣": 7.0,
    "⭐": 4.0,
    "🍉": 3.0,
    "🍋": 2.0,
    "🍒": 1.5,
}


def _spin_slots() -> tuple[list[str], float]:
    """Spin 3 reels. Returns (reels, multiplier) where multiplier=0 means loss."""
    reels = [random.choice(SLOT_EMOJIS) for _ in range(3)]
    if reels[0] == reels[1] == reels[2]:
        return reels, SLOT_PAYOUTS.get(reels[0], 1.5)
    return reels, 0.0


# ── Blackjack buttons ──────────────────────────────────────────────────────────

class BlackjackView(discord.ui.View):
    """
    Discord View that holds Hit / Stand / Double buttons for a blackjack game.

    Only the original player can interact. Buttons are disabled after the
    game ends or on timeout.
    """

    def __init__(self, game: BlackjackGame, player: discord.Member, wallet: int):
        super().__init__(timeout=60)
        self.game      = game
        self.player    = player
        self.wallet    = wallet
        self.message: Optional[discord.Message] = None
        self._ended    = False

    # ── Guard ──────────────────────────────────────────────────────────────────

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.player.id:
            await interaction.response.send_message(
                "This is not your game!", ephemeral=True
            )
            return False
        return True

    async def on_timeout(self) -> None:
        """Stand automatically when the player doesn't respond in time."""
        if not self._ended and self.message:
            self._ended = True
            self._disable_all()
            outcome, delta = self.game.resolve()
            await db.add_wallet(self.player.id, delta, reason="blackjack timeout-stand")
            embed = _bj_embed(self.game, outcome, delta, timed_out=True)
            await self.message.edit(embed=embed, view=self)

    def _disable_all(self) -> None:
        for child in self.children:
            child.disabled = True  # type: ignore[attr-defined]

    # ── Hit ────────────────────────────────────────────────────────────────────

    @discord.ui.button(label="Hit", style=discord.ButtonStyle.primary, emoji="🃏")
    async def hit_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        self.game.hit()

        if self.game.player_busted:
            self._ended = True
            self._disable_all()
            await db.add_wallet(self.player.id, -self.game.bet, reason="blackjack bust")
            embed = _bj_embed(self.game, Outcome.BUST, -self.game.bet)
            await interaction.response.edit_message(embed=embed, view=self)
            self.stop()
        else:
            embed = _bj_embed_playing(self.game)
            await interaction.response.edit_message(embed=embed, view=self)

    # ── Stand ──────────────────────────────────────────────────────────────────

    @discord.ui.button(label="Stand", style=discord.ButtonStyle.secondary, emoji="✋")
    async def stand_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        self._ended = True
        self._disable_all()
        outcome, delta = self.game.resolve()
        await db.add_wallet(self.player.id, delta, reason=f"blackjack {outcome.name.lower()}")
        embed = _bj_embed(self.game, outcome, delta)
        await interaction.response.edit_message(embed=embed, view=self)
        self.stop()

    # ── Double ─────────────────────────────────────────────────────────────────

    @discord.ui.button(label="Double", style=discord.ButtonStyle.danger, emoji="💥")
    async def double_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        if len(self.game.player_cards) != 2:
            await interaction.response.send_message(
                "You can only double on your first two cards!", ephemeral=True
            )
            return

        row = await db.get_user(self.player.id)
        extra = min(self.game.bet, row["wallet"])
        if extra <= 0:
            await interaction.response.send_message(
                "Not enough coins to double!", ephemeral=True
            )
            return

        await db.add_wallet(self.player.id, -extra, reason="blackjack double extra bet")
        self.game.double_down(extra)

        self._ended = True
        self._disable_all()
        outcome, delta = self.game.resolve()
        await db.add_wallet(self.player.id, delta, reason=f"blackjack double {outcome.name.lower()}")
        embed = _bj_embed(self.game, outcome, delta, doubled=True)
        await interaction.response.edit_message(embed=embed, view=self)
        self.stop()


# ── Blackjack embed builders ───────────────────────────────────────────────────

def _bj_embed_playing(game: BlackjackGame) -> discord.Embed:
    embed = discord.Embed(title="🃏  Blackjack", color=config.COLOR_INFO)
    embed.add_field(
        name=f"Your hand  ({game.player_total})",
        value=cards_str(game.player_cards),
        inline=False,
    )
    embed.add_field(
        name="Dealer's hand  (?)",
        value=f"{game.dealer_cards[0]}  🂠",
        inline=False,
    )
    embed.set_footer(text=f"Bet: {fmt(game.bet)}")
    return embed


def _bj_embed(
    game: BlackjackGame,
    outcome: Outcome,
    delta: int,
    doubled: bool = False,
    timed_out: bool = False,
) -> discord.Embed:
    labels = {
        Outcome.PLAYER_WIN: ("✅  You Win!", config.COLOR_SUCCESS),
        Outcome.DEALER_WIN: ("❌  Dealer Wins!", config.COLOR_ERROR),
        Outcome.PUSH:       ("🤝  Push!", config.COLOR_INFO),
        Outcome.BLACKJACK:  ("🎉  BLACKJACK!", config.COLOR_GOLD),
        Outcome.BUST:       ("💥  You Bust!", config.COLOR_ERROR),
    }
    title, color = labels[outcome]
    if timed_out:
        title = f"⏰  Timed Out – {title}"

    embed = discord.Embed(title=title, color=color)
    embed.add_field(
        name=f"Your hand  ({game.player_total})",
        value=cards_str(game.player_cards),
        inline=False,
    )
    embed.add_field(
        name=f"Dealer's hand  ({game.dealer_total})",
        value=cards_str(game.dealer_cards),
        inline=False,
    )
    sign   = "+" if delta >= 0 else ""
    extra  = "  (Doubled)" if doubled else ""
    embed.add_field(
        name="Result",
        value=f"**{sign}{fmt(delta)}**{extra}",
        inline=False,
    )
    return embed


# ── Cog ────────────────────────────────────────────────────────────────────────

class Games(commands.Cog):
    """Gambling and interactive game commands."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    def _check_gamble_cooldown(self, user_id: int) -> Optional[str]:
        if is_on_cooldown(user_id, "gamble"):
            remaining = get_remaining(user_id, "gamble")
            return f"Slow down! Wait **{format_remaining(remaining)}** before gambling again."
        return None

    # ── .coinflip ──────────────────────────────────────────────────────────────

    @commands.command(name="coinflip", aliases=["cf"], help="Flip a coin and bet on the outcome. Usage: .coinflip <amount> <heads|tails>")
    async def coinflip(self, ctx: commands.Context, amount: int = None, side: str = None):
        if amount is None or side is None or side.lower() not in ("heads", "tails"):
            return await ctx.send(embed=error_embed("Usage: `.coinflip <amount> <heads|tails>`"))

        side = side.lower()
        user_id = ctx.author.id
        if msg := self._check_gamble_cooldown(user_id):
            return await ctx.send(embed=error_embed(msg))

        row = await db.get_user(user_id)
        if not await validate_bet(ctx, amount, row["wallet"]):
            return

        result = random.choice(["heads", "tails"])
        won    = result == side
        coin_emoji = "🟡" if result == "heads" else "⚫"

        if won:
            await db.add_wallet(user_id, amount, reason="coinflip win")
            embed = discord.Embed(
                title=f"{coin_emoji}  {result.capitalize()} — You Win!",
                description=f"**+{fmt(amount)}** added to your wallet.",
                color=config.COLOR_SUCCESS,
            )
        else:
            await db.add_wallet(user_id, -amount, reason="coinflip loss")
            embed = discord.Embed(
                title=f"{coin_emoji}  {result.capitalize()} — You Lose!",
                description=f"**-{fmt(amount)}** removed from your wallet.",
                color=config.COLOR_ERROR,
            )

        embed.set_footer(text=f"You bet: {side.capitalize()}  |  Result: {result.capitalize()}")
        set_cooldown(user_id, "gamble", GAMBLE_COOLDOWN)
        await db.add_xp(user_id, config.XP_PER_COMMAND)
        await ctx.send(embed=embed)

    # ── .slots ─────────────────────────────────────────────────────────────────

    @commands.command(name="slots", help="Spin the slot machine! Usage: .slots <amount>")
    async def slots(self, ctx: commands.Context, amount: int = None):
        if amount is None:
            return await ctx.send(embed=error_embed("Usage: `.slots <amount>`"))

        user_id = ctx.author.id
        if msg := self._check_gamble_cooldown(user_id):
            return await ctx.send(embed=error_embed(msg))

        row = await db.get_user(user_id)
        if not await validate_bet(ctx, amount, row["wallet"]):
            return

        reels, multiplier = _spin_slots()
        reel_display = " | ".join(reels)

        if multiplier > 0:
            winnings = int(amount * multiplier) - amount
            await db.add_wallet(user_id, winnings, reason="slots win")
            embed = discord.Embed(
                title=f"🎰  [ {reel_display} ]",
                description=(
                    f"**JACKPOT!** {reels[0]} × {multiplier}x\n"
                    f"**+{fmt(winnings)}** net winnings!"
                ),
                color=config.COLOR_GOLD,
            )
        else:
            await db.add_wallet(user_id, -amount, reason="slots loss")
            embed = discord.Embed(
                title=f"🎰  [ {reel_display} ]",
                description=f"No match. **-{fmt(amount)}** lost.",
                color=config.COLOR_ERROR,
            )

        embed.set_footer(text=f"Bet: {fmt(amount)}")
        set_cooldown(user_id, "gamble", GAMBLE_COOLDOWN)
        await db.add_xp(user_id, config.XP_PER_COMMAND)
        await ctx.send(embed=embed)

    # ── .dice ──────────────────────────────────────────────────────────────────

    @commands.command(name="dice", aliases=["dc"], help="Roll a dice against the bot. Usage: .dice <amount>")
    async def dice(self, ctx: commands.Context, amount: int = None):
        if amount is None:
            return await ctx.send(embed=error_embed("Usage: `.dice <amount>`"))

        user_id = ctx.author.id
        if msg := self._check_gamble_cooldown(user_id):
            return await ctx.send(embed=error_embed(msg))

        row = await db.get_user(user_id)
        if not await validate_bet(ctx, amount, row["wallet"]):
            return

        player_roll = random.randint(1, 6)
        bot_roll    = random.randint(1, 6)

        if player_roll > bot_roll:
            await db.add_wallet(user_id, amount, reason="dice win")
            color, result_text = config.COLOR_SUCCESS, f"**You win! +{fmt(amount)}**"
        elif player_roll < bot_roll:
            await db.add_wallet(user_id, -amount, reason="dice loss")
            color, result_text = config.COLOR_ERROR, f"**You lose! -{fmt(amount)}**"
        else:
            color, result_text = config.COLOR_INFO, "**Tie! No coins exchanged.**"

        embed = discord.Embed(title="🎲  Dice Roll", color=color)
        embed.add_field(name=f"You: {player_roll}", value="🎲", inline=True)
        embed.add_field(name=f"Bot: {bot_roll}",    value="🎲", inline=True)
        embed.add_field(name="Result", value=result_text, inline=False)

        set_cooldown(user_id, "gamble", GAMBLE_COOLDOWN)
        await db.add_xp(user_id, config.XP_PER_COMMAND)
        await ctx.send(embed=embed)

    # ── .blackjack ─────────────────────────────────────────────────────────────

    @commands.command(name="blackjack", aliases=["bj"], help="Play interactive Blackjack! Usage: .blackjack <amount>")
    async def blackjack(self, ctx: commands.Context, amount: int = None):
        if amount is None:
            return await ctx.send(embed=error_embed("Usage: `.blackjack <amount>`"))

        user_id = ctx.author.id
        if msg := self._check_gamble_cooldown(user_id):
            return await ctx.send(embed=error_embed(msg))

        row = await db.get_user(user_id)
        if not await validate_bet(ctx, amount, row["wallet"]):
            return

        await db.add_wallet(user_id, -amount, reason="blackjack bet placed")

        game = BlackjackGame(bet=amount)
        game.deal_initial()

        if game.is_natural_blackjack:
            payout = int(amount * 1.5)
            await db.add_wallet(user_id, amount + payout, reason="blackjack natural")
            embed = _bj_embed(game, Outcome.BLACKJACK, payout)
            return await ctx.send(embed=embed)

        view = BlackjackView(game=game, player=ctx.author, wallet=row["wallet"] - amount)
        embed = _bj_embed_playing(game)

        msg = await ctx.send(embed=embed, view=view)
        view.message = msg

        set_cooldown(user_id, "gamble", GAMBLE_COOLDOWN)


def setup(bot: commands.Bot) -> None:
    bot.add_cog(Games(bot))
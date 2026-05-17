"""
cogs/games.py – Gambling commands, interactive Blackjack, and Horse Racing.

Changes:
  - BJ: Double button removed; Push bug fixed (no money lost on draw)
  - BJ: 2-second reveal for coinflip result
  - Restyled embeds matching reference screenshots
  - Horse race shows horse names and owner before race starts
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

from datetime import datetime, timezone

GAMBLE_COOLDOWN  = 5
RACE_BUY_IN      = 500
RACE_JOIN_TIME   = 30
RACE_MIN_PLAYERS = 2
RACE_MAX_PLAYERS = 6
RACE_TRACK_LEN   = 20

HORSE_NAMES = [
    ("🐴", "Dusty Hooves"),
    ("🦄", "Sparkle Sprint"),
    ("🐎", "Iron Thunder"),
    ("🏇", "Lucky Stride"),
    ("🦓", "Zigzag Blaze"),
    ("🐴", "Midnight Runner"),
]

DRAMATIC_EVENTS = [
    "{horse} trips on a pebble! 😱",
    "{horse} gets a second wind! 💨",
    "{horse} is overtaken — wait, they're surging back! 😤",
    "{horse} winks at the crowd! 😎",
    "{horse} spots a carrot at the finish line! 🥕",
    "{horse} slips on a banana peel! 🍌",
    "{horse} steals the lead! 🔥",
    "{horse} is looking TIRED… 😮‍💨",
]


# ── Bet parsing ────────────────────────────────────────────────────────────────

def parse_bet(raw: str, wallet: int) -> Optional[int]:
    raw = raw.lower().strip()
    if raw == "all":
        return wallet
    if raw == "half":
        return max(1, wallet // 2)
    multipliers = {"k": 1_000, "m": 1_000_000, "b": 1_000_000_000}
    for suffix, mult in multipliers.items():
        if raw.endswith(suffix):
            try:
                return int(float(raw[:-1]) * mult)
            except ValueError:
                return None
    try:
        val = int(raw)
        return val if val > 0 else None
    except ValueError:
        return None


def parse_cf_args(args: tuple[str, ...]) -> tuple[Optional[str], Optional[str]]:
    SIDE_MAP = {"h": "heads", "t": "tails", "heads": "heads", "tails": "tails"}
    amount_str = None
    side       = None
    for arg in args:
        if arg.lower() in SIDE_MAP:
            side = SIDE_MAP[arg.lower()]
        elif amount_str is None:
            amount_str = arg
    return amount_str, side


# ── Slots helpers ──────────────────────────────────────────────────────────────

SLOT_EMOJIS   = ["🍒", "🍋", "🍉", "⭐", "💎", "7️⃣"]
SLOT_PAYOUTS  = {"💎": 10.0, "7️⃣": 7.0, "⭐": 4.0, "🍉": 3.0, "🍋": 2.0, "🍒": 1.5}


def _spin_slots() -> tuple[list[str], float]:
    reels = [random.choice(SLOT_EMOJIS) for _ in range(3)]
    if reels[0] == reels[1] == reels[2]:
        return reels, SLOT_PAYOUTS.get(reels[0], 1.5)
    return reels, 0.0


# ── Blackjack card display ─────────────────────────────────────────────────────

# Unicode playing card characters (U+1F0A0 block)
_SUIT_BASE = {"♠": 0x1F0A0, "♥": 0x1F0B0, "♦": 0x1F0C0, "♣": 0x1F0D0}
_RANK_OFFSET = {
    "A": 1, "2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "7": 7,
    "8": 8, "9": 9, "10": 10, "J": 11, "Q": 13, "K": 14,
}

def _card_str(card) -> str:
    """Render a card as its Unicode playing card character e.g. 🂡 🃊"""
    cp = _SUIT_BASE[card.suit] + _RANK_OFFSET[card.rank]
    return chr(cp)

def _hand_str(cards) -> str:
    return " ".join(_card_str(c) for c in cards)

def _hidden_hand_str(cards) -> str:
    """Show first card + face-down card (🂠) for dealer during play."""
    return f"{_card_str(cards[0])} 🂠"


# ── Blackjack embed builders ───────────────────────────────────────────────────

def _bj_embed_playing(game: BlackjackGame) -> discord.Embed:
    embed = discord.Embed(title="🃏  Blackjack", color=config.COLOR_INFO)
    embed.add_field(
        name="​",
        value=f"🤖 Dealer: {_hidden_hand_str(game.dealer_cards)} = ?\n👤 You: {_hand_str(game.player_cards)} = {game.player_total}",
        inline=False,
    )
    embed.set_footer(text=f"Bet: {fmt(game.bet)}  •  Hit or Stand?")
    return embed


def _bj_embed(game: BlackjackGame, outcome: Outcome, delta: int, timed_out: bool = False) -> discord.Embed:
    result_labels = {
        Outcome.PLAYER_WIN: ("🎉 YOU WON",    config.COLOR_SUCCESS),
        Outcome.DEALER_WIN: ("💀 You Lost",   config.COLOR_ERROR),
        Outcome.PUSH:       ("🤝 Push — Tie", config.COLOR_INFO),
        Outcome.BLACKJACK:  ("🎉 BLACKJACK!", config.COLOR_GOLD),
        Outcome.BUST:       ("💀 You Lost",   config.COLOR_ERROR),
    }
    earned_labels = {
        Outcome.PLAYER_WIN: "💰 Earned",
        Outcome.DEALER_WIN: "💸 Lost",
        Outcome.PUSH:       "💰 Earned",
        Outcome.BLACKJACK:  "💰 Earned",
        Outcome.BUST:       "💸 Lost",
    }
    result_label, color = result_labels[outcome]
    earned_label = earned_labels[outcome]
    if timed_out:
        result_label = "⏰ Timed Out"

    # Bust / dealer win shows card total; bust gets a marker appended
    bust_marker = "  · 💥 BUST!" if outcome == Outcome.BUST else ""
    you_line    = f"{_hand_str(game.player_cards)}  =  {game.player_total}{bust_marker}"
    dealer_line = f"{_hand_str(game.dealer_cards)}  =  {game.dealer_total}"

    embed = discord.Embed(title="🃏  Blackjack", color=color)
    embed.add_field(
        name="​",
        value=f"🤖 Dealer: {dealer_line}\n👤 You: {you_line}",
        inline=False,
    )
    embed.add_field(name="━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", value="\u200b", inline=False)

    sign = "+" if delta > 0 else ""
    earned_str = f"{sign}{fmt(delta)}" if delta != 0 else "—"
    embed.add_field(name="📊 Result",   value=result_label, inline=True)
    embed.add_field(name=earned_label,  value=earned_str,   inline=True)
    embed.set_footer(text=f"Bet: {fmt(game.bet)}")
    return embed


# ── Blackjack View (Hit / Stand only) ─────────────────────────────────────────

class BlackjackView(discord.ui.View):
    def __init__(self, game: BlackjackGame, player: discord.Member):
        super().__init__(timeout=60)
        self.game    = game
        self.player  = player
        self.message: Optional[discord.Message] = None
        self._ended  = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.player.id:
            await interaction.response.send_message("This is not your game!", ephemeral=True)
            return False
        return True

    async def on_timeout(self) -> None:
        if not self._ended and self.message:
            self._ended = True
            self._disable_all()
            outcome, delta = self.game.resolve()
            payout = self.game.bet + delta
            if payout > 0:
                await db.add_wallet(self.player.id, payout, reason="blackjack timeout stand")
            row   = await db.get_user(self.player.id)
            embed = _bj_embed(self.game, outcome, delta, timed_out=True)
            embed.add_field(name="💳 Balance", value=fmt(row["wallet"]), inline=True)
            await self.message.edit(embed=embed, view=self)

    def _disable_all(self) -> None:
        for child in self.children:
            child.disabled = True

    @discord.ui.button(label="Hit", style=discord.ButtonStyle.primary, emoji="🃏")
    async def hit_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        self.game.hit()
        if self.game.player_busted:
            self._ended = True
            self._disable_all()
            # Bet was already deducted when the game started; bust = keep nothing, add nothing
            await db.add_xp(self.player.id, config.XP_PER_COMMAND)
            row   = await db.get_user(self.player.id)
            embed = _bj_embed(self.game, Outcome.BUST, -self.game.bet)
            embed.add_field(name="💳 Balance", value=fmt(row["wallet"]), inline=True)
            await interaction.response.edit_message(embed=embed, view=self)
            self.stop()
        else:
            embed = _bj_embed_playing(self.game)
            await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Stand", style=discord.ButtonStyle.secondary, emoji="✋")
    async def stand_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        self._ended = True
        self._disable_all()
        outcome, delta = self.game.resolve()
        # Bet was deducted upfront. payout = stake_back + profit:
        #   Win:  bet + bet  = 2× bet credited back
        #   Push: bet + 0    = stake returned
        #   Loss: bet + -bet = 0 (nothing credited, already gone)
        payout = self.game.bet + delta
        if payout > 0:
            await db.add_wallet(self.player.id, payout, reason=f"blackjack {outcome.name.lower()}")
        await db.add_xp(self.player.id, config.XP_PER_COMMAND)
        row   = await db.get_user(self.player.id)
        embed = _bj_embed(self.game, outcome, delta)
        embed.add_field(name="💳 Balance", value=fmt(row["wallet"]), inline=True)
        await interaction.response.edit_message(embed=embed, view=self)
        self.stop()


# ── Horse Race helpers ─────────────────────────────────────────────────────────

def _render_track(positions: dict[int, int], horses: list[tuple[str, str, int]]) -> str:
    lines = []
    for emoji, name, uid in horses:
        pos   = positions[uid]
        track = "─" * pos + emoji + "─" * (RACE_TRACK_LEN - pos) + "🏁"
        lines.append(f"`{track}` **{name}**")
    return "\n".join(lines)


# ── Horse Race join view ───────────────────────────────────────────────────────

class JoinRaceView(discord.ui.View):
    def __init__(self, host: discord.Member):
        super().__init__(timeout=RACE_JOIN_TIME)
        self.host    = host
        self.players: list[discord.Member] = [host]
        self.message: Optional[discord.Message] = None
        self.started = False

    @discord.ui.button(label="🏇  Join Race!", style=discord.ButtonStyle.success)
    async def join_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        member = interaction.user
        if member.id in [p.id for p in self.players]:
            return await interaction.response.send_message("You're already in!", ephemeral=True)
        if len(self.players) >= RACE_MAX_PLAYERS:
            return await interaction.response.send_message("Race is full!", ephemeral=True)
        row = await db.get_user(member.id)
        if row["wallet"] < RACE_BUY_IN:
            return await interaction.response.send_message(
                f"You need {fmt(RACE_BUY_IN)} in your wallet to join!", ephemeral=True
            )
        self.players.append(member)
        names = "\n".join(f"• **{p.display_name}**" for p in self.players)
        embed = self.message.embeds[0]
        embed.set_field_at(0, name="🏇 Riders",   value=names,                                  inline=True)
        embed.set_field_at(1, name="💰 Entry",     value=fmt(RACE_BUY_IN),                       inline=True)
        embed.set_field_at(2, name="🏆 Prize Pool",value=fmt(RACE_BUY_IN * len(self.players)),   inline=True)
        await interaction.response.edit_message(embed=embed, view=self)

    async def on_timeout(self):
        if not self.started and self.message:
            for child in self.children:
                child.disabled = True
            await self.message.edit(view=self)


# ── Cog ────────────────────────────────────────────────────────────────────────

class Games(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot          = bot
        self._active_races: set[int] = set()

    def _check_gamble_cooldown(self, user_id: int) -> Optional[str]:
        if is_on_cooldown(user_id, "gamble"):
            remaining = get_remaining(user_id, "gamble")
            return f"Slow down! Wait **{format_remaining(remaining)}** before gambling again."
        return None

    async def _check_jail(self, user_id: int) -> Optional[str]:
        row = await db.get_user(user_id)
        if not row["jail_until"]:
            return None
        jail_until = datetime.fromisoformat(row["jail_until"]).replace(tzinfo=timezone.utc)
        if datetime.now(tz=timezone.utc) >= jail_until:
            await db.set_jail_until(user_id, None)
            return None
        remaining = (jail_until - datetime.now(tz=timezone.utc)).total_seconds()
        return format_remaining(remaining)

    # ── .coinflip ──────────────────────────────────────────────────────────────

    @commands.command(name="coinflip", aliases=["cf"])
    async def coinflip(self, ctx: commands.Context, *args: str):
        if len(args) < 2:
            return await ctx.send(embed=error_embed(
                "Usage: `.cf <amount|half|all> <h|t|heads|tails>`\n"
                "Example: `.cf 500 h` | `.cf half tails` | `.cf all t`"
            ))

        amount_str, side = parse_cf_args(args)
        if side is None:
            return await ctx.send(embed=error_embed("Pick a side: `h`/`heads` or `t`/`tails`."))
        if amount_str is None:
            return await ctx.send(embed=error_embed("Provide a bet amount."))

        user_id = ctx.author.id
        if msg := self._check_gamble_cooldown(user_id):
            return await ctx.send(embed=error_embed(msg))

        row    = await db.get_user(user_id)
        amount = parse_bet(amount_str, row["wallet"])
        if amount is None:
            return await ctx.send(embed=error_embed("Invalid amount."))
        if not await validate_bet(ctx, amount, row["wallet"]):
            return

        # ── 2-second suspense reveal ───────────────────────────────────────────
        suspense = discord.Embed(
            title="🪙  Flipping…",
            description=f"You chose: **{side.capitalize()}**\n🔄 The coin is in the air…",
            color=config.COLOR_INFO,
        )
        suspense.add_field(name="💵 Bet", value=fmt(amount), inline=True)
        msg_obj = await ctx.send(embed=suspense)
        await asyncio.sleep(2)

        result = random.choice(["heads", "tails"])
        won    = result == side
        coin_emoji = "🟡" if result == "heads" else "⚫"

        if won:
            await db.add_wallet(user_id, amount, reason="coinflip win")
            row = await db.get_user(user_id)
            embed = discord.Embed(
                title=f"{coin_emoji}  Coinflip",
                color=config.COLOR_SUCCESS,
            )
        else:
            await db.add_wallet(user_id, -amount, reason="coinflip loss")
            row = await db.get_user(user_id)
            embed = discord.Embed(
                title=f"{coin_emoji}  Coinflip",
                color=config.COLOR_ERROR,
            )

        embed.description = (
            f"🎰 🎰 🎰\n\n"
            f"The coin landed on **{result.upper()}!**\n"
            f"*You chose: {side.capitalize()}*"
        )
        embed.add_field(name="━━━━━━━━━━━━━━━━━━", value="\u200b", inline=False)
        embed.add_field(name="📊 Result", value="🎉 You Won"  if won else "💀 You Lost", inline=True)
        embed.add_field(name="💵 " + ("Earned" if won else "Lost"), value=("+" if won else "-") + fmt(amount), inline=True)
        embed.add_field(name="💳 Balance", value=fmt(row["wallet"]), inline=True)
        embed.set_thumbnail(url=ctx.author.display_avatar.url)

        set_cooldown(user_id, "gamble", GAMBLE_COOLDOWN)
        await db.add_xp(user_id, config.XP_PER_COMMAND)
        await msg_obj.edit(embed=embed)

    # ── .slots ─────────────────────────────────────────────────────────────────

    @commands.command(name="slots")
    async def slots(self, ctx: commands.Context, amount: str = None):
        if amount is None:
            return await ctx.send(embed=error_embed("Usage: `.slots <amount|half|all>`"))
        user_id = ctx.author.id
        if msg := self._check_gamble_cooldown(user_id):
            return await ctx.send(embed=error_embed(msg))
        row    = await db.get_user(user_id)
        parsed = parse_bet(amount, row["wallet"])
        if parsed is None:
            return await ctx.send(embed=error_embed("Invalid amount."))
        if not await validate_bet(ctx, parsed, row["wallet"]):
            return

        reels, multiplier = _spin_slots()
        reel_display = " | ".join(reels)

        if multiplier > 0:
            winnings = int(parsed * multiplier) - parsed
            await db.add_wallet(user_id, winnings, reason="slots win")
            row = await db.get_user(user_id)
            embed = discord.Embed(
                title=f"🎰  [ {reel_display} ]",
                description=f"**JACKPOT!** {reels[0]} × {multiplier}x",
                color=config.COLOR_GOLD,
            )
            embed.add_field(name="📊 Result",  value="🎉 You Won",      inline=True)
            embed.add_field(name="💵 Earned",  value=f"+{fmt(winnings)}", inline=True)
            embed.add_field(name="💳 Balance", value=fmt(row["wallet"]),  inline=True)
        else:
            await db.add_wallet(user_id, -parsed, reason="slots loss")
            row = await db.get_user(user_id)
            embed = discord.Embed(
                title=f"🎰  [ {reel_display} ]",
                description="No match!",
                color=config.COLOR_ERROR,
            )
            embed.add_field(name="📊 Result",  value="💀 You Lost",      inline=True)
            embed.add_field(name="💵 Lost",    value=f"-{fmt(parsed)}",   inline=True)
            embed.add_field(name="💳 Balance", value=fmt(row["wallet"]),  inline=True)

        embed.set_footer(text=f"Bet: {fmt(parsed)}")
        set_cooldown(user_id, "gamble", GAMBLE_COOLDOWN)
        await db.add_xp(user_id, config.XP_PER_COMMAND)
        await ctx.send(embed=embed)

    # ── .dice ──────────────────────────────────────────────────────────────────

    @commands.command(name="dice", aliases=["dc"])
    async def dice(self, ctx: commands.Context, amount: str = None):
        if amount is None:
            return await ctx.send(embed=error_embed("Usage: `.dice <amount|half|all>`"))
        user_id = ctx.author.id
        if msg := self._check_gamble_cooldown(user_id):
            return await ctx.send(embed=error_embed(msg))
        row    = await db.get_user(user_id)
        parsed = parse_bet(amount, row["wallet"])
        if parsed is None:
            return await ctx.send(embed=error_embed("Invalid amount."))
        if not await validate_bet(ctx, parsed, row["wallet"]):
            return

        player_roll = random.randint(1, 6)
        bot_roll    = random.randint(1, 6)

        if player_roll > bot_roll:
            await db.add_wallet(user_id, parsed, reason="dice win")
            row    = await db.get_user(user_id)
            color  = config.COLOR_SUCCESS
            result = f"🎉 You Won  +{fmt(parsed)}"
        elif player_roll < bot_roll:
            await db.add_wallet(user_id, -parsed, reason="dice loss")
            row    = await db.get_user(user_id)
            color  = config.COLOR_ERROR
            result = f"💀 You Lost  -{fmt(parsed)}"
        else:
            row    = await db.get_user(user_id)
            color  = config.COLOR_INFO
            result = "🤝 Tie!  No coins exchanged."

        embed = discord.Embed(title="🎲  Dice Roll", color=color)
        embed.add_field(name="🎲 You",    value=str(player_roll), inline=True)
        embed.add_field(name="🤖 Bot",    value=str(bot_roll),    inline=True)
        embed.add_field(name="📊 Result", value=result,           inline=False)
        embed.add_field(name="💳 Balance",value=fmt(row["wallet"]),inline=True)
        embed.set_footer(text=f"Bet: {fmt(parsed)}")
        set_cooldown(user_id, "gamble", GAMBLE_COOLDOWN)
        await db.add_xp(user_id, config.XP_PER_COMMAND)
        await ctx.send(embed=embed)

    # ── .blackjack ─────────────────────────────────────────────────────────────

    @commands.command(name="blackjack", aliases=["bj"])
    async def blackjack(self, ctx: commands.Context, amount: str = None):
        if amount is None:
            return await ctx.send(embed=error_embed("Usage: `.bj <amount|half|all>`"))

        user_id = ctx.author.id
        if msg := self._check_gamble_cooldown(user_id):
            return await ctx.send(embed=error_embed(msg))

        row    = await db.get_user(user_id)
        parsed = parse_bet(amount, row["wallet"])
        if parsed is None:
            return await ctx.send(embed=error_embed("Invalid amount."))
        if not await validate_bet(ctx, parsed, row["wallet"]):
            return

        # Bet is deducted AFTER the message sends — prevents coins vanishing on a crash

        game = BlackjackGame(bet=parsed)
        game.deal_initial()

        if game.is_natural_blackjack:
            # Natural blackjack (A + 10-value on deal) → 2.5x payout
            payout = int(parsed * 2.5)
            await db.add_wallet(user_id, -parsed, reason="blackjack bet placed")
            await db.add_wallet(user_id, parsed + payout, reason="blackjack natural")
            await db.add_xp(user_id, config.XP_PER_COMMAND)
            row   = await db.get_user(user_id)
            embed = _bj_embed(game, Outcome.BLACKJACK, payout)
            embed.add_field(name="💳 Balance", value=fmt(row["wallet"]), inline=True)
            return await ctx.send(embed=embed)

        view = BlackjackView(game=game, player=ctx.author)
        embed = _bj_embed_playing(game)
        msg   = await ctx.send(embed=embed, view=view)
        # Only deduct bet AFTER the message is sent — prevents losing coins on a crash
        await db.add_wallet(user_id, -parsed, reason="blackjack bet placed")
        view.message = msg
        set_cooldown(user_id, "gamble", GAMBLE_COOLDOWN)
        await db.add_xp(user_id, config.XP_PER_COMMAND)

    # ── .horserace ─────────────────────────────────────────────────────────────

    @commands.command(name="horserace", aliases=["race"])
    async def horserace(self, ctx: commands.Context):
        channel_id = ctx.channel.id
        if channel_id in self._active_races:
            return await ctx.send(embed=error_embed("A race is already running in this channel!"))

        host_row = await db.get_user(ctx.author.id)
        if host_row["wallet"] < RACE_BUY_IN:
            return await ctx.send(embed=error_embed(f"You need **{fmt(RACE_BUY_IN)}** to start a race!"))

        self._active_races.add(channel_id)
        view  = JoinRaceView(host=ctx.author)
        names = f"• **{ctx.author.display_name}**"

        embed = discord.Embed(
            title="🏇  Horse Race — Join Now!",
            description=(
                f"A race is starting! Entry fee: **{fmt(RACE_BUY_IN)}**.\n"
                f"Min {RACE_MIN_PLAYERS} · Max {RACE_MAX_PLAYERS} riders.\n"
                f"You have **{RACE_JOIN_TIME}s** to join. Winner takes **all**!"
            ),
            color=config.COLOR_GOLD,
        )
        embed.add_field(name="🏇 Riders",    value=names,             inline=True)
        embed.add_field(name="💰 Entry",      value=fmt(RACE_BUY_IN), inline=True)
        embed.add_field(name="🏆 Prize Pool", value=fmt(RACE_BUY_IN), inline=True)

        lobby_msg   = await ctx.send(embed=embed, view=view)
        view.message = lobby_msg

        await asyncio.sleep(RACE_JOIN_TIME)
        view.started = True
        for child in view.children:
            child.disabled = True
        await lobby_msg.edit(view=view)

        players = view.players
        if len(players) < RACE_MIN_PLAYERS:
            self._active_races.discard(channel_id)
            return await ctx.send(embed=error_embed("Not enough riders! Race cancelled."))

        # Collect entry fees
        valid_players = []
        for p in players:
            row = await db.get_user(p.id)
            if row["wallet"] >= RACE_BUY_IN:
                await db.add_wallet(p.id, -RACE_BUY_IN, reason="horse race entry fee")
                valid_players.append(p)
            else:
                await ctx.send(embed=error_embed(f"{p.mention} doesn't have enough and was removed."))

        if len(valid_players) < RACE_MIN_PLAYERS:
            for p in valid_players:
                await db.add_wallet(p.id, RACE_BUY_IN, reason="horse race refund")
            self._active_races.discard(channel_id)
            return await ctx.send(embed=error_embed("Not enough valid riders. Race cancelled, fees refunded."))

        prize_pool     = RACE_BUY_IN * len(valid_players)
        shuffled       = random.sample(HORSE_NAMES, min(len(valid_players), len(HORSE_NAMES)))
        horses         = [(emoji, name, p.id) for (emoji, name), p in zip(shuffled, valid_players)]
        name_map       = {p.id: p.display_name for p in valid_players}
        horse_display  = {uid: f"{emoji} {hname}" for emoji, hname, uid in horses}

        # ── Pre-race lineup ────────────────────────────────────────────────────
        lineup_lines = [
            f"{horse_display[uid]}  →  **{name_map[uid]}**"
            for _, _, uid in horses
        ]
        lineup_embed = discord.Embed(
            title="🏇  Race Lineup",
            description="\n".join(lineup_lines),
            color=config.COLOR_GOLD,
        )
        lineup_embed.add_field(name="🏆 Prize Pool", value=fmt(prize_pool), inline=True)
        lineup_embed.set_footer(text="The race starts in 3 seconds…")
        await ctx.send(embed=lineup_embed)
        await asyncio.sleep(3)

        # ── Race ──────────────────────────────────────────────────────────────
        positions  = {uid: 0 for _, _, uid in horses}
        race_embed = discord.Embed(title="🏇  AND THEY'RE OFF!", color=config.COLOR_GOLD)
        race_embed.description = _render_track(positions, horses)
        race_embed.set_footer(text=f"Prize pool: {fmt(prize_pool)}")
        race_msg = await ctx.send(embed=race_embed)

        winner_id = None
        tick      = 0
        while winner_id is None:
            await asyncio.sleep(1.5)
            tick += 1
            for emoji, hname, uid in horses:
                positions[uid] = min(positions[uid] + random.randint(0, 3), RACE_TRACK_LEN)
            leaders = [uid for uid, pos in positions.items() if pos >= RACE_TRACK_LEN]
            if leaders:
                winner_id = random.choice(leaders)
            drama = ""
            if tick % 3 == 0 and winner_id is None:
                sub = random.choice([uid for _, _, uid in horses])
                drama = "\n\n💬 *" + random.choice(DRAMATIC_EVENTS).format(horse=horse_display[sub]) + "*"
            race_embed.description = _render_track(positions, horses) + drama
            if winner_id:
                race_embed.title = "🏁  FINISH LINE!"
            await race_msg.edit(embed=race_embed)

        await db.add_wallet(winner_id, prize_pool, reason="horse race winner payout")
        winner_name  = name_map[winner_id]
        winner_horse = horse_display[winner_id]

        result_embed = discord.Embed(
            title=f"🏆  {winner_horse} wins!",
            description=(
                f"**{winner_name}** takes home **{fmt(prize_pool)}**!\n\n"
                + "\n".join(
                    f"{'🥇' if uid == winner_id else '💀'}  {horse_display[uid]} — {name_map[uid]}"
                    for _, _, uid in horses
                )
            ),
            color=config.COLOR_GOLD,
        )
        await ctx.send(embed=result_embed)
        self._active_races.discard(channel_id)


def setup(bot: commands.Bot) -> None:
    bot.add_cog(Games(bot))
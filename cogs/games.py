"""
cogs/games.py – Gambling commands, interactive Blackjack, and Horse Racing.

Commands: .coinflip/.cf, .slots, .dice/.dc, .blackjack/.bj, .horserace/.hr

Changes:
  - All bet commands accept: <amount|half|all> (e.g. .cf half h, .bj all)
  - .coinflip accepts shorthand: h/t for heads/tails, and flexible arg order
    (.cf 100 h, .cf h 100, .cf 100 heads, .cf tails 500 — all valid)
  - .horserace: multiplayer race with fixed 500-coin entry, dramatic live updates
  - Wallet can never go negative (enforced before every deduction)
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

# Gambling cooldown in seconds (prevents spam)
GAMBLE_COOLDOWN = 5

# Horse race constants
RACE_BUY_IN    = 500        # fixed entry fee
RACE_JOIN_TIME = 30         # seconds to gather players
RACE_MIN_PLAYERS = 2
RACE_MAX_PLAYERS = 6

HORSE_NAMES = [
    ("🐴", "Dusty Hooves"),
    ("🦄", "Sparkle Sprint"),
    ("🐎", "Iron Thunder"),
    ("🏇", "Lucky Stride"),
    ("🦓", "Zigzag Blaze"),
    ("🐴", "Midnight Runner"),
]

RACE_TRACK_LEN = 20   # total track positions


# ── Bet parsing ────────────────────────────────────────────────────────────────

def parse_bet(raw: str, wallet: int) -> Optional[int]:
    """
    Parse a bet string into an integer coin amount.
    Accepts: 100, 1k, 1.5m, half, all
    Returns None if invalid or <= 0.
    """
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


def parse_cf_args(args: tuple[str, ...]) -> tuple[Optional[int], Optional[str], Optional[int]]:
    """
    Parse coinflip args in any order: amount side or side amount.
    Returns (raw_amount_str, side, wallet_placeholder).
    Side accepts: h, t, heads, tails.
    Returns (amount_str, side) or (None, None) on failure.
    """
    SIDE_MAP = {"h": "heads", "t": "tails", "heads": "heads", "tails": "tails"}
    amount_str = None
    side = None
    for arg in args:
        if arg.lower() in SIDE_MAP:
            side = SIDE_MAP[arg.lower()]
        elif amount_str is None:
            amount_str = arg
    return amount_str, side


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
    def __init__(self, game: BlackjackGame, player: discord.Member, wallet: int):
        super().__init__(timeout=60)
        self.game      = game
        self.player    = player
        self.wallet    = wallet
        self.message: Optional[discord.Message] = None
        self._ended    = False

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
            await db.add_wallet(self.player.id, delta, reason="blackjack timeout-stand")
            embed = _bj_embed(self.game, outcome, delta, timed_out=True)
            await self.message.edit(embed=embed, view=self)

    def _disable_all(self) -> None:
        for child in self.children:
            child.disabled = True  # type: ignore[attr-defined]

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

    @discord.ui.button(label="Stand", style=discord.ButtonStyle.secondary, emoji="✋")
    async def stand_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        self._ended = True
        self._disable_all()
        outcome, delta = self.game.resolve()
        await db.add_wallet(self.player.id, delta, reason=f"blackjack {outcome.name.lower()}")
        embed = _bj_embed(self.game, outcome, delta)
        await interaction.response.edit_message(embed=embed, view=self)
        self.stop()

    @discord.ui.button(label="Double", style=discord.ButtonStyle.danger, emoji="💥")
    async def double_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        if len(self.game.player_cards) != 2:
            await interaction.response.send_message("You can only double on your first two cards!", ephemeral=True)
            return
        row = await db.get_user(self.player.id)
        extra = min(self.game.bet, row["wallet"])
        if extra <= 0:
            await interaction.response.send_message("Not enough coins to double!", ephemeral=True)
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
    embed.add_field(name=f"Your hand  ({game.player_total})", value=cards_str(game.player_cards), inline=False)
    embed.add_field(name="Dealer's hand  (?)", value=f"{game.dealer_cards[0]}  🂠", inline=False)
    embed.set_footer(text=f"Bet: {fmt(game.bet)}")
    return embed


def _bj_embed(game, outcome, delta, doubled=False, timed_out=False) -> discord.Embed:
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
    embed.add_field(name=f"Your hand  ({game.player_total})", value=cards_str(game.player_cards), inline=False)
    embed.add_field(name=f"Dealer's hand  ({game.dealer_total})", value=cards_str(game.dealer_cards), inline=False)
    sign  = "+" if delta >= 0 else ""
    extra = "  (Doubled)" if doubled else ""
    embed.add_field(name="Result", value=f"**{sign}{fmt(delta)}**{extra}", inline=False)
    return embed


# ── Horse Race helpers ─────────────────────────────────────────────────────────

def _render_track(positions: dict[int, int], horses: list[tuple[str, str, int]]) -> str:
    """
    Build a text race track.
    horses: list of (emoji, name, user_id)
    positions: user_id -> track position (0-RACE_TRACK_LEN)
    """
    lines = []
    for emoji, name, uid in horses:
        pos = positions[uid]
        track = "─" * pos + emoji + "─" * (RACE_TRACK_LEN - pos) + "🏁"
        lines.append(f"`{track}` **{name}**")
    return "\n".join(lines)


DRAMATIC_EVENTS = [
    "{horse} trips on a pebble! 😱",
    "{horse} gets a second wind! 💨",
    "{horse} is overtaken — wait, they're surging back! 😤",
    "{horse} winks at the crowd! 😎",
    "{horse} spots a carrot at the finish line! 🥕",
    "{horse} slips on a banana peel! 🍌",
    "{horse} steals the lead!  🔥",
    "{horse} is looking TIRED… 😮‍💨",
]


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

        # Check wallet
        row = await db.get_user(member.id)
        if row["wallet"] < RACE_BUY_IN:
            return await interaction.response.send_message(
                f"You need {fmt(RACE_BUY_IN)} in your wallet to join!", ephemeral=True
            )

        self.players.append(member)
        names = ", ".join(f"**{p.display_name}**" for p in self.players)
        embed = self.message.embeds[0]
        embed.set_field_at(0, name="Riders", value=names, inline=False)
        embed.set_field_at(1, name="Entry", value=fmt(RACE_BUY_IN), inline=True)
        embed.set_field_at(2, name="Prize Pool", value=fmt(RACE_BUY_IN * len(self.players)), inline=True)
        await interaction.response.edit_message(embed=embed, view=self)

    async def on_timeout(self):
        if not self.started and self.message:
            for child in self.children:
                child.disabled = True
            await self.message.edit(view=self)


# ── Cog ────────────────────────────────────────────────────────────────────────

class Games(commands.Cog):
    """Gambling and interactive game commands."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._active_races: set[int] = set()  # channel IDs with active races

    def _check_gamble_cooldown(self, user_id: int) -> Optional[str]:
        if is_on_cooldown(user_id, "gamble"):
            remaining = get_remaining(user_id, "gamble")
            return f"Slow down! Wait **{format_remaining(remaining)}** before gambling again."
        return None

    async def _check_jail(self, user_id: int):
        row = await db.get_user(user_id)
        if not row["jail_until"]:
            return None
        jail_until = datetime.fromisoformat(
            row["jail_until"]
        ).replace(tzinfo=timezone.utc)
        # Jail expired
        if datetime.now(tz=timezone.utc) >= jail_until:
            await db.set_jail_until(
                user_id,
                None
            )
            return None
        remaining = (
            jail_until - datetime.now(tz=timezone.utc)
        ).total_seconds()
        return format_remaining(remaining)

    # ── .coinflip ──────────────────────────────────────────────────────────────
    # Accepts any order: .cf 100 h | .cf h 100 | .cf half tails | .cf all t

    @commands.command(name="coinflip", aliases=["cf"],
                      help="Flip a coin. Usage: .cf <amount|half|all> <h|t|heads|tails> (order flexible)")
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
            return await ctx.send(embed=error_embed("Provide a bet amount: e.g. `500`, `half`, `all`."))

        user_id = ctx.author.id
        if msg := self._check_gamble_cooldown(user_id):
            return await ctx.send(embed=error_embed(msg))

        row = await db.get_user(user_id)
        amount = parse_bet(amount_str, row["wallet"])
        if amount is None:
            return await ctx.send(embed=error_embed("Invalid amount. Try `500`, `1k`, `half`, or `all`."))
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

    @commands.command(name="slots", help="Spin the slot machine! Usage: .slots <amount|half|all>")
    async def slots(self, ctx: commands.Context, amount: str = None):
        if amount is None:
            return await ctx.send(embed=error_embed("Usage: `.slots <amount|half|all>`"))

        user_id = ctx.author.id
        if msg := self._check_gamble_cooldown(user_id):
            return await ctx.send(embed=error_embed(msg))

        row = await db.get_user(user_id)
        parsed = parse_bet(amount, row["wallet"])
        if parsed is None:
            return await ctx.send(embed=error_embed("Invalid amount. Try `500`, `1k`, `half`, or `all`."))
        if not await validate_bet(ctx, parsed, row["wallet"]):
            return

        reels, multiplier = _spin_slots()
        reel_display = " | ".join(reels)

        if multiplier > 0:
            winnings = int(parsed * multiplier) - parsed
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
            await db.add_wallet(user_id, -parsed, reason="slots loss")
            embed = discord.Embed(
                title=f"🎰  [ {reel_display} ]",
                description=f"No match. **-{fmt(parsed)}** lost.",
                color=config.COLOR_ERROR,
            )

        embed.set_footer(text=f"Bet: {fmt(parsed)}")
        set_cooldown(user_id, "gamble", GAMBLE_COOLDOWN)
        await db.add_xp(user_id, config.XP_PER_COMMAND)
        await ctx.send(embed=embed)

    # ── .dice ──────────────────────────────────────────────────────────────────

    @commands.command(name="dice", aliases=["dc"], help="Roll a dice vs the bot. Usage: .dice <amount|half|all>")
    async def dice(self, ctx: commands.Context, amount: str = None):
        if amount is None:
            return await ctx.send(embed=error_embed("Usage: `.dice <amount|half|all>`"))

        user_id = ctx.author.id
        if msg := self._check_gamble_cooldown(user_id):
            return await ctx.send(embed=error_embed(msg))

        row = await db.get_user(user_id)
        parsed = parse_bet(amount, row["wallet"])
        if parsed is None:
            return await ctx.send(embed=error_embed("Invalid amount. Try `500`, `1k`, `half`, or `all`."))
        if not await validate_bet(ctx, parsed, row["wallet"]):
            return

        player_roll = random.randint(1, 6)
        bot_roll    = random.randint(1, 6)

        if player_roll > bot_roll:
            await db.add_wallet(user_id, parsed, reason="dice win")
            color, result_text = config.COLOR_SUCCESS, f"**You win! +{fmt(parsed)}**"
        elif player_roll < bot_roll:
            await db.add_wallet(user_id, -parsed, reason="dice loss")
            color, result_text = config.COLOR_ERROR, f"**You lose! -{fmt(parsed)}**"
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

    @commands.command(name="blackjack", aliases=["bj"],
                      help="Play interactive Blackjack! Usage: .bj <amount|half|all>")
    async def blackjack(self, ctx: commands.Context, amount: str = None):
        if amount is None:
            return await ctx.send(embed=error_embed("Usage: `.blackjack <amount|half|all>`"))

        user_id = ctx.author.id
        if msg := self._check_gamble_cooldown(user_id):
            return await ctx.send(embed=error_embed(msg))

        row = await db.get_user(user_id)
        parsed = parse_bet(amount, row["wallet"])
        if parsed is None:
            return await ctx.send(embed=error_embed("Invalid amount. Try `500`, `1k`, `half`, or `all`."))
        if not await validate_bet(ctx, parsed, row["wallet"]):
            return

        await db.add_wallet(user_id, -parsed, reason="blackjack bet placed")

        game = BlackjackGame(bet=parsed)
        game.deal_initial()

        if game.is_natural_blackjack:
            payout = int(parsed * 1.5)
            await db.add_wallet(user_id, parsed + payout, reason="blackjack natural")
            embed = _bj_embed(game, Outcome.BLACKJACK, payout)
            return await ctx.send(embed=embed)

        view = BlackjackView(game=game, player=ctx.author, wallet=row["wallet"] - parsed)
        embed = _bj_embed_playing(game)

        msg = await ctx.send(embed=embed, view=view)
        view.message = msg

        set_cooldown(user_id, "gamble", GAMBLE_COOLDOWN)

    # ── .horserace ─────────────────────────────────────────────────────────────

    @commands.command(name="horserace", aliases=["race"],
                      help=f"Start a horse race! Fixed entry: {RACE_BUY_IN} coins. Winner takes all.")
    async def horserace(self, ctx: commands.Context):
        channel_id = ctx.channel.id
        if channel_id in self._active_races:
            return await ctx.send(embed=error_embed("A race is already running in this channel!"))

        # Check host wallet
        host_row = await db.get_user(ctx.author.id)
        if host_row["wallet"] < RACE_BUY_IN:
            return await ctx.send(embed=error_embed(
                f"You need **{fmt(RACE_BUY_IN)}** in your wallet to start a race!"
            ))

        self._active_races.add(channel_id)

        # ── Lobby ──────────────────────────────────────────────────────────────
        view = JoinRaceView(host=ctx.author)
        names = f"**{ctx.author.display_name}**"

        embed = discord.Embed(
            title="🏇  Horse Race — Join Now!",
            description=(
                f"A race is starting! Entry fee: **{fmt(RACE_BUY_IN)}**.\n"
                f"Minimum {RACE_MIN_PLAYERS} riders · Max {RACE_MAX_PLAYERS} riders.\n"
                f"You have **{RACE_JOIN_TIME}s** to join. Winner takes **all** the coins!"
            ),
            color=config.COLOR_GOLD,
        )
        embed.add_field(name="Riders",      value=names,              inline=False)
        embed.add_field(name="Entry",        value=fmt(RACE_BUY_IN),  inline=True)
        embed.add_field(name="Prize Pool",   value=fmt(RACE_BUY_IN),  inline=True)

        lobby_msg = await ctx.send(embed=embed, view=view)
        view.message = lobby_msg

        await asyncio.sleep(RACE_JOIN_TIME)
        view.started = True
        for child in view.children:
            child.disabled = True
        await lobby_msg.edit(view=view)

        players = view.players

        # ── Not enough riders ──────────────────────────────────────────────────
        if len(players) < RACE_MIN_PLAYERS:
            self._active_races.discard(channel_id)
            return await ctx.send(embed=error_embed(
                f"Not enough riders! Need at least {RACE_MIN_PLAYERS}. Race cancelled."
            ))

        # ── Collect entry fees (verify wallets again) ──────────────────────────
        valid_players = []
        for p in players:
            row = await db.get_user(p.id)
            if row["wallet"] >= RACE_BUY_IN:
                await db.add_wallet(p.id, -RACE_BUY_IN, reason="horse race entry fee")
                valid_players.append(p)
            else:
                await ctx.send(embed=error_embed(
                    f"{p.mention} doesn't have enough coins and was removed from the race."
                ))

        if len(valid_players) < RACE_MIN_PLAYERS:
            # Refund those who already paid
            for p in valid_players:
                await db.add_wallet(p.id, RACE_BUY_IN, reason="horse race refund")
            self._active_races.discard(channel_id)
            return await ctx.send(embed=error_embed("Not enough valid riders after wallet check. Race cancelled, entry fees refunded."))

        prize_pool = RACE_BUY_IN * len(valid_players)

        # Assign horses (pick unique horses for each player)
        shuffled_horses = random.sample(HORSE_NAMES, min(len(valid_players), len(HORSE_NAMES)))
        horses = [(emoji, name, p.id) for (emoji, name), p in zip(shuffled_horses, valid_players)]

        # Map player id → display_name
        name_map = {p.id: p.display_name for p in valid_players}
        # Map player id → horse display string
        horse_display = {uid: f"{emoji} {hname}" for emoji, hname, uid in horses}

        # ── Race! ──────────────────────────────────────────────────────────────
        positions = {uid: 0 for _, _, uid in horses}
        race_embed = discord.Embed(
            title="🏇  AND THEY'RE OFF!",
            color=config.COLOR_GOLD,
        )
        race_embed.description = _render_track(positions, horses)
        race_embed.set_footer(text=f"Prize pool: {fmt(prize_pool)}")
        race_msg = await ctx.send(embed=race_embed)

        winner_id = None
        tick = 0
        while winner_id is None:
            await asyncio.sleep(1.5)
            tick += 1

            # Advance horses by random steps
            for emoji, hname, uid in horses:
                step = random.randint(0, 3)
                positions[uid] = min(positions[uid] + step, RACE_TRACK_LEN)

            # Check for winner
            leaders = [uid for uid, pos in positions.items() if pos >= RACE_TRACK_LEN]
            if leaders:
                winner_id = random.choice(leaders)  # tie-break random

            # Dramatic event every ~3 ticks
            drama = ""
            if tick % 3 == 0 and winner_id is None:
                subject_uid = random.choice([uid for _, _, uid in horses])
                template = random.choice(DRAMATIC_EVENTS)
                drama = "\n\n💬 *" + template.format(horse=horse_display[subject_uid]) + "*"

            race_embed.description = _render_track(positions, horses) + drama
            if winner_id:
                race_embed.title = "🏁  FINISH LINE!"
            await race_msg.edit(embed=race_embed)

        # ── Payout ────────────────────────────────────────────────────────────
        await db.add_wallet(winner_id, prize_pool, reason="horse race winner payout")
        winner_name = name_map[winner_id]
        winner_horse = horse_display[winner_id]

        result_embed = discord.Embed(
            title=f"🏆  {winner_horse} wins the race!",
            description=(
                f"**{winner_name}** takes home the prize pool of **{fmt(prize_pool)}**!\n\n"
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
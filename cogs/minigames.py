"""
cogs/minigames.py – Chat-spawned minigames for active channels.

Minigames spawn automatically when the chat is active, or can be triggered
manually. First person to answer correctly wins coins.

Games:
  - 🚩 Guess the Flag   – name the country from the flag emoji
  - ➗ Math Challenge    – solve an arithmetic expression
  - 🔤 Unscramble Word  – unscramble a jumbled word
  - ❓ Trivia           – answer a general knowledge question

Auto-spawn: after every N messages in a channel (configurable).
Manual: .minigame / .mg to force-spawn one.

Config keys (add to config.py):
  MINIGAME_REWARD_MIN  = 100
  MINIGAME_REWARD_MAX  = 500
  MINIGAME_AUTO_EVERY  = 25    # spawn after this many messages in a channel
  MINIGAME_TIMEOUT     = 30    # seconds before question expires
"""

from __future__ import annotations

import asyncio
import operator
import random
import string
from typing import Optional

import discord
from discord.ext import commands

import config
from database import db
from utils.economy_utils import fmt, success_embed

# ── Constants ──────────────────────────────────────────────────────────────────

REWARD_MIN    = getattr(config, "MINIGAME_REWARD_MIN", 100)
REWARD_MAX    = getattr(config, "MINIGAME_REWARD_MAX", 500)
AUTO_EVERY    = getattr(config, "MINIGAME_AUTO_EVERY", 25)
TIMEOUT       = getattr(config, "MINIGAME_TIMEOUT", 30)

# ── Flag data ──────────────────────────────────────────────────────────────────

FLAGS: list[tuple[str, list[str]]] = [
    ("🇺🇸", ["united states", "usa", "us", "america"]),
    ("🇬🇧", ["united kingdom", "uk", "britain", "england"]),
    ("🇫🇷", ["france"]),
    ("🇩🇪", ["germany"]),
    ("🇯🇵", ["japan"]),
    ("🇮🇳", ["india"]),
    ("🇧🇷", ["brazil"]),
    ("🇨🇦", ["canada"]),
    ("🇦🇺", ["australia"]),
    ("🇮🇹", ["italy"]),
    ("🇪🇸", ["spain"]),
    ("🇲🇽", ["mexico"]),
    ("🇳🇱", ["netherlands", "holland"]),
    ("🇸🇦", ["saudi arabia"]),
    ("🇰🇷", ["south korea", "korea"]),
    ("🇨🇳", ["china"]),
    ("🇷🇺", ["russia"]),
    ("🇿🇦", ["south africa"]),
    ("🇦🇷", ["argentina"]),
    ("🇹🇷", ["turkey", "türkiye"]),
    ("🇵🇰", ["pakistan"]),
    ("🇳🇬", ["nigeria"]),
    ("🇮🇩", ["indonesia"]),
    ("🇪🇬", ["egypt"]),
    ("🇵🇭", ["philippines"]),
    ("🇧🇩", ["bangladesh"]),
    ("🇸🇪", ["sweden"]),
    ("🇳🇴", ["norway"]),
    ("🇩🇰", ["denmark"]),
    ("🇫🇮", ["finland"]),
    ("🇵🇹", ["portugal"]),
    ("🇬🇷", ["greece"]),
    ("🇵🇱", ["poland"]),
    ("🇨🇭", ["switzerland"]),
    ("🇦🇹", ["austria"]),
    ("🇧🇪", ["belgium"]),
    ("🇮🇪", ["ireland"]),
    ("🇳🇿", ["new zealand"]),
    ("🇸🇬", ["singapore"]),
    ("🇲🇾", ["malaysia"]),
    ("🇹🇭", ["thailand"]),
    ("🇻🇳", ["vietnam"]),
    ("🇺🇦", ["ukraine"]),
    ("🇮🇱", ["israel"]),
    ("🇦🇪", ["uae", "united arab emirates"]),
    ("🇶🇦", ["qatar"]),
    ("🇮🇷", ["iran"]),
    ("🇮🇶", ["iraq"]),
    ("🇨🇴", ["colombia"]),
    ("🇨🇱", ["chile"]),
    ("🇵🇪", ["peru"]),
]

# ── Trivia data ────────────────────────────────────────────────────────────────

TRIVIA: list[tuple[str, list[str]]] = [
    ("What planet is known as the Red Planet?",          ["mars"]),
    ("How many sides does a hexagon have?",              ["6", "six"]),
    ("What is the capital of Japan?",                    ["tokyo"]),
    ("What is the fastest land animal?",                 ["cheetah"]),
    ("How many continents are there?",                   ["7", "seven"]),
    ("What gas do plants absorb from the air?",          ["carbon dioxide", "co2"]),
    ("What is the largest ocean?",                       ["pacific", "pacific ocean"]),
    ("Who painted the Mona Lisa?",                       ["da vinci", "leonardo da vinci", "leonardo"]),
    ("What is the chemical symbol for gold?",            ["au"]),
    ("What is the square root of 144?",                  ["12", "twelve"]),
    ("In what country is the Amazon rainforest mainly?", ["brazil"]),
    ("What is the hardest natural substance?",           ["diamond"]),
    ("How many players are in a standard soccer team?",  ["11", "eleven"]),
    ("What is the capital of Australia?",                ["canberra"]),
    ("What language has the most native speakers?",      ["mandarin", "chinese", "mandarin chinese"]),
    ("What is the longest river in the world?",          ["nile", "nile river"]),
    ("Who wrote Romeo and Juliet?",                      ["shakespeare", "william shakespeare"]),
    ("What is the smallest planet in our solar system?", ["mercury"]),
    ("What element does 'O' stand for on the periodic table?", ["oxygen"]),
    ("How many bones are in the adult human body?",      ["206"]),
    ("What country has the most natural lakes?",         ["canada"]),
    ("What is the tallest mountain in the world?",       ["everest", "mount everest", "mt everest"]),
    ("What currency does Japan use?",                    ["yen", "japanese yen"]),
    ("What is the most spoken language in the world?",   ["english"]),
    ("What organ filters blood in the human body?",      ["kidney", "kidneys"]),
    ("Which planet has the most moons?",                 ["saturn"]),
    ("What is the speed of light in km/s (approx)?",    ["300000", "300,000"]),
    ("What sport is played at Wimbledon?",               ["tennis"]),
    ("What is the capital of Canada?",                   ["ottawa"]),
    ("How many strings does a standard guitar have?",    ["6", "six"]),
]

# ── Word scramble data ─────────────────────────────────────────────────────────

SCRAMBLE_WORDS = [
    "python", "discord", "economy", "server", "dragon", "castle",
    "galaxy", "trophy", "hunter", "market", "bridge", "planet",
    "sunset", "rocket", "jungle", "pirate", "wizard", "battle",
    "cherry", "forest", "coffee", "button", "simple", "rabbit",
    "magnet", "flower", "silver", "golden", "frozen", "winter",
    "turkey", "cookie", "bottle", "hammer", "pencil", "purple",
    "cactus", "helmet", "island", "mirror", "oxygen", "parrot",
    "quartz", "shield", "temple", "violin", "walrus", "yellow",
]


def _scramble(word: str) -> str:
    chars = list(word)
    random.shuffle(chars)
    # Make sure it's actually different
    attempts = 0
    while "".join(chars) == word and attempts < 10:
        random.shuffle(chars)
        attempts += 1
    return "".join(chars)


# ── Math challenge ─────────────────────────────────────────────────────────────

OPERATORS = [
    ("+", operator.add),
    ("-", operator.sub),
    ("×", operator.mul),
]


def _make_math() -> tuple[str, int]:
    """Generate a simple two-operation arithmetic problem."""
    a = random.randint(2, 50)
    b = random.randint(2, 20)
    c = random.randint(2, 10)
    op1_sym, op1_fn = random.choice(OPERATORS)
    op2_sym, op2_fn = random.choice(OPERATORS[:2])  # only + and - for second op to keep it readable

    # Avoid negatives for subtraction
    if op1_sym == "-" and b > a:
        a, b = b, a
    intermediate = op1_fn(a, b)
    if op2_sym == "-" and c > intermediate:
        c = random.randint(1, max(1, intermediate))
    answer = op2_fn(intermediate, c)

    question = f"**{a} {op1_sym} {b} {op2_sym} {c} = ?**"
    return question, answer


# ── Active game tracker ────────────────────────────────────────────────────────

class ActiveGame:
    """Represents a running minigame in a channel."""
    def __init__(self, answers: list[str], reward: int, game_type: str):
        self.answers   = [a.lower().strip() for a in answers]
        self.reward    = reward
        self.game_type = game_type
        self.claimed   = False


# ── Cog ────────────────────────────────────────────────────────────────────────

class Minigames(commands.Cog):
    """Auto-spawning and manual minigame commands."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._message_counts: dict[int, int] = {}      # channel_id -> msg count since last game
        self._active_games: dict[int, ActiveGame] = {} # channel_id -> active game

    # ── Message counter for auto-spawn ────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if message.guild is None:
            return

        channel_id = message.channel.id

        # Check if there's an active game and this is an answer attempt
        if channel_id in self._active_games:
            game = self._active_games[channel_id]
            if not game.claimed:
                guess = message.content.lower().strip()
                if guess in game.answers:
                    game.claimed = True
                    del self._active_games[channel_id]
                    await db.add_wallet(message.author.id, game.reward, reason=f"minigame win: {game.game_type}")
                    await db.add_xp(message.author.id, config.XP_PER_COMMAND)
                    row = await db.get_user(message.author.id)
                    embed = success_embed(
                        f"🎉  Correct! +{fmt(game.reward)}",
                        f"{message.author.mention} got it right!\n\nNew wallet: {fmt(row['wallet'])}",
                    )
                    await message.channel.send(embed=embed)
            return  # Don't count toward auto-spawn while game is active

        # Increment message counter
        self._message_counts[channel_id] = self._message_counts.get(channel_id, 0) + 1
        if self._message_counts[channel_id] >= AUTO_EVERY:
            self._message_counts[channel_id] = 0
            await self._spawn_random_game(message.channel)

    # ── Game spawner ──────────────────────────────────────────────────────────

    async def _spawn_random_game(self, channel: discord.TextChannel):
        """Randomly pick and run a minigame in the given channel."""
        if channel.id in self._active_games:
            return  # already one running

        game_choice = random.choice(["flag", "math", "scramble", "trivia"])
        reward = random.randint(REWARD_MIN, REWARD_MAX)

        if game_choice == "flag":
            await self._spawn_flag(channel, reward)
        elif game_choice == "math":
            await self._spawn_math(channel, reward)
        elif game_choice == "scramble":
            await self._spawn_scramble(channel, reward)
        else:
            await self._spawn_trivia(channel, reward)

    async def _post_game(self, channel, embed: discord.Embed, answers: list[str], reward: int, game_type: str):
        """Post the game embed and register it, then expire after timeout."""
        game = ActiveGame(answers=answers, reward=reward, game_type=game_type)
        self._active_games[channel.id] = game
        await channel.send(embed=embed)

        await asyncio.sleep(TIMEOUT)

        if channel.id in self._active_games and not self._active_games[channel.id].claimed:
            del self._active_games[channel.id]
            expired = discord.Embed(
                title="⏰  Time's up!",
                description=f"Nobody answered in time! The answer was: **{answers[0].title()}**",
                color=config.COLOR_ERROR,
            )
            await channel.send(embed=expired)

    async def _spawn_flag(self, channel, reward: int):
        emoji, answers = random.choice(FLAGS)
        embed = discord.Embed(
            title="🚩  Guess the Flag!",
            description=(
                f"# {emoji}\n\n"
                f"Which country does this flag belong to?\n"
                f"First to type the correct country name wins **{fmt(reward)}**!"
            ),
            color=0x3498DB,
        )
        embed.set_footer(text=f"⏳ You have {TIMEOUT} seconds!")
        await self._post_game(channel, embed, answers, reward, "flag")

    async def _spawn_math(self, channel, reward: int):
        question, answer = _make_math()
        embed = discord.Embed(
            title="➗  Math Challenge!",
            description=(
                f"Solve this: {question}\n\n"
                f"First correct answer wins **{fmt(reward)}**!"
            ),
            color=0x2ECC71,
        )
        embed.set_footer(text=f"⏳ You have {TIMEOUT} seconds!")
        await self._post_game(channel, embed, [str(answer)], reward, "math")

    async def _spawn_scramble(self, channel, reward: int):
        word = random.choice(SCRAMBLE_WORDS)
        scrambled = _scramble(word)
        embed = discord.Embed(
            title="🔤  Unscramble the Word!",
            description=(
                f"**`{scrambled.upper()}`**\n\n"
                f"Unscramble this word!\n"
                f"First correct answer wins **{fmt(reward)}**!"
            ),
            color=0x9B59B6,
        )
        embed.set_footer(text=f"⏳ You have {TIMEOUT} seconds!")
        await self._post_game(channel, embed, [word], reward, "scramble")

    async def _spawn_trivia(self, channel, reward: int):
        question, answers = random.choice(TRIVIA)
        embed = discord.Embed(
            title="❓  Trivia Time!",
            description=(
                f"{question}\n\n"
                f"First correct answer wins **{fmt(reward)}**!"
            ),
            color=0xE67E22,
        )
        embed.set_footer(text=f"⏳ You have {TIMEOUT} seconds!")
        await self._post_game(channel, embed, answers, reward, "trivia")

    # ── Manual trigger ─────────────────────────────────────────────────────────

    @commands.command(name="minigame", aliases=["mg"],
                      help="Manually spawn a minigame in the current channel!")
    @commands.cooldown(rate=1, per=60, type=commands.BucketType.channel)
    async def minigame(self, ctx: commands.Context):
        if ctx.channel.id in self._active_games:
            return await ctx.send(embed=discord.Embed(
                description="❌  There's already an active minigame in this channel!",
                color=config.COLOR_ERROR,
            ))
        self._message_counts[ctx.channel.id] = 0  # reset counter
        await self._spawn_random_game(ctx.channel)

    @minigame.error
    async def minigame_error(self, ctx, error):
        if isinstance(error, commands.CommandOnCooldown):
            await ctx.send(embed=discord.Embed(
                description=f"❌  Minigames can only be manually triggered once per minute per channel. Try again in **{error.retry_after:.0f}s**.",
                color=config.COLOR_ERROR,
            ))

    # ── .minigame stats ────────────────────────────────────────────────────────

    @commands.command(name="gameinfo", aliases=["gi"],
                      help="Show info about the current minigame (if active).")
    async def gameinfo(self, ctx: commands.Context):
        game = self._active_games.get(ctx.channel.id)
        if not game:
            return await ctx.send(embed=discord.Embed(
                description="No active minigame in this channel right now.",
                color=config.COLOR_INFO,
            ))
        await ctx.send(embed=discord.Embed(
            description=f"🎮 Active **{game.game_type}** game · Reward: **{fmt(game.reward)}**",
            color=config.COLOR_INFO,
        ))


def setup(bot: commands.Bot) -> None:
    bot.add_cog(Minigames(bot))
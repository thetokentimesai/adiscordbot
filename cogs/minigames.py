"""
cogs/minigames.py – Chat-spawned minigames.

Changes:
  - .mg admin-only
  - .gi removed
  - Flag games use real flag images from flagcdn.com
  - Per-player minigame streak tracking
  - Streak bonus displayed on win
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
from utils.economy_utils import fmt, error_embed, success_embed

REWARD_MIN = getattr(config, "MINIGAME_REWARD_MIN", 100)
REWARD_MAX = getattr(config, "MINIGAME_REWARD_MAX", 500)
AUTO_EVERY = getattr(config, "MINIGAME_AUTO_EVERY", 25)
TIMEOUT    = getattr(config, "MINIGAME_TIMEOUT", 30)

# ── Flag data — (country_code, [accepted answers]) ────────────────────────────
# country_code is used to build the flagcdn.com URL

FLAGS: list[tuple[str, list[str]]] = [
    ("us", ["united states", "usa", "us", "america"]),
    ("gb", ["united kingdom", "uk", "britain", "england"]),
    ("fr", ["france"]),
    ("de", ["germany"]),
    ("jp", ["japan"]),
    ("in", ["india"]),
    ("br", ["brazil"]),
    ("ca", ["canada"]),
    ("au", ["australia"]),
    ("it", ["italy"]),
    ("es", ["spain"]),
    ("mx", ["mexico"]),
    ("nl", ["netherlands", "holland"]),
    ("sa", ["saudi arabia"]),
    ("kr", ["south korea", "korea"]),
    ("cn", ["china"]),
    ("ru", ["russia"]),
    ("za", ["south africa"]),
    ("ar", ["argentina"]),
    ("tr", ["turkey", "türkiye"]),
    ("pk", ["pakistan"]),
    ("ng", ["nigeria"]),
    ("id", ["indonesia"]),
    ("eg", ["egypt"]),
    ("ph", ["philippines"]),
    ("bd", ["bangladesh"]),
    ("se", ["sweden"]),
    ("no", ["norway"]),
    ("dk", ["denmark"]),
    ("fi", ["finland"]),
    ("pt", ["portugal"]),
    ("gr", ["greece"]),
    ("pl", ["poland"]),
    ("ch", ["switzerland"]),
    ("at", ["austria"]),
    ("be", ["belgium"]),
    ("ie", ["ireland"]),
    ("nz", ["new zealand"]),
    ("sg", ["singapore"]),
    ("my", ["malaysia"]),
    ("th", ["thailand"]),
    ("vn", ["vietnam"]),
    ("ua", ["ukraine"]),
    ("il", ["israel"]),
    ("ae", ["uae", "united arab emirates"]),
    ("qa", ["qatar"]),
    ("ir", ["iran"]),
    ("iq", ["iraq"]),
    ("co", ["colombia"]),
    ("cl", ["chile"]),
    ("pe", ["peru"]),
]

def _flag_image_url(country_code: str) -> str:
    """Return a flagcdn.com image URL for the given 2-letter country code."""
    return f"https://flagcdn.com/w320/{country_code.lower()}.png"


# ── Trivia ─────────────────────────────────────────────────────────────────────

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

# ── Scramble words ─────────────────────────────────────────────────────────────

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
    for _ in range(10):
        random.shuffle(chars)
        if "".join(chars) != word:
            break
    return "".join(chars)


# ── Math challenge ─────────────────────────────────────────────────────────────

OPERATORS = [("+", operator.add), ("-", operator.sub), ("×", operator.mul)]


def _make_math() -> tuple[str, int]:
    a = random.randint(2, 50)
    b = random.randint(2, 20)
    c = random.randint(2, 10)
    op1_sym, op1_fn = random.choice(OPERATORS)
    op2_sym, op2_fn = random.choice(OPERATORS[:2])
    if op1_sym == "-" and b > a:
        a, b = b, a
    intermediate = op1_fn(a, b)
    if op2_sym == "-" and c > intermediate:
        c = random.randint(1, max(1, intermediate))
    answer   = op2_fn(intermediate, c)
    question = f"**{a} {op1_sym} {b} {op2_sym} {c} = ?**"
    return question, answer


# ── Number sequence ────────────────────────────────────────────────────────────

SEQUENCE_TYPES = [
    lambda n: [n, n + 2, n + 4, n + 6],
    lambda n: [n, n * 2, n * 4, n * 8],
    lambda n: [n, n + 5, n + 10, n + 15],
    lambda n: [n, n * 3, n * 9, n * 27],
]


def _make_sequence() -> tuple[str, list[str]]:
    base     = random.randint(1, 20)
    seq      = random.choice(SEQUENCE_TYPES)(base)
    answer   = str(seq[-1])
    question = f"**{'  '.join(map(str, seq[:-1]))}  ?**"
    return question, [answer]


# ── Active game tracker ────────────────────────────────────────────────────────

class ActiveGame:
    def __init__(self, answers: list[str], reward: int, game_type: str):
        self.answers   = [a.lower().strip() for a in answers]
        self.reward    = reward
        self.game_type = game_type
        self.claimed   = False


# ── Admin check helper ─────────────────────────────────────────────────────────

def _is_admin(member: discord.Member) -> bool:
    admin_role = getattr(config, "ADMIN_ROLE_NAME", "・Administrators")
    return (
        any(r.name == admin_role for r in member.roles)
        or member.guild_permissions.administrator
    )


# ── Cog ────────────────────────────────────────────────────────────────────────

class Minigames(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._message_counts: dict[int, int]    = {}
        self._active_games:   dict[int, ActiveGame] = {}

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.guild is None:
            return

        channel_id = message.channel.id

        if channel_id in self._active_games:
            game = self._active_games[channel_id]
            if not game.claimed:
                guess = message.content.lower().strip()
                if guess in game.answers:
                    game.claimed = True
                    del self._active_games[channel_id]

                    # Record win + streak
                    new_streak = await db.record_mg_win(message.author.id)
                    await db.add_xp(message.author.id, config.XP_PER_COMMAND)
                    row = await db.get_user(message.author.id)

                    streak_text = (
                        f"🔥 **{new_streak}-win streak!**" if new_streak > 1
                        else "First win — start a streak!"
                    )
                    embed = discord.Embed(
                        title=f"🎉  Correct! +{fmt(game.reward)}",
                        color=config.COLOR_SUCCESS,
                    )
                    embed.add_field(name="🏆 Winner",    value=message.author.mention, inline=True)
                    embed.add_field(name="💵 Reward",    value=fmt(game.reward),       inline=True)
                    embed.add_field(name="🔥 Streak",    value=streak_text,            inline=False)
                    embed.add_field(name="💳 Balance",   value=fmt(row["wallet"]),     inline=True)
                    embed.add_field(name="🎮 Total Wins",value=str(row["mg_wins"]),    inline=True)
                    await message.channel.send(embed=embed)
            return

        self._message_counts[channel_id] = self._message_counts.get(channel_id, 0) + 1
        if self._message_counts[channel_id] >= AUTO_EVERY:
            self._message_counts[channel_id] = 0
            await self._spawn_random_game(message.channel)

    # ── Game spawner ──────────────────────────────────────────────────────────

    async def _spawn_random_game(self, channel: discord.TextChannel):
        if channel.id in self._active_games:
            return

        game_choice = random.choice(["flag", "math", "scramble", "trivia", "sequence"])
        difficulty_name, reward_min, reward_max = random.choice([
            ("Easy",   100, 250),
            ("Medium", 250, 500),
            ("Hard",   500, 900),
        ])
        reward = random.randint(reward_min, reward_max)

        if game_choice == "flag":
            await self._spawn_flag(channel, reward, difficulty_name)
        elif game_choice == "math":
            await self._spawn_math(channel, reward, difficulty_name)
        elif game_choice == "scramble":
            await self._spawn_scramble(channel, reward, difficulty_name)
        elif game_choice == "sequence":
            await self._spawn_sequence(channel, reward, difficulty_name)
        else:
            await self._spawn_trivia(channel, reward, difficulty_name)

    async def _post_game(self, channel, embed: discord.Embed, answers: list[str], reward: int, game_type: str):
        game = ActiveGame(answers=answers, reward=reward, game_type=game_type)
        self._active_games[channel.id] = game
        await channel.send(embed=embed)

        await asyncio.sleep(TIMEOUT)

        if channel.id in self._active_games and not self._active_games[channel.id].claimed:
            del self._active_games[channel.id]
            expired = discord.Embed(
                title="⏰  Time's Up!",
                description=f"Nobody answered in time!\nThe answer was: **{answers[0].title()}**",
                color=config.COLOR_ERROR,
            )
            await channel.send(embed=expired)

    async def _spawn_flag(self, channel, reward: int, difficulty_name: str):
        code, answers = random.choice(FLAGS)
        image_url = _flag_image_url(code)
        embed = discord.Embed(
            title=f"🚩  Guess the Flag! • {difficulty_name}",
            description=(
                f"Which country does this flag belong to?\n"
                f"First correct answer wins **{fmt(reward)}**!"
            ),
            color=0x3498DB,
        )
        embed.set_image(url=image_url)
        embed.set_footer(text=f"⏳ You have {TIMEOUT} seconds!")
        await self._post_game(channel, embed, answers, reward, "flag")

    async def _spawn_math(self, channel, reward: int, difficulty_name: str):
        question, answer = _make_math()
        embed = discord.Embed(
            title=f"➗  Math Challenge! • {difficulty_name}",
            description=f"Solve this: {question}\n\nFirst correct answer wins **{fmt(reward)}**!",
            color=0x2ECC71,
        )
        embed.set_footer(text=f"⏳ You have {TIMEOUT} seconds!")
        await self._post_game(channel, embed, [str(answer)], reward, "math")

    async def _spawn_scramble(self, channel, reward: int, difficulty_name: str):
        word      = random.choice(SCRAMBLE_WORDS)
        scrambled = _scramble(word)
        embed = discord.Embed(
            title=f"🔤  Unscramble the Word! • {difficulty_name}",
            description=f"**`{scrambled.upper()}`**\n\nUnscramble this word!\nFirst correct answer wins **{fmt(reward)}**!",
            color=0x9B59B6,
        )
        embed.set_footer(text=f"⏳ You have {TIMEOUT} seconds!")
        await self._post_game(channel, embed, [word], reward, "scramble")

    async def _spawn_trivia(self, channel, reward: int, difficulty_name: str):
        question, answers = random.choice(TRIVIA)
        embed = discord.Embed(
            title=f"❓  Trivia Time! • {difficulty_name}",
            description=f"{question}\n\nFirst correct answer wins **{fmt(reward)}**!",
            color=0xE67E22,
        )
        embed.set_footer(text=f"⏳ You have {TIMEOUT} seconds!")
        await self._post_game(channel, embed, answers, reward, "trivia")

    async def _spawn_sequence(self, channel, reward: int, difficulty_name: str):
        question, answers = _make_sequence()
        embed = discord.Embed(
            title=f"🔢  Number Sequence • {difficulty_name}",
            description=f"What comes next?\n{question}\n\nFirst correct answer wins **{fmt(reward)}**!",
            color=0x1ABC9C,
        )
        embed.set_footer(text=f"⏳ You have {TIMEOUT} seconds!")
        await self._post_game(channel, embed, answers, reward, "sequence")

    # ── .minigame (admin only) ────────────────────────────────────────────────

    @commands.command(name="minigame", aliases=["mg"])
    async def minigame(self, ctx: commands.Context):
        if not _is_admin(ctx.author):
            return await ctx.send(embed=error_embed("🔒 Only admins can manually trigger a minigame."))
        if ctx.channel.id in self._active_games:
            return await ctx.send(embed=error_embed("There's already an active minigame in this channel!"))
        self._message_counts[ctx.channel.id] = 0
        await self._spawn_random_game(ctx.channel)


def setup(bot: commands.Bot) -> None:
    bot.add_cog(Minigames(bot))
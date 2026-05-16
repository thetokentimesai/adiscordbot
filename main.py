import discord
from discord.ext import commands
from threading import Thread
from http.server import HTTPServer, BaseHTTPRequestHandler
import logging

import config
from database import db

logging.basicConfig(level=logging.INFO)

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(
    command_prefix=".",
    intents=intents,
    help_command=None,
)


# ── Custom help command ────────────────────────────────────────────────────────

@bot.command(name="help", aliases=["h"])
async def help_command(ctx: commands.Context):
    embed = discord.Embed(
        title="📖  Command List",
        description="All commands use the `.` prefix. Aliases shown in brackets.",
        color=config.COLOR_INFO,
    )

    # ── Economy ────────────────────────────────────────────────────────────────
    embed.add_field(name="\u200b", value="**💰 Economy**", inline=False)
    embed.add_field(name=".balance [.bal]",              value="Check your wallet, bank, level & XP",  inline=True)
    embed.add_field(name=".wallet [.w]",                 value="Check just your wallet balance",        inline=True)
    embed.add_field(name=".deposit [.dep/.d] <amt|all>", value="Deposit coins to bank",                 inline=True)
    embed.add_field(name=".withdraw [.wd] <amt|all>",    value="Withdraw coins from bank",              inline=True)
    embed.add_field(name=".pay <@user> <amount>",        value="Pay another user",                      inline=True)

    # ── Rewards ────────────────────────────────────────────────────────────────
    embed.add_field(name="\u200b", value="**🎁 Rewards**", inline=False)
    embed.add_field(name=".daily [.dy]",     value=f"🪙 {config.DAILY_MIN}–{config.DAILY_MAX} every 22 hours",     inline=True)
    embed.add_field(name=".hourly [.hr]",    value=f"🪙 {config.HOURLY_MIN}–{config.HOURLY_MAX} every 1 hour",     inline=True)
    embed.add_field(name=".work [.wr]",      value=f"🪙 {config.WORK_MIN}–{config.WORK_MAX} every 30 minutes",     inline=True)
    embed.add_field(name=".sidequest [.sq]", value=f"🪙 {config.SIDEQUEST_MIN}–{config.SIDEQUEST_MAX} every 6 hours", inline=True)
    embed.add_field(
        name=".weekly [.wk] 🔒",
        value=f"🪙 {config.WEEKLY_MIN:,}–{config.WEEKLY_MAX:,} every 7 days · **{config.VERIFIED_ROLE_NAME} only**",
        inline=True,
    )
    embed.add_field(
        name=".monthly [.mo] 🔒",
        value=f"🪙 {config.MONTHLY_MIN:,}–{config.MONTHLY_MAX:,} every 30 days · **{config.VERIFIED_ROLE_NAME} only**",
        inline=True,
    )
    embed.add_field(name=".cooldowns [.cd]", value="See all your reward timers", inline=True)

    # ── Games ──────────────────────────────────────────────────────────────────
    embed.add_field(name="\u200b", value="**🎮 Games**", inline=False)
    embed.add_field(
        name=".coinflip [.cf] <amt|half|all> <h|t>",
        value="Flip a coin — args in any order",
        inline=True,
    )
    embed.add_field(
        name=".slots <amt|half|all>",
        value="Spin the slot machine",
        inline=True,
    )
    embed.add_field(
        name=".dice [.dc] <amt|half|all>",
        value="Roll dice against the bot",
        inline=True,
    )
    embed.add_field(
        name=".blackjack [.bj] <amt|half|all>",
        value="Play interactive blackjack",
        inline=True,
    )
    embed.add_field(
        name=".horserace [.race]",
        value=f"🏇 Race for 🪙 500 buy-in · winner takes all",
        inline=True,
    )

    # ── Minigames ──────────────────────────────────────────────────────────────
    embed.add_field(name="\u200b", value="**🧠 Minigames**", inline=False)
    embed.add_field(
        name="Auto-spawning",
        value=f"Flag, math, unscramble & trivia questions pop up every ~{config.MINIGAME_AUTO_EVERY} messages. First correct answer wins 🪙 {config.MINIGAME_REWARD_MIN}–{config.MINIGAME_REWARD_MAX}!",
        inline=False,
    )
    embed.add_field(name=".minigame [.mg]", value="Manually trigger a minigame",          inline=True)
    embed.add_field(name=".gameinfo [.gi]", value="Check if a minigame is currently live", inline=True)

    # ── Fun ────────────────────────────────────────────────────────────────────
    embed.add_field(name="\u200b", value="**😂 Fun**", inline=False)
    embed.add_field(name=".gaybar [@user]",   value="Gay-o-meter 🌈",         inline=True)
    embed.add_field(name=".susmeter [@user]", value="Sus meter 📣",           inline=True)
    embed.add_field(name=".nerdrate [@user]", value="Nerd rate 🤓",           inline=True)
    embed.add_field(name=".ship <@u1> <@u2>", value="Compatibility check 💞", inline=True)

    embed.set_footer(text="Amounts: 1k = 1,000 | 1m = 1,000,000 | half = 50% wallet | all = full wallet")
    await ctx.send(embed=embed)


# ── Ready ──────────────────────────────────────────────────────────────────────

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    try:
        db.init_db()
        print("Database initialized.")
    except Exception as e:
        print(f"Database init error: {e}")


# ── Cogs ───────────────────────────────────────────────────────────────────────

COGS = ["cogs.economy", "cogs.fun", "cogs.games", "cogs.minigames"]

for cog in COGS:
    try:
        bot.load_extension(cog)
        print(f"Loaded {cog}")
    except Exception as e:
        print(f"Failed to load {cog}: {e}")


# ── Keep-alive ─────────────────────────────────────────────────────────────────
# Minimal HTTP server for UptimeRobot / Render health checks.
#
# The "output too large" error from some monitors happens when the response
# includes verbose headers or a large body. This handler returns:
#   - HTTP 200
#   - A single "Content-Length: 2" header (so the monitor knows exactly when
#     the response is done and doesn't wait/buffer)
#   - A 2-byte body: "OK"
# No Date, Server, or any other auto-generated headers are sent.

class PingHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = b"OK"
        # Send status line manually then flush — avoids BaseHTTPRequestHandler
        # auto-adding verbose headers like Server and Date.
        self.wfile.write(
            b"HTTP/1.1 200 OK\r\n"
            b"Content-Type: text/plain\r\n"
            b"Content-Length: 2\r\n"
            b"Connection: close\r\n"
            b"\r\n"
            + body
        )

    def do_HEAD(self):
        # Some monitors send HEAD instead of GET
        self.wfile.write(
            b"HTTP/1.1 200 OK\r\n"
            b"Content-Type: text/plain\r\n"
            b"Content-Length: 2\r\n"
            b"Connection: close\r\n"
            b"\r\n"
        )

    def log_message(self, format, *args):
        pass  # suppress access logs from stdout


def run_webserver():
    server = HTTPServer(("0.0.0.0", 8080), PingHandler)
    server.serve_forever()

Thread(target=run_webserver, daemon=True).start()

# ── Run ────────────────────────────────────────────────────────────────────────

bot.run(config.DISCORD_TOKEN)
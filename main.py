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
    help_command=None,   # we define our own below
)


# ── Custom help command ────────────────────────────────────────────────────────

@bot.command(name="help", aliases=["h"])
async def help_command(ctx: commands.Context):
    embed = discord.Embed(
        title="📖  Command List",
        description="All commands use the `.` prefix. Aliases shown in brackets.",
        color=config.COLOR_INFO,
    )

    embed.add_field(name="\u200b", value="**💰 Economy**", inline=False)
    embed.add_field(
        name=".balance [.bal]",
        value="Check your wallet, bank, level & XP",
        inline=True,
    )
    embed.add_field(
        name=".wallet [.w]",
        value="Check just your wallet balance",
        inline=True,
    )
    embed.add_field(
        name=".deposit [.dep / .d] <amount|all>",
        value="Deposit coins to bank",
        inline=True,
    )
    embed.add_field(
        name=".withdraw [.wd] <amount|all>",
        value="Withdraw coins from bank",
        inline=True,
    )
    embed.add_field(
        name=".pay <@user> <amount>",
        value="Pay another user",
        inline=True,
    )
    embed.add_field(
        name="\u200b", value="**🎁 Rewards**", inline=False,
    )
    embed.add_field(
        name=".daily [.dy]",
        value=f"🪙 {config.DAILY_MIN}–{config.DAILY_MAX} every 22 hours",
        inline=True,
    )
    embed.add_field(
        name=".hourly [.hr]",
        value=f"🪙 {config.HOURLY_MIN}–{config.HOURLY_MAX} every 1 hour",
        inline=True,
    )
    embed.add_field(
        name=".work [.wr]",
        value=f"🪙 {config.WORK_MIN}–{config.WORK_MAX} every 30 minutes",
        inline=True,
    )
    embed.add_field(
        name=".sidequest [.sq]",
        value=f"🪙 {config.SIDEQUEST_MIN}–{config.SIDEQUEST_MAX} every 6 hours",
        inline=True,
    )
    embed.add_field(
        name=".cooldowns [.cd]",
        value="See all your reward timers",
        inline=True,
    )
    embed.add_field(name="\u200b", value="**🎮 Games**", inline=False)
    embed.add_field(
        name=".coinflip [.cf] <amount> <heads|tails>",
        value="Flip a coin",
        inline=True,
    )
    embed.add_field(
        name=".slots <amount>",
        value="Spin the slot machine",
        inline=True,
    )
    embed.add_field(
        name=".dice [.dc] <amount>",
        value="Roll dice against the bot",
        inline=True,
    )
    embed.add_field(
        name=".blackjack [.bj] <amount>",
        value="Play interactive blackjack",
        inline=True,
    )
    embed.add_field(name="\u200b", value="**😂 Fun**", inline=False)
    embed.add_field(name=".gaybar [@user]",    value="Gay-o-meter 🌈",        inline=True)
    embed.add_field(name=".susmeter [@user]",  value="Sus meter 📣",          inline=True)
    embed.add_field(name=".nerdrate [@user]",  value="Nerd rate 🤓",          inline=True)
    embed.add_field(name=".ship <@u1> <@u2>",  value="Compatibility check 💞", inline=True)

    embed.set_footer(text="Amounts accept shorthand: 1k = 1,000 | 1m = 1,000,000")
    await ctx.send(embed=embed)


# ── Ready ──────────────────────────────────────────────────────────────────────

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    try:
        await db.init_db()
        print("Database initialized.")
    except Exception as e:
        print(f"Database init error: {e}")


# ── Cogs ───────────────────────────────────────────────────────────────────────

COGS = ["cogs.economy", "cogs.fun", "cogs.games"]

for cog in COGS:
    try:
        bot.load_extension(cog)
        print(f"Loaded {cog}")
    except Exception as e:
        print(f"Failed to load {cog}: {e}")


# ── Keep-alive ─────────────────────────────────────────────────────────────────

class PingHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")
    def log_message(self, format, *args):
        pass

def run_webserver():
    server = HTTPServer(("0.0.0.0", 8080), PingHandler)
    server.serve_forever()

Thread(target=run_webserver, daemon=True).start()

# ── Run ────────────────────────────────────────────────────────────────────────

bot.run(config.DISCORD_TOKEN)

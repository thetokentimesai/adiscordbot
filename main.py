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

def _help_pages() -> list[discord.Embed]:
    """Build all help embed pages. Called once per .help invocation."""

    pages = []

    # ── Page 1: Economy & Crime ────────────────────────────────────────────────
    e1 = discord.Embed(
        title="📖  Command List  •  Page 1 / 4",
        description="All commands use the `.` prefix. Aliases shown in brackets.",
        color=config.COLOR_INFO,
    )
    e1.add_field(name="\u200b", value="**💰 Economy**", inline=False)
    e1.add_field(name=".balance [.bal]",               value="Check your wallet, bank, level & XP", inline=True)
    e1.add_field(name=".wallet [.w]",                  value="Check just your wallet balance",       inline=True)
    e1.add_field(name=".deposit [.dep/.d] <amt|all>",  value="Deposit coins to bank",                inline=True)
    e1.add_field(name=".withdraw [.wd] <amt|all>",     value="Withdraw coins from bank",             inline=True)
    e1.add_field(name=".send [.pay/.give] <@user> <amount>", value="Send coins to another user",      inline=True)
    e1.add_field(name="\u200b", value="**💀 Crime**", inline=False)
    e1.add_field(name=".rob <@user>",                  value="Attempt to rob another user",          inline=True)
    e1.add_field(name=".steal <@user>",                value="Attempt to steal from another user",   inline=True)
    e1.add_field(name=".heist <store|jewelry|bank>",   value="Attempt a risky heist",                inline=True)
    e1.set_footer(text="Amounts: 1k = 1,000 | 1m = 1,000,000 | half = 50% wallet | all = full wallet")
    pages.append(e1)

    # ── Page 2: Rewards ────────────────────────────────────────────────────────
    e2 = discord.Embed(
        title="📖  Command List  •  Page 2 / 4",
        description="All commands use the `.` prefix. Aliases shown in brackets.",
        color=config.COLOR_INFO,
    )
    e2.add_field(name="\u200b", value="**🎁 Rewards**", inline=False)
    e2.add_field(name=".daily [.dy]",     value=f"🪙 {config.DAILY_MIN}–{config.DAILY_MAX} every 22 hours",           inline=True)
    e2.add_field(name=".hourly [.hr]",    value=f"🪙 {config.HOURLY_MIN}–{config.HOURLY_MAX} every 1 hour",           inline=True)
    e2.add_field(name=".work [.wr]",      value=f"🪙 {config.WORK_MIN}–{config.WORK_MAX} every 30 minutes",           inline=True)
    e2.add_field(name=".sidequest [.sq]", value=f"🪙 {config.SIDEQUEST_MIN}–{config.SIDEQUEST_MAX} every 6 hours",    inline=True)
    e2.add_field(
        name=".weekly [.wk] 🔒",
        value=f"🪙 {config.WEEKLY_MIN:,}–{config.WEEKLY_MAX:,} every 7 days · **{config.VERIFIED_ROLE_NAME} only**",
        inline=True,
    )
    e2.add_field(
        name=".monthly [.mo] 🔒",
        value=f"🪙 {config.MONTHLY_MIN:,}–{config.MONTHLY_MAX:,} every 30 days · **{config.VERIFIED_ROLE_NAME} only**",
        inline=True,
    )
    e2.add_field(name=".cooldowns [.cd]", value="See all your reward timers", inline=True)
    e2.set_footer(text="🔒 = Verified members only")
    pages.append(e2)

    # ── Page 3: Games ─────────────────────────────────────────────────────────
    e3 = discord.Embed(
        title="📖  Command List  •  Page 3 / 4",
        description="All commands use the `.` prefix. Aliases shown in brackets.",
        color=config.COLOR_INFO,
    )
    e3.add_field(name="\u200b", value="**🎮 Games**", inline=False)
    e3.add_field(name=".coinflip [.cf] <amt|half|all> <h|t>", value="Flip a coin — args in any order", inline=True)
    e3.add_field(name=".slots <amt|half|all>",                 value="Spin the slot machine",           inline=True)
    e3.add_field(name=".dice [.dc] <amt|half|all>",            value="Roll dice against the bot",       inline=True)
    e3.add_field(name=".blackjack [.bj] <amt|half|all>",       value="Play interactive blackjack",      inline=True)
    e3.add_field(name=".horserace [.race]",                    value="🏇 Race · 🪙 500 buy-in · winner takes all", inline=True)
    e3.set_footer(text="Amounts: 1k = 1,000 | 1m = 1,000,000 | half = 50% wallet | all = full wallet")
    pages.append(e3)

    # ── Page 4: Minigames & Fun ────────────────────────────────────────────────
    e4 = discord.Embed(
        title="📖  Command List  •  Page 4 / 4",
        description="All commands use the `.` prefix. Aliases shown in brackets.",
        color=config.COLOR_INFO,
    )
    e4.add_field(name="\u200b", value="**🧠 Minigames**", inline=False)
    e4.add_field(
        name="Auto-spawning",
        value=f"Flag, math, sequence, unscramble & trivia pop up every ~{config.MINIGAME_AUTO_EVERY} messages. First correct answer wins 🪙 rewards!",
        inline=False,
    )
    e4.add_field(name=".minigame [.mg]", value="Manually trigger a minigame",          inline=True)
    e4.add_field(name=".gameinfo [.gi]", value="Check if a minigame is currently live", inline=True)
    e4.add_field(name="\u200b", value="**😂 Fun**", inline=False)
    e4.add_field(name=".gaybar [.gay] [@user]",   value="Gay-o-meter 🌈",   inline=True)
    e4.add_field(name=".susmeter [.sus] [@user]", value="Sus meter 📣",     inline=True)
    e4.add_field(name=".nerdrate [.nerd] [@user]", value="Nerd rate 🤓",    inline=True)
    e4.add_field(name=".ship <@user>",     value="Relationship score 💞", inline=True)
    e4.set_footer(text="Results reset every Monday 00:00 UTC")
    pages.append(e4)

    return pages


class HelpView(discord.ui.View):
    """Paginated help menu with ◀ / ▶ buttons."""

    def __init__(self, pages: list[discord.Embed], author_id: int):
        super().__init__(timeout=120)
        self.pages     = pages
        self.author_id = author_id
        self.index     = 0
        self._update_buttons()

    def _update_buttons(self):
        self.prev_button.disabled = self.index == 0
        self.next_button.disabled = self.index == len(self.pages) - 1

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This help menu isn't yours!", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        # Disable buttons when the view expires
        for child in self.children:
            child.disabled = True
        if self.message:
            await self.message.edit(view=self)

    @discord.ui.button(label="◀ Prev", style=discord.ButtonStyle.secondary)
    async def prev_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        self.index -= 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.pages[self.index], view=self)

    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.secondary)
    async def next_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        self.index += 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.pages[self.index], view=self)


@bot.command(name="help", aliases=["h"])
async def help_command(ctx: commands.Context):
    pages = _help_pages()
    view  = HelpView(pages, author_id=ctx.author.id)
    view.message = await ctx.send(embed=pages[0], view=view)


# ── Ready ──────────────────────────────────────────────────────────────────────

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    try:
        await db.init_db()
        print("Database initialized.")
    except Exception as e:
        print(f"Database init error: {e}")
    try:
        await bot.sync_commands()
        print("Slash commands synced.")
    except Exception as e:
        print(f"Slash command sync error: {e}")


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

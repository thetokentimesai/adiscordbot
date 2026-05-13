import discord
import logging

import config
from database import db

logging.basicConfig(level=logging.INFO)

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = discord.Bot(intents=intents)


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

    try:
        db.init_db()
        print("Database initialized.")
    except Exception as e:
        print(f"Database init error: {e}")

    try:
        synced = await bot.sync_commands(
            guild_ids=[config.ALLOWED_GUILD_ID]
        )
        print(f"Synced {len(synced)} commands.")
    except Exception as e:
        print(f"Command sync error: {e}")


COGS = [
    "cogs.economy",
    "cogs.fun",
    "cogs.games",
]

for cog in COGS:
    try:
        bot.load_extension(cog)
        print(f"Loaded {cog}")
    except Exception as e:
        print(f"Failed to load {cog}: {e}")


bot.run(config.DISCORD_TOKEN)
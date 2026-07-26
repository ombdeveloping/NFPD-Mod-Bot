import asyncio
import logging

import discord
from discord.ext import commands

from config import BOT_TOKEN, COMMAND_PREFIX
from database import initialize_database

logging.basicConfig(level=logging.INFO)

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix=COMMAND_PREFIX, intents=intents)

INITIAL_COGS = (
    "cogs.moderation",
    "cogs.global_moderation",
)


@bot.event
async def on_ready():
    logging.info("Logged in as %s (%s)", bot.user, bot.user.id)
    synced_commands = await bot.tree.sync()
    logging.info("Synced %d slash command(s)", len(synced_commands))


async def main():
    await initialize_database()
    async with bot:
        for cog in INITIAL_COGS:
            await bot.load_extension(cog)
        await bot.start(BOT_TOKEN)


if __name__ == "__main__":
    asyncio.run(main())

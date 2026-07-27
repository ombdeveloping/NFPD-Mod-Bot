import asyncio
import logging

import discord
from discord.ext import commands

from config import BOT_TOKEN, COMMAND_PREFIX
from database import close_database, connect_database
from embeds import build_notice_embed

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s %(name)s: %(message)s")
logger = logging.getLogger("modbot")

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix=COMMAND_PREFIX, intents=intents, help_command=None)

INITIAL_COGS = (
    "cogs.moderation",
    "cogs.case_management",
    "cogs.global_moderation",
    "cogs.settings",
    "cogs.channel_moderation",
    "cogs.raid_protection",
    "cogs.scheduled_tasks",
)


@bot.event
async def on_ready():
    logger.info("Logged in as %s (%s) across %d guild(s)", bot.user, bot.user.id, len(bot.guilds))
    synced = await bot.tree.sync()
    logger.info("Synced %d slash command(s)", len(synced))


@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError):
    """Turn the common permission and usage failures into readable replies instead of tracebacks."""
    if isinstance(error, commands.CommandNotFound):
        return

    if isinstance(error, commands.MissingPermissions):
        message = "You don't have permission to use that."
    elif isinstance(error, commands.BotMissingPermissions):
        missing = ", ".join(permission.replace("_", " ") for permission in error.missing_permissions)
        message = f"I'm missing the required permission(s): {missing}."
    elif isinstance(error, commands.CheckFailure):
        message = "That command is restricted to global moderators."
    elif isinstance(error, commands.MissingRequiredArgument):
        message = f"Missing argument: `{error.param.name}`."
    elif isinstance(error, (commands.MemberNotFound, commands.UserNotFound)):
        message = "I couldn't find that user."
    elif isinstance(error, commands.BadArgument):
        message = "One of those arguments wasn't valid."
    else:
        logger.exception("Unhandled command error in %s", ctx.command, exc_info=error)
        message = "Something went wrong running that command."

    await ctx.send(embed=build_notice_embed(message, success=False))


async def main():
    await connect_database()
    try:
        async with bot:
            for cog in INITIAL_COGS:
                await bot.load_extension(cog)
            await bot.start(BOT_TOKEN)
    finally:
        await close_database()


if __name__ == "__main__":
    asyncio.run(main())

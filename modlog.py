import logging

import discord
from discord.ext import commands

from database import add_case, get_guild_settings
from embeds import build_case_embed

logger = logging.getLogger("modbot.modlog")


async def post_to_log_channel(guild: discord.Guild, embed: discord.Embed) -> None:
    settings = await get_guild_settings(guild.id)
    channel_id = settings["log_channel_id"]
    if channel_id is None:
        return

    channel = guild.get_channel(channel_id)
    if not isinstance(channel, discord.abc.Messageable):
        logger.warning(
            "Log channel %s in guild %s (%s) no longer exists or is not messageable",
            channel_id, guild.name, guild.id,
        )
        return

    try:
        await channel.send(embed=embed)
    except discord.HTTPException as error:
        logger.warning("Could not post to log channel in guild %s (%s): %s", guild.name, guild.id, error)


async def check_log_channel(guild: discord.Guild) -> tuple[bool, str]:
    """Diagnose why the configured log channel would or wouldn't actually receive a message."""
    settings = await get_guild_settings(guild.id)
    channel_id = settings["log_channel_id"]
    if channel_id is None:
        return False, "No log channel configured. Set one with /setlogchannel."

    channel = guild.get_channel(channel_id)
    if channel is None:
        return False, f"Configured channel `{channel_id}` no longer exists. Set a new one with /setlogchannel."
    if not isinstance(channel, discord.abc.Messageable):
        return False, f"{channel.mention} exists but is not a type the bot can send messages to."

    if guild.me is not None:
        permissions = channel.permissions_for(guild.me)
        missing = [
            name for name, has_it in (
                ("View Channel", permissions.view_channel),
                ("Send Messages", permissions.send_messages),
                ("Embed Links", permissions.embed_links),
            )
            if not has_it
        ]
        if missing:
            return False, f"{channel.mention} is set, but I am missing: {', '.join(missing)}."

    return True, f"{channel.mention} is set and reachable."


async def record_case(
    guild: discord.Guild,
    target: discord.abc.User,
    moderator: discord.abc.User,
    action_type: str,
    reason: str,
) -> discord.Embed:
    """Save the case, mirror it to the guild's log channel, and return the embed."""
    case_id = await add_case(guild.id, target.id, moderator.id, action_type, reason)
    embed = build_case_embed(action_type, target, moderator, reason, case_id)
    await post_to_log_channel(guild, embed)
    return embed


async def announce_case(
    ctx: commands.Context,
    target: discord.abc.User,
    action_type: str,
    reason: str,
    moderator: discord.abc.User | None = None,
) -> discord.Embed:
    """record_case, plus the reply in the channel the command was run from."""
    embed = await record_case(ctx.guild, target, moderator or ctx.author, action_type, reason)
    await ctx.send(embed=embed)
    return embed


async def try_dm(user: discord.abc.User, embed: discord.Embed) -> bool:
    """DMs fail for closed DMs (403), bots and blocked senders (400), and deleted accounts (404)."""
    try:
        await user.send(embed=embed)
        return True
    except discord.HTTPException:
        return False

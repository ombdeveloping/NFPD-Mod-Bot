import discord
from discord.ext import commands

from database import add_case, get_guild_settings
from embeds import build_case_embed


async def post_to_log_channel(guild: discord.Guild, embed: discord.Embed) -> None:
    settings = await get_guild_settings(guild.id)
    channel_id = settings["log_channel_id"]
    if channel_id is None:
        return

    channel = guild.get_channel(channel_id)
    if channel is None:
        return

    try:
        await channel.send(embed=embed)
    except discord.Forbidden:
        pass


async def record_case(
    guild: discord.Guild,
    target: discord.abc.User,
    moderator: discord.abc.User,
    action_type: str,
    reason: str,
) -> discord.Embed:
    """Save the case, mirror it to the guild's log channel, and hand back the embed to reply with."""
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

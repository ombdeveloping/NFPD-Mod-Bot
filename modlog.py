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
    # The channel may have been deleted, or converted to a type that can't receive messages.
    if not isinstance(channel, discord.abc.Messageable):
        return

    try:
        await channel.send(embed=embed)
    except discord.HTTPException:
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


async def try_dm(user: discord.abc.User, embed: discord.Embed) -> bool:
    """DMs fail for closed DMs (403), bots and blocked senders (400), and deleted accounts (404)."""
    try:
        await user.send(embed=embed)
        return True
    except discord.HTTPException:
        return False


async def check_log_channel(guild: discord.Guild) -> tuple[bool, str]:
    settings = await get_guild_settings(guild.id)
    channel_id = settings["log_channel_id"]
    if channel_id is None:
        return False, "No log channel configured."

    channel = guild.get_channel(channel_id)
    if channel is None:
        return False, "Configured log channel does not exist."

    if not isinstance(channel, discord.abc.Messageable):
        return False, "Configured log channel is not messageable."

    me = guild.me
    if me is None:
        return False, "Bot member unavailable."

    perms = channel.permissions_for(me)
    if not perms.send_messages:
        return False, "Missing Send Messages permission."
    if not perms.embed_links:
        return False, "Missing Embed Links permission."

    return True, f"Logging to #{getattr(channel, 'name', channel_id)}"

import discord

from database import get_guild_settings


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

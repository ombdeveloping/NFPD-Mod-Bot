from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from database import pop_channel_lock, save_channel_lock

MAX_SLOWMODE_SECONDS = 21600  # Discord's own cap: 6 hours


def _serialize_tristate(value: Optional[bool]) -> str:
    if value is True:
        return "true"
    if value is False:
        return "false"
    return "none"


def _deserialize_tristate(value: str) -> Optional[bool]:
    if value == "true":
        return True
    if value == "false":
        return False
    return None


class ChannelModeration(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="slowmode", description="Set the slowmode delay for a channel")
    @app_commands.describe(
        seconds="Delay between messages, in seconds (0 to disable, max 21600)",
        channel="Channel to apply to (defaults to this channel)",
    )
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def slowmode(self, ctx: commands.Context, seconds: int, channel: Optional[discord.TextChannel] = None):
        target_channel = channel or ctx.channel
        if seconds < 0 or seconds > MAX_SLOWMODE_SECONDS:
            await ctx.send(f"Slowmode delay must be between 0 and {MAX_SLOWMODE_SECONDS} seconds (6 hours).")
            return

        await target_channel.edit(slowmode_delay=seconds)
        if seconds == 0:
            await ctx.send(f"Slowmode disabled in {target_channel.mention}.")
        else:
            await ctx.send(f"Slowmode set to {seconds}s in {target_channel.mention}.")

    @commands.hybrid_command(name="lockdown", description="Prevent @everyone from sending messages in a channel")
    @app_commands.describe(
        channel="Channel to lock (defaults to this channel)",
        reason="Why the channel is being locked",
    )
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def lockdown(
        self,
        ctx: commands.Context,
        channel: Optional[discord.TextChannel] = None,
        *,
        reason: str = "No reason provided",
    ):
        target_channel = channel or ctx.channel
        everyone_role = ctx.guild.default_role
        overwrite = target_channel.overwrites_for(everyone_role)

        await save_channel_lock(ctx.guild.id, target_channel.id, _serialize_tristate(overwrite.send_messages))
        overwrite.send_messages = False
        await target_channel.set_permissions(everyone_role, overwrite=overwrite, reason=reason)

        await ctx.send(f"\U0001F512 {target_channel.mention} is locked. Reason: {reason}")

    @commands.hybrid_command(name="unlock", description="Restore @everyone's ability to send messages in a channel")
    @app_commands.describe(channel="Channel to unlock (defaults to this channel)")
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def unlock(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None):
        target_channel = channel or ctx.channel
        everyone_role = ctx.guild.default_role

        previous_state = await pop_channel_lock(ctx.guild.id, target_channel.id)
        overwrite = target_channel.overwrites_for(everyone_role)
        overwrite.send_messages = _deserialize_tristate(previous_state) if previous_state is not None else None
        await target_channel.set_permissions(everyone_role, overwrite=overwrite)

        note = "" if previous_state is not None else " (no lock record found, reset to default)"
        await ctx.send(f"\U0001F513 {target_channel.mention} is unlocked.{note}")


async def setup(bot: commands.Bot):
    await bot.add_cog(ChannelModeration(bot))

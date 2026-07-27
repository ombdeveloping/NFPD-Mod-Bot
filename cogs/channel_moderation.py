from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from database import get_guild_settings, pop_channel_lock, save_channel_lock
from embeds import MUTED_COLOR, NEUTRAL_COLOR, SUCCESS_COLOR, base_embed, build_notice_embed
from modlog import post_to_log_channel

MAX_SLOWMODE_SECONDS = 21600  # Discord's own cap: 6 hours
MAX_PURGE_MESSAGES = 100

TRISTATE_TO_TEXT = {True: "true", False: "false", None: "none"}
TEXT_TO_TRISTATE = {"true": True, "false": False, "none": None}


class ChannelModeration(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def resolve_lockdown_role(self, guild: discord.Guild) -> discord.Role:
        """The role a lockdown silences. Falls back to @everyone until one is configured."""
        settings = await get_guild_settings(guild.id)
        role_id = settings["lockdown_role_id"]
        if role_id is None:
            return guild.default_role
        return guild.get_role(role_id) or guild.default_role

    @commands.hybrid_command(name="slowmode", description="Set a channel's slowmode delay")
    @app_commands.describe(
        seconds="Delay between messages in seconds (0 disables, max 21600)",
        channel="Channel to apply to, defaults to the current one",
    )
    @commands.guild_only()
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def slowmode(self, ctx: commands.Context, seconds: int, channel: Optional[discord.TextChannel] = None):
        target = channel or ctx.channel
        if not 0 <= seconds <= MAX_SLOWMODE_SECONDS:
            await ctx.send(
                embed=build_notice_embed(
                    f"Delay must be between 0 and {MAX_SLOWMODE_SECONDS} seconds (6 hours).", success=False
                )
            )
            return

        await target.edit(slowmode_delay=seconds)
        message = (
            f"Slowmode disabled in {target.mention}."
            if seconds == 0
            else f"Slowmode set to **{seconds}s** in {target.mention}."
        )
        await ctx.send(embed=build_notice_embed(message))

    @commands.hybrid_command(name="purge", description="Bulk delete recent messages from a channel")
    @app_commands.describe(
        amount="How many messages to scan and delete (1 to 100)",
        member="Only delete messages from this member",
    )
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True, read_message_history=True)
    async def purge(self, ctx: commands.Context, amount: int, member: Optional[discord.Member] = None):
        if not 1 <= amount <= MAX_PURGE_MESSAGES:
            await ctx.send(
                embed=build_notice_embed(f"Amount must be between 1 and {MAX_PURGE_MESSAGES}.", success=False)
            )
            return

        # Remove the invoking message first so it isn't counted or left dangling.
        if ctx.interaction is None:
            try:
                await ctx.message.delete()
            except discord.HTTPException:
                pass
        else:
            await ctx.defer(ephemeral=True)

        # purge() calls check() on every message, so this must be callable even with no member filter.
        if member is None:
            message_filter = lambda message: True
        else:
            message_filter = lambda message: message.author.id == member.id

        deleted = await ctx.channel.purge(limit=amount, check=message_filter)

        scope = f" from {member.mention}" if member else ""
        embed = base_embed(
            "Messages Purged",
            NEUTRAL_COLOR,
            f"Deleted **{len(deleted)}** message(s){scope} in {ctx.channel.mention}.",
        )
        embed.add_field(name="Purged by", value=ctx.author.mention, inline=True)
        if len(deleted) < amount:
            embed.set_footer(text="Discord can only bulk delete messages under 14 days old.")

        await ctx.send(embed=embed)
        await post_to_log_channel(ctx.guild, embed)

    @commands.hybrid_command(name="lockdown", description="Stop the lockdown role from sending messages")
    @app_commands.describe(
        channel="Channel to lock, defaults to the current one",
        reason="Why the channel is being locked",
    )
    @commands.guild_only()
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def lockdown(
        self,
        ctx: commands.Context,
        channel: Optional[discord.TextChannel] = None,
        *,
        reason: str = "No reason provided",
    ):
        target = channel or ctx.channel
        locked_role = await self.resolve_lockdown_role(ctx.guild)
        overwrite = target.overwrites_for(locked_role)

        # Remember the prior value so unlock restores it rather than assuming "allow".
        await save_channel_lock(ctx.guild.id, target.id, TRISTATE_TO_TEXT[overwrite.send_messages])
        overwrite.send_messages = False
        await target.set_permissions(locked_role, overwrite=overwrite, reason=reason)

        embed = base_embed("Channel Locked", MUTED_COLOR, f"{locked_role.mention} can no longer post in {target.mention}.")
        embed.add_field(name="Reason", value=reason, inline=False)
        embed.add_field(name="Locked by", value=ctx.author.mention, inline=True)
        await ctx.send(embed=embed)
        await post_to_log_channel(ctx.guild, embed)

    @commands.hybrid_command(name="unlock", description="Restore the lockdown role's ability to send messages")
    @app_commands.describe(channel="Channel to unlock, defaults to the current one")
    @commands.guild_only()
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def unlock(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None):
        target = channel or ctx.channel
        locked_role = await self.resolve_lockdown_role(ctx.guild)

        saved_state = await pop_channel_lock(ctx.guild.id, target.id)
        overwrite = target.overwrites_for(locked_role)
        overwrite.send_messages = TEXT_TO_TRISTATE.get(saved_state) if saved_state else None
        await target.set_permissions(locked_role, overwrite=overwrite)

        description = f"{locked_role.mention} can post in {target.mention} again."
        if saved_state is None:
            description += "\n*No lock record found, so the override was cleared to the category default.*"

        embed = base_embed("Channel Unlocked", SUCCESS_COLOR, description)
        embed.add_field(name="Unlocked by", value=ctx.author.mention, inline=True)
        await ctx.send(embed=embed)
        await post_to_log_channel(ctx.guild, embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(ChannelModeration(bot))

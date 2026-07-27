from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from database import pop_channel_lock, save_channel_lock
from embeds import MUTED_COLOR, SUCCESS_COLOR, base_embed, build_notice_embed
from modlog import post_to_log_channel

MAX_SLOWMODE_SECONDS = 21600  # Discord's own cap: 6 hours

TRISTATE_TO_TEXT = {True: "true", False: "false", None: "none"}
TEXT_TO_TRISTATE = {"true": True, "false": False, "none": None}


class ChannelModeration(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="slowmode", description="Set a channel's slowmode delay")
    @app_commands.describe(
        seconds="Delay between messages in seconds (0 disables, max 21600)",
        channel="Channel to apply to, defaults to the current one",
    )
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

    @commands.hybrid_command(name="lockdown", description="Stop @everyone from sending messages in a channel")
    @app_commands.describe(
        channel="Channel to lock, defaults to the current one",
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
        target = channel or ctx.channel
        everyone = ctx.guild.default_role
        overwrite = target.overwrites_for(everyone)

        # Remember the prior value so unlock restores it rather than assuming "allow".
        await save_channel_lock(ctx.guild.id, target.id, TRISTATE_TO_TEXT[overwrite.send_messages])
        overwrite.send_messages = False
        await target.set_permissions(everyone, overwrite=overwrite, reason=reason)

        embed = base_embed("Channel Locked", MUTED_COLOR, f"{target.mention} is now read-only.")
        embed.add_field(name="Reason", value=reason, inline=False)
        embed.add_field(name="Locked by", value=ctx.author.mention, inline=True)
        await ctx.send(embed=embed)
        await post_to_log_channel(ctx.guild, embed)

    @commands.hybrid_command(name="unlock", description="Restore @everyone's ability to send messages")
    @app_commands.describe(channel="Channel to unlock, defaults to the current one")
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def unlock(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None):
        target = channel or ctx.channel
        everyone = ctx.guild.default_role

        saved_state = await pop_channel_lock(ctx.guild.id, target.id)
        overwrite = target.overwrites_for(everyone)
        overwrite.send_messages = TEXT_TO_TRISTATE.get(saved_state) if saved_state else None
        await target.set_permissions(everyone, overwrite=overwrite)

        description = f"{target.mention} is open again."
        if saved_state is None:
            description += "\n*No lock record found, so permissions were reset to the category default.*"

        embed = base_embed("Channel Unlocked", SUCCESS_COLOR, description)
        embed.add_field(name="Unlocked by", value=ctx.author.mention, inline=True)
        await ctx.send(embed=embed)
        await post_to_log_channel(ctx.guild, embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(ChannelModeration(bot))

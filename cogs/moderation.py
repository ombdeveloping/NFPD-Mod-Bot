from datetime import timedelta
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from database import add_temp_ban, get_guild_settings, get_warn_count, remove_temp_ban
from embeds import build_dm_notice_embed, build_notice_embed
from modlog import announce_case, record_case

MAX_TIMEOUT_MINUTES = 40320  # Discord's own cap: 28 days


def outranked(actor: discord.Member, target: discord.Member) -> bool:
    if actor.id == actor.guild.owner_id:
        return False
    return target.top_role >= actor.top_role


async def notify_member(member: discord.Member, action_type: str, guild_name: str, reason: str) -> None:
    try:
        await member.send(embed=build_dm_notice_embed(action_type, guild_name, reason))
    except discord.Forbidden:
        pass


class Moderation(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def escalate_if_needed(self, ctx: commands.Context, member: discord.Member, warn_count: int) -> None:
        settings = await get_guild_settings(ctx.guild.id)
        reason = f"Automatic action after reaching {warn_count} warns"

        if settings["warn_ban_threshold"] == warn_count:
            action_type, perform = "ban", member.ban(reason=reason)
        elif settings["warn_kick_threshold"] == warn_count:
            action_type, perform = "kick", member.kick(reason=reason)
        elif settings["warn_mute_threshold"] == warn_count:
            until = discord.utils.utcnow() + timedelta(minutes=settings["warn_mute_minutes"] or 60)
            action_type, perform = "mute", member.timeout(until, reason=reason)
        else:
            return

        try:
            await perform
        except discord.Forbidden:
            await ctx.send(
                embed=build_notice_embed(
                    f"{member.mention} hit the warn threshold for an automatic {action_type}, "
                    "but I lack permission to do it.",
                    success=False,
                )
            )
            return

        await announce_case(ctx, member, action_type, reason, moderator=self.bot.user)

    @commands.hybrid_command(name="kick", description="Kick a member from this server")
    @app_commands.describe(member="The member to kick", reason="Why they're being kicked")
    @commands.has_permissions(kick_members=True)
    @commands.bot_has_permissions(kick_members=True)
    async def kick(self, ctx: commands.Context, member: discord.Member, *, reason: str = "No reason provided"):
        if outranked(ctx.author, member):
            await ctx.send(embed=build_notice_embed("You can't kick someone ranked equal or above you.", success=False))
            return

        await notify_member(member, "kick", ctx.guild.name, reason)
        await member.kick(reason=f"{ctx.author} ({ctx.author.id}): {reason}")
        await announce_case(ctx, member, "kick", reason)

    @commands.hybrid_command(name="ban", description="Ban a member, optionally for a limited time")
    @app_commands.describe(
        member="The member to ban",
        duration_minutes="Auto-unban after this many minutes (omit for permanent)",
        reason="Why they're being banned",
    )
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    async def ban(
        self,
        ctx: commands.Context,
        member: discord.Member,
        duration_minutes: Optional[int] = None,
        *,
        reason: str = "No reason provided",
    ):
        if outranked(ctx.author, member):
            await ctx.send(embed=build_notice_embed("You can't ban someone ranked equal or above you.", success=False))
            return
        if duration_minutes is not None and duration_minutes <= 0:
            await ctx.send(embed=build_notice_embed("Duration must be a positive number of minutes.", success=False))
            return

        await notify_member(member, "ban", ctx.guild.name, reason)
        await member.ban(reason=f"{ctx.author} ({ctx.author.id}): {reason}")

        embed = await record_case(ctx.guild, member, ctx.author, "ban", reason)
        if duration_minutes:
            unban_at = discord.utils.utcnow() + timedelta(minutes=duration_minutes)
            await add_temp_ban(ctx.guild.id, member.id, unban_at)
            embed.add_field(name="Expires", value=discord.utils.format_dt(unban_at, style="R"), inline=True)

        await ctx.send(embed=embed)

    @commands.hybrid_command(name="unban", description="Unban a user from this server")
    @app_commands.describe(user="The user to unban", reason="Why they're being unbanned")
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    async def unban(self, ctx: commands.Context, user: discord.User, *, reason: str = "No reason provided"):
        try:
            await ctx.guild.unban(user, reason=f"{ctx.author} ({ctx.author.id}): {reason}")
        except discord.NotFound:
            await ctx.send(embed=build_notice_embed(f"**{user}** isn't banned here.", success=False))
            return

        await remove_temp_ban(ctx.guild.id, user.id)
        await announce_case(ctx, user, "unban", reason)

    @commands.hybrid_command(name="warn", description="Warn a member")
    @app_commands.describe(member="The member to warn", reason="Why they're being warned")
    @commands.has_permissions(kick_members=True)
    async def warn(self, ctx: commands.Context, member: discord.Member, *, reason: str = "No reason provided"):
        await notify_member(member, "warn", ctx.guild.name, reason)
        await announce_case(ctx, member, "warn", reason)

        warn_count = await get_warn_count(ctx.guild.id, member.id)
        await self.escalate_if_needed(ctx, member, warn_count)

    @commands.hybrid_command(name="mute", description="Timeout a member for a set duration")
    @app_commands.describe(
        member="The member to mute",
        duration_minutes="How long to mute for, in minutes (max 40320 = 28 days)",
        reason="Why they're being muted",
    )
    @commands.has_permissions(moderate_members=True)
    @commands.bot_has_permissions(moderate_members=True)
    async def mute(
        self,
        ctx: commands.Context,
        member: discord.Member,
        duration_minutes: int,
        *,
        reason: str = "No reason provided",
    ):
        if outranked(ctx.author, member):
            await ctx.send(embed=build_notice_embed("You can't mute someone ranked equal or above you.", success=False))
            return
        if duration_minutes <= 0 or duration_minutes > MAX_TIMEOUT_MINUTES:
            await ctx.send(
                embed=build_notice_embed(
                    f"Duration must be between 1 and {MAX_TIMEOUT_MINUTES} minutes (28 days).", success=False
                )
            )
            return

        until = discord.utils.utcnow() + timedelta(minutes=duration_minutes)
        await member.timeout(until, reason=f"{ctx.author} ({ctx.author.id}): {reason}")
        await notify_member(member, "mute", ctx.guild.name, reason)

        embed = await record_case(ctx.guild, member, ctx.author, "mute", reason)
        embed.add_field(name="Expires", value=discord.utils.format_dt(until, style="R"), inline=True)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="unmute", description="Remove an active timeout from a member")
    @app_commands.describe(member="The member to unmute", reason="Why they're being unmuted")
    @commands.has_permissions(moderate_members=True)
    @commands.bot_has_permissions(moderate_members=True)
    async def unmute(self, ctx: commands.Context, member: discord.Member, *, reason: str = "No reason provided"):
        if member.timed_out_until is None:
            await ctx.send(embed=build_notice_embed(f"{member.mention} isn't currently muted.", success=False))
            return

        await member.timeout(None, reason=f"{ctx.author} ({ctx.author.id}): {reason}")
        await announce_case(ctx, member, "unmute", reason)


async def setup(bot: commands.Bot):
    await bot.add_cog(Moderation(bot))

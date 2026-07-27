from datetime import timedelta
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from database import (
    add_case,
    add_temp_ban,
    get_guild_settings,
    get_warn_count,
    remove_temp_ban,
)
from embeds import build_case_embed, build_dm_notice_embed
from modlog import post_to_log_channel

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


async def apply_warn_escalation(bot: commands.Bot, ctx: commands.Context, member: discord.Member, warn_count: int) -> None:
    settings = await get_guild_settings(ctx.guild.id)
    reason = f"Automatic action: reached {warn_count} warns"

    if settings["warn_ban_threshold"] and warn_count == settings["warn_ban_threshold"]:
        await _run_escalation(bot, ctx, member, "ban", reason, lambda: member.ban(reason=reason))
    elif settings["warn_kick_threshold"] and warn_count == settings["warn_kick_threshold"]:
        await _run_escalation(bot, ctx, member, "kick", reason, lambda: member.kick(reason=reason))
    elif settings["warn_mute_threshold"] and warn_count == settings["warn_mute_threshold"]:
        until = discord.utils.utcnow() + timedelta(minutes=settings["warn_mute_minutes"] or 60)
        await _run_escalation(bot, ctx, member, "mute", reason, lambda: member.timeout(until, reason=reason))


async def _run_escalation(bot, ctx, member, action_type, reason, perform_action) -> None:
    try:
        await perform_action()
    except discord.Forbidden:
        await ctx.send(
            f"{member.mention} reached the warn threshold for an automatic {action_type}, "
            "but I don't have permission to do that."
        )
        return

    case_id = await add_case(ctx.guild.id, member.id, bot.user.id, action_type, reason)
    embed = build_case_embed(action_type, member, bot.user, reason, case_id)
    await ctx.send(embed=embed)
    await post_to_log_channel(ctx.guild, embed)


class Moderation(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="kick", description="Kick a member from this server")
    @app_commands.describe(member="The member to kick", reason="Why they're being kicked")
    @commands.has_permissions(kick_members=True)
    @commands.bot_has_permissions(kick_members=True)
    async def kick(self, ctx: commands.Context, member: discord.Member, *, reason: str = "No reason provided"):
        if outranked(ctx.author, member):
            await ctx.send("You can't kick someone with an equal or higher role than you.")
            return

        await notify_member(member, "kick", ctx.guild.name, reason)
        await member.kick(reason=f"{ctx.author} ({ctx.author.id}): {reason}")
        case_id = await add_case(ctx.guild.id, member.id, ctx.author.id, "kick", reason)

        embed = build_case_embed("kick", member, ctx.author, reason, case_id)
        await ctx.send(embed=embed)
        await post_to_log_channel(ctx.guild, embed)

    @commands.hybrid_command(name="ban", description="Ban a member from this server")
    @app_commands.describe(
        member="The member to ban",
        duration_minutes="If set, automatically unban after this many minutes (omit for a permanent ban)",
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
            await ctx.send("You can't ban someone with an equal or higher role than you.")
            return
        if duration_minutes is not None and duration_minutes <= 0:
            await ctx.send("Duration must be a positive number of minutes.")
            return

        await notify_member(member, "ban", ctx.guild.name, reason)
        await member.ban(reason=f"{ctx.author} ({ctx.author.id}): {reason}")
        case_id = await add_case(ctx.guild.id, member.id, ctx.author.id, "ban", reason)

        embed = build_case_embed("ban", member, ctx.author, reason, case_id)
        if duration_minutes:
            unban_at = discord.utils.utcnow() + timedelta(minutes=duration_minutes)
            await add_temp_ban(ctx.guild.id, member.id, unban_at)
            embed.add_field(name="Expires", value=discord.utils.format_dt(unban_at, style="R"), inline=False)

        await ctx.send(embed=embed)
        await post_to_log_channel(ctx.guild, embed)

    @commands.hybrid_command(name="unban", description="Unban a user from this server")
    @app_commands.describe(user="The user to unban", reason="Why they're being unbanned")
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    async def unban(self, ctx: commands.Context, user: discord.User, *, reason: str = "No reason provided"):
        try:
            await ctx.guild.unban(user, reason=f"{ctx.author} ({ctx.author.id}): {reason}")
        except discord.NotFound:
            await ctx.send(f"{user} isn't banned here.")
            return

        await remove_temp_ban(ctx.guild.id, user.id)
        case_id = await add_case(ctx.guild.id, user.id, ctx.author.id, "unban", reason)

        embed = build_case_embed("unban", user, ctx.author, reason, case_id)
        await ctx.send(embed=embed)
        await post_to_log_channel(ctx.guild, embed)

    @commands.hybrid_command(name="warn", description="Warn a member")
    @app_commands.describe(member="The member to warn", reason="Why they're being warned")
    @commands.has_permissions(kick_members=True)
    async def warn(self, ctx: commands.Context, member: discord.Member, *, reason: str = "No reason provided"):
        case_id = await add_case(ctx.guild.id, member.id, ctx.author.id, "warn", reason)
        await notify_member(member, "warn", ctx.guild.name, reason)

        embed = build_case_embed("warn", member, ctx.author, reason, case_id)
        await ctx.send(embed=embed)
        await post_to_log_channel(ctx.guild, embed)

        warn_count = await get_warn_count(ctx.guild.id, member.id)
        await apply_warn_escalation(self.bot, ctx, member, warn_count)

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
            await ctx.send("You can't mute someone with an equal or higher role than you.")
            return
        if duration_minutes <= 0 or duration_minutes > MAX_TIMEOUT_MINUTES:
            await ctx.send(f"Duration must be between 1 and {MAX_TIMEOUT_MINUTES} minutes (28 days).")
            return

        until = discord.utils.utcnow() + timedelta(minutes=duration_minutes)
        await member.timeout(until, reason=f"{ctx.author} ({ctx.author.id}): {reason}")
        case_id = await add_case(ctx.guild.id, member.id, ctx.author.id, "mute", reason)
        await notify_member(member, "mute", ctx.guild.name, reason)

        embed = build_case_embed("mute", member, ctx.author, reason, case_id)
        await ctx.send(embed=embed)
        await post_to_log_channel(ctx.guild, embed)

    @commands.hybrid_command(name="unmute", description="Remove an active timeout from a member")
    @app_commands.describe(member="The member to unmute", reason="Why they're being unmuted")
    @commands.has_permissions(moderate_members=True)
    @commands.bot_has_permissions(moderate_members=True)
    async def unmute(self, ctx: commands.Context, member: discord.Member, *, reason: str = "No reason provided"):
        if member.timed_out_until is None:
            await ctx.send(f"{member.mention} isn't currently muted.")
            return

        await member.timeout(None, reason=f"{ctx.author} ({ctx.author.id}): {reason}")
        case_id = await add_case(ctx.guild.id, member.id, ctx.author.id, "unmute", reason)

        embed = build_case_embed("unmute", member, ctx.author, reason, case_id)
        await ctx.send(embed=embed)
        await post_to_log_channel(ctx.guild, embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Moderation(bot))

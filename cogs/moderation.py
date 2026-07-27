from datetime import timedelta

import discord
from discord import app_commands
from discord.ext import commands

from database import add_case, get_cases_for_user
from embeds import build_case_embed, build_dm_notice_embed

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
        await ctx.send(embed=build_case_embed("kick", member, ctx.author, reason, case_id))

    @commands.hybrid_command(name="ban", description="Ban a member from this server")
    @app_commands.describe(member="The member to ban", reason="Why they're being banned")
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    async def ban(self, ctx: commands.Context, member: discord.Member, *, reason: str = "No reason provided"):
        if outranked(ctx.author, member):
            await ctx.send("You can't ban someone with an equal or higher role than you.")
            return

        await notify_member(member, "ban", ctx.guild.name, reason)
        await member.ban(reason=f"{ctx.author} ({ctx.author.id}): {reason}")
        case_id = await add_case(ctx.guild.id, member.id, ctx.author.id, "ban", reason)
        await ctx.send(embed=build_case_embed("ban", member, ctx.author, reason, case_id))

    @commands.hybrid_command(name="warn", description="Warn a member")
    @app_commands.describe(member="The member to warn", reason="Why they're being warned")
    @commands.has_permissions(kick_members=True)
    async def warn(self, ctx: commands.Context, member: discord.Member, *, reason: str = "No reason provided"):
        case_id = await add_case(ctx.guild.id, member.id, ctx.author.id, "warn", reason)
        await notify_member(member, "warn", ctx.guild.name, reason)
        await ctx.send(embed=build_case_embed("warn", member, ctx.author, reason, case_id))

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
        await ctx.send(embed=build_case_embed("mute", member, ctx.author, reason, case_id))

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
        await ctx.send(embed=build_case_embed("unmute", member, ctx.author, reason, case_id))

    @commands.hybrid_command(name="cases", description="View the moderation history for a member")
    @app_commands.describe(member="The member to look up")
    @commands.has_permissions(kick_members=True)
    async def cases(self, ctx: commands.Context, member: discord.Member):
        case_rows = await get_cases_for_user(ctx.guild.id, member.id)

        if not case_rows:
            await ctx.send(f"{member.mention} has no cases on record.")
            return

        embed = discord.Embed(
            title=f"Case History \u2014 {member}",
            color=discord.Color.blurple(),
            timestamp=discord.utils.utcnow(),
        )
        embed.set_thumbnail(url=member.display_avatar.url)

        for row in case_rows[:10]:
            moderator = ctx.guild.get_member(row["moderator_id"])
            moderator_name = moderator.mention if moderator else f"ID {row['moderator_id']}"
            embed.add_field(
                name=f"Case #{row['id']} \u2014 {row['action_type'].upper()}",
                value=f"By {moderator_name}\nReason: {row['reason']}\n{row['created_at']}",
                inline=False,
            )

        if len(case_rows) > 10:
            embed.set_footer(text=f"Showing 10 of {len(case_rows)} cases")

        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Moderation(bot))

from datetime import timedelta

import discord
from discord import app_commands
from discord.ext import commands

from config import GLOBAL_ACTION_ROLE_ID, OWNER_IDS
from database import add_case
from embeds import build_dm_notice_embed, build_summary_embed

MAX_TIMEOUT_MINUTES = 40320  # Discord's own cap: 28 days


def is_global_moderator():
    async def predicate(ctx: commands.Context) -> bool:
        if ctx.author.id in OWNER_IDS:
            return True
        if GLOBAL_ACTION_ROLE_ID is None:
            return False
        author_roles = getattr(ctx.author, "roles", [])
        return discord.utils.get(author_roles, id=GLOBAL_ACTION_ROLE_ID) is not None

    return commands.check(predicate)


async def notify_user(user: discord.User, action_type: str, reason: str) -> None:
    location_name = "the servers you were in" if action_type == "global_kick" else "all servers"
    try:
        await user.send(embed=build_dm_notice_embed(action_type, location_name, reason))
    except discord.Forbidden:
        pass


class GlobalModeration(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(
        name="globalkick",
        description="Kick a user from every server this bot shares with them",
    )
    @app_commands.describe(user="The user to kick everywhere", reason="Why they're being kicked")
    @is_global_moderator()
    async def globalkick(self, ctx: commands.Context, user: discord.User, *, reason: str = "No reason provided"):
        await ctx.defer()
        await notify_user(user, "global_kick", reason)

        kicked_from, failed_in = [], []
        for guild in self.bot.guilds:
            member = guild.get_member(user.id)
            if member is None:
                continue
            try:
                await member.kick(reason=f"Global kick by {ctx.author} ({ctx.author.id}): {reason}")
                await add_case(guild.id, user.id, ctx.author.id, "global_kick", reason)
                kicked_from.append(guild.name)
            except discord.Forbidden:
                failed_in.append(guild.name)

        await ctx.send(embed=build_summary_embed("global_kick", user, kicked_from, failed_in))

    @commands.hybrid_command(
        name="globalban",
        description="Ban a user from every server this bot is in",
    )
    @app_commands.describe(user="The user to ban everywhere", reason="Why they're being banned")
    @is_global_moderator()
    async def globalban(self, ctx: commands.Context, user: discord.User, *, reason: str = "No reason provided"):
        await ctx.defer()
        await notify_user(user, "global_ban", reason)

        banned_from, failed_in = [], []
        for guild in self.bot.guilds:
            try:
                await guild.ban(
                    user,
                    reason=f"Global ban by {ctx.author} ({ctx.author.id}): {reason}",
                    delete_message_seconds=0,
                )
                await add_case(guild.id, user.id, ctx.author.id, "global_ban", reason)
                banned_from.append(guild.name)
            except (discord.Forbidden, discord.HTTPException):
                failed_in.append(guild.name)

        await ctx.send(embed=build_summary_embed("global_ban", user, banned_from, failed_in))

    @commands.hybrid_command(
        name="globalunban",
        description="Unban a user from every server this bot is in",
    )
    @app_commands.describe(user="The user to unban everywhere", reason="Why they're being unbanned")
    @is_global_moderator()
    async def globalunban(self, ctx: commands.Context, user: discord.User, *, reason: str = "No reason provided"):
        await ctx.defer()

        unbanned_from, failed_in = [], []
        for guild in self.bot.guilds:
            try:
                await guild.unban(user, reason=f"Global unban by {ctx.author} ({ctx.author.id}): {reason}")
                await add_case(guild.id, user.id, ctx.author.id, "global_unban", reason)
                unbanned_from.append(guild.name)
            except discord.NotFound:
                continue  # user wasn't banned there, nothing to do
            except discord.Forbidden:
                failed_in.append(guild.name)

        await ctx.send(embed=build_summary_embed("global_unban", user, unbanned_from, failed_in))

    @commands.hybrid_command(
        name="globalmute",
        description="Timeout a user in every server this bot shares with them",
    )
    @app_commands.describe(
        user="The user to mute everywhere",
        duration_minutes="How long to mute for, in minutes (max 40320 = 28 days)",
        reason="Why they're being muted",
    )
    @is_global_moderator()
    async def globalmute(
        self,
        ctx: commands.Context,
        user: discord.User,
        duration_minutes: int,
        *,
        reason: str = "No reason provided",
    ):
        if duration_minutes <= 0 or duration_minutes > MAX_TIMEOUT_MINUTES:
            await ctx.send(f"Duration must be between 1 and {MAX_TIMEOUT_MINUTES} minutes (28 days).")
            return

        await ctx.defer()
        await notify_user(user, "global_mute", reason)
        until = discord.utils.utcnow() + timedelta(minutes=duration_minutes)

        muted_in, failed_in = [], []
        for guild in self.bot.guilds:
            member = guild.get_member(user.id)
            if member is None:
                continue
            try:
                await member.timeout(until, reason=f"Global mute by {ctx.author} ({ctx.author.id}): {reason}")
                await add_case(guild.id, user.id, ctx.author.id, "global_mute", reason)
                muted_in.append(guild.name)
            except discord.Forbidden:
                failed_in.append(guild.name)

        await ctx.send(embed=build_summary_embed("global_mute", user, muted_in, failed_in))

    @commands.hybrid_command(
        name="globalunmute",
        description="Remove an active timeout from a user in every server this bot shares with them",
    )
    @app_commands.describe(user="The user to unmute everywhere", reason="Why they're being unmuted")
    @is_global_moderator()
    async def globalunmute(self, ctx: commands.Context, user: discord.User, *, reason: str = "No reason provided"):
        await ctx.defer()

        unmuted_in, failed_in = [], []
        for guild in self.bot.guilds:
            member = guild.get_member(user.id)
            if member is None:
                continue
            try:
                await member.timeout(None, reason=f"Global unmute by {ctx.author} ({ctx.author.id}): {reason}")
                await add_case(guild.id, user.id, ctx.author.id, "global_unmute", reason)
                unmuted_in.append(guild.name)
            except discord.Forbidden:
                failed_in.append(guild.name)

        await ctx.send(embed=build_summary_embed("global_unmute", user, unmuted_in, failed_in))


async def setup(bot: commands.Bot):
    await bot.add_cog(GlobalModeration(bot))

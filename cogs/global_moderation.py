import discord
from discord import app_commands
from discord.ext import commands

from config import GLOBAL_ACTION_ROLE_ID, OWNER_IDS
from database import add_case


def is_global_moderator():
    async def predicate(ctx: commands.Context) -> bool:
        if ctx.author.id in OWNER_IDS:
            return True
        if GLOBAL_ACTION_ROLE_ID is None:
            return False
        author_roles = getattr(ctx.author, "roles", [])
        return discord.utils.get(author_roles, id=GLOBAL_ACTION_ROLE_ID) is not None

    return commands.check(predicate)


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

        summary = f"Kicked {user} from {len(kicked_from)} server(s)."
        if failed_in:
            summary += f" Missing permissions in: {', '.join(failed_in)}."
        await ctx.send(summary)

    @commands.hybrid_command(
        name="globalban",
        description="Ban a user from every server this bot is in",
    )
    @app_commands.describe(user="The user to ban everywhere", reason="Why they're being banned")
    @is_global_moderator()
    async def globalban(self, ctx: commands.Context, user: discord.User, *, reason: str = "No reason provided"):
        await ctx.defer()

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

        summary = f"Banned {user} from {len(banned_from)} server(s)."
        if failed_in:
            summary += f" Failed in: {', '.join(failed_in)}."
        await ctx.send(summary)


async def setup(bot: commands.Bot):
    await bot.add_cog(GlobalModeration(bot))

import discord
from discord import app_commands
from discord.ext import commands

from database import add_case, get_cases_for_user


def outranked(actor: discord.Member, target: discord.Member) -> bool:
    if actor.id == actor.guild.owner_id:
        return False
    return target.top_role >= actor.top_role


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

        await member.kick(reason=f"{ctx.author} ({ctx.author.id}): {reason}")
        case_id = await add_case(ctx.guild.id, member.id, ctx.author.id, "kick", reason)
        await ctx.send(f"Kicked {member} (case #{case_id}). Reason: {reason}")

    @commands.hybrid_command(name="ban", description="Ban a member from this server")
    @app_commands.describe(member="The member to ban", reason="Why they're being banned")
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    async def ban(self, ctx: commands.Context, member: discord.Member, *, reason: str = "No reason provided"):
        if outranked(ctx.author, member):
            await ctx.send("You can't ban someone with an equal or higher role than you.")
            return

        await member.ban(reason=f"{ctx.author} ({ctx.author.id}): {reason}")
        case_id = await add_case(ctx.guild.id, member.id, ctx.author.id, "ban", reason)
        await ctx.send(f"Banned {member} (case #{case_id}). Reason: {reason}")

    @commands.hybrid_command(name="warn", description="Warn a member")
    @app_commands.describe(member="The member to warn", reason="Why they're being warned")
    @commands.has_permissions(kick_members=True)
    async def warn(self, ctx: commands.Context, member: discord.Member, *, reason: str = "No reason provided"):
        case_id = await add_case(ctx.guild.id, member.id, ctx.author.id, "warn", reason)

        try:
            await member.send(f"You were warned in {ctx.guild.name}. Reason: {reason}")
        except discord.Forbidden:
            pass

        await ctx.send(f"Warned {member} (case #{case_id}). Reason: {reason}")

    @commands.hybrid_command(name="cases", description="View the moderation history for a member")
    @app_commands.describe(member="The member to look up")
    @commands.has_permissions(kick_members=True)
    async def cases(self, ctx: commands.Context, member: discord.Member):
        case_rows = await get_cases_for_user(ctx.guild.id, member.id)

        if not case_rows:
            await ctx.send(f"{member} has no cases on record.")
            return

        embed = discord.Embed(title=f"Case history for {member}", color=discord.Color.orange())
        for row in case_rows[:10]:
            moderator = ctx.guild.get_member(row["moderator_id"])
            moderator_name = moderator.mention if moderator else f"ID {row['moderator_id']}"
            embed.add_field(
                name=f"Case #{row['id']} — {row['action_type'].upper()}",
                value=f"By {moderator_name}\nReason: {row['reason']}\n{row['created_at']}",
                inline=False,
            )

        if len(case_rows) > 10:
            embed.set_footer(text=f"Showing 10 of {len(case_rows)} cases")

        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Moderation(bot))

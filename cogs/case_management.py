import discord
from discord import app_commands
from discord.ext import commands

from database import (
    delete_case,
    get_action_counts,
    get_case_by_id,
    get_cases_for_user,
    get_most_warned_users,
    get_top_moderators,
    update_case_reason,
)
from embeds import ACTION_COLORS
from modlog import post_to_log_channel
from views import CasesPaginatorView


class CaseManagement(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="cases", description="View the moderation history for a member")
    @app_commands.describe(member="The member to look up")
    @commands.has_permissions(kick_members=True)
    async def cases(self, ctx: commands.Context, member: discord.Member):
        case_rows = await get_cases_for_user(ctx.guild.id, member.id)

        if not case_rows:
            await ctx.send(f"{member.mention} has no cases on record.")
            return

        view = CasesPaginatorView(ctx.author.id, member, case_rows, ctx.guild)
        view.message = await ctx.send(embed=view.build_embed(), view=view)

    @commands.hybrid_command(name="casesearch", description="Look up a single case by its ID")
    @app_commands.describe(case_id="The case number to look up")
    @commands.has_permissions(kick_members=True)
    async def casesearch(self, ctx: commands.Context, case_id: int):
        case_row = await get_case_by_id(ctx.guild.id, case_id)
        if case_row is None:
            await ctx.send(f"No case #{case_id} found in this server.")
            return

        target_user = self.bot.get_user(case_row["user_id"]) or await self.bot.fetch_user(case_row["user_id"])
        moderator = ctx.guild.get_member(case_row["moderator_id"])
        moderator_name = moderator.mention if moderator else f"ID {case_row['moderator_id']}"

        embed = discord.Embed(
            title=f"Case #{case_row['id']} \u2014 {case_row['action_type'].upper()}",
            color=ACTION_COLORS.get(case_row["action_type"], discord.Color.blurple()),
            timestamp=discord.utils.utcnow(),
        )
        embed.set_thumbnail(url=target_user.display_avatar.url)
        embed.add_field(name="User", value=f"{target_user.mention}\n`{target_user.id}`", inline=True)
        embed.add_field(name="Moderator", value=moderator_name, inline=True)
        embed.add_field(name="Reason", value=case_row["reason"], inline=False)
        embed.set_footer(text=case_row["created_at"])
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="caseedit", description="Edit the reason on an existing case")
    @app_commands.describe(case_id="The case number to edit", new_reason="The corrected reason")
    @commands.has_permissions(manage_guild=True)
    async def caseedit(self, ctx: commands.Context, case_id: int, *, new_reason: str):
        updated = await update_case_reason(ctx.guild.id, case_id, new_reason)
        if not updated:
            await ctx.send(f"No case #{case_id} found in this server.")
            return

        embed = discord.Embed(
            title=f"Case #{case_id} Updated",
            description=f"New reason: {new_reason}",
            color=discord.Color.blurple(),
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(name="Edited by", value=ctx.author.mention)
        await ctx.send(embed=embed)
        await post_to_log_channel(ctx.guild, embed)

    @commands.hybrid_command(name="casedelete", description="Permanently delete a case record")
    @app_commands.describe(case_id="The case number to delete")
    @commands.has_permissions(manage_guild=True)
    async def casedelete(self, ctx: commands.Context, case_id: int):
        deleted = await delete_case(ctx.guild.id, case_id)
        if not deleted:
            await ctx.send(f"No case #{case_id} found in this server.")
            return

        embed = discord.Embed(
            title=f"Case #{case_id} Deleted",
            color=discord.Color.dark_grey(),
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(name="Deleted by", value=ctx.author.mention)
        await ctx.send(embed=embed)
        await post_to_log_channel(ctx.guild, embed)

    @commands.hybrid_command(name="modstats", description="Show moderation activity stats for this server")
    @commands.has_permissions(kick_members=True)
    async def modstats(self, ctx: commands.Context):
        action_counts = await get_action_counts(ctx.guild.id)
        top_moderators = await get_top_moderators(ctx.guild.id)
        most_warned = await get_most_warned_users(ctx.guild.id)

        embed = discord.Embed(title=f"Moderation Stats \u2014 {ctx.guild.name}", color=discord.Color.blurple())

        if action_counts:
            counts_text = "\n".join(
                f"{row['action_type'].replace('_', ' ').title()}: {row['total']}" for row in action_counts
            )
        else:
            counts_text = "No cases recorded yet."
        embed.add_field(name="Actions Logged", value=counts_text, inline=False)

        if top_moderators:
            lines = []
            for row in top_moderators:
                moderator = ctx.guild.get_member(row["moderator_id"])
                name = moderator.mention if moderator else f"ID {row['moderator_id']}"
                lines.append(f"{name}: {row['total']}")
            embed.add_field(name="Most Active Moderators", value="\n".join(lines), inline=False)

        if most_warned:
            lines = []
            for row in most_warned:
                member = ctx.guild.get_member(row["user_id"])
                name = member.mention if member else f"ID {row['user_id']}"
                lines.append(f"{name}: {row['total']}")
            embed.add_field(name="Most Warned Members", value="\n".join(lines), inline=False)

        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(CaseManagement(bot))

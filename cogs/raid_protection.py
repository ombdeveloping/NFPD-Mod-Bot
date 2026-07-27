from datetime import datetime, timezone

import discord
from discord.ext import commands

from database import get_guild_settings
from modlog import post_to_log_channel


class RaidProtection(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        settings = await get_guild_settings(member.guild.id)
        min_age_hours = settings["raid_min_account_age_hours"]
        if not min_age_hours:
            return

        account_age = datetime.now(timezone.utc) - member.created_at
        if account_age.total_seconds() >= min_age_hours * 3600:
            return

        embed = discord.Embed(
            title="New Account Alert",
            description=f"{member.mention} joined with an account under {min_age_hours}h old.",
            color=discord.Color.gold(),
            timestamp=discord.utils.utcnow(),
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(
            name="Account Created", value=discord.utils.format_dt(member.created_at, style="R"), inline=True
        )
        embed.add_field(name="User ID", value=f"`{member.id}`", inline=True)

        await post_to_log_channel(member.guild, embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(RaidProtection(bot))

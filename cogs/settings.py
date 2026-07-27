import discord
from discord import app_commands
from discord.ext import commands

from database import set_log_channel, set_raid_protection, set_warn_thresholds


class Settings(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="setlogchannel", description="Set the channel where moderation actions are logged")
    @app_commands.describe(channel="The channel to post mod-log entries to")
    @commands.has_permissions(manage_guild=True)
    async def setlogchannel(self, ctx: commands.Context, channel: discord.TextChannel):
        await set_log_channel(ctx.guild.id, channel.id)
        await ctx.send(f"Mod-log channel set to {channel.mention}.")

    @commands.hybrid_command(
        name="setraidprotection",
        description="Flag new members whose account is younger than this many hours (0 to disable)",
    )
    @app_commands.describe(
        minimum_account_age_hours="Minimum account age in hours; younger accounts get flagged in the log channel"
    )
    @commands.has_permissions(manage_guild=True)
    async def setraidprotection(self, ctx: commands.Context, minimum_account_age_hours: int):
        if minimum_account_age_hours < 0:
            await ctx.send("Minimum account age can't be negative.")
            return

        await set_raid_protection(ctx.guild.id, minimum_account_age_hours or None)
        if minimum_account_age_hours == 0:
            await ctx.send("Raid protection disabled.")
        else:
            await ctx.send(
                f"Raid protection enabled: accounts younger than {minimum_account_age_hours}h will be flagged "
                "in the mod-log channel when they join. Set one with /setlogchannel if you haven't."
            )

    @commands.hybrid_command(
        name="setwarnthresholds",
        description="Configure automatic escalation based on warn count (0 disables a threshold)",
    )
    @app_commands.describe(
        mute_at="Warn count that triggers an automatic mute (0 to disable)",
        mute_minutes="How long the automatic mute lasts, in minutes",
        kick_at="Warn count that triggers an automatic kick (0 to disable)",
        ban_at="Warn count that triggers an automatic ban (0 to disable)",
    )
    @commands.has_permissions(manage_guild=True)
    async def setwarnthresholds(
        self,
        ctx: commands.Context,
        mute_at: int = 0,
        mute_minutes: int = 60,
        kick_at: int = 0,
        ban_at: int = 0,
    ):
        active_thresholds = [value for value in (mute_at, kick_at, ban_at) if value > 0]
        if active_thresholds != sorted(active_thresholds):
            await ctx.send("Thresholds must increase in severity: mute_at < kick_at < ban_at.")
            return

        await set_warn_thresholds(
            ctx.guild.id,
            mute_at or None,
            mute_minutes if mute_at else None,
            kick_at or None,
            ban_at or None,
        )
        await ctx.send(
            "Warn escalation updated:\n"
            f"- Mute at {mute_at or 'disabled'} warns" + (f" for {mute_minutes}m" if mute_at else "") + "\n"
            f"- Kick at {kick_at or 'disabled'} warns\n"
            f"- Ban at {ban_at or 'disabled'} warns"
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Settings(bot))

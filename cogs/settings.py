import discord
from discord import app_commands
from discord.ext import commands

from database import get_guild_settings, set_lockdown_role, set_log_channel, set_raid_protection, set_warn_thresholds
from embeds import NEUTRAL_COLOR, base_embed, build_notice_embed
from modlog import check_log_channel


def describe_threshold(count: int | None, suffix: str = "") -> str:
    return f"{count} warns{suffix}" if count else "Disabled"


class Settings(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="settings", description="Show this server's moderation configuration")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def settings(self, ctx: commands.Context):
        config = await get_guild_settings(ctx.guild.id)
        log_channel = ctx.guild.get_channel(config["log_channel_id"]) if config["log_channel_id"] else None
        lockdown_role = ctx.guild.get_role(config["lockdown_role_id"]) if config["lockdown_role_id"] else None
        raid_hours = config["raid_min_account_age_hours"]
        mute_minutes = config["warn_mute_minutes"]

        embed = base_embed(f"Settings  \u2022  {ctx.guild.name}", NEUTRAL_COLOR)
        embed.add_field(name="Mod-log channel", value=log_channel.mention if log_channel else "Not set", inline=False)
        embed.add_field(
            name="Lockdown role",
            value=lockdown_role.mention if lockdown_role else "Not set, falls back to @everyone",
            inline=False,
        )
        embed.add_field(
            name="Raid protection",
            value=f"Flag accounts under {raid_hours}h old" if raid_hours else "Disabled",
            inline=False,
        )
        embed.add_field(
            name="Warn escalation",
            value=(
                f"Mute at {describe_threshold(config['warn_mute_threshold'], f' for {mute_minutes}m' if mute_minutes else '')}\n"
                f"Kick at {describe_threshold(config['warn_kick_threshold'])}\n"
                f"Ban at {describe_threshold(config['warn_ban_threshold'])}"
            ),
            inline=False,
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="setlogchannel", description="Set where moderation actions are logged")
    @app_commands.describe(channel="The channel to post mod-log entries to")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def setlogchannel(self, ctx: commands.Context, channel: discord.TextChannel):
        await set_log_channel(ctx.guild.id, channel.id)
        ok, detail = await check_log_channel(ctx.guild)
        message = f"Mod-log channel set to {channel.mention}."
        if not ok:
            message += f"\n\u26A0 {detail}"
        await ctx.send(embed=build_notice_embed(message, success=ok))

    @commands.hybrid_command(name="testlog", description="Send a test message to the configured mod-log channel")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def testlog(self, ctx: commands.Context):
        ok, detail = await check_log_channel(ctx.guild)
        if not ok:
            await ctx.send(embed=build_notice_embed(detail, success=False))
            return

        config = await get_guild_settings(ctx.guild.id)
        channel = ctx.guild.get_channel(config["log_channel_id"])
        try:
            await channel.send(embed=base_embed("Test Message", NEUTRAL_COLOR, "If you can see this, logging works."))
        except discord.HTTPException as error:
            await ctx.send(embed=build_notice_embed(f"Channel looked reachable, but sending failed: `{error}`", success=False))
            return

        await ctx.send(embed=build_notice_embed(f"Test message sent to {channel.mention}."))

    @commands.hybrid_command(name="setlockdownrole", description="Set which role /lockdown silences")
    @app_commands.describe(role="The role that loses send-message access during a lockdown")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def setlockdownrole(self, ctx: commands.Context, role: discord.Role):
        await set_lockdown_role(ctx.guild.id, role.id)
        await ctx.send(embed=build_notice_embed(f"/lockdown will now silence {role.mention}."))

    @commands.hybrid_command(
        name="setraidprotection",
        description="Flag joins from accounts younger than this many hours (0 disables)",
    )
    @app_commands.describe(minimum_account_age_hours="Minimum account age in hours, or 0 to disable")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def setraidprotection(self, ctx: commands.Context, minimum_account_age_hours: int):
        if minimum_account_age_hours < 0:
            await ctx.send(embed=build_notice_embed("Minimum account age can't be negative.", success=False))
            return

        await set_raid_protection(ctx.guild.id, minimum_account_age_hours or None)
        if minimum_account_age_hours == 0:
            await ctx.send(embed=build_notice_embed("Raid protection disabled."))
            return

        await ctx.send(
            embed=build_notice_embed(
                f"Accounts younger than **{minimum_account_age_hours}h** will be flagged in the mod-log channel."
            )
        )

    @commands.hybrid_command(
        name="setwarnthresholds",
        description="Auto-escalate at set warn counts (0 disables that step)",
    )
    @app_commands.describe(
        mute_at="Warn count that triggers an automatic mute (0 to disable)",
        mute_minutes="How long the automatic mute lasts, in minutes",
        kick_at="Warn count that triggers an automatic kick (0 to disable)",
        ban_at="Warn count that triggers an automatic ban (0 to disable)",
    )
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def setwarnthresholds(
        self,
        ctx: commands.Context,
        mute_at: int = 0,
        mute_minutes: int = 60,
        kick_at: int = 0,
        ban_at: int = 0,
    ):
        active = [value for value in (mute_at, kick_at, ban_at) if value > 0]
        if active != sorted(active) or len(active) != len(set(active)):
            await ctx.send(
                embed=build_notice_embed(
                    "Thresholds must increase in severity, with no ties: mute < kick < ban.", success=False
                )
            )
            return

        await set_warn_thresholds(
            ctx.guild.id, mute_at or None, mute_minutes if mute_at else None, kick_at or None, ban_at or None
        )

        embed = base_embed("Warn Escalation Updated", NEUTRAL_COLOR)
        embed.add_field(name="Mute", value=describe_threshold(mute_at, f" for {mute_minutes}m"), inline=True)
        embed.add_field(name="Kick", value=describe_threshold(kick_at), inline=True)
        embed.add_field(name="Ban", value=describe_threshold(ban_at), inline=True)
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Settings(bot))

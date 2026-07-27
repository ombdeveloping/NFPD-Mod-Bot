import math
import os
import platform
from datetime import timedelta

import discord
from discord.ext import commands

import config
import database
import diagnostics
from embeds import NEUTRAL_COLOR, base_embed, clamp
from modlog import check_log_channel

try:
    import psutil
    _process = psutil.Process(os.getpid())
    _process.cpu_percent(interval=None)  # first call always returns 0.0; this just seeds the baseline
except Exception:
    # Missing psutil, or a sandboxed host that refuses process introspection - degrade gracefully.
    psutil = None
    _process = None


def is_bot_owner():
    async def predicate(ctx: commands.Context) -> bool:
        return ctx.author.id in config.OWNER_IDS

    return commands.check(predicate)


def format_duration(seconds: float) -> str:
    return str(timedelta(seconds=int(seconds)))


class Debug(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="debug", description="Full diagnostic report. Owner-only.")
    @is_bot_owner()
    async def debug(self, ctx: commands.Context):
        await ctx.defer(ephemeral=True)
        embeds = [
            self._overview_embed(),
            await self._health_embed(ctx.guild),
            self._config_embed(),
            self._activity_embed(),
        ]
        await ctx.send(embeds=embeds, ephemeral=True)

    def _overview_embed(self) -> discord.Embed:
        embed = base_embed("Debug - Overview", NEUTRAL_COLOR)

        version_lines = [
            f"discord.py `{discord.__version__}`",
            f"Python `{platform.python_version()}`",
            f"Platform `{platform.system()} {platform.release()}`",
        ]
        commit = os.environ.get("RAILWAY_GIT_COMMIT_SHA")
        if commit:
            version_lines.append(f"Commit `{commit[:7]}`")
        deployment = os.environ.get("RAILWAY_DEPLOYMENT_ID")
        if deployment:
            version_lines.append(f"Deployment `{deployment[:8]}`")
        embed.add_field(name="Build", value="\n".join(version_lines), inline=True)

        embed.add_field(
            name="Uptime",
            value=format_duration(diagnostics.uptime_seconds()),
            inline=True,
        )
        embed.add_field(
            name="Latency",
            value="n/a (no heartbeat yet)" if math.isnan(self.bot.latency) else f"{self.bot.latency * 1000:.0f}ms",
            inline=True,
        )

        embed.add_field(
            name="Scope",
            value=(
                f"Guilds: **{len(self.bot.guilds)}**\n"
                f"Users cached: **{len(self.bot.users)}**\n"
                f"Commands loaded: **{len(self.bot.commands)}**"
            ),
            inline=True,
        )

        loaded_cogs = ", ".join(sorted(self.bot.cogs.keys())) or "None"
        embed.add_field(name=f"Loaded cogs ({len(self.bot.cogs)})", value=clamp(loaded_cogs), inline=False)

        if _process is not None:
            memory_mb = _process.memory_info().rss / (1024 * 1024)
            cpu_percent = _process.cpu_percent(interval=None)  # non-blocking: uses the seeded baseline
            embed.add_field(
                name="Resource usage",
                value=f"Memory: **{memory_mb:.1f} MB**\nCPU: **{cpu_percent:.1f}%**\nPID: `{os.getpid()}`",
                inline=True,
            )
        else:
            embed.add_field(name="Resource usage", value="psutil not installed", inline=True)

        return embed

    async def _health_embed(self, guild: discord.Guild | None) -> discord.Embed:
        embed = base_embed("Debug - Health", NEUTRAL_COLOR)

        gateway_ok = self.bot.is_ready() and not self.bot.is_closed()
        embed.add_field(
            name="Discord gateway",
            value=f"{'\u2705' if gateway_ok else '\u274C'} {'Connected' if gateway_ok else 'Not connected'}",
            inline=True,
        )

        db_ok, db_detail = await database.check_connection()
        embed.add_field(name="Database", value=f"{'\u2705' if db_ok else '\u274C'} {db_detail}", inline=True)

        temp_ban_count = await database.get_active_temp_ban_count() if db_ok else 0
        total_cases = await database.get_total_case_count() if db_ok else 0
        embed.add_field(
            name="Data",
            value=f"Cases logged: **{total_cases}**\nActive temp-bans: **{temp_ban_count}**",
            inline=True,
        )

        scheduled_cog = self.bot.get_cog("ScheduledTasks")
        if scheduled_cog is not None:
            loop = scheduled_cog.expire_temp_bans
            loop_ok = loop.is_running() and not loop.failed()
            status = "Running" if loop_ok else ("Failed" if loop.failed() else "Not running")
            embed.add_field(
                name="Temp-ban expiry loop",
                value=f"{'\u2705' if loop_ok else '\u274C'} {status}\nIterations: **{loop.current_loop}**",
                inline=True,
            )

        if guild is not None:
            log_ok, log_detail = await check_log_channel(guild)
            embed.add_field(
                name="Mod-log (this server)",
                value=f"{'\u2705' if log_ok else '\u26A0'} {clamp(log_detail, 200)}",
                inline=False,
            )

        return embed

    def _config_embed(self) -> discord.Embed:
        embed = base_embed("Debug - Config", NEUTRAL_COLOR)

        # Presence and counts only - never the actual token or raw ID values here.
        embed.add_field(
            name="Environment",
            value=(
                f"BOT_TOKEN: {'set' if config.BOT_TOKEN else 'MISSING'} (redacted)\n"
                f"COMMAND_PREFIX: `{config.COMMAND_PREFIX}`\n"
                f"BRAND_NAME: `{config.BRAND_NAME}`\n"
                f"DATABASE_PATH: `{config.DATABASE_PATH}`"
            ),
            inline=False,
        )
        embed.add_field(
            name="Access control",
            value=(
                f"Owners configured: **{len(config.OWNER_IDS)}**\n"
                f"Global-mod roles configured: **{len(config.GLOBAL_ACTION_ROLE_IDS)}**\n"
                f"Approved servers: **{len(config.APPROVED_GUILD_IDS) or 'all (no allowlist)'}**\n"
                f"Auto-leave unapproved: **{config.LEAVE_UNAPPROVED_GUILDS}**"
            ),
            inline=False,
        )

        warnings = diagnostics.validate_config()
        embed.add_field(
            name=f"Validation ({'clean' if not warnings else f'{len(warnings)} issue(s)'})",
            value=clamp("\n".join(f"\u26A0 {warning}" for warning in warnings), empty="\u2705 No issues found."),
            inline=False,
        )
        return embed

    def _activity_embed(self) -> discord.Embed:
        embed = base_embed("Debug - Activity", NEUTRAL_COLOR)

        top_commands, total_invocations, total_errors = diagnostics.get_command_stats()
        if top_commands:
            command_lines = "\n".join(f"`/{name}` - **{count}**" for name, count in top_commands)
        else:
            command_lines = "No commands used since last restart."
        embed.add_field(
            name=f"Command usage ({total_invocations} total, {total_errors} errors)",
            value=clamp(command_lines),
            inline=False,
        )

        recent_logs = diagnostics.get_recent_logs(limit=8)
        embed.add_field(
            name="Recent warnings/errors",
            value=clamp("\n".join(f"`{line}`" for line in recent_logs), empty="None recorded since last restart."),
            inline=False,
        )

        return embed


async def setup(bot: commands.Bot):
    await bot.add_cog(Debug(bot))

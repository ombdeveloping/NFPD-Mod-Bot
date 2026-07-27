from datetime import datetime, timezone

import discord
from discord.ext import commands, tasks

from database import get_expired_temp_bans, remove_temp_ban
from modlog import record_case


class ScheduledTasks(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.expire_temp_bans.start()

    def cog_unload(self) -> None:
        self.expire_temp_bans.cancel()

    @tasks.loop(minutes=1)
    async def expire_temp_bans(self) -> None:
        for row in await get_expired_temp_bans(datetime.now(timezone.utc)):
            guild_id, user_id = row["guild_id"], row["user_id"]
            await remove_temp_ban(guild_id, user_id)

            guild = self.bot.get_guild(guild_id)
            if guild is None:
                continue

            try:
                user = await self.bot.fetch_user(user_id)
                await guild.unban(user, reason="Temporary ban expired")
            except (discord.NotFound, discord.Forbidden):
                continue

            await record_case(guild, user, self.bot.user, "unban", "Temporary ban expired")

    @expire_temp_bans.before_loop
    async def before_expire_temp_bans(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(ScheduledTasks(bot))

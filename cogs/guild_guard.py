import logging

import discord
from discord.ext import commands

from config import APPROVED_GUILD_IDS, LEAVE_UNAPPROVED_GUILDS, OWNER_IDS

logger = logging.getLogger("modbot.guild_guard")


class GuildGuard(commands.Cog):
    """Tracks which servers the bot has been added to, and optionally refuses to stay in unapproved ones."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def is_approved(self, guild: discord.Guild) -> bool:
        return not APPROVED_GUILD_IDS or guild.id in APPROVED_GUILD_IDS

    async def alert_owners(self, message: str) -> None:
        for owner_id in OWNER_IDS:
            try:
                owner = self.bot.get_user(owner_id) or await self.bot.fetch_user(owner_id)
                await owner.send(message)
            except discord.HTTPException:
                continue

    @commands.Cog.listener()
    async def on_ready(self):
        unapproved = [guild for guild in self.bot.guilds if not self.is_approved(guild)]
        for guild in unapproved:
            logger.warning("In unapproved server: %s (%s), owner %s", guild.name, guild.id, guild.owner_id)
            if LEAVE_UNAPPROVED_GUILDS:
                await guild.leave()
                logger.warning("Left unapproved server %s (%s)", guild.name, guild.id)

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        logger.info("Added to server: %s (%s), owner %s", guild.name, guild.id, guild.owner_id)

        if self.is_approved(guild):
            await self.alert_owners(f"Added to approved server **{guild.name}** (`{guild.id}`).")
            return

        await self.alert_owners(
            f"Added to **unapproved** server **{guild.name}** (`{guild.id}`), "
            f"owner ID `{guild.owner_id}`, {guild.member_count} members."
            + ("\nLeaving automatically." if LEAVE_UNAPPROVED_GUILDS else "\nGlobal actions will not apply there.")
        )

        if LEAVE_UNAPPROVED_GUILDS:
            await guild.leave()
            logger.warning("Left unapproved server %s (%s)", guild.name, guild.id)


async def setup(bot: commands.Bot):
    await bot.add_cog(GuildGuard(bot))

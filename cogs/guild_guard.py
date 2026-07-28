import logging

import discord
from discord.ext import commands

from config import APPROVED_GUILD_IDS, LEAVE_UNAPPROVED_GUILDS, OWNER_IDS

logger = logging.getLogger("modbot.guild_guard")


async def resolve_invite(guild: discord.Guild) -> str | None:
    """Try to generate a 24-hour invite from the first channel we have permission to use."""
    if guild.me is None:
        return None
    for channel in guild.text_channels:
        if not channel.permissions_for(guild.me).create_instant_invite:
            continue
        try:
            invite = await channel.create_invite(
                max_age=86400,
                max_uses=0,
                unique=False,
                reason="Unapproved server alert - requested by bot owner",
            )
            return invite.url
        except discord.HTTPException:
            continue
    return None


class GuildGuard(commands.Cog):
    """Tracks which servers the bot has been added to and optionally refuses to stay in unapproved ones."""

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

    async def _leave(self, guild: discord.Guild) -> None:
        try:
            await guild.leave()
            logger.warning("Left unapproved server %s (%s)", guild.name, guild.id)
        except discord.HTTPException as error:
            logger.warning("Tried to leave unapproved server %s (%s) but failed: %s", guild.name, guild.id, error)

    @commands.Cog.listener()
    async def on_ready(self):
        for guild in self.bot.guilds:
            if self.is_approved(guild):
                continue
            logger.warning("In unapproved server: %s (%s), owner %s", guild.name, guild.id, guild.owner_id)
            if LEAVE_UNAPPROVED_GUILDS:
                await self._leave(guild)

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        logger.info("Added to server: %s (%s), owner %s", guild.name, guild.id, guild.owner_id)

        if self.is_approved(guild):
            await self.alert_owners(f"Added to approved server **{guild.name}** (`{guild.id}`).")
            return

        # Unapproved server - try to get an invite before potentially leaving,
        # since we can't generate one after the bot has left.
        invite_url = await resolve_invite(guild)

        lines = [
            f"Added to **unapproved** server **{guild.name}** (`{guild.id}`),",
            f"owner ID `{guild.owner_id}`, {guild.member_count} members.",
        ]
        if invite_url:
            lines.append(f"Invite (24h): {invite_url}")
        else:
            lines.append("Could not generate an invite - no channel with Create Invite permission.")

        if LEAVE_UNAPPROVED_GUILDS:
            lines.append("Leaving automatically.")
        else:
            lines.append("Global actions will not apply there.")

        await self.alert_owners("\n".join(lines))

        if LEAVE_UNAPPROVED_GUILDS:
            await self._leave(guild)


async def setup(bot: commands.Bot):
    await bot.add_cog(GuildGuard(bot))

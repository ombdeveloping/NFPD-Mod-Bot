import logging

import discord
from discord.ext import commands

from config import APPROVED_GUILD_IDS, LEAVE_UNAPPROVED_GUILDS, OWNER_IDS

logger = logging.getLogger("modbot.guild_guard")

UNAPPROVED_SERVER_MESSAGE = (
    "This server is not an approved NFPD server.\n"
    "If you believe this is a mistake, please DM the developer.\n\n"
    "**Developer:** omb\n"
    "**Username:** ombdeveloping\n"
    "**Discord ID:** `1285998518213017663`"
)


async def resolve_invite(guild: discord.Guild) -> str | None:
    """Try to generate a 24-hour invite from the first channel the bot can use."""
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


async def post_in_server(guild: discord.Guild, message: str) -> bool:
    """Post a message in the server's system channel, or the first writable text channel."""
    candidates = []
    if guild.system_channel is not None:
        candidates.append(guild.system_channel)
    candidates.extend(ch for ch in guild.text_channels if ch != guild.system_channel)

    if guild.me is None:
        return False

    for channel in candidates:
        if not channel.permissions_for(guild.me).send_messages:
            continue
        try:
            await channel.send(message)
            return True
        except discord.HTTPException:
            continue
    return False


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

        # Try to get an invite before potentially leaving - can't generate one after the bot has left.
        invite_url = await resolve_invite(guild)

        # Post the unapproved notice in the server itself so the server owner sees it.
        await post_in_server(guild, UNAPPROVED_SERVER_MESSAGE)

        # Alert owners via DM with full details.
        owner_lines = [
            f"Added to **unapproved** server **{guild.name}** (`{guild.id}`),",
            f"owner ID `{guild.owner_id}`, {guild.member_count} members.",
        ]
        if invite_url:
            owner_lines.append(f"Invite (24h): {invite_url}")
        else:
            owner_lines.append("Could not generate an invite - no channel with Create Invite permission.")

        owner_lines.append("Leaving automatically." if LEAVE_UNAPPROVED_GUILDS else "Global actions will not apply there.")
        await self.alert_owners("\n".join(owner_lines))

        if LEAVE_UNAPPROVED_GUILDS:
            await self._leave(guild)


async def setup(bot: commands.Bot):
    await bot.add_cog(GuildGuard(bot))

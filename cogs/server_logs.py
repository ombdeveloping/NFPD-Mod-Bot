"""Full server event logging - mirrors Sapphire's audit log output.

Covers: messages (delete/edit/bulk delete), members (join/leave/ban/unban/nickname/roles),
voice state (join/move/leave), channels (create/delete/edit), roles (create/delete/edit),
and invites (create/delete).

All events post to the guild's configured log channel. If no log channel is set the
listener exits early so there is no overhead for guilds that don't use logging.
"""
from __future__ import annotations

from datetime import datetime, timezone

import discord
from discord.ext import commands

from modlog import post_to_log_channel

# Soft colour palette - distinct enough to read at a glance, not as alarming as the
# moderation action palette since these are informational, not punitive.
COLOR_JOIN      = 0x3BA55D  # green
COLOR_LEAVE     = 0x747F8D  # grey
COLOR_DELETE    = 0xD93A3A  # red
COLOR_EDIT      = 0xF5A524  # amber
COLOR_VOICE     = 0x5865F2  # blurple
COLOR_ROLE      = 0xEB459E  # fuchsia
COLOR_CHANNEL   = 0x57F287  # mint
COLOR_BAN       = 0xA32828  # dark red
COLOR_UNBAN     = 0x3BA55D  # green
COLOR_INVITE    = 0x9B59B6  # purple
COLOR_NICKNAME  = 0xFEE75C  # yellow


def _footer(embed: discord.Embed, user: discord.abc.User | discord.Member | None = None) -> discord.Embed:
    if user is not None:
        embed.set_footer(text=f"User ID: {user.id}")
    embed.timestamp = discord.utils.utcnow()
    return embed


def _short(text: str, limit: int = 1024) -> str:
    if not text:
        return "*empty*"
    if len(text) <= limit:
        return text
    return text[:limit - 3].rstrip() + "..."


class ServerLogs(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # -----------------------------------------------------------------------
    # Messages
    # -----------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message) -> None:
        if message.guild is None or message.author.bot:
            return

        embed = discord.Embed(color=COLOR_DELETE, title="Message Deleted")
        embed.set_author(name=str(message.author), icon_url=message.author.display_avatar.url)
        embed.add_field(name="Author", value=message.author.mention, inline=True)
        embed.add_field(name="Channel", value=message.channel.mention, inline=True)
        if message.content:
            embed.add_field(name="Content", value=_short(message.content), inline=False)
        if message.attachments:
            embed.add_field(
                name=f"Attachments ({len(message.attachments)})",
                value="\n".join(a.filename for a in message.attachments),
                inline=False,
            )
        _footer(embed, message.author)
        await post_to_log_channel(message.guild, embed)

    @commands.Cog.listener()
    async def on_bulk_message_delete(self, messages: list[discord.Message]) -> None:
        if not messages or messages[0].guild is None:
            return
        guild = messages[0].guild

        # Only count non-bot messages for the headline number.
        non_bot = [m for m in messages if not m.author.bot]
        channel = messages[0].channel

        embed = discord.Embed(color=COLOR_DELETE, title="Bulk Message Delete")
        embed.add_field(name="Channel", value=channel.mention, inline=True)
        embed.add_field(name="Messages removed", value=f"{len(non_bot)} user / {len(messages)} total", inline=True)
        embed.timestamp = discord.utils.utcnow()
        await post_to_log_channel(guild, embed)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message) -> None:
        if before.guild is None or before.author.bot:
            return
        if before.content == after.content:
            return  # Embed unfurl, pin, etc. - not a real edit.

        embed = discord.Embed(color=COLOR_EDIT, title="Message Edited")
        embed.set_author(name=str(before.author), icon_url=before.author.display_avatar.url)
        embed.add_field(name="Author", value=before.author.mention, inline=True)
        embed.add_field(name="Channel", value=before.channel.mention, inline=True)
        embed.add_field(name="Jump to message", value=f"[Click here]({after.jump_url})", inline=True)
        embed.add_field(name="Before", value=_short(before.content or "*empty*", 512), inline=False)
        embed.add_field(name="After", value=_short(after.content or "*empty*", 512), inline=False)
        _footer(embed, before.author)
        await post_to_log_channel(before.guild, embed)

    # -----------------------------------------------------------------------
    # Members
    # -----------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        account_age = discord.utils.utcnow() - member.created_at
        age_days = account_age.days

        embed = discord.Embed(color=COLOR_JOIN, title="Member Joined")
        embed.set_author(name=str(member), icon_url=member.display_avatar.url)
        embed.add_field(name="User", value=f"{member.mention}\n`{member.id}`", inline=True)
        embed.add_field(
            name="Account created",
            value=f"{discord.utils.format_dt(member.created_at, 'R')}\n({age_days} days old)",
            inline=True,
        )
        embed.add_field(
            name="Member count",
            value=str(member.guild.member_count),
            inline=True,
        )
        if age_days < 7:
            embed.add_field(
                name="\u26A0 New account",
                value=f"This account is only **{age_days} day(s)** old.",
                inline=False,
            )
        _footer(embed, member)
        await post_to_log_channel(member.guild, embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        embed = discord.Embed(color=COLOR_LEAVE, title="Member Left")
        embed.set_author(name=str(member), icon_url=member.display_avatar.url)
        embed.add_field(name="User", value=f"{member.mention}\n`{member.id}`", inline=True)

        roles = [r.mention for r in member.roles if r != member.guild.default_role]
        if roles:
            embed.add_field(name="Roles", value=", ".join(roles), inline=False)

        joined = member.joined_at
        if joined:
            embed.add_field(name="Joined", value=discord.utils.format_dt(joined, "R"), inline=True)

        _footer(embed, member)
        await post_to_log_channel(member.guild, embed)

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User) -> None:
        embed = discord.Embed(color=COLOR_BAN, title="\U0001F6D1  Member Banned")
        embed.set_author(name=str(user), icon_url=user.display_avatar.url)
        embed.add_field(name="User", value=f"{user.mention}\n`{user.id}`", inline=True)
        # Fetch the audit log entry so we can show who did it and why.
        reason, moderator = await _audit_ban_info(guild, user.id, discord.AuditLogAction.ban)
        if moderator:
            embed.add_field(name="Banned by", value=moderator.mention, inline=True)
        if reason:
            embed.add_field(name="Reason", value=_short(reason), inline=False)
        _footer(embed, user)
        await post_to_log_channel(guild, embed)

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User) -> None:
        embed = discord.Embed(color=COLOR_UNBAN, title="\U0001F513  Member Unbanned")
        embed.set_author(name=str(user), icon_url=user.display_avatar.url)
        embed.add_field(name="User", value=f"{user.mention}\n`{user.id}`", inline=True)
        reason, moderator = await _audit_ban_info(guild, user.id, discord.AuditLogAction.unban)
        if moderator:
            embed.add_field(name="Unbanned by", value=moderator.mention, inline=True)
        if reason:
            embed.add_field(name="Reason", value=_short(reason), inline=False)
        _footer(embed, user)
        await post_to_log_channel(guild, embed)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        guild = before.guild

        # Nickname change
        if before.nick != after.nick:
            embed = discord.Embed(color=COLOR_NICKNAME, title="Nickname Changed")
            embed.set_author(name=str(after), icon_url=after.display_avatar.url)
            embed.add_field(name="User", value=after.mention, inline=True)
            embed.add_field(name="Before", value=before.nick or "*none*", inline=True)
            embed.add_field(name="After", value=after.nick or "*none*", inline=True)
            _footer(embed, after)
            await post_to_log_channel(guild, embed)

        # Role changes
        added = [r for r in after.roles if r not in before.roles and r != guild.default_role]
        removed = [r for r in before.roles if r not in after.roles and r != guild.default_role]

        if added or removed:
            embed = discord.Embed(color=COLOR_ROLE, title="Member Roles Updated")
            embed.set_author(name=str(after), icon_url=after.display_avatar.url)
            embed.add_field(name="User", value=f"{after.mention}\n`{after.id}`", inline=True)
            if added:
                embed.add_field(name="Roles added", value=", ".join(r.mention for r in added), inline=False)
            if removed:
                embed.add_field(name="Roles removed", value=", ".join(r.mention for r in removed), inline=False)
            _footer(embed, after)
            await post_to_log_channel(guild, embed)

    # -----------------------------------------------------------------------
    # Voice
    # -----------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        if before.channel == after.channel:
            return  # Mute/deafen/stream toggle - not a channel movement.

        if before.channel is None and after.channel is not None:
            # Joined a voice channel.
            embed = discord.Embed(color=COLOR_VOICE, title="Joined Voice Channel")
            embed.set_author(name=str(member), icon_url=member.display_avatar.url)
            embed.add_field(name="User", value=member.mention, inline=True)
            embed.add_field(name="Channel", value=after.channel.mention, inline=True)

        elif before.channel is not None and after.channel is None:
            # Left a voice channel.
            embed = discord.Embed(color=COLOR_VOICE, title="Left Voice Channel")
            embed.set_author(name=str(member), icon_url=member.display_avatar.url)
            embed.add_field(name="User", value=member.mention, inline=True)
            embed.add_field(name="Channel", value=before.channel.mention, inline=True)

        else:
            # Moved between voice channels.
            embed = discord.Embed(color=COLOR_VOICE, title="Moved Voice Channel")
            embed.set_author(name=str(member), icon_url=member.display_avatar.url)
            embed.add_field(name="User", value=member.mention, inline=True)
            embed.add_field(name="From", value=before.channel.mention, inline=True)
            embed.add_field(name="To", value=after.channel.mention, inline=True)

        _footer(embed, member)
        await post_to_log_channel(member.guild, embed)

    # -----------------------------------------------------------------------
    # Channels
    # -----------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel) -> None:
        embed = discord.Embed(color=COLOR_CHANNEL, title="Channel Created")
        embed.add_field(name="Name", value=channel.mention, inline=True)
        embed.add_field(name="Type", value=str(channel.type).replace("_", " ").title(), inline=True)
        if hasattr(channel, "category") and channel.category:
            embed.add_field(name="Category", value=channel.category.name, inline=True)
        embed.timestamp = discord.utils.utcnow()
        await post_to_log_channel(channel.guild, embed)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> None:
        embed = discord.Embed(color=COLOR_DELETE, title="Channel Deleted")
        embed.add_field(name="Name", value=f"#{channel.name}", inline=True)
        embed.add_field(name="Type", value=str(channel.type).replace("_", " ").title(), inline=True)
        if hasattr(channel, "category") and channel.category:
            embed.add_field(name="Category", value=channel.category.name, inline=True)
        embed.timestamp = discord.utils.utcnow()
        await post_to_log_channel(channel.guild, embed)

    @commands.Cog.listener()
    async def on_guild_channel_update(
        self,
        before: discord.abc.GuildChannel,
        after: discord.abc.GuildChannel,
    ) -> None:
        changes: list[tuple[str, str, str]] = []

        if before.name != after.name:
            changes.append(("Name", before.name, after.name))
        if getattr(before, "topic", None) != getattr(after, "topic", None):
            changes.append(("Topic", before.topic or "*none*", after.topic or "*none*"))
        if getattr(before, "nsfw", None) != getattr(after, "nsfw", None):
            changes.append(("NSFW", str(before.nsfw), str(after.nsfw)))
        if getattr(before, "slowmode_delay", None) != getattr(after, "slowmode_delay", None):
            changes.append(("Slowmode", f"{before.slowmode_delay}s", f"{after.slowmode_delay}s"))

        if not changes:
            return

        embed = discord.Embed(color=COLOR_CHANNEL, title="Channel Updated")
        embed.add_field(name="Channel", value=after.mention, inline=False)
        for field_name, old_val, new_val in changes:
            embed.add_field(name=field_name, value=f"{_short(old_val, 200)} -> {_short(new_val, 200)}", inline=False)
        embed.timestamp = discord.utils.utcnow()
        await post_to_log_channel(after.guild, embed)

    # -----------------------------------------------------------------------
    # Roles
    # -----------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role) -> None:
        embed = discord.Embed(color=COLOR_ROLE, title="Role Created")
        embed.add_field(name="Name", value=role.mention, inline=True)
        embed.add_field(name="Color", value=str(role.color), inline=True)
        embed.add_field(name="Hoisted", value=str(role.hoist), inline=True)
        embed.timestamp = discord.utils.utcnow()
        await post_to_log_channel(role.guild, embed)

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role) -> None:
        embed = discord.Embed(color=COLOR_DELETE, title="Role Deleted")
        embed.add_field(name="Name", value=f"@{role.name}", inline=True)
        embed.add_field(name="Color", value=str(role.color), inline=True)
        embed.add_field(name="ID", value=f"`{role.id}`", inline=True)
        embed.timestamp = discord.utils.utcnow()
        await post_to_log_channel(role.guild, embed)

    @commands.Cog.listener()
    async def on_guild_role_update(self, before: discord.Role, after: discord.Role) -> None:
        changes: list[tuple[str, str, str]] = []

        if before.name != after.name:
            changes.append(("Name", before.name, after.name))
        if before.color != after.color:
            changes.append(("Color", str(before.color), str(after.color)))
        if before.hoist != after.hoist:
            changes.append(("Hoisted", str(before.hoist), str(after.hoist)))
        if before.mentionable != after.mentionable:
            changes.append(("Mentionable", str(before.mentionable), str(after.mentionable)))

        if not changes:
            return

        embed = discord.Embed(color=COLOR_ROLE, title="Role Updated")
        embed.add_field(name="Role", value=after.mention, inline=False)
        for field_name, old_val, new_val in changes:
            embed.add_field(name=field_name, value=f"{old_val} -> {new_val}", inline=False)
        embed.timestamp = discord.utils.utcnow()
        await post_to_log_channel(after.guild, embed)

    # -----------------------------------------------------------------------
    # Invites
    # -----------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_invite_create(self, invite: discord.Invite) -> None:
        if invite.guild is None:
            return
        embed = discord.Embed(color=COLOR_INVITE, title="Invite Created")
        embed.add_field(name="Code", value=f"[{invite.code}]({invite.url})", inline=True)
        if invite.inviter:
            embed.add_field(name="Created by", value=invite.inviter.mention, inline=True)
        if invite.channel:
            embed.add_field(name="Channel", value=invite.channel.mention, inline=True)
        expires = "Never" if invite.max_age == 0 else f"{invite.max_age // 3600}h"
        uses = "Unlimited" if invite.max_uses == 0 else str(invite.max_uses)
        embed.add_field(name="Expires", value=expires, inline=True)
        embed.add_field(name="Max uses", value=uses, inline=True)
        embed.timestamp = discord.utils.utcnow()
        await post_to_log_channel(invite.guild, embed)

    @commands.Cog.listener()
    async def on_invite_delete(self, invite: discord.Invite) -> None:
        if invite.guild is None:
            return
        embed = discord.Embed(color=COLOR_DELETE, title="Invite Deleted")
        embed.add_field(name="Code", value=invite.code, inline=True)
        if invite.channel:
            embed.add_field(name="Channel", value=invite.channel.mention, inline=True)
        embed.timestamp = discord.utils.utcnow()
        await post_to_log_channel(invite.guild, embed)


# ---------------------------------------------------------------------------
# Audit log helpers
# ---------------------------------------------------------------------------

async def _audit_ban_info(
    guild: discord.Guild,
    target_id: int,
    action: discord.AuditLogAction,
) -> tuple[str | None, discord.Member | discord.User | None]:
    """Look up the most recent audit log entry for a ban/unban and return (reason, moderator).

    Returns (None, None) if the bot lacks View Audit Log permission or the entry is not found.
    """
    if not guild.me or not guild.me.guild_permissions.view_audit_log:
        return None, None
    try:
        async for entry in guild.audit_logs(limit=5, action=action):
            if entry.target and entry.target.id == target_id:
                return entry.reason, entry.user
    except discord.HTTPException:
        pass
    return None, None


async def setup(bot: commands.Bot):
    await bot.add_cog(ServerLogs(bot))

"""Alt account likelihood detector with invite tracking.

Tracks guild invite usage so we can identify which invite a new member used,
then scores them for alt-account likelihood based on account age, avatar,
username patterns, and who invited them.

Requires: Manage Guild permission (to fetch invites).
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

import discord
from discord.ext import commands

import embeds as embeds_module
from config import BRAND_NAME
from modlog import post_to_server_log_channel

# Risk thresholds
HIGH_RISK  = 60
MEDIUM_RISK = 35

# Colors
COLOR_HIGH   = 0xD93A3A
COLOR_MEDIUM = 0xF5A524
COLOR_LOW    = 0x3BA55D

# Pattern: 4+ consecutive digits anywhere in the username
_DIGIT_RUN = re.compile(r"\d{4,}")


def _age_days(dt: datetime) -> int:
    return (datetime.now(timezone.utc) - dt).days


def _score_member(member: discord.Member, inviter: discord.Member | discord.User | None) -> tuple[int, list[str]]:
    """Return (risk_score, list of reasons) for a joining member."""
    score = 0
    reasons: list[str] = []

    age = _age_days(member.created_at)
    if age < 1:
        score += 65
        reasons.append(f"Account created **today** ({age} days old)")
    elif age < 7:
        score += 45
        reasons.append(f"Account is very new ({age} days old)")
    elif age < 30:
        score += 25
        reasons.append(f"Account is less than 30 days old ({age} days old)")
    elif age < 90:
        score += 10
        reasons.append(f"Account is less than 90 days old ({age} days old)")

    # No custom profile picture
    if member.display_avatar.key == member._user.default_avatar.key:
        score += 20
        reasons.append("No profile picture (using default avatar)")

    # Username contains a long run of digits (e.g. alt123456)
    if _DIGIT_RUN.search(member.name):
        score += 15
        reasons.append(f"Username contains a digit sequence (`{member.name}`)")

    # Inviter's own account is young
    if inviter is not None and hasattr(inviter, "created_at"):
        inviter_age = _age_days(inviter.created_at)
        if inviter_age < 30:
            score += 20
            reasons.append(f"Invited by a new account ({inviter_age} days old: {inviter})")

    if not reasons:
        reasons.append("No risk factors detected")

    return score, reasons


def _risk_label(score: int) -> tuple[str, int]:
    if score >= HIGH_RISK:
        return "HIGH", COLOR_HIGH
    if score >= MEDIUM_RISK:
        return "MEDIUM", COLOR_MEDIUM
    return "LOW", COLOR_LOW


def _build_alert(
    member: discord.Member,
    score: int,
    reasons: list[str],
    invite_code: str | None,
    inviter: discord.Member | discord.User | None,
) -> discord.Embed:
    label, color = _risk_label(score)
    embed = discord.Embed(
        title=f"\U0001F916  Alt Detection - {label} RISK",
        color=color,
        timestamp=discord.utils.utcnow(),
    )
    embed.set_author(name=str(member), icon_url=member.display_avatar.url)
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="User", value=f"{member.mention}\n`{member.id}`", inline=True)
    embed.add_field(name="Score", value=f"{score} / 100+", inline=True)
    embed.add_field(
        name="Account created",
        value=f"{discord.utils.format_dt(member.created_at, 'R')}\n({_age_days(member.created_at)} days old)",
        inline=True,
    )
    if inviter:
        embed.add_field(name="Invited by", value=f"{inviter.mention}\n`{inviter.id}`", inline=True)
    if invite_code:
        embed.add_field(name="Invite used", value=f"`{invite_code}`", inline=True)
    embed.add_field(
        name="Risk factors",
        value="\n".join(f"- {r}" for r in reasons),
        inline=False,
    )
    embed.set_footer(text=BRAND_NAME, icon_url=embeds_module.BRAND_ICON_URL)
    return embed


class AltDetector(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # {guild_id: {invite_code: (uses, inviter_id)}}
        self._invite_cache: dict[int, dict[str, tuple[int, int | None]]] = {}

    async def _cache_invites(self, guild: discord.Guild) -> None:
        if guild.me is None or not guild.me.guild_permissions.manage_guild:
            return
        try:
            invites = await guild.invites()
            self._invite_cache[guild.id] = {
                inv.code: (inv.uses or 0, inv.inviter.id if inv.inviter else None)
                for inv in invites
            }
        except discord.HTTPException:
            pass

    async def _find_used_invite(
        self, guild: discord.Guild
    ) -> tuple[str | None, discord.Member | discord.User | None]:
        """Compare cached and current invite uses to identify which was just used."""
        if guild.me is None or not guild.me.guild_permissions.manage_guild:
            return None, None

        old_cache = self._invite_cache.get(guild.id, {})

        try:
            current_invites = await guild.invites()
        except discord.HTTPException:
            return None, None

        for inv in current_invites:
            old_uses, inviter_id = old_cache.get(inv.code, (0, None))
            if (inv.uses or 0) > old_uses:
                inviter_id = inv.inviter.id if inv.inviter else None
                inviter = guild.get_member(inviter_id) if inviter_id else None
                if inviter is None and inviter_id:
                    try:
                        inviter = await self.bot.fetch_user(inviter_id)
                    except discord.HTTPException:
                        pass
                # Refresh cache entry
                self._invite_cache.setdefault(guild.id, {})[inv.code] = (
                    inv.uses or 0,
                    inviter_id,
                )
                return inv.code, inviter

        # Invite may have been deleted after reaching max_uses
        for code, (old_uses, inviter_id) in old_cache.items():
            if not any(inv.code == code for inv in current_invites):
                inviter = guild.get_member(inviter_id) if inviter_id else None
                if inviter is None and inviter_id:
                    try:
                        inviter = await self.bot.fetch_user(inviter_id)
                    except discord.HTTPException:
                        pass
                return code, inviter

        return None, None

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        for guild in self.bot.guilds:
            await self._cache_invites(guild)

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild) -> None:
        await self._cache_invites(guild)

    @commands.Cog.listener()
    async def on_invite_create(self, invite: discord.Invite) -> None:
        if invite.guild is None:
            return
        self._invite_cache.setdefault(invite.guild.id, {})[invite.code] = (
            invite.uses or 0,
            invite.inviter.id if invite.inviter else None,
        )

    @commands.Cog.listener()
    async def on_invite_delete(self, invite: discord.Invite) -> None:
        if invite.guild is None:
            return
        self._invite_cache.get(invite.guild.id, {}).pop(invite.code, None)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        invite_code, inviter = await self._find_used_invite(member.guild)
        score, reasons = _score_member(member, inviter)

        # Only alert on medium risk or higher to avoid noise
        if score < MEDIUM_RISK:
            return

        embed = _build_alert(member, score, reasons, invite_code, inviter)
        await post_to_server_log_channel(member.guild, embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        # Nothing to do for invites, but refresh cache on leave
        # so we don't end up with stale invite counts
        pass


async def setup(bot: commands.Bot):
    await bot.add_cog(AltDetector(bot))

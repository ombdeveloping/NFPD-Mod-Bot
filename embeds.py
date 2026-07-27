from datetime import datetime
from typing import NamedTuple

import discord

from config import BRAND_NAME


class ActionStyle(NamedTuple):
    color: int
    icon: str
    title: str
    dm_line: str


NEUTRAL_COLOR = 0x5865F2
SUCCESS_COLOR = 0x3BA55D
DANGER_COLOR = 0xD93A3A
MUTED_COLOR = 0x4F545C

ACTION_STYLES = {
    "warn":          ActionStyle(0xF5A524, "\u26A0",     "Warning",       "You were warned in {location}."),
    "mute":          ActionStyle(0xE8833A, "\U0001F507", "Mute",          "You were muted in {location}."),
    "unmute":        ActionStyle(SUCCESS_COLOR, "\U0001F508", "Unmute",   ""),
    "kick":          ActionStyle(0xE85D3A, "\U0001F6AA", "Kick",          "You were kicked from {location}."),
    "ban":           ActionStyle(DANGER_COLOR, "\U0001F6D1", "Ban",       "You were banned from {location}."),
    "unban":         ActionStyle(SUCCESS_COLOR, "\U0001F513", "Unban",    ""),
    "global_mute":   ActionStyle(0xC26B25, "\U0001F507", "Global Mute",   "You were muted across all servers."),
    "global_unmute": ActionStyle(SUCCESS_COLOR, "\U0001F508", "Global Unmute", ""),
    "global_kick":   ActionStyle(0xB84A2E, "\U0001F6AA", "Global Kick",   "You were removed from all servers."),
    "global_ban":    ActionStyle(0xA32828, "\U0001F6D1", "Global Ban",    "You were banned across all servers."),
    "global_unban":  ActionStyle(SUCCESS_COLOR, "\U0001F513", "Global Unban", ""),
}

FALLBACK_STYLE = ActionStyle(NEUTRAL_COLOR, "\U0001F4CB", "Action", "")

EMBED_FIELD_LIMIT = 1024
EMBED_DESCRIPTION_LIMIT = 4096


def clamp(text: str | None, limit: int = EMBED_FIELD_LIMIT, *, empty: str = "*Not specified*") -> str:
    """Discord rejects embed fields that are empty or over the character limit."""
    if not text or not text.strip():
        return empty
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def style_for(action_type: str) -> ActionStyle:
    return ACTION_STYLES.get(action_type, FALLBACK_STYLE)


def format_timestamp(iso_string: str, style: str = "f") -> str:
    """Render a stored ISO timestamp as a Discord timestamp that respects the viewer's timezone."""
    try:
        parsed = datetime.fromisoformat(iso_string)
    except (TypeError, ValueError):
        return iso_string
    return discord.utils.format_dt(parsed, style=style)


def base_embed(title: str, color: int, description: str | None = None) -> discord.Embed:
    embed = discord.Embed(title=title, description=description, color=color, timestamp=discord.utils.utcnow())
    embed.set_footer(text=BRAND_NAME)
    return embed


def build_case_embed(
    action_type: str,
    target: discord.abc.User,
    moderator: discord.abc.User,
    reason: str,
    case_id: int,
) -> discord.Embed:
    style = style_for(action_type)
    embed = discord.Embed(color=style.color, timestamp=discord.utils.utcnow())
    embed.set_author(name=f"{style.icon}  {style.title}", icon_url=target.display_avatar.url)
    embed.description = f"**{target}**\n`{target.id}`"
    embed.add_field(name="Moderator", value=moderator.mention, inline=True)
    embed.add_field(name="Reason", value=clamp(reason), inline=False)
    embed.set_footer(text=f"Case #{case_id}  \u2022  {BRAND_NAME}")
    return embed


def build_dm_notice_embed(action_type: str, location_name: str, reason: str) -> discord.Embed:
    style = style_for(action_type)
    embed = discord.Embed(
        title=f"{style.icon}  {style.title}",
        description=style.dm_line.format(location=f"**{location_name}**") or None,
        color=style.color,
        timestamp=discord.utils.utcnow(),
    )
    embed.add_field(name="Reason", value=clamp(reason), inline=False)
    embed.set_footer(text=BRAND_NAME)
    return embed


def build_summary_embed(
    action_type: str,
    user: discord.abc.User,
    affected: list[str],
    failed: list[str],
) -> discord.Embed:
    style = style_for(action_type)
    embed = discord.Embed(color=style.color, timestamp=discord.utils.utcnow())
    embed.set_author(name=f"{style.icon}  {style.title}", icon_url=user.display_avatar.url)
    embed.description = f"**{user}**\n`{user.id}`"

    embed.add_field(
        name=f"Applied in {len(affected)} server(s)",
        value=clamp("\n".join(f"- {name}" for name in affected), empty="*None*"),
        inline=False,
    )
    if failed:
        embed.add_field(
            name=f"Skipped, missing permissions ({len(failed)})",
            value=clamp("\n".join(f"- {name}" for name in failed)),
            inline=False,
        )

    embed.set_footer(text=BRAND_NAME)
    return embed


def build_case_line(row, guild: discord.Guild) -> tuple[str, str]:
    """One case rendered as an embed field name/value pair."""
    style = style_for(row["action_type"])
    moderator = guild.get_member(row["moderator_id"])
    moderator_name = moderator.mention if moderator else f"`{row['moderator_id']}`"

    name = f"{style.icon}  Case #{row['id']}  \u2022  {style.title}"
    reason = clamp(row["reason"], limit=800)
    value = f"{reason}\n{moderator_name}  \u2022  {format_timestamp(row['created_at'], 'R')}"
    return name, value


def build_notice_embed(message: str, *, success: bool = True) -> discord.Embed:
    return discord.Embed(
        description=message,
        color=SUCCESS_COLOR if success else DANGER_COLOR,
    )

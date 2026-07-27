import discord

ACTION_COLORS = {
    "kick": discord.Color.orange(),
    "ban": discord.Color.red(),
    "warn": discord.Color.yellow(),
    "mute": discord.Color.dark_gold(),
    "unmute": discord.Color.green(),
    "global_kick": discord.Color.dark_orange(),
    "global_ban": discord.Color.dark_red(),
    "global_unban": discord.Color.green(),
    "global_mute": discord.Color.dark_gold(),
    "global_unmute": discord.Color.green(),
}

ACTION_LABELS = {
    "kick": "kicked from",
    "ban": "banned from",
    "warn": "warned in",
    "mute": "muted in",
    "global_kick": "kicked from every server shared with",
    "global_ban": "banned from every server owned by",
    "global_mute": "muted in every server shared with",
}

SUMMARY_VERBS = {
    "global_kick": "Kicked",
    "global_ban": "Banned",
    "global_unban": "Unbanned",
    "global_mute": "Muted",
    "global_unmute": "Unmuted",
}


def build_case_embed(
    action_type: str,
    target: discord.abc.User,
    moderator: discord.abc.User,
    reason: str,
    case_id: int,
) -> discord.Embed:
    embed = discord.Embed(
        title=f"Case #{case_id} \u2014 {action_type.replace('_', ' ').title()}",
        color=ACTION_COLORS.get(action_type, discord.Color.blurple()),
        timestamp=discord.utils.utcnow(),
    )
    embed.set_thumbnail(url=target.display_avatar.url)
    embed.add_field(name="User", value=f"{target.mention}\n`{target.id}`", inline=True)
    embed.add_field(name="Moderator", value=moderator.mention, inline=True)
    embed.add_field(name="Reason", value=reason, inline=False)
    return embed


def build_dm_notice_embed(action_type: str, location_name: str, reason: str) -> discord.Embed:
    label = ACTION_LABELS.get(action_type, action_type)
    embed = discord.Embed(
        title=f"You have been {label} {location_name}",
        description=f"**Reason:** {reason}",
        color=ACTION_COLORS.get(action_type, discord.Color.blurple()),
        timestamp=discord.utils.utcnow(),
    )
    return embed


def build_summary_embed(action_type: str, user: discord.abc.User, affected: list[str], failed: list[str]) -> discord.Embed:
    verb = SUMMARY_VERBS.get(action_type, action_type.replace("_", " ").title())
    embed = discord.Embed(
        title=f"Global {verb} \u2014 {user}",
        color=ACTION_COLORS.get(action_type, discord.Color.blurple()),
        timestamp=discord.utils.utcnow(),
    )
    embed.set_thumbnail(url=user.display_avatar.url)
    embed.add_field(name=f"{verb} in ({len(affected)})", value="\n".join(affected) or "None", inline=False)
    if failed:
        embed.add_field(name=f"Missing permissions ({len(failed)})", value="\n".join(failed), inline=False)
    return embed

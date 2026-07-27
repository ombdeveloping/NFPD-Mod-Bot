import discord
from discord.ext import commands

from config import BLOCKED_USER_IDS, OWNER_IDS, PROTECTED_USER_IDS


class BlockedUser(commands.CheckFailure):
    """Raised when someone on BLOCKED_USER_IDS tries to run any command."""


def is_blocked(user_id: int) -> bool:
    """Users on the deny list cannot use the bot at all."""
    return user_id in BLOCKED_USER_IDS


def is_protected(user_id: int) -> bool:
    """Users who can never be the target of a moderation action.

    Owners are always included on top of PROTECTED_USER_IDS, so a moderator whose account
    is compromised still can't ban the people who administer the bot.
    """
    return user_id in PROTECTED_USER_IDS or user_id in OWNER_IDS


def outranks_or_equals(actor: discord.Member, target: discord.Member) -> bool:
    """True when the target sits at or above the actor in the role hierarchy."""
    if actor.id == actor.guild.owner_id:
        return False
    return target.top_role >= actor.top_role


def refusal_reason(
    actor: discord.Member,
    target: discord.abc.User,
    bot_user_id: int,
    *,
    check_hierarchy: bool = True,
) -> str | None:
    """Why a moderation action against this target must not proceed, or None if it may.

    Consolidates the self/bot/protected/owner/hierarchy checks that every moderation
    command needs, so they can't drift apart or be forgotten on a new command.
    """
    if target.id == actor.id:
        return "You can't use that on yourself."
    if target.id == bot_user_id:
        return "You can't use that on me."
    if is_protected(target.id):
        return f"**{target}** is on the protected list and can't be moderated."

    if isinstance(target, discord.Member):
        if target.id == target.guild.owner_id:
            return f"**{target}** owns this server and can't be moderated."
        if check_hierarchy and outranks_or_equals(actor, target):
            return "You can't action someone ranked equal to or above you."

    return None

import os

from dotenv import load_dotenv

load_dotenv()


def _parse_id_list(*variable_names: str) -> set[int]:
    """Read a comma-separated list of Discord IDs from the first variable that has a value."""
    for name in variable_names:
        raw_value = os.environ.get(name, "")
        if raw_value.strip():
            return {int(piece.strip()) for piece in raw_value.split(",") if piece.strip()}
    return set()


BOT_TOKEN = os.environ["BOT_TOKEN"]
COMMAND_PREFIX = os.environ.get("COMMAND_PREFIX", "!")
BRAND_NAME = os.environ.get("BRAND_NAME", "Moderation")

OWNER_IDS = _parse_id_list("OWNER_IDS")

# Accepts several roles. GLOBAL_ACTION_ROLE_ID is the older single-value name, still read as a fallback.
GLOBAL_ACTION_ROLE_IDS = _parse_id_list("GLOBAL_ACTION_ROLE_IDS", "GLOBAL_ACTION_ROLE_ID")

# Servers that global actions may be run from and applied to. Leaving this empty means
# global actions reach EVERY server the bot is in, including ones added without your knowledge.
APPROVED_GUILD_IDS = _parse_id_list("APPROVED_GUILD_IDS")

# When true, the bot immediately leaves any server not in APPROVED_GUILD_IDS.
LEAVE_UNAPPROVED_GUILDS = os.environ.get("LEAVE_UNAPPROVED_GUILDS", "").strip().lower() in {"1", "true", "yes"}

DATABASE_PATH = os.environ.get("DATABASE_PATH", "moderation.db")

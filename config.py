import os
import sys

from dotenv import load_dotenv

load_dotenv()


def _fail(message: str) -> None:
    """Configuration errors happen before logging is set up, so print plainly and exit clearly."""
    print(f"Configuration error: {message}", file=sys.stderr)
    raise SystemExit(1)


def _parse_id_list(*variable_names: str) -> set[int]:
    """Read a comma-separated list of Discord IDs from the first variable that has a value."""
    for name in variable_names:
        raw_value = os.environ.get(name, "")
        if not raw_value.strip():
            continue
        try:
            return {int(piece.strip()) for piece in raw_value.split(",") if piece.strip()}
        except ValueError:
            _fail(f"{name} must be a comma-separated list of numeric Discord IDs, got: {raw_value!r}")
    return set()


def _parse_bool(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes"}


BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
if not BOT_TOKEN:
    _fail("BOT_TOKEN is required. Set it in your .env file or hosting platform's environment variables.")

COMMAND_PREFIX = os.environ.get("COMMAND_PREFIX", "!")
BRAND_NAME = os.environ.get("BRAND_NAME", "Moderation")

OWNER_IDS = _parse_id_list("OWNER_IDS")

# Accepts several roles. GLOBAL_ACTION_ROLE_ID is the older single-value name, still read as a fallback.
GLOBAL_ACTION_ROLE_IDS = _parse_id_list("GLOBAL_ACTION_ROLE_IDS", "GLOBAL_ACTION_ROLE_ID")

# Servers that global actions may be run from and applied to. Leaving this empty means
# global actions reach EVERY server the bot is in, including ones added without your knowledge.
APPROVED_GUILD_IDS = _parse_id_list("APPROVED_GUILD_IDS")

# When true, the bot immediately leaves any server not in APPROVED_GUILD_IDS.
LEAVE_UNAPPROVED_GUILDS = _parse_bool("LEAVE_UNAPPROVED_GUILDS")

# Users who can never be the TARGET of a moderation action. Owners are always protected
# on top of this list, so a compromised moderator account can't remove them.
PROTECTED_USER_IDS = _parse_id_list("PROTECTED_USER_IDS")

# Users who may not USE the bot at all. Every command refuses for them.
BLOCKED_USER_IDS = _parse_id_list("BLOCKED_USER_IDS")

DATABASE_PATH = os.environ.get("DATABASE_PATH", "moderation.db")

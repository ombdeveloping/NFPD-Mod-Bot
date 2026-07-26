import os

from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.environ["BOT_TOKEN"]
COMMAND_PREFIX = os.environ.get("COMMAND_PREFIX", "!")

OWNER_IDS = {
    int(owner_id.strip())
    for owner_id in os.environ.get("OWNER_IDS", "").split(",")
    if owner_id.strip()
}

_global_role_id = os.environ.get("GLOBAL_ACTION_ROLE_ID", "").strip()
GLOBAL_ACTION_ROLE_ID = int(_global_role_id) if _global_role_id else None

DATABASE_PATH = os.environ.get("DATABASE_PATH", "moderation.db")

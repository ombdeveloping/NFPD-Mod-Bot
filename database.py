"""PostgreSQL database layer using asyncpg.

Replaces the previous aiosqlite/SQLite implementation. Data is now stored in
Railway's managed PostgreSQL service which persists across deploys with no
volume mounting required.

Connection: a single pool opened at startup, shared across all coroutines.
Queries:    use $1, $2 ... placeholders (asyncpg convention).
IDs:        BIGINT for Discord snowflakes (they exceed the 32-bit INT range).
"""
import json
import time as _time
from datetime import datetime, timezone

import asyncpg

from config import DATABASE_URL

_pool: asyncpg.Pool | None = None


SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS cases (
        id            SERIAL PRIMARY KEY,
        guild_id      BIGINT NOT NULL,
        user_id       BIGINT NOT NULL,
        moderator_id  BIGINT NOT NULL,
        action_type   TEXT NOT NULL,
        reason        TEXT,
        created_at    TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_cases_guild_user   ON cases (guild_id, user_id)",
    "CREATE INDEX IF NOT EXISTS idx_cases_guild_action ON cases (guild_id, action_type)",
    """
    CREATE TABLE IF NOT EXISTS guild_settings (
        guild_id                  BIGINT PRIMARY KEY,
        log_channel_id            BIGINT,
        server_log_channel_id     BIGINT,
        lockdown_role_id          BIGINT,
        raid_min_account_age_hours INTEGER,
        warn_mute_threshold        INTEGER,
        warn_mute_minutes          INTEGER,
        warn_kick_threshold        INTEGER,
        warn_ban_threshold         INTEGER
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS lockdown_roles (
        guild_id BIGINT NOT NULL,
        role_id  BIGINT NOT NULL,
        PRIMARY KEY (guild_id, role_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS temp_bans (
        guild_id  BIGINT NOT NULL,
        user_id   BIGINT NOT NULL,
        unban_at  TEXT NOT NULL,
        PRIMARY KEY (guild_id, user_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_temp_bans_unban_at ON temp_bans (unban_at)",
    """
    CREATE TABLE IF NOT EXISTS channel_locks (
        guild_id       BIGINT NOT NULL,
        channel_id     BIGINT NOT NULL,
        previous_state TEXT NOT NULL,
        PRIMARY KEY (guild_id, channel_id)
    )
    """,
)


async def connect_database() -> None:
    """Open the connection pool and ensure the schema exists. Call once at startup."""
    global _pool
    _pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=10)
    async with _pool.acquire() as conn:
        for statement in SCHEMA_STATEMENTS:
            await conn.execute(statement)


async def close_database() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def _get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("Database is not connected. Call connect_database() during startup.")
    return _pool


async def _fetch_all(query: str, *args) -> list[asyncpg.Record]:
    async with _get_pool().acquire() as conn:
        return await conn.fetch(query, *args)


async def _fetch_one(query: str, *args) -> asyncpg.Record | None:
    async with _get_pool().acquire() as conn:
        return await conn.fetchrow(query, *args)


async def _fetch_val(query: str, *args):
    async with _get_pool().acquire() as conn:
        return await conn.fetchval(query, *args)


async def _execute(query: str, *args) -> int:
    """Execute a statement and return the number of affected rows."""
    async with _get_pool().acquire() as conn:
        status = await conn.execute(query, *args)
    # asyncpg returns a status string like "UPDATE 3" or "DELETE 1"
    try:
        return int(status.split()[-1])
    except (IndexError, ValueError):
        return 0


# --- Cases -------------------------------------------------------------------

async def add_case(guild_id: int, user_id: int, moderator_id: int, action_type: str, reason: str) -> int:
    return await _fetch_val(
        """
        INSERT INTO cases (guild_id, user_id, moderator_id, action_type, reason, created_at)
        VALUES ($1, $2, $3, $4, $5, $6)
        RETURNING id
        """,
        guild_id, user_id, moderator_id, action_type, reason,
        datetime.now(timezone.utc).isoformat(),
    )


async def get_cases_for_user(guild_id: int, user_id: int) -> list[asyncpg.Record]:
    return await _fetch_all(
        """
        SELECT id, moderator_id, action_type, reason, created_at
        FROM cases
        WHERE guild_id = $1 AND user_id = $2
        ORDER BY id DESC
        """,
        guild_id, user_id,
    )


async def get_all_cases(guild_id: int) -> list[asyncpg.Record]:
    return await _fetch_all(
        """
        SELECT id, user_id, moderator_id, action_type, reason, created_at
        FROM cases
        WHERE guild_id = $1
        ORDER BY id ASC
        """,
        guild_id,
    )


async def get_case_by_id(guild_id: int, case_id: int) -> asyncpg.Record | None:
    return await _fetch_one(
        "SELECT * FROM cases WHERE guild_id = $1 AND id = $2",
        guild_id, case_id,
    )


async def update_case_reason(guild_id: int, case_id: int, new_reason: str) -> bool:
    changed = await _execute(
        "UPDATE cases SET reason = $1 WHERE guild_id = $2 AND id = $3",
        new_reason, guild_id, case_id,
    )
    return changed > 0


async def delete_case(guild_id: int, case_id: int) -> bool:
    changed = await _execute(
        "DELETE FROM cases WHERE guild_id = $1 AND id = $2",
        guild_id, case_id,
    )
    return changed > 0


async def get_warn_count(guild_id: int, user_id: int) -> int:
    val = await _fetch_val(
        "SELECT COUNT(*) FROM cases WHERE guild_id = $1 AND user_id = $2 AND action_type = 'warn'",
        guild_id, user_id,
    )
    return val or 0


async def get_action_counts(guild_id: int) -> list[asyncpg.Record]:
    return await _fetch_all(
        """
        SELECT action_type, COUNT(*) AS total
        FROM cases
        WHERE guild_id = $1
        GROUP BY action_type
        ORDER BY total DESC
        """,
        guild_id,
    )


async def get_top_moderators(guild_id: int, limit: int = 5) -> list[asyncpg.Record]:
    return await _fetch_all(
        """
        SELECT moderator_id, COUNT(*) AS total
        FROM cases
        WHERE guild_id = $1
        GROUP BY moderator_id
        ORDER BY total DESC
        LIMIT $2
        """,
        guild_id, limit,
    )


async def get_most_warned_users(guild_id: int, limit: int = 5) -> list[asyncpg.Record]:
    return await _fetch_all(
        """
        SELECT user_id, COUNT(*) AS total
        FROM cases
        WHERE guild_id = $1 AND action_type = 'warn'
        GROUP BY user_id
        ORDER BY total DESC
        LIMIT $2
        """,
        guild_id, limit,
    )


# --- Guild settings -----------------------------------------------------------

DEFAULT_SETTINGS: dict = {
    "log_channel_id": None,
    "server_log_channel_id": None,
    "lockdown_role_id": None,
    "raid_min_account_age_hours": None,
    "warn_mute_threshold": None,
    "warn_mute_minutes": None,
    "warn_kick_threshold": None,
    "warn_ban_threshold": None,
}


async def get_guild_settings(guild_id: int) -> dict:
    row = await _fetch_one("SELECT * FROM guild_settings WHERE guild_id = $1", guild_id)
    if row is None:
        return {"guild_id": guild_id, **DEFAULT_SETTINGS}
    return dict(row)


async def _upsert_settings(guild_id: int, column: str, value) -> None:
    async with _get_pool().acquire() as conn:
        await conn.execute(
            f"""
            INSERT INTO guild_settings (guild_id, {column})
            VALUES ($1, $2)
            ON CONFLICT (guild_id) DO UPDATE SET {column} = EXCLUDED.{column}
            """,
            guild_id, value,
        )


async def set_log_channel(guild_id: int, channel_id: int) -> None:
    await _upsert_settings(guild_id, "log_channel_id", channel_id)


async def set_server_log_channel(guild_id: int, channel_id: int | None) -> None:
    await _upsert_settings(guild_id, "server_log_channel_id", channel_id)


async def set_lockdown_role(guild_id: int, role_id: int | None) -> None:
    await _upsert_settings(guild_id, "lockdown_role_id", role_id)


async def set_raid_protection(guild_id: int, min_account_age_hours: int | None) -> None:
    await _upsert_settings(guild_id, "raid_min_account_age_hours", min_account_age_hours)


async def set_warn_thresholds(
    guild_id: int,
    mute_threshold: int | None,
    mute_minutes: int | None,
    kick_threshold: int | None,
    ban_threshold: int | None,
) -> None:
    async with _get_pool().acquire() as conn:
        await conn.execute(
            """
            INSERT INTO guild_settings
                (guild_id, warn_mute_threshold, warn_mute_minutes, warn_kick_threshold, warn_ban_threshold)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (guild_id) DO UPDATE SET
                warn_mute_threshold = EXCLUDED.warn_mute_threshold,
                warn_mute_minutes   = EXCLUDED.warn_mute_minutes,
                warn_kick_threshold = EXCLUDED.warn_kick_threshold,
                warn_ban_threshold  = EXCLUDED.warn_ban_threshold
            """,
            guild_id, mute_threshold, mute_minutes, kick_threshold, ban_threshold,
        )


# --- Lockdown roles ----------------------------------------------------------

async def get_lockdown_role_ids(guild_id: int) -> list[int]:
    rows = await _fetch_all(
        "SELECT role_id FROM lockdown_roles WHERE guild_id = $1 ORDER BY role_id",
        guild_id,
    )
    return [row["role_id"] for row in rows]


async def add_lockdown_role(guild_id: int, role_id: int) -> None:
    await _execute(
        "INSERT INTO lockdown_roles (guild_id, role_id) VALUES ($1, $2) ON CONFLICT DO NOTHING",
        guild_id, role_id,
    )


async def remove_lockdown_role(guild_id: int, role_id: int) -> bool:
    changed = await _execute(
        "DELETE FROM lockdown_roles WHERE guild_id = $1 AND role_id = $2",
        guild_id, role_id,
    )
    return changed > 0


async def clear_lockdown_roles(guild_id: int) -> None:
    await _execute("DELETE FROM lockdown_roles WHERE guild_id = $1", guild_id)


# --- Temporary bans ----------------------------------------------------------

async def add_temp_ban(guild_id: int, user_id: int, unban_at: datetime) -> None:
    await _execute(
        """
        INSERT INTO temp_bans (guild_id, user_id, unban_at)
        VALUES ($1, $2, $3)
        ON CONFLICT (guild_id, user_id) DO UPDATE SET unban_at = EXCLUDED.unban_at
        """,
        guild_id, user_id, unban_at.isoformat(),
    )


async def remove_temp_ban(guild_id: int, user_id: int) -> None:
    await _execute(
        "DELETE FROM temp_bans WHERE guild_id = $1 AND user_id = $2",
        guild_id, user_id,
    )


async def get_expired_temp_bans(now: datetime) -> list[asyncpg.Record]:
    return await _fetch_all(
        "SELECT guild_id, user_id FROM temp_bans WHERE unban_at <= $1",
        now.isoformat(),
    )


# --- Channel lock state -------------------------------------------------------

async def save_channel_lock(guild_id: int, channel_id: int, role_states: dict[int, str]) -> None:
    await _execute(
        """
        INSERT INTO channel_locks (guild_id, channel_id, previous_state)
        VALUES ($1, $2, $3)
        ON CONFLICT (guild_id, channel_id) DO UPDATE SET previous_state = EXCLUDED.previous_state
        """,
        guild_id, channel_id, json.dumps({str(k): v for k, v in role_states.items()}),
    )


async def pop_channel_lock(guild_id: int, channel_id: int) -> dict[int, str] | None:
    """Return {role_id: tristate_string} and delete the row, or None if none recorded."""
    row = await _fetch_one(
        "DELETE FROM channel_locks WHERE guild_id = $1 AND channel_id = $2 RETURNING previous_state",
        guild_id, channel_id,
    )
    if row is None:
        return None
    try:
        return {int(k): v for k, v in json.loads(row["previous_state"]).items()}
    except (json.JSONDecodeError, ValueError):
        return None


# --- Health checks -----------------------------------------------------------

async def check_connection() -> tuple[bool, str]:
    try:
        started = _time.perf_counter()
        await _fetch_val("SELECT 1")
        elapsed_ms = (_time.perf_counter() - started) * 1000
        return True, f"{elapsed_ms:.1f}ms"
    except Exception as error:
        return False, str(error)


async def get_total_case_count() -> int:
    return (await _fetch_val("SELECT COUNT(*) FROM cases")) or 0


async def get_active_temp_ban_count() -> int:
    return (await _fetch_val("SELECT COUNT(*) FROM temp_bans")) or 0

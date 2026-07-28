from datetime import datetime, timezone

import aiosqlite

from config import DATABASE_PATH

_connection: aiosqlite.Connection | None = None

SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS cases (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        moderator_id INTEGER NOT NULL,
        action_type TEXT NOT NULL,
        reason TEXT,
        created_at TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_cases_guild_user ON cases (guild_id, user_id)",
    "CREATE INDEX IF NOT EXISTS idx_cases_guild_action ON cases (guild_id, action_type)",
    """
    CREATE TABLE IF NOT EXISTS guild_settings (
        guild_id INTEGER PRIMARY KEY,
        log_channel_id INTEGER,
        lockdown_role_id INTEGER,
        raid_min_account_age_hours INTEGER,
        warn_mute_threshold INTEGER,
        warn_mute_minutes INTEGER,
        warn_kick_threshold INTEGER,
        warn_ban_threshold INTEGER
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS temp_bans (
        guild_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        unban_at TEXT NOT NULL,
        PRIMARY KEY (guild_id, user_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_temp_bans_unban_at ON temp_bans (unban_at)",
    """
    CREATE TABLE IF NOT EXISTS channel_locks (
        guild_id INTEGER NOT NULL,
        channel_id INTEGER NOT NULL,
        previous_state TEXT NOT NULL,
        PRIMARY KEY (guild_id, channel_id)
    )
    """,
)


# Columns added after the first release. CREATE TABLE IF NOT EXISTS won't add these to an
# existing database, so they're applied separately on every startup.
ADDED_COLUMNS = (
    ("guild_settings", "lockdown_role_id", "INTEGER"),
)


async def _apply_column_migrations(connection: aiosqlite.Connection) -> None:
    for table_name, column_name, column_type in ADDED_COLUMNS:
        cursor = await connection.execute(f"PRAGMA table_info({table_name})")
        existing_columns = {row["name"] for row in await cursor.fetchall()}
        if column_name not in existing_columns:
            await connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")


async def connect_database() -> None:
    """Open the shared connection and apply the schema. Call once at startup."""
    global _connection
    _connection = await aiosqlite.connect(DATABASE_PATH)
    _connection.row_factory = aiosqlite.Row

    # WAL lets reads proceed during a write, so the temp-ban loop never blocks a lookup.
    await _connection.execute("PRAGMA journal_mode=WAL")
    await _connection.execute("PRAGMA synchronous=NORMAL")

    for statement in SCHEMA_STATEMENTS:
        await _connection.execute(statement)
    await _apply_column_migrations(_connection)
    await _connection.commit()


async def close_database() -> None:
    global _connection
    if _connection is not None:
        await _connection.close()
        _connection = None


def _db() -> aiosqlite.Connection:
    if _connection is None:
        raise RuntimeError("Database is not connected. Call connect_database() during startup.")
    return _connection


async def _fetch_all(query: str, parameters: tuple = ()) -> list[aiosqlite.Row]:
    cursor = await _db().execute(query, parameters)
    return await cursor.fetchall()


async def _fetch_one(query: str, parameters: tuple = ()) -> aiosqlite.Row | None:
    cursor = await _db().execute(query, parameters)
    return await cursor.fetchone()


async def _execute(query: str, parameters: tuple = ()) -> int:
    cursor = await _db().execute(query, parameters)
    await _db().commit()
    return cursor.rowcount


# --- Cases -------------------------------------------------------------------

async def add_case(guild_id: int, user_id: int, moderator_id: int, action_type: str, reason: str) -> int:
    cursor = await _db().execute(
        """
        INSERT INTO cases (guild_id, user_id, moderator_id, action_type, reason, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (guild_id, user_id, moderator_id, action_type, reason, datetime.now(timezone.utc).isoformat()),
    )
    await _db().commit()
    return cursor.lastrowid


async def get_cases_for_user(guild_id: int, user_id: int) -> list[aiosqlite.Row]:
    return await _fetch_all(
        """
        SELECT id, moderator_id, action_type, reason, created_at
        FROM cases
        WHERE guild_id = ? AND user_id = ?
        ORDER BY id DESC
        """,
        (guild_id, user_id),
    )


async def get_all_cases(guild_id: int) -> list[aiosqlite.Row]:
    return await _fetch_all(
        """
        SELECT id, user_id, moderator_id, action_type, reason, created_at
        FROM cases
        WHERE guild_id = ?
        ORDER BY id ASC
        """,
        (guild_id,),
    )


async def get_case_by_id(guild_id: int, case_id: int) -> aiosqlite.Row | None:
    return await _fetch_one("SELECT * FROM cases WHERE guild_id = ? AND id = ?", (guild_id, case_id))


async def update_case_reason(guild_id: int, case_id: int, new_reason: str) -> bool:
    changed = await _execute(
        "UPDATE cases SET reason = ? WHERE guild_id = ? AND id = ?",
        (new_reason, guild_id, case_id),
    )
    return changed > 0


async def delete_case(guild_id: int, case_id: int) -> bool:
    changed = await _execute("DELETE FROM cases WHERE guild_id = ? AND id = ?", (guild_id, case_id))
    return changed > 0


async def get_warn_count(guild_id: int, user_id: int) -> int:
    row = await _fetch_one(
        "SELECT COUNT(*) AS total FROM cases WHERE guild_id = ? AND user_id = ? AND action_type = 'warn'",
        (guild_id, user_id),
    )
    return row["total"]


async def get_action_counts(guild_id: int) -> list[aiosqlite.Row]:
    return await _fetch_all(
        """
        SELECT action_type, COUNT(*) AS total
        FROM cases
        WHERE guild_id = ?
        GROUP BY action_type
        ORDER BY total DESC
        """,
        (guild_id,),
    )


async def get_top_moderators(guild_id: int, limit: int = 5) -> list[aiosqlite.Row]:
    return await _fetch_all(
        """
        SELECT moderator_id, COUNT(*) AS total
        FROM cases
        WHERE guild_id = ?
        GROUP BY moderator_id
        ORDER BY total DESC
        LIMIT ?
        """,
        (guild_id, limit),
    )


async def get_most_warned_users(guild_id: int, limit: int = 5) -> list[aiosqlite.Row]:
    return await _fetch_all(
        """
        SELECT user_id, COUNT(*) AS total
        FROM cases
        WHERE guild_id = ? AND action_type = 'warn'
        GROUP BY user_id
        ORDER BY total DESC
        LIMIT ?
        """,
        (guild_id, limit),
    )


# --- Guild settings -----------------------------------------------------------

DEFAULT_SETTINGS = {
    "log_channel_id": None,
    "lockdown_role_id": None,
    "raid_min_account_age_hours": None,
    "warn_mute_threshold": None,
    "warn_mute_minutes": None,
    "warn_kick_threshold": None,
    "warn_ban_threshold": None,
}


async def get_guild_settings(guild_id: int) -> dict:
    row = await _fetch_one("SELECT * FROM guild_settings WHERE guild_id = ?", (guild_id,))
    if row is None:
        return {"guild_id": guild_id, **DEFAULT_SETTINGS}
    return dict(row)


async def _upsert_settings(guild_id: int, assignments: str, values: tuple) -> None:
    await _db().execute("INSERT OR IGNORE INTO guild_settings (guild_id) VALUES (?)", (guild_id,))
    await _db().execute(f"UPDATE guild_settings SET {assignments} WHERE guild_id = ?", (*values, guild_id))
    await _db().commit()


async def set_log_channel(guild_id: int, channel_id: int) -> None:
    await _upsert_settings(guild_id, "log_channel_id = ?", (channel_id,))


async def set_lockdown_role(guild_id: int, role_id: int | None) -> None:
    await _upsert_settings(guild_id, "lockdown_role_id = ?", (role_id,))


async def set_raid_protection(guild_id: int, min_account_age_hours: int | None) -> None:
    await _upsert_settings(guild_id, "raid_min_account_age_hours = ?", (min_account_age_hours,))


async def set_warn_thresholds(
    guild_id: int,
    mute_threshold: int | None,
    mute_minutes: int | None,
    kick_threshold: int | None,
    ban_threshold: int | None,
) -> None:
    await _upsert_settings(
        guild_id,
        "warn_mute_threshold = ?, warn_mute_minutes = ?, warn_kick_threshold = ?, warn_ban_threshold = ?",
        (mute_threshold, mute_minutes, kick_threshold, ban_threshold),
    )


# --- Temporary bans -------------------------------------------------------------

async def add_temp_ban(guild_id: int, user_id: int, unban_at: datetime) -> None:
    await _execute(
        """
        INSERT INTO temp_bans (guild_id, user_id, unban_at)
        VALUES (?, ?, ?)
        ON CONFLICT (guild_id, user_id) DO UPDATE SET unban_at = excluded.unban_at
        """,
        (guild_id, user_id, unban_at.isoformat()),
    )


async def remove_temp_ban(guild_id: int, user_id: int) -> None:
    await _execute("DELETE FROM temp_bans WHERE guild_id = ? AND user_id = ?", (guild_id, user_id))


async def get_expired_temp_bans(now: datetime) -> list[aiosqlite.Row]:
    return await _fetch_all(
        "SELECT guild_id, user_id FROM temp_bans WHERE unban_at <= ?",
        (now.isoformat(),),
    )


# --- Channel lock state ----------------------------------------------------------

async def save_channel_lock(guild_id: int, channel_id: int, previous_state: str) -> None:
    await _execute(
        """
        INSERT INTO channel_locks (guild_id, channel_id, previous_state)
        VALUES (?, ?, ?)
        ON CONFLICT (guild_id, channel_id) DO UPDATE SET previous_state = excluded.previous_state
        """,
        (guild_id, channel_id, previous_state),
    )


async def pop_channel_lock(guild_id: int, channel_id: int) -> str | None:
    row = await _fetch_one(
        "SELECT previous_state FROM channel_locks WHERE guild_id = ? AND channel_id = ?",
        (guild_id, channel_id),
    )
    if row is None:
        return None

    await _execute("DELETE FROM channel_locks WHERE guild_id = ? AND channel_id = ?", (guild_id, channel_id))
    return row["previous_state"]


# --- Health checks (used by the debug cog) -----------------------------------

import time as _time


async def check_connection() -> tuple[bool, str]:
    """Ping the database with a lightweight query and return (ok, detail)."""
    try:
        started = _time.perf_counter()
        await _fetch_one("SELECT 1")
        elapsed_ms = (_time.perf_counter() - started) * 1000
        return True, f"{elapsed_ms:.1f}ms"
    except Exception as error:
        return False, str(error)


async def get_total_case_count() -> int:
    row = await _fetch_one("SELECT COUNT(*) AS total FROM cases")
    return row["total"] if row else 0


async def get_active_temp_ban_count() -> int:
    row = await _fetch_one("SELECT COUNT(*) AS total FROM temp_bans")
    return row["total"] if row else 0

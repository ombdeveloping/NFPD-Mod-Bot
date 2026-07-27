from datetime import datetime, timezone

import aiosqlite

from config import DATABASE_PATH as DB_PATH


async def initialize_database() -> None:
    async with aiosqlite.connect(DB_PATH) as connection:
        await connection.execute(
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
            """
        )
        await connection.execute(
            """
            CREATE TABLE IF NOT EXISTS guild_settings (
                guild_id INTEGER PRIMARY KEY,
                log_channel_id INTEGER,
                raid_min_account_age_hours INTEGER,
                warn_mute_threshold INTEGER,
                warn_mute_minutes INTEGER,
                warn_kick_threshold INTEGER,
                warn_ban_threshold INTEGER
            )
            """
        )
        await connection.execute(
            """
            CREATE TABLE IF NOT EXISTS temp_bans (
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                unban_at TEXT NOT NULL,
                PRIMARY KEY (guild_id, user_id)
            )
            """
        )
        await connection.execute(
            """
            CREATE TABLE IF NOT EXISTS channel_locks (
                guild_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                previous_state TEXT NOT NULL,
                PRIMARY KEY (guild_id, channel_id)
            )
            """
        )
        await connection.commit()


# --- Cases -----------------------------------------------------------------

async def add_case(guild_id: int, user_id: int, moderator_id: int, action_type: str, reason: str) -> int:
    created_at = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(DB_PATH) as connection:
        cursor = await connection.execute(
            """
            INSERT INTO cases (guild_id, user_id, moderator_id, action_type, reason, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (guild_id, user_id, moderator_id, action_type, reason, created_at),
        )
        await connection.commit()
        return cursor.lastrowid


async def get_cases_for_user(guild_id: int, user_id: int) -> list[aiosqlite.Row]:
    async with aiosqlite.connect(DB_PATH) as connection:
        connection.row_factory = aiosqlite.Row
        cursor = await connection.execute(
            """
            SELECT id, moderator_id, action_type, reason, created_at
            FROM cases
            WHERE guild_id = ? AND user_id = ?
            ORDER BY id DESC
            """,
            (guild_id, user_id),
        )
        return await cursor.fetchall()


async def get_case_by_id(guild_id: int, case_id: int) -> aiosqlite.Row | None:
    async with aiosqlite.connect(DB_PATH) as connection:
        connection.row_factory = aiosqlite.Row
        cursor = await connection.execute(
            "SELECT * FROM cases WHERE guild_id = ? AND id = ?",
            (guild_id, case_id),
        )
        return await cursor.fetchone()


async def update_case_reason(guild_id: int, case_id: int, new_reason: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as connection:
        cursor = await connection.execute(
            "UPDATE cases SET reason = ? WHERE guild_id = ? AND id = ?",
            (new_reason, guild_id, case_id),
        )
        await connection.commit()
        return cursor.rowcount > 0


async def delete_case(guild_id: int, case_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as connection:
        cursor = await connection.execute(
            "DELETE FROM cases WHERE guild_id = ? AND id = ?",
            (guild_id, case_id),
        )
        await connection.commit()
        return cursor.rowcount > 0


async def get_warn_count(guild_id: int, user_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as connection:
        cursor = await connection.execute(
            "SELECT COUNT(*) FROM cases WHERE guild_id = ? AND user_id = ? AND action_type = 'warn'",
            (guild_id, user_id),
        )
        row = await cursor.fetchone()
        return row[0]


async def get_action_counts(guild_id: int) -> list[aiosqlite.Row]:
    async with aiosqlite.connect(DB_PATH) as connection:
        connection.row_factory = aiosqlite.Row
        cursor = await connection.execute(
            """
            SELECT action_type, COUNT(*) AS total
            FROM cases
            WHERE guild_id = ?
            GROUP BY action_type
            ORDER BY total DESC
            """,
            (guild_id,),
        )
        return await cursor.fetchall()


async def get_top_moderators(guild_id: int, limit: int = 5) -> list[aiosqlite.Row]:
    async with aiosqlite.connect(DB_PATH) as connection:
        connection.row_factory = aiosqlite.Row
        cursor = await connection.execute(
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
        return await cursor.fetchall()


async def get_most_warned_users(guild_id: int, limit: int = 5) -> list[aiosqlite.Row]:
    async with aiosqlite.connect(DB_PATH) as connection:
        connection.row_factory = aiosqlite.Row
        cursor = await connection.execute(
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
        return await cursor.fetchall()


# --- Guild settings ---------------------------------------------------------

def _default_guild_settings(guild_id: int) -> dict:
    return {
        "guild_id": guild_id,
        "log_channel_id": None,
        "raid_min_account_age_hours": None,
        "warn_mute_threshold": None,
        "warn_mute_minutes": None,
        "warn_kick_threshold": None,
        "warn_ban_threshold": None,
    }


async def get_guild_settings(guild_id: int) -> dict:
    async with aiosqlite.connect(DB_PATH) as connection:
        connection.row_factory = aiosqlite.Row
        cursor = await connection.execute(
            "SELECT * FROM guild_settings WHERE guild_id = ?",
            (guild_id,),
        )
        row = await cursor.fetchone()
        return dict(row) if row is not None else _default_guild_settings(guild_id)


async def _ensure_guild_settings_row(guild_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as connection:
        await connection.execute(
            "INSERT OR IGNORE INTO guild_settings (guild_id) VALUES (?)",
            (guild_id,),
        )
        await connection.commit()


async def set_log_channel(guild_id: int, channel_id: int) -> None:
    await _ensure_guild_settings_row(guild_id)
    async with aiosqlite.connect(DB_PATH) as connection:
        await connection.execute(
            "UPDATE guild_settings SET log_channel_id = ? WHERE guild_id = ?",
            (channel_id, guild_id),
        )
        await connection.commit()


async def set_raid_protection(guild_id: int, min_account_age_hours: int | None) -> None:
    await _ensure_guild_settings_row(guild_id)
    async with aiosqlite.connect(DB_PATH) as connection:
        await connection.execute(
            "UPDATE guild_settings SET raid_min_account_age_hours = ? WHERE guild_id = ?",
            (min_account_age_hours, guild_id),
        )
        await connection.commit()


async def set_warn_thresholds(
    guild_id: int,
    mute_threshold: int | None,
    mute_minutes: int | None,
    kick_threshold: int | None,
    ban_threshold: int | None,
) -> None:
    await _ensure_guild_settings_row(guild_id)
    async with aiosqlite.connect(DB_PATH) as connection:
        await connection.execute(
            """
            UPDATE guild_settings
            SET warn_mute_threshold = ?, warn_mute_minutes = ?, warn_kick_threshold = ?, warn_ban_threshold = ?
            WHERE guild_id = ?
            """,
            (mute_threshold, mute_minutes, kick_threshold, ban_threshold, guild_id),
        )
        await connection.commit()


# --- Temporary bans ----------------------------------------------------------

async def add_temp_ban(guild_id: int, user_id: int, unban_at: datetime) -> None:
    async with aiosqlite.connect(DB_PATH) as connection:
        await connection.execute(
            """
            INSERT INTO temp_bans (guild_id, user_id, unban_at)
            VALUES (?, ?, ?)
            ON CONFLICT (guild_id, user_id) DO UPDATE SET unban_at = excluded.unban_at
            """,
            (guild_id, user_id, unban_at.isoformat()),
        )
        await connection.commit()


async def remove_temp_ban(guild_id: int, user_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as connection:
        await connection.execute(
            "DELETE FROM temp_bans WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        )
        await connection.commit()


async def get_expired_temp_bans(now: datetime) -> list[aiosqlite.Row]:
    async with aiosqlite.connect(DB_PATH) as connection:
        connection.row_factory = aiosqlite.Row
        cursor = await connection.execute(
            "SELECT guild_id, user_id FROM temp_bans WHERE unban_at <= ?",
            (now.isoformat(),),
        )
        return await cursor.fetchall()


# --- Channel lock state --------------------------------------------------------

async def save_channel_lock(guild_id: int, channel_id: int, previous_state: str) -> None:
    async with aiosqlite.connect(DB_PATH) as connection:
        await connection.execute(
            """
            INSERT INTO channel_locks (guild_id, channel_id, previous_state)
            VALUES (?, ?, ?)
            ON CONFLICT (guild_id, channel_id) DO UPDATE SET previous_state = excluded.previous_state
            """,
            (guild_id, channel_id, previous_state),
        )
        await connection.commit()


async def pop_channel_lock(guild_id: int, channel_id: int) -> str | None:
    async with aiosqlite.connect(DB_PATH) as connection:
        connection.row_factory = aiosqlite.Row
        cursor = await connection.execute(
            "SELECT previous_state FROM channel_locks WHERE guild_id = ? AND channel_id = ?",
            (guild_id, channel_id),
        )
        row = await cursor.fetchone()
        if row is None:
            return None

        await connection.execute(
            "DELETE FROM channel_locks WHERE guild_id = ? AND channel_id = ?",
            (guild_id, channel_id),
        )
        await connection.commit()
        return row["previous_state"]

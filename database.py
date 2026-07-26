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
        await connection.commit()


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

"""users + user_bazi CRUD. asyncpg Connection 주입 받음."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import asyncpg


@dataclass
class UserProfile:
    telegram_chat_id: int
    birth_year: int
    birth_month: int
    birth_day: int
    birth_hour: int
    birth_minute: int
    asset_class_pref: str = "swing"
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


_UPSERT_USER = """
INSERT INTO users (telegram_chat_id) VALUES ($1)
ON CONFLICT (telegram_chat_id) DO UPDATE
    SET updated_at = now()
RETURNING created_at, updated_at
"""

_UPSERT_BAZI = """
INSERT INTO user_bazi (
    telegram_chat_id, birth_year, birth_month, birth_day,
    birth_hour, birth_minute, asset_class_pref
) VALUES ($1, $2, $3, $4, $5, $6, $7)
ON CONFLICT (telegram_chat_id) DO UPDATE SET
    birth_year = EXCLUDED.birth_year,
    birth_month = EXCLUDED.birth_month,
    birth_day = EXCLUDED.birth_day,
    birth_hour = EXCLUDED.birth_hour,
    birth_minute = EXCLUDED.birth_minute,
    asset_class_pref = EXCLUDED.asset_class_pref,
    updated_at = now()
RETURNING created_at, updated_at
"""

_SELECT = """
SELECT u.telegram_chat_id,
       b.birth_year, b.birth_month, b.birth_day,
       b.birth_hour, b.birth_minute,
       b.asset_class_pref,
       u.created_at, u.updated_at
FROM users u
JOIN user_bazi b USING (telegram_chat_id)
WHERE u.telegram_chat_id = $1
"""


async def upsert_user(conn: asyncpg.Connection, profile: UserProfile) -> UserProfile:
    """users + user_bazi upsert. 단일 트랜잭션."""
    async with conn.transaction():
        u_row = await conn.fetchrow(_UPSERT_USER, profile.telegram_chat_id)
        b_row = await conn.fetchrow(
            _UPSERT_BAZI,
            profile.telegram_chat_id,
            profile.birth_year,
            profile.birth_month,
            profile.birth_day,
            profile.birth_hour,
            profile.birth_minute,
            profile.asset_class_pref,
        )
    return UserProfile(
        telegram_chat_id=profile.telegram_chat_id,
        birth_year=profile.birth_year,
        birth_month=profile.birth_month,
        birth_day=profile.birth_day,
        birth_hour=profile.birth_hour,
        birth_minute=profile.birth_minute,
        asset_class_pref=profile.asset_class_pref,
        created_at=u_row["created_at"],
        updated_at=b_row["updated_at"],
    )


async def get_user(conn: asyncpg.Connection, chat_id: int) -> Optional[UserProfile]:
    row = await conn.fetchrow(_SELECT, chat_id)
    if row is None:
        return None
    return UserProfile(
        telegram_chat_id=row["telegram_chat_id"],
        birth_year=row["birth_year"],
        birth_month=row["birth_month"],
        birth_day=row["birth_day"],
        birth_hour=row["birth_hour"],
        birth_minute=row["birth_minute"],
        asset_class_pref=row["asset_class_pref"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


async def delete_user(conn: asyncpg.Connection, chat_id: int) -> None:
    """ON DELETE CASCADE로 user_bazi도 함께 삭제. 없으면 no-op."""
    await conn.execute("DELETE FROM users WHERE telegram_chat_id = $1", chat_id)

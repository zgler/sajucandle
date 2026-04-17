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


async def list_chat_ids(conn: asyncpg.Connection) -> list[int]:
    """명식이 등록된 모든 사용자의 chat_id 리스트.

    user_bazi 기준. users에만 있고 명식 없는 레코드는 제외 (/score가 어차피 실패).
    반환 순서는 보장 X.
    """
    rows = await conn.fetch("SELECT telegram_chat_id FROM user_bazi")
    return [r["telegram_chat_id"] for r in rows]


# ─────────────────────────────────────────────
# Week 7: watchlist
# ─────────────────────────────────────────────


@dataclass
class WatchlistEntry:
    ticker: str
    added_at: datetime


async def list_watchlist(
    conn: asyncpg.Connection, chat_id: int
) -> list[WatchlistEntry]:
    """사용자의 watchlist (added_at ASC). 비어있으면 []."""
    rows = await conn.fetch(
        "SELECT ticker, added_at FROM user_watchlist "
        "WHERE telegram_chat_id = $1 ORDER BY added_at ASC",
        chat_id,
    )
    return [WatchlistEntry(ticker=r["ticker"], added_at=r["added_at"]) for r in rows]


async def add_to_watchlist(
    conn: asyncpg.Connection, chat_id: int, ticker: str
) -> None:
    """INSERT. 중복이면 asyncpg.UniqueViolationError 전파."""
    await conn.execute(
        "INSERT INTO user_watchlist (telegram_chat_id, ticker) VALUES ($1, $2)",
        chat_id, ticker,
    )


async def remove_from_watchlist(
    conn: asyncpg.Connection, chat_id: int, ticker: str
) -> bool:
    """DELETE. True=삭제됨, False=애초에 없었음."""
    result = await conn.execute(
        "DELETE FROM user_watchlist "
        "WHERE telegram_chat_id = $1 AND ticker = $2",
        chat_id, ticker,
    )
    # asyncpg execute는 "DELETE N" 형태 문자열 반환
    return result.endswith(" 1")


async def count_watchlist(
    conn: asyncpg.Connection, chat_id: int
) -> int:
    """현재 등록된 심볼 개수."""
    n = await conn.fetchval(
        "SELECT COUNT(*) FROM user_watchlist WHERE telegram_chat_id = $1",
        chat_id,
    )
    return int(n or 0)


async def list_all_watchlist_tickers(
    conn: asyncpg.Connection,
) -> set[str]:
    """모든 사용자 watchlist ticker union. broadcast precompute용."""
    rows = await conn.fetch("SELECT DISTINCT ticker FROM user_watchlist")
    return {r["ticker"] for r in rows}

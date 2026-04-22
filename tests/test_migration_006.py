"""Migration 006: signal_direction 컬럼 검증.

TEST_DATABASE_URL에 migration 006이 적용돼 있어야 한다
(conftest 동일 원칙 — 스키마는 사전 적용).
"""
from __future__ import annotations

import pytest
import asyncpg


async def test_signal_direction_column_exists(db_conn):
    row = await db_conn.fetchrow(
        """
        SELECT data_type
        FROM information_schema.columns
        WHERE table_name = 'signal_log' AND column_name = 'signal_direction'
        """
    )
    assert row is not None, "migration 006 미적용: signal_direction 컬럼 없음"
    assert row["data_type"] == "text"


async def test_signal_direction_check_constraint_rejects_invalid(db_conn):
    await db_conn.execute(
        """
        INSERT INTO users (telegram_chat_id, birth_year, birth_month,
                           birth_day, birth_hour, birth_minute)
        VALUES (999001, 1990, 1, 1, 0, 0)
        """
    )
    with pytest.raises(asyncpg.CheckViolationError):
        await db_conn.execute(
            """
            INSERT INTO signal_log (
                telegram_chat_id, ticker, target_date,
                composite_score, signal_grade, signal_direction
            ) VALUES ($1, $2, CURRENT_DATE, $3, $4, $5)
            """,
            999001, "BTCUSDT", 80, "진입_L", "INVALID",
        )


async def test_signal_direction_accepts_null(db_conn):
    await db_conn.execute(
        """
        INSERT INTO users (telegram_chat_id, birth_year, birth_month,
                           birth_day, birth_hour, birth_minute)
        VALUES (999002, 1990, 1, 1, 0, 0)
        """
    )
    await db_conn.execute(
        """
        INSERT INTO signal_log (
            telegram_chat_id, ticker, target_date,
            composite_score, signal_grade, signal_direction
        ) VALUES ($1, $2, CURRENT_DATE, $3, $4, NULL)
        """,
        999002, "BTCUSDT", 80, "진입", None,
    )
    got = await db_conn.fetchval(
        "SELECT signal_direction FROM signal_log WHERE telegram_chat_id=$1",
        999002,
    )
    assert got is None


async def test_signal_direction_accepts_long_short_neutral(db_conn):
    await db_conn.execute(
        """
        INSERT INTO users (telegram_chat_id, birth_year, birth_month,
                           birth_day, birth_hour, birth_minute)
        VALUES (999003, 1990, 1, 1, 0, 0)
        """
    )
    for direction in ("LONG", "SHORT", "NEUTRAL"):
        await db_conn.execute(
            """
            INSERT INTO signal_log (
                telegram_chat_id, ticker, target_date,
                composite_score, signal_grade, signal_direction
            ) VALUES ($1, $2, CURRENT_DATE, $3, $4, $5)
            """,
            999003, f"T{direction}", 60, "관망", direction,
        )
    got = await db_conn.fetch(
        "SELECT signal_direction FROM signal_log WHERE telegram_chat_id=$1",
        999003,
    )
    assert sorted(r["signal_direction"] for r in got) == ["LONG", "NEUTRAL", "SHORT"]

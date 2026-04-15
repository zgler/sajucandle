"""asyncpg Pool 싱글톤 테스트. 연결 테스트는 TEST_DATABASE_URL 필요."""
from __future__ import annotations

import os

import pytest

from sajucandle import db


@pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL not set",
)
async def test_connect_and_close():
    """connect() → ping → close()."""
    dsn = os.environ["TEST_DATABASE_URL"]
    await db.connect(dsn)
    try:
        async with db.acquire() as conn:
            result = await conn.fetchval("SELECT 1")
            assert result == 1
    finally:
        await db.close()


async def test_acquire_raises_when_not_connected():
    """connect() 전에 acquire()하면 명확한 에러."""
    await db.close()  # 혹시 열려있으면 닫음
    with pytest.raises(RuntimeError, match="not connected"):
        async with db.acquire() as _:
            pass

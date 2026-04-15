"""공통 fixture. DB 테스트는 TEST_DATABASE_URL 필요."""
from __future__ import annotations

import os

import pytest
import pytest_asyncio

from sajucandle import db


TEST_DSN = os.environ.get("TEST_DATABASE_URL")


@pytest_asyncio.fixture
async def db_pool():
    """세션 내내 Pool 1개. 없으면 스킵 시그널."""
    if not TEST_DSN:
        pytest.skip("TEST_DATABASE_URL not set")
    await db.connect(TEST_DSN, min_size=1, max_size=2)
    yield db.get_pool()
    await db.close()


@pytest_asyncio.fixture
async def db_conn(db_pool):
    """각 테스트마다 BEGIN → 테스트 → ROLLBACK.

    스키마는 migrations/001_init.sql이 TEST DB에 이미 적용되어 있어야 함.
    테스트 간 완전 격리를 위해 모든 변경은 롤백된다.
    """
    async with db_pool.acquire() as conn:
        tx = conn.transaction()
        await tx.start()
        try:
            yield conn
        finally:
            await tx.rollback()

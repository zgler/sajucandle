"""asyncpg Pool 싱글톤.

FastAPI lifespan에서 `await connect(dsn)` / `await close()`.
핸들러에서는 `async with acquire() as conn: ...`.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional

import asyncpg

logger = logging.getLogger(__name__)

_pool: Optional[asyncpg.Pool] = None


async def connect(dsn: str, min_size: int = 1, max_size: int = 5) -> None:
    """Pool 생성. 이미 열려있으면 no-op."""
    global _pool
    if _pool is not None:
        return
    _pool = await asyncpg.create_pool(dsn, min_size=min_size, max_size=max_size)
    logger.info("asyncpg pool ready (min=%d max=%d)", min_size, max_size)


async def close() -> None:
    """Pool 닫기. 열려있지 않으면 no-op."""
    global _pool
    if _pool is None:
        return
    await _pool.close()
    _pool = None
    logger.info("asyncpg pool closed")


@asynccontextmanager
async def acquire() -> AsyncIterator[asyncpg.Connection]:
    """Pool에서 커넥션 획득. Pool이 없으면 RuntimeError."""
    if _pool is None:
        raise RuntimeError("db not connected; call db.connect(dsn) first")
    async with _pool.acquire() as conn:
        yield conn


def get_pool() -> Optional[asyncpg.Pool]:
    """헬스체크용. None이면 미연결."""
    return _pool

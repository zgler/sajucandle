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


async def connect(
    dsn: str,
    min_size: int = 1,
    max_size: int = 5,
    statement_cache_size: Optional[int] = None,
) -> None:
    """Pool 생성. 이미 열려있으면 no-op.

    statement_cache_size: None=asyncpg 기본값(1024). Supabase transaction
    pooler(port 6543)는 prepared statement 미지원이므로 이 경우 0 권장.
    """
    global _pool
    if _pool is not None:
        return
    kwargs: dict = {"min_size": min_size, "max_size": max_size}
    if statement_cache_size is not None:
        kwargs["statement_cache_size"] = statement_cache_size
    _pool = await asyncpg.create_pool(dsn, **kwargs)
    logger.info(
        "asyncpg pool ready (min=%d max=%d stmt_cache=%s)",
        min_size, max_size, statement_cache_size,
    )


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

"""FastAPI 앱. 봇과 웹 공통 백엔드.

인증: X-SAJUCANDLE-KEY 헤더.
DB: DATABASE_URL env로 lifespan에서 Pool 연결.
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Header, HTTPException, Request

from sajucandle import db, repositories
from sajucandle.cache import BaziCache
from sajucandle.cached_engine import CachedSajuEngine
from sajucandle.models import (
    BaziResponse,
    BirthRequest,
    UserProfileRequest,
    UserProfileResponse,
    bazi_chart_to_response,
)

logger = logging.getLogger(__name__)


def _build_default_engine() -> CachedSajuEngine:
    redis_url = os.environ.get("REDIS_URL")
    redis_client = None
    if redis_url:
        try:
            import redis as redis_lib
            redis_client = redis_lib.from_url(redis_url)
            redis_client.ping()
            logger.info("API: Redis 연결 성공.")
        except Exception as e:
            logger.warning("API: Redis 연결 실패 (%s).", e)
            redis_client = None
    else:
        logger.info("API: REDIS_URL 미설정.")
    return CachedSajuEngine(cache=BaziCache(redis_client=redis_client))


def _require_api_key(request: Request, x_sajucandle_key: Optional[str]) -> None:
    expected = os.environ.get("SAJUCANDLE_API_KEY", "").strip()
    if not expected:
        return
    if x_sajucandle_key != expected:
        raise HTTPException(status_code=401, detail="invalid or missing API key")


def _profile_to_response(p: repositories.UserProfile) -> UserProfileResponse:
    return UserProfileResponse(
        telegram_chat_id=p.telegram_chat_id,
        birth_year=p.birth_year,
        birth_month=p.birth_month,
        birth_day=p.birth_day,
        birth_hour=p.birth_hour,
        birth_minute=p.birth_minute,
        asset_class_pref=p.asset_class_pref,  # type: ignore[arg-type]
        created_at=p.created_at,
        updated_at=p.updated_at,
    )


def create_app(engine: CachedSajuEngine | None = None) -> FastAPI:
    engine = engine or _build_default_engine()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        dsn = os.environ.get("DATABASE_URL")
        if dsn:
            try:
                await db.connect(dsn)
            except Exception as e:
                logger.error("DB 연결 실패: %s", e)
        else:
            logger.warning("DATABASE_URL 미설정 — 사용자 엔드포인트 비활성.")
        yield
        await db.close()

    app = FastAPI(title="SajuCandle API", version="0.2.0", lifespan=lifespan)

    @app.get("/health")
    async def health() -> dict[str, str]:
        pool = db.get_pool()
        db_status = "down"
        if pool is not None:
            try:
                async with db.acquire() as conn:
                    await conn.fetchval("SELECT 1")
                db_status = "up"
            except Exception:
                db_status = "down"
        return {"status": "ok", "db": db_status}

    @app.post("/v1/bazi", response_model=BaziResponse)
    async def bazi(
        body: BirthRequest,
        request: Request,
        x_sajucandle_key: Optional[str] = Header(default=None),
    ) -> BaziResponse:
        _require_api_key(request, x_sajucandle_key)
        try:
            chart = engine.calc_bazi(body.year, body.month, body.day, body.hour)
        except Exception as e:
            logger.exception("calc_bazi failed")
            raise HTTPException(400, detail=f"명식 계산 실패: {type(e).__name__}")
        return bazi_chart_to_response(chart)

    @app.put("/v1/users/{chat_id}", response_model=UserProfileResponse)
    async def put_user(
        chat_id: int,
        body: UserProfileRequest,
        request: Request,
        x_sajucandle_key: Optional[str] = Header(default=None),
    ) -> UserProfileResponse:
        _require_api_key(request, x_sajucandle_key)
        if db.get_pool() is None:
            raise HTTPException(503, detail="database not available")
        async with db.acquire() as conn:
            saved = await repositories.upsert_user(
                conn,
                repositories.UserProfile(
                    telegram_chat_id=chat_id,
                    birth_year=body.birth_year,
                    birth_month=body.birth_month,
                    birth_day=body.birth_day,
                    birth_hour=body.birth_hour,
                    birth_minute=body.birth_minute,
                    asset_class_pref=body.asset_class_pref,
                ),
            )
        return _profile_to_response(saved)

    return app


app = create_app()

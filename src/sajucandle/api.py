"""FastAPI 엔드포인트. 봇과 Next.js 웹 공통 백엔드.

인증: X-SAJUCANDLE-KEY 헤더 + SAJUCANDLE_API_KEY 환경변수 비교.
엔진: create_app(engine=...)로 테스트에서 주입. 기본값은 REDIS_URL 자동 감지.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from fastapi import FastAPI, Header, HTTPException, Request

from sajucandle.cache import BaziCache
from sajucandle.cached_engine import CachedSajuEngine
from sajucandle.models import BirthRequest, BaziResponse, bazi_chart_to_response

logger = logging.getLogger(__name__)


def _build_default_engine() -> CachedSajuEngine:
    """REDIS_URL 있으면 붙고, 아니면 no-op 캐시."""
    redis_url = os.environ.get("REDIS_URL")
    redis_client = None
    if redis_url:
        try:
            import redis as redis_lib

            redis_client = redis_lib.from_url(redis_url)
            redis_client.ping()
            logger.info("API: Redis 연결 성공.")
        except Exception as e:
            logger.warning("API: Redis 연결 실패 (%s). 캐시 없이 진행.", e)
            redis_client = None
    else:
        logger.info("API: REDIS_URL 미설정. 캐시 없이 진행.")
    cache = BaziCache(redis_client=redis_client)
    return CachedSajuEngine(cache=cache)


def _require_api_key(request: Request, x_sajucandle_key: Optional[str]) -> None:
    """헤더의 키가 env의 키와 일치하는지 확인. 없거나 틀리면 401.

    SAJUCANDLE_API_KEY 환경변수가 비어 있으면 인증 비활성 (로컬 개발).
    단 운영(Railway)에선 반드시 설정해야 함.
    """
    expected = os.environ.get("SAJUCANDLE_API_KEY", "").strip()
    if not expected:
        # 로컬 dev 편의 — 프로덕션에선 env를 반드시 세팅
        return
    if x_sajucandle_key != expected:
        raise HTTPException(status_code=401, detail="invalid or missing API key")


def create_app(engine: CachedSajuEngine | None = None) -> FastAPI:
    """FastAPI 앱 팩토리. 테스트에서 엔진 주입 가능."""
    app = FastAPI(title="SajuCandle API", version="0.1.0")
    engine = engine or _build_default_engine()

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

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
            logger.exception("calc_bazi failed for %s", body.model_dump())
            raise HTTPException(
                status_code=400,
                detail=f"명식 계산 실패: {type(e).__name__}",
            )
        return bazi_chart_to_response(chart)

    return app


# 모듈 레벨 기본 앱 — uvicorn entry point로 사용 (`uvicorn sajucandle.api:app`)
app = create_app()

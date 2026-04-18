"""FastAPI 앱. 봇과 웹 공통 백엔드.

인증: X-SAJUCANDLE-KEY 헤더.
DB: DATABASE_URL env로 lifespan에서 Pool 연결.
"""
from __future__ import annotations

import logging
import os
import time
from datetime import date as date_cls, datetime
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Header, HTTPException, Request

from sajucandle import db, repositories
from sajucandle.cache import BaziCache
from sajucandle.cached_engine import CachedSajuEngine
from sajucandle.market.base import UnsupportedTicker
from sajucandle.market.router import MarketRouter
from sajucandle.market.yfinance import YFinanceClient
from sajucandle.market_data import BinanceClient, MarketDataUnavailable
from sajucandle.models import (
    BaziResponse,
    BirthRequest,
    SignalResponse,
    UserProfileRequest,
    UserProfileResponse,
    WatchlistAddRequest,
    WatchlistItem,
    WatchlistResponse,
    WatchlistSymbolsResponse,
    bazi_chart_to_response,
)
from sajucandle.score_service import KST, ScoreService
from sajucandle.signal_service import SignalService

logger = logging.getLogger(__name__)


def _configure_sajucandle_logging() -> None:
    """sajucandle.* 로거에 StreamHandler 부착 (멱등).

    Railway는 `uvicorn sajucandle.api:app`을 직접 실행해서 uvicorn이 uvicorn.*
    로거만 설정함. sajucandle.* 로거는 전파할 핸들러가 없어 INFO 로그가 유실됨.
    모듈 임포트 시 1회 세팅해서 Railway stdout으로 나가게 한다.
    """
    lg = logging.getLogger("sajucandle")
    if lg.handlers:  # 이미 세팅됨 (bot.py basicConfig 등)
        return
    h = logging.StreamHandler()
    h.setFormatter(
        logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    )
    lg.addHandler(h)
    lg.setLevel(logging.INFO)


_configure_sajucandle_logging()


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


def create_app(
    engine: CachedSajuEngine | None = None,
    signal_service: SignalService | None = None,
) -> FastAPI:
    engine = engine or _build_default_engine()

    def _build_score_service() -> ScoreService:
        redis_url = os.environ.get("REDIS_URL")
        redis_client = None
        if redis_url:
            try:
                import redis as redis_lib
                redis_client = redis_lib.from_url(redis_url)
                redis_client.ping()
            except Exception:
                redis_client = None
        return ScoreService(engine=engine, redis_client=redis_client)

    score_service = _build_score_service()

    def _build_signal_service() -> SignalService:
        redis_url = os.environ.get("REDIS_URL")
        redis_client = None
        if redis_url:
            try:
                import redis as redis_lib
                redis_client = redis_lib.from_url(redis_url)
                redis_client.ping()
            except Exception:
                redis_client = None
        binance = BinanceClient(redis_client=redis_client, timeout=3.0)
        yfinance_client = YFinanceClient(redis_client=redis_client)
        router = MarketRouter(binance=binance, yfinance=yfinance_client)
        return SignalService(
            score_service=score_service,
            market_router=router,
            redis_client=redis_client,
        )

    signal_service = signal_service or _build_signal_service()

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
        # auth: API 키가 설정됐으면 "enabled", 없으면 "disabled"(= 누구나 접근 가능)
        # 프로덕션에서 "disabled"면 환경변수 누락을 의미 — 즉시 감지하려고 노출.
        auth_status = "enabled" if os.environ.get("SAJUCANDLE_API_KEY", "").strip() else "disabled"
        return {"status": "ok", "db": db_status, "auth": auth_status}

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

    @app.get("/v1/users/{chat_id}", response_model=UserProfileResponse)
    async def get_user_endpoint(
        chat_id: int,
        request: Request,
        x_sajucandle_key: Optional[str] = Header(default=None),
    ) -> UserProfileResponse:
        _require_api_key(request, x_sajucandle_key)
        if db.get_pool() is None:
            raise HTTPException(503, detail="database not available")
        async with db.acquire() as conn:
            user = await repositories.get_user(conn, chat_id)
        if user is None:
            raise HTTPException(404, detail="user not found")
        return _profile_to_response(user)

    @app.delete("/v1/users/{chat_id}", status_code=204)
    async def delete_user_endpoint(
        chat_id: int,
        request: Request,
        x_sajucandle_key: Optional[str] = Header(default=None),
    ) -> None:
        _require_api_key(request, x_sajucandle_key)
        if db.get_pool() is None:
            raise HTTPException(503, detail="database not available")
        async with db.acquire() as conn:
            await repositories.delete_user(conn, chat_id)
        return None

    @app.get("/v1/admin/users")
    async def list_users_endpoint(
        request: Request,
        x_sajucandle_key: Optional[str] = Header(default=None),
    ):
        """등록된 사용자 chat_id 리스트. 데일리 브로드캐스트용.

        X-SAJUCANDLE-KEY 필요. 반환 순서 보장 X. 페이지네이션 X.
        """
        _require_api_key(request, x_sajucandle_key)
        if db.get_pool() is None:
            raise HTTPException(503, detail="database not available")
        async with db.acquire() as conn:
            chat_ids = await repositories.list_chat_ids(conn)
        logger.info("admin list_users count=%s", len(chat_ids))
        return {"chat_ids": chat_ids}

    _WATCHLIST_MAX = 5

    def _normalize_ticker(t: str) -> str:
        return t.upper().lstrip("$")

    def _ticker_is_supported(t: str) -> bool:
        """MarketRouter.all_symbols()의 ticker set 검증."""
        supported = {s["ticker"] for s in MarketRouter.all_symbols()}
        return t in supported

    @app.get("/v1/users/{chat_id}/watchlist", response_model=WatchlistResponse)
    async def list_watchlist_endpoint(
        chat_id: int,
        request: Request,
        x_sajucandle_key: Optional[str] = Header(default=None),
    ) -> WatchlistResponse:
        _require_api_key(request, x_sajucandle_key)
        if db.get_pool() is None:
            raise HTTPException(503, detail="database not available")
        async with db.acquire() as conn:
            entries = await repositories.list_watchlist(conn, chat_id)
        return WatchlistResponse(
            items=[WatchlistItem(ticker=e.ticker, added_at=e.added_at)
                   for e in entries]
        )

    @app.post("/v1/users/{chat_id}/watchlist", status_code=204)
    async def add_watchlist_endpoint(
        chat_id: int,
        body: WatchlistAddRequest,
        request: Request,
        x_sajucandle_key: Optional[str] = Header(default=None),
    ) -> None:
        _require_api_key(request, x_sajucandle_key)
        if db.get_pool() is None:
            raise HTTPException(503, detail="database not available")

        ticker = _normalize_ticker(body.ticker)
        if not _ticker_is_supported(ticker):
            raise HTTPException(400, detail=f"unsupported ticker: {ticker}")

        import asyncpg
        async with db.acquire() as conn:
            async with conn.transaction():
                # 사용자 존재 확인
                user = await repositories.get_user(conn, chat_id)
                if user is None:
                    raise HTTPException(404, detail="user not found")
                # 5개 제한 (트랜잭션 내 검증)
                n = await repositories.count_watchlist(conn, chat_id)
                if n >= _WATCHLIST_MAX:
                    raise HTTPException(
                        409,
                        detail=f"watchlist full (max {_WATCHLIST_MAX})",
                    )
                try:
                    await repositories.add_to_watchlist(conn, chat_id, ticker)
                except asyncpg.UniqueViolationError:
                    raise HTTPException(409, detail="already in watchlist")
        logger.info(
            "watchlist added chat_id=%s ticker=%s count=%s/%s",
            chat_id, ticker, n + 1, _WATCHLIST_MAX,
        )
        return None

    @app.delete("/v1/users/{chat_id}/watchlist/{ticker}", status_code=204)
    async def remove_watchlist_endpoint(
        chat_id: int,
        ticker: str,
        request: Request,
        x_sajucandle_key: Optional[str] = Header(default=None),
    ) -> None:
        _require_api_key(request, x_sajucandle_key)
        if db.get_pool() is None:
            raise HTTPException(503, detail="database not available")
        t = _normalize_ticker(ticker)
        async with db.acquire() as conn:
            deleted = await repositories.remove_from_watchlist(conn, chat_id, t)
        if not deleted:
            raise HTTPException(404, detail="not in watchlist")
        logger.info("watchlist removed chat_id=%s ticker=%s", chat_id, t)
        return None

    @app.get(
        "/v1/admin/watchlist-symbols",
        response_model=WatchlistSymbolsResponse,
    )
    async def admin_watchlist_symbols_endpoint(
        request: Request,
        x_sajucandle_key: Optional[str] = Header(default=None),
    ) -> WatchlistSymbolsResponse:
        _require_api_key(request, x_sajucandle_key)
        if db.get_pool() is None:
            raise HTTPException(503, detail="database not available")
        async with db.acquire() as conn:
            symbols = await repositories.list_all_watchlist_tickers(conn)
        return WatchlistSymbolsResponse(symbols=sorted(symbols))

    @app.get("/v1/users/{chat_id}/score")
    async def score_endpoint(
        chat_id: int,
        request: Request,
        date: Optional[str] = None,
        asset: Optional[str] = None,
        x_sajucandle_key: Optional[str] = Header(default=None),
    ):
        _require_api_key(request, x_sajucandle_key)
        if db.get_pool() is None:
            raise HTTPException(503, detail="database not available")

        # date 파싱
        if date is None:
            target = datetime.now(tz=KST).date()
        else:
            try:
                target = date_cls.fromisoformat(date)
            except ValueError:
                raise HTTPException(400, detail="date must be YYYY-MM-DD")

        # asset 검증
        allowed_assets = {"swing", "scalp", "long", "default"}
        if asset is not None and asset not in allowed_assets:
            raise HTTPException(400, detail=f"asset must be one of {sorted(allowed_assets)}")

        async with db.acquire() as conn:
            profile = await repositories.get_user(conn, chat_id)
        if profile is None:
            raise HTTPException(404, detail="user not found")

        final_asset = asset or profile.asset_class_pref
        t0 = time.perf_counter()
        try:
            result = score_service.compute(profile, target, final_asset)
        except Exception as e:
            logger.exception("score compute failed")
            raise HTTPException(400, detail=f"점수 계산 실패: {type(e).__name__}")
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        logger.info(
            "score ok chat_id=%s date=%s asset=%s composite=%s grade=%s elapsed_ms=%s",
            chat_id, target.isoformat(), final_asset,
            result.composite_score, result.signal_grade, elapsed_ms,
        )
        return result

    @app.get("/v1/signal/symbols")
    async def signal_symbols_endpoint(
        request: Request,
        x_sajucandle_key: Optional[str] = Header(default=None),
    ):
        """지원 심볼 카탈로그. 봇 /signal list용."""
        _require_api_key(request, x_sajucandle_key)
        return {"symbols": MarketRouter.all_symbols()}

    @app.get("/v1/users/{chat_id}/signal", response_model=SignalResponse)
    async def signal_endpoint(
        chat_id: int,
        request: Request,
        ticker: str = "BTCUSDT",
        date: Optional[str] = None,
        x_sajucandle_key: Optional[str] = Header(default=None),
    ):
        _require_api_key(request, x_sajucandle_key)
        if db.get_pool() is None:
            raise HTTPException(503, detail="database not available")

        # date 파싱
        if date is None:
            target = datetime.now(tz=KST).date()
        else:
            try:
                target = date_cls.fromisoformat(date)
            except ValueError:
                raise HTTPException(400, detail="date must be YYYY-MM-DD")

        async with db.acquire() as conn:
            profile = await repositories.get_user(conn, chat_id)
        if profile is None:
            raise HTTPException(404, detail="user not found")

        t0 = time.perf_counter()
        try:
            result = signal_service.compute(profile, target, ticker)
        except UnsupportedTicker as e:
            raise HTTPException(400, detail=f"unsupported ticker: {e.symbol}")
        except MarketDataUnavailable as e:
            logger.warning("signal market data unavailable: %s", e)
            raise HTTPException(502, detail="chart data unavailable")
        except Exception as e:
            logger.exception("signal compute failed")
            raise HTTPException(400, detail=f"신호 계산 실패: {type(e).__name__}")
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        logger.info(
            "signal ok chat_id=%s ticker=%s date=%s composite=%s grade=%s "
            "saju=%s chart=%s elapsed_ms=%s",
            chat_id, ticker, target.isoformat(),
            result.composite_score, result.signal_grade,
            result.saju.composite, result.chart.score, elapsed_ms,
        )
        # Week 8: signal_log 기록 (best effort)
        try:
            if db.get_pool() is not None and result.analysis is not None:
                async with db.acquire() as conn:
                    await repositories.insert_signal_log(
                        conn,
                        source="ondemand",
                        telegram_chat_id=chat_id,
                        ticker=ticker,
                        target_date=target,
                        entry_price=result.price.current,
                        saju_score=result.saju.composite,
                        analysis_score=result.analysis.composite_score,
                        structure_state=result.analysis.structure.state,
                        alignment_bias=result.analysis.alignment.bias,
                        rsi_1h=result.analysis.rsi_1h,
                        volume_ratio_1d=result.analysis.volume_ratio_1d,
                        composite_score=result.composite_score,
                        signal_grade=result.signal_grade,
                    )
        except Exception as e:
            logger.warning("signal_log insert failed chat_id=%s: %s", chat_id, e)
        return result

    return app


app = create_app()

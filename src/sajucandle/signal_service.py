"""사주 + 차트 결합 신호 서비스.

책임:
1. ScoreService.compute() → 사주 composite
2. BinanceClient.fetch_klines() → OHLCV
3. tech_analysis.score_chart() → chart_score
4. 가중합 (0.4 * saju + 0.6 * chart) → final_score + grade
5. SignalResponse 조립 + Redis 캐시 (signal:*, TTL=300)

사주는 자체 캐시(score:*, KST 자정 TTL)가 있어서 재활용됨.
차트는 가격 변동이 있어서 짧은 TTL(5분) 씌움.
"""
from __future__ import annotations

import json
import logging
from datetime import date
from typing import Optional

from sajucandle.market_data import BinanceClient, Kline
from sajucandle.models import (
    ChartSummary,
    PricePoint,
    SajuSummary,
    SignalResponse,
)
from sajucandle.repositories import UserProfile
from sajucandle.score_service import ScoreService
from sajucandle.tech_analysis import score_chart

logger = logging.getLogger(__name__)

_SIGNAL_TTL = 300


def _grade_signal(score: int) -> str:
    if score >= 75:
        return "강진입"
    if score >= 60:
        return "진입"
    if score >= 40:
        return "관망"
    return "회피"


class SignalService:
    def __init__(
        self,
        score_service: ScoreService,
        market_client: BinanceClient,
        redis_client=None,
    ):
        self._score = score_service
        self._market = market_client
        self._redis = redis_client

    def compute(
        self,
        profile: UserProfile,
        target_date: date,
        ticker: str,
    ) -> SignalResponse:
        cache_key = (
            f"signal:{profile.telegram_chat_id}:{target_date.isoformat()}:{ticker}"
        )

        # 1. 캐시 히트?
        cached = self._redis_get(cache_key)
        if cached is not None:
            return cached

        # 2. 사주 (기존 score_service가 자체 캐시 사용)
        saju_resp = self._score.compute(
            profile, target_date, profile.asset_class_pref
        )

        # 3. 차트 데이터 (실패 시 MarketDataUnavailable 전파)
        klines: list[Kline] = self._market.fetch_klines(ticker, interval="1d", limit=100)
        closes = [k.close for k in klines]
        volumes = [k.volume for k in klines]

        chart_b = score_chart(closes, volumes)

        # 4. 가격 포인트
        current = klines[-1].close
        prev = klines[-2].close if len(klines) >= 2 else current
        change_pct = ((current / prev) - 1.0) * 100 if prev else 0.0

        # 5. 결합
        final = round(0.4 * saju_resp.composite_score + 0.6 * chart_b.score)
        final = max(0, min(100, final))
        grade = _grade_signal(final)

        resp = SignalResponse(
            chat_id=profile.telegram_chat_id,
            ticker=ticker,
            date=target_date.isoformat(),
            price=PricePoint(current=current, change_pct_24h=change_pct),
            saju=SajuSummary(
                composite=saju_resp.composite_score,
                grade=saju_resp.signal_grade,
            ),
            chart=ChartSummary(
                score=chart_b.score,
                rsi=chart_b.rsi_value,
                ma20=chart_b.ma20,
                ma50=chart_b.ma50,
                ma_trend=chart_b.ma_trend,  # type: ignore[arg-type]
                volume_ratio=chart_b.volume_ratio_value,
                reason=chart_b.reason,
            ),
            composite_score=final,
            signal_grade=grade,
            best_hours=saju_resp.best_hours,
        )

        # 6. 캐시 저장
        self._redis_set(cache_key, resp)
        return resp

    # ─────────────────────────────────────────────
    # cache helpers
    # ─────────────────────────────────────────────

    def _redis_get(self, key: str) -> Optional[SignalResponse]:
        if self._redis is None:
            return None
        try:
            raw = self._redis.get(key)
        except Exception as e:
            logger.warning("signal cache GET 실패: %s", e)
            return None
        if raw is None:
            return None
        try:
            if isinstance(raw, (bytes, bytearray)):
                raw = raw.decode("utf-8")
            return SignalResponse(**json.loads(raw))
        except Exception as e:
            logger.warning("signal cache deserialize 실패: %s", e)
            return None

    def _redis_set(self, key: str, resp: SignalResponse) -> None:
        if self._redis is None:
            return
        try:
            self._redis.setex(key, _SIGNAL_TTL, resp.model_dump_json())
        except Exception as e:
            logger.warning("signal cache SET 실패: %s", e)

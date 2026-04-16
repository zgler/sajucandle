"""일일 점수 서비스.

책임:
1. UserProfile → BaziChart 계산 (cached_engine 위임)
2. ScoreCard 계산
3. Pydantic 응답으로 변환
4. Redis에 결과 캐시 (KST 자정까지 TTL)
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sajucandle.cached_engine import CachedSajuEngine
from sajucandle.models import AxisScore, HourRecommendation, SajuScoreResponse
from sajucandle.repositories import UserProfile

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))


def _seconds_until_kst_midnight(now_utc: Optional[datetime] = None) -> int:
    """지금부터 다음 KST 자정까지 남은 초. 최소 60초."""
    now = now_utc or datetime.now(tz=timezone.utc)
    kst_now = now.astimezone(KST)
    tomorrow = (kst_now + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    delta = (tomorrow - kst_now).total_seconds()
    return max(int(delta), 60)


class ScoreService:
    def __init__(self, engine: CachedSajuEngine, redis_client=None):
        self._engine = engine
        self._redis = redis_client

    def compute(
        self,
        profile: UserProfile,
        target_date: date,
        asset_class: str,
    ) -> SajuScoreResponse:
        cache_key = f"score:{profile.telegram_chat_id}:{target_date.isoformat()}:{asset_class}"

        # 1) Redis 히트?
        if self._redis is not None:
            try:
                raw = self._redis.get(cache_key)
            except Exception as e:
                logger.warning("score cache GET 실패: %s", e)
                raw = None
            if raw:
                try:
                    data = json.loads(raw)
                    return SajuScoreResponse(**data)
                except Exception:
                    pass  # 깨진 캐시는 무시, 아래에서 재계산

        # 2) 계산
        bazi = self._engine.calc_bazi(
            profile.birth_year,
            profile.birth_month,
            profile.birth_day,
            profile.birth_hour,
        )
        card = self._engine.engine.calc_daily_score(
            bazi, target_date, asset_class=asset_class
        )

        resp = SajuScoreResponse(
            chat_id=profile.telegram_chat_id,
            date=target_date.isoformat(),
            asset_class=asset_class,  # type: ignore[arg-type]
            iljin=card.iljin,
            composite_score=card.composite_score,
            signal_grade=card.signal_grade,
            axes={
                "wealth":     AxisScore(score=card.wealth_score,     reason=card.wealth_reason),
                "decision":   AxisScore(score=card.decision_score,   reason=card.decision_reason),
                "volatility": AxisScore(score=card.volatility_score, reason=card.volatility_reason),
                "flow":       AxisScore(score=card.flow_score,       reason=card.flow_reason),
            },
            best_hours=[
                HourRecommendation(shichen=zhi, time_range=tr, multiplier=mult)
                for (zhi, tr, mult) in card.best_hours
            ],
        )

        # 3) 캐시 저장 (실패해도 무시)
        if self._redis is not None:
            try:
                self._redis.set(
                    cache_key,
                    resp.model_dump_json(),
                    ex=_seconds_until_kst_midnight(),
                )
            except Exception as e:
                logger.warning("score cache SET 실패: %s", e)

        return resp

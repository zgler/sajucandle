"""Redis 기반 일반 캐시 래퍼. Redis 없으면 pass-through."""
from __future__ import annotations

import logging
import pickle
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


class BaziCache:
    """get_or_compute 패턴으로 호출부 단순화.

    redis_client가 None이면 캐시 비활성 (로컬 테스트/Redis 미설정 첫 배포 등).
    Redis가 중간에 죽어도 예외를 먹고 compute_fn으로 graceful degradation.

    직렬화는 pickle - 내부 전용 캐시. 외부 API 응답에 그대로 쓰면 안 됨.
    """

    def __init__(
        self,
        redis_client: Optional[Any] = None,
        ttl_seconds: int = 30 * 24 * 3600,  # 30일
    ) -> None:
        self._redis = redis_client
        self._ttl = ttl_seconds

    def get_or_compute(self, key: str, compute_fn: Callable[[], Any]) -> Any:
        """캐시 히트면 반환, 미스면 compute_fn 실행 후 저장."""
        if self._redis is None:
            return compute_fn()

        try:
            cached = self._redis.get(key)
        except Exception as e:  # Redis 다운/네트워크 실패
            logger.warning("Redis GET 실패 (%s). compute_fn으로 fallback.", e)
            return compute_fn()

        if cached is not None:
            try:
                return pickle.loads(cached)
            except Exception as e:  # 포맷 깨짐 - 무시하고 재계산
                logger.warning("캐시 역직렬화 실패 (%s). 재계산.", e)

        result = compute_fn()

        try:
            self._redis.set(key, pickle.dumps(result), ex=self._ttl)
        except Exception as e:
            logger.warning("Redis SET 실패 (%s). 캐시 저장 스킵.", e)

        return result

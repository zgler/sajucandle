"""BaziCache 단위 테스트. fakeredis로 Redis 모킹."""
from __future__ import annotations

import fakeredis

from sajucandle.cache import BaziCache


def test_cache_miss_then_hit():
    """첫 호출은 compute_fn 실행, 두 번째는 캐시에서."""
    redis = fakeredis.FakeStrictRedis()
    cache = BaziCache(redis_client=redis, ttl_seconds=60)

    call_count = {"n": 0}

    def compute():
        call_count["n"] += 1
        return {"pillar": "庚午"}

    first = cache.get_or_compute("bazi:1990031514", compute)
    assert first == {"pillar": "庚午"}
    assert call_count["n"] == 1

    second = cache.get_or_compute("bazi:1990031514", compute)
    assert second == {"pillar": "庚午"}
    assert call_count["n"] == 1  # 캐시 히트라 재계산 없음


def test_cache_no_redis_is_noop():
    """redis_client=None이면 매번 compute_fn 실행 (fallback)."""
    cache = BaziCache(redis_client=None, ttl_seconds=60)

    call_count = {"n": 0}

    def compute():
        call_count["n"] += 1
        return "result"

    assert cache.get_or_compute("key", compute) == "result"
    assert cache.get_or_compute("key", compute) == "result"
    assert call_count["n"] == 2


def test_cache_ttl_expiry():
    """TTL 지나면 재계산 (여기선 수동 delete로 만료 시뮬레이션)."""
    redis = fakeredis.FakeStrictRedis()
    cache = BaziCache(redis_client=redis, ttl_seconds=60)

    cache.get_or_compute("key", lambda: "v1")
    redis.delete("key")  # expire 시뮬레이션

    call_count = {"n": 0}

    def compute_v2():
        call_count["n"] += 1
        return "v2"

    assert cache.get_or_compute("key", compute_v2) == "v2"
    assert call_count["n"] == 1


def test_cache_redis_failure_falls_back_to_compute():
    """Redis GET이 예외 던지면 compute_fn으로 fallback."""

    class BrokenRedis:
        def get(self, key):
            raise ConnectionError("Redis down")

        def set(self, *args, **kwargs):
            raise ConnectionError("Redis down")

    cache = BaziCache(redis_client=BrokenRedis(), ttl_seconds=60)

    call_count = {"n": 0}

    def compute():
        call_count["n"] += 1
        return "fallback_ok"

    assert cache.get_or_compute("key", compute) == "fallback_ok"
    assert call_count["n"] == 1

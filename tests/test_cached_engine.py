"""CachedSajuEngine 테스트. SajuEngine 래퍼 + 캐시 키 포맷 검증."""
from __future__ import annotations

import fakeredis

from sajucandle.cache import BaziCache
from sajucandle.cached_engine import CachedSajuEngine
from sajucandle.saju_engine import BaziChart


def test_calc_bazi_cached_returns_same_object():
    redis = fakeredis.FakeStrictRedis()
    cache = BaziCache(redis_client=redis, ttl_seconds=60)
    engine = CachedSajuEngine(cache=cache)

    c1 = engine.calc_bazi(1990, 3, 15, 14)
    c2 = engine.calc_bazi(1990, 3, 15, 14)

    assert isinstance(c1, BaziChart)
    assert c1.year_gan == c2.year_gan
    assert c1.month_gan == c2.month_gan
    assert c1.day_gan == c2.day_gan
    assert c1.hour_gan == c2.hour_gan


def test_calc_bazi_key_format():
    """키 포맷이 시진 단위(YYYYMMDDHH)여야 같은 시 내 분 차이는 무시 가능."""
    redis = fakeredis.FakeStrictRedis()
    cache = BaziCache(redis_client=redis, ttl_seconds=60)
    engine = CachedSajuEngine(cache=cache)

    engine.calc_bazi(1990, 3, 15, 14)
    keys = [k.decode() for k in redis.keys("bazi:*")]
    assert "bazi:1990031514" in keys


def test_calc_bazi_without_redis_still_works():
    """Redis None이어도 엔진 동작."""
    cache = BaziCache(redis_client=None)
    engine = CachedSajuEngine(cache=cache)

    chart = engine.calc_bazi(1990, 3, 15, 14)
    assert chart.day_gan == "己"


def test_different_inputs_different_keys():
    redis = fakeredis.FakeStrictRedis()
    cache = BaziCache(redis_client=redis, ttl_seconds=60)
    engine = CachedSajuEngine(cache=cache)

    engine.calc_bazi(1990, 3, 15, 14)
    engine.calc_bazi(1990, 3, 15, 15)  # 다른 시
    engine.calc_bazi(1991, 3, 15, 14)  # 다른 연

    keys = [k.decode() for k in redis.keys("bazi:*")]
    assert len(keys) == 3

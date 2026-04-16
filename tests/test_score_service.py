"""score_service: ScoreCard → SajuScoreResponse 변환 + 캐시."""
from __future__ import annotations

from datetime import date

import fakeredis

from sajucandle.cache import BaziCache
from sajucandle.cached_engine import CachedSajuEngine
from sajucandle.repositories import UserProfile
from sajucandle.score_service import ScoreService


def _profile() -> UserProfile:
    return UserProfile(
        telegram_chat_id=1,
        birth_year=1990, birth_month=3, birth_day=15,
        birth_hour=14, birth_minute=0,
        asset_class_pref="swing",
    )


def test_compute_returns_saju_score_response():
    engine = CachedSajuEngine(cache=BaziCache(redis_client=None))
    svc = ScoreService(engine=engine, redis_client=None)
    resp = svc.compute(_profile(), target_date=date(2026, 4, 16), asset_class="swing")

    assert resp.chat_id == 1
    assert resp.date == "2026-04-16"
    assert resp.asset_class == "swing"
    assert 0 <= resp.composite_score <= 100
    assert set(resp.axes.keys()) == {"wealth", "decision", "volatility", "flow"}
    for axis in resp.axes.values():
        assert 0 <= axis.score <= 100


def test_compute_uses_redis_cache_on_second_call():
    r = fakeredis.FakeRedis()
    engine = CachedSajuEngine(cache=BaziCache(redis_client=r))
    svc = ScoreService(engine=engine, redis_client=r)

    # 첫 호출 — MISS → SET
    r1 = svc.compute(_profile(), target_date=date(2026, 4, 16), asset_class="swing")
    keys = [k.decode() for k in r.keys("score:*")]
    assert len(keys) == 1
    assert keys[0] == "score:1:2026-04-16:swing"

    # 두 번째 호출 — HIT → 값 동일
    r2 = svc.compute(_profile(), target_date=date(2026, 4, 16), asset_class="swing")
    assert r1.model_dump() == r2.model_dump()


def test_compute_cache_key_varies_by_asset():
    r = fakeredis.FakeRedis()
    engine = CachedSajuEngine(cache=BaziCache(redis_client=r))
    svc = ScoreService(engine=engine, redis_client=r)

    svc.compute(_profile(), target_date=date(2026, 4, 16), asset_class="swing")
    svc.compute(_profile(), target_date=date(2026, 4, 16), asset_class="scalp")

    keys = sorted(k.decode() for k in r.keys("score:*"))
    assert keys == [
        "score:1:2026-04-16:scalp",
        "score:1:2026-04-16:swing",
    ]


def test_compute_with_no_redis_still_works():
    engine = CachedSajuEngine(cache=BaziCache(redis_client=None))
    svc = ScoreService(engine=engine, redis_client=None)
    resp = svc.compute(_profile(), target_date=date(2026, 4, 16), asset_class="swing")
    assert resp.composite_score >= 0


from datetime import datetime, timezone  # noqa: E402

from sajucandle.score_service import _seconds_until_kst_midnight  # noqa: E402


def test_seconds_until_kst_midnight_at_kst_noon():
    # 2026-04-16 03:00 UTC = 12:00 KST → 자정까지 12시간
    now = datetime(2026, 4, 16, 3, 0, 0, tzinfo=timezone.utc)
    assert _seconds_until_kst_midnight(now) == 12 * 3600


def test_seconds_until_kst_midnight_is_positive_and_min_60():
    # 2026-04-16 14:59:30 UTC = 23:59:30 KST → 30초지만 최소 60초로 clamp
    now = datetime(2026, 4, 16, 14, 59, 30, tzinfo=timezone.utc)
    assert _seconds_until_kst_midnight(now) >= 60

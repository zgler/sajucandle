"""FastAPI 엔드포인트 테스트. TestClient + fakeredis."""
from __future__ import annotations

import fakeredis
import pytest
from fastapi.testclient import TestClient

from sajucandle.api import create_app
from sajucandle.cache import BaziCache
from sajucandle.cached_engine import CachedSajuEngine


@pytest.fixture
def api_key() -> str:
    return "test-secret-key"


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, api_key: str) -> TestClient:
    monkeypatch.setenv("SAJUCANDLE_API_KEY", api_key)
    redis = fakeredis.FakeStrictRedis()
    cache = BaziCache(redis_client=redis, ttl_seconds=60)
    engine = CachedSajuEngine(cache=cache)
    app = create_app(engine=engine)
    return TestClient(app)


def test_health_ok(client: TestClient):
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert data["db"] in ("up", "down")
    # 이 테스트는 SAJUCANDLE_API_KEY를 세팅하므로 enabled여야 함
    assert data["auth"] == "enabled"


def test_health_reports_auth_disabled_when_no_key(monkeypatch: pytest.MonkeyPatch):
    """프로덕션에서 API 키 누락 시 즉시 감지 가능해야 함."""
    monkeypatch.delenv("SAJUCANDLE_API_KEY", raising=False)
    from sajucandle.api import create_app
    from sajucandle.cache import BaziCache
    from sajucandle.cached_engine import CachedSajuEngine
    app = create_app(engine=CachedSajuEngine(cache=BaziCache(redis_client=None)))
    c = TestClient(app)
    r = c.get("/health")
    assert r.status_code == 200
    assert r.json()["auth"] == "disabled"


def test_bazi_requires_api_key(client: TestClient):
    r = client.post(
        "/v1/bazi",
        json={"year": 1990, "month": 3, "day": 15, "hour": 14},
    )
    assert r.status_code == 401


def test_bazi_wrong_api_key(client: TestClient):
    r = client.post(
        "/v1/bazi",
        json={"year": 1990, "month": 3, "day": 15, "hour": 14},
        headers={"X-SAJUCANDLE-KEY": "wrong"},
    )
    assert r.status_code == 401


def test_bazi_success(client: TestClient, api_key: str):
    r = client.post(
        "/v1/bazi",
        json={"year": 1990, "month": 3, "day": 15, "hour": 14},
        headers={"X-SAJUCANDLE-KEY": api_key},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["day_gan"] == "己"
    assert data["year"]["gan"] == "庚"
    assert data["year"]["zhi"] == "午"
    assert data["birth_solar"] == "1990-03-15"


def test_bazi_validation_error(client: TestClient, api_key: str):
    r = client.post(
        "/v1/bazi",
        json={"year": 1990, "month": 13, "day": 15, "hour": 14},
        headers={"X-SAJUCANDLE-KEY": api_key},
    )
    assert r.status_code == 422  # Pydantic validation


def test_bazi_cache_hit_on_second_call(client: TestClient, api_key: str):
    payload = {"year": 1990, "month": 3, "day": 15, "hour": 14}
    headers = {"X-SAJUCANDLE-KEY": api_key}

    r1 = client.post("/v1/bazi", json=payload, headers=headers)
    r2 = client.post("/v1/bazi", json=payload, headers=headers)

    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json() == r2.json()


# ─────────────────────────────────────────────
# /v1/users/{chat_id}/signal — DB 불필요 케이스만
# (DB 필요한 케이스는 test_api_signal.py)
# ─────────────────────────────────────────────

def test_signal_requires_api_key(client: TestClient):
    r = client.get("/v1/users/123/signal")
    assert r.status_code == 401


def test_signal_db_unavailable_returns_503(client: TestClient, api_key: str):
    # DATABASE_URL 없으므로 db.get_pool() is None
    r = client.get(
        "/v1/users/123/signal",
        headers={"X-SAJUCANDLE-KEY": api_key},
    )
    assert r.status_code == 503

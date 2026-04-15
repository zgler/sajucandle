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
    assert r.json() == {"status": "ok"}


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

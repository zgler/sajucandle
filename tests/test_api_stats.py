"""api: /v1/admin/signal-stats 엔드포인트."""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from sajucandle.api import create_app


@pytest.fixture
def api_key(monkeypatch):
    monkeypatch.setenv("SAJUCANDLE_API_KEY", "test-key")
    return "test-key"


@pytest.fixture
def client(api_key, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", os.environ.get("TEST_DATABASE_URL", ""))
    app = create_app()
    with TestClient(app) as c:
        yield c


HEADERS = {"X-SAJUCANDLE-KEY": "test-key"}

pytestmark = pytest.mark.skipif(
    os.environ.get("TEST_DATABASE_URL") is None,
    reason="TEST_DATABASE_URL not set",
)


def test_stats_requires_api_key(client):
    r = client.get("/v1/admin/signal-stats")
    assert r.status_code == 401


def test_stats_empty_returns_zero(client):
    r = client.get("/v1/admin/signal-stats", headers=HEADERS)
    assert r.status_code == 200
    body = r.json()
    assert "total" in body
    assert "by_grade" in body
    assert "by_direction" in body
    assert "tracking" in body
    assert "mfe_mae" in body


def test_stats_rejects_bad_since(client):
    r = client.get(
        "/v1/admin/signal-stats",
        params={"since": "not-a-date"},
        headers=HEADERS,
    )
    assert r.status_code == 400


def test_stats_endpoint_run_id_param(client):
    """?run_id=... 전달 시 aggregate_signal_stats에 반영."""
    r = client.get(
        "/v1/admin/signal-stats",
        params={"run_id": "phase1-test-endpoint"},
        headers=HEADERS,
    )
    assert r.status_code == 200
    body = r.json()
    # 빈 결과라도 필터 응답에 run_id 반영
    assert body["filters"]["run_id"] == "phase1-test-endpoint"


def test_stats_endpoint_run_id_null_default(client):
    """run_id 미지정 기본 None → 응답 filters.run_id null."""
    r = client.get("/v1/admin/signal-stats", headers=HEADERS)
    assert r.status_code == 200
    body = r.json()
    assert body["filters"]["run_id"] is None

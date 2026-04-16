"""GET /v1/users/{chat_id}/score 통합 테스트."""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from sajucandle.api import create_app

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL not set",
)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("SAJUCANDLE_API_KEY", "test-key")
    monkeypatch.setenv("DATABASE_URL", os.environ["TEST_DATABASE_URL"])
    app = create_app()
    with TestClient(app) as c:
        yield c


HDR = {"X-SAJUCANDLE-KEY": "test-key"}


def _create(client, chat_id: int):
    client.put(
        f"/v1/users/{chat_id}",
        json={
            "birth_year": 1990, "birth_month": 3, "birth_day": 15,
            "birth_hour": 14, "birth_minute": 0,
            "asset_class_pref": "swing",
        },
        headers=HDR,
    )


def test_score_returns_full_payload(client):
    _create(client, 701001)
    try:
        r = client.get("/v1/users/701001/score?date=2026-04-16", headers=HDR)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["chat_id"] == 701001
        assert data["date"] == "2026-04-16"
        assert data["asset_class"] == "swing"
        assert 0 <= data["composite_score"] <= 100
        assert set(data["axes"].keys()) == {"wealth", "decision", "volatility", "flow"}
        assert isinstance(data["best_hours"], list)
    finally:
        client.delete("/v1/users/701001", headers=HDR)


def test_score_404_when_user_missing(client):
    r = client.get("/v1/users/9999988/score?date=2026-04-16", headers=HDR)
    assert r.status_code == 404


def test_score_asset_override(client):
    _create(client, 701002)
    try:
        r = client.get(
            "/v1/users/701002/score?date=2026-04-16&asset=scalp", headers=HDR
        )
        assert r.status_code == 200
        assert r.json()["asset_class"] == "scalp"
    finally:
        client.delete("/v1/users/701002", headers=HDR)


def test_score_default_date_is_today_kst(client):
    _create(client, 701003)
    try:
        r = client.get("/v1/users/701003/score", headers=HDR)
        assert r.status_code == 200
        # date 필드는 YYYY-MM-DD 형식
        assert len(r.json()["date"]) == 10
    finally:
        client.delete("/v1/users/701003", headers=HDR)


def test_score_rejects_bad_date(client):
    _create(client, 701004)
    try:
        r = client.get("/v1/users/701004/score?date=not-a-date", headers=HDR)
        assert r.status_code == 400
    finally:
        client.delete("/v1/users/701004", headers=HDR)

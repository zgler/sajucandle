"""/v1/users/* 엔드포인트 통합 테스트. 실제 DB 필요."""
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


def test_put_user_creates(client):
    body = {
        "birth_year": 1990, "birth_month": 3, "birth_day": 15,
        "birth_hour": 14, "birth_minute": 0,
        "asset_class_pref": "swing",
    }
    r = client.put("/v1/users/700001", json=body, headers=HDR)
    assert r.status_code == 200
    data = r.json()
    assert data["telegram_chat_id"] == 700001
    assert data["birth_year"] == 1990
    assert data["asset_class_pref"] == "swing"

    # cleanup
    client.delete("/v1/users/700001", headers=HDR)


def test_put_user_updates(client):
    body = {
        "birth_year": 1990, "birth_month": 3, "birth_day": 15,
        "birth_hour": 14, "birth_minute": 0,
        "asset_class_pref": "swing",
    }
    client.put("/v1/users/700002", json=body, headers=HDR)
    body["asset_class_pref"] = "scalp"
    body["birth_year"] = 1991
    r = client.put("/v1/users/700002", json=body, headers=HDR)
    assert r.status_code == 200
    assert r.json()["birth_year"] == 1991
    assert r.json()["asset_class_pref"] == "scalp"

    client.delete("/v1/users/700002", headers=HDR)


def test_put_user_requires_api_key(client):
    body = {
        "birth_year": 1990, "birth_month": 3, "birth_day": 15,
        "birth_hour": 14, "birth_minute": 0,
    }
    r = client.put("/v1/users/700003", json=body)
    assert r.status_code == 401


def test_put_user_rejects_invalid_payload(client):
    r = client.put("/v1/users/700004",
                   json={"birth_year": 1800, "birth_month": 1, "birth_day": 1,
                         "birth_hour": 0},
                   headers=HDR)
    assert r.status_code == 422

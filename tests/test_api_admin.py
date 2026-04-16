"""/v1/admin/users 엔드포인트 통합 테스트. 실제 DB 필요."""
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


def test_admin_users_empty_or_list(client):
    """빈 DB면 [], 등록된 사용자 있으면 그 리스트. 순서 무관."""
    r = client.get("/v1/admin/users", headers=HDR)
    assert r.status_code == 200
    data = r.json()
    assert "chat_ids" in data
    assert isinstance(data["chat_ids"], list)
    for cid in data["chat_ids"]:
        assert isinstance(cid, int)


def test_admin_users_includes_registered(client):
    body = {
        "birth_year": 1990, "birth_month": 3, "birth_day": 15,
        "birth_hour": 14, "birth_minute": 0,
        "asset_class_pref": "swing",
    }
    client.put("/v1/users/720001", json=body, headers=HDR)
    client.put("/v1/users/720002", json=body, headers=HDR)

    try:
        r = client.get("/v1/admin/users", headers=HDR)
        assert r.status_code == 200
        ids = r.json()["chat_ids"]
        assert 720001 in ids
        assert 720002 in ids
    finally:
        client.delete("/v1/users/720001", headers=HDR)
        client.delete("/v1/users/720002", headers=HDR)

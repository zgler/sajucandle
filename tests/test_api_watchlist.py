"""api: watchlist 엔드포인트. DB 모의 없이 실제 test DB 사용."""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from sajucandle.api import create_app


TEST_DSN = os.environ.get("TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    TEST_DSN is None, reason="TEST_DATABASE_URL not set"
)


@pytest.fixture
def api_key(monkeypatch):
    monkeypatch.setenv("SAJUCANDLE_API_KEY", "test-key")
    return "test-key"


@pytest.fixture
def client(api_key, monkeypatch):
    """TestClient. create_app()은 lifespan으로 DB 연결."""
    monkeypatch.setenv("DATABASE_URL", TEST_DSN)
    app = create_app()
    with TestClient(app) as c:
        yield c


CHAT_ID = 900001
HEADERS = {"X-SAJUCANDLE-KEY": "test-key"}


def _register_user(client):
    r = client.put(
        f"/v1/users/{CHAT_ID}",
        json={
            "birth_year": 1990, "birth_month": 3, "birth_day": 15,
            "birth_hour": 14, "birth_minute": 0,
            "asset_class_pref": "swing",
        },
        headers=HEADERS,
    )
    assert r.status_code == 200, r.text


def _cleanup(client):
    client.delete(f"/v1/users/{CHAT_ID}", headers=HEADERS)


def test_list_watchlist_requires_api_key(client):
    r = client.get(f"/v1/users/{CHAT_ID}/watchlist")
    assert r.status_code == 401


def test_list_watchlist_empty(client):
    _register_user(client)
    try:
        r = client.get(f"/v1/users/{CHAT_ID}/watchlist", headers=HEADERS)
        assert r.status_code == 200
        assert r.json() == {"items": []}
    finally:
        _cleanup(client)


def test_add_watchlist_success(client):
    _register_user(client)
    try:
        r = client.post(
            f"/v1/users/{CHAT_ID}/watchlist",
            json={"ticker": "AAPL"},
            headers=HEADERS,
        )
        assert r.status_code == 204

        r2 = client.get(f"/v1/users/{CHAT_ID}/watchlist", headers=HEADERS)
        items = r2.json()["items"]
        assert len(items) == 1
        assert items[0]["ticker"] == "AAPL"
    finally:
        _cleanup(client)


def test_add_watchlist_normalizes_symbol(client):
    """`$aapl` → `AAPL`."""
    _register_user(client)
    try:
        r = client.post(
            f"/v1/users/{CHAT_ID}/watchlist",
            json={"ticker": "$aapl"},
            headers=HEADERS,
        )
        assert r.status_code == 204
        r2 = client.get(f"/v1/users/{CHAT_ID}/watchlist", headers=HEADERS)
        assert r2.json()["items"][0]["ticker"] == "AAPL"
    finally:
        _cleanup(client)


def test_add_watchlist_unsupported_ticker_400(client):
    _register_user(client)
    try:
        r = client.post(
            f"/v1/users/{CHAT_ID}/watchlist",
            json={"ticker": "ZZZZ"},
            headers=HEADERS,
        )
        assert r.status_code == 400
        assert "unsupported" in r.json()["detail"].lower()
    finally:
        _cleanup(client)


def test_add_watchlist_duplicate_409_already(client):
    _register_user(client)
    try:
        client.post(
            f"/v1/users/{CHAT_ID}/watchlist",
            json={"ticker": "AAPL"},
            headers=HEADERS,
        )
        r = client.post(
            f"/v1/users/{CHAT_ID}/watchlist",
            json={"ticker": "AAPL"},
            headers=HEADERS,
        )
        assert r.status_code == 409
        assert "already" in r.json()["detail"]
    finally:
        _cleanup(client)


def test_add_watchlist_full_409_full(client):
    _register_user(client)
    try:
        for t in ["AAPL", "MSFT", "GOOGL", "NVDA", "TSLA"]:
            r = client.post(
                f"/v1/users/{CHAT_ID}/watchlist",
                json={"ticker": t},
                headers=HEADERS,
            )
            assert r.status_code == 204
        r = client.post(
            f"/v1/users/{CHAT_ID}/watchlist",
            json={"ticker": "BTCUSDT"},
            headers=HEADERS,
        )
        assert r.status_code == 409
        assert "full" in r.json()["detail"]
    finally:
        _cleanup(client)


def test_add_watchlist_user_not_registered_404(client):
    r = client.post(
        "/v1/users/999999999/watchlist",
        json={"ticker": "AAPL"},
        headers=HEADERS,
    )
    assert r.status_code == 404


def test_remove_watchlist_success(client):
    _register_user(client)
    try:
        client.post(
            f"/v1/users/{CHAT_ID}/watchlist",
            json={"ticker": "AAPL"},
            headers=HEADERS,
        )
        r = client.delete(
            f"/v1/users/{CHAT_ID}/watchlist/AAPL",
            headers=HEADERS,
        )
        assert r.status_code == 204
        r2 = client.get(f"/v1/users/{CHAT_ID}/watchlist", headers=HEADERS)
        assert r2.json()["items"] == []
    finally:
        _cleanup(client)


def test_remove_watchlist_missing_404(client):
    _register_user(client)
    try:
        r = client.delete(
            f"/v1/users/{CHAT_ID}/watchlist/AAPL",
            headers=HEADERS,
        )
        assert r.status_code == 404
        assert "not in watchlist" in r.json()["detail"]
    finally:
        _cleanup(client)


def test_remove_watchlist_normalizes_symbol(client):
    _register_user(client)
    try:
        client.post(
            f"/v1/users/{CHAT_ID}/watchlist",
            json={"ticker": "AAPL"},
            headers=HEADERS,
        )
        r = client.delete(
            f"/v1/users/{CHAT_ID}/watchlist/aapl",
            headers=HEADERS,
        )
        assert r.status_code == 204
    finally:
        _cleanup(client)


def test_admin_watchlist_symbols_returns_union(client):
    _register_user(client)
    try:
        for t in ["AAPL", "TSLA"]:
            client.post(
                f"/v1/users/{CHAT_ID}/watchlist",
                json={"ticker": t},
                headers=HEADERS,
            )
        r = client.get("/v1/admin/watchlist-symbols", headers=HEADERS)
        assert r.status_code == 200
        symbols = set(r.json()["symbols"])
        assert symbols == {"AAPL", "TSLA"}
    finally:
        _cleanup(client)


def test_admin_watchlist_symbols_requires_api_key(client):
    r = client.get("/v1/admin/watchlist-symbols")
    assert r.status_code == 401

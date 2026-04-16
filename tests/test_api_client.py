"""api_client 단위 테스트. respx로 API 모킹."""
from __future__ import annotations

import httpx
import pytest
import respx

from sajucandle.api_client import (
    ApiClient,
    ApiError,
    NotFoundError,
)


BASE = "https://api.test"
KEY = "test-key"


@pytest.fixture
def client():
    return ApiClient(base_url=BASE, api_key=KEY, timeout=1.0)


@respx.mock
async def test_put_user_sends_correct_request(client):
    route = respx.put(f"{BASE}/v1/users/123").mock(
        return_value=httpx.Response(200, json={
            "telegram_chat_id": 123,
            "birth_year": 1990, "birth_month": 3, "birth_day": 15,
            "birth_hour": 14, "birth_minute": 0,
            "asset_class_pref": "swing",
            "created_at": "2026-04-16T00:00:00Z",
            "updated_at": "2026-04-16T00:00:00Z",
        })
    )
    result = await client.put_user(
        123,
        birth_year=1990, birth_month=3, birth_day=15,
        birth_hour=14, birth_minute=0, asset_class_pref="swing",
    )
    assert route.called
    assert route.calls.last.request.headers["X-SAJUCANDLE-KEY"] == KEY
    assert result["telegram_chat_id"] == 123


@respx.mock
async def test_get_user_404_raises_notfound(client):
    respx.get(f"{BASE}/v1/users/999").mock(
        return_value=httpx.Response(404, json={"detail": "user not found"})
    )
    with pytest.raises(NotFoundError):
        await client.get_user(999)


@respx.mock
async def test_get_user_success(client):
    respx.get(f"{BASE}/v1/users/123").mock(
        return_value=httpx.Response(200, json={
            "telegram_chat_id": 123,
            "birth_year": 1990, "birth_month": 3, "birth_day": 15,
            "birth_hour": 14, "birth_minute": 0,
            "asset_class_pref": "swing",
            "created_at": "2026-04-16T00:00:00Z",
            "updated_at": "2026-04-16T00:00:00Z",
        })
    )
    result = await client.get_user(123)
    assert result["birth_year"] == 1990


@respx.mock
async def test_delete_user_204(client):
    route = respx.delete(f"{BASE}/v1/users/123").mock(
        return_value=httpx.Response(204)
    )
    await client.delete_user(123)
    assert route.called


@respx.mock
async def test_get_score_success(client):
    respx.get(f"{BASE}/v1/users/123/score").mock(
        return_value=httpx.Response(200, json={
            "chat_id": 123, "date": "2026-04-16", "asset_class": "swing",
            "iljin": "庚申", "composite_score": 72, "signal_grade": "👍 진입각",
            "axes": {
                "wealth":     {"score": 78, "reason": "..."},
                "decision":   {"score": 65, "reason": "..."},
                "volatility": {"score": 70, "reason": "..."},
                "flow":       {"score": 75, "reason": "..."},
            },
            "best_hours": [
                {"shichen": "巳", "time_range": "09:00~11:00", "multiplier": 1.15},
            ],
        })
    )
    result = await client.get_score(123, date="2026-04-16", asset="swing")
    assert result["composite_score"] == 72


@respx.mock
async def test_500_raises_apierror(client):
    respx.get(f"{BASE}/v1/users/1").mock(return_value=httpx.Response(500))
    with pytest.raises(ApiError):
        await client.get_user(1)

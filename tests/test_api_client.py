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


def _signal_response_fixture() -> dict:
    return {
        "chat_id": 123, "ticker": "BTCUSDT", "date": "2026-04-16",
        "price": {"current": 67432.1, "change_pct_24h": 2.15},
        "saju": {"composite": 55, "grade": "🔄 관망"},
        "chart": {
            "score": 72, "rsi": 58.2, "ma20": 65100.0, "ma50": 62300.0,
            "ma_trend": "up", "volume_ratio": 1.3,
            "reason": "RSI 58(중립), MA20>MA50, 볼륨→",
        },
        "composite_score": 65, "signal_grade": "진입",
        "best_hours": [
            {"shichen": "寅", "time_range": "03:00~05:00", "multiplier": 1.1},
        ],
    }


@respx.mock
async def test_get_signal_success(client):
    route = respx.get(f"{BASE}/v1/users/123/signal").mock(
        return_value=httpx.Response(200, json=_signal_response_fixture())
    )
    result = await client.get_signal(123, ticker="BTCUSDT")
    assert route.called
    assert route.calls.last.request.url.params["ticker"] == "BTCUSDT"
    assert result["composite_score"] == 65
    assert result["signal_grade"] == "진입"


@respx.mock
async def test_get_signal_404_raises_notfound(client):
    respx.get(f"{BASE}/v1/users/999/signal").mock(
        return_value=httpx.Response(404, json={"detail": "user not found"})
    )
    with pytest.raises(NotFoundError):
        await client.get_signal(999)


@respx.mock
async def test_get_signal_502_raises_apierror(client):
    respx.get(f"{BASE}/v1/users/123/signal").mock(
        return_value=httpx.Response(502, json={"detail": "chart data unavailable"})
    )
    with pytest.raises(ApiError) as exc_info:
        await client.get_signal(123)
    assert exc_info.value.status == 502

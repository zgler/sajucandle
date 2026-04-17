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


# ─────────────────────────────────────────────
# get_admin_users
# ─────────────────────────────────────────────

@respx.mock
async def test_get_admin_users_returns_list(client):
    route = respx.get(f"{BASE}/v1/admin/users").mock(
        return_value=httpx.Response(200, json={"chat_ids": [1, 2, 3]})
    )
    result = await client.get_admin_users()
    assert route.called
    assert route.calls.last.request.headers["X-SAJUCANDLE-KEY"] == KEY
    assert result == [1, 2, 3]


@respx.mock
async def test_get_admin_users_empty(client):
    respx.get(f"{BASE}/v1/admin/users").mock(
        return_value=httpx.Response(200, json={"chat_ids": []})
    )
    result = await client.get_admin_users()
    assert result == []


@respx.mock
async def test_get_admin_users_401_raises(client):
    respx.get(f"{BASE}/v1/admin/users").mock(
        return_value=httpx.Response(401, json={"detail": "invalid key"})
    )
    with pytest.raises(ApiError) as exc_info:
        await client.get_admin_users()
    assert exc_info.value.status == 401


# ─────────────────────────────────────────────
# get_supported_symbols
# ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_supported_symbols_returns_list():
    """지원 심볼 목록 API 응답을 파싱."""
    import respx as _respx
    from httpx import Response

    with _respx.mock(base_url="http://test") as mock:
        mock.get("/v1/signal/symbols").mock(
            return_value=Response(
                200,
                json={
                    "symbols": [
                        {"ticker": "BTCUSDT", "name": "Bitcoin", "category": "crypto"},
                        {"ticker": "AAPL", "name": "Apple", "category": "us_stock"},
                    ]
                },
            )
        )
        c = ApiClient(base_url="http://test", api_key="k")
        out = await c.get_supported_symbols()
    assert out == [
        {"ticker": "BTCUSDT", "name": "Bitcoin", "category": "crypto"},
        {"ticker": "AAPL", "name": "Apple", "category": "us_stock"},
    ]


@pytest.mark.asyncio
async def test_get_supported_symbols_401():
    """인증 실패 시 ApiError."""
    import respx as _respx
    from httpx import Response

    with _respx.mock(base_url="http://test") as mock:
        mock.get("/v1/signal/symbols").mock(
            return_value=Response(401, json={"detail": "invalid key"})
        )
        c = ApiClient(base_url="http://test", api_key="wrong")
        with pytest.raises(ApiError) as exc:
            await c.get_supported_symbols()
    assert exc.value.status == 401


# ─────────────────────────────────────────────
# Week 7: watchlist
# ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_watchlist_returns_items():
    import respx
    from httpx import Response
    from sajucandle.api_client import ApiClient

    with respx.mock(base_url="http://test") as mock:
        mock.get("/v1/users/42/watchlist").mock(
            return_value=Response(
                200,
                json={"items": [
                    {"ticker": "AAPL", "added_at": "2026-04-16T09:00:00+09:00"},
                    {"ticker": "TSLA", "added_at": "2026-04-17T10:00:00+09:00"},
                ]},
            )
        )
        c = ApiClient(base_url="http://test", api_key="k")
        items = await c.get_watchlist(42)
    assert len(items) == 2
    assert items[0]["ticker"] == "AAPL"


@pytest.mark.asyncio
async def test_add_watchlist_success_204():
    import respx
    from httpx import Response
    from sajucandle.api_client import ApiClient

    with respx.mock(base_url="http://test") as mock:
        mock.post("/v1/users/42/watchlist").mock(return_value=Response(204))
        c = ApiClient(base_url="http://test", api_key="k")
        await c.add_watchlist(42, "AAPL")   # returns None


@pytest.mark.asyncio
async def test_add_watchlist_conflict_409_full():
    import respx
    from httpx import Response
    from sajucandle.api_client import ApiClient, ApiError

    with respx.mock(base_url="http://test") as mock:
        mock.post("/v1/users/42/watchlist").mock(
            return_value=Response(409, json={"detail": "watchlist full (max 5)"})
        )
        c = ApiClient(base_url="http://test", api_key="k")
        with pytest.raises(ApiError) as exc:
            await c.add_watchlist(42, "AAPL")
    assert exc.value.status == 409
    assert "full" in exc.value.detail


@pytest.mark.asyncio
async def test_add_watchlist_conflict_409_already():
    import respx
    from httpx import Response
    from sajucandle.api_client import ApiClient, ApiError

    with respx.mock(base_url="http://test") as mock:
        mock.post("/v1/users/42/watchlist").mock(
            return_value=Response(409, json={"detail": "already in watchlist"})
        )
        c = ApiClient(base_url="http://test", api_key="k")
        with pytest.raises(ApiError) as exc:
            await c.add_watchlist(42, "AAPL")
    assert exc.value.status == 409
    assert "already" in exc.value.detail


@pytest.mark.asyncio
async def test_add_watchlist_unsupported_400():
    import respx
    from httpx import Response
    from sajucandle.api_client import ApiClient, ApiError

    with respx.mock(base_url="http://test") as mock:
        mock.post("/v1/users/42/watchlist").mock(
            return_value=Response(400, json={"detail": "unsupported ticker: AMZN"})
        )
        c = ApiClient(base_url="http://test", api_key="k")
        with pytest.raises(ApiError) as exc:
            await c.add_watchlist(42, "AMZN")
    assert exc.value.status == 400


@pytest.mark.asyncio
async def test_remove_watchlist_success_204():
    import respx
    from httpx import Response
    from sajucandle.api_client import ApiClient

    with respx.mock(base_url="http://test") as mock:
        mock.delete("/v1/users/42/watchlist/AAPL").mock(return_value=Response(204))
        c = ApiClient(base_url="http://test", api_key="k")
        await c.remove_watchlist(42, "AAPL")


@pytest.mark.asyncio
async def test_remove_watchlist_not_found_404():
    import respx
    from httpx import Response
    from sajucandle.api_client import ApiClient, NotFoundError

    with respx.mock(base_url="http://test") as mock:
        mock.delete("/v1/users/42/watchlist/AAPL").mock(
            return_value=Response(404, json={"detail": "not in watchlist"})
        )
        c = ApiClient(base_url="http://test", api_key="k")
        with pytest.raises(NotFoundError):
            await c.remove_watchlist(42, "AAPL")


@pytest.mark.asyncio
async def test_get_admin_watchlist_symbols_returns_list():
    import respx
    from httpx import Response
    from sajucandle.api_client import ApiClient

    with respx.mock(base_url="http://test") as mock:
        mock.get("/v1/admin/watchlist-symbols").mock(
            return_value=Response(200, json={"symbols": ["AAPL", "TSLA"]})
        )
        c = ApiClient(base_url="http://test", api_key="k")
        syms = await c.get_admin_watchlist_symbols()
    assert syms == ["AAPL", "TSLA"]

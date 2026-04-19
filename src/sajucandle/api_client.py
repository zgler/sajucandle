"""봇용 API HTTP 클라이언트. httpx AsyncClient 래퍼.

에러 체계:
- NotFoundError: 404
- ApiError: 기타 4xx/5xx
- TimeoutError (stdlib), httpx.TransportError: 네트워크
봇 핸들러는 이들을 사용자 친화적 메시지로 변환.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

import httpx


class ApiError(RuntimeError):
    """4xx/5xx 응답."""

    def __init__(self, status: int, detail: str):
        super().__init__(f"API {status}: {detail}")
        self.status = status
        self.detail = detail


class NotFoundError(ApiError):
    pass


class ApiClient:
    def __init__(self, base_url: str, api_key: str, timeout: float = 10.0):
        self._base = base_url.rstrip("/")
        self._headers = {"X-SAJUCANDLE-KEY": api_key}
        self._timeout = timeout

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self._base, headers=self._headers, timeout=self._timeout
        )

    async def _raise_for_status(self, resp: httpx.Response) -> None:
        if 200 <= resp.status_code < 300:
            return
        try:
            detail = resp.json().get("detail", "")
        except Exception:
            detail = resp.text
        if resp.status_code == 404:
            raise NotFoundError(404, detail)
        raise ApiError(resp.status_code, detail)

    async def put_user(
        self,
        chat_id: int,
        *,
        birth_year: int,
        birth_month: int,
        birth_day: int,
        birth_hour: int,
        birth_minute: int = 0,
        asset_class_pref: str = "swing",
    ) -> Dict[str, Any]:
        body = {
            "birth_year": birth_year,
            "birth_month": birth_month,
            "birth_day": birth_day,
            "birth_hour": birth_hour,
            "birth_minute": birth_minute,
            "asset_class_pref": asset_class_pref,
        }
        async with self._client() as c:
            r = await c.put(f"/v1/users/{chat_id}", json=body)
        await self._raise_for_status(r)
        return r.json()

    async def get_user(self, chat_id: int) -> Dict[str, Any]:
        async with self._client() as c:
            r = await c.get(f"/v1/users/{chat_id}")
        await self._raise_for_status(r)
        return r.json()

    async def delete_user(self, chat_id: int) -> None:
        async with self._client() as c:
            r = await c.delete(f"/v1/users/{chat_id}")
        await self._raise_for_status(r)

    async def get_score(
        self,
        chat_id: int,
        date: Optional[str] = None,
        asset: Optional[str] = None,
    ) -> Dict[str, Any]:
        params: Dict[str, str] = {}
        if date:
            params["date"] = date
        if asset:
            params["asset"] = asset
        async with self._client() as c:
            r = await c.get(f"/v1/users/{chat_id}/score", params=params)
        await self._raise_for_status(r)
        return r.json()

    async def get_admin_users(self) -> list[int]:
        """등록된 사용자 chat_id 리스트. 브로드캐스트용."""
        async with self._client() as c:
            r = await c.get("/v1/admin/users")
        await self._raise_for_status(r)
        data = r.json()
        return list(data.get("chat_ids", []))

    async def get_signal(
        self,
        chat_id: int,
        ticker: str = "BTCUSDT",
        date: Optional[str] = None,
    ) -> Dict[str, Any]:
        params: Dict[str, str] = {"ticker": ticker}
        if date:
            params["date"] = date
        async with self._client() as c:
            r = await c.get(f"/v1/users/{chat_id}/signal", params=params)
        await self._raise_for_status(r)
        return r.json()

    async def get_supported_symbols(self) -> list[dict]:
        """GET /v1/signal/symbols. 반환: [{ticker,name,category}, ...]."""
        async with self._client() as c:
            r = await c.get("/v1/signal/symbols")
        await self._raise_for_status(r)
        data = r.json()
        return list(data.get("symbols", []))

    async def get_watchlist(self, chat_id: int) -> list[dict]:
        """GET /v1/users/{chat_id}/watchlist. [{ticker, added_at}, ...]"""
        async with self._client() as c:
            r = await c.get(f"/v1/users/{chat_id}/watchlist")
        await self._raise_for_status(r)
        return list(r.json().get("items", []))

    async def add_watchlist(self, chat_id: int, ticker: str) -> None:
        """POST /v1/users/{chat_id}/watchlist body={ticker}. 204 or raise ApiError."""
        async with self._client() as c:
            r = await c.post(
                f"/v1/users/{chat_id}/watchlist",
                json={"ticker": ticker},
            )
        await self._raise_for_status(r)

    async def remove_watchlist(self, chat_id: int, ticker: str) -> None:
        """DELETE /v1/users/{chat_id}/watchlist/{ticker}. 204 or raise ApiError."""
        async with self._client() as c:
            r = await c.delete(f"/v1/users/{chat_id}/watchlist/{ticker}")
        await self._raise_for_status(r)

    async def get_admin_watchlist_symbols(self) -> list[str]:
        """GET /v1/admin/watchlist-symbols. 반환: ['AAPL', 'TSLA', ...]"""
        async with self._client() as c:
            r = await c.get("/v1/admin/watchlist-symbols")
        await self._raise_for_status(r)
        return list(r.json().get("symbols", []))

    async def get_admin_ohlcv(
        self,
        ticker: str,
        *,
        interval: str = "1h",
        since: Optional[str] = None,
        limit: int = 168,
    ) -> list[dict]:
        """GET /v1/admin/ohlcv. Phase 0 tracking용."""
        params: Dict[str, str] = {
            "ticker": ticker,
            "interval": interval,
            "limit": str(limit),
        }
        if since:
            params["since"] = since
        async with self._client() as c:
            r = await c.get("/v1/admin/ohlcv", params=params)
        await self._raise_for_status(r)
        return list(r.json().get("klines", []))

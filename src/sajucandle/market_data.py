"""Binance 공개 REST로 OHLCV 받아오는 마켓 데이터 클라이언트.

인증 불필요. Redis 2단 캐시로 장애 대응:
  - fresh (TTL=300s): 일반 조회
  - backup (TTL=86400s): Binance 장애 시 fallback

Redis 없는 환경(로컬 dev)은 캐시 건너뛰고 HTTP만. HTTP 실패 시 MarketDataUnavailable.
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.binance.com"
_FRESH_TTL = 300            # 5분
_BACKUP_TTL = 86400         # 24시간


class MarketDataUnavailable(Exception):
    """Binance 응답 실패 + 캐시 모두 없음."""


@dataclass
class Kline:
    open_time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["open_time"] = self.open_time.isoformat()
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Kline":
        return cls(
            open_time=datetime.fromisoformat(d["open_time"]),
            open=float(d["open"]),
            high=float(d["high"]),
            low=float(d["low"]),
            close=float(d["close"]),
            volume=float(d["volume"]),
        )

    @classmethod
    def from_binance_row(cls, row: list[Any]) -> "Kline":
        """Binance /klines 응답 1개 항목 → Kline.

        row[0]=open_time(ms), row[1]=open, row[2]=high, row[3]=low,
        row[4]=close, row[5]=volume, ... (이후 필드는 무시)
        """
        return cls(
            open_time=datetime.fromtimestamp(row[0] / 1000, tz=timezone.utc),
            open=float(row[1]),
            high=float(row[2]),
            low=float(row[3]),
            close=float(row[4]),
            volume=float(row[5]),
        )


class BinanceClient:
    def __init__(
        self,
        http_client: Optional[httpx.Client] = None,
        redis_client: Optional[Any] = None,
        timeout: float = 3.0,
    ) -> None:
        self._http = http_client or httpx.Client(timeout=timeout)
        self._owns_http = http_client is None
        self._redis = redis_client
        self._timeout = timeout

    def close(self) -> None:
        if self._owns_http:
            self._http.close()

    # ─────────────────────────────────────────────
    # Public
    # ─────────────────────────────────────────────

    def fetch_klines(
        self,
        symbol: str,
        interval: str = "1d",
        limit: int = 100,
    ) -> list[Kline]:
        fresh_key = f"ohlcv:{symbol}:{interval}:fresh"
        backup_key = f"ohlcv:{symbol}:{interval}:backup"

        # 1. fresh cache
        cached = self._redis_get(fresh_key)
        if cached is not None:
            return cached

        # 2. HTTP
        try:
            klines = self._http_fetch(symbol, interval, limit)
        except Exception as e:
            logger.warning("binance fetch failed: %s", e)
            # 3. backup cache fallback
            backup = self._redis_get(backup_key)
            if backup is not None:
                logger.warning("using backup ohlcv cache for %s", symbol)
                return backup
            raise MarketDataUnavailable(
                f"binance fetch failed and no backup cache: {e}"
            ) from e

        # 4. HTTP 성공 → 양쪽 캐시 set
        self._redis_set(fresh_key, klines, _FRESH_TTL)
        self._redis_set(backup_key, klines, _BACKUP_TTL)
        return klines

    # ─────────────────────────────────────────────
    # Internals
    # ─────────────────────────────────────────────

    def _http_fetch(self, symbol: str, interval: str, limit: int) -> list[Kline]:
        url = f"{_BASE_URL}/api/v3/klines"
        r = self._http.get(
            url,
            params={"symbol": symbol, "interval": interval, "limit": limit},
            timeout=self._timeout,
        )
        r.raise_for_status()
        rows = r.json()
        if not isinstance(rows, list) or not rows:
            raise ValueError(f"unexpected klines response: {rows!r}"[:200])
        return [Kline.from_binance_row(row) for row in rows]

    def _redis_get(self, key: str) -> Optional[list[Kline]]:
        if self._redis is None:
            return None
        try:
            raw = self._redis.get(key)
        except Exception as e:
            logger.warning("redis GET %s failed: %s", key, e)
            return None
        if raw is None:
            return None
        try:
            if isinstance(raw, (bytes, bytearray)):
                raw = raw.decode("utf-8")
            data = json.loads(raw)
            return [Kline.from_dict(d) for d in data]
        except Exception as e:
            logger.warning("redis %s deserialize failed: %s", key, e)
            return None

    def _redis_set(self, key: str, klines: list[Kline], ttl: int) -> None:
        if self._redis is None:
            return
        try:
            payload = json.dumps([k.to_dict() for k in klines])
            self._redis.setex(key, ttl, payload)
        except Exception as e:
            logger.warning("redis SETEX %s failed: %s", key, e)

"""yfinance 기반 미국주식 OHLCV 클라이언트.

Redis 2단 캐시:
  - ohlcv:{symbol}:{interval}:fresh   TTL=3600 (1시간)
  - ohlcv:{symbol}:{interval}:backup  TTL=86400 (24시간, 장애 fallback)

yfinance.Ticker.history()는 동기이며 내부적으로 HTTP 호출. 주말/휴장일에 호출하면
마지막 거래일까지의 DataFrame을 반환한다.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime
from typing import Any, Optional
from zoneinfo import ZoneInfo

import yfinance as yf

from sajucandle.market.base import UnsupportedTicker
from sajucandle.market_data import Kline, MarketDataUnavailable

logger = logging.getLogger(__name__)

_NY_TZ = ZoneInfo("America/New_York")
_SUPPORTED = frozenset({"AAPL", "MSFT", "GOOGL", "NVDA", "TSLA"})
_FRESH_TTL = 3600
_BACKUP_TTL = 86400


class YFinanceClient:
    def __init__(self, redis_client: Optional[Any] = None) -> None:
        self._redis = redis_client

    # ─────────────────────────────────────────────
    # Public
    # ─────────────────────────────────────────────

    def fetch_klines(
        self,
        symbol: str,
        interval: str = "1d",
        limit: int = 100,
    ) -> list[Kline]:
        sym = symbol.upper().lstrip("$")
        if sym not in _SUPPORTED:
            raise UnsupportedTicker(sym)

        fresh_key = f"ohlcv:{sym}:{interval}:fresh"
        backup_key = f"ohlcv:{sym}:{interval}:backup"

        cached = self._redis_get(fresh_key)
        if cached is not None:
            return cached

        try:
            klines = self._yf_fetch(sym, interval, limit)
        except Exception as e:
            logger.warning("yfinance fetch failed symbol=%s: %s", sym, e)
            backup = self._redis_get(backup_key)
            if backup is not None:
                logger.warning("using backup ohlcv cache for %s", sym)
                return backup
            raise MarketDataUnavailable(
                f"yfinance fetch failed and no backup cache: {e}"
            ) from e

        if not klines:
            raise MarketDataUnavailable(
                f"yfinance returned empty data for {sym}"
            )

        self._redis_set(fresh_key, klines, _FRESH_TTL)
        self._redis_set(backup_key, klines, _BACKUP_TTL)
        return klines

    # ─────────────────────────────────────────────
    # Internals
    # ─────────────────────────────────────────────

    def _yf_fetch(self, symbol: str, interval: str, limit: int) -> list[Kline]:
        """yfinance.Ticker.history() → list[Kline]."""
        ticker = yf.Ticker(symbol)
        # period="{limit}d"로 요청. 주말/휴장 포함되지 않으므로 limit 근처의 거래일 반환.
        df = ticker.history(period=f"{limit}d", interval=interval, auto_adjust=False)
        if df is None or df.empty:
            return []
        klines: list[Kline] = []
        for idx, row in df.iterrows():
            ts = idx.to_pydatetime() if hasattr(idx, "to_pydatetime") else idx
            klines.append(
                Kline(
                    open_time=ts,
                    open=float(row["Open"]),
                    high=float(row["High"]),
                    low=float(row["Low"]),
                    close=float(row["Close"]),
                    volume=float(row["Volume"]),
                )
            )
        return klines

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

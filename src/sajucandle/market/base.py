"""MarketDataProvider Protocol + UnsupportedTicker.

ticker에 따라 BinanceClient(crypto) 또는 YFinanceClient(us_stocks)를 선택하는
라우팅 계층을 가능하게 하는 공통 인터페이스.
"""
from __future__ import annotations

from datetime import date
from typing import Protocol

from sajucandle.market_data import Kline


class UnsupportedTicker(Exception):
    """화이트리스트에 없는 심볼이 요청됐을 때."""

    def __init__(self, symbol: str):
        super().__init__(f"unsupported ticker: {symbol}")
        self.symbol = symbol


class MarketDataProvider(Protocol):
    """OHLCV 제공자 공통 인터페이스.

    BinanceClient와 YFinanceClient 모두 구조적으로 만족한다.
    runtime_checkable은 사용하지 않는다 — duck typing만으로 충분.
    """

    def fetch_klines(
        self, symbol: str, interval: str = "1d", limit: int = 100
    ) -> list[Kline]: ...

    def is_market_open(self, symbol: str) -> bool: ...

    def last_session_date(self, symbol: str) -> date: ...

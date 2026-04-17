"""ticker 문자열을 BinanceClient 또는 YFinanceClient로 라우팅.

화이트리스트 기반. 그 외 심볼은 UnsupportedTicker.
"""
from __future__ import annotations

from dataclasses import dataclass

from sajucandle.market.base import MarketDataProvider, UnsupportedTicker


_CRYPTO_SYMBOLS = frozenset({"BTCUSDT"})
_STOCK_SYMBOLS = frozenset({"AAPL", "MSFT", "GOOGL", "NVDA", "TSLA"})


@dataclass
class MarketRouter:
    binance: MarketDataProvider
    yfinance: MarketDataProvider

    def get_provider(self, ticker: str) -> MarketDataProvider:
        sym = ticker.upper().lstrip("$")
        if sym in _CRYPTO_SYMBOLS:
            return self.binance
        if sym in _STOCK_SYMBOLS:
            return self.yfinance
        raise UnsupportedTicker(sym)

    @classmethod
    def all_symbols(cls) -> list[dict[str, str]]:
        """전체 지원 심볼 카탈로그. /v1/signal/symbols 및 /signal list용."""
        return [
            {"ticker": "BTCUSDT", "name": "Bitcoin", "category": "crypto"},
            {"ticker": "AAPL", "name": "Apple", "category": "us_stock"},
            {"ticker": "MSFT", "name": "Microsoft", "category": "us_stock"},
            {"ticker": "GOOGL", "name": "Alphabet", "category": "us_stock"},
            {"ticker": "NVDA", "name": "NVIDIA", "category": "us_stock"},
            {"ticker": "TSLA", "name": "Tesla", "category": "us_stock"},
        ]

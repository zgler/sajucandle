"""market.base: MarketDataProvider Protocol + UnsupportedTicker."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol

from sajucandle.market.base import MarketDataProvider, UnsupportedTicker
from sajucandle.market_data import BinanceClient


def test_unsupported_ticker_is_exception():
    """UnsupportedTicker는 Exception 서브클래스여야 한다."""
    assert issubclass(UnsupportedTicker, Exception)


def test_unsupported_ticker_carries_symbol_in_str():
    """에러 메시지에 심볼이 포함되어야 한다."""
    e = UnsupportedTicker("AMZN")
    assert "AMZN" in str(e)


def test_market_data_provider_is_protocol():
    """MarketDataProvider는 Protocol이며 runtime_checkable 아님(duck typing)."""
    assert Protocol in MarketDataProvider.__mro__ or hasattr(
        MarketDataProvider, "_is_protocol"
    )


def test_binance_client_satisfies_protocol_structurally():
    """BinanceClient는 세 메서드(fetch_klines, is_market_open, last_session_date)를 가진다."""
    client = BinanceClient()
    assert hasattr(client, "fetch_klines")
    assert hasattr(client, "is_market_open")
    assert hasattr(client, "last_session_date")
    # 실제 호출도 가능해야 함
    assert client.is_market_open("BTCUSDT") is True
    assert client.last_session_date("BTCUSDT") == datetime.now(timezone.utc).date()

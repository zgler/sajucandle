"""market.router: ticker → provider 라우팅."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from sajucandle.market.base import UnsupportedTicker
from sajucandle.market.router import MarketRouter


def _fake_providers():
    binance = MagicMock(name="binance")
    yfinance = MagicMock(name="yfinance")
    return binance, yfinance


def test_btcusdt_routes_to_binance():
    b, y = _fake_providers()
    r = MarketRouter(binance=b, yfinance=y)
    assert r.get_provider("BTCUSDT") is b


def test_aapl_routes_to_yfinance():
    b, y = _fake_providers()
    r = MarketRouter(binance=b, yfinance=y)
    assert r.get_provider("AAPL") is y


def test_unknown_ticker_raises():
    b, y = _fake_providers()
    r = MarketRouter(binance=b, yfinance=y)
    with pytest.raises(UnsupportedTicker):
        r.get_provider("ZZZZ")


def test_lowercase_is_normalized():
    b, y = _fake_providers()
    r = MarketRouter(binance=b, yfinance=y)
    assert r.get_provider("aapl") is y
    assert r.get_provider("btcusdt") is b


def test_dollar_prefix_is_stripped():
    b, y = _fake_providers()
    r = MarketRouter(binance=b, yfinance=y)
    assert r.get_provider("$AAPL") is y


def test_all_symbols_returns_full_catalog():
    b, y = _fake_providers()
    r = MarketRouter(binance=b, yfinance=y)
    symbols = r.all_symbols()
    tickers = [s["ticker"] for s in symbols]
    assert "BTCUSDT" in tickers
    assert "AAPL" in tickers
    assert "MSFT" in tickers
    assert "GOOGL" in tickers
    assert "NVDA" in tickers
    assert "TSLA" in tickers
    # 각 항목은 ticker/name/category를 가진다
    for s in symbols:
        assert set(s.keys()) >= {"ticker", "name", "category"}
        assert s["category"] in ("crypto", "us_stock")

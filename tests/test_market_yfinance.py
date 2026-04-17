"""market.yfinance: YFinanceClient — 미국주식 OHLCV.

yfinance.Ticker를 mock. 실제 네트워크 호출 0회.
"""
from __future__ import annotations

import json
from datetime import datetime
from unittest.mock import patch, MagicMock

import fakeredis
import pandas as pd
import pytest

from sajucandle.market.base import UnsupportedTicker
from sajucandle.market.yfinance import YFinanceClient
from sajucandle.market_data import Kline, MarketDataUnavailable


def _make_yf_dataframe(n: int = 100) -> pd.DataFrame:
    """yfinance Ticker.history() 스타일 DataFrame. DatetimeIndex + OHLCV 컬럼."""
    idx = pd.date_range(end="2026-04-16", periods=n, freq="B", tz="America/New_York")
    rows = []
    for i in range(n):
        base = 180.0 + i * 0.3
        rows.append({
            "Open": base - 0.2,
            "High": base + 0.5,
            "Low": base - 0.5,
            "Close": base,
            "Volume": 50_000_000 + i * 100_000,
        })
    return pd.DataFrame(rows, index=idx)


def test_fetch_klines_rejects_unsupported_symbol():
    """화이트리스트 외 심볼은 UnsupportedTicker."""
    client = YFinanceClient()
    with pytest.raises(UnsupportedTicker):
        client.fetch_klines("AMZN")


def test_fetch_klines_returns_klines_for_supported_symbol():
    """yf.Ticker를 mock하고 AAPL 조회 시 Kline 리스트 반환."""
    df = _make_yf_dataframe(100)
    fake_ticker = MagicMock()
    fake_ticker.history.return_value = df

    client = YFinanceClient()
    with patch("sajucandle.market.yfinance.yf.Ticker", return_value=fake_ticker):
        klines = client.fetch_klines("AAPL")

    assert len(klines) == 100
    assert all(isinstance(k, Kline) for k in klines)
    last = klines[-1]
    assert last.close == pytest.approx(180.0 + 99 * 0.3)
    assert last.volume > 0


def test_fetch_klines_normalizes_symbol_to_upper():
    """소문자 입력도 대문자로 정규화해서 처리."""
    df = _make_yf_dataframe(5)
    fake_ticker = MagicMock()
    fake_ticker.history.return_value = df

    client = YFinanceClient()
    with patch("sajucandle.market.yfinance.yf.Ticker", return_value=fake_ticker) as p:
        client.fetch_klines("aapl")
    # 호출 인자 첫번째가 AAPL 이어야 함
    args, kwargs = p.call_args
    assert args[0] == "AAPL"


def test_fetch_klines_fresh_cache_hit_skips_network():
    """fresh 캐시에 hit 하면 yf.Ticker 호출 없이 반환."""
    r = fakeredis.FakeStrictRedis()
    # 미리 fresh 키 주입
    preloaded = [
        Kline(
            open_time=datetime.fromisoformat("2026-04-16T00:00:00+00:00"),
            open=180.0, high=181.0, low=179.5, close=180.5, volume=1_000_000,
        ),
    ]
    r.setex(
        "ohlcv:AAPL:1d:fresh",
        3600,
        json.dumps([k.to_dict() for k in preloaded]),
    )

    client = YFinanceClient(redis_client=r)
    with patch("sajucandle.market.yfinance.yf.Ticker") as p:
        klines = client.fetch_klines("AAPL")
        assert p.call_count == 0   # network skipped
    assert len(klines) == 1
    assert klines[0].close == 180.5


def test_fetch_klines_writes_fresh_and_backup_cache():
    """성공 시 fresh (3600) + backup (86400) 양쪽에 set."""
    df = _make_yf_dataframe(3)
    fake_ticker = MagicMock()
    fake_ticker.history.return_value = df

    r = fakeredis.FakeStrictRedis()
    client = YFinanceClient(redis_client=r)
    with patch("sajucandle.market.yfinance.yf.Ticker", return_value=fake_ticker):
        client.fetch_klines("AAPL")

    assert r.exists("ohlcv:AAPL:1d:fresh")
    assert r.exists("ohlcv:AAPL:1d:backup")
    # fresh TTL ~ 3600 이내
    ttl_fresh = r.ttl("ohlcv:AAPL:1d:fresh")
    assert 0 < ttl_fresh <= 3600
    ttl_backup = r.ttl("ohlcv:AAPL:1d:backup")
    assert 3600 < ttl_backup <= 86400


def test_fetch_klines_empty_dataframe_raises_unavailable():
    """yfinance가 빈 DataFrame 반환 시 MarketDataUnavailable (상장폐지 등)."""
    fake_ticker = MagicMock()
    fake_ticker.history.return_value = pd.DataFrame()
    client = YFinanceClient()
    with patch("sajucandle.market.yfinance.yf.Ticker", return_value=fake_ticker):
        with pytest.raises(MarketDataUnavailable):
            client.fetch_klines("AAPL")


def test_fetch_klines_network_error_uses_backup_cache():
    """yfinance 예외 시 backup 캐시 사용."""
    r = fakeredis.FakeStrictRedis()
    backup_klines = [
        Kline(
            open_time=datetime.fromisoformat("2026-04-15T00:00:00+00:00"),
            open=179.0, high=180.0, low=178.5, close=179.5, volume=900_000,
        ),
    ]
    r.setex(
        "ohlcv:AAPL:1d:backup",
        86400,
        json.dumps([k.to_dict() for k in backup_klines]),
    )

    client = YFinanceClient(redis_client=r)
    with patch(
        "sajucandle.market.yfinance.yf.Ticker",
        side_effect=RuntimeError("network down"),
    ):
        klines = client.fetch_klines("AAPL")
    assert len(klines) == 1
    assert klines[0].close == 179.5


def test_fetch_klines_network_error_no_backup_raises():
    """예외 + backup 없으면 MarketDataUnavailable."""
    client = YFinanceClient()
    with patch(
        "sajucandle.market.yfinance.yf.Ticker",
        side_effect=RuntimeError("boom"),
    ):
        with pytest.raises(MarketDataUnavailable):
            client.fetch_klines("AAPL")

"""market_data: Binance 공개 REST + Redis 2단 캐시.

respx로 Binance mock, 실제 호출 0회.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import fakeredis
import httpx
import pytest
import respx

from sajucandle.market_data import (
    BinanceClient,
    Kline,
    MarketDataUnavailable,
)


def _make_binance_response(n: int = 100) -> list[list]:
    """Binance /klines 원본 포맷 응답 생성."""
    base_ms = 1700000000000  # 2023-11-14T22:13:20Z
    one_day_ms = 86400 * 1000
    rows = []
    for i in range(n):
        open_t = base_ms + i * one_day_ms
        # open, high, low, close, volume
        rows.append([
            open_t,
            str(100.0 + i),        # open
            str(100.0 + i + 2),    # high
            str(100.0 + i - 1),    # low
            str(100.0 + i + 1),    # close
            str(1000.0 + i * 10),  # volume
            open_t + one_day_ms - 1,  # close_time
            "0", "0", "0", "0", "0",  # ignored
        ])
    return rows


# ─────────────────────────────────────────────
# Fresh cache hit
# ─────────────────────────────────────────────

def test_fetch_klines_fresh_cache_hit():
    r = fakeredis.FakeStrictRedis()
    # 미리 fresh 키 주입
    preloaded = [
        Kline(
            open_time=datetime(2026, 4, 1, tzinfo=timezone.utc),
            open=1.0, high=2.0, low=0.5, close=1.5, volume=100.0,
        )
    ]
    payload = json.dumps([k.to_dict() for k in preloaded])
    r.setex("ohlcv:BTCUSDT:1d:fresh", 300, payload)

    with respx.mock(assert_all_called=False) as mock:
        klines = mock.get("https://data-api.binance.vision/api/v3/klines").respond(200, json=[])
        client = BinanceClient(redis_client=r)
        out = client.fetch_klines("BTCUSDT")
        assert len(out) == 1
        assert out[0].close == 1.5
        # HTTP 호출 안 일어나야 함
        assert not klines.called


# ─────────────────────────────────────────────
# HTTP 성공 → fresh + backup 둘 다 set
# ─────────────────────────────────────────────

@respx.mock
def test_fetch_klines_http_success_sets_both_caches():
    r = fakeredis.FakeStrictRedis()
    binance = respx.get("https://data-api.binance.vision/api/v3/klines").respond(
        200, json=_make_binance_response(100)
    )
    client = BinanceClient(redis_client=r)
    out = client.fetch_klines("BTCUSDT")
    assert len(out) == 100
    assert binance.called
    # 둘 다 셋팅됨
    assert r.get("ohlcv:BTCUSDT:1d:fresh") is not None
    assert r.get("ohlcv:BTCUSDT:1d:backup") is not None


# ─────────────────────────────────────────────
# HTTP 실패 + backup 있음 → backup 반환
# ─────────────────────────────────────────────

@respx.mock
def test_fetch_klines_http_fail_backup_hit():
    r = fakeredis.FakeStrictRedis()
    # backup 미리 주입
    preloaded = [
        Kline(
            open_time=datetime(2026, 4, 10, tzinfo=timezone.utc),
            open=50.0, high=52.0, low=49.0, close=51.0, volume=500.0,
        )
    ]
    r.setex(
        "ohlcv:BTCUSDT:1d:backup",
        86400,
        json.dumps([k.to_dict() for k in preloaded]),
    )
    # fresh는 없음 (만료된 것처럼)
    respx.get("https://data-api.binance.vision/api/v3/klines").mock(
        side_effect=httpx.ConnectError("boom")
    )

    client = BinanceClient(redis_client=r)
    out = client.fetch_klines("BTCUSDT")
    assert len(out) == 1
    assert out[0].close == 51.0


# ─────────────────────────────────────────────
# HTTP 실패 + backup 없음 → MarketDataUnavailable
# ─────────────────────────────────────────────

@respx.mock
def test_fetch_klines_http_fail_no_backup_raises():
    r = fakeredis.FakeStrictRedis()
    respx.get("https://data-api.binance.vision/api/v3/klines").mock(
        side_effect=httpx.ConnectError("boom")
    )
    client = BinanceClient(redis_client=r)
    with pytest.raises(MarketDataUnavailable):
        client.fetch_klines("BTCUSDT")


@respx.mock
def test_fetch_klines_http_5xx_no_backup_raises():
    r = fakeredis.FakeStrictRedis()
    respx.get("https://data-api.binance.vision/api/v3/klines").respond(500, text="server err")
    client = BinanceClient(redis_client=r)
    with pytest.raises(MarketDataUnavailable):
        client.fetch_klines("BTCUSDT")


# ─────────────────────────────────────────────
# Redis 없음
# ─────────────────────────────────────────────

@respx.mock
def test_fetch_klines_no_redis_http_ok():
    respx.get("https://data-api.binance.vision/api/v3/klines").respond(
        200, json=_make_binance_response(50)
    )
    client = BinanceClient(redis_client=None)
    out = client.fetch_klines("BTCUSDT")
    assert len(out) == 50


@respx.mock
def test_fetch_klines_no_redis_http_fail_raises():
    respx.get("https://data-api.binance.vision/api/v3/klines").mock(
        side_effect=httpx.TimeoutException("timeout")
    )
    client = BinanceClient(redis_client=None)
    with pytest.raises(MarketDataUnavailable):
        client.fetch_klines("BTCUSDT")


# ─────────────────────────────────────────────
# Kline parse
# ─────────────────────────────────────────────

def test_kline_from_binance_row():
    row = [
        1700000000000, "100.5", "102.0", "99.5", "101.0", "1234.5",
        1700086399999, "0", "0", "0", "0", "0",
    ]
    k = Kline.from_binance_row(row)
    assert k.open == 100.5
    assert k.high == 102.0
    assert k.low == 99.5
    assert k.close == 101.0
    assert k.volume == 1234.5
    assert k.open_time.tzinfo is not None


def test_kline_roundtrip_dict():
    k = Kline(
        open_time=datetime(2026, 4, 16, 12, 0, 0, tzinfo=timezone.utc),
        open=1.0, high=2.0, low=0.5, close=1.5, volume=100.0,
    )
    d = k.to_dict()
    k2 = Kline.from_dict(d)
    assert k == k2


# ─────────────────────────────────────────────
# Week 6: MarketDataProvider protocol conformance
# ─────────────────────────────────────────────

def test_binance_is_market_open_always_true():
    """BTC는 24/7 거래이므로 항상 True."""
    client = BinanceClient()
    assert client.is_market_open("BTCUSDT") is True


def test_binance_last_session_date_is_today_utc():
    """BTC는 현재 UTC 날짜를 마지막 세션으로 간주."""
    from datetime import datetime, timezone
    client = BinanceClient()
    expected = datetime.now(timezone.utc).date()
    assert client.last_session_date("BTCUSDT") == expected

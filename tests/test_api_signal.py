"""GET /v1/users/{chat_id}/signal 통합 테스트.

DB 필요(TEST_DATABASE_URL). Binance는 fake market client로 차단.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

import fakeredis
import pytest
from fastapi.testclient import TestClient

from sajucandle.api import create_app
from sajucandle.cache import BaziCache
from sajucandle.cached_engine import CachedSajuEngine
from sajucandle.market.router import MarketRouter
from sajucandle.market_data import Kline, MarketDataUnavailable
from sajucandle.score_service import ScoreService
from sajucandle.signal_service import SignalService

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL not set",
)


def _make_klines(n: int = 100) -> list[Kline]:
    out = []
    base_ts = datetime(2026, 2, 1, tzinfo=timezone.utc).timestamp()
    for i in range(n):
        c = 100.0 + i * 0.3
        out.append(
            Kline(
                open_time=datetime.fromtimestamp(base_ts + i * 86400, tz=timezone.utc),
                open=c - 0.1, high=c + 0.5, low=c - 0.5, close=c,
                volume=1000.0 if i < n - 1 else 2500.0,
            )
        )
    return out


class _FakeMarketClient:
    def __init__(self, klines=None, raise_exc=None):
        self.klines = klines if klines is not None else _make_klines()
        self.raise_exc = raise_exc
        self.call_count = 0

    def fetch_klines(self, symbol, interval="1d", limit=100):
        self.call_count += 1
        if self.raise_exc is not None:
            raise self.raise_exc
        return self.klines

    def is_market_open(self, symbol: str) -> bool:
        return True

    def last_session_date(self, symbol: str):
        from datetime import date as date_cls
        return date_cls(2026, 4, 16)


@pytest.fixture
def fake_market():
    return _FakeMarketClient()


@pytest.fixture
def redis():
    return fakeredis.FakeStrictRedis()


@pytest.fixture
def client(monkeypatch, fake_market, redis):
    monkeypatch.setenv("SAJUCANDLE_API_KEY", "test-key")
    monkeypatch.setenv("DATABASE_URL", os.environ["TEST_DATABASE_URL"])
    engine = CachedSajuEngine(cache=BaziCache(redis_client=redis))
    score_svc = ScoreService(engine=engine, redis_client=redis)
    router = MarketRouter(binance=fake_market, yfinance=fake_market)
    signal_svc = SignalService(
        score_service=score_svc,
        market_router=router,
        redis_client=redis,
    )
    app = create_app(engine=engine, signal_service=signal_svc)
    with TestClient(app) as c:
        yield c


HDR = {"X-SAJUCANDLE-KEY": "test-key"}


def _create(client, chat_id: int):
    client.put(
        f"/v1/users/{chat_id}",
        json={
            "birth_year": 1990, "birth_month": 3, "birth_day": 15,
            "birth_hour": 14, "birth_minute": 0,
            "asset_class_pref": "swing",
        },
        headers=HDR,
    )


def test_signal_invalid_ticker_returns_400(client):
    _create(client, 720001)
    try:
        r = client.get(
            "/v1/users/720001/signal?ticker=ETHUSDT", headers=HDR
        )
        assert r.status_code == 400
        assert "unsupported" in r.json()["detail"].lower()
    finally:
        client.delete("/v1/users/720001", headers=HDR)


def test_signal_user_not_found_returns_404(client):
    r = client.get("/v1/users/999998/signal", headers=HDR)
    assert r.status_code == 404


def test_signal_success_full_payload(client, fake_market):
    _create(client, 720002)
    try:
        r = client.get("/v1/users/720002/signal?date=2026-04-16", headers=HDR)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["chat_id"] == 720002
        assert data["ticker"] == "BTCUSDT"
        assert data["date"] == "2026-04-16"
        assert 0 <= data["composite_score"] <= 100
        assert data["signal_grade"] in {"강진입", "진입", "관망", "회피"}
        assert 0 <= data["saju"]["composite"] <= 100
        assert 0 <= data["chart"]["score"] <= 100
        assert data["chart"]["ma_trend"] in {"up", "down", "flat"}
        assert "RSI" in data["chart"]["reason"]
        assert data["price"]["current"] == fake_market.klines[-1].close
        assert isinstance(data["best_hours"], list)
    finally:
        client.delete("/v1/users/720002", headers=HDR)


def test_signal_market_unavailable_returns_502(monkeypatch, redis):
    """market_client이 MarketDataUnavailable 올리면 502."""
    monkeypatch.setenv("SAJUCANDLE_API_KEY", "test-key")
    monkeypatch.setenv("DATABASE_URL", os.environ["TEST_DATABASE_URL"])
    engine = CachedSajuEngine(cache=BaziCache(redis_client=redis))
    score_svc = ScoreService(engine=engine, redis_client=redis)
    broken_market = _FakeMarketClient(raise_exc=MarketDataUnavailable("boom"))
    router = MarketRouter(binance=broken_market, yfinance=broken_market)
    signal_svc = SignalService(
        score_service=score_svc,
        market_router=router,
        redis_client=redis,
    )
    app = create_app(engine=engine, signal_service=signal_svc)
    with TestClient(app) as c:
        c.put(
            "/v1/users/720003",
            json={
                "birth_year": 1990, "birth_month": 3, "birth_day": 15,
                "birth_hour": 14, "birth_minute": 0,
                "asset_class_pref": "swing",
            },
            headers=HDR,
        )
        try:
            r = c.get("/v1/users/720003/signal", headers=HDR)
            assert r.status_code == 502
        finally:
            c.delete("/v1/users/720003", headers=HDR)


def test_signal_cache_hit_skips_market(client, fake_market):
    _create(client, 720004)
    try:
        r1 = client.get("/v1/users/720004/signal?date=2026-04-16", headers=HDR)
        assert r1.status_code == 200
        first_calls = fake_market.call_count
        assert first_calls == 1

        r2 = client.get("/v1/users/720004/signal?date=2026-04-16", headers=HDR)
        assert r2.status_code == 200
        # 캐시 히트 → Binance 호출 재발생 없음
        assert fake_market.call_count == first_calls
        assert r1.json() == r2.json()
    finally:
        client.delete("/v1/users/720004", headers=HDR)


def test_signal_rejects_bad_date(client):
    _create(client, 720005)
    try:
        r = client.get("/v1/users/720005/signal?date=not-a-date", headers=HDR)
        assert r.status_code == 400
    finally:
        client.delete("/v1/users/720005", headers=HDR)


@pytest.fixture
def stub_yfinance():
    """yfinance.Ticker를 mock해서 일정한 AAPL DataFrame 반환."""
    from unittest.mock import patch, MagicMock
    import pandas as pd
    idx = pd.date_range(end="2026-04-16", periods=100, freq="B", tz="America/New_York")
    df = pd.DataFrame({
        "Open": [180.0 + i * 0.3 for i in range(100)],
        "High": [180.5 + i * 0.3 for i in range(100)],
        "Low": [179.5 + i * 0.3 for i in range(100)],
        "Close": [180.2 + i * 0.3 for i in range(100)],
        "Volume": [50_000_000] * 100,
    }, index=idx)
    fake = MagicMock()
    fake.history.return_value = df
    with patch("sajucandle.market.yfinance.yf.Ticker", return_value=fake):
        yield


def test_signal_endpoint_rejects_unsupported_ticker(client):
    """AMZN 같은 화이트리스트 외 심볼은 400."""
    _create(client, 720006)
    try:
        resp = client.get(
            "/v1/users/720006/signal",
            params={"ticker": "AMZN"},
            headers=HDR,
        )
        assert resp.status_code == 400
        assert "unsupported" in resp.json()["detail"].lower()
    finally:
        client.delete("/v1/users/720006", headers=HDR)


def test_signal_endpoint_accepts_aapl(monkeypatch, stub_yfinance, redis):
    """AAPL은 정상 처리되어 market_status.category='us_stock' 반환."""
    monkeypatch.setenv("SAJUCANDLE_API_KEY", "test-key")
    monkeypatch.setenv("DATABASE_URL", os.environ["TEST_DATABASE_URL"])
    engine = CachedSajuEngine(cache=BaziCache(redis_client=redis))
    score_svc = ScoreService(engine=engine, redis_client=redis)
    # Use a real YFinanceClient (stub_yfinance patches yf.Ticker) with fake binance for crypto
    from sajucandle.market.yfinance import YFinanceClient
    yf_client = YFinanceClient(redis_client=redis)
    router = MarketRouter(binance=_FakeMarketClient(), yfinance=yf_client)
    signal_svc = SignalService(
        score_service=score_svc,
        market_router=router,
        redis_client=redis,
    )
    app = create_app(engine=engine, signal_service=signal_svc)
    with TestClient(app) as c:
        c.put(
            "/v1/users/720007",
            json={
                "birth_year": 1990, "birth_month": 3, "birth_day": 15,
                "birth_hour": 14, "birth_minute": 0,
                "asset_class_pref": "swing",
            },
            headers=HDR,
        )
        try:
            resp = c.get(
                "/v1/users/720007/signal",
                params={"ticker": "AAPL", "date": "2026-04-16"},
                headers=HDR,
            )
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body["ticker"] == "AAPL"
            assert body["market_status"]["category"] == "us_stock"
        finally:
            c.delete("/v1/users/720007", headers=HDR)

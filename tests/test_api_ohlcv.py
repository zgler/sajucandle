"""api: /v1/admin/ohlcv 엔드포인트."""
from __future__ import annotations

import os
from unittest.mock import patch, MagicMock

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from sajucandle.api import create_app


@pytest.fixture
def api_key(monkeypatch):
    monkeypatch.setenv("SAJUCANDLE_API_KEY", "test-key")
    return "test-key"


@pytest.fixture
def client(api_key, monkeypatch):
    app = create_app()
    with TestClient(app) as c:
        yield c


HEADERS = {"X-SAJUCANDLE-KEY": "test-key"}


def test_ohlcv_requires_api_key(client):
    r = client.get("/v1/admin/ohlcv", params={"ticker": "BTCUSDT"})
    assert r.status_code == 401


def test_ohlcv_rejects_unsupported_ticker(client):
    r = client.get(
        "/v1/admin/ohlcv",
        params={"ticker": "AMZN"},
        headers=HEADERS,
    )
    assert r.status_code == 400
    assert "unsupported" in r.json()["detail"].lower()


def test_ohlcv_rejects_unsupported_interval(client):
    r = client.get(
        "/v1/admin/ohlcv",
        params={"ticker": "BTCUSDT", "interval": "15m"},
        headers=HEADERS,
    )
    assert r.status_code == 400


def test_ohlcv_rejects_bad_limit(client):
    r = client.get(
        "/v1/admin/ohlcv",
        params={"ticker": "BTCUSDT", "limit": "9999"},
        headers=HEADERS,
    )
    assert r.status_code == 400


def test_ohlcv_rejects_bad_since(client):
    r = client.get(
        "/v1/admin/ohlcv",
        params={"ticker": "BTCUSDT", "since": "not-a-date"},
        headers=HEADERS,
    )
    assert r.status_code == 400


def test_ohlcv_returns_klines_for_aapl(client):
    idx = pd.date_range(end="2026-04-19", periods=5, freq="1h",
                        tz="America/New_York")
    df = pd.DataFrame({
        "Open": [180.0] * 5,
        "High": [181.0] * 5,
        "Low": [179.0] * 5,
        "Close": [180.5] * 5,
        "Volume": [1_000_000] * 5,
    }, index=idx)
    fake_ticker = MagicMock()
    fake_ticker.history.return_value = df

    with patch("sajucandle.market.yfinance.yf.Ticker", return_value=fake_ticker):
        r = client.get(
            "/v1/admin/ohlcv",
            params={"ticker": "AAPL", "interval": "1h", "limit": "5"},
            headers=HEADERS,
        )
    assert r.status_code == 200
    body = r.json()
    assert body["ticker"] == "AAPL"
    assert body["interval"] == "1h"
    assert len(body["klines"]) == 5


def test_ohlcv_since_filter(client):
    from datetime import datetime, timezone, timedelta
    base = datetime(2026, 4, 19, 12, 0, tzinfo=timezone.utc)
    idx = pd.date_range(end=base, periods=10, freq="1h", tz="UTC")
    df = pd.DataFrame({
        "Open": [100.0] * 10, "High": [101.0] * 10,
        "Low": [99.0] * 10, "Close": [100.5] * 10,
        "Volume": [1000] * 10,
    }, index=idx)
    fake_ticker = MagicMock()
    fake_ticker.history.return_value = df

    since = (base - timedelta(hours=4)).isoformat()
    with patch("sajucandle.market.yfinance.yf.Ticker", return_value=fake_ticker):
        r = client.get(
            "/v1/admin/ohlcv",
            params={"ticker": "AAPL", "interval": "1h",
                    "since": since, "limit": "20"},
            headers=HEADERS,
        )
    assert r.status_code == 200
    body = r.json()
    assert len(body["klines"]) <= 5

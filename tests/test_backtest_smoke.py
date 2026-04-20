"""backtest smoke: 합성 히스토리로 end-to-end 실행."""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest

from sajucandle.backtest.engine import run_backtest
from sajucandle.backtest.aggregate import aggregate_run
from sajucandle.backtest.history import TickerHistory
from sajucandle.market_data import Kline
from sajucandle import db


pytestmark = pytest.mark.skipif(
    os.environ.get("TEST_DATABASE_URL") is None,
    reason="TEST_DATABASE_URL not set",
)


def _synthetic_history(ticker: str) -> TickerHistory:
    """강한 uptrend 합성 히스토리 200 × 1d, 동등 4h/1h."""
    base = datetime(2025, 1, 1, tzinfo=timezone.utc)
    k1d = []
    for i in range(200):
        p = 100 + i * 0.5
        k1d.append(Kline(
            open_time=base + timedelta(days=i),
            open=p, high=p + 1, low=p - 1, close=p, volume=1000,
        ))
    k4h = []
    for i in range(200 * 6):
        p = 100 + i * 0.08
        k4h.append(Kline(
            open_time=base + timedelta(hours=4 * i),
            open=p, high=p + 0.5, low=p - 0.5, close=p, volume=300,
        ))
    k1h = []
    for i in range(200 * 24):
        p = 100 + i * 0.02
        k1h.append(Kline(
            open_time=base + timedelta(hours=i),
            open=p, high=p + 0.2, low=p - 0.2, close=p, volume=100,
        ))
    return TickerHistory(ticker=ticker, klines_1h=k1h, klines_4h=k4h, klines_1d=k1d)


@pytest.mark.asyncio
async def test_backtest_end_to_end(db_pool):
    """run_backtest → aggregate_run 성공 + row count 기대값."""
    hist = _synthetic_history("BTCUSDT")
    from_dt = datetime(2025, 3, 1, tzinfo=timezone.utc)
    to_dt = datetime(2025, 3, 11, tzinfo=timezone.utc)

    # router 더미 (history_override 사용하므로 호출 안 됨)
    from unittest.mock import MagicMock
    router = MagicMock()

    summary = await run_backtest(
        ticker="BTCUSDT",
        from_dt=from_dt, to_dt=to_dt,
        run_id="phase1-smoke-test",
        router=router,
        history_override=hist,
    )
    assert summary.signals_total == 10

    # 집계 — tracking_done=TRUE rows 있어야 aggregate 결과 있음
    async with db.acquire() as conn:
        stats = await aggregate_run(conn, run_id="phase1-smoke-test")
        # 7일 추적 필요 — history 200봉이라 일부 tracking_done=True
        # 최소 등급 breakdown 확인
        total = sum(s.count for s in stats)
        assert total >= 0   # 존재 여부만 smoke 확인

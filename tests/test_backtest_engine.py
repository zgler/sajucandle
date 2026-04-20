"""backtest.engine: run_backtest 통합."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock

import pytest

from sajucandle.backtest.engine import run_backtest, BacktestSummary
from sajucandle.backtest.history import TickerHistory
from sajucandle.market_data import Kline


def _k(t: datetime, price: float) -> Kline:
    return Kline(open_time=t, open=price, high=price + 1, low=price - 1,
                 close=price, volume=100.0)


def _mock_history(ticker: str, from_dt: datetime, to_dt: datetime) -> TickerHistory:
    # 합성 히스토리: 매 1h마다 가격 상승 (강한 uptrend)
    n_hours = int((to_dt - from_dt).total_seconds() / 3600)
    # 1h 전체
    k1h = [_k(from_dt + timedelta(hours=i), 100 + i * 0.1) for i in range(n_hours + 100)]
    # 4h 집계
    k4h = [_k(from_dt + timedelta(hours=4 * i), 100 + i * 0.4) for i in range((n_hours + 100) // 4)]
    # 1d 집계
    k1d = [_k(from_dt + timedelta(days=i), 100 + i * 2.4) for i in range((n_hours + 100) // 24 + 1)]
    return TickerHistory(ticker=ticker, klines_1h=k1h, klines_4h=k4h, klines_1d=k1d)


@pytest.mark.asyncio
async def test_run_backtest_runs_daily_signals():
    from_dt = datetime(2026, 1, 1, tzinfo=timezone.utc)
    to_dt = datetime(2026, 1, 11, tzinfo=timezone.utc)   # 10일
    hist = _mock_history("BTCUSDT", from_dt, to_dt)

    # load_history를 직접 mock 주입
    router = MagicMock()
    fake_provider = MagicMock()
    fake_provider.fetch_klines = MagicMock()
    router.get_provider = MagicMock(return_value=fake_provider)

    # insert 수집
    inserted: list[dict] = []
    async def fake_insert(**kwargs):
        inserted.append(kwargs)
        return len(inserted)

    summary = await run_backtest(
        ticker="BTCUSDT",
        from_dt=from_dt,
        to_dt=to_dt,
        run_id="phase1-test-run",
        router=router,
        saju_score_fn=lambda d, ac: 50,
        insert_log_fn=fake_insert,
        history_override=hist,   # test injection
    )
    assert isinstance(summary, BacktestSummary)
    assert summary.run_id == "phase1-test-run"
    assert summary.ticker == "BTCUSDT"
    # 10일 동안 1일 1회
    assert summary.signals_total == 10
    assert len(inserted) == 10
    # 전부 run_id 전파
    for row in inserted:
        assert row["run_id"] == "phase1-test-run"
        assert row["source"] == "backtest"


@pytest.mark.asyncio
async def test_run_backtest_grades_aggregated():
    from_dt = datetime(2026, 1, 1, tzinfo=timezone.utc)
    to_dt = datetime(2026, 1, 4, tzinfo=timezone.utc)
    hist = _mock_history("BTCUSDT", from_dt, to_dt)

    inserted: list[dict] = []
    async def fake_insert(**kwargs):
        inserted.append(kwargs)
        return len(inserted)

    summary = await run_backtest(
        ticker="BTCUSDT",
        from_dt=from_dt, to_dt=to_dt,
        run_id="phase1-test-grades",
        router=MagicMock(),
        insert_log_fn=fake_insert,
        history_override=hist,
    )
    # summary.signals_by_grade 합 == signals_total
    assert sum(summary.signals_by_grade.values()) == summary.signals_total

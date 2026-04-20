from __future__ import annotations

from datetime import datetime, timezone, timedelta

from sajucandle.backtest.history import TickerHistory
from sajucandle.backtest.slicer import HistoryWindow
from sajucandle.market_data import Kline


def _bars(start: datetime, interval_hours: float, count: int, base_price: float = 100.0) -> list[Kline]:
    out = []
    dt = timedelta(hours=interval_hours)
    for i in range(count):
        p = base_price + i * 0.5
        out.append(Kline(
            open_time=start + dt * i,
            open=p, high=p + 1, low=p - 1, close=p, volume=100.0,
        ))
    return out


def _make_window(t0: datetime) -> HistoryWindow:
    hist = TickerHistory(
        ticker="BTCUSDT",
        klines_1h=_bars(t0 - timedelta(days=10), 1, 24 * 10),  # 10일 (plan typo: 20 → 10)
        klines_4h=_bars(t0 - timedelta(days=30), 4, 6 * 30),
        klines_1d=_bars(t0 - timedelta(days=60), 24, 60),
    )
    return HistoryWindow(history=hist)


def test_slice_at_returns_bars_before_t_only():
    t0 = datetime(2026, 4, 20, 0, 0, tzinfo=timezone.utc)
    window = _make_window(t0)
    t = t0   # 지금
    k1h, k4h, k1d = window.slice_at(t)
    # 모든 봉이 open_time + interval <= t
    assert all(k.open_time + timedelta(hours=1) <= t for k in k1h)
    assert all(k.open_time + timedelta(hours=4) <= t for k in k4h)
    assert all(k.open_time + timedelta(days=1) <= t for k in k1d)


def test_slice_at_deterministic():
    t0 = datetime(2026, 4, 20, 0, 0, tzinfo=timezone.utc)
    window = _make_window(t0)
    r1 = window.slice_at(t0)
    r2 = window.slice_at(t0)
    assert len(r1[0]) == len(r2[0])
    assert len(r1[1]) == len(r2[1])
    assert len(r1[2]) == len(r2[2])


def test_slice_at_past_t_yields_fewer_bars():
    t0 = datetime(2026, 4, 20, 0, 0, tzinfo=timezone.utc)
    window = _make_window(t0)
    k1h_now, _, _ = window.slice_at(t0)
    k1h_past, _, _ = window.slice_at(t0 - timedelta(days=5))
    assert len(k1h_past) < len(k1h_now)


def test_post_bars_1h_returns_bars_after_t():
    t0 = datetime(2026, 4, 20, 0, 0, tzinfo=timezone.utc)
    window = _make_window(t0)
    # t는 히스토리 중간 시점
    t = t0 - timedelta(days=5)
    post = window.post_bars_1h(t, hours=24)
    # 전부 t 이후
    assert all(k.open_time >= t for k in post)
    # ~24개
    assert 20 <= len(post) <= 26


def test_post_bars_1h_beyond_history_returns_partial():
    t0 = datetime(2026, 4, 20, 0, 0, tzinfo=timezone.utc)
    window = _make_window(t0)
    t = t0 - timedelta(hours=3)
    post = window.post_bars_1h(t, hours=168)   # 7일 요청
    # history는 t0까지만 있으므로 3h치만
    assert len(post) <= 5

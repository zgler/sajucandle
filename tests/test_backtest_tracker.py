"""backtest.tracker: MFE/MAE 순수 함수."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta

import pytest

from sajucandle.backtest.tracker import MfeMae, compute_mfe_mae  # noqa: F401
from sajucandle.market_data import Kline


def _bar(hours_after: float, high: float, low: float, close: float,
         base_t: datetime) -> Kline:
    return Kline(
        open_time=base_t + timedelta(hours=hours_after),
        open=(high + low) / 2, high=high, low=low, close=close, volume=100.0,
    )


def test_compute_mfe_mae_basic():
    """entry=100, 이후 high=110, low=95 → MFE=+10%, MAE=-5%."""
    t0 = datetime(2026, 4, 20, 0, 0, tzinfo=timezone.utc)
    post = [
        _bar(0.5, high=102, low=99, close=101, base_t=t0),
        _bar(1.5, high=110, low=101, close=108, base_t=t0),
        _bar(2.5, high=107, low=95, close=96, base_t=t0),
    ]
    r = compute_mfe_mae(entry_price=100.0, post_bars_1h=post, sent_at=t0)
    assert r is not None
    assert r.mfe_pct == pytest.approx(10.0, abs=0.01)
    assert r.mae_pct == pytest.approx(-5.0, abs=0.01)


def test_compute_mfe_mae_close_24h_7d():
    """sent_at 이후 24h 지점 close, 7d 지점 close 반환."""
    t0 = datetime(2026, 4, 20, 0, 0, tzinfo=timezone.utc)
    post = []
    # 1시간마다 1 bar, 200h (>7d)
    for i in range(1, 200):
        post.append(_bar(i, high=100 + i, low=100, close=100 + i, base_t=t0))
    r = compute_mfe_mae(entry_price=100.0, post_bars_1h=post, sent_at=t0)
    assert r.close_24h is not None
    assert r.close_24h > 100  # 24h 시점 상승 시가
    assert r.close_7d is not None


def test_compute_mfe_mae_empty_returns_none():
    t0 = datetime(2026, 4, 20, 0, 0, tzinfo=timezone.utc)
    assert compute_mfe_mae(entry_price=100.0, post_bars_1h=[], sent_at=t0) is None


def test_compute_mfe_mae_zero_entry_returns_none():
    t0 = datetime(2026, 4, 20, 0, 0, tzinfo=timezone.utc)
    post = [_bar(1, 100, 100, 100, t0)]
    assert compute_mfe_mae(entry_price=0.0, post_bars_1h=post, sent_at=t0) is None

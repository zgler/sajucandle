"""analysis.timeframe: 단일 TF 추세 방향 판정 (close vs EMA50 + 기울기)."""
from __future__ import annotations

from datetime import datetime, timezone

from sajucandle.analysis.timeframe import TrendDirection, trend_direction
from sajucandle.market_data import Kline


def _klines(closes: list[float]) -> list[Kline]:
    out = []
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for i, c in enumerate(closes):
        out.append(Kline(
            open_time=base.replace(day=(i % 28) + 1),
            open=c, high=c + 0.5, low=c - 0.5, close=c, volume=1000.0,
        ))
    return out


def test_trend_up_when_close_above_ema_and_ema_rising():
    closes = [100 + i * 0.5 for i in range(60)]
    assert trend_direction(_klines(closes)) == TrendDirection.UP


def test_trend_down_when_close_below_ema_and_ema_falling():
    closes = [100 - i * 0.5 for i in range(60)]
    assert trend_direction(_klines(closes)) == TrendDirection.DOWN


def test_trend_flat_when_sideways():
    closes = [100.0] * 60
    assert trend_direction(_klines(closes)) == TrendDirection.FLAT


def test_trend_flat_when_close_above_but_ema_falling():
    closes = [100 + i * 0.5 for i in range(50)] + [125 - i * 1.0 for i in range(10)]
    r = trend_direction(_klines(closes))
    assert r in (TrendDirection.DOWN, TrendDirection.FLAT)


def test_trend_too_few_bars_returns_flat():
    closes = [100.0] * 20
    assert trend_direction(_klines(closes)) == TrendDirection.FLAT

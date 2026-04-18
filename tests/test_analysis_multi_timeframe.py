"""analysis.multi_timeframe: 3개 TF 정렬 판정."""
from __future__ import annotations

from datetime import datetime, timezone

from sajucandle.analysis.multi_timeframe import Alignment, compute_alignment
from sajucandle.analysis.timeframe import TrendDirection
from sajucandle.market_data import Kline


def _klines(closes: list[float]) -> list[Kline]:
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [
        Kline(open_time=base, open=c, high=c + 0.5, low=c - 0.5,
              close=c, volume=1000.0)
        for c in closes
    ]


def test_aligned_bullish_all_up():
    up_series = [100 + i * 0.5 for i in range(60)]
    r = compute_alignment(_klines(up_series), _klines(up_series), _klines(up_series))
    assert r.tf_1h == TrendDirection.UP
    assert r.tf_4h == TrendDirection.UP
    assert r.tf_1d == TrendDirection.UP
    assert r.aligned is True
    assert r.bias == "bullish"
    assert r.score >= 85


def test_aligned_bearish_all_down():
    dn_series = [100 - i * 0.5 for i in range(60)]
    r = compute_alignment(_klines(dn_series), _klines(dn_series), _klines(dn_series))
    assert r.aligned is True
    assert r.bias == "bearish"
    assert r.score <= 15


def test_mixed_1h_up_others_flat():
    up_series = [100 + i * 0.5 for i in range(60)]
    flat_series = [100.0] * 60
    r = compute_alignment(_klines(up_series), _klines(flat_series), _klines(flat_series))
    assert r.aligned is False
    assert r.bias in ("bullish", "mixed")


def test_mixed_conflicting():
    up_series = [100 + i * 0.5 for i in range(60)]
    dn_series = [100 - i * 0.5 for i in range(60)]
    r = compute_alignment(_klines(up_series), _klines(dn_series), _klines(dn_series))
    assert r.aligned is False
    assert r.bias in ("mixed", "bearish")


def test_score_range_0_to_100():
    flat = [100.0] * 60
    r = compute_alignment(_klines(flat), _klines(flat), _klines(flat))
    assert 0 <= r.score <= 100

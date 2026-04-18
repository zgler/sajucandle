"""analysis.swing: Fractals + ATR 필터 기반 swing high/low 감지."""
from __future__ import annotations

from datetime import datetime, timezone


from sajucandle.analysis.swing import SwingPoint, detect_swings
from sajucandle.market_data import Kline


def _mk_klines(prices: list[tuple[float, float, float, float]]) -> list[Kline]:
    """Each tuple = (open, high, low, close). volume=1000."""
    out = []
    base_ts = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for i, (o, h, lo, c) in enumerate(prices):
        out.append(Kline(
            open_time=base_ts.replace(day=1 + i % 28),
            open=o, high=h, low=lo, close=c, volume=1000.0,
        ))
    return out


def test_detect_swings_empty():
    assert detect_swings([]) == []


def test_detect_swings_too_few_bars():
    """window=5면 최소 11봉 필요 (5+1+5). 부족하면 []."""
    klines = _mk_klines([(100, 101, 99, 100)] * 5)
    assert detect_swings(klines, fractal_window=5, atr_multiplier=0.0) == []


def test_detect_swings_single_clear_high():
    prices = [
        (100, 101, 99, 100),
        (100, 102, 99, 101),
        (101, 103, 100, 102),
        (102, 104, 101, 103),
        (103, 105, 102, 104),
        (104, 120, 103, 110),  # 5 ← swing high
        (103, 105, 102, 104),
        (102, 104, 101, 103),
        (101, 103, 100, 102),
        (100, 102, 99, 101),
        (100, 101, 99, 100),
    ]
    klines = _mk_klines(prices)
    swings = detect_swings(klines, fractal_window=5, atr_multiplier=0.0)
    highs = [s for s in swings if s.kind == "high"]
    assert len(highs) == 1
    assert highs[0].index == 5
    assert highs[0].price == 120.0


def test_detect_swings_single_clear_low():
    prices = [
        (100, 101, 99, 100),
        (99, 100, 98, 99),
        (98, 99, 97, 98),
        (97, 98, 96, 97),
        (96, 97, 95, 96),
        (95, 96, 80, 85),  # 5 ← swing low
        (96, 97, 95, 96),
        (97, 98, 96, 97),
        (98, 99, 97, 98),
        (99, 100, 98, 99),
        (100, 101, 99, 100),
    ]
    klines = _mk_klines(prices)
    swings = detect_swings(klines, fractal_window=5, atr_multiplier=0.0)
    lows = [s for s in swings if s.kind == "low"]
    assert len(lows) == 1
    assert lows[0].index == 5
    assert lows[0].price == 80.0


def test_detect_swings_atr_filter_removes_noise():
    """큰 스윙만 남아야 함."""
    prices = [(100, 101, 99, 100)] * 5 + [
        (100, 120, 99, 110),   # 5: 큰 swing high
    ] + [(100, 101, 99, 100)] * 5 + [
        (100, 101.5, 99.5, 100),  # 11: 아주 작은 변동
    ] + [(100, 101, 99, 100)] * 5
    klines = _mk_klines(prices)
    swings = detect_swings(klines, fractal_window=5, atr_multiplier=1.5, atr_period=14)
    assert all(s.price == 120.0 or s.price == 99.0 for s in swings if s.kind == "high")


def test_swing_point_is_dataclass():
    from dataclasses import is_dataclass
    assert is_dataclass(SwingPoint)
    p = SwingPoint(index=5, timestamp=datetime.now(timezone.utc),
                   price=100.0, kind="high")
    assert p.index == 5
    assert p.kind == "high"

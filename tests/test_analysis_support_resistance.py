"""analysis.support_resistance: swing + volume → SRLevel 융합."""
from __future__ import annotations

from datetime import datetime, timezone

from sajucandle.analysis.support_resistance import (
    LevelKind,
    SRLevel,
    identify_sr_levels,
)
from sajucandle.analysis.swing import SwingPoint
from sajucandle.market_data import Kline


def _sp(kind: str, price: float, idx: int = 0) -> SwingPoint:
    return SwingPoint(
        index=idx, timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
        price=price, kind=kind,  # type: ignore[arg-type]
    )


def _kline(high: float, low: float, vol: float = 1000) -> Kline:
    mid = (high + low) / 2
    return Kline(
        open_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
        open=mid, high=high, low=low, close=mid, volume=vol,
    )


def test_empty_inputs_returns_empty():
    r = identify_sr_levels(klines_1d=[], swings=[], current_price=100.0)
    assert r == []


def test_swing_high_above_current_is_resistance():
    klines = [_kline(110, 90)] * 50
    swings = [_sp("high", 108), _sp("low", 92)]
    r = identify_sr_levels(klines, swings, current_price=100.0)
    resistances = [x for x in r if x.kind == LevelKind.RESISTANCE]
    supports = [x for x in r if x.kind == LevelKind.SUPPORT]
    assert any(abs(x.price - 108) < 1 for x in resistances)
    assert any(abs(x.price - 92) < 1 for x in supports)


def test_swing_and_volume_overlap_strength_high():
    """swing + volume 같은 가격대 → strength=high."""
    klines = [_kline(110, 100, 10000)] * 30   # 105 근처 고볼륨
    swings = [_sp("high", 105)]
    r = identify_sr_levels(klines, swings, current_price=95.0,
                            max_resistances=5)
    near_105 = [x for x in r if abs(x.price - 105) < 6]
    assert any(x.strength == "high" for x in near_105)


def test_volume_only_level_medium_if_top_bucket():
    klines = [_kline(120, 110, 50000)] * 20 + [_kline(100, 95, 1000)] * 20
    swings = []
    r = identify_sr_levels(klines, swings, current_price=105.0)
    volume_based = [x for x in r if "volume_node" in x.sources]
    assert len(volume_based) > 0
    assert any(x.strength in ("medium", "high") for x in volume_based)


def test_levels_limited_by_max_count():
    klines = [_kline(100 + i, 90 + i, 1000) for i in range(50)]
    swings = [_sp("high", 150), _sp("high", 145), _sp("high", 140),
              _sp("high", 135), _sp("low", 80), _sp("low", 75)]
    r = identify_sr_levels(klines, swings, current_price=120,
                            max_supports=2, max_resistances=2)
    assert len([x for x in r if x.kind == LevelKind.RESISTANCE]) <= 2
    assert len([x for x in r if x.kind == LevelKind.SUPPORT]) <= 2


def test_merge_tolerance_combines_close_levels():
    klines = [_kline(110, 90)] * 30
    swings = [_sp("high", 108), _sp("high", 108.5)]
    r = identify_sr_levels(klines, swings, current_price=100.0,
                            merge_tolerance_pct=1.0)
    resistances = [x for x in r if x.kind == LevelKind.RESISTANCE]
    near_108 = [x for x in resistances if 107 <= x.price <= 109]
    assert len(near_108) == 1


def test_sr_level_is_dataclass():
    from dataclasses import is_dataclass
    assert is_dataclass(SRLevel)
    level = SRLevel(price=100.0, kind=LevelKind.SUPPORT,
                    strength="medium", sources=["swing_low"])
    assert level.price == 100.0

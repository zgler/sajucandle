"""analysis.composite: AnalysisResult 조립 + composite_score."""
from __future__ import annotations

from datetime import datetime, timezone

from sajucandle.analysis.composite import AnalysisResult, analyze
from sajucandle.analysis.timeframe import TrendDirection
from sajucandle.market_data import Kline


def _klines(closes: list[float], volumes: list[float] | None = None) -> list[Kline]:
    if volumes is None:
        volumes = [1000.0] * len(closes)
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [
        Kline(
            open_time=base.replace(day=(i % 28) + 1),
            open=c, high=c + 0.5, low=c - 0.5, close=c, volume=v,
        )
        for i, (c, v) in enumerate(zip(closes, volumes))
    ]


def test_analyze_strong_uptrend_aligned():
    up_1h = [100 + i * 0.2 for i in range(200)]
    up_4h = [100 + i * 0.3 for i in range(100)]
    up_1d = [100 + i * 0.5 for i in range(100)]
    r = analyze(_klines(up_1h), _klines(up_4h), _klines(up_1d))
    assert r.composite_score >= 65
    assert r.alignment.aligned is True
    assert r.alignment.bias == "bullish"


def test_analyze_strong_downtrend_aligned():
    """Phase 2: composite_score = max(long, short) — 하락장은 short_score가 크므로
    composite_score는 크게 나옴. 대신 direction/long_score로 하락 판정."""
    dn_1h = [100 - i * 0.2 for i in range(200)]
    dn_4h = [100 - i * 0.3 for i in range(100)]
    dn_1d = [100 - i * 0.5 for i in range(100)]
    r = analyze(_klines(dn_1h), _klines(dn_4h), _klines(dn_1d))
    assert r.alignment.bias == "bearish"
    assert r.long_score <= 40     # 롱 관점 점수 낮음
    assert r.short_score >= 60    # 숏 관점 점수 높음


def test_analyze_returns_fields_populated():
    flat = [100.0] * 100
    r = analyze(_klines(flat), _klines(flat), _klines(flat))
    assert isinstance(r, AnalysisResult)
    assert 0 <= r.composite_score <= 100
    # Enum 멤버들의 value로 체크 (Enum 인스턴스 자체)
    from sajucandle.analysis.structure import MarketStructure as MS
    assert r.structure.state in list(MS)
    assert r.alignment.tf_1h in (TrendDirection.UP, TrendDirection.DOWN,
                                   TrendDirection.FLAT)
    assert isinstance(r.reason, str)
    assert len(r.reason) > 0


def test_analyze_reason_contains_tf_markers():
    up = [100 + i * 0.3 for i in range(100)]
    r = analyze(_klines(up), _klines(up), _klines(up))
    assert "1d" in r.reason or "1h" in r.reason


def test_analyze_score_clamped():
    flat = [100.0] * 100
    r = analyze(_klines(flat), _klines(flat), _klines(flat))
    assert 0 <= r.composite_score <= 100


def test_analyze_composite_weighting_strong_up():
    strong_up = [100 * (1.005 ** i) for i in range(100)]
    r = analyze(_klines(strong_up), _klines(strong_up), _klines(strong_up))
    assert r.composite_score >= 70


# ─────────────────────────────────────────────
# Week 9: sr_levels + atr_1d 필드
# ─────────────────────────────────────────────


def test_analyze_returns_sr_levels_and_atr():
    from datetime import datetime, timezone
    from sajucandle.analysis.composite import analyze
    from sajucandle.market_data import Kline

    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    up = [
        Kline(
            open_time=base.replace(day=(i % 28) + 1),
            open=100 + i * 0.3,
            high=100 + i * 0.3 + 0.5,
            low=100 + i * 0.3 - 0.5,
            close=100 + i * 0.3,
            volume=1000.0,
        )
        for i in range(100)
    ]
    r = analyze(up, up, up)
    assert hasattr(r, "sr_levels")
    assert isinstance(r.sr_levels, list)
    assert hasattr(r, "atr_1d")
    assert r.atr_1d > 0


# ─────────────────────────────────────────────
# Phase 2: direction + long_score/short_score
# ─────────────────────────────────────────────


def test_analyze_strong_uptrend_direction_long():
    up_1h = [100 + i * 0.2 for i in range(200)]
    up_4h = [100 + i * 0.3 for i in range(100)]
    up_1d = [100 + i * 0.5 for i in range(100)]
    r = analyze(_klines(up_1h), _klines(up_4h), _klines(up_1d))
    assert r.direction == "LONG"
    assert r.long_score > r.short_score
    assert r.composite_score == max(r.long_score, r.short_score)


def test_analyze_strong_downtrend_direction_short():
    dn_1h = [100 - i * 0.2 for i in range(200)]
    dn_4h = [100 - i * 0.3 for i in range(100)]
    dn_1d = [100 - i * 0.5 for i in range(100)]
    r = analyze(_klines(dn_1h), _klines(dn_4h), _klines(dn_1d))
    assert r.direction == "SHORT"
    assert r.short_score > r.long_score
    assert r.composite_score == max(r.long_score, r.short_score)


def test_analyze_flat_direction_neutral():
    """RANGE (flat) → direction 항상 NEUTRAL."""
    flat = [100.0] * 100
    r = analyze(_klines(flat), _klines(flat), _klines(flat))
    from sajucandle.analysis.structure import MarketStructure
    assert r.structure.state == MarketStructure.RANGE
    assert r.direction == "NEUTRAL"


def test_analyze_composite_equals_max_long_short():
    """composite_score == max(long_score, short_score) invariant."""
    cases = [
        [100 + i * 0.3 for i in range(100)],  # up
        [100 - i * 0.3 for i in range(100)],  # down
        [100.0] * 100,                         # flat
    ]
    for series in cases:
        r = analyze(_klines(series), _klines(series), _klines(series))
        assert r.composite_score == max(r.long_score, r.short_score)


def test_analyze_direction_margin():
    """|long - short| < 10 → NEUTRAL (δ=10 tie-break)."""
    # 약한 상승 → RANGE로 판정되거나 long/short 차이 작아서 NEUTRAL 가능성
    flat = [100.0] * 100
    r = analyze(_klines(flat), _klines(flat), _klines(flat))
    # 3 FLAT → 각 스코어 비슷 → NEUTRAL
    assert r.direction == "NEUTRAL"
    assert abs(r.long_score - r.short_score) < 10

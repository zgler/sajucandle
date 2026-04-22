"""analysis.structure: swing points → MarketStructure."""
from __future__ import annotations

from datetime import datetime, timezone

from sajucandle.analysis.structure import (
    MarketStructure,
    classify_structure,
)
from sajucandle.analysis.swing import SwingPoint


def _sp(kind: str, price: float, idx: int) -> SwingPoint:
    return SwingPoint(
        index=idx, timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
        price=price, kind=kind,  # type: ignore[arg-type]
    )


def test_classify_empty_returns_range():
    r = classify_structure([])
    assert r.state == MarketStructure.RANGE
    assert r.last_high is None
    assert r.last_low is None
    assert 40 <= r.score <= 60


def test_classify_uptrend_hh_hl():
    """HH-HL 연속: 상승추세."""
    swings = [
        _sp("low", 100, 0),
        _sp("high", 110, 5),
        _sp("low", 105, 10),
        _sp("high", 120, 15),
        _sp("low", 112, 20),
        _sp("high", 130, 25),
    ]
    r = classify_structure(swings)
    assert r.state == MarketStructure.UPTREND
    assert r.last_high.price == 130
    assert r.last_low.price == 112
    assert r.score >= 65


def test_classify_downtrend_lh_ll():
    """LH-LL 연속: 하락추세."""
    swings = [
        _sp("high", 130, 0),
        _sp("low", 120, 5),
        _sp("high", 125, 10),
        _sp("low", 115, 15),
        _sp("high", 120, 20),
        _sp("low", 110, 25),
    ]
    r = classify_structure(swings)
    assert r.state == MarketStructure.DOWNTREND
    assert r.last_high.price == 120
    assert r.last_low.price == 110
    assert r.score <= 30


def test_classify_range_mixed():
    """HH 후 LL 나와 정렬 없음: 횡보."""
    swings = [
        _sp("low", 100, 0),
        _sp("high", 120, 5),
        _sp("low", 98, 10),
        _sp("high", 118, 15),
    ]
    r = classify_structure(swings)
    assert r.state == MarketStructure.RANGE


def test_classify_breakout_from_range():
    """최근 high가 범위 상단 돌파."""
    swings = [
        _sp("low", 100, 0),
        _sp("high", 110, 5),
        _sp("low", 102, 10),
        _sp("high", 109, 15),
        _sp("low", 103, 20),
        _sp("high", 120, 25),
    ]
    r = classify_structure(swings)
    assert r.state == MarketStructure.BREAKOUT
    assert r.score >= 70


def test_classify_breakdown_from_uptrend():
    """uptrend 중 최근 low가 직전 HL 하향 이탈."""
    swings = [
        _sp("low", 100, 0),
        _sp("high", 110, 5),
        _sp("low", 105, 10),
        _sp("high", 120, 15),
        _sp("low", 100, 20),  # HL 깨짐 (105 밑)
    ]
    r = classify_structure(swings)
    assert r.state == MarketStructure.BREAKDOWN
    assert r.score <= 40


# Phase 2: long_score / short_score 대칭

def test_symmetric_scores_uptrend():
    swings = [
        _sp("low", 100, 0), _sp("high", 110, 5),
        _sp("low", 105, 10), _sp("high", 120, 15),
        _sp("low", 112, 20), _sp("high", 130, 25),
    ]
    r = classify_structure(swings)
    assert r.state == MarketStructure.UPTREND
    assert r.long_score == 70
    assert r.short_score == 20


def test_symmetric_scores_downtrend():
    swings = [
        _sp("high", 130, 0), _sp("low", 120, 5),
        _sp("high", 125, 10), _sp("low", 115, 15),
        _sp("high", 120, 20), _sp("low", 110, 25),
    ]
    r = classify_structure(swings)
    assert r.state == MarketStructure.DOWNTREND
    assert r.long_score == 20
    assert r.short_score == 80


def test_symmetric_scores_range_neutral():
    """빈 swings → RANGE, long/short 모두 50."""
    r = classify_structure([])
    assert r.state == MarketStructure.RANGE
    assert r.long_score == 50
    assert r.short_score == 50


def test_symmetric_scores_breakout():
    swings = [
        _sp("low", 100, 0), _sp("high", 110, 5),
        _sp("low", 102, 10), _sp("high", 109, 15),
        _sp("low", 103, 20), _sp("high", 120, 25),
    ]
    r = classify_structure(swings)
    assert r.state == MarketStructure.BREAKOUT
    assert r.long_score == 80
    assert r.short_score == 15


def test_symmetric_scores_breakdown():
    swings = [
        _sp("low", 100, 0), _sp("high", 110, 5),
        _sp("low", 105, 10), _sp("high", 120, 15),
        _sp("low", 100, 20),
    ]
    r = classify_structure(swings)
    assert r.state == MarketStructure.BREAKDOWN
    assert r.long_score == 30
    assert r.short_score == 70


def test_legacy_score_equals_long_score():
    """score 필드는 항상 long_score와 동일 (하위호환 invariant)."""
    cases = [
        [],  # RANGE (empty)
        [_sp("low", 100, 0), _sp("high", 110, 5),
         _sp("low", 105, 10), _sp("high", 120, 15),
         _sp("low", 112, 20), _sp("high", 130, 25)],  # UPTREND
        [_sp("high", 130, 0), _sp("low", 120, 5),
         _sp("high", 125, 10), _sp("low", 115, 15),
         _sp("high", 120, 20), _sp("low", 110, 25)],  # DOWNTREND
    ]
    for swings in cases:
        r = classify_structure(swings)
        assert r.score == r.long_score

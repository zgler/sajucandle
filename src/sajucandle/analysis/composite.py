"""Analysis 조합기: swing → structure + multi TF → composite_score.

Phase 2: long_score/short_score 양방향 산출 + direction 결정.

Weights (각 방향):
  *_score = 0.45 * structure.*_score
          + 0.35 * alignment.*_score
          + 0.10 * rsi_*_score  (1h RSI)
          + 0.10 * volume_score (1d volume_ratio, 방향 중립)

composite_score = max(long_score, short_score)  (하위호환)

direction:
  - RANGE 구조 → 항상 NEUTRAL
  - |long - short| < δ(=10) → NEUTRAL
  - long > short + δ → LONG
  - short > long + δ → SHORT
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from sajucandle.analysis.multi_timeframe import Alignment, compute_alignment
from sajucandle.analysis.structure import (
    MarketStructure,
    StructureAnalysis,
    classify_structure,
)
from sajucandle.analysis.support_resistance import SRLevel, identify_sr_levels
from sajucandle.analysis.swing import _atr, detect_swings
from sajucandle.analysis.timeframe import TrendDirection
from sajucandle.market_data import Kline
from sajucandle.tech_analysis import (
    _rsi_score,
    _rsi_score_short,
    _volume_score,
    rsi,
    volume_ratio,
)

SignalDirection = Literal["LONG", "SHORT", "NEUTRAL"]

_DIRECTION_MARGIN = 10  # δ: |long - short| < δ → NEUTRAL

_TF_ARROW = {
    TrendDirection.UP: "↑",
    TrendDirection.DOWN: "↓",
    TrendDirection.FLAT: "→",
}


@dataclass
class AnalysisResult:
    structure: StructureAnalysis
    alignment: Alignment
    rsi_1h: float
    volume_ratio_1d: float
    composite_score: int
    reason: str
    # Week 9
    sr_levels: list[SRLevel] = field(default_factory=list)
    atr_1d: float = 0.0
    # Phase 2
    long_score: int = 0
    short_score: int = 0
    direction: SignalDirection = "NEUTRAL"


def _safe_rsi(klines: list[Kline], period: int = 14) -> float:
    if len(klines) < period + 1:
        return 50.0
    try:
        return rsi([k.close for k in klines], period)
    except Exception:
        return 50.0


def _safe_vol_ratio(klines: list[Kline], lookback: int = 20) -> float:
    if len(klines) < lookback + 1:
        return 1.0
    try:
        return volume_ratio([k.volume for k in klines], lookback)
    except Exception:
        return 1.0


def _decide_direction(
    state: MarketStructure,
    long_score: int,
    short_score: int,
    swings_detected: bool,
) -> SignalDirection:
    """RANGE(의도적 박스권, swings 존재) → NEUTRAL 강제.

    swings 미감지로 RANGE 폴백된 경우엔 alignment 기반 보정 점수로 방향 판정.
    """
    if state == MarketStructure.RANGE and swings_detected:
        return "NEUTRAL"
    if long_score - short_score >= _DIRECTION_MARGIN:
        return "LONG"
    if short_score - long_score >= _DIRECTION_MARGIN:
        return "SHORT"
    return "NEUTRAL"


def analyze(
    klines_1h: list[Kline],
    klines_4h: list[Kline],
    klines_1d: list[Kline],
) -> AnalysisResult:
    # 구조는 1d 기준; 1d 스윙이 없으면 1h로 폴백 (데이터 부족 대응)
    swings = detect_swings(klines_1d, fractal_window=5, atr_multiplier=1.5)
    if not swings and len(klines_1h) >= 11:
        swings = detect_swings(klines_1h, fractal_window=5, atr_multiplier=1.5)
    structure = classify_structure(swings)

    # 정렬
    alignment = compute_alignment(klines_1h, klines_4h, klines_1d)

    # RSI(1h) + Volume(1d)
    rsi_1h = _safe_rsi(klines_1h, 14)
    vr_1d = _safe_vol_ratio(klines_1d, 20)

    rsi_long_score = _rsi_score(rsi_1h)
    rsi_short_score = _rsi_score_short(rsi_1h)
    vol_score_ = _volume_score(vr_1d)

    # 스윙이 감지되지 않아 구조가 RANGE로 폴백된 경우: alignment 방향으로 보정
    struct_long = structure.long_score
    struct_short = structure.short_score
    if not swings:
        struct_long = round(0.5 * struct_long + 0.5 * alignment.long_score)
        struct_short = round(0.5 * struct_short + 0.5 * alignment.short_score)

    long_score = round(
        0.45 * struct_long
        + 0.35 * alignment.long_score
        + 0.10 * rsi_long_score
        + 0.10 * vol_score_
    )
    short_score = round(
        0.45 * struct_short
        + 0.35 * alignment.short_score
        + 0.10 * rsi_short_score
        + 0.10 * vol_score_
    )
    long_score = max(0, min(100, long_score))
    short_score = max(0, min(100, short_score))

    direction = _decide_direction(
        structure.state, long_score, short_score, swings_detected=bool(swings)
    )
    composite = max(long_score, short_score)

    tf_str = (
        f"1d{_TF_ARROW[alignment.tf_1d]} "
        f"4h{_TF_ARROW[alignment.tf_4h]} "
        f"1h{_TF_ARROW[alignment.tf_1h]}"
    )
    if alignment.aligned:
        align_label = "강정렬"
    elif alignment.bias == "mixed":
        align_label = "혼조"
    else:
        align_label = "부분정렬"
    vol_label = "볼륨↑" if vr_1d >= 1.5 else "볼륨→" if vr_1d >= 0.8 else "볼륨↓"
    reason = f"{tf_str} ({align_label}) · RSI(1h) {rsi_1h:.0f} · {vol_label}"

    # Week 9: S/R + ATR(1d)
    current = klines_1d[-1].close if klines_1d else 0.0
    sr_levels = (
        identify_sr_levels(klines_1d, swings, current)
        if klines_1d and current > 0
        else []
    )
    atr_1d_value = _atr(klines_1d, 14) if len(klines_1d) >= 15 else 0.0

    return AnalysisResult(
        structure=structure,
        alignment=alignment,
        rsi_1h=rsi_1h,
        volume_ratio_1d=vr_1d,
        composite_score=composite,
        reason=reason,
        sr_levels=sr_levels,
        atr_1d=atr_1d_value,
        long_score=long_score,
        short_score=short_score,
        direction=direction,
    )

"""Analysis 조합기: swing → structure + multi TF → composite_score.

Weights:
  composite = 0.45 * structure.score
            + 0.35 * alignment.score
            + 0.10 * rsi_score (1h RSI)
            + 0.10 * volume_score (1d volume_ratio)
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sajucandle.analysis.multi_timeframe import Alignment, compute_alignment
from sajucandle.analysis.structure import StructureAnalysis, classify_structure
from sajucandle.analysis.support_resistance import SRLevel, identify_sr_levels
from sajucandle.analysis.swing import _atr, detect_swings
from sajucandle.analysis.timeframe import TrendDirection
from sajucandle.market_data import Kline
from sajucandle.tech_analysis import (
    _rsi_score,
    _volume_score,
    rsi,
    volume_ratio,
)

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

    rsi_score_ = _rsi_score(rsi_1h)
    vol_score_ = _volume_score(vr_1d)

    # 스윙이 감지되지 않아 구조가 RANGE로 폴백된 경우: alignment 방향으로 structure score 보정
    structure_score = structure.score
    if not swings:
        # alignment score를 50% 반영하여 방향성 보정 (완전한 스윙 없이도 추세 반영)
        structure_score = round(0.5 * structure.score + 0.5 * alignment.score)

    composite = round(
        0.45 * structure_score
        + 0.35 * alignment.score
        + 0.10 * rsi_score_
        + 0.10 * vol_score_
    )
    composite = max(0, min(100, composite))

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
    )

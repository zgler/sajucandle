"""swing points → MarketStructure 분류.

HH-HL 연속 = UPTREND, LH-LL 연속 = DOWNTREND,
박스 돌파 = BREAKOUT, 상승추세 HL 이탈 = BREAKDOWN, 그 외 = RANGE.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from sajucandle.analysis.swing import SwingPoint


class MarketStructure(str, Enum):
    UPTREND = "uptrend"
    DOWNTREND = "downtrend"
    RANGE = "range"
    BREAKOUT = "breakout"
    BREAKDOWN = "breakdown"


@dataclass
class StructureAnalysis:
    state: MarketStructure
    last_high: Optional[SwingPoint]
    last_low: Optional[SwingPoint]
    score: int   # 0~100


_SCORE_MAP = {
    MarketStructure.UPTREND: 70,
    MarketStructure.BREAKOUT: 80,
    MarketStructure.RANGE: 50,
    MarketStructure.BREAKDOWN: 30,
    MarketStructure.DOWNTREND: 20,
}


def _last(swings: list[SwingPoint], kind: str) -> Optional[SwingPoint]:
    for sp in reversed(swings):
        if sp.kind == kind:
            return sp
    return None


def classify_structure(swings: list[SwingPoint]) -> StructureAnalysis:
    last_high = _last(swings, "high")
    last_low = _last(swings, "low")

    if not swings or (last_high is None and last_low is None):
        return StructureAnalysis(
            state=MarketStructure.RANGE,
            last_high=last_high, last_low=last_low,
            score=_SCORE_MAP[MarketStructure.RANGE],
        )

    highs = [s for s in swings if s.kind == "high"]
    lows = [s for s in swings if s.kind == "low"]

    # UPTREND: 최소 3개씩, 마지막 3개 high 모두 상승(HH-HH) + 마지막 3개 low 모두 상승(HL-HL)
    uptrend = (
        len(highs) >= 3 and len(lows) >= 3
        and highs[-1].price > highs[-2].price > highs[-3].price
        and lows[-1].price > lows[-2].price > lows[-3].price
    )
    downtrend = (
        len(highs) >= 3 and len(lows) >= 3
        and highs[-1].price < highs[-2].price < highs[-3].price
        and lows[-1].price < lows[-2].price < lows[-3].price
    )
    # BREAKDOWN: HH인데 LL (lows 3개 이상으로 충분)
    breakdown = (
        len(highs) >= 2 and len(lows) >= 3
        and highs[-1].price > highs[-2].price
        and lows[-1].price < lows[-2].price
    )
    # BREAKOUT: 마지막 high가 직전 high들보다 3%+ 돌파
    breakout = False
    if len(highs) >= 3:
        prev_range_top = max(h.price for h in highs[:-1])
        if highs[-1].price > prev_range_top * 1.03:
            breakout = True

    if uptrend:
        state = MarketStructure.UPTREND
    elif breakdown:
        state = MarketStructure.BREAKDOWN
    elif breakout:
        state = MarketStructure.BREAKOUT
    elif downtrend:
        state = MarketStructure.DOWNTREND
    else:
        state = MarketStructure.RANGE

    return StructureAnalysis(
        state=state,
        last_high=last_high,
        last_low=last_low,
        score=_SCORE_MAP[state],
    )

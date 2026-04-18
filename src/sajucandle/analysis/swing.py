"""Fractals + ATR 필터 기반 swing high/low 감지.

Fractal: N봉 기준. 중심 봉의 high가 좌우 N봉의 high보다 크면 swing high,
         low가 좌우 N봉의 low보다 작으면 swing low.
ATR 필터: 직전 반대 극점과의 거리가 ATR(period) * multiplier 미만이면 노이즈로 무시.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from sajucandle.market_data import Kline


@dataclass
class SwingPoint:
    index: int
    timestamp: datetime
    price: float
    kind: Literal["high", "low"]


def _atr(klines: list[Kline], period: int = 14) -> float:
    """Average True Range (Wilder). len(klines) >= period+1 전제."""
    if len(klines) < period + 1:
        return 0.0
    trs: list[float] = []
    for i in range(1, len(klines)):
        h = klines[i].high
        low_ = klines[i].low
        prev_c = klines[i - 1].close
        tr = max(h - low_, abs(h - prev_c), abs(low_ - prev_c))
        trs.append(tr)
    avg = sum(trs[:period]) / period
    for i in range(period, len(trs)):
        avg = (avg * (period - 1) + trs[i]) / period
    return avg


def detect_swings(
    klines: list[Kline],
    fractal_window: int = 5,
    atr_multiplier: float = 1.5,
    atr_period: int = 14,
) -> list[SwingPoint]:
    """Fractals + ATR 필터. 중심봉 좌우 fractal_window개 비교.

    반환: 시간순 SwingPoint 리스트.
    """
    n = len(klines)
    if n < 2 * fractal_window + 1:
        return []

    atr_value = 0.0
    if atr_multiplier > 0 and atr_period + 1 <= n:
        atr_value = _atr(klines, atr_period)
    threshold = atr_value * atr_multiplier if atr_value > 0 else 0.0

    candidates: list[SwingPoint] = []
    for i in range(fractal_window, n - fractal_window):
        center = klines[i]
        left = klines[i - fractal_window:i]
        right = klines[i + 1:i + 1 + fractal_window]
        neighbors = left + right
        if (all(center.high > k.high for k in left) and
                all(center.high > k.high for k in right)):
            prominence = center.high - max(k.high for k in neighbors)
            if threshold <= 0 or prominence >= threshold:
                candidates.append(SwingPoint(
                    index=i, timestamp=center.open_time,
                    price=center.high, kind="high",
                ))
        if (all(center.low < k.low for k in left) and
                all(center.low < k.low for k in right)):
            prominence = min(k.low for k in neighbors) - center.low
            if threshold <= 0 or prominence >= threshold:
                candidates.append(SwingPoint(
                    index=i, timestamp=center.open_time,
                    price=center.low, kind="low",
                ))

    return candidates

"""단일 타임프레임 추세 방향.

규칙:
  - close > EMA50 AND EMA50 기울기(최근 5봉) 양수 → UP
  - close < EMA50 AND EMA50 기울기 음수 → DOWN
  - 그 외 → FLAT
"""
from __future__ import annotations

from enum import Enum

from sajucandle.market_data import Kline


class TrendDirection(str, Enum):
    UP = "up"
    DOWN = "down"
    FLAT = "flat"


def _ema(values: list[float], period: int) -> list[float]:
    """EMA 시리즈. 길이 == len(values). 초기값은 SMA(period)."""
    if len(values) < period:
        return []
    k = 2.0 / (period + 1)
    out: list[float] = [0.0] * (period - 1)
    sma = sum(values[:period]) / period
    out.append(sma)
    for i in range(period, len(values)):
        prev = out[-1]
        out.append(values[i] * k + prev * (1 - k))
    return out


def trend_direction(klines: list[Kline], ema_period: int = 50) -> TrendDirection:
    if len(klines) < ema_period + 6:
        return TrendDirection.FLAT
    closes = [k.close for k in klines]
    emas = _ema(closes, ema_period)
    if not emas:
        return TrendDirection.FLAT
    last_close = closes[-1]
    last_ema = emas[-1]
    prev_ema = emas[-6]
    slope = last_ema - prev_ema

    # 절대값 기준으로 유의미한 기울기/이격 여부 판단
    threshold = last_ema * 0.0001  # 0.01% 이상이어야 방향성 있다고 간주

    above = last_close > last_ema + threshold
    below = last_close < last_ema - threshold
    rising = slope > threshold
    falling = slope < -threshold

    # 최근 close 단기 방향 (5봉 기준)
    close_slope = closes[-1] - closes[-6]
    close_rising = close_slope > threshold
    close_falling = close_slope < -threshold

    # UP: EMA 위 + EMA 상승 + close도 단기 상승
    if above and rising and close_rising:
        return TrendDirection.UP
    # DOWN: EMA 아래 + EMA 하락 + close도 단기 하락
    if below and falling and close_falling:
        return TrendDirection.DOWN
    return TrendDirection.FLAT

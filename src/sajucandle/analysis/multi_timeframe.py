"""1h/4h/1d 3개 TF의 트렌드 방향 → Alignment.

aligned: 3개 TF가 전부 UP 또는 전부 DOWN일 때만 True.
bias: UP 개수 - DOWN 개수 부호로 bullish/mixed/bearish.
score: bullish일수록 높음 (롱 관점). 0~100.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from sajucandle.analysis.timeframe import TrendDirection, trend_direction
from sajucandle.market_data import Kline


@dataclass
class Alignment:
    tf_1h: TrendDirection
    tf_4h: TrendDirection
    tf_1d: TrendDirection
    aligned: bool
    bias: Literal["bullish", "mixed", "bearish"]
    score: int          # legacy == long_score (하위호환)
    long_score: int = 0   # Phase 2: 롱 유리도
    short_score: int = 0  # Phase 2: 숏 유리도


def compute_alignment(
    klines_1h: list[Kline],
    klines_4h: list[Kline],
    klines_1d: list[Kline],
) -> Alignment:
    t1h = trend_direction(klines_1h)
    t4h = trend_direction(klines_4h)
    t1d = trend_direction(klines_1d)

    dirs = [t1h, t4h, t1d]
    ups = dirs.count(TrendDirection.UP)
    downs = dirs.count(TrendDirection.DOWN)

    aligned = (ups == 3) or (downs == 3)

    if ups > downs:
        bias: Literal["bullish", "mixed", "bearish"] = "bullish"
    elif downs > ups:
        bias = "bearish"
    else:
        bias = "mixed"

    diff = ups - downs    # -3..3
    long_score = round((diff + 3) / 6 * 100)
    short_score = round((-diff + 3) / 6 * 100)
    if aligned and bias == "bullish":
        long_score = max(long_score, 90)
        short_score = min(short_score, 10)
    if aligned and bias == "bearish":
        long_score = min(long_score, 10)
        short_score = max(short_score, 90)

    return Alignment(
        tf_1h=t1h, tf_4h=t4h, tf_1d=t1d,
        aligned=aligned, bias=bias,
        score=long_score,
        long_score=long_score,
        short_score=short_score,
    )

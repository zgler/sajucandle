"""차트 기술 분석 순수 함수 모음.

의존성 없음 (stdlib만). numpy/pandas/pandas-ta 미사용.

3개 지표 → chart_score(0~100) 결합:
  - RSI(14): 과매수/과매도
  - MA20 vs MA50: 추세
  - volume_ratio: 최근 볼륨 모멘텀

가중치는 spec §3.2에 하드코드. 백테스트 후 튜닝은 별도.
"""
from __future__ import annotations

from dataclasses import dataclass
from statistics import mean


# ─────────────────────────────────────────────
# Primitive indicators
# ─────────────────────────────────────────────

def sma(values: list[float], period: int) -> float:
    """Simple moving average of last `period` values."""
    if period <= 0:
        raise ValueError("period must be positive")
    if len(values) < period:
        raise ValueError(f"need at least {period} values, got {len(values)}")
    return mean(values[-period:])


def rsi(closes: list[float], period: int = 14) -> float:
    """Wilder's RSI.

    Standard formula:
      delta = close[t] - close[t-1]
      gain = max(delta, 0), loss = max(-delta, 0)
      avg_gain / avg_loss: 처음 period개는 단순 평균, 이후는 Wilder smoothing
        avg_new = (avg_prev * (period-1) + current) / period
      RS = avg_gain / avg_loss
      RSI = 100 - 100/(1+RS)

    closes 길이 < period+1이면 ValueError.
    """
    if period <= 0:
        raise ValueError("period must be positive")
    if len(closes) < period + 1:
        raise ValueError(f"need at least {period + 1} closes, got {len(closes)}")

    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [max(d, 0.0) for d in deltas]
    losses = [max(-d, 0.0) for d in deltas]

    # 초기 period 평균
    avg_gain = mean(gains[:period])
    avg_loss = mean(losses[:period])

    # Wilder smoothing (period+1번째부터)
    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    rs = avg_gain / avg_loss
    return 100.0 - 100.0 / (1.0 + rs)


def volume_ratio(volumes: list[float], lookback: int = 20) -> float:
    """오늘 볼륨 / 지난 lookback일 평균 볼륨.

    volumes[-1]이 "오늘", volumes[-lookback-1:-1]이 "과거 lookback일".
    길이 < lookback+1이면 ValueError.
    """
    if lookback <= 0:
        raise ValueError("lookback must be positive")
    if len(volumes) < lookback + 1:
        raise ValueError(f"need at least {lookback + 1} volumes, got {len(volumes)}")
    past_avg = mean(volumes[-lookback - 1:-1])
    if past_avg == 0:
        return 1.0  # 무의미한 경우 중립
    return volumes[-1] / past_avg


# ─────────────────────────────────────────────
# Scoring (0~100)
# ─────────────────────────────────────────────

def _rsi_score(rsi_value: float) -> int:
    """RSI → 0~100. 과매도(낮은 RSI)가 매수 기회로 점수 높음."""
    if rsi_value <= 30:
        return 70
    if rsi_value <= 45:
        return 55
    if rsi_value <= 55:
        return 50
    if rsi_value <= 70:
        return 40
    return 20


def _ma_score_and_trend(ma20_v: float, ma50_v: float) -> tuple[int, str]:
    """MA20/MA50 비교 → (점수, trend)."""
    if ma50_v == 0:
        return 50, "flat"
    ratio = ma20_v / ma50_v
    if ratio >= 1.02:
        return 70, "up"
    if ratio > 1.0:
        return 60, "up"
    if ratio >= 0.98:
        return 50, "flat"
    return 35, "down"


def _volume_score(ratio: float) -> int:
    """volume_ratio → 0~100. 강한 관심(>1.5)이 점수 높음."""
    if ratio >= 1.5:
        return 65
    if ratio >= 1.0:
        return 55
    if ratio >= 0.5:
        return 45
    return 35


@dataclass
class ChartScoreBreakdown:
    score: int              # 0~100 최종 차트 스코어
    rsi_value: float
    ma20: float
    ma50: float
    ma_trend: str           # "up" | "down" | "flat"
    volume_ratio_value: float
    reason: str             # 한국어 한 줄 요약


def score_chart(closes: list[float], volumes: list[float]) -> ChartScoreBreakdown:
    """closes/volumes(시간순, 최근이 마지막)로부터 차트 스코어 계산.

    필요 길이:
      - closes: RSI(14)+1 = 15 이상
      - closes: MA50 = 50 이상
      - volumes: lookback(20)+1 = 21 이상
    → 실무적으로 최소 50개 권장. Binance limit=100이 충분.

    결합: 0.4*rsi + 0.4*ma + 0.2*vol (spec §3.2).
    """
    if len(closes) < 50:
        raise ValueError(f"need >= 50 closes for MA50, got {len(closes)}")
    if len(volumes) < 21:
        raise ValueError(f"need >= 21 volumes, got {len(volumes)}")

    rsi_v = rsi(closes, 14)
    ma20_v = sma(closes, 20)
    ma50_v = sma(closes, 50)
    vr = volume_ratio(volumes, 20)

    s_rsi = _rsi_score(rsi_v)
    s_ma, trend = _ma_score_and_trend(ma20_v, ma50_v)
    s_vol = _volume_score(vr)

    final = round(0.4 * s_rsi + 0.4 * s_ma + 0.2 * s_vol)
    final = max(0, min(100, final))

    # 한국어 요약
    rsi_label = (
        "과매도" if rsi_v <= 30 else
        "낮음" if rsi_v <= 45 else
        "중립" if rsi_v <= 55 else
        "높음" if rsi_v <= 70 else
        "과매수"
    )
    ma_label = {"up": "MA20>MA50", "down": "MA20<MA50", "flat": "MA20≈MA50"}[trend]
    vol_label = "볼륨↑" if vr >= 1.5 else "볼륨→" if vr >= 0.5 else "볼륨↓"
    reason = f"RSI {rsi_v:.0f}({rsi_label}), {ma_label}, {vol_label}"

    return ChartScoreBreakdown(
        score=final,
        rsi_value=rsi_v,
        ma20=ma20_v,
        ma50=ma50_v,
        ma_trend=trend,
        volume_ratio_value=vr,
        reason=reason,
    )

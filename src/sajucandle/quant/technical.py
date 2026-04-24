"""TA (Technical Analysis) Score.

PRD §5-3, §6-3 기준:

주식 (100점):
  - Supertrend 방향                      25
  - 20/60/200 MA 정배열                  25
  - RSI 40~70 구간                       15
  - 거래량 추세 (20일 평균 대비)         15
  - 상대강도 RS (지수 대비)              20

코인 (100점):
  - Supertrend 방향                      30
  - 200MA 위 + RSI 40~65                 20
  - 모멘텀 (MACD 히스토그램)             20  (Funding 데이터 없어 대체)
  - 거래량 추세                          15
  - 상대강도 RS (BTC 대비)               15

출력: {"total": 0~100, "breakdown": {...}, "signals": [...]}

외부 의존:
  - `ta` 패키지 (RSI, MACD, BB)
  - Supertrend는 자체 구현 (ta에 없음)
"""

from __future__ import annotations

from typing import Dict, Optional

import numpy as np
import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import MACD


# ===================================================================
# 지표 구현
# ===================================================================

def _atr(df: pd.DataFrame, period: int = 10) -> pd.Series:
    h, l, c = df["high"], df["low"], df["close"]
    prev_c = c.shift(1)
    tr = pd.concat([(h - l),
                    (h - prev_c).abs(),
                    (l - prev_c).abs()], axis=1).max(axis=1)
    return tr.rolling(period, min_periods=1).mean()


def supertrend(df: pd.DataFrame, period: int = 10, multiplier: float = 3.0) -> pd.DataFrame:
    """Supertrend 지표. direction=+1(up), -1(down) 열 포함.

    참고: TradingView Supertrend 알고리즘의 표준 구현.
    """
    atr = _atr(df, period)
    hl2 = (df["high"] + df["low"]) / 2
    upper_band = hl2 + multiplier * atr
    lower_band = hl2 - multiplier * atr

    # 최종 상/하단 밴드 계산 (끈적임 방지)
    final_upper = upper_band.copy()
    final_lower = lower_band.copy()
    for i in range(1, len(df)):
        if upper_band.iloc[i] < final_upper.iloc[i - 1] or df["close"].iloc[i - 1] > final_upper.iloc[i - 1]:
            final_upper.iloc[i] = upper_band.iloc[i]
        else:
            final_upper.iloc[i] = final_upper.iloc[i - 1]
        if lower_band.iloc[i] > final_lower.iloc[i - 1] or df["close"].iloc[i - 1] < final_lower.iloc[i - 1]:
            final_lower.iloc[i] = lower_band.iloc[i]
        else:
            final_lower.iloc[i] = final_lower.iloc[i - 1]

    # 방향
    direction = pd.Series(index=df.index, dtype=float)
    supert = pd.Series(index=df.index, dtype=float)
    direction.iloc[0] = 1.0
    supert.iloc[0] = final_lower.iloc[0]
    for i in range(1, len(df)):
        prev_dir = direction.iloc[i - 1]
        if prev_dir == 1:
            if df["close"].iloc[i] < final_lower.iloc[i]:
                direction.iloc[i] = -1
                supert.iloc[i] = final_upper.iloc[i]
            else:
                direction.iloc[i] = 1
                supert.iloc[i] = final_lower.iloc[i]
        else:
            if df["close"].iloc[i] > final_upper.iloc[i]:
                direction.iloc[i] = 1
                supert.iloc[i] = final_lower.iloc[i]
            else:
                direction.iloc[i] = -1
                supert.iloc[i] = final_upper.iloc[i]

    return pd.DataFrame({
        "supertrend": supert,
        "direction": direction,
        "atr": atr,
    }, index=df.index)


def moving_averages(df: pd.DataFrame) -> pd.DataFrame:
    """20/60/200일 이평."""
    c = df["close"]
    return pd.DataFrame({
        "ma20": c.rolling(20, min_periods=1).mean(),
        "ma60": c.rolling(60, min_periods=1).mean(),
        "ma200": c.rolling(200, min_periods=1).mean(),
    }, index=df.index)


# ===================================================================
# 점수 계산
# ===================================================================

def _score_supertrend(df: pd.DataFrame) -> float:
    st = supertrend(df)
    last = st["direction"].iloc[-1]
    if np.isnan(last):
        return 50.0
    # 매수(+1) → 100, 매도(-1) → 0
    return 100.0 if last > 0 else 0.0


def _score_ma_alignment(df: pd.DataFrame) -> float:
    """20/60/200 정배열: 20>60>200 (상승)이면 100, 역배열(20<60<200)이면 0."""
    ma = moving_averages(df)
    c = df["close"].iloc[-1]
    ma20, ma60, ma200 = ma["ma20"].iloc[-1], ma["ma60"].iloc[-1], ma["ma200"].iloc[-1]
    if any(np.isnan(x) for x in [ma20, ma60, ma200]):
        return 50.0
    score = 0
    if c > ma20: score += 25
    if ma20 > ma60: score += 25
    if ma60 > ma200: score += 25
    if c > ma200: score += 25
    return float(score)


def _score_rsi(df: pd.DataFrame, low: int = 40, high: int = 70) -> float:
    """RSI가 40~70 구간이면 높은 점수 (추세 생존).

    <30 과매도: 50점 (반등 기대)
    30~40 회복 초입: 70점
    40~70 이상적: 100점
    70~80 과열: 60점
    >80 매우 과열: 20점
    """
    rsi = RSIIndicator(df["close"], window=14).rsi().iloc[-1]
    if np.isnan(rsi):
        return 50.0
    if low <= rsi <= high: return 100.0
    if 30 <= rsi < low: return 70.0
    if high < rsi <= 80: return 60.0
    if rsi > 80: return 20.0
    if rsi < 30: return 50.0
    return 50.0


def _score_volume_trend(df: pd.DataFrame) -> float:
    """최근 5일 평균 거래량 / 최근 20일 평균 거래량 (증가율)."""
    v = df["volume"]
    v5 = v.iloc[-5:].mean()
    v20 = v.iloc[-20:].mean()
    if v20 == 0 or np.isnan(v20):
        return 50.0
    ratio = v5 / v20
    # 1.5배 이상 증가 → 100, 동일 → 50, 0.5 이하 → 0
    if ratio >= 1.5: return 100.0
    if ratio <= 0.5: return 0.0
    return (ratio - 0.5) / (1.5 - 0.5) * 100


def _score_rs(df: pd.DataFrame, bench: pd.DataFrame, window: int = 60) -> float:
    """상대강도: 대상 60일 수익률 / 벤치마크 60일 수익률.

    1.2 이상 → 100, 1.0 → 50, 0.8 이하 → 0
    """
    if bench is None or bench.empty or len(df) < window:
        return 50.0
    r_self = df["close"].iloc[-1] / df["close"].iloc[-window] - 1
    # 벤치 일자 맞춤
    bench_aligned = bench[bench.index <= df.index[-1]]
    if len(bench_aligned) < window:
        return 50.0
    r_bench = bench_aligned["close"].iloc[-1] / bench_aligned["close"].iloc[-window] - 1
    if abs(r_bench) < 1e-6:
        return 50.0
    rs = (1 + r_self) / (1 + r_bench)
    if rs >= 1.2: return 100.0
    if rs <= 0.8: return 0.0
    return (rs - 0.8) / (1.2 - 0.8) * 100


def _score_macd_momentum(df: pd.DataFrame) -> float:
    """MACD 히스토그램 양수·상승이면 고점."""
    m = MACD(df["close"])
    hist = m.macd_diff()
    if len(hist) < 2:
        return 50.0
    last = hist.iloc[-1]
    prev = hist.iloc[-2]
    if np.isnan(last) or np.isnan(prev):
        return 50.0
    # 양수 & 증가
    if last > 0 and last > prev: return 100.0
    if last > 0 and last <= prev: return 70.0
    if last <= 0 and last > prev: return 50.0  # 반등 초입
    return 20.0


# ===================================================================
# 통합 점수
# ===================================================================

def ta_score_stock(df: pd.DataFrame, bench: Optional[pd.DataFrame] = None) -> Dict:
    """주식 TA Score (100점)."""
    if df.empty or len(df) < 30:
        return {"total": 50.0, "breakdown": {}, "warning": "insufficient data"}
    breakdown = {
        "supertrend": _score_supertrend(df),
        "ma_alignment": _score_ma_alignment(df),
        "rsi": _score_rsi(df),
        "volume_trend": _score_volume_trend(df),
        "relative_strength": _score_rs(df, bench),
    }
    weights = {
        "supertrend": 25,
        "ma_alignment": 25,
        "rsi": 15,
        "volume_trend": 15,
        "relative_strength": 20,
    }
    total = sum(breakdown[k] / 100 * w for k, w in weights.items())
    return {
        "total": round(total, 1),
        "breakdown": {k: round(v, 1) for k, v in breakdown.items()},
        "weights": weights,
    }


def ta_score_coin(df: pd.DataFrame, btc: Optional[pd.DataFrame] = None) -> Dict:
    """코인 TA Score (100점)."""
    if df.empty or len(df) < 30:
        return {"total": 50.0, "breakdown": {}, "warning": "insufficient data"}
    # 200MA + RSI 복합
    ma = moving_averages(df)
    rsi = RSIIndicator(df["close"], window=14).rsi().iloc[-1]
    above_200 = df["close"].iloc[-1] > ma["ma200"].iloc[-1] if not np.isnan(ma["ma200"].iloc[-1]) else False
    rsi_ok = 40 <= rsi <= 65 if not np.isnan(rsi) else False
    ma_rsi_score = 100.0 if (above_200 and rsi_ok) else (50.0 if above_200 or rsi_ok else 0.0)

    breakdown = {
        "supertrend": _score_supertrend(df),
        "ma200_rsi": ma_rsi_score,
        "macd_momentum": _score_macd_momentum(df),
        "volume_trend": _score_volume_trend(df),
        "relative_strength_vs_btc": _score_rs(df, btc),
    }
    weights = {
        "supertrend": 30,
        "ma200_rsi": 20,
        "macd_momentum": 20,
        "volume_trend": 15,
        "relative_strength_vs_btc": 15,
    }
    total = sum(breakdown[k] / 100 * w for k, w in weights.items())
    return {
        "total": round(total, 1),
        "breakdown": {k: round(v, 1) for k, v in breakdown.items()},
        "weights": weights,
    }

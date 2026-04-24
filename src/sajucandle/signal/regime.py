"""시장 레짐 감지 — Bull / Bear / Sideways.

기준 (PRD Null Test 결과 기반):
  Bull     : 벤치마크 최근 N개월 수익률 >= +threshold
  Bear     : 벤치마크 최근 N개월 수익률 <= -threshold
  Sideways : 그 사이

사주 필터 활성화 조건:
  Phase 2 코인 실험: Sideways에서 z=1.08 (유일하게 marginal edge)
  → Sideways일 때만 C 필터 ON, 나머지는 순수 퀀트
"""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import Enum


from ..quant.price_data import get_ohlcv


class Regime(str, Enum):
    BULL = "bull"
    BEAR = "bear"
    SIDEWAYS = "sideways"
    UNKNOWN = "unknown"


def detect_regime(
    asset_class: str,
    asof: datetime,
    lookback_months: int = 3,
    bull_threshold: float = 0.05,
    bear_threshold: float = -0.05,
) -> tuple[Regime, float]:
    """현재 시점 레짐 감지.

    Parameters
    ----------
    lookback_months : 최근 몇 개월 수익률로 판단 (기본 3개월)
    bull_threshold  : 이 이상이면 Bull
    bear_threshold  : 이 이하면 Bear

    Returns
    -------
    (Regime, bench_return) — 벤치마크 수익률과 레짐
    """
    bench = "SPY" if asset_class == "stock" else "BTC-USD"
    start = asof - timedelta(days=lookback_months * 31 + 10)

    df = get_ohlcv(bench, asset_class, start, asof)
    if df.empty or len(df) < 5:
        return Regime.UNKNOWN, 0.0

    # lookback_months 전 종가 → asof 종가
    cutoff = asof - timedelta(days=lookback_months * 30)
    past = df[df.index <= cutoff]
    recent = df[df.index <= asof]

    if past.empty or recent.empty:
        return Regime.UNKNOWN, 0.0

    bench_return = float(recent["close"].iloc[-1] / past["close"].iloc[-1] - 1)

    if bench_return >= bull_threshold:
        regime = Regime.BULL
    elif bench_return <= bear_threshold:
        regime = Regime.BEAR
    else:
        regime = Regime.SIDEWAYS

    return regime, round(bench_return, 4)


def detect_regime_monthly_series(
    asset_class: str,
    start: datetime,
    end: datetime,
    lookback_months: int = 1,
    bull_threshold: float = 0.05,
    bear_threshold: float = -0.05,
) -> dict[str, Regime]:
    """리밸런싱 월별 레짐 시리즈 반환.

    Returns
    -------
    { "YYYY-MM-DD": Regime, ... }
    """
    bench = "SPY" if asset_class == "stock" else "BTC-USD"
    df = get_ohlcv(bench, asset_class, start - timedelta(days=60), end + timedelta(days=5))
    if df.empty:
        return {}

    result = {}
    cur = datetime(start.year, start.month, 1)
    while cur <= end:
        date_str = cur.strftime("%Y-%m-%d")
        prev = cur - timedelta(days=lookback_months * 31)

        past = df[df.index <= prev]
        recent = df[df.index <= cur]
        if past.empty or recent.empty:
            result[date_str] = Regime.UNKNOWN
        else:
            ret = float(recent["close"].iloc[-1] / past["close"].iloc[-1] - 1)
            if ret >= bull_threshold:
                result[date_str] = Regime.BULL
            elif ret <= bear_threshold:
                result[date_str] = Regime.BEAR
            else:
                result[date_str] = Regime.SIDEWAYS

        if cur.month == 12:
            cur = datetime(cur.year + 1, 1, 1)
        else:
            cur = datetime(cur.year, cur.month + 1, 1)

    return result

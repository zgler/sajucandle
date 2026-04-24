"""On-chain Score — 코인 전용.

PRD §6-2 풀 구성 (100점):
  MVRV Z-Score                 25  (코인별 캘리브레이션)
  SOPR · aSOPR 추세            15
  거래소 순유출입              20
  HODL Waves (LTH 비중)        15
  NUPL                         10
  고래 매집 지표               15

Phase 1 간이 구현 (Tier 0) — CoinMetrics Community 무료 제한 반영:
  AdrActCnt : 30일 vs 90일 활성주소 변화    25
  Cap trend : 90일 시가총액 모멘텀         20
  Price drawdown : ATH 대비 하락 정도        20
  Volume surge : 최근 7일 vs 30일 거래량   20
  Price 200D ratio : 현재가 / 200일 평균    15

**403 락 메트릭들** (CapRealUSD·NVTAdj·TxTfrValAdjUSD): Phase 2에서 Glassnode
Advanced $39/월 또는 Dune 쿼리 직접 작성으로 MVRV·NVT·SOPR 정식 구현.

데이터 소스:
  - CoinMetrics Community API: CapMrktCurUSD, AdrActCnt (무료)
  - yfinance (price_data.get_ohlcv): 가격·거래량

BTC/ETH는 AdrActCnt 사용, 알트는 가격/거래량 proxy만.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict, Optional

import pandas as pd


_CM_SUPPORTED = {
    "BTC-USD": "btc",
    "ETH-USD": "eth",
    "BTC/USDT": "btc",
    "ETH/USDT": "eth",
    "BTC": "btc",
    "ETH": "eth",
}


def _to_cm_asset(symbol: str) -> Optional[str]:
    return _CM_SUPPORTED.get(symbol.upper())


def _fetch_cm_metric(asset: str, metric: str, start: datetime, end: datetime) -> pd.Series:
    """CoinMetrics Community API로 시계열 메트릭 조회. 실패 시 빈 시리즈."""
    import requests
    try:
        url = "https://community-api.coinmetrics.io/v4/timeseries/asset-metrics"
        params = {
            "assets": asset,
            "metrics": metric,
            "frequency": "1d",
            "start_time": start.strftime("%Y-%m-%d"),
            "end_time": end.strftime("%Y-%m-%d"),
            "page_size": 10000,
        }
        r = requests.get(url, params=params, timeout=30)
        r.raise_for_status()
        data = r.json().get("data", [])
        if not data:
            return pd.Series(dtype=float)
        rows = [(pd.to_datetime(d["time"]), float(d[metric]))
                for d in data if metric in d and d.get(metric) not in (None, "")]
        if not rows:
            return pd.Series(dtype=float)
        s = pd.Series({t: v for t, v in rows}).sort_index()
        return s
    except Exception:
        return pd.Series(dtype=float)


def _score_active_addresses(asset: str, start: datetime, end: datetime) -> float:
    """활성 주소 30일 평균 vs 90일 평균 증가율. CoinMetrics 무료 메트릭."""
    s = _fetch_cm_metric(asset, "AdrActCnt", start, end)
    if s.empty or len(s) < 90:
        return 50.0
    recent = s.iloc[-30:].mean()
    past = s.iloc[-90:-60].mean() if len(s) >= 90 else s.iloc[:30].mean()
    if past <= 0:
        return 50.0
    ratio = recent / past
    if ratio >= 1.3: return 90.0
    if ratio >= 1.1: return 75.0
    if ratio >= 0.95: return 55.0
    if ratio >= 0.85: return 40.0
    return 20.0


def _score_cap_trend(asset: str, start: datetime, end: datetime) -> float:
    """시가총액 90일 모멘텀. CoinMetrics 무료."""
    s = _fetch_cm_metric(asset, "CapMrktCurUSD", start, end)
    if s.empty or len(s) < 90:
        return 50.0
    recent = float(s.iloc[-1])
    past = float(s.iloc[-90])
    if past <= 0:
        return 50.0
    change = (recent - past) / past * 100
    if change >= 30: return 90.0
    if change >= 10: return 75.0
    if change >= 0: return 55.0
    if change >= -15: return 35.0
    return 15.0


def _score_drawdown(symbol: str, end: datetime) -> float:
    """현재가의 1년 최고가 대비 낙폭.

    낙폭이 클수록 저가 매수 기회 → 점수 ↑
    """
    from datetime import timedelta
    from .price_data import get_ohlcv
    start = end - timedelta(days=400)
    df = get_ohlcv(symbol, "coin", start, end)
    if df.empty or len(df) < 30:
        return 50.0
    ath = df["close"].max()
    cur = df["close"].iloc[-1]
    if ath <= 0:
        return 50.0
    dd = (cur - ath) / ath * 100  # 음수
    if dd <= -50: return 90.0   # 50%+ 하락 → 저가 기회
    if dd <= -30: return 75.0
    if dd <= -15: return 55.0
    if dd <= -5: return 45.0
    return 30.0                 # ATH 근처 → 과열


def _score_price_ma_ratio(symbol: str, end: datetime) -> float:
    """현재가 / 200일 이평. 1.0 근처가 안정, 급등·급락 감점."""
    from datetime import timedelta
    from .price_data import get_ohlcv
    start = end - timedelta(days=400)
    df = get_ohlcv(symbol, "coin", start, end)
    if df.empty or len(df) < 200:
        return 50.0
    ma200 = df["close"].iloc[-200:].mean()
    cur = df["close"].iloc[-1]
    if ma200 <= 0:
        return 50.0
    ratio = cur / ma200
    if 1.0 <= ratio <= 1.3: return 90.0   # 상승 추세 안정
    if 0.9 <= ratio < 1.0: return 70.0    # 근접
    if 1.3 < ratio <= 1.6: return 60.0    # 과열 초입
    if 0.7 <= ratio < 0.9: return 55.0    # 눌림
    if ratio > 1.6: return 30.0           # 매우 과열
    return 40.0                            # 심각한 하락


def _score_volume_vs_30d(symbol: str, end: datetime) -> float:
    """7일 평균 거래량 / 30일 평균 거래량. 1.5배 이상 급증."""
    from datetime import timedelta
    from .price_data import get_ohlcv
    start = end - timedelta(days=60)
    df = get_ohlcv(symbol, "coin", start, end)
    if df.empty or len(df) < 30:
        return 50.0
    v7 = df["volume"].iloc[-7:].mean()
    v30 = df["volume"].iloc[-30:].mean()
    if v30 <= 0:
        return 50.0
    ratio = v7 / v30
    if ratio >= 1.5: return 85.0
    if ratio >= 1.2: return 70.0
    if ratio >= 0.9: return 55.0
    if ratio >= 0.7: return 40.0
    return 20.0


def onchain_score(symbol: str) -> Dict:
    """코인 On-chain Score (100점).

    Phase 1: CoinMetrics 무료(BTC/ETH) + 가격 proxy. 알트는 가격 proxy만.
    """
    end = datetime.utcnow()
    start = end - timedelta(days=180)
    asset = _to_cm_asset(symbol)

    # CoinMetrics 지원 (BTC·ETH): 활성주소·시총모멘텀 사용
    if asset:
        active = _score_active_addresses(asset, start, end)
        cap_trend = _score_cap_trend(asset, start, end)
    else:
        active = 50.0
        cap_trend = 50.0

    breakdown = {
        "active_addresses": active,
        "cap_trend_90d": cap_trend,
        "price_drawdown": _score_drawdown(symbol, end),
        "price_ma200_ratio": _score_price_ma_ratio(symbol, end),
        "volume_7d_vs_30d": _score_volume_vs_30d(symbol, end),
    }
    weights = {
        "active_addresses": 25 if asset else 0,
        "cap_trend_90d": 20 if asset else 0,
        "price_drawdown": 20,
        "price_ma200_ratio": 15,
        "volume_7d_vs_30d": 20,
    }
    # 알트는 가중치 재분배 (45점 누락분을 나머지 55에 비례 재할당)
    if not asset:
        scale = 100 / 55
        weights = {
            "active_addresses": 0,
            "cap_trend_90d": 0,
            "price_drawdown": round(20 * scale),
            "price_ma200_ratio": round(15 * scale),
            "volume_7d_vs_30d": round(20 * scale),
        }

    total_w = sum(weights.values())
    total = sum(breakdown[k] / 100 * w for k, w in weights.items())
    if total_w != 100 and total_w > 0:
        total = total / total_w * 100
    return {
        "total": round(total, 1),
        "breakdown": {k: round(v, 1) for k, v in breakdown.items()},
        "weights": weights,
        "symbol": symbol,
        "note": ("Phase 1 간이 버전. MVRV/NVT/SOPR은 Phase 2 (유료 Glassnode 또는 Dune)."
                 if asset else
                 "알트코인: CoinMetrics 미지원, 가격 proxy만 사용."),
    }

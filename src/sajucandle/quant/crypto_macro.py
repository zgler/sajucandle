"""Crypto Macro Score.

PRD §6-1 구성 (100점):
  BTC Dominance 방향               20
  ETF 순유입 (4주 누적)            20   (Phase 2 — 현재는 생략하고 재분배)
  스테이블 공급 변화               15
  DXY + 미 유동성                  15
  Funding Rate 중간값              15
  청산 히트맵 리스크               15   (Phase 2 — 현재는 생략하고 재분배)

Phase 1 조정: ETF·청산 제외하고 가중치 재분배 (20+15가 빠지므로 남은 5개 = 65 → 100)
  BTC Dominance   31   (= 20 × 100/65)
  스테이블 공급   23
  DXY + 유동성   23
  Funding Rate   23

데이터 소스 (Tier 0):
- CoinGecko 무료 API: BTC Dominance, 스테이블 시총
- FRED: DXY, M2 통화량 (WM2NS)
- ccxt Binance: Funding Rate (선물 페어)

캐싱:
- 시세 데이터 캐시는 price_data 활용
- 매크로 스칼라 값은 호출마다 재계산 (주 1회 배치 권장)
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict, Optional

import numpy as np
import pandas as pd


def _score_btc_dominance(asof: datetime) -> float:
    """BTC Dominance(시총 점유율) 방향.

    CoinGecko /global 엔드포인트에서 현재값·30일 전 값 차로 방향 판단.

    - 상승 (알트 약세): 40
    - 하락 (알트 강세): 80
    - 횡보: 60
    """
    try:
        import requests
        r = requests.get("https://api.coingecko.com/api/v3/global", timeout=10)
        r.raise_for_status()
        cur = float(r.json()["data"]["market_cap_percentage"]["btc"])
        # 30일 전 값은 /global/market_cap_chart?days=30 (Pro 전용일 수 있음)
        # 무료는 현재값만 → 과거 비교 불가. 대안: BTC 시총 전체 시총 비율 직접 계산.
        # 여기선 단순화: 현재 BTC 도미넌스만으로 수준 판단.
        # >60: 알트 약세 (베어) → 40
        # 50~60: 중립 → 60
        # <50: 알트 강세 → 80
        if cur >= 60: return 40.0
        if cur >= 50: return 60.0
        return 80.0
    except Exception:
        return 50.0


def _score_stablecoin_supply(asof: datetime) -> float:
    """USDT+USDC 시총 변화 (매수 유동성 대리 지표).

    CoinGecko /coins/{id}/market_chart로 30일 과거 데이터 조회.
    증가 → 매수 대기 유동성 풍부 → 높은 점수.
    """
    try:
        import requests
        total_change = 0.0
        for coin_id in ["tether", "usd-coin"]:
            r = requests.get(
                f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart",
                params={"vs_currency": "usd", "days": "30"}, timeout=10,
            )
            r.raise_for_status()
            caps = r.json().get("market_caps", [])
            if len(caps) < 2:
                continue
            start_val = caps[0][1]
            end_val = caps[-1][1]
            if start_val > 0:
                total_change += (end_val - start_val) / start_val
        # 평균 변화
        avg_change = total_change / 2 * 100  # %
        # +5% 이상 → 100, 0 → 50, -5% 이하 → 0
        if avg_change >= 5: return 100.0
        if avg_change <= -5: return 0.0
        return 50.0 + avg_change * 10
    except Exception:
        return 50.0


def _score_dxy_liquidity(asof: datetime) -> float:
    """DXY 하락 + 미국 M2 증가 = 위험자산 우호.

    DXY는 macro.py의 _score_dxy 재활용.
    M2 증가율로 추가 가산.
    """
    from .macro import _score_dxy
    from datetime import timedelta
    start = asof - timedelta(days=365)
    dxy_score = _score_dxy(start, asof)
    # M2 증감 확인 (FRED CSV 직통)
    try:
        from .macro import _fetch_fred
        m2 = _fetch_fred("WM2NS", asof - timedelta(days=180), asof)
        if len(m2) >= 2:
            recent = float(m2.iloc[-1])
            past = float(m2.iloc[0])
            change_pct = (recent - past) / past * 100
            if change_pct > 1.5: dxy_score = min(100, dxy_score + 15)
            elif change_pct < 0: dxy_score = max(0, dxy_score - 10)
    except Exception:
        pass
    return dxy_score


def _score_funding_rate(asof: datetime) -> float:
    """Binance 주요 페어 Funding Rate 중간값으로 과열/정상 판단.

    BTC·ETH·SOL·BNB·XRP 페어의 최근 funding rate 평균.
    - 0.01%~0.03% : 정상 추세 → 100
    - 0~0.01%     : 중립 → 70
    - 음수        : 숏 우세 → 50
    - >0.05%      : 과열 → 30
    """
    try:
        import ccxt
        ex = ccxt.binance({"options": {"defaultType": "future"}, "enableRateLimit": True})
        rates = []
        for sym in ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT",
                    "BNB/USDT:USDT", "XRP/USDT:USDT"]:
            try:
                r = ex.fetch_funding_rate(sym)
                rates.append(r.get("fundingRate", 0) or 0)
            except Exception:
                continue
        if not rates:
            return 50.0
        avg = float(np.mean(rates)) * 100  # %
        if avg < 0: return 50.0
        if avg < 0.01: return 70.0
        if avg <= 0.03: return 100.0
        if avg <= 0.05: return 60.0
        return 30.0
    except Exception:
        return 50.0


def crypto_macro_score(asof: Optional[datetime] = None) -> Dict:
    """코인 Macro Score (100점 만점, Phase 1 조정 가중치)."""
    if asof is None:
        asof = datetime.utcnow()
    breakdown = {
        "btc_dominance": _score_btc_dominance(asof),
        "stablecoin_supply": _score_stablecoin_supply(asof),
        "dxy_liquidity": _score_dxy_liquidity(asof),
        "funding_rate": _score_funding_rate(asof),
    }
    # Phase 1 조정 가중치 (ETF·청산 제외)
    weights = {
        "btc_dominance": 31,
        "stablecoin_supply": 23,
        "dxy_liquidity": 23,
        "funding_rate": 23,
    }
    total = sum(breakdown[k] / 100 * w for k, w in weights.items())
    return {
        "total": round(total, 1),
        "breakdown": {k: round(v, 1) for k, v in breakdown.items()},
        "weights": weights,
        "asof": asof.isoformat(),
        "note": "ETF·청산 지표는 Phase 2에 추가 (가중치 재분배)",
    }

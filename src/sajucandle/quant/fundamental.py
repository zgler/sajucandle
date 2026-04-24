"""FA (Fundamental Analysis) Score — 주식 전용.

PRD §5-2 풀 구성 (100점):
  DCF Fair Value vs 현재가     25
  EV/EBITDA (업종 대비)        15
  ROIC − WACC (해자)           20
  Piotroski F-Score ≥ 6        15
  FCF Yield                    15
  EPS Growth 3Y                10

Phase 1 간이 구현 (yfinance 의존, Tier 0):
  Valuation: forwardPE + PEG 하이브리드   25
  Quality: ROE + operatingMargin          25
  FCF Yield                                20
  Growth: Revenue YoY + EPS YoY            15
  Balance Sheet: debtToEquity              15

완전한 DCF·F-Score는 Phase 2 (SEC EDGAR XBRL 파서 + 3년 재무제표 전수 계산).

데이터 품질 주의:
- yfinance info dict는 가끔 누락/이상값 → 0 또는 NaN 처리
- 섹터/업종별 normalize 필요 (지금은 글로벌 임계치 사용)
- 배당 수익률, 자사주 매입은 다음 버전 반영
"""

from __future__ import annotations

from functools import lru_cache
from typing import Dict, Optional

# yfinance.Ticker(sym).info 결과를 세션 내에서 캐시
# (종목당 2~5초 걸리는 호출을 반복하지 않기 위함)
_FA_INFO_CACHE: dict = {}


def _safe(info: dict, key: str, default=None):
    v = info.get(key, default)
    if v is None or (isinstance(v, float) and (v != v)):  # NaN 체크
        return default
    return v


def _score_valuation(info: dict) -> float:
    """PEG + forwardPE 기반 밸류에이션 점수.

    - PEG < 1, forwardPE < 20: 매우 저평가 → 100
    - PEG 1~2, forwardPE 20~30: 중립 → 60
    - PEG > 3 또는 forwardPE > 40: 고평가 → 20
    """
    peg = _safe(info, "pegRatio") or _safe(info, "trailingPegRatio")
    fpe = _safe(info, "forwardPE") or _safe(info, "trailingPE")
    if peg is None and fpe is None:
        return 50.0
    score = 50.0
    if peg is not None:
        if peg <= 0: score = 50.0  # 음수면 데이터 이상
        elif peg < 1: score += 25
        elif peg < 2: score += 10
        elif peg < 3: score -= 5
        else: score -= 20
    if fpe is not None:
        if fpe <= 0: pass
        elif fpe < 15: score += 15
        elif fpe < 25: score += 5
        elif fpe < 35: score -= 5
        else: score -= 15
    return max(0.0, min(100.0, score))


def _score_quality(info: dict) -> float:
    """ROE + operatingMargin 기반 수익성·효율성."""
    roe = _safe(info, "returnOnEquity")
    op_margin = _safe(info, "operatingMargins")
    if roe is None and op_margin is None:
        return 50.0
    score = 50.0
    if roe is not None:
        if roe > 0.25: score += 25
        elif roe > 0.15: score += 15
        elif roe > 0.10: score += 5
        elif roe < 0: score -= 25
    if op_margin is not None:
        if op_margin > 0.25: score += 25
        elif op_margin > 0.15: score += 10
        elif op_margin > 0.05: score += 0
        elif op_margin < 0: score -= 20
    return max(0.0, min(100.0, score))


def _score_fcf_yield(info: dict) -> float:
    """FCF Yield = Free Cash Flow / Market Cap.

    - 8%+ : 매우 우수 → 100
    - 5~8%: 양호 → 70
    - 2~5%: 중립 → 50
    - <2% : 낮음 → 30
    - 음수 : 소모 → 10
    """
    fcf = _safe(info, "freeCashflow")
    mcap = _safe(info, "marketCap")
    if fcf is None or mcap is None or mcap <= 0:
        return 50.0
    y = fcf / mcap
    if y >= 0.08: return 100.0
    if y >= 0.05: return 75.0
    if y >= 0.02: return 55.0
    if y >= 0: return 35.0
    return 10.0


def _score_growth(info: dict) -> float:
    """매출 + EPS 성장률."""
    rev_g = _safe(info, "revenueGrowth")      # 전년 동기 대비
    eps_g = _safe(info, "earningsGrowth")
    if rev_g is None and eps_g is None:
        return 50.0
    score = 50.0
    if rev_g is not None:
        if rev_g > 0.30: score += 25
        elif rev_g > 0.15: score += 15
        elif rev_g > 0.05: score += 5
        elif rev_g < 0: score -= 20
    if eps_g is not None:
        if eps_g > 0.30: score += 25
        elif eps_g > 0.15: score += 15
        elif eps_g > 0: score += 5
        elif eps_g < -0.10: score -= 20
    return max(0.0, min(100.0, score))


def _score_balance(info: dict) -> float:
    """부채비율·유동성 건전성."""
    de = _safe(info, "debtToEquity")
    current = _safe(info, "currentRatio")
    if de is None and current is None:
        return 50.0
    score = 50.0
    if de is not None:
        # yfinance는 debtToEquity를 퍼센트로 반환 (100 = 1.0 배)
        de_ratio = de / 100 if de > 10 else de
        if de_ratio < 0.3: score += 20
        elif de_ratio < 0.6: score += 10
        elif de_ratio < 1.0: score += 0
        elif de_ratio < 2.0: score -= 10
        else: score -= 20
    if current is not None:
        if current > 2: score += 15
        elif current > 1.5: score += 10
        elif current > 1: score += 0
        elif current < 1: score -= 15
    return max(0.0, min(100.0, score))


def fa_score(symbol: str, info: Optional[dict] = None) -> Dict:
    """주식 FA Score (100점 만점).

    Parameters
    ----------
    symbol : str
        티커 (예: "NVDA").
    info : dict | None
        이미 조회된 yfinance Ticker.info dict. 없으면 조회.
    """
    if info is None:
        if symbol in _FA_INFO_CACHE:
            info = _FA_INFO_CACHE[symbol]
        else:
            try:
                import yfinance as yf
                info = yf.Ticker(symbol).info or {}
            except Exception:
                info = {}
            _FA_INFO_CACHE[symbol] = info
    if not info:
        return {"total": 50.0, "breakdown": {}, "warning": "no fundamental data",
                "symbol": symbol}

    breakdown = {
        "valuation": _score_valuation(info),
        "quality": _score_quality(info),
        "fcf_yield": _score_fcf_yield(info),
        "growth": _score_growth(info),
        "balance_sheet": _score_balance(info),
    }
    weights = {
        "valuation": 25,
        "quality": 25,
        "fcf_yield": 20,
        "growth": 15,
        "balance_sheet": 15,
    }
    total = sum(breakdown[k] / 100 * w for k, w in weights.items())
    return {
        "total": round(total, 1),
        "breakdown": {k: round(v, 1) for k, v in breakdown.items()},
        "weights": weights,
        "symbol": symbol,
        "raw_metrics": {
            "forwardPE": _safe(info, "forwardPE"),
            "pegRatio": _safe(info, "pegRatio") or _safe(info, "trailingPegRatio"),
            "returnOnEquity": _safe(info, "returnOnEquity"),
            "operatingMargins": _safe(info, "operatingMargins"),
            "revenueGrowth": _safe(info, "revenueGrowth"),
            "earningsGrowth": _safe(info, "earningsGrowth"),
            "marketCap": _safe(info, "marketCap"),
            "freeCashflow": _safe(info, "freeCashflow"),
            "debtToEquity": _safe(info, "debtToEquity"),
        },
    }

"""종합 사주 점수 (PRD §4-3 스코어링 공식).

점수 구성 (100점 만점):
  25 × (월운 × 종목일주 궁합)      — 스윙 기간의 핵심
  20 × (일진 × 종목일주 궁합)      — 오늘의 진입 타이밍
  15 × (세운 오행 편향)             — 올해 왕성 오행과 종목 오행 일치도
  10 × (대운 장기 편향)             — 10년 단위 배경
  10 × (종목 오행 균형도)           — 종목 사주 내부 오행 분포
  10 × (합충형파해 이벤트)          — 세운/월운/일진과의 삼합·충 이벤트
  10 × (신살 보정)                  — 천을귀인·도화살 등

궁합 점수(raw)를 0~100 척도로 정규화하는 보수적 매핑:
  raw ≥ +25 → 100
  raw ≤ -25 → 0
  선형 스케일: (raw + 25) / 50 × 100
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, Optional

from ..manseryeok.core import SajuCalculator
from .constants import BRANCH_ELEMENT, STEM_ELEMENT
from .relations import (
    element_balance,
    pillar_compat_score,
    samhap_detection,
)
from .shinsal import find_shinsal, shinsal_total_score


def _normalize_raw(raw: int, lo: int = -25, hi: int = +25) -> float:
    """Raw score를 0~100으로 정규화 (clip)."""
    if raw <= lo:
        return 0.0
    if raw >= hi:
        return 100.0
    return (raw - lo) / (hi - lo) * 100


def _element_of_pillar(pillar: str) -> set:
    if not pillar or len(pillar) != 2:
        return set()
    out = set()
    s_el = STEM_ELEMENT.get(pillar[0])
    b_el = BRANCH_ELEMENT.get(pillar[1])
    if s_el: out.add(s_el)
    if b_el: out.add(b_el)
    return out


def saju_score(
    calc: SajuCalculator,
    ticker_primary_pillar: str,
    ticker_saju: Dict,                # 종목의 4주 (primary 구성요소)
    target_dt: datetime,               # 평가 시점 (오늘 + 시각)
    gender_of_user: Optional[str] = None,
) -> Dict:
    """종합 사주 점수 산출.

    Parameters
    ----------
    calc : SajuCalculator
    ticker_primary_pillar : str
        종목의 대표 일주 (primary).
    ticker_saju : dict
        종목 primary 구성요소의 4주 (year/month/day/hour pillars).
    target_dt : datetime
        평가 시점 (보통 오늘 또는 리밸런싱 시점).
    gender_of_user : str, optional
        대운 계산 필요 시 사용. 현재는 종목 사주 자체에 대운 개념 없으므로 미사용.

    Returns
    -------
    {
       "total_100": 78.3,
       "breakdown": {
          "wolwoon_x_ilju": 65.5,
          "ilji_x_ilju": 80.0,
          "sewoon_element_match": 55.0,
          "daeun_bias": 50.0,       # placeholder (종목은 대운 없음)
          "element_balance": 60.0,
          "samchung_events": 70.0,
          "shinsal_boost": 55.0,
       },
       "weighted": {
           "wolwoon_x_ilju": 25 * 0.655 = 16.4,
           ...
       },
       "today_context": {
           "sewoon": "丙午", "wolwoon": "壬辰", "ilji": "丁卯"
       }
    }
    """
    today_saju = calc.calculate_saju(
        year=target_dt.year, month=target_dt.month, day=target_dt.day,
        hour=target_dt.hour, minute=target_dt.minute,
        use_solar_time=False,  # 시장 KST 기준
    )
    sewoon = today_saju["year_pillar"]
    wolwoon = today_saju["month_pillar"]
    ilji = today_saju["day_pillar"]

    # 1) 월운 × 종목 일주
    wr = pillar_compat_score(ticker_primary_pillar, wolwoon)
    wolwoon_score = _normalize_raw(wr["total"])

    # 2) 일진 × 종목 일주
    ir = pillar_compat_score(ticker_primary_pillar, ilji)
    ilji_score = _normalize_raw(ir["total"])

    # 3) 세운 오행 편향: 세운 천간·지지의 오행과 종목 4주 오행 겹침 정도
    sewoon_elems = _element_of_pillar(sewoon)
    ticker_elems = set()
    for p in [ticker_saju.get("year_pillar", ""),
              ticker_saju.get("month_pillar", ""),
              ticker_saju.get("day_pillar", ""),
              ticker_saju.get("hour_pillar", "")]:
        ticker_elems |= _element_of_pillar(p)
    overlap = len(sewoon_elems & ticker_elems)
    possible = max(len(sewoon_elems), 1)
    sewoon_match_score = (overlap / possible) * 100

    # 4) 대운 편향: 종목은 "고정된 사주"라 대운 없음. Placeholder 50 (중립).
    daeun_score = 50.0

    # 5) 종목 오행 균형도
    ticker_pillars = [ticker_saju.get("year_pillar", ""),
                      ticker_saju.get("month_pillar", ""),
                      ticker_saju.get("day_pillar", ""),
                      ticker_saju.get("hour_pillar", "")]
    bal = element_balance(ticker_pillars)
    balance_score = bal["balance_score"] * 10  # 0~10 → 0~100

    # 6) 합충 이벤트: 세운·월운·일진·시주 지지와 종목 4주 지지에서 삼합/충 탐지
    all_branches = [today_saju["year_branch"], today_saju["month_branch"],
                    today_saju["day_branch"], today_saju["hour_branch"]]
    for p in ticker_pillars:
        if p and len(p) == 2:
            all_branches.append(p[1])
    samhap = samhap_detection(all_branches)
    # 충 감점은 이미 pillar_compat_score에 반영됨 → 삼합 위주 가산
    event_raw = 0
    for s in samhap:
        event_raw += s["score"]
    event_score = _normalize_raw(event_raw, lo=-25, hi=+25)

    # 7) 신살: 종목 4주의 신살 합산
    findings = find_shinsal(ticker_saju)
    shinsal_boost = shinsal_total_score(findings)  # -10 ~ +10
    shinsal_norm = (shinsal_boost + 10) / 20 * 100  # 0~100

    breakdown = {
        "wolwoon_x_ilju": round(wolwoon_score, 1),
        "ilji_x_ilju": round(ilji_score, 1),
        "sewoon_element_match": round(sewoon_match_score, 1),
        "daeun_bias": round(daeun_score, 1),
        "element_balance": round(balance_score, 1),
        "samchung_events": round(event_score, 1),
        "shinsal_boost": round(shinsal_norm, 1),
    }

    # 가중치 (100점 환산)
    weights = {
        "wolwoon_x_ilju": 25,
        "ilji_x_ilju": 20,
        "sewoon_element_match": 15,
        "daeun_bias": 10,
        "element_balance": 10,
        "samchung_events": 10,
        "shinsal_boost": 10,
    }
    weighted = {k: round(breakdown[k] / 100 * w, 2) for k, w in weights.items()}
    total_100 = round(sum(weighted.values()), 1)

    return {
        "total_100": total_100,
        "breakdown": breakdown,
        "weighted": weighted,
        "weights": weights,
        "today_context": {"sewoon": sewoon, "wolwoon": wolwoon, "ilji": ilji},
        "relations": {
            "wolwoon_raw": wr,
            "ilji_raw": ir,
            "samhap_events": samhap,
            "shinsal_findings": findings,
        },
    }


def saju_score_v2(
    calc: SajuCalculator,
    ticker_primary_pillar: str,
    ticker_saju: Dict,
    target_dt: datetime,
    gender_of_user: Optional[str] = None,
) -> Dict:
    """사주 점수 v2 — IC 분석 기반 3컴포넌트 재설계.

    IC 분석으로 ICIR > 0 인 컴포넌트만 유지:
      월운×일주 (ICIR=0.152)  36%
      세운 오행매칭 (ICIR=0.157) 37%
      신살보정 (ICIR=0.113)   27%

    제거된 컴포넌트:
      일진×일주  (ICIR=-0.133 — 월간 리밸런싱에 일봉 노이즈)
      대운편향   (상수 50, 무의미)
      오행균형   (ICIR=-0.038)
      합충이벤트  (ICIR=-0.024, 불안정)
    """
    today_saju = calc.calculate_saju(
        year=target_dt.year, month=target_dt.month, day=target_dt.day,
        hour=target_dt.hour, minute=target_dt.minute,
        use_solar_time=False,
    )
    sewoon = today_saju["year_pillar"]
    wolwoon = today_saju["month_pillar"]

    # 1) 월운 × 종목 일주 (ICIR=0.152 → 36%)
    wr = pillar_compat_score(ticker_primary_pillar, wolwoon)
    wolwoon_score = _normalize_raw(wr["total"])

    # 2) 세운 오행 편향 (ICIR=0.157 → 37%)
    sewoon_elems = _element_of_pillar(sewoon)
    ticker_elems: set = set()
    for p in [ticker_saju.get("year_pillar", ""),
              ticker_saju.get("month_pillar", ""),
              ticker_saju.get("day_pillar", ""),
              ticker_saju.get("hour_pillar", "")]:
        ticker_elems |= _element_of_pillar(p)
    overlap = len(sewoon_elems & ticker_elems)
    possible = max(len(sewoon_elems), 1)
    sewoon_match_score = (overlap / possible) * 100

    # 3) 신살 보정 (ICIR=0.113 → 27%)
    findings = find_shinsal(ticker_saju)
    shinsal_boost = shinsal_total_score(findings)
    shinsal_norm = (shinsal_boost + 10) / 20 * 100

    # ICIR 비례 가중치 (합=100)
    weights = {
        "wolwoon_x_ilju": 36,
        "sewoon_element_match": 37,
        "shinsal_boost": 27,
    }
    breakdown = {
        "wolwoon_x_ilju": round(wolwoon_score, 1),
        "sewoon_element_match": round(sewoon_match_score, 1),
        "shinsal_boost": round(shinsal_norm, 1),
    }
    weighted = {k: round(breakdown[k] / 100 * w, 2) for k, w in weights.items()}
    total_100 = round(sum(weighted.values()), 1)

    return {
        "total_100": total_100,
        "breakdown": breakdown,
        "weighted": weighted,
        "weights": weights,
        "today_context": {"sewoon": sewoon, "wolwoon": wolwoon},
        "version": "v2",
    }

"""종목 → 다층 종목사주 해석기.

각 종목의 창립일/상장일/전환점으로부터 개별 사주를 산출하고,
종목 레코드의 가중치에 따라 "유효 간지(effective pillar)"를 선택.

**유효 일주 선택 규칙**:
- 가중치가 가장 큰 구성요소의 일주를 primary로 사용
- 나머지는 보조 정보로 제공 (궁합 점수 계산 시 멀티-레이어 평균 가능)

본 초안에서는 primary 일주만 사용하여 궁합 계산을 단순화.
멀티-레이어 평균은 Phase 1에서 백테스트로 효용 확인 후 도입.
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, Optional

from ..manseryeok.core import SajuCalculator
from .schema import TickerRecord


def _parse_date_time(date_str: Optional[str], time_str: str) -> Optional[datetime]:
    if not date_str:
        return None
    try:
        date_part = datetime.strptime(date_str, "%Y-%m-%d").date()
        hh, mm = 0, 0
        if time_str and ":" in time_str:
            hh, mm = (int(x) for x in time_str.split(":")[:2])
        return datetime.combine(date_part, datetime.min.time()).replace(hour=hh, minute=mm)
    except (ValueError, TypeError):
        return None


def compute_component_saju(
    calc: SajuCalculator,
    dt: datetime,
    city: str,
) -> Dict:
    """주어진 시점에 대한 사주 4주 산출."""
    return calc.calculate_saju(
        year=dt.year, month=dt.month, day=dt.day,
        hour=dt.hour, minute=dt.minute,
        city=city, use_solar_time=True,
    )


def resolve_ticker_saju(calc: SajuCalculator, rec: TickerRecord) -> Dict:
    """종목의 다층 사주 반환.

    Returns
    -------
    {
      "symbol": "NVDA",
      "components": {
         "founding": {"weight": 0.5, "dt": "1993-04-05 00:00", "saju": {...}} | None,
         "listing":  {"weight": 0.3, "dt": "1999-01-22 09:30", "saju": {...}} | None,
         "transition": [ {weight_share, label, saju}, ... ]
      },
      "primary_pillar": "庚午",  # 가중치 최대 구성요소의 일주
      "primary_source": "founding" | "listing" | "transition",
    }
    """
    components: Dict = {"founding": None, "listing": None, "transition": []}

    # 만세력 범위(1900~2100) 밖이면 해당 구성요소 skip
    def _in_range(dt: datetime) -> bool:
        return 1900 <= dt.year <= 2100

    fd_dt = _parse_date_time(rec.founding_date, rec.founding_time)
    if fd_dt and rec.weight_founding > 0 and _in_range(fd_dt):
        components["founding"] = {
            "weight": rec.weight_founding,
            "dt": fd_dt.strftime("%Y-%m-%d %H:%M"),
            "saju": compute_component_saju(calc, fd_dt, rec.birth_city),
        }

    ld_dt = _parse_date_time(rec.listing_date, rec.listing_time)
    if ld_dt and rec.weight_listing > 0 and _in_range(ld_dt):
        components["listing"] = {
            "weight": rec.weight_listing,
            "dt": ld_dt.strftime("%Y-%m-%d %H:%M"),
            "saju": compute_component_saju(calc, ld_dt, rec.birth_city),
        }

    if rec.transition_points and rec.weight_transition > 0:
        per_point = rec.weight_transition / len(rec.transition_points)
        for tp in rec.transition_points:
            tp_dt = _parse_date_time(tp.date, tp.time)
            if tp_dt is None or not _in_range(tp_dt):
                continue
            components["transition"].append({
                "weight": per_point,
                "label": tp.label,
                "dt": tp_dt.strftime("%Y-%m-%d %H:%M"),
                "saju": compute_component_saju(calc, tp_dt, rec.birth_city),
            })

    # Primary: 가중치 최대
    best_source = None
    best_weight = 0.0
    best_pillar = ""
    if components["founding"] and components["founding"]["weight"] > best_weight:
        best_weight = components["founding"]["weight"]
        best_source = "founding"
        best_pillar = components["founding"]["saju"]["day_pillar"]
    if components["listing"] and components["listing"]["weight"] > best_weight:
        best_weight = components["listing"]["weight"]
        best_source = "listing"
        best_pillar = components["listing"]["saju"]["day_pillar"]
    for t in components["transition"]:
        if t["weight"] > best_weight:
            best_weight = t["weight"]
            best_source = "transition"
            best_pillar = t["saju"]["day_pillar"]

    return {
        "symbol": rec.symbol,
        "name": rec.name,
        "asset_class": rec.asset_class,
        "components": components,
        "primary_pillar": best_pillar,
        "primary_source": best_source,
    }

"""세운(歲運)·월운(月運) 계산 래퍼.

세운 = 특정 날짜에 적용되는 연주 간지 (입춘 기준 해당 해의 간지)
월운 = 특정 날짜에 적용되는 월주 간지 (절입 기준 해당 월의 간지)

이는 만세력 엔진(SajuCalculator)이 이미 계산해주는 값이다.
본 모듈은 "특정 시점의 세운/월운"을 질의하는 편의 래퍼를 제공.

주의: 일간(日干)은 "일진(日辰)"이라 하며, 주식/코인 추천 로직에서
"오늘의 일진" ↔ "종목 사주의 일주" 궁합 계산에 사용된다.
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict


def compute_sewoon_wolwoon_ilji(
    saju_calculator,
    target_dt: datetime,
) -> Dict:
    """주어진 시점(target_dt, KST 기준)의 세운·월운·일진.

    Parameters
    ----------
    saju_calculator : SajuCalculator
        초기화된 만세력 엔진 인스턴스.
    target_dt : datetime
        조회 시점. 매수 고려 시각 등.

    Returns
    -------
    dict:
        {
          "date": "YYYY-MM-DD HH:MM",
          "sewoon": "甲辰",     # 해당 시점의 연주
          "wolwoon": "戊辰",    # 해당 시점의 월주
          "ilji": "丙寅",       # 해당 시점의 일주(일진)
          "시주": "癸巳",       # 해당 시점의 시주
        }
    """
    saju = saju_calculator.calculate_saju(
        year=target_dt.year,
        month=target_dt.month,
        day=target_dt.day,
        hour=target_dt.hour,
        minute=target_dt.minute,
        # 시장 일진은 한국 KST 기준 — 태양시 보정 불필요
        use_solar_time=False,
        utc_offset=9,
    )
    return {
        "date": target_dt.strftime("%Y-%m-%d %H:%M"),
        "sewoon": saju["year_pillar"],
        "wolwoon": saju["month_pillar"],
        "ilji": saju["day_pillar"],
        "시주": saju["hour_pillar"],
    }

"""대운(大運) 계산 모듈.

명리학적 룰:
1. 대운 방향: 양년생남·음년생녀 → 순행(順行), 음년생남·양년생녀 → 역행(逆行)
2. 출발 간지: 월주(月柱) 기준 순행/역행으로 10년마다 다음 간지
3. 대운수(시작 나이):
   - 순행: 출생시각 ~ **다음** 절입시각까지의 시간 / 3일 = 1세
   - 역행: **이전** 절입시각 ~ 출생시각까지의 시간 / 3일 = 1세
4. 일반적으로 10년 단위로 대운 교체 (대운 기간 내에서 세운/월운이 추가 순환)

시간 단위 변환 관행:
- 3일 = 1세 (대운수 계산 기준)
- 1일 = 4개월, 2시간 = 10일 × 4/24 ≈ 1.67일... 실제로는 "시간 나누기 3" 근사 후 반올림

본 모듈은 **연속값(소수점 나이)** 을 반환하여 호출자가 사용자에게 반올림 표시 여부를 결정하도록 함.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from .constants import GAPJA, gapja_index, is_yang_year


def _parse_term_time_kst(term_time) -> Optional[datetime]:
    """YYYYMMDDHHMM 형식의 KST 절기 시각 파싱.

    pandas read_csv가 NaN 때문에 float로 읽는 경우("199010082213.0") 까지 처리.
    """
    if term_time is None:
        return None
    s = str(term_time).strip()
    if not s or s.lower() == "nan":
        return None
    # float 문자열이면 int로 재변환
    if "." in s:
        try:
            s = str(int(float(s)))
        except ValueError:
            return None
    # zero-pad 12자리로 보정 (앞자리 빠진 경우 대비)
    if len(s) < 12:
        s = s.zfill(12)
    if len(s) != 12:
        return None
    try:
        return datetime(
            year=int(s[0:4]), month=int(s[4:6]), day=int(s[6:8]),
            hour=int(s[8:10]), minute=int(s[10:12]),
        )
    except ValueError:
        return None


# 12절(월주 전환) 한자 집합 — core.py와 동기화 필요
MONTHLY_TERMS_SET = {
    "立春", "驚蟄", "清明", "立夏", "芒種", "小暑",
    "立秋", "白露", "寒露", "立冬", "大雪", "小寒",
}


def _find_adjacent_monthly_term(
    calendar_data,  # pandas DataFrame (sajucandle.manseryeok CSV 로드된 것)
    birth_dt: datetime,
    direction: str,
) -> Optional[datetime]:
    """출생시각 기준 다음 또는 이전 12절 시각 반환 (KST).

    direction: "forward" | "backward"
    """
    # 월주 전환 절기만 필터링
    df = calendar_data[calendar_data['solar_term_hanja'].isin(MONTHLY_TERMS_SET)]
    # 각 행의 term_time 파싱
    candidates = []
    for _, row in df.iterrows():
        dt = _parse_term_time_kst(row.get('term_time', ''))
        if dt is None:
            continue
        candidates.append(dt)
    if not candidates:
        return None
    candidates.sort()

    if direction == "forward":
        for dt in candidates:
            if dt > birth_dt:
                return dt
        return None
    else:  # backward
        prev = None
        for dt in candidates:
            if dt < birth_dt:
                prev = dt
            else:
                break
        return prev


def compute_daeun(
    calendar_data,
    birth_dt: datetime,
    year_pillar: str,
    month_pillar: str,
    gender: str,
    num_daeun: int = 10,
) -> Dict:
    """대운 리스트 계산.

    Parameters
    ----------
    calendar_data : pandas DataFrame
        사주캔들 만세력 CSV가 로드된 DataFrame (`SajuCalculator.data`).
    birth_dt : datetime
        출생 시각 (KST 기준, 태양시 보정 전 원본).
    year_pillar : str
        연주 간지 (예: "甲辰"). 입춘 경계 처리 반영된 최종 연주.
    month_pillar : str
        월주 간지 (예: "丙寅"). 절기 경계 처리 반영된 최종 월주.
    gender : str
        "M"(남) 또는 "F"(여).
    num_daeun : int
        산출할 대운 개수. 기본 10개 (100년치).

    Returns
    -------
    dict:
        {
          "direction": "순행" | "역행",
          "is_yang_year": bool,
          "gender": "M"|"F",
          "start_age_years": float,   # 첫 대운 시작 나이 (연속값)
          "daeun": [
             {"index": 1, "pillar": "丁卯", "stem": "丁", "branch": "卯",
              "start_age": 7.3, "end_age": 17.3,
              "start_date": "YYYY-MM-DD", "end_date": "YYYY-MM-DD"},
             ...
          ]
        }
    """
    if gender not in {"M", "F"}:
        raise ValueError("gender must be 'M' or 'F'")
    yy = is_yang_year(year_pillar)
    # 순행: 양남·음녀, 역행: 음남·양녀
    if (gender == "M" and yy) or (gender == "F" and not yy):
        direction = "순행"
        step = +1
        target_term_dt = _find_adjacent_monthly_term(calendar_data, birth_dt, "forward")
        if target_term_dt is None:
            raise ValueError("다음 절입 시각을 찾을 수 없음")
        delta_seconds = (target_term_dt - birth_dt).total_seconds()
    else:
        direction = "역행"
        step = -1
        target_term_dt = _find_adjacent_monthly_term(calendar_data, birth_dt, "backward")
        if target_term_dt is None:
            raise ValueError("이전 절입 시각을 찾을 수 없음")
        delta_seconds = (birth_dt - target_term_dt).total_seconds()

    # 3일 = 1세 → 초 단위: 3 * 86400
    start_age = delta_seconds / (3 * 86400)
    # 대운 간지
    mi = gapja_index(month_pillar)
    if mi < 0:
        raise ValueError(f"Unknown month pillar: {month_pillar}")

    daeun_list = []
    for i in range(num_daeun):
        idx = (mi + step * (i + 1)) % 60
        pillar = GAPJA[idx]
        age_start = start_age + i * 10
        age_end = age_start + 10
        # 대응 날짜 (연속 나이를 출생 datetime에 더함)
        start_date_dt = birth_dt + timedelta(days=age_start * 365.2425)
        end_date_dt = birth_dt + timedelta(days=age_end * 365.2425)
        daeun_list.append({
            "index": i + 1,
            "pillar": pillar,
            "stem": pillar[0],
            "branch": pillar[1],
            "start_age": round(age_start, 2),
            "end_age": round(age_end, 2),
            "start_date": start_date_dt.strftime("%Y-%m-%d"),
            "end_date": end_date_dt.strftime("%Y-%m-%d"),
        })

    return {
        "direction": direction,
        "is_yang_year": yy,
        "gender": gender,
        "start_age_years": round(start_age, 2),
        "daeun": daeun_list,
    }

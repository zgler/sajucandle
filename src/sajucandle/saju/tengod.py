"""십신(十神) 계산.

일간(日干)을 기준으로 다른 천간 또는 지지의 본기(本氣) 천간에 대해
다음 10가지 중 하나의 관계를 결정:

- 비견(比肩): 같은 오행, 같은 음양
- 겁재(劫財): 같은 오행, 다른 음양
- 식신(食神): 일간이 생하는 오행, 같은 음양
- 상관(傷官): 일간이 생하는 오행, 다른 음양
- 편재(偏財): 일간이 극하는 오행, 같은 음양
- 정재(正財): 일간이 극하는 오행, 다른 음양
- 편관(偏官/七殺): 일간을 극하는 오행, 같은 음양
- 정관(正官): 일간을 극하는 오행, 다른 음양
- 편인(偏印): 일간을 생하는 오행, 같은 음양
- 정인(正印): 일간을 생하는 오행, 다른 음양
"""

from __future__ import annotations

from typing import Dict, List

from .constants import (
    BRANCH_ELEMENT,
    ELEMENT_GENERATES,
    ELEMENT_OVERCOMES,
    STEM_ELEMENT,
    STEM_YIN_YANG,
    is_yang_stem,
)


# 지지 본기(本氣) 천간: 지지를 10천간으로 대표할 때 사용
BRANCH_MAIN_STEM = {
    "子": "癸",
    "丑": "己",
    "寅": "甲",
    "卯": "乙",
    "辰": "戊",
    "巳": "丙",
    "午": "丁",
    "未": "己",
    "申": "庚",
    "酉": "辛",
    "戌": "戊",
    "亥": "壬",
}


def ten_god_for_stem(day_stem: str, other_stem: str) -> str:
    """일간 기준 other_stem의 십신 명칭."""
    if not day_stem or not other_stem:
        return ""
    day_el = STEM_ELEMENT.get(day_stem)
    other_el = STEM_ELEMENT.get(other_stem)
    if not day_el or not other_el:
        return ""

    day_yang = is_yang_stem(day_stem)
    other_yang = is_yang_stem(other_stem)
    same_yinyang = (day_yang == other_yang)

    # 관계 결정
    if day_el == other_el:
        return "비견" if same_yinyang else "겁재"
    if ELEMENT_GENERATES.get(day_el) == other_el:
        return "식신" if same_yinyang else "상관"
    if ELEMENT_OVERCOMES.get(day_el) == other_el:
        return "편재" if same_yinyang else "정재"
    if ELEMENT_OVERCOMES.get(other_el) == day_el:
        return "편관" if same_yinyang else "정관"
    if ELEMENT_GENERATES.get(other_el) == day_el:
        return "편인" if same_yinyang else "정인"
    return ""


def ten_god_for_branch(day_stem: str, branch: str) -> str:
    """일간 기준 지지 본기의 십신."""
    main = BRANCH_MAIN_STEM.get(branch)
    if not main:
        return ""
    return ten_god_for_stem(day_stem, main)


def tengod_distribution(saju: Dict) -> Dict:
    """사주 4주의 십신 분포 반환.

    Parameters
    ----------
    saju : dict
        SajuCalculator.calculate_saju() 결과 (year/month/day/hour stem·branch 포함).

    Returns
    -------
    dict:
      {
        "day_stem": "丙",
        "year_stem_tg": "식신", "year_branch_tg": "정재",
        "month_stem_tg": ..., "month_branch_tg": ...,
        "hour_stem_tg": ..., "hour_branch_tg": ...,
        "counts": {"비견": 1, "식신": 2, ...},
        "dominant_group": "재성" | "관성" | "인성" | "식상" | "비겁"
      }
    """
    day_stem = saju.get("day_stem", "")
    if not day_stem:
        return {}
    result = {"day_stem": day_stem}

    # 연/월/시의 천간과 지지 각각에 대해 십신 결정
    mapping = {
        "year": ("year_stem", "year_branch"),
        "month": ("month_stem", "month_branch"),
        "hour": ("hour_stem", "hour_branch"),
    }
    counts: Dict[str, int] = {}
    for prefix, (stem_key, branch_key) in mapping.items():
        stem_tg = ten_god_for_stem(day_stem, saju.get(stem_key, ""))
        branch_tg = ten_god_for_branch(day_stem, saju.get(branch_key, ""))
        result[f"{prefix}_stem_tg"] = stem_tg
        result[f"{prefix}_branch_tg"] = branch_tg
        for tg in [stem_tg, branch_tg]:
            if tg:
                counts[tg] = counts.get(tg, 0) + 1

    # 일주 지지도 포함
    day_branch_tg = ten_god_for_branch(day_stem, saju.get("day_branch", ""))
    result["day_branch_tg"] = day_branch_tg
    if day_branch_tg:
        counts[day_branch_tg] = counts.get(day_branch_tg, 0) + 1

    result["counts"] = counts

    # 육친 그룹
    groups = {
        "비겁": ("비견", "겁재"),
        "식상": ("식신", "상관"),
        "재성": ("편재", "정재"),
        "관성": ("편관", "정관"),
        "인성": ("편인", "정인"),
    }
    group_counts = {
        g: sum(counts.get(t, 0) for t in tgs)
        for g, tgs in groups.items()
    }
    result["group_counts"] = group_counts
    result["dominant_group"] = max(group_counts, key=group_counts.get) if any(group_counts.values()) else ""

    return result

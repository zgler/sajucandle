"""감정서 컨텍스트 수집 — 기존 사주 엔진을 조합하여 Claude에 전달할 dict 생성."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sajucandle.manseryeok.core import get_saju_calculator
from sajucandle.saju.constants import element_of_stem, is_yang_stem
from sajucandle.saju.tengod import tengod_distribution, ten_god_for_stem
from sajucandle.saju.investor_profile import classify_investor_type
from sajucandle.saju.relations import element_balance, pillar_compat_score
from sajucandle.saju.shinsal import find_shinsal
from sajucandle.saju.daeun import compute_daeun
from sajucandle.saju.sewoon import compute_sewoon_wolwoon_ilji


def collect_report_context(
    year: int,
    month: int,
    day: int,
    hour: int | None,
    gender: str,
    target_year: int,
) -> dict[str, Any]:
    """사주 엔진 모듈을 조합하여 감정서 생성용 컨텍스트를 수집한다."""
    calc = get_saju_calculator()
    h = hour if hour is not None else 0
    saju = calc.calculate_saju(year, month, day, h)

    if hour is None:
        saju["hour_pillar"] = ""
        saju["hour_stem"] = ""
        saju["hour_branch"] = ""

    day_stem = saju["day_stem"]

    # 십신 분포
    td = tengod_distribution(saju)

    # 투자 체질
    profile = classify_investor_type(saju)

    # 오행 균형
    pillars = [saju["year_pillar"], saju["month_pillar"], saju["day_pillar"]]
    if hour is not None:
        pillars.append(saju["hour_pillar"])
    eb = element_balance(pillars)

    # 세운
    target_dt = datetime(target_year, 6, 1, 12)
    sewoon_ctx = compute_sewoon_wolwoon_ilji(calc, target_dt)
    sewoon_pillar = sewoon_ctx["sewoon"]
    sewoon_stem = sewoon_pillar[0] if sewoon_pillar else ""
    sewoon_tg = ten_god_for_stem(day_stem, sewoon_stem)

    # 12개월 월운
    monthly_pillars = []
    for m in range(1, 13):
        m_dt = datetime(target_year, m, 1, 12)
        m_ctx = compute_sewoon_wolwoon_ilji(calc, m_dt)
        m_pillar = m_ctx["wolwoon"]
        m_stem = m_pillar[0] if m_pillar else ""
        m_tg = ten_god_for_stem(day_stem, m_stem)
        monthly_pillars.append({
            "month": m,
            "pillar": m_pillar,
            "stem": m_stem,
            "tengod": m_tg,
        })

    # 대운
    birth_dt = datetime(year, month, day, h)
    daeun_data = compute_daeun(
        calc.data, birth_dt,
        saju["year_pillar"], saju["month_pillar"], gender,
    )
    age = target_year - year
    current_daeun: dict[str, Any] = {}
    for d in daeun_data.get("daeun", []):
        if d["start_age"] <= age < d["end_age"]:
            current_daeun = d
            break

    daeun_stem = current_daeun.get("stem", "")
    daeun_tg = ten_god_for_stem(day_stem, daeun_stem) if daeun_stem else ""
    daeun_pillar = current_daeun.get("pillar", "")

    # 신살
    shinsal_list = find_shinsal(saju)
    shinsal_names = [s["name"] for s in shinsal_list]

    # 관계 분석
    day_pillar = saju["day_pillar"]
    day_sewoon = pillar_compat_score(day_pillar, sewoon_pillar)
    day_daeun = pillar_compat_score(day_pillar, daeun_pillar) if daeun_pillar else {
        "pros": [], "cons": [],
    }

    def _format_rels(compat: dict) -> dict:
        return {
            "pros": [r.get("detail", r.get("type", "")) for r in compat.get("pros", [])],
            "cons": [r.get("detail", r.get("type", "")) for r in compat.get("cons", [])],
        }

    # hour pillar 처리
    hour_data = None
    if hour is not None:
        hour_data = {
            "pillar": saju["hour_pillar"],
            "stem": saju["hour_stem"],
            "branch": saju["hour_branch"],
        }

    return {
        "birth": {
            "year": year,
            "month": month,
            "day": day,
            "hour": hour,
            "gender": gender,
        },
        "pillars": {
            "year": {
                "pillar": saju["year_pillar"],
                "stem": saju["year_stem"],
                "branch": saju["year_branch"],
            },
            "month": {
                "pillar": saju["month_pillar"],
                "stem": saju["month_stem"],
                "branch": saju["month_branch"],
            },
            "day": {
                "pillar": saju["day_pillar"],
                "stem": saju["day_stem"],
                "branch": saju["day_branch"],
            },
            "hour": hour_data,
        },
        "day_master": {
            "stem": day_stem,
            "element": element_of_stem(day_stem),
            "yin_yang": "양" if is_yang_stem(day_stem) else "음",
        },
        "tengod_distribution": td["group_counts"],
        "element_balance": eb["counts"],
        "dominant_group": td["dominant_group"],
        "investor_type": profile.investor_type,
        "sewoon": {
            "pillar": sewoon_pillar,
            "stem": sewoon_stem,
            "tengod": sewoon_tg,
        },
        "monthly_pillars": monthly_pillars,
        "current_daeun": {
            "pillar": daeun_pillar,
            "stem": daeun_stem,
            "tengod": daeun_tg,
            "start_age": int(current_daeun.get("start_age", 0)),
            "end_age": int(current_daeun.get("end_age", 0)),
        },
        "shinsal": shinsal_names,
        "relations": {
            "day_sewoon": _format_rels(day_sewoon),
            "day_daeun": _format_rels(day_daeun),
        },
    }

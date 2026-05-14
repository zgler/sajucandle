"""사주캔들 사주 운세 라우터 — /api/saju/profile, /api/saju/daily, /api/saju/yearly, /api/saju/report."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Optional

import anthropic
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from sajucandle.manseryeok.core import get_saju_calculator
from sajucandle.saju.investor_profile import classify_investor_type, DAY_MASTER_DESCRIPTIONS
from sajucandle.saju.daily_fortune import generate_daily_fortune
from sajucandle.saju.fortune_templates import SEWOON_TEMPLATES, DAEUN_TEMPLATES
from sajucandle.saju.tengod import ten_god_for_stem
from sajucandle.saju.daeun import compute_daeun
from sajucandle.saju.sewoon import compute_sewoon_wolwoon_ilji
from sajucandle.saju.constants import element_of_stem
from sajucandle.saju.report_context import collect_report_context
from sajucandle.saju.report_generator import generate_report

router = APIRouter()

_ELEMENT_KR = {"木": "목", "火": "화", "土": "토", "金": "금", "水": "수"}


def _element_kr(stem: str) -> str:
    return _ELEMENT_KR.get(element_of_stem(stem), "")


def _has_anthropic_key() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def _calc_saju_for_user(req_year: int, req_month: int, req_day: int,
                        req_hour: Optional[int], req_minute: int = 0) -> dict:
    """유저 생년월일 → 사주 계산. 시간 미입력 시 시주 제거."""
    calc = get_saju_calculator()
    h = req_hour if req_hour is not None else 0
    saju = calc.calculate_saju(req_year, req_month, req_day, h, req_minute)
    if req_hour is None:
        saju["hour_pillar"] = ""
        saju["hour_stem"] = ""
        saju["hour_branch"] = ""
    return saju


# ── 스키마 ────────────────────────────────────────────────────────────────

class ProfileRequest(BaseModel):
    year: int
    month: int
    day: int
    hour: Optional[int] = None
    minute: int = 0
    gender: str = "M"


class ReportRequest(BaseModel):
    year: int
    month: int
    day: int
    hour: Optional[int] = None
    gender: str = "M"
    tier: str = "standard"  # "standard" (Sonnet) or "premium" (Opus)


# ── 라우트 ────────────────────────────────────────────────────────────────

@router.post("/api/saju/profile")
def saju_profile(req: ProfileRequest):
    """생년월일시 → 투자 체질 프로필."""
    saju = _calc_saju_for_user(req.year, req.month, req.day, req.hour, req.minute)
    profile = classify_investor_type(saju)
    return {
        "pillars": {
            "year_stem": saju["year_stem"],
            "year_branch": saju["year_branch"],
            "month_stem": saju["month_stem"],
            "month_branch": saju["month_branch"],
            "day_stem": saju["day_stem"],
            "day_branch": saju["day_branch"],
            "hour_stem": saju.get("hour_stem") or None,
            "hour_branch": saju.get("hour_branch") or None,
        },
        "day_master": profile.day_master,
        "day_master_element": _element_kr(profile.day_master),
        "day_master_description": DAY_MASTER_DESCRIPTIONS.get(profile.day_master, ""),
        "investor_type": profile.investor_type,
        "description": profile.description,
        "strengths": profile.strengths,
        "weaknesses": profile.weaknesses,
        "risk_score": profile.risk_score,
        "element_distribution": profile.element_distribution,
        "dominant_group": profile.dominant_group,
        "tengod_counts": profile.tengod_counts,
    }


@router.get("/api/saju/daily")
def saju_daily(
    year: int,
    month: int,
    day: int,
    hour: Optional[int] = None,
    minute: int = 0,
    gender: str = "M",
    date: Optional[str] = None,
):
    """오늘의 매매 기운."""
    saju = _calc_saju_for_user(year, month, day, hour, minute)

    if date:
        parts = date.split("-")
        target = datetime(int(parts[0]), int(parts[1]), int(parts[2]), 12)
    else:
        target = datetime.now().replace(hour=12, minute=0, second=0, microsecond=0)

    fortune = generate_daily_fortune(saju, target)
    iljin_stem = fortune.day_pillar_today[0] if fortune.day_pillar_today else ""
    iljin_branch = fortune.day_pillar_today[1] if len(fortune.day_pillar_today) > 1 else ""
    return {
        "date": fortune.date,
        "scores": {
            "judgment": fortune.judgment_score,
            "action": fortune.execution_score,
            "patience": fortune.patience_score,
        },
        "coaching": fortune.coaching,
        "caution": fortune.caution,
        "detail": fortune.detail,
        "shinsal_messages": fortune.shinsal_messages,
        "relation_messages": fortune.relation_messages,
        "iljin_stem": iljin_stem,
        "iljin_branch": iljin_branch,
        "iljin_element": _element_kr(iljin_stem),
    }


@router.get("/api/saju/yearly")
def saju_yearly(
    year: int,
    month: int,
    day: int,
    hour: Optional[int] = None,
    minute: int = 0,
    gender: str = "M",
    target_year: Optional[int] = None,
):
    """올해 세운/대운 투자 흐름 해설."""
    saju = _calc_saju_for_user(year, month, day, hour, minute)
    calc = get_saju_calculator()
    now = datetime.now()
    ty = target_year or now.year

    target = datetime(ty, now.month, now.day, 12)
    context = compute_sewoon_wolwoon_ilji(calc, target)

    sewoon_pillar = context["sewoon"]
    sewoon_stem = sewoon_pillar[0] if sewoon_pillar else ""
    day_stem = saju["day_stem"]
    sewoon_tg = ten_god_for_stem(day_stem, sewoon_stem)

    group_map = {
        "비견": "비겁", "겁재": "비겁",
        "식신": "식상", "상관": "식상",
        "편재": "재성", "정재": "재성",
        "편관": "관성", "정관": "관성",
        "편인": "인성", "정인": "인성",
    }

    h = hour if hour is not None else 0
    birth_dt = datetime(year, month, day, h, minute)
    daeun_data = compute_daeun(
        calc.data, birth_dt,
        saju["year_pillar"], saju["month_pillar"], gender,
    )

    current_daeun = None
    age = ty - year
    for d in daeun_data.get("daeun", []):
        if d["start_age"] <= age < d["end_age"]:
            current_daeun = d
            break

    sewoon_branch = sewoon_pillar[1] if len(sewoon_pillar) > 1 else ""

    daeun_stem_val = ""
    daeun_branch_val = ""
    daeun_start = 0
    daeun_desc = ""
    if current_daeun:
        daeun_stem_val = current_daeun["stem"]
        daeun_pillar = current_daeun["pillar"]
        daeun_branch_val = daeun_pillar[1] if len(daeun_pillar) > 1 else ""
        daeun_tg = ten_god_for_stem(day_stem, daeun_stem_val)
        daeun_group = group_map.get(daeun_tg, "비겁")
        daeun_start = int(current_daeun["start_age"])
        daeun_desc = DAEUN_TEMPLATES.get(daeun_group, "")

    return {
        "year": ty,
        "sewoon_stem": sewoon_stem,
        "sewoon_branch": sewoon_branch,
        "sewoon_element": _element_kr(sewoon_stem),
        "yearly_outlook": SEWOON_TEMPLATES.get(sewoon_tg, ""),
        "monthly_tips": [],
        "daeun_stem": daeun_stem_val,
        "daeun_branch": daeun_branch_val,
        "daeun_element": _element_kr(daeun_stem_val),
        "daeun_start_age": daeun_start,
        "daeun_description": daeun_desc,
    }


@router.post("/api/saju/report")
async def saju_report(req: ReportRequest):
    """사주 기반 투자 감정서 생성."""
    if not _has_anthropic_key():
        raise HTTPException(status_code=503, detail="감정서 서비스 준비 중입니다")

    now_year = datetime.now().year
    hour_str = f"{req.hour:02d}" if req.hour is not None else "00"
    report_id = f"rpt_{req.year}{req.month:02d}{req.day:02d}{hour_str}{req.gender}_{now_year}"

    try:
        context = collect_report_context(
            req.year, req.month, req.day,
            req.hour, req.gender, now_year,
        )
        tier = req.tier if req.tier in ("standard", "premium") else "standard"
        sections = await generate_report(context, tier=tier)
    except ValueError:
        raise HTTPException(status_code=502, detail="감정서 생성 중 오류가 발생했습니다")
    except anthropic.APITimeoutError:
        raise HTTPException(
            status_code=504,
            detail="감정서 생성 시간이 초과되었습니다. 잠시 후 다시 시도해주세요",
        )
    except Exception:
        raise HTTPException(status_code=502, detail="감정서 생성 중 오류가 발생했습니다")

    redacted = []
    for sec in sections:
        if sec["id"] <= 2:
            redacted.append({**sec, "locked": False})
        else:
            redacted.append({
                "id": sec["id"],
                "title": sec["title"],
                "highlight": sec["highlight"],
                "content": "",
                "locked": True,
            })

    return {
        "report_id": report_id,
        "target_year": now_year,
        "tier": tier,
        "sections": redacted,
    }

"""일일 투자 운세 — 일진 × 명식 → 매매기운 점수 + 코칭 메시지."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from sajucandle.manseryeok.core import get_saju_calculator
from sajucandle.saju.tengod import ten_god_for_stem
from sajucandle.saju.relations import pillar_compat_score
from sajucandle.saju.shinsal import find_shinsal
from sajucandle.saju.sewoon import compute_sewoon_wolwoon_ilji
from sajucandle.saju.fortune_templates import (
    TENGOD_COACHING,
    SHINSAL_MESSAGES,
    RELATION_MESSAGES,
)


@dataclass
class DailyFortune:
    date: str
    day_pillar_today: str
    tengod_label: str
    judgment_score: int
    execution_score: int
    patience_score: int
    coaching: str
    caution: str
    detail: str
    shinsal_messages: list[str] = field(default_factory=list)
    relation_messages: list[str] = field(default_factory=list)


_BASE_SCORES: dict[str, dict[str, int]] = {
    "비견": {"judgment": 50, "execution": 60, "patience": 50},
    "겁재": {"judgment": 40, "execution": 70, "patience": 30},
    "식신": {"judgment": 60, "execution": 50, "patience": 60},
    "상관": {"judgment": 55, "execution": 65, "patience": 35},
    "편재": {"judgment": 55, "execution": 75, "patience": 40},
    "정재": {"judgment": 60, "execution": 45, "patience": 75},
    "편관": {"judgment": 70, "execution": 70, "patience": 40},
    "정관": {"judgment": 75, "execution": 55, "patience": 70},
    "편인": {"judgment": 65, "execution": 35, "patience": 70},
    "정인": {"judgment": 70, "execution": 40, "patience": 80},
}


def generate_daily_fortune(saju: dict, target_dt: datetime) -> DailyFortune:
    """명식 × 오늘 일진 → 일일 투자 운세 생성."""
    calc = get_saju_calculator()
    context = compute_sewoon_wolwoon_ilji(calc, target_dt)
    today_pillar = context["ilji"]
    today_stem = today_pillar[0] if today_pillar else ""

    day_stem = saju["day_stem"]
    tengod = ten_god_for_stem(day_stem, today_stem) if today_stem else "비견"

    template = TENGOD_COACHING.get(tengod, TENGOD_COACHING["비견"])
    base = _BASE_SCORES.get(tengod, _BASE_SCORES["비견"])

    compat = pillar_compat_score(saju["day_pillar"], today_pillar)
    adj = max(-20, min(20, compat["total"] // 2))

    judgment = max(0, min(100, base["judgment"] + adj))
    execution = max(0, min(100, base["execution"] + adj))
    patience = max(0, min(100, base["patience"] - adj))

    today_saju = calc.calculate_saju(
        target_dt.year, target_dt.month, target_dt.day, 12,
    )
    findings = find_shinsal(today_saju)
    shinsal_msgs = []
    for f in findings:
        msg = SHINSAL_MESSAGES.get(f["name"])
        if msg:
            shinsal_msgs.append(msg)

    relation_msgs = []
    for rel in compat.get("pros", []) + compat.get("cons", []):
        rel_type = rel.get("type", "")
        msg = RELATION_MESSAGES.get(rel_type)
        if msg and msg not in relation_msgs:
            relation_msgs.append(msg)

    detail_parts = [template["trading_mood"]]
    if shinsal_msgs:
        detail_parts.append(shinsal_msgs[0])
    if relation_msgs:
        detail_parts.append(relation_msgs[0])

    return DailyFortune(
        date=target_dt.strftime("%Y-%m-%d"),
        day_pillar_today=today_pillar,
        tengod_label=template["label"],
        judgment_score=judgment,
        execution_score=execution,
        patience_score=patience,
        coaching=template["judgment"],
        caution=template["caution"],
        detail=" ".join(detail_parts),
        shinsal_messages=shinsal_msgs,
        relation_messages=relation_msgs,
    )

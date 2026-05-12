"""투자 체질 분류기 — 십신 기반 5유형 분류 + 리스크 점수."""
from __future__ import annotations

from dataclasses import dataclass

from sajucandle.saju.tengod import tengod_distribution
from sajucandle.saju.relations import element_balance
from sajucandle.saju.constants import STEM_ELEMENT


INVESTOR_TYPES: dict[str, str] = {
    "비겁": "독립형",
    "식상": "직감형",
    "재성": "실리형",
    "관성": "원칙형",
    "인성": "분석형",
}

TYPE_DESCRIPTIONS: dict[str, dict[str, str | list[str]]] = {
    "독립형": {
        "description": "자기 판단을 신뢰하는 투자자. 남들이 파는 장에서 사는 역발상에 강하다.",
        "strengths": ["역추세 매매에 강함", "확신이 있으면 흔들리지 않음", "독자적 분석력"],
        "weaknesses": ["손절이 늦을 수 있음", "타인 의견 무시 경향", "과잉 확신 위험"],
    },
    "직감형": {
        "description": "남들이 보지 못하는 기회를 포착하는 투자자. 테마주와 신사업에 민감하다.",
        "strengths": ["트렌드 포착력", "창의적 종목 발굴", "빠른 판단"],
        "weaknesses": ["충동 매매 위험", "분석보다 감에 의존", "수익 실현이 빠름"],
    },
    "실리형": {
        "description": "수익률과 배당에 집중하는 실용적 투자자. 가치투자와 배당주에 적합하다.",
        "strengths": ["수익률 계산 철저", "배당/가치 투자 적합", "현실적 목표 설정"],
        "weaknesses": ["성장주를 놓칠 수 있음", "단기 수익에 집착", "리스크 회피 과다"],
    },
    "원칙형": {
        "description": "룰 기반으로 움직이는 체계적 투자자. 시스템 매매와 리밸런싱에 강하다.",
        "strengths": ["규칙 기반 매매", "감정 통제력", "리밸런싱 준수"],
        "weaknesses": ["유연성 부족", "급변장에서 대응 느림", "과도한 규칙 고집"],
    },
    "분석형": {
        "description": "리서치와 공부를 좋아하는 신중한 투자자. 깊은 분석 후 진입한다.",
        "strengths": ["철저한 리서치", "리스크 관리 우수", "장기 관점 유지"],
        "weaknesses": ["진입 타이밍을 놓침", "과도한 분석 마비", "결단력 부족"],
    },
}

DAY_MASTER_DESCRIPTIONS: dict[str, str] = {
    "甲": "갑목(甲木) 일주 — 곧게 뻗는 큰 나무. 성장주와 장기투자에 적합한 기질.",
    "乙": "을목(乙木) 일주 — 유연한 풀과 덩굴. 시장 변화에 유연하게 적응하는 분산투자형.",
    "丙": "병화(丙火) 일주 — 태양의 기운. 밝고 확신에 찬 매매 스타일. 과열에 주의.",
    "丁": "정화(丁火) 일주 — 촛불의 기운. 섬세한 분석과 집중력. 소수 종목 깊은 분석에 강하다.",
    "戊": "무토(戊土) 일주 — 산의 기운. 묵직하고 흔들리지 않는 투자. 대형 우량주에 적합.",
    "己": "기토(己土) 일주 — 평야의 기운. 균형 잡힌 포트폴리오에 강하다.",
    "庚": "경금(庚金) 일주 — 강철의 기운. 원칙에 강한 가치투자형. 손절이 늦는 경향.",
    "辛": "신금(辛金) 일주 — 보석의 기운. 숨겨진 가치를 찾는 눈. 저평가 종목 발굴에 강하다.",
    "壬": "임수(壬水) 일주 — 큰 바다의 기운. 거시적 관점과 자금 흐름을 읽는 힘.",
    "癸": "계수(癸水) 일주 — 이슬과 비의 기운. 작지만 꾸준한 수익. 적립식 투자에 최적.",
}


@dataclass
class InvestorProfile:
    investor_type: str
    day_master: str
    day_master_element: str
    description: str
    strengths: list[str]
    weaknesses: list[str]
    risk_score: int
    element_distribution: dict[str, int]
    dominant_group: str
    tengod_counts: dict[str, int]


def classify_investor_type(saju: dict) -> InvestorProfile:
    """명식 → 투자 체질 프로필 분류."""
    tengod = tengod_distribution(saju)
    dominant = tengod["dominant_group"]
    investor_type = INVESTOR_TYPES.get(dominant, "분석형")
    type_info = TYPE_DESCRIPTIONS[investor_type]

    pillars = [saju["year_pillar"], saju["month_pillar"], saju["day_pillar"]]
    if saju.get("hour_pillar"):
        pillars.append(saju["hour_pillar"])
    balance = element_balance(pillars)

    balance_score = balance["balance_score"]
    risk_score = max(0, min(100, int((10 - balance_score) * 10)))

    day_stem = saju["day_stem"]
    day_element = STEM_ELEMENT.get(day_stem, "")

    return InvestorProfile(
        investor_type=investor_type,
        day_master=day_stem,
        day_master_element=day_element,
        description=type_info["description"],
        strengths=list(type_info["strengths"]),
        weaknesses=list(type_info["weaknesses"]),
        risk_score=risk_score,
        element_distribution=balance["counts"],
        dominant_group=dominant,
        tengod_counts=tengod["group_counts"],
    )

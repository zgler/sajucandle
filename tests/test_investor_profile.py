"""tests/test_investor_profile.py — 투자 체질 분류기 단위 테스트."""
from __future__ import annotations

import pytest

from sajucandle.saju.investor_profile import (
    InvestorProfile,
    classify_investor_type,
)


# ---------------------------------------------------------------------------
# 테스트용 사주 픽스처
# ---------------------------------------------------------------------------

def _make_saju(
    year_stem: str,
    year_branch: str,
    month_stem: str,
    month_branch: str,
    day_stem: str,
    day_branch: str,
    hour_stem: str = "",
    hour_branch: str = "",
) -> dict:
    """최소 saju dict 생성 헬퍼."""
    return {
        "year_stem": year_stem,
        "year_branch": year_branch,
        "month_stem": month_stem,
        "month_branch": month_branch,
        "day_stem": day_stem,
        "day_branch": day_branch,
        "hour_stem": hour_stem,
        "hour_branch": hour_branch,
        # pillar 형태도 제공 (element_balance 에서 사용)
        "year_pillar": year_stem + year_branch,
        "month_pillar": month_stem + month_branch,
        "day_pillar": day_stem + day_branch,
        "hour_pillar": hour_stem + hour_branch if hour_stem else "",
    }


# ─── 비겁 heavy: 甲木 일간, 연/월/시 모두 木 오행 비겁 ───
# 甲(木陽) 일간 → 비겁=甲(비견)/乙(겁재)
# 연주 甲寅, 월주 乙卯, 일주 甲子, 시주 甲寅
SAJU_BIJUK_HEAVY = _make_saju(
    year_stem="甲", year_branch="寅",
    month_stem="乙", month_branch="卯",
    day_stem="甲", day_branch="子",
    hour_stem="甲", hour_branch="寅",
)

# ─── 식상 heavy: 丙火 일간, 식상=戊(식신)/己(상관) ───
# 연주 戊子, 월주 己丑, 일주 丙午, 시주 己未
SAJU_SIKSANG_HEAVY = _make_saju(
    year_stem="戊", year_branch="子",
    month_stem="己", month_branch="丑",
    day_stem="丙", day_branch="午",
    hour_stem="己", hour_branch="未",
)

# ─── 관성 heavy: 壬水 일간, 관성=戊(편관)/己(정관) → 실제로는 土가 극水 ───
# 연주 戊午, 월주 己未, 일주 壬子, 시주 戊戌
SAJU_GWANSUNG_HEAVY = _make_saju(
    year_stem="戊", year_branch="午",
    month_stem="己", month_branch="未",
    day_stem="壬", day_branch="子",
    hour_stem="戊", hour_branch="戌",
)

# ─── 오행 편중(水 only) → 높은 리스크 점수 ───
# 모든 주가 壬子 — 水 오행만 존재
SAJU_SKEWED = _make_saju(
    year_stem="壬", year_branch="子",
    month_stem="壬", month_branch="子",
    day_stem="壬", day_branch="子",
    hour_stem="壬", hour_branch="子",
)

# ─── 3주 모드 (시주 없음) ───
SAJU_THREE_PILLAR = _make_saju(
    year_stem="甲", year_branch="寅",
    month_stem="甲", month_branch="子",
    day_stem="甲", day_branch="辰",
    # hour 비어 있음
)


# ---------------------------------------------------------------------------
# 기본 반환 구조 테스트
# ---------------------------------------------------------------------------

class TestInvestorProfileStructure:
    def test_returns_investor_profile_instance(self):
        profile = classify_investor_type(SAJU_BIJUK_HEAVY)
        assert isinstance(profile, InvestorProfile)

    def test_all_required_fields_present(self):
        profile = classify_investor_type(SAJU_BIJUK_HEAVY)
        assert isinstance(profile.investor_type, str)
        assert isinstance(profile.day_master, str)
        assert isinstance(profile.day_master_element, str)
        assert isinstance(profile.description, str)
        assert isinstance(profile.strengths, list)
        assert isinstance(profile.weaknesses, list)
        assert isinstance(profile.risk_score, int)
        assert isinstance(profile.element_distribution, dict)
        assert isinstance(profile.dominant_group, str)
        assert isinstance(profile.tengod_counts, dict)

    def test_investor_type_is_valid(self):
        valid_types = {"독립형", "직감형", "실리형", "원칙형", "분석형"}
        for saju in [SAJU_BIJUK_HEAVY, SAJU_SIKSANG_HEAVY, SAJU_GWANSUNG_HEAVY]:
            profile = classify_investor_type(saju)
            assert profile.investor_type in valid_types, (
                f"unexpected type: {profile.investor_type}"
            )

    def test_risk_score_in_range(self):
        for saju in [SAJU_BIJUK_HEAVY, SAJU_SIKSANG_HEAVY, SAJU_SKEWED]:
            profile = classify_investor_type(saju)
            assert 0 <= profile.risk_score <= 100, (
                f"risk_score {profile.risk_score} out of [0, 100]"
            )

    def test_strengths_and_weaknesses_nonempty(self):
        profile = classify_investor_type(SAJU_BIJUK_HEAVY)
        assert len(profile.strengths) > 0
        assert len(profile.weaknesses) > 0


# ---------------------------------------------------------------------------
# 투자 유형 매핑 테스트
# ---------------------------------------------------------------------------

class TestInvestorTypeMapping:
    def test_bijuk_heavy_is_dongnip(self):
        """비겁 dominant → 독립형."""
        profile = classify_investor_type(SAJU_BIJUK_HEAVY)
        assert profile.investor_type == "독립형", (
            f"비겁 heavy saju → 독립형 기대, 실제: {profile.investor_type}"
        )

    def test_dominant_group_bijuk(self):
        profile = classify_investor_type(SAJU_BIJUK_HEAVY)
        assert profile.dominant_group == "비겁"

    def test_siksang_heavy_is_jiggam(self):
        """식상 dominant → 직감형."""
        profile = classify_investor_type(SAJU_SIKSANG_HEAVY)
        assert profile.investor_type == "직감형", (
            f"식상 heavy saju → 직감형 기대, 실제: {profile.investor_type}"
        )

    def test_gwansung_heavy_is_wonchik(self):
        """관성 dominant → 원칙형."""
        profile = classify_investor_type(SAJU_GWANSUNG_HEAVY)
        assert profile.investor_type == "원칙형", (
            f"관성 heavy saju → 원칙형 기대, 실제: {profile.investor_type}"
        )


# ---------------------------------------------------------------------------
# 일간(日干) 및 오행 테스트
# ---------------------------------------------------------------------------

class TestDayMaster:
    def test_day_master_is_day_stem(self):
        profile = classify_investor_type(SAJU_BIJUK_HEAVY)
        assert profile.day_master == "甲"

    def test_day_master_element_wood(self):
        profile = classify_investor_type(SAJU_BIJUK_HEAVY)
        assert profile.day_master_element == "木"

    def test_day_master_element_water(self):
        profile = classify_investor_type(SAJU_SKEWED)
        assert profile.day_master_element == "水"


# ---------------------------------------------------------------------------
# 리스크 점수 테스트
# ---------------------------------------------------------------------------

class TestRiskScore:
    def test_skewed_elements_high_risk(self):
        """오행이 한 곳에 편중 → 리스크 점수 ≥ 60."""
        profile = classify_investor_type(SAJU_SKEWED)
        assert profile.risk_score >= 60, (
            f"편중 사주 → risk_score ≥ 60 기대, 실제: {profile.risk_score}"
        )

    def test_risk_score_is_int(self):
        profile = classify_investor_type(SAJU_BIJUK_HEAVY)
        assert isinstance(profile.risk_score, int)


# ---------------------------------------------------------------------------
# 3주 모드 테스트
# ---------------------------------------------------------------------------

class TestThreePillarMode:
    def test_three_pillar_works(self):
        """시주 없는 3주 모드에서도 정상 동작."""
        profile = classify_investor_type(SAJU_THREE_PILLAR)
        assert isinstance(profile, InvestorProfile)
        assert profile.investor_type in {"독립형", "직감형", "실리형", "원칙형", "분석형"}

    def test_three_pillar_day_master(self):
        profile = classify_investor_type(SAJU_THREE_PILLAR)
        assert profile.day_master == "甲"
        assert profile.day_master_element == "木"

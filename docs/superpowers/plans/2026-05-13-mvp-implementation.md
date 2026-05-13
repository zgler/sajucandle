# 사주캔들 MVP 구현 플랜

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 투자 특화 사주 웹앱 1단계 MVP — 온보딩(투자 체질 프로필) + 매일 운세 피드 + 카카오톡 공유

**Architecture:** FastAPI 백엔드에 신규 운세 API 3개를 추가하고, Next.js 프론트엔드를 새로 구축한다. 기존 사주 엔진(`manseryeok/core.py`, `saju/*`)을 그대로 활용하며, 신규 모듈 2개(`investor_profile.py`, `daily_fortune.py`)와 텍스트 템플릿을 추가한다. 유저 데이터는 localStorage에 저장하고 서버 DB는 사용하지 않는다.

**Tech Stack:** Python 3.12 / FastAPI / Next.js 15 (App Router, SSR) / TypeScript / Tailwind CSS

**Spec:** `docs/superpowers/specs/2026-05-13-app-pivot-design.md`

---

## 파일 구조

### 백엔드 신규/수정

| 파일 | 역할 |
|---|---|
| Create: `src/sajucandle/saju/investor_profile.py` | 투자 체질 분류기 — 명식 → 5유형 분류 + 해설 |
| Create: `src/sajucandle/saju/daily_fortune.py` | 일일 투자 운세 — 일진 × 명식 → 매매기운 + 해설 |
| Create: `src/sajucandle/saju/fortune_templates.py` | 운세 텍스트 템플릿 (십신별 투자 코칭) |
| Modify: `src/sajucandle/api/main.py` | 신규 엔드포인트 3개 추가 + CORS 설정 |
| Create: `tests/test_investor_profile.py` | 투자 체질 분류기 테스트 |
| Create: `tests/test_daily_fortune.py` | 일일 투자 운세 테스트 |
| Create: `tests/test_api_saju.py` | 신규 API 엔드포인트 테스트 |

### 프론트엔드 신규

| 파일 | 역할 |
|---|---|
| `frontend/package.json` | Next.js + 의존성 |
| `frontend/tailwind.config.ts` | Tailwind 설정 (오행 색상 팔레트) |
| `frontend/src/app/layout.tsx` | 루트 레이아웃 (메타데이터, 폰트) |
| `frontend/src/app/page.tsx` | 메인 페이지 (온보딩 or 피드 분기) |
| `frontend/src/app/feed/page.tsx` | 매일 운세 피드 |
| `frontend/src/app/profile/page.tsx` | 내 투자 사주 프로필 |
| `frontend/src/app/card/[id]/page.tsx` | 공유 카드 랜딩 페이지 |
| `frontend/src/app/card/[id]/opengraph-image.tsx` | og:image 동적 생성 |
| `frontend/src/components/OnboardingForm.tsx` | 생년월일 입력 폼 |
| `frontend/src/components/ProfileCard.tsx` | 투자 체질 카드 |
| `frontend/src/components/DailyFortune.tsx` | 오늘의 매매 기운 카드 |
| `frontend/src/components/FortuneDetail.tsx` | 명리 해설 섹션 |
| `frontend/src/components/PillarChart.tsx` | 사주 4주 시각화 |
| `frontend/src/components/ElementBar.tsx` | 오행 분포 바 차트 |
| `frontend/src/lib/api.ts` | FastAPI 호출 클라이언트 |
| `frontend/src/lib/storage.ts` | localStorage 유저 데이터 관리 |
| `frontend/src/lib/types.ts` | TypeScript 타입 정의 |
| `frontend/src/lib/kakao.ts` | 카카오 SDK 공유 래퍼 |
| `frontend/src/lib/constants.ts` | 오행 색상, 천간/지지 한글 매핑 |

---

## Task 1: 투자 체질 분류기 — 테스트 + 구현

**Files:**
- Create: `src/sajucandle/saju/investor_profile.py`
- Create: `tests/test_investor_profile.py`

- [ ] **Step 1: 테스트 파일 작성**

```python
# tests/test_investor_profile.py
from __future__ import annotations

import pytest
from sajucandle.saju.investor_profile import classify_investor_type, InvestorProfile


class TestClassifyInvestorType:
    """투자 체질 분류기 테스트."""

    def test_returns_investor_profile(self):
        """분류 결과가 InvestorProfile 타입이다."""
        saju = {
            "year_pillar": "甲辰", "month_pillar": "丙寅",
            "day_pillar": "庚午", "hour_pillar": "戊寅",
            "year_stem": "甲", "year_branch": "辰",
            "month_stem": "丙", "month_branch": "寅",
            "day_stem": "庚", "day_branch": "午",
            "hour_stem": "戊", "hour_branch": "寅",
        }
        result = classify_investor_type(saju)
        assert isinstance(result, InvestorProfile)

    def test_profile_has_required_fields(self):
        """프로필에 필수 필드가 모두 있다."""
        saju = {
            "year_pillar": "甲辰", "month_pillar": "丙寅",
            "day_pillar": "庚午", "hour_pillar": "戊寅",
            "year_stem": "甲", "year_branch": "辰",
            "month_stem": "丙", "month_branch": "寅",
            "day_stem": "庚", "day_branch": "午",
            "hour_stem": "戊", "hour_branch": "寅",
        }
        result = classify_investor_type(saju)
        assert result.investor_type in ("독립형", "직감형", "실리형", "원칙형", "분석형")
        assert 0 <= result.risk_score <= 100
        assert len(result.description) > 0
        assert len(result.strengths) > 0
        assert len(result.weaknesses) > 0
        assert result.day_master != ""

    def test_dominant_bigyeop_yields_independent(self):
        """비겁이 강하면 독립형이 나온다."""
        # 庚일간 + 庚(비견)이 많은 사주
        saju = {
            "year_pillar": "庚申", "month_pillar": "庚辰",
            "day_pillar": "庚午", "hour_pillar": "庚寅",
            "year_stem": "庚", "year_branch": "申",
            "month_stem": "庚", "month_branch": "辰",
            "day_stem": "庚", "day_branch": "午",
            "hour_stem": "庚", "hour_branch": "寅",
        }
        result = classify_investor_type(saju)
        assert result.investor_type == "독립형"

    def test_element_balance_affects_risk(self):
        """오행 분포가 편중되면 리스크 점수가 높다."""
        # 금(金)에 편중된 사주
        saju_skewed = {
            "year_pillar": "庚申", "month_pillar": "辛酉",
            "day_pillar": "庚申", "hour_pillar": "辛酉",
            "year_stem": "庚", "year_branch": "申",
            "month_stem": "辛", "month_branch": "酉",
            "day_stem": "庚", "day_branch": "申",
            "hour_stem": "辛", "hour_branch": "酉",
        }
        result_skewed = classify_investor_type(saju_skewed)
        # 편중 → 공격적 → 리스크 점수 높음
        assert result_skewed.risk_score >= 60

    def test_three_pillar_mode(self):
        """시주 없이 3주로도 분류할 수 있다."""
        saju = {
            "year_pillar": "甲辰", "month_pillar": "丙寅",
            "day_pillar": "庚午", "hour_pillar": "",
            "year_stem": "甲", "year_branch": "辰",
            "month_stem": "丙", "month_branch": "寅",
            "day_stem": "庚", "day_branch": "午",
            "hour_stem": "", "hour_branch": "",
        }
        result = classify_investor_type(saju)
        assert result.investor_type in ("독립형", "직감형", "실리형", "원칙형", "분석형")
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

Run: `PYTHONPATH=src ./.venv/Scripts/python.exe -m pytest tests/test_investor_profile.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sajucandle.saju.investor_profile'`

- [ ] **Step 3: investor_profile.py 구현**

```python
# src/sajucandle/saju/investor_profile.py
from __future__ import annotations

from dataclasses import dataclass

from sajucandle.saju.tengod import tengod_distribution
from sajucandle.saju.relations import element_balance
from sajucandle.saju.constants import STEM_ELEMENT


INVESTOR_TYPES = {
    "비겁": "독립형",
    "식상": "직감형",
    "재성": "실리형",
    "관성": "원칙형",
    "인성": "분석형",
}

TYPE_DESCRIPTIONS = {
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

    pillars = [
        saju["year_pillar"], saju["month_pillar"], saju["day_pillar"],
    ]
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
        strengths=type_info["strengths"],
        weaknesses=type_info["weaknesses"],
        risk_score=risk_score,
        element_distribution=balance["counts"],
        dominant_group=dominant,
        tengod_counts=tengod["group_counts"],
    )
```

- [ ] **Step 4: 테스트 실행 — 통과 확인**

Run: `PYTHONPATH=src ./.venv/Scripts/python.exe -m pytest tests/test_investor_profile.py -v`
Expected: 5 passed

- [ ] **Step 5: 커밋**

```bash
git add src/sajucandle/saju/investor_profile.py tests/test_investor_profile.py
git commit -m "feat(saju): 투자 체질 분류기 — 십신 기반 5유형 분류 + 리스크 점수"
```

---

## Task 2: 운세 텍스트 템플릿

**Files:**
- Create: `src/sajucandle/saju/fortune_templates.py`

- [ ] **Step 1: 템플릿 모듈 작성**

```python
# src/sajucandle/saju/fortune_templates.py
from __future__ import annotations

TENGOD_COACHING: dict[str, dict[str, str]] = {
    "비견": {
        "label": "비견(比肩)의 날",
        "trading_mood": "동료 투자자와 보조를 맞추는 기운. 독단보다 협력이 유리한 날.",
        "judgment": "내 판단을 고집하기보다 시장 컨센서스를 참고하라.",
        "caution": "경쟁심에 무리한 추격 매수를 조심.",
    },
    "겁재": {
        "label": "겁재(劫財)의 날",
        "trading_mood": "기회를 뺏길까 조급해지는 기운. 침착함이 무기인 날.",
        "judgment": "FOMO에 휘둘리지 마라. 놓친 종목은 다시 온다.",
        "caution": "충동 매수와 과도한 레버리지를 경계.",
    },
    "식신": {
        "label": "식신(食神)의 날",
        "trading_mood": "여유롭고 창의적인 기운. 새로운 종목 탐색에 좋은 날.",
        "judgment": "분석보다 직관이 빛나는 날. 평소 관심 없던 섹터를 살펴보라.",
        "caution": "기분에 취해 포지션을 너무 키우지 마라.",
    },
    "상관": {
        "label": "상관(傷官)의 날",
        "trading_mood": "기존 질서에 반발하는 기운. 역발상 아이디어가 떠오르는 날.",
        "judgment": "대세에 반하는 포지션이 빛날 수 있으나, 확신 없으면 관망.",
        "caution": "반항심에 손절 규칙까지 무시하지 마라.",
    },
    "편재": {
        "label": "편재(偏財)의 날",
        "trading_mood": "단기 수익 기회가 보이는 기운. 트레이딩에 유리한 날.",
        "judgment": "빠른 매매에 감이 살아있다. 단, 욕심은 금물.",
        "caution": "큰 한방을 노리다 원금까지 잃을 수 있다.",
    },
    "정재": {
        "label": "정재(正財)의 날",
        "trading_mood": "꾸준한 적립과 배당이 빛나는 기운. 안정 추구의 날.",
        "judgment": "급등주보다 우량주 적립이 길한 날.",
        "caution": "지나친 안전 추구로 기회를 놓치지 마라.",
    },
    "편관": {
        "label": "편관(偏官)의 날",
        "trading_mood": "과감한 결단이 필요한 기운. 변화와 도전의 날.",
        "judgment": "묵은 포지션 정리나 새 진입에 적합. 우유부단이 적.",
        "caution": "과감함과 무모함은 다르다. 레버리지 조심.",
    },
    "정관": {
        "label": "정관(正官)의 날",
        "trading_mood": "질서와 원칙의 기운. 계획대로 실행하기 좋은 날.",
        "judgment": "정해둔 리밸런싱 규칙을 따르라. 즉흥은 흉.",
        "caution": "규칙에 매몰되어 급변하는 시장을 무시하지 마라.",
    },
    "편인": {
        "label": "편인(偏印)의 날",
        "trading_mood": "깊은 통찰의 기운. 리서치와 공부에 최적인 날.",
        "judgment": "매매보다 분석에 시간을 쓰라. 오늘 공부한 것이 내일의 수익.",
        "caution": "분석 마비(analysis paralysis)에 빠지지 마라.",
    },
    "정인": {
        "label": "정인(正印)의 날",
        "trading_mood": "차분한 내면의 기운. 장기 관점으로 돌아보기 좋은 날.",
        "judgment": "단기 등락에 흔들리지 마라. 큰 그림을 봐라.",
        "caution": "신중함이 지나쳐 매수 타이밍을 놓칠 수 있다.",
    },
}

SHINSAL_MESSAGES: dict[str, str] = {
    "천을귀인": "귀인의 기운이 감돈다. 뜻밖의 정보나 도움이 올 수 있는 날.",
    "삼기": "세 가지 기운이 모이는 길한 날. 중요한 투자 결정에 적합.",
    "천덕귀인": "하늘의 덕이 있는 날. 위험한 상황에서도 손실이 줄어드는 기운.",
    "월덕귀인": "달의 덕이 있는 날. 매매 실수가 나더라도 만회할 기운.",
    "문창귀인": "학문의 기운. 투자 리서치와 보고서 분석에 집중하면 좋은 날.",
    "금여": "금여록의 날. 재물이 들어오는 기운이 있으나 교만은 금물.",
    "도화살": "매력과 유혹의 기운. 화려한 테마주에 끌리기 쉬우니 냉정하게.",
    "역마살": "변동과 이동의 기운. 해외 주식이나 새로운 시장에 관심이 가는 날.",
    "화개살": "고독한 수행의 기운. 남의 말보다 자기 분석을 믿으라.",
    "백호살": "강렬한 변동의 기운. 큰 수익과 큰 손실 모두 가능. 포지션 사이즈를 줄여라.",
    "괴강살": "극단적 결단의 기운. 올인은 위험하다. 분산 투자를 고수하라.",
    "양인살": "날카로운 기운. 단타에 감이 살아나지만 과욕은 화를 부른다.",
}

RELATION_MESSAGES: dict[str, str] = {
    "천간합": "천간이 합하는 날. 시장과 호흡이 맞는 기운. 매매에 순풍.",
    "천간충": "천간이 충하는 날. 내 판단과 시장이 엇갈릴 수 있다. 신중하게.",
    "육합": "지지가 합하는 날. 안정적인 기운. 보유 종목이 빛나는 날.",
    "삼합": "삼합의 기운. 큰 흐름에 올라탈 수 있는 날. 추세 매매에 유리.",
    "반합": "반합의 기운. 절반의 순풍. 소규모 매매가 적합.",
    "충": "지지가 충하는 날. 급변동 가능. 스톱로스를 반드시 설정하라.",
    "형": "형(刑)의 기운. 예상치 못한 악재에 주의. 방어적 포지션 권장.",
    "파": "파(破)의 기운. 깨지는 기운. 기대한 수익이 무너질 수 있다.",
    "해": "해(害)의 기운. 숨겨진 리스크에 주의. 겉으로 좋아 보이는 종목을 조심.",
}

SEWOON_TEMPLATES: dict[str, str] = {
    "비견": "올해는 비견의 해. 경쟁이 치열하지만 자기 실력이 빛나는 시기. 독자적 투자 전략을 세우라.",
    "겁재": "올해는 겁재의 해. 재물이 빠져나가기 쉬운 시기. 공격보다 수비, 저축과 안전자산 비중을 높여라.",
    "식신": "올해는 식신의 해. 새로운 투자 아이디어가 넘치는 시기. 소액 다양한 시도가 길하다.",
    "상관": "올해는 상관의 해. 기존 포트폴리오를 뒤집고 싶은 충동이 올 수 있다. 전면 교체보다 점진적 조정.",
    "편재": "올해는 편재의 해. 단기 수익 기회가 많은 시기. 단, 한 곳에 몰빵은 흉.",
    "정재": "올해는 정재의 해. 꾸준한 적립과 배당 수익이 쌓이는 시기. 급등주 욕심은 접어라.",
    "편관": "올해는 편관의 해. 큰 변화와 도전의 시기. 커리어 전환이 투자 전략도 바꿀 수 있다.",
    "정관": "올해는 정관의 해. 원칙과 규율이 수익으로 이어지는 시기. 시스템 매매가 빛난다.",
    "편인": "올해는 편인의 해. 투자 공부에 최적의 시기. 올해 배운 것이 내년 수익의 씨앗.",
    "정인": "올해는 정인의 해. 차분하게 장기 관점을 잡는 시기. 10년 후를 보고 포트폴리오를 짜라.",
}

DAEUN_TEMPLATES: dict[str, str] = {
    "비겁": "현재 대운은 비겁. 자기 힘으로 돌파해야 하는 국면. 남에게 의존하지 말고 실력을 키워라.",
    "식상": "현재 대운은 식상. 표현과 창조의 국면. 새로운 투자 전략을 실험하기 좋은 시기.",
    "재성": "현재 대운은 재성. 재물이 들어오는 국면. 적극적 투자가 보상받는 시기.",
    "관성": "현재 대운은 관성. 시스템과 규율의 국면. 무리한 투자보다 안정적 운용이 길하다.",
    "인성": "현재 대운은 인성. 학습과 성장의 국면. 수익보다 실력을 쌓는 데 집중하라.",
}

DAY_MASTER_DESCRIPTIONS: dict[str, str] = {
    "甲": "갑목(甲木) 일주 — 곧게 뻗는 큰 나무. 성장주와 장기투자에 적합한 기질. 꺾이면 회복이 어렵다.",
    "乙": "을목(乙木) 일주 — 유연한 풀과 덩굴. 시장 변화에 유연하게 적응. 분산투자에 강하다.",
    "丙": "병화(丙火) 일주 — 태양의 기운. 밝고 확신에 찬 매매 스타일. 과열에 주의.",
    "丁": "정화(丁火) 일주 — 촛불의 기운. 섬세한 분석과 집중력. 소수 종목 깊은 분석에 강하다.",
    "戊": "무토(戊土) 일주 — 산의 기운. 묵직하고 흔들리지 않는 투자. 대형 우량주에 적합.",
    "己": "기토(己土) 일주 — 평야의 기운. 균형 잡힌 포트폴리오에 강하다. 다양한 자산 배분에 유리.",
    "庚": "경금(庚金) 일주 — 강철의 기운. 원칙에 강한 가치투자형. 손절이 늦는 경향.",
    "辛": "신금(辛金) 일주 — 보석의 기운. 숨겨진 가치를 찾는 눈. 저평가 종목 발굴에 강하다.",
    "壬": "임수(壬水) 일주 — 큰 바다의 기운. 거시적 관점과 자금 흐름을 읽는 힘. 매크로 투자에 강하다.",
    "癸": "계수(癸水) 일주 — 이슬과 비의 기운. 작지만 꾸준한 수익. 적립식 투자에 최적.",
}
```

- [ ] **Step 2: 커밋**

```bash
git add src/sajucandle/saju/fortune_templates.py
git commit -m "feat(saju): 투자 운세 텍스트 템플릿 — 십신·신살·세운·대운 코칭 메시지"
```

---

## Task 3: 일일 투자 운세 생성기 — 테스트 + 구현

**Files:**
- Create: `src/sajucandle/saju/daily_fortune.py`
- Create: `tests/test_daily_fortune.py`

- [ ] **Step 1: 테스트 파일 작성**

```python
# tests/test_daily_fortune.py
from __future__ import annotations

from datetime import datetime

import pytest
from sajucandle.saju.daily_fortune import generate_daily_fortune, DailyFortune


@pytest.fixture
def sample_saju() -> dict:
    return {
        "year_pillar": "甲辰", "month_pillar": "丙寅",
        "day_pillar": "庚午", "hour_pillar": "戊寅",
        "year_stem": "甲", "year_branch": "辰",
        "month_stem": "丙", "month_branch": "寅",
        "day_stem": "庚", "day_branch": "午",
        "hour_stem": "戊", "hour_branch": "寅",
    }


class TestGenerateDailyFortune:
    """일일 투자 운세 생성 테스트."""

    def test_returns_daily_fortune(self, sample_saju: dict):
        result = generate_daily_fortune(sample_saju, datetime(2026, 5, 13))
        assert isinstance(result, DailyFortune)

    def test_has_three_scores(self, sample_saju: dict):
        result = generate_daily_fortune(sample_saju, datetime(2026, 5, 13))
        assert 0 <= result.judgment_score <= 100
        assert 0 <= result.execution_score <= 100
        assert 0 <= result.patience_score <= 100

    def test_has_coaching_text(self, sample_saju: dict):
        result = generate_daily_fortune(sample_saju, datetime(2026, 5, 13))
        assert len(result.tengod_label) > 0
        assert len(result.coaching) > 0
        assert len(result.caution) > 0
        assert len(result.detail) > 0

    def test_different_dates_yield_different_results(self, sample_saju: dict):
        r1 = generate_daily_fortune(sample_saju, datetime(2026, 5, 13))
        r2 = generate_daily_fortune(sample_saju, datetime(2026, 5, 14))
        assert r1.tengod_label != r2.tengod_label or r1.judgment_score != r2.judgment_score

    def test_has_shinsal_messages(self, sample_saju: dict):
        result = generate_daily_fortune(sample_saju, datetime(2026, 5, 13))
        assert isinstance(result.shinsal_messages, list)

    def test_has_relation_summary(self, sample_saju: dict):
        result = generate_daily_fortune(sample_saju, datetime(2026, 5, 13))
        assert isinstance(result.relation_messages, list)
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

Run: `PYTHONPATH=src ./.venv/Scripts/python.exe -m pytest tests/test_daily_fortune.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: daily_fortune.py 구현**

```python
# src/sajucandle/saju/daily_fortune.py
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


SCORE_MAP = {
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
    base_scores = SCORE_MAP.get(tengod, SCORE_MAP["비견"])

    compat = pillar_compat_score(saju["day_pillar"], today_pillar)
    score_adj = max(-20, min(20, compat["total"] // 2))

    judgment = max(0, min(100, base_scores["judgment"] + score_adj))
    execution = max(0, min(100, base_scores["execution"] + score_adj))
    patience = max(0, min(100, base_scores["patience"] - score_adj))

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
```

- [ ] **Step 4: 테스트 실행 — 통과 확인**

Run: `PYTHONPATH=src ./.venv/Scripts/python.exe -m pytest tests/test_daily_fortune.py -v`
Expected: 6 passed

- [ ] **Step 5: 커밋**

```bash
git add src/sajucandle/saju/daily_fortune.py tests/test_daily_fortune.py
git commit -m "feat(saju): 일일 투자 운세 생성기 — 매매기운 점수 + 코칭 메시지"
```

---

## Task 4: FastAPI 신규 엔드포인트

**Files:**
- Modify: `src/sajucandle/api/main.py`
- Create: `tests/test_api_saju.py`

- [ ] **Step 1: API 테스트 작성**

```python
# tests/test_api_saju.py
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sajucandle.api.main import app


@pytest.fixture
def client():
    return TestClient(app)


class TestProfileEndpoint:
    """POST /api/saju/profile 테스트."""

    def test_profile_returns_200(self, client: TestClient):
        resp = client.post("/api/saju/profile", json={
            "year": 1985, "month": 3, "day": 15,
            "hour": 14, "gender": "M",
        })
        assert resp.status_code == 200

    def test_profile_response_shape(self, client: TestClient):
        resp = client.post("/api/saju/profile", json={
            "year": 1985, "month": 3, "day": 15,
            "hour": 14, "gender": "M",
        })
        data = resp.json()
        assert "investor_type" in data
        assert "day_master" in data
        assert "saju" in data
        assert "element_distribution" in data
        assert "description" in data

    def test_profile_without_hour(self, client: TestClient):
        resp = client.post("/api/saju/profile", json={
            "year": 1985, "month": 3, "day": 15,
            "gender": "F",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["saju"]["hour_pillar"] == ""


class TestDailyEndpoint:
    """GET /api/saju/daily 테스트."""

    def test_daily_returns_200(self, client: TestClient):
        resp = client.get("/api/saju/daily", params={
            "year": 1985, "month": 3, "day": 15,
            "hour": 14, "gender": "M",
        })
        assert resp.status_code == 200

    def test_daily_response_shape(self, client: TestClient):
        resp = client.get("/api/saju/daily", params={
            "year": 1985, "month": 3, "day": 15,
            "hour": 14, "gender": "M",
        })
        data = resp.json()
        assert "judgment_score" in data
        assert "execution_score" in data
        assert "patience_score" in data
        assert "tengod_label" in data
        assert "coaching" in data

    def test_daily_with_specific_date(self, client: TestClient):
        resp = client.get("/api/saju/daily", params={
            "year": 1985, "month": 3, "day": 15,
            "hour": 14, "gender": "M",
            "date": "2026-05-13",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["date"] == "2026-05-13"


class TestYearlyEndpoint:
    """GET /api/saju/yearly 테스트."""

    def test_yearly_returns_200(self, client: TestClient):
        resp = client.get("/api/saju/yearly", params={
            "year": 1985, "month": 3, "day": 15,
            "hour": 14, "gender": "M",
        })
        assert resp.status_code == 200

    def test_yearly_response_shape(self, client: TestClient):
        resp = client.get("/api/saju/yearly", params={
            "year": 1985, "month": 3, "day": 15,
            "hour": 14, "gender": "M",
        })
        data = resp.json()
        assert "sewoon_pillar" in data
        assert "sewoon_tengod" in data
        assert "sewoon_message" in data
        assert "daeun" in data
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

Run: `PYTHONPATH=src ./.venv/Scripts/python.exe -m pytest tests/test_api_saju.py -v`
Expected: FAIL — endpoint not found (404)

- [ ] **Step 3: main.py에 엔드포인트 추가**

`src/sajucandle/api/main.py` 끝에 추가:

```python
# --- 신규 사주 운세 API (MVP) ---

from pydantic import BaseModel as _BaseModel
from sajucandle.saju.investor_profile import classify_investor_type
from sajucandle.saju.daily_fortune import generate_daily_fortune
from sajucandle.saju.fortune_templates import (
    SEWOON_TEMPLATES,
    DAEUN_TEMPLATES,
    DAY_MASTER_DESCRIPTIONS,
)
from sajucandle.saju.tengod import ten_god_for_stem
from sajucandle.saju.daeun import compute_daeun


class ProfileRequest(_BaseModel):
    year: int
    month: int
    day: int
    hour: int | None = None
    minute: int = 0
    gender: str = "M"


@app.post("/api/saju/profile")
def saju_profile(req: ProfileRequest):
    calc = get_saju_calculator()
    hour = req.hour if req.hour is not None else 0
    saju = calc.calculate_saju(req.year, req.month, req.day, hour, req.minute)

    if req.hour is None:
        saju["hour_pillar"] = ""
        saju["hour_stem"] = ""
        saju["hour_branch"] = ""

    profile = classify_investor_type(saju)

    return {
        "saju": {
            "year_pillar": saju["year_pillar"],
            "month_pillar": saju["month_pillar"],
            "day_pillar": saju["day_pillar"],
            "hour_pillar": saju.get("hour_pillar", ""),
        },
        "day_master": profile.day_master,
        "day_master_element": profile.day_master_element,
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


@app.get("/api/saju/daily")
def saju_daily(
    year: int,
    month: int,
    day: int,
    hour: int | None = None,
    minute: int = 0,
    gender: str = "M",
    date: str | None = None,
):
    calc = get_saju_calculator()
    h = hour if hour is not None else 0
    saju = calc.calculate_saju(year, month, day, h, minute)

    if hour is None:
        saju["hour_pillar"] = ""
        saju["hour_stem"] = ""
        saju["hour_branch"] = ""

    if date:
        parts = date.split("-")
        target = datetime(int(parts[0]), int(parts[1]), int(parts[2]), 12)
    else:
        target = datetime.now().replace(hour=12, minute=0, second=0, microsecond=0)

    fortune = generate_daily_fortune(saju, target)

    return {
        "date": fortune.date,
        "day_pillar_today": fortune.day_pillar_today,
        "tengod_label": fortune.tengod_label,
        "judgment_score": fortune.judgment_score,
        "execution_score": fortune.execution_score,
        "patience_score": fortune.patience_score,
        "coaching": fortune.coaching,
        "caution": fortune.caution,
        "detail": fortune.detail,
        "shinsal_messages": fortune.shinsal_messages,
        "relation_messages": fortune.relation_messages,
    }


@app.get("/api/saju/yearly")
def saju_yearly(
    year: int,
    month: int,
    day: int,
    hour: int | None = None,
    minute: int = 0,
    gender: str = "M",
    target_year: int | None = None,
):
    calc = get_saju_calculator()
    h = hour if hour is not None else 0
    saju = calc.calculate_saju(year, month, day, h, minute)
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

    birth_dt = datetime(year, month, day, h, minute)
    daeun_data = compute_daeun(
        calc.calendar_data, birth_dt,
        saju["year_pillar"], saju["month_pillar"], gender,
    )

    current_daeun = None
    age = ty - year
    for d in daeun_data.get("daeun", []):
        if d["start_age"] <= age < d["end_age"]:
            current_daeun = d
            break

    daeun_info = {}
    if current_daeun:
        daeun_stem = current_daeun["stem"]
        daeun_tg = ten_god_for_stem(day_stem, daeun_stem)
        daeun_group = group_map.get(daeun_tg, "비겁")
        daeun_info = {
            "pillar": current_daeun["pillar"],
            "tengod": daeun_tg,
            "group": daeun_group,
            "message": DAEUN_TEMPLATES.get(daeun_group, ""),
            "start_age": current_daeun["start_age"],
            "end_age": current_daeun["end_age"],
        }

    return {
        "target_year": ty,
        "sewoon_pillar": sewoon_pillar,
        "sewoon_tengod": sewoon_tg,
        "sewoon_message": SEWOON_TEMPLATES.get(sewoon_tg, ""),
        "daeun": daeun_info,
    }


# CORS for frontend
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

- [ ] **Step 4: 테스트 실행 — 통과 확인**

Run: `PYTHONPATH=src ./.venv/Scripts/python.exe -m pytest tests/test_api_saju.py -v`
Expected: 8 passed

- [ ] **Step 5: 수동 검증 — 서버 실행 후 API 호출**

```bash
# 터미널 1: 서버 실행
PYTHONPATH=src ./.venv/Scripts/python.exe -m uvicorn sajucandle.api.main:app --port 8001

# 터미널 2: API 호출
curl http://localhost:8001/api/saju/profile -X POST -H "Content-Type: application/json" -d '{"year":1985,"month":3,"day":15,"hour":14,"gender":"M"}'
curl "http://localhost:8001/api/saju/daily?year=1985&month=3&day=15&hour=14&gender=M"
curl "http://localhost:8001/api/saju/yearly?year=1985&month=3&day=15&hour=14&gender=M"
```

- [ ] **Step 6: 커밋**

```bash
git add src/sajucandle/api/main.py tests/test_api_saju.py
git commit -m "feat(api): 사주 프로필/일일운세/연간운세 엔드포인트 추가"
```

---

## Task 5: Next.js 프로젝트 초기화

**Files:**
- Create: `frontend/` 디렉토리 전체

- [ ] **Step 1: Next.js 프로젝트 생성**

```bash
npx create-next-app@latest frontend --typescript --tailwind --eslint --app --src-dir --no-import-alias
```

- [ ] **Step 2: 의존성 추가**

```bash
cd frontend && npm install
```

- [ ] **Step 3: 오행 색상 팔레트 + 폰트 설정 — tailwind.config.ts**

```typescript
// frontend/tailwind.config.ts
import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        wood: { DEFAULT: "#22C55E", light: "#DCFCE7", dark: "#166534" },
        fire: { DEFAULT: "#EF4444", light: "#FEE2E2", dark: "#991B1B" },
        earth: { DEFAULT: "#EAB308", light: "#FEF9C3", dark: "#854D0E" },
        metal: { DEFAULT: "#A1A1AA", light: "#F4F4F5", dark: "#3F3F46" },
        water: { DEFAULT: "#3B82F6", light: "#DBEAFE", dark: "#1E40AF" },
      },
      fontFamily: {
        sans: ["Pretendard", "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
};
export default config;
```

- [ ] **Step 4: 루트 레이아웃 — layout.tsx**

```tsx
// frontend/src/app/layout.tsx
import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "사주캔들 — 내 사주로 보는 투자 체질",
  description: "투자자를 위한 사주 앱. 매일 매매 기운과 투자 체질을 확인하세요.",
  openGraph: {
    title: "사주캔들",
    description: "내 사주로 보는 투자 체질 · 매일 매매 기운",
    type: "website",
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ko">
      <head>
        <link
          rel="stylesheet"
          href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css"
        />
      </head>
      <body className="bg-zinc-950 text-zinc-100 font-sans min-h-screen">
        <main className="max-w-md mx-auto px-4 py-6">
          {children}
        </main>
      </body>
    </html>
  );
}
```

- [ ] **Step 5: 커밋**

```bash
git add frontend/
git commit -m "chore(frontend): Next.js 프로젝트 초기화 — Tailwind + 오행 색상"
```

---

## Task 6: 공통 유틸 — TypeScript 타입 + API 클라이언트 + localStorage

**Files:**
- Create: `frontend/src/lib/types.ts`
- Create: `frontend/src/lib/api.ts`
- Create: `frontend/src/lib/storage.ts`
- Create: `frontend/src/lib/constants.ts`

- [ ] **Step 1: TypeScript 타입 정의**

```typescript
// frontend/src/lib/types.ts
export interface SajuPillars {
  year_pillar: string;
  month_pillar: string;
  day_pillar: string;
  hour_pillar: string;
}

export interface ProfileResponse {
  saju: SajuPillars;
  day_master: string;
  day_master_element: string;
  day_master_description: string;
  investor_type: string;
  description: string;
  strengths: string[];
  weaknesses: string[];
  risk_score: number;
  element_distribution: Record<string, number>;
  dominant_group: string;
  tengod_counts: Record<string, number>;
}

export interface DailyFortuneResponse {
  date: string;
  day_pillar_today: string;
  tengod_label: string;
  judgment_score: number;
  execution_score: number;
  patience_score: number;
  coaching: string;
  caution: string;
  detail: string;
  shinsal_messages: string[];
  relation_messages: string[];
}

export interface YearlyFortuneResponse {
  target_year: number;
  sewoon_pillar: string;
  sewoon_tengod: string;
  sewoon_message: string;
  daeun: {
    pillar: string;
    tengod: string;
    group: string;
    message: string;
    start_age: number;
    end_age: number;
  };
}

export interface UserData {
  year: number;
  month: number;
  day: number;
  hour: number | null;
  minute: number;
  gender: string;
  profile: ProfileResponse | null;
}
```

- [ ] **Step 2: API 클라이언트**

```typescript
// frontend/src/lib/api.ts
import type { ProfileResponse, DailyFortuneResponse, YearlyFortuneResponse } from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";

export async function fetchProfile(params: {
  year: number;
  month: number;
  day: number;
  hour?: number | null;
  minute?: number;
  gender: string;
}): Promise<ProfileResponse> {
  const body: Record<string, unknown> = {
    year: params.year,
    month: params.month,
    day: params.day,
    gender: params.gender,
  };
  if (params.hour != null) {
    body.hour = params.hour;
    body.minute = params.minute ?? 0;
  }
  const res = await fetch(`${API_BASE}/api/saju/profile`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`Profile API error: ${res.status}`);
  return res.json();
}

export async function fetchDailyFortune(params: {
  year: number;
  month: number;
  day: number;
  hour?: number | null;
  minute?: number;
  gender: string;
  date?: string;
}): Promise<DailyFortuneResponse> {
  const query = new URLSearchParams({
    year: String(params.year),
    month: String(params.month),
    day: String(params.day),
    gender: params.gender,
  });
  if (params.hour != null) query.set("hour", String(params.hour));
  if (params.date) query.set("date", params.date);
  const res = await fetch(`${API_BASE}/api/saju/daily?${query}`);
  if (!res.ok) throw new Error(`Daily API error: ${res.status}`);
  return res.json();
}

export async function fetchYearlyFortune(params: {
  year: number;
  month: number;
  day: number;
  hour?: number | null;
  minute?: number;
  gender: string;
}): Promise<YearlyFortuneResponse> {
  const query = new URLSearchParams({
    year: String(params.year),
    month: String(params.month),
    day: String(params.day),
    gender: params.gender,
  });
  if (params.hour != null) query.set("hour", String(params.hour));
  const res = await fetch(`${API_BASE}/api/saju/yearly?${query}`);
  if (!res.ok) throw new Error(`Yearly API error: ${res.status}`);
  return res.json();
}
```

- [ ] **Step 3: localStorage 관리**

```typescript
// frontend/src/lib/storage.ts
import type { UserData } from "./types";

const STORAGE_KEY = "sajucandle_user";

export function saveUser(data: UserData): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
}

export function loadUser(): UserData | null {
  if (typeof window === "undefined") return null;
  const raw = localStorage.getItem(STORAGE_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as UserData;
  } catch {
    return null;
  }
}

export function clearUser(): void {
  if (typeof window === "undefined") return;
  localStorage.removeItem(STORAGE_KEY);
}
```

- [ ] **Step 4: 상수 (오행 색상, 한글 매핑)**

```typescript
// frontend/src/lib/constants.ts
export const ELEMENT_COLORS: Record<string, { bg: string; text: string; label: string }> = {
  "木": { bg: "bg-wood", text: "text-wood", label: "목(木)" },
  "火": { bg: "bg-fire", text: "text-fire", label: "화(火)" },
  "土": { bg: "bg-earth", text: "text-earth", label: "토(土)" },
  "金": { bg: "bg-metal", text: "text-metal", label: "금(金)" },
  "水": { bg: "bg-water", text: "text-water", label: "수(水)" },
};

export const ELEMENT_KR: Record<string, string> = {
  "木": "목", "火": "화", "土": "토", "金": "금", "水": "수",
};

export const STEM_KR: Record<string, string> = {
  "甲": "갑", "乙": "을", "丙": "병", "丁": "정", "戊": "무",
  "己": "기", "庚": "경", "辛": "신", "壬": "임", "癸": "계",
};

export const BRANCH_KR: Record<string, string> = {
  "子": "자", "丑": "축", "寅": "인", "卯": "묘", "辰": "진", "巳": "사",
  "午": "오", "未": "미", "申": "신", "酉": "유", "戌": "술", "亥": "해",
};
```

- [ ] **Step 5: 커밋**

```bash
git add frontend/src/lib/
git commit -m "feat(frontend): 타입 정의 + API 클라이언트 + localStorage + 상수"
```

---

## Task 7: 온보딩 폼 컴포넌트

**Files:**
- Create: `frontend/src/components/OnboardingForm.tsx`

- [ ] **Step 1: 컴포넌트 구현**

```tsx
// frontend/src/components/OnboardingForm.tsx
"use client";

import { useState } from "react";
import { fetchProfile } from "@/lib/api";
import { saveUser } from "@/lib/storage";
import type { UserData } from "@/lib/types";

interface Props {
  onComplete: (data: UserData) => void;
}

export default function OnboardingForm({ onComplete }: Props) {
  const [year, setYear] = useState("");
  const [month, setMonth] = useState("");
  const [day, setDay] = useState("");
  const [hour, setHour] = useState<string>("");
  const [knowTime, setKnowTime] = useState(true);
  const [gender, setGender] = useState("M");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      const params = {
        year: parseInt(year),
        month: parseInt(month),
        day: parseInt(day),
        hour: knowTime && hour ? parseInt(hour) : null,
        minute: 0,
        gender,
      };
      const profile = await fetchProfile(params);
      const userData: UserData = { ...params, profile };
      saveUser(userData);
      onComplete(userData);
    } catch (err) {
      setError("사주 계산 중 오류가 발생했습니다. 다시 시도해주세요.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      <div className="text-center space-y-2">
        <h1 className="text-2xl font-bold">사주캔들</h1>
        <p className="text-zinc-400">내 사주로 보는 투자 체질</p>
      </div>

      <div className="space-y-4">
        <label className="block text-sm text-zinc-400">생년월일</label>
        <div className="grid grid-cols-3 gap-3">
          <input
            type="number"
            placeholder="년 (예: 1985)"
            value={year}
            onChange={(e) => setYear(e.target.value)}
            className="bg-zinc-800 rounded-lg px-3 py-3 text-center"
            min="1920" max="2010"
            required
          />
          <input
            type="number"
            placeholder="월"
            value={month}
            onChange={(e) => setMonth(e.target.value)}
            className="bg-zinc-800 rounded-lg px-3 py-3 text-center"
            min="1" max="12"
            required
          />
          <input
            type="number"
            placeholder="일"
            value={day}
            onChange={(e) => setDay(e.target.value)}
            className="bg-zinc-800 rounded-lg px-3 py-3 text-center"
            min="1" max="31"
            required
          />
        </div>
      </div>

      <div className="space-y-3">
        <div className="flex items-center gap-3">
          <label className="text-sm text-zinc-400">출생 시간</label>
          <button
            type="button"
            onClick={() => setKnowTime(!knowTime)}
            className={`text-xs px-3 py-1 rounded-full ${
              knowTime ? "bg-zinc-700 text-zinc-300" : "bg-zinc-600 text-white"
            }`}
          >
            {knowTime ? "모름" : "시간 모름 ✓"}
          </button>
        </div>
        {knowTime && (
          <input
            type="number"
            placeholder="시 (0~23)"
            value={hour}
            onChange={(e) => setHour(e.target.value)}
            className="bg-zinc-800 rounded-lg px-3 py-3 w-full text-center"
            min="0" max="23"
          />
        )}
      </div>

      <div className="space-y-2">
        <label className="block text-sm text-zinc-400">성별</label>
        <div className="grid grid-cols-2 gap-3">
          {(["M", "F"] as const).map((g) => (
            <button
              key={g}
              type="button"
              onClick={() => setGender(g)}
              className={`py-3 rounded-lg text-center ${
                gender === g
                  ? "bg-zinc-600 text-white ring-1 ring-zinc-400"
                  : "bg-zinc-800 text-zinc-400"
              }`}
            >
              {g === "M" ? "남성" : "여성"}
            </button>
          ))}
        </div>
      </div>

      {error && <p className="text-red-400 text-sm text-center">{error}</p>}

      <button
        type="submit"
        disabled={loading}
        className="w-full py-4 bg-gradient-to-r from-fire to-earth rounded-xl font-bold text-lg disabled:opacity-50"
      >
        {loading ? "사주 분석 중..." : "내 투자 체질 확인하기"}
      </button>

      <p className="text-xs text-zinc-500 text-center">
        입력 정보는 기기에만 저장되며 서버로 전송되지 않습니다.
      </p>
    </form>
  );
}
```

- [ ] **Step 2: 커밋**

```bash
git add frontend/src/components/OnboardingForm.tsx
git commit -m "feat(frontend): 온보딩 폼 — 생년월일·시간·성별 입력"
```

---

## Task 8: 사주 시각화 컴포넌트 (4주 차트 + 오행 분포)

**Files:**
- Create: `frontend/src/components/PillarChart.tsx`
- Create: `frontend/src/components/ElementBar.tsx`

- [ ] **Step 1: 사주 4주 시각화**

```tsx
// frontend/src/components/PillarChart.tsx
import { STEM_KR, BRANCH_KR, ELEMENT_COLORS } from "@/lib/constants";

interface Props {
  pillars: { year_pillar: string; month_pillar: string; day_pillar: string; hour_pillar: string };
  stemElements: Record<string, string>;
  branchElements: Record<string, string>;
}

const PILLAR_LABELS = ["시주", "일주", "월주", "년주"];
const PILLAR_KEYS = ["hour_pillar", "day_pillar", "month_pillar", "year_pillar"] as const;

export default function PillarChart({ pillars, stemElements, branchElements }: Props) {
  return (
    <div className="grid grid-cols-4 gap-2 text-center">
      {PILLAR_KEYS.map((key, i) => {
        const pillar = pillars[key];
        if (!pillar) {
          return (
            <div key={key} className="space-y-1">
              <p className="text-xs text-zinc-500">{PILLAR_LABELS[i]}</p>
              <div className="bg-zinc-800 rounded-lg py-4 text-zinc-600">?</div>
              <div className="bg-zinc-800 rounded-lg py-4 text-zinc-600">?</div>
            </div>
          );
        }
        const stem = pillar[0];
        const branch = pillar[1];
        const stemEl = stemElements[stem] || "";
        const branchEl = branchElements[branch] || "";
        const stemColor = ELEMENT_COLORS[stemEl] || { bg: "bg-zinc-700", text: "text-zinc-300" };
        const branchColor = ELEMENT_COLORS[branchEl] || { bg: "bg-zinc-700", text: "text-zinc-300" };

        return (
          <div key={key} className="space-y-1">
            <p className="text-xs text-zinc-500">{PILLAR_LABELS[i]}</p>
            <div className={`${stemColor.bg} bg-opacity-20 rounded-lg py-4`}>
              <p className={`text-xl font-bold ${stemColor.text}`}>{stem}</p>
              <p className="text-xs text-zinc-400">{STEM_KR[stem]}</p>
            </div>
            <div className={`${branchColor.bg} bg-opacity-20 rounded-lg py-4`}>
              <p className={`text-xl font-bold ${branchColor.text}`}>{branch}</p>
              <p className="text-xs text-zinc-400">{BRANCH_KR[branch]}</p>
            </div>
          </div>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 2: 오행 분포 바 차트**

```tsx
// frontend/src/components/ElementBar.tsx
import { ELEMENT_COLORS, ELEMENT_KR } from "@/lib/constants";

interface Props {
  distribution: Record<string, number>;
}

const ELEMENTS = ["木", "火", "土", "金", "水"];

export default function ElementBar({ distribution }: Props) {
  const total = Object.values(distribution).reduce((a, b) => a + b, 0) || 1;

  return (
    <div className="space-y-2">
      {ELEMENTS.map((el) => {
        const count = distribution[el] || 0;
        const pct = Math.round((count / total) * 100);
        const color = ELEMENT_COLORS[el];
        return (
          <div key={el} className="flex items-center gap-3">
            <span className={`w-12 text-sm ${color.text}`}>{color.label}</span>
            <div className="flex-1 h-5 bg-zinc-800 rounded-full overflow-hidden">
              <div
                className={`h-full ${color.bg} bg-opacity-60 rounded-full transition-all`}
                style={{ width: `${pct}%` }}
              />
            </div>
            <span className="text-xs text-zinc-400 w-8 text-right">{count}</span>
          </div>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 3: 커밋**

```bash
git add frontend/src/components/PillarChart.tsx frontend/src/components/ElementBar.tsx
git commit -m "feat(frontend): 사주 4주 시각화 + 오행 분포 바 차트"
```

---

## Task 9: 투자 체질 카드 컴포넌트

**Files:**
- Create: `frontend/src/components/ProfileCard.tsx`

- [ ] **Step 1: 컴포넌트 구현**

```tsx
// frontend/src/components/ProfileCard.tsx
import type { ProfileResponse } from "@/lib/types";
import PillarChart from "./PillarChart";
import ElementBar from "./ElementBar";

const STEM_ELEMENT: Record<string, string> = {
  "甲": "木", "乙": "木", "丙": "火", "丁": "火", "戊": "土",
  "己": "土", "庚": "金", "辛": "金", "壬": "水", "癸": "水",
};
const BRANCH_ELEMENT: Record<string, string> = {
  "子": "水", "丑": "土", "寅": "木", "卯": "木", "辰": "土", "巳": "火",
  "午": "火", "未": "土", "申": "金", "酉": "金", "戌": "土", "亥": "水",
};

interface Props {
  profile: ProfileResponse;
}

export default function ProfileCard({ profile }: Props) {
  return (
    <div className="space-y-6">
      <div className="text-center space-y-2">
        <p className="text-zinc-400 text-sm">나의 투자 체질</p>
        <h2 className="text-3xl font-bold">{profile.investor_type}</h2>
        <p className="text-lg text-zinc-300">{profile.day_master_description}</p>
      </div>

      <PillarChart
        pillars={profile.saju}
        stemElements={STEM_ELEMENT}
        branchElements={BRANCH_ELEMENT}
      />

      <ElementBar distribution={profile.element_distribution} />

      <div className="bg-zinc-800/50 rounded-xl p-4 space-y-3">
        <p className="text-zinc-300">{profile.description}</p>
        <div>
          <p className="text-sm text-zinc-400 mb-1">강점</p>
          <ul className="text-sm space-y-1">
            {profile.strengths.map((s) => (
              <li key={s} className="text-green-400">+ {s}</li>
            ))}
          </ul>
        </div>
        <div>
          <p className="text-sm text-zinc-400 mb-1">주의점</p>
          <ul className="text-sm space-y-1">
            {profile.weaknesses.map((w) => (
              <li key={w} className="text-red-400">- {w}</li>
            ))}
          </ul>
        </div>
      </div>

      <div className="flex items-center justify-between bg-zinc-800/50 rounded-xl p-4">
        <span className="text-zinc-400">리스크 성향</span>
        <div className="flex items-center gap-2">
          <div className="w-32 h-2 bg-zinc-700 rounded-full overflow-hidden">
            <div
              className="h-full bg-gradient-to-r from-blue-500 to-red-500 rounded-full"
              style={{ width: `${profile.risk_score}%` }}
            />
          </div>
          <span className="text-sm font-mono">{profile.risk_score}</span>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: 커밋**

```bash
git add frontend/src/components/ProfileCard.tsx
git commit -m "feat(frontend): 투자 체질 카드 — 프로필·강점·리스크 표시"
```

---

## Task 10: 매일 운세 피드 컴포넌트

**Files:**
- Create: `frontend/src/components/DailyFortune.tsx`
- Create: `frontend/src/components/FortuneDetail.tsx`

- [ ] **Step 1: 매매 기운 카드**

```tsx
// frontend/src/components/DailyFortune.tsx
import type { DailyFortuneResponse } from "@/lib/types";

interface Props {
  fortune: DailyFortuneResponse;
}

function ScoreBar({ label, score }: { label: string; score: number }) {
  const color =
    score >= 70 ? "bg-green-500" : score >= 40 ? "bg-yellow-500" : "bg-red-500";
  return (
    <div className="flex items-center gap-3">
      <span className="text-sm text-zinc-400 w-16">{label}</span>
      <div className="flex-1 h-3 bg-zinc-800 rounded-full overflow-hidden">
        <div
          className={`h-full ${color} rounded-full transition-all`}
          style={{ width: `${score}%` }}
        />
      </div>
      <span className="text-sm font-mono w-8 text-right">{score}</span>
    </div>
  );
}

export default function DailyFortune({ fortune }: Props) {
  return (
    <div className="bg-zinc-900 rounded-2xl p-5 space-y-4">
      <div className="flex justify-between items-center">
        <h3 className="font-bold text-lg">오늘의 매매 기운</h3>
        <span className="text-sm text-zinc-500">{fortune.date}</span>
      </div>

      <p className="text-zinc-300 font-medium">{fortune.tengod_label}</p>

      <div className="space-y-2">
        <ScoreBar label="판단운" score={fortune.judgment_score} />
        <ScoreBar label="실행운" score={fortune.execution_score} />
        <ScoreBar label="인내운" score={fortune.patience_score} />
      </div>

      <div className="bg-zinc-800/50 rounded-xl p-4 space-y-2">
        <p className="text-zinc-200">{fortune.coaching}</p>
        <p className="text-sm text-red-400">{fortune.caution}</p>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: 명리 해설 섹션**

```tsx
// frontend/src/components/FortuneDetail.tsx
import type { DailyFortuneResponse } from "@/lib/types";

interface Props {
  fortune: DailyFortuneResponse;
}

export default function FortuneDetail({ fortune }: Props) {
  return (
    <div className="bg-zinc-900 rounded-2xl p-5 space-y-4">
      <h3 className="font-bold text-lg">명리 해설</h3>

      <p className="text-zinc-300 leading-relaxed">{fortune.detail}</p>

      {fortune.shinsal_messages.length > 0 && (
        <div className="space-y-2">
          <p className="text-sm text-zinc-500">오늘의 신살</p>
          {fortune.shinsal_messages.map((msg, i) => (
            <p key={i} className="text-sm text-zinc-400 pl-3 border-l-2 border-zinc-700">
              {msg}
            </p>
          ))}
        </div>
      )}

      {fortune.relation_messages.length > 0 && (
        <div className="space-y-2">
          <p className="text-sm text-zinc-500">기운의 흐름</p>
          {fortune.relation_messages.map((msg, i) => (
            <p key={i} className="text-sm text-zinc-400 pl-3 border-l-2 border-zinc-700">
              {msg}
            </p>
          ))}
        </div>
      )}

      <p className="text-xs text-zinc-600 text-center pt-2">
        본 콘텐츠는 오락 목적이며 투자 조언이 아닙니다.
      </p>
    </div>
  );
}
```

- [ ] **Step 3: 커밋**

```bash
git add frontend/src/components/DailyFortune.tsx frontend/src/components/FortuneDetail.tsx
git commit -m "feat(frontend): 매매 기운 카드 + 명리 해설 컴포넌트"
```

---

## Task 11: 페이지 조합 — 메인(온보딩/피드 분기) + 피드 + 프로필

**Files:**
- Create: `frontend/src/app/page.tsx`
- Create: `frontend/src/app/feed/page.tsx`
- Create: `frontend/src/app/profile/page.tsx`

- [ ] **Step 1: 메인 페이지 (온보딩 or 피드 분기)**

```tsx
// frontend/src/app/page.tsx
"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { loadUser, saveUser } from "@/lib/storage";
import OnboardingForm from "@/components/OnboardingForm";
import ProfileCard from "@/components/ProfileCard";
import type { UserData } from "@/lib/types";

export default function Home() {
  const router = useRouter();
  const [user, setUser] = useState<UserData | null>(null);
  const [showResult, setShowResult] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const saved = loadUser();
    if (saved?.profile) {
      router.replace("/feed");
    } else {
      setLoading(false);
    }
  }, [router]);

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <p className="text-zinc-500">로딩 중...</p>
      </div>
    );
  }

  if (showResult && user?.profile) {
    return (
      <div className="space-y-6">
        <ProfileCard profile={user.profile} />
        <button
          onClick={() => router.push("/feed")}
          className="w-full py-4 bg-gradient-to-r from-fire to-earth rounded-xl font-bold text-lg"
        >
          매일 운세 보러가기
        </button>
        <button
          onClick={() => {
            if (navigator.share) {
              navigator.share({
                title: `나는 ${user.profile!.investor_type} — 사주캔들`,
                text: user.profile!.day_master_description,
                url: window.location.origin,
              });
            }
          }}
          className="w-full py-3 bg-zinc-800 rounded-xl text-zinc-300"
        >
          카카오톡으로 공유하기
        </button>
      </div>
    );
  }

  return (
    <OnboardingForm
      onComplete={(data) => {
        setUser(data);
        setShowResult(true);
      }}
    />
  );
}
```

- [ ] **Step 2: 피드 페이지**

```tsx
// frontend/src/app/feed/page.tsx
"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { loadUser } from "@/lib/storage";
import { fetchDailyFortune } from "@/lib/api";
import DailyFortune from "@/components/DailyFortune";
import FortuneDetail from "@/components/FortuneDetail";
import type { UserData, DailyFortuneResponse } from "@/lib/types";

export default function FeedPage() {
  const router = useRouter();
  const [user, setUser] = useState<UserData | null>(null);
  const [fortune, setFortune] = useState<DailyFortuneResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const saved = loadUser();
    if (!saved?.profile) {
      router.replace("/");
      return;
    }
    setUser(saved);

    fetchDailyFortune({
      year: saved.year,
      month: saved.month,
      day: saved.day,
      hour: saved.hour,
      gender: saved.gender,
    })
      .then(setFortune)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [router]);

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <p className="text-zinc-500">운세 불러오는 중...</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <nav className="flex gap-4 text-sm border-b border-zinc-800 pb-3">
        <span className="text-white font-bold border-b-2 border-fire pb-1">오늘</span>
        <button
          onClick={() => router.push("/profile")}
          className="text-zinc-500"
        >
          내 사주
        </button>
      </nav>

      {fortune && (
        <>
          <DailyFortune fortune={fortune} />
          <FortuneDetail fortune={fortune} />
        </>
      )}

      <div className="bg-zinc-900 rounded-2xl p-5 opacity-50">
        <p className="text-zinc-500 text-center text-sm">
          월간 투자 시그널 — 곧 출시
        </p>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: 프로필 페이지**

```tsx
// frontend/src/app/profile/page.tsx
"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { loadUser, clearUser } from "@/lib/storage";
import { fetchYearlyFortune } from "@/lib/api";
import ProfileCard from "@/components/ProfileCard";
import type { UserData, YearlyFortuneResponse } from "@/lib/types";

export default function ProfilePage() {
  const router = useRouter();
  const [user, setUser] = useState<UserData | null>(null);
  const [yearly, setYearly] = useState<YearlyFortuneResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const saved = loadUser();
    if (!saved?.profile) {
      router.replace("/");
      return;
    }
    setUser(saved);

    fetchYearlyFortune({
      year: saved.year,
      month: saved.month,
      day: saved.day,
      hour: saved.hour,
      gender: saved.gender,
    })
      .then(setYearly)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [router]);

  if (loading || !user?.profile) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <p className="text-zinc-500">로딩 중...</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <nav className="flex gap-4 text-sm border-b border-zinc-800 pb-3">
        <button
          onClick={() => router.push("/feed")}
          className="text-zinc-500"
        >
          오늘
        </button>
        <span className="text-white font-bold border-b-2 border-fire pb-1">내 사주</span>
      </nav>

      <ProfileCard profile={user.profile} />

      {yearly && (
        <div className="space-y-4">
          <div className="bg-zinc-900 rounded-2xl p-5 space-y-3">
            <h3 className="font-bold text-lg">올해 투자 흐름</h3>
            <p className="text-zinc-400 text-sm">
              {yearly.target_year}년 세운: {yearly.sewoon_pillar} ({yearly.sewoon_tengod})
            </p>
            <p className="text-zinc-300">{yearly.sewoon_message}</p>
          </div>

          {yearly.daeun?.pillar && (
            <div className="bg-zinc-900 rounded-2xl p-5 space-y-3">
              <h3 className="font-bold text-lg">현재 대운</h3>
              <p className="text-zinc-400 text-sm">
                {yearly.daeun.pillar} ({yearly.daeun.tengod}) · {yearly.daeun.start_age}~{yearly.daeun.end_age}세
              </p>
              <p className="text-zinc-300">{yearly.daeun.message}</p>
            </div>
          )}
        </div>
      )}

      <button
        onClick={() => {
          if (navigator.share) {
            navigator.share({
              title: `나는 ${user.profile!.investor_type} — 사주캔들`,
              text: user.profile!.day_master_description,
              url: window.location.origin,
            });
          }
        }}
        className="w-full py-3 bg-zinc-800 rounded-xl text-zinc-300"
      >
        카카오톡으로 공유하기
      </button>

      <button
        onClick={() => {
          clearUser();
          router.replace("/");
        }}
        className="w-full py-3 text-zinc-600 text-sm"
      >
        사주 정보 초기화
      </button>
    </div>
  );
}
```

- [ ] **Step 4: 커밋**

```bash
git add frontend/src/app/
git commit -m "feat(frontend): 메인·피드·프로필 페이지 — 온보딩 분기 + 피드 스크롤 + 프로필 탭"
```

---

## Task 12: 카카오톡 공유 카드 (og:image)

**Files:**
- Create: `frontend/src/app/card/[id]/page.tsx`
- Create: `frontend/src/app/card/[id]/opengraph-image.tsx`
- Create: `frontend/src/lib/kakao.ts`

- [ ] **Step 1: 공유 카드 랜딩 페이지**

```tsx
// frontend/src/app/card/[id]/page.tsx
import type { Metadata } from "next";

interface Props {
  params: Promise<{ id: string }>;
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { id } = await params;
  return {
    title: "사주캔들 — 내 투자 체질 확인하기",
    description: "사주캔들에서 나만의 투자 체질을 확인해보세요",
    openGraph: {
      title: "나의 투자 체질 — 사주캔들",
      description: "내 사주로 보는 투자 체질을 확인해보세요",
      images: [`/card/${id}/opengraph-image`],
    },
  };
}

export default async function CardPage({ params }: Props) {
  return (
    <div className="space-y-6 text-center pt-12">
      <h1 className="text-2xl font-bold">사주캔들</h1>
      <p className="text-zinc-400">내 사주로 보는 투자 체질</p>
      <a
        href="/"
        className="inline-block px-8 py-4 bg-gradient-to-r from-fire to-earth rounded-xl font-bold text-lg"
      >
        나도 해보기
      </a>
    </div>
  );
}
```

- [ ] **Step 2: og:image 동적 생성**

```tsx
// frontend/src/app/card/[id]/opengraph-image.tsx
import { ImageResponse } from "next/og";

export const runtime = "edge";
export const alt = "사주캔들 투자 체질 카드";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export default async function Image({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;

  let decodedData = { type: "분석형", master: "庚", element: "金" };
  try {
    decodedData = JSON.parse(atob(id));
  } catch {}

  const ELEMENT_COLOR: Record<string, string> = {
    "木": "#22C55E", "火": "#EF4444", "土": "#EAB308",
    "金": "#A1A1AA", "水": "#3B82F6",
  };

  const color = ELEMENT_COLOR[decodedData.element] || "#A1A1AA";

  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          background: "linear-gradient(135deg, #18181B 0%, #27272A 100%)",
          fontFamily: "sans-serif",
        }}
      >
        <div style={{ fontSize: 32, color: "#71717A", marginBottom: 16 }}>
          사주캔들
        </div>
        <div style={{ fontSize: 80, color, fontWeight: "bold", marginBottom: 12 }}>
          {decodedData.master}
        </div>
        <div style={{ fontSize: 48, color: "#FAFAFA", fontWeight: "bold", marginBottom: 24 }}>
          {decodedData.type}
        </div>
        <div style={{ fontSize: 24, color: "#A1A1AA" }}>
          내 사주로 보는 투자 체질
        </div>
      </div>
    ),
    { ...size },
  );
}
```

- [ ] **Step 3: 카카오 SDK 래퍼**

```typescript
// frontend/src/lib/kakao.ts
declare global {
  interface Window {
    Kakao?: {
      init: (key: string) => void;
      isInitialized: () => boolean;
      Share: {
        sendDefault: (params: Record<string, unknown>) => void;
      };
    };
  }
}

const KAKAO_KEY = process.env.NEXT_PUBLIC_KAKAO_JS_KEY || "";

export function initKakao(): void {
  if (typeof window === "undefined") return;
  if (!window.Kakao || window.Kakao.isInitialized()) return;
  if (KAKAO_KEY) {
    window.Kakao.init(KAKAO_KEY);
  }
}

export function shareKakao(params: {
  title: string;
  description: string;
  imageUrl: string;
  link: string;
}): void {
  if (typeof window === "undefined" || !window.Kakao?.isInitialized()) {
    if (navigator.share) {
      navigator.share({ title: params.title, text: params.description, url: params.link });
    }
    return;
  }

  window.Kakao.Share.sendDefault({
    objectType: "feed",
    content: {
      title: params.title,
      description: params.description,
      imageUrl: params.imageUrl,
      link: { mobileWebUrl: params.link, webUrl: params.link },
    },
    buttons: [
      { title: "나도 해보기", link: { mobileWebUrl: params.link, webUrl: params.link } },
    ],
  });
}
```

- [ ] **Step 4: 커밋**

```bash
git add frontend/src/app/card/ frontend/src/lib/kakao.ts
git commit -m "feat(frontend): 카카오톡 공유 카드 — og:image 동적 생성 + 랜딩 페이지"
```

---

## Task 13: 통합 테스트 — 풀스택 검증

**Files:** (기존 파일들 검증)

- [ ] **Step 1: 백엔드 전체 테스트 실행**

Run:
```bash
PYTHONPATH=src ./.venv/Scripts/python.exe -m pytest tests/test_investor_profile.py tests/test_daily_fortune.py tests/test_api_saju.py -v
```
Expected: 전체 PASS

- [ ] **Step 2: 프론트엔드 빌드 확인**

```bash
cd frontend && npm run build
```
Expected: 빌드 성공, 에러 없음

- [ ] **Step 3: 풀스택 수동 검증**

터미널 1 — 백엔드:
```bash
PYTHONPATH=src ./.venv/Scripts/python.exe -m uvicorn sajucandle.api.main:app --port 8001
```

터미널 2 — 프론트엔드:
```bash
cd frontend && npm run dev
```

브라우저에서 `http://localhost:3000` 접속 후 확인:
1. 온보딩 폼 → 생년월일 입력 → 투자 체질 카드 표시
2. "매일 운세 보러가기" → 피드 페이지 (매매 기운 + 해설)
3. "내 사주" 탭 → 프로필 + 세운/대운 해설
4. 공유 버튼 클릭 → Web Share API 또는 카카오 SDK 동작
5. 새로고침 → localStorage에서 복원 → 바로 피드로 이동

- [ ] **Step 4: ruff 린트 확인**

```bash
./.venv/Scripts/python.exe -m ruff check src/sajucandle/saju/investor_profile.py src/sajucandle/saju/daily_fortune.py src/sajucandle/saju/fortune_templates.py
```

- [ ] **Step 5: 최종 커밋**

```bash
git add -A
git commit -m "test: 통합 테스트 통과 확인 — 백엔드 + 프론트엔드 풀스택 검증"
```

---

## 구현 범위 밖 (2단계)

다음 항목은 이 플랜에 포함하지 않는다. 1단계 MVP 검증 후 별도 플랜으로 진행:

- 투자 시그널 탭 (한국주식 / 미국주식 / 코인)
- 한국 주식 유니버스 구축
- 카카오 개발자 앱 등록 + 실제 카카오 SDK 연동
- 유저 DB / 회원가입
- 수익화 (구독)
- 푸시 알림
- 네이티브 앱 전환
- 도메인 구매 + 프로덕션 배포

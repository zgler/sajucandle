# 나의 투자 감정서 — 백엔드 구현 플랜

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Claude API로 개인 맞춤 투자 사주 감정서(7섹션 JSON)를 생성하는 백엔드 파이프라인 구현

**Architecture:** 3단계 파이프라인 — (1) report_context.py가 기존 사주 엔진 모듈들을 조합하여 구조화된 컨텍스트 dict를 생성 → (2) report_prompt.py가 시스템 프롬프트와 유저 메시지를 조립 → (3) report_generator.py가 Anthropic API를 호출하고 7섹션 JSON을 파싱하여 반환. FastAPI 엔드포인트 `POST /api/saju/report`가 이 파이프라인을 호출한다.

**Tech Stack:** Python 3.12+, FastAPI, anthropic SDK, 기존 sajucandle.saju/manseryeok 모듈

---

## 파일 구조

| 파일 | 역할 | 상태 |
|------|------|------|
| `src/sajucandle/saju/report_context.py` | 사주 엔진 → 구조화된 컨텍스트 dict 수집 | 신규 |
| `src/sajucandle/saju/report_prompt.py` | 시스템 프롬프트 + 유저 메시지 조립 (상수) | 신규 |
| `src/sajucandle/saju/report_generator.py` | Anthropic API 호출 + JSON 파싱 | 신규 |
| `src/sajucandle/api/main.py` | `POST /api/saju/report` 엔드포인트 추가 | 수정 |
| `pyproject.toml` | `anthropic` 의존성 추가 | 수정 |
| `tests/test_report_context.py` | 컨텍스트 수집 테스트 | 신규 |
| `tests/test_report_prompt.py` | 프롬프트 조립 테스트 | 신규 |
| `tests/test_report_generator.py` | API 호출 + 파싱 테스트 (mock) | 신규 |
| `tests/test_api_report.py` | 엔드포인트 통합 테스트 (mock) | 신규 |

---

### Task 1: anthropic 의존성 추가

**Files:**
- Modify: `pyproject.toml:6-18`

- [ ] **Step 1: pyproject.toml에 anthropic 추가**

`pyproject.toml`의 `dependencies` 리스트에 `anthropic` 추가:

```python
# pyproject.toml dependencies 리스트 끝에 추가
    "anthropic>=0.49,<1.0",
```

전체 dependencies 블록:
```toml
dependencies = [
    "fastapi>=0.110,<1.0",
    "uvicorn[standard]>=0.27",
    "pydantic>=2.0,<3.0",
    "httpx>=0.27",
    "yfinance>=0.2.40,<0.3",
    "pandas>=2.2,<3.0",
    "numpy>=1.26,<3.0",
    "geopy>=2.4,<3.0",
    "apscheduler>=3.10,<4.0",
    "ta>=0.11,<0.12",
    "ccxt>=4.2,<5.0",
    "requests>=2.31,<3.0",
    "anthropic>=0.49,<1.0",
]
```

- [ ] **Step 2: 패키지 설치**

Run: `./.venv/Scripts/python.exe -m pip install -e ".[dev]"`
Expected: anthropic 설치 성공

- [ ] **Step 3: 설치 확인**

Run: `./.venv/Scripts/python.exe -c "import anthropic; print(anthropic.__version__)"`
Expected: 버전 번호 출력 (0.49.x 이상)

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "chore: add anthropic SDK dependency"
```

---

### Task 2: report_context.py — 컨텍스트 수집

**Files:**
- Create: `src/sajucandle/saju/report_context.py`
- Test: `tests/test_report_context.py`

- [ ] **Step 1: 테스트 작성**

`tests/test_report_context.py`:

```python
"""tests/test_report_context.py — 감정서 컨텍스트 수집 테스트."""
from __future__ import annotations

import pytest
from sajucandle.saju.report_context import collect_report_context


class TestCollectReportContext:
    """collect_report_context가 올바른 구조를 반환하는지 검증."""

    def test_returns_dict(self):
        ctx = collect_report_context(1985, 3, 15, 14, "M", 2026)
        assert isinstance(ctx, dict)

    def test_birth_section(self):
        ctx = collect_report_context(1985, 3, 15, 14, "M", 2026)
        birth = ctx["birth"]
        assert birth["year"] == 1985
        assert birth["month"] == 3
        assert birth["day"] == 15
        assert birth["hour"] == 14
        assert birth["gender"] == "M"

    def test_pillars_section(self):
        ctx = collect_report_context(1985, 3, 15, 14, "M", 2026)
        pillars = ctx["pillars"]
        for key in ("year", "month", "day", "hour"):
            p = pillars[key]
            assert "pillar" in p
            assert "stem" in p
            assert "branch" in p
            assert len(p["pillar"]) == 2

    def test_day_master_section(self):
        ctx = collect_report_context(1985, 3, 15, 14, "M", 2026)
        dm = ctx["day_master"]
        assert "stem" in dm
        assert "element" in dm
        assert dm["element"] in ("木", "火", "土", "金", "水")
        assert "yin_yang" in dm
        assert dm["yin_yang"] in ("양", "음")

    def test_tengod_distribution(self):
        ctx = collect_report_context(1985, 3, 15, 14, "M", 2026)
        td = ctx["tengod_distribution"]
        for group in ("비겁", "식상", "재성", "관성", "인성"):
            assert group in td
            assert isinstance(td[group], int)

    def test_element_balance(self):
        ctx = collect_report_context(1985, 3, 15, 14, "M", 2026)
        eb = ctx["element_balance"]
        for elem in ("木", "火", "土", "金", "水"):
            assert elem in eb

    def test_investor_type(self):
        ctx = collect_report_context(1985, 3, 15, 14, "M", 2026)
        assert ctx["investor_type"] in ("독립형", "직감형", "실리형", "원칙형", "분석형")
        assert isinstance(ctx["dominant_group"], str)

    def test_sewoon(self):
        ctx = collect_report_context(1985, 3, 15, 14, "M", 2026)
        sewoon = ctx["sewoon"]
        assert "pillar" in sewoon
        assert "stem" in sewoon
        assert "tengod" in sewoon

    def test_monthly_pillars_count(self):
        ctx = collect_report_context(1985, 3, 15, 14, "M", 2026)
        mp = ctx["monthly_pillars"]
        assert len(mp) == 12
        assert mp[0]["month"] == 1
        assert mp[11]["month"] == 12
        for entry in mp:
            assert "pillar" in entry
            assert "stem" in entry
            assert "tengod" in entry

    def test_current_daeun(self):
        ctx = collect_report_context(1985, 3, 15, 14, "M", 2026)
        daeun = ctx["current_daeun"]
        assert "pillar" in daeun
        assert "stem" in daeun
        assert "tengod" in daeun
        assert "start_age" in daeun
        assert "end_age" in daeun

    def test_shinsal(self):
        ctx = collect_report_context(1985, 3, 15, 14, "M", 2026)
        assert isinstance(ctx["shinsal"], list)

    def test_relations(self):
        ctx = collect_report_context(1985, 3, 15, 14, "M", 2026)
        rels = ctx["relations"]
        assert "day_sewoon" in rels
        assert "day_daeun" in rels
        for key in ("day_sewoon", "day_daeun"):
            assert "pros" in rels[key]
            assert "cons" in rels[key]

    def test_hour_none(self):
        """시주 없는 경우에도 정상 작동."""
        ctx = collect_report_context(1985, 3, 15, None, "F", 2026)
        assert ctx["birth"]["hour"] is None
        assert ctx["pillars"]["hour"] is None


class TestCollectReportContextEdgeCases:
    def test_female_gender(self):
        ctx = collect_report_context(1990, 7, 20, 8, "F", 2026)
        assert ctx["birth"]["gender"] == "F"
        assert isinstance(ctx["current_daeun"], dict)

    def test_different_target_year(self):
        ctx = collect_report_context(1985, 3, 15, 14, "M", 2027)
        assert ctx["sewoon"]["pillar"]  # 다른 연도여도 세운 존재
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `PYTHONPATH=src ./.venv/Scripts/python.exe -m pytest tests/test_report_context.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sajucandle.saju.report_context'`

- [ ] **Step 3: 구현**

`src/sajucandle/saju/report_context.py`:

```python
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
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `PYTHONPATH=src ./.venv/Scripts/python.exe -m pytest tests/test_report_context.py -v`
Expected: 전체 PASS

- [ ] **Step 5: Commit**

```bash
git add src/sajucandle/saju/report_context.py tests/test_report_context.py
git commit -m "feat(report): add report context collector"
```

---

### Task 3: report_prompt.py — 프롬프트 조립

**Files:**
- Create: `src/sajucandle/saju/report_prompt.py`
- Test: `tests/test_report_prompt.py`

- [ ] **Step 1: 테스트 작성**

`tests/test_report_prompt.py`:

```python
"""tests/test_report_prompt.py — 프롬프트 조립 테스트."""
from __future__ import annotations

import json
from sajucandle.saju.report_prompt import build_messages


SAMPLE_CONTEXT = {
    "birth": {"year": 1985, "month": 3, "day": 15, "hour": 14, "gender": "M"},
    "pillars": {
        "year": {"pillar": "乙丑", "stem": "乙", "branch": "丑"},
        "month": {"pillar": "己卯", "stem": "己", "branch": "卯"},
        "day": {"pillar": "癸丑", "stem": "癸", "branch": "丑"},
        "hour": {"pillar": "己未", "stem": "己", "branch": "未"},
    },
    "day_master": {"stem": "癸", "element": "水", "yin_yang": "음"},
    "tengod_distribution": {"비겁": 2, "식상": 0, "재성": 1, "관성": 2, "인성": 1},
    "element_balance": {"木": 2, "火": 0, "土": 3, "金": 0, "水": 1},
    "dominant_group": "관성",
    "investor_type": "원칙형",
    "sewoon": {"pillar": "丙午", "stem": "丙", "tengod": "정재"},
    "monthly_pillars": [
        {"month": i, "pillar": "己丑", "stem": "己", "tengod": "편관"}
        for i in range(1, 13)
    ],
    "current_daeun": {
        "pillar": "乙亥", "stem": "乙",
        "tengod": "식신", "start_age": 33, "end_age": 43,
    },
    "shinsal": ["천을귀인", "역마살"],
    "relations": {
        "day_sewoon": {"pros": ["육합"], "cons": []},
        "day_daeun": {"pros": [], "cons": ["충"]},
    },
}


class TestBuildMessages:
    def test_returns_two_messages(self):
        msgs = build_messages(SAMPLE_CONTEXT)
        assert len(msgs) == 2

    def test_system_message_role(self):
        msgs = build_messages(SAMPLE_CONTEXT)
        assert msgs[0]["role"] == "system"

    def test_user_message_role(self):
        msgs = build_messages(SAMPLE_CONTEXT)
        assert msgs[1]["role"] == "user"

    def test_system_contains_role_definition(self):
        msgs = build_messages(SAMPLE_CONTEXT)
        system_text = msgs[0]["content"]
        assert "투자" in system_text
        assert "감정사" in system_text or "감정서" in system_text

    def test_system_contains_output_format(self):
        msgs = build_messages(SAMPLE_CONTEXT)
        system_text = msgs[0]["content"]
        assert "sections" in system_text
        assert "JSON" in system_text

    def test_system_contains_disclaimer(self):
        msgs = build_messages(SAMPLE_CONTEXT)
        system_text = msgs[0]["content"]
        assert "투자 권유" in system_text or "투자 조언" in system_text

    def test_user_contains_context_json(self):
        msgs = build_messages(SAMPLE_CONTEXT)
        user_text = msgs[1]["content"]
        assert "癸" in user_text
        assert "원칙형" in user_text
        assert "丙午" in user_text

    def test_user_message_parseable_json_block(self):
        """유저 메시지 안에 컨텍스트 JSON이 파싱 가능해야 한다."""
        msgs = build_messages(SAMPLE_CONTEXT)
        user_text = msgs[1]["content"]
        # JSON 블록 추출
        start = user_text.find("{")
        end = user_text.rfind("}") + 1
        assert start >= 0
        parsed = json.loads(user_text[start:end])
        assert parsed["day_master"]["stem"] == "癸"

    def test_seven_section_guide_present(self):
        msgs = build_messages(SAMPLE_CONTEXT)
        system_text = msgs[0]["content"]
        assert "명식 해석" in system_text
        assert "투자 DNA" in system_text
        assert "세운 전략" in system_text
        assert "월별 타이밍" in system_text
        assert "현재 대운" in system_text
        assert "투자 스타일" in system_text
        assert "투자 함정" in system_text
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `PYTHONPATH=src ./.venv/Scripts/python.exe -m pytest tests/test_report_prompt.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: 구현**

`src/sajucandle/saju/report_prompt.py`:

```python
"""감정서 프롬프트 — 시스템 프롬프트 + 유저 메시지 조립."""
from __future__ import annotations

import json
from typing import Any


SYSTEM_PROMPT = """\
당신은 30년 경력의 투자 전문 사주 감정사입니다. 명리학의 전통 이론에 기반하여 \
의뢰인의 사주 원국과 세운/대운 데이터를 분석하고, 투자 관점의 감정서를 작성합니다.

## 작성 원칙

1. 명리 용어를 사용하되, 괄호 안에 쉬운 설명을 병기합니다.
   예: "편관(偏官, 나를 제어하는 힘)"
2. 단정적 톤을 사용합니다. "~합니다", "~입니다" 형태.
3. 추상적 운세가 아닌 구체적 투자 행동을 제안합니다.
   나쁜 예: "올해 재물운이 좋습니다"
   좋은 예: "상반기에 분할 매수로 포지션을 구축하고, 7월 전환점에서 일부 수익 실현을 검토하세요"
4. 특정 종목명, 가격, 수익률은 절대 언급하지 않습니다.
5. 천간뿐 아니라 지지의 지장간까지 언급하여 깊이를 더합니다.
6. 합/충/형 관계를 투자 맥락으로 해석합니다.
7. 십신 간 상생/상극을 판단·실행·인내 프레임으로 연결합니다.

## 7섹션 작성 가이드

### 섹션 1: 명식 해석
- 데이터: 4주 원국, 오행 균형
- 일주의 본질적 성격을 투자자 관점에서 풀이
- 오행 편중이 투자 성향에 미치는 영향
- 시주 미상이면 "3주 기준 해석" 명시
- 300~500자

### 섹션 2: 투자 DNA
- 데이터: 십신 분포, 일주
- 투자 성향 심층 분석
- investor_type이 왜 맞는지 설명
- 가장 강한/약한 십신이 만드는 투자 패턴
- 300~500자

### 섹션 3: {target_year} 세운 전략
- 데이터: 세운 × 명식
- 세운의 십신이 올해 투자에 의미하는 바
- 상반기/하반기 에너지 전환점
- 300~500자

### 섹션 4: 월별 타이밍
- 데이터: 12개월 월운 × 일주
- 매매 적기(공격)·관망기(수비)·위험기(회피) 3단계 분류
- 서술형으로 작성
- 주의할 달은 이유와 함께 상세히
- 400~600자

### 섹션 5: 현재 대운
- 데이터: 대운 × 명식
- 인생 전체 투자 흐름에서 지금의 국면
- 해야 할 것과 하지 말아야 할 것
- 300~500자

### 섹션 6: 나의 투자 스타일
- 데이터: 종합 분석
- 가치투자/모멘텀/배당/단기트레이딩/인덱스 적립 중 적합 스타일 + 보조 스타일 1개
- 이유 포함
- 300~500자

### 섹션 7: 투자 함정
- 데이터: 신살, 충/형 관계
- 가장 위험한 투자 습관 2~3가지
- 발동 상황과 방어법
- 말미에 "본 감정서는 명리학적 해석이며 투자 권유가 아닙니다" 고지 필수
- 300~500자

## 출력 형식

반드시 아래 JSON 형식으로만 응답하세요. JSON 외의 텍스트를 포함하지 마세요.

```json
{
  "sections": [
    {
      "id": 1,
      "title": "명식 해석",
      "content": "본문 300~500자",
      "highlight": "핵심 한 줄 20자 이내"
    },
    {
      "id": 2,
      "title": "투자 DNA",
      "content": "...",
      "highlight": "..."
    },
    {
      "id": 3,
      "title": "{target_year} 세운 전략",
      "content": "...",
      "highlight": "..."
    },
    {
      "id": 4,
      "title": "월별 타이밍",
      "content": "...",
      "highlight": "..."
    },
    {
      "id": 5,
      "title": "현재 대운",
      "content": "...",
      "highlight": "..."
    },
    {
      "id": 6,
      "title": "나의 투자 스타일",
      "content": "...",
      "highlight": "..."
    },
    {
      "id": 7,
      "title": "투자 함정",
      "content": "...",
      "highlight": "..."
    }
  ]
}
```\
"""


def build_messages(context: dict[str, Any]) -> list[dict[str, str]]:
    """시스템 프롬프트와 유저 메시지를 조립하여 반환한다."""
    target_year = context.get("sewoon", {}).get("pillar", "")
    # 세운 pillar에서 연도 추론 불가하므로 birth + target 정보 활용
    # 실제 target_year는 caller가 전달

    system_text = SYSTEM_PROMPT

    user_text = (
        "아래 사주 데이터를 기반으로 투자 감정서 7섹션을 작성해주세요.\n\n"
        + json.dumps(context, ensure_ascii=False, indent=2)
    )

    return [
        {"role": "system", "content": system_text},
        {"role": "user", "content": user_text},
    ]
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `PYTHONPATH=src ./.venv/Scripts/python.exe -m pytest tests/test_report_prompt.py -v`
Expected: 전체 PASS

- [ ] **Step 5: Commit**

```bash
git add src/sajucandle/saju/report_prompt.py tests/test_report_prompt.py
git commit -m "feat(report): add prompt builder with 7-section guide"
```

---

### Task 4: report_generator.py — Claude API 호출 + JSON 파싱

**Files:**
- Create: `src/sajucandle/saju/report_generator.py`
- Test: `tests/test_report_generator.py`

- [ ] **Step 1: 테스트 작성**

`tests/test_report_generator.py`:

```python
"""tests/test_report_generator.py — Claude API 호출 + 파싱 테스트 (mock)."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
from sajucandle.saju.report_generator import generate_report, parse_sections


VALID_SECTIONS = {
    "sections": [
        {"id": i, "title": f"섹션{i}", "content": f"내용{i}", "highlight": f"핵심{i}"}
        for i in range(1, 8)
    ]
}

VALID_JSON_STR = json.dumps(VALID_SECTIONS, ensure_ascii=False)


class TestParseSections:
    def test_parse_clean_json(self):
        result = parse_sections(VALID_JSON_STR)
        assert len(result) == 7
        assert result[0]["id"] == 1
        assert result[6]["id"] == 7

    def test_parse_json_in_code_block(self):
        text = f"```json\n{VALID_JSON_STR}\n```"
        result = parse_sections(text)
        assert len(result) == 7

    def test_parse_json_with_surrounding_text(self):
        text = f"분석 결과입니다:\n{VALID_JSON_STR}\n\n감사합니다."
        result = parse_sections(text)
        assert len(result) == 7

    def test_parse_invalid_json_raises(self):
        with pytest.raises(ValueError, match="JSON"):
            parse_sections("이것은 JSON이 아닙니다")

    def test_parse_missing_sections_key_raises(self):
        with pytest.raises(ValueError, match="sections"):
            parse_sections('{"data": []}')

    def test_parse_wrong_section_count_raises(self):
        bad = {"sections": [{"id": 1, "title": "a", "content": "b", "highlight": "c"}]}
        with pytest.raises(ValueError, match="7"):
            parse_sections(json.dumps(bad))


SAMPLE_CONTEXT = {
    "birth": {"year": 1985, "month": 3, "day": 15, "hour": 14, "gender": "M"},
    "day_master": {"stem": "癸", "element": "水", "yin_yang": "음"},
}


class TestGenerateReport:
    @pytest.mark.asyncio
    async def test_successful_generation(self):
        mock_message = MagicMock()
        mock_message.content = [MagicMock(text=VALID_JSON_STR)]

        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(return_value=mock_message)

        with patch("sajucandle.saju.report_generator.anthropic.AsyncAnthropic",
                    return_value=mock_client):
            sections = await generate_report(SAMPLE_CONTEXT)

        assert len(sections) == 7
        assert sections[0]["id"] == 1

    @pytest.mark.asyncio
    async def test_retry_on_parse_failure(self):
        """첫 번째 시도 파싱 실패 → 재시도 성공."""
        bad_message = MagicMock()
        bad_message.content = [MagicMock(text="잘못된 응답")]

        good_message = MagicMock()
        good_message.content = [MagicMock(text=VALID_JSON_STR)]

        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(
            side_effect=[bad_message, good_message]
        )

        with patch("sajucandle.saju.report_generator.anthropic.AsyncAnthropic",
                    return_value=mock_client):
            sections = await generate_report(SAMPLE_CONTEXT)

        assert len(sections) == 7
        assert mock_client.messages.create.call_count == 2

    @pytest.mark.asyncio
    async def test_raises_after_all_retries_fail(self):
        bad_message = MagicMock()
        bad_message.content = [MagicMock(text="잘못된 응답")]

        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(return_value=bad_message)

        with patch("sajucandle.saju.report_generator.anthropic.AsyncAnthropic",
                    return_value=mock_client):
            with pytest.raises(ValueError):
                await generate_report(SAMPLE_CONTEXT)

    @pytest.mark.asyncio
    async def test_uses_sonnet_for_standard_tier(self):
        mock_message = MagicMock()
        mock_message.content = [MagicMock(text=VALID_JSON_STR)]

        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(return_value=mock_message)

        with patch("sajucandle.saju.report_generator.anthropic.AsyncAnthropic",
                    return_value=mock_client):
            await generate_report(SAMPLE_CONTEXT, tier="standard")

        call_kwargs = mock_client.messages.create.call_args[1]
        assert "sonnet" in call_kwargs["model"]

    @pytest.mark.asyncio
    async def test_no_api_key_raises(self):
        with patch.dict("os.environ", {}, clear=True):
            with patch("sajucandle.saju.report_generator.anthropic.AsyncAnthropic",
                        side_effect=Exception("API key missing")):
                with pytest.raises(Exception):
                    await generate_report(SAMPLE_CONTEXT)
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `PYTHONPATH=src ./.venv/Scripts/python.exe -m pytest tests/test_report_generator.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: 구현**

`src/sajucandle/saju/report_generator.py`:

```python
"""감정서 생성기 — Anthropic Claude API 호출 + JSON 파싱."""
from __future__ import annotations

import json
import re
from typing import Any

import anthropic

from sajucandle.saju.report_prompt import build_messages

MODEL_STANDARD = "claude-sonnet-4-6"
MODEL_PREMIUM = "claude-opus-4-6"
MAX_TOKENS = 4096
TIMEOUT = 60.0
MAX_RETRIES = 2


def parse_sections(text: str) -> list[dict[str, Any]]:
    """Claude 응답 텍스트에서 7섹션 JSON을 추출한다."""
    # code block 안의 JSON 시도
    code_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if code_match:
        text = code_match.group(1)

    # JSON 객체 추출
    brace_start = text.find("{")
    brace_end = text.rfind("}") + 1
    if brace_start < 0 or brace_end <= brace_start:
        raise ValueError("JSON 객체를 찾을 수 없습니다")

    try:
        parsed = json.loads(text[brace_start:brace_end])
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON 파싱 실패: {e}") from e

    if "sections" not in parsed:
        raise ValueError("'sections' 키가 없습니다")

    sections = parsed["sections"]
    if len(sections) != 7:
        raise ValueError(f"섹션 수가 7개가 아닙니다: {len(sections)}")

    return sections


async def generate_report(
    context: dict[str, Any],
    tier: str = "standard",
) -> list[dict[str, Any]]:
    """Claude API를 호출하여 7섹션 감정서를 생성한다."""
    model = MODEL_STANDARD if tier == "standard" else MODEL_PREMIUM
    messages = build_messages(context)

    client = anthropic.AsyncAnthropic()

    last_error: Exception | None = None
    for attempt in range(MAX_RETRIES):
        response = await client.messages.create(
            model=model,
            max_tokens=MAX_TOKENS,
            system=messages[0]["content"],
            messages=[{"role": "user", "content": messages[1]["content"]}],
            timeout=TIMEOUT,
        )

        response_text = response.content[0].text
        try:
            return parse_sections(response_text)
        except ValueError as e:
            last_error = e
            continue

    raise ValueError(f"감정서 파싱 실패 ({MAX_RETRIES}회 시도): {last_error}")
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `PYTHONPATH=src ./.venv/Scripts/python.exe -m pytest tests/test_report_generator.py -v`
Expected: 전체 PASS

- [ ] **Step 5: Commit**

```bash
git add src/sajucandle/saju/report_generator.py tests/test_report_generator.py
git commit -m "feat(report): add Claude API generator with JSON parsing"
```

---

### Task 5: POST /api/saju/report 엔드포인트

**Files:**
- Modify: `src/sajucandle/api/main.py`
- Test: `tests/test_api_report.py`

- [ ] **Step 1: 테스트 작성**

`tests/test_api_report.py`:

```python
"""tests/test_api_report.py — POST /api/saju/report 엔드포인트 테스트."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
from fastapi.testclient import TestClient
from sajucandle.api.main import app


@pytest.fixture
def client():
    return TestClient(app)


MOCK_SECTIONS = [
    {"id": i, "title": f"섹션{i}", "content": f"내용{i}", "highlight": f"핵심{i}"}
    for i in range(1, 8)
]


class TestReportEndpoint:
    def test_report_returns_200(self, client: TestClient):
        with patch("sajucandle.api.main.generate_report",
                    new_callable=AsyncMock, return_value=MOCK_SECTIONS):
            resp = client.post("/api/saju/report", json={
                "year": 1985, "month": 3, "day": 15,
                "hour": 14, "gender": "M",
            })
        assert resp.status_code == 200

    def test_report_response_shape(self, client: TestClient):
        with patch("sajucandle.api.main.generate_report",
                    new_callable=AsyncMock, return_value=MOCK_SECTIONS):
            resp = client.post("/api/saju/report", json={
                "year": 1985, "month": 3, "day": 15,
                "hour": 14, "gender": "M",
            })
        data = resp.json()
        assert "report_id" in data
        assert "target_year" in data
        assert "tier" in data
        assert "sections" in data
        assert len(data["sections"]) == 7

    def test_report_id_format(self, client: TestClient):
        with patch("sajucandle.api.main.generate_report",
                    new_callable=AsyncMock, return_value=MOCK_SECTIONS):
            resp = client.post("/api/saju/report", json={
                "year": 1985, "month": 3, "day": 15,
                "hour": 14, "gender": "M",
            })
        data = resp.json()
        assert data["report_id"].startswith("rpt_")
        assert "M" in data["report_id"]

    def test_report_without_hour(self, client: TestClient):
        with patch("sajucandle.api.main.generate_report",
                    new_callable=AsyncMock, return_value=MOCK_SECTIONS):
            resp = client.post("/api/saju/report", json={
                "year": 1985, "month": 3, "day": 15,
                "gender": "F",
            })
        assert resp.status_code == 200
        data = resp.json()
        assert "00F" in data["report_id"]

    def test_report_no_api_key_returns_503(self, client: TestClient):
        with patch("sajucandle.api.main.generate_report",
                    new_callable=AsyncMock,
                    side_effect=Exception("API key")):
            with patch.dict("os.environ", {}, clear=False):
                with patch("sajucandle.api.main._has_anthropic_key",
                            return_value=False):
                    resp = client.post("/api/saju/report", json={
                        "year": 1985, "month": 3, "day": 15,
                        "gender": "M",
                    })
        assert resp.status_code == 503

    def test_report_parse_error_returns_502(self, client: TestClient):
        with patch("sajucandle.api.main._has_anthropic_key", return_value=True):
            with patch("sajucandle.api.main.generate_report",
                        new_callable=AsyncMock,
                        side_effect=ValueError("파싱 실패")):
                resp = client.post("/api/saju/report", json={
                    "year": 1985, "month": 3, "day": 15,
                    "gender": "M",
                })
        assert resp.status_code == 502
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `PYTHONPATH=src ./.venv/Scripts/python.exe -m pytest tests/test_api_report.py -v`
Expected: FAIL — `ImportError` (generate_report, _has_anthropic_key 미정의)

- [ ] **Step 3: main.py에 엔드포인트 추가**

`src/sajucandle/api/main.py` 파일 끝에 추가:

```python
# ── 감정서 API ─────────────────────────────────────────────────────────────
import os
import asyncio
from sajucandle.saju.report_context import collect_report_context
from sajucandle.saju.report_generator import generate_report


def _has_anthropic_key() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


class ReportRequest(BaseModel):
    year: int
    month: int
    day: int
    hour: Optional[int] = None
    gender: str = "M"


@app.post("/api/saju/report")
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
        sections = await generate_report(context)
    except ValueError:
        raise HTTPException(status_code=502, detail="감정서 생성 중 오류가 발생했습니다")
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=504,
            detail="감정서 생성 시간이 초과되었습니다. 잠시 후 다시 시도해주세요",
        )
    except Exception:
        raise HTTPException(status_code=502, detail="감정서 생성 중 오류가 발생했습니다")

    return {
        "report_id": report_id,
        "target_year": now_year,
        "tier": "standard",
        "sections": sections,
    }
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `PYTHONPATH=src ./.venv/Scripts/python.exe -m pytest tests/test_api_report.py -v`
Expected: 전체 PASS

- [ ] **Step 5: 기존 API 테스트 회귀 확인**

Run: `PYTHONPATH=src ./.venv/Scripts/python.exe -m pytest tests/test_api_saju.py tests/test_api_report.py -v`
Expected: 전체 PASS

- [ ] **Step 6: Commit**

```bash
git add src/sajucandle/api/main.py tests/test_api_report.py
git commit -m "feat(report): add POST /api/saju/report endpoint"
```

---

### Task 6: 린트 + 전체 테스트 통과

**Files:**
- (이전 Task에서 생성/수정한 모든 파일)

- [ ] **Step 1: ruff 린트**

Run: `PYTHONPATH=src ./.venv/Scripts/python.exe -m ruff check src/sajucandle/saju/report_context.py src/sajucandle/saju/report_prompt.py src/sajucandle/saju/report_generator.py src/sajucandle/api/main.py tests/test_report_context.py tests/test_report_prompt.py tests/test_report_generator.py tests/test_api_report.py`
Expected: 에러 없음

린트 에러가 있으면 수정한다.

- [ ] **Step 2: 전체 pytest 테스트**

Run: `PYTHONPATH=src ./.venv/Scripts/python.exe -m pytest tests/test_report_context.py tests/test_report_prompt.py tests/test_report_generator.py tests/test_api_report.py tests/test_api_saju.py tests/test_investor_profile.py -v`
Expected: 전체 PASS

- [ ] **Step 3: 린트 수정 시 Commit**

```bash
git add -u
git commit -m "fix: lint cleanup for report modules"
```

---

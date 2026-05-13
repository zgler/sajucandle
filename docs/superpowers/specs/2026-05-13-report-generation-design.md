# 나의 투자 사주 감정서 — 설계 스펙

## 1. 제품 정의

Claude API로 생성하는 개인 맞춤 투자 사주 리포트. 사용자의 명식(4주)·십신·오행·세운·대운·신살 데이터를 기존 사주 엔진에서 수집하고, Claude Sonnet에 전달하여 7섹션 감정서를 생성한다. 웹 페이지로 렌더링하며, 2섹션 무료 프리뷰 + 5섹션 블러 처리로 유료 전환을 유도한다.

### 타겟

40~50대 한국 투자자. 오프라인 사주 상담(10~20만원) 경험이 있거나 관심 있는 층.

### 가격

- 기본: 4,900원 (Sonnet 생성) — API 원가 ~320원, 마진 93%
- 프리미엄: 9,900원 (Opus 생성) — 이번 스펙에서 미구현, 향후 확장

## 2. 스코프

### 포함

- 사주 컨텍스트 수집 모듈 (`saju/report_context.py`)
- Claude API 호출 모듈 (`saju/report_generator.py`)
- 시스템 프롬프트 + 섹션별 작성 가이드 (`saju/report_prompt.py`)
- FastAPI 엔드포인트 `POST /api/saju/report`
- 프론트엔드 `/report` 페이지 (블러 프리뷰 포함)
- 프로필 페이지에 감정서 CTA 추가
- localStorage 캐싱
- 에러 처리 (API 키 미설정, 타임아웃)

### 제외

- 결제 연동 (Toss Payments / KakaoPay) — 별도 스펙
- Opus 프리미엄 티어 — 향후 확장
- PDF 다운로드 — 향후 확장
- 서버 DB 저장 — MVP는 localStorage
- 푸시 알림
- 관리자 대시보드

## 3. 아키텍처

```
프론트엔드                    백엔드                        외부
──────────                  ──────                       ──────
/report 페이지               POST /api/saju/report
  ├─ CTA 클릭                 ├─ 1단계: 컨텍스트 수집
  ├─ 로딩 애니메이션            │   report_context.py
  │   "감정서 작성 중..."       │   ├─ calculate_saju()        manseryeok/core
  │                           │   ├─ tengod_distribution()   saju/tengod
  │                           │   ├─ element_balance()       saju/constants
  │                           │   ├─ compute_sewoon (12개월)  saju/sewoon
  │                           │   ├─ compute_daeun()         saju/daeun
  │                           │   ├─ find_shinsal()          saju/shinsal
  │                           │   └─ pillar_compat_score()   saju/relations
  │                           │
  │                           ├─ 2단계: 프롬프트 조립
  │                           │   report_prompt.py
  │                           │   ├─ system prompt
  │                           │   └─ user message (컨텍스트 JSON)
  │                           │
  │                           └─ 3단계: Claude API 호출
  │                               report_generator.py
  │                               └─ anthropic.messages.create()
  │                                    ↕
  ◀── 7섹션 JSON 응답                Anthropic API
  │
  ├─ 섹션 1~2: 전체 표시
  ├─ 섹션 3~7: 블러 + CTA
  └─ localStorage 캐싱
```

## 4. 백엔드 모듈

### 4.1 `saju/report_context.py` — 컨텍스트 수집

기존 사주 엔진 모듈을 조합하여 Claude에 전달할 구조화된 컨텍스트를 생성한다.

```python
def collect_report_context(
    year: int, month: int, day: int,
    hour: int | None, gender: str,
    target_year: int,
) -> dict:
```

반환 구조:
```json
{
  "birth": {"year": 1985, "month": 3, "day": 15, "hour": null, "gender": "M"},
  "pillars": {
    "year": {"pillar": "乙丑", "stem": "乙", "branch": "丑"},
    "month": {"pillar": "己卯", "stem": "己", "branch": "卯"},
    "day": {"pillar": "癸丑", "stem": "癸", "branch": "丑"},
    "hour": null
  },
  "day_master": {"stem": "癸", "element": "水", "yin_yang": "음"},
  "tengod_distribution": {"비겁": 2, "식상": 0, "재성": 1, "관성": 2, "인성": 1},
  "element_balance": {"木": 2, "火": 0, "土": 3, "金": 0, "水": 1},
  "dominant_group": "관성",
  "investor_type": "원칙형",
  "sewoon": {"pillar": "丙午", "stem": "丙", "tengod": "정재"},
  "monthly_pillars": [
    {"month": 1, "pillar": "己丑", "stem": "己", "tengod": "편관"},
    {"month": 2, "pillar": "庚寅", "stem": "庚", "tengod": "정관"},
    ...
  ],
  "current_daeun": {
    "pillar": "乙亥", "stem": "乙",
    "tengod": "식신", "start_age": 33, "end_age": 43
  },
  "shinsal": ["천을귀인", "역마살"],
  "relations": {
    "day_sewoon": {"pros": [...], "cons": [...]},
    "day_daeun": {"pros": [...], "cons": [...]}
  }
}
```

12개월 월운은 `compute_sewoon_wolwoon_ilji(calc, datetime(target_year, m, 1, 12))` 를 1~12월 반복 호출하여 수집한다.

### 4.2 `saju/report_prompt.py` — 프롬프트

시스템 프롬프트와 섹션별 작성 가이드를 상수로 정의한다.

**시스템 프롬프트 원칙:**
- 역할: 30년 경력 투자 전문 사주 감정사
- 명리 용어 사용 + 괄호 안 쉬운 설명 병기
- 단정적 톤 ("~합니다", "~입니다")
- 추상적 운세가 아닌 구체적 투자 행동 제안
- 특정 종목·가격·수익률 언급 금지
- 천간뿐 아니라 지지의 지장간까지 언급
- 합/충/형 관계를 투자 맥락으로 해석
- 십신 간 상생/상극을 판단·실행·인내 프레임으로 연결

**섹션별 작성 가이드:**

| # | 제목 | 데이터 소스 | 지시 |
|---|---|---|---|
| 1 | 명식 해석 | 4주 원국, 오행 균형 | 일주의 본질적 성격을 투자자 관점에서 풀이. 오행 편중이 투자 성향에 미치는 영향. 시주 미상이면 "3주 기준 해석" 명시 |
| 2 | 투자 DNA | 십신 분포, 일주 | 투자 성향 심층 분석. investor_type이 왜 맞는지, 가장 강한/약한 십신이 만드는 투자 패턴 |
| 3 | 2026 세운 전략 | 세운 × 명식 | 세운의 십신이 올해 투자에 의미하는 바. 상반기/하반기 에너지 전환점 |
| 4 | 월별 타이밍 | 12개월 월운 × 일주 | 매매 적기(공격)·관망기(수비)·위험기(회피) 3단계 분류. 서술형. 주의할 달은 이유와 함께 상세히 |
| 5 | 현재 대운 | 대운 × 명식 | 인생 전체 투자 흐름에서 지금의 국면. 해야 할 것과 하지 말아야 할 것 |
| 6 | 나의 투자 스타일 | 종합 분석 | 가치투자/모멘텀/배당/단기트레이딩/인덱스 적립 중 적합 스타일 + 보조 스타일 1개. 이유 포함 |
| 7 | 투자 함정 | 신살, 충/형 관계 | 가장 위험한 투자 습관 2~3가지. 발동 상황과 방어법. 말미에 "명리 해석이며 투자 권유 아님" 고지 |

**출력 포맷:**
```json
{
  "sections": [
    {
      "id": 1,
      "title": "명식 해석",
      "content": "본문 300~500자",
      "highlight": "핵심 한 줄 20자 이내"
    }
  ]
}
```

### 4.3 `saju/report_generator.py` — Claude API 호출

```python
import anthropic

async def generate_report(context: dict, tier: str = "standard") -> dict:
```

- `tier="standard"` → `claude-sonnet-4-6`, max_tokens=4096
- `tier="premium"` → `claude-opus-4-6` (향후)
- 환경변수 `ANTHROPIC_API_KEY` 필수
- 타임아웃: 60초
- 응답 파싱: JSON 블록 추출 → 7섹션 dict
- 파싱 실패 시 재시도 1회

### 4.4 FastAPI 엔드포인트

**`POST /api/saju/report`**

요청:
```json
{
  "year": 1985,
  "month": 3,
  "day": 15,
  "hour": null,
  "gender": "M"
}
```

응답 (성공):
```json
{
  "report_id": "rpt_1985031500M_2026",
  "target_year": 2026,
  "tier": "standard",
  "sections": [
    {"id": 1, "title": "명식 해석", "content": "...", "highlight": "..."},
    {"id": 2, "title": "투자 DNA", "content": "...", "highlight": "..."},
    {"id": 3, "title": "2026 세운 전략", "content": "...", "highlight": "..."},
    {"id": 4, "title": "월별 타이밍", "content": "...", "highlight": "..."},
    {"id": 5, "title": "현재 대운", "content": "...", "highlight": "..."},
    {"id": 6, "title": "나의 투자 스타일", "content": "...", "highlight": "..."},
    {"id": 7, "title": "투자 함정", "content": "...", "highlight": "..."}
  ]
}
```

응답 (에러):
- `ANTHROPIC_API_KEY` 미설정 → 503 `{"detail": "감정서 서비스 준비 중입니다"}`
- Claude API 타임아웃 → 504 `{"detail": "감정서 생성 시간이 초과되었습니다. 잠시 후 다시 시도해주세요"}`
- Claude API 응답 파싱 실패 → 502 `{"detail": "감정서 생성 중 오류가 발생했습니다"}`

`report_id` 형식: `rpt_{year}{month:02d}{day:02d}{hour:02d|00}{gender}_{targetYear}`
동일 사용자 + 동일 연도 → 동일 report_id → 프론트 캐시 키로 사용.

## 5. 프론트엔드

### 5.1 신규 페이지: `/report`

**진입 경로:** 프로필 페이지(`/profile`) 하단에 CTA 버튼 추가
> "나의 투자 감정서 보기 →"

**페이지 상태:**

1. **로딩**: "감정서 작성 중..." 애니메이션 (15~20초 예상)
2. **완료**: 7섹션 렌더링
   - 섹션 1~2: 전체 표시 (highlight 강조 박스 + content 본문)
   - 섹션 3~7: 블러 처리 (CSS `filter: blur(8px)` + 그라데이션 오버레이)
   - 블러 영역 중앙에 CTA: "감정서 전체 보기 4,900원"
   - CTA 클릭 → "결제 기능 준비 중입니다" 토스트 (placeholder)
3. **에러**: 에러 메시지 + "다시 시도" 버튼

**캐싱:**
- 키: `saju_report_{report_id}`
- 값: 전체 응답 JSON
- 같은 연도 재방문 시 API 재호출 없이 캐시에서 로드
- 연도 변경 시 (1월 1일) 캐시 무효화

### 5.2 신규 컴포넌트

**`ReportSection`**: 개별 섹션 카드
- props: `section`, `blurred: boolean`
- 블러 시: content에 `blur(8px)` + `select-none` + 오버레이

**`ReportPage`**: 전체 리포트 페이지
- 로딩/완료/에러 상태 관리
- 섹션 리스트 렌더링
- 블러 CTA

### 5.3 기존 페이지 수정

**`/profile` (profile/page.tsx):**
- "카카오톡으로 공유하기" 버튼 위에 감정서 CTA 추가:
  ```
  ┌─────────────────────────────────────┐
  │  🕯️ 나의 투자 감정서                  │
  │  사주로 읽는 2026년 투자 전략          │
  │           [감정서 보기 →]             │
  └─────────────────────────────────────┘
  ```

### 5.4 신규 타입

```typescript
interface ReportSection {
  id: number;
  title: string;
  content: string;
  highlight: string;
}

interface ReportResponse {
  report_id: string;
  target_year: number;
  tier: string;
  sections: ReportSection[];
}
```

### 5.5 API 클라이언트 추가

`lib/api.ts`에 `fetchReport()` 함수 추가.
- POST `/api/saju/report`
- 타임아웃: 60초 (일반 API보다 김)

## 6. 의존성

### 백엔드
- `anthropic` 파이썬 패키지 — `pyproject.toml`에 추가
- 환경변수: `ANTHROPIC_API_KEY`

### 프론트엔드
- 추가 의존성 없음 (Tailwind CSS blur 유틸리티 사용)

## 7. 테스트 전략

### 백엔드
- `test_report_context.py`: 컨텍스트 수집이 올바른 구조를 반환하는지 (Claude API 호출 없이)
- `test_report_prompt.py`: 프롬프트 조립이 올바른 형식인지
- `test_report_generator.py`: Claude API mock으로 응답 파싱 테스트
- `test_api_report.py`: 엔드포인트 통합 테스트 (Claude API mock)

### 프론트엔드
- TypeScript 타입체크
- 빌드 통과
- 브라우저 수동 검증: 로딩 → 렌더링 → 블러 → CTA

## 8. 향후 확장

1. **결제 연동** → 블러 해제를 결제 완료 조건으로 변경
2. **Opus 프리미엄 티어** → tier="premium" 파라미터 활성화
3. **PDF 다운로드** → 결제 완료 유저에게 PDF 변환 제공
4. **서버 캐싱** → DB에 생성된 리포트 저장 (재생성 비용 절감)
5. **연간 갱신** → 매년 1월 "2027 감정서 나왔어요" 푸시

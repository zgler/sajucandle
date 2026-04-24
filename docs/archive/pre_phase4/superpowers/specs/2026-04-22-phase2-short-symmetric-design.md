# Phase 2 설계 — 숏 대칭 + 5등급

- 날짜: 2026-04-22
- 대상: Phase 2 — 숏(하락) 신호 대칭화 + 5등급 체계
- 상태: Draft (설계자 검토 대기)
- 기반 커밋: `b0df064` (main)
- 선행 성과: Phase 0 현황 파악 + Phase 1 백테스트 하네스 (12 Task 완료)

---

## 1. 목적

현재 분석 엔진은 롱(상승) 관점만 지원. 하락장·DOWNTREND에서는 "관망"으로만 표기되어 유의미한 숏 시그널을 놓친다. Phase 2에서는 분석 엔진과 등급 체계를 **양방향 대칭**으로 재구성하여 숏 신호를 발생시키고, TradeSetup·카드·DB·백테스트 하네스까지 방향(Direction) 개념을 일관되게 주입한다. Phase 1의 run_id 기반 A/B 인프라로 "롱 전용 vs 대칭"을 정량 비교하여 회귀 없음을 증명한다.

---

## 2. 목표 / 범위

### 포함
- **5등급 체계**: 강진입_L / 진입_L / 관망 / 진입_S / 강진입_S
- `_grade_signal` 양방향 판정 로직 (structure + alignment + long/short score)
- DOWNTREND/BREAKDOWN + 과매수(RSI) + BEARISH 정렬 → 숏 신호화
- TradeSetup 숏 버전: `entry > SL`, `entry < TP1/TP2` → `entry > TP1/TP2`, `entry < SL` (가격 역전)
- Telegram 카드: 방향 뱃지(🟢 롱 / 🔴 숏 / 🟡 관망) + 세팅 블록 방향 표기
- signal_log 스키마: `signal_direction` 신규 컬럼 + signal_grade 값 확장 (migration 006)
- Phase 1 하네스 `--mode longonly|symmetric` 옵션 + run_id suffix 규칙
- 단위/통합 테스트 + 회귀 스냅샷 테스트

### 범위 밖 (Phase 3~4)
- RSI divergence (Phase 3)
- Volatility regime (변동성 체제 감지) — Phase 3
- BREAKOUT/BREAKDOWN 판정 임계 재튜닝 — Phase 3
- `_SL_ATR_MULT` 등 튜닝 상수 조정 — Phase 4
- 포지션 사이징, 수수료/슬리피지 반영 — Phase 4
- 공매도 가능성(규제/차입) 체크 — 운영 단계에서 별도 이슈

---

## 3. 설계 결정 (8개)

### 3.1 등급 체계

| 옵션 | 내용 | 장점 | 단점 |
|------|------|------|------|
| **A** | 5등급 문자열 (`강진입_L/진입_L/관망/진입_S/강진입_S`) | DB 단일 컬럼, 카드 렌더 단순, 기존 집계 쿼리와 호환 쉬움 | "관망"은 direction이 모호, 문자열 파싱 필요 |
| B | 7등급 (+약진입_L/약진입_S) | 세분화 | TradeSetup 트리거 경계가 복잡해짐 |
| C | 2D: `grade(강/중/약/회피)` + `direction(L/S/NEUTRAL)` | 쿼리 깔끔 | 기존 signal_grade 컬럼을 깨거나 이중 유지, 회귀 위험 |

**추천: A** — 운영·DB·카드 모두 단일 진입점 유지. 단 **결정 3.6**에서 `signal_direction` 관찰용 컬럼을 redundant 하게 추가하여 쿼리 편의를 확보한다 (즉 C의 "둘 다"를 부분 채택).

### 3.2 판정 기준 (스칼라 vs 2-score)

| 옵션 | 내용 | 장점 | 단점 |
|------|------|------|------|
| A | 기존 `final_score` 유지 + `structure.state`로 방향 재매핑 | 최소 변경, 하위호환 | 대칭성 보장이 암묵적, BREAKDOWN인데 BULLISH alignment 같은 모순 케이스 처리 난해 |
| **B** | `long_score`, `short_score` 별도 산출 → `direction = argmax`, `strength = max` | 대칭 명확, 백테스트 해석 쉬움, RANGE에서도 미세 편향 가능 | 공수 ↑ (각 부-모듈 대칭화 필요) |
| C | composite.py 자체를 신호 generator로 리팩터 | 최고 설계 | Phase 2 범위 초과 |

**추천: B** — 현재 `structure.score`, `alignment.score`는 전부 "롱 유리도"로 정의된 것. 이를 `long_signal_score` + `short_signal_score` 두 벡터로 분리. `final = 0.1*saju + 0.9*analysis.*_score`를 양 방향 모두 계산하고 강한 쪽이 방향을 결정.

### 3.3 structure_state ↔ direction 매핑

| 구조 | Long 점수 | Short 점수 | 허용 방향 |
|------|-----------|------------|-----------|
| UPTREND | 70 | 20 | LONG only |
| BREAKOUT | 80 | 15 | LONG only |
| RANGE | 50 | 50 | NEUTRAL (관망) |
| BREAKDOWN | 30 | 70 | SHORT only |
| DOWNTREND | 20 | 80 | SHORT only |

**추천**: RANGE는 NEUTRAL 고정. 이유: 박스권에서 RSI/MA-slope 편향은 false positive 비용이 크고, Phase 3에서 divergence/volatility 도입 시 자연스러운 hook이 됨. BREAKOUT/BREAKDOWN은 각각 방향 명확하므로 반대 방향 점수는 보수적으로 낮게 고정.

### 3.4 RSI / 오실레이터 대칭화

현재 `_rsi_score`는 oversold(≤30)→70, overbought(≥70)→20 으로 **롱 편향**.

- **롱**: oversold 가점, overbought 감점 (기존 유지)
- **숏**: overbought 가점, oversold 감점 (대칭 역전)

```
rsi_long_score(rsi):  ≤30→70, ≤45→55, ≤55→50, ≤70→40, else→20   (기존)
rsi_short_score(rsi): ≥70→70, ≥55→55, ≥45→50, ≥30→40, else→20   (신규·대칭)
```

`_volume_score`는 방향 중립 (거래량 관심도만 측정) — 양 방향 동일 점수 사용.

Phase 3 RSI divergence 도입 시 `long_score/short_score`는 **가산**이 아닌 **AND 조건**(divergence 확인되면 +보너스)으로 합쳐질 예정이므로, 현재 대칭 스코어 API는 Phase 3와 충돌 없음.

### 3.5 TradeSetup 숏 버전

공식:

```
Long (기존):
  SL  = entry - _SL_ATR_MULT  * atr   (support snap 시 lvl - buffer)
  TP1 = entry + _TP1_ATR_MULT * atr   (resistance snap 시 lvl - buffer)
  TP2 = entry + _TP2_ATR_MULT * atr

Short (신규):
  SL  = entry + _SL_ATR_MULT  * atr   (resistance snap 시 lvl + buffer)
  TP1 = entry - _TP1_ATR_MULT * atr   (support snap 시 lvl + buffer)
  TP2 = entry - _TP2_ATR_MULT * atr
```

- Resistance/Support 역할이 뒤집힘 (숏에서는 resistance가 손절 기준).
- `_SR_BUFFER_ATR`도 부호 반전 (lvl + buffer).
- `risk = SL - entry` (숏), `rr_tp* = (entry - tp*) / risk`.

**상수 분리 여부**:
- 옵션 A: L/S 동일 상수 (`_SL_ATR_MULT=1.5` 공유)
- 옵션 B: `_SL_ATR_MULT_LONG`, `_SL_ATR_MULT_SHORT` 분리
- **추천: A (공유)** — 초기 단순성 우선. Phase 4 튜닝 단계에서 백테스트로 비대칭 필요 시 분리. 근거: 숏의 반전 위험이 롱보다 크다는 것은 시장 속설이지만 실증 전엔 가정하지 않는다 (데이터가 결정).

### 3.6 DB 스키마 (migration 006)

| 옵션 | 내용 |
|------|------|
| A | `signal_grade` 값 종류만 확장 (기존 컬럼 그대로) |
| B | `signal_direction` 컬럼 신설만 (grade 유지) |
| **C** | 둘 다: grade 5종 + direction 3종 (LONG/SHORT/NEUTRAL) |

**추천: C**. 이유:
1. direction 컬럼은 "진입_L"/"진입_S" 별도 집계 없이 `WHERE signal_direction='SHORT'` 하나로 숏 기준 MFE/MAE 조회 가능.
2. signal_grade 문자열 변경이 누락된 쿼리도 direction 컬럼이 backstop 역할.
3. redundant지만 migration 단방향 이동 (기존 row는 `direction=NULL`, 집계 쿼리는 NULL 처리).

**Migration 006 계획**:

```sql
-- 006_signal_log_direction.sql
ALTER TABLE signal_log
    ADD COLUMN IF NOT EXISTS signal_direction TEXT
        CHECK (signal_direction IN ('LONG', 'SHORT', 'NEUTRAL'));

CREATE INDEX IF NOT EXISTS idx_signal_log_direction
    ON signal_log(signal_direction, sent_at DESC)
    WHERE signal_direction IS NOT NULL;
```

**하위호환**:
- 기존 row (Phase 0~1 운영 데이터): `signal_direction=NULL`, `signal_grade ∈ {강진입/진입/관망/회피}`.
- 신규 row (Phase 2+): `signal_direction ∈ {LONG,SHORT,NEUTRAL}`, `signal_grade ∈ {강진입_L/진입_L/관망/진입_S/강진입_S}`.
- 집계 쿼리 (`aggregate_signal_stats`, `/stats` 카드): NULL-safe COALESCE 또는 CASE WHEN으로 레거시→신 매핑 지원.
  - 매핑: `강진입 → 강진입_L`, `진입 → 진입_L`, `관망 → 관망`, `회피 → 관망` (회피는 Phase 2에서 제거, 가장 보수적으로 관망에 흡수).

### 3.7 Telegram 카드 변경

**등급 라벨**:
```
🟢 강진입 (롱)      🔥   ← 기존 강진입과 동의
🟢 진입 (롱)        👍
🟡 관망                   (방향 중립)
🔴 진입 (숏)        👎
🔴 강진입 (숏)      🧊
```

**TradeSetup 블록** (숏일 때):
```
세팅 (숏):
 진입 $1,234.56
 손절 $1,260.00 (+2.1%)      ← 숏은 손절이 위
 익절1 $1,200.00 (-2.8%)  익절2 $1,150.00 (-6.8%)
 R:R 1.3 / 3.2   리스크 2.1%
```

**카드 적용 지점**:
- `format.py` / `handlers.py:_format_signal_card`: 분기 + 세팅 블록 분기
- `_STRUCTURE_LABEL`: 유지 (구조 라벨은 롱/숏 무관)
- `_GUIDE_TEXT`: 5등급 + 방향 설명 추가
- `/stats` 카드: `by_grade` 5종 루프 + direction 별 집계 한 줄
- `DISCLAIMER`: 변경 없음
- 브로드캐스트 카드(`broadcast.py`): 동일 포맷터 사용 → 자동 반영 (별도 작업 불필요 확인)

### 3.8 백테스트 검증 전략 (Phase 1 하네스 활용)

**Run ID 네이밍 규칙**:
```
phase2-<git-sha7>-longonly     ← symmetric 플래그 OFF (regression baseline)
phase2-<git-sha7>-symmetric    ← symmetric 플래그 ON  (Phase 2 target)
```

**CLI 변경**:
- `src/sajucandle/backtest/cli.py`에 `--mode {longonly,symmetric}` 옵션 추가
- 기본값 `symmetric` (Phase 2 시점 이후의 basecase)
- `longonly` 모드는 `_grade_signal`에 분기 플래그 전달 → DOWNTREND/BREAKDOWN 숏 판정 skip

**비교 지표** (aggregate 결과):

| 지표 | longonly 기대 | symmetric 기대 |
|------|--------------|----------------|
| 관망/NEUTRAL 비율 | 40~60% | 20~40% ↓ |
| 롱 신호 수 (강진입_L + 진입_L) | baseline | **동일** (회귀 0) |
| 숏 신호 수 | 0 | > 0 |
| 하락장 기간 MFE 평균 (숏 신호만) | N/A | 양수(≥0.5%) |
| 전체 signal당 평균 MAE | baseline | baseline ±0.3%p |

**회귀 방어 (필수)**:
- 동일 기간·심볼·UserProfile에 대해 symmetric 모드에서 **롱 신호가 나야 할 날**은 반드시 `강진입_L` 또는 `진입_L`이 발생 (등급 강도 일치).
- 스냅샷 테스트: Phase 1 smoke 샘플 히스토리를 `conftest`에 고정 → Phase 2 이후 동일 입력 → 동일 롱 출력.

---

## 4. 아키텍처

### 4.1 변경 모듈

| 모듈 | 변경 내용 | 시그니처 영향 |
|------|-----------|----------------|
| `analysis/structure.py` | `StructureAnalysis`에 `long_score`, `short_score` 추가 | 하위호환 (`score` 유지, 신규 필드 default) |
| `analysis/multi_timeframe.py` | `Alignment.long_score`, `Alignment.short_score` 추가 | 하위호환 |
| `tech_analysis.py` | `_rsi_score_short` 신규. `_volume_score` 재사용 | 추가만 |
| `analysis/composite.py` | `AnalysisResult`에 `long_score`, `short_score`, `direction` 추가 | 하위호환 (`composite_score = max(long,short)` 로 호환) |
| `analysis/trade_setup.py` | `compute_trade_setup(direction=...)` 매개변수 추가 | 기본값 `LONG`으로 하위호환 |
| `signal_service.py` | `_grade_signal` 재작성 (양방향) + TradeSetup direction 주입 | 내부 함수, 외부 API 영향 없음 |
| `models.py` | `SignalDirection = Literal["LONG","SHORT","NEUTRAL"]` + `AnalysisSummary.direction`, `TradeSetupSummary.direction` 추가 | API 계약 **확장** (신규 필드, Optional) |
| `format.py` / `handlers.py` | 5등급 라벨, 숏 세팅 블록, _GUIDE_TEXT 업데이트 | 내부 |
| `repositories.py` | `insert_signal_log(signal_direction=...)` 매개변수 추가 | 호출부 수정 |
| `api.py` | `/v1/signal/stats` → by_direction 반환 추가 | 응답 확장 |
| `backtest/*.py` | `SymmetryMode` enum + run_id suffix 규칙 | CLI + 내부 |

### 4.2 분류 로직 흐름 (ASCII)

```
      klines_1h/4h/1d
           │
           ▼
  ┌───────────────────┐
  │  swing + structure │──► StructureAnalysis
  │                    │      .state, .long_score, .short_score
  └───────────────────┘
           │
           ▼
  ┌───────────────────┐
  │  multi_timeframe   │──► Alignment
  │                    │      .long_score, .short_score
  └───────────────────┘
           │
           ▼
  ┌───────────────────┐
  │  RSI(1h),Vol(1d)   │──► rsi_long/short_score, vol_score
  └───────────────────┘
           │
           ▼
  ┌───────────────────────────────────────────┐
  │  composite.py                              │
  │   long_score  = 0.45*st.long  + 0.35*al.L  │
  │                 + 0.10*rsi_L  + 0.10*vol   │
  │   short_score = 0.45*st.short + 0.35*al.S  │
  │                 + 0.10*rsi_S  + 0.10*vol   │
  │   direction   = LONG if long>short+δ       │
  │                 SHORT if short>long+δ      │
  │                 else NEUTRAL               │
  │   composite_score = max(long,short)        │
  └───────────────────────────────────────────┘
           │
           ▼
  ┌───────────────────┐    ┌──────────────────────┐
  │ signal_service     │    │ _grade_signal         │
  │  final = 0.1*saju  │───►│  (score, analysis,    │
  │       + 0.9*comp   │    │   direction) → grade  │
  └───────────────────┘    └──────────────────────┘
           │                         │
           ▼                         │
  direction == NEUTRAL ─ yes ─► 관망  │
           │ no                      │
           ▼                         │
  ┌───────────────────┐              │
  │ compute_trade_    │◄─────────────┘
  │ setup(direction)  │   (강진입_L/진입_L/강진입_S/진입_S 만)
  └───────────────────┘
```

### 4.3 핵심 함수 시그니처 변경

```python
# analysis/structure.py
@dataclass
class StructureAnalysis:
    state: MarketStructure
    last_high: Optional[SwingPoint]
    last_low: Optional[SwingPoint]
    score: int            # legacy: == long_score (하위호환)
    long_score: int       # 신규
    short_score: int      # 신규

# analysis/multi_timeframe.py
@dataclass
class Alignment:
    tf_1h: TrendDirection
    tf_4h: TrendDirection
    tf_1d: TrendDirection
    aligned: bool
    bias: Literal["bullish","mixed","bearish"]
    score: int            # legacy: == long_score
    long_score: int       # 신규
    short_score: int      # 신규

# analysis/composite.py
SignalDirection = Literal["LONG","SHORT","NEUTRAL"]

@dataclass
class AnalysisResult:
    structure: StructureAnalysis
    alignment: Alignment
    rsi_1h: float
    volume_ratio_1d: float
    composite_score: int              # = max(long,short) 하위호환
    reason: str
    sr_levels: list[SRLevel] = ...
    atr_1d: float = 0.0
    # 신규
    long_score: int = 0
    short_score: int = 0
    direction: SignalDirection = "NEUTRAL"

# analysis/trade_setup.py
def compute_trade_setup(
    entry: float,
    atr_1d: float,
    sr_levels: list[SRLevel],
    direction: SignalDirection = "LONG",   # 신규
) -> TradeSetup: ...

@dataclass
class TradeSetup:
    ...
    direction: SignalDirection = "LONG"    # 신규

# signal_service.py
def _grade_signal(score: int, analysis: AnalysisResult) -> str:
    """반환값: '강진입_L'|'진입_L'|'관망'|'진입_S'|'강진입_S'"""

# repositories.py
async def insert_signal_log(
    ...,
    signal_direction: Optional[str] = None,   # 신규 (default=None, 하위호환)
) -> int: ...
```

---

## 5. 데이터 모델

### 5.1 signal_log 확장

- Migration 006 신설 (section 3.6 쿼리).
- `signal_direction TEXT CHECK IN ('LONG','SHORT','NEUTRAL')` — Nullable (레거시 row 보존).
- 인덱스: `(signal_direction, sent_at DESC) WHERE signal_direction IS NOT NULL`.

### 5.2 하위호환 / 마이그레이션 경로

| 측면 | 방법 |
|------|------|
| 레거시 row (pre-Phase 2) | `signal_direction=NULL` 유지. 백필 X. |
| 집계 쿼리 | `COALESCE(signal_direction, CASE signal_grade WHEN '강진입' THEN 'LONG' WHEN '진입' THEN 'LONG' WHEN '관망' THEN 'NEUTRAL' ELSE 'NEUTRAL' END)` 패턴 |
| API 응답 `signal_grade` | 신규 값 반환. 클라이언트 파서는 suffix `_L`/`_S` 인식 추가. |
| Telegram 카드 | 라벨 테이블 확장 (5종). |
| Phase 1 백테스트 DB rows | `run_id`가 있는 row는 Phase 1 longonly 결과물. Phase 2 run은 symmetric suffix로 구분. |

---

## 6. 등급 판정 규칙

### 6.1 Long 진입 조건 (기존 유지 + 명시화)

```
direction == LONG AND final_score >= 75
  AND alignment.aligned AND alignment.bias == "bullish"
  AND structure.state in {UPTREND, BREAKOUT}
  → "강진입_L"

direction == LONG AND final_score >= 60
  → "진입_L"
```

### 6.2 Short 진입 조건 (신규, 대칭)

```
direction == SHORT AND final_score >= 75
  AND alignment.aligned AND alignment.bias == "bearish"
  AND structure.state in {DOWNTREND, BREAKDOWN}
  → "강진입_S"

direction == SHORT AND final_score >= 60
  → "진입_S"
```

### 6.3 관망 폴백

```
direction == NEUTRAL           → "관망"
final_score < 60               → "관망"
structure.state == RANGE       → direction 무시하고 "관망" 강제 (부분 대칭 방어)
```

**중요**: 기존 "회피" 등급 **제거**. 근거: 회피는 점수<40 케이스였으나, Phase 2 하에서는 "관망"과 실질적 차이 없음 (둘 다 TradeSetup 미생성). 카드 단순화.

### 6.4 δ (direction tie-break margin)

`|long_score - short_score| < δ` 이면 direction=NEUTRAL.

**추천값**: `δ = 10` (0~100 스케일에서 10점 차). Phase 4에서 튜닝.

---

## 7. TradeSetup 대칭

### 7.1 숏 버전 공식 (section 3.5 재확인)

- SL·TP 방향 역전
- Resistance/Support 역할 교환 (숏은 resistance로 SL snap, support로 TP snap)
- `risk_pct`, `rr_tp*` 계산식 부호 보정

### 7.2 L/S 상수 분리 여부

**결정**: 공유 (분리 안 함). Phase 4에서 백테스트 근거로 재검토.

---

## 8. UI / 출력

### 8.1 Telegram 카드 변경 위치

| 파일:함수 | 변경 |
|-----------|------|
| `handlers.py::_format_signal_card` | 등급 → 라벨 변환 테이블 5종, 방향 배지 줄 추가 |
| `handlers.py::_append_trade_setup_block` | 숏일 때 "세팅 (숏)" + 부호 반전 % 표시 |
| `handlers.py::_GUIDE_TEXT` | 5등급 + 방향 설명, 숏 세팅 예시 |
| `handlers.py::_format_stats_card` | by_grade 5종 루프, by_direction 요약 한 줄 |
| `format.py` | 변경 없음 (명식 카드는 무관) |
| `broadcast.py` | `_format_signal_card` 재사용 → 추가 작업 없음 (확인 필요) |

### 8.2 등급 이모지 / 라벨 테이블

```python
_GRADE_LABEL = {
    "강진입_L": "🔥 강진입 (롱)",
    "진입_L":   "🟢 진입 (롱)",
    "관망":     "🟡 관망",
    "진입_S":   "🔴 진입 (숏)",
    "강진입_S": "🧊 강진입 (숏)",
}
```

---

## 9. 테스트 전략

### 9.1 단위 테스트

- `test_grade_signal.py` (신규): 각 등급 5종의 경계값 테스트 (score=74/75, direction 조합).
- `test_structure_symmetric.py`: DOWNTREND → short_score=80, long_score=20. RANGE → 50/50.
- `test_multi_timeframe_symmetric.py`: BEARISH aligned → short_score=max(score,90).
- `test_rsi_score_short.py`: RSI 80 → short_score=70, long_score=20.
- `test_trade_setup_short.py`: 숏 SL>entry>TP1>TP2, rr 양수, SR snap 역방향.

### 9.2 통합 테스트

- `test_signal_service_short.py`: 합성 DOWNTREND klines → 진입_S 또는 강진입_S, TradeSetup.direction=SHORT.
- `test_signal_service_neutral.py`: RANGE + 혼조 → 관망 + TradeSetup=None.
- `test_api_signal_direction.py`: `/v1/signal` 응답에 `analysis.direction`, `trade_setup.direction` 포함.
- `test_repositories_direction.py`: insert_signal_log(signal_direction=...) round-trip.

### 9.3 백테스트 A/B (Phase 1 하네스)

- `backtest/tests/test_symmetry_mode.py`:
  - 합성 히스토리 (longonly 기간 + 하락장 기간 혼합)
  - longonly 모드 → 하락장에서 "관망"만 발생
  - symmetric 모드 → 하락장에서 "진입_S"/"강진입_S" ≥1건 발생
- `backtest/tests/test_regression_longside.py`:
  - Phase 1 smoke 데이터 입력
  - symmetric 모드 결과의 롱 신호(LONG direction) = Phase 1 longonly 결과와 **등급 완전 일치**

### 9.4 회귀 스냅샷

- `tests/snapshots/phase1_baseline.json`: Phase 1 smoke 히스토리의 기대 출력 (grade, composite_score, TradeSetup).
- Phase 2 구현 후 `pytest -k snapshot` 으로 차이 0 확인 (LONG 사이드에서).

---

## 10. 관측성

### 10.1 로그

`signal_service.compute()`에서 INFO 로그 한 줄 (기존 포맷 확장):
```
signal ok chat_id=X ticker=Y composite=N grade=강진입_L direction=LONG long=85 short=15
```

### 10.2 신호 분포 모니터링

관리자 `/stats` 카드에 다음 섹션 추가:

```
방향별 (30일):
  LONG    45건  (평균 MFE +2.1%, MAE -1.4%)
  SHORT   12건  (평균 MFE +1.8%, MAE -1.6%)
  NEUTRAL 103건 (추적 제외)
```

경보 기준 (수작업 확인):
- SHORT 비율이 > 40% 이상 지속 → 시장 체제 변화 or false positive 의심
- SHORT의 MAE 절대값이 LONG 대비 1.5배 초과 → 비대칭 튜닝 필요 (Phase 4 플래그)

---

## 11. 위험과 대응

| # | 위험 | 영향 | 대응 |
|---|------|------|------|
| 1 | 숏 신호 false positive로 하락장 단기 반등에 손절 | 실계좌 손실 | (a) δ=10 마진 (b) Phase 3 divergence 필터 전까진 관리자 발송만, 일반 사용자 공개 지연 옵션 |
| 2 | RANGE에서 직전 스윙 부족으로 false SHORT (composite.py 폴백 로직) | 관망이어야 할 때 진입_S | RANGE 강제 관망 규칙(6.3)으로 방어 |
| 3 | 기존 운영 signal_log가 `signal_grade='진입'` 으로 남아 있어 집계 쿼리 쪼개짐 | /stats 숫자 왜곡 | COALESCE 매핑 CTE (section 5.2) + 집계 함수 단위 테스트 |
| 4 | TradeSetup 숏 SL snap에서 resistance가 entry 위에 없으면 ATR 폴백 | SL이 지나치게 타이트하거나 루즈 | section 3.5 공식 고정 + 단위 테스트로 경계값 커버 |
| 5 | `signal_direction` 컬럼 NULL 남발 (레거시 row) | 필터링 실수 | 인덱스에 `WHERE NOT NULL` 부분 인덱스, 쿼리 관행 `WHERE signal_direction = 'SHORT'` 사용 |
| 6 | API 스키마 확장 (AnalysisSummary.direction)으로 기존 클라이언트 파서 에러 | telegram bot 구버전 배포 동안 장애 | Pydantic Optional 필드 + 필드 추가만 (제거 X) |
| 7 | Phase 1 하네스의 `--mode longonly` 추가가 run_id 규칙과 충돌 | 백테스트 재현성 손상 | run_id suffix 표준 문서화 (section 3.8) + CLI help 텍스트 명시 |
| 8 | `SymmetryMode.LONGONLY` 모드가 미래에 dead code 될 수 있음 | 코드 부채 | Phase 4 종료 시점에 legacy 모드 제거 가부 검토 항목 추가 |
| 9 | 숏 신호 시점의 공매도 가능성(차입/규제) 무관하게 발신 | 실현 불가 조언 | DISCLAIMER 유지 + /guide에 "숏 = 현물 매도 or 선물/옵션" 한 줄 추가 |

---

## 12. 완료 기준

- [ ] migration 006 작성 + TEST_DATABASE_URL 적용 + 운영 DB 적용
- [ ] `AnalysisResult.direction` + `long_score`/`short_score` 신규 필드 통과 테스트
- [ ] `_grade_signal` 5등급 반환 + 단위 테스트 모든 경계값 green
- [ ] TradeSetup 숏 버전 + 단위 테스트 green
- [ ] Telegram 카드 5등급 렌더 + 수동 스크린샷 비교
- [ ] `/stats` 카드 5등급 + direction 섹션
- [ ] Phase 1 하네스 `--mode {longonly,symmetric}` CLI
- [ ] 회귀 스냅샷 테스트 0 diff (LONG 사이드)
- [ ] 합성 하락장 샘플에서 symmetric 모드 숏 신호 ≥1건
- [ ] `ruff check src/ tests/` 통과
- [ ] `pytest` full 통과 (기존 307 + 신규)

---

## 13. Phase 3 예고

- **RSI divergence**: bullish/bearish divergence를 `long_score/short_score`에 **배수 가점** 또는 **필수 조건**으로 결합
- **Volatility regime**: ATR-percentile 기반 저변동/고변동 체제 감지 → TradeSetup 상수 동적 조정
- **BREAKOUT/BREAKDOWN 재검증**: 현재 3% 고정 임계를 ATR 상대 임계로 전환
- **Phase 4**: `_SL_ATR_MULT` 등 튜닝 상수 L/S 분리 여부 백테스트로 결정, 수수료/슬리피지 반영

---

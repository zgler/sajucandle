# Phase 2 구현 플랜 — 숏 대칭 + 5등급

- 날짜: 2026-04-22
- 기반 스펙: `docs/superpowers/specs/2026-04-22-phase2-short-symmetric-design.md`
- 기반 커밋: `b0df064` (main)
- 설계 결정: 8가지 추천안 모두 승인 완료 (2026-04-22)
- 원칙: 1 Task = 1 commit (Phase 1 패턴 계승), TDD 우선, 하위호환 유지

---

## 0. 실행 지침

- 각 Task 시작 전 **실패하는 테스트부터** 작성 → 실패 확인 → 구현 → 통과 → `ruff check` → commit.
- 하위호환 필드는 Optional + default로 추가. 기존 시그니처 제거 금지.
- Task 간 의존성 주의: **T1 → T2,T3,T4 → T5 → T6 → T7 → T8,T9 → T10,T11 → T12,T13 → T14** (토폴로지).
- 각 commit 메시지: `feat(scope): ...` / `test(scope): ...` / `refactor(scope): ...` 컨벤션.
- 매 Task 종료 시 `pytest -q` 전체 green, `ruff check src/ tests/` 0 error.

---

## Task 배치도

```
T1  migration 006
        │
        ├────────────────────┐
        ▼                    ▼
T2 structure.py     T3 multi_timeframe.py   T4 tech_analysis.py
        │                    │                   │
        └────────────────────┴───────────────────┘
                            │
                            ▼
                  T5 composite.py (direction)
                            │
                            ▼
                  T6 trade_setup.py (direction)
                            │
                            ▼
                  T7 models.py (SignalDirection)
                            │
              ┌─────────────┼─────────────┐
              ▼             ▼             ▼
       T8 signal_service  T9 repos    T10 api.py
              │
              ▼
       T11 format/handlers + /guide
              │
              ▼
       T12 backtest CLI --mode
              │
              ▼
       T13 회귀 스냅샷 테스트
              │
              ▼
       T14 A/B 합성 하락장 테스트 (완료 기준)
```

---

## Task 상세

### T1 — migration 006: `signal_direction` 컬럼

**목적**: 향후 모든 insert/집계에 방향 관찰 컬럼 확보. 기존 row는 NULL (레거시 보존).

**변경 파일**:
- `migrations/006_signal_log_direction.sql` (신규)
- `tests/test_migrations.py` (기존 테스트 있으면 확장, 없으면 생성)

**SQL**:
```sql
-- 006_signal_log_direction.sql
ALTER TABLE signal_log
    ADD COLUMN IF NOT EXISTS signal_direction TEXT
        CHECK (signal_direction IN ('LONG', 'SHORT', 'NEUTRAL'));

CREATE INDEX IF NOT EXISTS idx_signal_log_direction
    ON signal_log(signal_direction, sent_at DESC)
    WHERE signal_direction IS NOT NULL;
```

**검증**:
- `TEST_DATABASE_URL` 있는 환경에서 migration 실행 → `\d signal_log` 에 컬럼 존재 확인.
- CHECK 제약: `INSERT ... signal_direction='INVALID'` → 거부 테스트.
- 기존 row 대응: `INSERT ... signal_direction=NULL` → 허용 테스트.

**완료 기준**:
- [ ] SQL 파일 작성
- [ ] CHECK/인덱스 테스트 추가 (skip-safe with TEST_DATABASE_URL)
- [ ] `pytest tests/test_migrations.py -q` green (or skip)

**Commit**: `feat(db): migration 006 — signal_direction 컬럼 + 부분 인덱스`

---

### T2 — `structure.py`: `long_score` / `short_score` 필드 추가

**목적**: 구조 상태별 롱/숏 점수를 **명시적으로** 분리.

**변경 파일**:
- `src/sajucandle/analysis/structure.py`
- `tests/test_structure.py`

**구현**:

```python
@dataclass
class StructureAnalysis:
    state: MarketStructure
    last_high: Optional[SwingPoint]
    last_low: Optional[SwingPoint]
    score: int            # legacy, == long_score (하위호환)
    long_score: int = 0   # 신규
    short_score: int = 0  # 신규

_LONG_SCORE_MAP = {
    MarketStructure.UPTREND: 70,
    MarketStructure.BREAKOUT: 80,
    MarketStructure.RANGE: 50,
    MarketStructure.BREAKDOWN: 30,
    MarketStructure.DOWNTREND: 20,
}
_SHORT_SCORE_MAP = {
    MarketStructure.UPTREND: 20,
    MarketStructure.BREAKOUT: 15,
    MarketStructure.RANGE: 50,
    MarketStructure.BREAKDOWN: 70,
    MarketStructure.DOWNTREND: 80,
}
```

- 기존 `_SCORE_MAP` → `_LONG_SCORE_MAP` 리네이밍.
- `classify_structure`의 반환에 `long_score`, `short_score` 채움.
- 하위호환: `score = long_score`.

**테스트 추가**:
- `test_structure_symmetric_scores`: 각 5개 state에 대해 `long_score`, `short_score` 기대값 매칭.
- `test_structure_legacy_score_equals_long`: `sa.score == sa.long_score` invariant.

**완료 기준**: 기존 test_structure.py 테스트 0 회귀 + 신규 테스트 통과.

**Commit**: `refactor(structure): long_score/short_score 분리 (하위호환 score 유지)`

---

### T3 — `multi_timeframe.py`: `long_score` / `short_score` 필드 추가

**목적**: alignment의 롱/숏 유리도 분리.

**변경 파일**:
- `src/sajucandle/analysis/multi_timeframe.py`
- `tests/test_multi_timeframe.py`

**구현**:

```python
@dataclass
class Alignment:
    tf_1h: TrendDirection
    tf_4h: TrendDirection
    tf_1d: TrendDirection
    aligned: bool
    bias: Literal["bullish","mixed","bearish"]
    score: int            # legacy == long_score
    long_score: int = 0
    short_score: int = 0
```

**공식** (기존 `score` 로직을 long_score로 유지, short_score는 100에서 대칭):

```python
diff = ups - downs            # -3..3
long_score = round((diff + 3) / 6 * 100)
short_score = round((-diff + 3) / 6 * 100)    # = 100 - long_score (대칭)

if aligned and bias == "bullish":
    long_score = max(long_score, 90)
    short_score = min(short_score, 10)
if aligned and bias == "bearish":
    long_score = min(long_score, 10)
    short_score = max(short_score, 90)

score = long_score  # 하위호환
```

**테스트 추가**:
- `test_alignment_symmetric`: 3 UP → long=100, short=0. 3 DOWN → long=0, short=100.
- `test_alignment_mixed`: 2 UP + 1 DOWN → long=67, short=33 (반올림).
- 기존 `test_multi_timeframe` 기대값 유지 (회귀 0).

**Commit**: `refactor(multi_timeframe): long_score/short_score 분리 (하위호환)`

---

### T4 — `tech_analysis.py`: `_rsi_score_short` 신규

**목적**: RSI 대칭. overbought → short 가점.

**변경 파일**:
- `src/sajucandle/tech_analysis.py`
- `tests/test_tech_analysis.py`

**구현**:

```python
def _rsi_score_short(rsi_value: float) -> int:
    """RSI → 0~100 (숏 관점). 과매수(높은 RSI)가 매도 기회."""
    if rsi_value >= 70:
        return 70
    if rsi_value >= 55:
        return 55
    if rsi_value >= 45:
        return 50
    if rsi_value >= 30:
        return 40
    return 20
```

- `_rsi_score` 유지 (하위호환). `_volume_score` 유지 (방향 중립).
- 공개 API 아님 (`_` prefix) → 새로운 export 없음.

**테스트 추가**:
- `test_rsi_score_short_boundaries`: 29/30/31, 44/45/46, 54/55/56, 69/70/71, 80 케이스.
- **대칭성 불변식**: `_rsi_score(r) + _rsi_score_short(r)` 은 5개 구간에서 일정 범위 (예: 90점 내외) — 느슨한 sanity check만.

**Commit**: `feat(tech_analysis): _rsi_score_short 대칭 신규 추가`

---

### T5 — `composite.py`: `direction` + `long_score/short_score` 산출

**목적**: AnalysisResult에 방향 결정 로직 통합.

**변경 파일**:
- `src/sajucandle/analysis/composite.py`
- `tests/test_composite.py` (or `test_composite_analyze.py`)

**구현**:

```python
SignalDirection = Literal["LONG", "SHORT", "NEUTRAL"]
_DIRECTION_MARGIN = 10  # δ (tie-break)

@dataclass
class AnalysisResult:
    structure: StructureAnalysis
    alignment: Alignment
    rsi_1h: float
    volume_ratio_1d: float
    composite_score: int              # = max(long_score, short_score)
    reason: str
    sr_levels: list[SRLevel] = field(default_factory=list)
    atr_1d: float = 0.0
    # 신규
    long_score: int = 0
    short_score: int = 0
    direction: SignalDirection = "NEUTRAL"

def analyze(...) -> AnalysisResult:
    ...  # structure, alignment, rsi_1h, vr_1d 기존대로

    rsi_long  = _rsi_score(rsi_1h)
    rsi_short = _rsi_score_short(rsi_1h)
    vol_score_ = _volume_score(vr_1d)

    # 스윙 부족 폴백: long_score/short_score 각각 alignment로 보정
    struct_long  = structure.long_score
    struct_short = structure.short_score
    if not swings:
        struct_long  = round(0.5 * struct_long  + 0.5 * alignment.long_score)
        struct_short = round(0.5 * struct_short + 0.5 * alignment.short_score)

    long_score = round(
        0.45 * struct_long
        + 0.35 * alignment.long_score
        + 0.10 * rsi_long
        + 0.10 * vol_score_
    )
    short_score = round(
        0.45 * struct_short
        + 0.35 * alignment.short_score
        + 0.10 * rsi_short
        + 0.10 * vol_score_
    )
    long_score  = max(0, min(100, long_score))
    short_score = max(0, min(100, short_score))

    # 방향 결정
    if structure.state == MarketStructure.RANGE:
        direction: SignalDirection = "NEUTRAL"
    elif long_score - short_score >= _DIRECTION_MARGIN:
        direction = "LONG"
    elif short_score - long_score >= _DIRECTION_MARGIN:
        direction = "SHORT"
    else:
        direction = "NEUTRAL"

    composite = max(long_score, short_score)

    return AnalysisResult(
        ...,
        composite_score=composite,
        long_score=long_score,
        short_score=short_score,
        direction=direction,
    )
```

**핵심 규칙**:
- RANGE 강제 NEUTRAL (스펙 §6.3).
- margin δ=10 (스펙 §6.4).
- `composite_score = max(long, short)` → 기존 하위호환.

**테스트 추가**:
- `test_analyze_uptrend_direction_long`: 명확한 상승 합성 klines → direction=LONG, long_score > short_score.
- `test_analyze_downtrend_direction_short`: 명확한 하락 합성 klines → direction=SHORT.
- `test_analyze_range_always_neutral`: RANGE 상태 → direction=NEUTRAL (long/short 점수 상관없이).
- `test_analyze_tie_break_margin`: |long - short| < 10 → NEUTRAL.
- `test_analyze_legacy_composite_score`: composite_score == max(long, short) invariant.
- **회귀**: 기존 composite 테스트 (`test_composite.py`)의 기대 composite_score 값 확인. 대부분 UPTREND 시나리오라 값이 유지돼야 함. 달라지면 스펙 검토 필요.

**Commit**: `feat(composite): direction + long_score/short_score 산출 (δ=10, RANGE=NEUTRAL)`

---

### T6 — `trade_setup.py`: `direction` 매개변수 + 숏 공식

**목적**: 방향별 SL/TP 대칭 계산.

**변경 파일**:
- `src/sajucandle/analysis/trade_setup.py`
- `tests/test_trade_setup.py`

**구현**:

```python
from typing import Literal

SignalDirection = Literal["LONG", "SHORT", "NEUTRAL"]

@dataclass
class TradeSetup:
    entry: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: float
    risk_pct: float
    rr_tp1: float
    rr_tp2: float
    sl_basis: Literal["atr", "sr_snap"]
    tp1_basis: Literal["atr", "sr_snap"]
    tp2_basis: Literal["atr", "sr_snap"]
    direction: SignalDirection = "LONG"   # 신규 (default=LONG 하위호환)

def compute_trade_setup(
    entry: float,
    atr_1d: float,
    sr_levels: list[SRLevel],
    direction: SignalDirection = "LONG",
) -> TradeSetup:
    if atr_1d <= 0:
        atr_1d = entry * 0.01

    supports = [x for x in sr_levels if x.kind == LevelKind.SUPPORT]
    resists  = [x for x in sr_levels if x.kind == LevelKind.RESISTANCE]

    if direction == "LONG":
        # 기존 공식 그대로
        ...
    else:  # SHORT
        # SL = entry + mult * atr, resistance snap, lvl + buffer
        sl_base = entry + _SL_ATR_MULT * atr_1d
        sl_min = entry + (_SL_ATR_MULT - _SNAP_TOLERANCE) * atr_1d
        sl_max = entry + (_SL_ATR_MULT + _SNAP_TOLERANCE) * atr_1d
        sl_best = _best_level_in_range(resists, sl_min, sl_max)
        if sl_best is not None:
            stop_loss = sl_best.price + _SR_BUFFER_ATR * atr_1d
            sl_basis = "sr_snap"
        else:
            stop_loss = sl_base
            sl_basis = "atr"

        # TP1, TP2: entry 아래, support snap, lvl + buffer
        tp1_base = entry - _TP1_ATR_MULT * atr_1d
        tp1_min  = entry - (_TP1_ATR_MULT + _SNAP_TOLERANCE) * atr_1d
        tp1_max  = entry - (_TP1_ATR_MULT - _SNAP_TOLERANCE) * atr_1d
        tp1_best = _best_level_in_range(supports, tp1_min, tp1_max)
        if tp1_best is not None:
            take_profit_1 = tp1_best.price + _SR_BUFFER_ATR * atr_1d
            tp1_basis = "sr_snap"
        else:
            take_profit_1 = tp1_base
            tp1_basis = "atr"

        # TP2 동일 패턴 (tolerance=_SNAP_TOLERANCE_TP2)
        ...

        risk = stop_loss - entry           # > 0
        risk_pct = (risk / entry * 100) if entry > 0 else 0.0
        rr_tp1 = ((entry - take_profit_1) / risk) if risk > 0 else 0.0
        rr_tp2 = ((entry - take_profit_2) / risk) if risk > 0 else 0.0

    return TradeSetup(..., direction=direction)
```

- 상수 공유 (L/S 동일) — 스펙 §7.2 결정.
- `direction="NEUTRAL"`은 이 함수 호출 안 됨 (signal_service에서 guard).

**테스트 추가**:
- `test_trade_setup_long_unchanged`: 기존 케이스 그대로 통과 (회귀 0).
- `test_trade_setup_short_basic`: SL > entry > TP1 > TP2 관계 확인, risk > 0, rr > 0.
- `test_trade_setup_short_sr_snap`: resistance가 SL 근처에 있으면 `sl_basis="sr_snap"`, `stop_loss = lvl + buffer*atr`.
- `test_trade_setup_short_tp_support_snap`: support가 TP1 근처 → `tp1_basis="sr_snap"`.
- **대칭 불변식**: 동일 ATR/entry에서 LONG rr_tp1 ≈ SHORT rr_tp1 (부호 부재의 sanity).

**Commit**: `feat(trade_setup): direction 매개변수 + 숏 대칭 공식`

---

### T7 — `models.py`: `SignalDirection` + direction 필드

**목적**: Pydantic API 계약에 방향 표기.

**변경 파일**:
- `src/sajucandle/models.py`
- `tests/test_models.py` (없으면 간단 round-trip 테스트 추가)

**변경**:

```python
from typing import Literal

SignalDirection = Literal["LONG", "SHORT", "NEUTRAL"]

class AnalysisSummary(BaseModel):
    ...
    direction: Optional[SignalDirection] = None   # 신규
    long_score: Optional[int] = None              # 신규 (관찰용)
    short_score: Optional[int] = None             # 신규 (관찰용)

class TradeSetupSummary(BaseModel):
    ...
    direction: Optional[SignalDirection] = None   # 신규 (default=LONG 의미)
```

- **Optional + default=None**: 기존 클라이언트(봇 구버전) JSON 파싱 호환.
- 신규 세트: direction, long_score, short_score, TradeSetupSummary.direction.

**테스트**: JSON 직렬화/역직렬화 round-trip, 신규 필드 누락 입력도 수용.

**Commit**: `feat(models): SignalDirection + AnalysisSummary/TradeSetupSummary direction 필드`

---

### T8 — `signal_service.py`: 5등급 `_grade_signal` + TradeSetup direction 주입

**목적**: 코어 등급 판정 로직을 5등급으로 전환. 분석 결과의 direction을 TradeSetup에 전달.

**변경 파일**:
- `src/sajucandle/signal_service.py`
- `tests/test_signal_service.py`

**핵심 변경**:

```python
_SCORE_THRESHOLD_STRONG = 75
_SCORE_THRESHOLD_ENTRY = 60

def _grade_signal(score: int, analysis: AnalysisResult) -> str:
    """5등급 반환: 강진입_L | 진입_L | 관망 | 진입_S | 강진입_S"""
    state = analysis.structure.state
    direction = analysis.direction

    # RANGE 강제 관망
    if state == MarketStructure.RANGE:
        return "관망"

    if direction == "NEUTRAL" or score < _SCORE_THRESHOLD_ENTRY:
        return "관망"

    if direction == "LONG":
        if (score >= _SCORE_THRESHOLD_STRONG
                and analysis.alignment.aligned
                and analysis.alignment.bias == "bullish"
                and state in (MarketStructure.UPTREND, MarketStructure.BREAKOUT)):
            return "강진입_L"
        return "진입_L"

    # SHORT
    if (score >= _SCORE_THRESHOLD_STRONG
            and analysis.alignment.aligned
            and analysis.alignment.bias == "bearish"
            and state in (MarketStructure.DOWNTREND, MarketStructure.BREAKDOWN)):
        return "강진입_S"
    return "진입_S"
```

**compute() 내 TradeSetup 생성 분기**:

```python
trade_setup: Optional[TradeSetup] = None
if grade in ("강진입_L", "진입_L", "강진입_S", "진입_S") and analysis.atr_1d > 0:
    trade_setup = compute_trade_setup(
        entry=current,
        atr_1d=analysis.atr_1d,
        sr_levels=analysis.sr_levels,
        direction=analysis.direction,   # 신규
    )
```

**AnalysisSummary 변환 함수**에 direction/long_score/short_score 전달.

**로그**:
```python
logger.info(
    "signal ok chat_id=%s ticker=%s composite=%d grade=%s direction=%s long=%d short=%d",
    profile.telegram_chat_id, ticker, final, grade,
    analysis.direction, analysis.long_score, analysis.short_score,
)
```

**테스트 추가**:
- `test_grade_long_entry_boundary`: score=60, 74, 75, 76 × direction=LONG + UPTREND/BREAKOUT + aligned/not → 등급 매핑.
- `test_grade_short_entry_boundary`: 대칭 케이스.
- `test_grade_range_always_neutral`: RANGE → 관망.
- `test_grade_direction_neutral_below_60`: NEUTRAL + score 40 → 관망.
- `test_grade_removed_avoid_level`: "회피" 반환되지 않음 (invariant).
- **회귀**: 기존 test_signal_service.py 통과 (단, 일부 기대값이 "강진입" → "강진입_L" 로 변경되어야 함. 테스트 코드 업데이트).

**Commit**: `feat(signal_service): 5등급 _grade_signal + TradeSetup direction 주입`

---

### T9 — `repositories.py`: `insert_signal_log(signal_direction=...)`

**목적**: DB 기록 경로에 direction 전달.

**변경 파일**:
- `src/sajucandle/repositories.py`
- `tests/test_repositories.py`
- **모든 호출부**: `broadcast.py`, 기타 `insert_signal_log` 호출 지점

**변경**:

```python
async def insert_signal_log(
    conn,
    ...,
    signal_direction: Optional[str] = None,   # 신규
    ...,
) -> int:
    await conn.execute(
        """
        INSERT INTO signal_log
            (..., signal_direction)
        VALUES (..., $N)
        """,
        ..., signal_direction,
    )
```

**호출부 업데이트**:
- `broadcast.py::send_daily_broadcast` (or 유사 루틴) — 기존 `insert_signal_log(signal_grade=grade, ...)` 호출에 `signal_direction=resp.analysis.direction` 추가.
- 백테스트 `engine.py`의 insert 경로 — 마찬가지로 direction 전달.

**테스트**:
- `test_insert_signal_log_direction_roundtrip`: insert 후 SELECT → direction 일치.
- `test_insert_signal_log_null_direction`: 미전달 시 NULL 저장.

**Commit**: `feat(repositories): insert_signal_log signal_direction 매개변수`

---

### T10 — `api.py`: `/v1/signal` 응답 + `/v1/signal/stats` by_direction

**목적**: API 응답에 direction/long_score/short_score 포함, stats 엔드포인트에 방향별 집계 추가.

**변경 파일**:
- `src/sajucandle/api.py`
- `src/sajucandle/api_client.py` (타입 맞추기)
- `tests/test_api.py`

**핵심**:
- `/v1/signal` 응답 SignalResponse에 이미 AnalysisSummary.direction 포함 → 자동 전달 (T7 완료 이후 자동).
- `/v1/signal/stats` 응답에 `by_direction: dict[str, DirectionStats]` 필드 추가 (LONG/SHORT/NEUTRAL 카운트 + 평균 MFE/MAE).
- 집계 SQL에 COALESCE 매핑 CTE 사용 (스펙 §5.2).

**SQL 예시** (aggregate 계산 내부):

```sql
WITH mapped AS (
    SELECT
        signal_grade,
        COALESCE(
            signal_direction,
            CASE signal_grade
                WHEN '강진입' THEN 'LONG'
                WHEN '진입' THEN 'LONG'
                WHEN '강진입_L' THEN 'LONG'
                WHEN '진입_L' THEN 'LONG'
                WHEN '강진입_S' THEN 'SHORT'
                WHEN '진입_S' THEN 'SHORT'
                ELSE 'NEUTRAL'
            END
        ) AS direction,
        mfe_pct, mae_pct
    FROM signal_log
    WHERE ...
)
SELECT direction, COUNT(*) AS n,
       AVG(mfe_pct) AS avg_mfe, AVG(mae_pct) AS avg_mae
FROM mapped
GROUP BY direction;
```

**테스트**:
- `test_api_signal_direction_field`: mock → SignalResponse.analysis.direction 문자열.
- `test_api_stats_by_direction`: 레거시 row + 신규 row 혼합 샘플 → LONG 집계 합산 정상.

**Commit**: `feat(api): /v1/signal direction 노출 + /v1/signal/stats by_direction`

---

### T11 — `format.py` / `handlers.py`: 5등급 라벨 + 숏 세팅 블록 + `/guide`

**목적**: 사용자 가시화 UI 대칭. 봇 카드 5등급 + 숏 진입 세팅 블록 렌더.

**변경 파일**:
- `src/sajucandle/handlers.py` (`_format_signal_card`, `_append_trade_setup_block`, `_GUIDE_TEXT`, `_format_stats_card`)
- `src/sajucandle/format.py` (필요시 DISCLAIMER 유지)
- `tests/test_handlers.py`

**핵심 변경**:

```python
_GRADE_LABEL = {
    "강진입_L": "🔥 강진입 (롱)",
    "진입_L":   "🟢 진입 (롱)",
    "관망":     "🟡 관망",
    "진입_S":   "🔴 진입 (숏)",
    "강진입_S": "🧊 강진입 (숏)",
    # 레거시 호환 (운영 transition 기간)
    "강진입":   "🔥 강진입 (롱)",
    "진입":     "🟢 진입 (롱)",
    "회피":     "🟡 관망",
}

def _append_trade_setup_block(lines, ts: TradeSetupSummary, entry_price: float):
    direction = ts.direction or "LONG"
    if direction == "LONG":
        # 기존 포맷 유지
        lines.append("세팅 (롱):")
        lines.append(f" 진입 ${ts.entry:,.2f}")
        sl_pct = (ts.stop_loss / ts.entry - 1.0) * 100   # 음수
        tp1_pct = (ts.take_profit_1 / ts.entry - 1.0) * 100  # 양수
        ...
    else:  # SHORT
        lines.append("세팅 (숏):")
        lines.append(f" 진입 ${ts.entry:,.2f}")
        sl_pct = (ts.stop_loss / ts.entry - 1.0) * 100   # 양수 (위)
        tp1_pct = (ts.take_profit_1 / ts.entry - 1.0) * 100  # 음수
        ...
```

**`_GUIDE_TEXT` 업데이트**:
- 5등급 각각 설명 추가.
- "숏 = 현물 매도 or 선물/옵션" 한 줄 (스펙 §11 위험 #9 대응).
- 기존 DISCLAIMER 링크 유지.

**`_format_stats_card`**:
- `by_grade`: 5등급 루프 (레거시 4등급도 레거시 라벨로 표시 or 무시).
- `by_direction`: 한 줄 요약 (LONG/SHORT/NEUTRAL 카운트 + 평균 MFE).

**테스트**:
- `test_format_card_short_setting_block`: 숏 SignalResponse → 카드에 "세팅 (숏)" 포함 + SL/TP 부호 확인.
- `test_format_card_grade_labels`: 5등급 각각 라벨 매칭.
- `test_guide_text_mentions_short`: `/guide` 출력에 "숏" 키워드 포함.

**broadcast.py 확인**:
- `_format_signal_card` 재사용 확인 (Grep). 별도 포맷터 있으면 동일 변경 적용.

**Commit**: `feat(handlers): 5등급 라벨 + 숏 세팅 블록 + /guide 업데이트`

---

### T12 — 백테스트 CLI: `--mode {longonly,symmetric}` + run_id suffix

**목적**: Phase 1 하네스에 모드 플래그 도입. run_id 네이밍 규칙 표준화.

**변경 파일**:
- `src/sajucandle/backtest/cli.py`
- `src/sajucandle/backtest/engine.py`
- `tests/backtest/test_symmetry_mode.py` (신규)

**CLI 변경**:

```python
run_p.add_argument(
    "--mode",
    choices=["longonly", "symmetric"],
    default="symmetric",
    help="신호 모드. longonly=Phase 1 호환, symmetric=Phase 2 대칭(default)",
)

def _default_run_id(label: str = "auto", mode: str = "symmetric") -> str:
    sha = _short_sha()
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"phase2-{sha}-{mode}-{today}"
```

- 하위호환: `--run-id`를 명시 제공하면 그 값 그대로 사용.
- 자동 생성 시 `phase2-<sha7>-longonly-<date>` / `phase2-<sha7>-symmetric-<date>`.

**engine.py 변경**:

```python
async def run_backtest(
    ...,
    mode: Literal["longonly", "symmetric"] = "symmetric",
) -> BacktestSummary:
    ...
```

- `mode == "longonly"`일 때 → `_grade_signal` 결과를 후처리로 **강제 매핑**:
  - `진입_S`, `강진입_S` → `관망`
  - 나머지는 그대로.
- 즉 signal_service 자체는 손대지 않고, **engine 레벨에서 방향 스트립**만 수행.
- 이유: 간단 + longonly는 phase1 재현 목적이라 기존 분기 로직 완전 복제보다 **출력 필터**가 안전.

**테스트** (`test_symmetry_mode.py`):
- 합성 klines (UPTREND 구간 10일 + DOWNTREND 구간 10일) 제공.
- longonly 모드: 하락장 구간 grade ∈ {관망} only.
- symmetric 모드: 하락장 구간 grade ∈ {진입_S, 강진입_S} ≥ 1건.
- 두 모드의 상승장 구간 grade 결과 **완전 일치** (회귀).

**Commit**: `feat(backtest): --mode longonly|symmetric + run_id suffix 규칙`

---

### T13 — 회귀 스냅샷 테스트 (롱 사이드 0 diff)

**목적**: Phase 1 smoke 히스토리에서 LONG 사이드 출력이 Phase 2 이후도 완전 동일.

**변경 파일**:
- `tests/snapshots/phase1_baseline.json` (신규 or 기존 smoke 결과 고정)
- `tests/test_regression_longside.py` (신규)

**구현**:
1. Phase 1 smoke 테스트 재실행 → 기대 출력 (grade, composite_score, TradeSetup 주요 필드) JSON 고정.
2. Phase 2 symmetric 모드로 동일 입력 → LONG 사이드 (direction=LONG인 row) 결과와 Phase 1 snapshot의 strongentry/entry row가 **정확히 일치** 비교.
3. 의도된 차이 허용 범위:
   - `signal_grade`: `강진입` ↔ `강진입_L`, `진입` ↔ `진입_L` 매핑만 diff 허용.
   - `composite_score`: ±0 (동일해야 함). 다르면 T5의 공식이 롱 케이스를 깨뜨린 것.
   - `TradeSetup.entry/SL/TP*`: ±0.

**Skip 조건**: smoke 데이터는 `backtest/tests/data/` 에 고정 (Phase 1에서 이미 존재) → DB 무관.

**Commit**: `test(backtest): 회귀 스냅샷 — LONG 사이드 Phase 2 0 diff`

---

### T14 — A/B 합성 하락장 테스트 (완료 기준)

**목적**: 최종 "Phase 2 작동 증명" 게이트.

**변경 파일**:
- `tests/backtest/test_phase2_acceptance.py` (신규)

**시나리오**:
1. 60일 합성 히스토리:
   - day 0~20: 완만한 UPTREND (HH-HL 3세트)
   - day 20~40: RANGE (박스권)
   - day 40~60: DOWNTREND (LH-LL 3세트)
2. 동일 입력을 두 모드로 실행:
   - longonly: 20~40 RANGE 대부분 관망, 40~60 전부 관망
   - symmetric: 40~60 구간 `진입_S` 또는 `강진입_S` **≥1건 발생**
3. insert 결과 신규 `signal_direction` 컬럼 값도 확인.

**완료 기준 assertions** (스펙 §12와 정확히 일치):
- [ ] symmetric 모드 하락장 구간에 SHORT 신호 ≥ 1건
- [ ] longonly 모드 동일 하락장 구간에 SHORT 신호 = 0건
- [ ] 두 모드의 상승장 구간 LONG 신호 건수/grade 완전 일치
- [ ] 전 테스트 스위트 `pytest -q` green (307 + 신규)
- [ ] `ruff check src/ tests/` 0 error

**Commit**: `test(backtest): Phase 2 acceptance — 대칭 모드 숏 신호 발생 검증`

---

## 완료 후 산출물

### 코드 변경 파일 (예상)
- `migrations/006_signal_log_direction.sql` (신규)
- `src/sajucandle/analysis/structure.py`
- `src/sajucandle/analysis/multi_timeframe.py`
- `src/sajucandle/analysis/composite.py`
- `src/sajucandle/analysis/trade_setup.py`
- `src/sajucandle/tech_analysis.py`
- `src/sajucandle/models.py`
- `src/sajucandle/signal_service.py`
- `src/sajucandle/repositories.py`
- `src/sajucandle/api.py`
- `src/sajucandle/api_client.py`
- `src/sajucandle/handlers.py`
- `src/sajucandle/format.py` (최소)
- `src/sajucandle/broadcast.py` (호출부 update)
- `src/sajucandle/backtest/cli.py`
- `src/sajucandle/backtest/engine.py`

### 테스트 파일 (신규/확장)
- `tests/test_structure.py`, `tests/test_multi_timeframe.py`, `tests/test_tech_analysis.py`
- `tests/test_composite.py`
- `tests/test_trade_setup.py`
- `tests/test_models.py`
- `tests/test_signal_service.py`
- `tests/test_repositories.py`
- `tests/test_api.py`
- `tests/test_handlers.py`
- `tests/test_migrations.py`
- `tests/backtest/test_symmetry_mode.py` (신규)
- `tests/backtest/test_phase2_acceptance.py` (신규)
- `tests/snapshots/phase1_baseline.json` (신규)
- `tests/test_regression_longside.py` (신규)

### Commit 개수 예상
- 14 commits (T1~T14).

### 운영 롤아웃 체크리스트 (Phase 2 완료 후, 별도 Task 아님)
- [ ] 운영 DB에 migration 006 적용 (`DATABASE_URL` 대상)
- [ ] Railway 재배포 후 `/signal` 카드 5등급 스크린샷 확인
- [ ] 첫 주 `/stats` 카드에서 SHORT 비율 / MAE 모니터링
- [ ] 숏 false positive 발생 시 스펙 §11 위험 #1 대응 (관리자 dryrun)

---

## 오픈 이슈 / 설계자 승인 요청

이 플랜에 대해 사용자(설계자)가 확인/답변 필요:

1. **T12 구현 방식**: longonly 모드를 "engine 출력 필터"로 구현 제안. 대안은 `_grade_signal`에 `mode` 파라미터 전달인데 signal_service 오염 우려. 필터 방식 OK?
2. **T13 snapshot 기준**: Phase 1 smoke 테스트가 이미 `backtest/tests/` 아래 존재한다고 가정. 파일 위치·이름 확인 필요.
3. **T11 `/guide` 텍스트**: 최종 문구는 T11 구현 시점에 초안 작성 → 설계자 검토 원하시면 별도 사전 승인 단계 추가 가능.
4. **Phase 0 Open Question 재확인**: `volume_profile.top_n`, OHLCV TTL 일원화, CI 도입, backtest 경로 — Phase 2 **시작 전** 답변 필요했던 사항인데 Phase 1 완료 시 일부 해소됐는지? (Phase 2는 이 중 어느 것도 직접 수정 안 함)

위 4개 확인 후 **T1부터 구현 착수** 가능. 사용자가 `"구현해"` 지시 시 T1 → ... → T14 순차 진행.

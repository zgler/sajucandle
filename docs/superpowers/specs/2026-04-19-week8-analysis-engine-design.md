# Week 8 설계 — 기술 분석 엔진 재설계 Phase 1 (시장 구조 + 멀티 TF + 로깅)

- 날짜: 2026-04-19
- 대상 주차: Week 8 (4주 스프린트 Week 8~11 중 Phase 1)
- 상태: Draft (brainstorming 합의 완료, 사용자 리뷰 대기)

## 1. 목적

현재 `tech_analysis.py`는 RSI/MA20vs50/volume_ratio 3개 지표의 가중합(0.4/0.4/0.2)을 일봉 단일 타임프레임으로 계산한다. 사용자 피드백: **"기술적 분석 부실, 엔터테인먼트 치중으로 투자 상품으로 부적합, 실패 누적 시 신뢰 급하락 위험"**. Week 8은 4주 스프린트의 Phase 1로, 엔진을 **가격 구조 + 멀티 타임프레임 + 수급**의 3축 프레임으로 재구성하고, 모든 시그널 결과를 DB에 추적 저장해 Week 11 백테스트 기반 개선의 원천 데이터를 만든다.

사주는 폐기하지 않되 가중치 0.4 → 0.1로 강등, 카드에서도 "참고 코멘트 한 줄"로 축소. "엔터테인먼트 목적" 문구는 "정보 제공 목적"으로 톤 상향.

## 2. 목표 / 범위

### 포함 (Week 8 Phase 1)

1. `signal_log` 테이블 + MFE/MAE 7일 추적 파이프라인
2. Fractals + ATR 필터 기반 swing high/low 감지 (`analysis/swing.py`)
3. 시장 구조 분류 (UPTREND / DOWNTREND / RANGE / BREAKDOWN / BREAKOUT) (`analysis/structure.py`)
4. 타임프레임별 트렌드 방향 (`analysis/timeframe.py`) + 1h/4h/1d 정렬 판정 (`analysis/multi_timeframe.py`)
5. 분석 조합기 (`analysis/composite.py`) — 기존 RSI/볼륨은 보조(각 10%)로 재사용
6. `SignalService` 가중치 재조정 (사주 0.4→0.1, 차트 0.6→0.9)
7. 강진입 등급에 추가 조건 (정렬 + 추세장)
8. 시그널 카드 포맷 개편 (구조/정렬/진입조건 3줄 + 사주 축소)
9. 모닝 사주 카드 톤 완화 (제목/종합→성향)
10. disclaimer 전역 교체 ("엔터테인먼트 목적" → "정보 제공 목적. 투자 판단과 손실 책임은 본인에게 있습니다.")

### 범위 밖 (Week 9+)

- **Week 9:** 지지/저항 자동 식별 (swing + volume node), SL/TP 자동 제안 (ATR + S/R)
- **Week 10:** 카드에 백테스트 통계 주입, 시그널 발송 거부 규칙 (구조 역행 차단)
- **Week 11:** MFE/MAE 통계 집계 API, 적중률 리포트, 등급 임계값 재조정, 백테스트 엔진 (`source='backtest'`)
- **Week 12+:** 국내주식 (KIS), 장중 실시간 강진입 알림, 가격 breakout alert

## 3. 설계 결정 (brainstorming 요약)

| # | 주제 | 결정 | 근거 |
|---|------|------|------|
| Q1 | 엔진 방향 | **전면 재설계** (C) | 지표 추가는 부실 근본 해결 아님. 판단 프레임(구조+정렬+수급) 재구성 필요 |
| Q2 | Swing 감지 | **Fractals + ATR 필터** (C) | 결정론적(실시간 안전) + 노이즈 제거. lookahead 편향 없음 |
| Q3 | 결과 추적 범위 | **MFE/MAE 포함** (C) | 승률 아닌 R/R 메트릭이 Week 11 가치. Week 9 SL/TP 자동화 근거 |

## 4. 아키텍처

### 4.1 모듈 구성

```
src/sajucandle/
├── tech_analysis.py                # 기존 — RSI/MA/volume 순수함수로 유지 (보조 도구)
├── analysis/                       # [CREATE] 고수준 분석 레이어
│   ├── __init__.py
│   ├── swing.py                    # SwingPoint detection (Fractals + ATR)
│   ├── structure.py                # MarketStructure 분류
│   ├── timeframe.py                # TrendDirection (single TF)
│   ├── multi_timeframe.py          # Alignment (1h/4h/1d 조합)
│   └── composite.py                # AnalysisResult 조립 + composite_score
├── chart_engine.py                 # [DELETE or thin wrapper] — analysis/composite.py로 이전
├── signal_service.py               # [MODIFY] composite.analyze() 호출, 가중치 재조정, signal_log 기록
├── repositories.py                 # [MODIFY] insert_signal_log + list_pending_tracking + update_signal_tracking
├── models.py                       # [MODIFY] SignalResponse에 구조/정렬 필드 추가
├── handlers.py                     # [MODIFY] 카드 포맷 개편, DISCLAIMER 상수 사용
├── broadcast.py                    # [MODIFY] Phase 0 tracking update, 모닝 카드 톤 완화, Phase 3 disclaimer 교체
├── market_data.py + market/yfinance.py   # [MODIFY] 1h/4h/1d interval 지원 (yfinance 4h는 내부 resample)
└── format.py                       # [CREATE or MODIFY] DISCLAIMER 상수 + 포맷 헬퍼

migrations/
└── 003_signal_log.sql              # [CREATE]
```

### 4.2 핵심 데이터 타입

```python
# analysis/swing.py
@dataclass
class SwingPoint:
    index: int
    timestamp: datetime
    price: float
    kind: Literal["high", "low"]

def detect_swings(
    klines: list[Kline],
    fractal_window: int = 5,
    atr_multiplier: float = 1.5,
    atr_period: int = 14,
) -> list[SwingPoint]: ...

# analysis/structure.py
class MarketStructure(str, Enum):
    UPTREND = "uptrend"
    DOWNTREND = "downtrend"
    RANGE = "range"
    BREAKDOWN = "breakdown"
    BREAKOUT = "breakout"

@dataclass
class StructureAnalysis:
    state: MarketStructure
    last_high: Optional[SwingPoint]
    last_low: Optional[SwingPoint]
    score: int        # 0~100

def classify_structure(swings: list[SwingPoint]) -> StructureAnalysis: ...

# analysis/timeframe.py
class TrendDirection(str, Enum):
    UP = "up"
    DOWN = "down"
    FLAT = "flat"

def trend_direction(klines: list[Kline], ema_period: int = 50) -> TrendDirection:
    """close > EMA50 AND EMA50 기울기(최근 5봉 선형회귀 slope) 양 → UP.
    close < EMA50 AND 기울기 음 → DOWN. 그 외 FLAT."""

# analysis/multi_timeframe.py
@dataclass
class Alignment:
    tf_1h: TrendDirection
    tf_4h: TrendDirection
    tf_1d: TrendDirection
    aligned: bool              # 3개 TF 전부 UP 또는 전부 DOWN
    bias: Literal["bullish", "bearish", "mixed"]
    score: int                 # 정렬도 0~100

def compute_alignment(
    klines_1h: list[Kline], klines_4h: list[Kline], klines_1d: list[Kline]
) -> Alignment: ...

# analysis/composite.py
@dataclass
class AnalysisResult:
    structure: StructureAnalysis
    alignment: Alignment
    rsi_1h: float
    volume_ratio_1d: float
    composite_score: int       # 0~100
    reason: str                # "1d↑ 4h↑ 1h↗ · HL 확인 · 거래량 1.5x"

def analyze(
    klines_1h: list[Kline], klines_4h: list[Kline], klines_1d: list[Kline]
) -> AnalysisResult: ...
```

### 4.3 점수 조합 (composite.py)

```
structure.score 계산 (대략):
  UPTREND + BREAKOUT 직후 → 85
  UPTREND → 70
  BREAKOUT (range에서 돌파 직후) → 75
  RANGE → 50
  BREAKDOWN → 30
  DOWNTREND → 20

alignment.score 계산:
  aligned=True AND bias=bullish → 90
  aligned=True AND bias=bearish → 10 (강한 하락 — 롱에 불리)
  mixed (bias=bullish 쪽 우세) → 60
  mixed (bearish 쪽 우세) → 40

rsi_score: 기존 tech_analysis._rsi_score (BUT 1h RSI 사용)
volume_score: 기존 tech_analysis._volume_score (1d volume_ratio)

analysis.composite_score = round(
    0.45 * structure.score +
    0.35 * alignment.score +
    0.10 * rsi_score +
    0.10 * volume_score
)
# 0~100 클램프
```

**signal_service.py 최종 가중치:**
```python
final = round(0.1 * saju.composite + 0.9 * analysis.composite_score)
```

### 4.4 강진입 등급 추가 조건

```python
def grade_signal(score: int, analysis: AnalysisResult) -> str:
    if (score >= 75
        and analysis.alignment.aligned
        and analysis.structure.state in (MarketStructure.UPTREND, MarketStructure.BREAKOUT)):
        return "강진입"
    if score >= 60:
        return "진입"
    if score >= 40:
        return "관망"
    return "회피"
```

점수만으로 "강진입" 나오지 않음 — 멀티 TF 정렬 + 상승 구조 둘 다 필요.

### 4.5 멀티 타임프레임 데이터 조달

- **BTC (Binance):** `interval=1h|4h|1d` 전부 공식 지원. `fetch_klines(symbol, "1h"|"4h"|"1d", limit)` 그대로.
- **미국주식 (yfinance):**
  - `1d`: 정상 — `limit`만큼 일봉.
  - `1h`: 최근 60일 제한. limit=120 정도면 일주일치 충분.
  - `4h`: yfinance 직접 지원 X → **1h봉 fetch 후 내부 resample**. `pandas.DataFrame.resample("4H").agg(...)`.
- `YFinanceClient.fetch_klines`의 interval 처리 확장 필요. 캐시 키에 interval 포함 (이미 그렇게 되어있음: `ohlcv:{symbol}:{interval}:fresh`).

## 5. 데이터 모델

### 5.1 `signal_log` 스키마 (`migrations/003_signal_log.sql`)

```sql
CREATE TABLE IF NOT EXISTS signal_log (
    id              BIGSERIAL PRIMARY KEY,
    sent_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    source          TEXT NOT NULL,          -- 'ondemand' | 'broadcast' | 'backtest'
    telegram_chat_id BIGINT,                -- NULL 허용 (backtest)

    ticker          TEXT NOT NULL,
    target_date     DATE NOT NULL,
    entry_price     NUMERIC(18,8) NOT NULL,

    saju_score      INT NOT NULL,
    analysis_score  INT NOT NULL,
    structure_state TEXT NOT NULL,
    alignment_bias  TEXT NOT NULL,          -- 'bullish'|'mixed'|'bearish'
    rsi_1h          NUMERIC(5,2),
    volume_ratio_1d NUMERIC(6,3),

    composite_score INT NOT NULL,
    signal_grade    TEXT NOT NULL,

    -- 추적 (7일 동안 업데이트)
    mfe_7d_pct      NUMERIC(6,3),
    mae_7d_pct      NUMERIC(6,3),
    close_24h       NUMERIC(18,8),
    close_7d        NUMERIC(18,8),
    last_tracked_at TIMESTAMPTZ,
    tracking_done   BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_signal_log_ticker_sent_at
    ON signal_log(ticker, sent_at DESC);
CREATE INDEX IF NOT EXISTS idx_signal_log_tracking
    ON signal_log(tracking_done, sent_at)
    WHERE tracking_done = FALSE;
```

### 5.2 Repository 함수

```python
# repositories.py
@dataclass
class SignalLogRow:
    id: int
    sent_at: datetime
    ticker: str
    target_date: date
    entry_price: Decimal
    # ... (전 필드)
    tracking_done: bool

async def insert_signal_log(conn, *,
    source: str, telegram_chat_id: Optional[int],
    ticker: str, target_date: date, entry_price: float,
    saju_score: int, analysis_score: int,
    structure_state: str, alignment_bias: str,
    rsi_1h: Optional[float], volume_ratio_1d: Optional[float],
    composite_score: int, signal_grade: str,
) -> int: ...

async def list_pending_tracking(
    conn, now: datetime, max_rows: int = 500
) -> list[SignalLogRow]:
    """tracking_done=FALSE AND sent_at > now-7d AND sent_at < now-1h."""

async def update_signal_tracking(conn, signal_id: int, *,
    mfe_pct: float, mae_pct: float,
    close_24h: Optional[float], close_7d: Optional[float],
    tracking_done: bool,
) -> None: ...
```

### 5.3 기록 시점

`SignalService.compute()`가 성공적으로 `SignalResponse` 반환 **직후** `insert_signal_log()` 호출. 파라미터 추가:

```python
def compute(self, profile, target_date, ticker, *, source: str = "ondemand") -> SignalResponse:
    # ... 기존 로직 + 새 analysis ...
    # 성공 후:
    await self._log_signal(source, profile, ticker, target_date, resp, analysis)
    return resp
```

- `api.py`의 `/signal` 엔드포인트: `source="ondemand"` (기본)
- `broadcast.py`의 watchlist precompute + 요약 루프: `source="broadcast"`
- 실패(예외) 시 기록 안 함.

## 6. MFE/MAE 추적 파이프라인

### 6.1 Phase 0 — broadcast 크론의 맨 앞

기존 `run_broadcast`에 Phase 0 삽입:

```
[Phase 0: 추적 업데이트]
  pending = list_pending_tracking(conn, now=datetime.utcnow())
  for row in pending:
      hours_since = (now - row.sent_at).total_seconds() / 3600
      # 1h봉 최근 7일치 조회 (같은 심볼 precompute 대상과 겹치면 cache hit)
      klines_1h = market_router.get_provider(row.ticker).fetch_klines(
          row.ticker, interval="1h", limit=24*7
      )
      # row.sent_at 이후의 봉들만 필터
      post_bars = [k for k in klines_1h if k.open_time >= row.sent_at]
      if not post_bars:
          continue
      highs = [k.high for k in post_bars]
      lows = [k.low for k in post_bars]
      mfe = max(highs) / row.entry_price - 1.0    # 최고 수익률
      mae = min(lows) / row.entry_price - 1.0     # 최저 (음수)
      # 24h/7d 지점 종가 (가능하면)
      close_24h = first bar at hours_since >= 24 .close, else None
      close_7d  = first bar at hours_since >= 168 .close, else None
      done = hours_since >= 168
      update_signal_tracking(conn, row.id,
          mfe_pct=mfe*100, mae_pct=mae*100,
          close_24h=close_24h, close_7d=close_7d,
          tracking_done=done)
      summary.tracking_updated += 1
      if done: summary.tracking_completed += 1
```

실패 시 warning 로그 + 다음 row 진행. Phase 1/2/3 진행 방해 안 함.

### 6.2 BroadcastSummary 확장

```python
@dataclass
class BroadcastSummary:
    # 기존 Week 5/7 필드 그대로
    sent: int = 0
    # ...
    # Week 8
    tracking_updated: int = 0
    tracking_completed: int = 0
    tracking_failed: int = 0
```

### 6.3 최종 로그 확장

```
broadcast done date=... sent=... watchlist_sent=... precompute_ok=...
  tracking_updated=12 tracking_completed=3 tracking_failed=0
```

## 7. 카드 포맷 개편

### 7.1 `/signal` 카드 (AAPL 장중 예시)

```
── 2026-04-19 AAPL ──
🟢 장 중
현재가: $184.12 (+1.23%)

구조: 상승추세 (HH-HL)
정렬: 1d↑ 4h↑ 1h↗  (강정렬)
진입조건: RSI(1h) 35 · 거래량 1.5x

종합: 72 | 진입
사주: 56 (관망) · 충돌운 높음

※ 정보 제공 목적. 투자 판단과 손실 책임은 본인에게 있습니다.
```

**구조 줄 매핑:**
- `UPTREND` → `"상승추세 (HH-HL)"`
- `DOWNTREND` → `"하락추세 (LH-LL)"`
- `RANGE` → `"횡보 (박스)"`
- `BREAKOUT` → `"상승 돌파"`
- `BREAKDOWN` → `"하락 이탈"`

**정렬 줄:** 각 TF 화살표 `↑/↓/↗/↘/→` 매핑 (UP/DOWN/FLAT). aligned=True면 `(강정렬)`, 정렬 방향 일부 일치면 `(부분정렬)`, 그 외 `(혼조)`.

**진입조건 줄:** RSI 값 + 볼륨 배수. 일부만 표시.

**사주 줄 (마지막 바로 위):** `사주: {score} ({grade}) · {dominant_axis_comment}`. dominant_axis는 4축 중 가장 극단적인(50에서 가장 먼) 축의 코멘트.

### 7.2 BTC 카드

위와 동일하되, BTC는 24/7이라 `🟢 장 중` 배지 없음 (Week 6 동작 유지).

### 7.3 모닝 사주 카드 (broadcast.py)

현재:
```
☀️ 2026-04-19 (일) 사주캔들
── 庚申 [swing] ──
재물운: ...
종합: 56 | 😐 관망
```

변경:
```
☀️ 2026-04-19 (일) 오늘의 명식 참고
── 庚申 [swing] ──
재물운:  50  | 특별한 재물 신호 없음
결단운:  50  | 평범한 결단력의 날
충돌운:  75  | 명식과 충(沖) 1건; 명식과 형(刑) 1건
합  운:  65  | 일진 오행 金이 용신과 일치
────────────
성향: 😐 관망  (변동성 주의)
추천 시진: 午시 11:00~13:00, 子시 23:00~01:00, 亥시 21:00~23:00

오늘 BTC는 /signal, 관심 종목은 /watchlist 확인.

※ 정보 제공 목적. 투자 판단과 손실 책임은 본인에게 있습니다.
```

**변경 요약:**
- 제목: "사주캔들" → "오늘의 명식 참고"
- "종합" 줄 → "성향" 줄로 대체, 점수 숫자 생략 (등급만), 괄호에 dominant axis 한 줄 코멘트
- CTA에 `/watchlist` 추가
- disclaimer 교체

### 7.4 Watchlist 요약 카드 (Week 7 유지)

변경: disclaimer만 교체.

### 7.5 전역 disclaimer 상수

`src/sajucandle/format.py` (신규 or 기존 확장):

```python
DISCLAIMER = "정보 제공 목적. 투자 판단과 손실 책임은 본인에게 있습니다."
```

사용처:
- `handlers._format_signal_card`
- `handlers.signal_command` (fallback)
- `broadcast.format_morning_card`
- `broadcast.format_watchlist_summary`

## 8. SignalResponse 확장 (models.py)

```python
class StructureSummary(BaseModel):
    state: Literal["uptrend", "downtrend", "range", "breakout", "breakdown"]
    score: int

class AlignmentSummary(BaseModel):
    tf_1h: Literal["up", "down", "flat"]
    tf_4h: Literal["up", "down", "flat"]
    tf_1d: Literal["up", "down", "flat"]
    aligned: bool
    bias: Literal["bullish", "mixed", "bearish"]
    score: int

class AnalysisSummary(BaseModel):
    structure: StructureSummary
    alignment: AlignmentSummary
    rsi_1h: float
    volume_ratio_1d: float
    composite_score: int
    reason: str

class SignalResponse(BaseModel):
    # 기존 필드 유지
    ...
    analysis: AnalysisSummary   # 신규
    # 기존 chart: ChartSummary 필드는 하위호환을 위해 유지하되 내부에서 analysis 값으로 채움
```

하위호환: 기존 `chart.score`는 `analysis.composite_score`로, `chart.rsi`는 `analysis.rsi_1h`로 채워서 Week 7 이하 클라이언트(bot 핸들러)도 깨지지 않도록.

## 9. 테스트 전략

| 파일 | 커버리지 |
|------|----------|
| `tests/test_analysis_swing.py` (신규) | Fractals 기본 감지, ATR 필터, 단일 고점/저점, 빈 데이터 |
| `tests/test_analysis_structure.py` (신규) | UPTREND/DOWNTREND/RANGE/BREAKOUT/BREAKDOWN 각 케이스, swing 2개 미만일 때 RANGE fallback |
| `tests/test_analysis_timeframe.py` (신규) | UP/DOWN/FLAT 경계 케이스 (EMA50 기울기 근사치) |
| `tests/test_analysis_multi_timeframe.py` (신규) | aligned=True/False, bias 3종, score 단조성 |
| `tests/test_analysis_composite.py` (신규) | 가중치 정확도, 경계값(0/100) 클램프 |
| `tests/test_signal_service.py` (수정) | 새 가중치 0.1/0.9 반영, 강진입 추가 조건 (정렬+추세장 아니면 진입/관망), signal_log insert 호출 확인 |
| `tests/test_repositories.py` (수정) | insert_signal_log, list_pending_tracking, update_signal_tracking (DB 통합, TEST_DATABASE_URL 필요) |
| `tests/test_broadcast.py` (수정) | Phase 0 tracking update — pending 조회, MFE/MAE 계산 mock, tracking_done 경계 (168h) |
| `tests/test_handlers.py` (수정) | 새 카드 포맷 3줄(구조/정렬/진입조건), 사주 마지막 줄, disclaimer 교체 |
| `tests/test_market_yfinance.py` (수정) | 1h/4h interval, 4h는 resample 검증 |

## 10. 관측성

- `logger.info("analysis done ticker=%s structure=%s aligned=%s composite=%s", ...)`
- `logger.info("signal_log inserted id=%s ticker=%s composite=%s", ...)`
- `logger.info("tracking updated signal_id=%s mfe=%s mae=%s done=%s", ...)`
- 기존 broadcast 로그에 `tracking_updated/completed/failed` 추가

## 11. 배포

1. 코드 푸시 → Railway 3서비스 자동 재배포.
2. **사용자 수동 작업:**
   - Supabase Studio → `migrations/003_signal_log.sql` 실행 (Week 7 migration과 동일 패턴).
   - Railway env 변경 없음 (SAJUCANDLE_ADMIN_CHAT_ID는 Week 7에서 이미).
3. 로컬 스모크: `pytest` 전량 + `python -m sajucandle.broadcast --dry-run --test-chat-id 7492682272`.
4. 운영 스모크:
   - `/signal AAPL` → 새 카드 포맷 확인 (구조/정렬/진입조건 3줄)
   - `/signal` (BTC) → 동일
   - 모닝 카드 → 제목 변경 + "정보 제공" disclaimer
   - `signal_log` 테이블에 row 쌓이는지 (`SELECT COUNT(*) FROM signal_log;`)

## 12. 위험과 대응

| 위험 | 대응 |
|------|------|
| yfinance 1h 60일 제한 | limit을 `min(limit, 24*60)`로 클램프. 4h resample 시 충분 |
| 4h resample 정확도 | `pandas.resample("4H", origin="epoch").agg(...)`로 결정론적. UTC 기준 00/04/08/12/16/20 봉 |
| 새 엔진이 기존보다 시그널 수 감소 | "강진입" 추가 조건으로 의도된 보수화. 수 줄면서 정확도 ↑ 기대 |
| signal_log 쓰기 실패 시 시그널 응답 영향 | try/except로 격리, insert 실패해도 user에게 응답은 정상 반환. warning 로그 |
| 기존 SignalResponse 필드 소비자 깨짐 | `chart` 필드는 유지하되 내부 값을 analysis로 채움 (호환성) |
| Phase 0 추적 크론 실패 | Phase 1/2/3 독립. Phase 0 예외 잡아 summary.tracking_failed 증가, 다음 Phase 진행 |
| 백테스트용 source="backtest" 구현 미흡 | Week 8에는 컬럼만 있고 사용 X. Week 11에서 완성 |
| 4주 스프린트가 길어서 사용자 피드백 없이 진행 | Week 8 말/9 초에 본인 트레이딩 관점 1차 검토 게이트 |

## 13. 완료 기준

- [ ] `analysis/` 패키지 5개 모듈 + 단위 테스트 전량 통과
- [ ] `signal_log` 테이블 migration 적용 + repository 함수 3개 동작
- [ ] `SignalService`가 새 composite 사용, 사주 0.1 / 분석 0.9 가중치
- [ ] 강진입 등급이 "점수 + 정렬 + 상승구조" 3조건 요구
- [ ] 새 `/signal` 카드 포맷 운영 확인 (구조/정렬/진입조건 3줄)
- [ ] 모닝 카드 제목 "오늘의 명식 참고" + disclaimer 교체 확인
- [ ] Phase 0 tracking 크론 1회 이상 실행 + signal_log에 MFE/MAE 업데이트 확인
- [ ] yfinance 1h/4h/1d 3개 interval 정상 조회 (주식 `/signal AAPL` 동작)
- [ ] pytest 전량 통과 + ruff clean

## 14. Week 9~11 예고

- **Week 9:** 지지/저항 자동 식별 + SL/TP 자동 제안 (카드에 "손절 $180.50, 익절 $190/$196" 라인 추가)
- **Week 10:** 시그널 발송 거부 규칙 (BREAKDOWN에서 매수 차단), 카드 UX 세밀 조정, onboarding 메시지
- **Week 11:** MFE/MAE 집계 → 카드에 백테스트 통계 노출, 등급 임계값 재조정, 관리자 리포트 API

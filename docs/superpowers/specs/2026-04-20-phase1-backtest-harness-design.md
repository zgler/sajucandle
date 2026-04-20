# Phase 1 설계 — 백테스트 하네스

- 날짜: 2026-04-20
- 대상: Phase 1 (백테스트 인프라)
- 상태: **Approved** (설계자 승인 2026-04-20)
- 선행: `docs/planning/research/phase0_current_state.md`, `CLAUDE.md`
- 베이스 커밋: `7681adb` 이상

---

## 1. 목적

과거 OHLCV 데이터로 임의 시점 `t`에서 `analyze()` + `_grade_signal()`을 재생산하고, 발생한 시그널 각각에 대해 **7일 MFE/MAE**(기존 운영 tracking 공식과 동일)를 재계산해 DB에 기록한다. Phase 2~4가 "실데이터 기반" 의사결정을 할 수 있는 증거 기반을 제공한다. 서비스 코드 회귀 0을 유지한다.

---

## 2. 목표 / 범위

### 2.1 포함

- `src/sajucandle/backtest/` 신규 패키지 (서비스 코드는 변경 안 함, 신규 모듈만).
- 과거 OHLCV 벌크 로더 + 룩어헤드 방지 슬라이서.
- `analyze()` + `_grade_signal()` 재사용 (수정 금지).
- TradeSetup은 운영 엔진 그대로 생성 (진입/강진입일 때만).
- MFE/MAE 계산 — `broadcast.run_phase0_tracking` 공식 재사용.
- `signal_log`에 `source='backtest'` + `run_id`로 기록.
- CLI: `python -m sajucandle.backtest run --ticker BTCUSDT --from 2024-04-01 --to 2026-04-01`.
- 집계 헬퍼: 등급별 승률/평균 MFE/MAE/평균 R:R를 뽑는 SQL 뷰 or 집계 함수.
- 단위·스모크 테스트 + CI 반영.

### 2.2 범위 밖 (Phase 2~4로 이연)

- 숏 신호 백테스트 (Phase 2: `_grade_signal` 대칭화 이후).
- 튜닝 그리드 서치 (Phase 4).
- RSI divergence / volatility regime (Phase 3).
- 사주 축의 백테스트 (가중치 10% → 민감도 낮음. Phase 4 민감도 분석 시 별도).
- 실시간 incremental 백테스트 (매 새 봉 들어올 때 자동 실행).

---

## 3. 설계 결정 (7개)

각 항목: 옵션 → 트레이드오프 → 추천안 → **설계자 선택**(비워둠).

### 3.1 시간 스냅샷 메커니즘 — 룩어헤드 방지

시점 `t`에 analyze()에 공급되는 OHLCV는 `open_time ≤ t`인 봉만이어야 한다.

| 옵션 | 내용 | 장점 | 단점 |
|---|---|---|---|
| A | 매 시점 `t`마다 provider 호출, `endTime=t` 파라미터 추가 | 코드 단순 | Binance API N회 호출 (1000회+/심볼), yfinance는 `endTime` 미지원 |
| B | 전체 히스토리 1회 bulk fetch → 메모리 보관 → 시점마다 슬라이싱 | **1 HTTP** / 심볼·TF, in-process 슬라이스 O(1) | 메모리 사용 (수년치 1h = ~26k 봉 × 48B ≈ 1.2MB/심볼) |
| C | Redis 캐시에 backup layer 활용 + B와 동일 슬라이싱 | 재실행 시 HTTP 0회 | 초기 실행은 B와 동일, 복잡도만 증가 |

**추천: B (bulk fetch + in-memory slice).** 이유:
- 1.2MB/심볼 × 11심볼 × 3TF = ~40MB 메모리. 현재 환경(Railway/로컬) 어디서든 여유.
- yfinance는 `endTime` 깔끔한 지원이 없어 A 불가.
- C는 B 대비 한 번만 더 시간 단축. 첫 실행 + 재실행 패턴을 위해서는 CLI `--ohlcv-cache-file <path>`로 **디스크 JSON 캐시** 도입이 Redis보다 단순.

**설계자 선택**: _____

### 3.2 타임프레임 전략

`analyze()`는 1h/4h/1d 3 TF를 요구한다.

| 옵션 | 내용 | 장점 | 단점 |
|---|---|---|---|
| A | 1d 단일 TF, analyze 대체 엔진(1h/4h 부분 스킵) | 성능 최고, yfinance 60일 제약 회피 | **운영 엔진과 다른 로직** → 백테스트 결과가 실 운영 신호를 대변 못 함 |
| B | 3 TF 전체 (운영 엔진 그대로) | 운영 엔진 1:1 재현 | yfinance 1h 60일 제한 → 주식 백테스트 기간 제한 |
| C | 자산별 분기 — crypto 3TF, stock 1d TF-only(데이터 합성 fallback) | 각 자산 최대 활용 | 복잡도↑, 주식 결과 해석 어려움 |

**추천: B (3TF 전체).** 이유:
- Phase 1의 본질은 "운영 엔진이 실제로 어떤 성과를 낳는가?"의 증거 확보. 엔진을 바꾸면 증거력 훼손.
- yfinance 60일 제한은 주식 백테스트 기간을 60일로 제한하는 식으로 수용 (Decision 3.4와 결합). 제한 받아들이는 것이 엔진 변형보다 낫다.
- 성능은 Decision 3.1-B로 이미 충분.

**설계자 선택**: _____

### 3.3 심볼 범위

운영 지원 심볼은 11종 (crypto 3 + stock 8).

| 옵션 | 내용 |
|---|---|
| A | 전체 11종 |
| B | crypto 3종만 (긴 히스토리 가능) |
| C | 대표 5종 (BTCUSDT, ETHUSDT, AAPL, NVDA, TSLA) |

**추천: A (전체 11종).** 이유:
- Phase 4 튜닝 대상이 전 심볼이므로 백테스트 범위도 일치해야 일반화 가능.
- Decision 3.1-B로 fetch 비용은 선형. 11배 증가해도 전체 실행 < 1분(로컬).

**설계자 선택**: _____

### 3.4 기간

| 옵션 | 내용 |
|---|---|
| A | 최근 1년 (crypto 3TF + stock 60일만) |
| B | 최근 2년 crypto / stock 60일 |
| C | 자산별 다르게 — crypto 3년, stock 60일(1h/4h/1d) + stock 2년(1d-only 별도 모드) |

**추천: B (crypto 2년 + stock 60일).** 이유:
- 2년치 crypto 일봉 = ~730봉 × 11심볼 중 3종. Phase 1 최소 충분 샘플 확보.
- stock 60일은 운영 엔진 재현 유지하는 상한. 통계적 유의미성은 Phase 4에서 더 많은 데이터 확보 시 재평가.
- C는 "stock 1d-only 모드"가 운영 엔진과 달라져 해석 혼란. Phase 1에서는 단일 엔진으로 갈 것.

**설계자 선택**: _____

### 3.5 시그널 발생 빈도

| 옵션 | 내용 |
|---|---|
| A | 일 1회, UTC 기준 1d 종가 시점 | 
| B | 4h마다 (1d 하루에 6회) |
| C | 1h마다 (1d 하루에 24회) |

**추천: A (일 1회).** 이유:
- 운영 `broadcast.py`가 하루 1회 (07:00 KST) 푸시. 백테스트 샘플 단위도 동일해야 "하루에 한 번 내린 판단의 성과"로 해석 일치.
- 동일 날짜에 intraday로 등급이 바뀌어도 어느 시점이 "그날의 시그널"인지 애매해짐(Phase 0 리서치 권고사항 3번 참조).
- crypto 730봉 × 3 = 2190 샘플, stock 60봉 × 8 = 480 샘플. 충분.

**설계자 선택**: _____

### 3.6 결과 저장

`signal_log`는 `source TEXT` 컬럼을 이미 가짐. 하지만 **`run_id`가 없어 동일 심볼·날짜를 여러 번 백테스트할 때 구분 불가**.

| 옵션 | 내용 |
|---|---|
| A | signal_log 그대로 사용, `source='backtest'` 단일값. 재실행 시 기존 row 삭제 후 insert 필요 |
| B | 별도 테이블 `backtest_runs` + `backtest_signals` 신설 (마이그레이션 2개) |
| C | signal_log + migration 005로 `run_id TEXT NULL` 컬럼 추가. `source='backtest'` + `run_id='phase1-2026-04-20'` 식 기록. 운영 운영 signal은 `run_id IS NULL` |

**추천: C (migration 005 + run_id 컬럼).** 이유:
- `run_id` NULL 허용 → 운영 signal 기존 코드 변경 0. 기존 집계 SQL(`aggregate_signal_stats`)도 영향 X.
- 백테스트 재실행은 `run_id` 바꿔서 여러 버전 공존 가능 (예: `phase1-baseline`, `phase1-weights-v2`). Phase 4 튜닝에 필수.
- B의 별도 테이블은 `aggregate_signal_stats` 쿼리를 duplicate해야 하고, 집계 일관성도 깨짐.

**설계자 선택**: _____

### 3.7 실행 인터페이스

| 옵션 | 내용 |
|---|---|
| A | CLI — `python -m sajucandle.backtest run --ticker BTCUSDT --from 2024-01-01 --to 2026-01-01 --run-id phase1-baseline` |
| B | Jupyter/스크립트 import 위주 |
| C | API 엔드포인트 `POST /v1/admin/backtest` |

**추천: A (CLI).** 이유:
- `broadcast.py` CLI 패턴과 통일. Railway cron 등록도 가능(분기별 자동 재실행).
- B는 A의 내부 함수 `run_backtest()`를 그대로 import 가능하므로 완비 — 추가 작업 불필요.
- C는 백테스트가 분 단위 작업이라 HTTP request/response 모델에 부적합 (timeout). 필요하면 Phase 4 이후에 고려.

**설계자 선택**: _____

---

## 4. 아키텍처

### 4.1 모듈 구성 (`src/sajucandle/backtest/`)

| 파일 | 책임 |
|---|---|
| `__init__.py` | 패키지 메타 |
| `__main__.py` | `python -m sajucandle.backtest` 엔트리 → `cli.main()` |
| `cli.py` | argparse + sub-command `run`/`aggregate` 디스패치 |
| `history.py` | 벌크 OHLCV 로더 — crypto: Binance API (확장), stock: yfinance. 디스크 JSON 캐시 (`.cache/backtest/{ticker}_{interval}.json`). |
| `slicer.py` | `HistoryWindow` dataclass — 3TF 봉들을 보관하고 `.slice_at(t: datetime) → (k1h, k4h, k1d)` 반환. 룩어헤드 방지 assertion 내장 |
| `engine.py` | `run_backtest(ticker, from_dt, to_dt, run_id, saju_score_fn) → BacktestSummary`. 매일 1회 슬라이스 → analyze → grade → trade_setup → MFE/MAE → insert_signal_log |
| `tracker.py` | `compute_mfe_mae(entry_price, post_bars_1h) → MfeMae` — `run_phase0_tracking` 내부 로직을 순수 함수로 추출 |
| `saju_stub.py` | `fixed_saju_score(chat_id, target_date, asset_class) → int` — 백테스트용 합리적 기본값 제공기 (예: 상수 50) |
| `aggregate.py` | `aggregate_run(conn, run_id) → RunStats` — 등급별 승률/평균 MFE/MAE/R:R |

### 4.2 데이터 흐름

```
                 +---------------------------+
--ticker BTCUSDT | cli.main()                |
--from 2024-04-01|   ↓                       |
--to   2026-04-01|   engine.run_backtest(...)|
--run-id baseline|                           |
                 +------┬--------------------+
                        │
           +------------┼-------------+-------------------+
           ↓            ↓             ↓                   ↓
   history.load_all  slicer.build  saju_stub.fixed   repositories.
   (Binance|yf +      HistoryWindow score              insert_signal_log
   disk cache)        (3TF bars)                       (source='backtest',
           │            │             │                run_id=...)
           └────────────┴─────────────┘                       ↑
                        │                                     │
                        ↓                                     │
              for t in daily_t_series(from_dt, to_dt):        │
                  (k1h, k4h, k1d) = window.slice_at(t)        │
                  analysis = composite.analyze(k1h,k4h,k1d)   │
                  final = round(0.1*saju + 0.9*analysis.cs)   │
                  grade = signal_service._grade_signal(...)   │
                  if grade in ("강진입","진입"):              │
                      ts = trade_setup.compute_trade_setup(..)│
                  mfe, mae = tracker.compute_mfe_mae(          │
                      entry=k1d[-1].close,                    │
                      post_bars_1h = window.post_bars(t,168h) │
                  )                                           │
                  insert_signal_log(...) ───────────────────→ │
```

### 4.3 핵심 시그니처 (스텁)

```python
# history.py
@dataclass
class TickerHistory:
    ticker: str
    klines_1h: list[Kline]
    klines_4h: list[Kline]
    klines_1d: list[Kline]

def load_history(
    ticker: str,
    from_dt: datetime,
    to_dt: datetime,
    *,
    provider: MarketDataProvider,
    cache_dir: Optional[Path] = None,
) -> TickerHistory: ...

# slicer.py
@dataclass
class HistoryWindow:
    history: TickerHistory
    def slice_at(self, t: datetime) -> tuple[list[Kline], list[Kline], list[Kline]]: ...
    def post_bars_1h(self, t: datetime, hours: int = 168) -> list[Kline]: ...

# engine.py
@dataclass
class BacktestSummary:
    run_id: str
    ticker: str
    from_dt: datetime
    to_dt: datetime
    signals_total: int
    signals_by_grade: dict[str, int]
    insert_errors: int

async def run_backtest(
    *,
    ticker: str,
    from_dt: datetime,
    to_dt: datetime,
    run_id: str,
    router: MarketRouter,
    saju_score_fn: Callable[[date, str], int] = lambda d, ac: 50,
    cache_dir: Optional[Path] = None,
    insert_log_fn: Optional[Callable] = None,   # 테스트 주입 지점
) -> BacktestSummary: ...

# tracker.py
@dataclass
class MfeMae:
    mfe_pct: float
    mae_pct: float
    close_24h: Optional[float]
    close_7d: Optional[float]

def compute_mfe_mae(
    entry_price: float,
    post_bars_1h: list[Kline],
    sent_at: datetime,
) -> Optional[MfeMae]: ...

# aggregate.py
@dataclass
class GradeStats:
    grade: str
    count: int
    win_rate: float         # mfe_7d_pct > 0 비율
    avg_mfe: float
    avg_mae: float
    avg_rr_tp1: Optional[float]

async def aggregate_run(conn, run_id: str) -> list[GradeStats]: ...
```

---

## 5. 데이터 모델

### 5.1 Migration 005 (Decision 3.6-C 시)

```sql
-- migrations/005_signal_log_run_id.sql
ALTER TABLE signal_log
    ADD COLUMN IF NOT EXISTS run_id TEXT NULL;

CREATE INDEX IF NOT EXISTS idx_signal_log_run_id
    ON signal_log(run_id, ticker, target_date)
    WHERE run_id IS NOT NULL;

-- 운영 signal은 run_id IS NULL 유지 → 기존 인덱스/쿼리 영향 없음.
```

`repositories.insert_signal_log`에 `run_id: Optional[str] = None` 인자 추가 필요 (서비스 코드 변경 1건 — 본 Phase에서 최소 한정).

### 5.2 BacktestRun / BacktestSignal — 불필요 (Decision 3.6-C 채택 시)

---

## 6. 시간 스냅샷 / 룩어헤드 방지

### 6.1 구체 규칙

- 시점 `t`는 **UTC 일봉 종가 시각** (매일 00:00 UTC). 1d 봉 중 `open_time == t_prev_day`인 봉이 **해당 날짜의 "마지막 완성된 봉"**.
- `window.slice_at(t)`가 반환하는 각 TF는 **`open_time + interval ≤ t`**인 봉만 포함 (종가 시점 t에 이미 "닫힌" 봉).
- 금지 규칙 (assertion):
  - `klines_1d[-1].open_time + 1d <= t`
  - `klines_4h[-1].open_time + 4h <= t`
  - `klines_1h[-1].open_time + 1h <= t`

### 6.2 테스트로 보호

- `test_backtest_slicer.py`: 의도적으로 미래 봉 포함 시 assertion 실패 확인.
- 동일 `t`에 대해 `slice_at`을 2회 호출해도 반환 동일 (결정적).

---

## 7. 성능

### 7.1 예상 연산량

- crypto 2년 × 1심볼: 1d 730봉, 4h 4380봉, 1h 17520봉 → fetch 3회 HTTP.
- stock 60일 × 1심볼: 1d 60봉, 4h 360봉, 1h 1440봉 → fetch 3회.
- 11 심볼 총 33 HTTP call. Binance rate limit 1200/min → 여유.
- Signal 평가: crypto 730회 × 3 + stock 60회 × 8 = 2670회. `analyze()`는 1봉당 수 ms → 전체 < 30초.

### 7.2 병렬화

- 심볼 간 embarrassingly parallel. `asyncio.gather` 또는 `concurrent.futures.ProcessPoolExecutor` 둘 다 가능.
- **권고**: 초기 버전은 **직렬 실행** (11 심볼 × 30초 = 5~6분). 복잡도 낮게 시작. Phase 4 튜닝 루프에서 병렬화 필요 시 추가.

---

## 8. 집계 / 분석

### 8.1 승률 계산 공식

- **승**: `mfe_7d_pct > 0` (7일 내 entry 대비 +0% 초과 도달).
- **패**: `mfe_7d_pct ≤ 0` OR `mae_7d_pct < -SL_pct (risk_pct)`.
- (옵션) **정교한 정의**: "TP1 도달 여부" — `post_bars`에서 TP1 가격 터치 시 승. Phase 1에서는 단순 MFE 승률로 시작, Phase 4에서 정교화.

### 8.2 등급별 MFE/MAE 분포

```python
# aggregate.py 반환 구조 예시
[
    GradeStats(grade="강진입", count=12, win_rate=0.83, avg_mfe=4.2, avg_mae=-1.8, avg_rr_tp1=1.5),
    GradeStats(grade="진입",   count=48, win_rate=0.58, avg_mfe=2.1, avg_mae=-2.5, avg_rr_tp1=1.4),
    GradeStats(grade="관망",   count=410, win_rate=0.45, avg_mfe=1.2, avg_mae=-2.0, avg_rr_tp1=None),
    GradeStats(grade="회피",   count=150, win_rate=0.30, avg_mfe=0.5, avg_mae=-3.2, avg_rr_tp1=None),
]
```

### 8.3 결과 조회 SQL 예시

```sql
-- 등급별 승률
SELECT signal_grade,
       COUNT(*) AS n,
       AVG(CASE WHEN mfe_7d_pct > 0 THEN 1.0 ELSE 0.0 END) AS win_rate,
       AVG(mfe_7d_pct) AS avg_mfe,
       AVG(mae_7d_pct) AS avg_mae
FROM signal_log
WHERE run_id = $1 AND tracking_done = TRUE
GROUP BY signal_grade
ORDER BY AVG(mfe_7d_pct) DESC;

-- 심볼별 성과
SELECT ticker, signal_grade, COUNT(*), AVG(mfe_7d_pct), AVG(mae_7d_pct)
FROM signal_log
WHERE run_id = $1
GROUP BY ticker, signal_grade;

-- 구조별 분포
SELECT structure_state, signal_grade, COUNT(*), AVG(mfe_7d_pct)
FROM signal_log WHERE run_id = $1
GROUP BY structure_state, signal_grade;
```

---

## 9. 테스트 전략

### 9.1 단위 테스트

| 파일 | 대상 | 케이스 |
|---|---|---|
| `test_backtest_slicer.py` | HistoryWindow | slice_at 룩어헤드 방지, 미래 봉 포함 시 assertion, 동일 t 결정적 |
| `test_backtest_tracker.py` | compute_mfe_mae | `run_phase0_tracking` 공식과 동치성 (기존 테스트와 parametrize 공유) |
| `test_backtest_engine.py` | run_backtest | mock history + mock insert → 등급별 카운트 정합, `run_id` 전파, 시그널 수 = 일수 |
| `test_backtest_aggregate.py` | aggregate_run | 합성 signal_log rows → win_rate/MFE 집계 정합 |
| `test_backtest_cli.py` | CLI 파싱 | `--from` 잘못된 형식, 필수 인자 누락 |

### 9.2 통합 테스트 (smoke)

- `tests/test_backtest_smoke.py`:
  - fake history (수작업 합성 klines 20봉) × 1심볼로 end-to-end 실행.
  - `db_conn` fixture (TEST_DATABASE_URL 시) 에 insert → aggregate 확인.
  - TEST_DATABASE_URL 없으면 skip.

### 9.3 회귀 방어 (CI)

- 현재 `.github/workflows/ci.yml`에 pytest 실행 존재 (Phase 0 커밋으로 추가됨).
- 신규 test 파일 자동 수집.
- 추가 권고: CI에 **fake-history 기반 전체 백테스트 실행 (< 10초)** 스텝 — 정적 기대 등급 카운트 확인으로 `analyze()` 회귀 방어.

---

## 10. 관측성

- 진행률 로그: 심볼 시작/종료, 시그널 발생 시 매 10회당 `logger.info`.
- 실패한 시그널 복구:
  - `analyze()` 예외 → 로그 + 해당 t 건너뛰고 다음 t로.
  - `insert_signal_log` 실패 → 재시도 1회 → 실패 시 `BacktestSummary.insert_errors` 누적.
- CLI 종료 시 요약 출력:
  ```
  run_id=phase1-baseline ticker=BTCUSDT signals=730
    by_grade: 강진입=12 진입=48 관망=410 회피=260
    insert_errors=0 elapsed=8.3s
  ```

---

## 11. 위험과 대응

| # | 위험 | 영향 | 대응 |
|---|---|---|---|
| 1 | yfinance 1h 60일 제한 | 주식 백테스트 히스토리 짧음 | Decision 3.4에서 stock 60일로 한정, 추가 데이터는 Phase 2 이후 별도 수집 |
| 2 | Binance 벌크 fetch 실패 | 백테스트 실행 불가 | 디스크 캐시 우선 참조 + 실패 시 명확한 에러 메시지 (rate limit 구분) |
| 3 | `_grade_signal`/`analyze` 로직 변경이 과거 백테스트 결과와 불일치 | run 간 비교 무의미 | `run_id`에 **커밋 SHA prefix** 포함 권고 (예: `phase1-7681adb-baseline`) |
| 4 | `signal_log` 대량 row 삽입으로 운영 쿼리 느려짐 | `/stats` 느려짐 | `run_id IS NULL`로 운영 쿼리 필터링 (Phase 0 리서치의 `aggregate_signal_stats`는 이미 그래야 함 → 검토 필요) |
| 5 | 사주 점수 stub 값이 등급 판정 경계에 영향 | 결과 편향 | Phase 1은 상수 50 사용 + Phase 4 민감도 분석에서 {0, 50, 100} 3가지 돌려 차이 확인 |
| 6 | 룩어헤드 버그 | 백테스트 결과 위조됨 | Decision 6.2 assertion + 단위 테스트 강제 |
| 7 | SL 도달 판정 누락 | 등급별 성과 왜곡 | Phase 1 단순 MFE 승률로 시작, Phase 4에서 TP/SL 도달 분기 추가 |

---

## 12. 완료 기준

- [ ] `src/sajucandle/backtest/` 패키지 8개 모듈 구현 (`__init__`, `__main__`, `cli`, `history`, `slicer`, `engine`, `tracker`, `saju_stub`, `aggregate`).
- [ ] migration 005 작성 + `repositories.insert_signal_log`에 `run_id` 파라미터 추가 (유일한 서비스 코드 변경 지점).
- [ ] 단위 테스트 5개 + smoke 테스트 1개 전부 통과.
- [ ] 기존 307 passed 수 유지 또는 증가, 0 failures.
- [ ] CLI 실행 `python -m sajucandle.backtest run --ticker BTCUSDT --from 2024-04-20 --to 2026-04-20 --run-id phase1-smoke` 로컬 성공.
- [ ] CLI 실행 `python -m sajucandle.backtest aggregate --run-id phase1-smoke` → 등급별 표 출력.
- [ ] ruff 통과 (`python -m ruff check src/sajucandle/backtest tests/test_backtest_*`).
- [ ] 이 spec 기반 **구현 플랜 문서** (`docs/superpowers/plans/2026-04-??-phase1-backtest-harness-plan.md`) 작성 완료.

---

## 13. Phase 2 예고

Phase 2 (숏 대칭 + 5등급)에서 본 하네스 활용 방식:

1. `_grade_signal` 대칭 구현 후 동일 기간/심볼로 **두 개의 run** 비교:
   - `run_id=phase2-long-only` (기존 로직 — Phase 1 baseline)
   - `run_id=phase2-symmetric` (숏 포함)
2. 하락장 구간(2022 BTC 곰시장 등)에서 **숏 등급 샘플 수와 MFE 분포** 확인 → 숏 로직 설계 타당성 검증.
3. `aggregate_run` 결과 diff → Phase 2 PR의 "before/after" 증거 섹션.

Phase 3 (지표 고도화)도 마찬가지: RSI divergence 반영 전/후 run 비교.
Phase 4 (튜닝)는 하네스가 핵심 인프라 — 가중치 grid ({0.40/0.40/0.10/0.10}, {0.50/0.30/0.10/0.10} 등) × 임계값 grid ({70/55/35}, {75/60/40}) 전체 × 심볼 run_id를 생성해 Pareto front 도출.

---

## 14. 설계자 승인 (2026-04-20 완료)

| # | 항목 | 승인 내용 |
|---|------|-----------|
| 1 | Decision 3.1~3.7 | **전부 추천안 채택** |
| 2 | 서비스 코드 변경 범위 | **4건 확장 승인** — spec §5.2 테이블 참조. `insert_signal_log` + migration 005 + `aggregate_signal_stats` (run_id 필터) + `admin_signal_stats_endpoint` |
| 3 | Saju stub 값 | **50 (중립)**. Phase 4 민감도 분석에서 `{0, 50, 100}` 3값 비교 |
| 4 | run_id 포맷 | **`phase{N}-{git-sha-short7}-{label}`**. CLI 미지정 시 자동 생성 (`phase1-{sha}-{yyyymmdd}`) |
| 5 | HistoryWindow 방향성 | `slice_at(t)` = t 이전만 (assertion), `post_bars_1h(t)` = t 이후만 (룩어헤드 허용) |
| 6 | CLI aggregate 출력 | 기본 텍스트 표, `--json` 플래그로 JSON |
| 7 | 성능 §7.1 메모리 | **정정: ~4MB** (spec 초안 "~40MB"는 과대) |

**플랜 문서**: `docs/superpowers/plans/2026-04-20-phase1-backtest-harness-plan.md`

**구현 시작 전 주의**:
- CLAUDE.md §1.1 "구현해" 지시 전까지 서비스 코드 수정 금지 원칙 유지.
- 본 Phase 1은 위 4건 서비스 코드 변경이 범위 안에 포함되나, 각 Task 완료 시점마다 plan의 checkpoint 준수.

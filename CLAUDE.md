# CLAUDE.md — SajuCandle 프로젝트 지침

> Claude Code 세션 시작 시 최우선으로 이 문서를 읽고 모든 작업을 진행하기 전 준수해야 할 규칙·용어·컨벤션을 따른다.

## 1. 워크플로우 규칙

### 1.1 설계자-실행자 모델
- **설계자는 사용자.** 너(Claude)는 실행자(Executor)다.
- 사용자가 `"구현해"` 또는 동등한 명시적 지시를 내리기 전까지 **서비스 코드(`src/sajucandle/*`)를 수정하지 않는다**.
- 리서치, 설계, 플랜 문서 작성은 항상 먼저 한다. 실행은 승인 후.

### 1.2 산출물 규칙
- 채팅에 장문 작성 금지. 모든 산출물은 `docs/**/*.md` 파일로 쓰고 채팅엔 경로와 요약만.
- 산출물 디렉토리 표준:
  - `docs/planning/research/` — 현황 파악 리서치
  - `docs/superpowers/specs/` — 설계 스펙
  - `docs/superpowers/plans/` — 구현 플랜

### 1.3 Phase 모델
- 현재 진행 중: **Phase 0** (현황 파악) → Phase 1 (백테스트 하네스) → Phase 2 (숏 대칭) → Phase 3 (지표 고도화) → Phase 4 (튜닝).
- 각 Phase 완료 시 사용자 승인 대기 → 다음 Phase 프롬프트 작성.

## 2. 도메인 용어

| 용어 | 정의 |
|------|------|
| **swing** | Fractals + ATR prominence 필터로 감지한 국소 고/저점 (`SwingPoint`) |
| **structure** | swing 기반 시장 상태 분류 (UPTREND/DOWNTREND/RANGE/BREAKOUT/BREAKDOWN) |
| **alignment** | 1h/4h/1d 3개 TF의 trend_direction 정렬 상태 |
| **composite_score** | analyze()의 최종 점수 (0.45 structure + 0.35 alignment + 0.10 rsi + 0.10 volume, 0~100) |
| **final_score** | `0.1 × saju + 0.9 × analysis.composite_score` (등급 판정 입력) |
| **signal_grade** | 강진입/진입/관망/회피 4종 (롱 관점. 숏은 Phase 2에서 추가) |
| **TradeSetup** | entry/SL/TP1/TP2/R:R/risk_pct 구체 가격 제시 (진입/강진입 등급만) |
| **S/R** | Support/Resistance 레벨. swing + volume profile 융합 |
| **VPVR** | Volume Profile Visible Range. bucket별 volume 합 상위 N개 |
| **ATR** | Average True Range (Wilder, period=14). 변동성 지표 |
| **EMA** | Exponential Moving Average (period=50, α=2/51) |
| **iljin** | 日辰 — 해당 날짜의 천간지지 (명리) |
| **yongsin** | 用神 — 명식 전체 균형에 도움되는 오행 |

## 3. 코딩 컨벤션

### 3.1 Python 스타일
- **Python 3.12+** 전제. `from __future__ import annotations` 항상 사용.
- **PEP 621** + hatchling 빌드. `pyproject.toml`에 의존성 관리.
- **ruff** 린트 (line-length=100, target-version=py312). 커밋 전 `python -m ruff check src/ tests/` 통과 필수.
- 타입 힌트 적극 사용. dataclass / Pydantic BaseModel로 데이터 구조 표현.
- **Private 상수**는 module-level `_PREFIX` 언더스코어.
- **async** I/O는 FastAPI + asyncpg. 순수 계산 함수는 sync.

### 3.2 테스트
- pytest + pytest-asyncio (`asyncio_mode = "auto"`).
- TDD 선호: 테스트 먼저 → 실패 확인 → 구현 → 통과 → commit.
- DB 통합 테스트는 `db_conn` fixture(트랜잭션 롤백) 사용. `TEST_DATABASE_URL` 없을 때 자동 skip.
- Mock: `unittest.mock` + `respx` (httpx) + `fakeredis`.

### 3.3 커밋 메시지
- Conventional commits: `feat(scope): ...`, `fix(...)`, `docs(...)`, `refactor(...)`, `test(...)`.
- 각 task = 1 commit 원칙 (구현 플랜의 subagent-driven 패턴 계승).

## 4. 모듈 책임

### 4.1 분석 엔진 (`src/sajucandle/analysis/`)

| 모듈 | 책임 |
|------|------|
| `swing.py` | Fractals + ATR prominence → `SwingPoint` list |
| `structure.py` | swings → `MarketStructure` enum + score |
| `timeframe.py` | 단일 TF EMA50 기반 `TrendDirection` enum |
| `multi_timeframe.py` | 3TF 정렬 → `Alignment` (aligned/bias/score) |
| `volume_profile.py` | VPVR bucket 누적 → top-N `VolumeNode` |
| `support_resistance.py` | swing + volume 융합 → 현재가 기준 `SRLevel` 최대 6개 |
| `trade_setup.py` | ATR + S/R snap 하이브리드 → `TradeSetup` |
| `composite.py` | 위 모듈 조합 → `AnalysisResult` (analyze 엔트리) |

### 4.2 서비스 레이어

| 모듈 | 책임 |
|------|------|
| `signal_service.py` | analyze() + 사주 합산 + 등급 판정 + TradeSetup 생성 + Redis 캐시 |
| `score_service.py` | 사주 4축 점수 + KST 자정 TTL 캐시 |
| `tech_analysis.py` | RSI/SMA/volume_ratio/score 매핑 (순수 함수) |
| `market_data.py` | Binance OHLCV 클라이언트 + 2-tier Redis 캐시 (fresh 5분/backup 24h) |
| `market/yfinance.py` | yfinance OHLCV + 2-tier 캐시 (fresh 1h/backup 24h) + 4h resample |
| `market/router.py` | ticker → provider 라우팅 + 화이트리스트 |

### 4.3 인프라

| 모듈 | 책임 |
|------|------|
| `api.py` | FastAPI 엔드포인트 전체 (14개) |
| `api_client.py` | 봇 → API httpx 래퍼 |
| `handlers.py` | Telegram 커맨드 (13개) + 카드 포맷 |
| `broadcast.py` | 일일 푸시 CLI (Phase 0 tracking → Phase 1 precompute → Phase 2 사주 → Phase 3 watchlist) |
| `repositories.py` | DB CRUD (users/user_bazi/user_watchlist/signal_log) |
| `models.py` | Pydantic 모델 |
| `format.py` | 명식 카드 + DISCLAIMER 상수 |

## 5. 제약사항 / 주의점

### 5.1 외부 API 제약
- **yfinance 1h 인터벌**: 최근 **60일**만 조회 가능. 백테스트 시 제약.
- **yfinance 4h**: 네이티브 미지원 → 1h 데이터를 `pandas.resample("4h", origin="epoch")`로 집계.
- **Binance `data-api.binance.vision`**: Market data 공개 미러. 인증 불필요. Railway IP 차단 우회 (`api.binance.com`은 차단됨).
- **미국 장 공휴일 미처리**: `is_market_open`이 True로 잘못 판정될 수 있음 (1년 ~9일). `last_session_date`는 yfinance가 휴장일 데이터 안 주므로 정확.

### 5.2 로직 제약
- **숏 미지원**: 현재 분석은 롱 관점만. 하락장은 "회피"로만 표시. Phase 2에서 대칭 구현 예정.
- **사주 가중치 10%**: Week 8에서 0.4→0.1로 강등. 실 트레이딩 판단은 차트 중심.
- **구조 판정 엄격**: UPTREND/DOWNTREND는 3개 연속 HH-HL/LH-LL 요구. swing 부족 시 RANGE 폴백 → composite에서 alignment 50% 섞음.
- **튜닝 상수**: `_SL_ATR_MULT` 등은 **백테스트 이전 initial value**. Phase 4에서 조정 예정.

### 5.3 캐시 TTL (provider별 비대칭 주의)
- Binance OHLCV: **fresh 5분** (24/7 시장 실시간성)
- yfinance OHLCV: **fresh 1h** (시간외 변동 작음)
- Signal composite: 5분 (`signal:*`)
- 사주: KST 자정까지 (`score:*`)

## 6. 현재 구현 상태 (Phase 0 확정)

- **브랜치**: `main` (commit `c092a7c` 기준)
- **주차**: Week 10 Phase 2 완료
- **테스트**: 307 passed, 69 skipped
- **상세**: `docs/planning/research/phase0_current_state.md`

## 7. 다음 단계 (Phase 1 준비)

Phase 1은 **백테스트 하네스 구축**. 시작 전 설계자가 Phase 0 리서치의 "Open Questions"에 답변 필요:

1. volume_profile.top_n 기본값 3 → 5 보정 여부
2. OHLCV TTL 비대칭을 명세 반영 or 코드 일원화
3. Phase 1 전 CI 도입 여부
4. backtest 패키지 경로 (신규 vs broadcast CLI 확장)

위 답변 후 Phase 1 프롬프트 작성 단계로 이동.

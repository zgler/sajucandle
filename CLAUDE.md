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

### 1.3 Phase 모델 (현재 기준: Phase 4 완료)
- Phase 0 (현황 파악) → Phase 1 (백테스트 하네스) → Phase 2 (숏 대칭) → Phase 3 (지표 고도화) → **Phase 4 (Saju-filter quant + 월간 시그널)**.
- Phase 4 산출물이 `main` 브랜치 기준 `src/sajucandle/`의 현행 구조다. 이전 Phase(analysis/backtest/market 아키텍처)는 제거됨.

## 2. 도메인 용어 (Phase 4 기준)

| 용어 | 정의 |
|------|------|
| **saju_score** | 명식 × 일진/세운의 궁합을 천간·지지 관계로 평가한 0~100 점수 (`saju/scorer.py`) |
| **saju_score_v2** | 3컴포넌트(Heaven-Earth / Day-Ilju / Daeun) + ICIR 가중. Null Test FAIL로 deprecated |
| **C 필터** | Saju score 임계값 미만 티커를 쿼트 랭킹 전에 제외하는 전략 (Phase 4 확정 전략) |
| **regime** | SPY 3개월 롤링 기반 Bull/Bear/Sideways 레짐 감지 (`signal/regime.py`) |
| **signal_type** | 월간 시그널 6종: BUY/ACCUMULATE/HOLD/WATCH/SELL/KILL (`signal/engine.py`) |
| **ta_score** | RSI/MACD/Bollinger 기반 기술적 점수 (주식/코인 분리, `quant/technical.py`) |
| **macro_score** | 거시지표 보조 점수. 주식/코인(crypto_macro) 분리 |
| **fa_score** | 펀더멘털 지표 점수 (주식 전용, `quant/fundamental.py`) |
| **onchain_score** | 온체인 지표 점수 (코인 전용, `quant/onchain.py`) |
| **null_test** | Saju 점수를 무작위 대체해 z-score로 유효성 검증 (`quant/null_test.py`) |
| **OOS validation** | 학습(2015-19)/테스트(2020-24) threshold grid 검증 |
| **iljin** | 日辰 — 해당 날짜의 천간지지 (명리) |
| **daeun** | 大運 — 10년 단위 대운 (`saju/daeun.py`) |
| **sewoon** | 歲運 — 1년 단위 세운 (`saju/sewoon.py`) |
| **shinsal** | 神煞 — 길흉 특수 관계 (`saju/shinsal.py`) |
| **manseryeok** | 萬歲曆 — 천문력 기반 사주 계산 (skyfield ephemeris + CSV, `manseryeok/core.py`) |

## 3. 코딩 컨벤션

### 3.1 Python 스타일
- **Python 3.12+** 전제. `from __future__ import annotations` 적극 사용.
- **PEP 621** + hatchling 빌드. `pyproject.toml`에 의존성 관리.
- **ruff** 린트 (line-length=100, target-version=py312). 커밋 전 `./.venv/Scripts/python.exe -m ruff check src/ tests/` 통과 권장.
- 타입 힌트 적극 사용. dataclass / Pydantic BaseModel로 데이터 구조 표현.
- pandas/numpy를 많이 쓰므로 순수 dict 대신 DataFrame 기본.

### 3.2 테스트
- **Phase 4는 smoke test 스크립트 기반**: `tests/smoke_test_*.py`. pytest로 자동 수집되지 않고 직접 실행한다.
- 실행: `PYTHONPATH=src ./.venv/Scripts/python.exe tests/smoke_test_<name>.py`.
- 결과물은 `tests/smoke_output_<name>.{json,html}` 또는 `tests/smoke_output_<name>/` 에 기록.
- 핵심 회귀 smoke: `smoke_test_oos_validation.py`, `smoke_test_regime_engine.py`, `smoke_test_coin_v2.py`, `smoke_test_nulltest_v2.py`, `smoke_test_signal_engine.py`.

### 3.3 커밋 메시지
- Conventional commits: `feat(scope): ...`, `fix(...)`, `docs(...)`, `refactor(...)`, `test(...)`, `chore(...)`.
- 각 논리 변경 = 1 commit 원칙.

## 4. 모듈 책임 (Phase 4)

### 4.1 사주 레이어 (`src/sajucandle/saju/`, `manseryeok/`)

| 모듈 | 책임 |
|------|------|
| `manseryeok/core.py` | `SajuCalculator` — 출생일시 → 명식 4주. skyfield CSV + geopy 경도 보정 |
| `saju/constants.py` | 천간/지지/오행 상수 |
| `saju/relations.py` | 천간합/충, 지지 육합/삼합/충/형/파/해 관계 |
| `saju/tengod.py` | 십신(十神) 계산 |
| `saju/shinsal.py` | 신살(神煞) 판정 |
| `saju/daeun.py` / `sewoon.py` | 대운/세운 |
| `saju/scorer.py` | `saju_score()` — 명식 × 일진 궁합 점수 엔트리 |

### 4.2 쿼트 레이어 (`src/sajucandle/quant/`)

| 모듈 | 책임 |
|------|------|
| `price_data.py` | yfinance 기반 OHLCV 로더 + `data/prices/` 캐시 |
| `technical.py` | RSI/MACD/Bollinger → `ta_score_stock`/`ta_score_coin` (ta 라이브러리) |
| `macro.py` / `crypto_macro.py` | 거시 지표 점수 (주식/코인) |
| `fundamental.py` | 펀더멘털 점수 (yfinance) |
| `onchain.py` | 온체인 점수 (코인 전용) |
| `ranker.py` | 종목 랭킹 (saju filter + 쿼트 점수 합산) |
| `backtest.py` | 월간 백테스트 엔진 (saju_filter_mode 지원) |
| `null_test.py` | 사주 점수 placebo 테스트 |
| `saju_calibrator.py` | 사주 점수 calibration (ICIR 등) |

### 4.3 시그널·서비스 레이어

| 모듈 | 책임 |
|------|------|
| `signal/regime.py` | SPY 3M 롤링 기반 Bull/Bear/Sideways 감지 |
| `signal/engine.py` | 월간 시그널 생성기 — `generate_signals()` → BUY/HOLD/SELL/WATCH/KILL |
| `signal/renderer.py` | Telegram MDv2 / HTML 이메일 / 텍스트 출력 |
| `ticker/schema.py` | `TickerRecord`, `TransitionPoint` 데이터클래스 |
| `ticker/loader.py` | `data/tickers/*.csv` 로더 |
| `ticker/saju_resolver.py` | 티커 상장일 → 명식 계산 |
| `api/main.py` | FastAPI — `/health`, `/signals/stock`, `/signals/stock/html`, `/signals/stock/telegram` |
| `scheduler/runner.py` | APScheduler — 매월 1일 09:00 KST 자동 실행 + Telegram 전송 훅 |
| `transport/config.py` | `TransportConfig` — `.env` → 설정 (SecretStr Bot Token 보호) |
| `transport/telegram.py` | `send_message()` — httpx 기반 Telegram Bot API 전송, MDv2 + chunk + retry |

### 4.4 보조 도구 (`tools/`, optional deps `[tools]`)

| 모듈 | 책임 |
|------|------|
| `tools/compute_solar_terms.py` | skyfield + DE440s.bsp → 24절기 JSON 생성 |
| `tools/build_manseryeok_csv.py` | 만세력 CSV 빌드 |
| `tools/verify_day_pillar.py` / `cross_validate_day_pillar.py` | 일주 검증 |
| `tools/compare_solar_terms.py` | 절기 비교 |

## 5. 실행 진입점

### 5.1 로컬 개발
```bash
# venv + deps
py -3.14 -m venv .venv
./.venv/Scripts/python.exe -m pip install -e ".[dev]"

# 툴 작업 시
./.venv/Scripts/python.exe -m pip install -e ".[tools]"

# smoke test 1개
PYTHONPATH=src ./.venv/Scripts/python.exe tests/smoke_test_signal_engine.py
```

### 5.2 API 서버
```bash
PYTHONPATH=src ./.venv/Scripts/python.exe -m uvicorn sajucandle.api.main:app --port 8001
```
엔드포인트: `GET /health`, `GET /signals/stock` (JSON / html / telegram)

### 5.3 월간 스케줄러
```bash
# 데몬 (매월 1일 09:00 KST)
PYTHONPATH=src ./.venv/Scripts/python.exe -m sajucandle.scheduler.runner --daemon

# 수동 실행 (특정일)
PYTHONPATH=src ./.venv/Scripts/python.exe -m sajucandle.scheduler.runner --date 2026-05-01

# Telegram 전송 없이 파일 저장만 (드라이런)
PYTHONPATH=src ./.venv/Scripts/python.exe -m sajucandle.scheduler.runner --date 2026-05-01 --no-notify
```

`.env` (또는 배포 환경변수)에 `TRANSPORT_ENABLED=true`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ADMIN_CHAT_ID` 설정 시 잡 말미에 관리자 Telegram 전송. `.env.example` 참고.

### 5.4 배포 (Railway / 범용 Docker)
- Dockerfile CMD: `uvicorn sajucandle.api.main:app --host 0.0.0.0 --port 8000`
- Procfile `web` / `worker` 는 API / 스케줄러 각각.

## 6. 제약사항 / 주의점

### 6.1 런타임 데이터 / 설정
- **data/tickers/**, **data/manseryeok/**, **data/solar_terms/** 는 git tracking (런타임 필수).
- **data/prices/**, **data/signals/** 는 gitignore (캐시/출력). 재계산 가능.
- **.bsp 천체력 파일**(de421.bsp 16MB, de440s.bsp 32MB)은 gitignore. 필요 시 `skyfield.api.load()`로 재다운로드.
- **`.env` TRANSPORT_ENABLED**: `false` 기본값. `true` + `TELEGRAM_BOT_TOKEN` + `TELEGRAM_ADMIN_CHAT_ID` 주입 시에만 실제 Telegram 전송. 설정 예시는 `.env.example`.

### 6.2 외부 API / 환경
- **yfinance**: 1h 인터벌 최근 60일 제한. 일봉 기반 백테스트는 무제한.
- **Windows stdout 버퍼링**: 스크립트 실행 시 `sys.stdout.reconfigure(encoding="utf-8")` 권장.
- **bash-native 실행**: `PYTHONPATH=src ./.venv/Scripts/python.exe ...` 형태.
- **APScheduler**: `job.next_run_time`은 `scheduler.start()` 이후에만 유효.
- **FastAPI load_tickers**: `Path` 객체 필요 (`str()` 변환 금지).

### 6.3 로직 제약 (검증 결과)
- **사주 = 가중치 실패, 필터로만 유효**
  - Null Test v1 (30% 가중): z = −7.46 FAIL
  - Null Test v2 (10% 가중, 3컴포넌트): z = −3.97 FAIL
  - 원인: 60갑자 사이클 → 구조적 나이/섹터 편향
- **확정 전략 = C 필터**: saju_score < 30 제외 후 순수 퀀트 랭킹
- **Regime-conditional은 불필요**: Sideways 71% → always-ON과 동일
- **OOS 검증 PASS (2026-04-24)**: threshold 20/30 동률, 40+ 급락 (overfitting 경계)
- **saju_score_v2는 deprecated**

### 6.4 검증 결과 요약

| 전략 | 자산 | CAGR | Sharpe | MDD |
|---|---|---|---|---|
| C 필터 <30 | 주식 2015-24 | 14.0% | 0.97 | −14.8% |
| C 필터 <30 | 코인 2020-24 | 85.8% | 0.93 | −72.5% |
| SPY B&H (baseline) | 주식 2015-24 | 13.0% | 0.90 | −33.7% |

## 7. 현재 구현 상태 (2026-04-24)

- **브랜치**: `phase4-logic-merge` (main 기준 +N 커밋, Phase 4 로직 반입)
- **Phase**: 4 완료 (검증·OOS PASS)
- **테스트**: smoke test 22종, pytest 수집 0건 (Phase 4는 스크립트 기반)
- **핸드오버**: `PHASE4_HANDOVER.md` (상세 매니페스트 + 검증 테이블)

## 8. 다음 단계 후보

1. threshold 20 vs 30 실운영 선택 (OOS 동률 → A/B 시험)
2. UI/렌더링 연결 — renderer 출력을 프론트엔드/이메일/텔레그램 봇에 연결
3. 구독자 DB 연동 — 시그널 → 구독자별 전송 파이프라인
4. 결제 연동
5. Phase 2 코인 정밀 재검증 (50개월 / 15종)

위 중 선택 후 스펙 작성 → 플랜 → 실행 순서.

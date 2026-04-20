# 사주캔들 (SajuCandle)

사주 일진(日辰) 점수와 기술적 차트 분석을 결합해 개인별 매매 진입 시점을 추천하는 서비스.
현재는 MVP 초기 단계 — Telegram 봇 + FastAPI 백엔드 + Redis 캐시.

> **정보 제공 목적. 투자 판단과 손실 책임은 본인에게 있습니다.**

---

## 아키텍처

```
[Telegram 사용자]
      │ /start, /score, /signal, /me, /forget, /help
      ▼
┌─────────────────────────┐
│  Railway: sajucandle-bot │ (worker — python -m sajucandle.bot)
│  python-telegram-bot 21  │
└──────────┬──────────────┘
           │ httpx AsyncClient
           │ X-SAJUCANDLE-KEY
           ▼
┌─────────────────────────┐     ┌────────────────────────┐
│  Railway: sajucandle-api │────▶│  Upstash Redis         │
│  FastAPI + uvicorn       │     │  bazi:*, score:*,      │
│  Score + Signal Services │     │  signal:*, ohlcv:*     │
└──────────┬──────────────┘     └────────────────────────┘
           │ asyncpg Pool         ▲
           ▼                      │ 2-tier cache
┌─────────────────────────┐       │ (fresh 5min +
│  Supabase PostgreSQL     │      │  backup 24h)
│  users, user_bazi,         │      │
│  user_watchlist (W7)     │      │
└─────────────────────────┘       │
                                  │
                         ┌────────┴───────┐   ┌──────────────────────┐
                         │  Binance API   │   │  yfinance (PyPI)     │
                         │  /klines       │   │  AAPL/MSFT/GOOGL/    │
                         │  (BTCUSDT)     │   │  NVDA/TSLA 일봉      │
                         └────────────────┘   └──────────────────────┘
```

두 Railway 서비스는 같은 GitHub repo + 같은 Dockerfile + 같은 `REDIS_URL`을 공유한다. 봇은 API에 HTTP로만 접근하고 엔진/DB를 직접 건드리지 않는다.

---

## 로컬 개발

### 설치
```bash
python -m venv .venv
.venv/Scripts/activate  # Windows
# source .venv/bin/activate  # macOS/Linux
pip install -e ".[dev]"
```

### 테스트
```bash
pytest -v
```
Week 10 Phase 2 기준 **307 passed + 69 skipped** (DB 연결 없을 때). DB 테스트는 `TEST_DATABASE_URL` 환경변수 있을 때만 실행.

### 봇 로컬 실행
```bash
export BOT_TOKEN=...  # BotFather
# export REDIS_URL=rediss://...  # 선택 — 없으면 캐시 비활성
python -m sajucandle.bot
```

### API 로컬 실행
```bash
export SAJUCANDLE_API_KEY=local-dev-key
# export REDIS_URL=rediss://...  # 선택
python -m uvicorn sajucandle.api:app --host 127.0.0.1 --port 8000 --reload
```

테스트 호출:
```bash
curl http://127.0.0.1:8000/health
curl -X POST http://127.0.0.1:8000/v1/bazi \
  -H "Content-Type: application/json" \
  -H "X-SAJUCANDLE-KEY: local-dev-key" \
  -d '{"year":1990,"month":3,"day":15,"hour":14}'
```

자동 생성 OpenAPI 문서: http://127.0.0.1:8000/docs

---

## 배포 (Railway)

### 사전 준비
1. **Upstash Redis 생성** → `REDIS_URL` (rediss://...) 복사
2. **API 키 발급** → `openssl rand -hex 32` 로 `SAJUCANDLE_API_KEY` 생성

### 서비스 1: sajucandle-bot (기존)
- GitHub repo 연결
- Environment:
  - `BOT_TOKEN` = BotFather 토큰
  - `REDIS_URL` = Upstash URL
- Start Command (railway.toml 기본값): `python -m sajucandle.bot`

### 서비스 2: sajucandle-api (신규)
- 같은 GitHub repo에 새 서비스 추가
- Environment:
  - `SAJUCANDLE_API_KEY` = 위에서 생성한 키
  - `REDIS_URL` = Upstash URL (봇과 동일)
- Start Command Override: `python -m uvicorn sajucandle.api:app --host 0.0.0.0 --port $PORT`
- Networking → Generate Domain

### 헬스체크
```bash
curl https://<api-domain>.up.railway.app/health
```

---

## 프로젝트 구조

```
src/sajucandle/
├── bot.py              # Telegram 봇 엔트리 포인트
├── handlers.py         # /start /score /signal /me /forget /help 핸들러
├── api_client.py       # 봇 → API httpx 래퍼 (NotFoundError/ApiError)
├── format.py           # 명식 카드 텍스트 렌더러
├── saju_engine.py      # 명리 계산 엔진 (lunar_python)
├── cache.py            # Redis 캐시 래퍼
├── cached_engine.py    # SajuEngine + BaziCache
├── score_service.py    # 일일 점수 + KST 자정 TTL 캐시
├── tech_analysis.py    # RSI/SMA/volume_ratio → chart_score (순수 함수)
├── market_data.py      # Binance 클라이언트 + 2-tier OHLCV 캐시
├── market/             # Week 6: 멀티 자산 시장 데이터 (신규)
│   ├── base.py         #   MarketDataProvider Protocol + UnsupportedTicker
│   ├── yfinance.py     #   YFinanceClient (Redis 2단 캐시, fresh 1h / backup 24h)
│   └── router.py       #   MarketRouter.get_provider() / all_symbols()
├── signal_service.py   # saju 0.1 + analysis 0.9 결합 + TTL 5분 캐시 (Week 8 재설계)
├── analysis/           # Week 8~9: 시장 구조 + 멀티 타임프레임 + 수급 + S/R + SL/TP 엔진
│   ├── swing.py        #   Fractals + ATR prominence 필터 기반 swing high/low 감지
│   ├── structure.py    #   UPTREND/DOWNTREND/RANGE/BREAKOUT/BREAKDOWN 분류
│   ├── multi_timeframe.py #  1h/4h/1d 정렬 (Alignment + bias)
│   ├── timeframe.py    #   TrendDirection enum + 단일 TF 분석
│   ├── composite.py    #   analyze() 진입점 — 0.45*structure + 0.35*alignment + 0.10*rsi + 0.10*volume
│   ├── volume_profile.py # Week 9: VPVR 매물대 상위 N개 (VolumeProfile)
│   ├── support_resistance.py # Week 9: Swing + Volume 융합 → SRLevel
│   └── trade_setup.py  #   Week 9: 하이브리드 ATR + S/R snap SL/TP 제안
├── broadcast.py        # 데일리 푸시 CLI (Railway Cron에서 매일 07:00 KST 실행)
├── api.py              # FastAPI 앱 + 엔드포인트
├── api_main.py         # uvicorn 엔트리 (Railway PORT 읽기)
├── models.py           # Pydantic 요청/응답 모델
├── db.py               # asyncpg Pool 싱글톤
└── repositories.py     # users + user_bazi + signal_log CRUD

migrations/
├── 001_init.sql        # Supabase 초기 스키마
├── 002_watchlist.sql   # user_watchlist 테이블 (Week 7)
├── 003_signal_log.sql  # signal_log 테이블 + MFE/MAE 추적 컬럼 (Week 8)
└── 004_signal_log_sl_tp.sql  # SL/TP + R:R 컬럼 확장 (Week 9)

tests/
├── test_api.py / test_api_users.py / test_api_score.py / test_api_signal.py
├── test_api_admin.py / test_api_client.py
├── test_cache.py / test_cached_engine.py
├── test_db.py / test_repositories.py
├── test_format.py / test_handlers.py / test_score_service.py
├── test_tech_analysis.py / test_market_data.py / test_signal_service.py
├── test_market_base.py / test_market_yfinance.py / test_market_router.py  # Week 6
├── test_broadcast.py
├── test_analysis_volume_profile.py / test_analysis_support_resistance.py  # Week 9
├── test_analysis_trade_setup.py / test_api_ohlcv.py                       # Week 9
└── conftest.py         # db_pool, db_conn 롤백 fixture

docs/superpowers/
├── specs/              # 설계 문서 (v0.1 기획서, Week 3 design)
└── plans/              # 주차별 구현 플랜
```

---

## 봇 커맨드

| Command | 설명 |
|---------|------|
| `/start YYYY-MM-DD HH:MM` | 생년월일시 등록 (upsert) |
| `/score [swing\|scalp\|long]` | 오늘의 일진 점수 카드 |
| `/signal [심볼]` | **사주+차트 결합 신호** — BTC 기본, AAPL/MSFT/GOOGL/NVDA/TSLA 지원 (Week 6) |
| `/signal list` | 지원 심볼 목록 |
| `/watch <심볼>` | 관심 종목 추가 (최대 5개, Week 7) |
| `/unwatch <심볼>` | 관심 종목 제거 (Week 7) |
| `/watchlist` | 내 관심 종목 목록 (Week 7) |
| `/me` | 등록된 내 정보 |
| `/forget` | 내 정보 삭제 (멱등) |
| `/help` | 명령어 도움말 |

## API 엔드포인트

- `POST   /v1/bazi` — 명식 계산 (DB 불필요)
- `PUT    /v1/users/{chat_id}` — 프로필 upsert
- `GET    /v1/users/{chat_id}` — 조회 (없으면 404)
- `DELETE /v1/users/{chat_id}` — 삭제 (멱등, 204)
- `GET    /v1/users/{chat_id}/score?date=&asset=` — 일일 4축 + 종합 점수 + 추천 시진
- `GET    /v1/users/{chat_id}/signal?ticker=BTCUSDT&date=` — **사주 + 차트 결합 신호** (Week 4)
- `GET    /v1/admin/users` — 등록된 chat_id 리스트 (브로드캐스트용, Week 5)
- `GET    /v1/signal/symbols` — 지원 심볼 카탈로그 (인증 필요, Week 6)
- `GET    /v1/users/{chat_id}/watchlist` — 관심 종목 목록 (Week 7)
- `POST   /v1/users/{chat_id}/watchlist` — 관심 종목 추가 body: `{"ticker": "AAPL"}` (Week 7)
- `DELETE /v1/users/{chat_id}/watchlist/{ticker}` — 관심 종목 제거 (Week 7)
- `GET    /v1/admin/watchlist-symbols` — broadcast 전용 union (Week 7)

점수 응답은 `score:{chat_id}:{date}:{asset}` 키로 Redis에 캐싱되고, TTL은 **KST 자정까지** (최소 60초)이다.
신호 응답은 `signal:{chat_id}:{date}:{ticker}` 키로 TTL 5분 캐싱.

## Week 4 기능 (사주 + 차트 결합 신호)

`/signal` 커맨드는 사용자의 **오늘 사주 점수**와 **BTC 일봉 기술분석**을 합쳐 0~100점 종합 신호를 돌려준다.

- **차트 점수** (0~100) = `0.4 * RSI + 0.4 * MA + 0.2 * volume`
  - RSI(14): ≤30 과매도→70, ≤45→55, ≤55 중립→50, ≤70→40, >70 과매수→20
  - MA20 vs MA50: 교차 비율로 70/60/50/35 + trend(up/flat/down)
  - 거래량: 최근 5일 평균 / 이전 20일 평균 비율로 65/55/45/35
- **종합** = `round(0.4 * saju + 0.6 * chart)` → 75+ 강진입 / 60+ 진입 / 40+ 관망 / else 회피
- **2-tier OHLCV 캐시**: `ohlcv:*:fresh` TTL 5분 + `ohlcv:*:backup` TTL 24시간. Binance 장애 시 백업 폴백.
- **Week 4 한계**: 티커는 BTCUSDT 고정. 자산군 가중치 분기는 미구현.

## Week 5 기능 (데일리 푸시)

매일 **KST 07:00**에 등록된 사용자 전원에게 오늘의 사주 점수 카드를 자동 발송한다.

```
python -m sajucandle.broadcast [--dry-run] [--test-chat-id N] [--date YYYY-MM-DD]
```

- 필수 env: `BOT_TOKEN`, `SAJUCANDLE_API_BASE_URL`, `SAJUCANDLE_API_KEY`
- `--dry-run`: 전송 안 하고 포맷만 출력
- `--test-chat-id`: admin 리스트 무시, 특정 chat_id에만 발송 (스모크 테스트용)
- 실패 처리: 봇 차단(Forbidden) / 사용자 삭제(404) / 네트워크 에러 → 해당 건만 스킵, 나머지는 계속

### Railway Cron 서비스 (세 번째 서비스)
- Start Command: `python -m sajucandle.broadcast`
- Cron Schedule: `0 22 * * *` (UTC 22:00 = KST 07:00)
- Variables: `BOT_TOKEN`, `SAJUCANDLE_API_BASE_URL`, `SAJUCANDLE_API_KEY` (기존 서비스와 동일 값)

### DB 초기화
Supabase Studio → SQL Editor → `migrations/001_init.sql` 전체 붙여넣고 Run. `users`, `user_bazi` 두 테이블이 생긴다.

### 신규 환경변수
| 서비스 | 변수 | 예 |
|--------|------|-----|
| sajucandle-api | `DATABASE_URL` | `postgresql://postgres.<ref>:<pw>@aws-X-<region>.pooler.supabase.com:5432/postgres` |
| sajucandle-bot | `SAJUCANDLE_API_BASE_URL` | `https://sajucandle-api-production.up.railway.app` |
| sajucandle-bot | `SAJUCANDLE_API_KEY` | (API 서비스와 동일) |

`DATABASE_URL`이 없으면 API는 `/v1/users/*`, `/v1/users/{chat_id}/score`를 503으로 응답하고 `/health`의 `db` 필드가 `"down"`이 된다. `/v1/bazi`는 DB 없이 동작.

### 테스트 DB
통합 테스트(`test_repositories.py`, `test_api_users.py`, `test_api_score.py`)는 `TEST_DATABASE_URL`이 없으면 스킵된다. 실행 시:
```powershell
$env:TEST_DATABASE_URL = "postgresql://..."
pytest -v
```

## Week 6: 미국주식 /signal

yfinance 기반 미국주식 5종 지원. 휴장/주말에도 마지막 종가로 카드 생성.

### 지원 심볼
| 심볼 | 이름 | 카테고리 |
|------|------|----------|
| BTCUSDT | Bitcoin | crypto |
| AAPL | Apple | us_stock |
| MSFT | Microsoft | us_stock |
| GOOGL | Alphabet | us_stock |
| NVDA | NVIDIA | us_stock |
| TSLA | Tesla | us_stock |

### 명령어
- `/signal` — BTC (기본)
- `/signal AAPL` — 애플
- `/signal aapl` / `/signal $AAPL` — 대소문자/$ 무관 정규화
- `/signal list` — 지원 심볼 목록
- `/signal UNKNOWN` — "지원하지 않는 심볼" 안내

### 카드 포맷 (주식)

```
── 2026-04-17 AAPL ──
🕐 휴장 중 · 기준: 2026-04-16 종가
현재가: $184.12 (+1.23%)
────────────────
사주 점수:  56 (관망)
차트 점수:  72 (MA 우상향, RSI 62)
────────────────
종합:  66 | 진입
※ 정보 제공 목적. 투자 판단과 손실 책임은 본인에게 있습니다.
```

### 새 API 엔드포인트
- `GET /v1/signal/symbols` — 지원 심볼 카탈로그 (인증 필요)

### 아키텍처
- `src/sajucandle/market/` 패키지 신설
  - `base.py` — `MarketDataProvider` Protocol + `UnsupportedTicker`
  - `yfinance.py` — `YFinanceClient` (Redis 2단 캐시, fresh 1h / backup 24h)
  - `router.py` — `MarketRouter.get_provider(ticker)`, `MarketRouter.all_symbols()`
- `BinanceClient`에 `is_market_open` / `last_session_date` 추가 (24/7 trivial impl)
- `SignalResponse.market_status: MarketStatus` 필드 추가

### 범위 밖 (Week 7+)
- 사용자별 watchlist (`/watch AAPL`) → **Week 7에서 구현 완료**
- 모닝 푸시 카드에 watchlist 시그널 요약 → **Week 7에서 구현 완료**
- 국내주식 (KIS OpenAPI)
- 공휴일 정확 판별
- 프리마켓/애프터아워

---

## Week 7: Watchlist + 모닝 카드 통합

사용자별 관심 종목(최대 5개) 등록 + 매일 07:00 사주 카드 1통 + watchlist 시그널 요약 1통 발송.

### 새 명령어
- `/watch <심볼>` — 관심 종목 추가 (최대 5개)
- `/unwatch <심볼>` — 관심 종목 제거
- `/watchlist` — 내 관심 종목 목록

정규화 규칙은 `/signal`과 동일 (`upper + $제거`).

### Broadcast 흐름 (07:00 KST)

```
Phase 1: Precompute (admin chat으로 watchlist union 캐시 워밍)
Phase 2: 사주 카드 N통 (기존 Week 5 그대로, 회귀 0)
Phase 3: Watchlist 요약 (watchlist 있는 사용자에게만 1통씩)
```

Phase 1 실패해도 Phase 2/3 진행 (graceful). watchlist 비어있는 사용자는 Phase 3 skip → 기존처럼 1통만 받음.

### 새 API 엔드포인트
- `GET /v1/users/{chat_id}/watchlist`
- `POST /v1/users/{chat_id}/watchlist` body: `{"ticker": "AAPL"}`
- `DELETE /v1/users/{chat_id}/watchlist/{ticker}`
- `GET /v1/admin/watchlist-symbols` — broadcast 전용 union

### 에러 매트릭스 (API)

| 상황 | HTTP | detail |
|------|------|--------|
| 지원 안 하는 심볼 | 400 | `unsupported ticker: ...` |
| 이미 있음 | 409 | `already in watchlist` |
| 5개 가득 | 409 | `watchlist full (max 5)` |
| 없는 심볼 제거 | 404 | `not in watchlist` |
| 명식 미등록 | 404 | `user not found` |

### DB 스키마
새 테이블 `user_watchlist`. `migrations/002_watchlist.sql` 참조.

### CLI 플래그
```
python -m sajucandle.broadcast               # Phase 1+2+3 (기본)
python -m sajucandle.broadcast --skip-watchlist   # Phase 1+2 (Week 5 상태)
python -m sajucandle.broadcast --dry-run --test-chat-id N
```

### 새 환경변수
- `SAJUCANDLE_ADMIN_CHAT_ID` — Phase 1 precompute에 쓸 사용자 chat_id.
  - `sajucandle-broadcast` 서비스 Variables에만 추가.
  - 미설정 시 Phase 1 skip (Phase 2/3만 실행).

### 범위 밖 (Week 8+)
- KIS 국내주식
- 장중 실시간 강진입 알림
- 가격 breakout alert
- 시그널 적중률 로깅

---

## Week 8 Phase 1: 기술 분석 엔진 재설계

현재까지 RSI/MA/volume 3지표 일봉 단일 TF였던 `tech_analysis.py`를 **시장 구조 + 멀티 타임프레임 + 수급** 3축 프레임으로 재구성. 사주 가중치 0.4→0.1 강등, 모든 시그널 `signal_log` DB 기록 + MFE/MAE 7일 추적.

### 새 아키텍처

```
SignalService.compute(ticker)
  ├── ScoreService.compute()          # 사주 composite (가중치 0.1)
  └── analysis.composite.analyze()    # 가중치 0.9
       ├── swing.detect_swings()      # Fractals + ATR prominence 필터
       ├── structure.classify()       # UPTREND/DOWNTREND/RANGE/BREAKOUT/BREAKDOWN
       ├── multi_timeframe.compute()  # 1h/4h/1d 정렬
       └── rsi(1h) + volume(1d)       # 기존 tech_analysis 보조
```

### 가중치

```
composite = 0.45 * structure + 0.35 * alignment + 0.10 * rsi + 0.10 * volume
final = 0.1 * saju + 0.9 * analysis
```

### 강진입 조건 (3중 조건)

```
score >= 75
 + alignment.aligned = True
 + structure.state in (UPTREND, BREAKOUT)
```

### 새 카드 포맷

```
── 2026-04-19 AAPL ──
🟢 장 중
현재가: $184.12 (+1.23%)

구조: 상승추세 (HH-HL)
정렬: 1d↑ 4h↑ 1h↑  (강정렬)
진입조건: RSI(1h) 35 · 거래량 1.5x

종합:  72 | 진입
사주:  56 (😐 관망)

※ 정보 제공 목적. 투자 판단과 손실 책임은 본인에게 있습니다.
```

### 모닝 카드 톤 변경

- 제목: "사주캔들" → **"오늘의 명식 참고"**
- "종합: N | grade" → "성향: grade (변동성 주의 등)"
- CTA에 `/watchlist` 추가
- disclaimer: "엔터테인먼트 목적" → "정보 제공 목적"

### signal_log + MFE/MAE 추적

- 모든 `/signal` 호출 + broadcast 발송 시 DB 기록
- **Phase 0** (broadcast 07:00 크론 맨 앞): pending row의 MFE/MAE 업데이트
- 7일 경과 시 `tracking_done=TRUE`
- Week 11 백테스트 분석 원천 데이터

### 새 컬럼 (signal_log)

```sql
-- migrations/003_signal_log.sql
signal_log (
    id, sent_at, source, telegram_chat_id,
    ticker, target_date, entry_price,
    saju_score, analysis_score,
    structure_state, alignment_bias,
    rsi_1h, volume_ratio_1d,
    composite_score, signal_grade,
    mfe_7d_pct, mae_7d_pct,
    close_24h, close_7d,
    last_tracked_at, tracking_done
)
```

### 수동 단계 (Supabase)

Supabase Studio → SQL Editor → `migrations/003_signal_log.sql` 전체 붙여넣고 Run.

### 범위 밖 (Week 9~11)

- **Week 9:** 지지/저항 자동 식별, SL/TP 자동 제안, admin OHLCV 엔드포인트 → **완료 (Week 9 섹션 참조)**
- **Week 10:** 시그널 발송 거부 규칙 (BREAKDOWN에서 매수 차단), 카드 세밀 조정
- **Week 11:** MFE/MAE 통계 집계 API, 카드에 백테스트 프루프 노출, 등급 임계값 재조정

---

## Week 9 Phase 2: S/R + SL/TP + admin OHLCV

Week 8의 "왜 진입?"에서 Week 9는 **"어디에 진입/손절/익절?"**로 격상. 지지/저항 자동 식별 + 하이브리드 ATR·S/R SL/TP 제안.

### 새 분석 모듈
- `analysis/volume_profile.py` — VPVR 매물대 상위 N개
- `analysis/support_resistance.py` — Swing + Volume 융합 → SRLevel
- `analysis/trade_setup.py` — 하이브리드 ATR + S/R snap SL/TP

### 새 카드 포맷

**진입/강진입:**
```
구조: 상승추세 (HH-HL)
정렬: 1d↑ 4h↑ 1h↑  (강정렬)
진입조건: RSI(1h) 35 · 거래량 1.5x

세팅:
 진입 $184.12
 손절 $180.50 (-2.0%)
 익절1 $188.50 (+2.4%)  익절2 $193.00 (+4.8%)
 R:R 1.2 / 2.4   리스크 2.0%

종합: 72 | 진입
```

**관망/회피:**
```
주요 레벨:
 저항 $188.50 · $193.00 · $196.50
 지지 $180.50 · $177.00 · $172.00

종합: 48 | 관망
```

### 새 API 엔드포인트
- `GET /v1/admin/ohlcv?ticker=&interval=&since=&limit=` — Phase 0 tracking용 OHLCV 조회 (인증 필요)

### Phase 0 실데이터 연결
Week 8의 `_default_get_klines` skeleton이 admin OHLCV 호출로 교체되어 **signal_log의 MFE/MAE가 실제로 채워지기 시작**.

### signal_log 확장 컬럼 (migration 004)
`stop_loss`, `take_profit_1`, `take_profit_2`, `risk_pct`, `rr_tp1`, `rr_tp2`, `sl_basis`, `tp1_basis`, `tp2_basis`.

### 수동 단계 (Supabase)

Supabase Studio → SQL Editor → `migrations/004_signal_log_sl_tp.sql` 전체 붙여넣고 Run.

### 범위 밖 (Week 10~11)
- 시그널 발송 거부 규칙 (BREAKDOWN에서 매수 차단)
- MFE/MAE 통계 집계 API + 카드에 백테스트 프루프
- 튜닝 상수 최적화

---

## Week 10 Phase 1: 관측성 도구

signal_log 집계로 누적 상황 확인. 운영 중 `/stats` 한 번으로 진행상황 체크.

### 새 API
- `GET /v1/admin/signal-stats?ticker=&grade=&since=` — 집계 관측 (인증 필요)

### 새 봇 명령 (관리자만)
- `/stats` — 최근 30일 전체
- `/stats AAPL` — AAPL 30일
- `/stats AAPL 진입` — AAPL 진입 등급 30일

### 카드 예시
```
📊 신호 통계 (최근 30일)
─────────────
필터: 전체
총 발송: 42건

등급별:
  강진입  5건
  진입    12건
  관망    20건
  회피    5건

추적 완료: 15/42 (35%)

MFE/MAE 평균 (n=15):
  MFE  +2.8% (중앙 +2.3%)
  MAE  -1.4% (중앙 -1.1%)
```

### 권한
`SAJUCANDLE_ADMIN_CHAT_ID` env의 chat_id만 `/stats` 사용 가능. **bot 서비스 Variables에도 이 값 설정 필요** (broadcast 서비스에는 Week 7에서 이미 설정됨).

### Phase 2 (데이터 쌓인 후)
발송 거부 규칙 (BREAKDOWN 매수 차단), 카드 세밀 조정, 에러 메시지 개선.

---

## 주요 명령 정리

| 목적 | 명령 |
|------|------|
| 설치 | `pip install -e ".[dev]"` |
| 테스트 | `pytest -v` |
| 봇 실행 | `python -m sajucandle.bot` |
| API 실행 | `python -m uvicorn sajucandle.api:app --host 0.0.0.0 --port 8000` |
| 린트 | `ruff check .` |

## Week 10 Phase 2: 게이팅 + /guide + 에러 UX

운영 중 데이터 쌓이는 동안의 품질 다짐.

### 등급 게이팅 강화

`DOWNTREND` / `BREAKDOWN` 구조에서는 점수 60+여도 **"관망"으로 강등**. 구조가 뒷받침하는 장에서만 "진입" 등급 허용.

### 새 봇 명령: `/guide`

카드 해석법 (등급 4종 / 구조 5종 / 정렬 / 세팅 블록). 온보딩용. `/help`에도 노출.

### 에러 메시지 분리

| 상황 | 메시지 예시 |
|------|-------------|
| 타임아웃 | ⏱️ 서버 응답 지연. 잠시 후 다시. |
| 네트워크 | 🔌 네트워크 연결 실패. |
| 502 | 📉 시장 데이터 소스 일시 불가. 1~2분 후 재시도. |
| 503 | 🛠️ 일시 점검 중. |
| 5xx 기타 | ⚠️ 서버 오류 (N). 지속되면 관리자 문의. |

### 범위 밖 (Week 11+)

- 카드 세밀 조정 (이모지/정렬) — 실사용 피드백 기반
- 등급 임계값 재조정 — MFE/MAE 누적 후 Week 11 백테스트
- Rate limiting — 사용자 수 증가 후

---

## Phase 1: 백테스트 하네스

운영 시그널이 쌓이는 시간 없이 **과거 OHLCV로 analyze() + _grade_signal() 재생산**하고, 등급별 승률/MFE/MAE를 즉시 확인할 수 있는 인프라.

### 새 패키지
`src/sajucandle/backtest/` — 9개 모듈 (cli, history, slicer, engine, tracker, saju_stub, aggregate, ...).

### 새 명령
```
# 백테스트 실행 (결과는 signal_log에 source='backtest' + run_id로 저장)
python -m sajucandle.backtest run --ticker BTCUSDT --from 2024-04-01 --to 2026-04-01 --run-id phase1-7681adb-baseline

# 집계 결과 확인
python -m sajucandle.backtest aggregate --run-id phase1-7681adb-baseline
python -m sajucandle.backtest aggregate --run-id phase1-7681adb-baseline --json
```

### 출력 예시

```
Run: phase1-7681adb-baseline
grade        n    win%  avg_mfe  avg_mae  rr_tp1
------------------------------------------------
강진입      12    83.3   +4.20%   -1.80%    1.50
진입        48    58.3   +2.10%   -2.50%    1.40
관망       410    45.1   +1.20%   -2.00%      -
회피       150    30.0   +0.50%   -3.20%      -
```

### 새 SQL 컬럼 (migration 005)
`signal_log.run_id TEXT NULL` — 운영 signal은 NULL 유지.

### 서비스 코드 변경
- `repositories.insert_signal_log`: `run_id` Optional 파라미터 추가 (백테스트만 사용)
- `repositories.aggregate_signal_stats`: `run_id` 필터 — 기본 `run_id IS NULL`로 운영만 집계 (백테스트 오염 방지)
- `api.py::admin_signal_stats_endpoint`: `run_id` query param 전달

### Phase 2~4 활용
- Phase 2: 숏 대칭 구현 후 `phase2-long-only` vs `phase2-symmetric` run 비교
- Phase 3: RSI divergence 전/후 run 비교
- Phase 4: 가중치/임계값 grid 튜닝

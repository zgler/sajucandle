# Week 4: 사주 + 차트 결합 신호 Implementation Plan

**Goal:** 기존 `/score`(사주 4축)에 차트 기술 분석(RSI/MA/Volume)을 결합한 `/signal` 커맨드와 `/v1/users/{chat_id}/signal` 엔드포인트를 추가한다. 대상은 BTC/USDT 단일. 기존 기능 불변.

**Architecture:** 봇 `/signal` → api `SignalService.compute()` → (a) `ScoreService.compute()` (기존 사주 composite) + (b) `BinanceClient.fetch_klines()` + `tech_analysis.score_chart()`. 가중합 `0.4*saju + 0.6*chart` → 등급 4단계. Redis 2단 캐시 (fresh 5분, backup 24시간).

**Tech Stack:** 기존 의존성만 사용 (httpx, fastapi, redis, pydantic). 신규 패키지 0개. RSI/MA는 순수 stdlib 구현.

**Spec:** `docs/superpowers/specs/2026-04-16-week4-chart-signal-design.md`

**Out of scope:** 뉴스 감성, 백테스트, 복수 티커, 멀티 타임프레임, 가격 알림, pandas-ta 의존, Binance 인증 API.

---

## 사람이 직접 해야 하는 작업

없음. 전부 자동 배포. 환경변수 추가도 없음.

구현 후 smoke test만:
- Railway 재배포 완료 후 `/signal` 텔레그램에서 1회 호출 → 응답 형식 눈으로 확인

---

## File Structure 변경

```
src/sajucandle/
├── api.py              # MOD: /v1/users/{chat_id}/signal 엔드포인트 추가
├── api_client.py       # MOD: get_signal(chat_id, ticker) 추가
├── bot.py              # MOD: /signal CommandHandler 등록
├── handlers.py         # MOD: signal_command + /help 한 줄 추가
├── market_data.py      # NEW: BinanceClient + Kline + 2단 캐시
├── models.py           # MOD: SignalResponse + Price/Saju/Chart summary 모델
├── signal_service.py   # NEW: saju + chart 결합 + signal:* 캐시
└── tech_analysis.py    # NEW: rsi/sma/volume_ratio + score_chart

tests/
├── test_api_signal.py      # NEW: /v1/users/{chat_id}/signal 엔드포인트
├── test_handlers_signal.py # NEW: signal_command 유닛
├── test_market_data.py     # NEW: respx로 Binance mock + 2단 캐시
├── test_signal_service.py  # NEW: fake market + fake redis 통합
└── test_tech_analysis.py   # NEW: 순수 함수 fixture 기반
```

---

## Task 1: `tech_analysis.py` + 테스트

**Goal:** 순수 함수 RSI / MA / volume_ratio + `score_chart()`. 의존성 없음.

**Files:**
- [ ] `src/sajucandle/tech_analysis.py` (NEW)
- [ ] `tests/test_tech_analysis.py` (NEW)

**Steps:**

- [ ] `Kline` dataclass 정의 (`market_data.py`에서 재사용하게 일단 여기) — 또는 `tech_analysis.py`는 list[float]만 받고 Kline은 market_data에서. **후자 선택** (분리 명확).
- [ ] `rsi(closes: list[float], period: int = 14) -> float` — Wilder's smoothing. closes 길이 < period+1이면 `ValueError`.
- [ ] `sma(values: list[float], period: int) -> float` — 마지막 period개 평균. 길이 부족 시 `ValueError`.
- [ ] `volume_ratio(volumes: list[float], lookback: int = 20) -> float` — `volumes[-1] / mean(volumes[-lookback-1:-1])`. 길이 부족 시 `ValueError`.
- [ ] `ChartScoreBreakdown` dataclass: score(int), rsi_value, ma20, ma50, ma_trend("up"|"down"|"flat"), volume_ratio_value, reason(str).
- [ ] `score_chart(closes: list[float], volumes: list[float]) -> ChartScoreBreakdown`:
  - RSI→점수 테이블 (spec §3.2 A)
  - MA20/MA50 비교 → 점수 + trend (spec §3.2 B)
  - volume_ratio → 점수 (spec §3.2 C)
  - 가중합 `0.4*rsi + 0.4*ma + 0.2*vol`
  - reason: 세 축 요약 한국어 문자열 예 "RSI 58(중립), MA20>MA50, 볼륨↑"

**Tests (test_tech_analysis.py):**
- [ ] `test_rsi_known_sequence` — 고정 입력 예: 14일 동안 일정 증가 → RSI ≈ 100, 일정 감소 → RSI ≈ 0
- [ ] `test_rsi_insufficient_data_raises`
- [ ] `test_sma_simple` — `[1,2,3,4,5]` period=3 → 4.0
- [ ] `test_volume_ratio_spike` — 마지막 값이 평균의 2배 → 2.0 근사
- [ ] `test_score_chart_bullish` — RSI 35 + MA20>MA50*1.03 + volume_ratio 1.8 → score > 65, ma_trend="up"
- [ ] `test_score_chart_bearish` — RSI 75 + MA20<MA50 + volume_ratio 0.3 → score < 40, ma_trend="down"
- [ ] `test_score_chart_neutral` — RSI 50 + MA flat + volume_ratio 1.0 → score ≈ 50
- [ ] `test_chart_score_bounded_0_100` — 경계 케이스 여러 개 돌려서 0 ≤ score ≤ 100 보장

**Success Criteria:**
- [ ] 모든 테스트 통과 (pytest)
- [ ] ruff check 통과
- [ ] 외부 의존성 0 (stdlib + python-dev-essentials 만)

---

## Task 2: `market_data.py` + 테스트

**Goal:** Binance 공개 REST에서 OHLCV 받아오고 Redis 2단 캐시로 장애 대응.

**Files:**
- [ ] `src/sajucandle/market_data.py` (NEW)
- [ ] `tests/test_market_data.py` (NEW)

**Steps:**
- [ ] `Kline` dataclass: open_time(datetime), open/high/low/close(float), volume(float)
- [ ] `MarketDataUnavailable(Exception)` 커스텀 예외
- [ ] `BinanceClient`:
  - `__init__(http_client: httpx.Client | None = None, redis_client=None, timeout: float = 3.0)`
  - `fetch_klines(symbol: str, interval: str = "1d", limit: int = 100) -> list[Kline]`:
    1. `fresh_key = f"ohlcv:{symbol}:{interval}:fresh"` → Redis GET → hit 시 JSON deserialize → 반환
    2. miss → HTTP GET `https://api.binance.com/api/v3/klines` with params
       - 성공 → parse → Redis SETEX fresh(TTL=300) + backup(TTL=86400) → 반환
       - 실패 (timeout/HTTPError/ConnectError) → backup_key 조회
         - hit → 로그 WARN "using backup cache" → 반환
         - miss → raise MarketDataUnavailable
    3. Redis 자체가 None이면 캐시 단계 전부 skip, HTTP만. HTTP 실패 시 MarketDataUnavailable.
- [ ] JSON serialize/deserialize 헬퍼: Kline list ↔ list[list] (Binance 원본 포맷과 호환).

**Tests (respx 사용):**
- [ ] `test_fetch_klines_fresh_cache_hit` — fresh 키 미리 셋팅 → HTTP 호출 없이 반환
- [ ] `test_fetch_klines_http_and_cache_set` — respx mock 200 응답 → fresh + backup 둘 다 Redis에 있음
- [ ] `test_fetch_klines_http_fail_backup_hit` — respx 500 + backup 미리 셋팅 → backup 값 반환
- [ ] `test_fetch_klines_http_fail_and_no_backup_raises` — respx 500 + Redis 빈 상태 → `MarketDataUnavailable`
- [ ] `test_fetch_klines_no_redis_http_ok` — redis_client=None, respx 200 → 정상 반환
- [ ] `test_fetch_klines_no_redis_http_fail_raises` — redis_client=None, respx 500 → `MarketDataUnavailable`
- [ ] `test_kline_parse_binance_format` — Binance 원본 배열 1개 → Kline dataclass 필드 일치

**Success Criteria:**
- [ ] 전 테스트 통과, 실제 Binance 호출 0회
- [ ] ruff 통과
- [ ] 캐시 키 포맷이 spec §3.1과 일치 (`ohlcv:BTCUSDT:1d:fresh` / `:backup`)

---

## Task 3: `signal_service.py` + Pydantic 모델 + 테스트

**Goal:** `ScoreService` + `BinanceClient` + `score_chart` 오케스트레이션, Redis `signal:*` 캐시.

**Files:**
- [ ] `src/sajucandle/signal_service.py` (NEW)
- [ ] `src/sajucandle/models.py` (MOD — SignalResponse 등 추가)
- [ ] `tests/test_signal_service.py` (NEW)

**Steps:**
- [ ] `models.py`에 spec §7의 Pydantic 모델 추가: `PricePoint`, `SajuSummary`, `ChartSummary`, `SignalResponse`.
- [ ] `SignalService.__init__(score_service, market_client, redis_client=None)`.
- [ ] `_grade_signal(score: int) -> str` — 75/60/40 경계.
- [ ] `compute(profile: UserProfile, target_date: date, ticker: str) -> SignalResponse`:
  1. Redis `signal:{chat_id}:{date}:{ticker}` GET → hit 시 JSON → SignalResponse 반환
  2. `saju = score_service.compute(profile, target_date, profile.asset_class_pref)` (기존 호출, score:* 캐시 재사용)
  3. `klines = market_client.fetch_klines(ticker)`
  4. closes/volumes 추출
  5. `chart = score_chart(closes, volumes)`
  6. `current = klines[-1].close`, `change_pct = (klines[-1].close / klines[-2].close - 1) * 100`
  7. `final = round(0.4 * saju.composite_score + 0.6 * chart.score)`
  8. `grade = _grade_signal(final)`
  9. `SignalResponse` 조립 (best_hours는 saju 응답에서 복사)
  10. Redis SETEX `signal:{chat_id}:{date}:{ticker}` TTL=300 with `response.model_dump_json()`
  11. 반환

**Tests (fakeredis + fake objects):**
- [ ] `test_compute_basic_response_shape` — 고정 klines + 고정 사주 입력 → `composite_score` int, `signal_grade` 4단계 중 하나, `chart.reason` non-empty
- [ ] `test_compute_cache_hit_on_second_call` — 두 번 호출 → Redis `signal:*` 키 1개만, 두 호출 결과 동일
- [ ] `test_compute_cache_key_varies_by_ticker` — BTCUSDT와 ETHUSDT → 별도 키 (Week 4는 BTC만 허용하지만 서비스 레벨에선 구분해야)
- [ ] `test_compute_final_weighting` — saju=100, chart=0 → final≈40 (0.4). saju=0, chart=100 → final≈60. saju=50, chart=50 → final=50.
- [ ] `test_compute_without_redis_still_works` — redis_client=None → 계산은 되고 캐시 set 안 됨
- [ ] `test_compute_propagates_market_data_unavailable` — fake market_client.fetch_klines raises → SignalService도 그대로 전파 (엔드포인트에서 502로 변환)
- [ ] `test_grade_boundaries` — 75→강진입, 74→진입, 60→진입, 59→관망, 40→관망, 39→회피

**Success Criteria:**
- [ ] 전 테스트 통과
- [ ] ruff 통과
- [ ] cache 키 포맷 `signal:{chat_id}:{date}:{ticker}` 확인

---

## Task 4: `/v1/users/{chat_id}/signal` 엔드포인트 + 테스트

**Goal:** api.py에 엔드포인트 추가. 사용자 인증/프로필 조회는 기존 `/score` 엔드포인트 로직 재사용.

**Files:**
- [ ] `src/sajucandle/api.py` (MOD)
- [ ] `tests/test_api_signal.py` (NEW)

**Steps:**
- [ ] `create_app()` 안에 `SignalService` 인스턴스 생성 (engine, score_service, market_client 주입).
  - 모듈 로딩 시 1회. market_client는 `BinanceClient(http_client=httpx.Client(timeout=3.0), redis_client=redis_client)`.
- [ ] `@app.get("/v1/users/{chat_id}/signal")` 핸들러:
  - `_require_api_key`
  - `db.get_pool() is None` → 503
  - `ticker` 기본값 `"BTCUSDT"`, 다른 값이면 400 `"ticker must be BTCUSDT (Week 4 limit)"`
  - `date` 파싱 (기존 score 엔드포인트와 동일, None이면 오늘 KST)
  - `get_user` → None이면 404
  - `signal_service.compute(profile, date, ticker)` 호출
    - `MarketDataUnavailable` → 502 `"chart data unavailable"`
    - `Exception` → `logger.exception` + 400 `"신호 계산 실패: {type}"`
  - INFO 로그: `signal ok chat_id=... ticker=... composite=... grade=... chart=... saju=... elapsed_ms=...`
  - 응답 반환

**Tests (fakeredis + monkeypatch로 BinanceClient.fetch_klines 치환):**
- [ ] `test_signal_requires_api_key` — 헤더 없으면 401
- [ ] `test_signal_invalid_ticker_400` — `?ticker=ETHUSDT` → 400
- [ ] `test_signal_db_unavailable_503` — DB 없이 create_app → 503
- [ ] `test_signal_user_not_found_404`
- [ ] `test_signal_success` — 등록된 사용자 + mock klines → 200 + SignalResponse 필드 검증
- [ ] `test_signal_market_unavailable_502` — fake market raises MarketDataUnavailable → 502
- [ ] `test_signal_cache_hit_on_second_call` — 두 번 호출 → Binance mock 1회만 호출됨 (score:* 도 1회)

**Success Criteria:**
- [ ] 전 테스트 통과
- [ ] ruff 통과
- [ ] 기존 테스트 전부 회귀 통과

---

## Task 5: `api_client.get_signal()` + `handlers.signal_command` + 테스트

**Goal:** 봇 쪽 wrapper 추가. 기존 `get_score`와 동일한 에러 처리 패턴 재사용.

**Files:**
- [ ] `src/sajucandle/api_client.py` (MOD)
- [ ] `src/sajucandle/handlers.py` (MOD)
- [ ] `tests/test_api_client.py` (MOD — signal 케이스 추가)
- [ ] `tests/test_handlers_signal.py` (NEW)

**Steps:**
- [ ] `ApiClient.get_signal(chat_id: int, ticker: str = "BTCUSDT") -> dict`:
  - `GET /v1/users/{chat_id}/signal?ticker={ticker}`
  - 404 → NotFoundError / 502 → ApiError(502, "chart data unavailable") / 기타 non-2xx → ApiError
- [ ] `handlers.signal_command(update, context)`:
  - `chat_id = update.effective_chat.id`
  - `data = await _api_client.get_signal(chat_id)`
  - 예외: NotFoundError(등록 안내), TimeoutException, TransportError, ApiError(502 "시장 데이터 일시 불능. 잠시 후.", 기타 "서버 오류 ({status})"), Exception(logger.exception)
  - 출력 포맷 (spec §5.1):
    ```
    ── 2026-04-16 BTC/USDT ──
    현재가: $67,432 (+2.1%)
    ────────────────
    사주 점수: 55 (관망)
    차트 점수: 72 (RSI 58, MA20>MA50, 볼륨↑)
    ────────────────
    종합: 65 | 진입
    추천 시진: 寅시 03:00-05:00

    ※ 엔터테인먼트 목적. 투자 추천 아님.
    ```
  - best_hours 없으면 해당 줄 생략.
- [ ] INFO 로그: `signal ok chat_id=... ticker=...`

**Tests:**
- [ ] `test_api_client.py`: `test_get_signal_success`, `test_get_signal_404`, `test_get_signal_502`
- [ ] `test_handlers_signal.py` (fake api_client monkeypatch 방식, 기존 test_handlers 패턴):
  - `test_signal_command_success` — 응답 문자열에 "BTC/USDT", "종합:", 등급 포함
  - `test_signal_command_not_registered`
  - `test_signal_command_market_unavailable` — ApiError(502) → "시장 데이터 일시 불능"
  - `test_signal_command_generic_api_error` — ApiError(500) → "서버 오류 (500)"
  - `test_signal_command_timeout`

**Success Criteria:**
- [ ] 모든 테스트 통과
- [ ] ruff 통과

---

## Task 6: `bot.py` 등록 + `/help` 업데이트

**Goal:** `/signal` 커맨드를 봇에 연결.

**Files:**
- [ ] `src/sajucandle/bot.py` (MOD)
- [ ] `src/sajucandle/handlers.py` (MOD — `/help` 한 줄)

**Steps:**
- [ ] `bot.py`: `from sajucandle.handlers import ... signal_command` 추가, `app.add_handler(CommandHandler("signal", signal_command))` 추가
- [ ] `handlers.help_command`: 메시지에 `/signal — BTC 사주+차트 결합 신호` 한 줄 삽입

**Tests:**
- [ ] 기존 test_handlers.test_help 업데이트 — `/signal` 문자열 포함 assert

**Success Criteria:**
- [ ] 기존 test_handlers 전부 통과 (help 문자열만 변경)
- [ ] 봇 로컬 실행 → `/help`에 /signal 줄 보임

---

## Task 7: 전체 린트/테스트/README/커밋/푸시/smoke

**Goal:** Week 4 끝.

**Files:**
- [ ] `README.md` (MOD)

**Steps:**
- [ ] `pytest -v` — 전 테스트 통과 (TEST_DATABASE_URL 없으면 DB 테스트 스킵, 있으면 전부 통과)
- [ ] `ruff check .` — 클린
- [ ] README:
  - 아키텍처 다이어그램에 "Binance public API" 노드 추가
  - 봇 커맨드 표에 `/signal` 추가
  - 엔드포인트 리스트에 `GET /v1/users/{chat_id}/signal` 추가
  - "Week 4 기능 (차트 결합 신호)" 섹션 신설
  - 테스트 카운트 업데이트
- [ ] `git add . && git commit -m "feat(week4): chart signal combining saju + BTC technical analysis"`
- [ ] `git push origin main`
- [ ] Railway 재배포 완료 대기 (~3분)
- [ ] curl smoke:
  ```
  curl "https://sajucandle-api-production.up.railway.app/v1/users/<본인chat_id>/signal" \
    -H "X-SAJUCANDLE-KEY: $KEY"
  ```
- [ ] 텔레그램에서 `/signal` → 응답 형식 확인

**Success Criteria:**
- [ ] 전 테스트 통과 (Week 3 + Week 4)
- [ ] Railway 배포 성공
- [ ] curl 응답에 `ticker`, `saju`, `chart`, `composite_score`, `signal_grade` 필드 전부 존재
- [ ] 텔레그램 `/signal` 응답 한국어 카드 정상

---

## Rollback 시나리오

문제 발생 시:
1. `bot.py`에서 `app.add_handler(CommandHandler("signal", signal_command))` 한 줄 주석 → 재배포 → `/signal` 비활성화
2. 그래도 api `/v1/users/{chat_id}/signal`은 남아있지만 아무도 호출 안 함
3. 더 급하면 `git revert <commit>` → push → 원복

기존 `/score`, `/start`, `/me`, `/forget`, `/help` 전부 불변이므로 Week 3 기능은 영향 없음.

# Week 7 설계 — Watchlist + 모닝 카드 통합

- 날짜: 2026-04-17
- 대상 주차: Week 7
- 상태: Draft (brainstorming 합의 완료, 사용자 리뷰 대기)

## 1. 목적

현재 07:00 모닝 푸시는 사주 4축 점수만 발송. 사용자(본인 + 트레이더 친구들)의 실제 니즈는 "내 관심 종목이 오늘 맞는지"다. `/watch AAPL` 형태로 최대 5개 심볼을 등록하고, 매일 아침 사주 카드 + 관심 종목 시그널 요약이 함께 발송되는 것이 Week 7의 목표.

KIS 국내주식(Week 8+)과 결제/유료 전환은 범위 밖. 기존 Week 5 broadcast 동작은 회귀 없음.

## 2. 목표 / 범위

### 포함
- 사용자별 watchlist (최대 5개)
- 봇 명령어 `/watch`, `/unwatch`, `/watchlist`
- API 엔드포인트 4개 (목록 / 추가 / 제거 / admin union)
- Broadcast 흐름 개편: Phase 1 Precompute → Phase 2 기존 사주 카드 → Phase 3 Watchlist 요약
- Watchlist 요약 카드 포맷 (장/휴장 아이콘 포함)
- BroadcastSummary 확장 + 새 CLI 플래그 `--skip-watchlist`

### 범위 밖 (Week 8+)
- 장중 실시간 알림 (강진입 시 즉시 push)
- watchlist 가격 breakout alert
- watchlist 순서 재배열 / 드래그 정렬
- asset_class_pref에 따른 watchlist 가중치 개인화
- KIS 국내주식 (Week 8+)

## 3. 설계 결정 (brainstorming 요약)

| # | 주제 | 결정 | 근거 |
|---|------|------|------|
| Q1 | 개수 제한 | **5개** | 모닝 카드 가독성, 07:00 push 속도 보장, YAGNI |
| Q2 | 모닝 카드 통합 | **사주 1통 + watchlist 1통** | 기존 사주 카드 회귀 0, 알림 2번만 |
| Q3 | 시그널 계산 방식 | **Broadcast 내장 Precompute** | Railway 서비스 증설 불필요, 현재 규모 충분 |

## 4. 데이터 모델

### 4.1 DB 스키마

```sql
CREATE TABLE IF NOT EXISTS user_watchlist (
    telegram_chat_id BIGINT NOT NULL
        REFERENCES user_bazi(telegram_chat_id) ON DELETE CASCADE,
    ticker TEXT NOT NULL,
    added_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (telegram_chat_id, ticker)
);

CREATE INDEX IF NOT EXISTS idx_user_watchlist_chat_id
    ON user_watchlist(telegram_chat_id);
```

- PK 복합키로 DB 레벨 중복 방지
- ON DELETE CASCADE로 `/forget` 시 자동 정리
- ticker 제약은 앱 레벨(MarketRouter 화이트리스트)에서만 검증 — Week 7+ 심볼 추가 시 스키마 변경 불필요

### 4.2 Repository 레이어 (`repositories.py`)

```python
@dataclass
class WatchlistEntry:
    ticker: str
    added_at: datetime

async def list_watchlist(conn, chat_id: int) -> list[WatchlistEntry]:
    """added_at ASC. 비어있으면 []."""

async def add_to_watchlist(conn, chat_id: int, ticker: str) -> None:
    """INSERT. 중복(PK 충돌)은 asyncpg.UniqueViolationError 전파."""

async def remove_from_watchlist(conn, chat_id: int, ticker: str) -> bool:
    """DELETE. True=삭제됨, False=애초에 없었음."""

async def count_watchlist(conn, chat_id: int) -> int:
    """현재 등록된 심볼 개수. 5개 제한 검증용."""

async def list_all_watchlist_tickers(conn) -> set[str]:
    """모든 사용자 watchlist의 ticker union (중복 제거). broadcast precompute용."""
```

## 5. API 표면

### 5.1 엔드포인트

| 메서드 | 경로 | 인증 | 응답 |
|--------|------|------|------|
| `GET` | `/v1/users/{chat_id}/watchlist` | X-SAJUCANDLE-KEY | `{"items":[{"ticker":"AAPL","added_at":"..."}, ...]}` |
| `POST` | `/v1/users/{chat_id}/watchlist` | X-SAJUCANDLE-KEY | `204 No Content` (성공), 4xx (실패) |
| `DELETE` | `/v1/users/{chat_id}/watchlist/{ticker}` | X-SAJUCANDLE-KEY | `204 No Content` |
| `GET` | `/v1/admin/watchlist-symbols` | X-SAJUCANDLE-KEY | `{"symbols":["AAPL","TSLA",...]}` |

POST body: `{"ticker": "AAPL"}`.

### 5.2 에러 매트릭스

| 시나리오 | HTTP | detail |
|----------|------|--------|
| 지원 안 하는 심볼 추가 | 400 | `"unsupported ticker: XYZ"` |
| 이미 있는 심볼 추가 | 409 | `"already in watchlist"` |
| 5개 가득 상태에서 추가 | 409 | `"watchlist full (max 5)"` |
| 없는 심볼 제거 | 404 | `"not in watchlist"` |
| 명식 미등록 (FK 실패) | 404 | `"user not found"` |
| 인증 실패 | 401 | `"invalid or missing API key"` |

5개 제한과 중복 모두 409인 이유: 둘 다 "리소스 상태 때문에 충돌"이라 의미적으로 같은 카테고리. 봇 핸들러가 detail로 두 케이스 구분.

## 6. 봇 명령어

### 6.1 문법

```
/watch AAPL         → 추가
/watch aapl         → AAPL (upper 정규화)
/watch $AAPL        → AAPL ($ 제거)
/unwatch AAPL       → 제거
/watchlist          → 본인 목록 표시
```

인자 정규화는 `/signal`과 동일 (`upper().lstrip("$")`).

### 6.2 응답 포맷

**`/watch AAPL` 성공:**
```
✅ AAPL (Apple) 관심 종목 추가 완료.
현재 3/5개. /watchlist 로 전체 확인.
```
(심볼 이름은 `MarketRouter.all_symbols()` 조회해서 매핑)

**`/watch AAPL` 실패:**
| 상황 | 응답 |
|------|------|
| 이미 있음 (409, detail=already) | `이미 관심 종목에 있습니다: AAPL` |
| 5개 가득 (409, detail=full) | `관심 종목은 최대 5개입니다. /watchlist 에서 제거 후 다시 시도.` |
| 지원 안함 (400) | `지원하지 않는 심볼: XYZ. /signal list 로 확인.` |
| 명식 미등록 (404) | `먼저 생년월일을 등록하세요. 예: /start 1990-03-15 14:00` |
| 인자 없음 | `사용법: /watch <심볼>\n예: /watch AAPL` |

**`/unwatch AAPL` 성공:**
```
🗑️ AAPL 관심 종목에서 제거했습니다.
```

**`/unwatch AAPL` 실패:**
| 상황 | 응답 |
|------|------|
| 없음 (404) | `관심 종목에 없습니다: AAPL` |
| 인자 없음 | `사용법: /unwatch <심볼>` |

**`/watchlist` 빈 경우:**
```
관심 종목이 비어있습니다.
/watch AAPL 로 추가하세요.
/signal list 로 지원 심볼 확인.
```

**`/watchlist` 채워진 경우:**
```
📊 관심 종목 (3/5)
─────────────
1. BTCUSDT — Bitcoin (2026-04-15 추가)
2. AAPL — Apple (2026-04-16 추가)
3. TSLA — Tesla (2026-04-17 추가)

/unwatch <심볼> 로 제거
매일 07:00 자동 시그널 발송됩니다.
```

### 6.3 `/help` 업데이트

```
/start YYYY-MM-DD HH:MM — 생년월일시 등록
/score [swing|scalp|long] — 오늘 사주 점수
/signal [심볼] — 사주+차트 결합 신호
  · 지원: BTCUSDT, AAPL, MSFT, GOOGL, NVDA, TSLA
  · /signal list — 전체 목록
/watch <심볼> — 관심 종목 추가 (최대 5개)
/unwatch <심볼> — 관심 종목 제거
/watchlist — 내 관심 종목 + 매일 07:00 자동 시그널
/me — 등록된 정보 확인
/forget — 내 정보 삭제
/help — 이 도움말
```

### 6.4 `ApiClient` 확장

```python
async def get_watchlist(self, chat_id: int) -> list[dict]:
    """GET. 반환: [{ticker, added_at}, ...]"""

async def add_watchlist(self, chat_id: int, ticker: str) -> None:
    """POST body={ticker}. 204 or raise ApiError."""

async def remove_watchlist(self, chat_id: int, ticker: str) -> None:
    """DELETE. 204 or raise ApiError."""

async def get_admin_watchlist_symbols(self) -> list[str]:
    """GET /v1/admin/watchlist-symbols. broadcast 전용."""
```

`ApiError.status + detail` 분기로 봇 핸들러가 적절한 사용자 메시지 생성.

## 7. Broadcast 통합

### 7.1 새 흐름

```
[Phase 1: Precompute — best effort]
  admin_chat = SAJUCANDLE_ADMIN_CHAT_ID (env)
  symbols = GET /v1/admin/watchlist-symbols  → union set
  for ticker in symbols:
    try: GET /v1/users/{admin_chat}/signal?ticker=X  (Redis 캐시 워밍)
    except: warning 로그, 다음 심볼 진행
  precompute_ok / precompute_failed 카운트

[Phase 2: 기존 사주 카드 — Week 5 회귀 0]
  chat_ids = GET /v1/admin/users
  for chat_id in chat_ids:
    GET /score → format_morning_card → send_message
    (기존 Week 5 로직 그대로)

[Phase 3: Watchlist 요약 — 신규]
  if CLI flag --skip-watchlist: skip
  for chat_id in chat_ids:
    items = GET /v1/users/{chat_id}/watchlist
    if not items:
      watchlist_skipped_empty += 1
      continue
    signals = []
    for item in items:
      try: sig = GET /v1/users/{chat_id}/signal?ticker=item.ticker (캐시 히트 예상)
           signals.append(sig)
      except: signals.append({"ticker": item.ticker, "error": "데이터 불가"})
    card = format_watchlist_summary(signals, target_date)
    send_message(chat_id, card)
    watchlist_sent += 1
```

**포인트:**
- Phase 1이 완전 실패해도 Phase 2/3 진행 (Phase 3에서 캐시 미스 → 순차 계산으로 fallback, 느려질 뿐)
- Phase 2는 Week 5 코드 **그대로** — 기존 함수 수정 금지
- Phase 3에서 watchlist 비어있는 사용자 skip (정상 케이스, not an error)
- `SAJUCANDLE_ADMIN_CHAT_ID` env 미설정 시 Phase 1 skip, Phase 2/3만 실행

### 7.2 Watchlist 요약 카드 포맷

```
📊 2026-04-17 (금) 관심 종목
─────────────
[BTC]   72 진입   $72,120.00  (+1.5%)
[AAPL]  65 진입   $184.12     (+1.2%)  🕐
[TSLA]  45 관망   $215.00     (-2.3%)  🕐

상세: /signal AAPL
※ 엔터테인먼트 목적. 투자 추천 아님.
```

**열 규칙:**
- 티커 열: `[{ticker}]` 최대 8자 (BTCUSDT는 `[BTC]`로 축약 — `ticker.rstrip("USDT") if ticker.endswith("USDT") else ticker`)
- 점수 열: 우정렬 3자리 `{:>3}`
- 등급 열: 진입/관망/회피
- 가격 열: `${current:,.2f}` 우정렬 12자
- 변동 열: `(+1.23%)` (부호 명시)
- 휴장 아이콘: `market_status.is_open==False and category=="us_stock"`일 때만 `🕐`

**실패 심볼:**
```
[XYZ]  데이터 불가
```

**순서:** watchlist added_at ASC (추가 순).

### 7.3 BroadcastSummary 확장

```python
@dataclass
class BroadcastSummary:
    # 기존
    sent: int = 0
    failed: int = 0
    blocked: int = 0
    not_found: int = 0
    bad_request: int = 0
    # 신규
    watchlist_sent: int = 0
    watchlist_skipped_empty: int = 0
    watchlist_failed: int = 0
    precompute_ok: int = 0
    precompute_failed: int = 0

    def total(self) -> int:
        return self.sent + self.failed + self.blocked + self.not_found + self.bad_request
```

로그 라인:
```
broadcast done date=2026-04-17 sent=15 failed=0 blocked=0 not_found=0 bad_request=0
  watchlist_sent=8 watchlist_skipped_empty=7 watchlist_failed=0
  precompute_ok=5/6 (failed=1)
```

### 7.4 CLI 플래그

```
python -m sajucandle.broadcast                       # 기본: Phase 1+2+3
python -m sajucandle.broadcast --skip-watchlist      # Phase 1+2만 (Week 5 상태)
python -m sajucandle.broadcast --dry-run             # 전 Phase 실행하되 전송 skip
python -m sajucandle.broadcast --test-chat-id N      # admin list 대신 N만 대상
python -m sajucandle.broadcast --date YYYY-MM-DD     # 특정 날짜 기준 (기존)
```

조합 허용. 예: `--dry-run --test-chat-id 7492682272` → 본인 기준 Phase 1+2+3 dry-run.

### 7.5 새 환경변수

`sajucandle-broadcast` Railway 서비스 Variables에 추가:
- `SAJUCANDLE_ADMIN_CHAT_ID` — Phase 1 precompute에 쓸 사용자 chat_id (본인, 예: `7492682272`)
  - 미설정 시 Phase 1 skip, Phase 2/3만 실행
  - `bot`, `api` 서비스에는 불필요

## 8. 테스트 전략

| 파일 | 커버리지 |
|------|----------|
| `tests/test_repositories.py` (수정) | list/add/remove/count/list_all_watchlist_tickers CRUD (DB 통합, TEST_DATABASE_URL 있을 때만) |
| `tests/test_api_watchlist.py` (신규) | 엔드포인트 4개, 모든 에러 케이스 (400/404/409) |
| `tests/test_api_client.py` (수정) | 3개 새 메서드 respx mock (200/400/404/409) |
| `tests/test_handlers.py` (수정) | `/watch AAPL`, `/watch aapl`, `/watch $AAPL`, `/watch UNKNOWN`, `/watch` 빈 인자, `/watch` 5개 가득, `/unwatch AAPL`, `/unwatch UNKNOWN`, `/watchlist` 빈/채움, /help |
| `tests/test_broadcast.py` (수정) | precompute 성공/실패, watchlist 요약 성공/빈 사용자 skip/일부 시그널 실패, `--skip-watchlist` 플래그, format_watchlist_summary 단위 |

## 9. 관측성

- `logger.info("watchlist added chat_id=%s ticker=%s count=%s/5", ...)`
- `logger.info("watchlist removed chat_id=%s ticker=%s", ...)`
- `logger.warning("broadcast precompute failed ticker=%s: %s", ...)` — Phase 1
- `logger.info("watchlist summary sent chat_id=%s count=%s", ...)` — Phase 3

## 10. 배포

1. Railway PostgreSQL: `user_watchlist` 테이블 생성 — `db.py` lifespan의 CREATE TABLE IF NOT EXISTS에 추가. 기존 Week 2 패턴 재사용.
2. `sajucandle-broadcast` Variables에 `SAJUCANDLE_ADMIN_CHAT_ID=7492682272` 추가 (본인 chat_id).
3. 코드 push → Railway 3 서비스 자동 재배포.
4. 로컬 스모크: `pytest`, 실기 봇 테스트 (`/watch AAPL` → `/watchlist` → `/unwatch AAPL`).
5. 운영 스모크: `sajucandle-broadcast` 수동 트리거 (임시 cron으로) → 본인 폰에 2통(사주 카드 + watchlist 요약) 도착 확인.

## 11. 위험과 대응

| 위험 | 대응 |
|------|------|
| Phase 1 실패 시 Phase 3 느림 | graceful degradation. 캐시 미스라 그냥 순차 계산 → 결국 성공. |
| 사용자가 5개 이하로 등록하는데 일부만 지원 안 하는 심볼이면? | `/watch`에서 추가 시점 검증 (400) — 이미 들어간 심볼은 DB에 존재하므로 broadcast 시 계산은 성공 |
| Phase 1에서 `admin_chat`의 /score가 DB 접근 필요 | admin 계정도 정상 등록된 사용자여야 함. 미등록 시 Phase 1 skip (404 catch) |
| 5개 제한 우회 가능? | API 레벨 검증 (count < 5). race condition은 PK 충돌로 보호되지 않음 — 트랜잭션 내 count + insert로 처리 |
| 카드 너무 길어서 모바일 가독성 ↓ | 5개 제한 + 1줄 요약 + 고정폭 정렬 → OK 예상 |
| BTCUSDT 티커 표시 `[BTC]` 축약 로직 | 단순 `.rstrip("USDT")` — 현재 BTCUSDT만 이 패턴. 향후 ETHUSDT 추가 시 일관됨 |

## 12. 완료 기준

- [ ] `user_watchlist` 테이블 생성 + repositories CRUD
- [ ] 엔드포인트 4개 + 모든 에러 매트릭스 테스트 통과
- [ ] `/watch`, `/unwatch`, `/watchlist` + 정규화 + 실패 분기 모두 통과
- [ ] `/help` 갱신
- [ ] broadcast: Phase 1 Precompute + Phase 3 Watchlist 요약 동작, Phase 2 회귀 0
- [ ] `--skip-watchlist` 플래그 + `SAJUCANDLE_ADMIN_CHAT_ID` env 처리
- [ ] 로컬 pytest 전량 통과 (기존 164 + 신규 ~30)
- [ ] Railway 배포 후 본인 텔레그램에 2통(사주 + watchlist) 도착 확인
- [ ] watchlist 비어있는 상태에서 1통(사주)만 도착 확인

## 13. 이후 과제 (Week 8+)

- KIS OpenAPI → 국내주식 (승인 후)
- 장중 실시간 강진입 알림
- watchlist 가격 breakout alert
- 시그널 적중률 로그 적재 (Week 9 후보)
- 결제/유료 전환 (사용자 10+ 확보 후)

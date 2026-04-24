# Week 5 설계 — 데일리 푸시 알림

**Date**: 2026-04-16
**Status**: approved
**Context**: Week 1~4에서 `/start /score /signal` pull 기반 MVP 완성. 사용자가 **매일 앱을 열 이유**가 없으면 리텐션이 안 나온다. 기획서 v0.1 §2.6 "데일리 푸시" 구현.

## 목표

매일 **KST 07:00**에 등록된 사용자 전원에게 오늘의 사주 점수 카드를 자동 발송.

## 비목표 (Week 5)

- 시진 알림 (개별 시간대별 푸시) — 기획서 §2.6 두 번째 항목. P1.
- 사용자별 알림 시간/ON-OFF 토글 UI — 불편 생기면 추가.
- BTC 신호 동시 푸시 — 카드 2장 되면 스팸 느낌. /score만, /signal 안내만 한 줄.
- 다국어, 다타임존.

## 아키텍처

```
┌──────────────────────────┐
│  Railway: sajucandle-    │  Cron: 0 22 * * * (UTC = 07:00 KST)
│  broadcast (cron mode)   │  startCommand: python -m sajucandle.broadcast
│  1회 실행 후 종료         │
└────────────┬─────────────┘
             │ 1. GET /v1/admin/users
             │ 2. per chat_id: GET /v1/users/{id}/score
             ▼
┌──────────────────────────┐
│  sajucandle-api (기존)    │
└────────────┬─────────────┘
             │ (기존 경로)
             ▼
  Supabase + Redis + Binance
             
┌──────────────────────────┐
│  Telegram Bot API         │◀── broadcast가 직접 send_message
└──────────────────────────┘
```

**왜 Railway Cron (별도 서비스)인가?**
- APScheduler를 기존 봇에 넣으면 봇 프로세스 죽었을 때 푸시도 같이 죽음.
- Cron은 1회성, 5~10초, 실패 독립 관측.
- 같은 repo/Dockerfile 재사용 → 추가 빌드 비용 0.

**왜 /v1/admin/users 신설인가?**
- 브로드캐스트는 user 리스트가 필요한데, 봇/broadcast에서 직접 DB 접근은 안 함 (Week 3 원칙: 엔진/DB는 API 뒤).
- 기존 API 키 `X-SAJUCANDLE-KEY`로 같은 인증 모델 유지.

## API 변경

### 신규: `GET /v1/admin/users`

- **인증**: `X-SAJUCANDLE-KEY`
- **응답** 200: `{"chat_ids": [12345, 67890, ...]}`
- **503**: DB 미연결

반환 순서 보장 X. 페이지네이션 X (수천명까지는 한 번에 돌려도 됨; 10만+ 되면 `?limit=&offset=` 추가).

## 모듈 설계

### `src/sajucandle/broadcast.py` (신규)

```
python -m sajucandle.broadcast [옵션]
```

**옵션**:
- `--dry-run` : 전송 안 하고 출력만
- `--test-chat-id INT` : admin 리스트 무시하고 이 chat_id 하나에만 보냄 (개인 스모크용)
- `--date YYYY-MM-DD` : 점수 산출 기준 날짜 override (기본: KST 오늘)

**환경 변수** (전부 필수, 없으면 에러 후 exit 1):
- `BOT_TOKEN` — Telegram 봇 토큰
- `SAJUCANDLE_API_BASE_URL`
- `SAJUCANDLE_API_KEY`

**동작 순서**:
1. env 검증
2. `api_client.get_admin_users()` → chat_ids (또는 `--test-chat-id` 하나)
3. 각 chat_id 순회:
    a. `api_client.get_score(chat_id)` — asset는 전달 안 함 → 서버가 `asset_class_pref` 사용
    b. 카드 포맷팅 (`format_morning_card(score_data)`)
    c. `telegram.Bot.send_message(chat_id, text)` (HTML 금지, 순수 텍스트)
    d. 50ms sleep (rate limit)
    e. 예외별 처리:
       - `telegram.error.Forbidden` (사용자 봇 차단) → INFO 로그, 스킵
       - `telegram.error.BadRequest` (chat not found 등) → WARNING, 스킵
       - `api_client.NotFoundError` (사용자 등록 삭제됨) → INFO, 스킵
       - 기타 `ApiError` / `httpx.*` → WARNING, 스킵
4. 요약: `sent=N failed=M blocked=K` INFO 로그 → stdout

### 카드 포맷

```
☀️ 2026-04-16 (목) 사주캔들
── 己未 [swing] ──
재물운:  50  | 재성 신호 없음
결단운:  82  | 비견+삼합
충돌운:  50  | 형충 없음
합  운:  70  | 삼합 2자
────────────
종합:  64  | 🔄 관망
추천 시진: 巳시 09:00~11:00

오늘 BTC는 /signal 로 확인하세요.
```

요일은 stdlib `["월","화","수","목","금","토","일"][weekday()]`.

### `api_client.py` 확장

```python
async def get_admin_users(self) -> list[int]:
    ...
```

단순 GET. 404 없음 (빈 리스트는 200).

### `repositories.py` 확장

```python
async def list_chat_ids(conn) -> list[int]:
    rows = await conn.fetch("SELECT telegram_chat_id FROM user_bazi")
    return [r["telegram_chat_id"] for r in rows]
```

`user_bazi`를 기준으로 함 — `users`에는 있는데 명식 없는 사용자는 /score가 어차피 실패하므로 제외.

## 에러 처리

| 상황 | 동작 |
|---|---|
| BOT_TOKEN 없음 | exit 1, stderr 메시지 |
| API_BASE_URL/KEY 없음 | exit 1 |
| admin GET 401 | exit 1 (키 틀림 → 전체 중단) |
| admin GET 503 | exit 1 (DB 다운 → 다음 cron에서 재시도) |
| 개별 /score 404 | skip, 요약 counter++ |
| 개별 /score 502 | skip (차트 데이터는 /signal만 씀, /score는 502 없음) |
| Telegram Forbidden | skip, blocked counter++ |
| Telegram BadRequest | skip, failed counter++ |
| 부분 실패 | exit 0 (cron 재시도 X — 중복 발송 위험) |
| 전체 실패 (>50%) | exit 0 + ERROR 로그 (Railway 로그에서 감지) |

**멱등성**: 같은 날 2번 실행되면 같은 사용자에게 2번 발송됨. Cron이 1일 1회 보장 → 의존. 수동 Redeploy 주의.

## 테스트 전략

### `tests/test_broadcast.py`

- `format_morning_card()` 순수 함수 단위 테스트 (실제 score 응답 fixture)
- `run_broadcast()` — respx로 API mock, `AsyncMock`으로 `Bot.send_message` mock
  - happy path: 3명 전원 발송, summary 검증
  - dry-run: send_message 0회 호출
  - Forbidden: 1명 차단, 2명 발송
  - NotFoundError: 1명 등록 삭제, 2명 발송
- CLI arg 파싱 — argparse만 간단히

### `tests/test_api_admin.py`

- `GET /v1/admin/users` 401 (키 없음)
- 200 (빈 리스트 / 여러 명) — DB 있을 때만, TEST_DATABASE_URL 없으면 skip
- 503 (DB 다운)

### 로컬 스모크

```bash
# 1. dry-run: 실제 발송 X, 포맷만 확인
python -m sajucandle.broadcast --dry-run --test-chat-id <본인 chat_id>

# 2. 본인에게 실전 1회
python -m sajucandle.broadcast --test-chat-id <본인 chat_id>
```

### Railway 스모크

배포 후 Railway UI **Redeploy** 버튼으로 즉시 1회 trigger → 본인 텔레그램에 카드 도착 확인.

## 성공 기준

- `pytest -q` — Week 4 104 passed 유지 + broadcast 신규 테스트 전부 통과
- 로컬 dry-run에서 카드 포맷 의도대로 렌더링
- 로컬 실전 발송 → 본인 텔레그램에 1장 도착
- Railway cron 서비스 설정 완료, 수동 trigger로 1장 도착
- 다음 날 07:00 KST에 자동 도착 확인

## 배포 체크리스트 (사용자 담당)

1. Railway 프로젝트 → "+ New" → GitHub Repo 선택
2. 서비스 이름: `sajucandle-broadcast`
3. Settings → Deploy → Custom Start Command: `python -m sajucandle.broadcast`
4. Settings → Cron Schedule: `0 22 * * *`
5. Variables: `BOT_TOKEN`, `SAJUCANDLE_API_BASE_URL`, `SAJUCANDLE_API_KEY` (기존 서비스와 동일 값)
6. Redeploy 버튼으로 즉시 테스트
7. 내 텔레그램에 카드 도착 확인

# Week 5 구현 플랜 — 데일리 푸시

**Date**: 2026-04-16
**Spec**: docs/superpowers/specs/2026-04-16-week5-daily-push-design.md

## Task 1 — repositories.list_chat_ids

**파일**: `src/sajucandle/repositories.py`, `tests/test_repositories.py`

- `async def list_chat_ids(conn) -> list[int]` 추가
- SELECT from `user_bazi` (명식 있는 사용자만)
- DB 테스트: `TEST_DATABASE_URL` 있을 때만 (skip 패턴 유지)

**Success**:
- 빈 테이블 → `[]`
- 3명 등록 후 → len 3, 정렬 X
- pytest tests/test_repositories.py 통과

## Task 2 — API GET /v1/admin/users

**파일**: `src/sajucandle/api.py`, `tests/test_api.py`, `tests/test_api_admin.py`

- `/v1/admin/users` 엔드포인트 신설
- `_require_api_key` + DB pool 체크 (503)
- `tests/test_api.py`: 401 no key (DB 불필요)
- `tests/test_api_admin.py`: 503 (DB 없음) + 200 (DB 있음, TEST_DATABASE_URL skip 패턴)

**Success**: ruff clean, 새 테스트 통과

## Task 3 — api_client.get_admin_users

**파일**: `src/sajucandle/api_client.py`, `tests/test_api_client.py`

- `async def get_admin_users(self) -> list[int]`
- respx 모킹 테스트 1개 (200 + 401)

## Task 4 — broadcast.py 코어 로직

**파일**: `src/sajucandle/broadcast.py` (신규), `tests/test_broadcast.py` (신규)

순수 함수와 부작용 분리:

```python
def format_morning_card(score: dict, target_date: date) -> str: ...

async def run_broadcast(
    api_client: ApiClient,
    send_message: Callable[[int, str], Awaitable[None]],
    chat_ids: list[int],
    target_date: date,
    dry_run: bool = False,
) -> BroadcastSummary: ...
```

- `send_message`는 호출 가능한 의존성 주입 → 테스트에서 `AsyncMock` 주입
- `BroadcastSummary` dataclass: sent, failed, blocked, not_found

**테스트**:
1. `test_format_morning_card` — fixture score 입력 → 기대 문자열 포함 검증
2. `test_run_broadcast_happy_path` — 3명 전원 발송
3. `test_run_broadcast_dry_run` — send_message 미호출
4. `test_run_broadcast_forbidden_skipped` — 1명 blocked
5. `test_run_broadcast_notfound_skipped` — 1명 etag
6. `test_run_broadcast_score_502_skipped`

## Task 5 — broadcast CLI 엔트리

**파일**: `src/sajucandle/broadcast.py`의 `__main__`

- argparse: `--dry-run`, `--test-chat-id`, `--date`
- env 읽기: BOT_TOKEN, SAJUCANDLE_API_BASE_URL, SAJUCANDLE_API_KEY
- `asyncio.run(main())`
- `main()`에서 `telegram.Bot(token=...).send_message` 어댑터 함수를 `run_broadcast`에 주입
- 로깅: stdout INFO, httpx WARNING

**Success**:
- `python -m sajucandle.broadcast --dry-run --test-chat-id 1` → env 없으면 exit 1
- env 채운 후 → 실제 카드 포맷 출력

## Task 6 — 로컬 스모크

1. `.env` 또는 shell export로 env 채우기:
   ```
   BOT_TOKEN=<봇 토큰>
   SAJUCANDLE_API_BASE_URL=https://sajucandle-api-production.up.railway.app
   SAJUCANDLE_API_KEY=<현재 API 키>
   ```
2. `python -m sajucandle.broadcast --dry-run --test-chat-id <본인 chat_id>` — 출력 확인
3. `python -m sajucandle.broadcast --test-chat-id <본인 chat_id>` — 텔레그램에 실제 도착 확인

## Task 7 — 전체 회귀 + 커밋

- `ruff check .`
- `pytest -q`
- README 업데이트: Week 5 섹션, 환경 변수 표에 broadcast 3개 추가
- 커밋 메시지: `feat(week5): daily push broadcast (cron-triggered)`
- push → origin main

## Task 8 — Railway 배포 (사용자 담당)

spec의 "배포 체크리스트 (사용자 담당)" 7단계.

## Task 9 — 프로덕션 검증

- Redeploy 수동 trigger → 본인 텔레그램 카드 도착
- 다음 날 07:00 KST 자동 발송 확인
- Railway logs에서 `sent=N failed=M` 라인 확인

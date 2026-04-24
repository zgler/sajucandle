# Phase 5 플랜 — 전송 파이프라인 MVP 구현

> 2026-04-24 작성 / 스펙: [`../specs/2026-04-24-phase5-transport-design.md`](../specs/2026-04-24-phase5-transport-design.md)
> 브랜치: `phase5-transport-mvp` (main 8068d1e 기반)
> 각 Task = 1 commit 원칙, 모든 commit 전 `ruff check src/` 통과 필수.

---

## 실행 순서

| # | Task | 변경 파일 | 수락 기준 | Commit prefix |
|---|------|----------|----------|---------------|
| 1 | Transport 설정 스키마 | `src/sajucandle/transport/{__init__,config}.py` | `from sajucandle.transport.config import TransportConfig; cfg = TransportConfig.from_env()` OK | `feat(transport)` |
| 2 | Telegram sender | `src/sajucandle/transport/telegram.py` | `send_message()` 가 `httpx.MockTransport`로 200 받으면 True 반환 (Task 5에서 검증) | `feat(transport)` |
| 3 | `.env.example` 갱신 | `/.env.example` | 기존 구 스키마(DATABASE_URL/REDIS_URL 등) 삭제, Phase 5 키 4종 추가 | `docs(env)` |
| 4 | 스케줄러 훅 연결 | `src/sajucandle/scheduler/runner.py` | `run_monthly_job(dt, notify=True)` 시 Telegram 전송 호출, `--no-notify` 지원 | `feat(scheduler)` |
| 5 | Config unit smoke | `tests/smoke_test_transport_config.py` | 4가지 env 조합(전부 있음/token 누락/chat_id 누락/disabled)에서 `is_telegram_ready()` 예상대로 | `test(transport)` |
| 6 | Telegram mock smoke | `tests/smoke_test_transport_telegram.py` | httpx MockTransport로 200/429→200(retry)/403(no retry)/4096초과(chunk 2) 4 케이스 검증 | `test(transport)` |
| 7 | CLAUDE.md 모듈 책임 갱신 | `CLAUDE.md` | § 4.3에 transport 레이어 추가, § 5.2/5.3에 `TRANSPORT_ENABLED` 언급 | `docs(claude)` |

**커밋 후 매 단계 `./.venv/Scripts/python.exe -m ruff check src/` 통과 확인.**

**Task 6 완료 후 로컬 Integration 수동 검증**: BotFather 봇 발급 → `.env` 작성 → `--date 2026-05-01` 실행 → Telegram 도착 스크린샷.

**전체 완료 후 PR 생성 (base=main, head=phase5-transport-mvp)**.

---

## Task 1 — Transport 설정 스키마

### 파일: `src/sajucandle/transport/__init__.py`
빈 파일.

### 파일: `src/sajucandle/transport/config.py`

```python
"""Transport 계층 설정 스키마.

.env → TransportConfig 매핑. SecretStr로 Bot Token 보호.
"""
from __future__ import annotations

import os

from pydantic import BaseModel, SecretStr


class TransportConfig(BaseModel):
    enabled: bool = False
    telegram_bot_token: SecretStr | None = None
    telegram_admin_chat_id: str | None = None
    telegram_api_base: str = "https://api.telegram.org"

    @classmethod
    def from_env(cls) -> "TransportConfig":
        raw_token = os.getenv("TELEGRAM_BOT_TOKEN")
        return cls(
            enabled=os.getenv("TRANSPORT_ENABLED", "false").lower() == "true",
            telegram_bot_token=SecretStr(raw_token) if raw_token else None,
            telegram_admin_chat_id=os.getenv("TELEGRAM_ADMIN_CHAT_ID") or None,
            telegram_api_base=os.getenv("TELEGRAM_API_BASE",
                                        "https://api.telegram.org"),
        )

    def is_telegram_ready(self) -> bool:
        return (
            self.enabled
            and self.telegram_bot_token is not None
            and bool(self.telegram_admin_chat_id)
        )
```

### 수락 기준
```bash
./.venv/Scripts/python.exe -c "
from sajucandle.transport.config import TransportConfig
cfg = TransportConfig.from_env()
print('ready=', cfg.is_telegram_ready())
"
```
→ 에러 없이 실행, env 없으면 `ready= False`.

### Commit
```
feat(transport): TransportConfig 스키마 + env 로드

- Pydantic BaseModel 기반 설정 객체
- SecretStr로 Bot Token 보호
- is_telegram_ready() 플래그로 전송 전 검증
```

---

## Task 2 — Telegram sender

### 파일: `src/sajucandle/transport/telegram.py`

```python
"""Telegram Bot API를 통한 관리자 메시지 전송.

사용:
    from sajucandle.transport.telegram import send_message
    send_message(render_telegram(report))
"""
from __future__ import annotations

import logging
import time

import httpx

from .config import TransportConfig

log = logging.getLogger(__name__)

MDV2_CHUNK_LIMIT = 4096
_HTTP_TIMEOUT = 10.0
_MAX_RETRIES = 2
_RETRY_STATUS = {408, 429, 500, 502, 503, 504}


def send_message(text: str, cfg: TransportConfig | None = None) -> bool:
    """텔레그램 관리자에게 MDv2 메시지 전송.

    반환: 모든 chunk 전송 성공 시 True, 하나라도 실패/비활성화 시 False.
    """
    cfg = cfg or TransportConfig.from_env()
    if not cfg.is_telegram_ready():
        log.info("Telegram 전송 skip (TRANSPORT_ENABLED=false or creds missing)")
        return False

    assert cfg.telegram_bot_token is not None  # is_telegram_ready 검증 후
    assert cfg.telegram_admin_chat_id is not None

    chunks = _chunk_text(text, MDV2_CHUNK_LIMIT)
    token = cfg.telegram_bot_token.get_secret_value()
    url = f"{cfg.telegram_api_base}/bot{token}/sendMessage"

    with httpx.Client(timeout=_HTTP_TIMEOUT) as client:
        for i, chunk in enumerate(chunks, 1):
            payload = {
                "chat_id": cfg.telegram_admin_chat_id,
                "text": chunk,
                "parse_mode": "MarkdownV2",
                "disable_web_page_preview": True,
            }
            if not _post_with_retry(client, url, payload, chunk_idx=i, total=len(chunks)):
                return False

    log.info(f"Telegram 전송 완료 (chat_id={cfg.telegram_admin_chat_id}, {len(chunks)} chunks)")
    return True


def _chunk_text(text: str, limit: int) -> list[str]:
    """줄 경계 기준으로 텍스트를 limit 이하 chunk로 분할.

    단일 줄이 limit 초과 시 강제로 limit 단위 컷.
    """
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for line in text.splitlines(keepends=True):
        if len(line) > limit:
            if current:
                chunks.append("".join(current))
                current, current_len = [], 0
            for i in range(0, len(line), limit):
                chunks.append(line[i:i + limit])
            continue
        if current_len + len(line) > limit:
            chunks.append("".join(current))
            current, current_len = [line], len(line)
        else:
            current.append(line)
            current_len += len(line)
    if current:
        chunks.append("".join(current))
    return chunks


def _post_with_retry(client: httpx.Client, url: str, payload: dict,
                     *, chunk_idx: int, total: int) -> bool:
    """2xx 성공, 5xx/408/429 retry, 4xx(기타) 즉시 실패."""
    for attempt in range(_MAX_RETRIES + 1):
        try:
            r = client.post(url, json=payload)
        except httpx.RequestError as e:
            log.warning(f"Telegram request error (chunk {chunk_idx}/{total}, attempt {attempt+1}): {e}")
            if attempt >= _MAX_RETRIES:
                log.error(f"Telegram 전송 실패 (chunk {chunk_idx}/{total}): 연결 오류")
                return False
            time.sleep(1.0 * (attempt + 1))
            continue

        if 200 <= r.status_code < 300:
            return True
        if r.status_code in _RETRY_STATUS and attempt < _MAX_RETRIES:
            log.warning(f"Telegram {r.status_code} (chunk {chunk_idx}/{total}, attempt {attempt+1}) — retry")
            time.sleep(1.0 * (attempt + 1))
            continue
        # 4xx (401/403/400 등) 또는 retry 소진
        log.error(f"Telegram 전송 실패 status={r.status_code} body={r.text[:200]}")
        return False

    return False
```

### 수락 기준
- `ruff check src/` 통과
- Python import 성공: `from sajucandle.transport.telegram import send_message`
- 실제 호출 검증은 Task 6에서

### Commit
```
feat(transport): Telegram sender (httpx + MDv2 + chunk + retry)

- send_message(): MDv2 parse_mode로 Telegram Bot API 호출
- 4096자 초과 시 줄 경계 기준 자동 분할
- 5xx/408/429 최대 2회 retry (지수 백오프)
- 4xx 계열은 즉시 실패 + ERROR 로그
- 비활성화 시 no-op 반환 False
```

---

## Task 3 — `.env.example` 갱신

### 현재 `.env.example` 확인 후 전면 교체

```bash
# Phase 5 transport
TRANSPORT_ENABLED=false
TELEGRAM_BOT_TOKEN=
TELEGRAM_ADMIN_CHAT_ID=
TELEGRAM_API_BASE=https://api.telegram.org

# (참고) 배포 환경에서는 Railway Dashboard에 주입.
# 로컬 테스트 시 이 파일을 .env로 복사 후 실제 값 입력:
#   cp .env.example .env
# BotFather (@BotFather) 에서 봇 생성 → TELEGRAM_BOT_TOKEN 획득.
# 본인 Telegram에서 @userinfobot 에게 메시지 → 본인 chat_id 확인.
```

### Commit
```
docs(env): .env.example을 Phase 5 transport 키로 갱신

구 스키마(DATABASE_URL / REDIS_URL / TELEGRAM_WEBHOOK 등) 제거하고
Phase 5 MVP transport 4개 키(TRANSPORT_ENABLED, TELEGRAM_BOT_TOKEN,
TELEGRAM_ADMIN_CHAT_ID, TELEGRAM_API_BASE)만 남긴다. BotFather /
@userinfobot 설정 가이드 주석 추가.
```

---

## Task 4 — 스케줄러 훅 연결

### 파일: `src/sajucandle/scheduler/runner.py`

`run_monthly_job` 말미에 전송 로직 추가 + `main()`에 `--no-notify` 플래그.

```python
# import 블록에 추가
from sajucandle.transport.config import TransportConfig
from sajucandle.transport.telegram import send_message as tg_send

# run_monthly_job 시그니처 변경
def run_monthly_job(dt: datetime | None = None, *, notify: bool = True) -> None:
    ...
    # 기존: log.info(f"새 보유: {sorted(report.new_holdings)}")
    # 그 뒤에 추가:

    if notify:
        cfg = TransportConfig.from_env()
        if cfg.is_telegram_ready():
            ok = tg_send(render_telegram(report), cfg=cfg)
            if ok:
                log.info("Telegram 전송 완료")
            else:
                log.error("Telegram 전송 실패 — 파일 저장본은 유지됨")
        else:
            log.info("Telegram 비활성화 (TRANSPORT_ENABLED=false 또는 creds 누락)")

# main() 수정
def main() -> None:
    parser = argparse.ArgumentParser(description="사주캔들 월간 신호 스케줄러")
    parser.add_argument("--daemon", action="store_true", ...)
    parser.add_argument("--date", type=str, default=None, ...)
    parser.add_argument("--no-notify", action="store_true",
                        help="Telegram 전송 skip (파일 저장만)")
    args = parser.parse_args()

    notify = not args.no_notify
    if args.daemon:
        ...
        scheduler.add_job(
            lambda: run_monthly_job(notify=notify),  # 람다로 감싸서 플래그 전달
            ...
        )
    else:
        dt = None
        if args.date:
            dt = datetime.strptime(args.date, "%Y-%m-%d").replace(hour=9)
        run_monthly_job(dt, notify=notify)
```

### 수락 기준
- `TRANSPORT_ENABLED=false` 상태에서 `--date 2026-05-01` 실행 시: 기존처럼 파일 저장 + "비활성화" 로그만
- `--no-notify` 플래그 시: `TRANSPORT_ENABLED`와 무관하게 전송 skip

### Commit
```
feat(scheduler): 월간 잡 말미에 Telegram 전송 훅 추가

- run_monthly_job(dt, *, notify=True) 시그니처
- notify=True + cfg.is_telegram_ready() 시 render_telegram 결과 전송
- --no-notify CLI 플래그로 드라이런 지원
- 전송 실패 시 ERROR 로그만, 파일 저장본으로 복구 가능
```

---

## Task 5 — Config unit smoke

### 파일: `tests/smoke_test_transport_config.py`

```python
"""Transport config env 로드 검증."""
from __future__ import annotations

import os
import sys
sys.stdout.reconfigure(encoding="utf-8")

from sajucandle.transport.config import TransportConfig


def _set_env(**kwargs):
    for k in ("TRANSPORT_ENABLED", "TELEGRAM_BOT_TOKEN",
              "TELEGRAM_ADMIN_CHAT_ID", "TELEGRAM_API_BASE"):
        os.environ.pop(k, None)
    for k, v in kwargs.items():
        if v is not None:
            os.environ[k] = v


cases = [
    ("전부 설정",  dict(TRANSPORT_ENABLED="true",
                       TELEGRAM_BOT_TOKEN="abc:def",
                       TELEGRAM_ADMIN_CHAT_ID="123"), True),
    ("disabled",   dict(TRANSPORT_ENABLED="false",
                       TELEGRAM_BOT_TOKEN="abc:def",
                       TELEGRAM_ADMIN_CHAT_ID="123"), False),
    ("token 누락", dict(TRANSPORT_ENABLED="true",
                       TELEGRAM_ADMIN_CHAT_ID="123"),    False),
    ("chat_id 누락", dict(TRANSPORT_ENABLED="true",
                         TELEGRAM_BOT_TOKEN="abc:def"),  False),
]

failed = 0
for name, env, expected in cases:
    _set_env(**env)
    cfg = TransportConfig.from_env()
    actual = cfg.is_telegram_ready()
    mark = "✓" if actual == expected else "✗"
    print(f"  {mark} {name:20s} ready={actual} (expected {expected})")
    if actual != expected:
        failed += 1

if failed:
    print(f"\n❌ {failed}/{len(cases)} FAIL")
    sys.exit(1)
print(f"\n✓ {len(cases)}/{len(cases)} PASS")
```

### 수락 기준
`PYTHONPATH=src ./.venv/Scripts/python.exe tests/smoke_test_transport_config.py` 4/4 PASS.

### Commit
```
test(transport): TransportConfig env 조합 smoke test

4 케이스 — 전부설정/비활성화/token누락/chat_id누락 —
is_telegram_ready() 반환값 검증.
```

---

## Task 6 — Telegram mock smoke

### 파일: `tests/smoke_test_transport_telegram.py`

```python
"""Telegram sender 검증 — httpx.MockTransport 사용."""
from __future__ import annotations

import sys
sys.stdout.reconfigure(encoding="utf-8")

import httpx
from pydantic import SecretStr

from sajucandle.transport.config import TransportConfig
from sajucandle.transport import telegram as tg_mod


def _cfg():
    return TransportConfig(
        enabled=True,
        telegram_bot_token=SecretStr("abc:def"),
        telegram_admin_chat_id="123",
        telegram_api_base="https://api.telegram.org",
    )


def _patched_send(text: str, handler) -> bool:
    """httpx.MockTransport로 client.post를 모킹."""
    orig_client = tg_mod.httpx.Client
    transport = httpx.MockTransport(handler)

    class _Client(orig_client):  # type: ignore
        def __init__(self, *a, **kw):
            kw["transport"] = transport
            super().__init__(*a, **kw)

    tg_mod.httpx.Client = _Client
    try:
        return tg_mod.send_message(text, cfg=_cfg())
    finally:
        tg_mod.httpx.Client = orig_client


# Case 1: 200 OK
def h_ok(req):
    return httpx.Response(200, json={"ok": True})

# Case 2: 429 → 200 (retry)
_retry_state = {"count": 0}
def h_retry(req):
    _retry_state["count"] += 1
    if _retry_state["count"] == 1:
        return httpx.Response(429, json={"ok": False})
    return httpx.Response(200, json={"ok": True})

# Case 3: 403 (no retry)
def h_403(req):
    return httpx.Response(403, json={"ok": False, "description": "Forbidden"})

# Case 4: 4096자 초과 → 2 chunks (둘 다 200)
_chunk_state = {"count": 0}
def h_chunks(req):
    _chunk_state["count"] += 1
    return httpx.Response(200, json={"ok": True})


cases = []

print("Case 1: 200 OK")
r = _patched_send("hello", h_ok)
cases.append(("200 OK", r, True))
print(f"  result={r}")

print("Case 2: 429 → 200 (retry)")
_retry_state["count"] = 0
r = _patched_send("hello", h_retry)
cases.append(("429 retry", r, True))
print(f"  result={r}, attempts={_retry_state['count']}")

print("Case 3: 403 (no retry)")
r = _patched_send("hello", h_403)
cases.append(("403 fail", r, False))
print(f"  result={r}")

print("Case 4: 4096자 초과 → 2 chunks")
long_text = "\n".join([f"line{i}" for i in range(1000)])  # ~8000자
_chunk_state["count"] = 0
r = _patched_send(long_text, h_chunks)
cases.append(("chunk split", r, True))
print(f"  result={r}, post_count={_chunk_state['count']} (expected >=2)")
assert _chunk_state["count"] >= 2, "chunk 분할 실패"

failed = sum(1 for _, actual, expected in cases if actual != expected)
if failed:
    print(f"\n❌ {failed}/{len(cases)} FAIL")
    sys.exit(1)
print(f"\n✓ {len(cases)}/{len(cases)} PASS")
```

### 수락 기준
`PYTHONPATH=src ./.venv/Scripts/python.exe tests/smoke_test_transport_telegram.py` 4/4 PASS.

### Commit
```
test(transport): Telegram sender httpx mock smoke test

4 시나리오:
- 200 OK → True
- 429 → 200 retry → True (호출 2회)
- 403 → False (retry 없음)
- 4096자 초과 → chunk 분할 후 2+ POST
```

---

## Task 7 — CLAUDE.md 갱신

### § 4.3 시그널·서비스 레이어 테이블에 행 추가:

| `transport/config.py` | TransportConfig — .env → 설정 객체 (SecretStr 보호) |
| `transport/telegram.py` | send_message() — httpx 기반 Telegram Bot API 전송, MDv2 + chunk + retry |

### § 5.3 월간 스케줄러 섹션에 추가:

```bash
# Telegram 전송 없이 파일 저장만 (로컬 dry-run)
PYTHONPATH=src ./.venv/Scripts/python.exe -m sajucandle.scheduler.runner --date 2026-05-01 --no-notify
```

### § 6.1에 추가 한 줄:
- **`.env` TRANSPORT_ENABLED**: `false` 기본값. `true` + 토큰 주입 시에만 실제 Telegram 전송.

### Commit
```
docs(claude): Phase 5 transport 모듈 추가 언급

- § 4.3 transport/{config,telegram} 레이어
- § 5.3 --no-notify 드라이런 명령
- § 6.1 TRANSPORT_ENABLED 플래그
```

---

## PR 생성 (전체 완료 후)

```bash
git push -u origin phase5-transport-mvp
GH_REPO="zgler/sajucandle" gh pr create --title "Phase 5 MVP: Telegram 관리자 전송 파이프라인" \
  --base main --body "..."
```

PR 본문에 포함:
- 스펙 링크
- 각 Task 7개의 커밋 요약
- `.env` 설정 가이드 (BotFather / @userinfobot)
- 로컬 Integration 결과 (스크린샷 or 로그)
- Test plan 체크리스트

---

## 중단·재개 전략

각 Task 완료 시 커밋 → 중간 중단해도 `git log --oneline` 으로 현재 위치 파악 가능. 다음 세션은 "Task N 다음 진행" 으로 재개.

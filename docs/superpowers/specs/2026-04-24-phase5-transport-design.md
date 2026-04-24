# Phase 5 스펙 — 전송 파이프라인 MVP (Telegram 관리자 1명)

> 2026-04-24 작성 / 상위 리서치: [`../../planning/research/phase5_transport_current_state.md`](../../planning/research/phase5_transport_current_state.md)
> 범위: α MVP-single · 채널: Telegram only

---

## 1. 목표 (한 문장)

**월간 스케줄러가 신호를 생성한 직후, `render_telegram()` 출력을 관리자 개인 Telegram 채팅에 자동 전송한다.** 구독자 DB 없이 `.env`에 정의된 단일 수신자만 대상으로 한다.

## 2. 비목표 (Phase 5 이 스펙 밖)

- 구독자 DB / 티어 / 구독·해지 API (→ C4)
- 이메일 전송 (→ 이 스펙에서는 제외)
- 웹 프론트엔드 / 인증 UI
- 복수 수신자 broadcast (옵션 β/γ)
- 봇 양방향 인터랙션 (명령어, 콜백 버튼) — 순수 push-only

## 3. 사용자 시나리오

**S1 — 월간 자동 전송**
1. 매월 1일 09:00 KST, `scheduler/runner.py` 데몬이 `run_monthly_job()` 실행
2. 신호 생성 · 파일 저장은 기존대로
3. **신규**: 말미에 `transport.telegram.send_message(report_text)` 호출
4. 성공 시 로그 `"Telegram 전송 완료 (chat_id=XXXX)"`, 실패 시 `ERROR` 로그만 남기고 파일 저장은 유지

**S2 — 수동 재전송**
- `python -m sajucandle.scheduler.runner --date 2026-04-01` 에 `--notify` 플래그 추가 → 기존 저장본 재생성·재전송

**S3 — 드라이런**
- `.env`에 `TRANSPORT_ENABLED=false` 이면 메시지 포맷팅만 하고 실제 API 호출 생략 (로그만 출력)

## 4. 설정 스키마 (`.env`)

```bash
# Phase 5 transport
TRANSPORT_ENABLED=true                  # false면 실제 전송 skip
TELEGRAM_BOT_TOKEN=123456:ABC-DEF...    # BotFather에서 발급
TELEGRAM_ADMIN_CHAT_ID=123456789        # 관리자 개인 chat_id
TELEGRAM_API_BASE=https://api.telegram.org  # 기본값, 프록시 시 override
```

- `.env.example` 갱신해서 위 키를 노출 (값은 비움)
- `.env` 자체는 이미 `.gitignore` 처리됨
- Railway는 Dashboard에서 동일 키 주입

## 5. 모듈 설계 (신규)

```
src/sajucandle/transport/
├── __init__.py
├── config.py       # Pydantic TransportConfig — .env 로드/검증
└── telegram.py     # send_message(), _chunk_text()
```

### 5.1 `transport/config.py`

```python
from pydantic import BaseModel, SecretStr
import os

class TransportConfig(BaseModel):
    enabled: bool
    telegram_bot_token: SecretStr | None
    telegram_admin_chat_id: str | None
    telegram_api_base: str = "https://api.telegram.org"

    @classmethod
    def from_env(cls) -> "TransportConfig":
        return cls(
            enabled=os.getenv("TRANSPORT_ENABLED", "false").lower() == "true",
            telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN") or None,
            telegram_admin_chat_id=os.getenv("TELEGRAM_ADMIN_CHAT_ID") or None,
            telegram_api_base=os.getenv("TELEGRAM_API_BASE",
                                        "https://api.telegram.org"),
        )

    def is_telegram_ready(self) -> bool:
        return self.enabled and bool(self.telegram_bot_token) and bool(self.telegram_admin_chat_id)
```

### 5.2 `transport/telegram.py`

```python
import logging
import httpx
from .config import TransportConfig

log = logging.getLogger(__name__)

MDV2_CHUNK_LIMIT = 4096          # Telegram 1 msg 최대 길이
_HTTP_TIMEOUT = 10.0
_MAX_RETRIES = 2


def send_message(text: str, cfg: TransportConfig | None = None) -> bool:
    """텔레그램 관리자에게 MDv2 메시지 전송. 성공 여부 반환.

    - cfg.enabled=False 이면 즉시 False (no-op)
    - 4096자 초과 시 자동 분할해 순차 전송 (각 chunk 성공해야 True)
    - 실패는 retry 1회 후 False + ERROR 로그
    """
    cfg = cfg or TransportConfig.from_env()
    if not cfg.is_telegram_ready():
        log.info("Telegram 비활성화 (TRANSPORT_ENABLED or creds 누락)")
        return False

    chunks = _chunk_text(text, MDV2_CHUNK_LIMIT)
    url = f"{cfg.telegram_api_base}/bot{cfg.telegram_bot_token.get_secret_value()}/sendMessage"

    for i, chunk in enumerate(chunks):
        payload = {
            "chat_id": cfg.telegram_admin_chat_id,
            "text": chunk,
            "parse_mode": "MarkdownV2",
            "disable_web_page_preview": True,
        }
        if not _post_with_retry(url, payload):
            log.error(f"Telegram 전송 실패 (chunk {i+1}/{len(chunks)})")
            return False
    log.info(f"Telegram 전송 완료 (chat_id={cfg.telegram_admin_chat_id}, {len(chunks)} chunks)")
    return True


def _chunk_text(text: str, limit: int) -> list[str]:
    """줄 경계 우선으로 분할. 단일 줄이 limit 초과 시 강제 컷."""
    ...  # 구현 디테일은 플랜에서


def _post_with_retry(url: str, payload: dict) -> bool:
    """httpx.post, 2xx면 성공. 5xx·timeout만 retry."""
    ...
```

### 5.3 `scheduler/runner.py` 변경

```python
from sajucandle.transport.telegram import send_message as tg_send
from sajucandle.transport.config import TransportConfig

def run_monthly_job(dt=None, *, notify: bool = True):
    ...
    out_dir = save_report(report, dt)
    save_holdings(report.new_holdings, dt)
    print(render_text(report))

    # 신규: Telegram 전송
    if notify:
        cfg = TransportConfig.from_env()
        if cfg.is_telegram_ready():
            tg_send(render_telegram(report), cfg=cfg)
        else:
            log.info("Telegram 비활성화 — 파일 저장만 완료")

def main():
    parser.add_argument("--no-notify", action="store_true", ...)
    ...
    run_monthly_job(dt, notify=not args.no_notify)
```

## 6. 에러 핸들링 정책

| 상황 | 처리 |
|---|---|
| `TRANSPORT_ENABLED=false` | INFO 로그 "비활성화", `send_message` 즉시 False. job 성공으로 간주 |
| creds 누락 | INFO 로그 "creds 누락", False. 파일 저장은 완료되어야 함 |
| Telegram 5xx / timeout | 1회 retry, 실패 시 ERROR 로그 + False. **job 자체는 성공으로 취급** (파일 저장되어 있으므로) |
| Telegram 4xx (Bad Request / 401) | retry 없이 ERROR 로그. MDv2 이스케이프 실수일 가능성 → fallback 없음, 로그만 남김 |
| MDv2 parse_mode 거부 | 초기 MVP는 fallback 없음 — renderer 쪽 이스케이프 신뢰. 문제 발생 시 별도 fix |

## 7. 테스트 전략

### 7.1 Unit
- `tests/smoke_test_transport_config.py` — 환경변수 조합별 `is_telegram_ready()` 검증
- `tests/smoke_test_transport_telegram.py` — `httpx.MockTransport` 로 응답 모킹
  - 200 → `send_message` 반환 True
  - 429 + 200 → retry 후 True
  - 403 → False (retry 안 함)
  - 4096자 초과 → 2 chunk 전송 검증

### 7.2 Integration (수동)
1. BotFather에서 `@sajucandle_signal_bot` 생성 → `TELEGRAM_BOT_TOKEN` 획득
2. 본인 Telegram으로 봇에게 `/start` → `@userinfobot` 등으로 본인 `chat_id` 확인
3. `.env` 세팅 + `TRANSPORT_ENABLED=true`
4. `PYTHONPATH=src ./.venv/Scripts/python.exe -m sajucandle.scheduler.runner --date 2026-05-01`
5. Telegram에 메시지 수신 확인

### 7.3 CI
- 기존 `ci.yml` 그대로. 신규 smoke test 2개는 네트워크 불필요(mock) → CI 포함 가능

## 8. 보안 고려

- **Bot Token은 `SecretStr`로 감싸서 로그/에러 메시지에 노출 방지**
- Token 유출 시 BotFather `/revoke`로 즉시 무효화
- `chat_id`는 secret 아니지만 관행상 `.env`에 저장
- Railway Dashboard에 환경변수 주입 시 "sealed" 옵션 사용 (노출 최소화)

## 9. 롤아웃

1. 로컬에서 BotFather 봇 발급 + `.env` 구성 + 수동 테스트 (S1 시나리오 실행)
2. 스케줄러를 Railway에 `worker` 서비스로 배포 (`Procfile` `worker` 라인 이미 갱신됨)
3. Railway 환경변수 주입
4. 다음 매월 1일 09:00 KST 자동 발송 대기, 또는 Railway `Redeploy` + `--date` 오버라이드로 즉시 검증

## 10. 작업 분해 (구현 플랜에서 상세화)

| # | Task | 예상 파일 | 커밋 유형 |
|---|---|---|---|
| 1 | `transport/__init__.py`, `transport/config.py` | `src/sajucandle/transport/` | feat(transport) |
| 2 | `transport/telegram.py` | 위 | feat(transport) |
| 3 | `.env.example` 갱신 | `/` | docs |
| 4 | `scheduler/runner.py` 훅 추가 + `--no-notify` 옵션 | 수정 | feat(scheduler) |
| 5 | smoke_test_transport_config.py | `tests/` | test |
| 6 | smoke_test_transport_telegram.py (httpx mock) | `tests/` | test |
| 7 | CLAUDE.md § 4.3, § 5.3에 transport 언급 | `CLAUDE.md` | docs |

- 전체 코드 변경 ~300줄 예상
- 1-2 commit로 쪼개 리뷰 가능

## 11. 미해결·후속 (범위 외)

- `β` (Broadcast-list) 또는 `γ` (Full-DB) 확장: 별도 스펙 필요
- 이메일 채널: 동 스펙에서 SMTP 또는 Resend 백엔드 결정 후 추가 스펙
- 웹 대시보드: `/signals/stock/html` 이상의 UI는 Phase 6 후보
- Telegram 봇 양방향 인터랙션(명령어, 버튼): 별도 스펙
- MDv2 parse 실패 시 HTML parse_mode fallback: 운영 중 문제 발생 시 fix

---

**승인 시** 이 스펙 기준으로 [`../plans/2026-04-24-phase5-transport-plan.md`](../plans/2026-04-24-phase5-transport-plan.md) 구현 플랜 작성 → 실행 순서.

# Phase 5 리서치 — 전송 파이프라인 현황

> 2026-04-24 / 브랜치 `phase4-logic-merge` 기준
> 목적: Renderer 출력 → 실제 구독자 전달 경로(텔레그램/이메일/웹) 구현 전 현황 파악.

---

## 1. 현재 구현된 출력 경로

### 1.1 Renderer 함수 (`signal/renderer.py`)
| 함수 | 반환 | 포맷 |
|---|---|---|
| `render_telegram(report)` | `str` | Telegram MarkdownV2 (이모지 + 코드블록) |
| `render_email_html(report)` | `str` | 완성 HTML (inline CSS, 테이블 + 뱃지) |
| `render_text(report)` | `str` | plain text (콘솔/슬랙용) |

**세 함수 모두 문자열만 반환. 실제 전송 로직은 포함되지 않는다.**

### 1.2 FastAPI 엔드포인트 (`api/main.py`)
| 엔드포인트 | 용도 |
|---|---|
| `GET /signals/stock` | JSON 응답 (pull) |
| `GET /signals/stock/html` | HTML 미리보기 (이메일 preview) |
| `GET /signals/stock/telegram` | `{"message": "...MDv2 텍스트..."}` (preview) |

**모두 pull-based.** 호출자가 직접 받아 가는 구조 — 자동 push 없음.

### 1.3 월간 스케줄러 (`scheduler/runner.py`)
- 매월 1일 09:00 KST `run_monthly_job()` 실행
- 동작: (1) 신호 생성 → (2) `data/signals/YYYY-MM/` 에 `.json / .html / .txt` 3종 파일 저장 → (3) 콘솔 print → (4) `data/signals/holdings.json` 갱신
- **실제 전송 로직 없음.** 외부 수신자에게 알림이 가지 않는다.

---

## 2. 부재 요소 (실제 전달에 필요한 것)

### 2.1 Telegram Bot
- Bot Token 없음 (env var / secret storage 스키마 없음)
- Chat ID / Group ID 없음
- Telegram Bot API 호출 코드 없음 (`python-telegram-bot`은 Phase 4에서 deps 제거됨 — `httpx`만 있음)
- Rate-limit 처리 (초당 30 msg 제한) 없음

### 2.2 이메일 (SMTP)
- `smtplib` / `email.message.EmailMessage` 사용처 없음
- SMTP 호스트/포트/인증 secret 없음
- 발신자 주소 / 수신자 리스트 없음
- HTML + plain-text multipart 조립 코드 없음

### 2.3 웹 프론트엔드
- `static/`, `templates/`, Jinja2 설정 없음
- `/signals/stock/html` 는 동적 렌더. 방문자용 UI(네비/로그인/로그/구독)는 없음
- React/Vue 등 별도 앱 없음

### 2.4 수신자 관리 (구독자 DB)
- Phase 4에서 `repositories.py` / `db.py` / `migrations/` 전부 삭제됨 (구 아키텍처)
- 현재 `data/signals/holdings.json` 는 **보유 종목 persistence**지 구독자 리스트 아님
- 티어/플랜/구독 상태/unsubscribe 토큰 등 없음

### 2.5 배포 환경 Secret 주입
- Railway 기준: `$PORT` 외 env var 주입 흐름 없음
- `.env.example` 존재하지만 내용은 `DATABASE_URL` / `REDIS_URL` 등 구 스키마

---

## 3. 의존성 · 제약

### 3.1 이미 확보된 것
- `httpx` (base dep) → Telegram Bot API HTTP 호출 가능
- `pydantic` (base dep) → 설정 스키마 정의 가능
- `fastapi` (base dep) → 웹 API 뼈대는 있음

### 3.2 추가 필요 가능성
- `python-telegram-bot` 재도입? 또는 `httpx` raw 호출? → C3 스펙 단계 결정 항목
- `aiosmtplib` (async SMTP) 또는 표준 `smtplib` → 동 결정 항목
- SMTP 대신 SaaS (Resend / SendGrid / Postmark) API → 인증 키 관리 단순함

### 3.3 배포 상 제약
- Railway 무료 플랜: 메모리 512MB, 아웃바운드 제한 없음 (Telegram/SMTP 직결 가능)
- Railway IP 블록: `api.binance.com` 차단 사례 있음 — Telegram API(`api.telegram.org`) / SMTP 는 실측 필요
- 스케줄러 데몬(`BlockingScheduler`) 과 API 서버는 Railway에서 **별도 서비스**로 띄워야 동시 실행

---

## 4. C3 스펙 범위 옵션 (사용자 결정 필요)

### 옵션 α — MVP-single (1~2일)
- `.env`에 `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ADMIN_CHAT_ID`, `SMTP_*`, `ADMIN_EMAIL` 만 두고
- `scheduler/runner.py`가 실행 말미에 **관리자 1명**에게만 전송
- 구독자 DB 없이 본인 수신으로 E2E 검증
- **다음 단계(C4) 전제 불필요**

### 옵션 β — Broadcast-list 파일 기반 (3~5일)
- `data/subscribers.json` 같은 파일로 수신자 리스트 관리
  ```json
  [
    {"chat_id": 12345, "email": "a@b.com", "tier": "free"},
    ...
  ]
  ```
- 수동 수정 가능, 백업 단순
- 유료/무료 티어 구분 힌트 가능
- **C4(구독자 DB) 없이 운영 가능한 과도기**

### 옵션 γ — Full-DB 선행 (C4 먼저, C3 후행, 1~2주)
- users / subscriptions / send_log 스키마 설계 후 신규 `migrations/001_phase5_subscribers.sql` 작성
- FastAPI에 `/subscribe`, `/unsubscribe`, `/admin/*` 라우트 추가
- 전송 파이프라인은 DB에서 active 구독자 쿼리 → 전송 → send_log 기록
- **실서비스 수준의 완성도**

---

## 5. 채널 우선순위 결정 필요

| 채널 | 장점 | 단점 |
|---|---|---|
| Telegram | 즉시성, 모바일 푸시, 봇 가입 마찰 낮음, 무료 | 본인의 Telegram 계정 필요, iOS 일부 국가 제한 |
| 이메일 (SMTP/Resend) | 모두가 가짐, HTML 포맷 풍부, 스팸 규제로 발송자 신뢰 필요 | DNS(SPF/DKIM/DMARC) 설정 부담, 수동 구독 마찰 |
| 웹 대시보드 | 히스토리 조회, 차트 삽입 가능 | 트래픽 확보 부담, 별도 인증 필요 |

**추천 MVP 조합**: Telegram(primary) + 이메일(secondary). 웹은 `/signals/stock/html` 로 임시 preview 가능하니 C3 범위 밖으로 미룸.

---

## 6. 다음 액션 (사용자 결정 후 스펙 작성)

결정 필요 항목:
1. **스펙 범위**: α / β / γ 중 선택
2. **채널**: Telegram / 이메일 / 둘 다 / Slack 등 추가
3. **이메일 백엔드**: 직접 SMTP / Resend API / SendGrid / Postmark / AWS SES
4. **Secret 관리**: Railway 환경변수 / 별도 secret manager (Doppler 등)
5. **unsubscribe 정책**: 옵션 β/γ 선택 시 — 토큰 방식 / 1-click 링크 / 이메일 회신 기반

사용자 답변 후 `docs/superpowers/specs/2026-04-24-phase5-transport-design.md` 스펙 작성.

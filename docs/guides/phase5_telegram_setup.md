# Phase 5 Telegram 전송 검증 가이드 (초심자용)

> 목표: 사주캔들 월간 신호를 **내 Telegram에 실제로 받아보기**.
> 소요 시간: 10~15분. 결제·신용카드 불필요.
> 전제: Telegram 앱이 스마트폰에 설치되어 있고, 본 프로젝트 로컬 환경(`.venv`)이 준비됨.

---

## 한눈에 보는 단계

1. Telegram에서 **BotFather** 와 대화 → 기존 **@sajucandle** 봇 토큰 받기
2. Telegram에서 **@userinfobot** 과 대화 → 내 **chat_id** 받기
3. **@sajucandle 봇과 한 번 대화 시작(`/start`)** ← 이걸 빼먹으면 403 에러
4. 프로젝트 루트에 `.env` 파일 만들고 토큰/chat_id 입력
5. 명령어 1줄 실행 → Telegram에 메시지 도착 확인

---

## Step 1. 기존 @sajucandle 봇 토큰 가져오기 (BotFather)

> 이미 `@sajucandle` 봇을 BotFather로 만들어두었음. 새로 만들 필요 없고 **토큰만 재확인**하면 됨.
> 과거 `.env` 파일이나 비밀번호 매니저에 토큰이 있다면 그걸 써도 됩니다. 분실했으면 아래 절차로 재발급 받으세요.

1. Telegram 앱에서 검색창에 `@BotFather` 입력
   - 프로필 사진에 **파란 체크마크(공식)** 가 있는 계정을 선택 (가짜 주의!)
2. 대화창 열기 → `/mybots` 전송
3. 내 봇 목록이 나옴 → **`@sajucandle`** 클릭
4. 메뉴에서 `API Token` 누르기
5. 화면에 현재 토큰이 표시됨. 예:
   ```
   You can use this token to access HTTP API:
   123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw
   ```
   **이 토큰을 복사**. 이게 `TELEGRAM_BOT_TOKEN` 값.

### 토큰을 새로 발급받아야 한다면
토큰이 유출됐거나 분실했으면 같은 메뉴에서 `Revoke current token` → 새 토큰 발급.
**주의**: revoke 하면 기존 토큰은 즉시 무효화됨. 다른 곳에서 이 봇을 쓰고 있다면 모두 업데이트 필요.

> ⚠️ **토큰은 비밀번호와 같음.** 카카오톡·GitHub·디스코드에 절대 붙여넣지 말 것. 유출 의심 시 즉시 `Revoke`.

---

## Step 2. 내 chat_id 확인 (@userinfobot)

1. Telegram 앱 검색창에 `@userinfobot` 입력 → 선택
2. 대화 열기 → `/start` 전송
3. 즉시 회신으로 내 정보가 옴:
   ```
   Id: 123456789
   First: 홍길동
   ...
   ```
4. **`Id:` 옆 숫자를 복사**. 이게 `TELEGRAM_ADMIN_CHAT_ID` 값입니다.

---

## Step 3. @sajucandle 봇과 대화 시작 (← 빼먹기 쉬움)

**중요**: Telegram Bot API는 **내가 먼저 봇에게 말을 건 적이 없으면** 메시지를 못 보냄 (403 Forbidden).

1. Telegram 검색창에 **`@sajucandle`** 입력 → 내 봇 선택
2. 봇 프로필 열기 → `시작(START)` 또는 `/start` 전송
3. 봇은 아직 응답 프로그램이 없어서 **아무 답도 안 옴** — 그래도 OK. "말 걸기"만 해두면 서버가 나를 수신자로 인식.

> 과거 이 봇과 이미 대화한 적이 있으면 이 단계는 이미 통과된 상태. 그냥 Step 4로 넘어가도 됨.
> 확실치 않으면 그냥 `/start` 다시 한 번 보내면 안전.

---

## Step 4. `.env` 파일 만들기

프로젝트 루트(`M:/사주캔들/`)에서:

### 방법 A — 터미널 (Git Bash)
```bash
cd "M:/사주캔들"
cp .env.example .env
```

### 방법 B — 메모장
1. 파일 탐색기로 `M:/사주캔들/` 열기
2. `.env.example` 파일 오른쪽 클릭 → 복사 → 붙여넣기
3. 붙여넣은 복사본 이름을 `.env` 로 변경 (점 앞에 아무것도 없음, 확장자 아님)

### 열어서 값 채우기
`.env` 를 메모장으로 열어 다음처럼 수정:

```bash
TRANSPORT_ENABLED=true
TELEGRAM_BOT_TOKEN=123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw
TELEGRAM_ADMIN_CHAT_ID=123456789
TELEGRAM_API_BASE=https://api.telegram.org
```

> 실제 토큰/chat_id는 Step 1, 2에서 받은 값으로. 큰따옴표 붙이지 말 것. 값 뒤에 공백 없도록.

`.env` 는 `.gitignore` 로 자동 제외되므로 git에 커밋되지 않음 — 안전.

---

## Step 5. 실제 실행

Git Bash에서:

```bash
cd "M:/사주캔들"

# .env를 현재 셸에 로드 (1줄)
set -a; source .env; set +a

# 실행 (특정 날짜 지정 → 즉시 1회 실행)
PYTHONPATH=src ./.venv/Scripts/python.exe -m sajucandle.scheduler.runner --date 2026-05-01
```

### 기대 결과

터미널에 이런 로그가 흘러감 (2~3분 소요 — yfinance 주가 수집):
```
2026-04-24 ... [INFO] 월간 신호 생성 시작: 2026-05-01
2026-04-24 ... [INFO] 유니버스: 30종
...
2026-04-24 ... [INFO] BUY: ['WMT', 'CAT', 'AVGO', 'BAC', 'AMD']
2026-04-24 ... [INFO] Telegram 전송 완료 (chat_id=123456789, 1 chunks)
```

**내 Telegram** 에 몇 초 안에 아래 같은 메시지가 도착:

```
📊 사주캔들 2026년 05월 리밸런싱 신호
유니버스 30종 → 사주 통과 26종

🟢 BUY
  WMT      #1   사주 77 / 퀀트 77
  CAT      #2   사주 64 / 퀀트 74
  ...
```

✅ 메시지를 받았다면 **검증 성공**.

---

## 문제 해결 (자주 겪는 에러)

### ❌ "Telegram 전송 실패 status=401"
→ 토큰이 틀림. BotFather에서 `/mybots` → 내 봇 선택 → `API Token` 재확인.

### ❌ "Telegram 전송 실패 status=403 ... Forbidden: bot can't initiate conversation"
→ **Step 3을 안 함.** 내 봇과 대화창 열어서 `/start` 한 번 누를 것.

### ❌ "Telegram 전송 실패 status=400 ... chat not found"
→ `TELEGRAM_ADMIN_CHAT_ID` 에 숫자가 아닌 다른 게 들어감. @userinfobot 에서 **Id: 옆 숫자만** 복사.

### ❌ "Telegram 비활성화 (TRANSPORT_ENABLED=false ...)"
→ `.env` 값이 안 로드됨. 
- `TRANSPORT_ENABLED=true` 정확히 (True, TRUE도 OK / "true" 따옴표 주의)
- `set -a; source .env; set +a` 를 **같은 터미널 세션에서** 실행했는지
- PowerShell이면 `Get-Content .env | ForEach-Object { ... }` 로 별도 로드 필요 → Git Bash 권장

### ❌ "ModuleNotFoundError: No module named 'sajucandle'"
→ `PYTHONPATH=src` 누락. 명령어 복붙 시 맨 앞 `PYTHONPATH=src` 포함 확인.

### ❌ 명령은 통과했는데 Telegram이 안 옴
→ 봇 차단/음소거 확인. Telegram 내 봇 프로필 → 상단 메뉴 → `차단 해제` or `알림 켜기`.

### ❌ "pip: command not found" / venv 에러
→ `.venv` 재생성 필요:
```bash
py -3.14 -m venv .venv
./.venv/Scripts/python.exe -m pip install -e ".[dev]"
```

---

## 드라이런 (토큰 없이 테스트)

실제 전송은 막고 로직만 확인하고 싶을 때:

```bash
PYTHONPATH=src ./.venv/Scripts/python.exe -m sajucandle.scheduler.runner --date 2026-05-01 --no-notify
```

→ `data/signals/2026-05/stock_signals.{json,html,txt}` 만 저장, Telegram 호출 안 함.

---

## 다음 단계 (참고)

- **자동 실행**: `--daemon` 붙이면 매월 1일 09:00 KST 자동 발동 (로컬 PC 켜져 있어야 함)
- **Railway 배포**: PR #2 머지 후 Railway에 `worker` 서비스로 올리면 24/7 자동 실행
- **구독자 추가**: 지금은 관리자 1명. 여러 명 받으려면 C4 (구독자 DB) 또는 β (subscribers.json) 스펙 필요

---

문제가 계속되면 터미널 로그 마지막 20줄을 그대로 복사해서 세션에 붙여넣으면 원인 분석 가능.

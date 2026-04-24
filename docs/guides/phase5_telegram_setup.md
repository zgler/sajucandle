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

## Step 4. `.env` 파일 만들기 (메모장만 써서)

> 터미널을 아직 안 열어도 됩니다. 파일 탐색기 + 메모장으로 충분.

### 4-1. 파일 탐색기에서 프로젝트 폴더 열기
주소 표시줄에 `M:\사주캔들` 입력 후 엔터.

### 4-2. `.env.example` 을 `.env` 로 복사
1. `.env.example` 파일 클릭해서 선택 → `Ctrl+C` (복사)
2. 같은 폴더 빈 곳에서 `Ctrl+V` (붙여넣기)
3. `.env.example - 복사본` 같은 파일이 생김 → 오른쪽 클릭 → `이름 바꾸기`
4. 이름을 **정확히 `.env`** 로 변경 (앞 점 빠뜨리지 말 것, 뒤에 확장자 없음)
   - "파일이 쓸 수 없게 될 수 있습니다" 경고가 뜨면 `예` 클릭
   - 파일명 그대로 `.env` (즉, 이름 없이 확장자만 있는 형태)로 표시됨

> 확장자가 안 보이면: 파일 탐색기 상단 **`보기`** 탭 → **`파일 확장명`** 체크박스 켜기.

### 4-3. 메모장으로 열어서 값 채우기
1. `.env` 파일 오른쪽 클릭 → `연결 프로그램` → `메모장` 선택
2. 안에 이런 내용이 들어 있음:
   ```
   TRANSPORT_ENABLED=false
   TELEGRAM_BOT_TOKEN=
   TELEGRAM_ADMIN_CHAT_ID=
   TELEGRAM_API_BASE=https://api.telegram.org
   ```
3. 아래처럼 수정:
   - `TRANSPORT_ENABLED=false` → **`TRANSPORT_ENABLED=true`**
   - `TELEGRAM_BOT_TOKEN=` 뒤에 **Step 1에서 복사한 토큰 붙여넣기**
   - `TELEGRAM_ADMIN_CHAT_ID=` 뒤에 **Step 2에서 복사한 숫자 붙여넣기**
   - `TELEGRAM_API_BASE=https://api.telegram.org` **그대로 둘 것** (Telegram 공식 서버 주소. 프록시나 자체 Bot API 서버 쓰는 특수 상황에만 바꾸면 됨. 개인 사용자는 건드릴 이유 없음)
4. 최종 결과 예시 (토큰·chat_id는 본인 것으로):
   ```
   TRANSPORT_ENABLED=true
   TELEGRAM_BOT_TOKEN=123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw
   TELEGRAM_ADMIN_CHAT_ID=987654321
   TELEGRAM_API_BASE=https://api.telegram.org
   ```
5. `Ctrl+S` → 저장 → 메모장 닫기

> ⚠️ 흔한 실수
> - `=` 양쪽에 **공백 넣지 말 것** (`TRANSPORT_ENABLED = true` ❌)
> - 값에 **큰따옴표 넣지 말 것** (`"123:abc"` ❌)
> - 값 **끝에 공백/줄바꿈** 없게 (보이지 않지만 파싱 실패 원인)
> - **위·아래 백틱(` ``` `) 복붙 금지** — 이 문서의 코드블록 표시일 뿐. 내용만 4줄 복사
> - 각 줄 **앞 공백/들여쓰기** 금지 — 왼쪽 끝에 붙여 쓸 것

`.env` 는 이미 `.gitignore` 에 포함되어 있어 git에 커밋되지 않음 — 안전.

---

## Step 5. 실제 실행 (Git Bash 터미널)

### 5-1. Git Bash 열기
Windows 시작 메뉴 → `Git Bash` 검색 → 실행.
(Git Bash가 없으면: https://git-scm.com/download/win 에서 설치 → 기본 옵션으로 쭉 `Next`)

Git Bash 창이 열리면 보통 `~` 위치에서 시작. 프로젝트 폴더로 이동이 필요.

### 5-2. 프로젝트 폴더로 이동
Git Bash에 아래 한 줄 복붙 후 엔터:
```bash
cd "/m/사주캔들"
```
> Windows의 `M:\` 드라이브는 Git Bash에서 `/m/` 으로 표기됨 (소문자, 슬래시).
> 잘 이동했는지 확인: `pwd` 치면 `/m/사주캔들` 이 나와야 함.

### 5-3. `.env` 값을 현재 터미널에 로드
```bash
set -a; source .env; set +a
```
**이 한 줄이 하는 일**: `.env` 안의 `TRANSPORT_ENABLED=true` 같은 줄들을 읽어서 **지금 이 터미널에서만** 쓸 수 있는 임시 변수로 등록. 터미널 닫으면 사라짐 (안전).

확인: 아래 명령으로 값이 제대로 실렸는지 확인 가능 (토큰은 보이지 않아도 OK):
```bash
echo "enabled=$TRANSPORT_ENABLED chat_id=$TELEGRAM_ADMIN_CHAT_ID"
```
→ `enabled=true chat_id=987654321` 같은 출력이 나오면 성공.

### 5-4. 실제 실행
```bash
PYTHONPATH=src ./.venv/Scripts/python.exe -m sajucandle.scheduler.runner --date 2026-05-01
```

**명령어 풀이** (알면 디버깅 쉬움):
| 조각 | 의미 |
|---|---|
| `PYTHONPATH=src` | "`src` 폴더에서 파이썬 모듈을 찾아라" |
| `./.venv/Scripts/python.exe` | 프로젝트용 가상환경에 설치된 파이썬 실행 (시스템 파이썬 X) |
| `-m sajucandle.scheduler.runner` | `sajucandle/scheduler/runner.py` 를 메인 모듈로 실행 |
| `--date 2026-05-01` | "2026년 5월 1일" 기준으로 시그널 생성 (과거·미래 아무 날짜나 가능) |

2~3분 걸림 (yfinance에서 30개 종목 주가 수집 때문).

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

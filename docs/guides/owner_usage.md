# 사주캔들 운영자 사용 설명서 (초심자용)

> 이 문서는 "개발자가 아니라 사주캔들을 **매달 실제로 쓸 사람**"을 위한 것입니다.
> 테스트·검증 같은 기술적 내용은 뺐습니다. 당신이 실제로 눌러야 할 버튼과 붙여넣어야 할 명령만 담았습니다.

---

## 0. 먼저 이해할 것 — 이 시스템이 하는 일

- 매월 1일 아침 9시에 자동으로 **"이번 달 주식 5종목 BUY/SELL/WATCH"** 신호를 계산합니다
- 계산 결과를 **`@sajucandle` 봇이 내 Telegram에 메시지로 보냅니다**
- 내가 할 일: 메시지를 보고 증권사 앱에서 실제 거래
- 판단 근거: 사주 필터(< 30점 제외) + 퀀트 랭킹 (기술적·거시·펀더멘털 종합)

---

## 1. 최초 1회만 하는 설정 (한 번 하면 끝)

### 1-1. `@userinfobot` 에서 내 chat_id 받기
신호를 **나에게만 보내기 위해** Telegram이 나를 식별할 번호가 필요합니다.

1. Telegram 앱 → 검색창 → `@userinfobot`
2. 대화창에서 `/start` 전송
3. 회신으로 `Id: 123456789` 같은 **숫자 9~10자리** 가 옴 → **이 숫자를 메모**

### 1-2. `@sajucandle` 봇에 "말 걸기"
Telegram은 사용자가 먼저 봇에게 말을 건 적이 없으면 봇이 사용자에게 메시지를 못 보냅니다. (보안 정책)

1. Telegram 앱 → 검색창 → `@sajucandle`
2. 대화창 열기 → `/start` 한 번 전송
3. 봇이 답을 안 해도 OK. "말 걸기"만 성공하면 됨.

> 과거 이 봇과 이미 대화한 적 있으면 이 단계는 건너뛰어도 됩니다.

### 1-3. `@sajucandle` 봇 토큰 받기
봇 계정의 비밀번호 같은 것. `.env` 파일에 넣기 위함.

1. Telegram → 검색 → `@BotFather` (파란 체크 공식 계정)
2. `/mybots` 전송
3. 목록에서 `@sajucandle` 선택
4. `API Token` 버튼 → 토큰 표시됨 → **메모** (예: `123456789:AAH...`)

### 1-4. `.env` 파일 작성
프로젝트 폴더 `M:\사주캔들\` 안에 있는 설정 파일입니다. 이 안에 토큰과 chat_id를 넣으면 시스템이 사용.

**가장 확실한 방법 — Git Bash에서 아래 3줄 실행**:

```bash
cd "/m/사주캔들"
```

```bash
read -s -p "Bot Token 붙여넣기(1-3 토큰): " TOKEN; echo
read -p "Chat ID 숫자(1-1 chat_id): " CHATID
cat > .env << EOF
TRANSPORT_ENABLED=true
TELEGRAM_BOT_TOKEN=${TOKEN}
TELEGRAM_ADMIN_CHAT_ID=${CHATID}
TELEGRAM_API_BASE=https://api.telegram.org
EOF
unset TOKEN CHATID
```

- 첫 명령에서 `Bot Token 붙여넣기:` 가 뜨면 1-3에서 받은 토큰을 **우클릭 → 붙여넣기** 하고 엔터. (화면에 안 보이지만 입력되는 중)
- 이어서 `Chat ID 숫자:` → 1-1에서 받은 숫자 붙여넣고 엔터.
- 자동으로 `.env` 파일이 만들어집니다.

이제 **1.은 끝**. 앞으로 매달 쓸 때는 2.만 하면 됩니다.

---

## 2. 매월 1일 (반복 — 이것만 하면 됨)

### 방법 A — 수동 (PC 켤 때 내가 직접)
매달 1일 오전에 컴퓨터 켜고 아래 한 번만 하면 됩니다.

1. Windows 시작 메뉴 → `Git Bash` 실행
2. 아래 한 줄 복붙 → 엔터:
   ```bash
   cd "/m/사주캔들" && set -a && source .env && set +a && PYTHONPATH=src ./.venv/Scripts/python.exe -m sajucandle.scheduler.runner
   ```
3. 2~3분 기다림 (주가 데이터 수집 중)
4. 내 Telegram에 `@sajucandle` 으로부터 메시지 도착
5. 메시지 보고 증권사 앱에서 거래

메시지 예시:
```
📊 사주캔들 2026년 05월 리밸런싱 신호
유니버스 30종 → 사주 통과 27종

🟢 BUY
  AMD      #5   사주 38 / 퀀트 71

🔵 HOLD
  WMT      #1   사주 75 / 퀀트 77
  CAT      #2   ...

🔴 SELL
  NVDA     #6   사주 47 / 퀀트 71

📋 이번 달 보유: AMD AVGO BAC CAT WMT
```

- 🟢 BUY: 새로 살 것
- 🔵 HOLD: 이미 가진 것, 유지
- 🔴 SELL: 이미 가진 것, 정리
- 🟡 WATCH: 아직 아님, 지켜볼 것
- ⚫ KILL: 사주 점수 낮음, 제외

### 방법 B — 완전 자동화 (내가 아무것도 안 해도 됨)
**옵션 B-1: 내 PC 24시간 켜두기**
1. Git Bash에서 아래 실행 (한 번만):
   ```bash
   cd "/m/사주캔들" && set -a && source .env && set +a && PYTHONPATH=src ./.venv/Scripts/python.exe -m sajucandle.scheduler.runner --daemon
   ```
2. 이 터미널을 **닫지 않고 최소화만**. PC가 켜져 있는 한 매월 1일 09:00 KST에 자동 실행.
3. PC 끄거나 터미널 닫으면 멈춤 → 다시 1번 실행해야 재개.

**옵션 B-2: Railway 클라우드 배포 (PC 꺼도 됨, 월 약 $5)**
- 별도 설정 과정이 있음. 원하면 따로 가이드 작성 가능 (이 스펙 범위 밖).

---

## 3. 문제 생겼을 때

### 명령 실행은 되는데 Telegram에 메시지가 안 와요
터미널 맨 아랫줄 로그를 봅니다:

| 로그 | 원인 | 해결 |
|---|---|---|
| `Telegram 전송 완료 (...)` | 성공. Telegram 앱 확인 | 봇 알림 꺼져 있는지 확인 |
| `Telegram 비활성화 (TRANSPORT_ENABLED=false ...)` | `.env` 로딩 실패 | `cd "/m/사주캔들" && set -a && source .env && set +a` 를 **같은 터미널**에서 다시 실행 |
| `Telegram 전송 실패 status=401` | 토큰 틀림 | 1-3 다시 해서 토큰 재확인 + `.env` 재작성 |
| `Telegram 전송 실패 status=403 ... Forbidden` | 봇에 /start 안 함 | 1-2 다시 |
| `Telegram 전송 실패 status=400 ... chat not found` | chat_id 틀림 | 1-1 다시 |

### `ModuleNotFoundError: No module named 'sajucandle'`
→ 명령어 맨 앞에 `PYTHONPATH=src` 가 빠졌거나 `cd "/m/사주캔들"` 을 안 함.

### `pip: command not found` / Python 에러
→ `.venv` 가 깨짐. 아래 명령 한 번 실행하면 복구:
```bash
cd "/m/사주캔들" && py -3.14 -m venv .venv --clear && ./.venv/Scripts/python.exe -m pip install -e ".[dev]"
```
(약 3~5분 소요. 한 번 하면 끝.)

---

## 4. 나중에 고려할 것 (지금은 안 해도 됨)

### 여러 명에게 신호 보내기
현재는 **관리자 1명(나)** 에게만 전송. 다른 사람도 받게 하려면 추가 개발 필요:
- 구독자 DB 기능 (`docs/phase5 C4` 로 나중에 계획)
- 가입/해지 웹페이지
- (유료라면) 결제 연동

### 이메일로도 받기
Telegram 외에 이메일도 원하면 별도 개발. 현재 범위 밖.

### 신호 종목 유니버스 바꾸기
`data/tickers/stock_universe_30.csv` 파일을 열어 종목 추가/제거. 단, 새 종목은 **상장일 명시** 필요 (사주 계산용).

### 신호 검증 결과 다시 보기
`PHASE4_HANDOVER.md` 열면 백테스트 결과·통계 볼 수 있음:
- 주식 C필터 <30: CAGR 14.0%, Sharpe 0.97, MDD −14.8% (SPY 13.0%/0.90/−33.7% 대비)
- 코인 C필터 <30: CAGR 85.8%, Sharpe 0.93

---

## 5. 요약 (제일 중요)

**딱 3가지만 기억하세요**:
1. **최초 1회**: `@userinfobot` chat_id 받기 + `@sajucandle` 에 `/start` + `.env` 작성
2. **매월 1일**: Git Bash 열고 한 줄 복붙 (또는 `--daemon` 으로 상시)
3. **메시지 보고 증권사 앱에서 거래**

끝.

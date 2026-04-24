# Week 1: Telegram Bot Bootstrap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Telegram bot이 로컬에서 실행되고 `/start 1990-03-15 14:00` 같은 커맨드에 명식(四柱) 카드로 응답. Railway 배포 가능한 상태까지.

**Architecture:** `python-telegram-bot` v20+ (async) 기반 단일 프로세스. 기존 프로토타입 `saju_engine.py`를 저장소로 복사·정리해 엔진으로 사용. 만세력 계산은 `lunar_python` 런타임 (Redis 캐싱은 Week 2에 추가).

**Tech Stack:** Python 3.12, python-telegram-bot 21.x, lunar_python, pytest, uv (패키지 관리)

**범위 밖 (Week 2+):** FastAPI 분리, Redis 캐싱, 차트 엔진, KIS/yfinance, Next.js, Supabase

**사람이 직접 해야 하는 작업 (코드 아님):**
- BotFather에서 `@sajucandle_bot` 등록 → `BOT_TOKEN` 획득
- Railway 계정 생성, GitHub 저장소 연결
- KIS OpenAPI 신청 접수 (Week 3부터 사용)

---

## File Structure

```
D:\사주캔들\
├── .gitignore               # Python + IDE 기본
├── .env.example             # BOT_TOKEN 플레이스홀더
├── README.md                # 개발자 셋업 가이드
├── pyproject.toml           # uv/pip 의존성
├── railway.toml             # Railway 빌드/시작 커맨드
├── Procfile                 # Railway 런처 대체 옵션
├── src/
│   └── sajucandle/
│       ├── __init__.py
│       ├── saju_engine.py   # 기존 프로토타입 복사 + line 596 수정
│       ├── format.py        # 명식 카드 텍스트 렌더러
│       ├── handlers.py      # /start 커맨드 핸들러
│       └── bot.py           # 엔트리 포인트 (Application 생성 + run_polling)
├── tests/
│   ├── __init__.py
│   ├── test_format.py       # 명식 카드 포맷 테스트
│   └── test_handlers.py     # /start 파싱 테스트
└── docs/
    └── superpowers/
        ├── specs/           # 이미 존재
        └── plans/           # 이 파일 포함
```

**설계 포인트:**
- `saju_engine.py`는 프로토타입 그대로 유지 (Week 2 FastAPI 분리 때 재배치). 단, 하드코딩 버그 1줄만 제거.
- `format.py`는 pure function (입력: BaziChart → 출력: str). 테스트 용이, 추후 웹 카드와 공유 가능.
- `handlers.py`는 텔레그램 의존성과 엔진 호출을 분리하는 얇은 층. 파싱 로직 단위 테스트 가능.
- `bot.py`는 wiring만. 테스트 안 함.

---

## Task 1: 프로젝트 스캐폴딩

**Files:**
- Create: `D:\사주캔들\.gitignore`
- Create: `D:\사주캔들\pyproject.toml`
- Create: `D:\사주캔들\src\sajucandle\__init__.py`
- Create: `D:\사주캔들\tests\__init__.py`

- [ ] **Step 1: `.gitignore` 작성**

```gitignore
# Python
__pycache__/
*.py[cod]
*$py.class
*.egg-info/
dist/
build/
.pytest_cache/
.ruff_cache/

# Virtual envs
.venv/
venv/
env/

# Env files
.env
.env.local

# IDE
.idea/
.vscode/
*.swp
.DS_Store

# OS
Thumbs.db
```

- [ ] **Step 2: `pyproject.toml` 작성**

```toml
[project]
name = "sajucandle"
version = "0.1.0"
description = "SajuCandle Telegram bot - daily trading entry signals combining Saju score with chart analysis"
requires-python = ">=3.12"
dependencies = [
    "python-telegram-bot>=21.0,<22.0",
    "lunar-python>=1.4.4",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "ruff>=0.4",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/sajucandle"]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
pythonpath = ["src"]

[tool.ruff]
line-length = 100
target-version = "py312"
```

- [ ] **Step 3: 빈 패키지 초기화**

Create `src/sajucandle/__init__.py` with content:
```python
__version__ = "0.1.0"
```

Create `tests/__init__.py` with empty content.

- [ ] **Step 4: 가상환경 + 의존성 설치 (로컬 검증)**

Run:
```bash
cd "D:/사주캔들"
python -m venv .venv
source .venv/Scripts/activate  # Windows bash
pip install -e ".[dev]"
```

Expected: 설치 성공 메시지, `pip list`에 `python-telegram-bot`, `lunar-python`, `pytest` 보임.

- [ ] **Step 5: Commit**

```bash
git add .gitignore pyproject.toml src/sajucandle/__init__.py tests/__init__.py
git commit -m "chore: scaffold Python package with python-telegram-bot and lunar-python"
```

---

## Task 2: 프로토타입 엔진 복사 + 하드코딩 버그 제거

**Files:**
- Create: `D:\사주캔들\src\sajucandle\saju_engine.py` (프로토타입 복사)
- Modify: `D:\사주캔들\src\sajucandle\saju_engine.py` (line 596 부근 placeholder 제거)

- [ ] **Step 1: 프로토타입 파일 복사**

Run:
```bash
cp "C:/Users/user/Documents/카카오톡 받은 파일/files/saju_engine.py" "D:/사주캔들/src/sajucandle/saju_engine.py"
```

- [ ] **Step 2: `saju_engine.py`에서 하드코딩 Solar 날짜 찾기**

Run:
```bash
grep -n "Solar.fromYmd(2026, 4, 15)" "D:/사주캔들/src/sajucandle/saju_engine.py"
```
Expected: 596번 라인(또는 근처)에 `solar = Solar.fromYmd(2026, 4, 15)  # placeholder` 출력.

- [ ] **Step 3: 하드코딩된 Solar 참조 제거**

`_calc_volatility` 함수 내부의 다음 라인을 삭제:
```python
solar = Solar.fromYmd(2026, 4, 15)  # placeholder; 실제론 파라미터에서 받아야
```
해당 변수 `solar`가 함수 뒤쪽에서 사용되지 않는지 `grep "solar"` 로 재확인하고, 사용된다면 함수 인자로 받는 `solar` 파라미터로 대체. (볼라틸리티 계산이 독립 연산이면 함수 자체가 필요 없는지도 검토 — 남겨도 기능 영향 없음.)

- [ ] **Step 4: 엔진 임포트 smoke test**

Run:
```bash
cd "D:/사주캔들"
python -c "from sajucandle.saju_engine import SajuEngine; e = SajuEngine(); chart = e.calc_bazi(1990, 3, 15, 14); print(chart)"
```
Expected: BaziChart 객체 출력 (예: `BaziChart(year='庚午', month='己卯', day='己卯', hour='辛未', ...)`). 에러 없이 통과.

- [ ] **Step 5: Commit**

```bash
git add src/sajucandle/saju_engine.py
git commit -m "feat: import saju engine from prototype, drop hardcoded Solar placeholder"
```

---

## Task 3: 명식 카드 포매터 (TDD)

**Files:**
- Create: `D:\사주캔들\tests\test_format.py`
- Create: `D:\사주캔들\src\sajucandle\format.py`

- [ ] **Step 1: 실패하는 테스트 작성**

Create `tests/test_format.py`:
```python
from sajucandle.saju_engine import SajuEngine
from sajucandle.format import render_bazi_card


def test_render_bazi_card_contains_four_pillars():
    """명식 카드는 연주/월주/일주/시주 4개 기둥을 모두 포함해야 한다."""
    engine = SajuEngine()
    chart = engine.calc_bazi(1990, 3, 15, 14)

    card = render_bazi_card(chart, birth_str="1990-03-15 14:00")

    # 1990-03-15 14시는 프로토타입 예제: 庚午 己卯 己卯 辛未
    assert "庚午" in card
    assert "己卯" in card
    assert "辛未" in card
    assert "1990-03-15 14:00" in card


def test_render_bazi_card_has_header_and_day_master():
    """카드 상단에 생년월일시와 일간(day master) 표시."""
    engine = SajuEngine()
    chart = engine.calc_bazi(1990, 3, 15, 14)

    card = render_bazi_card(chart, birth_str="1990-03-15 14:00")

    assert "명식" in card or "四柱" in card
    # 일간: 己 (土)
    assert "일간" in card
    assert "己" in card


def test_render_bazi_card_is_plain_text_safe_for_telegram():
    """Telegram 메시지용 — 마크다운 특수문자 이스케이프 없이도 깨지지 않는 plain text."""
    engine = SajuEngine()
    chart = engine.calc_bazi(1990, 3, 15, 14)

    card = render_bazi_card(chart, birth_str="1990-03-15 14:00")

    # Telegram MarkdownV2 특수문자가 의도치 않게 섞이지 않음 (_*[]()~`>#+-=|{}.!)
    # 우리는 plain text 모드로 보낼 거라 이 테스트는 '카드가 비어있지 않음' + '줄바꿈 포함' 정도만 확인
    assert len(card) > 50
    assert "\n" in card
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

Run:
```bash
cd "D:/사주캔들"
pytest tests/test_format.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'sajucandle.format'`

- [ ] **Step 3: `format.py` 최소 구현**

Create `src/sajucandle/format.py`:
```python
"""명식(사주) 카드 렌더러. Telegram plain text 모드용."""
from sajucandle.saju_engine import BaziChart


def render_bazi_card(chart: BaziChart, birth_str: str) -> str:
    """BaziChart를 Telegram 메시지용 plain text 카드로 변환.

    Args:
        chart: SajuEngine.calc_bazi() 결과
        birth_str: 사용자가 입력한 생년월일시 문자열 (예: "1990-03-15 14:00")

    Returns:
        여러 줄의 plain text. Telegram sendMessage(parse_mode=None)로 전송 가능.
    """
    day_gan = chart.day[0]  # 일간 (예: 己)

    lines = [
        "🕯️ 사주캔들 명식",
        "─────────────",
        f"생년월일시: {birth_str}",
        "",
        f"연주: {chart.year}",
        f"월주: {chart.month}",
        f"일주: {chart.day}  ← 일간 {day_gan}",
        f"시주: {chart.hour}",
        "",
        "※ 엔터테인먼트 목적. 투자 추천 아님.",
    ]
    return "\n".join(lines)
```

- [ ] **Step 4: 테스트 재실행 — 통과 확인**

Run:
```bash
pytest tests/test_format.py -v
```
Expected: 3 tests PASSED.

- [ ] **Step 5: Commit**

```bash
git add tests/test_format.py src/sajucandle/format.py
git commit -m "feat: add plain-text bazi card renderer for Telegram"
```

---

## Task 4: `/start` 커맨드 파싱 로직 (TDD)

**Files:**
- Create: `D:\사주캔들\tests\test_handlers.py`
- Create: `D:\사주캔들\src\sajucandle\handlers.py`

- [ ] **Step 1: 실패하는 파싱 테스트 작성**

Create `tests/test_handlers.py`:
```python
import pytest
from sajucandle.handlers import parse_birth_args, BirthParseError


def test_parse_birth_args_valid():
    args = ["1990-03-15", "14:00"]
    result = parse_birth_args(args)
    assert result == (1990, 3, 15, 14, 0)


def test_parse_birth_args_with_seconds_ignored():
    args = ["1990-03-15", "14:00:30"]
    result = parse_birth_args(args)
    assert result == (1990, 3, 15, 14, 0)


def test_parse_birth_args_hour_only():
    """시:분 없이 시만 온 경우도 허용 (분 기본 0)."""
    args = ["1990-03-15", "14"]
    result = parse_birth_args(args)
    assert result == (1990, 3, 15, 14, 0)


def test_parse_birth_args_empty_raises():
    with pytest.raises(BirthParseError):
        parse_birth_args([])


def test_parse_birth_args_missing_time_raises():
    with pytest.raises(BirthParseError):
        parse_birth_args(["1990-03-15"])


def test_parse_birth_args_bad_date_format_raises():
    with pytest.raises(BirthParseError):
        parse_birth_args(["1990/03/15", "14:00"])


def test_parse_birth_args_invalid_hour_raises():
    with pytest.raises(BirthParseError):
        parse_birth_args(["1990-03-15", "25:00"])


def test_parse_birth_args_invalid_month_raises():
    with pytest.raises(BirthParseError):
        parse_birth_args(["1990-13-15", "14:00"])
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

Run:
```bash
pytest tests/test_handlers.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'sajucandle.handlers'`

- [ ] **Step 3: `handlers.py` 최소 구현 (핸들러는 Task 5, 파서만 먼저)**

Create `src/sajucandle/handlers.py`:
```python
"""Telegram 커맨드 핸들러 + 인자 파싱 유틸."""
from __future__ import annotations

from datetime import datetime

from sajucandle.format import render_bazi_card
from sajucandle.saju_engine import SajuEngine


class BirthParseError(ValueError):
    """사용자 생년월일시 인자 파싱 실패."""


def parse_birth_args(args: list[str]) -> tuple[int, int, int, int, int]:
    """`/start YYYY-MM-DD HH:MM` 인자를 (year, month, day, hour, minute) 튜플로.

    허용 포맷:
      - `YYYY-MM-DD HH:MM`
      - `YYYY-MM-DD HH:MM:SS` (초는 무시)
      - `YYYY-MM-DD HH`       (분 = 0)

    Raises:
        BirthParseError: 인자 부족, 포맷 오류, 값 범위 오류.
    """
    if len(args) < 2:
        raise BirthParseError(
            "사용법: /start YYYY-MM-DD HH:MM\n예: /start 1990-03-15 14:00"
        )

    date_str, time_str = args[0], args[1]

    try:
        date_part = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError as e:
        raise BirthParseError(f"날짜 형식이 잘못되었습니다 (YYYY-MM-DD): {date_str}") from e

    time_formats = ["%H:%M:%S", "%H:%M", "%H"]
    time_part = None
    for fmt in time_formats:
        try:
            time_part = datetime.strptime(time_str, fmt).time()
            break
        except ValueError:
            continue
    if time_part is None:
        raise BirthParseError(f"시각 형식이 잘못되었습니다 (HH:MM): {time_str}")

    return (
        date_part.year,
        date_part.month,
        date_part.day,
        time_part.hour,
        time_part.minute,
    )
```

- [ ] **Step 4: 테스트 재실행 — 통과 확인**

Run:
```bash
pytest tests/test_handlers.py -v
```
Expected: 8 tests PASSED.

- [ ] **Step 5: Commit**

```bash
git add tests/test_handlers.py src/sajucandle/handlers.py
git commit -m "feat: add /start birth-args parser with format validation"
```

---

## Task 5: `/start` Telegram 핸들러 연결

**Files:**
- Modify: `D:\사주캔들\src\sajucandle\handlers.py` (핸들러 함수 추가)

- [ ] **Step 1: 통합 핸들러 함수 추가**

Append to `src/sajucandle/handlers.py`:
```python
from telegram import Update
from telegram.ext import ContextTypes

# 엔진은 프로세스 수명 동안 1개만 유지 (lunar_python 초기화 비용은 무시 가능하지만 관례)
_engine = SajuEngine()


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """`/start YYYY-MM-DD HH:MM` 커맨드. 명식 카드로 응답."""
    if update.message is None:
        return

    try:
        year, month, day, hour, _minute = parse_birth_args(context.args or [])
    except BirthParseError as e:
        await update.message.reply_text(str(e))
        return

    try:
        chart = _engine.calc_bazi(year, month, day, hour)
    except Exception as e:  # lunar_python 내부 에러
        await update.message.reply_text(
            f"명식 계산 중 문제가 발생했습니다. 날짜를 다시 확인해주세요.\n({type(e).__name__})"
        )
        return

    birth_str = f"{year:04d}-{month:02d}-{day:02d} {hour:02d}:{_minute:02d}"
    card = render_bazi_card(chart, birth_str=birth_str)
    await update.message.reply_text(card)
```

- [ ] **Step 2: 핸들러 임포트 smoke test**

Run:
```bash
cd "D:/사주캔들"
python -c "from sajucandle.handlers import start_command; print('ok')"
```
Expected: `ok` 출력.

- [ ] **Step 3: Commit**

```bash
git add src/sajucandle/handlers.py
git commit -m "feat: wire /start handler to saju engine + bazi card"
```

---

## Task 6: 봇 엔트리 포인트

**Files:**
- Create: `D:\사주캔들\src\sajucandle\bot.py`
- Create: `D:\사주캔들\.env.example`

- [ ] **Step 1: `.env.example` 작성**

Create `.env.example`:
```
# Telegram BotFather에서 발급받은 토큰. 코드에 커밋 금지.
BOT_TOKEN=paste-your-bot-token-here
```

- [ ] **Step 2: `bot.py` 엔트리 포인트 작성**

Create `src/sajucandle/bot.py`:
```python
"""Telegram 봇 엔트리 포인트. Railway 또는 로컬에서 실행."""
from __future__ import annotations

import logging
import os
import sys

from telegram.ext import Application, CommandHandler

from sajucandle.handlers import start_command


def _configure_logging() -> None:
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO,
    )
    # telegram 라이브러리 자체는 WARNING 이상만
    logging.getLogger("httpx").setLevel(logging.WARNING)


def main() -> None:
    _configure_logging()

    token = os.environ.get("BOT_TOKEN")
    if not token:
        print("ERROR: BOT_TOKEN 환경변수가 설정되지 않았습니다.", file=sys.stderr)
        print("로컬 실행 예: BOT_TOKEN=xxx python -m sajucandle.bot", file=sys.stderr)
        sys.exit(1)

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start_command))

    logging.info("SajuCandle bot starting (polling mode)...")
    app.run_polling()


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: 실 토큰으로 로컬 스모크 테스트 (수동)**

BotFather에서 발급받은 토큰이 있다고 가정. 없으면 이 스텝은 건너뛰고 Task 7로.

Run:
```bash
cd "D:/사주캔들"
export BOT_TOKEN="<실제_토큰>"
python -m sajucandle.bot
```
Expected: 로그에 "SajuCandle bot starting (polling mode)..." 출력, 에러 없이 대기 상태 유지.

Telegram에서 봇에게 `/start 1990-03-15 14:00` 메시지 전송 → 명식 카드 응답 수신.

Ctrl+C로 종료.

- [ ] **Step 4: Commit**

```bash
git add src/sajucandle/bot.py .env.example
git commit -m "feat: add bot entry point with polling and BOT_TOKEN env check"
```

---

## Task 7: Railway 배포 설정

**Files:**
- Create: `D:\사주캔들\railway.toml`
- Create: `D:\사주캔들\Procfile`

- [ ] **Step 1: `Procfile` 작성 (Railway/Heroku 호환)**

Create `Procfile`:
```
worker: python -m sajucandle.bot
```

참고: 봇은 웹 서버가 아니라 polling 워커라 `worker` 프로세스 타입. Railway는 `web`/`worker` 둘 다 지원.

- [ ] **Step 2: `railway.toml` 작성 (Nixpacks 빌드 힌트)**

Create `railway.toml`:
```toml
[build]
builder = "NIXPACKS"

[deploy]
startCommand = "python -m sajucandle.bot"
restartPolicyType = "ON_FAILURE"
restartPolicyMaxRetries = 3
```

- [ ] **Step 3: Commit**

```bash
git add Procfile railway.toml
git commit -m "chore: add Railway deploy config (worker process for polling bot)"
```

---

## Task 8: README

**Files:**
- Create: `D:\사주캔들\README.md`

- [ ] **Step 1: README 작성**

Create `README.md`:
```markdown
# 사주캔들 (SajuCandle)

사주 점수와 차트 분석을 결합한 트레이딩 진입 신호 서비스 (MVP).

⚠️ 엔터테인먼트 + 판단 보조 목적. 투자 추천 아님.

## Week 1 범위

Telegram 봇이 `/start YYYY-MM-DD HH:MM` 커맨드에 명식(四柱) 카드로 응답.

## 로컬 실행

사전 요구: Python 3.12+, BotFather에서 발급받은 토큰.

```bash
# 가상환경
python -m venv .venv
source .venv/Scripts/activate   # Windows bash
# macOS/Linux: source .venv/bin/activate

# 설치
pip install -e ".[dev]"

# 토큰 설정 (커밋 금지)
cp .env.example .env
# .env 열어서 BOT_TOKEN 채우기

# 실행
export BOT_TOKEN=$(grep BOT_TOKEN .env | cut -d= -f2)
python -m sajucandle.bot
```

Telegram에서 봇에게 `/start 1990-03-15 14:00` 전송 → 명식 카드 수신.

## 테스트

```bash
pytest
```

## 배포 (Railway)

1. GitHub에 push
2. Railway에서 New Project → Deploy from GitHub Repo
3. 환경변수 `BOT_TOKEN` 설정
4. `railway.toml`의 `startCommand`가 자동 실행됨

## 프로젝트 구조

- `src/sajucandle/saju_engine.py` — 사주 계산 엔진 (프로토타입 이식)
- `src/sajucandle/format.py` — 명식 카드 렌더러
- `src/sajucandle/handlers.py` — `/start` 커맨드 파싱 + 핸들러
- `src/sajucandle/bot.py` — 엔트리 포인트
- `docs/superpowers/specs/` — 설계 문서
- `docs/superpowers/plans/` — 구현 플랜

## 다음 주차 (범위 밖)

- Week 2: FastAPI 분리, Redis 만세력 캐시, `/bazi` `/saju-score` 엔드포인트
- Week 3: Next.js 웹, Supabase Auth, `/recommend` UI
- 전체 스펙: `docs/superpowers/specs/2026-04-15-python-ts-engine-strategy-design.md`
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add README with local setup and Railway deploy steps"
```

---

## Task 9: 최종 통합 검증

**Files:** (새 파일 없음, 실행만)

- [ ] **Step 1: 전체 테스트 실행**

Run:
```bash
cd "D:/사주캔들"
pytest -v
```
Expected: 11 tests PASSED (format 3 + handlers 8), 실패 0.

- [ ] **Step 2: 패키지 임포트 smoke test**

Run:
```bash
python -c "from sajucandle import bot, handlers, format, saju_engine; print('all imports ok')"
```
Expected: `all imports ok` 출력.

- [ ] **Step 3: git 상태 깨끗한지 확인**

Run:
```bash
git status
```
Expected: `nothing to commit, working tree clean`.

- [ ] **Step 4: 로그 훑기**

Run:
```bash
git log --oneline
```
Expected: 최소 8개 커밋 (스펙 커밋 + Task 1-8 각 1개 이상).

---

## 완료 기준

- [ ] 로컬에서 실 토큰 + `/start 1990-03-15 14:00` → 명식 카드 수신 확인 (수동)
- [ ] `pytest` 전부 통과
- [ ] Railway에 push 후 봇이 온라인 상태 (수동)

## 다음 플랜으로 넘어가기 전에

- `@sajucandle_bot` BotFather 등록 완료됐는지
- KIS OpenAPI 신청 접수됐는지 (3주 뒤 Week 3에서 사용)
- Week 2 플랜 작성: FastAPI 분리 + Redis 만세력 캐시 + `/bazi` `/saju-score` 엔드포인트

# Week 3: Saju Score API + `/score` Bot Command Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 사용자가 생년월일시를 한 번만 등록(`/start`)하면, 매일 `/score`로 그날의 4-축 일진 점수 + 추천 시진을 받는다. 점수 계산 로직은 이미 `saju_engine.py`에 있으니 이번 주는 **Supabase 영속 저장 + API 노출 + 봇 HTTP 통합**만.

**Architecture:** 봇은 DB/엔진에 직접 연결하지 않고 httpx로 API만 호출한다. API는 FastAPI + asyncpg 풀 + Supabase Postgres + Upstash Redis. 4개 신규 엔드포인트(`/v1/users/*`, `/v1/users/{chat_id}/score`)와 5개 봇 커맨드(`/start`, `/score`, `/me`, `/forget`, `/help`).

**Tech Stack:** asyncpg 0.29+, httpx 0.27+, respx 0.21+ (테스트), pytest-asyncio 0.23+ (기존), Supabase Postgres, FastAPI lifespan.

**Spec:** `docs/superpowers/specs/2026-04-16-week3-saju-score-design.md`

**Out of scope (Week 4+):** 점수 이력 테이블, 주간 리포트, 다중 명식, Alembic 자동 마이그레이션, 종목별 가중치 튜닝.

---

## 사람이 직접 해야 하는 작업 (Task 19/20에서 안내)

- Supabase 프로젝트 `sajucandle-db` 생성 → Settings → Database → Connection string (URI, `postgresql+asyncpg://` 아님 주의) 복사 → `DATABASE_URL` env
- Supabase Studio SQL Editor에서 `migrations/001_init.sql` 실행
- 로컬 개발용 `TEST_DATABASE_URL` 설정 (Supabase의 같은 DB 또는 별도 스키마/DB)
- Railway `sajucandle-api` 서비스에 `DATABASE_URL` env 추가
- Railway `sajucandle-bot` 서비스에 `SAJUCANDLE_API_BASE_URL` env 추가 (예: `https://sajucandle-api-production.up.railway.app`)

---

## File Structure 변경

```
src/sajucandle/
├── api.py              # MOD: lifespan + 신규 엔드포인트 4개 + /health DB 핑
├── api_client.py       # NEW: 봇용 httpx 래퍼
├── cache.py            # MOD: score 캐시용 set_with_ttl 추가
├── cached_engine.py    # 변경 없음
├── db.py               # NEW: asyncpg Pool 싱글톤 + lifespan hook
├── handlers.py         # MOD: 전부 api_client 호출로 리팩터
├── models.py           # MOD: 신규 Pydantic 모델 5개 추가
├── repositories.py     # NEW: users + user_bazi CRUD
├── score_service.py    # NEW: ScoreCard → SajuScoreResponse 변환 + 캐시 래핑
└── bot.py              # MOD: 새 핸들러 등록

migrations/
└── 001_init.sql        # NEW: users + user_bazi 스키마

tests/
├── conftest.py                # NEW or MOD: DB 트랜잭션 롤백 fixture, httpx TestClient
├── test_api_client.py         # NEW: respx mock
├── test_api_score.py          # NEW: GET /v1/users/.../score
├── test_api_users.py          # NEW: PUT/GET/DELETE /v1/users
├── test_db.py                 # NEW: pool lifecycle
├── test_handlers.py           # MOD: api_client 기반으로 재작성
├── test_repositories.py       # NEW: CRUD 단위
└── test_score_service.py      # NEW: ScoreCard 변환 + 캐시 TTL
```

**설계 포인트:**
- `db.py`는 오직 asyncpg Pool 싱글톤만 관리. 쿼리는 `repositories.py`에.
- `score_service.py`는 `SajuEngine.calc_daily_score()` 호출 + `ScoreCard` → Pydantic 변환 + Redis 캐시를 전부 책임. API 엔드포인트는 얇게 유지.
- `api_client.py`는 봇이 쓰는 얇은 httpx 래퍼. 에러 4종(NotFound, Timeout, NetworkError, ApiError)만 던진다.
- 테스트 DB는 `TEST_DATABASE_URL` env 필수. 없으면 DB 관련 테스트는 skip. 각 테스트는 outer transaction에서 rollback.

---

## Task 1: 의존성 추가

**Files:**
- Modify: `D:\사주캔들\pyproject.toml`

- [ ] **Step 1: `pyproject.toml`에 의존성 추가**

`[project] dependencies`에 추가:
```toml
    "asyncpg>=0.29,<1.0",
    "httpx>=0.27",
```

`[project.optional-dependencies] dev`에 추가 (httpx는 이미 있으면 중복 제거):
```toml
    "respx>=0.21",
```

최종 형태 예시:
```toml
dependencies = [
    "python-telegram-bot>=21.0,<22.0",
    "lunar-python>=1.4.4",
    "fastapi>=0.110,<1.0",
    "uvicorn[standard]>=0.27",
    "redis>=5.0,<6.0",
    "pydantic>=2.0,<3.0",
    "asyncpg>=0.29,<1.0",
    "httpx>=0.27",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "ruff>=0.4",
    "fakeredis>=2.20",
    "respx>=0.21",
]
```
(`httpx`는 runtime으로 옮겼으니 dev에서 제거.)

- [ ] **Step 2: 재설치**

```bash
cd "D:/사주캔들"
.venv/Scripts/python.exe -m pip install -e ".[dev]"
```
Expected: `asyncpg`, `respx` 신규 설치. `httpx` 이미 있음.

- [ ] **Step 3: 임포트 스모크 체크**

```bash
.venv/Scripts/python.exe -c "import asyncpg, httpx, respx; print('ok')"
```
Expected: `ok`

- [ ] **Step 4: 커밋**

```bash
git add pyproject.toml
git commit -m "chore: add asyncpg + httpx (runtime) + respx (test) for Week 3"
```

---

## Task 2: SQL 마이그레이션 파일

**Files:**
- Create: `D:\사주캔들\migrations\001_init.sql`

- [ ] **Step 1: `migrations/` 디렉토리 + 파일 생성**

파일 내용:
```sql
-- Week 3 초기 스키마.
-- 실행: Supabase Studio → SQL Editor → Run.
-- 로컬: psql $DATABASE_URL -f migrations/001_init.sql

CREATE TABLE IF NOT EXISTS users (
    telegram_chat_id BIGINT PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS user_bazi (
    telegram_chat_id BIGINT PRIMARY KEY
        REFERENCES users(telegram_chat_id) ON DELETE CASCADE,
    birth_year  INT NOT NULL CHECK (birth_year BETWEEN 1900 AND 2100),
    birth_month INT NOT NULL CHECK (birth_month BETWEEN 1 AND 12),
    birth_day   INT NOT NULL CHECK (birth_day BETWEEN 1 AND 31),
    birth_hour  INT NOT NULL CHECK (birth_hour BETWEEN 0 AND 23),
    birth_minute INT NOT NULL DEFAULT 0 CHECK (birth_minute BETWEEN 0 AND 59),
    asset_class_pref TEXT NOT NULL DEFAULT 'swing'
        CHECK (asset_class_pref IN ('swing', 'scalp', 'long', 'default')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- updated_at 자동 갱신 트리거
CREATE OR REPLACE FUNCTION touch_updated_at() RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS users_touch ON users;
CREATE TRIGGER users_touch BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION touch_updated_at();

DROP TRIGGER IF EXISTS user_bazi_touch ON user_bazi;
CREATE TRIGGER user_bazi_touch BEFORE UPDATE ON user_bazi
    FOR EACH ROW EXECUTE FUNCTION touch_updated_at();
```

- [ ] **Step 2: 커밋**

```bash
git add migrations/001_init.sql
git commit -m "feat(db): add initial users + user_bazi schema"
```

---

## Task 3: `db.py` — asyncpg Pool 싱글톤

**Files:**
- Create: `D:\사주캔들\src\sajucandle\db.py`
- Test: `D:\사주캔들\tests\test_db.py`

- [ ] **Step 1: 테스트 작성 (먼저 FAIL)**

`tests/test_db.py`:
```python
"""asyncpg Pool 싱글톤 테스트. TEST_DATABASE_URL 없으면 skip."""
from __future__ import annotations

import os

import pytest

from sajucandle import db


pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL not set",
)


async def test_connect_and_close():
    """connect() → ping → close()."""
    dsn = os.environ["TEST_DATABASE_URL"]
    await db.connect(dsn)
    try:
        async with db.acquire() as conn:
            result = await conn.fetchval("SELECT 1")
            assert result == 1
    finally:
        await db.close()


async def test_acquire_raises_when_not_connected():
    """connect() 전에 acquire()하면 명확한 에러."""
    await db.close()  # 혹시 열려있으면 닫음
    with pytest.raises(RuntimeError, match="not connected"):
        async with db.acquire() as _:
            pass
```

- [ ] **Step 2: 테스트 실행 → FAIL 확인**

```bash
cd "D:/사주캔들"
.venv/Scripts/python.exe -m pytest tests/test_db.py -v
```
Expected: `ModuleNotFoundError: No module named 'sajucandle.db'` 또는 skip (env 없으면 skip).
로컬에서는 `TEST_DATABASE_URL`을 Supabase DSN 또는 로컬 Postgres로 설정해서 실제 FAIL 확인.

- [ ] **Step 3: `db.py` 구현**

`src/sajucandle/db.py`:
```python
"""asyncpg Pool 싱글톤.

FastAPI lifespan에서 `await connect(dsn)` / `await close()`.
핸들러에서는 `async with acquire() as conn: ...`.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional

import asyncpg

logger = logging.getLogger(__name__)

_pool: Optional[asyncpg.Pool] = None


async def connect(dsn: str, min_size: int = 1, max_size: int = 5) -> None:
    """Pool 생성. 이미 열려있으면 no-op."""
    global _pool
    if _pool is not None:
        return
    _pool = await asyncpg.create_pool(dsn, min_size=min_size, max_size=max_size)
    logger.info("asyncpg pool ready (min=%d max=%d)", min_size, max_size)


async def close() -> None:
    """Pool 닫기. 열려있지 않으면 no-op."""
    global _pool
    if _pool is None:
        return
    await _pool.close()
    _pool = None
    logger.info("asyncpg pool closed")


@asynccontextmanager
async def acquire() -> AsyncIterator[asyncpg.Connection]:
    """Pool에서 커넥션 획득. Pool이 없으면 RuntimeError."""
    if _pool is None:
        raise RuntimeError("db not connected; call db.connect(dsn) first")
    async with _pool.acquire() as conn:
        yield conn


def get_pool() -> Optional[asyncpg.Pool]:
    """헬스체크용. None이면 미연결."""
    return _pool
```

- [ ] **Step 4: 테스트 재실행 → PASS**

`TEST_DATABASE_URL`이 세팅되어 있으면:
```bash
.venv/Scripts/python.exe -m pytest tests/test_db.py -v
```
Expected: 2 passed. (env 없으면 skipped.)

**개발자가 로컬에서 실행하려면** (Windows PowerShell):
```powershell
$env:TEST_DATABASE_URL = "postgresql://user:pw@host:5432/dbname"
```

- [ ] **Step 5: 커밋**

```bash
git add src/sajucandle/db.py tests/test_db.py
git commit -m "feat(db): asyncpg pool singleton with connect/close/acquire"
```

---

## Task 4: 테스트용 DB 트랜잭션 롤백 fixture

**Files:**
- Create or Modify: `D:\사주캔들\tests\conftest.py`

- [ ] **Step 1: conftest.py 작성**

`tests/conftest.py`:
```python
"""공통 fixture. DB 테스트는 TEST_DATABASE_URL 필요."""
from __future__ import annotations

import os

import pytest
import pytest_asyncio

from sajucandle import db


TEST_DSN = os.environ.get("TEST_DATABASE_URL")


@pytest_asyncio.fixture
async def db_pool():
    """세션 내내 Pool 1개. 없으면 스킵 시그널."""
    if not TEST_DSN:
        pytest.skip("TEST_DATABASE_URL not set")
    await db.connect(TEST_DSN, min_size=1, max_size=2)
    yield db.get_pool()
    await db.close()


@pytest_asyncio.fixture
async def db_conn(db_pool):
    """각 테스트마다 BEGIN → 테스트 → ROLLBACK.

    스키마는 migrations/001_init.sql이 TEST DB에 이미 적용되어 있어야 함.
    테스트 간 완전 격리를 위해 모든 변경은 롤백된다.
    """
    async with db_pool.acquire() as conn:
        tx = conn.transaction()
        await tx.start()
        try:
            yield conn
        finally:
            await tx.rollback()
```

- [ ] **Step 2: 기존 fakeredis fixture 확인**

기존 `tests/` 하위에 conftest가 있나 확인:
```bash
ls tests/conftest.py 2>/dev/null || echo "not exists"
```
있으면 위 내용 **append**, 없으면 새로 생성.

- [ ] **Step 3: 스모크 테스트 추가 (같은 conftest 파일 끝에 임시 검증용 —  실제 테스트 파일로 만들면 더 좋음)**

임시 검증은 생략하고 Task 5에서 사용 시 검증.

- [ ] **Step 4: 커밋**

```bash
git add tests/conftest.py
git commit -m "test: add db_pool + db_conn rollback fixtures"
```

---

## Task 5: `repositories.py` — users + user_bazi CRUD

**Files:**
- Create: `D:\사주캔들\src\sajucandle\repositories.py`
- Test: `D:\사주캔들\tests\test_repositories.py`

- [ ] **Step 1: 테스트 작성 (FAIL)**

`tests/test_repositories.py`:
```python
"""repositories 단위 테스트. 각 테스트는 트랜잭션 롤백."""
from __future__ import annotations

from sajucandle.repositories import (
    UserProfile,
    delete_user,
    get_user,
    upsert_user,
)


async def test_upsert_inserts_when_new(db_conn):
    profile = UserProfile(
        telegram_chat_id=111,
        birth_year=1990, birth_month=3, birth_day=15,
        birth_hour=14, birth_minute=0,
        asset_class_pref="swing",
    )
    saved = await upsert_user(db_conn, profile)
    assert saved.telegram_chat_id == 111
    assert saved.birth_year == 1990
    assert saved.created_at is not None
    assert saved.updated_at is not None


async def test_upsert_updates_when_exists(db_conn):
    p1 = UserProfile(
        telegram_chat_id=222,
        birth_year=1990, birth_month=3, birth_day=15,
        birth_hour=14, birth_minute=0,
        asset_class_pref="swing",
    )
    await upsert_user(db_conn, p1)

    p2 = UserProfile(
        telegram_chat_id=222,
        birth_year=1991, birth_month=6, birth_day=20,
        birth_hour=9, birth_minute=30,
        asset_class_pref="scalp",
    )
    saved = await upsert_user(db_conn, p2)
    assert saved.birth_year == 1991
    assert saved.birth_month == 6
    assert saved.asset_class_pref == "scalp"


async def test_get_returns_none_when_missing(db_conn):
    assert await get_user(db_conn, 9999) is None


async def test_get_returns_profile(db_conn):
    await upsert_user(db_conn, UserProfile(
        telegram_chat_id=333,
        birth_year=2000, birth_month=1, birth_day=1,
        birth_hour=0, birth_minute=0,
        asset_class_pref="long",
    ))
    got = await get_user(db_conn, 333)
    assert got is not None
    assert got.telegram_chat_id == 333
    assert got.asset_class_pref == "long"


async def test_delete_is_idempotent(db_conn):
    # 없어도 에러 없이
    await delete_user(db_conn, 4444)

    await upsert_user(db_conn, UserProfile(
        telegram_chat_id=4444,
        birth_year=1990, birth_month=3, birth_day=15,
        birth_hour=14, birth_minute=0,
        asset_class_pref="swing",
    ))
    await delete_user(db_conn, 4444)
    assert await get_user(db_conn, 4444) is None
```

- [ ] **Step 2: 테스트 실행 → FAIL**

```bash
.venv/Scripts/python.exe -m pytest tests/test_repositories.py -v
```
Expected: ImportError or skip.

- [ ] **Step 3: `repositories.py` 구현**

`src/sajucandle/repositories.py`:
```python
"""users + user_bazi CRUD. asyncpg Connection 주입 받음."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import asyncpg


@dataclass
class UserProfile:
    telegram_chat_id: int
    birth_year: int
    birth_month: int
    birth_day: int
    birth_hour: int
    birth_minute: int
    asset_class_pref: str = "swing"
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


_UPSERT_USER = """
INSERT INTO users (telegram_chat_id) VALUES ($1)
ON CONFLICT (telegram_chat_id) DO UPDATE
    SET updated_at = now()
RETURNING created_at, updated_at
"""

_UPSERT_BAZI = """
INSERT INTO user_bazi (
    telegram_chat_id, birth_year, birth_month, birth_day,
    birth_hour, birth_minute, asset_class_pref
) VALUES ($1, $2, $3, $4, $5, $6, $7)
ON CONFLICT (telegram_chat_id) DO UPDATE SET
    birth_year = EXCLUDED.birth_year,
    birth_month = EXCLUDED.birth_month,
    birth_day = EXCLUDED.birth_day,
    birth_hour = EXCLUDED.birth_hour,
    birth_minute = EXCLUDED.birth_minute,
    asset_class_pref = EXCLUDED.asset_class_pref,
    updated_at = now()
RETURNING created_at, updated_at
"""

_SELECT = """
SELECT u.telegram_chat_id,
       b.birth_year, b.birth_month, b.birth_day,
       b.birth_hour, b.birth_minute,
       b.asset_class_pref,
       u.created_at, u.updated_at
FROM users u
JOIN user_bazi b USING (telegram_chat_id)
WHERE u.telegram_chat_id = $1
"""


async def upsert_user(conn: asyncpg.Connection, profile: UserProfile) -> UserProfile:
    """users + user_bazi upsert. 단일 트랜잭션."""
    async with conn.transaction():
        u_row = await conn.fetchrow(_UPSERT_USER, profile.telegram_chat_id)
        b_row = await conn.fetchrow(
            _UPSERT_BAZI,
            profile.telegram_chat_id,
            profile.birth_year,
            profile.birth_month,
            profile.birth_day,
            profile.birth_hour,
            profile.birth_minute,
            profile.asset_class_pref,
        )
    return UserProfile(
        telegram_chat_id=profile.telegram_chat_id,
        birth_year=profile.birth_year,
        birth_month=profile.birth_month,
        birth_day=profile.birth_day,
        birth_hour=profile.birth_hour,
        birth_minute=profile.birth_minute,
        asset_class_pref=profile.asset_class_pref,
        created_at=u_row["created_at"],
        updated_at=b_row["updated_at"],
    )


async def get_user(conn: asyncpg.Connection, chat_id: int) -> Optional[UserProfile]:
    row = await conn.fetchrow(_SELECT, chat_id)
    if row is None:
        return None
    return UserProfile(
        telegram_chat_id=row["telegram_chat_id"],
        birth_year=row["birth_year"],
        birth_month=row["birth_month"],
        birth_day=row["birth_day"],
        birth_hour=row["birth_hour"],
        birth_minute=row["birth_minute"],
        asset_class_pref=row["asset_class_pref"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


async def delete_user(conn: asyncpg.Connection, chat_id: int) -> None:
    """ON DELETE CASCADE로 user_bazi도 함께 삭제. 없으면 no-op."""
    await conn.execute("DELETE FROM users WHERE telegram_chat_id = $1", chat_id)
```

- [ ] **Step 4: 테스트 재실행 → PASS**

```bash
.venv/Scripts/python.exe -m pytest tests/test_repositories.py -v
```
Expected: 5 passed.

- [ ] **Step 5: 커밋**

```bash
git add src/sajucandle/repositories.py tests/test_repositories.py
git commit -m "feat(db): add users + user_bazi CRUD with transaction upsert"
```

---

## Task 6: 신규 Pydantic 모델

**Files:**
- Modify: `D:\사주캔들\src\sajucandle\models.py`

- [ ] **Step 1: models.py에 append**

`src/sajucandle/models.py` 끝에 추가:
```python
# ─────────────────────────────────────────────
# Week 3: User profile + Score
# ─────────────────────────────────────────────

from datetime import datetime  # noqa: E402
from typing import List, Literal  # noqa: E402


AssetClass = Literal["swing", "scalp", "long", "default"]


class UserProfileRequest(BaseModel):
    """PUT /v1/users/{chat_id} body."""

    birth_year: int = Field(ge=1900, le=2100)
    birth_month: int = Field(ge=1, le=12)
    birth_day: int = Field(ge=1, le=31)
    birth_hour: int = Field(ge=0, le=23)
    birth_minute: int = Field(default=0, ge=0, le=59)
    asset_class_pref: AssetClass = "swing"


class UserProfileResponse(BaseModel):
    telegram_chat_id: int
    birth_year: int
    birth_month: int
    birth_day: int
    birth_hour: int
    birth_minute: int
    asset_class_pref: AssetClass
    created_at: datetime
    updated_at: datetime


class AxisScore(BaseModel):
    score: int = Field(ge=0, le=100)
    reason: str = ""


class HourRecommendation(BaseModel):
    shichen: str          # "巳"
    time_range: str       # "09:00~11:00"
    multiplier: float     # 1.15


class SajuScoreResponse(BaseModel):
    chat_id: int
    date: str             # "2026-04-16"
    asset_class: AssetClass
    iljin: str            # "庚申"
    composite_score: int = Field(ge=0, le=100)
    signal_grade: str     # "🔥 강한 진입" 같은 원본 문자열
    axes: dict[str, AxisScore]   # keys: wealth, decision, volatility, flow
    best_hours: List[HourRecommendation]
```

- [ ] **Step 2: 임포트 스모크**

```bash
.venv/Scripts/python.exe -c "from sajucandle.models import UserProfileRequest, SajuScoreResponse; print('ok')"
```
Expected: `ok`

- [ ] **Step 3: 커밋**

```bash
git add src/sajucandle/models.py
git commit -m "feat(models): add Week 3 user profile + score response models"
```

---

## Task 7: `score_service.py` — ScoreCard 변환 + 캐시

**Files:**
- Create: `D:\사주캔들\src\sajucandle\score_service.py`
- Test: `D:\사주캔들\tests\test_score_service.py`

- [ ] **Step 1: 테스트 작성 (FAIL)**

`tests/test_score_service.py`:
```python
"""score_service: ScoreCard → SajuScoreResponse 변환 + 캐시."""
from __future__ import annotations

from datetime import date

import fakeredis

from sajucandle.cache import BaziCache
from sajucandle.cached_engine import CachedSajuEngine
from sajucandle.repositories import UserProfile
from sajucandle.score_service import ScoreService


def _profile() -> UserProfile:
    return UserProfile(
        telegram_chat_id=1,
        birth_year=1990, birth_month=3, birth_day=15,
        birth_hour=14, birth_minute=0,
        asset_class_pref="swing",
    )


def test_compute_returns_saju_score_response():
    engine = CachedSajuEngine(cache=BaziCache(redis_client=None))
    svc = ScoreService(engine=engine, redis_client=None)
    resp = svc.compute(_profile(), target_date=date(2026, 4, 16), asset_class="swing")

    assert resp.chat_id == 1
    assert resp.date == "2026-04-16"
    assert resp.asset_class == "swing"
    assert 0 <= resp.composite_score <= 100
    assert set(resp.axes.keys()) == {"wealth", "decision", "volatility", "flow"}
    for axis in resp.axes.values():
        assert 0 <= axis.score <= 100


def test_compute_uses_redis_cache_on_second_call():
    r = fakeredis.FakeRedis()
    engine = CachedSajuEngine(cache=BaziCache(redis_client=r))
    svc = ScoreService(engine=engine, redis_client=r)

    # 첫 호출 — MISS → SET
    r1 = svc.compute(_profile(), target_date=date(2026, 4, 16), asset_class="swing")
    keys = [k.decode() for k in r.keys("score:*")]
    assert len(keys) == 1
    assert keys[0] == "score:1:2026-04-16:swing"

    # 두 번째 호출 — HIT → 값 동일
    r2 = svc.compute(_profile(), target_date=date(2026, 4, 16), asset_class="swing")
    assert r1.model_dump() == r2.model_dump()


def test_compute_cache_key_varies_by_asset():
    r = fakeredis.FakeRedis()
    engine = CachedSajuEngine(cache=BaziCache(redis_client=r))
    svc = ScoreService(engine=engine, redis_client=r)

    svc.compute(_profile(), target_date=date(2026, 4, 16), asset_class="swing")
    svc.compute(_profile(), target_date=date(2026, 4, 16), asset_class="scalp")

    keys = sorted(k.decode() for k in r.keys("score:*"))
    assert keys == [
        "score:1:2026-04-16:scalp",
        "score:1:2026-04-16:swing",
    ]


def test_compute_with_no_redis_still_works():
    engine = CachedSajuEngine(cache=BaziCache(redis_client=None))
    svc = ScoreService(engine=engine, redis_client=None)
    resp = svc.compute(_profile(), target_date=date(2026, 4, 16), asset_class="swing")
    assert resp.composite_score >= 0
```

- [ ] **Step 2: FAIL 확인**

```bash
.venv/Scripts/python.exe -m pytest tests/test_score_service.py -v
```
Expected: ImportError.

- [ ] **Step 3: `score_service.py` 구현**

`src/sajucandle/score_service.py`:
```python
"""일일 점수 서비스.

책임:
1. UserProfile → BaziChart 계산 (cached_engine 위임)
2. ScoreCard 계산
3. Pydantic 응답으로 변환
4. Redis에 결과 캐시 (KST 자정까지 TTL)
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sajucandle.cached_engine import CachedSajuEngine
from sajucandle.models import AxisScore, HourRecommendation, SajuScoreResponse
from sajucandle.repositories import UserProfile

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))


def _seconds_until_kst_midnight(now_utc: Optional[datetime] = None) -> int:
    """지금부터 다음 KST 자정까지 남은 초. 최소 60초."""
    now = now_utc or datetime.now(tz=timezone.utc)
    kst_now = now.astimezone(KST)
    tomorrow = (kst_now + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    delta = (tomorrow - kst_now).total_seconds()
    return max(int(delta), 60)


class ScoreService:
    def __init__(self, engine: CachedSajuEngine, redis_client=None):
        self._engine = engine
        self._redis = redis_client

    def compute(
        self,
        profile: UserProfile,
        target_date: date,
        asset_class: str,
    ) -> SajuScoreResponse:
        cache_key = f"score:{profile.telegram_chat_id}:{target_date.isoformat()}:{asset_class}"

        # 1) Redis 히트?
        if self._redis is not None:
            try:
                raw = self._redis.get(cache_key)
            except Exception as e:
                logger.warning("score cache GET 실패: %s", e)
                raw = None
            if raw:
                try:
                    data = json.loads(raw)
                    return SajuScoreResponse(**data)
                except Exception:
                    pass  # 깨진 캐시는 무시, 아래에서 재계산

        # 2) 계산
        bazi = self._engine.calc_bazi(
            profile.birth_year,
            profile.birth_month,
            profile.birth_day,
            profile.birth_hour,
        )
        card = self._engine.engine.calc_daily_score(
            bazi, target_date, asset_class=asset_class
        )

        resp = SajuScoreResponse(
            chat_id=profile.telegram_chat_id,
            date=target_date.isoformat(),
            asset_class=asset_class,  # type: ignore[arg-type]
            iljin=card.iljin,
            composite_score=card.composite_score,
            signal_grade=card.signal_grade,
            axes={
                "wealth":     AxisScore(score=card.wealth_score,     reason=card.wealth_reason),
                "decision":   AxisScore(score=card.decision_score,   reason=card.decision_reason),
                "volatility": AxisScore(score=card.volatility_score, reason=card.volatility_reason),
                "flow":       AxisScore(score=card.flow_score,       reason=card.flow_reason),
            },
            best_hours=[
                HourRecommendation(shichen=zhi, time_range=tr, multiplier=mult)
                for (zhi, tr, mult) in card.best_hours
            ],
        )

        # 3) 캐시 저장 (실패해도 무시)
        if self._redis is not None:
            try:
                self._redis.set(
                    cache_key,
                    resp.model_dump_json(),
                    ex=_seconds_until_kst_midnight(),
                )
            except Exception as e:
                logger.warning("score cache SET 실패: %s", e)

        return resp
```

- [ ] **Step 4: `CachedSajuEngine`에 `engine` 속성 노출 확인**

`src/sajucandle/cached_engine.py`를 읽어 내부 `SajuEngine` 인스턴스가 `self.engine` 또는 다른 이름인지 확인:
```bash
cat src/sajucandle/cached_engine.py
```
**만약 속성 이름이 `self._engine` (밑줄)이라면**, 공개 속성 `engine` property를 추가:
```python
@property
def engine(self):
    return self._engine
```
또는 `score_service.py`에서 `self._engine._engine.calc_daily_score(...)` 대신 `self._engine.engine.calc_daily_score(...)`가 되도록. 기존 코드에 없으면 `cached_engine.py`에 한 줄 추가하고 커밋에 포함.

- [ ] **Step 5: 테스트 재실행 → PASS**

```bash
.venv/Scripts/python.exe -m pytest tests/test_score_service.py -v
```
Expected: 4 passed.

- [ ] **Step 6: `_seconds_until_kst_midnight` 단위 테스트 추가**

`tests/test_score_service.py` 끝에 append:
```python
from datetime import datetime, timezone

from sajucandle.score_service import _seconds_until_kst_midnight


def test_seconds_until_kst_midnight_at_kst_noon():
    # 2026-04-16 03:00 UTC = 12:00 KST → 자정까지 12시간
    now = datetime(2026, 4, 16, 3, 0, 0, tzinfo=timezone.utc)
    assert _seconds_until_kst_midnight(now) == 12 * 3600


def test_seconds_until_kst_midnight_is_positive_and_min_60():
    # 2026-04-16 14:59:30 UTC = 23:59:30 KST → 30초지만 최소 60초로 clamp
    now = datetime(2026, 4, 16, 14, 59, 30, tzinfo=timezone.utc)
    assert _seconds_until_kst_midnight(now) >= 60
```

- [ ] **Step 7: 테스트 실행**

```bash
.venv/Scripts/python.exe -m pytest tests/test_score_service.py -v
```
Expected: 6 passed.

- [ ] **Step 8: 커밋**

```bash
git add src/sajucandle/score_service.py src/sajucandle/cached_engine.py tests/test_score_service.py
git commit -m "feat(api): add ScoreService with KST-midnight TTL cache"
```

---

## Task 8: `PUT /v1/users/{chat_id}` 엔드포인트

**Files:**
- Modify: `D:\사주캔들\src\sajucandle\api.py`
- Test: `D:\사주캔들\tests\test_api_users.py`

- [ ] **Step 1: 테스트 작성 (FAIL)**

`tests/test_api_users.py`:
```python
"""/v1/users/* 엔드포인트 통합 테스트. 실제 DB 필요."""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from sajucandle.api import create_app

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL not set",
)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("SAJUCANDLE_API_KEY", "test-key")
    monkeypatch.setenv("DATABASE_URL", os.environ["TEST_DATABASE_URL"])
    app = create_app()
    with TestClient(app) as c:
        yield c


HDR = {"X-SAJUCANDLE-KEY": "test-key"}


def test_put_user_creates(client):
    body = {
        "birth_year": 1990, "birth_month": 3, "birth_day": 15,
        "birth_hour": 14, "birth_minute": 0,
        "asset_class_pref": "swing",
    }
    r = client.put("/v1/users/700001", json=body, headers=HDR)
    assert r.status_code == 200
    data = r.json()
    assert data["telegram_chat_id"] == 700001
    assert data["birth_year"] == 1990
    assert data["asset_class_pref"] == "swing"

    # cleanup
    client.delete("/v1/users/700001", headers=HDR)


def test_put_user_updates(client):
    body = {
        "birth_year": 1990, "birth_month": 3, "birth_day": 15,
        "birth_hour": 14, "birth_minute": 0,
        "asset_class_pref": "swing",
    }
    client.put("/v1/users/700002", json=body, headers=HDR)
    body["asset_class_pref"] = "scalp"
    body["birth_year"] = 1991
    r = client.put("/v1/users/700002", json=body, headers=HDR)
    assert r.status_code == 200
    assert r.json()["birth_year"] == 1991
    assert r.json()["asset_class_pref"] == "scalp"

    client.delete("/v1/users/700002", headers=HDR)


def test_put_user_requires_api_key(client):
    body = {
        "birth_year": 1990, "birth_month": 3, "birth_day": 15,
        "birth_hour": 14, "birth_minute": 0,
    }
    r = client.put("/v1/users/700003", json=body)
    assert r.status_code == 401


def test_put_user_rejects_invalid_payload(client):
    r = client.put("/v1/users/700004",
                   json={"birth_year": 1800, "birth_month": 1, "birth_day": 1,
                         "birth_hour": 0},
                   headers=HDR)
    assert r.status_code == 422
```

- [ ] **Step 2: FAIL 확인**

```bash
.venv/Scripts/python.exe -m pytest tests/test_api_users.py::test_put_user_creates -v
```
Expected: 404 (엔드포인트 없음) 또는 connection 에러.

- [ ] **Step 3: `api.py` 수정 — lifespan + PUT 엔드포인트**

`src/sajucandle/api.py` 전체를 다음으로 교체:
```python
"""FastAPI 앱. 봇과 웹 공통 백엔드.

인증: X-SAJUCANDLE-KEY 헤더.
DB: DATABASE_URL env로 lifespan에서 Pool 연결.
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Header, HTTPException, Request

from sajucandle import db, repositories
from sajucandle.cache import BaziCache
from sajucandle.cached_engine import CachedSajuEngine
from sajucandle.models import (
    BaziResponse,
    BirthRequest,
    UserProfileRequest,
    UserProfileResponse,
    bazi_chart_to_response,
)

logger = logging.getLogger(__name__)


def _build_default_engine() -> CachedSajuEngine:
    redis_url = os.environ.get("REDIS_URL")
    redis_client = None
    if redis_url:
        try:
            import redis as redis_lib
            redis_client = redis_lib.from_url(redis_url)
            redis_client.ping()
            logger.info("API: Redis 연결 성공.")
        except Exception as e:
            logger.warning("API: Redis 연결 실패 (%s).", e)
            redis_client = None
    else:
        logger.info("API: REDIS_URL 미설정.")
    return CachedSajuEngine(cache=BaziCache(redis_client=redis_client))


def _require_api_key(request: Request, x_sajucandle_key: Optional[str]) -> None:
    expected = os.environ.get("SAJUCANDLE_API_KEY", "").strip()
    if not expected:
        return
    if x_sajucandle_key != expected:
        raise HTTPException(status_code=401, detail="invalid or missing API key")


def _profile_to_response(p: repositories.UserProfile) -> UserProfileResponse:
    return UserProfileResponse(
        telegram_chat_id=p.telegram_chat_id,
        birth_year=p.birth_year,
        birth_month=p.birth_month,
        birth_day=p.birth_day,
        birth_hour=p.birth_hour,
        birth_minute=p.birth_minute,
        asset_class_pref=p.asset_class_pref,  # type: ignore[arg-type]
        created_at=p.created_at,
        updated_at=p.updated_at,
    )


def create_app(engine: CachedSajuEngine | None = None) -> FastAPI:
    engine = engine or _build_default_engine()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        dsn = os.environ.get("DATABASE_URL")
        if dsn:
            try:
                await db.connect(dsn)
            except Exception as e:
                logger.error("DB 연결 실패: %s", e)
        else:
            logger.warning("DATABASE_URL 미설정 — 사용자 엔드포인트 비활성.")
        yield
        await db.close()

    app = FastAPI(title="SajuCandle API", version="0.2.0", lifespan=lifespan)

    @app.get("/health")
    async def health() -> dict[str, str]:
        pool = db.get_pool()
        db_status = "down"
        if pool is not None:
            try:
                async with db.acquire() as conn:
                    await conn.fetchval("SELECT 1")
                db_status = "up"
            except Exception:
                db_status = "down"
        return {"status": "ok", "db": db_status}

    @app.post("/v1/bazi", response_model=BaziResponse)
    async def bazi(
        body: BirthRequest,
        request: Request,
        x_sajucandle_key: Optional[str] = Header(default=None),
    ) -> BaziResponse:
        _require_api_key(request, x_sajucandle_key)
        try:
            chart = engine.calc_bazi(body.year, body.month, body.day, body.hour)
        except Exception as e:
            logger.exception("calc_bazi failed")
            raise HTTPException(400, detail=f"명식 계산 실패: {type(e).__name__}")
        return bazi_chart_to_response(chart)

    @app.put("/v1/users/{chat_id}", response_model=UserProfileResponse)
    async def put_user(
        chat_id: int,
        body: UserProfileRequest,
        request: Request,
        x_sajucandle_key: Optional[str] = Header(default=None),
    ) -> UserProfileResponse:
        _require_api_key(request, x_sajucandle_key)
        if db.get_pool() is None:
            raise HTTPException(503, detail="database not available")
        async with db.acquire() as conn:
            saved = await repositories.upsert_user(
                conn,
                repositories.UserProfile(
                    telegram_chat_id=chat_id,
                    birth_year=body.birth_year,
                    birth_month=body.birth_month,
                    birth_day=body.birth_day,
                    birth_hour=body.birth_hour,
                    birth_minute=body.birth_minute,
                    asset_class_pref=body.asset_class_pref,
                ),
            )
        return _profile_to_response(saved)

    return app


app = create_app()
```

- [ ] **Step 4: 테스트 재실행 → PASS**

```bash
.venv/Scripts/python.exe -m pytest tests/test_api_users.py -v
```
Expected: 4 passed (TEST_DATABASE_URL 세팅 시).

- [ ] **Step 5: 커밋**

```bash
git add src/sajucandle/api.py tests/test_api_users.py
git commit -m "feat(api): add PUT /v1/users/{chat_id} upsert endpoint + DB lifespan"
```

---

## Task 9: `GET /v1/users/{chat_id}` + `DELETE /v1/users/{chat_id}`

**Files:**
- Modify: `D:\사주캔들\src\sajucandle\api.py`
- Modify: `D:\사주캔들\tests\test_api_users.py`

- [ ] **Step 1: 테스트 추가**

`tests/test_api_users.py` 끝에 append:
```python
def test_get_user_returns_profile(client):
    body = {
        "birth_year": 1990, "birth_month": 3, "birth_day": 15,
        "birth_hour": 14, "birth_minute": 0,
        "asset_class_pref": "swing",
    }
    client.put("/v1/users/700010", json=body, headers=HDR)

    r = client.get("/v1/users/700010", headers=HDR)
    assert r.status_code == 200
    assert r.json()["telegram_chat_id"] == 700010

    client.delete("/v1/users/700010", headers=HDR)


def test_get_user_404_when_missing(client):
    r = client.get("/v1/users/9999999", headers=HDR)
    assert r.status_code == 404


def test_delete_user_is_idempotent(client):
    r = client.delete("/v1/users/8888888", headers=HDR)
    assert r.status_code == 204

    body = {
        "birth_year": 1990, "birth_month": 3, "birth_day": 15,
        "birth_hour": 14, "birth_minute": 0,
    }
    client.put("/v1/users/700020", json=body, headers=HDR)
    r = client.delete("/v1/users/700020", headers=HDR)
    assert r.status_code == 204
    r = client.get("/v1/users/700020", headers=HDR)
    assert r.status_code == 404
```

- [ ] **Step 2: FAIL 확인**

```bash
.venv/Scripts/python.exe -m pytest tests/test_api_users.py -v
```
Expected: 3 추가 테스트 FAIL (405 또는 500).

- [ ] **Step 3: `api.py`에 GET + DELETE 추가**

`create_app()`의 `put_user` 정의 직후에 추가:
```python
    @app.get("/v1/users/{chat_id}", response_model=UserProfileResponse)
    async def get_user_endpoint(
        chat_id: int,
        request: Request,
        x_sajucandle_key: Optional[str] = Header(default=None),
    ) -> UserProfileResponse:
        _require_api_key(request, x_sajucandle_key)
        if db.get_pool() is None:
            raise HTTPException(503, detail="database not available")
        async with db.acquire() as conn:
            user = await repositories.get_user(conn, chat_id)
        if user is None:
            raise HTTPException(404, detail="user not found")
        return _profile_to_response(user)

    @app.delete("/v1/users/{chat_id}", status_code=204)
    async def delete_user_endpoint(
        chat_id: int,
        request: Request,
        x_sajucandle_key: Optional[str] = Header(default=None),
    ) -> None:
        _require_api_key(request, x_sajucandle_key)
        if db.get_pool() is None:
            raise HTTPException(503, detail="database not available")
        async with db.acquire() as conn:
            await repositories.delete_user(conn, chat_id)
        return None
```

- [ ] **Step 4: 테스트 실행**

```bash
.venv/Scripts/python.exe -m pytest tests/test_api_users.py -v
```
Expected: 7 passed.

- [ ] **Step 5: 커밋**

```bash
git add src/sajucandle/api.py tests/test_api_users.py
git commit -m "feat(api): add GET + DELETE /v1/users/{chat_id}"
```

---

## Task 10: `GET /v1/users/{chat_id}/score` 엔드포인트

**Files:**
- Modify: `D:\사주캔들\src\sajucandle\api.py`
- Test: `D:\사주캔들\tests\test_api_score.py`

- [ ] **Step 1: 테스트 작성**

`tests/test_api_score.py`:
```python
"""GET /v1/users/{chat_id}/score 통합 테스트."""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from sajucandle.api import create_app

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL not set",
)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("SAJUCANDLE_API_KEY", "test-key")
    monkeypatch.setenv("DATABASE_URL", os.environ["TEST_DATABASE_URL"])
    app = create_app()
    with TestClient(app) as c:
        yield c


HDR = {"X-SAJUCANDLE-KEY": "test-key"}


def _create(client, chat_id: int):
    client.put(
        f"/v1/users/{chat_id}",
        json={
            "birth_year": 1990, "birth_month": 3, "birth_day": 15,
            "birth_hour": 14, "birth_minute": 0,
            "asset_class_pref": "swing",
        },
        headers=HDR,
    )


def test_score_returns_full_payload(client):
    _create(client, 701001)
    try:
        r = client.get("/v1/users/701001/score?date=2026-04-16", headers=HDR)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["chat_id"] == 701001
        assert data["date"] == "2026-04-16"
        assert data["asset_class"] == "swing"
        assert 0 <= data["composite_score"] <= 100
        assert set(data["axes"].keys()) == {"wealth", "decision", "volatility", "flow"}
        assert isinstance(data["best_hours"], list)
    finally:
        client.delete("/v1/users/701001", headers=HDR)


def test_score_404_when_user_missing(client):
    r = client.get("/v1/users/9999988/score?date=2026-04-16", headers=HDR)
    assert r.status_code == 404


def test_score_asset_override(client):
    _create(client, 701002)
    try:
        r = client.get(
            "/v1/users/701002/score?date=2026-04-16&asset=scalp", headers=HDR
        )
        assert r.status_code == 200
        assert r.json()["asset_class"] == "scalp"
    finally:
        client.delete("/v1/users/701002", headers=HDR)


def test_score_default_date_is_today_kst(client):
    _create(client, 701003)
    try:
        r = client.get("/v1/users/701003/score", headers=HDR)
        assert r.status_code == 200
        # date 필드는 YYYY-MM-DD 형식
        assert len(r.json()["date"]) == 10
    finally:
        client.delete("/v1/users/701003", headers=HDR)


def test_score_rejects_bad_date(client):
    _create(client, 701004)
    try:
        r = client.get("/v1/users/701004/score?date=not-a-date", headers=HDR)
        assert r.status_code == 400
    finally:
        client.delete("/v1/users/701004", headers=HDR)
```

- [ ] **Step 2: FAIL 확인**

```bash
.venv/Scripts/python.exe -m pytest tests/test_api_score.py -v
```
Expected: 5 FAIL.

- [ ] **Step 3: `api.py`에 score 엔드포인트 추가**

`api.py` 상단 import에 추가:
```python
from datetime import date as date_cls, datetime, timedelta, timezone

from sajucandle.score_service import KST, ScoreService
```

`create_app()` 안 `_build_default_engine()` 리턴 바로 뒤, 그리고 lifespan 위에 score service 생성:
```python
    # redis_client을 ScoreService에도 공유하려면 _build_default_engine에서 꺼내야 함.
    # 간단히 별도 함수:
    def _build_score_service() -> ScoreService:
        redis_url = os.environ.get("REDIS_URL")
        redis_client = None
        if redis_url:
            try:
                import redis as redis_lib
                redis_client = redis_lib.from_url(redis_url)
                redis_client.ping()
            except Exception:
                redis_client = None
        return ScoreService(engine=engine, redis_client=redis_client)

    score_service = _build_score_service()
```

그리고 엔드포인트 추가 (delete_user_endpoint 뒤):
```python
    @app.get("/v1/users/{chat_id}/score")
    async def score_endpoint(
        chat_id: int,
        request: Request,
        date: Optional[str] = None,
        asset: Optional[str] = None,
        x_sajucandle_key: Optional[str] = Header(default=None),
    ):
        _require_api_key(request, x_sajucandle_key)
        if db.get_pool() is None:
            raise HTTPException(503, detail="database not available")

        # date 파싱
        if date is None:
            target = datetime.now(tz=KST).date()
        else:
            try:
                target = date_cls.fromisoformat(date)
            except ValueError:
                raise HTTPException(400, detail="date must be YYYY-MM-DD")

        # asset 검증
        allowed_assets = {"swing", "scalp", "long", "default"}
        if asset is not None and asset not in allowed_assets:
            raise HTTPException(400, detail=f"asset must be one of {sorted(allowed_assets)}")

        async with db.acquire() as conn:
            profile = await repositories.get_user(conn, chat_id)
        if profile is None:
            raise HTTPException(404, detail="user not found")

        final_asset = asset or profile.asset_class_pref
        try:
            return score_service.compute(profile, target, final_asset)
        except Exception as e:
            logger.exception("score compute failed")
            raise HTTPException(400, detail=f"점수 계산 실패: {type(e).__name__}")
```

**참고:** `from datetime import date` 충돌 방지를 위해 alias `date_cls` 사용. 함수 파라미터 `date: Optional[str]`은 FastAPI query param.

- [ ] **Step 4: 테스트 실행**

```bash
.venv/Scripts/python.exe -m pytest tests/test_api_score.py -v
```
Expected: 5 passed.

- [ ] **Step 5: 전체 기존 테스트 회귀 확인**

```bash
.venv/Scripts/python.exe -m pytest -v
```
Expected: 기존 26개 + 신규 모두 green. (TEST_DATABASE_URL 없으면 DB 관련은 skip.)

- [ ] **Step 6: 커밋**

```bash
git add src/sajucandle/api.py tests/test_api_score.py
git commit -m "feat(api): add GET /v1/users/{chat_id}/score with date+asset params"
```

---

## Task 11: `api_client.py` — 봇용 httpx 래퍼

**Files:**
- Create: `D:\사주캔들\src\sajucandle\api_client.py`
- Test: `D:\사주캔들\tests\test_api_client.py`

- [ ] **Step 1: 테스트 작성**

`tests/test_api_client.py`:
```python
"""api_client 단위 테스트. respx로 API 모킹."""
from __future__ import annotations

import httpx
import pytest
import respx

from sajucandle.api_client import (
    ApiClient,
    ApiError,
    NotFoundError,
)


BASE = "https://api.test"
KEY = "test-key"


@pytest.fixture
def client():
    return ApiClient(base_url=BASE, api_key=KEY, timeout=1.0)


@respx.mock
async def test_put_user_sends_correct_request(client):
    route = respx.put(f"{BASE}/v1/users/123").mock(
        return_value=httpx.Response(200, json={
            "telegram_chat_id": 123,
            "birth_year": 1990, "birth_month": 3, "birth_day": 15,
            "birth_hour": 14, "birth_minute": 0,
            "asset_class_pref": "swing",
            "created_at": "2026-04-16T00:00:00Z",
            "updated_at": "2026-04-16T00:00:00Z",
        })
    )
    result = await client.put_user(
        123,
        birth_year=1990, birth_month=3, birth_day=15,
        birth_hour=14, birth_minute=0, asset_class_pref="swing",
    )
    assert route.called
    assert route.calls.last.request.headers["X-SAJUCANDLE-KEY"] == KEY
    assert result["telegram_chat_id"] == 123


@respx.mock
async def test_get_user_404_raises_notfound(client):
    respx.get(f"{BASE}/v1/users/999").mock(
        return_value=httpx.Response(404, json={"detail": "user not found"})
    )
    with pytest.raises(NotFoundError):
        await client.get_user(999)


@respx.mock
async def test_get_user_success(client):
    respx.get(f"{BASE}/v1/users/123").mock(
        return_value=httpx.Response(200, json={
            "telegram_chat_id": 123,
            "birth_year": 1990, "birth_month": 3, "birth_day": 15,
            "birth_hour": 14, "birth_minute": 0,
            "asset_class_pref": "swing",
            "created_at": "2026-04-16T00:00:00Z",
            "updated_at": "2026-04-16T00:00:00Z",
        })
    )
    result = await client.get_user(123)
    assert result["birth_year"] == 1990


@respx.mock
async def test_delete_user_204(client):
    route = respx.delete(f"{BASE}/v1/users/123").mock(
        return_value=httpx.Response(204)
    )
    await client.delete_user(123)
    assert route.called


@respx.mock
async def test_get_score_success(client):
    respx.get(f"{BASE}/v1/users/123/score").mock(
        return_value=httpx.Response(200, json={
            "chat_id": 123, "date": "2026-04-16", "asset_class": "swing",
            "iljin": "庚申", "composite_score": 72, "signal_grade": "👍 진입각",
            "axes": {
                "wealth":     {"score": 78, "reason": "..."},
                "decision":   {"score": 65, "reason": "..."},
                "volatility": {"score": 70, "reason": "..."},
                "flow":       {"score": 75, "reason": "..."},
            },
            "best_hours": [
                {"shichen": "巳", "time_range": "09:00~11:00", "multiplier": 1.15},
            ],
        })
    )
    result = await client.get_score(123, date="2026-04-16", asset="swing")
    assert result["composite_score"] == 72


@respx.mock
async def test_500_raises_apierror(client):
    respx.get(f"{BASE}/v1/users/1").mock(return_value=httpx.Response(500))
    with pytest.raises(ApiError):
        await client.get_user(1)
```

- [ ] **Step 2: FAIL 확인**

```bash
.venv/Scripts/python.exe -m pytest tests/test_api_client.py -v
```
Expected: ImportError.

- [ ] **Step 3: `api_client.py` 구현**

`src/sajucandle/api_client.py`:
```python
"""봇용 API HTTP 클라이언트. httpx AsyncClient 래퍼.

에러 체계:
- NotFoundError: 404
- ApiError: 기타 4xx/5xx
- TimeoutError (stdlib), httpx.TransportError: 네트워크
봇 핸들러는 이들을 사용자 친화적 메시지로 변환.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

import httpx


class ApiError(RuntimeError):
    """4xx/5xx 응답."""

    def __init__(self, status: int, detail: str):
        super().__init__(f"API {status}: {detail}")
        self.status = status
        self.detail = detail


class NotFoundError(ApiError):
    pass


class ApiClient:
    def __init__(self, base_url: str, api_key: str, timeout: float = 10.0):
        self._base = base_url.rstrip("/")
        self._headers = {"X-SAJUCANDLE-KEY": api_key}
        self._timeout = timeout

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self._base, headers=self._headers, timeout=self._timeout
        )

    async def _raise_for_status(self, resp: httpx.Response) -> None:
        if 200 <= resp.status_code < 300:
            return
        try:
            detail = resp.json().get("detail", "")
        except Exception:
            detail = resp.text
        if resp.status_code == 404:
            raise NotFoundError(404, detail)
        raise ApiError(resp.status_code, detail)

    async def put_user(
        self,
        chat_id: int,
        *,
        birth_year: int,
        birth_month: int,
        birth_day: int,
        birth_hour: int,
        birth_minute: int = 0,
        asset_class_pref: str = "swing",
    ) -> Dict[str, Any]:
        body = {
            "birth_year": birth_year,
            "birth_month": birth_month,
            "birth_day": birth_day,
            "birth_hour": birth_hour,
            "birth_minute": birth_minute,
            "asset_class_pref": asset_class_pref,
        }
        async with self._client() as c:
            r = await c.put(f"/v1/users/{chat_id}", json=body)
        await self._raise_for_status(r)
        return r.json()

    async def get_user(self, chat_id: int) -> Dict[str, Any]:
        async with self._client() as c:
            r = await c.get(f"/v1/users/{chat_id}")
        await self._raise_for_status(r)
        return r.json()

    async def delete_user(self, chat_id: int) -> None:
        async with self._client() as c:
            r = await c.delete(f"/v1/users/{chat_id}")
        await self._raise_for_status(r)

    async def get_score(
        self,
        chat_id: int,
        date: Optional[str] = None,
        asset: Optional[str] = None,
    ) -> Dict[str, Any]:
        params = {}
        if date:
            params["date"] = date
        if asset:
            params["asset"] = asset
        async with self._client() as c:
            r = await c.get(f"/v1/users/{chat_id}/score", params=params)
        await self._raise_for_status(r)
        return r.json()
```

- [ ] **Step 4: 테스트 실행**

```bash
.venv/Scripts/python.exe -m pytest tests/test_api_client.py -v
```
Expected: 6 passed.

- [ ] **Step 5: 커밋**

```bash
git add src/sajucandle/api_client.py tests/test_api_client.py
git commit -m "feat(bot): add httpx-based ApiClient wrapper"
```

---

## Task 12: 봇 핸들러 리팩터링 — `/start`, `/help`

**Files:**
- Modify: `D:\사주캔들\src\sajucandle\handlers.py`
- Modify: `D:\사주캔들\tests\test_handlers.py`

- [ ] **Step 1: 기존 test_handlers.py 백업 & 리뷰**

```bash
cp tests/test_handlers.py tests/test_handlers.py.bak
cat tests/test_handlers.py
```
기존 테스트가 `_engine` 목킹 전제라면 api_client 목킹 방식으로 재작성해야 함.

- [ ] **Step 2: 새 핸들러 테스트 작성 (기존 파일 덮어쓰기)**

`tests/test_handlers.py`:
```python
"""핸들러 테스트. api_client를 respx로 목킹."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from sajucandle import handlers
from sajucandle.api_client import NotFoundError


def _update(text: str, chat_id: int = 12345):
    """최소 Update + Message 목."""
    msg = MagicMock()
    msg.reply_text = AsyncMock()
    msg.text = text
    msg.chat_id = chat_id
    upd = MagicMock()
    upd.message = msg
    upd.effective_chat.id = chat_id
    return upd


def _ctx(args: list[str]):
    ctx = MagicMock()
    ctx.args = args
    return ctx


# ── parse_birth_args 기존 테스트 유지 ──

def test_parse_birth_args_valid():
    assert handlers.parse_birth_args(["1990-03-15", "14:00"]) == (1990, 3, 15, 14, 0)


def test_parse_birth_args_hour_only():
    assert handlers.parse_birth_args(["1990-03-15", "14"]) == (1990, 3, 15, 14, 0)


def test_parse_birth_args_too_few_args_raises():
    with pytest.raises(handlers.BirthParseError):
        handlers.parse_birth_args(["1990-03-15"])


def test_parse_birth_args_bad_date_raises():
    with pytest.raises(handlers.BirthParseError):
        handlers.parse_birth_args(["bad", "14:00"])


# ── /start ──

async def test_start_with_no_args_shows_help(monkeypatch):
    upd = _update("/start")
    await handlers.start_command(upd, _ctx([]))
    upd.message.reply_text.assert_awaited_once()
    call_text = upd.message.reply_text.await_args.args[0]
    assert "/start" in call_text


async def test_start_valid_calls_put_user_and_replies_card(monkeypatch):
    fake = MagicMock()
    fake.put_user = AsyncMock(return_value={
        "telegram_chat_id": 12345,
        "birth_year": 1990, "birth_month": 3, "birth_day": 15,
        "birth_hour": 14, "birth_minute": 0,
        "asset_class_pref": "swing",
        "created_at": "2026-04-16T00:00:00Z",
        "updated_at": "2026-04-16T00:00:00Z",
    })
    monkeypatch.setattr(handlers, "_api_client", fake)

    upd = _update("/start 1990-03-15 14:00")
    await handlers.start_command(upd, _ctx(["1990-03-15", "14:00"]))

    fake.put_user.assert_awaited_once()
    call_kwargs = fake.put_user.await_args.kwargs
    assert call_kwargs["birth_year"] == 1990
    upd.message.reply_text.assert_awaited_once()


# ── /score ──

async def test_score_replies_with_score(monkeypatch):
    fake = MagicMock()
    fake.get_score = AsyncMock(return_value={
        "chat_id": 12345,
        "date": "2026-04-16",
        "asset_class": "swing",
        "iljin": "庚申",
        "composite_score": 72,
        "signal_grade": "👍 진입각",
        "axes": {
            "wealth":     {"score": 78, "reason": "재성 투간"},
            "decision":   {"score": 65, "reason": ""},
            "volatility": {"score": 70, "reason": ""},
            "flow":       {"score": 75, "reason": ""},
        },
        "best_hours": [
            {"shichen": "巳", "time_range": "09:00~11:00", "multiplier": 1.15},
        ],
    })
    monkeypatch.setattr(handlers, "_api_client", fake)

    upd = _update("/score")
    await handlers.score_command(upd, _ctx([]))

    fake.get_score.assert_awaited_once_with(12345, date=None, asset=None)
    text = upd.message.reply_text.await_args.args[0]
    assert "72" in text
    assert "진입각" in text


async def test_score_404_tells_user_to_register(monkeypatch):
    fake = MagicMock()
    fake.get_score = AsyncMock(side_effect=NotFoundError(404, "user not found"))
    monkeypatch.setattr(handlers, "_api_client", fake)

    upd = _update("/score")
    await handlers.score_command(upd, _ctx([]))

    text = upd.message.reply_text.await_args.args[0]
    assert "/start" in text


async def test_score_with_asset_arg(monkeypatch):
    fake = MagicMock()
    fake.get_score = AsyncMock(return_value={
        "chat_id": 12345, "date": "2026-04-16", "asset_class": "scalp",
        "iljin": "甲子", "composite_score": 50, "signal_grade": "😐 관망",
        "axes": {
            "wealth": {"score": 50, "reason": ""},
            "decision": {"score": 50, "reason": ""},
            "volatility": {"score": 50, "reason": ""},
            "flow": {"score": 50, "reason": ""},
        },
        "best_hours": [],
    })
    monkeypatch.setattr(handlers, "_api_client", fake)

    await handlers.score_command(_update("/score scalp"), _ctx(["scalp"]))
    fake.get_score.assert_awaited_once_with(12345, date=None, asset="scalp")


# ── /me ──

async def test_me_shows_profile(monkeypatch):
    fake = MagicMock()
    fake.get_user = AsyncMock(return_value={
        "telegram_chat_id": 12345,
        "birth_year": 1990, "birth_month": 3, "birth_day": 15,
        "birth_hour": 14, "birth_minute": 0,
        "asset_class_pref": "swing",
        "created_at": "2026-04-16T00:00:00Z",
        "updated_at": "2026-04-16T00:00:00Z",
    })
    monkeypatch.setattr(handlers, "_api_client", fake)

    await handlers.me_command(_update("/me"), _ctx([]))
    fake.get_user.assert_awaited_once_with(12345)
    text = upd_text = fake  # placeholder reference removed
    reply = handlers  # ensure accessible
    assert "1990" in (
        (await AsyncMock(return_value=None)()) or ""
    ) or True  # soft check


async def test_me_404(monkeypatch):
    fake = MagicMock()
    fake.get_user = AsyncMock(side_effect=NotFoundError(404, "nope"))
    monkeypatch.setattr(handlers, "_api_client", fake)

    upd = _update("/me")
    await handlers.me_command(upd, _ctx([]))
    assert "/start" in upd.message.reply_text.await_args.args[0]


# ── /forget ──

async def test_forget_deletes(monkeypatch):
    fake = MagicMock()
    fake.delete_user = AsyncMock(return_value=None)
    monkeypatch.setattr(handlers, "_api_client", fake)

    upd = _update("/forget")
    await handlers.forget_command(upd, _ctx([]))
    fake.delete_user.assert_awaited_once_with(12345)
    assert upd.message.reply_text.await_count == 1


# ── /help ──

async def test_help_lists_commands():
    upd = _update("/help")
    await handlers.help_command(upd, _ctx([]))
    text = upd.message.reply_text.await_args.args[0]
    for cmd in ("/start", "/score", "/me", "/forget"):
        assert cmd in text
```

**주의:** `test_me_shows_profile`의 soft check는 좀 어색하니 깔끔하게 다시:

기존 테스트 파일 전체에서 `test_me_shows_profile`만 교체:
```python
async def test_me_shows_profile(monkeypatch):
    fake = MagicMock()
    fake.get_user = AsyncMock(return_value={
        "telegram_chat_id": 12345,
        "birth_year": 1990, "birth_month": 3, "birth_day": 15,
        "birth_hour": 14, "birth_minute": 0,
        "asset_class_pref": "swing",
        "created_at": "2026-04-16T00:00:00Z",
        "updated_at": "2026-04-16T00:00:00Z",
    })
    monkeypatch.setattr(handlers, "_api_client", fake)

    upd = _update("/me")
    await handlers.me_command(upd, _ctx([]))
    fake.get_user.assert_awaited_once_with(12345)
    text = upd.message.reply_text.await_args.args[0]
    assert "1990" in text
    assert "swing" in text
```
(위에 있던 placeholder 덩어리는 전부 삭제하고 이걸로.)

- [ ] **Step 3: FAIL 확인**

```bash
.venv/Scripts/python.exe -m pytest tests/test_handlers.py -v
```
Expected: 대부분 FAIL (핸들러 함수 없음).

- [ ] **Step 4: `handlers.py` 전체 재작성**

`src/sajucandle/handlers.py`:
```python
"""Telegram 커맨드 핸들러. API 호출만 수행, 엔진/DB 직접 접근 금지."""
from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Optional

import httpx
from telegram import Update
from telegram.ext import ContextTypes

from sajucandle.api_client import ApiClient, ApiError, NotFoundError

logger = logging.getLogger(__name__)


class BirthParseError(ValueError):
    pass


def parse_birth_args(args: list[str]) -> tuple[int, int, int, int, int]:
    """`/start YYYY-MM-DD HH:MM` → (year, month, day, hour, minute)."""
    if len(args) < 2:
        raise BirthParseError(
            "사용법: /start YYYY-MM-DD HH:MM\n예: /start 1990-03-15 14:00"
        )
    date_str, time_str = args[0], args[1]
    try:
        date_part = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError as e:
        raise BirthParseError(
            f"날짜 형식이 잘못되었습니다 (YYYY-MM-DD): {date_str}"
        ) from e
    time_part = None
    for fmt in ("%H:%M:%S", "%H:%M", "%H"):
        try:
            time_part = datetime.strptime(time_str, fmt).time()
            break
        except ValueError:
            continue
    if time_part is None:
        raise BirthParseError(f"시각 형식이 잘못되었습니다 (HH:MM): {time_str}")
    return (
        date_part.year, date_part.month, date_part.day,
        time_part.hour, time_part.minute,
    )


def _build_api_client() -> ApiClient:
    base = os.environ.get("SAJUCANDLE_API_BASE_URL", "http://127.0.0.1:8000")
    key = os.environ.get("SAJUCANDLE_API_KEY", "")
    return ApiClient(base_url=base, api_key=key, timeout=10.0)


_api_client = _build_api_client()


async def _network_safe(reply_fn, coro):
    """httpx 네트워크 에러 → 사용자 메시지로 변환."""
    try:
        return await coro
    except NotFoundError:
        raise
    except httpx.TimeoutException:
        await reply_fn("서버 응답이 느립니다. 잠시 후 다시 시도해주세요.")
        return None
    except httpx.TransportError as e:
        logger.warning("transport error: %s", e)
        await reply_fn("서버에 연결할 수 없습니다. 잠시 후 다시 시도해주세요.")
        return None
    except ApiError as e:
        logger.warning("api error: %s", e)
        await reply_fn(f"서버 오류가 발생했습니다. ({e.status})")
        return None


# ─────────────────────────────────────────────
# Commands
# ─────────────────────────────────────────────

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    args = list(context.args or [])
    if not args:
        await update.message.reply_text(
            "사용법:\n/start YYYY-MM-DD HH:MM\n예: /start 1990-03-15 14:00\n\n"
            "생년월일시를 저장하면 매일 /score 로 그날 점수를 볼 수 있습니다."
        )
        return
    try:
        year, month, day, hour, minute = parse_birth_args(args)
    except BirthParseError as e:
        await update.message.reply_text(str(e))
        return

    chat_id = update.effective_chat.id
    result = await _network_safe(
        update.message.reply_text,
        _api_client.put_user(
            chat_id,
            birth_year=year, birth_month=month, birth_day=day,
            birth_hour=hour, birth_minute=minute,
            asset_class_pref="swing",
        ),
    )
    if result is None:
        return

    await update.message.reply_text(
        f"✅ 등록 완료.\n"
        f"생년월일: {year:04d}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}\n"
        f"이제 /score 로 오늘 점수를 확인하세요."
    )


async def score_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    chat_id = update.effective_chat.id
    args = list(context.args or [])
    asset: Optional[str] = args[0] if args else None

    try:
        data = await _api_client.get_score(chat_id, date=None, asset=asset)
    except NotFoundError:
        await update.message.reply_text(
            "먼저 생년월일을 등록하세요.\n예: /start 1990-03-15 14:00"
        )
        return
    except httpx.TimeoutException:
        await update.message.reply_text("서버 응답이 느립니다. 잠시 후 다시.")
        return
    except httpx.TransportError:
        await update.message.reply_text("서버에 연결할 수 없습니다.")
        return
    except ApiError as e:
        await update.message.reply_text(f"서버 오류 ({e.status}).")
        return

    lines = [
        f"── {data['date']} ({data['iljin']}) ── [{data['asset_class']}]",
        f"재물운: {data['axes']['wealth']['score']:>3}  | {data['axes']['wealth']['reason']}",
        f"결단운: {data['axes']['decision']['score']:>3}  | {data['axes']['decision']['reason']}",
        f"충돌운: {data['axes']['volatility']['score']:>3}  | {data['axes']['volatility']['reason']}",
        f"합  운: {data['axes']['flow']['score']:>3}  | {data['axes']['flow']['reason']}",
        "────────────────────────────────",
        f"종합: {data['composite_score']:>3}  | {data['signal_grade']}",
    ]
    if data["best_hours"]:
        hrs = ", ".join(f"{h['shichen']}시 {h['time_range']}" for h in data["best_hours"])
        lines.append(f"추천 시진: {hrs}")
    await update.message.reply_text("\n".join(lines))


async def me_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    chat_id = update.effective_chat.id
    try:
        data = await _api_client.get_user(chat_id)
    except NotFoundError:
        await update.message.reply_text(
            "등록된 정보가 없습니다.\n/start YYYY-MM-DD HH:MM 로 먼저 등록하세요."
        )
        return
    except httpx.TimeoutException:
        await update.message.reply_text("서버 응답이 느립니다.")
        return
    except httpx.TransportError:
        await update.message.reply_text("서버에 연결할 수 없습니다.")
        return
    except ApiError as e:
        await update.message.reply_text(f"서버 오류 ({e.status}).")
        return

    await update.message.reply_text(
        f"등록된 정보:\n"
        f"생년월일: {data['birth_year']:04d}-{data['birth_month']:02d}-{data['birth_day']:02d}\n"
        f"시각: {data['birth_hour']:02d}:{data['birth_minute']:02d}\n"
        f"선호 자산군: {data['asset_class_pref']}\n"
        f"(변경은 /start 로 재등록, 삭제는 /forget)"
    )


async def forget_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    chat_id = update.effective_chat.id
    try:
        await _api_client.delete_user(chat_id)
    except httpx.TimeoutException:
        await update.message.reply_text("서버 응답이 느립니다. 잠시 후 다시.")
        return
    except httpx.TransportError:
        await update.message.reply_text("서버에 연결할 수 없습니다.")
        return
    except ApiError as e:
        await update.message.reply_text(f"서버 오류 ({e.status}).")
        return
    await update.message.reply_text("🗑️ 등록된 정보를 모두 삭제했습니다.")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    await update.message.reply_text(
        "SajuCandle 봇 사용법\n"
        "─────────────\n"
        "/start YYYY-MM-DD HH:MM — 생년월일시 등록\n"
        "/score [swing|scalp|long] — 오늘 점수\n"
        "/me — 등록된 정보 확인\n"
        "/forget — 내 정보 삭제\n"
        "/help — 이 도움말\n"
        "\n※ 엔터테인먼트 목적. 투자 추천 아님."
    )
```

- [ ] **Step 5: 테스트 실행**

```bash
.venv/Scripts/python.exe -m pytest tests/test_handlers.py -v
```
Expected: 모든 테스트 passed.

- [ ] **Step 6: 백업 파일 삭제**

```bash
rm tests/test_handlers.py.bak
```

- [ ] **Step 7: 커밋**

```bash
git add src/sajucandle/handlers.py tests/test_handlers.py
git commit -m "refactor(bot): migrate handlers to ApiClient, add /score /me /forget /help"
```

---

## Task 13: `bot.py`에 새 핸들러 등록

**Files:**
- Modify: `D:\사주캔들\src\sajucandle\bot.py`

- [ ] **Step 1: 기존 bot.py 읽기**

```bash
cat src/sajucandle/bot.py
```

- [ ] **Step 2: 새 핸들러 등록 추가**

`bot.py`의 `CommandHandler` 등록부를 다음과 같이 수정 (기존 `start_command` 등록은 유지하고 추가):
```python
from sajucandle.handlers import (
    forget_command,
    help_command,
    me_command,
    score_command,
    start_command,
)

# ... 기존 Application 생성 후 ...
app.add_handler(CommandHandler("start", start_command))
app.add_handler(CommandHandler("score", score_command))
app.add_handler(CommandHandler("me", me_command))
app.add_handler(CommandHandler("forget", forget_command))
app.add_handler(CommandHandler("help", help_command))
```

실제 구조는 기존 파일에 맞게. import 수정 + add_handler 4줄 추가가 전부.

- [ ] **Step 3: 봇 로컬 스모크 (토큰 있으면)**

```bash
# 환경변수 세팅 후
.venv/Scripts/python.exe -m sajucandle.bot
```
Expected: "봇 실행 중..." 로그. Telegram에서 `/help` 보내면 도움말이 답장.
토큰 없으면 이 단계 skip.

- [ ] **Step 4: 커밋**

```bash
git add src/sajucandle/bot.py
git commit -m "feat(bot): register /score /me /forget /help handlers"
```

---

## Task 14: `/health` DB 핑 확인 (이미 Task 8에서 반영됨) + 전체 회귀

**Files:**
- 검증만

- [ ] **Step 1: 전체 테스트**

```bash
cd "D:/사주캔들"
.venv/Scripts/python.exe -m pytest -v
```
Expected: 기존 26개 + 이번 주 추가분 전부 green. DB/TEST_DATABASE_URL 없으면 일부 skip.

- [ ] **Step 2: ruff 린트**

```bash
.venv/Scripts/python.exe -m ruff check .
```
Expected: 0 errors. 있으면 고치고 커밋.

- [ ] **Step 3: API 로컬 실행 + /health**

```powershell
$env:SAJUCANDLE_API_KEY = "local-dev-key"
$env:DATABASE_URL = "<TEST_DATABASE_URL과 동일>"
.venv/Scripts/python.exe -m uvicorn sajucandle.api:app --host 127.0.0.1 --port 8000
```
다른 터미널:
```powershell
curl.exe http://127.0.0.1:8000/health
```
Expected: `{"status":"ok","db":"up"}`

- [ ] **Step 4: 커밋 (lint 고친 게 있으면)**

```bash
git add -A
git commit -m "chore: lint pass for Week 3"
```
변경 없으면 skip.

---

## Task 15: README 업데이트

**Files:**
- Modify: `D:\사주캔들\README.md`

- [ ] **Step 1: 새 섹션 append (Week 3 기능 설명)**

README.md의 "주요 명령 정리" 전에 추가:
```markdown
## Week 3 기능 (사주 점수)

### 봇 커맨드
| Command | 설명 |
|---------|------|
| `/start YYYY-MM-DD HH:MM` | 생년월일시 등록 |
| `/score [swing\|scalp\|long]` | 오늘의 일진 점수 |
| `/me` | 등록된 내 정보 |
| `/forget` | 내 정보 삭제 |
| `/help` | 도움말 |

### 신규 API 엔드포인트
- `PUT    /v1/users/{chat_id}` — upsert
- `GET    /v1/users/{chat_id}` — 조회
- `DELETE /v1/users/{chat_id}` — 삭제 (멱등)
- `GET    /v1/users/{chat_id}/score?date=YYYY-MM-DD&asset=swing` — 일일 점수

### DB 초기화
Supabase Studio → SQL Editor → `migrations/001_init.sql` 실행.

### 신규 환경변수
| 서비스 | 변수 | 예 |
|--------|------|-----|
| sajucandle-api | `DATABASE_URL` | `postgresql://postgres:pw@...supabase.co:5432/postgres` |
| sajucandle-bot | `SAJUCANDLE_API_BASE_URL` | `https://sajucandle-api-production.up.railway.app` |
| sajucandle-bot | `SAJUCANDLE_API_KEY` | (API와 동일 키) |

### 테스트 DB
로컬 테스트 실행 시 `TEST_DATABASE_URL`을 Supabase DSN 또는 로컬 Postgres로 지정:
```powershell
$env:TEST_DATABASE_URL = "postgresql://..."
pytest -v
```
```

- [ ] **Step 2: 커밋**

```bash
git add README.md
git commit -m "docs: README update for Week 3 score API + bot commands"
```

---

## Task 16: 사람 작업 — Supabase 셋업

**자동화 안 됨. 사용자가 직접.**

- [ ] **Step 1: Supabase 프로젝트 생성**
  1. https://supabase.com 로그인
  2. New project → Name: `sajucandle-db`, Region: `Northeast Asia (Seoul)`, DB password 설정
  3. 생성 후 Settings → Database → Connection string → **URI** (session pooler 권장: port 6543)
  4. 예: `postgresql://postgres.xxxxxx:<PASSWORD>@aws-0-ap-northeast-2.pooler.supabase.com:6543/postgres`

- [ ] **Step 2: 스키마 적용**

Supabase Studio → SQL Editor → New query → `migrations/001_init.sql` 내용 붙여넣고 Run.

확인:
```sql
SELECT table_name FROM information_schema.tables WHERE table_schema='public';
-- users, user_bazi 나와야 함
```

- [ ] **Step 3: 로컬 테스트 실행 검증**

```powershell
$env:TEST_DATABASE_URL = "<위 URI>"
.venv/Scripts/python.exe -m pytest tests/test_repositories.py tests/test_api_users.py tests/test_api_score.py -v
```
Expected: 모두 PASS.

---

## Task 17: 사람 작업 — Railway 배포

- [ ] **Step 1: sajucandle-api 서비스에 env 추가**

Railway Dashboard → sajucandle-api → Variables:
- `DATABASE_URL` = Supabase URI (위와 동일)
- 기존 `REDIS_URL`, `SAJUCANDLE_API_KEY` 유지 확인

- [ ] **Step 2: sajucandle-bot 서비스에 env 추가**

Railway Dashboard → sajucandle-bot → Variables:
- `SAJUCANDLE_API_BASE_URL` = `https://sajucandle-api-production.up.railway.app` (본인 도메인)
- `SAJUCANDLE_API_KEY` = API 서비스와 동일 키

- [ ] **Step 3: 재배포 및 헬스체크**

```powershell
curl.exe https://sajucandle-api-production.up.railway.app/health
```
Expected: `{"status":"ok","db":"up"}`

- [ ] **Step 4: 봇 e2e 테스트**

Telegram에서 본인 계정으로:
1. `/start 1990-03-15 14:00` → "✅ 등록 완료" + 안내
2. `/me` → 등록 정보 표시
3. `/score` → 오늘 점수 카드
4. `/score scalp` → 스캘프 점수
5. `/forget` → "🗑️ 삭제" 메시지
6. `/me` → "등록된 정보 없음"

- [ ] **Step 5: 최종 커밋 (문서 업데이트 있으면)**

필요 시:
```bash
git add -A
git commit -m "chore: finalize Week 3 deployment"
```

---

## 자기 검토 (Self-Review)

**Spec 커버리지:**
- §2 아키텍처 → Task 12~13
- §3 스키마 → Task 2
- §4.1 PUT → Task 8
- §4.2 GET → Task 9
- §4.3 DELETE → Task 9
- §4.4 score → Task 10
- §5 봇 커맨드 5개 → Task 12~13
- §6 신규 파일 → Task 3, 5, 7, 11
- §7 캐싱 → Task 7 (score:{chat_id}:{date}:{asset} + KST 자정 TTL)
- §8 시크릿 → Task 16, 17
- §9 에러 처리 → Task 8/10 (503/404/400), Task 12 (timeout/transport)
- §10 테스트 전략 → Task 4 (트랜잭션 롤백), 11 (respx), 12 (핸들러 목)
- §12 OOS → 건드리지 않음 ✓

**Placeholder 스캔:** `TODO/TBD/fill in` 없음. 모든 코드 블록은 실제 구현. 일부 JSON 예시의 `"reason": "..."`는 의도적 샘플값 (테스트에서도 동일 패턴).

**타입 일관성:**
- `UserProfile` dataclass 필드 == Pydantic `UserProfileRequest/Response` 필드 ✓
- `ApiClient.put_user/get_user/delete_user/get_score` → 핸들러에서 정확히 동일 메서드명 호출 ✓
- `ScoreService.compute(profile, target_date, asset_class)` 시그니처 일관 ✓
- `AssetClass = Literal["swing","scalp","long","default"]` — `asset_class_pref` DB CHECK와 일치 ✓

---

## 실행 옵션

플랜 완성. 저장 위치: `docs/superpowers/plans/2026-04-16-week3-saju-score.md`.

**두 가지 실행 방식 중 선택:**

1. **Subagent-Driven (권장)** — 태스크마다 새 서브에이전트를 띄워서 실행, 태스크 간 리뷰, 이슈 빠르게 감지
2. **Inline Execution** — 이 세션에서 순서대로 실행, 체크포인트마다 리뷰

어느 쪽으로 갈까요?

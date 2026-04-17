# Week 7: Watchlist + 모닝 카드 통합 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 사용자별 watchlist(최대 5개)를 DB에 저장하고, 매일 07:00 모닝 푸시에 사주 카드(기존) + watchlist 시그널 요약(신규)을 각각 1통씩 발송한다.

**Architecture:** `user_watchlist` 테이블(복합 PK + ON DELETE CASCADE) + repositories CRUD + API 엔드포인트 4개 + 봇 명령어 3개(`/watch`, `/unwatch`, `/watchlist`). Broadcast는 Phase 1 Precompute(캐시 워밍) + Phase 2 기존 사주 카드(회귀 0) + Phase 3 Watchlist 요약으로 확장. Phase 3은 `--skip-watchlist` 플래그로 off 가능.

**Tech Stack:** Python 3.12, FastAPI, python-telegram-bot 21, asyncpg, pydantic v2, pytest, pytest-asyncio, respx, fakeredis, httpx. hatchling + PEP 621 빌드.

**Spec:** `docs/superpowers/specs/2026-04-17-week7-watchlist-design.md` (commit 16e4602)

**스펙 교정 노트:** 스펙 §10의 "db.py lifespan의 CREATE TABLE IF NOT EXISTS에 추가"는 틀린 정보. 실제로는 `migrations/NNN_*.sql` 파일을 만들고 Supabase Studio에서 수동 실행한다 (기존 `001_init.sql` 패턴). 이 플랜은 올바른 경로로 진행.

---

## File Structure (New / Modified)

```
migrations/
├── 001_init.sql                  # 기존 — 건드리지 않음
└── 002_watchlist.sql             # [CREATE] user_watchlist 테이블

src/sajucandle/
├── repositories.py               # [MODIFY] WatchlistEntry + 5개 함수
├── models.py                     # [MODIFY] WatchlistAddRequest, WatchlistItem, WatchlistResponse
├── api.py                        # [MODIFY] 4개 watchlist 엔드포인트
├── api_client.py                 # [MODIFY] 4개 watchlist 메서드
├── handlers.py                   # [MODIFY] /watch, /unwatch, /watchlist, /help
└── broadcast.py                  # [MODIFY] Phase 1 precompute + Phase 3 watchlist 요약 + --skip-watchlist

tests/
├── test_repositories.py          # [MODIFY] watchlist CRUD (db_conn 픽스처 재사용)
├── test_api_watchlist.py         # [CREATE] 엔드포인트 4개
├── test_api_client.py            # [MODIFY] 4개 메서드 respx mock
├── test_handlers.py              # [MODIFY] /watch /unwatch /watchlist 시나리오
└── test_broadcast.py             # [MODIFY] precompute / watchlist 요약 / skip 플래그

README.md                         # [MODIFY] Week 7 섹션 추가, 테스트 수 갱신
```

**운영 작업 (user manual step, Task 1의 일부):**
- Supabase Studio에서 `migrations/002_watchlist.sql` 실행
- Railway `sajucandle-broadcast` 서비스 Variables에 `SAJUCANDLE_ADMIN_CHAT_ID=7492682272` 추가

---

## Task 1: Create migration SQL + manual deploy notes

**Files:**
- Create: `migrations/002_watchlist.sql`

- [ ] **Step 1: Create migration file**

`D:\사주캔들\migrations\002_watchlist.sql` 신규 작성:

```sql
-- Week 7: user_watchlist 테이블.
-- 실행: Supabase Studio → SQL Editor → Run.
-- 로컬: psql $DATABASE_URL -f migrations/002_watchlist.sql
-- 로컬 테스트 DB: psql $TEST_DATABASE_URL -f migrations/002_watchlist.sql

CREATE TABLE IF NOT EXISTS user_watchlist (
    telegram_chat_id BIGINT NOT NULL
        REFERENCES user_bazi(telegram_chat_id) ON DELETE CASCADE,
    ticker TEXT NOT NULL,
    added_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (telegram_chat_id, ticker)
);

CREATE INDEX IF NOT EXISTS idx_user_watchlist_chat_id
    ON user_watchlist(telegram_chat_id);
```

- [ ] **Step 2: Apply to local TEST DB (if TEST_DATABASE_URL set)**

`TEST_DATABASE_URL` 환경변수가 설정된 로컬 개발 환경이면:

```
psql $env:TEST_DATABASE_URL -f migrations/002_watchlist.sql
```

PowerShell에서 `$env:TEST_DATABASE_URL` 사용. 미설정이면 이 step은 skip — DB 통합 테스트는 어차피 pytest 자동 skip.

Expected: `CREATE TABLE` + `CREATE INDEX` 출력 (또는 `NOTICE: ... already exists`이면 이미 적용됨).

- [ ] **Step 3: Commit migration file**

```
git add migrations/002_watchlist.sql
git commit -m "feat(db): add user_watchlist migration (Week 7)"
```

- [ ] **Step 4: (Deferred) Manual production application**

**운영 DB 적용은 Task 9(최종) 배포 직전에 수행.** 지금은 파일만 커밋.

---

## Task 2: repositories.py — WatchlistEntry + 5개 함수 (TDD, DB 통합 테스트)

**Files:**
- Modify: `src/sajucandle/repositories.py`
- Modify: `tests/test_repositories.py`

- [ ] **Step 1: Write failing tests**

`tests/test_repositories.py` 맨 아래에 추가:

```python
# ─────────────────────────────────────────────
# Week 7: watchlist CRUD
# ─────────────────────────────────────────────

from sajucandle.repositories import (
    WatchlistEntry,
    add_to_watchlist,
    count_watchlist,
    list_all_watchlist_tickers,
    list_watchlist,
    remove_from_watchlist,
)


async def _register_user(db_conn, chat_id: int) -> None:
    """watchlist FK를 만족시키기 위한 전제 사용자 등록."""
    await upsert_user(db_conn, UserProfile(
        telegram_chat_id=chat_id,
        birth_year=1990, birth_month=3, birth_day=15,
        birth_hour=14, birth_minute=0,
        asset_class_pref="swing",
    ))


async def test_list_watchlist_empty(db_conn):
    await _register_user(db_conn, 100001)
    items = await list_watchlist(db_conn, 100001)
    assert items == []


async def test_add_and_list_watchlist(db_conn):
    await _register_user(db_conn, 100002)
    await add_to_watchlist(db_conn, 100002, "AAPL")
    items = await list_watchlist(db_conn, 100002)
    assert len(items) == 1
    assert items[0].ticker == "AAPL"
    assert items[0].added_at is not None


async def test_list_watchlist_ordered_by_added_at_asc(db_conn):
    await _register_user(db_conn, 100003)
    await add_to_watchlist(db_conn, 100003, "AAPL")
    await add_to_watchlist(db_conn, 100003, "MSFT")
    await add_to_watchlist(db_conn, 100003, "BTCUSDT")
    items = await list_watchlist(db_conn, 100003)
    tickers = [i.ticker for i in items]
    assert tickers == ["AAPL", "MSFT", "BTCUSDT"]


async def test_add_duplicate_raises_unique_violation(db_conn):
    import asyncpg
    await _register_user(db_conn, 100004)
    await add_to_watchlist(db_conn, 100004, "AAPL")
    with pytest.raises(asyncpg.UniqueViolationError):
        await add_to_watchlist(db_conn, 100004, "AAPL")


async def test_remove_from_watchlist_returns_true_when_existed(db_conn):
    await _register_user(db_conn, 100005)
    await add_to_watchlist(db_conn, 100005, "AAPL")
    deleted = await remove_from_watchlist(db_conn, 100005, "AAPL")
    assert deleted is True
    items = await list_watchlist(db_conn, 100005)
    assert items == []


async def test_remove_from_watchlist_returns_false_when_missing(db_conn):
    await _register_user(db_conn, 100006)
    deleted = await remove_from_watchlist(db_conn, 100006, "AAPL")
    assert deleted is False


async def test_count_watchlist(db_conn):
    await _register_user(db_conn, 100007)
    assert await count_watchlist(db_conn, 100007) == 0
    await add_to_watchlist(db_conn, 100007, "AAPL")
    await add_to_watchlist(db_conn, 100007, "MSFT")
    assert await count_watchlist(db_conn, 100007) == 2


async def test_list_all_watchlist_tickers_union(db_conn):
    await _register_user(db_conn, 100008)
    await _register_user(db_conn, 100009)
    await add_to_watchlist(db_conn, 100008, "AAPL")
    await add_to_watchlist(db_conn, 100008, "TSLA")
    await add_to_watchlist(db_conn, 100009, "AAPL")   # 중복 (union 처리 검증)
    await add_to_watchlist(db_conn, 100009, "BTCUSDT")
    symbols = await list_all_watchlist_tickers(db_conn)
    assert symbols == {"AAPL", "TSLA", "BTCUSDT"}


async def test_delete_user_cascades_watchlist(db_conn):
    await _register_user(db_conn, 100010)
    await add_to_watchlist(db_conn, 100010, "AAPL")
    await delete_user(db_conn, 100010)
    # user_bazi 삭제 → watchlist도 CASCADE
    items = await list_watchlist(db_conn, 100010)
    assert items == []
```

파일 상단에 `import pytest`가 이미 있는지 확인. 없으면 추가.

- [ ] **Step 2: Run tests to verify they fail**

Run:
```
pytest tests/test_repositories.py -v -k "watchlist"
```

Expected: `ImportError: cannot import name 'WatchlistEntry' from 'sajucandle.repositories'`.

`TEST_DATABASE_URL` 미설정 시 전부 skip — 이 경우 Step 3으로 진행하되 검증은 CI/다른 환경에서. 로컬 개발 환경이 TEST_DATABASE_URL 있으면 실제 실패 확인.

- [ ] **Step 3: Implement in repositories.py**

`src/sajucandle/repositories.py` 맨 아래(`list_chat_ids` 함수 다음)에 추가:

```python
# ─────────────────────────────────────────────
# Week 7: watchlist
# ─────────────────────────────────────────────


@dataclass
class WatchlistEntry:
    ticker: str
    added_at: datetime


async def list_watchlist(
    conn: asyncpg.Connection, chat_id: int
) -> list[WatchlistEntry]:
    """사용자의 watchlist (added_at ASC). 비어있으면 []."""
    rows = await conn.fetch(
        "SELECT ticker, added_at FROM user_watchlist "
        "WHERE telegram_chat_id = $1 ORDER BY added_at ASC",
        chat_id,
    )
    return [WatchlistEntry(ticker=r["ticker"], added_at=r["added_at"]) for r in rows]


async def add_to_watchlist(
    conn: asyncpg.Connection, chat_id: int, ticker: str
) -> None:
    """INSERT. 중복이면 asyncpg.UniqueViolationError 전파."""
    await conn.execute(
        "INSERT INTO user_watchlist (telegram_chat_id, ticker) VALUES ($1, $2)",
        chat_id, ticker,
    )


async def remove_from_watchlist(
    conn: asyncpg.Connection, chat_id: int, ticker: str
) -> bool:
    """DELETE. True=삭제됨, False=애초에 없었음."""
    result = await conn.execute(
        "DELETE FROM user_watchlist "
        "WHERE telegram_chat_id = $1 AND ticker = $2",
        chat_id, ticker,
    )
    # asyncpg execute는 "DELETE N" 형태 문자열 반환
    return result.endswith(" 1")


async def count_watchlist(
    conn: asyncpg.Connection, chat_id: int
) -> int:
    """현재 등록된 심볼 개수."""
    n = await conn.fetchval(
        "SELECT COUNT(*) FROM user_watchlist WHERE telegram_chat_id = $1",
        chat_id,
    )
    return int(n or 0)


async def list_all_watchlist_tickers(
    conn: asyncpg.Connection,
) -> set[str]:
    """모든 사용자 watchlist ticker union. broadcast precompute용."""
    rows = await conn.fetch("SELECT DISTINCT ticker FROM user_watchlist")
    return {r["ticker"] for r in rows}
```

- [ ] **Step 4: Run tests — PASS**

Run:
```
pytest tests/test_repositories.py -v
```

Expected (TEST_DATABASE_URL 있는 경우): 기존 테스트 + 신규 9개 전량 통과.
Expected (없는 경우): 전부 skip, 단 import error는 없어야 함.

- [ ] **Step 5: Full suite regression**

Run:
```
pytest -q
```

Expected: 회귀 0. TEST_DATABASE_URL 설정 여부에 따라 passed 수 다름.

- [ ] **Step 6: Commit**

```
git add src/sajucandle/repositories.py tests/test_repositories.py
git commit -m "feat(repo): add watchlist CRUD (list/add/remove/count/union)"
```

---

## Task 3: api.py — 4개 엔드포인트 + Pydantic 모델 (TDD)

**Files:**
- Modify: `src/sajucandle/models.py`
- Modify: `src/sajucandle/api.py`
- Create: `tests/test_api_watchlist.py`

5개 제한 검증 + MarketRouter 화이트리스트 검증 + 409/400/404 에러 매핑.

- [ ] **Step 1: Add Pydantic models**

`src/sajucandle/models.py` 맨 아래에 추가:

```python
# ─────────────────────────────────────────────
# Week 7: Watchlist
# ─────────────────────────────────────────────


class WatchlistAddRequest(BaseModel):
    """POST /v1/users/{chat_id}/watchlist body."""
    ticker: str = Field(min_length=1, max_length=16)


class WatchlistItem(BaseModel):
    ticker: str
    added_at: datetime


class WatchlistResponse(BaseModel):
    items: List[WatchlistItem]


class WatchlistSymbolsResponse(BaseModel):
    symbols: List[str]
```

- [ ] **Step 2: Write failing tests**

`tests/test_api_watchlist.py` 신규 작성. 기존 `tests/test_api_signal.py`의 TestClient 구성 패턴을 참조한다. 핵심 fixture:

```python
"""api: watchlist 엔드포인트. DB 모의 없이 실제 test DB 사용."""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from sajucandle import db
from sajucandle.api import create_app


TEST_DSN = os.environ.get("TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    TEST_DSN is None, reason="TEST_DATABASE_URL not set"
)


@pytest.fixture
def api_key(monkeypatch):
    monkeypatch.setenv("SAJUCANDLE_API_KEY", "test-key")
    return "test-key"


@pytest.fixture
def client(api_key, monkeypatch):
    """TestClient. create_app()은 lifespan으로 DB 연결."""
    monkeypatch.setenv("DATABASE_URL", TEST_DSN)
    app = create_app()
    with TestClient(app) as c:
        yield c


CHAT_ID = 900001
HEADERS = {"X-SAJUCANDLE-KEY": "test-key"}


def _register_user(client):
    """테스트 전제: 사용자 등록."""
    r = client.put(
        f"/v1/users/{CHAT_ID}",
        json={
            "birth_year": 1990, "birth_month": 3, "birth_day": 15,
            "birth_hour": 14, "birth_minute": 0,
            "asset_class_pref": "swing",
        },
        headers=HEADERS,
    )
    assert r.status_code == 200, r.text


def _cleanup(client):
    """테스트 후 정리 — DELETE cascade."""
    client.delete(f"/v1/users/{CHAT_ID}", headers=HEADERS)


def test_list_watchlist_requires_api_key(client):
    r = client.get(f"/v1/users/{CHAT_ID}/watchlist")
    assert r.status_code == 401


def test_list_watchlist_empty(client):
    _register_user(client)
    try:
        r = client.get(f"/v1/users/{CHAT_ID}/watchlist", headers=HEADERS)
        assert r.status_code == 200
        assert r.json() == {"items": []}
    finally:
        _cleanup(client)


def test_add_watchlist_success(client):
    _register_user(client)
    try:
        r = client.post(
            f"/v1/users/{CHAT_ID}/watchlist",
            json={"ticker": "AAPL"},
            headers=HEADERS,
        )
        assert r.status_code == 204

        r2 = client.get(f"/v1/users/{CHAT_ID}/watchlist", headers=HEADERS)
        items = r2.json()["items"]
        assert len(items) == 1
        assert items[0]["ticker"] == "AAPL"
    finally:
        _cleanup(client)


def test_add_watchlist_normalizes_symbol(client):
    """`aapl` → `AAPL`, `$AAPL` → `AAPL`."""
    _register_user(client)
    try:
        r = client.post(
            f"/v1/users/{CHAT_ID}/watchlist",
            json={"ticker": "$aapl"},
            headers=HEADERS,
        )
        assert r.status_code == 204
        r2 = client.get(f"/v1/users/{CHAT_ID}/watchlist", headers=HEADERS)
        assert r2.json()["items"][0]["ticker"] == "AAPL"
    finally:
        _cleanup(client)


def test_add_watchlist_unsupported_ticker_400(client):
    _register_user(client)
    try:
        r = client.post(
            f"/v1/users/{CHAT_ID}/watchlist",
            json={"ticker": "AMZN"},
            headers=HEADERS,
        )
        assert r.status_code == 400
        assert "unsupported" in r.json()["detail"].lower()
    finally:
        _cleanup(client)


def test_add_watchlist_duplicate_409_already(client):
    _register_user(client)
    try:
        client.post(
            f"/v1/users/{CHAT_ID}/watchlist",
            json={"ticker": "AAPL"},
            headers=HEADERS,
        )
        r = client.post(
            f"/v1/users/{CHAT_ID}/watchlist",
            json={"ticker": "AAPL"},
            headers=HEADERS,
        )
        assert r.status_code == 409
        assert "already" in r.json()["detail"]
    finally:
        _cleanup(client)


def test_add_watchlist_full_409_full(client):
    """5개 이미 등록된 상태에서 6번째 추가 → 409 full."""
    _register_user(client)
    try:
        for t in ["AAPL", "MSFT", "GOOGL", "NVDA", "TSLA"]:
            r = client.post(
                f"/v1/users/{CHAT_ID}/watchlist",
                json={"ticker": t},
                headers=HEADERS,
            )
            assert r.status_code == 204
        r = client.post(
            f"/v1/users/{CHAT_ID}/watchlist",
            json={"ticker": "BTCUSDT"},
            headers=HEADERS,
        )
        assert r.status_code == 409
        assert "full" in r.json()["detail"]
    finally:
        _cleanup(client)


def test_add_watchlist_user_not_registered_404(client):
    """명식 미등록 사용자 → 404 (FK 실패 매핑)."""
    r = client.post(
        "/v1/users/999999999/watchlist",
        json={"ticker": "AAPL"},
        headers=HEADERS,
    )
    assert r.status_code == 404


def test_remove_watchlist_success(client):
    _register_user(client)
    try:
        client.post(
            f"/v1/users/{CHAT_ID}/watchlist",
            json={"ticker": "AAPL"},
            headers=HEADERS,
        )
        r = client.delete(
            f"/v1/users/{CHAT_ID}/watchlist/AAPL",
            headers=HEADERS,
        )
        assert r.status_code == 204
        r2 = client.get(f"/v1/users/{CHAT_ID}/watchlist", headers=HEADERS)
        assert r2.json()["items"] == []
    finally:
        _cleanup(client)


def test_remove_watchlist_missing_404(client):
    _register_user(client)
    try:
        r = client.delete(
            f"/v1/users/{CHAT_ID}/watchlist/AAPL",
            headers=HEADERS,
        )
        assert r.status_code == 404
        assert "not in watchlist" in r.json()["detail"]
    finally:
        _cleanup(client)


def test_remove_watchlist_normalizes_symbol(client):
    """URL 경로의 소문자도 대문자로 정규화."""
    _register_user(client)
    try:
        client.post(
            f"/v1/users/{CHAT_ID}/watchlist",
            json={"ticker": "AAPL"},
            headers=HEADERS,
        )
        r = client.delete(
            f"/v1/users/{CHAT_ID}/watchlist/aapl",
            headers=HEADERS,
        )
        assert r.status_code == 204
    finally:
        _cleanup(client)


def test_admin_watchlist_symbols_returns_union(client):
    _register_user(client)
    try:
        for t in ["AAPL", "TSLA"]:
            client.post(
                f"/v1/users/{CHAT_ID}/watchlist",
                json={"ticker": t},
                headers=HEADERS,
            )
        r = client.get("/v1/admin/watchlist-symbols", headers=HEADERS)
        assert r.status_code == 200
        symbols = set(r.json()["symbols"])
        assert symbols == {"AAPL", "TSLA"}
    finally:
        _cleanup(client)


def test_admin_watchlist_symbols_requires_api_key(client):
    r = client.get("/v1/admin/watchlist-symbols")
    assert r.status_code == 401
```

- [ ] **Step 3: Run tests to verify fails**

Run:
```
pytest tests/test_api_watchlist.py -v
```

Expected: 404 (엔드포인트 없음) 다수. TEST_DATABASE_URL 없으면 전부 skip.

- [ ] **Step 4: Implement endpoints in api.py**

`src/sajucandle/api.py` 수정:

**(a) 파일 상단 import 섹션에 추가:**

```python
from sajucandle.market.router import MarketRouter  # 기존에 있으면 패스
from sajucandle.models import (
    # 기존 ...
    WatchlistAddRequest,
    WatchlistItem,
    WatchlistResponse,
    WatchlistSymbolsResponse,
)
```

(기존 import 목록 확인 후 필요한 것만 추가.)

**(b) `create_app` 함수 내부, 기존 `/v1/admin/users` 엔드포인트 **다음**에 4개 엔드포인트 추가:**

```python
    _WATCHLIST_MAX = 5

    def _normalize_ticker(t: str) -> str:
        return t.upper().lstrip("$")

    def _ticker_is_supported(t: str) -> bool:
        """MarketRouter.all_symbols()의 ticker set 검증."""
        supported = {s["ticker"] for s in MarketRouter.all_symbols()}
        return t in supported

    @app.get("/v1/users/{chat_id}/watchlist", response_model=WatchlistResponse)
    async def list_watchlist_endpoint(
        chat_id: int,
        request: Request,
        x_sajucandle_key: Optional[str] = Header(default=None),
    ) -> WatchlistResponse:
        _require_api_key(request, x_sajucandle_key)
        if db.get_pool() is None:
            raise HTTPException(503, detail="database not available")
        async with db.acquire() as conn:
            entries = await repositories.list_watchlist(conn, chat_id)
        return WatchlistResponse(
            items=[WatchlistItem(ticker=e.ticker, added_at=e.added_at)
                   for e in entries]
        )

    @app.post("/v1/users/{chat_id}/watchlist", status_code=204)
    async def add_watchlist_endpoint(
        chat_id: int,
        body: WatchlistAddRequest,
        request: Request,
        x_sajucandle_key: Optional[str] = Header(default=None),
    ) -> None:
        _require_api_key(request, x_sajucandle_key)
        if db.get_pool() is None:
            raise HTTPException(503, detail="database not available")

        ticker = _normalize_ticker(body.ticker)
        if not _ticker_is_supported(ticker):
            raise HTTPException(400, detail=f"unsupported ticker: {ticker}")

        import asyncpg
        async with db.acquire() as conn:
            async with conn.transaction():
                # 사용자 존재 확인
                user = await repositories.get_user(conn, chat_id)
                if user is None:
                    raise HTTPException(404, detail="user not found")
                # 5개 제한 (트랜잭션 내)
                n = await repositories.count_watchlist(conn, chat_id)
                if n >= _WATCHLIST_MAX:
                    raise HTTPException(
                        409,
                        detail=f"watchlist full (max {_WATCHLIST_MAX})",
                    )
                try:
                    await repositories.add_to_watchlist(conn, chat_id, ticker)
                except asyncpg.UniqueViolationError:
                    raise HTTPException(409, detail="already in watchlist")
        logger.info(
            "watchlist added chat_id=%s ticker=%s count=%s/%s",
            chat_id, ticker, n + 1, _WATCHLIST_MAX,
        )
        return None

    @app.delete("/v1/users/{chat_id}/watchlist/{ticker}", status_code=204)
    async def remove_watchlist_endpoint(
        chat_id: int,
        ticker: str,
        request: Request,
        x_sajucandle_key: Optional[str] = Header(default=None),
    ) -> None:
        _require_api_key(request, x_sajucandle_key)
        if db.get_pool() is None:
            raise HTTPException(503, detail="database not available")
        t = _normalize_ticker(ticker)
        async with db.acquire() as conn:
            deleted = await repositories.remove_from_watchlist(conn, chat_id, t)
        if not deleted:
            raise HTTPException(404, detail="not in watchlist")
        logger.info("watchlist removed chat_id=%s ticker=%s", chat_id, t)
        return None

    @app.get(
        "/v1/admin/watchlist-symbols",
        response_model=WatchlistSymbolsResponse,
    )
    async def admin_watchlist_symbols_endpoint(
        request: Request,
        x_sajucandle_key: Optional[str] = Header(default=None),
    ) -> WatchlistSymbolsResponse:
        _require_api_key(request, x_sajucandle_key)
        if db.get_pool() is None:
            raise HTTPException(503, detail="database not available")
        async with db.acquire() as conn:
            symbols = await repositories.list_all_watchlist_tickers(conn)
        return WatchlistSymbolsResponse(symbols=sorted(symbols))
```

- [ ] **Step 5: Run tests — PASS**

Run:
```
pytest tests/test_api_watchlist.py -v
```

Expected (TEST_DATABASE_URL 있는 환경): 14 passed. 없으면 skip.

- [ ] **Step 6: Full regression**

```
pytest -q
```

Expected: 회귀 0.

- [ ] **Step 7: Commit**

```
git add src/sajucandle/models.py src/sajucandle/api.py tests/test_api_watchlist.py
git commit -m "feat(api): add watchlist endpoints (list/add/remove/admin union)"
```

---

## Task 4: api_client.py — 4개 메서드 (TDD)

**Files:**
- Modify: `src/sajucandle/api_client.py`
- Modify: `tests/test_api_client.py`

- [ ] **Step 1: Write failing tests**

`tests/test_api_client.py` 맨 아래에 추가:

```python
# ─────────────────────────────────────────────
# Week 7: watchlist
# ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_watchlist_returns_items():
    import respx
    from httpx import Response
    from sajucandle.api_client import ApiClient

    with respx.mock(base_url="http://test") as mock:
        mock.get("/v1/users/42/watchlist").mock(
            return_value=Response(
                200,
                json={"items": [
                    {"ticker": "AAPL", "added_at": "2026-04-16T09:00:00+09:00"},
                    {"ticker": "TSLA", "added_at": "2026-04-17T10:00:00+09:00"},
                ]},
            )
        )
        c = ApiClient(base_url="http://test", api_key="k")
        items = await c.get_watchlist(42)
    assert len(items) == 2
    assert items[0]["ticker"] == "AAPL"


@pytest.mark.asyncio
async def test_add_watchlist_success_204():
    import respx
    from httpx import Response
    from sajucandle.api_client import ApiClient

    with respx.mock(base_url="http://test") as mock:
        mock.post("/v1/users/42/watchlist").mock(return_value=Response(204))
        c = ApiClient(base_url="http://test", api_key="k")
        await c.add_watchlist(42, "AAPL")   # returns None


@pytest.mark.asyncio
async def test_add_watchlist_conflict_409_full():
    import respx
    from httpx import Response
    from sajucandle.api_client import ApiClient, ApiError

    with respx.mock(base_url="http://test") as mock:
        mock.post("/v1/users/42/watchlist").mock(
            return_value=Response(409, json={"detail": "watchlist full (max 5)"})
        )
        c = ApiClient(base_url="http://test", api_key="k")
        with pytest.raises(ApiError) as exc:
            await c.add_watchlist(42, "AAPL")
    assert exc.value.status == 409
    assert "full" in exc.value.detail


@pytest.mark.asyncio
async def test_add_watchlist_conflict_409_already():
    import respx
    from httpx import Response
    from sajucandle.api_client import ApiClient, ApiError

    with respx.mock(base_url="http://test") as mock:
        mock.post("/v1/users/42/watchlist").mock(
            return_value=Response(409, json={"detail": "already in watchlist"})
        )
        c = ApiClient(base_url="http://test", api_key="k")
        with pytest.raises(ApiError) as exc:
            await c.add_watchlist(42, "AAPL")
    assert exc.value.status == 409
    assert "already" in exc.value.detail


@pytest.mark.asyncio
async def test_add_watchlist_unsupported_400():
    import respx
    from httpx import Response
    from sajucandle.api_client import ApiClient, ApiError

    with respx.mock(base_url="http://test") as mock:
        mock.post("/v1/users/42/watchlist").mock(
            return_value=Response(400, json={"detail": "unsupported ticker: AMZN"})
        )
        c = ApiClient(base_url="http://test", api_key="k")
        with pytest.raises(ApiError) as exc:
            await c.add_watchlist(42, "AMZN")
    assert exc.value.status == 400


@pytest.mark.asyncio
async def test_remove_watchlist_success_204():
    import respx
    from httpx import Response
    from sajucandle.api_client import ApiClient

    with respx.mock(base_url="http://test") as mock:
        mock.delete("/v1/users/42/watchlist/AAPL").mock(return_value=Response(204))
        c = ApiClient(base_url="http://test", api_key="k")
        await c.remove_watchlist(42, "AAPL")


@pytest.mark.asyncio
async def test_remove_watchlist_not_found_404():
    import respx
    from httpx import Response
    from sajucandle.api_client import ApiClient, NotFoundError

    with respx.mock(base_url="http://test") as mock:
        mock.delete("/v1/users/42/watchlist/AAPL").mock(
            return_value=Response(404, json={"detail": "not in watchlist"})
        )
        c = ApiClient(base_url="http://test", api_key="k")
        with pytest.raises(NotFoundError):
            await c.remove_watchlist(42, "AAPL")


@pytest.mark.asyncio
async def test_get_admin_watchlist_symbols_returns_list():
    import respx
    from httpx import Response
    from sajucandle.api_client import ApiClient

    with respx.mock(base_url="http://test") as mock:
        mock.get("/v1/admin/watchlist-symbols").mock(
            return_value=Response(200, json={"symbols": ["AAPL", "TSLA"]})
        )
        c = ApiClient(base_url="http://test", api_key="k")
        syms = await c.get_admin_watchlist_symbols()
    assert syms == ["AAPL", "TSLA"]
```

- [ ] **Step 2: Run — fail**

```
pytest tests/test_api_client.py -v -k "watchlist"
```

Expected: `AttributeError: 'ApiClient' object has no attribute 'get_watchlist'`.

- [ ] **Step 3: Implement in api_client.py**

`src/sajucandle/api_client.py` 내 `ApiClient` 클래스 **마지막**(기존 `get_supported_symbols` 메서드 다음)에 추가:

```python
    async def get_watchlist(self, chat_id: int) -> list[dict]:
        """GET /v1/users/{chat_id}/watchlist. [{ticker, added_at}, ...]"""
        async with self._client() as c:
            r = await c.get(f"/v1/users/{chat_id}/watchlist")
        await self._raise_for_status(r)
        return list(r.json().get("items", []))

    async def add_watchlist(self, chat_id: int, ticker: str) -> None:
        """POST /v1/users/{chat_id}/watchlist body={ticker}. 204 or raise ApiError."""
        async with self._client() as c:
            r = await c.post(
                f"/v1/users/{chat_id}/watchlist",
                json={"ticker": ticker},
            )
        await self._raise_for_status(r)

    async def remove_watchlist(self, chat_id: int, ticker: str) -> None:
        """DELETE /v1/users/{chat_id}/watchlist/{ticker}. 204 or raise ApiError."""
        async with self._client() as c:
            r = await c.delete(f"/v1/users/{chat_id}/watchlist/{ticker}")
        await self._raise_for_status(r)

    async def get_admin_watchlist_symbols(self) -> list[str]:
        """GET /v1/admin/watchlist-symbols. 반환: ['AAPL', 'TSLA', ...]"""
        async with self._client() as c:
            r = await c.get("/v1/admin/watchlist-symbols")
        await self._raise_for_status(r)
        return list(r.json().get("symbols", []))
```

- [ ] **Step 4: Run tests — PASS**

```
pytest tests/test_api_client.py -v
```

Expected: 기존 + 신규 8개 전량 통과.

- [ ] **Step 5: Full regression**

```
pytest -q
```

- [ ] **Step 6: Commit**

```
git add src/sajucandle/api_client.py tests/test_api_client.py
git commit -m "feat(api_client): add watchlist methods (get/add/remove/admin symbols)"
```

---

## Task 5: handlers.py — /watch, /unwatch, /watchlist, /help (TDD)

**Files:**
- Modify: `src/sajucandle/handlers.py`
- Modify: `tests/test_handlers.py`

가장 큰 태스크 — 3개 명령 + /help 업데이트 + 다양한 에러 분기.

- [ ] **Step 1: Write failing tests**

`tests/test_handlers.py` 맨 아래에 추가:

```python
# ─────────────────────────────────────────────
# Week 7: /watch /unwatch /watchlist
# ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_watch_success(monkeypatch):
    from sajucandle import handlers
    from unittest.mock import AsyncMock, MagicMock

    captured = {}
    async def fake_add(chat_id, ticker):
        captured["ticker"] = ticker

    monkeypatch.setattr(
        handlers, "_api_client",
        MagicMock(
            add_watchlist=fake_add,
            get_watchlist=AsyncMock(return_value=[{"ticker": "AAPL"}]),
        ),
    )
    context = MagicMock(args=["AAPL"])
    update = _make_update(text="/watch AAPL", chat_id=42)
    update.message.reply_text = AsyncMock()

    await handlers.watch_command(update, context)
    assert captured["ticker"] == "AAPL"
    sent = update.message.reply_text.call_args[0][0]
    assert "AAPL" in sent
    assert "추가" in sent
    assert "/5" in sent


@pytest.mark.asyncio
async def test_watch_normalizes_lowercase_and_dollar(monkeypatch):
    from sajucandle import handlers
    from unittest.mock import AsyncMock, MagicMock

    captured = {}
    async def fake_add(chat_id, ticker):
        captured["ticker"] = ticker

    monkeypatch.setattr(
        handlers, "_api_client",
        MagicMock(
            add_watchlist=fake_add,
            get_watchlist=AsyncMock(return_value=[]),
        ),
    )
    context = MagicMock(args=["$aapl"])
    update = _make_update(text="/watch $aapl", chat_id=42)
    update.message.reply_text = AsyncMock()

    await handlers.watch_command(update, context)
    assert captured["ticker"] == "AAPL"


@pytest.mark.asyncio
async def test_watch_no_args_shows_usage(monkeypatch):
    from sajucandle import handlers
    from unittest.mock import AsyncMock, MagicMock

    monkeypatch.setattr(handlers, "_api_client", MagicMock())
    context = MagicMock(args=[])
    update = _make_update(text="/watch", chat_id=42)
    update.message.reply_text = AsyncMock()

    await handlers.watch_command(update, context)
    sent = update.message.reply_text.call_args[0][0]
    assert "사용법" in sent


@pytest.mark.asyncio
async def test_watch_full_409(monkeypatch):
    from sajucandle import handlers
    from sajucandle.api_client import ApiError
    from unittest.mock import AsyncMock, MagicMock

    async def fake_add(chat_id, ticker):
        raise ApiError(409, "watchlist full (max 5)")

    monkeypatch.setattr(
        handlers, "_api_client",
        MagicMock(add_watchlist=fake_add),
    )
    context = MagicMock(args=["AAPL"])
    update = _make_update(text="/watch AAPL", chat_id=42)
    update.message.reply_text = AsyncMock()

    await handlers.watch_command(update, context)
    sent = update.message.reply_text.call_args[0][0]
    assert "최대 5개" in sent


@pytest.mark.asyncio
async def test_watch_already_409(monkeypatch):
    from sajucandle import handlers
    from sajucandle.api_client import ApiError
    from unittest.mock import AsyncMock, MagicMock

    async def fake_add(chat_id, ticker):
        raise ApiError(409, "already in watchlist")

    monkeypatch.setattr(
        handlers, "_api_client",
        MagicMock(add_watchlist=fake_add),
    )
    context = MagicMock(args=["AAPL"])
    update = _make_update(text="/watch AAPL", chat_id=42)
    update.message.reply_text = AsyncMock()

    await handlers.watch_command(update, context)
    sent = update.message.reply_text.call_args[0][0]
    assert "이미" in sent


@pytest.mark.asyncio
async def test_watch_unsupported_400(monkeypatch):
    from sajucandle import handlers
    from sajucandle.api_client import ApiError
    from unittest.mock import AsyncMock, MagicMock

    async def fake_add(chat_id, ticker):
        raise ApiError(400, "unsupported ticker: AMZN")

    monkeypatch.setattr(
        handlers, "_api_client",
        MagicMock(add_watchlist=fake_add),
    )
    context = MagicMock(args=["AMZN"])
    update = _make_update(text="/watch AMZN", chat_id=42)
    update.message.reply_text = AsyncMock()

    await handlers.watch_command(update, context)
    sent = update.message.reply_text.call_args[0][0]
    assert "지원하지 않" in sent
    assert "/signal list" in sent


@pytest.mark.asyncio
async def test_watch_user_not_registered_404(monkeypatch):
    from sajucandle import handlers
    from sajucandle.api_client import NotFoundError
    from unittest.mock import AsyncMock, MagicMock

    async def fake_add(chat_id, ticker):
        raise NotFoundError(404, "user not found")

    monkeypatch.setattr(
        handlers, "_api_client",
        MagicMock(add_watchlist=fake_add),
    )
    context = MagicMock(args=["AAPL"])
    update = _make_update(text="/watch AAPL", chat_id=42)
    update.message.reply_text = AsyncMock()

    await handlers.watch_command(update, context)
    sent = update.message.reply_text.call_args[0][0]
    assert "생년월일" in sent


@pytest.mark.asyncio
async def test_unwatch_success(monkeypatch):
    from sajucandle import handlers
    from unittest.mock import AsyncMock, MagicMock

    captured = {}
    async def fake_remove(chat_id, ticker):
        captured["ticker"] = ticker

    monkeypatch.setattr(
        handlers, "_api_client",
        MagicMock(remove_watchlist=fake_remove),
    )
    context = MagicMock(args=["AAPL"])
    update = _make_update(text="/unwatch AAPL", chat_id=42)
    update.message.reply_text = AsyncMock()

    await handlers.unwatch_command(update, context)
    assert captured["ticker"] == "AAPL"
    sent = update.message.reply_text.call_args[0][0]
    assert "🗑️" in sent or "제거" in sent


@pytest.mark.asyncio
async def test_unwatch_missing_404(monkeypatch):
    from sajucandle import handlers
    from sajucandle.api_client import NotFoundError
    from unittest.mock import AsyncMock, MagicMock

    async def fake_remove(chat_id, ticker):
        raise NotFoundError(404, "not in watchlist")

    monkeypatch.setattr(
        handlers, "_api_client",
        MagicMock(remove_watchlist=fake_remove),
    )
    context = MagicMock(args=["AAPL"])
    update = _make_update(text="/unwatch AAPL", chat_id=42)
    update.message.reply_text = AsyncMock()

    await handlers.unwatch_command(update, context)
    sent = update.message.reply_text.call_args[0][0]
    assert "없습니다" in sent or "없" in sent


@pytest.mark.asyncio
async def test_unwatch_no_args_shows_usage(monkeypatch):
    from sajucandle import handlers
    from unittest.mock import AsyncMock, MagicMock

    monkeypatch.setattr(handlers, "_api_client", MagicMock())
    context = MagicMock(args=[])
    update = _make_update(text="/unwatch", chat_id=42)
    update.message.reply_text = AsyncMock()

    await handlers.unwatch_command(update, context)
    sent = update.message.reply_text.call_args[0][0]
    assert "사용법" in sent


@pytest.mark.asyncio
async def test_watchlist_empty(monkeypatch):
    from sajucandle import handlers
    from unittest.mock import AsyncMock, MagicMock

    async def fake_list(chat_id):
        return []

    monkeypatch.setattr(
        handlers, "_api_client",
        MagicMock(get_watchlist=fake_list),
    )
    context = MagicMock(args=[])
    update = _make_update(text="/watchlist", chat_id=42)
    update.message.reply_text = AsyncMock()

    await handlers.watchlist_command(update, context)
    sent = update.message.reply_text.call_args[0][0]
    assert "비어있" in sent
    assert "/watch" in sent


@pytest.mark.asyncio
async def test_watchlist_renders_items(monkeypatch):
    from sajucandle import handlers
    from unittest.mock import AsyncMock, MagicMock

    async def fake_list(chat_id):
        return [
            {"ticker": "BTCUSDT", "added_at": "2026-04-15T09:00:00+09:00"},
            {"ticker": "AAPL", "added_at": "2026-04-16T10:00:00+09:00"},
            {"ticker": "TSLA", "added_at": "2026-04-17T11:00:00+09:00"},
        ]

    monkeypatch.setattr(
        handlers, "_api_client",
        MagicMock(get_watchlist=fake_list),
    )
    context = MagicMock(args=[])
    update = _make_update(text="/watchlist", chat_id=42)
    update.message.reply_text = AsyncMock()

    await handlers.watchlist_command(update, context)
    sent = update.message.reply_text.call_args[0][0]
    assert "3/5" in sent
    assert "BTCUSDT" in sent
    assert "AAPL" in sent
    assert "TSLA" in sent
    # 이름 매핑
    assert "Bitcoin" in sent or "Apple" in sent


@pytest.mark.asyncio
async def test_help_includes_watch_commands(monkeypatch):
    from sajucandle import handlers
    from unittest.mock import AsyncMock, MagicMock

    context = MagicMock(args=[])
    update = _make_update(text="/help", chat_id=42)
    update.message.reply_text = AsyncMock()

    await handlers.help_command(update, context)
    sent = update.message.reply_text.call_args[0][0]
    assert "/watch" in sent
    assert "/unwatch" in sent
    assert "/watchlist" in sent
```

- [ ] **Step 2: Run — fail**

```
pytest tests/test_handlers.py -v -k "watch or help_includes"
```

Expected: `AttributeError: module 'sajucandle.handlers' has no attribute 'watch_command'` 등.

- [ ] **Step 3: Implement in handlers.py**

`src/sajucandle/handlers.py`에 다음 추가. 기존 `signal_command` 아래, `help_command` 위에 위치:

```python
# ─────────────────────────────────────────────
# Week 7: watchlist commands
# ─────────────────────────────────────────────

_SYMBOL_NAMES = {
    "BTCUSDT": "Bitcoin",
    "AAPL": "Apple",
    "MSFT": "Microsoft",
    "GOOGL": "Alphabet",
    "NVDA": "NVIDIA",
    "TSLA": "Tesla",
}


def _symbol_name(ticker: str) -> str:
    return _SYMBOL_NAMES.get(ticker, ticker)


async def watch_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """`/watch <심볼>` — 관심 종목 추가 (최대 5개)."""
    if update.message is None:
        return
    chat_id = update.effective_chat.id
    args = list(context.args or [])

    if not args:
        await update.message.reply_text(
            "사용법: /watch <심볼>\n예: /watch AAPL"
        )
        return

    ticker = args[0].upper().lstrip("$")

    try:
        await _api_client.add_watchlist(chat_id, ticker)
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
        detail = (e.detail or "").lower()
        if e.status == 409 and "full" in detail:
            await update.message.reply_text(
                "관심 종목은 최대 5개입니다.\n"
                "/watchlist 에서 제거 후 다시 시도."
            )
        elif e.status == 409 and "already" in detail:
            await update.message.reply_text(f"이미 관심 종목에 있습니다: {ticker}")
        elif e.status == 400 and "unsupported" in detail:
            await update.message.reply_text(
                f"지원하지 않는 심볼: {ticker}\n"
                f"/signal list 로 확인."
            )
        else:
            logger.warning(
                "watch api error chat_id=%s status=%s", chat_id, e.status
            )
            await update.message.reply_text(f"서버 오류 ({e.status}).")
        return
    except Exception:
        logger.exception("watch_command unexpected error chat_id=%s", chat_id)
        await update.message.reply_text("예기치 못한 오류가 발생했습니다.")
        return

    # 성공 시 현재 개수 조회해서 표시
    try:
        items = await _api_client.get_watchlist(chat_id)
        count = len(items)
    except Exception:
        count = "?"

    await update.message.reply_text(
        f"✅ {ticker} ({_symbol_name(ticker)}) 관심 종목 추가 완료.\n"
        f"현재 {count}/5개. /watchlist 로 전체 확인."
    )


async def unwatch_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """`/unwatch <심볼>` — 관심 종목 제거."""
    if update.message is None:
        return
    chat_id = update.effective_chat.id
    args = list(context.args or [])

    if not args:
        await update.message.reply_text("사용법: /unwatch <심볼>")
        return

    ticker = args[0].upper().lstrip("$")

    try:
        await _api_client.remove_watchlist(chat_id, ticker)
    except NotFoundError:
        await update.message.reply_text(f"관심 종목에 없습니다: {ticker}")
        return
    except httpx.TimeoutException:
        await update.message.reply_text("서버 응답이 느립니다. 잠시 후 다시.")
        return
    except httpx.TransportError:
        await update.message.reply_text("서버에 연결할 수 없습니다.")
        return
    except ApiError as e:
        logger.warning(
            "unwatch api error chat_id=%s status=%s", chat_id, e.status
        )
        await update.message.reply_text(f"서버 오류 ({e.status}).")
        return
    except Exception:
        logger.exception("unwatch_command unexpected error chat_id=%s", chat_id)
        await update.message.reply_text("예기치 못한 오류가 발생했습니다.")
        return

    await update.message.reply_text(f"🗑️ {ticker} 관심 종목에서 제거했습니다.")


async def watchlist_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """`/watchlist` — 본인 관심 종목 목록."""
    if update.message is None:
        return
    chat_id = update.effective_chat.id

    try:
        items = await _api_client.get_watchlist(chat_id)
    except httpx.TimeoutException:
        await update.message.reply_text("서버 응답이 느립니다. 잠시 후 다시.")
        return
    except httpx.TransportError:
        await update.message.reply_text("서버에 연결할 수 없습니다.")
        return
    except ApiError as e:
        logger.warning(
            "watchlist api error chat_id=%s status=%s", chat_id, e.status
        )
        await update.message.reply_text(f"서버 오류 ({e.status}).")
        return

    if not items:
        await update.message.reply_text(
            "관심 종목이 비어있습니다.\n"
            "/watch AAPL 로 추가하세요.\n"
            "/signal list 로 지원 심볼 확인."
        )
        return

    lines = [f"📊 관심 종목 ({len(items)}/5)", "─────────────"]
    for i, it in enumerate(items, start=1):
        ticker = it["ticker"]
        added = it.get("added_at", "")[:10]   # "2026-04-15" 부분만
        lines.append(f"{i}. {ticker} — {_symbol_name(ticker)} ({added} 추가)")
    lines.append("")
    lines.append("/unwatch <심볼> 로 제거")
    lines.append("매일 07:00 자동 시그널 발송됩니다.")

    await update.message.reply_text("\n".join(lines))
```

**(b) `help_command` reply_text 문구 교체:**

```python
    await update.message.reply_text(
        "SajuCandle 봇 사용법\n"
        "─────────────\n"
        "/start YYYY-MM-DD HH:MM — 생년월일시 등록\n"
        "/score [swing|scalp|long] — 오늘 사주 점수\n"
        "/signal [심볼] — 사주+차트 결합 신호\n"
        "  · 지원: BTCUSDT, AAPL, MSFT, GOOGL, NVDA, TSLA\n"
        "  · /signal list — 전체 목록\n"
        "/watch <심볼> — 관심 종목 추가 (최대 5개)\n"
        "/unwatch <심볼> — 관심 종목 제거\n"
        "/watchlist — 내 관심 종목 + 매일 07:00 자동 시그널\n"
        "/me — 등록된 정보 확인\n"
        "/forget — 내 정보 삭제\n"
        "/help — 이 도움말\n"
        "\n※ 엔터테인먼트 목적. 투자 추천 아님."
    )
```

- [ ] **Step 4: Register commands in bot.py**

`src/sajucandle/bot.py` 에서 기존 `CommandHandler` 등록 부분을 찾아 3개 추가:

```python
# 기존 등록 근처에 추가
application.add_handler(CommandHandler("watch", handlers.watch_command))
application.add_handler(CommandHandler("unwatch", handlers.unwatch_command))
application.add_handler(CommandHandler("watchlist", handlers.watchlist_command))
```

bot.py 파일이 있는지 먼저 확인하고 정확한 등록 위치를 찾는다. 보통 `add_handler(CommandHandler("help", handlers.help_command))` 다음 줄.

- [ ] **Step 5: Run tests — PASS**

```
pytest tests/test_handlers.py -v
```

Expected: 기존 + 신규 13개 전량 통과.

- [ ] **Step 6: Full regression**

```
pytest -q
```

- [ ] **Step 7: Commit**

```
git add src/sajucandle/handlers.py src/sajucandle/bot.py tests/test_handlers.py
git commit -m "feat(bot): add /watch /unwatch /watchlist commands"
```

---

## Task 6: broadcast.py — BroadcastSummary 확장 + format_watchlist_summary (TDD, 순수 함수)

**Files:**
- Modify: `src/sajucandle/broadcast.py`
- Modify: `tests/test_broadcast.py`

순수 함수 먼저 구현. Phase 1/3 통합은 Task 7/8.

- [ ] **Step 1: Write failing tests for BroadcastSummary extension**

`tests/test_broadcast.py` 맨 아래에 추가:

```python
# ─────────────────────────────────────────────
# Week 7: BroadcastSummary 확장 + format_watchlist_summary
# ─────────────────────────────────────────────


def test_broadcast_summary_has_watchlist_fields():
    from sajucandle.broadcast import BroadcastSummary
    s = BroadcastSummary()
    assert s.watchlist_sent == 0
    assert s.watchlist_skipped_empty == 0
    assert s.watchlist_failed == 0
    assert s.precompute_ok == 0
    assert s.precompute_failed == 0


def test_format_watchlist_summary_renders_open_stock():
    from datetime import date
    from sajucandle.broadcast import format_watchlist_summary

    signals = [{
        "ticker": "AAPL",
        "price": {"current": 184.12, "change_pct_24h": 1.23},
        "composite_score": 66,
        "signal_grade": "진입",
        "market_status": {"is_open": True, "category": "us_stock",
                           "last_session_date": "2026-04-16"},
    }]
    card = format_watchlist_summary(signals, date(2026, 4, 17))
    assert "2026-04-17" in card
    assert "관심 종목" in card
    assert "AAPL" in card
    assert "66" in card
    assert "진입" in card
    assert "184.12" in card
    assert "+1.23" in card
    # 장 중이라 휴장 아이콘 없음
    assert "🕐" not in card
    assert "엔터테인먼트" in card   # disclaimer


def test_format_watchlist_summary_closed_stock_shows_clock():
    from datetime import date
    from sajucandle.broadcast import format_watchlist_summary

    signals = [{
        "ticker": "TSLA",
        "price": {"current": 215.00, "change_pct_24h": -2.3},
        "composite_score": 45,
        "signal_grade": "관망",
        "market_status": {"is_open": False, "category": "us_stock",
                           "last_session_date": "2026-04-16"},
    }]
    card = format_watchlist_summary(signals, date(2026, 4, 17))
    assert "🕐" in card


def test_format_watchlist_summary_btc_no_clock():
    """crypto는 24/7이라 휴장 아이콘 없음."""
    from datetime import date
    from sajucandle.broadcast import format_watchlist_summary

    signals = [{
        "ticker": "BTCUSDT",
        "price": {"current": 72120.0, "change_pct_24h": 1.5},
        "composite_score": 72,
        "signal_grade": "진입",
        "market_status": {"is_open": True, "category": "crypto",
                           "last_session_date": "2026-04-17"},
    }]
    card = format_watchlist_summary(signals, date(2026, 4, 17))
    assert "🕐" not in card
    # BTCUSDT는 [BTC]로 축약
    assert "[BTC]" in card or "BTCUSDT" not in card.split("\n")[2]


def test_format_watchlist_summary_failed_signal():
    """시그널 실패한 심볼은 '데이터 불가'."""
    from datetime import date
    from sajucandle.broadcast import format_watchlist_summary

    signals = [{
        "ticker": "XYZ",
        "error": "데이터 불가",
    }]
    card = format_watchlist_summary(signals, date(2026, 4, 17))
    assert "XYZ" in card
    assert "데이터 불가" in card


def test_format_watchlist_summary_empty_returns_none():
    from datetime import date
    from sajucandle.broadcast import format_watchlist_summary
    assert format_watchlist_summary([], date(2026, 4, 17)) is None


def test_format_watchlist_summary_multiple_mixed():
    from datetime import date
    from sajucandle.broadcast import format_watchlist_summary

    signals = [
        {"ticker": "BTCUSDT",
         "price": {"current": 72000.0, "change_pct_24h": 1.5},
         "composite_score": 72, "signal_grade": "진입",
         "market_status": {"is_open": True, "category": "crypto",
                            "last_session_date": "2026-04-17"}},
        {"ticker": "AAPL",
         "price": {"current": 184.12, "change_pct_24h": 1.2},
         "composite_score": 65, "signal_grade": "진입",
         "market_status": {"is_open": False, "category": "us_stock",
                            "last_session_date": "2026-04-16"}},
        {"ticker": "TSLA", "error": "데이터 불가"},
    ]
    card = format_watchlist_summary(signals, date(2026, 4, 17))
    for t in ["BTC", "AAPL", "TSLA"]:
        assert t in card
    assert card.count("\n") >= 4   # 헤더 + 구분 + 3종목 + disclaimer
```

- [ ] **Step 2: Run — fail**

```
pytest tests/test_broadcast.py -v -k "watchlist or summary_has_watchlist or format_watchlist"
```

Expected: `ImportError: cannot import name 'format_watchlist_summary'` 또는 AttributeError.

- [ ] **Step 3: Extend BroadcastSummary and add format_watchlist_summary**

`src/sajucandle/broadcast.py`를 먼저 읽고 기존 구조 파악. `BroadcastSummary` dataclass에 필드 추가 + 새 함수 추가:

```python
@dataclass
class BroadcastSummary:
    sent: int = 0
    failed: int = 0
    blocked: int = 0
    not_found: int = 0
    bad_request: int = 0
    # Week 7
    watchlist_sent: int = 0
    watchlist_skipped_empty: int = 0
    watchlist_failed: int = 0
    precompute_ok: int = 0
    precompute_failed: int = 0

    def total(self) -> int:
        return (self.sent + self.failed + self.blocked
                + self.not_found + self.bad_request)
```

format_watchlist_summary 함수 추가 (기존 format_morning_card 근처):

```python
_WEEKDAY_KO = ["월", "화", "수", "목", "금", "토", "일"]


def _short_ticker(ticker: str) -> str:
    """BTCUSDT → BTC 축약. 그 외는 원본 유지."""
    if ticker.endswith("USDT"):
        return ticker[:-4]
    return ticker


def format_watchlist_summary(signals: list[dict], target_date) -> Optional[str]:
    """watchlist 요약 카드.

    signals 원소:
      - 정상: {"ticker", "price":{"current","change_pct_24h"},
               "composite_score", "signal_grade",
               "market_status":{"is_open","category","last_session_date"}}
      - 실패: {"ticker", "error": str}

    빈 리스트면 None 반환 (호출자가 전송 skip).
    """
    if not signals:
        return None
    weekday = _WEEKDAY_KO[target_date.weekday()]
    lines = [f"📊 {target_date.isoformat()} ({weekday}) 관심 종목", "─────────────"]
    for s in signals:
        if "error" in s:
            lines.append(f"[{_short_ticker(s['ticker'])}]  {s['error']}")
            continue
        t = _short_ticker(s["ticker"])
        score = s.get("composite_score", 0)
        grade = s.get("signal_grade", "")
        price = s.get("price", {})
        cur = price.get("current", 0.0)
        pct = price.get("change_pct_24h", 0.0)
        sign = "+" if pct >= 0 else ""
        status = s.get("market_status") or {}
        clock = ""
        if status.get("category") == "us_stock" and not status.get("is_open"):
            clock = "  🕐"
        lines.append(
            f"[{t:<5}] {score:>3} {grade}  ${cur:,.2f}  ({sign}{pct:.2f}%){clock}"
        )
    lines.append("")
    lines.append("상세: /signal <심볼>")
    lines.append("※ 엔터테인먼트 목적. 투자 추천 아님.")
    return "\n".join(lines)
```

`Optional` 임포트가 이미 있는지 확인.

- [ ] **Step 4: Run tests — PASS**

```
pytest tests/test_broadcast.py -v -k "watchlist or summary_has_watchlist or format_watchlist"
```

Expected: 7개 신규 전부 통과.

- [ ] **Step 5: Full regression**

```
pytest -q
```

Expected: 기존 테스트 전량 통과 (BroadcastSummary 필드 추가는 default값 0이라 비파괴적).

- [ ] **Step 6: Commit**

```
git add src/sajucandle/broadcast.py tests/test_broadcast.py
git commit -m "feat(broadcast): BroadcastSummary watchlist fields + format_watchlist_summary"
```

---

## Task 7: broadcast.py — Phase 1 Precompute 통합 (TDD)

**Files:**
- Modify: `src/sajucandle/broadcast.py`
- Modify: `tests/test_broadcast.py`

`run_broadcast` 함수 시작 시점에 Phase 1(캐시 워밍)을 추가. 실패해도 Phase 2 진행.

- [ ] **Step 1: Write failing tests**

`tests/test_broadcast.py` 맨 아래에 추가:

```python
# ─────────────────────────────────────────────
# Week 7: Phase 1 Precompute
# ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_precompute_warms_cache_for_all_symbols(monkeypatch):
    """run_broadcast 시작 시 admin chat으로 watchlist union 심볼 선조회."""
    from unittest.mock import AsyncMock, MagicMock
    from sajucandle.broadcast import run_broadcast

    api_client = MagicMock()
    api_client.get_admin_users = AsyncMock(return_value=[])   # Phase 2 비움
    api_client.get_admin_watchlist_symbols = AsyncMock(
        return_value=["AAPL", "TSLA"]
    )
    # precompute: admin chat으로 signal 2회
    precompute_calls = []
    async def fake_get_signal(chat_id, ticker=None, date=None):
        precompute_calls.append((chat_id, ticker))
        return {}
    api_client.get_signal = fake_get_signal

    send = AsyncMock()
    summary = await run_broadcast(
        api_client=api_client,
        send_message=send,
        chat_ids=[],
        target_date=date(2026, 4, 17),
        dry_run=True,
        admin_chat_id=7492682272,
    )
    # 2개 심볼 각각 1회 precompute
    assert len(precompute_calls) == 2
    assert all(c[0] == 7492682272 for c in precompute_calls)
    tickers_called = {c[1] for c in precompute_calls}
    assert tickers_called == {"AAPL", "TSLA"}
    assert summary.precompute_ok == 2
    assert summary.precompute_failed == 0


@pytest.mark.asyncio
async def test_precompute_continues_on_partial_failure(monkeypatch):
    """일부 심볼 실패해도 나머지 진행."""
    from unittest.mock import AsyncMock, MagicMock
    from sajucandle.api_client import ApiError
    from sajucandle.broadcast import run_broadcast

    api_client = MagicMock()
    api_client.get_admin_users = AsyncMock(return_value=[])
    api_client.get_admin_watchlist_symbols = AsyncMock(
        return_value=["AAPL", "TSLA"]
    )

    async def fake_get_signal(chat_id, ticker=None, date=None):
        if ticker == "AAPL":
            raise ApiError(502, "chart data unavailable")
        return {}
    api_client.get_signal = fake_get_signal

    send = AsyncMock()
    summary = await run_broadcast(
        api_client=api_client,
        send_message=send,
        chat_ids=[],
        target_date=date(2026, 4, 17),
        dry_run=True,
        admin_chat_id=7492682272,
    )
    assert summary.precompute_ok == 1
    assert summary.precompute_failed == 1


@pytest.mark.asyncio
async def test_precompute_skipped_when_admin_chat_id_none():
    """admin_chat_id=None이면 Phase 1 skip."""
    from unittest.mock import AsyncMock, MagicMock
    from sajucandle.broadcast import run_broadcast

    api_client = MagicMock()
    api_client.get_admin_users = AsyncMock(return_value=[])
    api_client.get_admin_watchlist_symbols = AsyncMock(return_value=["AAPL"])
    api_client.get_signal = AsyncMock()

    send = AsyncMock()
    summary = await run_broadcast(
        api_client=api_client,
        send_message=send,
        chat_ids=[],
        target_date=date(2026, 4, 17),
        dry_run=True,
        admin_chat_id=None,
    )
    # get_admin_watchlist_symbols도 호출되지 않아야 함
    api_client.get_admin_watchlist_symbols.assert_not_called()
    api_client.get_signal.assert_not_called()
    assert summary.precompute_ok == 0
    assert summary.precompute_failed == 0


@pytest.mark.asyncio
async def test_precompute_failure_does_not_abort_phase2(monkeypatch):
    """Phase 1 완전 실패해도 Phase 2(사주 카드)는 진행."""
    from unittest.mock import AsyncMock, MagicMock
    from sajucandle.api_client import ApiError
    from sajucandle.broadcast import run_broadcast

    api_client = MagicMock()
    api_client.get_admin_users = AsyncMock(return_value=[])
    # watchlist 심볼 조회 자체가 실패
    api_client.get_admin_watchlist_symbols = AsyncMock(
        side_effect=ApiError(500, "db down")
    )
    # Phase 2용 score 호출
    api_client.get_score = AsyncMock(return_value=_sample_score_payload())

    send = AsyncMock()
    # chat_ids=[99] → Phase 2에서 1명 발송
    summary = await run_broadcast(
        api_client=api_client,
        send_message=send,
        chat_ids=[99],
        target_date=date(2026, 4, 17),
        dry_run=True,
        admin_chat_id=7492682272,
    )
    # Phase 1 fail: 심볼 리스트 자체를 못 받음. 카운트 0.
    assert summary.precompute_ok == 0
    # Phase 2는 정상 실행됐는지 → sent/dry-run 카운트 확인 (기존 dry-run 포맷)
    # 기존 run_broadcast가 dry-run에서 sent을 카운트하는지 여부에 따라 검증
    # 최소한 get_score는 호출됐어야 함
    api_client.get_score.assert_called_once_with(99, date="2026-04-17")
```

**단, `_sample_score_payload`가 기존 test_broadcast.py에 헬퍼로 있어야 함. 없으면 간단한 dict 직접 작성.** 기존 테스트 파일 상단에서 이런 헬퍼를 찾아 재사용.

- [ ] **Step 2: Run — fail**

```
pytest tests/test_broadcast.py -v -k "precompute"
```

Expected: `TypeError: run_broadcast() got an unexpected keyword argument 'admin_chat_id'` 등.

- [ ] **Step 3: Implement Phase 1 in run_broadcast**

`src/sajucandle/broadcast.py`의 `run_broadcast` 함수 시그니처 변경 + 시작부에 Phase 1 추가:

기존 시그니처에 `admin_chat_id: Optional[int] = None` 추가:

```python
async def run_broadcast(
    api_client,
    send_message,
    chat_ids: list[int],
    target_date,
    *,
    dry_run: bool = False,
    forbidden_exc=None,
    bad_request_exc=None,
    send_delay: float = 0.05,
    admin_chat_id: Optional[int] = None,   # Week 7: Phase 1 precompute용
) -> BroadcastSummary:
    summary = BroadcastSummary()

    # ─── Phase 1: Precompute (watchlist 심볼 캐시 워밍) ───
    if admin_chat_id is not None:
        try:
            symbols = await api_client.get_admin_watchlist_symbols()
        except Exception as e:
            logger.warning("broadcast precompute symbol list failed: %s", e)
            symbols = []
        for ticker in symbols:
            try:
                await api_client.get_signal(
                    admin_chat_id,
                    ticker=ticker,
                    date=target_date.isoformat(),
                )
                summary.precompute_ok += 1
            except Exception as e:
                logger.warning(
                    "broadcast precompute failed ticker=%s: %s", ticker, e
                )
                summary.precompute_failed += 1

    # ─── Phase 2: 기존 사주 카드 로직 (Week 5 그대로) ───
    # ... 기존 코드 유지 ...
```

**중요:** 기존 `run_broadcast` 내부의 사주 카드 발송 루프 (Week 5)는 **수정하지 말 것**. Phase 1 블록만 함수 시작부에 삽입.

- [ ] **Step 4: Run tests — PASS**

```
pytest tests/test_broadcast.py -v -k "precompute"
```

Expected: 4개 통과.

- [ ] **Step 5: Full regression**

```
pytest -q
```

Expected: 기존 broadcast 테스트 전량 통과 (admin_chat_id는 optional, 기본 None → Phase 1 skip이라 회귀 0).

- [ ] **Step 6: Commit**

```
git add src/sajucandle/broadcast.py tests/test_broadcast.py
git commit -m "feat(broadcast): Phase 1 precompute warms watchlist signal cache"
```

---

## Task 8: broadcast.py — Phase 3 Watchlist 요약 + --skip-watchlist + SAJUCANDLE_ADMIN_CHAT_ID

**Files:**
- Modify: `src/sajucandle/broadcast.py`
- Modify: `tests/test_broadcast.py`

Phase 2 이후에 사용자별 watchlist 요약 발송 + CLI 플래그 + env 통합.

- [ ] **Step 1: Write failing tests**

`tests/test_broadcast.py` 맨 아래에 추가:

```python
# ─────────────────────────────────────────────
# Week 7: Phase 3 Watchlist 요약
# ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_watchlist_summary_sent_for_user_with_items():
    """watchlist 있는 사용자에게 2번째 메시지로 요약 발송."""
    from unittest.mock import AsyncMock, MagicMock
    from sajucandle.broadcast import run_broadcast

    api_client = MagicMock()
    api_client.get_admin_users = AsyncMock(return_value=[99])
    api_client.get_admin_watchlist_symbols = AsyncMock(return_value=[])
    api_client.get_score = AsyncMock(return_value=_sample_score_payload())

    async def fake_get_watchlist(chat_id):
        return [
            {"ticker": "AAPL", "added_at": "2026-04-16T09:00:00+09:00"},
        ]
    api_client.get_watchlist = fake_get_watchlist

    async def fake_get_signal(chat_id, ticker=None, date=None):
        return {
            "ticker": ticker,
            "price": {"current": 184.12, "change_pct_24h": 1.2},
            "composite_score": 65, "signal_grade": "진입",
            "market_status": {"is_open": True, "category": "us_stock",
                               "last_session_date": "2026-04-16"},
        }
    api_client.get_signal = fake_get_signal

    sent_messages = []
    async def send(chat_id, text):
        sent_messages.append((chat_id, text))
    send_mock = send

    summary = await run_broadcast(
        api_client=api_client,
        send_message=send_mock,
        chat_ids=[99],
        target_date=date(2026, 4, 17),
        dry_run=False,
        admin_chat_id=None,
        skip_watchlist=False,
    )
    # 1통 사주 + 1통 watchlist = 2통
    assert len(sent_messages) == 2
    # 두 번째가 watchlist 요약
    assert "관심 종목" in sent_messages[1][1]
    assert "AAPL" in sent_messages[1][1]
    assert summary.watchlist_sent == 1
    assert summary.watchlist_skipped_empty == 0


@pytest.mark.asyncio
async def test_watchlist_skipped_for_empty_user():
    """watchlist 비어있는 사용자는 1통(사주)만 발송."""
    from unittest.mock import AsyncMock, MagicMock
    from sajucandle.broadcast import run_broadcast

    api_client = MagicMock()
    api_client.get_admin_users = AsyncMock(return_value=[99])
    api_client.get_admin_watchlist_symbols = AsyncMock(return_value=[])
    api_client.get_score = AsyncMock(return_value=_sample_score_payload())
    api_client.get_watchlist = AsyncMock(return_value=[])
    api_client.get_signal = AsyncMock()

    sent_messages = []
    async def send(chat_id, text):
        sent_messages.append((chat_id, text))

    summary = await run_broadcast(
        api_client=api_client,
        send_message=send,
        chat_ids=[99],
        target_date=date(2026, 4, 17),
        dry_run=False,
        admin_chat_id=None,
        skip_watchlist=False,
    )
    assert len(sent_messages) == 1
    assert summary.watchlist_skipped_empty == 1
    assert summary.watchlist_sent == 0


@pytest.mark.asyncio
async def test_watchlist_partial_signal_failure_still_sends():
    """일부 심볼 시그널 실패해도 나머지 포함해 요약 발송."""
    from unittest.mock import AsyncMock, MagicMock
    from sajucandle.api_client import ApiError
    from sajucandle.broadcast import run_broadcast

    api_client = MagicMock()
    api_client.get_admin_users = AsyncMock(return_value=[99])
    api_client.get_admin_watchlist_symbols = AsyncMock(return_value=[])
    api_client.get_score = AsyncMock(return_value=_sample_score_payload())
    api_client.get_watchlist = AsyncMock(return_value=[
        {"ticker": "AAPL", "added_at": "2026-04-16"},
        {"ticker": "TSLA", "added_at": "2026-04-17"},
    ])

    async def fake_get_signal(chat_id, ticker=None, date=None):
        if ticker == "TSLA":
            raise ApiError(502, "chart data unavailable")
        return {
            "ticker": ticker,
            "price": {"current": 184.12, "change_pct_24h": 1.2},
            "composite_score": 65, "signal_grade": "진입",
            "market_status": {"is_open": True, "category": "us_stock",
                               "last_session_date": "2026-04-16"},
        }
    api_client.get_signal = fake_get_signal

    sent_messages = []
    async def send(chat_id, text):
        sent_messages.append((chat_id, text))

    summary = await run_broadcast(
        api_client=api_client,
        send_message=send,
        chat_ids=[99],
        target_date=date(2026, 4, 17),
        dry_run=False,
        admin_chat_id=None,
        skip_watchlist=False,
    )
    assert len(sent_messages) == 2
    # 2번째 메시지에 TSLA '데이터 불가' + AAPL 정상
    assert "데이터 불가" in sent_messages[1][1]
    assert "AAPL" in sent_messages[1][1]
    assert "TSLA" in sent_messages[1][1]
    assert summary.watchlist_sent == 1


@pytest.mark.asyncio
async def test_skip_watchlist_flag_disables_phase3():
    """skip_watchlist=True 시 Phase 3 완전 skip."""
    from unittest.mock import AsyncMock, MagicMock
    from sajucandle.broadcast import run_broadcast

    api_client = MagicMock()
    api_client.get_admin_users = AsyncMock(return_value=[99])
    api_client.get_admin_watchlist_symbols = AsyncMock(return_value=[])
    api_client.get_score = AsyncMock(return_value=_sample_score_payload())
    api_client.get_watchlist = AsyncMock()   # 호출되면 안 됨
    api_client.get_signal = AsyncMock()

    sent_messages = []
    async def send(chat_id, text):
        sent_messages.append((chat_id, text))

    summary = await run_broadcast(
        api_client=api_client,
        send_message=send,
        chat_ids=[99],
        target_date=date(2026, 4, 17),
        dry_run=False,
        admin_chat_id=None,
        skip_watchlist=True,
    )
    api_client.get_watchlist.assert_not_called()
    # 1통(사주)만
    assert len(sent_messages) == 1
    assert summary.watchlist_sent == 0
    assert summary.watchlist_skipped_empty == 0


@pytest.mark.asyncio
async def test_watchlist_dry_run_does_not_send():
    """dry_run=True면 Phase 3도 전송 skip (로그만)."""
    from unittest.mock import AsyncMock, MagicMock
    from sajucandle.broadcast import run_broadcast

    api_client = MagicMock()
    api_client.get_admin_users = AsyncMock(return_value=[99])
    api_client.get_admin_watchlist_symbols = AsyncMock(return_value=[])
    api_client.get_score = AsyncMock(return_value=_sample_score_payload())
    api_client.get_watchlist = AsyncMock(return_value=[
        {"ticker": "AAPL", "added_at": "2026-04-16"},
    ])
    api_client.get_signal = AsyncMock(return_value={
        "ticker": "AAPL",
        "price": {"current": 184.12, "change_pct_24h": 1.2},
        "composite_score": 65, "signal_grade": "진입",
        "market_status": {"is_open": True, "category": "us_stock",
                           "last_session_date": "2026-04-16"},
    })

    sent_messages = []
    async def send(chat_id, text):
        sent_messages.append((chat_id, text))

    await run_broadcast(
        api_client=api_client,
        send_message=send,
        chat_ids=[99],
        target_date=date(2026, 4, 17),
        dry_run=True,
        admin_chat_id=None,
        skip_watchlist=False,
    )
    # dry-run이라 아무 전송도 없어야 함
    assert len(sent_messages) == 0


def test_cli_parses_skip_watchlist_flag():
    """argparse --skip-watchlist 플래그 파싱."""
    from sajucandle.broadcast import _parse_args
    args = _parse_args(["--skip-watchlist"])
    assert args.skip_watchlist is True


def test_cli_default_skip_watchlist_false():
    from sajucandle.broadcast import _parse_args
    args = _parse_args([])
    assert args.skip_watchlist is False
```

- [ ] **Step 2: Run — fail**

```
pytest tests/test_broadcast.py -v -k "watchlist or skip_watchlist"
```

Expected: `TypeError: run_broadcast() got an unexpected keyword argument 'skip_watchlist'` 등.

- [ ] **Step 3: Implement Phase 3 in run_broadcast + CLI**

`src/sajucandle/broadcast.py`의 `run_broadcast`에 `skip_watchlist` 파라미터 추가 + Phase 2 루프 다음에 Phase 3 블록 삽입:

```python
async def run_broadcast(
    api_client,
    send_message,
    chat_ids: list[int],
    target_date,
    *,
    dry_run: bool = False,
    forbidden_exc=None,
    bad_request_exc=None,
    send_delay: float = 0.05,
    admin_chat_id: Optional[int] = None,
    skip_watchlist: bool = False,   # Week 7
) -> BroadcastSummary:
    # ... Phase 1 (기존 Task 7) ...
    # ... Phase 2 (기존 사주 카드 루프) ...

    # ─── Phase 3: Watchlist 요약 ───
    if not skip_watchlist:
        for chat_id in chat_ids:
            try:
                items = await api_client.get_watchlist(chat_id)
            except Exception as e:
                logger.warning(
                    "watchlist fetch failed chat_id=%s: %s", chat_id, e
                )
                summary.watchlist_failed += 1
                continue

            if not items:
                summary.watchlist_skipped_empty += 1
                continue

            signals = []
            for it in items:
                ticker = it["ticker"]
                try:
                    sig = await api_client.get_signal(
                        chat_id,
                        ticker=ticker,
                        date=target_date.isoformat(),
                    )
                    signals.append(sig)
                except Exception as e:
                    logger.warning(
                        "watchlist signal failed chat_id=%s ticker=%s: %s",
                        chat_id, ticker, e,
                    )
                    signals.append({"ticker": ticker, "error": "데이터 불가"})

            card = format_watchlist_summary(signals, target_date)
            if card is None:
                continue
            if dry_run:
                logger.info(
                    "[DRY-RUN] watchlist chat_id=%s text=\n%s",
                    chat_id, card,
                )
            else:
                try:
                    await send_message(chat_id, card)
                    summary.watchlist_sent += 1
                    await asyncio.sleep(send_delay)
                except Exception as e:
                    logger.warning(
                        "watchlist send failed chat_id=%s: %s", chat_id, e
                    )
                    summary.watchlist_failed += 1

    # ─── 최종 로그 ───
    logger.info(
        "broadcast done date=%s sent=%s failed=%s blocked=%s not_found=%s "
        "bad_request=%s watchlist_sent=%s watchlist_skipped_empty=%s "
        "watchlist_failed=%s precompute_ok=%s precompute_failed=%s",
        target_date.isoformat(),
        summary.sent, summary.failed, summary.blocked,
        summary.not_found, summary.bad_request,
        summary.watchlist_sent, summary.watchlist_skipped_empty,
        summary.watchlist_failed,
        summary.precompute_ok, summary.precompute_failed,
    )
    return summary
```

**중요:** 기존 최종 로그 줄(`logger.info("broadcast done ...")`)이 있으면 위 버전으로 교체 — 기존 포맷은 그대로 + 새 카운터 6개 추가.

**(b) CLI argparse `_parse_args`에 플래그 추가:**

기존 `_parse_args` 함수 찾아서 argument 추가:

```python
parser.add_argument(
    "--skip-watchlist",
    action="store_true",
    help="Phase 3 watchlist 요약을 발송하지 않음 (Week 5 동작 유지)",
)
```

**(c) CLI `main()` 또는 `__main__` 블록에서 `admin_chat_id` env 읽기 + skip_watchlist 전달:**

```python
admin_chat_id_env = os.environ.get("SAJUCANDLE_ADMIN_CHAT_ID")
admin_chat_id = int(admin_chat_id_env) if admin_chat_id_env else None

summary = await run_broadcast(
    api_client=api_client,
    send_message=send_message,
    chat_ids=chat_ids,
    target_date=target_date,
    dry_run=args.dry_run,
    admin_chat_id=admin_chat_id,
    skip_watchlist=args.skip_watchlist,
)
```

기존 `main()` 구조에 맞춰 정확한 위치 조정.

- [ ] **Step 4: Run tests — PASS**

```
pytest tests/test_broadcast.py -v -k "watchlist or skip_watchlist or precompute"
```

Expected: Week 7 신규 모두 통과.

- [ ] **Step 5: Full regression**

```
pytest -q
```

Expected: 전량 통과 (skip_watchlist 기본값 False지만 chat_ids=[]이거나 get_watchlist mock 없어도 안전한 경로).

**기존 테스트 호환성 체크:** Week 5 테스트가 `run_broadcast(..., admin_chat_id=None, skip_watchlist=False)` 기본값으로 Phase 1 skip + Phase 3은 `get_watchlist`를 호출 시도하게 됨. MagicMock 기본 동작은 AsyncMock이 아닌 MagicMock을 반환하므로 await 실패 가능. 기존 테스트가 이 경로에서 깨지면 해당 테스트에 `skip_watchlist=True`를 추가하거나 MagicMock이 아닌 AsyncMock을 사용하도록 조정.

**구체적 대응:** Week 5 `test_broadcast.py`의 `run_broadcast` 호출 중 watchlist 관련 설정이 없는 것은 **`skip_watchlist=True`를 명시적으로 추가**해서 Week 5 동작을 유지하도록 수정. Week 7 테스트만 `skip_watchlist=False`로 명시. 회귀 0.

- [ ] **Step 6: Commit**

```
git add src/sajucandle/broadcast.py tests/test_broadcast.py
git commit -m "feat(broadcast): Phase 3 watchlist summary + --skip-watchlist flag"
```

---

## Task 9: README + final verification + push + prod smoke

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Lint check**

```
ruff check src/ tests/
```

Expected: clean.

- [ ] **Step 2: Full pytest**

```
pytest -q
```

Expected: ~195+ passed (164 기존 + ~30 Week 7 신규), ~30 skipped.

- [ ] **Step 3: README update**

`README.md`에 Week 7 섹션 추가 (Week 6 섹션 아래):

```markdown
## Week 7: Watchlist + 모닝 카드 통합

사용자별 관심 종목(최대 5개) 등록 + 매일 07:00 사주 카드 1통 + watchlist 시그널 요약 1통 발송.

### 새 명령어
- `/watch <심볼>` — 관심 종목 추가 (최대 5개)
- `/unwatch <심볼>` — 관심 종목 제거
- `/watchlist` — 내 관심 종목 목록

정규화 규칙은 `/signal`과 동일 (`upper + $제거`).

### Broadcast 흐름 (07:00 KST)

```
Phase 1: Precompute (admin chat으로 watchlist union 캐시 워밍)
Phase 2: 사주 카드 N통 (기존 Week 5 그대로, 회귀 0)
Phase 3: Watchlist 요약 (watchlist 있는 사용자에게만 1통씩)
```

Phase 1 실패해도 Phase 2/3 진행 (graceful). watchlist 비어있는 사용자는 Phase 3 skip → 기존처럼 1통만 받음.

### 새 API 엔드포인트
- `GET /v1/users/{chat_id}/watchlist`
- `POST /v1/users/{chat_id}/watchlist` body: `{"ticker": "AAPL"}`
- `DELETE /v1/users/{chat_id}/watchlist/{ticker}`
- `GET /v1/admin/watchlist-symbols` — broadcast 전용 union

### 에러 매트릭스 (API)

| 상황 | HTTP | detail |
|------|------|--------|
| 지원 안 하는 심볼 | 400 | `unsupported ticker: ...` |
| 이미 있음 | 409 | `already in watchlist` |
| 5개 가득 | 409 | `watchlist full (max 5)` |
| 없는 심볼 제거 | 404 | `not in watchlist` |
| 명식 미등록 | 404 | `user not found` |

### DB 스키마
새 테이블 `user_watchlist`. `migrations/002_watchlist.sql` 참조.

### CLI 플래그
```
python -m sajucandle.broadcast               # Phase 1+2+3 (기본)
python -m sajucandle.broadcast --skip-watchlist   # Phase 1+2 (Week 5 상태)
python -m sajucandle.broadcast --dry-run --test-chat-id N
```

### 새 환경변수
- `SAJUCANDLE_ADMIN_CHAT_ID` — Phase 1 precompute에 쓸 사용자 chat_id.
  - `sajucandle-broadcast` 서비스 Variables에만 추가.
  - 미설정 시 Phase 1 skip (Phase 2/3만 실행).

### 범위 밖 (Week 8+)
- KIS 국내주식
- 장중 실시간 강진입 알림
- 가격 breakout alert
- 시그널 적중률 로깅
```

또한 기존 README에서:
- 테스트 개수 배지/섹션이 있으면 최신 숫자로 갱신
- 봇 커맨드 표에 /watch, /unwatch, /watchlist 추가
- API 엔드포인트 목록에 4개 추가
- 아키텍처 다이어그램이 있으면 `user_watchlist` 테이블 및 Phase 1~3 흐름 반영

- [ ] **Step 4: Commit README**

```
git add README.md
git commit -m "docs: Week 7 watchlist + morning push integration complete"
```

- [ ] **Step 5: Push to remote**

```
git log --oneline origin/main..HEAD
```

Week 7 커밋 목록 확인 (스펙 + 태스크 1~9 커밋). 그 후:

```
git push origin main
```

Railway 3 서비스 자동 재배포.

- [ ] **Step 6: Apply production DB migration (user manual step)**

배포와 별개로 **Supabase Studio에서 `migrations/002_watchlist.sql` 실행**. 실행 안 하면 운영에서 watchlist API 호출 시 500 (`relation "user_watchlist" does not exist`).

실행 방법:
1. Supabase 대시보드 → 프로젝트 → SQL Editor
2. `migrations/002_watchlist.sql` 내용 복붙
3. Run

기대: `CREATE TABLE` + `CREATE INDEX` 성공.

- [ ] **Step 7: Set Railway env var**

`sajucandle-broadcast` 서비스 → Variables → 추가:
```
SAJUCANDLE_ADMIN_CHAT_ID=7492682272
```
(본인 chat_id)

저장 후 서비스 자동 재시작.

- [ ] **Step 8: Production smoke**

배포 완료 후 (~3분):

**API 엔드포인트 확인:**
```
curl.exe -H "X-SAJUCANDLE-KEY: <KEY>" https://sajucandle-api-production.up.railway.app/v1/admin/watchlist-symbols
```
기대: `{"symbols":[]}` (아직 아무도 등록 안함).

**봇 명령어 스모크:**
- `/help` → /watch, /unwatch, /watchlist 포함
- `/watch AAPL` → ✅ 추가 응답
- `/watchlist` → 1/5, AAPL 표시
- `/watch MSFT` → ✅ 2/5
- `/watch GOOGL` → 3/5
- `/watch NVDA` → 4/5
- `/watch TSLA` → 5/5
- `/watch BTCUSDT` → "최대 5개" 에러
- `/unwatch TSLA` → 🗑️ 제거
- `/watch BTCUSDT` → ✅ 5/5 (이제 BTC 들어감)
- `/watch AMZN` → "지원하지 않는 심볼"
- `/watchlist` → 5개 표시

**Broadcast 수동 스모크 (선택):**
`sajucandle-broadcast` Settings → Cron Schedule 임시로 "N+2 M * * *"(현재 UTC +2분)로 변경 → 대기 → 로그 확인:
- `precompute_ok=6/6` 나오는지
- 본인 폰에 2통(사주 + watchlist) 도착하는지
- 끝나면 Cron Schedule 원복 (`0 22 * * *`)

---

## Self-Review

### Spec coverage

- [x] §4.1 user_watchlist 스키마 → Task 1 (migration SQL)
- [x] §4.2 5개 repository 함수 → Task 2
- [x] §5.1 4개 엔드포인트 → Task 3
- [x] §5.2 에러 매트릭스 (400/404/409) → Task 3 테스트 + api.py 구현
- [x] §6.1 /watch, /unwatch, /watchlist 정규화 → Task 5
- [x] §6.2 응답 문구 → Task 5
- [x] §6.3 /help 업데이트 → Task 5
- [x] §6.4 ApiClient 4개 메서드 → Task 4
- [x] §7.1 Phase 1 precompute → Task 7
- [x] §7.1 Phase 2 회귀 0 → Task 7/8 (기존 코드 유지)
- [x] §7.1 Phase 3 watchlist 요약 → Task 8
- [x] §7.2 카드 포맷 + [BTC] 축약 + 🕐 → Task 6 format_watchlist_summary
- [x] §7.3 BroadcastSummary 확장 → Task 6
- [x] §7.4 --skip-watchlist CLI → Task 8
- [x] §7.5 SAJUCANDLE_ADMIN_CHAT_ID env → Task 8 (main) + Task 9 (배포)
- [x] §8 테스트 전략 전 파일 → Task 2-8 분산
- [x] §9 관측성 로그 → Task 3,5,7,8
- [x] §10 배포 단계 → Task 9
- [x] §11 위험 (race condition 트랜잭션) → Task 3 add_watchlist_endpoint 트랜잭션 블록
- [x] §12 완료 기준 → Task 9 prod smoke

### Placeholder scan

- 모든 step에 실제 코드/명령 포함
- "similar to" "TODO" "TBD" 없음
- 에러 분기 전부 구체 문자열 검증

### Type consistency

- `WatchlistEntry(ticker, added_at)` Task 2 정의 → Task 3 엔드포인트에서 `e.ticker`, `e.added_at` 일치
- `WatchlistAddRequest.ticker`, `WatchlistResponse.items`, `WatchlistSymbolsResponse.symbols` Task 3 정의 → Task 4 응답 키 일치 (`items`, `symbols`)
- `market_status.category` 값은 `"crypto" | "us_stock"` — Task 6 format_watchlist_summary 분기 일치
- `BroadcastSummary` 필드명 Task 6 정의 → Task 7/8 카운터 증가 일치 (`watchlist_sent/skipped_empty/failed`, `precompute_ok/failed`)
- `run_broadcast` 새 파라미터 `admin_chat_id: Optional[int]`, `skip_watchlist: bool` Task 7/8 일관

### 주의사항

- Task 5 Step 4의 bot.py 수정은 실제 파일 구조에 맞춰 조정 필요. `CommandHandler` 등록 패턴 확인 후 삽입.
- Task 7/8에서 기존 `run_broadcast` 함수 시그니처에 새 파라미터 2개 추가. 기본값 지정으로 하위 호환.
- Task 8 Step 5에서 Week 5 테스트 일부가 Phase 3 기본 활성으로 깨질 수 있음. 대응은 `skip_watchlist=True` 명시 추가.
- Task 9 Step 6(운영 DB 마이그레이션)은 **사용자가 직접 실행**. 플랜 실행자(subagent)는 못 함.
- Windows PowerShell에서 psql 명령 실행 시 `$env:TEST_DATABASE_URL` 사용.

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-04-17-week7-watchlist.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**

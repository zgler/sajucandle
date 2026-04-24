# Week 10 Phase 1: 관측성 도구 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) to implement this plan task-by-task.

**Goal:** signal_log 집계 엔드포인트 + 봇 `/stats` 관리자 명령 추가. 3~5일 운영 중 사용자가 매일 누적 상황을 한 번에 확인할 수 있게 함.

**Architecture:** `repositories.aggregate_signal_stats()` PostgreSQL 집계 쿼리 + `GET /v1/admin/signal-stats` API + `ApiClient.get_signal_stats()` + handlers `/stats` 명령. 권한은 `SAJUCANDLE_ADMIN_CHAT_ID` env 기반.

**Tech Stack:** Python 3.12, FastAPI, asyncpg (percentile_cont), pytest, respx.

**Spec:** `docs/superpowers/specs/2026-04-19-week10-phase1-observability-design.md`

---

## File Structure

```
src/sajucandle/
├── repositories.py           # [MODIFY] aggregate_signal_stats 추가
├── api.py                    # [MODIFY] GET /v1/admin/signal-stats 추가
├── api_client.py             # [MODIFY] get_signal_stats
├── handlers.py               # [MODIFY] /stats 명령 + _format_stats_card
└── bot.py                    # [MODIFY] CommandHandler("stats") 등록

tests/
├── test_repositories.py      # [MODIFY] aggregate_signal_stats (DB 통합)
├── test_api_stats.py         # [CREATE] /v1/admin/signal-stats
├── test_api_client.py        # [MODIFY] get_signal_stats respx
└── test_handlers.py          # [MODIFY] /stats admin only
```

---

## Task 1: repositories.aggregate_signal_stats (TDD)

**Files:**
- Modify: `src/sajucandle/repositories.py`
- Modify: `tests/test_repositories.py`

- [ ] **Step 1: Write failing tests**

`tests/test_repositories.py` 맨 아래에 추가:

```python
# ─────────────────────────────────────────────
# Week 10 Phase 1: aggregate_signal_stats
# ─────────────────────────────────────────────

from datetime import timedelta

from sajucandle.repositories import aggregate_signal_stats


async def test_aggregate_signal_stats_empty(db_conn):
    now = datetime.now(timezone.utc)
    stats = await aggregate_signal_stats(db_conn, since=now - timedelta(days=30))
    assert stats["total"] == 0
    assert stats["by_grade"] == {}
    assert stats["tracking_completed"] == 0
    assert stats["tracking_pending"] == 0
    assert stats["sample_size"] == 0


async def test_aggregate_signal_stats_counts_by_grade(db_conn):
    await _register_user(db_conn, 400001)
    now = datetime.now(timezone.utc)
    # 3 entries, 1 gwan, 1 hoe
    for grade in ["진입", "진입", "진입", "관망", "회피"]:
        await insert_signal_log(
            db_conn,
            source="ondemand", telegram_chat_id=400001,
            ticker="BTCUSDT", target_date=date(2026, 4, 19),
            entry_price=70000.0,
            saju_score=50, analysis_score=60,
            structure_state="range", alignment_bias="mixed",
            rsi_1h=None, volume_ratio_1d=None,
            composite_score=60, signal_grade=grade,
        )
    stats = await aggregate_signal_stats(db_conn, since=now - timedelta(days=30))
    assert stats["total"] == 5
    assert stats["by_grade"]["진입"] == 3
    assert stats["by_grade"]["관망"] == 1
    assert stats["by_grade"]["회피"] == 1


async def test_aggregate_signal_stats_ticker_filter(db_conn):
    await _register_user(db_conn, 400002)
    now = datetime.now(timezone.utc)
    for ticker in ["BTCUSDT", "BTCUSDT", "AAPL"]:
        await insert_signal_log(
            db_conn,
            source="ondemand", telegram_chat_id=400002,
            ticker=ticker, target_date=date(2026, 4, 19),
            entry_price=100.0,
            saju_score=50, analysis_score=60,
            structure_state="range", alignment_bias="mixed",
            rsi_1h=None, volume_ratio_1d=None,
            composite_score=60, signal_grade="관망",
        )
    stats = await aggregate_signal_stats(
        db_conn, since=now - timedelta(days=30), ticker="BTCUSDT"
    )
    assert stats["total"] == 2


async def test_aggregate_signal_stats_grade_filter(db_conn):
    await _register_user(db_conn, 400003)
    now = datetime.now(timezone.utc)
    for grade in ["진입", "관망", "관망"]:
        await insert_signal_log(
            db_conn,
            source="ondemand", telegram_chat_id=400003,
            ticker="BTCUSDT", target_date=date(2026, 4, 19),
            entry_price=100.0,
            saju_score=50, analysis_score=60,
            structure_state="range", alignment_bias="mixed",
            rsi_1h=None, volume_ratio_1d=None,
            composite_score=60, signal_grade=grade,
        )
    stats = await aggregate_signal_stats(
        db_conn, since=now - timedelta(days=30), grade="관망"
    )
    assert stats["total"] == 2
    assert stats["by_grade"] == {"관망": 2}


async def test_aggregate_signal_stats_mfe_mae_only_from_tracking_done(db_conn):
    """MFE/MAE는 tracking_done=TRUE 건만."""
    await _register_user(db_conn, 400004)
    now = datetime.now(timezone.utc)
    # row 1: tracking_done=TRUE, mfe=3, mae=-1
    id1 = await insert_signal_log(
        db_conn,
        source="ondemand", telegram_chat_id=400004,
        ticker="BTCUSDT", target_date=date(2026, 4, 19),
        entry_price=100.0,
        saju_score=50, analysis_score=60,
        structure_state="range", alignment_bias="mixed",
        rsi_1h=None, volume_ratio_1d=None,
        composite_score=60, signal_grade="진입",
    )
    from sajucandle.repositories import update_signal_tracking
    await update_signal_tracking(
        db_conn, id1,
        mfe_pct=3.0, mae_pct=-1.0,
        close_24h=None, close_7d=None,
        tracking_done=True,
    )
    # row 2: tracking_done=FALSE (집계에서 제외)
    id2 = await insert_signal_log(
        db_conn,
        source="ondemand", telegram_chat_id=400004,
        ticker="BTCUSDT", target_date=date(2026, 4, 19),
        entry_price=100.0,
        saju_score=50, analysis_score=60,
        structure_state="range", alignment_bias="mixed",
        rsi_1h=None, volume_ratio_1d=None,
        composite_score=60, signal_grade="진입",
    )
    stats = await aggregate_signal_stats(db_conn, since=now - timedelta(days=30))
    assert stats["total"] == 2
    assert stats["tracking_completed"] == 1
    assert stats["tracking_pending"] == 1
    assert stats["sample_size"] == 1
    assert stats["mfe_avg"] == 3.0
    assert stats["mae_avg"] == -1.0
```

- [ ] **Step 2: Run — fail**

```
pytest tests/test_repositories.py -v -k "aggregate_signal_stats"
```

기대: ImportError or skip.

- [ ] **Step 3: Implement**

`src/sajucandle/repositories.py` 맨 아래에 추가:

```python
# ─────────────────────────────────────────────
# Week 10 Phase 1: signal_log 집계
# ─────────────────────────────────────────────


async def aggregate_signal_stats(
    conn: asyncpg.Connection,
    *,
    since: datetime,
    ticker: Optional[str] = None,
    grade: Optional[str] = None,
) -> dict:
    """signal_log 집계 — total, by_grade, tracking, MFE/MAE 통계."""
    # 동적 WHERE 조합
    conditions = ["sent_at >= $1"]
    params: list = [since]
    if ticker is not None:
        params.append(ticker)
        conditions.append(f"ticker = ${len(params)}")
    if grade is not None:
        params.append(grade)
        conditions.append(f"signal_grade = ${len(params)}")
    where = " AND ".join(conditions)

    # 1. total + by_grade
    total_row = await conn.fetchval(
        f"SELECT COUNT(*) FROM signal_log WHERE {where}",
        *params,
    )
    total = int(total_row or 0)

    by_grade_rows = await conn.fetch(
        f"SELECT signal_grade, COUNT(*) AS cnt FROM signal_log "
        f"WHERE {where} GROUP BY signal_grade",
        *params,
    )
    by_grade = {r["signal_grade"]: int(r["cnt"]) for r in by_grade_rows}

    # 2. tracking counts
    tracking_row = await conn.fetchrow(
        f"SELECT "
        f"  COUNT(*) FILTER (WHERE tracking_done) AS done, "
        f"  COUNT(*) FILTER (WHERE NOT tracking_done) AS pending "
        f"FROM signal_log WHERE {where}",
        *params,
    )
    tracking_completed = int(tracking_row["done"] or 0)
    tracking_pending = int(tracking_row["pending"] or 0)

    # 3. MFE/MAE (tracking_done=TRUE만)
    stats_row = await conn.fetchrow(
        f"SELECT "
        f"  COUNT(*) AS n, "
        f"  AVG(mfe_7d_pct) AS mfe_avg, "
        f"  AVG(mae_7d_pct) AS mae_avg, "
        f"  PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY mfe_7d_pct) AS mfe_median, "
        f"  PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY mae_7d_pct) AS mae_median "
        f"FROM signal_log "
        f"WHERE {where} AND tracking_done = TRUE "
        f"AND mfe_7d_pct IS NOT NULL AND mae_7d_pct IS NOT NULL",
        *params,
    )
    sample_size = int(stats_row["n"] or 0)
    mfe_avg = float(stats_row["mfe_avg"]) if stats_row["mfe_avg"] is not None else None
    mae_avg = float(stats_row["mae_avg"]) if stats_row["mae_avg"] is not None else None
    mfe_median = (
        float(stats_row["mfe_median"]) if stats_row["mfe_median"] is not None else None
    )
    mae_median = (
        float(stats_row["mae_median"]) if stats_row["mae_median"] is not None else None
    )

    return {
        "total": total,
        "by_grade": by_grade,
        "tracking_completed": tracking_completed,
        "tracking_pending": tracking_pending,
        "sample_size": sample_size,
        "mfe_avg": mfe_avg,
        "mfe_median": mfe_median,
        "mae_avg": mae_avg,
        "mae_median": mae_median,
    }
```

- [ ] **Step 4-6: Run + Commit**

```
pytest tests/test_repositories.py -v
pytest -q
git add src/sajucandle/repositories.py tests/test_repositories.py
git commit -m "feat(repo): add aggregate_signal_stats for signal_log rollup"
```

---

## Task 2: api.py — GET /v1/admin/signal-stats

**Files:**
- Modify: `src/sajucandle/api.py`
- Create: `tests/test_api_stats.py`

- [ ] **Step 1: Write failing tests**

`tests/test_api_stats.py`:

```python
"""api: /v1/admin/signal-stats 엔드포인트."""
from __future__ import annotations

import os
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from sajucandle.api import create_app


@pytest.fixture
def api_key(monkeypatch):
    monkeypatch.setenv("SAJUCANDLE_API_KEY", "test-key")
    return "test-key"


@pytest.fixture
def client(api_key, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", os.environ.get("TEST_DATABASE_URL", ""))
    app = create_app()
    with TestClient(app) as c:
        yield c


HEADERS = {"X-SAJUCANDLE-KEY": "test-key"}

pytestmark = pytest.mark.skipif(
    os.environ.get("TEST_DATABASE_URL") is None,
    reason="TEST_DATABASE_URL not set",
)


def test_stats_requires_api_key(client):
    r = client.get("/v1/admin/signal-stats")
    assert r.status_code == 401


def test_stats_empty_returns_zero(client):
    r = client.get("/v1/admin/signal-stats", headers=HEADERS)
    assert r.status_code == 200
    body = r.json()
    assert "total" in body
    assert "by_grade" in body
    assert "tracking" in body
    assert "mfe_mae" in body


def test_stats_rejects_bad_since(client):
    r = client.get(
        "/v1/admin/signal-stats",
        params={"since": "not-a-date"},
        headers=HEADERS,
    )
    assert r.status_code == 400
```

- [ ] **Step 2: Run — fail**

```
pytest tests/test_api_stats.py -v
```

- [ ] **Step 3: Modify api.py**

기존 `/v1/admin/ohlcv` 엔드포인트 근처에 추가:

```python
    @app.get("/v1/admin/signal-stats")
    async def admin_signal_stats_endpoint(
        request: Request,
        ticker: Optional[str] = None,
        grade: Optional[str] = None,
        since: Optional[str] = None,
        x_sajucandle_key: Optional[str] = Header(default=None),
    ):
        """Week 10: signal_log 집계 관측 도구."""
        _require_api_key(request, x_sajucandle_key)
        if db.get_pool() is None:
            raise HTTPException(503, detail="database not available")

        if since:
            try:
                since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
            except ValueError:
                raise HTTPException(400, detail="since must be ISO 8601")
        else:
            from datetime import timedelta
            since_dt = datetime.now(timezone.utc) - timedelta(days=30)

        async with db.acquire() as conn:
            stats = await repositories.aggregate_signal_stats(
                conn, since=since_dt, ticker=ticker, grade=grade
            )

        logger.info(
            "signal stats ticker=%s grade=%s since=%s total=%s",
            ticker, grade, since_dt.isoformat(), stats["total"],
        )

        return {
            "since": since_dt.isoformat(),
            "filters": {"ticker": ticker, "grade": grade},
            "total": stats["total"],
            "by_grade": stats["by_grade"],
            "tracking": {
                "completed": stats["tracking_completed"],
                "pending": stats["tracking_pending"],
            },
            "mfe_mae": {
                "sample_size": stats["sample_size"],
                "mfe_avg": stats["mfe_avg"],
                "mfe_median": stats["mfe_median"],
                "mae_avg": stats["mae_avg"],
                "mae_median": stats["mae_median"],
            },
        }
```

`timezone` import 확인 (기존 api.py에서 사용 중).

- [ ] **Step 4-6: Run + Commit**

```
pytest tests/test_api_stats.py -v
pytest -q
git add src/sajucandle/api.py tests/test_api_stats.py
git commit -m "feat(api): GET /v1/admin/signal-stats observability endpoint"
```

---

## Task 3: api_client.get_signal_stats

**Files:**
- Modify: `src/sajucandle/api_client.py`
- Modify: `tests/test_api_client.py`

- [ ] **Step 1: Write failing tests**

`tests/test_api_client.py` 맨 아래:

```python
@pytest.mark.asyncio
async def test_get_signal_stats_returns_dict():
    import respx
    from httpx import Response
    from sajucandle.api_client import ApiClient

    with respx.mock(base_url="http://test") as mock:
        mock.get("/v1/admin/signal-stats").mock(
            return_value=Response(200, json={
                "since": "2026-03-20T00:00:00+00:00",
                "filters": {"ticker": None, "grade": None},
                "total": 10,
                "by_grade": {"진입": 3, "관망": 7},
                "tracking": {"completed": 2, "pending": 8},
                "mfe_mae": {
                    "sample_size": 2, "mfe_avg": 2.5, "mfe_median": 2.5,
                    "mae_avg": -1.0, "mae_median": -1.0,
                },
            })
        )
        c = ApiClient(base_url="http://test", api_key="k")
        stats = await c.get_signal_stats()
    assert stats["total"] == 10
    assert stats["by_grade"]["진입"] == 3


@pytest.mark.asyncio
async def test_get_signal_stats_with_filters():
    import respx
    from httpx import Response
    from sajucandle.api_client import ApiClient

    with respx.mock(base_url="http://test") as mock:
        route = mock.get("/v1/admin/signal-stats").mock(
            return_value=Response(200, json={
                "since": "x", "filters": {}, "total": 0,
                "by_grade": {}, "tracking": {"completed": 0, "pending": 0},
                "mfe_mae": {"sample_size": 0, "mfe_avg": None, "mfe_median": None,
                            "mae_avg": None, "mae_median": None},
            })
        )
        c = ApiClient(base_url="http://test", api_key="k")
        await c.get_signal_stats(ticker="AAPL", grade="진입")
    req = route.calls.last.request
    assert "ticker=AAPL" in str(req.url)
    assert "grade=%EC%A7%84%EC%9E%85" in str(req.url) or "grade=진입" in str(req.url)
```

- [ ] **Step 2-6: Run + Implement + Commit**

`src/sajucandle/api_client.py` 맨 아래 추가:

```python
    async def get_signal_stats(
        self,
        *,
        ticker: Optional[str] = None,
        grade: Optional[str] = None,
        since: Optional[str] = None,
    ) -> dict:
        """GET /v1/admin/signal-stats. 집계 관측 도구."""
        params: Dict[str, str] = {}
        if ticker:
            params["ticker"] = ticker
        if grade:
            params["grade"] = grade
        if since:
            params["since"] = since
        async with self._client() as c:
            r = await c.get("/v1/admin/signal-stats", params=params)
        await self._raise_for_status(r)
        return r.json()
```

```
pytest tests/test_api_client.py -v
pytest -q
git add src/sajucandle/api_client.py tests/test_api_client.py
git commit -m "feat(api_client): add get_signal_stats"
```

---

## Task 4: handlers.py — /stats 명령 + admin 체크 + 카드

**Files:**
- Modify: `src/sajucandle/handlers.py`
- Modify: `src/sajucandle/bot.py`
- Modify: `tests/test_handlers.py`

- [ ] **Step 1: Tests**

`tests/test_handlers.py` 맨 아래:

```python
# ─────────────────────────────────────────────
# Week 10 Phase 1: /stats admin 명령
# ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_stats_rejects_non_admin(monkeypatch):
    from sajucandle import handlers
    from unittest.mock import AsyncMock, MagicMock

    monkeypatch.setenv("SAJUCANDLE_ADMIN_CHAT_ID", "99999")
    monkeypatch.setattr(handlers, "_api_client", MagicMock())
    context = MagicMock(args=[])
    update = _make_update(text="/stats", chat_id=12345)  # not admin
    update.message.reply_text = AsyncMock()

    await handlers.stats_command(update, context)
    sent = update.message.reply_text.call_args[0][0]
    assert "관리자" in sent or "권한" in sent


@pytest.mark.asyncio
async def test_stats_admin_calls_api(monkeypatch):
    from sajucandle import handlers
    from unittest.mock import AsyncMock, MagicMock

    monkeypatch.setenv("SAJUCANDLE_ADMIN_CHAT_ID", "12345")

    async def fake_stats(**kwargs):
        return {
            "since": "2026-03-20T00:00:00+00:00",
            "filters": {"ticker": None, "grade": None},
            "total": 5,
            "by_grade": {"진입": 2, "관망": 3},
            "tracking": {"completed": 1, "pending": 4},
            "mfe_mae": {
                "sample_size": 1, "mfe_avg": 2.5, "mfe_median": 2.5,
                "mae_avg": -1.0, "mae_median": -1.0,
            },
        }

    monkeypatch.setattr(handlers, "_api_client",
                        MagicMock(get_signal_stats=fake_stats))
    context = MagicMock(args=[])
    update = _make_update(text="/stats", chat_id=12345)
    update.message.reply_text = AsyncMock()

    await handlers.stats_command(update, context)
    sent = update.message.reply_text.call_args[0][0]
    assert "총 발송" in sent
    assert "5" in sent
    assert "진입" in sent


@pytest.mark.asyncio
async def test_stats_with_ticker_and_grade_args(monkeypatch):
    from sajucandle import handlers
    from unittest.mock import AsyncMock, MagicMock

    monkeypatch.setenv("SAJUCANDLE_ADMIN_CHAT_ID", "12345")
    captured = {}

    async def fake_stats(*, ticker=None, grade=None, since=None):
        captured["ticker"] = ticker
        captured["grade"] = grade
        return {
            "since": "2026-03-20T00:00:00+00:00",
            "filters": {"ticker": ticker, "grade": grade},
            "total": 0,
            "by_grade": {},
            "tracking": {"completed": 0, "pending": 0},
            "mfe_mae": {"sample_size": 0, "mfe_avg": None, "mfe_median": None,
                        "mae_avg": None, "mae_median": None},
        }

    monkeypatch.setattr(handlers, "_api_client",
                        MagicMock(get_signal_stats=fake_stats))
    context = MagicMock(args=["AAPL", "진입"])
    update = _make_update(text="/stats AAPL 진입", chat_id=12345)
    update.message.reply_text = AsyncMock()

    await handlers.stats_command(update, context)
    assert captured["ticker"] == "AAPL"
    assert captured["grade"] == "진입"


@pytest.mark.asyncio
async def test_stats_empty_shows_no_history(monkeypatch):
    from sajucandle import handlers
    from unittest.mock import AsyncMock, MagicMock

    monkeypatch.setenv("SAJUCANDLE_ADMIN_CHAT_ID", "12345")

    async def fake_stats(**kwargs):
        return {
            "since": "2026-03-20T00:00:00+00:00",
            "filters": {"ticker": None, "grade": None},
            "total": 0,
            "by_grade": {},
            "tracking": {"completed": 0, "pending": 0},
            "mfe_mae": {"sample_size": 0, "mfe_avg": None, "mfe_median": None,
                        "mae_avg": None, "mae_median": None},
        }

    monkeypatch.setattr(handlers, "_api_client",
                        MagicMock(get_signal_stats=fake_stats))
    context = MagicMock(args=[])
    update = _make_update(text="/stats", chat_id=12345)
    update.message.reply_text = AsyncMock()

    await handlers.stats_command(update, context)
    sent = update.message.reply_text.call_args[0][0]
    assert "없" in sent or "0" in sent
```

- [ ] **Step 2: Run — fail**

```
pytest tests/test_handlers.py -v -k "stats"
```

- [ ] **Step 3: Implement handlers.py**

파일 맨 아래(`help_command` 이전)에 추가:

```python
async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """`/stats [심볼] [등급]` — 관리자 전용 signal_log 집계."""
    if update.message is None:
        return
    chat_id = update.effective_chat.id

    admin_chat_id_env = os.environ.get("SAJUCANDLE_ADMIN_CHAT_ID")
    if not admin_chat_id_env or str(chat_id) != admin_chat_id_env:
        await update.message.reply_text("관리자 전용 명령입니다.")
        return

    args = list(context.args or [])
    ticker: Optional[str] = None
    grade: Optional[str] = None
    if len(args) >= 1:
        ticker = args[0].upper().lstrip("$")
    if len(args) >= 2:
        grade = args[1]

    try:
        stats = await _api_client.get_signal_stats(ticker=ticker, grade=grade)
    except httpx.TimeoutException:
        await update.message.reply_text("서버 응답이 느립니다. 잠시 후 다시.")
        return
    except httpx.TransportError:
        await update.message.reply_text("서버에 연결할 수 없습니다.")
        return
    except ApiError as e:
        logger.warning("stats api error status=%s", e.status)
        await update.message.reply_text(f"서버 오류 ({e.status}).")
        return

    await update.message.reply_text(_format_stats_card(stats))


def _format_stats_card(stats: dict) -> str:
    total = stats.get("total", 0)
    by_grade = stats.get("by_grade") or {}
    tracking = stats.get("tracking") or {}
    mfe_mae = stats.get("mfe_mae") or {}
    filters = stats.get("filters") or {}

    filter_parts = []
    if filters.get("ticker"):
        filter_parts.append(filters["ticker"])
    if filters.get("grade"):
        filter_parts.append(filters["grade"])
    filter_str = " · ".join(filter_parts) if filter_parts else "전체"

    lines = [
        "📊 신호 통계 (최근 30일)",
        "─────────────",
        f"필터: {filter_str}",
        f"총 발송: {total}건",
    ]

    if total == 0:
        lines.append("")
        lines.append("해당 조건의 발송 이력이 없습니다.")
        return "\n".join(lines)

    lines.append("")
    lines.append("등급별:")
    for grade_name in ["강진입", "진입", "관망", "회피"]:
        cnt = by_grade.get(grade_name, 0)
        if cnt > 0:
            lines.append(f"  {grade_name:<4}  {cnt}건")

    completed = tracking.get("completed", 0)
    pending = tracking.get("pending", 0)
    pct = int(completed / total * 100) if total > 0 else 0
    lines.append("")
    lines.append(f"추적 완료: {completed}/{total} ({pct}%)")

    sample_size = mfe_mae.get("sample_size", 0)
    if sample_size > 0:
        mfe_avg = mfe_mae.get("mfe_avg") or 0.0
        mfe_med = mfe_mae.get("mfe_median") or 0.0
        mae_avg = mfe_mae.get("mae_avg") or 0.0
        mae_med = mfe_mae.get("mae_median") or 0.0
        lines.append("")
        lines.append(f"MFE/MAE 평균 (n={sample_size}):")
        lines.append(f"  MFE  {mfe_avg:+.1f}% (중앙 {mfe_med:+.1f}%)")
        lines.append(f"  MAE  {mae_avg:+.1f}% (중앙 {mae_med:+.1f}%)")
    else:
        lines.append("")
        lines.append("MFE/MAE: 샘플 부족 (추적 완료 0건)")

    return "\n".join(lines)
```

- [ ] **Step 4: Register in bot.py**

```
grep -n "CommandHandler" src/sajucandle/bot.py
```

기존 `CommandHandler("watchlist", ...)` 또는 `CommandHandler("help", ...)` 근처에 추가:

```python
application.add_handler(CommandHandler("stats", handlers.stats_command))
```

- [ ] **Step 5-6: Run + Commit**

```
pytest tests/test_handlers.py -v -k "stats"
pytest -q
git add src/sajucandle/handlers.py src/sajucandle/bot.py tests/test_handlers.py
git commit -m "feat(bot): add /stats admin command for signal_log observability"
```

---

## Task 5: README + push

**Files:**
- Modify: `README.md`

- [ ] **Step 1: ruff + pytest**

```
ruff check src/ tests/
pytest -q
```

- [ ] **Step 2: README**

Week 9 섹션 아래에 Week 10 Phase 1 섹션 추가:

```markdown
## Week 10 Phase 1: 관측성 도구

signal_log 집계로 누적 상황 확인. 운영 중 `/stats` 한 번으로 진행상황 체크.

### 새 API
- `GET /v1/admin/signal-stats?ticker=&grade=&since=` — 집계 관측

### 새 봇 명령 (관리자만)
- `/stats` — 최근 30일 전체
- `/stats AAPL` — AAPL 30일
- `/stats AAPL 진입` — AAPL 진입 등급 30일

### 카드 예시
```
📊 신호 통계 (최근 30일)
─────────────
필터: 전체
총 발송: 42건

등급별:
  강진입  5건
  진입    12건
  관망    20건
  회피    5건

추적 완료: 15/42 (35%)

MFE/MAE 평균 (n=15):
  MFE  +2.8% (중앙 +2.3%)
  MAE  -1.4% (중앙 -1.1%)
```

### 권한
`SAJUCANDLE_ADMIN_CHAT_ID` env의 chat_id만 `/stats` 사용 가능 (일반 `/help`에는 숨김).

### Phase 2 (데이터 쌓인 후)
발송 거부 규칙 (BREAKDOWN 매수 차단), 카드 세밀 조정, 에러 메시지 개선.
```

- [ ] **Step 3: Commit + push**

```
git add README.md
git commit -m "docs: Week 10 Phase 1 observability (/stats admin command)"
git push origin main
```

---

## Self-Review

### Spec coverage
- [x] §4.1 signal-stats 엔드포인트 → Task 2
- [x] §4.2 aggregate_signal_stats → Task 1
- [x] §4.3 api_client → Task 3
- [x] §4.4 /stats 명령 + admin 체크 → Task 4
- [x] §4.5 카드 포맷 → Task 4 `_format_stats_card`
- [x] §5 에러 매트릭스 → Task 4 (admin reject) + Task 2 (400)

### Type consistency
- `aggregate_signal_stats` 반환 dict 키 (`total`, `by_grade`, `tracking_completed`, `tracking_pending`, `sample_size`, `mfe_avg`, `mfe_median`, `mae_avg`, `mae_median`) Task 1 정의 ↔ Task 2 엔드포인트 응답 구성 일치.
- API 응답 구조 (`tracking`, `mfe_mae` 중첩 dict) Task 2 정의 ↔ Task 3 api_client 통과 ↔ Task 4 카드 소비 일치.

### 주의
- `/help`에는 `/stats` 노출 안 함 (관리자 전용 → 일반 사용자 혼란 방지). Task 4 Step 3에서 `help_command` 수정 금지.
- `SAJUCANDLE_ADMIN_CHAT_ID`는 Week 7에서 이미 broadcast 서비스 Variables에 설정됨. Week 10 Phase 1에선 **bot 서비스 Variables에도 동일 값** 필요. 배포 후 사용자 수동 확인.

---

## Execution Handoff

**Plan complete. Two options:**

**1. Subagent-Driven (recommended)** — 태스크당 fresh subagent.

**2. Inline Execution** — 이 세션에서 순차 실행.

작은 스프린트(5 태스크)라 둘 다 적합. 사용자 "자율 진행" 지시 기반 **Subagent-Driven 채택**.

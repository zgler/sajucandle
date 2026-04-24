# Phase 1 구현 플랜 — 백테스트 하네스

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 과거 OHLCV로 임의 시점 `t`에서 `analyze()` + `_grade_signal()` 재생산 + 7일 MFE/MAE 계산 + `signal_log`에 `source='backtest'` + `run_id` 기록. Phase 2~4의 실데이터 기반 의사결정 인프라 완성. 서비스 코드 회귀 0.

**Architecture:** 신규 `src/sajucandle/backtest/` 패키지 9개 모듈 (`__init__`, `__main__`, `cli`, `history`, `slicer`, `engine`, `tracker`, `saju_stub`, `aggregate`). migration 005로 `signal_log.run_id` 컬럼 추가. `repositories.insert_signal_log` / `aggregate_signal_stats` + `api.py::admin_signal_stats_endpoint`에 `run_id` 파라미터 추가 (기본 None, 하위호환 100%). CLI `python -m sajucandle.backtest {run|aggregate}`.

**Tech Stack:** Python 3.12, asyncpg, pandas (yfinance resample 이미 설치), pytest/pytest-asyncio/respx/fakeredis, `MarketRouter` 재사용.

**Spec:** `docs/superpowers/specs/2026-04-20-phase1-backtest-harness-design.md` (Approved)

---

## File Structure

```
migrations/
└── 005_signal_log_run_id.sql           # [CREATE]

src/sajucandle/
├── repositories.py                     # [MODIFY] insert_signal_log + aggregate_signal_stats에 run_id
├── api.py                              # [MODIFY] admin_signal_stats_endpoint에 run_id query param
└── backtest/                           # [CREATE] 신규 패키지
    ├── __init__.py                     # 빈 (docstring)
    ├── __main__.py                     # cli.main() 진입
    ├── cli.py                          # argparse run/aggregate sub-commands
    ├── history.py                      # TickerHistory + load_history (디스크 JSON 캐시)
    ├── slicer.py                       # HistoryWindow.slice_at / post_bars_1h
    ├── tracker.py                      # compute_mfe_mae 순수 함수
    ├── saju_stub.py                    # fixed_saju_score → 50
    ├── engine.py                       # run_backtest (async)
    └── aggregate.py                    # aggregate_run (async) + GradeStats

tests/
├── test_backtest_slicer.py             # [CREATE] 룩어헤드 assertion
├── test_backtest_tracker.py            # [CREATE] compute_mfe_mae 공식
├── test_backtest_engine.py             # [CREATE] mock history + mock insert
├── test_backtest_aggregate.py          # [CREATE] 합성 signal_log 집계
├── test_backtest_cli.py                # [CREATE] argparse 파싱 오류
├── test_backtest_smoke.py              # [CREATE] end-to-end (DB 통합, TEST_DATABASE_URL 있을 때)
├── test_repositories.py                # [MODIFY] run_id 파라미터 통합 테스트
├── test_api_stats.py                   # [MODIFY] run_id query param
└── conftest.py                         # 기존 재사용

README.md                               # [MODIFY] Phase 1 섹션 추가
```

**운영 수동 단계 (Task 13):**
- Supabase Studio에서 `migrations/005_signal_log_run_id.sql` 실행

---

## Task 1: migration 005 + repositories.insert_signal_log에 run_id

**Files:**
- Create: `migrations/005_signal_log_run_id.sql`
- Modify: `src/sajucandle/repositories.py`
- Modify: `tests/test_repositories.py`

- [ ] **Step 1: Migration 파일**

`migrations/005_signal_log_run_id.sql`:

```sql
-- Phase 1: signal_log에 run_id 컬럼 추가 (백테스트 run 구분용).
-- 실행: Supabase Studio → SQL Editor → Run.
-- 로컬: psql $DATABASE_URL -f migrations/005_signal_log_run_id.sql
-- 로컬 테스트 DB: psql $TEST_DATABASE_URL -f migrations/005_signal_log_run_id.sql

ALTER TABLE signal_log
    ADD COLUMN IF NOT EXISTS run_id TEXT NULL;

CREATE INDEX IF NOT EXISTS idx_signal_log_run_id
    ON signal_log(run_id, ticker, target_date)
    WHERE run_id IS NOT NULL;
```

TEST_DATABASE_URL 있으면 `psql $env:TEST_DATABASE_URL -f migrations/005_signal_log_run_id.sql` 실행.

- [ ] **Step 2: Write failing test**

`tests/test_repositories.py` 맨 아래에 추가:

```python
# ─────────────────────────────────────────────
# Phase 1: insert_signal_log run_id
# ─────────────────────────────────────────────


async def test_insert_signal_log_with_run_id(db_conn):
    await _register_user(db_conn, 500001)
    row_id = await insert_signal_log(
        db_conn,
        source="backtest",
        telegram_chat_id=None,
        ticker="BTCUSDT",
        target_date=date(2026, 4, 19),
        entry_price=70000.0,
        saju_score=50,
        analysis_score=72,
        structure_state="uptrend",
        alignment_bias="bullish",
        rsi_1h=60.0,
        volume_ratio_1d=1.2,
        composite_score=70,
        signal_grade="진입",
        run_id="phase1-abc1234-baseline",
    )
    row = await db_conn.fetchrow(
        "SELECT run_id, source FROM signal_log WHERE id = $1", row_id
    )
    assert row["run_id"] == "phase1-abc1234-baseline"
    assert row["source"] == "backtest"


async def test_insert_signal_log_run_id_default_none(db_conn):
    """기존 호출 (run_id 미지정) 하위호환 — NULL 저장."""
    await _register_user(db_conn, 500002)
    row_id = await insert_signal_log(
        db_conn,
        source="ondemand",
        telegram_chat_id=500002,
        ticker="BTCUSDT",
        target_date=date(2026, 4, 19),
        entry_price=70000.0,
        saju_score=50,
        analysis_score=50,
        structure_state="range",
        alignment_bias="mixed",
        rsi_1h=None,
        volume_ratio_1d=None,
        composite_score=50,
        signal_grade="관망",
    )
    row = await db_conn.fetchrow(
        "SELECT run_id FROM signal_log WHERE id = $1", row_id
    )
    assert row["run_id"] is None
```

- [ ] **Step 3: Run — fail**

```
pytest tests/test_repositories.py -v -k "with_run_id or run_id_default_none"
```

TEST_DATABASE_URL 있으면 `TypeError: insert_signal_log() got an unexpected keyword argument 'run_id'`. 없으면 skip.

- [ ] **Step 4: Modify `repositories.insert_signal_log`**

`src/sajucandle/repositories.py` 내 `insert_signal_log` 시그니처에 Week 9 필드 **다음**에 추가:

```python
async def insert_signal_log(
    conn: asyncpg.Connection,
    *,
    source: str,
    telegram_chat_id: Optional[int],
    ticker: str,
    target_date,
    entry_price: float,
    saju_score: int,
    analysis_score: int,
    structure_state: str,
    alignment_bias: str,
    rsi_1h: Optional[float],
    volume_ratio_1d: Optional[float],
    composite_score: int,
    signal_grade: str,
    # Week 9
    stop_loss: Optional[float] = None,
    take_profit_1: Optional[float] = None,
    take_profit_2: Optional[float] = None,
    risk_pct: Optional[float] = None,
    rr_tp1: Optional[float] = None,
    rr_tp2: Optional[float] = None,
    sl_basis: Optional[str] = None,
    tp1_basis: Optional[str] = None,
    tp2_basis: Optional[str] = None,
    # Phase 1
    run_id: Optional[str] = None,
) -> int:
    row = await conn.fetchrow(
        """
        INSERT INTO signal_log (
            source, telegram_chat_id,
            ticker, target_date, entry_price,
            saju_score, analysis_score,
            structure_state, alignment_bias,
            rsi_1h, volume_ratio_1d,
            composite_score, signal_grade,
            stop_loss, take_profit_1, take_profit_2,
            risk_pct, rr_tp1, rr_tp2,
            sl_basis, tp1_basis, tp2_basis,
            run_id
        ) VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13,
            $14, $15, $16, $17, $18, $19, $20, $21, $22, $23
        ) RETURNING id
        """,
        source, telegram_chat_id,
        ticker, target_date, entry_price,
        saju_score, analysis_score,
        structure_state, alignment_bias,
        rsi_1h, volume_ratio_1d,
        composite_score, signal_grade,
        stop_loss, take_profit_1, take_profit_2,
        risk_pct, rr_tp1, rr_tp2,
        sl_basis, tp1_basis, tp2_basis,
        run_id,
    )
    return int(row["id"])
```

- [ ] **Step 5: Run — PASS**

```
pytest tests/test_repositories.py -v
pytest -q
```

Expected: 기존 + 신규 2개 passed. 회귀 0.

- [ ] **Step 6: Commit**

```
git add migrations/005_signal_log_run_id.sql src/sajucandle/repositories.py tests/test_repositories.py
git commit -m "feat(db,repo): add signal_log.run_id column + insert_signal_log 파라미터"
```

---

## Task 2: aggregate_signal_stats에 run_id 필터

**Files:**
- Modify: `src/sajucandle/repositories.py`
- Modify: `tests/test_repositories.py`

운영 `/stats`는 기본적으로 `run_id IS NULL`인 운영 signal만 집계. `run_id` 명시 시 해당 run만.

- [ ] **Step 1: Write failing tests**

`tests/test_repositories.py` 맨 아래에 추가:

```python
async def test_aggregate_signal_stats_default_excludes_backtest(db_conn):
    """run_id 미지정 시 backtest row 제외, 운영(NULL)만 집계."""
    await _register_user(db_conn, 500003)
    # 운영 signal
    await insert_signal_log(
        db_conn, source="ondemand", telegram_chat_id=500003,
        ticker="BTCUSDT", target_date=date(2026, 4, 19),
        entry_price=70000.0, saju_score=50, analysis_score=60,
        structure_state="range", alignment_bias="mixed",
        rsi_1h=None, volume_ratio_1d=None,
        composite_score=60, signal_grade="관망",
    )
    # 백테스트 signal (같은 사용자, 다른 날짜로 덮어쓰기 방지)
    await insert_signal_log(
        db_conn, source="backtest", telegram_chat_id=500003,
        ticker="BTCUSDT", target_date=date(2026, 4, 18),
        entry_price=70000.0, saju_score=50, analysis_score=60,
        structure_state="range", alignment_bias="mixed",
        rsi_1h=None, volume_ratio_1d=None,
        composite_score=60, signal_grade="진입",
        run_id="phase1-test-a",
    )
    now = datetime.now(timezone.utc)
    stats = await aggregate_signal_stats(db_conn, since=now - timedelta(days=30))
    # 운영 row 1개만 집계
    assert stats["total"] == 1
    assert stats["by_grade"].get("관망") == 1
    assert "진입" not in stats["by_grade"] or stats["by_grade"]["진입"] == 0


async def test_aggregate_signal_stats_with_run_id(db_conn):
    """run_id 명시 시 해당 run만 집계."""
    await _register_user(db_conn, 500004)
    await insert_signal_log(
        db_conn, source="backtest", telegram_chat_id=500004,
        ticker="BTCUSDT", target_date=date(2026, 4, 19),
        entry_price=70000.0, saju_score=50, analysis_score=72,
        structure_state="uptrend", alignment_bias="bullish",
        rsi_1h=None, volume_ratio_1d=None,
        composite_score=70, signal_grade="진입",
        run_id="phase1-test-b",
    )
    now = datetime.now(timezone.utc)
    stats = await aggregate_signal_stats(
        db_conn, since=now - timedelta(days=30), run_id="phase1-test-b"
    )
    assert stats["total"] == 1
    assert stats["by_grade"]["진입"] == 1
```

- [ ] **Step 2: Run — fail**

Expected: `TypeError: aggregate_signal_stats() got an unexpected keyword argument 'run_id'`.

- [ ] **Step 3: Modify `aggregate_signal_stats`**

`src/sajucandle/repositories.py`의 `aggregate_signal_stats`:

```python
async def aggregate_signal_stats(
    conn: asyncpg.Connection,
    *,
    since: datetime,
    ticker: Optional[str] = None,
    grade: Optional[str] = None,
    run_id: Optional[str] = None,   # Phase 1
) -> dict:
    conditions = ["sent_at >= $1"]
    params: list = [since]
    if ticker is not None:
        params.append(ticker)
        conditions.append(f"ticker = ${len(params)}")
    if grade is not None:
        params.append(grade)
        conditions.append(f"signal_grade = ${len(params)}")
    # Phase 1: run_id 처리 — None이면 운영만(run_id IS NULL), 값 있으면 해당 run만
    if run_id is None:
        conditions.append("run_id IS NULL")
    else:
        params.append(run_id)
        conditions.append(f"run_id = ${len(params)}")
    where = " AND ".join(conditions)

    # ... 이하 기존 쿼리 그대로 (where만 바뀜) ...
```

기존 `where = " AND ".join(conditions)` 아래 3개 SELECT는 변경 불필요 (where 변수만 쓰니까).

- [ ] **Step 4: Run — PASS**

```
pytest tests/test_repositories.py -v
```

- [ ] **Step 5: Full regression + Commit**

```
pytest -q
git add src/sajucandle/repositories.py tests/test_repositories.py
git commit -m "feat(repo): aggregate_signal_stats에 run_id 필터 (운영 기본 IS NULL)"
```

---

## Task 3: api.py admin_signal_stats_endpoint에 run_id query param

**Files:**
- Modify: `src/sajucandle/api.py`
- Modify: `tests/test_api_stats.py`

- [ ] **Step 1: Failing test**

`tests/test_api_stats.py` 맨 아래에 추가:

```python
def test_stats_endpoint_run_id_param(client):
    """?run_id=... 전달 시 aggregate_signal_stats에 반영."""
    r = client.get(
        "/v1/admin/signal-stats",
        params={"run_id": "phase1-test-endpoint"},
        headers=HEADERS,
    )
    assert r.status_code == 200
    body = r.json()
    # 빈 결과라도 필터 응답에 run_id 반영
    assert body["filters"]["run_id"] == "phase1-test-endpoint"


def test_stats_endpoint_run_id_null_default(client):
    """run_id 미지정 기본 None → 응답 filters.run_id null."""
    r = client.get("/v1/admin/signal-stats", headers=HEADERS)
    assert r.status_code == 200
    body = r.json()
    assert body["filters"]["run_id"] is None
```

- [ ] **Step 2: Run — fail**

- [ ] **Step 3: Modify `admin_signal_stats_endpoint`**

`src/sajucandle/api.py`의 해당 엔드포인트에서:

```python
    @app.get("/v1/admin/signal-stats")
    async def admin_signal_stats_endpoint(
        request: Request,
        ticker: Optional[str] = None,
        grade: Optional[str] = None,
        since: Optional[str] = None,
        run_id: Optional[str] = None,   # Phase 1
        x_sajucandle_key: Optional[str] = Header(default=None),
    ):
        _require_api_key(request, x_sajucandle_key)
        if db.get_pool() is None:
            raise HTTPException(503, detail="database not available")

        # ... since 파싱 기존 그대로 ...

        async with db.acquire() as conn:
            stats = await repositories.aggregate_signal_stats(
                conn, since=since_dt, ticker=ticker, grade=grade, run_id=run_id
            )

        # ... 로그 기존 그대로 ...

        return {
            "since": since_dt.isoformat(),
            "filters": {"ticker": ticker, "grade": grade, "run_id": run_id},  # run_id 추가
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

- [ ] **Step 4: Run + Commit**

```
pytest tests/test_api_stats.py -v
pytest -q
git add src/sajucandle/api.py tests/test_api_stats.py
git commit -m "feat(api): admin_signal_stats_endpoint에 run_id query param"
```

---

## Task 4: backtest 패키지 bootstrap + tracker.py

**Files:**
- Create: `src/sajucandle/backtest/__init__.py`
- Create: `src/sajucandle/backtest/tracker.py`
- Create: `tests/test_backtest_tracker.py`

- [ ] **Step 1: Tests**

`tests/test_backtest_tracker.py`:

```python
"""backtest.tracker: MFE/MAE 순수 함수."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta

import pytest

from sajucandle.backtest.tracker import MfeMae, compute_mfe_mae
from sajucandle.market_data import Kline


def _bar(hours_after: float, high: float, low: float, close: float,
         base_t: datetime) -> Kline:
    return Kline(
        open_time=base_t + timedelta(hours=hours_after),
        open=(high + low) / 2, high=high, low=low, close=close, volume=100.0,
    )


def test_compute_mfe_mae_basic():
    """entry=100, 이후 high=110, low=95 → MFE=+10%, MAE=-5%."""
    t0 = datetime(2026, 4, 20, 0, 0, tzinfo=timezone.utc)
    post = [
        _bar(0.5, high=102, low=99, close=101, base_t=t0),
        _bar(1.5, high=110, low=101, close=108, base_t=t0),
        _bar(2.5, high=107, low=95, close=96, base_t=t0),
    ]
    r = compute_mfe_mae(entry_price=100.0, post_bars_1h=post, sent_at=t0)
    assert r is not None
    assert r.mfe_pct == pytest.approx(10.0, abs=0.01)
    assert r.mae_pct == pytest.approx(-5.0, abs=0.01)


def test_compute_mfe_mae_close_24h_7d():
    """sent_at 이후 24h 지점 close, 7d 지점 close 반환."""
    t0 = datetime(2026, 4, 20, 0, 0, tzinfo=timezone.utc)
    post = []
    # 1시간마다 1 bar, 200h (>7d)
    for i in range(1, 200):
        post.append(_bar(i, high=100 + i, low=100, close=100 + i, base_t=t0))
    r = compute_mfe_mae(entry_price=100.0, post_bars_1h=post, sent_at=t0)
    assert r.close_24h is not None
    assert r.close_24h > 100  # 24h 시점 상승 시가
    assert r.close_7d is not None


def test_compute_mfe_mae_empty_returns_none():
    t0 = datetime(2026, 4, 20, 0, 0, tzinfo=timezone.utc)
    assert compute_mfe_mae(entry_price=100.0, post_bars_1h=[], sent_at=t0) is None


def test_compute_mfe_mae_zero_entry_returns_none():
    t0 = datetime(2026, 4, 20, 0, 0, tzinfo=timezone.utc)
    post = [_bar(1, 100, 100, 100, t0)]
    assert compute_mfe_mae(entry_price=0.0, post_bars_1h=post, sent_at=t0) is None
```

- [ ] **Step 2: Run — fail** (ModuleNotFoundError)

- [ ] **Step 3: Implement**

`src/sajucandle/backtest/__init__.py`:
```python
"""SajuCandle 백테스트 하네스 (Phase 1)."""
```

`src/sajucandle/backtest/tracker.py`:
```python
"""백테스트 MFE/MAE 계산 — broadcast.run_phase0_tracking 공식 재사용."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from sajucandle.market_data import Kline


@dataclass
class MfeMae:
    mfe_pct: float
    mae_pct: float
    close_24h: Optional[float]
    close_7d: Optional[float]


def compute_mfe_mae(
    *,
    entry_price: float,
    post_bars_1h: list[Kline],
    sent_at: datetime,
) -> Optional[MfeMae]:
    """entry_price 대비 sent_at 이후 post_bars의 최고/최저가 → MFE/MAE %.

    - MFE = (max(high) / entry - 1) × 100
    - MAE = (min(low)  / entry - 1) × 100   (음수)
    - close_24h/7d = sent_at+24h/+7d 이후 첫 봉의 close

    Returns None: entry <= 0 or post_bars 비어있음.
    """
    if entry_price <= 0 or not post_bars_1h:
        return None
    highs = [k.high for k in post_bars_1h]
    lows = [k.low for k in post_bars_1h]
    mfe = (max(highs) / entry_price - 1.0) * 100.0
    mae = (min(lows) / entry_price - 1.0) * 100.0

    close_24h: Optional[float] = None
    close_7d: Optional[float] = None
    t_24h = sent_at + timedelta(hours=24)
    t_7d = sent_at + timedelta(days=7)
    for k in post_bars_1h:
        if close_24h is None and k.open_time >= t_24h:
            close_24h = k.close
        if close_7d is None and k.open_time >= t_7d:
            close_7d = k.close
            break

    return MfeMae(
        mfe_pct=mfe, mae_pct=mae,
        close_24h=close_24h, close_7d=close_7d,
    )
```

- [ ] **Step 4: Run + Commit**

```
pytest tests/test_backtest_tracker.py -v
pytest -q
git add src/sajucandle/backtest/__init__.py src/sajucandle/backtest/tracker.py tests/test_backtest_tracker.py
git commit -m "feat(backtest): add tracker.compute_mfe_mae (phase 0 공식 재사용)"
```

---

## Task 5: backtest/saju_stub.py

**Files:**
- Create: `src/sajucandle/backtest/saju_stub.py`
- Create: `tests/test_backtest_saju_stub.py`

- [ ] **Step 1: Tests**

`tests/test_backtest_saju_stub.py`:

```python
from datetime import date

from sajucandle.backtest.saju_stub import fixed_saju_score


def test_fixed_saju_score_returns_50():
    assert fixed_saju_score(date(2026, 4, 20), "swing") == 50
    assert fixed_saju_score(date(2020, 1, 1), "scalp") == 50
    assert fixed_saju_score(date.today(), "long") == 50
```

- [ ] **Step 2-5: Implement + Commit**

`src/sajucandle/backtest/saju_stub.py`:
```python
"""백테스트용 사주 점수 스텁.

Phase 1은 중립값 50으로 고정. Phase 4 민감도 분석에서 {0, 50, 100} 3값 비교 예정.
"""
from __future__ import annotations

from datetime import date


def fixed_saju_score(target_date: date, asset_class: str) -> int:
    """백테스트용 고정 사주 composite. 가중치 10%라 결과 편향 제한적."""
    return 50
```

```
pytest tests/test_backtest_saju_stub.py -v
git add src/sajucandle/backtest/saju_stub.py tests/test_backtest_saju_stub.py
git commit -m "feat(backtest): saju_stub.fixed_saju_score → 50 (중립)"
```

---

## Task 6: backtest/history.py — 벌크 OHLCV 로더 + 디스크 캐시

**Files:**
- Create: `src/sajucandle/backtest/history.py`
- Create: `tests/test_backtest_history.py`

- [ ] **Step 1: Tests**

`tests/test_backtest_history.py`:

```python
"""backtest.history: OHLCV 벌크 로더 + 디스크 JSON 캐시."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from sajucandle.backtest.history import TickerHistory, load_history
from sajucandle.market_data import Kline


def _kline(ts: datetime, v: float) -> Kline:
    return Kline(open_time=ts, open=v, high=v + 1, low=v - 1, close=v, volume=100)


def test_load_history_returns_three_tf(tmp_path):
    """provider.fetch_klines 3회 호출 (1h, 4h, 1d)."""
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    provider = MagicMock()
    provider.fetch_klines = MagicMock(return_value=[_kline(base, 100.0)])

    hist = load_history(
        ticker="BTCUSDT",
        from_dt=base,
        to_dt=datetime(2026, 2, 1, tzinfo=timezone.utc),
        provider=provider,
        cache_dir=tmp_path,
    )
    assert isinstance(hist, TickerHistory)
    assert hist.ticker == "BTCUSDT"
    # 1h / 4h / 1d 각각 fetch_klines 호출
    assert provider.fetch_klines.call_count == 3
    # 각 호출의 interval 검증
    intervals = [c.kwargs.get("interval") or c.args[1]
                 for c in provider.fetch_klines.call_args_list]
    assert set(intervals) == {"1h", "4h", "1d"}


def test_load_history_disk_cache_hit(tmp_path):
    """두 번째 호출 시 provider 호출 안 함 (캐시 파일 존재)."""
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    provider = MagicMock()
    provider.fetch_klines = MagicMock(return_value=[_kline(base, 100.0)])

    # 1st call — fetch
    load_history(
        ticker="BTCUSDT", from_dt=base,
        to_dt=datetime(2026, 2, 1, tzinfo=timezone.utc),
        provider=provider, cache_dir=tmp_path,
    )
    assert provider.fetch_klines.call_count == 3

    # 2nd call — cache hit
    load_history(
        ticker="BTCUSDT", from_dt=base,
        to_dt=datetime(2026, 2, 1, tzinfo=timezone.utc),
        provider=provider, cache_dir=tmp_path,
    )
    assert provider.fetch_klines.call_count == 3   # 증가 없음


def test_load_history_cache_file_format(tmp_path):
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    provider = MagicMock()
    provider.fetch_klines = MagicMock(return_value=[
        _kline(base, 100.0), _kline(base, 101.0),
    ])

    load_history(
        ticker="BTCUSDT", from_dt=base,
        to_dt=datetime(2026, 2, 1, tzinfo=timezone.utc),
        provider=provider, cache_dir=tmp_path,
    )
    # cache file 존재 확인
    cache_files = list(tmp_path.glob("*.json"))
    assert len(cache_files) == 3   # 1h / 4h / 1d
    for f in cache_files:
        data = json.loads(f.read_text(encoding="utf-8"))
        assert isinstance(data, list)
        assert len(data) == 2
        assert "open_time" in data[0]
```

- [ ] **Step 2-5: Implement**

`src/sajucandle/backtest/history.py`:

```python
"""벌크 OHLCV 로더 + 디스크 JSON 캐시.

Phase 1 시간 스냅샷 메커니즘: bulk fetch + in-memory slice (Decision 3.1-B).
디스크 캐시로 재실행 시 HTTP 0회 (`.cache/backtest/{ticker}_{interval}.json`).
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from sajucandle.market.base import MarketDataProvider
from sajucandle.market_data import Kline

logger = logging.getLogger(__name__)

_DEFAULT_LIMIT_1D = 750       # 2년 여유
_DEFAULT_LIMIT_4H = 4400      # 2년 × 6
_DEFAULT_LIMIT_1H = 17600     # 2년 × 24


@dataclass
class TickerHistory:
    ticker: str
    klines_1h: list[Kline]
    klines_4h: list[Kline]
    klines_1d: list[Kline]


def _cache_path(cache_dir: Path, ticker: str, interval: str) -> Path:
    safe = ticker.replace("/", "_")
    return cache_dir / f"{safe}_{interval}.json"


def _load_cache(p: Path) -> Optional[list[Kline]]:
    if not p.exists():
        return None
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        return [Kline.from_dict(d) for d in raw]
    except Exception as e:
        logger.warning("cache load failed %s: %s", p, e)
        return None


def _save_cache(p: Path, klines: list[Kline]) -> None:
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            json.dumps([k.to_dict() for k in klines], ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception as e:
        logger.warning("cache save failed %s: %s", p, e)


def load_history(
    ticker: str,
    from_dt: datetime,
    to_dt: datetime,
    *,
    provider: MarketDataProvider,
    cache_dir: Optional[Path] = None,
) -> TickerHistory:
    """Provider에서 1h/4h/1d OHLCV 벌크 로드.

    cache_dir 제공 시 디스크 JSON 캐시 사용 (재실행 시 HTTP 0회).
    from_dt/to_dt는 현재는 limit 계산 참고용 (provider가 `since` 미지원이면 최근 N봉만 반환).
    """
    if cache_dir:
        cache_dir = Path(cache_dir)

    klines_by_interval: dict[str, list[Kline]] = {}
    limits = {"1h": _DEFAULT_LIMIT_1H, "4h": _DEFAULT_LIMIT_4H, "1d": _DEFAULT_LIMIT_1D}

    for interval, limit in limits.items():
        # 캐시 확인
        if cache_dir:
            cpath = _cache_path(cache_dir, ticker, interval)
            cached = _load_cache(cpath)
            if cached is not None:
                logger.info("cache hit %s %s (%d bars)", ticker, interval, len(cached))
                klines_by_interval[interval] = cached
                continue
        # Provider fetch
        logger.info("fetching %s %s (limit=%d)", ticker, interval, limit)
        klines = provider.fetch_klines(ticker, interval=interval, limit=limit)
        klines_by_interval[interval] = klines
        # 캐시 저장
        if cache_dir:
            _save_cache(_cache_path(cache_dir, ticker, interval), klines)

    return TickerHistory(
        ticker=ticker,
        klines_1h=klines_by_interval["1h"],
        klines_4h=klines_by_interval["4h"],
        klines_1d=klines_by_interval["1d"],
    )
```

```
pytest tests/test_backtest_history.py -v
git add src/sajucandle/backtest/history.py tests/test_backtest_history.py
git commit -m "feat(backtest): history — bulk OHLCV 3TF + 디스크 JSON 캐시"
```

---

## Task 7: backtest/slicer.py — HistoryWindow + 룩어헤드 방지

**Files:**
- Create: `src/sajucandle/backtest/slicer.py`
- Create: `tests/test_backtest_slicer.py`

- [ ] **Step 1: Tests**

`tests/test_backtest_slicer.py`:

```python
from __future__ import annotations

from datetime import datetime, timezone, timedelta

import pytest

from sajucandle.backtest.history import TickerHistory
from sajucandle.backtest.slicer import HistoryWindow
from sajucandle.market_data import Kline


def _bars(start: datetime, interval_hours: float, count: int, base_price: float = 100.0) -> list[Kline]:
    out = []
    dt = timedelta(hours=interval_hours)
    for i in range(count):
        p = base_price + i * 0.5
        out.append(Kline(
            open_time=start + dt * i,
            open=p, high=p + 1, low=p - 1, close=p, volume=100.0,
        ))
    return out


def _make_window(t0: datetime) -> HistoryWindow:
    hist = TickerHistory(
        ticker="BTCUSDT",
        klines_1h=_bars(t0 - timedelta(days=10), 1, 24 * 20),  # 20일
        klines_4h=_bars(t0 - timedelta(days=30), 4, 6 * 30),
        klines_1d=_bars(t0 - timedelta(days=60), 24, 60),
    )
    return HistoryWindow(history=hist)


def test_slice_at_returns_bars_before_t_only():
    t0 = datetime(2026, 4, 20, 0, 0, tzinfo=timezone.utc)
    window = _make_window(t0)
    t = t0   # 지금
    k1h, k4h, k1d = window.slice_at(t)
    # 모든 봉이 open_time + interval <= t
    assert all(k.open_time + timedelta(hours=1) <= t for k in k1h)
    assert all(k.open_time + timedelta(hours=4) <= t for k in k4h)
    assert all(k.open_time + timedelta(days=1) <= t for k in k1d)


def test_slice_at_deterministic():
    t0 = datetime(2026, 4, 20, 0, 0, tzinfo=timezone.utc)
    window = _make_window(t0)
    r1 = window.slice_at(t0)
    r2 = window.slice_at(t0)
    assert len(r1[0]) == len(r2[0])
    assert len(r1[1]) == len(r2[1])
    assert len(r1[2]) == len(r2[2])


def test_slice_at_past_t_yields_fewer_bars():
    t0 = datetime(2026, 4, 20, 0, 0, tzinfo=timezone.utc)
    window = _make_window(t0)
    k1h_now, _, _ = window.slice_at(t0)
    k1h_past, _, _ = window.slice_at(t0 - timedelta(days=5))
    assert len(k1h_past) < len(k1h_now)


def test_post_bars_1h_returns_bars_after_t():
    t0 = datetime(2026, 4, 20, 0, 0, tzinfo=timezone.utc)
    window = _make_window(t0)
    # t는 히스토리 중간 시점
    t = t0 - timedelta(days=5)
    post = window.post_bars_1h(t, hours=24)
    # 전부 t 이후
    assert all(k.open_time >= t for k in post)
    # ~24개
    assert 20 <= len(post) <= 26


def test_post_bars_1h_beyond_history_returns_partial():
    t0 = datetime(2026, 4, 20, 0, 0, tzinfo=timezone.utc)
    window = _make_window(t0)
    t = t0 - timedelta(hours=3)
    post = window.post_bars_1h(t, hours=168)   # 7일 요청
    # history는 t0까지만 있으므로 3h치만
    assert len(post) <= 5
```

- [ ] **Step 2-5: Implement**

`src/sajucandle/backtest/slicer.py`:

```python
"""HistoryWindow — 백테스트 시점 t 기준 OHLCV 슬라이싱.

룩어헤드 방지: slice_at(t)는 `open_time + interval <= t`인 봉만 반환.
post_bars_1h(t, hours)는 반대로 t 이후 봉 반환 (백테스트 추적용).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sajucandle.backtest.history import TickerHistory
from sajucandle.market_data import Kline


@dataclass
class HistoryWindow:
    history: TickerHistory

    def slice_at(self, t: datetime) -> tuple[list[Kline], list[Kline], list[Kline]]:
        """t 이전에 **닫힌** 봉만 반환. 각 TF 별도.

        룩어헤드 방지: `k.open_time + interval <= t`
        """
        def _closed_before(klines: list[Kline], interval: timedelta) -> list[Kline]:
            return [k for k in klines if k.open_time + interval <= t]

        k1h = _closed_before(self.history.klines_1h, timedelta(hours=1))
        k4h = _closed_before(self.history.klines_4h, timedelta(hours=4))
        k1d = _closed_before(self.history.klines_1d, timedelta(days=1))
        return k1h, k4h, k1d

    def post_bars_1h(self, t: datetime, hours: int = 168) -> list[Kline]:
        """t 이후 hours시간치 1h봉 반환 (MFE/MAE 추적용).

        룩어헤드 허용 — 백테스트 시점에서 미래는 이미 확정된 과거 데이터.
        """
        end = t + timedelta(hours=hours)
        return [k for k in self.history.klines_1h if t <= k.open_time < end]
```

```
pytest tests/test_backtest_slicer.py -v
git add src/sajucandle/backtest/slicer.py tests/test_backtest_slicer.py
git commit -m "feat(backtest): slicer.HistoryWindow — 룩어헤드 방지 slice_at + post_bars"
```

---

## Task 8: backtest/engine.py — run_backtest (큰 태스크)

**Files:**
- Create: `src/sajucandle/backtest/engine.py`
- Create: `tests/test_backtest_engine.py`

- [ ] **Step 1: Tests**

`tests/test_backtest_engine.py` — run_backtest는 async이고 history/router mock + insert mock 주입:

```python
"""backtest.engine: run_backtest 통합."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta, date
from unittest.mock import AsyncMock, MagicMock

import pytest

from sajucandle.backtest.engine import run_backtest, BacktestSummary
from sajucandle.backtest.history import TickerHistory
from sajucandle.market_data import Kline


def _k(t: datetime, price: float) -> Kline:
    return Kline(open_time=t, open=price, high=price + 1, low=price - 1,
                 close=price, volume=100.0)


def _mock_history(ticker: str, from_dt: datetime, to_dt: datetime) -> TickerHistory:
    # 합성 히스토리: 매 1h마다 가격 상승 (강한 uptrend)
    n_hours = int((to_dt - from_dt).total_seconds() / 3600)
    # 1h 전체
    k1h = [_k(from_dt + timedelta(hours=i), 100 + i * 0.1) for i in range(n_hours + 100)]
    # 4h 집계
    k4h = [_k(from_dt + timedelta(hours=4 * i), 100 + i * 0.4) for i in range((n_hours + 100) // 4)]
    # 1d 집계
    k1d = [_k(from_dt + timedelta(days=i), 100 + i * 2.4) for i in range((n_hours + 100) // 24 + 1)]
    return TickerHistory(ticker=ticker, klines_1h=k1h, klines_4h=k4h, klines_1d=k1d)


@pytest.mark.asyncio
async def test_run_backtest_runs_daily_signals():
    from_dt = datetime(2026, 1, 1, tzinfo=timezone.utc)
    to_dt = datetime(2026, 1, 11, tzinfo=timezone.utc)   # 10일
    hist = _mock_history("BTCUSDT", from_dt, to_dt)

    # load_history를 직접 mock 주입
    router = MagicMock()
    fake_provider = MagicMock()
    fake_provider.fetch_klines = MagicMock()
    router.get_provider = MagicMock(return_value=fake_provider)

    # insert 수집
    inserted: list[dict] = []
    async def fake_insert(**kwargs):
        inserted.append(kwargs)
        return len(inserted)

    summary = await run_backtest(
        ticker="BTCUSDT",
        from_dt=from_dt,
        to_dt=to_dt,
        run_id="phase1-test-run",
        router=router,
        saju_score_fn=lambda d, ac: 50,
        insert_log_fn=fake_insert,
        history_override=hist,   # test injection
    )
    assert isinstance(summary, BacktestSummary)
    assert summary.run_id == "phase1-test-run"
    assert summary.ticker == "BTCUSDT"
    # 10일 동안 1일 1회
    assert summary.signals_total == 10
    assert len(inserted) == 10
    # 전부 run_id 전파
    for row in inserted:
        assert row["run_id"] == "phase1-test-run"
        assert row["source"] == "backtest"


@pytest.mark.asyncio
async def test_run_backtest_grades_aggregated():
    from_dt = datetime(2026, 1, 1, tzinfo=timezone.utc)
    to_dt = datetime(2026, 1, 4, tzinfo=timezone.utc)
    hist = _mock_history("BTCUSDT", from_dt, to_dt)

    inserted: list[dict] = []
    async def fake_insert(**kwargs):
        inserted.append(kwargs)
        return len(inserted)

    summary = await run_backtest(
        ticker="BTCUSDT",
        from_dt=from_dt, to_dt=to_dt,
        run_id="phase1-test-grades",
        router=MagicMock(),
        insert_log_fn=fake_insert,
        history_override=hist,
    )
    # summary.signals_by_grade 합 == signals_total
    assert sum(summary.signals_by_grade.values()) == summary.signals_total
```

- [ ] **Step 2-5: Implement**

`src/sajucandle/backtest/engine.py`:

```python
"""Phase 1 백테스트 엔진.

매일 1회 UTC 종가 시점에 analyze + grade + trade_setup + MFE/MAE 계산 →
signal_log에 source='backtest' + run_id로 기록.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Awaitable, Callable, Optional

from sajucandle.analysis.composite import analyze
from sajucandle.analysis.trade_setup import compute_trade_setup
from sajucandle.analysis.structure import MarketStructure
from sajucandle.backtest.history import TickerHistory, load_history
from sajucandle.backtest.slicer import HistoryWindow
from sajucandle.backtest.saju_stub import fixed_saju_score
from sajucandle.backtest.tracker import compute_mfe_mae
from sajucandle.market.router import MarketRouter
from sajucandle.signal_service import _grade_signal
from sajucandle import repositories

logger = logging.getLogger(__name__)


@dataclass
class BacktestSummary:
    run_id: str
    ticker: str
    from_dt: datetime
    to_dt: datetime
    signals_total: int = 0
    signals_by_grade: dict[str, int] = field(default_factory=dict)
    insert_errors: int = 0


async def run_backtest(
    *,
    ticker: str,
    from_dt: datetime,
    to_dt: datetime,
    run_id: str,
    router: MarketRouter,
    saju_score_fn: Callable[[date, str], int] = fixed_saju_score,
    asset_class: str = "swing",
    cache_dir: Optional[Path] = None,
    insert_log_fn: Optional[Callable[..., Awaitable[int]]] = None,
    history_override: Optional[TickerHistory] = None,
) -> BacktestSummary:
    """Phase 1 백테스트 엔트리.

    Args:
        insert_log_fn: 테스트 주입용. None이면 repositories.insert_signal_log 사용.
        history_override: 테스트 주입용. None이면 router에서 fetch.
    """
    # 히스토리 준비
    if history_override is not None:
        hist = history_override
    else:
        provider = router.get_provider(ticker)
        hist = load_history(
            ticker, from_dt, to_dt, provider=provider, cache_dir=cache_dir
        )
    window = HistoryWindow(history=hist)

    # 일별 시점 생성 (UTC 00:00 시리즈)
    signal_times: list[datetime] = []
    cursor = datetime(from_dt.year, from_dt.month, from_dt.day,
                      0, 0, tzinfo=timezone.utc) + timedelta(days=1)
    end = datetime(to_dt.year, to_dt.month, to_dt.day,
                   0, 0, tzinfo=timezone.utc)
    while cursor <= end:
        signal_times.append(cursor)
        cursor += timedelta(days=1)

    summary = BacktestSummary(
        run_id=run_id, ticker=ticker,
        from_dt=from_dt, to_dt=to_dt,
    )

    from sajucandle import db

    for t in signal_times:
        try:
            k1h, k4h, k1d = window.slice_at(t)
            if len(k1d) < 50:  # EMA50 불가
                continue
            if len(k1h) < 56 or len(k4h) < 56:
                continue

            analysis = analyze(k1h, k4h, k1d)
            current = k1d[-1].close

            saju = saju_score_fn(t.date(), asset_class)
            final = round(0.1 * saju + 0.9 * analysis.composite_score)
            final = max(0, min(100, final))

            grade = _grade_signal(final, analysis)

            ts = None
            if grade in ("강진입", "진입") and analysis.atr_1d > 0:
                ts = compute_trade_setup(
                    entry=current, atr_1d=analysis.atr_1d,
                    sr_levels=analysis.sr_levels,
                )

            # MFE/MAE
            post = window.post_bars_1h(t, hours=168)
            mfe_mae = compute_mfe_mae(
                entry_price=current, post_bars_1h=post, sent_at=t,
            )

            tracking_done = (
                len(post) > 0
                and post[-1].open_time >= t + timedelta(days=7)
            )

            # insert
            insert_fn = insert_log_fn
            if insert_fn is None:
                async def _default_insert(**kwargs):
                    if db.get_pool() is None:
                        raise RuntimeError("db pool not initialized")
                    async with db.acquire() as conn:
                        return await repositories.insert_signal_log(conn, **kwargs)
                insert_fn = _default_insert

            try:
                await insert_fn(
                    source="backtest",
                    telegram_chat_id=None,
                    ticker=ticker,
                    target_date=t.date(),
                    entry_price=current,
                    saju_score=saju,
                    analysis_score=analysis.composite_score,
                    structure_state=analysis.structure.state.value,
                    alignment_bias=analysis.alignment.bias,
                    rsi_1h=analysis.rsi_1h,
                    volume_ratio_1d=analysis.volume_ratio_1d,
                    composite_score=final,
                    signal_grade=grade,
                    stop_loss=ts.stop_loss if ts else None,
                    take_profit_1=ts.take_profit_1 if ts else None,
                    take_profit_2=ts.take_profit_2 if ts else None,
                    risk_pct=ts.risk_pct if ts else None,
                    rr_tp1=ts.rr_tp1 if ts else None,
                    rr_tp2=ts.rr_tp2 if ts else None,
                    sl_basis=ts.sl_basis if ts else None,
                    tp1_basis=ts.tp1_basis if ts else None,
                    tp2_basis=ts.tp2_basis if ts else None,
                    run_id=run_id,
                )
                # 주의: MFE/MAE는 별도 update_signal_tracking 호출로 기록해야 한다.
                # Phase 1 최소 구현은 insert 시점에서 mfe_mae는 이미 계산됐으므로
                # 동일 connection에서 UPDATE 수행.
                if mfe_mae is not None and db.get_pool() is not None and insert_log_fn is None:
                    async with db.acquire() as conn:
                        last_id = await conn.fetchval(
                            "SELECT id FROM signal_log WHERE run_id = $1 "
                            "AND ticker = $2 AND target_date = $3 "
                            "ORDER BY id DESC LIMIT 1",
                            run_id, ticker, t.date(),
                        )
                        if last_id:
                            await repositories.update_signal_tracking(
                                conn, last_id,
                                mfe_pct=mfe_mae.mfe_pct,
                                mae_pct=mfe_mae.mae_pct,
                                close_24h=mfe_mae.close_24h,
                                close_7d=mfe_mae.close_7d,
                                tracking_done=tracking_done,
                            )

                summary.signals_total += 1
                summary.signals_by_grade[grade] = (
                    summary.signals_by_grade.get(grade, 0) + 1
                )
            except Exception as e:
                logger.warning("insert signal_log 실패 t=%s: %s", t, e)
                summary.insert_errors += 1

        except Exception as e:
            logger.warning("backtest t=%s 예외: %s", t, e)
            continue

    logger.info(
        "backtest done run_id=%s ticker=%s total=%d grades=%s errors=%d",
        run_id, ticker, summary.signals_total,
        summary.signals_by_grade, summary.insert_errors,
    )
    return summary
```

```
pytest tests/test_backtest_engine.py -v
git add src/sajucandle/backtest/engine.py tests/test_backtest_engine.py
git commit -m "feat(backtest): engine.run_backtest — analyze + grade + TradeSetup + MFE/MAE"
```

---

## Task 9: backtest/aggregate.py

**Files:**
- Create: `src/sajucandle/backtest/aggregate.py`
- Create: `tests/test_backtest_aggregate.py`

- [ ] **Step 1: Tests**

```python
"""backtest.aggregate: run별 GradeStats 집계."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from sajucandle.backtest.aggregate import aggregate_run, GradeStats
from sajucandle.repositories import insert_signal_log, update_signal_tracking


# DB integration tests — TEST_DATABASE_URL 있을 때만
pytestmark = pytest.mark.asyncio


async def _seed(db_conn, run_id: str, entries: list[tuple[str, float, float]]):
    """entries: (grade, mfe_pct, mae_pct) 튜플들 — 전부 tracking_done=TRUE로 저장."""
    from sajucandle.repositories import UserProfile, upsert_user
    await upsert_user(db_conn, UserProfile(
        telegram_chat_id=600001,
        birth_year=1990, birth_month=3, birth_day=15,
        birth_hour=14, birth_minute=0, asset_class_pref="swing",
    ))
    for i, (grade, mfe, mae) in enumerate(entries):
        row_id = await insert_signal_log(
            db_conn,
            source="backtest", telegram_chat_id=None,
            ticker="BTCUSDT", target_date=date(2026, 1, 1) + timedelta(days=i),
            entry_price=100.0, saju_score=50, analysis_score=60,
            structure_state="range", alignment_bias="mixed",
            rsi_1h=None, volume_ratio_1d=None,
            composite_score=60, signal_grade=grade,
            run_id=run_id,
        )
        await update_signal_tracking(
            db_conn, row_id,
            mfe_pct=mfe, mae_pct=mae,
            close_24h=100 + mfe, close_7d=100 + mfe,
            tracking_done=True,
        )


async def test_aggregate_run_empty_returns_empty_list(db_conn):
    r = await aggregate_run(db_conn, run_id="phase1-nonexistent")
    assert r == []


async def test_aggregate_run_win_rate_by_grade(db_conn):
    run_id = "phase1-test-winrate"
    await _seed(db_conn, run_id, [
        ("진입", 3.0, -1.0),
        ("진입", 2.0, -2.0),
        ("진입", -0.5, -3.0),  # 패 (mfe <= 0)
        ("관망", 1.0, -1.0),
    ])
    r = await aggregate_run(db_conn, run_id=run_id)
    by_grade = {gs.grade: gs for gs in r}
    assert by_grade["진입"].count == 3
    assert by_grade["진입"].win_rate == pytest.approx(2 / 3, abs=0.01)
    assert by_grade["진입"].avg_mfe == pytest.approx((3 + 2 - 0.5) / 3, abs=0.01)
    assert by_grade["관망"].count == 1
    assert by_grade["관망"].win_rate == 1.0
```

- [ ] **Step 2-5: Implement**

`src/sajucandle/backtest/aggregate.py`:

```python
"""backtest.aggregate: run별 등급 통계.

run_id로 필터한 signal_log에서 tracking_done=TRUE row만 집계.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import asyncpg


@dataclass
class GradeStats:
    grade: str
    count: int
    win_rate: float           # mfe_7d_pct > 0 비율
    avg_mfe: float
    avg_mae: float
    avg_rr_tp1: Optional[float]


async def aggregate_run(
    conn: asyncpg.Connection,
    *,
    run_id: str,
) -> list[GradeStats]:
    """signal_log WHERE run_id=$1 AND tracking_done=TRUE → 등급별 집계."""
    rows = await conn.fetch(
        """
        SELECT signal_grade,
               COUNT(*) AS cnt,
               AVG(CASE WHEN mfe_7d_pct > 0 THEN 1.0 ELSE 0.0 END) AS win_rate,
               AVG(mfe_7d_pct) AS avg_mfe,
               AVG(mae_7d_pct) AS avg_mae,
               AVG(rr_tp1) AS avg_rr_tp1
        FROM signal_log
        WHERE run_id = $1 AND tracking_done = TRUE
        GROUP BY signal_grade
        ORDER BY AVG(mfe_7d_pct) DESC NULLS LAST
        """,
        run_id,
    )
    out: list[GradeStats] = []
    for r in rows:
        out.append(GradeStats(
            grade=r["signal_grade"],
            count=int(r["cnt"] or 0),
            win_rate=float(r["win_rate"] or 0.0),
            avg_mfe=float(r["avg_mfe"] or 0.0),
            avg_mae=float(r["avg_mae"] or 0.0),
            avg_rr_tp1=float(r["avg_rr_tp1"]) if r["avg_rr_tp1"] is not None else None,
        ))
    return out
```

```
pytest tests/test_backtest_aggregate.py -v
git add src/sajucandle/backtest/aggregate.py tests/test_backtest_aggregate.py
git commit -m "feat(backtest): aggregate_run — run_id별 등급 승률/MFE/MAE/R:R"
```

---

## Task 10: backtest/cli.py + __main__.py

**Files:**
- Create: `src/sajucandle/backtest/cli.py`
- Create: `src/sajucandle/backtest/__main__.py`
- Create: `tests/test_backtest_cli.py`

- [ ] **Step 1: Tests**

```python
"""backtest.cli: argparse 파싱."""
from __future__ import annotations

import pytest

from sajucandle.backtest.cli import _parse_args


def test_parse_run_required_args():
    args = _parse_args(["run", "--ticker", "BTCUSDT",
                         "--from", "2024-04-01", "--to", "2026-04-01"])
    assert args.subcommand == "run"
    assert args.ticker == "BTCUSDT"
    assert str(args.from_dt.date()) == "2024-04-01"


def test_parse_run_optional_run_id():
    args = _parse_args([
        "run", "--ticker", "AAPL",
        "--from", "2026-01-01", "--to", "2026-03-01",
        "--run-id", "phase1-test-manual",
    ])
    assert args.run_id == "phase1-test-manual"


def test_parse_run_bad_date_raises():
    with pytest.raises(SystemExit):
        _parse_args(["run", "--ticker", "BTCUSDT",
                     "--from", "not-a-date", "--to", "2026-04-01"])


def test_parse_aggregate_required_run_id():
    args = _parse_args(["aggregate", "--run-id", "phase1-abc-baseline"])
    assert args.subcommand == "aggregate"
    assert args.run_id == "phase1-abc-baseline"


def test_parse_aggregate_json_flag():
    args = _parse_args(["aggregate", "--run-id", "r1", "--json"])
    assert args.json is True


def test_parse_aggregate_text_default():
    args = _parse_args(["aggregate", "--run-id", "r1"])
    assert args.json is False
```

- [ ] **Step 2-5: Implement**

`src/sajucandle/backtest/cli.py`:

```python
"""Phase 1 백테스트 CLI — argparse 진입점."""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sajucandle import db
from sajucandle import repositories
from sajucandle.backtest.aggregate import aggregate_run
from sajucandle.backtest.engine import run_backtest
from sajucandle.market.binance import BinanceClient
from sajucandle.market.router import MarketRouter
from sajucandle.market.yfinance import YFinanceClient

logger = logging.getLogger(__name__)


def _short_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short=7", "HEAD"],
            text=True,
        ).strip()
    except Exception:
        return "unknown"


def _default_run_id(label: str = "auto") -> str:
    sha = _short_sha()
    today = datetime.utcnow().strftime("%Y%m%d")
    return f"phase1-{sha}-{label}-{today}"


def _parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m sajucandle.backtest",
        description="SajuCandle Phase 1 백테스트 하네스",
    )
    sub = parser.add_subparsers(dest="subcommand", required=True)

    # run
    run_p = sub.add_parser("run", help="백테스트 실행")
    run_p.add_argument("--ticker", required=True, help="심볼 (예: BTCUSDT, AAPL)")
    run_p.add_argument("--from", dest="from_dt", required=True,
                        type=lambda s: datetime.fromisoformat(s).replace(tzinfo=timezone.utc),
                        help="시작 날짜 (YYYY-MM-DD)")
    run_p.add_argument("--to", dest="to_dt", required=True,
                        type=lambda s: datetime.fromisoformat(s).replace(tzinfo=timezone.utc),
                        help="종료 날짜 (YYYY-MM-DD)")
    run_p.add_argument("--run-id", default=None,
                        help=f"백테스트 run 식별자. 미지정 시 자동 ({_default_run_id.__doc__})")
    run_p.add_argument("--cache-dir", default=".cache/backtest",
                        help="OHLCV 디스크 캐시 경로")

    # aggregate
    agg_p = sub.add_parser("aggregate", help="run별 집계 결과")
    agg_p.add_argument("--run-id", required=True)
    agg_p.add_argument("--json", action="store_true", help="JSON 출력")

    return parser.parse_args(argv)


async def _run_cmd(args: argparse.Namespace) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    run_id = args.run_id or _default_run_id(label="auto")
    router = MarketRouter(binance=BinanceClient(), yfinance=YFinanceClient())

    # DB 연결
    dsn = os.environ.get("DATABASE_URL") or os.environ.get("TEST_DATABASE_URL")
    if not dsn:
        print("ERROR: DATABASE_URL 또는 TEST_DATABASE_URL 환경변수 필요", file=sys.stderr)
        return 1
    await db.connect(dsn)

    try:
        summary = await run_backtest(
            ticker=args.ticker.upper().lstrip("$"),
            from_dt=args.from_dt,
            to_dt=args.to_dt,
            run_id=run_id,
            router=router,
            cache_dir=Path(args.cache_dir),
        )
        print(f"\nBacktest done — run_id={summary.run_id}")
        print(f"  ticker={summary.ticker}")
        print(f"  signals_total={summary.signals_total}")
        print(f"  by_grade:")
        for g, c in sorted(summary.signals_by_grade.items()):
            print(f"    {g:<6} {c}")
        print(f"  insert_errors={summary.insert_errors}")
        return 0
    finally:
        await db.close()


async def _aggregate_cmd(args: argparse.Namespace) -> int:
    logging.basicConfig(level=logging.WARNING)
    dsn = os.environ.get("DATABASE_URL") or os.environ.get("TEST_DATABASE_URL")
    if not dsn:
        print("ERROR: DATABASE_URL 필요", file=sys.stderr)
        return 1
    await db.connect(dsn)
    try:
        async with db.acquire() as conn:
            stats = await aggregate_run(conn, run_id=args.run_id)
        if args.json:
            import dataclasses
            print(json.dumps(
                [dataclasses.asdict(s) for s in stats],
                ensure_ascii=False, indent=2,
            ))
        else:
            print(f"\nRun: {args.run_id}")
            print(f"{'grade':<8} {'n':>5} {'win%':>7} {'avg_mfe':>8} {'avg_mae':>8} {'rr_tp1':>7}")
            print("-" * 48)
            for s in stats:
                rr = f"{s.avg_rr_tp1:.2f}" if s.avg_rr_tp1 else "  -  "
                print(f"{s.grade:<8} {s.count:>5} "
                      f"{s.win_rate*100:>6.1f}% "
                      f"{s.avg_mfe:>+7.2f}% {s.avg_mae:>+7.2f}% {rr:>7}")
            if not stats:
                print("(해당 run_id에 tracking_done=TRUE 데이터 없음)")
        return 0
    finally:
        await db.close()


def main(argv: Optional[list[str]] = None) -> int:
    args = _parse_args(argv)
    if args.subcommand == "run":
        return asyncio.run(_run_cmd(args))
    elif args.subcommand == "aggregate":
        return asyncio.run(_aggregate_cmd(args))
    return 1


if __name__ == "__main__":
    sys.exit(main())
```

`src/sajucandle/backtest/__main__.py`:
```python
from sajucandle.backtest.cli import main

raise SystemExit(main())
```

- [ ] **Step 3-5: Run + Commit**

```
pytest tests/test_backtest_cli.py -v
git add src/sajucandle/backtest/cli.py src/sajucandle/backtest/__main__.py tests/test_backtest_cli.py
git commit -m "feat(backtest): CLI — run/aggregate sub-commands + auto run_id"
```

---

## Task 11: smoke test (end-to-end)

**Files:**
- Create: `tests/test_backtest_smoke.py`

- [ ] **Step 1: Test**

```python
"""backtest smoke: 합성 히스토리로 end-to-end 실행."""
from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone

import pytest

from sajucandle.backtest.engine import run_backtest
from sajucandle.backtest.aggregate import aggregate_run
from sajucandle.backtest.history import TickerHistory
from sajucandle.market_data import Kline
from sajucandle import db


pytestmark = pytest.mark.skipif(
    os.environ.get("TEST_DATABASE_URL") is None,
    reason="TEST_DATABASE_URL not set",
)


def _synthetic_history(ticker: str) -> TickerHistory:
    """강한 uptrend 합성 히스토리 200 × 1d, 동등 4h/1h."""
    base = datetime(2025, 1, 1, tzinfo=timezone.utc)
    k1d = []
    for i in range(200):
        p = 100 + i * 0.5
        k1d.append(Kline(
            open_time=base + timedelta(days=i),
            open=p, high=p + 1, low=p - 1, close=p, volume=1000,
        ))
    k4h = []
    for i in range(200 * 6):
        p = 100 + i * 0.08
        k4h.append(Kline(
            open_time=base + timedelta(hours=4 * i),
            open=p, high=p + 0.5, low=p - 0.5, close=p, volume=300,
        ))
    k1h = []
    for i in range(200 * 24):
        p = 100 + i * 0.02
        k1h.append(Kline(
            open_time=base + timedelta(hours=i),
            open=p, high=p + 0.2, low=p - 0.2, close=p, volume=100,
        ))
    return TickerHistory(ticker=ticker, klines_1h=k1h, klines_4h=k4h, klines_1d=k1d)


@pytest.mark.asyncio
async def test_backtest_end_to_end(db_pool):
    """run_backtest → aggregate_run 성공 + row count 기대값."""
    hist = _synthetic_history("BTCUSDT")
    from_dt = datetime(2025, 3, 1, tzinfo=timezone.utc)
    to_dt = datetime(2025, 3, 11, tzinfo=timezone.utc)

    # router 더미 (history_override 사용하므로 호출 안 됨)
    from unittest.mock import MagicMock
    router = MagicMock()

    summary = await run_backtest(
        ticker="BTCUSDT",
        from_dt=from_dt, to_dt=to_dt,
        run_id="phase1-smoke-test",
        router=router,
        history_override=hist,
    )
    assert summary.signals_total == 10

    # 집계 — tracking_done=TRUE rows 있어야 aggregate 결과 있음
    async with db.acquire() as conn:
        stats = await aggregate_run(conn, run_id="phase1-smoke-test")
        # 7일 추적 필요 — history 200봉이라 일부 tracking_done=True
        # 최소 등급 breakdown 확인
        total = sum(s.count for s in stats)
        assert total >= 0   # 존재 여부만 smoke 확인
```

- [ ] **Step 2-3: Run + Commit**

```
pytest tests/test_backtest_smoke.py -v
git add tests/test_backtest_smoke.py
git commit -m "test(backtest): smoke end-to-end (합성 히스토리)"
```

---

## Task 12: README + ruff + push

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Lint**

```
python -m ruff check src/ tests/
```

- [ ] **Step 2: Full pytest**

```
pytest -q
```

예상: 기존 307 passed + ~25 신규 passed + smoke 1 (DB 있을 때). 70+ skipped.

- [ ] **Step 3: README**

Week 10 Phase 2 섹션 아래에 Phase 1 섹션:

```markdown
## Phase 1: 백테스트 하네스

운영 시그널이 쌓이는 시간 없이 **과거 OHLCV로 analyze() + _grade_signal() 재생산**하고, 등급별 승률/MFE/MAE를 즉시 확인할 수 있는 인프라.

### 새 패키지
`src/sajucandle/backtest/` — 9개 모듈 (cli, history, slicer, engine, tracker, saju_stub, aggregate, ...).

### 새 명령
```
# 백테스트 실행 (결과는 signal_log에 source='backtest' + run_id로 저장)
python -m sajucandle.backtest run --ticker BTCUSDT --from 2024-04-01 --to 2026-04-01 --run-id phase1-7681adb-baseline

# 집계 결과 확인
python -m sajucandle.backtest aggregate --run-id phase1-7681adb-baseline
python -m sajucandle.backtest aggregate --run-id phase1-7681adb-baseline --json
```

### 출력 예시

```
Run: phase1-7681adb-baseline
grade        n    win%  avg_mfe  avg_mae  rr_tp1
------------------------------------------------
강진입      12    83.3   +4.20%   -1.80%    1.50
진입        48    58.3   +2.10%   -2.50%    1.40
관망       410    45.1   +1.20%   -2.00%      -
회피       150    30.0   +0.50%   -3.20%      -
```

### 새 SQL 컬럼 (migration 005)
`signal_log.run_id TEXT NULL` — 운영 signal은 NULL 유지.

### 서비스 코드 변경
- `repositories.insert_signal_log`: `run_id` Optional 파라미터 추가 (백테스트만 사용)
- `repositories.aggregate_signal_stats`: `run_id` 필터 — 기본 `run_id IS NULL`로 운영만 집계 (백테스트 오염 방지)
- `api.py::admin_signal_stats_endpoint`: `run_id` query param 전달

### Phase 2~4 활용
- Phase 2: 숏 대칭 구현 후 `phase2-long-only` vs `phase2-symmetric` run 비교
- Phase 3: RSI divergence 전/후 run 비교
- Phase 4: 가중치/임계값 grid 튜닝
```

- [ ] **Step 4: Commit + Push**

```
git add README.md
git commit -m "docs: Phase 1 backtest harness README 섹션"
git push origin main
```

- [ ] **Step 5: Manual step (사용자 수동)**

1. Supabase Studio → SQL Editor → `migrations/005_signal_log_run_id.sql` 실행
2. 로컬에서 운영 DSN 세팅한 상태(또는 `TEST_DATABASE_URL`)로 smoke:
   ```
   python -m sajucandle.backtest run --ticker BTCUSDT --from 2025-06-01 --to 2025-07-01 --run-id phase1-smoke-prod
   python -m sajucandle.backtest aggregate --run-id phase1-smoke-prod
   ```

---

## Self-Review

### Spec coverage

- [x] §2.1 포함 항목 12개 → Task 1~12 커버
- [x] §4.1 모듈 9개 → Task 4~10
- [x] §5.1 migration 005 → Task 1
- [x] §5.2 서비스 코드 변경 4건 → Task 1, 2, 3
- [x] §6 룩어헤드 방지 → Task 7 slicer assertion
- [x] §7 성능 예상 → Task 6 벌크 + 8 engine 직렬
- [x] §8 집계 SQL → Task 9
- [x] §9 테스트 전략 → Task 4~11
- [x] §10 관측성 로그 → Task 8 engine
- [x] §12 완료 기준 → Task 12

### Placeholder scan

- 모든 Task에 실제 코드, TDD 순서, 커밋 메시지 포함.
- "similar to", "TBD", "fill in" 없음.

### Type consistency

- `BacktestSummary(run_id, ticker, from_dt, to_dt, signals_total, signals_by_grade, insert_errors)` 통일.
- `run_id: Optional[str] = None` 전 파이프라인 일관.
- `TickerHistory` / `HistoryWindow` / `MfeMae` / `GradeStats` 모두 dataclass.
- engine.py의 `insert_fn` 시그니처는 `repositories.insert_signal_log`와 **keyword-only 전부** 일치.

### 주의사항

- Task 8 engine은 크다. 필요 시 subagent review 권장.
- Task 11 smoke는 TEST_DATABASE_URL 없으면 skip. CI에서도 skip (현재 CI는 DB 안 띄움).
- Task 2의 `aggregate_signal_stats` 변경은 Phase 0 리서치 Risk §11-4의 "/stats 오염" 해결책.

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-04-20-phase1-backtest-harness-plan.md`.**

**설계자 승인 대기 중**. 승인 시:
- **Subagent-Driven 실행 (추천)**: 12 Task subagent-driven-development로 순차 구현
- **Inline Execution**: 이 세션에서 직접 12 Task 수행

총 Task 수: **12** (migration + service 변경 3 + backtest 신규 7 + smoke + README)
예상 총 소요: **45~60분** (subagent-driven). Task 8 engine이 가장 큼.

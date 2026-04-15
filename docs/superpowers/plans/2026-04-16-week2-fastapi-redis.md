# Week 2: FastAPI + Redis Cache Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** FastAPI 서비스를 봇과 별도 Railway 서비스로 띄우고, 만세력 계산을 Upstash Redis에 캐싱. 봇 사용자 경험은 동일하되 내부적으로 같은 캐시를 공유.

**Architecture:** 같은 GitHub 저장소에서 Railway 서비스 2개 — `sajucandle-bot`(worker, `python -m sajucandle.bot`)와 `sajucandle-api`(web, `uvicorn sajucandle.api:app`). 두 서비스 모두 `REDIS_URL` 환경변수 공유. FastAPI는 `X-SAJUCANDLE-KEY` 내부 토큰으로 인증.

**Tech Stack:** FastAPI 0.110+, uvicorn, redis-py 5+, Upstash Redis (free tier), pytest + httpx TestClient

**범위 밖 (Week 3+):** Next.js, Supabase, yfinance/KIS 가격 데이터, 차트 엔진 통합, 일일 크론 잡

**사람이 직접 해야 하는 작업 (코드 아님):**
- Upstash 계정 생성 → Redis 데이터베이스 `sajucandle-cache` 생성 → `REDIS_URL` (rediss://...) 복사
- Railway에 새 서비스 `sajucandle-api` 생성 (같은 GitHub repo, startCommand override)
- 양 서비스에 환경변수 등록: `REDIS_URL`, `SAJUCANDLE_API_KEY`(봇은 불필요하지만 일관성 위해)

---

## File Structure 변경

```
src/sajucandle/
├── __init__.py
├── saju_engine.py       # 변경 없음
├── format.py            # 변경 없음
├── handlers.py          # 캐시된 엔진 사용하도록 wiring만 변경
├── bot.py               # 변경 없음
├── cache.py             # NEW: Redis 캐시 래퍼 (Redis 없으면 no-op)
├── cached_engine.py     # NEW: SajuEngine + BaziCache 결합
├── api.py               # NEW: FastAPI 앱 + 엔드포인트
├── api_main.py          # NEW: uvicorn 엔트리 포인트
└── models.py            # NEW: API 요청/응답 Pydantic 모델

tests/
├── test_format.py       # 기존
├── test_handlers.py     # 기존
├── test_cache.py        # NEW: BaziCache 단위 테스트 (fake Redis)
├── test_cached_engine.py # NEW: CachedSajuEngine TDD
└── test_api.py          # NEW: FastAPI TestClient 기반
```

**설계 포인트:**
- `cache.py`는 Redis 의존성을 숨기는 얇은 래퍼. `redis_client` 인자로 주입 → 테스트에서 fake 주입 가능.
- `cached_engine.py`는 `SajuEngine`을 감싸 동일 인터페이스 + 캐시 히트/미스 로직. 봇과 API 모두 이걸 사용.
- `models.py`는 Pydantic 모델 모음. `BaziChart` dataclass → Pydantic 응답 변환 로직도 여기.
- `api.py`는 엔드포인트 정의만. 의존성 주입으로 엔진/캐시 받음.

---

## Task 1: 의존성 추가

**Files:**
- Modify: `D:\사주캔들\pyproject.toml`

- [ ] **Step 1: `pyproject.toml`에 runtime 의존성 추가**

`[project] dependencies` 섹션에 다음 추가:
```toml
    "fastapi>=0.110,<1.0",
    "uvicorn[standard]>=0.27",
    "redis>=5.0,<6.0",
```

`[project.optional-dependencies] dev` 섹션에 다음 추가:
```toml
    "httpx>=0.27",
    "fakeredis>=2.20",
```

- [ ] **Step 2: 설치 반영**

Run:
```bash
cd "D:/사주캔들"
.venv/Scripts/python.exe -m pip install -e ".[dev]"
```
Expected: `fastapi`, `uvicorn`, `redis`, `httpx`, `fakeredis` 설치 완료.

- [ ] **Step 3: 임포트 스모크 테스트**

Run:
```bash
.venv/Scripts/python.exe -c "import fastapi, uvicorn, redis, httpx, fakeredis; print('deps ok')"
```
Expected: `deps ok`.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "chore: add fastapi, uvicorn, redis, httpx, fakeredis deps for Week 2"
```

---

## Task 2: Redis 캐시 래퍼 (TDD)

**Files:**
- Create: `D:\사주캔들\tests\test_cache.py`
- Create: `D:\사주캔들\src\sajucandle\cache.py`

- [ ] **Step 1: 실패 테스트 작성**

Create `tests/test_cache.py`:
```python
from __future__ import annotations

import fakeredis

from sajucandle.cache import BaziCache


def test_cache_miss_then_hit():
    """첫 호출은 compute_fn 실행, 두 번째는 캐시에서."""
    redis = fakeredis.FakeStrictRedis()
    cache = BaziCache(redis_client=redis, ttl_seconds=60)

    call_count = {"n": 0}

    def compute():
        call_count["n"] += 1
        return {"pillar": "庚午"}

    first = cache.get_or_compute("bazi:1990031514", compute)
    assert first == {"pillar": "庚午"}
    assert call_count["n"] == 1

    second = cache.get_or_compute("bazi:1990031514", compute)
    assert second == {"pillar": "庚午"}
    assert call_count["n"] == 1  # 캐시 히트라 재계산 없음


def test_cache_no_redis_is_noop():
    """redis_client=None이면 매번 compute_fn 실행 (fallback)."""
    cache = BaziCache(redis_client=None, ttl_seconds=60)

    call_count = {"n": 0}

    def compute():
        call_count["n"] += 1
        return "result"

    assert cache.get_or_compute("key", compute) == "result"
    assert cache.get_or_compute("key", compute) == "result"
    assert call_count["n"] == 2


def test_cache_ttl_expiry():
    """TTL 지나면 재계산."""
    redis = fakeredis.FakeStrictRedis()
    cache = BaziCache(redis_client=redis, ttl_seconds=60)

    cache.get_or_compute("key", lambda: "v1")
    # fakeredis 시간 조작
    redis.delete("key")  # expire 시뮬레이션

    call_count = {"n": 0}

    def compute_v2():
        call_count["n"] += 1
        return "v2"

    assert cache.get_or_compute("key", compute_v2) == "v2"
    assert call_count["n"] == 1


def test_cache_survives_unpicklable_gracefully():
    """직렬화 불가 객체는 예외 대신 캐시 미스처럼 동작 (안전).

    단순 dict/dataclass/primitive만 캐시 대상이라 실전엔 잘 안 터짐.
    여기선 명시적으로 object() 같은 게 들어와도 죽지 않는 걸 확인.
    """
    redis = fakeredis.FakeStrictRedis()
    cache = BaziCache(redis_client=redis, ttl_seconds=60)

    sentinel = object()
    # pickle은 object()도 되므로 이 테스트는 정상 통과해야 함 (참고용)
    result = cache.get_or_compute("key", lambda: sentinel)
    assert result is sentinel
```

- [ ] **Step 2: 테스트 실행 — FAIL 확인**

Run:
```bash
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -m pytest tests/test_cache.py -v
```
Expected: `ModuleNotFoundError: No module named 'sajucandle.cache'`.

- [ ] **Step 3: `cache.py` 구현**

Create `src/sajucandle/cache.py`:
```python
"""Redis 기반 일반 캐시 래퍼. Redis 없으면 pass-through."""
from __future__ import annotations

import logging
import pickle
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


class BaziCache:
    """get_or_compute 패턴으로 호출부 단순화.

    redis_client가 None이면 캐시 비활성 (로컬 테스트/Redis 미설정 Railway 첫 배포 등에 유용).

    직렬화는 pickle — 내부 전용 캐시라 안전. 외부에 노출 금지.
    """

    def __init__(
        self,
        redis_client: Optional[Any] = None,
        ttl_seconds: int = 30 * 24 * 3600,  # 30일
    ) -> None:
        self._redis = redis_client
        self._ttl = ttl_seconds

    def get_or_compute(self, key: str, compute_fn: Callable[[], Any]) -> Any:
        """캐시 히트면 반환, 미스면 compute_fn 실행 후 저장."""
        if self._redis is None:
            return compute_fn()

        try:
            cached = self._redis.get(key)
        except Exception as e:  # Redis 다운/네트워크 실패
            logger.warning("Redis GET 실패 (%s). compute_fn으로 fallback.", e)
            return compute_fn()

        if cached is not None:
            try:
                return pickle.loads(cached)
            except Exception as e:  # 포맷 깨짐 — 무시하고 재계산
                logger.warning("캐시 역직렬화 실패 (%s). 재계산.", e)

        result = compute_fn()

        try:
            self._redis.set(key, pickle.dumps(result), ex=self._ttl)
        except Exception as e:
            logger.warning("Redis SET 실패 (%s). 캐시 저장 스킵.", e)

        return result
```

- [ ] **Step 4: 테스트 재실행 — PASS 확인**

Run:
```bash
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -m pytest tests/test_cache.py -v
```
Expected: 4 tests PASSED.

- [ ] **Step 5: Commit**

```bash
git add tests/test_cache.py src/sajucandle/cache.py
git commit -m "feat: add BaziCache Redis wrapper with no-op fallback"
```

---

## Task 3: 캐시된 엔진 (TDD)

**Files:**
- Create: `D:\사주캔들\tests\test_cached_engine.py`
- Create: `D:\사주캔들\src\sajucandle\cached_engine.py`

- [ ] **Step 1: 실패 테스트 작성**

Create `tests/test_cached_engine.py`:
```python
from __future__ import annotations

import fakeredis

from sajucandle.cache import BaziCache
from sajucandle.cached_engine import CachedSajuEngine
from sajucandle.saju_engine import BaziChart


def test_calc_bazi_cached_returns_same_object():
    redis = fakeredis.FakeStrictRedis()
    cache = BaziCache(redis_client=redis, ttl_seconds=60)
    engine = CachedSajuEngine(cache=cache)

    c1 = engine.calc_bazi(1990, 3, 15, 14)
    c2 = engine.calc_bazi(1990, 3, 15, 14)

    assert isinstance(c1, BaziChart)
    assert c1.year_gan == c2.year_gan
    assert c1.month_gan == c2.month_gan
    assert c1.day_gan == c2.day_gan
    assert c1.hour_gan == c2.hour_gan


def test_calc_bazi_key_format():
    """키 포맷이 시진 단위(YYYYMMDDHH)여야 같은 시 내 분 차이는 무시 가능."""
    redis = fakeredis.FakeStrictRedis()
    cache = BaziCache(redis_client=redis, ttl_seconds=60)
    engine = CachedSajuEngine(cache=cache)

    engine.calc_bazi(1990, 3, 15, 14)
    keys = [k.decode() for k in redis.keys("bazi:*")]
    assert "bazi:1990031514" in keys


def test_calc_bazi_without_redis_still_works():
    """Redis None이어도 엔진 동작."""
    cache = BaziCache(redis_client=None)
    engine = CachedSajuEngine(cache=cache)

    chart = engine.calc_bazi(1990, 3, 15, 14)
    assert chart.day_gan == "己"


def test_different_inputs_different_keys():
    redis = fakeredis.FakeStrictRedis()
    cache = BaziCache(redis_client=redis, ttl_seconds=60)
    engine = CachedSajuEngine(cache=cache)

    engine.calc_bazi(1990, 3, 15, 14)
    engine.calc_bazi(1990, 3, 15, 15)  # 다른 시
    engine.calc_bazi(1991, 3, 15, 14)  # 다른 연

    keys = [k.decode() for k in redis.keys("bazi:*")]
    assert len(keys) == 3
```

- [ ] **Step 2: FAIL 확인**

Run:
```bash
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -m pytest tests/test_cached_engine.py -v
```
Expected: ModuleNotFoundError.

- [ ] **Step 3: `cached_engine.py` 구현**

Create `src/sajucandle/cached_engine.py`:
```python
"""BaziCache를 두른 SajuEngine 래퍼."""
from __future__ import annotations

from sajucandle.cache import BaziCache
from sajucandle.saju_engine import BaziChart, SajuEngine


class CachedSajuEngine:
    """SajuEngine과 동일한 메서드 시그니처, 내부적으로 캐시 사용."""

    def __init__(
        self,
        cache: BaziCache,
        engine: SajuEngine | None = None,
    ) -> None:
        self._cache = cache
        self._engine = engine or SajuEngine()

    def calc_bazi(
        self,
        year: int,
        month: int,
        day: int,
        hour: int,
    ) -> BaziChart:
        key = f"bazi:{year:04d}{month:02d}{day:02d}{hour:02d}"
        return self._cache.get_or_compute(
            key,
            lambda: self._engine.calc_bazi(year, month, day, hour),
        )
```

- [ ] **Step 4: PASS 확인**

Run:
```bash
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -m pytest tests/test_cached_engine.py -v
```
Expected: 4 tests PASSED.

- [ ] **Step 5: Commit**

```bash
git add tests/test_cached_engine.py src/sajucandle/cached_engine.py
git commit -m "feat: add CachedSajuEngine wrapping SajuEngine + BaziCache"
```

---

## Task 4: 봇에 캐시 적용 (행동 변화 없음)

**Files:**
- Modify: `D:\사주캔들\src\sajucandle\handlers.py`

- [ ] **Step 1: `handlers.py`에서 엔진 생성 부분 교체**

기존:
```python
_engine = SajuEngine()
```

다음으로 교체:
```python
from sajucandle.cache import BaziCache
from sajucandle.cached_engine import CachedSajuEngine


def _build_engine() -> CachedSajuEngine:
    """REDIS_URL 환경변수 있으면 실제 Redis 연결, 없으면 no-op 캐시."""
    import os
    redis_url = os.environ.get("REDIS_URL")
    redis_client = None
    if redis_url:
        try:
            import redis
            redis_client = redis.from_url(redis_url)
            # 초기 ping으로 연결 확인 (실패 시 no-op로 degradation)
            redis_client.ping()
        except Exception:
            import logging
            logging.warning("Redis 연결 실패. 캐시 없이 진행.")
            redis_client = None
    cache = BaziCache(redis_client=redis_client)
    return CachedSajuEngine(cache=cache)


_engine = _build_engine()
```

그리고 파일 상단 `from sajucandle.saju_engine import SajuEngine` 제거 (더 이상 직접 사용 안 함 — `CachedSajuEngine` 경유).

- [ ] **Step 2: 기존 테스트 모두 통과 확인**

Run:
```bash
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -m pytest -v
```
Expected: 이전 모든 테스트 (format 4 + handlers 8 + cache 4 + cached_engine 4) 총 20 PASS.

- [ ] **Step 3: Commit**

```bash
git add src/sajucandle/handlers.py
git commit -m "feat: bot uses CachedSajuEngine with REDIS_URL env auto-detect"
```

---

## Task 5: Pydantic 모델 (API 요청/응답)

**Files:**
- Create: `D:\사주캔들\src\sajucandle\models.py`

- [ ] **Step 1: `models.py` 작성**

Create `src/sajucandle/models.py`:
```python
"""API 요청/응답 Pydantic 모델. BaziChart dataclass와 변환 함수."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from sajucandle.saju_engine import BaziChart


class BirthRequest(BaseModel):
    """생년월일시. 시간은 24시 기준, 분은 시진 단위라 일단 무시."""

    year: int = Field(ge=1900, le=2100)
    month: int = Field(ge=1, le=12)
    day: int = Field(ge=1, le=31)
    hour: int = Field(ge=0, le=23)
    minute: int = Field(default=0, ge=0, le=59)


class PillarModel(BaseModel):
    gan: Optional[str]
    zhi: Optional[str]


class BaziResponse(BaseModel):
    birth_solar: str
    birth_lunar: str
    year: PillarModel
    month: PillarModel
    day: PillarModel
    hour: PillarModel  # gan/zhi Optional (시주 미상 케이스)
    day_gan: str
    wuxing_dist: dict[str, int]
    day_master_strength: str
    yongsin: Optional[str]


def bazi_chart_to_response(chart: BaziChart) -> BaziResponse:
    return BaziResponse(
        birth_solar=chart.birth_solar,
        birth_lunar=chart.birth_lunar,
        year=PillarModel(gan=chart.year_gan, zhi=chart.year_zhi),
        month=PillarModel(gan=chart.month_gan, zhi=chart.month_zhi),
        day=PillarModel(gan=chart.day_gan, zhi=chart.day_zhi),
        hour=PillarModel(gan=chart.hour_gan, zhi=chart.hour_zhi),
        day_gan=chart.day_gan,
        wuxing_dist=chart.wuxing_dist,
        day_master_strength=chart.day_master_strength,
        yongsin=chart.yongsin.value if chart.yongsin else None,
    )
```

- [ ] **Step 2: 임포트 스모크**

Run:
```bash
.venv/Scripts/python.exe -c "from sajucandle.models import BirthRequest, BaziResponse, bazi_chart_to_response; print('ok')"
```
Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
git add src/sajucandle/models.py
git commit -m "feat: add Pydantic models for API birth request and bazi response"
```

---

## Task 6: FastAPI 앱 + 엔드포인트 (TDD)

**Files:**
- Create: `D:\사주캔들\tests\test_api.py`
- Create: `D:\사주캔들\src\sajucandle\api.py`

- [ ] **Step 1: 실패 테스트 작성**

Create `tests/test_api.py`:
```python
from __future__ import annotations

import os

import fakeredis
import pytest
from fastapi.testclient import TestClient

from sajucandle.api import create_app
from sajucandle.cache import BaziCache
from sajucandle.cached_engine import CachedSajuEngine


@pytest.fixture
def api_key() -> str:
    return "test-secret-key"


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, api_key: str) -> TestClient:
    monkeypatch.setenv("SAJUCANDLE_API_KEY", api_key)
    redis = fakeredis.FakeStrictRedis()
    cache = BaziCache(redis_client=redis, ttl_seconds=60)
    engine = CachedSajuEngine(cache=cache)
    app = create_app(engine=engine)
    return TestClient(app)


def test_health_ok(client: TestClient):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_bazi_requires_api_key(client: TestClient):
    r = client.post(
        "/v1/bazi",
        json={"year": 1990, "month": 3, "day": 15, "hour": 14},
    )
    assert r.status_code == 401


def test_bazi_wrong_api_key(client: TestClient):
    r = client.post(
        "/v1/bazi",
        json={"year": 1990, "month": 3, "day": 15, "hour": 14},
        headers={"X-SAJUCANDLE-KEY": "wrong"},
    )
    assert r.status_code == 401


def test_bazi_success(client: TestClient, api_key: str):
    r = client.post(
        "/v1/bazi",
        json={"year": 1990, "month": 3, "day": 15, "hour": 14},
        headers={"X-SAJUCANDLE-KEY": api_key},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["day_gan"] == "己"
    assert data["year"]["gan"] == "庚"
    assert data["year"]["zhi"] == "午"
    assert data["birth_solar"] == "1990-03-15"


def test_bazi_validation_error(client: TestClient, api_key: str):
    r = client.post(
        "/v1/bazi",
        json={"year": 1990, "month": 13, "day": 15, "hour": 14},
        headers={"X-SAJUCANDLE-KEY": api_key},
    )
    assert r.status_code == 422  # Pydantic validation


def test_bazi_cache_hit_on_second_call(client: TestClient, api_key: str):
    payload = {"year": 1990, "month": 3, "day": 15, "hour": 14}
    headers = {"X-SAJUCANDLE-KEY": api_key}

    r1 = client.post("/v1/bazi", json=payload, headers=headers)
    r2 = client.post("/v1/bazi", json=payload, headers=headers)

    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json() == r2.json()
```

- [ ] **Step 2: FAIL 확인**

Run:
```bash
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -m pytest tests/test_api.py -v
```
Expected: `ModuleNotFoundError: No module named 'sajucandle.api'`.

- [ ] **Step 3: `api.py` 구현**

Create `src/sajucandle/api.py`:
```python
"""FastAPI 엔드포인트. 봇과 Next.js 웹 공통 백엔드."""
from __future__ import annotations

import os

from fastapi import Depends, FastAPI, Header, HTTPException

from sajucandle.cache import BaziCache
from sajucandle.cached_engine import CachedSajuEngine
from sajucandle.models import BirthRequest, BaziResponse, bazi_chart_to_response


def _require_api_key(x_sajucandle_key: str | None = Header(default=None)) -> None:
    expected = os.environ.get("SAJUCANDLE_API_KEY")
    if not expected:
        raise HTTPException(
            status_code=500,
            detail="SAJUCANDLE_API_KEY 환경변수가 설정되지 않았습니다.",
        )
    if x_sajucandle_key != expected:
        raise HTTPException(status_code=401, detail="Invalid API key")


def _build_default_engine() -> CachedSajuEngine:
    redis_url = os.environ.get("REDIS_URL")
    redis_client = None
    if redis_url:
        try:
            import redis
            redis_client = redis.from_url(redis_url)
            redis_client.ping()
        except Exception:
            import logging
            logging.warning("Redis 연결 실패. 캐시 없이 진행.")
            redis_client = None
    return CachedSajuEngine(cache=BaziCache(redis_client=redis_client))


def create_app(engine: CachedSajuEngine | None = None) -> FastAPI:
    """테스트에서 engine 주입 가능. 프로덕션은 default 사용."""
    app = FastAPI(title="SajuCandle API", version="0.2.0")
    _engine = engine or _build_default_engine()

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post(
        "/v1/bazi",
        response_model=BaziResponse,
        dependencies=[Depends(_require_api_key)],
    )
    def compute_bazi(req: BirthRequest) -> BaziResponse:
        chart = _engine.calc_bazi(req.year, req.month, req.day, req.hour)
        return bazi_chart_to_response(chart)

    return app


# uvicorn이 app을 모듈 속성으로 찾는다
app = create_app()
```

- [ ] **Step 4: PASS 확인**

Run:
```bash
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -m pytest tests/test_api.py -v
```
Expected: 6 tests PASSED.

- [ ] **Step 5: 전체 테스트 회귀 확인**

Run:
```bash
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -m pytest -v
```
Expected: 26 tests PASSED (format 4 + handlers 8 + cache 4 + cached_engine 4 + api 6).

- [ ] **Step 6: Commit**

```bash
git add tests/test_api.py src/sajucandle/api.py
git commit -m "feat: FastAPI app with /health and /v1/bazi endpoints + API key auth"
```

---

## Task 7: API 로컬 실행 확인

**Files:** (새 파일 없음)

- [ ] **Step 1: 로컬에서 uvicorn으로 API 띄우기**

Run (PowerShell):
```powershell
$env:SAJUCANDLE_API_KEY = "local-dev-key"
.venv\Scripts\uvicorn.exe sajucandle.api:app --port 8000
```
Expected: `Uvicorn running on http://127.0.0.1:8000` 출력.

- [ ] **Step 2: 다른 터미널에서 /health curl**

Run:
```bash
curl http://localhost:8000/health
```
Expected: `{"status":"ok"}`.

- [ ] **Step 3: /v1/bazi curl**

Run:
```bash
curl -X POST http://localhost:8000/v1/bazi \
  -H "Content-Type: application/json" \
  -H "X-SAJUCANDLE-KEY: local-dev-key" \
  -d '{"year":1990,"month":3,"day":15,"hour":14}'
```
Expected: JSON 응답에 `"day_gan":"己"`, `"year":{"gan":"庚","zhi":"午"}` 포함.

- [ ] **Step 4: API 자동 문서 확인**

브라우저에서 `http://localhost:8000/docs` 열기. Swagger UI에 `/health`, `/v1/bazi` 표시되는지 확인. (수동 스텝, 커밋 없음.)

Ctrl+C로 uvicorn 종료.

---

## Task 8: Railway 2-서비스 배포 설정

**Files:**
- Modify: `D:\사주캔들\Procfile` (web 프로세스 타입 추가)
- Modify: `D:\사주캔들\Dockerfile` (기본 CMD만 바꾸지 않음 — Railway에서 startCommand override)

- [ ] **Step 1: `Procfile` 업데이트**

현재 내용:
```
worker: python -m sajucandle.bot
```

다음으로 교체:
```
worker: python -m sajucandle.bot
web: uvicorn sajucandle.api:app --host 0.0.0.0 --port $PORT
```

- [ ] **Step 2: `Dockerfile` 확인 (변경 없음)**

현재 Dockerfile의 `CMD ["python", "-m", "sajucandle.bot"]`는 bot 서비스 기본값. API 서비스는 Railway 대시보드에서 `startCommand`로 `uvicorn sajucandle.api:app --host 0.0.0.0 --port $PORT` 지정.

- [ ] **Step 3: Commit**

```bash
git add Procfile
git commit -m "chore: add web process type for FastAPI service in Procfile"
```

- [ ] **Step 4: GitHub push**

```bash
git push
```

- [ ] **Step 5: Railway 대시보드에서 수동 작업 (사람)**

1. Upstash:
   - upstash.com 로그인 → Create Redis Database (free, 이름 `sajucandle-cache`, 리전 선택 — Singapore 또는 us-west 추천)
   - "Connect to your database" 섹션에서 `REDIS_URL` (rediss://...) 복사
2. 기존 bot 서비스:
   - Variables에 `REDIS_URL` 추가 → 저장 (자동 재배포)
3. 새 API 서비스:
   - Railway 프로젝트 → + New → GitHub Repo → `zgler/sajucandle` 선택
   - Settings → Start Command: `uvicorn sajucandle.api:app --host 0.0.0.0 --port $PORT`
   - Variables: `REDIS_URL`(위와 동일), `SAJUCANDLE_API_KEY`(랜덤 긴 문자열 — `openssl rand -hex 32` 또는 수동)
   - Networking → Generate Domain → `sajucandle-api.up.railway.app` 같은 URL 획득
4. 배포 후 확인:
   - `curl https://<API-URL>/health` → `{"status":"ok"}`
   - `curl -X POST https://<API-URL>/v1/bazi -H "X-SAJUCANDLE-KEY: <KEY>" -H "Content-Type: application/json" -d '{"year":1990,"month":3,"day":15,"hour":14}'` → JSON 응답

---

## Task 9: README 업데이트

**Files:**
- Modify: `D:\사주캔들\README.md`

- [ ] **Step 1: README에 API 섹션 추가**

기존 "다음 주차 (범위 밖)" 섹션 앞에 다음 추가:

```markdown
## FastAPI (Week 2+)

내부 API 서버. 봇과 웹이 공통으로 호출.

### 로컬 실행

```bash
export SAJUCANDLE_API_KEY="local-dev-key"
export REDIS_URL=""  # 비우면 캐시 없이 동작
.venv/Scripts/uvicorn.exe sajucandle.api:app --port 8000
```

문서: http://localhost:8000/docs

### 엔드포인트

- `GET /health` — 상태 체크, 인증 불필요
- `POST /v1/bazi` — 명식 계산. Header `X-SAJUCANDLE-KEY` 필수. Body: `{"year":1990,"month":3,"day":15,"hour":14}`

### 배포 (Railway 2-서비스)

- `sajucandle-bot` (worker): `python -m sajucandle.bot`
- `sajucandle-api` (web): `uvicorn sajucandle.api:app --host 0.0.0.0 --port $PORT`
- 두 서비스 모두 `REDIS_URL`(Upstash) 공유
- API 서비스는 `SAJUCANDLE_API_KEY` 추가 필수
```

"다음 주차 (범위 밖)" 섹션의 Week 2 불릿 삭제, Week 3 시작:
```markdown
- Week 3: Next.js 웹 + Supabase Auth, API 통해 명식 카드 렌더
- Week 4+: yfinance 미국주식 추천 카드, KIS 연동
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: document Week 2 FastAPI service and Railway 2-service setup"
```

---

## Task 10: 최종 통합 검증

- [ ] **Step 1: 전체 테스트**

```bash
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -m pytest -v
```
Expected: 26 tests PASSED.

- [ ] **Step 2: 임포트 smoke**

```bash
.venv/Scripts/python.exe -c "from sajucandle import api, bot, handlers, cache, cached_engine, models; print('all imports ok')"
```
Expected: `all imports ok`.

- [ ] **Step 3: git log 확인**

```bash
git log --oneline | head -15
```
Expected: Week 2 커밋 10개 + Week 1 커밋들.

- [ ] **Step 4: push**

```bash
git push
```

- [ ] **Step 5: 수동 통합 테스트 (사람)**

1. Telegram에서 `@sajucandle_bot` `/start 1990-03-15 14:00` — 이전과 동일한 카드 수신 (캐시 히트여야 정상)
2. API 서비스 URL에 curl — `{"day_gan":"己"}` 포함된 JSON
3. 같은 요청 재호출 — 응답 동일, Upstash 대시보드에서 키 `bazi:1990031514` 존재 확인

---

## 완료 기준

- [ ] `pytest` 26 PASS
- [ ] 로컬에서 uvicorn + curl로 `/health` `/v1/bazi` 동작 확인
- [ ] Railway에 `sajucandle-api` 서비스 Active 상태
- [ ] 프로덕션 API URL로 curl → `day_gan:"己"` 반환
- [ ] Upstash 대시보드에서 캐시 키 1개 이상 존재 (봇 또는 API 호출 후)
- [ ] 봇 `/start` 여전히 정상 동작

## 다음 플랜

Week 3: Next.js 14 스캐폴딩 + Supabase Auth + API 호출해서 명식 카드 웹 UI. API URL은 `NEXT_PUBLIC_SAJUCANDLE_API_URL`, 키는 서버 사이드 env (브라우저 노출 금지).

# Week 6: US Stocks /signal Extension — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `/signal AAPL` 같은 미국주식 5종(AAPL/MSFT/GOOGL/NVDA/TSLA) 시그널을 yfinance 기반으로 추가하고, 휴장/주말에도 마지막 종가 기준으로 카드를 반환한다. 기존 BTC `/signal` 동작은 100% 유지.

**Architecture:** 새 `src/sajucandle/market/` 패키지에 `MarketDataProvider` 프로토콜(base) + 기존 Binance + 신규 YFinance + 티커 라우터를 구성. `SignalService`에 `MarketRouter`를 DI해서 ticker별로 provider를 선택. `models.py`에 `MarketStatus` 필드를 추가해 카드에 장 상태 배지 표시.

**Tech Stack:** Python 3.12, FastAPI, python-telegram-bot 21, httpx, Pydantic v2, yfinance 0.2.40+, pytest, fakeredis, respx, unittest.mock (yfinance mocking)

**Spec:** `docs/superpowers/specs/2026-04-17-week6-us-stocks-design.md` (commit 3a26fd7)

**Build system note:** 프로젝트는 PEP 621 + hatchling(폴리트리 아님). 의존성 추가는 `pyproject.toml` 직접 편집 + `pip install -e ".[dev]"`로 재설치.

---

## File Structure (New / Modified)

```
src/sajucandle/
├── market_data.py                # [MODIFY] is_market_open + last_session_date 메서드 추가 (BinanceClient)
├── market/                       # [CREATE] 새 패키지
│   ├── __init__.py               # [CREATE] 빈 파일
│   ├── base.py                   # [CREATE] MarketDataProvider Protocol + UnsupportedTicker
│   ├── yfinance.py               # [CREATE] YFinanceClient
│   └── router.py                 # [CREATE] MarketRouter + all_symbols()
├── models.py                     # [MODIFY] MarketStatus 모델 + SignalResponse.market_status 필드
├── signal_service.py             # [MODIFY] market_client → market_router DI 전환
├── api.py                        # [MODIFY] BTCUSDT 가드 제거 + /v1/signal/symbols + MarketRouter DI
├── api_client.py                 # [MODIFY] get_supported_symbols() 추가
└── handlers.py                   # [MODIFY] /signal 인자 파싱, /signal list, 카드 포맷, /help

tests/
├── test_market_data.py           # [MODIFY] BinanceClient의 is_market_open + last_session_date 테스트 추가
├── test_market_yfinance.py       # [CREATE] YFinanceClient 전용 테스트
├── test_market_router.py         # [CREATE] MarketRouter 전용 테스트
├── test_signal_service.py        # [MODIFY] _FakeMarketClient → router wiring, market_status 필드 검증
├── test_api_signal.py            # [MODIFY] /signal?ticker=AAPL 통과, AMZN→400
├── test_api.py                   # [MODIFY] /v1/signal/symbols 인증/정상 테스트
├── test_api_client.py            # [MODIFY] get_supported_symbols 테스트
└── test_handlers.py              # [MODIFY] /signal AAPL, /signal list, /signal UNKNOWN, 배지 포함 카드

pyproject.toml                    # [MODIFY] yfinance 의존성 추가
README.md                         # [MODIFY] Week 6 섹션 추가, /help 명령 목록 갱신
```

---

## Task 1: Add yfinance dependency

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Edit pyproject.toml**

`[project] dependencies` 배열에 yfinance 추가.

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
    "yfinance>=0.2.40,<0.3",
]
```

- [ ] **Step 2: Reinstall to pick up new dep**

Run (Windows PowerShell):
```
pip install -e ".[dev]"
```

Expected: `Successfully installed yfinance-0.2.x ... pandas-2.x ... numpy-1.x ...` (transitive deps).

- [ ] **Step 3: Verify import works**

Run:
```
python -c "import yfinance; print(yfinance.__version__)"
```

Expected: `0.2.40` 이상의 버전 출력.

- [ ] **Step 4: Run existing tests — make sure nothing broke**

Run:
```
pytest -q
```

Expected: 기존 모든 테스트 그대로 통과 (153+ passed). 실패 시 yfinance 설치 문제 — Python 3.12 휠 확인.

- [ ] **Step 5: Commit**

```
git add pyproject.toml
git commit -m "deps: add yfinance for Week 6 US stocks signal"
```

---

## Task 2: Extend BinanceClient with is_market_open + last_session_date

**Files:**
- Modify: `src/sajucandle/market_data.py` (BinanceClient 클래스에 2개 메서드 추가)
- Modify: `tests/test_market_data.py` (기존 파일에 테스트 2개 추가)

목적: BinanceClient가 `MarketDataProvider` 프로토콜을 만족하도록 인터페이스 메서드 2개 추가. Crypto는 24/7이라 구현이 trivial.

- [ ] **Step 1: Write failing tests**

`tests/test_market_data.py` 파일 맨 아래에 추가:

```python
# ─────────────────────────────────────────────
# Week 6: MarketDataProvider protocol conformance
# ─────────────────────────────────────────────

def test_binance_is_market_open_always_true():
    """BTC는 24/7 거래이므로 항상 True."""
    client = BinanceClient()
    assert client.is_market_open("BTCUSDT") is True


def test_binance_last_session_date_is_today_utc():
    """BTC는 현재 UTC 날짜를 마지막 세션으로 간주."""
    from datetime import datetime, timezone
    client = BinanceClient()
    expected = datetime.now(timezone.utc).date()
    assert client.last_session_date("BTCUSDT") == expected
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```
pytest tests/test_market_data.py::test_binance_is_market_open_always_true tests/test_market_data.py::test_binance_last_session_date_is_today_utc -v
```

Expected: FAIL with `AttributeError: 'BinanceClient' object has no attribute 'is_market_open'`.

- [ ] **Step 3: Implement the methods**

`src/sajucandle/market_data.py`의 `BinanceClient` 클래스 마지막(`_redis_set` 메서드 아래)에 추가:

```python
    # ─────────────────────────────────────────────
    # MarketDataProvider protocol (Week 6+)
    # ─────────────────────────────────────────────

    def is_market_open(self, symbol: str) -> bool:
        """BTC 24/7 거래. 심볼 무관 항상 True."""
        return True

    def last_session_date(self, symbol: str):
        """24/7 거래라 '마지막 세션'은 현재 UTC 날짜."""
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).date()
```

- [ ] **Step 4: Run tests to verify PASS**

Run:
```
pytest tests/test_market_data.py -v
```

Expected: 기존 테스트 + 새 테스트 2개 PASS.

- [ ] **Step 5: Commit**

```
git add src/sajucandle/market_data.py tests/test_market_data.py
git commit -m "feat(market): add is_market_open/last_session_date to BinanceClient"
```

---

## Task 3: Create market/base.py — Protocol + UnsupportedTicker

**Files:**
- Create: `src/sajucandle/market/__init__.py`
- Create: `src/sajucandle/market/base.py`
- Create: `tests/test_market_base.py`

- [ ] **Step 1: Write failing test**

`tests/test_market_base.py`:

```python
"""market.base: MarketDataProvider Protocol + UnsupportedTicker."""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Protocol

import pytest

from sajucandle.market.base import MarketDataProvider, UnsupportedTicker
from sajucandle.market_data import BinanceClient, Kline


def test_unsupported_ticker_is_exception():
    """UnsupportedTicker는 Exception 서브클래스여야 한다."""
    assert issubclass(UnsupportedTicker, Exception)


def test_unsupported_ticker_carries_symbol_in_str():
    """에러 메시지에 심볼이 포함되어야 한다."""
    e = UnsupportedTicker("AMZN")
    assert "AMZN" in str(e)


def test_market_data_provider_is_protocol():
    """MarketDataProvider는 Protocol이며 runtime_checkable 아님(duck typing)."""
    assert Protocol in MarketDataProvider.__mro__ or hasattr(
        MarketDataProvider, "_is_protocol"
    )


def test_binance_client_satisfies_protocol_structurally():
    """BinanceClient는 세 메서드(fetch_klines, is_market_open, last_session_date)를 가진다."""
    client = BinanceClient()
    assert hasattr(client, "fetch_klines")
    assert hasattr(client, "is_market_open")
    assert hasattr(client, "last_session_date")
    # 실제 호출도 가능해야 함
    assert client.is_market_open("BTCUSDT") is True
    assert client.last_session_date("BTCUSDT") == datetime.now(timezone.utc).date()
```

- [ ] **Step 2: Run to verify fails**

```
pytest tests/test_market_base.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'sajucandle.market'`.

- [ ] **Step 3: Create package files**

`src/sajucandle/market/__init__.py` (빈 파일):

```python
"""Market data provider package (Week 6+)."""
```

`src/sajucandle/market/base.py`:

```python
"""MarketDataProvider Protocol + UnsupportedTicker.

ticker에 따라 BinanceClient(crypto) 또는 YFinanceClient(us_stocks)를 선택하는
라우팅 계층을 가능하게 하는 공통 인터페이스.
"""
from __future__ import annotations

from datetime import date
from typing import Protocol

from sajucandle.market_data import Kline


class UnsupportedTicker(Exception):
    """화이트리스트에 없는 심볼이 요청됐을 때."""

    def __init__(self, symbol: str):
        super().__init__(f"unsupported ticker: {symbol}")
        self.symbol = symbol


class MarketDataProvider(Protocol):
    """OHLCV 제공자 공통 인터페이스.

    BinanceClient와 YFinanceClient 모두 구조적으로 만족한다.
    runtime_checkable은 사용하지 않는다 — duck typing만으로 충분.
    """

    def fetch_klines(
        self, symbol: str, interval: str = "1d", limit: int = 100
    ) -> list[Kline]: ...

    def is_market_open(self, symbol: str) -> bool: ...

    def last_session_date(self, symbol: str) -> date: ...
```

- [ ] **Step 4: Run to verify PASS**

```
pytest tests/test_market_base.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```
git add src/sajucandle/market/__init__.py src/sajucandle/market/base.py tests/test_market_base.py
git commit -m "feat(market): add MarketDataProvider protocol + UnsupportedTicker"
```

---

## Task 4: Create market/yfinance.py — fetch_klines with Redis caching

**Files:**
- Create: `src/sajucandle/market/yfinance.py`
- Create: `tests/test_market_yfinance.py`

- [ ] **Step 1: Write failing tests for fetch_klines**

`tests/test_market_yfinance.py`:

```python
"""market.yfinance: YFinanceClient — 미국주식 OHLCV.

yfinance.Ticker를 mock. 실제 네트워크 호출 0회.
"""
from __future__ import annotations

import json
from datetime import datetime
from unittest.mock import patch, MagicMock

import fakeredis
import pandas as pd
import pytest

from sajucandle.market.base import UnsupportedTicker
from sajucandle.market.yfinance import YFinanceClient
from sajucandle.market_data import Kline, MarketDataUnavailable


def _make_yf_dataframe(n: int = 100) -> pd.DataFrame:
    """yfinance Ticker.history() 스타일 DataFrame. DatetimeIndex + OHLCV 컬럼."""
    idx = pd.date_range(end="2026-04-16", periods=n, freq="B", tz="America/New_York")
    rows = []
    for i in range(n):
        base = 180.0 + i * 0.3
        rows.append({
            "Open": base - 0.2,
            "High": base + 0.5,
            "Low": base - 0.5,
            "Close": base,
            "Volume": 50_000_000 + i * 100_000,
        })
    return pd.DataFrame(rows, index=idx)


def test_fetch_klines_rejects_unsupported_symbol():
    """화이트리스트 외 심볼은 UnsupportedTicker."""
    client = YFinanceClient()
    with pytest.raises(UnsupportedTicker):
        client.fetch_klines("AMZN")


def test_fetch_klines_returns_klines_for_supported_symbol():
    """yf.Ticker를 mock하고 AAPL 조회 시 Kline 리스트 반환."""
    df = _make_yf_dataframe(100)
    fake_ticker = MagicMock()
    fake_ticker.history.return_value = df

    client = YFinanceClient()
    with patch("sajucandle.market.yfinance.yf.Ticker", return_value=fake_ticker):
        klines = client.fetch_klines("AAPL")

    assert len(klines) == 100
    assert all(isinstance(k, Kline) for k in klines)
    last = klines[-1]
    assert last.close == pytest.approx(180.0 + 99 * 0.3)
    assert last.volume > 0


def test_fetch_klines_normalizes_symbol_to_upper():
    """소문자 입력도 대문자로 정규화해서 처리."""
    df = _make_yf_dataframe(5)
    fake_ticker = MagicMock()
    fake_ticker.history.return_value = df

    client = YFinanceClient()
    with patch("sajucandle.market.yfinance.yf.Ticker", return_value=fake_ticker) as p:
        client.fetch_klines("aapl")
    # 호출 인자 첫번째가 AAPL 이어야 함
    args, kwargs = p.call_args
    assert args[0] == "AAPL"


def test_fetch_klines_fresh_cache_hit_skips_network():
    """fresh 캐시에 hit 하면 yf.Ticker 호출 없이 반환."""
    r = fakeredis.FakeStrictRedis()
    # 미리 fresh 키 주입
    preloaded = [
        Kline(
            open_time=datetime.fromisoformat("2026-04-16T00:00:00+00:00"),
            open=180.0, high=181.0, low=179.5, close=180.5, volume=1_000_000,
        ),
    ]
    r.setex(
        "ohlcv:AAPL:1d:fresh",
        3600,
        json.dumps([k.to_dict() for k in preloaded]),
    )

    client = YFinanceClient(redis_client=r)
    with patch("sajucandle.market.yfinance.yf.Ticker") as p:
        klines = client.fetch_klines("AAPL")
        assert p.call_count == 0   # network skipped
    assert len(klines) == 1
    assert klines[0].close == 180.5


def test_fetch_klines_writes_fresh_and_backup_cache():
    """성공 시 fresh (3600) + backup (86400) 양쪽에 set."""
    df = _make_yf_dataframe(3)
    fake_ticker = MagicMock()
    fake_ticker.history.return_value = df

    r = fakeredis.FakeStrictRedis()
    client = YFinanceClient(redis_client=r)
    with patch("sajucandle.market.yfinance.yf.Ticker", return_value=fake_ticker):
        client.fetch_klines("AAPL")

    assert r.exists("ohlcv:AAPL:1d:fresh")
    assert r.exists("ohlcv:AAPL:1d:backup")
    # fresh TTL ~ 3600 이내
    ttl_fresh = r.ttl("ohlcv:AAPL:1d:fresh")
    assert 0 < ttl_fresh <= 3600
    ttl_backup = r.ttl("ohlcv:AAPL:1d:backup")
    assert 3600 < ttl_backup <= 86400


def test_fetch_klines_empty_dataframe_raises_unavailable():
    """yfinance가 빈 DataFrame 반환 시 MarketDataUnavailable (상장폐지 등)."""
    fake_ticker = MagicMock()
    fake_ticker.history.return_value = pd.DataFrame()
    client = YFinanceClient()
    with patch("sajucandle.market.yfinance.yf.Ticker", return_value=fake_ticker):
        with pytest.raises(MarketDataUnavailable):
            client.fetch_klines("AAPL")


def test_fetch_klines_network_error_uses_backup_cache():
    """yfinance 예외 시 backup 캐시 사용."""
    r = fakeredis.FakeStrictRedis()
    backup_klines = [
        Kline(
            open_time=datetime.fromisoformat("2026-04-15T00:00:00+00:00"),
            open=179.0, high=180.0, low=178.5, close=179.5, volume=900_000,
        ),
    ]
    r.setex(
        "ohlcv:AAPL:1d:backup",
        86400,
        json.dumps([k.to_dict() for k in backup_klines]),
    )

    client = YFinanceClient(redis_client=r)
    with patch(
        "sajucandle.market.yfinance.yf.Ticker",
        side_effect=RuntimeError("network down"),
    ):
        klines = client.fetch_klines("AAPL")
    assert len(klines) == 1
    assert klines[0].close == 179.5


def test_fetch_klines_network_error_no_backup_raises():
    """예외 + backup 없으면 MarketDataUnavailable."""
    client = YFinanceClient()
    with patch(
        "sajucandle.market.yfinance.yf.Ticker",
        side_effect=RuntimeError("boom"),
    ):
        with pytest.raises(MarketDataUnavailable):
            client.fetch_klines("AAPL")
```

- [ ] **Step 2: Run to verify fails**

```
pytest tests/test_market_yfinance.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'sajucandle.market.yfinance'`.

- [ ] **Step 3: Implement YFinanceClient.fetch_klines**

`src/sajucandle/market/yfinance.py`:

```python
"""yfinance 기반 미국주식 OHLCV 클라이언트.

Redis 2단 캐시:
  - ohlcv:{symbol}:{interval}:fresh   TTL=3600 (1시간)
  - ohlcv:{symbol}:{interval}:backup  TTL=86400 (24시간, 장애 fallback)

yfinance.Ticker.history()는 동기이며 내부적으로 HTTP 호출. 주말/휴장일에 호출하면
마지막 거래일까지의 DataFrame을 반환한다.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime
from typing import Any, Optional
from zoneinfo import ZoneInfo

import yfinance as yf

from sajucandle.market.base import UnsupportedTicker
from sajucandle.market_data import Kline, MarketDataUnavailable

logger = logging.getLogger(__name__)

_NY_TZ = ZoneInfo("America/New_York")
_SUPPORTED = frozenset({"AAPL", "MSFT", "GOOGL", "NVDA", "TSLA"})
_FRESH_TTL = 3600
_BACKUP_TTL = 86400


class YFinanceClient:
    def __init__(self, redis_client: Optional[Any] = None) -> None:
        self._redis = redis_client

    # ─────────────────────────────────────────────
    # Public
    # ─────────────────────────────────────────────

    def fetch_klines(
        self,
        symbol: str,
        interval: str = "1d",
        limit: int = 100,
    ) -> list[Kline]:
        sym = symbol.upper().lstrip("$")
        if sym not in _SUPPORTED:
            raise UnsupportedTicker(sym)

        fresh_key = f"ohlcv:{sym}:{interval}:fresh"
        backup_key = f"ohlcv:{sym}:{interval}:backup"

        cached = self._redis_get(fresh_key)
        if cached is not None:
            return cached

        try:
            klines = self._yf_fetch(sym, interval, limit)
        except Exception as e:
            logger.warning("yfinance fetch failed symbol=%s: %s", sym, e)
            backup = self._redis_get(backup_key)
            if backup is not None:
                logger.warning("using backup ohlcv cache for %s", sym)
                return backup
            raise MarketDataUnavailable(
                f"yfinance fetch failed and no backup cache: {e}"
            ) from e

        if not klines:
            raise MarketDataUnavailable(
                f"yfinance returned empty data for {sym}"
            )

        self._redis_set(fresh_key, klines, _FRESH_TTL)
        self._redis_set(backup_key, klines, _BACKUP_TTL)
        return klines

    # ─────────────────────────────────────────────
    # Internals
    # ─────────────────────────────────────────────

    def _yf_fetch(self, symbol: str, interval: str, limit: int) -> list[Kline]:
        """yfinance.Ticker.history() → list[Kline]."""
        ticker = yf.Ticker(symbol)
        # period="{limit}d"로 요청. 주말/휴장 포함되지 않으므로 limit 근처의 거래일 반환.
        df = ticker.history(period=f"{limit}d", interval=interval, auto_adjust=False)
        if df is None or df.empty:
            return []
        klines: list[Kline] = []
        for idx, row in df.iterrows():
            ts = idx.to_pydatetime() if hasattr(idx, "to_pydatetime") else idx
            klines.append(
                Kline(
                    open_time=ts,
                    open=float(row["Open"]),
                    high=float(row["High"]),
                    low=float(row["Low"]),
                    close=float(row["Close"]),
                    volume=float(row["Volume"]),
                )
            )
        return klines

    def _redis_get(self, key: str) -> Optional[list[Kline]]:
        if self._redis is None:
            return None
        try:
            raw = self._redis.get(key)
        except Exception as e:
            logger.warning("redis GET %s failed: %s", key, e)
            return None
        if raw is None:
            return None
        try:
            if isinstance(raw, (bytes, bytearray)):
                raw = raw.decode("utf-8")
            data = json.loads(raw)
            return [Kline.from_dict(d) for d in data]
        except Exception as e:
            logger.warning("redis %s deserialize failed: %s", key, e)
            return None

    def _redis_set(self, key: str, klines: list[Kline], ttl: int) -> None:
        if self._redis is None:
            return
        try:
            payload = json.dumps([k.to_dict() for k in klines])
            self._redis.setex(key, ttl, payload)
        except Exception as e:
            logger.warning("redis SETEX %s failed: %s", key, e)
```

- [ ] **Step 4: Run to verify PASS**

```
pytest tests/test_market_yfinance.py -v
```

Expected: 8 passed (fetch_klines 관련).

- [ ] **Step 5: Commit**

```
git add src/sajucandle/market/yfinance.py tests/test_market_yfinance.py
git commit -m "feat(market): add YFinanceClient.fetch_klines with Redis 2-tier cache"
```

---

## Task 5: YFinanceClient.is_market_open + last_session_date

**Files:**
- Modify: `src/sajucandle/market/yfinance.py`
- Modify: `tests/test_market_yfinance.py`

- [ ] **Step 1: Append failing tests**

`tests/test_market_yfinance.py` 맨 아래에 추가:

```python
# ─────────────────────────────────────────────
# is_market_open / last_session_date
# ─────────────────────────────────────────────

from datetime import date as date_cls
from zoneinfo import ZoneInfo


NY = ZoneInfo("America/New_York")


@patch("sajucandle.market.yfinance.datetime")
def test_is_market_open_weekday_mid_session(mock_dt):
    """수요일 12:00 ET → 장 중."""
    mock_dt.now.return_value = datetime(2026, 4, 15, 12, 0, tzinfo=NY)
    client = YFinanceClient()
    assert client.is_market_open("AAPL") is True


@patch("sajucandle.market.yfinance.datetime")
def test_is_market_open_weekday_before_open(mock_dt):
    """수요일 09:29 ET → 장 전."""
    mock_dt.now.return_value = datetime(2026, 4, 15, 9, 29, tzinfo=NY)
    client = YFinanceClient()
    assert client.is_market_open("AAPL") is False


@patch("sajucandle.market.yfinance.datetime")
def test_is_market_open_weekday_at_open(mock_dt):
    """수요일 정확히 09:30 ET → 장 시작 (inclusive)."""
    mock_dt.now.return_value = datetime(2026, 4, 15, 9, 30, tzinfo=NY)
    client = YFinanceClient()
    assert client.is_market_open("AAPL") is True


@patch("sajucandle.market.yfinance.datetime")
def test_is_market_open_weekday_at_close(mock_dt):
    """수요일 정확히 16:00 ET → 장 마감 직전 (inclusive)."""
    mock_dt.now.return_value = datetime(2026, 4, 15, 16, 0, tzinfo=NY)
    client = YFinanceClient()
    assert client.is_market_open("AAPL") is True


@patch("sajucandle.market.yfinance.datetime")
def test_is_market_open_weekday_after_close(mock_dt):
    """수요일 16:01 ET → 장 후."""
    mock_dt.now.return_value = datetime(2026, 4, 15, 16, 1, tzinfo=NY)
    client = YFinanceClient()
    assert client.is_market_open("AAPL") is False


@patch("sajucandle.market.yfinance.datetime")
def test_is_market_open_saturday(mock_dt):
    """토요일 어느 시각이든 False."""
    mock_dt.now.return_value = datetime(2026, 4, 18, 12, 0, tzinfo=NY)   # Sat
    client = YFinanceClient()
    assert client.is_market_open("AAPL") is False


@patch("sajucandle.market.yfinance.datetime")
def test_is_market_open_sunday(mock_dt):
    """일요일 어느 시각이든 False."""
    mock_dt.now.return_value = datetime(2026, 4, 19, 10, 0, tzinfo=NY)   # Sun
    client = YFinanceClient()
    assert client.is_market_open("AAPL") is False


def test_last_session_date_returns_last_kline_ny_date():
    """fetch_klines의 마지막 요소의 NY 날짜 반환."""
    df = _make_yf_dataframe(5)
    # DataFrame index 마지막은 2026-04-16 (기본값, NY tz)
    fake_ticker = MagicMock()
    fake_ticker.history.return_value = df
    client = YFinanceClient()
    with patch("sajucandle.market.yfinance.yf.Ticker", return_value=fake_ticker):
        d = client.last_session_date("AAPL")
    assert isinstance(d, date_cls)
    assert d == date_cls(2026, 4, 16)
```

참고: `_make_yf_dataframe`에서 `idx = pd.date_range(end="2026-04-16", periods=n, freq="B", tz="America/New_York")`로 생성되므로 마지막 인덱스는 2026-04-16 NY 날짜.

- [ ] **Step 2: Run to verify fails**

```
pytest tests/test_market_yfinance.py -v -k "is_market_open or last_session_date"
```

Expected: FAIL with `AttributeError: 'YFinanceClient' object has no attribute 'is_market_open'`.

- [ ] **Step 3: Import `datetime` at module level + implement methods**

`src/sajucandle/market/yfinance.py` — 파일 상단 import 섹션 확인. `datetime`이 이미 있으면 그대로, 없으면 추가:

```python
from datetime import date, datetime
```

`YFinanceClient` 클래스 `fetch_klines` 아래(Internals 위)에 추가:

```python
    def is_market_open(self, symbol: str) -> bool:
        """NYSE 정규장(ET 09:30~16:00, 주말 제외).

        공휴일은 커버하지 않는다 — 배지 정확도 < 복잡도 비용. 공휴일에는
        is_market_open=True 오판이 날 수 있으나 last_session_date는 정확하다
        (yfinance가 휴장일 데이터를 안 줌).
        """
        now_ny = datetime.now(_NY_TZ)
        if now_ny.weekday() >= 5:   # Sat=5, Sun=6
            return False
        open_t = now_ny.replace(hour=9, minute=30, second=0, microsecond=0)
        close_t = now_ny.replace(hour=16, minute=0, second=0, microsecond=0)
        return open_t <= now_ny <= close_t

    def last_session_date(self, symbol: str) -> date:
        """fetch_klines 마지막 캔들의 NY 날짜.

        주말/휴장일에도 금요일(직전 거래일)이 반환되므로 사용자에게 정확한
        '기준 날짜'를 표시할 수 있다.
        """
        klines = self.fetch_klines(symbol, limit=1)
        return klines[-1].open_time.astimezone(_NY_TZ).date()
```

- [ ] **Step 4: Run to verify PASS**

```
pytest tests/test_market_yfinance.py -v
```

Expected: 이전 8개 + 신규 8개 = 16 passed.

- [ ] **Step 5: Commit**

```
git add src/sajucandle/market/yfinance.py tests/test_market_yfinance.py
git commit -m "feat(market): add is_market_open/last_session_date to YFinanceClient"
```

---

## Task 6: Create market/router.py — MarketRouter + all_symbols()

**Files:**
- Create: `src/sajucandle/market/router.py`
- Create: `tests/test_market_router.py`

- [ ] **Step 1: Write failing tests**

`tests/test_market_router.py`:

```python
"""market.router: ticker → provider 라우팅."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from sajucandle.market.base import UnsupportedTicker
from sajucandle.market.router import MarketRouter


def _fake_providers():
    binance = MagicMock(name="binance")
    yfinance = MagicMock(name="yfinance")
    return binance, yfinance


def test_btcusdt_routes_to_binance():
    b, y = _fake_providers()
    r = MarketRouter(binance=b, yfinance=y)
    assert r.get_provider("BTCUSDT") is b


def test_aapl_routes_to_yfinance():
    b, y = _fake_providers()
    r = MarketRouter(binance=b, yfinance=y)
    assert r.get_provider("AAPL") is y


def test_unknown_ticker_raises():
    b, y = _fake_providers()
    r = MarketRouter(binance=b, yfinance=y)
    with pytest.raises(UnsupportedTicker):
        r.get_provider("AMZN")


def test_lowercase_is_normalized():
    b, y = _fake_providers()
    r = MarketRouter(binance=b, yfinance=y)
    assert r.get_provider("aapl") is y
    assert r.get_provider("btcusdt") is b


def test_dollar_prefix_is_stripped():
    b, y = _fake_providers()
    r = MarketRouter(binance=b, yfinance=y)
    assert r.get_provider("$AAPL") is y


def test_all_symbols_returns_full_catalog():
    b, y = _fake_providers()
    r = MarketRouter(binance=b, yfinance=y)
    symbols = r.all_symbols()
    tickers = [s["ticker"] for s in symbols]
    assert "BTCUSDT" in tickers
    assert "AAPL" in tickers
    assert "MSFT" in tickers
    assert "GOOGL" in tickers
    assert "NVDA" in tickers
    assert "TSLA" in tickers
    # 각 항목은 ticker/name/category를 가진다
    for s in symbols:
        assert set(s.keys()) >= {"ticker", "name", "category"}
        assert s["category"] in ("crypto", "us_stock")
```

- [ ] **Step 2: Run to verify fails**

```
pytest tests/test_market_router.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'sajucandle.market.router'`.

- [ ] **Step 3: Implement MarketRouter**

`src/sajucandle/market/router.py`:

```python
"""ticker 문자열을 BinanceClient 또는 YFinanceClient로 라우팅.

화이트리스트 기반. 그 외 심볼은 UnsupportedTicker.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sajucandle.market.base import MarketDataProvider, UnsupportedTicker


_CRYPTO_SYMBOLS = frozenset({"BTCUSDT"})
_STOCK_SYMBOLS = frozenset({"AAPL", "MSFT", "GOOGL", "NVDA", "TSLA"})


@dataclass
class MarketRouter:
    binance: MarketDataProvider
    yfinance: MarketDataProvider

    def get_provider(self, ticker: str) -> MarketDataProvider:
        sym = ticker.upper().lstrip("$")
        if sym in _CRYPTO_SYMBOLS:
            return self.binance
        if sym in _STOCK_SYMBOLS:
            return self.yfinance
        raise UnsupportedTicker(sym)

    @classmethod
    def all_symbols(cls) -> list[dict[str, str]]:
        """전체 지원 심볼 카탈로그. /v1/signal/symbols 및 /signal list용."""
        return [
            {"ticker": "BTCUSDT", "name": "Bitcoin", "category": "crypto"},
            {"ticker": "AAPL", "name": "Apple", "category": "us_stock"},
            {"ticker": "MSFT", "name": "Microsoft", "category": "us_stock"},
            {"ticker": "GOOGL", "name": "Alphabet", "category": "us_stock"},
            {"ticker": "NVDA", "name": "NVIDIA", "category": "us_stock"},
            {"ticker": "TSLA", "name": "Tesla", "category": "us_stock"},
        ]
```

- [ ] **Step 4: Run to verify PASS**

```
pytest tests/test_market_router.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```
git add src/sajucandle/market/router.py tests/test_market_router.py
git commit -m "feat(market): add MarketRouter + symbol catalog"
```

---

## Task 7: Add MarketStatus model to models.py

**Files:**
- Modify: `src/sajucandle/models.py` (SignalResponse 확장 + MarketStatus 추가)
- Modify: `tests/test_api_signal.py` (기존 signal response 검증에 market_status 추가, 일부만)

신규 필드는 `required` (default 없음). 기존 SignalResponse 생성 지점은 **Task 8/9에서 업데이트** — 이 태스크는 모델 자체만.

- [ ] **Step 1: Edit models.py**

`src/sajucandle/models.py` 맨 아래(SignalResponse 위)에 MarketStatus 추가하고 SignalResponse에 필드 삽입:

```python
class MarketStatus(BaseModel):
    """시장 개장 상태. 카드에 배지 표시용."""
    is_open: bool
    last_session_date: str   # ISO "YYYY-MM-DD" (주식=NY tz, crypto=UTC)
    category: Literal["crypto", "us_stock"]


class SignalResponse(BaseModel):
    chat_id: int
    ticker: str
    date: str             # "2026-04-16"
    price: PricePoint
    saju: SajuSummary
    chart: ChartSummary
    composite_score: int = Field(ge=0, le=100)
    signal_grade: str     # "강진입" | "진입" | "관망" | "회피"
    best_hours: List[HourRecommendation]
    market_status: MarketStatus
```

기존 `SignalResponse`의 정의를 찾아 `best_hours` 다음 줄에 `market_status: MarketStatus` 추가, 그리고 위 `class MarketStatus(BaseModel): ...` 블록을 SignalResponse 정의 직전에 넣는다.

- [ ] **Step 2: Run full test suite to see what breaks**

```
pytest -q
```

Expected: `test_signal_service.py`에서 SignalResponse 생성 누락으로 `ValidationError` 발생.

- [ ] **Step 3: Patch the minimum to make the import-level tests pass**

이 태스크는 모델만 다룬다. SignalService/api는 다음 태스크에서 수정. 여기선 모델 임포트가 정상인지만 확인.

```
python -c "from sajucandle.models import MarketStatus, SignalResponse; print('ok')"
```

Expected: `ok` 출력.

**주의:** Step 2에서 깨진 테스트는 Task 8/9 완료 시점에 전량 복구된다. 중간 커밋에서는 일시적으로 실패 상태.

- [ ] **Step 4: Commit (intermediate — tests will fail until Task 9)**

```
git add src/sajucandle/models.py
git commit -m "feat(models): add MarketStatus + extend SignalResponse

NOTE: This commit temporarily breaks SignalService tests.
Fixed in subsequent commits (Task 8 signal_service refactor)."
```

---

## Task 8: Refactor SignalService to use MarketRouter + populate market_status

**Files:**
- Modify: `src/sajucandle/signal_service.py`
- Modify: `tests/test_signal_service.py`

- [ ] **Step 1: Update existing tests to reflect new API**

`tests/test_signal_service.py`의 `_FakeMarketClient` 클래스 아래에 헬퍼 함수 추가 (파일 상단 import 근처에도 추가 import):

파일 상단 import 섹션에 추가:
```python
from sajucandle.market.base import UnsupportedTicker
from sajucandle.market.router import MarketRouter
```

`_FakeMarketClient` 정의 바로 아래에 삽입:

```python
def _make_fake_market_client(klines: Optional[list[Kline]] = None,
                              raise_exc: Exception = None) -> _FakeMarketClient:
    """테스트용 fake provider. is_market_open=True, last_session_date=오늘 UTC."""
    fake = _FakeMarketClient(klines=klines, raise_exc=raise_exc)

    from datetime import datetime as _dt, timezone as _tz
    fake.is_market_open = lambda symbol: True
    fake.last_session_date = lambda symbol: _dt.now(_tz.utc).date()
    return fake


def _make_router(
    fake_client: _FakeMarketClient,
) -> MarketRouter:
    """_FakeMarketClient를 양쪽 슬롯에 꽂은 MarketRouter.

    get_provider는 ticker로 분기하지만 테스트에서는 같은 fake로 양쪽 모두 반환.
    """
    return MarketRouter(binance=fake_client, yfinance=fake_client)
```

그리고 기존 `SignalService(..., market_client=fake, ...)` 호출 **전부** 를 찾아서 `market_router=_make_router(fake)` 로 교체. 파일 끝까지 `market_client=`로 검색해서 모두 바꾼다. `_make_fake_market_client(...)`를 사용해 fake 생성 시 is_market_open/last_session_date도 세팅.

또한 SignalResponse에 `market_status` 필드가 추가됐으므로, response 검증하는 테스트에서 `resp.market_status.is_open`, `resp.market_status.last_session_date`, `resp.market_status.category` 검증 최소 1개 추가:

```python
def test_signal_compute_populates_market_status():
    fake = _make_fake_market_client()
    score_svc = _make_score_service()
    svc = SignalService(
        score_service=score_svc,
        market_router=_make_router(fake),
    )
    resp = svc.compute(_profile(), date(2026, 4, 16), "BTCUSDT")
    assert resp.market_status.is_open is True
    assert resp.market_status.category in ("crypto", "us_stock")
    # last_session_date는 ISO 문자열
    assert len(resp.market_status.last_session_date) == 10
```

- [ ] **Step 2: Run tests to see them fail (signature mismatch / missing router)**

```
pytest tests/test_signal_service.py -v
```

Expected: FAIL with `TypeError: SignalService.__init__() got an unexpected keyword argument 'market_router'` 또는 유사.

- [ ] **Step 3: Refactor SignalService**

`src/sajucandle/signal_service.py`를 다음과 같이 수정:

파일 상단 import 변경:

```python
from sajucandle.market.base import MarketDataProvider
from sajucandle.market.router import MarketRouter
from sajucandle.market_data import Kline, MarketDataUnavailable   # re-export
```

(기존 `from sajucandle.market_data import BinanceClient, Kline`에서 BinanceClient 제거)

`SignalService.__init__` 시그니처 변경:

```python
class SignalService:
    def __init__(
        self,
        score_service: ScoreService,
        market_router: MarketRouter,
        redis_client=None,
    ):
        self._score = score_service
        self._router = market_router
        self._redis = redis_client
```

`compute()` 메서드 내부에서 market_client → router.get_provider 사용:

```python
    def compute(
        self,
        profile: UserProfile,
        target_date: date,
        ticker: str,
    ) -> SignalResponse:
        cache_key = (
            f"signal:{profile.telegram_chat_id}:{target_date.isoformat()}:{ticker}"
        )

        cached = self._redis_get(cache_key)
        if cached is not None:
            return cached

        saju_resp = self._score.compute(
            profile, target_date, profile.asset_class_pref
        )

        # ticker → provider 라우팅 (UnsupportedTicker는 상위로 전파)
        provider = self._router.get_provider(ticker)

        klines: list[Kline] = provider.fetch_klines(ticker, interval="1d", limit=100)
        closes = [k.close for k in klines]
        volumes = [k.volume for k in klines]
        chart_b = score_chart(closes, volumes)

        current = klines[-1].close
        prev = klines[-2].close if len(klines) >= 2 else current
        change_pct = ((current / prev) - 1.0) * 100 if prev else 0.0

        final = round(0.4 * saju_resp.composite_score + 0.6 * chart_b.score)
        final = max(0, min(100, final))
        grade = _grade_signal(final)

        # market_status 채우기
        from sajucandle.models import MarketStatus
        is_crypto = ticker.upper().lstrip("$") == "BTCUSDT"
        market_status = MarketStatus(
            is_open=provider.is_market_open(ticker),
            last_session_date=provider.last_session_date(ticker).isoformat(),
            category="crypto" if is_crypto else "us_stock",
        )

        resp = SignalResponse(
            chat_id=profile.telegram_chat_id,
            ticker=ticker,
            date=target_date.isoformat(),
            price=PricePoint(current=current, change_pct_24h=change_pct),
            saju=SajuSummary(
                composite=saju_resp.composite_score,
                grade=saju_resp.signal_grade,
            ),
            chart=ChartSummary(
                score=chart_b.score,
                rsi=chart_b.rsi_value,
                ma20=chart_b.ma20,
                ma50=chart_b.ma50,
                ma_trend=chart_b.ma_trend,  # type: ignore[arg-type]
                volume_ratio=chart_b.volume_ratio_value,
                reason=chart_b.reason,
            ),
            composite_score=final,
            signal_grade=grade,
            best_hours=saju_resp.best_hours,
            market_status=market_status,
        )

        self._redis_set(cache_key, resp)
        return resp
```

- [ ] **Step 4: Run tests PASS**

```
pytest tests/test_signal_service.py -v
```

Expected: 기존 테스트 + 신규 `test_signal_compute_populates_market_status` PASS.

- [ ] **Step 5: Run full suite**

```
pytest -q
```

Expected: `test_api*` 파일 일부는 여전히 실패 (다음 태스크에서 수정). `test_signal_service.py`는 전량 통과.

- [ ] **Step 6: Commit**

```
git add src/sajucandle/signal_service.py tests/test_signal_service.py
git commit -m "refactor(signal): SignalService uses MarketRouter + market_status field"
```

---

## Task 9: Update api.py — MarketRouter DI, remove BTCUSDT-only guard, UnsupportedTicker→400

**Files:**
- Modify: `src/sajucandle/api.py`
- Modify: `tests/test_api_signal.py`

- [ ] **Step 1: Update failing tests first**

`tests/test_api_signal.py` 읽어서 기존 테스트 확인:

```
grep -n "ticker" tests/test_api_signal.py
```

기존 `"ticker must be BTCUSDT"` 검증 테스트를 찾아서 **삭제** 또는 **반대 검증으로 수정**:

기존 케이스 교체 예시 (파일 상단 import 근처에 helper가 있다면 그대로 활용):

```python
def test_signal_endpoint_rejects_unsupported_ticker(monkeypatch, client, db_registered_user):
    """AMZN 같은 화이트리스트 외 심볼은 400."""
    resp = client.get(
        f"/v1/users/{db_registered_user}/signal",
        params={"ticker": "AMZN"},
        headers={"X-SAJUCANDLE-KEY": "test-key"},
    )
    assert resp.status_code == 400
    assert "unsupported" in resp.json()["detail"].lower()


def test_signal_endpoint_accepts_aapl(monkeypatch, client, db_registered_user, stub_yfinance):
    """AAPL은 정상 처리되어 market_status.category='us_stock' 반환."""
    resp = client.get(
        f"/v1/users/{db_registered_user}/signal",
        params={"ticker": "AAPL"},
        headers={"X-SAJUCANDLE-KEY": "test-key"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ticker"] == "AAPL"
    assert body["market_status"]["category"] == "us_stock"
```

**단, `client`, `db_registered_user`, `stub_yfinance` 픽스처가 기존 파일에 있는지 먼저 확인.**
- 없으면 `conftest.py` 규약을 파악해 새로 작성하거나, `test_api_signal.py` 내에서 roll-your-own fixture로 build.
- `stub_yfinance`는 기존에 없으므로 Task 9 범위 내에서 만들어야 한다.

Step 1-a: `test_api_signal.py` 상단에 stub 픽스처 추가:

```python
from unittest.mock import patch, MagicMock
import pandas as pd


@pytest.fixture
def stub_yfinance():
    """yfinance.Ticker를 mock해서 일정한 AAPL DataFrame 반환."""
    idx = pd.date_range(end="2026-04-16", periods=100, freq="B", tz="America/New_York")
    df = pd.DataFrame({
        "Open": [180.0 + i * 0.3 for i in range(100)],
        "High": [180.5 + i * 0.3 for i in range(100)],
        "Low": [179.5 + i * 0.3 for i in range(100)],
        "Close": [180.2 + i * 0.3 for i in range(100)],
        "Volume": [50_000_000] * 100,
    }, index=idx)
    fake = MagicMock()
    fake.history.return_value = df
    with patch("sajucandle.market.yfinance.yf.Ticker", return_value=fake):
        yield
```

기존 BTCUSDT-only 검증 테스트 (`test_signal_endpoint_rejects_non_btc` 같은 이름)는 **삭제**한다.

- [ ] **Step 2: Run tests to verify fails**

```
pytest tests/test_api_signal.py -v
```

Expected: 새 테스트가 yfinance/router DI 없어 FAIL. 또는 기존 BTCUSDT-only 테스트 시그니처 깨짐.

- [ ] **Step 3: Update api.py**

`src/sajucandle/api.py` 변경사항:

**(a) import 추가:**
```python
from sajucandle.market.base import UnsupportedTicker
from sajucandle.market.router import MarketRouter
from sajucandle.market.yfinance import YFinanceClient
```

**(b) `_build_signal_service` 함수 교체:**

기존 (약 115-130줄):
```python
    def _build_signal_service() -> SignalService:
        redis_url = os.environ.get("REDIS_URL")
        redis_client = None
        if redis_url:
            try:
                import redis as redis_lib
                redis_client = redis_lib.from_url(redis_url)
                redis_client.ping()
            except Exception:
                redis_client = None
        market_client = BinanceClient(redis_client=redis_client, timeout=3.0)
        return SignalService(
            score_service=score_service,
            market_client=market_client,
            redis_client=redis_client,
        )
```

교체:
```python
    def _build_signal_service() -> SignalService:
        redis_url = os.environ.get("REDIS_URL")
        redis_client = None
        if redis_url:
            try:
                import redis as redis_lib
                redis_client = redis_lib.from_url(redis_url)
                redis_client.ping()
            except Exception:
                redis_client = None
        binance = BinanceClient(redis_client=redis_client, timeout=3.0)
        yfinance_client = YFinanceClient(redis_client=redis_client)
        router = MarketRouter(binance=binance, yfinance=yfinance_client)
        return SignalService(
            score_service=score_service,
            market_router=router,
            redis_client=redis_client,
        )
```

**(c) `signal_endpoint` 함수 내부 수정:**

기존 BTCUSDT 가드 (약 307-309줄):
```python
        # Week 4: BTCUSDT만 허용
        if ticker != "BTCUSDT":
            raise HTTPException(400, detail="ticker must be BTCUSDT (Week 4 limit)")
```

**삭제.** 대신 `signal_service.compute()` 호출 지점의 `except` 블록에 `UnsupportedTicker` 추가:

기존:
```python
        try:
            result = signal_service.compute(profile, target, ticker)
        except MarketDataUnavailable as e:
            logger.warning("signal market data unavailable: %s", e)
            raise HTTPException(502, detail="chart data unavailable")
        except Exception as e:
            logger.exception("signal compute failed")
            raise HTTPException(400, detail=f"신호 계산 실패: {type(e).__name__}")
```

교체:
```python
        try:
            result = signal_service.compute(profile, target, ticker)
        except UnsupportedTicker as e:
            raise HTTPException(400, detail=f"unsupported ticker: {e.symbol}")
        except MarketDataUnavailable as e:
            logger.warning("signal market data unavailable: %s", e)
            raise HTTPException(502, detail="chart data unavailable")
        except Exception as e:
            logger.exception("signal compute failed")
            raise HTTPException(400, detail=f"신호 계산 실패: {type(e).__name__}")
```

- [ ] **Step 4: Run tests PASS**

```
pytest tests/test_api_signal.py -v
```

Expected: 새로 추가한 2개 + 나머지 기존(BTCUSDT 거부 테스트 삭제 후) 통과.

- [ ] **Step 5: Run full suite**

```
pytest -q
```

Expected: 전량 통과 또는 `test_api.py`의 /v1/signal/symbols 관련 테스트만 실패 (다음 태스크).

- [ ] **Step 6: Commit**

```
git add src/sajucandle/api.py tests/test_api_signal.py
git commit -m "feat(api): wire MarketRouter DI, accept AAPL/MSFT/GOOGL/NVDA/TSLA in /signal"
```

---

## Task 10: Add /v1/signal/symbols endpoint

**Files:**
- Modify: `src/sajucandle/api.py`
- Modify: `tests/test_api.py`

- [ ] **Step 1: Write failing tests**

`tests/test_api.py` 맨 아래에 추가:

```python
def test_signal_symbols_requires_api_key(client):
    resp = client.get("/v1/signal/symbols")
    assert resp.status_code == 401


def test_signal_symbols_returns_catalog(client):
    resp = client.get(
        "/v1/signal/symbols",
        headers={"X-SAJUCANDLE-KEY": "test-key"},
    )
    assert resp.status_code == 200
    body = resp.json()
    tickers = [s["ticker"] for s in body["symbols"]]
    assert "BTCUSDT" in tickers
    assert "AAPL" in tickers
    assert "MSFT" in tickers
    assert "GOOGL" in tickers
    assert "NVDA" in tickers
    assert "TSLA" in tickers
    for s in body["symbols"]:
        assert set(s.keys()) >= {"ticker", "name", "category"}
```

**client 픽스처**는 기존 `test_api.py`에 이미 있을 것 (없으면 conftest 확인). 인증 없는 경우 앱이 `SAJUCANDLE_API_KEY=test-key`로 env 세팅되어 있어야 401을 반환. `test_api.py` 상단 로직 확인.

- [ ] **Step 2: Run tests to verify fails**

```
pytest tests/test_api.py -v -k "signal_symbols"
```

Expected: FAIL with 404 (endpoint 없음).

- [ ] **Step 3: Add endpoint in api.py**

`src/sajucandle/api.py`의 `signal_endpoint` 함수 정의 바로 위(혹은 다른 `/v1/` 엔드포인트 정의 근처)에 삽입:

```python
    @app.get("/v1/signal/symbols")
    async def signal_symbols_endpoint(
        request: Request,
        x_sajucandle_key: Optional[str] = Header(default=None),
    ):
        """지원 심볼 카탈로그. 봇 /signal list용."""
        _require_api_key(request, x_sajucandle_key)
        return {"symbols": MarketRouter.all_symbols()}
```

- [ ] **Step 4: Run tests PASS**

```
pytest tests/test_api.py -v -k "signal_symbols"
```

Expected: 2 passed.

- [ ] **Step 5: Run full suite**

```
pytest -q
```

Expected: 전량 통과.

- [ ] **Step 6: Commit**

```
git add src/sajucandle/api.py tests/test_api.py
git commit -m "feat(api): add GET /v1/signal/symbols catalog endpoint"
```

---

## Task 11: Add get_supported_symbols to api_client.py

**Files:**
- Modify: `src/sajucandle/api_client.py`
- Modify: `tests/test_api_client.py`

- [ ] **Step 1: Write failing test**

`tests/test_api_client.py` 맨 아래에 추가:

```python
import pytest

@pytest.mark.asyncio
async def test_get_supported_symbols_returns_list():
    """지원 심볼 목록 API 응답을 파싱."""
    import respx
    from httpx import Response
    from sajucandle.api_client import ApiClient

    with respx.mock(base_url="http://test") as mock:
        mock.get("/v1/signal/symbols").mock(
            return_value=Response(
                200,
                json={
                    "symbols": [
                        {"ticker": "BTCUSDT", "name": "Bitcoin", "category": "crypto"},
                        {"ticker": "AAPL", "name": "Apple", "category": "us_stock"},
                    ]
                },
            )
        )
        c = ApiClient(base_url="http://test", api_key="k")
        out = await c.get_supported_symbols()
    assert out == [
        {"ticker": "BTCUSDT", "name": "Bitcoin", "category": "crypto"},
        {"ticker": "AAPL", "name": "Apple", "category": "us_stock"},
    ]


@pytest.mark.asyncio
async def test_get_supported_symbols_401():
    """인증 실패 시 ApiError."""
    import respx
    from httpx import Response
    from sajucandle.api_client import ApiClient, ApiError

    with respx.mock(base_url="http://test") as mock:
        mock.get("/v1/signal/symbols").mock(
            return_value=Response(401, json={"detail": "invalid key"})
        )
        c = ApiClient(base_url="http://test", api_key="wrong")
        with pytest.raises(ApiError) as exc:
            await c.get_supported_symbols()
    assert exc.value.status == 401
```

- [ ] **Step 2: Run tests to fail**

```
pytest tests/test_api_client.py -v -k "supported_symbols"
```

Expected: FAIL with `AttributeError: 'ApiClient' object has no attribute 'get_supported_symbols'`.

- [ ] **Step 3: Add method in api_client.py**

`ApiClient` 클래스 마지막(`get_signal` 아래)에 추가:

```python
    async def get_supported_symbols(self) -> list[dict]:
        """GET /v1/signal/symbols. 반환: [{ticker,name,category}, ...]."""
        async with self._client() as c:
            r = await c.get("/v1/signal/symbols")
        await self._raise_for_status(r)
        data = r.json()
        return list(data.get("symbols", []))
```

- [ ] **Step 4: Run tests PASS**

```
pytest tests/test_api_client.py -v
```

Expected: 신규 2개 + 기존 전량 통과.

- [ ] **Step 5: Commit**

```
git add src/sajucandle/api_client.py tests/test_api_client.py
git commit -m "feat(api_client): add get_supported_symbols()"
```

---

## Task 12: Update handlers.py — /signal arg parsing, /signal list, card with market_status badge, /help

**Files:**
- Modify: `src/sajucandle/handlers.py`
- Modify: `tests/test_handlers.py`

- [ ] **Step 1: Write failing tests**

`tests/test_handlers.py`의 signal_command 관련 테스트 섹션에 추가 (없으면 파일 맨 아래 새 섹션):

```python
# ─────────────────────────────────────────────
# Week 6: /signal 심볼 인자, /signal list, 배지
# ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_signal_no_arg_uses_btcusdt(monkeypatch):
    """`/signal` (인자 없음) → ticker=BTCUSDT."""
    from sajucandle import handlers
    from unittest.mock import AsyncMock, MagicMock

    # api_client.get_signal을 capture
    captured = {}
    async def fake_get_signal(chat_id, ticker="BTCUSDT", date=None):
        captured["ticker"] = ticker
        return _btc_signal_payload()

    monkeypatch.setattr(handlers, "_api_client",
                        MagicMock(get_signal=fake_get_signal))

    update = _make_update(text="/signal", chat_id=42)
    context = MagicMock(args=[])
    update.message.reply_text = AsyncMock()

    await handlers.signal_command(update, context)
    assert captured["ticker"] == "BTCUSDT"


@pytest.mark.asyncio
async def test_signal_aapl_routes_to_stock(monkeypatch):
    """`/signal AAPL` → ticker=AAPL."""
    from sajucandle import handlers
    from unittest.mock import AsyncMock, MagicMock

    captured = {}
    async def fake_get_signal(chat_id, ticker="BTCUSDT", date=None):
        captured["ticker"] = ticker
        return _aapl_signal_payload()

    monkeypatch.setattr(handlers, "_api_client",
                        MagicMock(get_signal=fake_get_signal))

    update = _make_update(text="/signal AAPL", chat_id=42)
    context = MagicMock(args=["AAPL"])
    update.message.reply_text = AsyncMock()

    await handlers.signal_command(update, context)
    assert captured["ticker"] == "AAPL"


@pytest.mark.asyncio
async def test_signal_lowercase_aapl_is_normalized(monkeypatch):
    """`/signal aapl` → AAPL."""
    from sajucandle import handlers
    from unittest.mock import AsyncMock, MagicMock

    captured = {}
    async def fake_get_signal(chat_id, ticker="BTCUSDT", date=None):
        captured["ticker"] = ticker
        return _aapl_signal_payload()

    monkeypatch.setattr(handlers, "_api_client",
                        MagicMock(get_signal=fake_get_signal))
    context = MagicMock(args=["aapl"])
    update = _make_update(text="/signal aapl", chat_id=42)
    update.message.reply_text = AsyncMock()

    await handlers.signal_command(update, context)
    assert captured["ticker"] == "AAPL"


@pytest.mark.asyncio
async def test_signal_dollar_prefix_stripped(monkeypatch):
    """`/signal $AAPL` → AAPL."""
    from sajucandle import handlers
    from unittest.mock import AsyncMock, MagicMock

    captured = {}
    async def fake_get_signal(chat_id, ticker="BTCUSDT", date=None):
        captured["ticker"] = ticker
        return _aapl_signal_payload()

    monkeypatch.setattr(handlers, "_api_client",
                        MagicMock(get_signal=fake_get_signal))
    context = MagicMock(args=["$AAPL"])
    update = _make_update(text="/signal $AAPL", chat_id=42)
    update.message.reply_text = AsyncMock()

    await handlers.signal_command(update, context)
    assert captured["ticker"] == "AAPL"


@pytest.mark.asyncio
async def test_signal_list_fetches_catalog(monkeypatch):
    """`/signal list` → get_supported_symbols 호출 + 메시지에 티커 포함."""
    from sajucandle import handlers
    from unittest.mock import AsyncMock, MagicMock

    async def fake_symbols():
        return [
            {"ticker": "BTCUSDT", "name": "Bitcoin", "category": "crypto"},
            {"ticker": "AAPL", "name": "Apple", "category": "us_stock"},
        ]

    monkeypatch.setattr(handlers, "_api_client",
                        MagicMock(get_supported_symbols=fake_symbols,
                                   get_signal=AsyncMock()))
    context = MagicMock(args=["list"])
    update = _make_update(text="/signal list", chat_id=42)
    update.message.reply_text = AsyncMock()

    await handlers.signal_command(update, context)
    sent = update.message.reply_text.call_args[0][0]
    assert "BTCUSDT" in sent
    assert "AAPL" in sent


@pytest.mark.asyncio
async def test_signal_unknown_symbol_shows_list_hint(monkeypatch):
    """`/signal UNKNOWN` → API 400 → 안내 문구."""
    from sajucandle import handlers
    from sajucandle.api_client import ApiError
    from unittest.mock import AsyncMock, MagicMock

    async def fake_get_signal(chat_id, ticker="BTCUSDT", date=None):
        raise ApiError(400, "unsupported ticker: UNKNOWN")

    monkeypatch.setattr(handlers, "_api_client",
                        MagicMock(get_signal=fake_get_signal))
    context = MagicMock(args=["UNKNOWN"])
    update = _make_update(text="/signal UNKNOWN", chat_id=42)
    update.message.reply_text = AsyncMock()

    await handlers.signal_command(update, context)
    sent = update.message.reply_text.call_args[0][0]
    assert "지원하지 않" in sent or "list" in sent.lower()


@pytest.mark.asyncio
async def test_signal_aapl_card_shows_closed_badge(monkeypatch):
    """휴장 상태의 AAPL 응답 → 카드에 '휴장 중' + 기준 날짜 포함."""
    from sajucandle import handlers
    from unittest.mock import AsyncMock, MagicMock

    payload = _aapl_signal_payload()
    payload["market_status"] = {
        "is_open": False,
        "last_session_date": "2026-04-16",
        "category": "us_stock",
    }

    async def fake_get_signal(chat_id, ticker="BTCUSDT", date=None):
        return payload

    monkeypatch.setattr(handlers, "_api_client",
                        MagicMock(get_signal=fake_get_signal))
    context = MagicMock(args=["AAPL"])
    update = _make_update(text="/signal AAPL", chat_id=42)
    update.message.reply_text = AsyncMock()

    await handlers.signal_command(update, context)
    sent = update.message.reply_text.call_args[0][0]
    assert "휴장" in sent
    assert "2026-04-16" in sent


@pytest.mark.asyncio
async def test_signal_btc_card_has_no_badge_line(monkeypatch):
    """BTC 응답은 배지 줄을 표시하지 않는다 (기존 포맷 유지)."""
    from sajucandle import handlers
    from unittest.mock import AsyncMock, MagicMock

    payload = _btc_signal_payload()
    payload["market_status"] = {
        "is_open": True,
        "last_session_date": "2026-04-16",
        "category": "crypto",
    }

    async def fake_get_signal(chat_id, ticker="BTCUSDT", date=None):
        return payload

    monkeypatch.setattr(handlers, "_api_client",
                        MagicMock(get_signal=fake_get_signal))
    context = MagicMock(args=[])
    update = _make_update(text="/signal", chat_id=42)
    update.message.reply_text = AsyncMock()

    await handlers.signal_command(update, context)
    sent = update.message.reply_text.call_args[0][0]
    assert "휴장" not in sent
    assert "장 중" not in sent
```

**헬퍼 함수** — `tests/test_handlers.py` 상단(또는 기존 헬퍼 섹션)에 추가:

```python
def _make_update(text: str, chat_id: int):
    """가짜 Telegram Update 객체."""
    from unittest.mock import MagicMock
    update = MagicMock()
    update.message = MagicMock()
    update.message.text = text
    update.effective_chat = MagicMock()
    update.effective_chat.id = chat_id
    return update


def _btc_signal_payload() -> dict:
    return {
        "ticker": "BTCUSDT",
        "date": "2026-04-16",
        "price": {"current": 72000.0, "change_pct_24h": 1.5},
        "saju": {"composite": 56, "grade": "😐 관망"},
        "chart": {"score": 72, "rsi": 60.0, "ma20": 71000.0, "ma50": 69000.0,
                   "ma_trend": "up", "volume_ratio": 1.2,
                   "reason": "MA 우상향"},
        "composite_score": 66,
        "signal_grade": "진입",
        "best_hours": [],
        "market_status": {"is_open": True, "last_session_date": "2026-04-16",
                           "category": "crypto"},
    }


def _aapl_signal_payload() -> dict:
    return {
        "ticker": "AAPL",
        "date": "2026-04-16",
        "price": {"current": 184.12, "change_pct_24h": 1.23},
        "saju": {"composite": 56, "grade": "😐 관망"},
        "chart": {"score": 72, "rsi": 62.0, "ma20": 180.0, "ma50": 175.0,
                   "ma_trend": "up", "volume_ratio": 1.1,
                   "reason": "MA 우상향, RSI 62"},
        "composite_score": 66,
        "signal_grade": "진입",
        "best_hours": [],
        "market_status": {"is_open": True, "last_session_date": "2026-04-16",
                           "category": "us_stock"},
    }
```

(이미 기존 `test_handlers.py`에 helper가 있으면 중복 선언 피하고 재사용.)

- [ ] **Step 2: Run tests to verify fails**

```
pytest tests/test_handlers.py -v -k "signal"
```

Expected: FAIL with various (현재 signal_command는 args 무시, /signal list 모름, 배지 안 씀).

- [ ] **Step 3: Rewrite signal_command + add _show_symbol_list + update /help**

`src/sajucandle/handlers.py`의 `signal_command` 전체를 다음으로 교체:

```python
async def signal_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """`/signal [심볼|list]`. 사주 + 차트 결합 신호.

    · 인자 없음: BTCUSDT
    · `/signal list`: 지원 심볼 목록
    · 그 외: 해당 심볼 조회 (내부에서 upper + $제거 정규화)
    """
    if update.message is None:
        return
    chat_id = update.effective_chat.id
    args = list(context.args or [])

    # 서브커맨드: list
    if args and args[0].lower() == "list":
        await _show_symbol_list(update)
        return

    # ticker 정규화
    if args:
        ticker = args[0].upper().lstrip("$")
    else:
        ticker = "BTCUSDT"

    try:
        data = await _api_client.get_signal(chat_id, ticker=ticker)
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
        if e.status == 400 and "unsupported" in (e.detail or "").lower():
            await update.message.reply_text(
                f"지원하지 않는 심볼: {ticker}\n"
                f"/signal list 로 지원 심볼을 확인하세요."
            )
        elif e.status == 502:
            await update.message.reply_text("시장 데이터 일시 불능. 잠시 후 다시.")
        else:
            logger.warning(
                "signal api error chat_id=%s status=%s", chat_id, e.status
            )
            await update.message.reply_text(f"서버 오류 ({e.status}).")
        return
    except Exception:
        logger.exception("signal_command unexpected error chat_id=%s", chat_id)
        await update.message.reply_text("예기치 못한 오류가 발생했습니다.")
        return

    logger.info(
        "signal ok chat_id=%s ticker=%s composite=%s grade=%s",
        chat_id, data["ticker"], data["composite_score"], data["signal_grade"],
    )

    await update.message.reply_text(_format_signal_card(data))


def _format_signal_card(data: dict) -> str:
    """/signal 응답 dict → 카드 문자열.

    BTC(crypto): 배지 줄 생략 (기존 포맷 유지)
    US stocks: `🟢 장 중` 또는 `🕐 휴장 중 · 기준: YYYY-MM-DD` 배지 표시
    """
    price = data["price"]
    saju = data["saju"]
    chart = data["chart"]
    status = data.get("market_status") or {}
    category = status.get("category", "crypto")

    change_sign = "+" if price["change_pct_24h"] >= 0 else ""
    lines = [f"── {data['date']} {data['ticker']} ──"]

    if category == "us_stock":
        if status.get("is_open"):
            lines.append("🟢 장 중")
        else:
            last = status.get("last_session_date", "")
            lines.append(f"🕐 휴장 중 · 기준: {last} 종가")

    lines.extend([
        f"현재가: ${price['current']:,.2f} "
        f"({change_sign}{price['change_pct_24h']:.2f}%)",
        "────────────────",
        f"사주 점수: {saju['composite']:>3} ({saju['grade']})",
        f"차트 점수: {chart['score']:>3} ({chart['reason']})",
        "────────────────",
        f"종합: {data['composite_score']:>3} | {data['signal_grade']}",
    ])
    if data.get("best_hours"):
        hrs = ", ".join(
            f"{h['shichen']}시 {h['time_range']}" for h in data["best_hours"]
        )
        lines.append(f"추천 시진: {hrs}")
    lines.append("")
    lines.append("※ 엔터테인먼트 목적. 투자 추천 아님.")
    return "\n".join(lines)


async def _show_symbol_list(update: Update) -> None:
    """`/signal list` — 지원 심볼 카탈로그 표시."""
    try:
        symbols = await _api_client.get_supported_symbols()
    except (httpx.TimeoutException, httpx.TransportError):
        await update.message.reply_text("서버에 연결할 수 없습니다.")
        return
    except ApiError as e:
        await update.message.reply_text(f"서버 오류 ({e.status}).")
        return

    crypto = [s for s in symbols if s.get("category") == "crypto"]
    stocks = [s for s in symbols if s.get("category") == "us_stock"]
    lines = ["지원 심볼:", "────────────"]
    if crypto:
        lines.append("암호화폐")
        for s in crypto:
            lines.append(f"  · {s['ticker']} — {s['name']}")
        lines.append("")
    if stocks:
        lines.append("미국주식")
        for s in stocks:
            lines.append(f"  · {s['ticker']} — {s['name']}")
        lines.append("")
    lines.append("사용법: /signal AAPL")
    await update.message.reply_text("\n".join(lines))
```

**help_command 업데이트** — 파일 맨 아래 `help_command` 내부 reply_text 문자열을 다음으로 교체:

```python
    await update.message.reply_text(
        "SajuCandle 봇 사용법\n"
        "─────────────\n"
        "/start YYYY-MM-DD HH:MM — 생년월일시 등록\n"
        "/score [swing|scalp|long] — 오늘 사주 점수\n"
        "/signal [심볼] — 사주+차트 결합 신호\n"
        "  · 심볼 생략: BTC\n"
        "  · 지원: BTCUSDT, AAPL, MSFT, GOOGL, NVDA, TSLA\n"
        "  · /signal list — 전체 목록\n"
        "/me — 등록된 정보 확인\n"
        "/forget — 내 정보 삭제\n"
        "/help — 이 도움말\n"
        "\n※ 엔터테인먼트 목적. 투자 추천 아님."
    )
```

- [ ] **Step 4: Run tests PASS**

```
pytest tests/test_handlers.py -v
```

Expected: 신규 + 기존 전량 통과.

- [ ] **Step 5: Run full suite**

```
pytest -q
```

Expected: 전량 통과 (153+기존 + 새 테스트).

- [ ] **Step 6: Commit**

```
git add src/sajucandle/handlers.py tests/test_handlers.py
git commit -m "feat(bot): /signal [SYMBOL|list] with market_status badge"
```

---

## Task 13: Final verification + README update + push

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Lint check**

```
ruff check src/ tests/
```

Expected: 0 errors. (경고 있으면 수정하거나 개별 `# noqa: XXX` 부여)

- [ ] **Step 2: Full pytest**

```
pytest -q
```

Expected: 기존 153+ passed + 새 테스트 ~35 passed (총 185+ passed). skip은 DB 통합테스트(TEST_DATABASE_URL 미설정 환경) 정도만.

- [ ] **Step 3: README 갱신**

`README.md`에 다음 섹션 추가 (기존 Week 5 섹션 아래):

```markdown
## Week 6: 미국주식 /signal

yfinance 기반 미국주식 5종 지원. 휴장/주말에도 마지막 종가로 카드 생성.

### 지원 심볼
| 심볼 | 이름 | 카테고리 |
|------|------|----------|
| BTCUSDT | Bitcoin | crypto |
| AAPL | Apple | us_stock |
| MSFT | Microsoft | us_stock |
| GOOGL | Alphabet | us_stock |
| NVDA | NVIDIA | us_stock |
| TSLA | Tesla | us_stock |

### 명령어
- `/signal` — BTC (기본)
- `/signal AAPL` — 애플
- `/signal aapl` / `/signal $AAPL` — 대소문자/$ 무관 정규화
- `/signal list` — 지원 심볼 목록
- `/signal UNKNOWN` — "지원하지 않는 심볼" 안내

### 카드 포맷 (주식)

```
── 2026-04-17 AAPL (금) ──
🕐 휴장 중 · 기준: 2026-04-16 (목) 종가
현재가: $184.12 (+1.23%)
────────────────
사주 점수:  56 (관망)
차트 점수:  72 (MA 우상향, RSI 62)
────────────────
종합:  66 | 진입
※ 엔터테인먼트 목적. 투자 추천 아님.
```

### 새 API 엔드포인트
- `GET /v1/signal/symbols` — 지원 심볼 카탈로그 (인증 필요)

### 아키텍처
- `src/sajucandle/market/` 패키지 신설
  - `base.py` — `MarketDataProvider` Protocol + `UnsupportedTicker`
  - `yfinance.py` — `YFinanceClient` (Redis 2단 캐시, fresh 1h / backup 24h)
  - `router.py` — `MarketRouter.get_provider(ticker)`, `MarketRouter.all_symbols()`
- `BinanceClient`에 `is_market_open` / `last_session_date` 추가 (24/7 trivial impl)
- `SignalResponse.market_status: MarketStatus` 필드 추가

### 범위 밖 (Week 7+)
- 모닝 푸시 카드에 주식 통합
- 사용자별 watchlist (`/watch AAPL`)
- 국내주식 (KIS OpenAPI)
- 공휴일 정확 판별
- 프리마켓/애프터아워
```

- [ ] **Step 4: Commit README + Push to trigger Railway deploy**

```
git add README.md
git commit -m "docs: Week 6 US stocks /signal complete"
git push origin main
```

Expected: GitHub push 성공, Railway가 3 서비스(api/bot/broadcast) 자동 재배포.

- [ ] **Step 5: Production smoke**

배포 완료 후(~3분):

```
curl.exe -H "X-SAJUCANDLE-KEY: <API_KEY>" "https://sajucandle-api-production.up.railway.app/v1/signal/symbols"
```

Expected: `{"symbols":[{"ticker":"BTCUSDT",...}, {"ticker":"AAPL",...}, ...]}`

봇에서:
- `/signal` → BTC 카드 (기존 동작)
- `/signal AAPL` → AAPL 카드 (배지 포함)
- `/signal list` → 심볼 목록
- `/signal AMZN` → "지원하지 않는 심볼" 안내

---

## Self-Review

### Spec coverage
- [x] 섹션 2 포함 범위: 화이트리스트 5종 → Task 4,6
- [x] `/signal AAPL`, `/signal list` → Task 12
- [x] `GET /v1/signal/symbols` → Task 10
- [x] 휴장 배지 → Task 5, 12 (`_format_signal_card`)
- [x] Redis 2단 캐시 → Task 4
- [x] 기존 BTC 회귀 없음 → Task 2,8,12에서 기존 테스트 전량 실행
- [x] `MarketDataProvider` Protocol → Task 3
- [x] `MarketRouter` → Task 6
- [x] `MarketStatus` 모델 → Task 7
- [x] `SignalService` DI 전환 → Task 8
- [x] api_client/handlers 확장 → Task 11,12
- [x] 에러 매트릭스 400/502/404 → Task 9,12
- [x] 명령어 문법 (대소문자, $) → Task 12 테스트
- [x] yfinance mock → Task 4 `unittest.mock.patch`
- [x] 공휴일 비커버 명시 → Task 5 주석
- [x] BTC 카드 배지 안 표시 → Task 12 `_format_signal_card` 분기 + 테스트
- [x] /help 갱신 → Task 12
- [x] README 갱신 → Task 13
- [x] 의존성 yfinance → Task 1

### Placeholder scan
- 모든 step에 실제 코드/명령 포함. "TODO", "TBD", "fill in", "similar to" 없음.
- `tests/test_api_signal.py`의 fixture 이름(`client`, `db_registered_user`)은 기존 파일에 있다고 가정 — 없으면 Task 9 Step 1에서 즉시 발견됨 (픽스처 없으면 pytest collection error).

### Type consistency
- `MarketDataProvider` Protocol의 세 메서드 `fetch_klines`/`is_market_open`/`last_session_date` 이름이 Task 2,3,4,5,6,8 전반에 일치.
- `MarketRouter` 필드명 `binance`/`yfinance`가 Task 6 정의 + Task 8,9 사용 일치.
- `MarketStatus` 필드 `is_open`/`last_session_date`/`category` Task 7 정의 + Task 8 populate + Task 12 사용 일치.
- `UnsupportedTicker` Task 3 정의 → Task 6,9,12 사용 일치.

### 주의사항
- Task 7은 **중간 커밋에서 테스트가 일시 실패** 상태. 이는 의도적이며 Task 8에서 복구.
- `pd.date_range(..., freq="B")`는 영업일 기준이라 휴장 제외. 테스트 픽스처의 날짜가 원하는 대로 나오는지 Task 4 Step 1 실행 시 즉시 확인됨.
- Windows에서 `python -c` 실행 시 인용부호 주의 (PowerShell은 `"` 사용, CMD는 변경 가능).

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-04-17-week6-us-stocks.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration
**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**

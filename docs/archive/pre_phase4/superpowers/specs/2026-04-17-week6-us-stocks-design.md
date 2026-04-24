# Week 6 설계 — 미국주식 `/signal` 확장 (yfinance)

- 날짜: 2026-04-17
- 대상 주차: Week 6
- 상태: Draft (brainstorming 합의 완료, 사용자 리뷰 대기)

## 1. 목적

`/signal`이 현재 BTC 전용이다. 실제 사용자(트레이더 친구/동료)의 니즈는 주식이 크다. MVP 기획서 Week 4에 빠진 "미국주식 4-5종 + yfinance" 작업을 Week 6에서 수행한다. KIS API 승인 대기 중이라도 yfinance는 인증이 없어 선행 가능하다.

## 2. 목표 / 범위

### 포함
- `/signal AAPL` 형태의 미국주식 시그널 (화이트리스트 5종: AAPL / MSFT / GOOGL / NVDA / TSLA)
- `/signal list` — 지원 심볼 목록
- `GET /v1/signal/symbols` API
- 휴장 배지 (`🟢 장 중` / `🕐 휴장 중 · 기준: YYYY-MM-DD (요일) 종가`)
- yfinance 기반 OHLCV 클라이언트 + Redis 2단 캐시 (fresh 1h / backup 24h)
- 기존 BTC `/signal` 동작/테스트 회귀 없음

### 범위 밖 (Week 7+)
- 모닝 푸시(07:00) 카드에 주식 통합
- 사용자별 즐겨찾기 심볼 (`/watch`), 동적 심볼 확장
- 국내주식 (KIS OpenAPI)
- 프리마켓 / 애프터아워 가격
- 공휴일 정확 판별
- 분봉 이하 타임프레임 (현재 `1d` 고정)
- 백테스트, 승률 추적

## 3. 설계 결정 (brainstorming 요약)

| # | 주제 | 결정 | 근거 |
|---|------|------|------|
| Q1 | 심볼 관리 | 화이트리스트 5종 고정 | MVP 품질 통제, 엣지케이스 5종만 검증 |
| Q2 | `/signal` 기본값 | BTC 유지 | 근육 기억 + 하위 호환. 새 사용자는 `/help`로 안내 |
| Q3 | 휴장 처리 | 정상 응답 + 배지 | "개장 전 종목 확인" 니즈가 가장 큼 |
| Q4 | 캐시 TTL | fresh 1h / backup 24h | 일봉 기반 신호, 분 단위 갱신 무의미 |
| Q5 | 모닝 카드 통합 | 안 함 (현상 유지) | Week 6 범위 명확히 유지 (YAGNI) |

## 4. 아키텍처

### 4.1 전체 흐름 (변화 없음)

```
Telegram → bot handlers → ApiClient → FastAPI (/v1/users/{chat_id}/signal?ticker=)
  → SignalService.compute(profile, date, ticker)
    → ScoreService (사주 4축)
    → MarketRouter.get_provider(ticker).fetch_klines()
      → (ticker에 따라) BinanceClient | YFinanceClient
    → score_chart(closes, volumes)
    → 가중합 (0.4 saju + 0.6 chart)
  → SignalResponse + Redis 캐시 (signal:*, 300s)
```

### 4.2 모듈 구성

```
src/sajucandle/
├── market_data.py          # 하위호환 re-export (BinanceClient, Kline, MarketDataUnavailable)
├── market/
│   ├── __init__.py
│   ├── base.py             # MarketDataProvider Protocol, UnsupportedTicker
│   ├── binance.py          # 기존 BinanceClient 이동 + MarketDataProvider 어댑터
│   ├── yfinance.py         # YFinanceClient (주식 5종)
│   └── router.py           # MarketRouter.get_provider(ticker)
├── signal_service.py       # 수정: market_router 주입, 내부 라우팅
├── models.py               # SignalResponse에 market_status 필드 추가
├── api.py                  # /v1/signal/symbols 추가
├── api_client.py           # get_supported_symbols() 추가
└── handlers.py             # /signal 인자 파싱, /signal list, 에러 분기
```

### 4.3 `MarketDataProvider` 인터페이스 (`market/base.py`)

```python
from typing import Protocol
from datetime import date
from sajucandle.market_data import Kline  # 기존 Kline 재사용

class MarketDataProvider(Protocol):
    def fetch_klines(
        self, symbol: str, interval: str = "1d", limit: int = 100
    ) -> list[Kline]: ...

    def is_market_open(self, symbol: str) -> bool: ...
    def last_session_date(self, symbol: str) -> date: ...

class UnsupportedTicker(Exception):
    """화이트리스트에 없는 심볼."""
```

### 4.4 `MarketRouter` (`market/router.py`)

```python
_STOCK_SYMBOLS = frozenset({"AAPL", "MSFT", "GOOGL", "NVDA", "TSLA"})
_CRYPTO_SYMBOLS = frozenset({"BTCUSDT"})

@dataclass
class MarketRouter:
    binance: MarketDataProvider
    yfinance: MarketDataProvider

    def get_provider(self, ticker: str) -> MarketDataProvider:
        t = ticker.upper().lstrip("$")
        if t in _CRYPTO_SYMBOLS:
            return self.binance
        if t in _STOCK_SYMBOLS:
            return self.yfinance
        raise UnsupportedTicker(t)

    @classmethod
    def all_symbols(cls) -> list[dict]:
        return [
            {"ticker": "BTCUSDT", "name": "Bitcoin", "category": "crypto"},
            {"ticker": "AAPL", "name": "Apple", "category": "us_stock"},
            {"ticker": "MSFT", "name": "Microsoft", "category": "us_stock"},
            {"ticker": "GOOGL", "name": "Alphabet", "category": "us_stock"},
            {"ticker": "NVDA", "name": "NVIDIA", "category": "us_stock"},
            {"ticker": "TSLA", "name": "Tesla", "category": "us_stock"},
        ]
```

### 4.5 `YFinanceClient` (`market/yfinance.py`)

```python
from datetime import datetime, date
from zoneinfo import ZoneInfo
import yfinance as yf

_NY_TZ = ZoneInfo("America/New_York")
_SUPPORTED = frozenset({"AAPL", "MSFT", "GOOGL", "NVDA", "TSLA"})
_FRESH_TTL = 3600
_BACKUP_TTL = 86400

class YFinanceClient:
    def __init__(self, redis_client=None):
        self._redis = redis_client

    def fetch_klines(self, symbol, interval="1d", limit=100) -> list[Kline]:
        sym = symbol.upper()
        if sym not in _SUPPORTED:
            raise UnsupportedTicker(sym)

        # Redis fresh → hit 반환
        # yf.Ticker(sym).history(period=f"{limit}d", interval="1d") → DataFrame
        # Row → Kline 변환 (index=Timestamp → open_time, columns=Open/High/Low/Close/Volume)
        # 양쪽 캐시 set
        # 실패 시 backup 반환, 없으면 MarketDataUnavailable

    def is_market_open(self, symbol: str) -> bool:
        now_ny = datetime.now(_NY_TZ)
        if now_ny.weekday() >= 5:   # Sat=5, Sun=6
            return False
        open_t = now_ny.replace(hour=9, minute=30, second=0, microsecond=0)
        close_t = now_ny.replace(hour=16, minute=0, second=0, microsecond=0)
        return open_t <= now_ny <= close_t

    def last_session_date(self, symbol: str) -> date:
        klines = self.fetch_klines(symbol, limit=1)
        return klines[-1].open_time.astimezone(_NY_TZ).date()
```

**중요 노트:**
- yfinance는 동기. 기존 `SignalService.compute()`는 동기이므로 `to_thread` 불필요.
- yfinance `history()`는 주말 호출 시 금요일까지의 DataFrame을 반환한다.
- 공휴일은 `is_market_open` 반환값이 틀릴 수 있으나, `last_session_date`는 정확하다. 사용자가 보는 날짜 정보가 틀리는 건 피한다.
- `_SUPPORTED` 상수는 `router.py`와 중복되지 않도록 `router._STOCK_SYMBOLS`를 import.

### 4.6 `SignalResponse` 확장 (`models.py`)

```python
class MarketStatus(BaseModel):
    is_open: bool
    last_session_date: str   # ISO "YYYY-MM-DD" (NY 기준)
    # 여기에는 "category" 등 추가 가능. MVP는 위 2개만.

class SignalResponse(BaseModel):
    ...  # 기존 필드 유지
    market_status: MarketStatus   # 새 필드 (BTC도 채움: is_open=True, last_session_date=UTC 오늘)
```

BTC는 24/7이므로 항상 `is_open=True`, `last_session_date=오늘`. BinanceClient 어댑터가 이를 채운다.

### 4.7 `SignalService` 변경

```python
class SignalService:
    def __init__(
        self,
        score_service: ScoreService,
        market_router: MarketRouter,   # ← 변경: BinanceClient가 아니라 Router
        redis_client=None,
    ):
        ...

    def compute(self, profile, target_date, ticker):
        ...
        provider = self._market_router.get_provider(ticker)   # UnsupportedTicker
        klines = provider.fetch_klines(ticker, "1d", 100)
        ...
        resp = SignalResponse(
            ...,
            market_status=MarketStatus(
                is_open=provider.is_market_open(ticker),
                last_session_date=provider.last_session_date(ticker).isoformat(),
            ),
        )
```

의존성 주입 지점(`api_main.py` 또는 `api.py` startup)에서 `MarketRouter(binance=BinanceClient(...), yfinance=YFinanceClient(...))`로 조립.

## 5. API 표면

### 5.1 기존 (변경 없음)
`GET /v1/users/{chat_id}/signal?ticker=BTCUSDT|AAPL|...` — 응답에 `market_status` 필드만 추가.

### 5.2 신규
```
GET /v1/signal/symbols
  auth: X-SAJUCANDLE-KEY (기존 /signal과 동일 정책)
  응답: {"symbols": [{"ticker":"BTCUSDT","name":"Bitcoin","category":"crypto"}, ...]}
```

### 5.3 에러 매트릭스

| 시나리오 | HTTP | 바디 | 봇 응답 |
|----------|------|------|---------|
| 지원 안 하는 심볼 | 400 | `{"detail":"unsupported ticker: AMZN"}` | "지원하지 않는 심볼. /signal list로 목록 확인" |
| yfinance 일시 장애 + 캐시 없음 | 502 | `{"detail":"market data unavailable"}` | "시장 데이터 일시 불능. 잠시 후 다시." |
| yfinance 장애 + backup 캐시 있음 | 200 | 정상 | 정상 카드 (내부 로그에 warning) |
| 명식 미등록 | 404 | 기존 그대로 | "먼저 생년월일을 등록하세요." |

## 6. 봇 명령어 / 카드

### 6.1 명령어 문법
```
/signal              → BTCUSDT (기본)
/signal AAPL         → 주식
/signal aapl         → 대소문자 무관
/signal $AAPL        → 선행 $ 제거
/signal list         → 지원 심볼 목록
/signal UNKNOWN      → 400 → "지원하지 않는 심볼 ..."
```

### 6.2 카드 포맷 (주식)

**장 중:**
```
── 2026-04-17 AAPL (금) ──
🟢 장 중
현재가: $184.12 (+1.23%)
────────────────
사주 점수:  56 (관망)
차트 점수:  72 (MA 우상향, RSI 62)
────────────────
종합:  66 | 진입
추천 시진: 午시 11:00~13:00, 子시 23:00~01:00, 亥시 21:00~23:00

※ 엔터테인먼트 목적. 투자 추천 아님.
```

**휴장:**
```
── 2026-04-17 AAPL (금) ──
🕐 휴장 중 · 기준: 2026-04-16 (목) 종가
현재가: $184.12 (+1.23%)
... (이하 동일)
```

**BTC** (24/7이라 배지 생략 또는 `🟢 24/7`):
- MVP는 **기존 포맷 유지** (배지 줄 자체를 BTC는 표시 안 함). `is_open=True`이고 crypto라는 조건으로 분기.

### 6.3 `/signal list` 응답
```
지원 심볼:
────────────
암호화폐
  · BTCUSDT — Bitcoin

미국주식
  · AAPL — Apple
  · MSFT — Microsoft
  · GOOGL — Alphabet
  · NVDA — NVIDIA
  · TSLA — Tesla

사용법: /signal AAPL
```

### 6.4 `/help` 업데이트
```
/signal [심볼] — 사주+차트 결합 신호
  · 심볼 생략: BTC
  · 지원: BTCUSDT, AAPL, MSFT, GOOGL, NVDA, TSLA
  · /signal list — 전체 목록
```

## 7. 의존성

```toml
# pyproject.toml [tool.poetry.dependencies] 또는 [project.dependencies]
yfinance = "^0.2.40"    # 0.2.40+ (2024 릴리즈 이후, pandas 2.x 호환)
```
- pandas는 yfinance의 transitive dep (명시 불필요)
- 빌드/런타임 영향: Docker 이미지 크기 ~30MB 증가 (numpy + pandas). 허용 범위.

## 8. 테스트 전략

| 파일 | 커버리지 |
|------|----------|
| `tests/test_market_yfinance.py` (신규) | fetch_klines 정상/빈결과/네트워크에러/mock DataFrame, is_market_open 경계(월요일 09:29/09:30/09:31, 금요일 16:00/16:01, 토요일, 서머타임 전후), last_session_date, Redis fresh/miss/backup |
| `tests/test_market_router.py` (신규) | BTCUSDT → binance 라우팅, AAPL → yfinance, AMZN → UnsupportedTicker, 대소문자 + `$` 정규화 |
| `tests/test_market_binance.py` (이동) | 기존 `test_market_data.py`를 `market/binance.py`로 재구성한 위치 변경 반영 |
| `tests/test_signal_service.py` (수정) | 기존 BTC 시나리오 + AAPL 시나리오 (router mock), market_status 필드 검증 |
| `tests/test_api.py` (수정) | `/v1/signal/symbols` 인증/정상, unsupported ticker 400 |
| `tests/test_handlers.py` (수정) | `/signal`, `/signal AAPL`, `/signal $aapl`, `/signal list`, `/signal UNKNOWN` 각 응답 |
| `tests/test_api_client.py` (수정) | `get_supported_symbols()` 추가 |

yfinance mock 전략: `unittest.mock.patch('yfinance.Ticker')` → `history()`가 고정 DataFrame 반환. 실제 네트워크 호출 금지.

## 9. 관측성

- `logger.info("signal ok chat_id=%s ticker=%s composite=%s market_open=%s", ...)` — 기존 로그에 market_open 추가
- `logger.warning("yfinance fetch failed symbol=%s: %s", symbol, err)` — backup fallback 시
- `logger.info("yfinance cache hit symbol=%s", symbol)` — fresh hit (디버그용)

## 10. 배포

1. poetry add yfinance → lock
2. 코드 푸시 → Railway 자동 배포 (3 서비스 모두 재빌드)
3. 환경변수 추가 없음 (yfinance 인증 불필요)
4. 로컬 스모크: `pytest`, `python -m sajucandle.bot` + `/signal AAPL`
5. 운영 스모크: `/signal AAPL` 봇 명령 → 카드 수신 확인

## 11. 위험과 대응

| 위험 | 대응 |
|------|------|
| yfinance 비공식 API 차단 | Redis backup 24h로 1일 버틸 수 있음. 장기화 시 Alpha Vantage or Tiingo 대체 (Week 7 과제) |
| pandas 번들 무거움 | Docker 이미지 30MB 증가 허용. 더 커지면 `slim` 이미지 고려 |
| 공휴일 `is_market_open=True` 오판 | `last_session_date`는 정확하므로 날짜 표시는 올바름. 배지 하나 틀린 것 < 날짜 틀리는 것 |
| BTC 기존 동작 회귀 | 기존 `BinanceClient` 그대로 이동 + MarketDataProvider 어댑터. 기존 테스트 전량 통과가 회귀 방지 증거 |
| 심볼 대소문자 변형 | router에서 `.upper().lstrip("$")` 정규화 |

## 12. 완료 기준

- [ ] 로컬 pytest 전량 통과 (기존 BTC 테스트 + 새 주식 테스트)
- [ ] `/signal` → BTC 카드 (회귀 없음)
- [ ] `/signal AAPL` → 주식 카드 (배지 포함)
- [ ] `/signal list` → 심볼 목록
- [ ] `/signal AMZN` → "지원하지 않는 심볼" 응답
- [ ] 휴장 시 `🕐 휴장 중 · 기준: YYYY-MM-DD` 배지 정상 표시
- [ ] Railway 3 서비스 정상 기동 (api / bot / broadcast)
- [ ] API 응답에 `market_status` 필드 포함

## 13. 이후 과제 (Week 7+ 후보)

- KIS OpenAPI 연동 → 국내주식 (005930 삼성전자 등)
- 모닝 푸시 카드에 watchlist 심볼 시그널 합류
- `/watch AAPL`, `/unwatch`, `/watchlist` 사용자별 즐겨찾기
- 공휴일 달력 (`pandas_market_calendars` or 정적 JSON)
- 시그널 적중률 로그 적재 → 가중치 튜닝
- 프리마켓 / 애프터아워 가격 (yfinance `prepost=True`)

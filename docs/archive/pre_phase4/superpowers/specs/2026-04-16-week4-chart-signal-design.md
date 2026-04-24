# Week 4 — 사주 + 차트 결합 신호 설계

**날짜:** 2026-04-16
**범위:** 기획서 v0.1 §2 (결합 로직 = 사주 × 차트), §4 (신호 등급)
**전제:** Week 3 (사주 점수 API + 봇 통합) 완료.

---

## 1. 목표

- `/score`로 받는 사주 4축 점수에 **차트 기술 분석 점수**를 결합해 "오늘 매매 신호"를 반환한다.
- 대상은 **BTC/USDT 단일 종목** (24/7 거래, 인증 없는 공개 API, 휴장/장시간 로직 불필요). 주식은 Week 5+.
- 봇에 `/signal` 커맨드 추가. 기존 `/score`는 건드리지 않음 (격리, 롤백 쉬움).

### Non-goals

- 뉴스 감성 (FinBERT) — 인프라 무거움, Week 5+
- 백테스트 — 별도 트랙
- 복수 티커 / 멀티 타임프레임 (1h/4h) — 1d 단일로 시작
- pandas-ta 같은 큰 의존성 — RSI/MA 직접 구현
- 가격 알림 / push — 사용자가 능동적으로 `/signal` 쳐야 함

---

## 2. 아키텍처

```
[Telegram]
   │ /signal
   ▼
┌─────────────────────┐       ┌──────────────────────────┐
│ sajucandle-bot       │──────▶│ sajucandle-api            │
│ handlers.signal      │ httpx │ /v1/users/{id}/signal     │
└─────────────────────┘       │   └─▶ signal_service       │
                              │       ├─▶ score_service     │
                              │       │   (사주 composite)  │
                              │       └─▶ market_data       │
                              │           + tech_analysis   │
                              │           (chart_score)     │
                              └────────┬──────────┬────────┘
                                       │          │
                                       ▼          ▼
                              ┌──────────┐  ┌───────────┐
                              │ Binance  │  │ Upstash   │
                              │ public   │  │ Redis     │
                              │ REST     │  │ signal:*  │
                              └──────────┘  │ ohlcv:*   │
                                            └───────────┘
```

- **신규 모듈 3개**: `market_data.py`, `tech_analysis.py`, `signal_service.py`
- **외부 의존성 추가 0개**: httpx(이미 있음), 그 외 지표는 순수 Python/stdlib.
- Binance 공개 REST만 사용 (API 키 불필요). 실패 시 stale cache fallback.

---

## 3. 차트 점수 계산

### 3.1 데이터

**Source:** Binance Spot REST  
**Endpoint:** `GET https://api.binance.com/api/v3/klines`  
**Params:** `symbol=BTCUSDT&interval=1d&limit=100`

응답 형태 (배열의 배열):
```
[
  [open_time, open, high, low, close, volume, close_time, ...],  # 각 캔들
  ...
]
```

100일치만 받음 — RSI(14) + MA50 계산에 충분하고 페이로드 작음.

**캐시 (2단 구조):**
- `ohlcv:BTCUSDT:1d:fresh` — TTL=300초 (5분). 일반 조회는 이 키만 봄.
- `ohlcv:BTCUSDT:1d:backup` — TTL=86400초 (24시간). Binance 응답 성공 시 fresh와 동시에 set. 장애 시 fallback.

**Fallback 로직:**
1. fresh 키 히트 → 사용
2. miss → Binance HTTP GET
   - 성공 → fresh + backup 둘 다 set → 사용
   - 실패 → backup 키 히트 → 사용 (로그 WARN "using backup cache age=...")
   - fresh miss + backup miss + HTTP 실패 → 502 `chart data unavailable`

Redis 자체가 없는 환경 (로컬 dev)에서는 fresh/backup 모두 miss로 취급, 실패 시 502.

### 3.2 지표 (3개)

**A. RSI(14)** — 과매수/과매도
```
RS = avg(gain_14) / avg(loss_14)
RSI = 100 - 100/(1+RS)
```
- RSI ≤ 30 → 70점 (과매도, 반등 기대)
- RSI 30~45 → 55점
- RSI 45~55 → 50점 (중립)
- RSI 55~70 → 40점
- RSI > 70 → 20점 (과매수, 경계)

**B. MA20 / MA50 크로스** — 추세
- MA20 > MA50 × 1.02 → 70점 (상승 추세)
- MA20 > MA50 → 60점 (상승)
- MA20 ≈ MA50 (±2% 이내) → 50점
- MA20 < MA50 → 35점 (하락)

**C. 볼륨 모멘텀** — 관심도
- `vol_today / avg(vol_last_20)` 비율
- ≥ 1.5 → 65점 (강한 관심)
- 1.0 ~ 1.5 → 55점
- 0.5 ~ 1.0 → 45점
- < 0.5 → 35점

**결합 (chart_score, 0~100):**
```
chart_score = 0.4 * rsi_score + 0.4 * ma_score + 0.2 * vol_score
```
- RSI와 추세에 비중, 볼륨은 보조.
- 가중치는 하드코드 (Week 4). 백테스트 후 조정은 별도.

### 3.3 최종 결합

```
final_score = 0.4 * saju_composite + 0.6 * chart_score
```

**등급:**
| final | grade |
|-------|-------|
| ≥ 75 | 강진입 |
| 60~74 | 진입 |
| 40~59 | 관망 |
| < 40 | 회피 |

`/score`의 signal_grade와는 다른 축. 헷갈림 방지 위해 `/signal` 응답에서는 `chart_grade` 같은 별도 필드 사용.

---

## 4. API

### 4.1 신규 엔드포인트

```
GET /v1/users/{chat_id}/signal?ticker=BTCUSDT&date=YYYY-MM-DD
```

**Query params:**
- `ticker` (optional, default `BTCUSDT`) — Week 4는 `BTCUSDT`만 허용. 다른 값이면 400.
- `date` (optional, default 오늘 KST) — 사주 점수 계산에 쓰임. 차트는 항상 "지금 시점" 기준.

**응답 (SignalResponse):**
```json
{
  "chat_id": 123,
  "ticker": "BTCUSDT",
  "date": "2026-04-16",
  "price": {
    "current": 67432.1,
    "change_pct_24h": 2.1
  },
  "saju": {
    "composite": 55,
    "grade": "관망"
  },
  "chart": {
    "score": 72,
    "rsi": 58.2,
    "ma20": 65100.0,
    "ma50": 62300.0,
    "ma_trend": "up",
    "volume_ratio": 1.3,
    "reason": "RSI 중립, MA20>MA50, 볼륨↑"
  },
  "composite_score": 65,
  "signal_grade": "진입",
  "best_hours": [
    {"shichen": "寅", "time_range": "03:00-05:00"}
  ]
}
```

**Redis 캐시:** `signal:{chat_id}:{date}:{ticker}` TTL=300초 (5분).
- 사주 부분은 KST 자정까지지만 차트 부분이 5분마다 변해서 짧게.
- `ohlcv:*` 캐시와 2단 구조: signal 캐시 miss → ohlcv 캐시 조회(또는 Binance fetch) → chart_score 계산 → signal 캐시 set.

**에러:**
- 400: 잘못된 ticker / date
- 401: API 키 불일치
- 404: 사용자 미등록
- 502: Binance + stale cache 모두 없음
- 503: DB 없음

### 4.2 `/health` 확장 (선택)

`market` 필드 추가: Binance 응답 가능하면 `"up"`, 아니면 `"down"`. 디버깅용.
→ 일단 Week 4 스코프 밖. 로그로 충분.

---

## 5. 봇

### 5.1 신규 커맨드

```
/signal
```

현재는 BTC 단일 — 인자 없음. Week 5에서 `/signal ETHUSDT` 등 확장 여지.

**봇 → api:** `_api_client.get_signal(chat_id, ticker="BTCUSDT")`

**응답 예:**
```
── 2026-04-16 BTC/USDT ──
현재가: $67,432 (+2.1%)
────────────────
사주 점수: 55 (관망)
차트 점수: 72 (RSI 58, MA20>MA50, 볼륨↑)
────────────────
종합: 65 | 진입
추천 시진: 寅시 03:00-05:00

※ 엔터테인먼트 목적. 투자 추천 아님.
```

**에러 처리 (handlers.signal_command):**
- NotFoundError → "먼저 /start 로 등록하세요"
- ApiError 502 → "시장 데이터 일시 불능. 잠시 후."
- ApiError 기타 → "서버 오류 (status)"
- Timeout / TransportError → 기존 패턴 재사용

### 5.2 `/help` 업데이트

`/signal` 한 줄 추가.

---

## 6. 새 모듈 세부

### 6.1 `market_data.py`

```python
@dataclass
class Kline:
    open_time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

class BinanceClient:
    BASE = "https://api.binance.com"
    def __init__(self, http_client: httpx.Client | None = None, redis_client=None): ...
    def fetch_klines(self, symbol: str, interval: str = "1d", limit: int = 100) -> list[Kline]:
        # Redis ohlcv:{symbol}:{interval} 먼저
        # miss → HTTP GET → parse → Redis set TTL=300
        # HTTP 실패 → stale cache 재사용 (persist=true 상태로) or raise MarketDataUnavailable
```

- 동기 httpx (score_service가 동기라 일관성).
- 테스트: respx로 mock.

### 6.2 `tech_analysis.py`

```python
def rsi(closes: list[float], period: int = 14) -> float: ...
def sma(closes: list[float], period: int) -> float: ...
def volume_ratio(volumes: list[float]) -> float:  # 오늘/최근20일 평균
    ...

@dataclass
class ChartScoreBreakdown:
    score: int             # 0~100
    rsi_value: float
    ma20: float
    ma50: float
    ma_trend: str          # "up" | "down" | "flat"
    volume_ratio: float
    reason: str

def score_chart(klines: list[Kline]) -> ChartScoreBreakdown: ...
```

- 순수 함수, 입출력 명확, stdlib만 사용 (numpy/pandas 없음).
- 테스트 쉬움: 고정 입력 → 고정 출력.

### 6.3 `signal_service.py`

```python
class SignalService:
    def __init__(
        self,
        score_service: ScoreService,       # 기존
        market_client: BinanceClient,      # 신규
        redis_client=None,
    ): ...
    def compute(
        self,
        profile: UserProfile,
        target_date: date,
        ticker: str,
    ) -> SignalResponse:
        # 1. signal:* cache → hit ? return
        # 2. sajucomposite = score_service.compute(profile, target_date, profile.asset_class_pref).composite_score
        # 3. klines = market_client.fetch_klines(ticker)
        # 4. chart = score_chart(klines)
        # 5. final = 0.4 * saju + 0.6 * chart.score
        # 6. grade = _grade_signal(final)
        # 7. build SignalResponse
        # 8. redis.setex("signal:...", 300, json)
        # 9. return
```

---

## 7. 모델 (Pydantic)

```python
class PricePoint(BaseModel):
    current: float
    change_pct_24h: float

class SajuSummary(BaseModel):
    composite: int
    grade: str

class ChartSummary(BaseModel):
    score: int
    rsi: float
    ma20: float
    ma50: float
    ma_trend: str  # "up" | "down" | "flat"
    volume_ratio: float
    reason: str

class SignalResponse(BaseModel):
    chat_id: int
    ticker: str
    date: str
    price: PricePoint
    saju: SajuSummary
    chart: ChartSummary
    composite_score: int
    signal_grade: str  # "강진입" | "진입" | "관망" | "회피"
    best_hours: list[BestHour]   # score_service 재사용
```

---

## 8. 테스트 전략

| 모듈 | 테스트 |
|------|--------|
| `tech_analysis` | RSI/MA/volume_ratio 고정 입력, score_chart 경계 조건 (RSI 30/70, MA 크로스) |
| `market_data` | respx로 Binance mock, cache hit/miss, HTTP 실패 시 stale 재사용, stale 없을 때 예외 |
| `signal_service` | fake market_client + fake redis로 통합. 캐시 키 포맷, 가중 공식 검증 |
| `/v1/.../signal` 엔드포인트 | TestClient + fakeredis + fake market. 404/502/성공 케이스. |
| `handlers.signal` | fake api_client로 응답 포맷, NotFoundError/502 분기 |

**Binance 실호출은 하지 않음** — 전부 respx mock. CI 안정성 우선.

---

## 9. 배포 / 운영

- **환경변수 추가 없음.** Binance 공개 API라 키 불필요.
- Railway 재배포만 하면 바로 동작.
- 로그 (이미 Week 3 관측 장비에서 세팅한 sajucandle logger):
  ```
  INFO signal ok chat_id=123 ticker=BTCUSDT composite=65 grade=진입 chart=72 saju=55 elapsed_ms=180
  WARN binance fetch failed, using stale cache age=420s
  ERROR binance fetch failed AND no cache available
  ```

---

## 10. 롤백 / 격리

- `/score`, `/start`, `/me`, `/forget`, `/help` 전부 미변경.
- `/signal` 하나만 켜고 끌 수 있음 (봇 `bot.py`에서 handler 등록 한 줄 제거).
- API 엔드포인트도 `/v1/users/{chat_id}/signal` 하나만 추가. 기존 엔드포인트 스키마 불변.

---

## 11. 오픈 이슈 (구현 중 결정)

- **사주 asset_class와 chart_score 상호작용:** 현재는 두 축 독립 가중합. 나중에 scalp일 때 chart 가중치 더 올리는 식 조정 가능. Week 4는 고정.
- **재시도:** Binance 타임아웃 시 1회 retry? 일단 0회 (timeout 3초 → 실패 → stale cache). 사용자 기다림 최소화.
- **등급 경계 한국어 표현:** "강진입"이 너무 공격적인가? "적극진입"? 사용자 반응 본 뒤 조정.

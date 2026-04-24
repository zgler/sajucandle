# Week 9 설계 — S/R + SL/TP 자동 제안 + admin OHLCV (Phase 0 실데이터)

- 날짜: 2026-04-19
- 대상 주차: Week 9 Phase 2 (4주 스프린트 Week 8~11 중 두 번째)
- 상태: Draft (brainstorming 합의 완료)

## 1. 목적

Week 8 Phase 1에서 /signal 카드에 "구조/정렬/진입조건" 3줄이 추가되어 **"왜 진입?"**에 답하게 됐다. Week 9는 **"어디에 진입/손절/익절?"**에 구체 가격으로 답한다. "의견"에서 "트레이딩 도구"로 격상하는 결정타.

추가로 Week 8의 Phase 0 tracking skeleton (`_default_get_klines`가 빈 리스트 반환)을 실제 admin OHLCV 엔드포인트로 연결해 MFE/MAE 데이터 누적 시작.

## 2. 목표 / 범위

### 포함
1. 지지/저항 자동 식별 — Swing point + Volume profile 융합 (`analysis/support_resistance.py`, `analysis/volume_profile.py`)
2. 하이브리드 SL/TP 산출 — ATR 기본 + S/R snap 조정 (`analysis/trade_setup.py`)
3. 포지션 리스크 % 표시 (진입~손절 거리 기반)
4. `AnalysisResult`에 `sr_levels` + `trade_setup` 필드
5. 시그널 카드 확장:
   - "진입"/"강진입": 진입/SL/TP1/TP2/R:R/리스크 풀 블록
   - "관망"/"회피": "주요 레벨" (지지 3 + 저항 3)만
6. `GET /v1/admin/ohlcv` 엔드포인트 (인증 필요)
7. `ApiClient.get_admin_ohlcv()`
8. broadcast.py Phase 0의 `_default_get_klines`를 admin ohlcv 엔드포인트 사용하도록 교체
9. signal_log에 SL/TP 컬럼 추가 (Week 11 백테스트용 — 실제 SL/TP 도달 여부 추적 기반)

### 범위 밖 (Week 10+)
- 발송 거부 규칙 (BREAKDOWN에서 강진입 차단 등)
- 카드 세밀 조정 (이모지, 정렬, 길이)
- MFE/MAE 통계 집계 API (Week 11)
- 적중률 카드 노출 (Week 11)

## 3. 설계 결정 (brainstorming 요약)

| # | 주제 | 결정 | 근거 |
|---|------|------|------|
| Q1 | S/R 알고리즘 | **Swing + Volume profile** (B) | VPVR 추가로 "매물대" 반영. 구현량 중, 효과 큼 |
| Q2 | SL/TP 기준 | **하이브리드 ATR + S/R snap** (C) | ATR 안정성 + S/R 정확성. 둘 중 하나 없어도 동작 |
| Q3 | 포지션 사이징 | **상대 % 리스크만** (A) | 계좌 크기 몰라도 가능, 한 줄 해결 |
| Q4 | SL/TP 표시 조건 | **등급별 차등** (C) | 진입 이상 풀, 관망/회피 S/R만 |

## 4. 아키텍처

### 4.1 모듈 구조

```
src/sajucandle/analysis/
├── swing.py                    # 기존 (Week 8)
├── structure.py                # 기존
├── timeframe.py                # 기존
├── multi_timeframe.py          # 기존
├── composite.py                # [MODIFY] sr_levels + trade_setup 조립
├── volume_profile.py           # [CREATE] VPVR 매물대 계산
├── support_resistance.py       # [CREATE] Swing + Volume 융합
└── trade_setup.py              # [CREATE] 하이브리드 SL/TP
```

### 4.2 volume_profile.py

```python
@dataclass
class VolumeNode:
    price_low: float
    price_high: float
    volume_sum: float


def compute_volume_profile(
    klines: list[Kline],
    bucket_count: int = 20,
    top_n: int = 3,
) -> list[VolumeNode]:
    """최근 N봉의 거래량을 가격 bucket별로 집계 → 상위 top_n 반환.

    알고리즘:
    1. 가격 범위 = [min_low, max_high] 전체
    2. bucket_count 등분 → bucket 폭 = (max - min) / N
    3. 각 봉 volume을 해당 봉의 (high+low)/2가 속한 bucket에 누적
       (더 정확히는 봉 내부 가격을 보간하지만 MVP는 중간값으로 근사)
    4. volume_sum 기준 내림차순 → 상위 top_n 반환
    """
```

### 4.3 support_resistance.py

```python
class LevelKind(str, Enum):
    SUPPORT = "support"
    RESISTANCE = "resistance"


@dataclass
class SRLevel:
    price: float
    kind: LevelKind
    strength: Literal["low", "medium", "high"]
    sources: list[str]   # ["swing_low", "volume_node"]


def identify_sr_levels(
    klines_1d: list[Kline],
    swings: list[SwingPoint],
    current_price: float,
    *,
    max_supports: int = 3,
    max_resistances: int = 3,
    merge_tolerance_pct: float = 0.5,
) -> list[SRLevel]:
    """swing points + volume profile → SRLevel 리스트.

    절차:
    1. 후보 생성:
       - swing high → RESISTANCE 후보 (price = sp.price, source="swing_high")
       - swing low → SUPPORT 후보 (source="swing_low")
       - volume_node → 현재가 기준 위쪽이면 RESISTANCE, 아래면 SUPPORT
         (node.price_low~high 중간값 사용, source="volume_node")
    2. merge: 같은 kind의 후보들 중 가격이 merge_tolerance_pct% 이내면 병합
       - sources를 합침 → strength 결정
    3. strength 판정:
       - sources에 ("swing_*" + "volume_node") 모두 있으면 → high
       - volume_node 단독이면서 volume_sum이 상위 1개면 → medium
       - 그 외 → low
    4. 현재가 기준:
       - support: price < current, 가까운 순으로 max_supports개
       - resistance: price > current, 가까운 순으로 max_resistances개
    """
```

### 4.4 trade_setup.py

```python
@dataclass
class TradeSetup:
    entry: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: float
    risk_pct: float          # (entry - sl) / entry * 100 (양수)
    rr_tp1: float            # (tp1 - entry) / (entry - sl)
    rr_tp2: float
    sl_basis: Literal["atr", "sr_snap"]
    tp1_basis: Literal["atr", "sr_snap"]
    tp2_basis: Literal["atr", "sr_snap"]


# 튜닝 상수 — Week 11 백테스트 후 조정
_SL_ATR_MULT = 1.5
_TP1_ATR_MULT = 1.5
_TP2_ATR_MULT = 3.0
_SNAP_TOLERANCE = 0.3      # ATR 거리의 ±30% 안에 S/R 있으면 snap
_SR_BUFFER_ATR = 0.2       # SL은 지지 밑 0.2 ATR 여유


def compute_trade_setup(
    entry: float,
    atr_1d: float,
    sr_levels: list[SRLevel],
) -> TradeSetup:
    """하이브리드 ATR + S/R snap.

    SL:
      base = entry - _SL_ATR_MULT * atr
      search range = [entry - (_SL_ATR_MULT + _SNAP_TOLERANCE) * atr,
                      entry - (_SL_ATR_MULT - _SNAP_TOLERANCE) * atr]
      가장 강한 SUPPORT이 range 안에 있으면 → sl = support.price - _SR_BUFFER_ATR * atr
      else → sl = base, sl_basis = "atr"

    TP1: 동일 로직 (저항 + _SR_BUFFER_ATR * atr 만큼 아래로 보수적 익절)
    TP2: _TP2_ATR_MULT 기준, snap 범위 넓힘 (±50% 허용) — 멀리 있는 저항도 잡음

    risk_pct = (entry - sl) / entry * 100
    rr_tp1 = (tp1 - entry) / (entry - sl)
    rr_tp2 = (tp2 - entry) / (entry - sl)
    """
```

### 4.5 composite.py 통합

```python
@dataclass
class AnalysisResult:
    # 기존 Week 8 필드
    structure: StructureAnalysis
    alignment: Alignment
    rsi_1h: float
    volume_ratio_1d: float
    composite_score: int
    reason: str
    # Week 9
    sr_levels: list[SRLevel]
    atr_1d: float   # trade_setup 계산에 SignalService가 활용
    # trade_setup은 analyze()가 아닌 SignalService가 등급 결정 후 채움


def analyze(klines_1h, klines_4h, klines_1d) -> AnalysisResult:
    # 기존 swing, structure, alignment ...
    
    # Week 9
    current = klines_1d[-1].close if klines_1d else 0.0
    sr_levels = identify_sr_levels(klines_1d, swings, current) if klines_1d else []
    atr_1d = _atr(klines_1d, 14) if len(klines_1d) >= 15 else 0.0
    
    return AnalysisResult(
        ...,
        sr_levels=sr_levels,
        atr_1d=atr_1d,
    )
```

### 4.6 signal_service.py 수정

```python
def compute(self, profile, target_date, ticker) -> SignalResponse:
    # ... 기존 analyze 호출 ...
    analysis = analyze(klines_1h, klines_4h, klines_1d)
    
    final = round(0.1 * saju.composite + 0.9 * analysis.composite_score)
    grade = _grade_signal(final, analysis)
    
    # Week 9: TradeSetup 조건부 계산
    trade_setup: Optional[TradeSetup] = None
    if grade in ("강진입", "진입") and analysis.atr_1d > 0:
        trade_setup = compute_trade_setup(
            entry=current,
            atr_1d=analysis.atr_1d,
            sr_levels=analysis.sr_levels,
        )
    
    # Pydantic 변환 — AnalysisSummary에 sr_levels + trade_setup 필드 추가 필요
    analysis_summary = _analysis_to_summary(analysis, trade_setup)
    resp = SignalResponse(..., analysis=analysis_summary)
```

### 4.7 models.py 확장

```python
class SRLevelSummary(BaseModel):
    price: float
    kind: Literal["support", "resistance"]
    strength: Literal["low", "medium", "high"]


class TradeSetupSummary(BaseModel):
    entry: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: float
    risk_pct: float
    rr_tp1: float
    rr_tp2: float


class AnalysisSummary(BaseModel):
    # 기존 필드 ...
    # Week 9 신규
    sr_levels: List[SRLevelSummary] = []
    trade_setup: Optional[TradeSetupSummary] = None
```

## 5. admin OHLCV 엔드포인트

### 5.1 엔드포인트

```
GET /v1/admin/ohlcv
  query:
    ticker     (required) — MarketRouter 화이트리스트
    interval   (default "1h") — "1h" | "4h" | "1d"
    since      (optional, ISO 8601) — 이 시각 이후 bar만 반환
    limit      (default 168, max 500)
  auth: X-SAJUCANDLE-KEY
  응답: {
    "ticker": "AAPL",
    "interval": "1h",
    "klines": [
      {"open_time": "...", "open": ..., "high": ..., "low": ...,
       "close": ..., "volume": ...},
      ...
    ]
  }
```

### 5.2 에러 매트릭스

| 상황 | HTTP | detail |
|------|------|--------|
| 인증 실패 | 401 | `invalid or missing API key` |
| 지원 안하는 ticker | 400 | `unsupported ticker: XYZ` |
| 지원 안하는 interval | 400 | `unsupported interval: 15m` |
| limit 범위 외 | 400 | `limit must be 1..500` |
| since 파싱 실패 | 400 | `since must be ISO 8601` |
| market data unavailable | 502 | `market data unavailable` |

### 5.3 api_client.py 확장

```python
async def get_admin_ohlcv(
    self, ticker: str, interval: str = "1h",
    since: Optional[str] = None, limit: int = 168,
) -> list[dict]:
    params: dict = {"ticker": ticker, "interval": interval, "limit": str(limit)}
    if since:
        params["since"] = since
    async with self._client() as c:
        r = await c.get("/v1/admin/ohlcv", params=params)
    await self._raise_for_status(r)
    return list(r.json().get("klines", []))
```

## 6. Phase 0 실데이터 연결

### 6.1 `_default_get_klines` 교체

Week 8에서는 빈 리스트 반환. Week 9에서:

```python
# broadcast.py 내부
async def _default_get_klines(ticker: str, sent_at: datetime):
    """admin OHLCV 엔드포인트 호출."""
    try:
        raw = await api_client.get_admin_ohlcv(
            ticker=ticker,
            interval="1h",
            since=sent_at.isoformat(),
            limit=168,   # 7일치 * 24h
        )
    except Exception as e:
        logger.warning(
            "phase0 ohlcv fetch failed ticker=%s: %s", ticker, e
        )
        return []
    # dict → Kline 변환 (Kline.from_dict은 Week 6 이미 구현)
    return [Kline.from_dict(d) for d in raw]
```

`_default_get_klines`는 `run_broadcast`가 `api_client` 캡처한 클로저여야 함.

### 6.2 Redis 캐시 활용

`admin_ohlcv_endpoint` 내부에서 `provider.fetch_klines` 호출 → 기존 Redis 2단 캐시(fresh 1h / backup 24h) 자동. Phase 1 precompute와 같은 심볼 조회 시 캐시 히트로 대부분의 OHLCV 왕복 비용 제거.

## 7. signal_log 확장

### 7.1 migration 004

`migrations/004_signal_log_tradesetup.sql`:

```sql
-- Week 9: signal_log에 TradeSetup 컬럼 추가.
-- 실행: Supabase Studio → SQL Editor → Run.

ALTER TABLE signal_log
    ADD COLUMN IF NOT EXISTS entry_price_tradesetup NUMERIC(18,8),
    ADD COLUMN IF NOT EXISTS stop_loss  NUMERIC(18,8),
    ADD COLUMN IF NOT EXISTS take_profit_1 NUMERIC(18,8),
    ADD COLUMN IF NOT EXISTS take_profit_2 NUMERIC(18,8),
    ADD COLUMN IF NOT EXISTS risk_pct   NUMERIC(6,3),
    ADD COLUMN IF NOT EXISTS rr_tp1     NUMERIC(6,3),
    ADD COLUMN IF NOT EXISTS rr_tp2     NUMERIC(6,3),
    ADD COLUMN IF NOT EXISTS sl_basis   TEXT,
    ADD COLUMN IF NOT EXISTS tp1_basis  TEXT,
    ADD COLUMN IF NOT EXISTS tp2_basis  TEXT;
```

**주의:** 기존 `entry_price` 컬럼은 **시그널 발송 시점 종가**로 유지. 신규 `entry_price_tradesetup`은 TradeSetup이 사용한 진입가 (현재는 동일하지만 Week 10+에서 "limit order 진입가" 같은 개념 도입 시 분리).

MVP는 `entry_price_tradesetup = entry_price`로 동일값 저장. Week 10에서 필요 시 분리.

### 7.2 repositories.py `insert_signal_log` 확장

추가 파라미터 (모두 Optional, 관망/회피 시 None):

```python
async def insert_signal_log(
    conn,
    *,
    # 기존 ...
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
) -> int:
```

### 7.3 api.py `signal_endpoint` insert 호출 확장

`result.analysis.trade_setup`이 있으면 추가 필드 채워서 insert.

## 8. 카드 포맷

### 8.1 "진입"/"강진입" 카드 (AAPL 예시)

```
── 2026-04-19 AAPL ──
🟢 장 중
현재가: $184.12 (+1.23%)

구조: 상승추세 (HH-HL)
정렬: 1d↑ 4h↑ 1h↑  (강정렬)
진입조건: RSI(1h) 35 · 거래량 1.5x

세팅:
 진입 $184.12
 손절 $180.50 (-2.0%)
 익절1 $188.50 (+2.4%)  익절2 $193.00 (+4.8%)
 R:R  1.2 / 2.4   리스크 2.0%

종합:  72 | 진입
사주:  56 (😐 관망)

※ 정보 제공 목적. 투자 판단과 손실 책임은 본인에게 있습니다.
```

**포인트:**
- "세팅" 블록 5줄. 모바일 한 화면에 적절.
- `R:R 1.2 / 2.4`: TP1까지 / TP2까지.
- `리스크 2.0%`: 진입~손절 거리. 트레이더가 이 숫자로 포지션 크기 자체 결정.

### 8.2 "관망"/"회피" 카드

```
── 2026-04-19 AAPL ──
🟢 장 중
현재가: $184.12 (+0.23%)

구조: 횡보 (박스)
정렬: 1d→ 4h↑ 1h→  (혼조)
진입조건: RSI(1h) 52 · 거래량 0.9x

주요 레벨:
 저항 $188.50 · $193.00 · $196.50
 지지 $180.50 · $177.00 · $172.00

종합:  48 | 관망
사주:  56 (😐 관망)

※ 정보 제공 목적. 투자 판단과 손실 책임은 본인에게 있습니다.
```

**포인트:**
- "세팅" 블록 대신 "주요 레벨" 블록.
- 지지/저항 각 3개 (가까운 순, 가격만).

### 8.3 `_format_signal_card` 수정

`handlers.py`의 카드 포맷 함수에 등급별 분기 추가:

```python
def _format_signal_card(data: dict) -> str:
    # ... 기존 구조/정렬/진입조건 3줄 ...

    analysis = data.get("analysis") or {}
    grade = data.get("signal_grade", "")

    # 등급별 블록
    if grade in ("강진입", "진입") and analysis.get("trade_setup"):
        _append_trade_setup_block(lines, analysis["trade_setup"])
    elif analysis.get("sr_levels"):
        _append_sr_levels_block(lines, analysis["sr_levels"])
    
    # ... 종합/사주/disclaimer ...
```

## 9. 테스트 전략

| 파일 | 커버리지 |
|------|----------|
| `tests/test_analysis_volume_profile.py` (신규) | VPVR 계산, bucket 경계, 상위 N개 정렬 |
| `tests/test_analysis_support_resistance.py` (신규) | swing-only, volume-only, 겹침(high strength), 현재가 위/아래 구분 |
| `tests/test_analysis_trade_setup.py` (신규) | 순수 ATR, S/R snap 적용, R:R 계산, risk_pct 공식 |
| `tests/test_analysis_composite.py` (수정) | sr_levels + atr_1d 필드 채워지는지 |
| `tests/test_signal_service.py` (수정) | "진입"에 trade_setup 있음, "관망"에 None |
| `tests/test_api.py` 또는 `test_api_ohlcv.py` (신규) | /v1/admin/ohlcv 정상/400/401/502 |
| `tests/test_api_client.py` (수정) | get_admin_ohlcv |
| `tests/test_broadcast.py` (수정) | Phase 0 default가 api_client 호출하는지 mock |
| `tests/test_handlers.py` (수정) | 진입 카드에 "세팅" 블록, 관망 카드에 "주요 레벨" 블록, disclaimer 유지 |
| `tests/test_repositories.py` (수정) | insert_signal_log에 trade_setup 필드 저장 (DB 통합) |

## 10. 관측성

- `logger.info("signal with tradesetup ticker=%s entry=%s sl=%s tp1=%s tp2=%s rr=%s", ...)`
- `logger.info("admin ohlcv ticker=%s interval=%s count=%s since=%s", ...)`
- Phase 0 MFE/MAE 계산 성공 시 기존 로그에 "real klines" 표시.

## 11. 배포

1. 코드 push → Railway 3서비스 자동 재배포.
2. **사용자 수동:** Supabase Studio → `migrations/004_signal_log_tradesetup.sql` 실행.
3. 로컬 스모크: `pytest`, 본인 /signal BTC + AAPL 카드 형태 확인.
4. 운영 스모크:
   - `/signal` (BTC) → "진입"이면 세팅 블록, "관망"이면 주요 레벨.
   - `curl.exe -H "X-SAJUCANDLE-KEY: ..." ".../v1/admin/ohlcv?ticker=BTCUSDT&limit=5"` → 5개 kline 반환.
   - 다음날 broadcast 후 `SELECT mfe_7d_pct, mae_7d_pct FROM signal_log WHERE tracking_done=FALSE LIMIT 5;` → 값 채워져 있는지.

## 12. 위험과 대응

| 위험 | 대응 |
|------|------|
| volume_profile MVP 근사치 | "중간값으로 근사" 주석. Week 11 백테스트 후 고도화 |
| SR snap tolerance 파라미터 튜닝 | module-level 상수로 빼두고 Week 11 조정 |
| TP1/TP2 R:R 이상값 (R:R < 0.5 등) | 카드에 그대로 표시하되 로그 warning. 로직 수정은 Week 10 |
| admin/ohlcv 남용 | limit 500 제한 + X-SAJUCANDLE-KEY 인증. 외부 rate limit 별도 안 검토 (현재 규모 낮음) |
| Phase 0 admin_ohlcv 실패 | try/except + warning → 빈 리스트 반환 → Phase 1/2/3 진행 |
| 기존 signal_log entry_price 스키마 영향 | 신규 컬럼 Optional. 기존 insert 호출 영향 없음 |
| 카드 길이 증가 | 진입 카드 세팅 블록 +5줄, 관망 카드 주요 레벨 +3줄. 모바일 한 화면 유지 가능 |

## 13. 완료 기준

- [ ] `analysis/volume_profile.py` + `support_resistance.py` + `trade_setup.py` 신규 + 단위 테스트 전량 통과
- [ ] `composite.py`가 sr_levels + atr_1d 채움
- [ ] `SignalService`가 "진입/강진입"에만 trade_setup 생성
- [ ] `GET /v1/admin/ohlcv` 엔드포인트 정상 동작 + 4가지 에러 분기 테스트
- [ ] `ApiClient.get_admin_ohlcv` 구현 + 테스트
- [ ] broadcast.py Phase 0 `_default_get_klines`가 admin ohlcv 호출
- [ ] `migrations/004_signal_log_tradesetup.sql` 커밋
- [ ] `repositories.insert_signal_log`가 trade_setup 필드 저장
- [ ] 진입 카드에 "세팅" 블록, 관망/회피 카드에 "주요 레벨" 블록
- [ ] 운영 스모크: /signal 카드 확인 + Supabase signal_log row에 SL/TP 채워짐 + 다음날 MFE/MAE 채워짐

## 14. Week 10~11 예고

- **Week 10:** 시그널 발송 거부 규칙 (BREAKDOWN에서 강진입 차단), 카드 UX 세밀 조정 (이모지/정렬/온보딩), /signal 호출 rate limit
- **Week 11:** MFE/MAE 통계 집계 API + 카드에 "지난 30일 강진입 승률 N%" 프루프 노출, 등급 임계값 재조정, 튜닝 상수(_SL_ATR_MULT 등) 최적화

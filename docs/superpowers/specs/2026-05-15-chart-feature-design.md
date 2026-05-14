# 차트 기능 설계 스펙

## 목표

종목별 캔들스틱 차트 + 사주/퀀트 분석 대시보드 페이지를 추가한다. 무료 영역(차트 + 사주 필터 판정)으로 트래픽을 유도하고, 유료 영역(퀀트 상세 분석)을 블러 마스킹으로 노출하여 결제를 유도한다.

## 핵심 결정 사항

| 항목 | 결정 |
|------|------|
| 페이지 위치 | `/chart` — TabNav 4번째 탭 (📊 차트) |
| 종목 범위 | 사용자 자유 입력. yfinance(주식) / ccxt(코인) 실시간 조회 |
| 차트 라이브러리 | Lightweight Charts (TradingView 오픈소스, ~45KB gzip) |
| 차별화 전략 | C 필터 스크리너 (백테스트 검증 완료, OOS PASS) |
| 과금 모델 | 차트 무료 / 분석 대시보드 유료 (990원/종목, 감정서와 별개 상품) |
| 유료 노출 방식 | 블러 마스킹 — 제목은 선명, 데이터는 blur(6px) |

## 페이지 구조

하나의 세로 스크롤 페이지. 위에서 아래로:

### 1. 검색 바
- 텍스트 입력으로 종목 심볼/이름 검색
- asset_class 자동 판별 (BTC, ETH 등 알려진 코인 심볼 → coin, 나머지 → stock)
- 엔터 또는 검색 버튼으로 조회

### 2. 종목 헤더 (무료)
- 종목 아이콘, 이름, 심볼, 거래소, 섹터
- 현재가, 등락률 (전일 대비)
- 사주 필터 뱃지: ✅ 통과 / ❌ 탈락
- 현재 월 시그널 뱃지: BUY / HOLD / SELL / WATCH / KILL

### 3. 캔들스틱 차트 (무료)
- Lightweight Charts 캔들스틱 시리즈
- 거래량 히스토그램 (하단 overlay)
- MA20 이동평균선
- BUY/SELL 시그널 마커 (월간 시그널을 차트 위에 표시)
- 기간 선택: 1M / 3M / 6M / 1Y / ALL
- 크로스헤어 인터랙션 (hover 시 가격/날짜 표시)

### 4. 퀀트 분석 (유료 — 블러 마스킹)
- 제목 "퀀트 분석" + PRO 뱃지는 선명
- 데이터 영역은 blur(6px) 처리:
  - 기술지표 점수 (ta_score) — 프로그레스 바
  - 거시지표 점수 (macro_score) — 프로그레스 바
  - 펀더멘털 점수 (fa_score, 주식만) — 프로그레스 바
  - 온체인 점수 (onchain_score, 코인만) — 프로그레스 바

### 5. 시그널 이력 (유료 — 블러 마스킹)
- 최근 6개월 시그널 태그 (BUY/HOLD/SELL/WATCH/KILL)
- 각 태그 색상: BUY=green, HOLD/WATCH=yellow, SELL/KILL=red

### 6. 기술지표 세부 (유료 — 블러 마스킹)
- Supertrend 방향 (▲/▼)
- RSI 값
- MACD 상태 (양전환/음전환)
- MA 정배열 여부
- 거래량 추세 (5일/20일 비율)

### 7. 종목 순위 (유료 — 블러 마스킹)
- "필터 통과 종목 중 #N / M" 형태

### 8. CTA 영역
- "🔓 상세 분석 잠금 해제"
- "퀀트 점수 · 기술지표 · 시그널 이력 · 종목 순위"
- 990원으로 해제 버튼 (골드)
- "종목당 1회 결제 · 영구 열람"

## 백엔드 API

### `POST /api/chart/ohlcv`

무료 엔드포인트. OHLCV 캔들 데이터 + 사주 필터 판정 + 현재 시그널 반환.

POST인 이유: 사주 필터 판정에 사용자 생년월일이 필요하고, 이 정보를 URL 쿼리에 노출하지 않기 위해 body로 전달.

**Request body**:
```json
{
  "symbol": "NVDA",
  "asset_class": "stock",
  "months": 3,
  "birth_date": "1990-03-15",
  "birth_time": "14:30",
  "gender": "M"
}
```

**응답**:
```json
{
  "symbol": "NVDA",
  "name": "NVIDIA Corp",
  "asset_class": "stock",
  "current_price": 135.42,
  "price_change_pct": 2.3,
  "saju_filter": {
    "passed": true,
    "threshold": 30
  },
  "current_signal": "BUY",
  "ohlcv": [
    {"date": "2025-02-15", "open": 118.5, "high": 120.1, "low": 117.8, "close": 119.3, "volume": 35000000}
  ],
  "signal_markers": [
    {"date": "2025-03-01", "signal": "BUY"},
    {"date": "2025-04-01", "signal": "HOLD"},
    {"date": "2025-05-01", "signal": "BUY"}
  ]
}
```

사주 필터 응답에서 `saju_score` 수치는 노출하지 않는다 (검증 실패한 점수를 보여주면 오해 유발). 통과/탈락만 반환.

**구현**: 기존 `get_ohlcv()`, `saju_score()`, signal engine 조합.

**시그널 계산 범위**: sample_tickers.csv에 등록된 21종목은 signal engine으로 시그널 계산. 미등록 종목은 사주 필터 판정 + 캔들차트만 제공하고, 시그널은 "미지원" 표시. 유료 분석(ta_score 등)은 미등록 종목도 실시간 계산 가능.

### `GET /api/chart/analysis`

유료 엔드포인트. 결제 검증 후 퀀트 상세 데이터 반환.

**파라미터**:
- `symbol` (str, 필수)
- `asset_class` (str, 기본 "stock")
- `payment_key` (str, 필수): Toss 결제 확인 키

**응답**:
```json
{
  "symbol": "NVDA",
  "quant_scores": {
    "ta_score": {"total": 72, "breakdown": {"supertrend": 25, "ma_alignment": 20, "rsi": 10, "volume": 8, "rs": 9}},
    "macro_score": {"total": 58, "breakdown": {...}},
    "fa_score": {"total": 81, "breakdown": {...}}
  },
  "signal_history": [
    {"month": "2025-05", "signal": "BUY", "quant_score": 72},
    {"month": "2025-04", "signal": "HOLD", "quant_score": 55},
    ...
  ],
  "ta_detail": {
    "supertrend": {"direction": "up", "value": 128.5},
    "rsi": 58.3,
    "macd": {"histogram": 1.2, "status": "positive"},
    "ma_alignment": true,
    "volume_trend": 1.4
  },
  "rank": {"position": 3, "total_passed": 17}
}
```

## 프론트엔드 파일 구조

```
frontend/src/
  app/chart/
    page.tsx              — 차트 페이지 (검색 + 데이터 fetch + 레이아웃)
  components/chart/
    SymbolSearch.tsx       — 검색 바 컴포넌트
    TickerHeader.tsx       — 종목 헤더 (가격, 필터 뱃지, 시그널 뱃지)
    CandleChart.tsx        — Lightweight Charts 래퍼 (캔들 + 볼륨 + MA + 마커)
    PeriodSelector.tsx     — 기간 선택 바 (1M/3M/6M/1Y/ALL)
    AnalysisDashboard.tsx  — 유료 대시보드 (블러 마스킹 + CTA)
  lib/
    api.ts                — 기존 파일에 fetchOhlcv(), fetchAnalysis() 추가
```

## 사주 필터 판정 로직

사용자의 프로필(생년월일/시간)은 프론트엔드 localStorage에 저장되어 있다 (온보딩 시 저장). API 호출 시 birth_date, birth_time, gender를 쿼리 파라미터로 전달하면, 백엔드에서:

1. 사용자 명식 계산 (`SajuCalculator`)
2. 종목의 상장일 기준 명식 계산 (`saju_resolver`)
3. `saju_score()` 계산
4. threshold(30) 미만이면 탈락, 이상이면 통과

## 결제 플로우

감정서 결제와 동일한 Toss Payments 플로우. 상품 구분:

| 상품 | 금액 | orderName |
|------|------|-----------|
| 감정서 봉인 해제 | 990원 | `saju-report-standard` |
| 감정서 PREMIUM | 9,900원 | `saju-report-premium` |
| 차트 분석 해제 | 990원 | `chart-analysis-{symbol}` |

`/api/payments/confirm` 엔드포인트에서 orderId prefix로 상품 타입을 구분한다.

## 기술 제약

- **yfinance 무료 API**: Rate limit 있음. 동일 종목 반복 조회 시 CSV 캐시 사용 (`data/prices/`).
- **ccxt Binance**: USDT 페어만 지원. 심볼 자동 변환 (BTC → BTC/USDT).
- **사주 필터 계산**: 종목의 상장일이 필요. sample_tickers.csv에 없는 종목은 yfinance `.info["ipoDate"]`로 상장일 조회 시도. 상장일 미상이면 사주 필터 뱃지를 "판정 불가 ⚠️"로 표시하고, 캔들차트는 정상 표시.
- **시그널 계산**: sample_tickers 21종목만 시그널 지원. 미등록 종목은 시그널 뱃지를 "미지원"으로 표시. 시그널 마커도 차트에 표시하지 않음.
- **유료 퀀트 분석**: ta_score, macro_score, fa_score는 임의 종목에 대해 실시간 계산 가능 (yfinance OHLCV + ta 라이브러리). 시그널 이력만 미등록 종목은 제공 불가.

## TabNav 변경

```typescript
const TABS = [
  { href: "/feed", label: "오늘", icon: "🔥" },
  { href: "/profile", label: "내 사주", icon: "🕯️" },
  { href: "/chart", label: "차트", icon: "📊" },
  { href: "/report", label: "감정서", icon: "📜" },
];
```

## 비포함 (YAGNI)

- 실시간 가격 업데이트 (웹소켓) — 일봉 기반이면 충분
- 인트라데이 차트 — 일봉만 지원
- 즐겨찾기/워치리스트 — v2에서 고려
- 소셜 공유 기능 — v2에서 고려
- 다중 종목 비교 차트 — v2에서 고려

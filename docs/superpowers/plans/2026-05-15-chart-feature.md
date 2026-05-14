# 차트 기능 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 종목별 캔들스틱 차트 + 사주 필터 스크리너 + 블러 마스킹 유료 대시보드 페이지를 추가한다.

**Architecture:** 백엔드에 `/api/chart/` 라우터 2개 추가 (ohlcv + analysis). 프론트엔드에 `/chart` 페이지 + 5개 컴포넌트. Lightweight Charts로 캔들 렌더링. 유료 영역은 블러 CSS + "준비 중" 토스트 (v1은 구독 결제 미연동).

**Tech Stack:** FastAPI, Lightweight Charts (lightweight-charts npm), Next.js 16, React 19, Tailwind 4

---

## 파일 구조

### 새로 생성하는 파일

| 파일 | 책임 |
|------|------|
| `src/sajucandle/api/routers/chart.py` | `/api/chart/ohlcv` (POST), `/api/chart/analysis` (GET) |
| `frontend/src/app/chart/page.tsx` | 차트 페이지 — 검색 + 데이터 fetch + 레이아웃 |
| `frontend/src/components/chart/SymbolSearch.tsx` | 종목 검색 바 |
| `frontend/src/components/chart/TickerHeader.tsx` | 종목 헤더 (가격, 필터 뱃지, 시그널 뱃지) |
| `frontend/src/components/chart/CandleChart.tsx` | Lightweight Charts 래퍼 |
| `frontend/src/components/chart/PeriodSelector.tsx` | 기간 선택 바 |
| `frontend/src/components/chart/AnalysisDashboard.tsx` | 유료 대시보드 (블러 + CTA) |
| `frontend/src/lib/chart-types.ts` | 차트 전용 타입 정의 |

### 수정하는 파일

| 파일 | 변경 |
|------|------|
| `src/sajucandle/api/main.py` | chart 라우터 등록 |
| `frontend/src/components/TabNav.tsx` | 📊 차트 탭 추가 |
| `frontend/src/lib/api.ts` | `fetchChartOhlcv()` 함수 추가 |
| `frontend/package.json` | `lightweight-charts` 의존성 추가 |

---

### Task 1: 차트 전용 타입 정의

**Files:**
- Create: `frontend/src/lib/chart-types.ts`

- [ ] **Step 1: 타입 파일 생성**

```typescript
// frontend/src/lib/chart-types.ts

export interface OhlcvBar {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface SajuFilter {
  passed: boolean | null;    // null = 판정 불가
  threshold: number;
}

export interface SignalMarker {
  date: string;
  signal: string;
}

export interface ChartOhlcvResponse {
  symbol: string;
  name: string;
  asset_class: string;
  current_price: number;
  price_change_pct: number;
  saju_filter: SajuFilter;
  current_signal: string | null;   // null = 미지원 종목
  ohlcv: OhlcvBar[];
  signal_markers: SignalMarker[];
}

export interface QuantScoreDetail {
  total: number;
  breakdown: Record<string, number>;
}

export interface TaDetail {
  supertrend: { direction: string; value: number };
  rsi: number;
  macd: { histogram: number; status: string };
  ma_alignment: boolean;
  volume_trend: number;
}

export interface SignalHistoryItem {
  month: string;
  signal: string;
  quant_score: number;
}

export interface ChartAnalysisResponse {
  symbol: string;
  quant_scores: {
    ta_score: QuantScoreDetail;
    macro_score: QuantScoreDetail;
    fa_score?: QuantScoreDetail;
    onchain_score?: QuantScoreDetail;
  };
  signal_history: SignalHistoryItem[];
  ta_detail: TaDetail;
  rank: { position: number; total_passed: number };
}
```

- [ ] **Step 2: 커밋**

```bash
git add frontend/src/lib/chart-types.ts
git commit -m "feat(chart): add chart feature type definitions"
```

---

### Task 2: 백엔드 차트 라우터

**Files:**
- Create: `src/sajucandle/api/routers/chart.py`
- Modify: `src/sajucandle/api/main.py`

- [ ] **Step 1: chart.py 라우터 생성**

```python
# src/sajucandle/api/routers/chart.py
"""차트 라우터 — /api/chart/ohlcv, /api/chart/analysis."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from sajucandle.manseryeok.core import get_saju_calculator
from sajucandle.quant.price_data import get_ohlcv
from sajucandle.quant.technical import ta_score_stock, ta_score_coin
from sajucandle.saju.scorer import saju_score
from sajucandle.ticker.loader import load_tickers
from sajucandle.ticker.saju_resolver import resolve_ticker_saju
from sajucandle.ticker.schema import TickerRecord

router = APIRouter()

# 알려진 코인 심볼 (asset_class 자동 판별용)
_KNOWN_COINS = {
    "BTC", "ETH", "SOL", "DOGE", "BNB", "XRP",
    "AVAX", "LINK", "MATIC", "ADA", "DOT", "ATOM",
}


def _guess_asset_class(symbol: str) -> str:
    """심볼로 asset_class 추론. 알려진 코인이면 coin, 나머지 stock."""
    clean = symbol.upper().replace("-USD", "").replace("/USDT", "")
    return "coin" if clean in _KNOWN_COINS else "stock"


def _get_ticker_record(symbol: str, asset_class: str) -> Optional[TickerRecord]:
    """sample_tickers에서 종목 레코드 조회. 없으면 None."""
    tickers = load_tickers()
    # 정확 매치
    if symbol in tickers:
        return tickers[symbol]
    # 코인: BTC → BTC-USD 매치
    if asset_class == "coin":
        alt = f"{symbol}-USD"
        if alt in tickers:
            return tickers[alt]
    return None


def _compute_saju_filter(
    symbol: str,
    asset_class: str,
    gender: str = "M",
    threshold: float = 30.0,
) -> dict:
    """C 필터 판정: 종목 사주 × 오늘 일진/세운 궁합 점수가 threshold 이상이면 통과.
    종목 상장일 미상이면 passed=None 반환."""
    rec = _get_ticker_record(symbol, asset_class)
    if rec is None or not rec.listing_date:
        return {"passed": None, "threshold": threshold}

    calc = get_saju_calculator()

    # 종목 사주
    resolved = resolve_ticker_saju(calc, rec)
    if not resolved.get("primary_pillar"):
        return {"passed": None, "threshold": threshold}

    primary_source = resolved["primary_source"]
    if primary_source == "founding":
        primary_saju = resolved["components"]["founding"]["saju"]
    elif primary_source == "listing":
        primary_saju = resolved["components"]["listing"]["saju"]
    else:
        primary_saju = resolved["components"]["transition"][0]["saju"]

    # C 필터: 종목 사주 × 오늘 일진/세운/월운 궁합 점수
    # (saju_score는 사용자 명식이 아닌 종목×일진 궁합을 평가)
    sc = saju_score(
        calc=calc,
        ticker_primary_pillar=resolved["primary_pillar"],
        ticker_saju=primary_saju,
        target_dt=datetime.now(),
        gender_of_user=gender,
    )
    score = sc["total_100"]
    return {"passed": score >= threshold, "threshold": threshold}


def _get_ticker_name(symbol: str, asset_class: str) -> str:
    """종목 이름 조회. 미등록이면 심볼 반환."""
    rec = _get_ticker_record(symbol, asset_class)
    return rec.name if rec else symbol


def _get_current_signal(symbol: str, asset_class: str) -> Optional[str]:
    """sample_tickers 등록 종목만 시그널 반환. 미등록이면 None."""
    rec = _get_ticker_record(symbol, asset_class)
    if rec is None:
        return None
    # 시그널 엔진 호출은 무거우므로 간소화:
    # 캐시된 시그널이 있으면 사용, 없으면 None
    # v1에서는 시그널 계산을 생략하고 None 반환
    # TODO v2: 시그널 캐시 레이어 추가
    return None


# ── 스키마 ────────────────────────────────────────────

class ChartOhlcvRequest(BaseModel):
    symbol: str
    asset_class: Optional[str] = None
    months: int = 3
    birth_date: str = ""
    birth_time: str = "00:00"
    gender: str = "M"


# ── 라우트 ────────────────────────────────────────────

@router.post("/api/chart/ohlcv")
def chart_ohlcv(req: ChartOhlcvRequest):
    """캔들 데이터 + 사주 필터 판정 + 현재 시그널."""
    symbol = req.symbol.upper().strip()
    if not symbol:
        raise HTTPException(status_code=400, detail="종목 심볼을 입력해주세요")

    asset_class = req.asset_class or _guess_asset_class(symbol)

    # OHLCV 조회
    end = datetime.now()
    start = end - timedelta(days=req.months * 31)
    try:
        df = get_ohlcv(symbol, asset_class, start, end)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"가격 데이터를 가져올 수 없습니다: {symbol}")

    if df.empty:
        raise HTTPException(status_code=404, detail=f"가격 데이터가 없습니다: {symbol}")

    # 현재가 / 등락률
    current_price = float(df["close"].iloc[-1])
    if len(df) >= 2:
        prev_close = float(df["close"].iloc[-2])
        price_change_pct = round((current_price - prev_close) / prev_close * 100, 2)
    else:
        price_change_pct = 0.0

    # 사주 필터
    saju_filter = {"passed": None, "threshold": 30}
    try:
        saju_filter = _compute_saju_filter(
            symbol, asset_class, req.gender,
        )
    except Exception:
        saju_filter = {"passed": None, "threshold": 30}

    # OHLCV를 JSON 직렬화
    ohlcv_list = []
    for idx, row in df.iterrows():
        ohlcv_list.append({
            "date": idx.strftime("%Y-%m-%d"),
            "open": round(float(row["open"]), 2),
            "high": round(float(row["high"]), 2),
            "low": round(float(row["low"]), 2),
            "close": round(float(row["close"]), 2),
            "volume": int(row["volume"]),
        })

    return {
        "symbol": symbol,
        "name": _get_ticker_name(symbol, asset_class),
        "asset_class": asset_class,
        "current_price": round(current_price, 2),
        "price_change_pct": price_change_pct,
        "saju_filter": saju_filter,
        "current_signal": _get_current_signal(symbol, asset_class),
        "ohlcv": ohlcv_list,
        "signal_markers": [],  # v1: 시그널 마커 미구현
    }


@router.get("/api/chart/analysis")
def chart_analysis(symbol: str, asset_class: str = "stock"):
    """퀀트 상세 분석 (유료). v1에서는 프론트에서 호출하지 않음."""
    symbol = symbol.upper().strip()

    end = datetime.now()
    start = end - timedelta(days=400)
    df = get_ohlcv(symbol, asset_class, start, end)
    if df.empty or len(df) < 30:
        raise HTTPException(status_code=404, detail="분석에 필요한 데이터가 부족합니다")

    # 벤치마크
    bench_sym = "SPY" if asset_class == "stock" else "BTC-USD"
    bench_df = get_ohlcv(bench_sym, asset_class, start, end)

    # TA score
    if asset_class == "stock":
        ta = ta_score_stock(df, bench_df)
    else:
        ta = ta_score_coin(df, bench_df)

    return {
        "symbol": symbol,
        "quant_scores": {
            "ta_score": {"total": ta["total"], "breakdown": ta.get("breakdown", {})},
            "macro_score": {"total": 50, "breakdown": {}},   # v1 간소화
        },
        "signal_history": [],  # v1: 미구현
        "ta_detail": ta.get("breakdown", {}),
        "rank": {"position": 0, "total_passed": 0},  # v1: 미구현
    }
```

- [ ] **Step 2: main.py에 chart 라우터 등록**

`src/sajucandle/api/main.py` 수정:

import 추가:
```python
from sajucandle.api.routers import signals, saju, payments, chart
```

라우터 등록 추가 (마지막 `include_router` 뒤에):
```python
app.include_router(chart.router)
```

- [ ] **Step 3: 로컬 테스트**

Run:
```bash
PYTHONPATH=src ./.venv/Scripts/python.exe -c "
from sajucandle.api.routers.chart import _guess_asset_class, _get_ticker_record
print(_guess_asset_class('NVDA'))   # stock
print(_guess_asset_class('BTC'))    # coin
print(_get_ticker_record('NVDA', 'stock'))  # TickerRecord or None
print(_get_ticker_record('RANDOM', 'stock'))  # None
"
```

Expected: `stock`, `coin`, `TickerRecord(...)`, `None`

- [ ] **Step 4: 커밋**

```bash
git add src/sajucandle/api/routers/chart.py src/sajucandle/api/main.py
git commit -m "feat(api): add /api/chart/ohlcv and /api/chart/analysis endpoints"
```

---

### Task 3: lightweight-charts 의존성 추가

**Files:**
- Modify: `frontend/package.json`

- [ ] **Step 1: npm install**

```bash
cd frontend && npm install lightweight-charts
```

- [ ] **Step 2: 설치 확인**

```bash
ls frontend/node_modules/lightweight-charts/dist/lightweight-charts.standalone.production.js
```

Expected: 파일 존재

- [ ] **Step 3: 커밋**

```bash
git add frontend/package.json frontend/package-lock.json
git commit -m "chore(frontend): add lightweight-charts dependency"
```

---

### Task 4: TabNav에 차트 탭 추가

**Files:**
- Modify: `frontend/src/components/TabNav.tsx`

- [ ] **Step 1: TABS 배열 수정**

기존:
```typescript
const TABS = [
  { href: "/feed", label: "오늘", icon: "🔥" },
  { href: "/profile", label: "내 사주", icon: "🕯️" },
  { href: "/report", label: "감정서", icon: "📜" },
];
```

변경:
```typescript
const TABS = [
  { href: "/feed", label: "오늘", icon: "🔥" },
  { href: "/profile", label: "내 사주", icon: "🕯️" },
  { href: "/chart", label: "차트", icon: "📊" },
  { href: "/report", label: "감정서", icon: "📜" },
];
```

- [ ] **Step 2: 빌드 확인**

```bash
cd frontend && npx next build
```

Expected: 빌드 성공 (차트 페이지가 아직 없으므로 /chart 접근 시 404이지만 빌드 자체는 통과)

- [ ] **Step 3: 커밋**

```bash
git add frontend/src/components/TabNav.tsx
git commit -m "feat(nav): add chart tab to TabNav"
```

---

### Task 5: API 클라이언트 함수 추가

**Files:**
- Modify: `frontend/src/lib/api.ts`

- [ ] **Step 1: fetchChartOhlcv 함수 추가**

파일 끝에 추가:

```typescript
import type { ChartOhlcvResponse } from "./chart-types";

export function fetchChartOhlcv(params: {
  symbol: string;
  asset_class?: string;
  months?: number;
  birth_date?: string;
  birth_time?: string;
  gender?: string;
}): Promise<ChartOhlcvResponse> {
  return api(`${API_BASE}/api/chart/ohlcv`, postJson(params, 30000));
}
```

주의: import 문은 파일 상단의 기존 import 블록 아래에 추가.

- [ ] **Step 2: 커밋**

```bash
git add frontend/src/lib/api.ts
git commit -m "feat(api): add fetchChartOhlcv client function"
```

---

### Task 6: SymbolSearch 컴포넌트

**Files:**
- Create: `frontend/src/components/chart/SymbolSearch.tsx`

- [ ] **Step 1: 컴포넌트 생성**

```tsx
// frontend/src/components/chart/SymbolSearch.tsx
"use client";

import { useState } from "react";

interface Props {
  onSearch: (symbol: string) => void;
  loading: boolean;
}

export default function SymbolSearch({ onSearch, loading }: Props) {
  const [input, setInput] = useState("");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = input.trim().toUpperCase();
    if (trimmed) onSearch(trimmed);
  };

  return (
    <form
      onSubmit={handleSubmit}
      className="flex items-center gap-2 px-4 py-3 bg-zinc-900 border-b border-zinc-800"
    >
      <span className="text-zinc-500 text-sm">🔍</span>
      <input
        type="text"
        value={input}
        onChange={(e) => setInput(e.target.value)}
        placeholder="종목 검색... NVDA, BTC, AAPL"
        className="flex-1 bg-transparent text-zinc-100 text-sm placeholder-zinc-600 outline-none"
        disabled={loading}
      />
      <button
        type="submit"
        disabled={loading || !input.trim()}
        className="text-xs text-amber-400 font-medium px-3 py-1.5 rounded-md bg-amber-400/10 disabled:opacity-40"
      >
        {loading ? "조회 중..." : "조회"}
      </button>
    </form>
  );
}
```

- [ ] **Step 2: 커밋**

```bash
git add frontend/src/components/chart/SymbolSearch.tsx
git commit -m "feat(chart): add SymbolSearch component"
```

---

### Task 7: TickerHeader 컴포넌트

**Files:**
- Create: `frontend/src/components/chart/TickerHeader.tsx`

- [ ] **Step 1: 컴포넌트 생성**

```tsx
// frontend/src/components/chart/TickerHeader.tsx
"use client";

import type { ChartOhlcvResponse } from "@/lib/chart-types";

interface Props {
  data: ChartOhlcvResponse;
}

const SIGNAL_COLORS: Record<string, string> = {
  BUY: "text-green-400 bg-green-400/10 border-green-400/30",
  HOLD: "text-amber-400 bg-amber-400/10 border-amber-400/30",
  SELL: "text-red-400 bg-red-400/10 border-red-400/30",
  WATCH: "text-amber-400 bg-amber-400/10 border-amber-400/30",
  KILL: "text-red-400 bg-red-400/10 border-red-400/30",
};

export default function TickerHeader({ data }: Props) {
  const changeColor = data.price_change_pct >= 0 ? "text-green-400" : "text-red-400";
  const changeSign = data.price_change_pct >= 0 ? "+" : "";

  // 사주 필터 뱃지
  let filterBadge: React.ReactNode;
  if (data.saju_filter.passed === true) {
    filterBadge = (
      <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-green-400/10 border border-green-400/20">
        <span className="text-sm">✅</span>
        <div>
          <div className="text-green-400 text-xs font-bold">사주 필터 통과</div>
          <div className="text-green-400/60 text-[10px]">내 명식과 상충 없음</div>
        </div>
      </div>
    );
  } else if (data.saju_filter.passed === false) {
    filterBadge = (
      <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-red-400/10 border border-red-400/20">
        <span className="text-sm">❌</span>
        <div>
          <div className="text-red-400 text-xs font-bold">사주 필터 탈락</div>
          <div className="text-red-400/60 text-[10px]">명식 상충 감지</div>
        </div>
      </div>
    );
  } else {
    filterBadge = (
      <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-zinc-700/30 border border-zinc-700/40">
        <span className="text-sm">⚠️</span>
        <div>
          <div className="text-zinc-400 text-xs font-bold">판정 불가</div>
          <div className="text-zinc-500 text-[10px]">상장일 미상</div>
        </div>
      </div>
    );
  }

  return (
    <div className="px-4 py-4 bg-gradient-to-br from-zinc-900 to-zinc-950">
      {/* 종목 이름 */}
      <div className="flex items-center gap-3 mb-2">
        <div className="w-9 h-9 rounded-lg bg-amber-400/10 border border-amber-400/30 flex items-center justify-center text-[10px] text-amber-400 font-bold">
          {data.symbol.slice(0, 2)}
        </div>
        <div>
          <div className="text-white text-lg font-bold tracking-tight">{data.name}</div>
          <div className="text-zinc-500 text-xs">
            {data.symbol} · {data.asset_class === "coin" ? "Crypto" : "Stock"}
          </div>
        </div>
      </div>

      {/* 가격 */}
      <div className="flex items-baseline gap-2 mb-3">
        <span className="text-white text-2xl font-bold tracking-tight">
          {data.asset_class === "coin" ? "" : "$"}{data.current_price.toLocaleString()}
        </span>
        <span className={`text-sm font-semibold ${changeColor}`}>
          {changeSign}{data.price_change_pct}%
        </span>
      </div>

      {/* 뱃지 */}
      <div className="flex gap-2 flex-wrap">
        {filterBadge}
        {data.current_signal ? (
          <div className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg border ${SIGNAL_COLORS[data.current_signal] || "text-zinc-400 bg-zinc-700/30 border-zinc-700/40"}`}>
            <span className="text-sm">📊</span>
            <div>
              <div className="text-xs font-bold">{data.current_signal}</div>
              <div className="text-[10px] opacity-60">
                {new Date().getMonth() + 1}월 시그널
              </div>
            </div>
          </div>
        ) : (
          <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-zinc-700/30 border border-zinc-700/40">
            <span className="text-sm">📊</span>
            <div>
              <div className="text-zinc-500 text-xs font-bold">시그널 미지원</div>
              <div className="text-zinc-600 text-[10px]">미등록 종목</div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: 커밋**

```bash
git add frontend/src/components/chart/TickerHeader.tsx
git commit -m "feat(chart): add TickerHeader component with saju filter badge"
```

---

### Task 8: PeriodSelector 컴포넌트

**Files:**
- Create: `frontend/src/components/chart/PeriodSelector.tsx`

- [ ] **Step 1: 컴포넌트 생성**

```tsx
// frontend/src/components/chart/PeriodSelector.tsx
"use client";

const PERIODS = [
  { label: "1M", months: 1 },
  { label: "3M", months: 3 },
  { label: "6M", months: 6 },
  { label: "1Y", months: 12 },
  { label: "ALL", months: 60 },
];

interface Props {
  selected: number;
  onSelect: (months: number) => void;
}

export default function PeriodSelector({ selected, onSelect }: Props) {
  return (
    <div className="flex gap-1 justify-center py-2 bg-zinc-950 border-b border-zinc-800">
      {PERIODS.map(({ label, months }) => (
        <button
          key={label}
          onClick={() => onSelect(months)}
          className={`text-xs px-3 py-1 rounded ${
            selected === months
              ? "text-amber-400 bg-amber-400/15 font-semibold"
              : "text-zinc-500 hover:text-zinc-300"
          }`}
        >
          {label}
        </button>
      ))}
    </div>
  );
}
```

- [ ] **Step 2: 커밋**

```bash
git add frontend/src/components/chart/PeriodSelector.tsx
git commit -m "feat(chart): add PeriodSelector component"
```

---

### Task 9: CandleChart 컴포넌트 (Lightweight Charts)

**Files:**
- Create: `frontend/src/components/chart/CandleChart.tsx`

- [ ] **Step 1: 컴포넌트 생성**

```tsx
// frontend/src/components/chart/CandleChart.tsx
"use client";

import { useEffect, useRef } from "react";
import type { OhlcvBar, SignalMarker } from "@/lib/chart-types";

interface Props {
  ohlcv: OhlcvBar[];
  markers: SignalMarker[];
}

export default function CandleChart({ ohlcv, markers }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<ReturnType<typeof import("lightweight-charts").createChart> | null>(null);

  useEffect(() => {
    if (!containerRef.current || ohlcv.length === 0) return;

    // Dynamic import — lightweight-charts는 SSR 불가
    let cancelled = false;

    import("lightweight-charts").then((LWC) => {
      if (cancelled || !containerRef.current) return;

      // 기존 차트 제거
      if (chartRef.current) {
        chartRef.current.remove();
        chartRef.current = null;
      }

      const chart = LWC.createChart(containerRef.current, {
        width: containerRef.current.clientWidth,
        height: 300,
        layout: {
          background: { type: LWC.ColorType.Solid, color: "#0a0f1e" },
          textColor: "#666",
          fontSize: 11,
        },
        grid: {
          vertLines: { color: "#1e293b40" },
          horzLines: { color: "#1e293b40" },
        },
        crosshair: {
          mode: LWC.CrosshairMode.Normal,
          vertLine: { color: "#fbbf2440", labelBackgroundColor: "#fbbf24" },
          horzLine: { color: "#fbbf2440", labelBackgroundColor: "#fbbf24" },
        },
        rightPriceScale: {
          borderColor: "#1e293b",
          scaleMargins: { top: 0.1, bottom: 0.2 },
        },
        timeScale: {
          borderColor: "#1e293b",
          timeVisible: false,
        },
      });

      chartRef.current = chart;

      // 캔들스틱
      const candleSeries = chart.addCandlestickSeries({
        upColor: "#4ade80",
        downColor: "#ef4444",
        borderDownColor: "#ef4444",
        borderUpColor: "#4ade80",
        wickDownColor: "#ef444488",
        wickUpColor: "#4ade8088",
      });

      const candleData = ohlcv.map((bar) => ({
        time: bar.date as string,
        open: bar.open,
        high: bar.high,
        low: bar.low,
        close: bar.close,
      }));
      candleSeries.setData(candleData);

      // 거래량
      const volumeSeries = chart.addHistogramSeries({
        priceFormat: { type: "volume" },
        priceScaleId: "vol",
      });
      volumeSeries.setData(
        ohlcv.map((bar) => ({
          time: bar.date as string,
          value: bar.volume,
          color: bar.close >= bar.open ? "#4ade8020" : "#ef444420",
        })),
      );
      chart.priceScale("vol").applyOptions({
        scaleMargins: { top: 0.85, bottom: 0 },
      });

      // MA20
      const ma20Data: { time: string; value: number }[] = [];
      for (let i = 19; i < ohlcv.length; i++) {
        let sum = 0;
        for (let j = i - 19; j <= i; j++) sum += ohlcv[j].close;
        ma20Data.push({ time: ohlcv[i].date, value: +(sum / 20).toFixed(2) });
      }
      if (ma20Data.length > 0) {
        const maSeries = chart.addLineSeries({
          color: "#fbbf2480",
          lineWidth: 1,
          priceLineVisible: false,
          lastValueVisible: false,
        });
        maSeries.setData(ma20Data);
      }

      // 시그널 마커
      if (markers.length > 0) {
        const MARKER_MAP: Record<string, { position: string; color: string; shape: string }> = {
          BUY: { position: "belowBar", color: "#4ade80", shape: "arrowUp" },
          SELL: { position: "aboveBar", color: "#ef4444", shape: "arrowDown" },
          HOLD: { position: "belowBar", color: "#fbbf24", shape: "circle" },
          WATCH: { position: "belowBar", color: "#fbbf24", shape: "circle" },
          KILL: { position: "aboveBar", color: "#ef4444", shape: "arrowDown" },
        };
        const chartMarkers = markers
          .filter((m) => MARKER_MAP[m.signal])
          .map((m) => ({
            time: m.date as string,
            ...(MARKER_MAP[m.signal] as any),
            text: m.signal,
          }));
        if (chartMarkers.length > 0) {
          candleSeries.setMarkers(chartMarkers);
        }
      }

      chart.timeScale().fitContent();

      // 리사이즈
      const ro = new ResizeObserver((entries) => {
        if (entries[0]) {
          chart.applyOptions({ width: entries[0].contentRect.width });
        }
      });
      ro.observe(containerRef.current);

      // cleanup에 ro 해제 추가
      return () => {
        ro.disconnect();
      };
    });

    return () => {
      cancelled = true;
      if (chartRef.current) {
        chartRef.current.remove();
        chartRef.current = null;
      }
    };
  }, [ohlcv, markers]);

  return <div ref={containerRef} className="w-full h-[300px] bg-[#0a0f1e]" />;
}
```

- [ ] **Step 2: 커밋**

```bash
git add frontend/src/components/chart/CandleChart.tsx
git commit -m "feat(chart): add CandleChart component with Lightweight Charts"
```

---

### Task 10: AnalysisDashboard 컴포넌트 (블러 마스킹 + CTA)

**Files:**
- Create: `frontend/src/components/chart/AnalysisDashboard.tsx`

- [ ] **Step 1: 컴포넌트 생성**

```tsx
// frontend/src/components/chart/AnalysisDashboard.tsx
"use client";

interface Props {
  symbol: string;
}

function ScoreBar({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div className="mb-2.5">
      <div className="flex justify-between mb-1">
        <span className="text-zinc-400 text-xs">{label}</span>
        <span className={`text-xs font-bold ${color}`}>{value}</span>
      </div>
      <div className="h-1.5 bg-zinc-800 rounded-full">
        <div
          className="h-1.5 rounded-full"
          style={{ width: `${value}%`, background: value >= 60 ? "#4ade80" : "#fbbf24" }}
        />
      </div>
    </div>
  );
}

export default function AnalysisDashboard({ symbol }: Props) {
  const handleCta = () => {
    alert("구독 서비스 준비 중입니다. 곧 만나요!");
  };

  return (
    <div>
      {/* 퀀트 분석 — 블러 */}
      <div className="px-4 py-3.5 bg-zinc-900 border-t border-zinc-800/50">
        <div className="flex items-center gap-2 mb-3">
          <span className="text-white text-sm font-bold">퀀트 분석</span>
          <span className="text-[9px] px-1.5 py-0.5 rounded bg-amber-400/20 text-amber-400">PRO</span>
        </div>
        <div className="blur-[6px] pointer-events-none select-none">
          <ScoreBar label="기술지표 (TA)" value={72} color="text-green-400" />
          <ScoreBar label="거시지표 (Macro)" value={58} color="text-amber-400" />
          <ScoreBar label="펀더멘털 (FA)" value={81} color="text-green-400" />
        </div>
      </div>

      {/* 시그널 이력 — 블러 */}
      <div className="px-4 py-3.5 bg-zinc-900 border-t border-zinc-800/30">
        <div className="text-white text-sm font-bold mb-2.5">시그널 이력</div>
        <div className="blur-[5px] pointer-events-none select-none">
          <div className="flex gap-1.5 flex-wrap">
            {["5월 BUY", "4월 HOLD", "3월 BUY", "2월 WATCH", "1월 SELL", "12월 BUY"].map((t, i) => {
              const color = t.includes("BUY")
                ? "bg-green-400/10 text-green-400"
                : t.includes("SELL")
                ? "bg-red-400/10 text-red-400"
                : "bg-amber-400/10 text-amber-400";
              return (
                <span key={i} className={`text-[11px] px-2.5 py-1 rounded-md font-medium ${color}`}>
                  {t}
                </span>
              );
            })}
          </div>
        </div>
      </div>

      {/* 기술지표 세부 — 블러 */}
      <div className="px-4 py-3.5 bg-zinc-900 border-t border-zinc-800/30">
        <div className="text-white text-sm font-bold mb-2.5">기술지표 세부</div>
        <div className="blur-[5px] pointer-events-none select-none text-xs text-zinc-400">
          {[
            ["Supertrend (10,3)", "▲ 상승", "text-green-400"],
            ["RSI (14)", "58.3", "text-amber-400"],
            ["MACD 히스토그램", "+ 양전환", "text-green-400"],
            ["MA 정배열 (20/60/200)", "✓", "text-green-400"],
            ["거래량 추세", "1.4x", "text-green-400"],
          ].map(([label, value, color], i) => (
            <div key={i} className="flex justify-between py-1 border-b border-zinc-800/50 last:border-b-0">
              <span>{label}</span>
              <span className={`font-semibold ${color}`}>{value}</span>
            </div>
          ))}
        </div>
      </div>

      {/* 종목 순위 — 블러 */}
      <div className="px-4 py-3 bg-zinc-800/50 border-t border-zinc-800/30">
        <div className="blur-[5px] pointer-events-none select-none flex justify-between items-center">
          <span className="text-zinc-400 text-xs">필터 통과 종목 중 순위</span>
          <span className="text-amber-400 text-xl font-bold">#3 / 17</span>
        </div>
      </div>

      {/* CTA */}
      <div className="px-4 py-6 text-center bg-gradient-to-b from-zinc-900 to-zinc-950 border-t-2 border-amber-400/30">
        <div className="text-amber-400 text-base font-bold mb-1">🔓 상세 분석 잠금 해제</div>
        <div className="text-zinc-500 text-xs mb-4">
          퀀트 점수 · 기술지표 · 시그널 이력 · 종목 순위
        </div>
        <button
          onClick={handleCta}
          className="bg-gradient-to-r from-amber-400 to-amber-500 text-black px-8 py-3 rounded-lg text-sm font-bold shadow-lg shadow-amber-400/30"
        >
          월 4,900원 구독
        </button>
        <div className="text-zinc-600 text-[10px] mt-2.5">전 종목 무제한 분석</div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: 커밋**

```bash
git add frontend/src/components/chart/AnalysisDashboard.tsx
git commit -m "feat(chart): add AnalysisDashboard with blur masking and CTA"
```

---

### Task 11: 차트 페이지 조립

**Files:**
- Create: `frontend/src/app/chart/page.tsx`

- [ ] **Step 1: 페이지 생성**

```tsx
// frontend/src/app/chart/page.tsx
"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { loadUser } from "@/lib/storage";
import { fetchChartOhlcv } from "@/lib/api";
import type { ChartOhlcvResponse } from "@/lib/chart-types";
import TabNav from "@/components/TabNav";
import SymbolSearch from "@/components/chart/SymbolSearch";
import TickerHeader from "@/components/chart/TickerHeader";
import CandleChart from "@/components/chart/CandleChart";
import PeriodSelector from "@/components/chart/PeriodSelector";
import AnalysisDashboard from "@/components/chart/AnalysisDashboard";

export default function ChartPage() {
  const router = useRouter();
  const [data, setData] = useState<ChartOhlcvResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [months, setMonths] = useState(3);

  const handleSearch = async (symbol: string, periodMonths?: number) => {
    setLoading(true);
    setError(null);

    const m = periodMonths ?? months;
    const user = loadUser();

    try {
      const result = await fetchChartOhlcv({
        symbol,
        months: m,
        birth_date: user
          ? `${user.year}-${String(user.month).padStart(2, "0")}-${String(user.day).padStart(2, "0")}`
          : undefined,
        birth_time: user?.hour !== undefined ? `${String(user.hour).padStart(2, "0")}:00` : undefined,
        gender: user?.gender,
      });
      setData(result);
    } catch (err: any) {
      setError(err.message || "조회에 실패했습니다");
      setData(null);
    } finally {
      setLoading(false);
    }
  };

  const handlePeriodChange = (m: number) => {
    setMonths(m);
    if (data) {
      handleSearch(data.symbol, m);
    }
  };

  return (
    <div className="min-h-screen bg-zinc-950">
      <TabNav />

      <SymbolSearch onSearch={handleSearch} loading={loading} />

      {error && (
        <div className="px-4 py-8 text-center">
          <p className="text-red-400 text-sm">{error}</p>
        </div>
      )}

      {!data && !error && !loading && (
        <div className="px-4 py-16 text-center">
          <p className="text-zinc-600 text-4xl mb-3">📊</p>
          <p className="text-zinc-500 text-sm">종목을 검색하면 차트가 표시됩니다</p>
          <p className="text-zinc-600 text-xs mt-1">NVDA, BTC, AAPL, ETH ...</p>
        </div>
      )}

      {loading && !data && (
        <div className="px-4 py-16 text-center">
          <p className="text-amber-400 text-sm animate-pulse">차트 데이터 조회 중...</p>
        </div>
      )}

      {data && (
        <>
          <TickerHeader data={data} />
          <CandleChart ohlcv={data.ohlcv} markers={data.signal_markers} />
          <PeriodSelector selected={months} onSelect={handlePeriodChange} />
          <AnalysisDashboard symbol={data.symbol} />
        </>
      )}
    </div>
  );
}
```

- [ ] **Step 2: 빌드 확인**

```bash
cd frontend && npx next build
```

Expected: 빌드 성공

- [ ] **Step 3: 커밋**

```bash
git add frontend/src/app/chart/page.tsx
git commit -m "feat(chart): add chart page assembling all components"
```

---

### Task 12: 통합 테스트 (로컬)

- [ ] **Step 1: 백엔드 시작**

```bash
PYTHONPATH=src ./.venv/Scripts/python.exe -m uvicorn sajucandle.api.main:app --port 8001
```

- [ ] **Step 2: 프론트엔드 시작**

```bash
cd frontend && npm run dev
```

- [ ] **Step 3: 브라우저에서 확인**

1. `http://localhost:3000/chart` 접속
2. TabNav에 📊 차트 탭 표시 확인
3. 검색창에 "NVDA" 입력 → 조회
4. 종목 헤더 (NVIDIA Corp, 가격, 사주 필터 뱃지) 표시 확인
5. 캔들스틱 차트 (캔들 + 볼륨 + MA20) 렌더링 확인
6. 기간 선택 바 (1M/3M/6M/1Y/ALL) 클릭 시 리로드 확인
7. 스크롤 다운 → 블러 마스킹된 유료 영역 확인
8. "월 4,900원 구독" 버튼 클릭 → "준비 중" alert 확인
9. "BTC" 검색 → 코인 차트 확인

- [ ] **Step 4: 최종 커밋 (필요 시)**

빌드/린트 수정 후:
```bash
git add -A
git commit -m "fix(chart): build and lint fixes for chart feature"
```

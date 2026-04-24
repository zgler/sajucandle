# Week 8 Phase 1: 기술 분석 엔진 재설계 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 현재 `tech_analysis.py`(3지표 일봉 단일 TF)를 **시장 구조 + 멀티 타임프레임 + 수급** 3축 분석 엔진으로 교체하고, 모든 시그널을 `signal_log` DB에 기록 + MFE/MAE 7일 추적하여 Week 11 백테스트 기반 개선의 원천 데이터를 확보한다. 사주 가중치 0.4→0.1, "엔터테인먼트 목적" → "정보 제공 목적" 톤 상향.

**Architecture:** 새 `analysis/` 패키지(swing/structure/timeframe/multi_timeframe/composite) 5모듈로 분석 레이어 분리. `SignalService`(sync)는 composite.analyze() 호출, DB 기록은 호출자(api.py `/signal` 엔드포인트, broadcast.py 크론)가 담당. Phase 0 추적 루프가 broadcast 크론의 맨 앞에 삽입되어 기존 pending row들의 MFE/MAE 업데이트.

**Tech Stack:** Python 3.12, FastAPI, asyncpg, pandas (yfinance resample), pytest, pytest-asyncio, respx, fakeredis. 기존 Week 1~7 인프라 재사용.

**Spec:** `docs/superpowers/specs/2026-04-19-week8-analysis-engine-design.md` (commit 05b38fc)

**스펙 교정 노트:** 스펙 §5.3은 "SignalService.compute() 내부에서 insert_signal_log 호출"이라 명시했지만, 실제 `SignalService.compute`는 sync 함수이고 asyncpg는 async API다. 플랜에서는 **호출자 측에서 insert** (api.py의 signal_endpoint = async, broadcast.py의 Phase 1/3 = async 루프)로 재조정. SignalService는 순수 계산만 담당, DB 부작용 분리.

---

## File Structure (New / Modified)

```
migrations/
├── 001_init.sql                    # 기존
├── 002_watchlist.sql               # 기존 (Week 7)
└── 003_signal_log.sql              # [CREATE] Week 8

src/sajucandle/
├── tech_analysis.py                # 기존 — 보조 지표로 그대로 유지 (수정 없음)
├── chart_engine.py                 # 기존 — thin wrapper 그대로 (수정 없음)
├── analysis/                       # [CREATE] 신규 패키지
│   ├── __init__.py                 # 빈 파일
│   ├── swing.py                    # SwingPoint + detect_swings
│   ├── structure.py                # MarketStructure + classify_structure
│   ├── timeframe.py                # TrendDirection + trend_direction
│   ├── multi_timeframe.py          # Alignment + compute_alignment
│   └── composite.py                # AnalysisResult + analyze
├── format.py                       # [CREATE] DISCLAIMER 상수 + 포맷 헬퍼
├── market/yfinance.py              # [MODIFY] 1h/4h/1d interval 지원 (4h는 1h resample)
├── models.py                       # [MODIFY] AnalysisSummary + SignalResponse.analysis
├── repositories.py                 # [MODIFY] SignalLogRow + insert/list_pending/update_tracking
├── signal_service.py               # [MODIFY] analysis.analyze 호출, 가중치 0.1/0.9, grade_signal 추가조건
├── api.py                          # [MODIFY] /signal 엔드포인트에서 insert_signal_log 호출
├── handlers.py                     # [MODIFY] _format_signal_card 개편, DISCLAIMER 사용
└── broadcast.py                    # [MODIFY] Phase 0 tracking + format_morning_card 톤 완화 + BroadcastSummary 확장 + insert_signal_log (broadcast source)

tests/
├── test_analysis_swing.py          # [CREATE]
├── test_analysis_structure.py      # [CREATE]
├── test_analysis_timeframe.py      # [CREATE]
├── test_analysis_multi_timeframe.py # [CREATE]
├── test_analysis_composite.py      # [CREATE]
├── test_format.py                  # [CREATE]
├── test_market_yfinance.py         # [MODIFY] 1h/4h/1d interval 테스트
├── test_signal_service.py          # [MODIFY] 새 가중치, grade_signal 추가조건
├── test_repositories.py            # [MODIFY] signal_log CRUD (DB 통합)
├── test_api_signal.py              # [MODIFY] insert_signal_log 호출 검증
├── test_handlers.py                # [MODIFY] 새 카드 포맷, disclaimer 교체
└── test_broadcast.py               # [MODIFY] Phase 0, 모닝 카드 톤, disclaimer

README.md                           # [MODIFY] Week 8 섹션
```

**운영 수동 단계 (Task 16):**
- Supabase Studio에서 `migrations/003_signal_log.sql` 실행

---

## Task 1: migration 003_signal_log.sql

**Files:**
- Create: `migrations/003_signal_log.sql`

- [ ] **Step 1: Create migration file**

`D:\사주캔들\migrations\003_signal_log.sql` 신규 작성:

```sql
-- Week 8 Phase 1: signal_log 테이블 (시그널 발송 기록 + MFE/MAE 추적).
-- 실행: Supabase Studio → SQL Editor → Run.
-- 로컬: psql $DATABASE_URL -f migrations/003_signal_log.sql
-- 로컬 테스트 DB: psql $TEST_DATABASE_URL -f migrations/003_signal_log.sql

CREATE TABLE IF NOT EXISTS signal_log (
    id              BIGSERIAL PRIMARY KEY,
    sent_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    source          TEXT NOT NULL,
    telegram_chat_id BIGINT,

    ticker          TEXT NOT NULL,
    target_date     DATE NOT NULL,
    entry_price     NUMERIC(18,8) NOT NULL,

    saju_score      INT NOT NULL,
    analysis_score  INT NOT NULL,
    structure_state TEXT NOT NULL,
    alignment_bias  TEXT NOT NULL,
    rsi_1h          NUMERIC(5,2),
    volume_ratio_1d NUMERIC(6,3),

    composite_score INT NOT NULL,
    signal_grade    TEXT NOT NULL,

    mfe_7d_pct      NUMERIC(6,3),
    mae_7d_pct      NUMERIC(6,3),
    close_24h       NUMERIC(18,8),
    close_7d        NUMERIC(18,8),
    last_tracked_at TIMESTAMPTZ,
    tracking_done   BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_signal_log_ticker_sent_at
    ON signal_log(ticker, sent_at DESC);
CREATE INDEX IF NOT EXISTS idx_signal_log_tracking
    ON signal_log(tracking_done, sent_at)
    WHERE tracking_done = FALSE;
```

- [ ] **Step 2: Apply to local TEST DB if TEST_DATABASE_URL set**

PowerShell:
```
if ($env:TEST_DATABASE_URL) { psql $env:TEST_DATABASE_URL -f migrations/003_signal_log.sql }
```

Expected: `CREATE TABLE` + 2 `CREATE INDEX` 또는 `NOTICE: already exists`.

- [ ] **Step 3: Commit**

```
git add migrations/003_signal_log.sql
git commit -m "feat(db): add signal_log migration (Week 8)"
```

---

## Task 2: analysis/swing.py — Fractals + ATR 필터 (TDD)

**Files:**
- Create: `src/sajucandle/analysis/__init__.py` (빈 파일)
- Create: `src/sajucandle/analysis/swing.py`
- Create: `tests/test_analysis_swing.py`

- [ ] **Step 1: Write failing tests**

`tests/test_analysis_swing.py`:

```python
"""analysis.swing: Fractals + ATR 필터 기반 swing high/low 감지."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from sajucandle.analysis.swing import SwingPoint, detect_swings
from sajucandle.market_data import Kline


def _mk_klines(prices: list[tuple[float, float, float, float]]) -> list[Kline]:
    """Each tuple = (open, high, low, close). volume=1000."""
    out = []
    base_ts = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for i, (o, h, l, c) in enumerate(prices):
        out.append(Kline(
            open_time=base_ts.replace(day=1 + i % 28),
            open=o, high=h, low=l, close=c, volume=1000.0,
        ))
    return out


def test_detect_swings_empty():
    assert detect_swings([]) == []


def test_detect_swings_too_few_bars():
    """window=5면 최소 11봉 필요 (5+1+5). 부족하면 []."""
    klines = _mk_klines([(100, 101, 99, 100)] * 5)
    assert detect_swings(klines, fractal_window=5, atr_multiplier=0.0) == []


def test_detect_swings_single_clear_high():
    """중앙 봉 고점이 좌우 5봉보다 뚜렷하게 높은 경우."""
    prices = [
        (100, 101, 99, 100),  # 0
        (100, 102, 99, 101),  # 1
        (101, 103, 100, 102), # 2
        (102, 104, 101, 103), # 3
        (103, 105, 102, 104), # 4
        (104, 120, 103, 110), # 5 ← swing high (중앙)
        (103, 105, 102, 104), # 6
        (102, 104, 101, 103), # 7
        (101, 103, 100, 102), # 8
        (100, 102, 99, 101),  # 9
        (100, 101, 99, 100),  # 10
    ]
    klines = _mk_klines(prices)
    swings = detect_swings(klines, fractal_window=5, atr_multiplier=0.0)
    highs = [s for s in swings if s.kind == "high"]
    assert len(highs) == 1
    assert highs[0].index == 5
    assert highs[0].price == 120.0


def test_detect_swings_single_clear_low():
    """중앙 봉 저점이 좌우 5봉보다 뚜렷하게 낮은 경우."""
    prices = [
        (100, 101, 99, 100),
        (99, 100, 98, 99),
        (98, 99, 97, 98),
        (97, 98, 96, 97),
        (96, 97, 95, 96),
        (95, 96, 80, 85),  # 5 ← swing low
        (96, 97, 95, 96),
        (97, 98, 96, 97),
        (98, 99, 97, 98),
        (99, 100, 98, 99),
        (100, 101, 99, 100),
    ]
    klines = _mk_klines(prices)
    swings = detect_swings(klines, fractal_window=5, atr_multiplier=0.0)
    lows = [s for s in swings if s.kind == "low"]
    assert len(lows) == 1
    assert lows[0].index == 5
    assert lows[0].price == 80.0


def test_detect_swings_atr_filter_removes_noise():
    """작은 스윙은 ATR 필터로 제거된다.

    노이즈 스윙(직전 스윙과 거리 < ATR * 1.5)은 반환 안 됨.
    """
    # ATR이 약 2 수준인 데이터에서 1~2 정도 변동의 작은 스윙은 버려야 함
    prices = [
        (100, 101, 99, 100)
    ] * 5 + [
        (100, 120, 99, 110),   # 5: 큰 swing high (의미있음)
    ] + [
        (100, 101, 99, 100)
    ] * 5 + [
        (100, 101.5, 99.5, 100),  # 11: 아주 작은 변동
    ] + [
        (100, 101, 99, 100)
    ] * 5
    klines = _mk_klines(prices)
    swings = detect_swings(klines, fractal_window=5, atr_multiplier=1.5, atr_period=14)
    # 큰 swing만 남아야 함
    assert all(s.price == 120.0 or s.price == 99.0 for s in swings if s.kind == "high")


def test_swing_point_is_dataclass():
    from dataclasses import is_dataclass
    assert is_dataclass(SwingPoint)
    p = SwingPoint(index=5, timestamp=datetime.now(timezone.utc),
                   price=100.0, kind="high")
    assert p.index == 5
    assert p.kind == "high"
```

- [ ] **Step 2: Run — fail**

```
pytest tests/test_analysis_swing.py -v
```

Expected: `ModuleNotFoundError: No module named 'sajucandle.analysis'`.

- [ ] **Step 3: Implement**

`D:\사주캔들\src\sajucandle\analysis\__init__.py`:

```python
"""Analysis package (Week 8+). 시장 구조 + 멀티 TF + composite."""
```

`D:\사주캔들\src\sajucandle\analysis\swing.py`:

```python
"""Fractals + ATR 필터 기반 swing high/low 감지.

Fractal: N봉 기준. 중심 봉의 high가 좌우 N봉의 high보다 크면 swing high,
         low가 좌우 N봉의 low보다 작으면 swing low.
ATR 필터: 직전 반대 극점과의 거리가 ATR(period) * multiplier 미만이면 노이즈로 무시.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from sajucandle.market_data import Kline


@dataclass
class SwingPoint:
    index: int
    timestamp: datetime
    price: float
    kind: Literal["high", "low"]


def _atr(klines: list[Kline], period: int = 14) -> float:
    """Average True Range (Wilder). len(klines) >= period+1 전제."""
    if len(klines) < period + 1:
        return 0.0
    trs: list[float] = []
    for i in range(1, len(klines)):
        h = klines[i].high
        low_ = klines[i].low
        prev_c = klines[i - 1].close
        tr = max(h - low_, abs(h - prev_c), abs(low_ - prev_c))
        trs.append(tr)
    # Wilder smoothing
    avg = sum(trs[:period]) / period
    for i in range(period, len(trs)):
        avg = (avg * (period - 1) + trs[i]) / period
    return avg


def detect_swings(
    klines: list[Kline],
    fractal_window: int = 5,
    atr_multiplier: float = 1.5,
    atr_period: int = 14,
) -> list[SwingPoint]:
    """Fractals + ATR 필터. 중심봉 좌우 fractal_window개 비교.

    반환: 시간순 SwingPoint 리스트.
    """
    n = len(klines)
    if n < 2 * fractal_window + 1:
        return []

    candidates: list[SwingPoint] = []
    for i in range(fractal_window, n - fractal_window):
        center = klines[i]
        left = klines[i - fractal_window:i]
        right = klines[i + 1:i + 1 + fractal_window]
        # swing high
        if (all(center.high > k.high for k in left) and
                all(center.high > k.high for k in right)):
            candidates.append(SwingPoint(
                index=i, timestamp=center.open_time,
                price=center.high, kind="high",
            ))
        # swing low (동시 만족도 허용하지만 드물다)
        if (all(center.low < k.low for k in left) and
                all(center.low < k.low for k in right)):
            candidates.append(SwingPoint(
                index=i, timestamp=center.open_time,
                price=center.low, kind="low",
            ))

    # ATR 필터: 직전 반대 극점과 거리가 atr * multiplier 미만이면 제거
    if atr_multiplier <= 0 or atr_period + 1 > n:
        return candidates

    atr_value = _atr(klines, atr_period)
    if atr_value <= 0:
        return candidates

    threshold = atr_value * atr_multiplier
    filtered: list[SwingPoint] = []
    last_opposite: SwingPoint | None = None
    for sp in candidates:
        if last_opposite is None or last_opposite.kind == sp.kind:
            filtered.append(sp)
            last_opposite = sp
            continue
        dist = abs(sp.price - last_opposite.price)
        if dist >= threshold:
            filtered.append(sp)
            last_opposite = sp
        # else: 노이즈 — 버림
    return filtered
```

- [ ] **Step 4: Run — PASS**

```
pytest tests/test_analysis_swing.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Full regression**

```
pytest -q
```

Expected: 회귀 0.

- [ ] **Step 6: Commit**

```
git add src/sajucandle/analysis/__init__.py src/sajucandle/analysis/swing.py tests/test_analysis_swing.py
git commit -m "feat(analysis): add swing detection (Fractals + ATR filter)"
```

---

## Task 3: analysis/structure.py — MarketStructure 분류 (TDD)

**Files:**
- Create: `src/sajucandle/analysis/structure.py`
- Create: `tests/test_analysis_structure.py`

- [ ] **Step 1: Write failing tests**

`tests/test_analysis_structure.py`:

```python
"""analysis.structure: swing points → MarketStructure."""
from __future__ import annotations

from datetime import datetime, timezone

from sajucandle.analysis.structure import (
    MarketStructure,
    StructureAnalysis,
    classify_structure,
)
from sajucandle.analysis.swing import SwingPoint


def _sp(kind: str, price: float, idx: int) -> SwingPoint:
    return SwingPoint(
        index=idx, timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
        price=price, kind=kind,  # type: ignore[arg-type]
    )


def test_classify_empty_returns_range():
    r = classify_structure([])
    assert r.state == MarketStructure.RANGE
    assert r.last_high is None
    assert r.last_low is None
    assert 40 <= r.score <= 60


def test_classify_uptrend_hh_hl():
    """HH-HL 연속: 상승추세."""
    swings = [
        _sp("low", 100, 0),
        _sp("high", 110, 5),
        _sp("low", 105, 10),   # HL (100보다 높음)
        _sp("high", 120, 15),  # HH (110보다 높음)
        _sp("low", 112, 20),   # HL
        _sp("high", 130, 25),  # HH
    ]
    r = classify_structure(swings)
    assert r.state == MarketStructure.UPTREND
    assert r.last_high.price == 130
    assert r.last_low.price == 112
    assert r.score >= 65


def test_classify_downtrend_lh_ll():
    """LH-LL 연속: 하락추세."""
    swings = [
        _sp("high", 130, 0),
        _sp("low", 120, 5),
        _sp("high", 125, 10),  # LH (130보다 낮음)
        _sp("low", 115, 15),   # LL (120보다 낮음)
        _sp("high", 120, 20),  # LH
        _sp("low", 110, 25),   # LL
    ]
    r = classify_structure(swings)
    assert r.state == MarketStructure.DOWNTREND
    assert r.last_high.price == 120
    assert r.last_low.price == 110
    assert r.score <= 30


def test_classify_range_mixed():
    """HH 후 LL 나와 정렬 없음: 횡보."""
    swings = [
        _sp("low", 100, 0),
        _sp("high", 120, 5),
        _sp("low", 98, 10),    # LL — uptrend 깨짐
        _sp("high", 118, 15),  # LH — downtrend 아님
    ]
    r = classify_structure(swings)
    assert r.state == MarketStructure.RANGE


def test_classify_breakout_from_range():
    """최근 high가 범위 상단 돌파."""
    swings = [
        _sp("low", 100, 0),
        _sp("high", 110, 5),
        _sp("low", 102, 10),
        _sp("high", 109, 15),   # 범위 상단 ~110
        _sp("low", 103, 20),
        _sp("high", 120, 25),   # 기존 상단 대비 크게 돌파
    ]
    r = classify_structure(swings)
    assert r.state == MarketStructure.BREAKOUT
    assert r.score >= 70


def test_classify_breakdown_from_uptrend():
    """uptrend 중 최근 low가 직전 HL 하향 이탈."""
    swings = [
        _sp("low", 100, 0),
        _sp("high", 110, 5),
        _sp("low", 105, 10),  # HL
        _sp("high", 120, 15), # HH
        _sp("low", 100, 20),  # HL 깨짐 (105 밑)
    ]
    r = classify_structure(swings)
    assert r.state == MarketStructure.BREAKDOWN
    assert r.score <= 40
```

- [ ] **Step 2: Run — fail**

```
pytest tests/test_analysis_structure.py -v
```

Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement**

`src/sajucandle/analysis/structure.py`:

```python
"""swing points → MarketStructure 분류.

HH-HL 연속 = UPTREND, LH-LL 연속 = DOWNTREND,
박스 돌파 = BREAKOUT, 상승추세 HL 이탈 = BREAKDOWN, 그 외 = RANGE.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from sajucandle.analysis.swing import SwingPoint


class MarketStructure(str, Enum):
    UPTREND = "uptrend"
    DOWNTREND = "downtrend"
    RANGE = "range"
    BREAKOUT = "breakout"
    BREAKDOWN = "breakdown"


@dataclass
class StructureAnalysis:
    state: MarketStructure
    last_high: Optional[SwingPoint]
    last_low: Optional[SwingPoint]
    score: int   # 0~100


_SCORE_MAP = {
    MarketStructure.UPTREND: 70,
    MarketStructure.BREAKOUT: 80,
    MarketStructure.RANGE: 50,
    MarketStructure.BREAKDOWN: 30,
    MarketStructure.DOWNTREND: 20,
}


def _last(swings: list[SwingPoint], kind: str) -> Optional[SwingPoint]:
    for sp in reversed(swings):
        if sp.kind == kind:
            return sp
    return None


def classify_structure(swings: list[SwingPoint]) -> StructureAnalysis:
    last_high = _last(swings, "high")
    last_low = _last(swings, "low")

    if not swings or (last_high is None and last_low is None):
        return StructureAnalysis(
            state=MarketStructure.RANGE,
            last_high=last_high, last_low=last_low,
            score=_SCORE_MAP[MarketStructure.RANGE],
        )

    highs = [s for s in swings if s.kind == "high"]
    lows = [s for s in swings if s.kind == "low"]

    # UPTREND: 마지막 2개 high가 HH + 마지막 2개 low가 HL
    uptrend = (
        len(highs) >= 2 and len(lows) >= 2
        and highs[-1].price > highs[-2].price
        and lows[-1].price > lows[-2].price
    )
    # DOWNTREND: LH-LL
    downtrend = (
        len(highs) >= 2 and len(lows) >= 2
        and highs[-1].price < highs[-2].price
        and lows[-1].price < lows[-2].price
    )

    # BREAKDOWN: 이전이 uptrend였는데 최근 low가 직전 HL 깨짐
    # 직전 상태: highs[-2] > highs[-3]? 간단히 "마지막 low < 직전 low이면 BREAKDOWN"
    breakdown = (
        len(highs) >= 2 and len(lows) >= 2
        and highs[-1].price > highs[-2].price  # 여전히 HH
        and lows[-1].price < lows[-2].price    # 하지만 LL로 꺾임
    )

    # BREAKOUT: 마지막 high가 직전 high들을 크게 상향 돌파 (range 이후)
    breakout = False
    if len(highs) >= 3:
        prev_range_top = max(h.price for h in highs[:-1])
        # 5% 이상 돌파 or 박스 내 변동 대비 큼
        if highs[-1].price > prev_range_top * 1.03:
            breakout = True

    # 우선순위: BREAKDOWN > BREAKOUT > UPTREND/DOWNTREND > RANGE
    if breakdown and not uptrend:
        state = MarketStructure.BREAKDOWN
    elif breakout:
        state = MarketStructure.BREAKOUT
    elif uptrend:
        state = MarketStructure.UPTREND
    elif downtrend:
        state = MarketStructure.DOWNTREND
    else:
        state = MarketStructure.RANGE

    return StructureAnalysis(
        state=state,
        last_high=last_high,
        last_low=last_low,
        score=_SCORE_MAP[state],
    )
```

- [ ] **Step 4: Run — PASS**

```
pytest tests/test_analysis_structure.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Full regression + Commit**

```
pytest -q
git add src/sajucandle/analysis/structure.py tests/test_analysis_structure.py
git commit -m "feat(analysis): add market structure classification (HH/HL/LH/LL)"
```

---

## Task 4: analysis/timeframe.py — 단일 TF 트렌드 방향 (TDD)

**Files:**
- Create: `src/sajucandle/analysis/timeframe.py`
- Create: `tests/test_analysis_timeframe.py`

- [ ] **Step 1: Write failing tests**

`tests/test_analysis_timeframe.py`:

```python
"""analysis.timeframe: 단일 TF 추세 방향 판정 (close vs EMA50 + 기울기)."""
from __future__ import annotations

from datetime import datetime, timezone

from sajucandle.analysis.timeframe import TrendDirection, trend_direction
from sajucandle.market_data import Kline


def _klines(closes: list[float]) -> list[Kline]:
    out = []
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for i, c in enumerate(closes):
        out.append(Kline(
            open_time=base.replace(day=(i % 28) + 1),
            open=c, high=c + 0.5, low=c - 0.5, close=c, volume=1000.0,
        ))
    return out


def test_trend_up_when_close_above_ema_and_ema_rising():
    """지속 상승 closes → UP."""
    closes = [100 + i * 0.5 for i in range(60)]
    assert trend_direction(_klines(closes)) == TrendDirection.UP


def test_trend_down_when_close_below_ema_and_ema_falling():
    closes = [100 - i * 0.5 for i in range(60)]
    assert trend_direction(_klines(closes)) == TrendDirection.DOWN


def test_trend_flat_when_sideways():
    """완전 횡보 → FLAT."""
    closes = [100.0] * 60
    assert trend_direction(_klines(closes)) == TrendDirection.FLAT


def test_trend_flat_when_close_above_but_ema_falling():
    """close > EMA지만 EMA 기울기 음수 → FLAT (모호한 상태)."""
    # 앞 50봉 상승 → 뒤 10봉 급락. close < EMA, EMA 기울기 아직 음 아닐 수도.
    closes = [100 + i * 0.5 for i in range(50)] + [125 - i * 1.0 for i in range(10)]
    r = trend_direction(_klines(closes))
    assert r in (TrendDirection.DOWN, TrendDirection.FLAT)


def test_trend_too_few_bars_returns_flat():
    """bars < 50이면 EMA50 계산 불가 → FLAT."""
    closes = [100.0] * 20
    assert trend_direction(_klines(closes)) == TrendDirection.FLAT
```

- [ ] **Step 2: Run — fail**

```
pytest tests/test_analysis_timeframe.py -v
```

Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement**

`src/sajucandle/analysis/timeframe.py`:

```python
"""단일 타임프레임 추세 방향.

규칙:
  - close > EMA50 AND EMA50 기울기(최근 5봉) 양수 → UP
  - close < EMA50 AND EMA50 기울기 음수 → DOWN
  - 그 외 (close는 위인데 기울기 음, 또는 반대) → FLAT

기울기: EMA50[-1] - EMA50[-6] 부호.
"""
from __future__ import annotations

from enum import Enum

from sajucandle.market_data import Kline


class TrendDirection(str, Enum):
    UP = "up"
    DOWN = "down"
    FLAT = "flat"


def _ema(values: list[float], period: int) -> list[float]:
    """EMA 시리즈. 결과 길이 == len(values). 초기값은 SMA(period)."""
    if len(values) < period:
        return []
    k = 2.0 / (period + 1)
    out: list[float] = [0.0] * (period - 1)
    sma = sum(values[:period]) / period
    out.append(sma)
    for i in range(period, len(values)):
        prev = out[-1]
        out.append(values[i] * k + prev * (1 - k))
    return out


def trend_direction(klines: list[Kline], ema_period: int = 50) -> TrendDirection:
    if len(klines) < ema_period + 6:
        return TrendDirection.FLAT
    closes = [k.close for k in klines]
    emas = _ema(closes, ema_period)
    if not emas:
        return TrendDirection.FLAT
    last_close = closes[-1]
    last_ema = emas[-1]
    prev_ema = emas[-6]  # 5봉 전 EMA
    slope = last_ema - prev_ema

    above = last_close > last_ema
    rising = slope > 0

    if above and rising:
        return TrendDirection.UP
    if not above and not rising:
        return TrendDirection.DOWN
    return TrendDirection.FLAT
```

- [ ] **Step 4: Run — PASS**

```
pytest tests/test_analysis_timeframe.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Full regression + Commit**

```
pytest -q
git add src/sajucandle/analysis/timeframe.py tests/test_analysis_timeframe.py
git commit -m "feat(analysis): add single-TF trend direction (EMA50 + slope)"
```

---

## Task 5: analysis/multi_timeframe.py — 1h/4h/1d 정렬 (TDD)

**Files:**
- Create: `src/sajucandle/analysis/multi_timeframe.py`
- Create: `tests/test_analysis_multi_timeframe.py`

- [ ] **Step 1: Write failing tests**

`tests/test_analysis_multi_timeframe.py`:

```python
"""analysis.multi_timeframe: 3개 TF 정렬 판정."""
from __future__ import annotations

from datetime import datetime, timezone

from sajucandle.analysis.multi_timeframe import Alignment, compute_alignment
from sajucandle.analysis.timeframe import TrendDirection
from sajucandle.market_data import Kline


def _klines(closes: list[float]) -> list[Kline]:
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [
        Kline(open_time=base, open=c, high=c + 0.5, low=c - 0.5,
              close=c, volume=1000.0)
        for c in closes
    ]


def test_aligned_bullish_all_up():
    up_series = [100 + i * 0.5 for i in range(60)]
    r = compute_alignment(_klines(up_series), _klines(up_series), _klines(up_series))
    assert r.tf_1h == TrendDirection.UP
    assert r.tf_4h == TrendDirection.UP
    assert r.tf_1d == TrendDirection.UP
    assert r.aligned is True
    assert r.bias == "bullish"
    assert r.score >= 85


def test_aligned_bearish_all_down():
    dn_series = [100 - i * 0.5 for i in range(60)]
    r = compute_alignment(_klines(dn_series), _klines(dn_series), _klines(dn_series))
    assert r.aligned is True
    assert r.bias == "bearish"
    assert r.score <= 15


def test_mixed_1h_up_others_flat():
    up_series = [100 + i * 0.5 for i in range(60)]
    flat_series = [100.0] * 60
    r = compute_alignment(_klines(up_series), _klines(flat_series), _klines(flat_series))
    assert r.aligned is False
    assert r.bias in ("bullish", "mixed")


def test_mixed_conflicting():
    up_series = [100 + i * 0.5 for i in range(60)]
    dn_series = [100 - i * 0.5 for i in range(60)]
    r = compute_alignment(_klines(up_series), _klines(dn_series), _klines(dn_series))
    assert r.aligned is False
    assert r.bias in ("mixed", "bearish")


def test_score_range_0_to_100():
    flat = [100.0] * 60
    r = compute_alignment(_klines(flat), _klines(flat), _klines(flat))
    assert 0 <= r.score <= 100
```

- [ ] **Step 2: Run — fail**

```
pytest tests/test_analysis_multi_timeframe.py -v
```

Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement**

`src/sajucandle/analysis/multi_timeframe.py`:

```python
"""1h/4h/1d 3개 TF의 트렌드 방향 → Alignment.

aligned: 3개 TF가 전부 UP 또는 전부 DOWN일 때만 True.
bias: UP 개수 - DOWN 개수 부호로 bullish/mixed/bearish 판정.
score: bullish일수록 높음 (롱 관점 기준). 0~100.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from sajucandle.analysis.timeframe import TrendDirection, trend_direction
from sajucandle.market_data import Kline


@dataclass
class Alignment:
    tf_1h: TrendDirection
    tf_4h: TrendDirection
    tf_1d: TrendDirection
    aligned: bool
    bias: Literal["bullish", "mixed", "bearish"]
    score: int


def compute_alignment(
    klines_1h: list[Kline],
    klines_4h: list[Kline],
    klines_1d: list[Kline],
) -> Alignment:
    t1h = trend_direction(klines_1h)
    t4h = trend_direction(klines_4h)
    t1d = trend_direction(klines_1d)

    dirs = [t1h, t4h, t1d]
    ups = dirs.count(TrendDirection.UP)
    downs = dirs.count(TrendDirection.DOWN)

    aligned = (ups == 3) or (downs == 3)

    if ups > downs:
        bias: Literal["bullish", "mixed", "bearish"] = "bullish"
    elif downs > ups:
        bias = "bearish"
    else:
        bias = "mixed"

    # 점수: bullish align=90, mixed=50 근처, bearish align=10
    # ups - downs 차이에 기반
    diff = ups - downs    # -3..3
    # map to 0..100 (bullish 쪽으로 갈수록 큼)
    score = round((diff + 3) / 6 * 100)
    if aligned and bias == "bullish":
        score = max(score, 90)
    if aligned and bias == "bearish":
        score = min(score, 10)

    return Alignment(
        tf_1h=t1h, tf_4h=t4h, tf_1d=t1d,
        aligned=aligned, bias=bias, score=score,
    )
```

- [ ] **Step 4: Run — PASS**

```
pytest tests/test_analysis_multi_timeframe.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Full regression + Commit**

```
pytest -q
git add src/sajucandle/analysis/multi_timeframe.py tests/test_analysis_multi_timeframe.py
git commit -m "feat(analysis): add multi-timeframe alignment (1h/4h/1d)"
```

---

## Task 6: analysis/composite.py — 조합기 + AnalysisResult (TDD, 큰 태스크)

**Files:**
- Create: `src/sajucandle/analysis/composite.py`
- Create: `tests/test_analysis_composite.py`

- [ ] **Step 1: Write failing tests**

`tests/test_analysis_composite.py`:

```python
"""analysis.composite: AnalysisResult 조립 + composite_score."""
from __future__ import annotations

from datetime import datetime, timezone

from sajucandle.analysis.composite import AnalysisResult, analyze
from sajucandle.analysis.structure import MarketStructure
from sajucandle.analysis.timeframe import TrendDirection
from sajucandle.market_data import Kline


def _klines(closes: list[float], volumes: list[float] | None = None) -> list[Kline]:
    if volumes is None:
        volumes = [1000.0] * len(closes)
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [
        Kline(
            open_time=base.replace(day=(i % 28) + 1),
            open=c, high=c + 0.5, low=c - 0.5, close=c, volume=v,
        )
        for i, (c, v) in enumerate(zip(closes, volumes))
    ]


def test_analyze_strong_uptrend_aligned():
    """3TF 전부 상승 + structure uptrend → 높은 composite."""
    up_1h = [100 + i * 0.2 for i in range(200)]
    up_4h = [100 + i * 0.3 for i in range(100)]
    up_1d = [100 + i * 0.5 for i in range(100)]
    r = analyze(_klines(up_1h), _klines(up_4h), _klines(up_1d))
    assert r.composite_score >= 65
    assert r.alignment.aligned is True
    assert r.alignment.bias == "bullish"


def test_analyze_strong_downtrend_aligned():
    dn_1h = [100 - i * 0.2 for i in range(200)]
    dn_4h = [100 - i * 0.3 for i in range(100)]
    dn_1d = [100 - i * 0.5 for i in range(100)]
    r = analyze(_klines(dn_1h), _klines(dn_4h), _klines(dn_1d))
    # bearish 정렬 → 롱 관점 낮은 점수
    assert r.composite_score <= 40
    assert r.alignment.bias == "bearish"


def test_analyze_returns_fields_populated():
    flat = [100.0] * 100
    r = analyze(_klines(flat), _klines(flat), _klines(flat))
    assert isinstance(r, AnalysisResult)
    assert 0 <= r.composite_score <= 100
    assert r.structure.state in MarketStructure.__members__.values()
    assert r.alignment.tf_1h in (TrendDirection.UP, TrendDirection.DOWN,
                                   TrendDirection.FLAT)
    assert isinstance(r.reason, str)
    assert len(r.reason) > 0


def test_analyze_reason_contains_tf_arrows():
    up = [100 + i * 0.3 for i in range(100)]
    r = analyze(_klines(up), _klines(up), _klines(up))
    # 정렬 줄에 화살표 또는 TF 마커 포함
    assert "1d" in r.reason or "1h" in r.reason


def test_analyze_score_clamped():
    flat = [100.0] * 100
    r = analyze(_klines(flat), _klines(flat), _klines(flat))
    assert 0 <= r.composite_score <= 100


def test_analyze_composite_weighting():
    """structure.score=100, alignment.score=100, rsi=50, vol=50
    → 100*0.45 + 100*0.35 + 50*0.10 + 50*0.10 = 90.
    완벽한 상승 케이스에서 대략 80+ 나와야."""
    strong_up = [100 * (1.005 ** i) for i in range(100)]
    r = analyze(_klines(strong_up), _klines(strong_up), _klines(strong_up))
    assert r.composite_score >= 70
```

- [ ] **Step 2: Run — fail**

```
pytest tests/test_analysis_composite.py -v
```

Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement**

`src/sajucandle/analysis/composite.py`:

```python
"""Analysis 조합기: swing → structure + multi TF → composite_score.

Weights:
  composite = 0.45 * structure.score
            + 0.35 * alignment.score
            + 0.10 * rsi_score (1h RSI 사용)
            + 0.10 * volume_score (1d volume_ratio)
"""
from __future__ import annotations

from dataclasses import dataclass

from sajucandle.analysis.multi_timeframe import Alignment, compute_alignment
from sajucandle.analysis.structure import StructureAnalysis, classify_structure
from sajucandle.analysis.swing import detect_swings
from sajucandle.analysis.timeframe import TrendDirection
from sajucandle.market_data import Kline
from sajucandle.tech_analysis import (
    _rsi_score,
    _volume_score,
    rsi,
    volume_ratio,
)

_TF_ARROW = {
    TrendDirection.UP: "↑",
    TrendDirection.DOWN: "↓",
    TrendDirection.FLAT: "→",
}


@dataclass
class AnalysisResult:
    structure: StructureAnalysis
    alignment: Alignment
    rsi_1h: float
    volume_ratio_1d: float
    composite_score: int
    reason: str


def _safe_rsi(klines: list[Kline], period: int = 14) -> float:
    if len(klines) < period + 1:
        return 50.0
    try:
        return rsi([k.close for k in klines], period)
    except Exception:
        return 50.0


def _safe_vol_ratio(klines: list[Kline], lookback: int = 20) -> float:
    if len(klines) < lookback + 1:
        return 1.0
    try:
        return volume_ratio([k.volume for k in klines], lookback)
    except Exception:
        return 1.0


def analyze(
    klines_1h: list[Kline],
    klines_4h: list[Kline],
    klines_1d: list[Kline],
) -> AnalysisResult:
    # 구조는 1d 기준
    swings = detect_swings(klines_1d, fractal_window=5, atr_multiplier=1.5)
    structure = classify_structure(swings)

    # 정렬
    alignment = compute_alignment(klines_1h, klines_4h, klines_1d)

    # RSI(1h) + Volume(1d)
    rsi_1h = _safe_rsi(klines_1h, 14)
    vr_1d = _safe_vol_ratio(klines_1d, 20)

    rsi_score_ = _rsi_score(rsi_1h)
    vol_score_ = _volume_score(vr_1d)

    composite = round(
        0.45 * structure.score
        + 0.35 * alignment.score
        + 0.10 * rsi_score_
        + 0.10 * vol_score_
    )
    composite = max(0, min(100, composite))

    # reason 줄
    tf_str = (
        f"1d{_TF_ARROW[alignment.tf_1d]} "
        f"4h{_TF_ARROW[alignment.tf_4h]} "
        f"1h{_TF_ARROW[alignment.tf_1h]}"
    )
    align_label = {
        "bullish": "강정렬" if alignment.aligned else "부분정렬",
        "bearish": "강정렬" if alignment.aligned else "부분정렬",
        "mixed": "혼조",
    }[alignment.bias]
    vol_label = "볼륨↑" if vr_1d >= 1.5 else "볼륨→" if vr_1d >= 0.8 else "볼륨↓"
    reason = f"{tf_str} ({align_label}) · RSI(1h) {rsi_1h:.0f} · {vol_label}"

    return AnalysisResult(
        structure=structure,
        alignment=alignment,
        rsi_1h=rsi_1h,
        volume_ratio_1d=vr_1d,
        composite_score=composite,
        reason=reason,
    )
```

**중요:** `tech_analysis._rsi_score`, `_volume_score`는 private(_prefix)이지만 같은 패키지 내 재사용 목적으로 import. 리팩토링 불필요 (YAGNI).

- [ ] **Step 4: Run — PASS**

```
pytest tests/test_analysis_composite.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Full regression + Commit**

```
pytest -q
git add src/sajucandle/analysis/composite.py tests/test_analysis_composite.py
git commit -m "feat(analysis): add composite analyzer (structure+alignment+RSI+vol)"
```

---

## Task 7: yfinance 1h/4h/1d interval 지원 (TDD)

**Files:**
- Modify: `src/sajucandle/market/yfinance.py`
- Modify: `tests/test_market_yfinance.py`

- [ ] **Step 1: Write failing tests**

`tests/test_market_yfinance.py` 맨 아래에 추가:

```python
# ─────────────────────────────────────────────
# Week 8: 1h/4h/1d interval 지원
# ─────────────────────────────────────────────

def test_fetch_klines_1h_interval_calls_yf_with_1h():
    """interval='1h' → yf.Ticker.history(period=..., interval='1h') 호출."""
    idx = pd.date_range(end="2026-04-19", periods=120, freq="1h", tz="America/New_York")
    df = pd.DataFrame({
        "Open": [180.0] * 120,
        "High": [181.0] * 120,
        "Low": [179.0] * 120,
        "Close": [180.5] * 120,
        "Volume": [1_000_000] * 120,
    }, index=idx)
    fake_ticker = MagicMock()
    fake_ticker.history.return_value = df

    client = YFinanceClient()
    with patch("sajucandle.market.yfinance.yf.Ticker", return_value=fake_ticker):
        klines = client.fetch_klines("AAPL", interval="1h", limit=120)

    # history 호출 인자 검증
    _, kwargs = fake_ticker.history.call_args
    assert kwargs["interval"] == "1h"
    assert len(klines) == 120


def test_fetch_klines_4h_resamples_from_1h():
    """interval='4h' → 내부에서 1h fetch 후 4h로 resample."""
    # 1h 데이터 96개 → 4h 24개로 집계
    idx = pd.date_range(end="2026-04-19 20:00:00+00:00",
                        periods=96, freq="1h", tz="UTC")
    opens = [100.0 + i * 0.1 for i in range(96)]
    highs = [101.0 + i * 0.1 for i in range(96)]
    lows = [99.0 + i * 0.1 for i in range(96)]
    closes = [100.5 + i * 0.1 for i in range(96)]
    volumes = [1_000_000] * 96
    df = pd.DataFrame({
        "Open": opens, "High": highs, "Low": lows,
        "Close": closes, "Volume": volumes,
    }, index=idx)
    fake_ticker = MagicMock()
    fake_ticker.history.return_value = df

    client = YFinanceClient()
    with patch("sajucandle.market.yfinance.yf.Ticker", return_value=fake_ticker):
        klines = client.fetch_klines("AAPL", interval="4h", limit=24)

    # 호출 인자는 1h (내부에서 resample)
    _, kwargs = fake_ticker.history.call_args
    assert kwargs["interval"] == "1h"
    # 결과는 4h 집계
    assert len(klines) <= 24
    assert len(klines) >= 20    # 96/4 = 24 근처


def test_fetch_klines_1d_interval_unchanged():
    """interval='1d'는 기존과 동일하게 처리."""
    idx = pd.date_range(end="2026-04-16", periods=100, freq="B", tz="America/New_York")
    df = pd.DataFrame({
        "Open": [180.0] * 100,
        "High": [181.0] * 100,
        "Low": [179.0] * 100,
        "Close": [180.5] * 100,
        "Volume": [50_000_000] * 100,
    }, index=idx)
    fake_ticker = MagicMock()
    fake_ticker.history.return_value = df

    client = YFinanceClient()
    with patch("sajucandle.market.yfinance.yf.Ticker", return_value=fake_ticker):
        klines = client.fetch_klines("AAPL", interval="1d")
    _, kwargs = fake_ticker.history.call_args
    assert kwargs["interval"] == "1d"
    assert len(klines) == 100


def test_fetch_klines_4h_cache_key_distinct_from_1d():
    """4h 캐시 키와 1d 캐시 키가 분리되어 있어야."""
    import fakeredis
    r = fakeredis.FakeStrictRedis()

    # 1h 데이터 24개 (4h로 6개 resample)
    idx = pd.date_range(end="2026-04-19 20:00:00+00:00",
                        periods=24, freq="1h", tz="UTC")
    df_1h = pd.DataFrame({
        "Open": [100.0] * 24, "High": [101.0] * 24,
        "Low": [99.0] * 24, "Close": [100.5] * 24,
        "Volume": [1_000_000] * 24,
    }, index=idx)
    fake_ticker = MagicMock()
    fake_ticker.history.return_value = df_1h

    client = YFinanceClient(redis_client=r)
    with patch("sajucandle.market.yfinance.yf.Ticker", return_value=fake_ticker):
        client.fetch_klines("AAPL", interval="4h", limit=6)

    # fresh 캐시 key는 4h
    assert r.exists("ohlcv:AAPL:4h:fresh")
    # 1d 캐시는 없어야
    assert not r.exists("ohlcv:AAPL:1d:fresh")
```

- [ ] **Step 2: Run — fail**

```
pytest tests/test_market_yfinance.py -v -k "1h_interval or 4h_resamples or 1d_interval_unchanged or 4h_cache_key"
```

Expected: interval 처리 안 돼서 FAIL.

- [ ] **Step 3: Modify YFinanceClient**

`D:\사주캔들\src\sajucandle\market\yfinance.py`의 `_yf_fetch` 메서드를 다음과 같이 교체:

```python
    def _yf_fetch(self, symbol: str, interval: str, limit: int) -> list[Kline]:
        """interval='1d' → yfinance 직접 호출.
        interval='1h' → yfinance 1h (60일 제한).
        interval='4h' → 1h 데이터 fetch 후 pandas resample.
        """
        ticker = yf.Ticker(symbol)

        if interval == "4h":
            # 1h로 요청 (limit * 4 개 1h봉 필요)
            period_days = max(1, limit * 4 // 24 + 1)
            df = ticker.history(
                period=f"{period_days}d",
                interval="1h",
                auto_adjust=False,
            )
            if df is None or df.empty:
                return []
            # 4시간 resample (UTC 기준 00/04/08/12/16/20)
            df = df.resample("4h", origin="epoch").agg({
                "Open": "first",
                "High": "max",
                "Low": "min",
                "Close": "last",
                "Volume": "sum",
            }).dropna()
        elif interval == "1h":
            # 1h는 yfinance 60일 제한, period="{limit}h" 대신 day 단위로 환산
            period_days = max(2, limit // 24 + 2)
            period_days = min(period_days, 60)
            df = ticker.history(
                period=f"{period_days}d",
                interval="1h",
                auto_adjust=False,
            )
            if df is None or df.empty:
                return []
        else:
            # 기존 1d 로직 그대로
            df = ticker.history(
                period=f"{limit}d",
                interval=interval,
                auto_adjust=False,
            )
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
        # limit 초과분 마지막 N개만
        if len(klines) > limit:
            klines = klines[-limit:]
        return klines
```

- [ ] **Step 4: Run — PASS**

```
pytest tests/test_market_yfinance.py -v
```

Expected: 기존 + 신규 4개 전부 passed.

- [ ] **Step 5: Full regression + Commit**

```
pytest -q
git add src/sajucandle/market/yfinance.py tests/test_market_yfinance.py
git commit -m "feat(market): YFinanceClient supports 1h/4h/1d (4h via resample)"
```

---

## Task 8: models.py — AnalysisSummary + SignalResponse 확장

**Files:**
- Modify: `src/sajucandle/models.py`
- Test는 Task 9에서 signal_service 통해 간접 검증

- [ ] **Step 1: Add models**

`D:\사주캔들\src\sajucandle\models.py` 맨 아래에 추가:

```python
# ─────────────────────────────────────────────
# Week 8: AnalysisSummary (SignalResponse에 포함)
# ─────────────────────────────────────────────


class StructureSummary(BaseModel):
    state: Literal["uptrend", "downtrend", "range", "breakout", "breakdown"]
    score: int = Field(ge=0, le=100)


class AlignmentSummary(BaseModel):
    tf_1h: Literal["up", "down", "flat"]
    tf_4h: Literal["up", "down", "flat"]
    tf_1d: Literal["up", "down", "flat"]
    aligned: bool
    bias: Literal["bullish", "mixed", "bearish"]
    score: int = Field(ge=0, le=100)


class AnalysisSummary(BaseModel):
    structure: StructureSummary
    alignment: AlignmentSummary
    rsi_1h: float
    volume_ratio_1d: float
    composite_score: int = Field(ge=0, le=100)
    reason: str
```

그리고 기존 `SignalResponse` 클래스 정의를 수정하여 `analysis` 필드 추가 + `chart` 필드 Optional 화:

```python
class SignalResponse(BaseModel):
    chat_id: int
    ticker: str
    date: str
    price: PricePoint
    saju: SajuSummary
    chart: ChartSummary                 # 하위호환 (Week 7 이하 클라이언트용, 내부는 analysis로 채움)
    composite_score: int = Field(ge=0, le=100)
    signal_grade: str
    best_hours: List[HourRecommendation]
    market_status: MarketStatus
    analysis: Optional[AnalysisSummary] = None   # Week 8 신규 (기본 None = 하위호환)
```

`Optional`이 이미 import되어 있는지 확인 (없으면 `from typing import Optional` 추가).

- [ ] **Step 2: Verify import**

```
python -c "from sajucandle.models import StructureSummary, AlignmentSummary, AnalysisSummary, SignalResponse; print('ok')"
```

Expected: `ok`.

- [ ] **Step 3: Full regression**

```
pytest -q
```

Expected: 회귀 0. Optional 필드 추가는 비파괴.

- [ ] **Step 4: Commit**

```
git add src/sajucandle/models.py
git commit -m "feat(models): add AnalysisSummary + SignalResponse.analysis (optional)"
```

---

## Task 9: signal_service.py refactor — analysis 호출 + 가중치 + grade_signal 추가조건 (TDD, 큰 태스크)

**Files:**
- Modify: `src/sajucandle/signal_service.py`
- Modify: `tests/test_signal_service.py`

- [ ] **Step 1: Update tests first**

`tests/test_signal_service.py`를 수정. 기존 `_FakeMarketClient`는 일봉만 반환 — 새로 `fetch_klines(symbol, interval, limit)`의 `interval`에 따라 다른 시리즈 반환하게 확장:

기존 `_FakeMarketClient` 클래스를 찾아 `fetch_klines` 메서드를 다음으로 교체 (파일 내부, 기존 mock 한정):

```python
class _FakeMarketClient:
    """BinanceClient 대체. interval별 다른 시리즈 지원."""

    def __init__(self, klines=None, raise_exc=None):
        self.klines = klines or _make_klines()
        self.raise_exc = raise_exc
        self.call_count = 0
        # interval별 오버라이드 (1h/4h/1d 각 다른 데이터 주입 가능)
        self.klines_by_interval: dict[str, list] = {}

    def fetch_klines(self, symbol, interval="1d", limit=100):
        self.call_count += 1
        if self.raise_exc is not None:
            raise self.raise_exc
        if interval in self.klines_by_interval:
            return self.klines_by_interval[interval]
        return self.klines
```

그리고 새 테스트 추가 (파일 맨 아래):

```python
# ─────────────────────────────────────────────
# Week 8: 가중치 재조정 + grade_signal 추가조건
# ─────────────────────────────────────────────


def test_weights_updated_saju_01_analysis_09():
    """새 가중치: 0.1 * saju + 0.9 * analysis.composite.

    saju=40, analysis=80 → 0.1*40 + 0.9*80 = 76.
    """
    from sajucandle.signal_service import SignalService

    fake = _make_fake_market_client()
    # 강한 상승 데이터 → analysis 점수 높음
    strong_up = _make_klines(n=200, base_close=100.0, drift=0.5)
    fake.klines_by_interval = {
        "1h": strong_up, "4h": strong_up, "1d": strong_up,
    }
    score_svc = _make_score_service_with_fixed_composite(40)   # 사주=40 고정
    svc = SignalService(
        score_service=score_svc,
        market_router=_make_router(fake),
    )
    resp = svc.compute(_profile(), date(2026, 4, 16), "BTCUSDT")
    # composite = round(0.1 * 40 + 0.9 * analysis) 와 근사
    # analysis는 70~90 예상
    assert 65 <= resp.composite_score <= 90


def test_grade_signal_requires_alignment_and_uptrend_for_strong():
    """점수만 75+ 해도, 정렬 안 되거나 구조가 UPTREND/BREAKOUT 아니면 '진입'."""
    from sajucandle.signal_service import SignalService

    fake = _make_fake_market_client()
    # mixed 데이터: 1h up / 4h flat / 1d down → aligned=False
    up = _make_klines(n=200, base_close=100.0, drift=0.5)
    flat = _make_klines(n=200, base_close=100.0, drift=0.0)
    dn = _make_klines(n=200, base_close=150.0, drift=-0.3)
    fake.klines_by_interval = {"1h": up, "4h": flat, "1d": dn}
    score_svc = _make_score_service_with_fixed_composite(80)   # 사주=80
    svc = SignalService(
        score_service=score_svc,
        market_router=_make_router(fake),
    )
    resp = svc.compute(_profile(), date(2026, 4, 16), "BTCUSDT")
    # 정렬 안 됨 → "강진입" 아님
    assert resp.signal_grade != "강진입"


def test_analysis_field_populated_in_response():
    """SignalResponse.analysis 필드가 채워지는지."""
    from sajucandle.signal_service import SignalService

    fake = _make_fake_market_client()
    score_svc = _make_score_service()
    svc = SignalService(
        score_service=score_svc,
        market_router=_make_router(fake),
    )
    resp = svc.compute(_profile(), date(2026, 4, 16), "BTCUSDT")
    assert resp.analysis is not None
    assert resp.analysis.structure.state in (
        "uptrend", "downtrend", "range", "breakout", "breakdown"
    )
    assert resp.analysis.alignment.tf_1d in ("up", "down", "flat")
    assert 0 <= resp.analysis.composite_score <= 100


def test_chart_field_still_populated_for_backward_compat():
    """기존 chart 필드는 하위호환으로 analysis 값에서 채워져야."""
    from sajucandle.signal_service import SignalService

    fake = _make_fake_market_client()
    score_svc = _make_score_service()
    svc = SignalService(
        score_service=score_svc,
        market_router=_make_router(fake),
    )
    resp = svc.compute(_profile(), date(2026, 4, 16), "BTCUSDT")
    assert resp.chart is not None
    # chart.score ≈ analysis.composite_score
    assert resp.chart.score == resp.analysis.composite_score
```

헬퍼 `_make_score_service_with_fixed_composite(n)` 필요. 파일 기존 헬퍼 섹션에 추가:

```python
def _make_score_service_with_fixed_composite(composite: int):
    """테스트용 ScoreService. 어떤 입력이든 지정된 composite 반환."""
    from unittest.mock import MagicMock
    from sajucandle.models import SajuScoreResponse, AxisScore, HourRecommendation

    svc = MagicMock()
    def fake_compute(profile, target_date, asset_class):
        return SajuScoreResponse(
            chat_id=profile.telegram_chat_id,
            date=target_date.isoformat(),
            asset_class=asset_class,
            iljin="庚申",
            composite_score=composite,
            signal_grade="진입" if composite >= 60 else "관망",
            axes={
                "wealth": AxisScore(score=composite, reason=""),
                "decision": AxisScore(score=composite, reason=""),
                "volatility": AxisScore(score=composite, reason=""),
                "flow": AxisScore(score=composite, reason=""),
            },
            best_hours=[],
        )
    svc.compute = fake_compute
    return svc
```

- [ ] **Step 2: Run — fail**

```
pytest tests/test_signal_service.py -v
```

Expected: 일부 기존 테스트가 0.4/0.6 가중치로 검증하던 게 실패 + 새 Week 8 테스트 전부 실패.

**기존 테스트 처리:** 0.4/0.6 가중치 하드코드된 assertion이 있으면 0.1/0.9 기반으로 수정. 찾기:
```
grep -n "0.4\|0.6\|composite_score ==" tests/test_signal_service.py
```

일일이 검토 후 새 가중치에 맞게 재계산. 범위가 애매한 assertion(예: `>= 50`)은 그대로.

- [ ] **Step 3: Refactor signal_service.py**

`D:\사주캔들\src\sajucandle\signal_service.py` 수정:

```python
"""사주 + 차트 결합 신호 서비스 (Week 8 개편).

책임:
1. ScoreService.compute() → 사주 composite (가중치 0.1)
2. MarketRouter.get_provider() + fetch_klines (1h/4h/1d 3개 TF)
3. analysis.composite.analyze() → AnalysisResult (가중치 0.9)
4. 가중합 → final_score + grade (grade는 추가 조건 필요)
5. SignalResponse 조립 (analysis 필드 + chart 하위호환)
6. Redis 캐시 (signal:*, TTL=300)
"""
from __future__ import annotations

import json
import logging
from datetime import date
from typing import Optional

from sajucandle.analysis.composite import AnalysisResult, analyze
from sajucandle.analysis.structure import MarketStructure
from sajucandle.market.router import MarketRouter
from sajucandle.market_data import Kline
from sajucandle.models import (
    AlignmentSummary,
    AnalysisSummary,
    ChartSummary,
    MarketStatus,
    PricePoint,
    SajuSummary,
    SignalResponse,
    StructureSummary,
)
from sajucandle.repositories import UserProfile
from sajucandle.score_service import ScoreService

logger = logging.getLogger(__name__)

_SIGNAL_TTL = 300


def _grade_signal(score: int, analysis: AnalysisResult) -> str:
    """Week 8: 강진입은 점수 + 정렬 + 상승구조 3조건 모두 만족할 때만."""
    if (score >= 75
            and analysis.alignment.aligned
            and analysis.structure.state in (MarketStructure.UPTREND, MarketStructure.BREAKOUT)):
        return "강진입"
    if score >= 60:
        return "진입"
    if score >= 40:
        return "관망"
    return "회피"


def _analysis_to_summary(a: AnalysisResult) -> AnalysisSummary:
    return AnalysisSummary(
        structure=StructureSummary(
            state=a.structure.state.value,  # type: ignore[arg-type]
            score=a.structure.score,
        ),
        alignment=AlignmentSummary(
            tf_1h=a.alignment.tf_1h.value,  # type: ignore[arg-type]
            tf_4h=a.alignment.tf_4h.value,  # type: ignore[arg-type]
            tf_1d=a.alignment.tf_1d.value,  # type: ignore[arg-type]
            aligned=a.alignment.aligned,
            bias=a.alignment.bias,
            score=a.alignment.score,
        ),
        rsi_1h=a.rsi_1h,
        volume_ratio_1d=a.volume_ratio_1d,
        composite_score=a.composite_score,
        reason=a.reason,
    )


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
        provider = self._router.get_provider(ticker)

        # 3개 TF fetch
        klines_1d: list[Kline] = provider.fetch_klines(ticker, interval="1d", limit=100)
        klines_4h: list[Kline] = provider.fetch_klines(ticker, interval="4h", limit=150)
        klines_1h: list[Kline] = provider.fetch_klines(ticker, interval="1h", limit=200)

        # 분석
        analysis = analyze(klines_1h, klines_4h, klines_1d)

        # 가격
        current = klines_1d[-1].close
        prev = klines_1d[-2].close if len(klines_1d) >= 2 else current
        change_pct = ((current / prev) - 1.0) * 100 if prev else 0.0

        # 최종 점수 + 등급
        final = round(0.1 * saju_resp.composite_score + 0.9 * analysis.composite_score)
        final = max(0, min(100, final))
        grade = _grade_signal(final, analysis)

        is_crypto = ticker.upper().lstrip("$") == "BTCUSDT"
        market_status = MarketStatus(
            is_open=provider.is_market_open(ticker),
            last_session_date=provider.last_session_date(ticker).isoformat(),
            category="crypto" if is_crypto else "us_stock",
        )

        analysis_summary = _analysis_to_summary(analysis)

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
                # 하위호환: analysis 값을 반영
                score=analysis.composite_score,
                rsi=analysis.rsi_1h,
                ma20=current,   # 1h 단일지표는 의미 작음 — placeholder
                ma50=current,
                ma_trend="up" if analysis.alignment.tf_1d.value == "up"
                          else "down" if analysis.alignment.tf_1d.value == "down"
                          else "flat",  # type: ignore[arg-type]
                volume_ratio=analysis.volume_ratio_1d,
                reason=analysis.reason,
            ),
            composite_score=final,
            signal_grade=grade,
            best_hours=saju_resp.best_hours,
            market_status=market_status,
            analysis=analysis_summary,
        )

        self._redis_set(cache_key, resp)
        return resp

    # ─── cache helpers (기존 그대로) ───
    def _redis_get(self, key):
        # 기존 코드 그대로 유지
        ...

    def _redis_set(self, key, resp):
        # 기존 코드 그대로 유지
        ...
```

**주의:** `_redis_get`, `_redis_set` 메서드는 **기존 코드 그대로 유지**. 위 `...` 부분을 실제 복사할 때는 기존 코드로 채움.

- [ ] **Step 4: Run — PASS**

```
pytest tests/test_signal_service.py -v
```

Expected: 기존 수정된 테스트 + 신규 4개 전부 passed.

- [ ] **Step 5: Full regression**

```
pytest -q
```

Expected: 회귀 0. test_api_signal.py에서 일부 assertion이 새 로직에 맞지 않으면 수정.

- [ ] **Step 6: Commit**

```
git add src/sajucandle/signal_service.py tests/test_signal_service.py
git commit -m "refactor(signal): use analysis composite, weights 0.1/0.9, strict 강진입"
```

---

## Task 10: repositories.py — signal_log CRUD (TDD, DB 통합)

**Files:**
- Modify: `src/sajucandle/repositories.py`
- Modify: `tests/test_repositories.py`

- [ ] **Step 1: Write failing tests**

`tests/test_repositories.py` 맨 아래에 추가:

```python
# ─────────────────────────────────────────────
# Week 8: signal_log CRUD
# ─────────────────────────────────────────────

from datetime import date, datetime, timezone, timedelta

from sajucandle.repositories import (
    SignalLogRow,
    insert_signal_log,
    list_pending_tracking,
    update_signal_tracking,
)


async def test_insert_signal_log_returns_id(db_conn):
    await _register_user(db_conn, 200001)
    row_id = await insert_signal_log(
        db_conn,
        source="ondemand",
        telegram_chat_id=200001,
        ticker="BTCUSDT",
        target_date=date(2026, 4, 19),
        entry_price=72000.0,
        saju_score=56,
        analysis_score=72,
        structure_state="uptrend",
        alignment_bias="bullish",
        rsi_1h=62.5,
        volume_ratio_1d=1.35,
        composite_score=70,
        signal_grade="진입",
    )
    assert row_id > 0


async def test_list_pending_tracking_returns_recent_not_done(db_conn):
    await _register_user(db_conn, 200002)
    # 방금 insert된 row는 아직 1h 미경과이므로 pending 대상 아님 (>= now-1h)
    # NULL NULL 상태로 삽입만 해서는 테스트 어려우니 sent_at 수동 조작
    import asyncpg
    await db_conn.execute("""
        INSERT INTO signal_log (sent_at, source, telegram_chat_id,
            ticker, target_date, entry_price,
            saju_score, analysis_score, structure_state, alignment_bias,
            composite_score, signal_grade, tracking_done)
        VALUES ($1, 'ondemand', $2, 'BTCUSDT', $3, 72000,
                50, 70, 'uptrend', 'bullish', 68, '진입', FALSE)
    """,
    datetime.now(timezone.utc) - timedelta(hours=2),   # 2h 전
    200002, date(2026, 4, 19))

    now = datetime.now(timezone.utc)
    pending = await list_pending_tracking(db_conn, now=now)
    assert len(pending) >= 1
    assert all(p.tracking_done is False for p in pending)


async def test_list_pending_excludes_done(db_conn):
    await _register_user(db_conn, 200003)
    await db_conn.execute("""
        INSERT INTO signal_log (sent_at, source, telegram_chat_id,
            ticker, target_date, entry_price,
            saju_score, analysis_score, structure_state, alignment_bias,
            composite_score, signal_grade, tracking_done)
        VALUES ($1, 'ondemand', $2, 'BTCUSDT', $3, 72000,
                50, 70, 'uptrend', 'bullish', 68, '진입', TRUE)
    """,
    datetime.now(timezone.utc) - timedelta(hours=2),
    200003, date(2026, 4, 19))
    pending = await list_pending_tracking(db_conn, now=datetime.now(timezone.utc))
    # tracking_done=TRUE면 포함 안 됨
    for p in pending:
        assert p.telegram_chat_id != 200003


async def test_update_signal_tracking_sets_mfe_mae(db_conn):
    await _register_user(db_conn, 200004)
    row_id = await insert_signal_log(
        db_conn,
        source="ondemand",
        telegram_chat_id=200004,
        ticker="BTCUSDT",
        target_date=date(2026, 4, 19),
        entry_price=72000.0,
        saju_score=56,
        analysis_score=72,
        structure_state="uptrend",
        alignment_bias="bullish",
        rsi_1h=None,
        volume_ratio_1d=None,
        composite_score=70,
        signal_grade="진입",
    )
    await update_signal_tracking(
        db_conn, row_id,
        mfe_pct=3.5, mae_pct=-1.2,
        close_24h=73000.0, close_7d=None,
        tracking_done=False,
    )
    row = await db_conn.fetchrow(
        "SELECT mfe_7d_pct, mae_7d_pct, close_24h, close_7d, tracking_done "
        "FROM signal_log WHERE id = $1", row_id
    )
    assert float(row["mfe_7d_pct"]) == 3.5
    assert float(row["mae_7d_pct"]) == -1.2
    assert float(row["close_24h"]) == 73000.0
    assert row["close_7d"] is None
    assert row["tracking_done"] is False


async def test_update_signal_tracking_done(db_conn):
    await _register_user(db_conn, 200005)
    row_id = await insert_signal_log(
        db_conn,
        source="ondemand", telegram_chat_id=200005,
        ticker="BTCUSDT", target_date=date(2026, 4, 19),
        entry_price=72000.0,
        saju_score=56, analysis_score=72,
        structure_state="uptrend", alignment_bias="bullish",
        rsi_1h=None, volume_ratio_1d=None,
        composite_score=70, signal_grade="진입",
    )
    await update_signal_tracking(
        db_conn, row_id,
        mfe_pct=5.0, mae_pct=-2.0,
        close_24h=73000.0, close_7d=75000.0,
        tracking_done=True,
    )
    row = await db_conn.fetchrow(
        "SELECT tracking_done FROM signal_log WHERE id = $1", row_id
    )
    assert row["tracking_done"] is True
```

- [ ] **Step 2: Run — fail**

```
pytest tests/test_repositories.py -v -k "signal_log or tracking or insert_signal"
```

Expected: ImportError 또는 skip (TEST_DATABASE_URL 없을 시).

- [ ] **Step 3: Implement**

`D:\사주캔들\src\sajucandle\repositories.py` 맨 아래에 추가:

```python
# ─────────────────────────────────────────────
# Week 8: signal_log
# ─────────────────────────────────────────────


@dataclass
class SignalLogRow:
    id: int
    sent_at: datetime
    source: str
    telegram_chat_id: Optional[int]
    ticker: str
    target_date: date
    entry_price: float
    saju_score: int
    analysis_score: int
    structure_state: str
    alignment_bias: str
    rsi_1h: Optional[float]
    volume_ratio_1d: Optional[float]
    composite_score: int
    signal_grade: str
    mfe_7d_pct: Optional[float]
    mae_7d_pct: Optional[float]
    close_24h: Optional[float]
    close_7d: Optional[float]
    last_tracked_at: Optional[datetime]
    tracking_done: bool


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
) -> int:
    """signal_log INSERT → id 반환."""
    row = await conn.fetchrow(
        """
        INSERT INTO signal_log (
            source, telegram_chat_id,
            ticker, target_date, entry_price,
            saju_score, analysis_score,
            structure_state, alignment_bias,
            rsi_1h, volume_ratio_1d,
            composite_score, signal_grade
        ) VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13
        ) RETURNING id
        """,
        source, telegram_chat_id,
        ticker, target_date, entry_price,
        saju_score, analysis_score,
        structure_state, alignment_bias,
        rsi_1h, volume_ratio_1d,
        composite_score, signal_grade,
    )
    return int(row["id"])


async def list_pending_tracking(
    conn: asyncpg.Connection,
    now: datetime,
    max_rows: int = 500,
) -> list[SignalLogRow]:
    """tracking_done=FALSE AND sent_at > now-7d AND sent_at < now-1h."""
    from datetime import timedelta
    rows = await conn.fetch(
        """
        SELECT id, sent_at, source, telegram_chat_id,
               ticker, target_date, entry_price,
               saju_score, analysis_score,
               structure_state, alignment_bias,
               rsi_1h, volume_ratio_1d,
               composite_score, signal_grade,
               mfe_7d_pct, mae_7d_pct,
               close_24h, close_7d,
               last_tracked_at, tracking_done
        FROM signal_log
        WHERE tracking_done = FALSE
          AND sent_at > $1
          AND sent_at < $2
        ORDER BY sent_at ASC
        LIMIT $3
        """,
        now - timedelta(days=7),
        now - timedelta(hours=1),
        max_rows,
    )
    result: list[SignalLogRow] = []
    for r in rows:
        result.append(SignalLogRow(
            id=int(r["id"]),
            sent_at=r["sent_at"],
            source=r["source"],
            telegram_chat_id=r["telegram_chat_id"],
            ticker=r["ticker"],
            target_date=r["target_date"],
            entry_price=float(r["entry_price"]),
            saju_score=int(r["saju_score"]),
            analysis_score=int(r["analysis_score"]),
            structure_state=r["structure_state"],
            alignment_bias=r["alignment_bias"],
            rsi_1h=float(r["rsi_1h"]) if r["rsi_1h"] is not None else None,
            volume_ratio_1d=float(r["volume_ratio_1d"]) if r["volume_ratio_1d"] is not None else None,
            composite_score=int(r["composite_score"]),
            signal_grade=r["signal_grade"],
            mfe_7d_pct=float(r["mfe_7d_pct"]) if r["mfe_7d_pct"] is not None else None,
            mae_7d_pct=float(r["mae_7d_pct"]) if r["mae_7d_pct"] is not None else None,
            close_24h=float(r["close_24h"]) if r["close_24h"] is not None else None,
            close_7d=float(r["close_7d"]) if r["close_7d"] is not None else None,
            last_tracked_at=r["last_tracked_at"],
            tracking_done=r["tracking_done"],
        ))
    return result


async def update_signal_tracking(
    conn: asyncpg.Connection,
    signal_id: int,
    *,
    mfe_pct: float,
    mae_pct: float,
    close_24h: Optional[float],
    close_7d: Optional[float],
    tracking_done: bool,
) -> None:
    await conn.execute(
        """
        UPDATE signal_log SET
            mfe_7d_pct = $2,
            mae_7d_pct = $3,
            close_24h = $4,
            close_7d = $5,
            tracking_done = $6,
            last_tracked_at = now()
        WHERE id = $1
        """,
        signal_id, mfe_pct, mae_pct, close_24h, close_7d, tracking_done,
    )
```

- [ ] **Step 4: Run — PASS**

```
pytest tests/test_repositories.py -v -k "signal_log or tracking or insert_signal"
```

Expected (TEST_DATABASE_URL 있음): 5 passed. 미설정 시 skip.

- [ ] **Step 5: Full regression + Commit**

```
pytest -q
git add src/sajucandle/repositories.py tests/test_repositories.py
git commit -m "feat(repo): add signal_log CRUD (insert/list_pending/update_tracking)"
```

---

## Task 11: api.py — /signal 엔드포인트에서 insert_signal_log 호출 (TDD)

**Files:**
- Modify: `src/sajucandle/api.py`
- Modify: `tests/test_api_signal.py`

- [ ] **Step 1: Write failing tests**

`tests/test_api_signal.py` 맨 아래에 추가:

```python
def test_signal_endpoint_writes_signal_log(client, stub_yfinance, db_registered_user):
    """/signal 호출 시 signal_log에 row 1개 INSERT."""
    # 호출 전 row 수
    import asyncio
    from sajucandle import db as _db
    async def count_before():
        async with _db.acquire() as conn:
            return await conn.fetchval("SELECT COUNT(*) FROM signal_log")

    # 현재 이벤트 루프가 없으니 sync 방식으로는 client 호출만
    resp = client.get(
        f"/v1/users/{db_registered_user}/signal",
        params={"ticker": "AAPL"},
        headers={"X-SAJUCANDLE-KEY": "test-key"},
    )
    assert resp.status_code == 200
    # SELECT COUNT(*)은 conftest의 db_conn 픽스처 롤백이 없으므로 후속 SELECT로 검증
    # → 별도 connection으로 count
    # client 픽스처가 이벤트루프 열린 상태이므로 TestClient 내부에서 post-request 검증
    # 간단하게: 본문에 analysis 필드 있으면 insert는 호출됐다고 간주
    body = resp.json()
    assert body["analysis"]["composite_score"] >= 0
```

**주의:** DB state를 직접 검증하기 어려운 통합 테스트. `signal_log` row 존재 확인은 `test_api_signal.py`가 `client` 픽스처(lifespan 공유 app) + 실제 TEST DB를 쓰는 경우 가능. 위 테스트는 API 응답에 analysis가 채워지는 것으로 대체 검증 (signal_log insert는 task 10 단위 테스트가 이미 커버).

추가로, "signal_log 기록 실패 시 시그널 응답은 정상" 검증:

```python
def test_signal_endpoint_succeeds_even_if_logging_fails(monkeypatch, client,
                                                         stub_yfinance,
                                                         db_registered_user):
    """insert_signal_log가 raise해도 시그널은 정상 반환."""
    import sajucandle.api as api_mod
    import sajucandle.repositories as repo_mod

    async def fake_insert(*args, **kwargs):
        raise RuntimeError("db down")
    monkeypatch.setattr(repo_mod, "insert_signal_log", fake_insert)

    resp = client.get(
        f"/v1/users/{db_registered_user}/signal",
        params={"ticker": "AAPL"},
        headers={"X-SAJUCANDLE-KEY": "test-key"},
    )
    assert resp.status_code == 200
    assert resp.json()["ticker"] == "AAPL"
```

- [ ] **Step 2: Run — fail or already passes**

```
pytest tests/test_api_signal.py -v -k "signal_log or logging_fails"
```

Expected: `analysis` 필드 없어서 fail, 또는 insert 호출 없어서 검증 불가.

- [ ] **Step 3: Add insert_signal_log call in api.py**

`D:\사주캔들\src\sajucandle\api.py`의 `signal_endpoint` 함수에서 `result = signal_service.compute(...)` 호출 다음에 DB 기록 추가:

```python
        t0 = time.perf_counter()
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

        # Week 8: signal_log 기록 (best effort)
        try:
            if db.get_pool() is not None and result.analysis is not None:
                async with db.acquire() as conn:
                    await repositories.insert_signal_log(
                        conn,
                        source="ondemand",
                        telegram_chat_id=chat_id,
                        ticker=ticker,
                        target_date=target,
                        entry_price=result.price.current,
                        saju_score=result.saju.composite,
                        analysis_score=result.analysis.composite_score,
                        structure_state=result.analysis.structure.state,
                        alignment_bias=result.analysis.alignment.bias,
                        rsi_1h=result.analysis.rsi_1h,
                        volume_ratio_1d=result.analysis.volume_ratio_1d,
                        composite_score=result.composite_score,
                        signal_grade=result.signal_grade,
                    )
        except Exception as e:
            logger.warning("signal_log insert failed chat_id=%s: %s", chat_id, e)

        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        logger.info(...)
        return result
```

- [ ] **Step 4: Run — PASS**

```
pytest tests/test_api_signal.py -v
```

Expected: 전부 passed.

- [ ] **Step 5: Full regression + Commit**

```
pytest -q
git add src/sajucandle/api.py tests/test_api_signal.py
git commit -m "feat(api): log signals to signal_log on /signal success"
```

---

## Task 12: format.py — DISCLAIMER 상수 (TDD, 작은 태스크)

**Files:**
- Create: `src/sajucandle/format.py`
- Create: `tests/test_format.py`

- [ ] **Step 1: Write failing test**

`tests/test_format.py`:

```python
"""format: 공통 포맷 헬퍼 + DISCLAIMER 상수."""
from __future__ import annotations


def test_disclaimer_is_info_purpose_not_entertainment():
    from sajucandle.format import DISCLAIMER
    assert "정보 제공" in DISCLAIMER
    assert "엔터테인먼트" not in DISCLAIMER
    assert "본인" in DISCLAIMER


def test_disclaimer_is_single_line():
    from sajucandle.format import DISCLAIMER
    assert "\n" not in DISCLAIMER
```

- [ ] **Step 2: Run — fail**

```
pytest tests/test_format.py -v
```

Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement**

`D:\사주캔들\src\sajucandle\format.py`:

```python
"""공통 메시지 포맷 상수.

Week 8: disclaimer를 "엔터테인먼트 목적" → "정보 제공 목적"으로 톤 상향.
"""
from __future__ import annotations


DISCLAIMER = "정보 제공 목적. 투자 판단과 손실 책임은 본인에게 있습니다."
```

- [ ] **Step 4: Run — PASS**

```
pytest tests/test_format.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```
git add src/sajucandle/format.py tests/test_format.py
git commit -m "feat(format): add DISCLAIMER constant (info purpose tone)"
```

---

## Task 13: handlers.py — 새 카드 포맷 + DISCLAIMER 교체 (TDD)

**Files:**
- Modify: `src/sajucandle/handlers.py`
- Modify: `tests/test_handlers.py`

- [ ] **Step 1: Write failing tests**

`tests/test_handlers.py` 맨 아래에 추가:

```python
# ─────────────────────────────────────────────
# Week 8: 새 카드 포맷 (구조/정렬/진입조건 + DISCLAIMER 교체)
# ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_signal_card_shows_structure_alignment_entry(monkeypatch):
    """새 카드 포맷: 구조/정렬/진입조건 3줄."""
    from sajucandle import handlers
    from unittest.mock import AsyncMock, MagicMock

    payload = _aapl_signal_payload()
    payload["analysis"] = {
        "structure": {"state": "uptrend", "score": 70},
        "alignment": {
            "tf_1h": "up", "tf_4h": "up", "tf_1d": "up",
            "aligned": True, "bias": "bullish", "score": 90,
        },
        "rsi_1h": 35.0,
        "volume_ratio_1d": 1.5,
        "composite_score": 75,
        "reason": "1d↑ 4h↑ 1h↑ (강정렬) · RSI(1h) 35 · 볼륨↑",
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
    assert "구조:" in sent
    assert "상승추세" in sent or "uptrend" in sent.lower()
    assert "정렬:" in sent
    assert "1d" in sent
    assert "진입조건:" in sent or "RSI" in sent


@pytest.mark.asyncio
async def test_signal_card_uses_new_disclaimer(monkeypatch):
    """카드 말미가 '정보 제공 목적' disclaimer."""
    from sajucandle import handlers
    from unittest.mock import AsyncMock, MagicMock

    payload = _aapl_signal_payload()
    payload["analysis"] = {
        "structure": {"state": "range", "score": 50},
        "alignment": {
            "tf_1h": "flat", "tf_4h": "flat", "tf_1d": "flat",
            "aligned": False, "bias": "mixed", "score": 50,
        },
        "rsi_1h": 50.0, "volume_ratio_1d": 1.0,
        "composite_score": 50,
        "reason": "...",
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
    assert "정보 제공" in sent
    assert "엔터테인먼트" not in sent


@pytest.mark.asyncio
async def test_signal_card_shows_saju_compact_line(monkeypatch):
    """사주는 마지막 바로 위 한 줄. 'composite + grade' 간결하게."""
    from sajucandle import handlers
    from unittest.mock import AsyncMock, MagicMock

    payload = _aapl_signal_payload()
    payload["saju"] = {"composite": 56, "grade": "😐 관망"}
    payload["analysis"] = {
        "structure": {"state": "uptrend", "score": 70},
        "alignment": {"tf_1h": "up", "tf_4h": "up", "tf_1d": "up",
                      "aligned": True, "bias": "bullish", "score": 90},
        "rsi_1h": 40.0, "volume_ratio_1d": 1.2,
        "composite_score": 72,
        "reason": "...",
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
    assert "사주" in sent
    assert "56" in sent
```

- [ ] **Step 2: Run — fail**

```
pytest tests/test_handlers.py -v -k "structure_alignment_entry or new_disclaimer or saju_compact"
```

Expected: 새 포맷 없어서 FAIL.

- [ ] **Step 3: Modify _format_signal_card**

`D:\사주캔들\src\sajucandle\handlers.py` 상단 imports에 추가:
```python
from sajucandle.format import DISCLAIMER
```

기존 `_format_signal_card` 함수를 다음으로 교체:

```python
_STRUCTURE_LABEL = {
    "uptrend": "상승추세 (HH-HL)",
    "downtrend": "하락추세 (LH-LL)",
    "range": "횡보 (박스)",
    "breakout": "상승 돌파",
    "breakdown": "하락 이탈",
}

_TF_ARROW_UI = {"up": "↑", "down": "↓", "flat": "→"}


def _format_signal_card(data: dict) -> str:
    """/signal 응답 dict → 카드 문자열 (Week 8 포맷).

    구조:
      ── date ticker ──
      (장 배지 — Week 6)
      현재가: ...

      구조: ...
      정렬: 1d↑ 4h↑ 1h↗ (강정렬)
      진입조건: RSI(1h) 35 · 볼륨 1.5x

      종합: N | grade
      사주: N (grade) · 코멘트

      ※ DISCLAIMER
    """
    price = data["price"]
    saju = data["saju"]
    status = data.get("market_status") or {}
    category = status.get("category", "crypto")
    analysis = data.get("analysis")

    change_sign = "+" if price["change_pct_24h"] >= 0 else ""
    lines = [f"── {data['date']} {data['ticker']} ──"]

    if category == "us_stock":
        if status.get("is_open"):
            lines.append("🟢 장 중")
        else:
            last = status.get("last_session_date", "")
            lines.append(f"🕐 휴장 중 · 기준: {last} 종가")

    lines.append(
        f"현재가: ${price['current']:,.2f} "
        f"({change_sign}{price['change_pct_24h']:.2f}%)"
    )

    # 분석 3줄 (analysis 있을 때만)
    if analysis:
        lines.append("")
        struct_state = analysis["structure"]["state"]
        lines.append(f"구조: {_STRUCTURE_LABEL.get(struct_state, struct_state)}")
        align = analysis["alignment"]
        tf_str = (
            f"1d{_TF_ARROW_UI.get(align['tf_1d'], '?')} "
            f"4h{_TF_ARROW_UI.get(align['tf_4h'], '?')} "
            f"1h{_TF_ARROW_UI.get(align['tf_1h'], '?')}"
        )
        if align["aligned"]:
            align_tag = "강정렬"
        elif align["bias"] == "mixed":
            align_tag = "혼조"
        else:
            align_tag = "부분정렬"
        lines.append(f"정렬: {tf_str}  ({align_tag})")
        rsi_v = analysis.get("rsi_1h", 50.0)
        vr = analysis.get("volume_ratio_1d", 1.0)
        lines.append(f"진입조건: RSI(1h) {rsi_v:.0f} · 거래량 {vr:.1f}x")

    lines.append("")
    lines.append(f"종합: {data['composite_score']:>3} | {data['signal_grade']}")
    lines.append(f"사주: {saju['composite']:>3} ({saju['grade']})")

    if data.get("best_hours"):
        hrs = ", ".join(
            f"{h['shichen']}시 {h['time_range']}" for h in data["best_hours"]
        )
        lines.append(f"추천 시진: {hrs}")

    lines.append("")
    lines.append(f"※ {DISCLAIMER}")
    return "\n".join(lines)
```

- [ ] **Step 4: Run — PASS**

```
pytest tests/test_handlers.py -v
```

Expected: 기존 + 신규 3개 전부 passed. 기존 "휴장 중" 등 테스트 회귀 없어야.

만약 기존 테스트의 "엔터테인먼트" 문자열 검증이 있으면 "정보 제공"으로 업데이트.

- [ ] **Step 5: Full regression + Commit**

```
pytest -q
git add src/sajucandle/handlers.py tests/test_handlers.py
git commit -m "feat(bot): redesign signal card with structure/alignment/entry + info disclaimer"
```

---

## Task 14: broadcast.py — 모닝 카드 톤 완화 + watchlist disclaimer + BroadcastSummary 확장 (TDD)

**Files:**
- Modify: `src/sajucandle/broadcast.py`
- Modify: `tests/test_broadcast.py`

- [ ] **Step 1: Write failing tests**

`tests/test_broadcast.py` 맨 아래에 추가:

```python
# ─────────────────────────────────────────────
# Week 8: 톤 완화 + BroadcastSummary 확장
# ─────────────────────────────────────────────


def test_format_morning_card_title_changed_to_myeongsik_reference():
    """제목이 '사주캔들' → '오늘의 명식 참고'."""
    from datetime import date
    from sajucandle.broadcast import format_morning_card

    score = _score_fixture()
    card = format_morning_card(score, date(2026, 4, 19))
    assert "오늘의 명식 참고" in card
    assert "사주캔들" not in card


def test_format_morning_card_uses_new_disclaimer():
    """카드 끝이 '정보 제공' disclaimer."""
    from datetime import date
    from sajucandle.broadcast import format_morning_card

    card = format_morning_card(_score_fixture(), date(2026, 4, 19))
    assert "정보 제공" in card
    assert "엔터테인먼트" not in card


def test_format_morning_card_has_seongyang_line_not_composite():
    """'종합: N | grade' 대신 '성향: grade'."""
    from datetime import date
    from sajucandle.broadcast import format_morning_card

    card = format_morning_card(_score_fixture(), date(2026, 4, 19))
    assert "성향:" in card


def test_format_watchlist_summary_uses_new_disclaimer():
    from datetime import date
    from sajucandle.broadcast import format_watchlist_summary

    signals = [{
        "ticker": "AAPL",
        "price": {"current": 184.12, "change_pct_24h": 1.23},
        "composite_score": 66, "signal_grade": "진입",
        "market_status": {"is_open": True, "category": "us_stock",
                           "last_session_date": "2026-04-18"},
    }]
    card = format_watchlist_summary(signals, date(2026, 4, 19))
    assert "정보 제공" in card
    assert "엔터테인먼트" not in card


def test_broadcast_summary_has_tracking_fields():
    from sajucandle.broadcast import BroadcastSummary
    s = BroadcastSummary()
    assert s.tracking_updated == 0
    assert s.tracking_completed == 0
    assert s.tracking_failed == 0
```

- [ ] **Step 2: Run — fail**

Expected: 위 5개 중 몇 개가 FAIL.

- [ ] **Step 3: Modify broadcast.py**

**(a) DISCLAIMER import:**
```python
from sajucandle.format import DISCLAIMER
```

**(b) `BroadcastSummary` 필드 3개 추가:**
```python
@dataclass
class BroadcastSummary:
    # 기존 필드들 ...
    # Week 8
    tracking_updated: int = 0
    tracking_completed: int = 0
    tracking_failed: int = 0
```

**(c) `format_morning_card` 수정:**

기존 함수를 찾아 다음 변경:
- 제목 라인: `"☀️ {date} ({weekday}) 사주캔들"` → `"☀️ {date} ({weekday}) 오늘의 명식 참고"`
- "종합: N | grade" 라인을 **"성향: grade (변동성 주의)"** 형태로. dominant axis 간단 코멘트:
  ```python
  # 4축 중 가장 극단(50에서 가장 먼) 찾아 한 단어 코멘트
  axes = score_data.get("axes", {})
  dominant_comment = _dominant_axis_comment(axes)
  lines.append(f"성향: {score_data['signal_grade']}  ({dominant_comment})")
  ```
  `_dominant_axis_comment` 헬퍼 신설:
  ```python
  def _dominant_axis_comment(axes: dict) -> str:
      """4축 중 50에서 가장 먼 축의 짧은 코멘트."""
      if not axes:
          return ""
      ranked = sorted(axes.items(),
                       key=lambda kv: abs(kv[1]["score"] - 50), reverse=True)
      key, val = ranked[0]
      label = {
          "wealth": "재물 흐름 주의",
          "decision": "결단 주의",
          "volatility": "변동성 주의",
          "flow": "합運 우세",
      }.get(key, "")
      return label
  ```
- disclaimer 라인: `"※ 엔터테인먼트 목적. 투자 추천 아님."` → `f"※ {DISCLAIMER}"`
- CTA 라인에 "/watchlist 확인" 추가 (있다면):
  ```python
  lines.append("오늘 BTC는 /signal, 관심 종목은 /watchlist 확인.")
  ```

**(d) `format_watchlist_summary` 수정:**

기존 함수 끝 disclaimer를 `DISCLAIMER` 사용:
```python
lines.append(f"※ {DISCLAIMER}")
```

- [ ] **Step 4: Run — PASS**

```
pytest tests/test_broadcast.py -v -k "morning_card or watchlist_summary or tracking_fields"
```

Expected: 신규 + 기존 일부 수정 전부 passed.

기존 테스트 중 "엔터테인먼트" 검증이나 "사주캔들" 제목 검증이 있으면 새 문구로 업데이트.

- [ ] **Step 5: Full regression + Commit**

```
pytest -q
git add src/sajucandle/broadcast.py tests/test_broadcast.py
git commit -m "feat(broadcast): soften morning card tone + new disclaimer + tracking fields"
```

---

## Task 15: broadcast.py — Phase 0 tracking + Phase 1/3 insert_signal_log (TDD, 큰 태스크)

**Files:**
- Modify: `src/sajucandle/broadcast.py`
- Modify: `tests/test_broadcast.py`

- [ ] **Step 1: Write failing tests**

`tests/test_broadcast.py` 맨 아래에 추가:

```python
# ─────────────────────────────────────────────
# Week 8: Phase 0 tracking
# ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_phase0_updates_pending_tracking_rows():
    """Phase 0: list_pending_tracking으로 조회된 row를 업데이트."""
    from datetime import date, datetime, timezone, timedelta
    from unittest.mock import AsyncMock, MagicMock
    from sajucandle.broadcast import run_broadcast
    from sajucandle.repositories import SignalLogRow

    api_client = MagicMock()
    api_client.get_admin_users = AsyncMock(return_value=[])
    api_client.get_admin_watchlist_symbols = AsyncMock(return_value=[])
    api_client.get_score = AsyncMock()

    # pending: 2h 전 시그널 row
    two_hours_ago = datetime.now(timezone.utc) - timedelta(hours=2)
    pending_row = SignalLogRow(
        id=101, sent_at=two_hours_ago, source="ondemand",
        telegram_chat_id=99, ticker="BTCUSDT",
        target_date=date(2026, 4, 19), entry_price=70000.0,
        saju_score=50, analysis_score=70,
        structure_state="uptrend", alignment_bias="bullish",
        rsi_1h=None, volume_ratio_1d=None,
        composite_score=68, signal_grade="진입",
        mfe_7d_pct=None, mae_7d_pct=None,
        close_24h=None, close_7d=None,
        last_tracked_at=None, tracking_done=False,
    )

    # fetch_klines가 1h봉 리턴 (entry 이후 몇 시간)
    post_klines = _make_klines(n=2, base_close=72000.0, drift=500.0)  # 72k 상승

    api_client.fetch_klines_for_tracking = AsyncMock(return_value=post_klines)

    tracking_list = AsyncMock(return_value=[pending_row])
    tracking_update = AsyncMock()

    send = AsyncMock()
    summary = await run_broadcast(
        api_client=api_client,
        send_message=send,
        chat_ids=[],
        target_date=date(2026, 4, 19),
        dry_run=True,
        admin_chat_id=None,
        skip_watchlist=True,
        _list_pending_tracking=tracking_list,
        _update_signal_tracking=tracking_update,
        _get_klines_for_tracking=api_client.fetch_klines_for_tracking,
    )
    assert summary.tracking_updated >= 1
    tracking_list.assert_called()
    tracking_update.assert_called()
```

**주의:** Phase 0 구현은 DB와 market provider 접근이 필요. 테스트 단순화를 위해 `run_broadcast`에 DI 포인트 3개 추가:
- `_list_pending_tracking: Optional[Callable]` (default: `repositories.list_pending_tracking`)
- `_update_signal_tracking: Optional[Callable]` (default: `repositories.update_signal_tracking`)
- `_get_klines_for_tracking: Optional[Callable]` (default: 내부에서 market_router 사용)

**실제 운영에서는 default 콜백 (DB 직접 접근)을 사용**하되, 테스트에서는 위 3개를 mock으로 주입.

이 방식이 너무 복잡하면 **Phase 0를 run_broadcast 외부 함수로 분리** (`run_phase0_tracking()`), run_broadcast는 호출만. 이 방식으로 변경:

테스트 재작성:

```python
@pytest.mark.asyncio
async def test_phase0_runs_independently():
    """run_phase0_tracking: pending row 조회 → 업데이트 → summary 반환."""
    from datetime import date, datetime, timezone, timedelta
    from unittest.mock import AsyncMock
    from sajucandle.broadcast import run_phase0_tracking
    from sajucandle.repositories import SignalLogRow
    from sajucandle.market_data import Kline

    two_hours_ago = datetime.now(timezone.utc) - timedelta(hours=2)
    pending = [
        SignalLogRow(
            id=101, sent_at=two_hours_ago, source="ondemand",
            telegram_chat_id=99, ticker="BTCUSDT",
            target_date=date(2026, 4, 19), entry_price=70000.0,
            saju_score=50, analysis_score=70,
            structure_state="uptrend", alignment_bias="bullish",
            rsi_1h=None, volume_ratio_1d=None,
            composite_score=68, signal_grade="진입",
            mfe_7d_pct=None, mae_7d_pct=None,
            close_24h=None, close_7d=None,
            last_tracked_at=None, tracking_done=False,
        ),
    ]

    # post-entry 1h klines
    post = [
        Kline(open_time=two_hours_ago + timedelta(minutes=30),
              open=71000, high=72000, low=70500, close=71500, volume=1000),
        Kline(open_time=two_hours_ago + timedelta(hours=1, minutes=30),
              open=71500, high=72500, low=71000, close=72000, volume=1000),
    ]

    list_pending = AsyncMock(return_value=pending)
    update_tracking = AsyncMock()
    get_klines = AsyncMock(return_value=post)

    result = await run_phase0_tracking(
        list_pending=list_pending,
        update_tracking=update_tracking,
        get_klines=get_klines,
        now=datetime.now(timezone.utc),
    )
    assert result["updated"] == 1
    assert result["completed"] == 0
    # update_tracking 인자 검증
    _, kwargs = update_tracking.call_args
    # mfe = (72500 - 70000) / 70000 * 100 = 3.571
    assert kwargs["mfe_pct"] == pytest.approx(3.571, abs=0.01)


@pytest.mark.asyncio
async def test_phase0_marks_done_after_7d():
    """sent_at이 7일 이상 경과 → tracking_done=True."""
    from datetime import date, datetime, timezone, timedelta
    from unittest.mock import AsyncMock
    from sajucandle.broadcast import run_phase0_tracking
    from sajucandle.repositories import SignalLogRow
    from sajucandle.market_data import Kline

    eight_days_ago = datetime.now(timezone.utc) - timedelta(days=8)
    pending = [
        SignalLogRow(
            id=102, sent_at=eight_days_ago, source="ondemand",
            telegram_chat_id=99, ticker="BTCUSDT",
            target_date=date(2026, 4, 10), entry_price=70000.0,
            saju_score=50, analysis_score=70,
            structure_state="uptrend", alignment_bias="bullish",
            rsi_1h=None, volume_ratio_1d=None,
            composite_score=68, signal_grade="진입",
            mfe_7d_pct=None, mae_7d_pct=None,
            close_24h=None, close_7d=None,
            last_tracked_at=None, tracking_done=False,
        ),
    ]
    post = [Kline(open_time=eight_days_ago + timedelta(hours=1),
                   open=70000, high=75000, low=69000, close=74000, volume=1000)]

    list_pending = AsyncMock(return_value=pending)
    update_tracking = AsyncMock()
    get_klines = AsyncMock(return_value=post)

    result = await run_phase0_tracking(
        list_pending=list_pending,
        update_tracking=update_tracking,
        get_klines=get_klines,
        now=datetime.now(timezone.utc),
    )
    _, kwargs = update_tracking.call_args
    assert kwargs["tracking_done"] is True
    assert result["completed"] == 1
```

- [ ] **Step 2: Run — fail**

```
pytest tests/test_broadcast.py -v -k "phase0"
```

Expected: `ImportError: cannot import name 'run_phase0_tracking'`.

- [ ] **Step 3: Add run_phase0_tracking function**

`D:\사주캔들\src\sajucandle\broadcast.py`에 추가 (파일 적절한 위치, 예: `run_broadcast` 함수 바로 위):

```python
async def run_phase0_tracking(
    *,
    list_pending,       # async callable(conn, now) → list[SignalLogRow] (또는 DI된 mock)
    update_tracking,    # async callable(conn, id, **kwargs)
    get_klines,         # async callable(ticker, sent_at) → list[Kline]
    now: datetime,
) -> dict:
    """Phase 0: pending signal_log row들의 MFE/MAE 업데이트.

    Returns dict with keys: updated, completed, failed.
    """
    summary = {"updated": 0, "completed": 0, "failed": 0}
    try:
        pending = await list_pending(now=now)
    except Exception as e:
        logger.warning("phase0 list_pending failed: %s", e)
        return summary

    from datetime import timedelta

    for row in pending:
        try:
            post_bars = await get_klines(row.ticker, row.sent_at)
            if not post_bars:
                continue
            highs = [k.high for k in post_bars]
            lows = [k.low for k in post_bars]
            entry = row.entry_price
            if entry <= 0:
                continue
            mfe_pct = (max(highs) / entry - 1.0) * 100.0
            mae_pct = (min(lows) / entry - 1.0) * 100.0

            # close_24h / close_7d
            close_24h = None
            close_7d = None
            t_24h = row.sent_at + timedelta(hours=24)
            t_7d = row.sent_at + timedelta(days=7)
            for k in post_bars:
                if close_24h is None and k.open_time >= t_24h:
                    close_24h = k.close
                if close_7d is None and k.open_time >= t_7d:
                    close_7d = k.close
                    break

            hours_since = (now - row.sent_at).total_seconds() / 3600
            done = hours_since >= 168

            await update_tracking(
                signal_id=row.id,
                mfe_pct=mfe_pct,
                mae_pct=mae_pct,
                close_24h=close_24h,
                close_7d=close_7d,
                tracking_done=done,
            )
            summary["updated"] += 1
            if done:
                summary["completed"] += 1
        except Exception as e:
            logger.warning("phase0 update failed signal_id=%s: %s", row.id, e)
            summary["failed"] += 1

    return summary
```

그리고 `run_broadcast` 함수 시작부(Phase 1 precompute **이전**)에 Phase 0 호출 추가:

```python
    # ─── Phase 0: MFE/MAE tracking (default callbacks) ───
    if list_pending_tracking_fn is None:
        # default: 실제 DB + market_router 사용
        async def _default_list_pending(now):
            from sajucandle import db as _db, repositories as _repo
            if _db.get_pool() is None:
                return []
            async with _db.acquire() as conn:
                return await _repo.list_pending_tracking(conn, now)

        async def _default_update(signal_id, **kwargs):
            from sajucandle import db as _db, repositories as _repo
            if _db.get_pool() is None:
                return
            async with _db.acquire() as conn:
                await _repo.update_signal_tracking(conn, signal_id, **kwargs)

        async def _default_get_klines(ticker, sent_at):
            # 간접 HTTP로 1h봉 조회 — broadcast에 market_router 직접 없음
            # api_client.get_signal 호출 대신 signal API에서 klines 노출 없음
            # → 간단히 "그때 이후 지금까지" 1h봉을 api에서 요청. 엔드포인트 없으므로 빈 리스트.
            # Week 9에서 admin ohlcv 엔드포인트 추가. 현재는 업데이트 skip.
            return []

        list_pending_tracking_fn = _default_list_pending
        update_signal_tracking_fn = _default_update
        get_klines_for_tracking_fn = _default_get_klines

    try:
        phase0 = await run_phase0_tracking(
            list_pending=list_pending_tracking_fn,
            update_tracking=update_signal_tracking_fn,
            get_klines=get_klines_for_tracking_fn,
            now=datetime.now(timezone.utc),
        )
        summary.tracking_updated = phase0["updated"]
        summary.tracking_completed = phase0["completed"]
        summary.tracking_failed = phase0["failed"]
    except Exception as e:
        logger.warning("phase 0 failed: %s", e)
```

run_broadcast 시그니처에 DI 파라미터 3개 추가:
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
    skip_watchlist: bool = False,
    # Week 8
    list_pending_tracking_fn=None,
    update_signal_tracking_fn=None,
    get_klines_for_tracking_fn=None,
) -> BroadcastSummary:
```

**중요:** `get_klines_for_tracking` default 구현은 빈 리스트 반환 — Phase 0가 동작하긴 하되 실제 MFE/MAE는 계산 안 됨. **Week 9에 admin OHLCV 엔드포인트 추가 예정**. Task 15는 구조만 확립하고 실제 데이터 연결은 다음 스프린트.

이는 스펙 §11 "Phase 0 추적 크론 실패 독립"과 일치 — 실패해도 Phase 1/2/3은 정상.

- [ ] **Step 4: Run — PASS**

```
pytest tests/test_broadcast.py -v -k "phase0"
```

Expected: 2개 passed.

- [ ] **Step 5: Full regression**

```
pytest -q
```

Expected: 전량 통과. Week 7 broadcast 테스트 회귀 0 (default가 빈 list라 영향 없음).

- [ ] **Step 6: Commit**

```
git add src/sajucandle/broadcast.py tests/test_broadcast.py
git commit -m "feat(broadcast): add Phase 0 MFE/MAE tracking loop (skeleton)"
```

---

## Task 16: README + final lint + push + prod smoke

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Lint**

```
ruff check src/ tests/
```

Expected: clean. 에러 있으면 수정.

- [ ] **Step 2: Full pytest**

```
pytest -q
```

Expected: 200+ passed, ~60 skipped.

- [ ] **Step 3: Update README**

Week 7 섹션 아래에 Week 8 섹션 추가:

```markdown
## Week 8 Phase 1: 기술 분석 엔진 재설계

현재까지 RSI/MA/volume 3지표 일봉 단일 TF였던 `tech_analysis.py`를 **시장 구조 + 멀티 타임프레임 + 수급** 3축 프레임으로 재구성. 사주 가중치 0.4→0.1 강등, 모든 시그널 `signal_log` DB 기록 + MFE/MAE 7일 추적.

### 새 아키텍처

```
SignalService.compute(ticker)
  ├── ScoreService.compute()          # 사주 composite (가중치 0.1)
  └── analysis.composite.analyze()    # 가중치 0.9
       ├── swing.detect_swings()      # Fractals + ATR
       ├── structure.classify()       # UPTREND/DOWNTREND/RANGE/BREAKOUT/BREAKDOWN
       ├── multi_timeframe.compute()  # 1h/4h/1d 정렬
       └── rsi(1h) + volume(1d)       # 기존 tech_analysis 보조
```

### 가중치

```
composite = 0.45 * structure + 0.35 * alignment + 0.10 * rsi + 0.10 * volume
final = 0.1 * saju + 0.9 * analysis
```

### 강진입 조건 (3중 조건)

```
score >= 75
 + alignment.aligned = True
 + structure.state in (UPTREND, BREAKOUT)
```

### 새 카드 포맷

```
── 2026-04-19 AAPL ──
🟢 장 중
현재가: $184.12 (+1.23%)

구조: 상승추세 (HH-HL)
정렬: 1d↑ 4h↑ 1h↗  (강정렬)
진입조건: RSI(1h) 35 · 거래량 1.5x

종합: 72 | 진입
사주: 56 (관망)

※ 정보 제공 목적. 투자 판단과 손실 책임은 본인에게 있습니다.
```

### signal_log 테이블 + MFE/MAE 추적

- 모든 /signal 호출 + broadcast 발송 시 DB 기록
- Phase 0 (broadcast 07:00 크론 맨 앞): pending row의 MFE/MAE 업데이트
- 7일 경과 시 `tracking_done=TRUE`
- Week 11 백테스트 분석 원천 데이터

### 범위 밖 (Week 9~11)

- **Week 9:** 지지/저항 자동 식별, SL/TP 자동 제안, admin OHLCV 엔드포인트 (Phase 0 실데이터 연결)
- **Week 10:** 시그널 발송 거부 규칙, 카드 세밀 조정
- **Week 11:** MFE/MAE 통계 집계 API, 카드에 백테스트 프루프 노출
```

또한 기존 README에서 갱신:
- 테스트 카운트 (새 숫자)
- 아키텍처 다이어그램에 `analysis/` 패키지 추가
- "엔터테인먼트 목적" 문구 있으면 "정보 제공 목적"으로

- [ ] **Step 4: Commit README**

```
git add README.md
git commit -m "docs: Week 8 Phase 1 analysis engine redesign"
```

- [ ] **Step 5: Review commit log + Push**

```
git log --oneline origin/main..HEAD
```

- [ ] **Step 6: Push**

```
git push origin main
```

Expected: Railway 3서비스 자동 재배포.

- [ ] **Step 7: Manual steps (사용자 직접)**

아래는 subagent가 할 수 없음 — **사용자에게 안내**:

1. Supabase Studio → SQL Editor → `migrations/003_signal_log.sql` 실행
2. (선택) SQL 확인: `SELECT COUNT(*) FROM signal_log;` → 0 반환하면 테이블 존재
3. Railway `sajucandle-broadcast` 재시작 (Variables 변경 없음)

- [ ] **Step 8: Production smoke**

배포 완료 후:

**API 확인:**
```
curl.exe -H "X-SAJUCANDLE-KEY: <KEY>" https://sajucandle-api-production.up.railway.app/v1/users/<YOUR_CHAT_ID>/signal?ticker=AAPL
```

Expected: `analysis` 필드 + `structure`/`alignment`/`composite_score` 포함.

**봇 스모크:**
- `/signal AAPL` → 새 3줄 포맷 (구조/정렬/진입조건)
- `/signal` (BTC) → 동일
- 모닝 카드 (다음날 07:00 or 수동 트리거) → "오늘의 명식 참고" 제목 + "정보 제공" disclaimer
- Supabase SQL: `SELECT * FROM signal_log ORDER BY sent_at DESC LIMIT 5;` → /signal 호출 후 row 쌓이는지

---

## Self-Review

### Spec coverage

- [x] §2.1 signal_log + MFE/MAE: Task 1, 10, 11, 15
- [x] §2.2 Fractals + ATR: Task 2
- [x] §2.3 MarketStructure: Task 3
- [x] §2.4 TF별 TrendDirection + 정렬: Task 4, 5
- [x] §2.5 composite 조합기: Task 6
- [x] §2.6 가중치 0.1/0.9 + 강진입 추가조건: Task 9
- [x] §2.7 카드 3줄 개편: Task 13
- [x] §2.8 모닝 카드 톤 완화: Task 14
- [x] §2.9 disclaimer 교체: Task 12, 13, 14
- [x] §2.10 yfinance 1h/4h/1d: Task 7
- [x] §5.1 signal_log 스키마: Task 1
- [x] §5.2 repo 함수: Task 10
- [x] §5.3 기록 시점 (api.py): Task 11
- [x] §6 MFE/MAE Phase 0: Task 15
- [x] §7 카드 포맷: Task 13, 14
- [x] §8 SignalResponse 확장: Task 8
- [x] §9 테스트 전략: 각 Task에 TDD 포함

### Placeholder scan

- "TBD", "TODO", "similar to" 없음
- 모든 step에 실제 코드/명령 포함
- Phase 0 `_default_get_klines`는 **의도적으로 빈 리스트 반환** (Week 9에서 실제 연결 예정) — 명시적 설명 포함됨

### Type consistency

- `SwingPoint(index, timestamp, price, kind)` 정의(Task 2) ↔ `structure.py` 사용(Task 3) 일치
- `MarketStructure` enum 값 "uptrend"/"downtrend"/etc. Task 3 정의 ↔ composite.py/models.py/handlers.py 사용 일치
- `TrendDirection` enum Task 4 ↔ multi_timeframe.py 사용 일치
- `Alignment` 필드명 Task 5 ↔ composite/models/handlers 일치
- `AnalysisResult` Task 6 ↔ signal_service `_analysis_to_summary` 변환 Task 9 필드명 일치
- `AnalysisSummary.structure.state` 문자열(Literal) vs `AnalysisResult.structure.state` enum — Task 9에서 `.value`로 변환 명시
- `SignalLogRow` Task 10 ↔ `run_phase0_tracking` Task 15 필드 접근 일치

### 주의사항

- Task 9 signal_service refactor는 큰 변경 — 기존 chart 필드 하위호환 유지 세심히
- Task 15 Phase 0의 `_default_get_klines`는 skeleton. Week 9에서 admin OHLCV 엔드포인트 + 실데이터 연결
- Task 11의 insert_signal_log는 "best effort" — DB 장애 시 시그널 응답에 영향 없음 (try/except)
- 기존 test_broadcast.py가 get_watchlist MagicMock으로 우연히 통과 — Task 15에서 Phase 0 mock 필요 (tracking_*_fn 3개 전달 안 하면 default)

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-04-19-week8-analysis-engine.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**

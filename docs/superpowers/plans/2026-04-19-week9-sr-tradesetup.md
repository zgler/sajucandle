# Week 9 Phase 2: S/R + SL/TP + admin OHLCV Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 시그널을 "의견"에서 "트레이딩 도구"로 격상. 지지/저항 자동 식별 (swing+volume profile) + 하이브리드 ATR/S/R SL·TP + 등급별 차등 카드 표시 + `GET /v1/admin/ohlcv` 엔드포인트로 Week 8 Phase 0 tracking을 실데이터와 연결.

**Architecture:** 새 `analysis/volume_profile.py` + `support_resistance.py` + `trade_setup.py` 3모듈 추가. `composite.analyze()`가 `sr_levels`와 `atr_1d`를 채우고, `SignalService`가 등급 결정 후 "진입"/"강진입"에만 `TradeSetup` 생성. `api.py`에 admin OHLCV 엔드포인트 추가 → broadcast Phase 0 default callback이 이를 호출 → signal_log에 MFE/MAE 실데이터 채워지기 시작. 카드 포맷은 handlers.py에서 grade별 분기 (세팅 블록 vs 주요 레벨 블록).

**Tech Stack:** Python 3.12, FastAPI, asyncpg, pandas, pydantic v2, pytest, pytest-asyncio, fakeredis, respx. 기존 Week 1~8 인프라 재사용.

**Spec:** `docs/superpowers/specs/2026-04-19-week9-sr-tradesetup-design.md` (commit ed5f655)

---

## File Structure

```
migrations/
└── 004_signal_log_tradesetup.sql       # [CREATE] ALTER TABLE 10 columns

src/sajucandle/
├── analysis/
│   ├── volume_profile.py               # [CREATE] VolumeNode + compute_volume_profile
│   ├── support_resistance.py           # [CREATE] LevelKind, SRLevel, identify_sr_levels
│   ├── trade_setup.py                  # [CREATE] TradeSetup + compute_trade_setup
│   └── composite.py                    # [MODIFY] AnalysisResult sr_levels + atr_1d
├── models.py                           # [MODIFY] SRLevelSummary + TradeSetupSummary + AnalysisSummary 확장
├── signal_service.py                   # [MODIFY] trade_setup 조건부 생성, Pydantic 변환
├── repositories.py                     # [MODIFY] insert_signal_log에 SL/TP Optional 파라미터 10개
├── api.py                              # [MODIFY] GET /v1/admin/ohlcv 엔드포인트 + signal_log insert에 SL/TP 필드
├── api_client.py                       # [MODIFY] get_admin_ohlcv
├── handlers.py                         # [MODIFY] _format_signal_card 등급별 분기
└── broadcast.py                        # [MODIFY] _default_get_klines → admin ohlcv 호출 클로저

tests/
├── test_analysis_volume_profile.py     # [CREATE]
├── test_analysis_support_resistance.py # [CREATE]
├── test_analysis_trade_setup.py        # [CREATE]
├── test_analysis_composite.py          # [MODIFY] sr_levels + atr_1d 검증
├── test_signal_service.py              # [MODIFY] trade_setup 조건부 생성
├── test_api_ohlcv.py                   # [CREATE] admin OHLCV 엔드포인트
├── test_api_client.py                  # [MODIFY] get_admin_ohlcv
├── test_broadcast.py                   # [MODIFY] Phase 0 default callback
├── test_handlers.py                    # [MODIFY] 세팅 블록 vs 주요 레벨 블록
└── test_repositories.py                # [MODIFY] insert_signal_log SL/TP 저장

README.md                               # [MODIFY] Week 9 섹션 추가
```

**운영 수동 단계 (Task 14):**
- Supabase Studio → `migrations/004_signal_log_tradesetup.sql` 실행

---

## Task 1: migration 004 — signal_log SL/TP 컬럼 추가

**Files:**
- Create: `migrations/004_signal_log_tradesetup.sql`

- [ ] **Step 1: Create migration file**

`D:\사주캔들\migrations\004_signal_log_tradesetup.sql`:

```sql
-- Week 9: signal_log에 TradeSetup 컬럼 추가.
-- 실행: Supabase Studio → SQL Editor → Run.

ALTER TABLE signal_log
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

**주의:** 스펙 §7.1은 `entry_price_tradesetup`도 포함이지만 MVP는 `entry_price`와 동일값이라 **분리 안 함**. 필요 시 Week 10에서 추가. 9개 컬럼만.

- [ ] **Step 2: Apply to local TEST DB if TEST_DATABASE_URL set**

```
if ($env:TEST_DATABASE_URL) { psql $env:TEST_DATABASE_URL -f migrations/004_signal_log_tradesetup.sql }
```

Expected: `ALTER TABLE` 출력 또는 `NOTICE: column already exists`.

- [ ] **Step 3: Commit**

```
git add migrations/004_signal_log_tradesetup.sql
git commit -m "feat(db): add signal_log SL/TP columns (Week 9)"
```

---

## Task 2: analysis/volume_profile.py (TDD)

**Files:**
- Create: `src/sajucandle/analysis/volume_profile.py`
- Create: `tests/test_analysis_volume_profile.py`

- [ ] **Step 1: Write failing tests**

`D:\사주캔들\tests\test_analysis_volume_profile.py`:

```python
"""analysis.volume_profile: 가격 bucket별 거래량 누적 → 매물대 상위 N개."""
from __future__ import annotations

from datetime import datetime, timezone

from sajucandle.analysis.volume_profile import VolumeNode, compute_volume_profile
from sajucandle.market_data import Kline


def _mk_klines(triples: list[tuple[float, float, float]]) -> list[Kline]:
    """Each tuple = (high, low, volume). open=close=(h+l)/2."""
    out = []
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for i, (h, l, v) in enumerate(triples):
        mid = (h + l) / 2
        out.append(Kline(
            open_time=base.replace(day=(i % 28) + 1),
            open=mid, high=h, low=l, close=mid, volume=v,
        ))
    return out


def test_compute_volume_profile_empty():
    assert compute_volume_profile([]) == []


def test_compute_volume_profile_returns_top_n_nodes():
    """높은 거래량 bucket이 상위 N개 반환."""
    klines = _mk_klines([
        (105, 100, 100),    # bucket around 102.5
        (110, 105, 500),    # around 107.5 (high volume)
        (105, 100, 200),
        (110, 105, 500),    # 또 107.5 근처
        (115, 110, 50),
        (105, 100, 300),
    ])
    nodes = compute_volume_profile(klines, bucket_count=5, top_n=3)
    assert len(nodes) <= 3
    assert all(isinstance(n, VolumeNode) for n in nodes)
    # 가장 높은 볼륨 bucket이 첫 번째
    assert nodes[0].volume_sum >= nodes[-1].volume_sum


def test_volume_node_is_dataclass():
    from dataclasses import is_dataclass
    assert is_dataclass(VolumeNode)
    n = VolumeNode(price_low=100.0, price_high=105.0, volume_sum=500.0)
    assert n.price_low == 100.0


def test_compute_volume_profile_bucket_boundaries():
    """bucket_count=10에서 가격 범위 min~max를 10등분."""
    klines = _mk_klines([(100 + i, 100 + i, 10) for i in range(10)])
    nodes = compute_volume_profile(klines, bucket_count=10, top_n=5)
    # 각 bucket에 하나씩 kline이 들어감 — 분포 고름
    assert len(nodes) == 5   # top_n=5
    # 각 node의 price_low < price_high
    for n in nodes:
        assert n.price_low < n.price_high


def test_compute_volume_profile_single_price_returns_one_node():
    """모든 bar가 같은 가격이면 range=0. 1개 node 반환 (or empty)."""
    klines = _mk_klines([(100, 100, 100)] * 5)
    nodes = compute_volume_profile(klines, bucket_count=5, top_n=3)
    # range=0이면 degenerate — 빈 리스트 or 단일 node
    assert len(nodes) <= 1
```

- [ ] **Step 2: Run — fail**

```
pytest tests/test_analysis_volume_profile.py -v
```

Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement**

`D:\사주캔들\src\sajucandle\analysis\volume_profile.py`:

```python
"""Volume Profile (VPVR) 근사치: 가격 bucket별 거래량 누적.

MVP: 각 봉의 중간값 (high+low)/2가 속한 bucket에 volume 전체를 배정.
정확한 VPVR은 봉 내 가격 분포를 보간해야 하지만 YAGNI.
"""
from __future__ import annotations

from dataclasses import dataclass

from sajucandle.market_data import Kline


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
    """가격 범위를 bucket_count 등분 → 각 bucket 거래량 합계 → 상위 top_n.

    반환: volume_sum 내림차순. 빈 입력이나 가격 range=0이면 [].
    """
    if not klines or bucket_count <= 0 or top_n <= 0:
        return []

    price_min = min(k.low for k in klines)
    price_max = max(k.high for k in klines)
    if price_max <= price_min:
        return []

    bucket_width = (price_max - price_min) / bucket_count
    if bucket_width <= 0:
        return []

    buckets: list[float] = [0.0] * bucket_count
    for k in klines:
        mid = (k.high + k.low) / 2
        idx = int((mid - price_min) / bucket_width)
        if idx == bucket_count:   # price_max 경계 보정
            idx = bucket_count - 1
        if 0 <= idx < bucket_count:
            buckets[idx] += k.volume

    nodes: list[VolumeNode] = []
    for i, vol in enumerate(buckets):
        if vol <= 0:
            continue
        low = price_min + i * bucket_width
        high = price_min + (i + 1) * bucket_width
        nodes.append(VolumeNode(
            price_low=low, price_high=high, volume_sum=vol,
        ))

    nodes.sort(key=lambda n: n.volume_sum, reverse=True)
    return nodes[:top_n]
```

- [ ] **Step 4: Run — PASS**

```
pytest tests/test_analysis_volume_profile.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Full regression + Commit**

```
pytest -q
git add src/sajucandle/analysis/volume_profile.py tests/test_analysis_volume_profile.py
git commit -m "feat(analysis): add volume profile (VPVR top-N nodes)"
```

---

## Task 3: analysis/support_resistance.py (TDD)

**Files:**
- Create: `src/sajucandle/analysis/support_resistance.py`
- Create: `tests/test_analysis_support_resistance.py`

- [ ] **Step 1: Write failing tests**

`D:\사주캔들\tests\test_analysis_support_resistance.py`:

```python
"""analysis.support_resistance: swing + volume → SRLevel 융합."""
from __future__ import annotations

from datetime import datetime, timezone

from sajucandle.analysis.support_resistance import (
    LevelKind,
    SRLevel,
    identify_sr_levels,
)
from sajucandle.analysis.swing import SwingPoint
from sajucandle.analysis.volume_profile import VolumeNode
from sajucandle.market_data import Kline


def _sp(kind: str, price: float, idx: int = 0) -> SwingPoint:
    return SwingPoint(
        index=idx, timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
        price=price, kind=kind,  # type: ignore[arg-type]
    )


def _kline(high: float, low: float, vol: float = 1000) -> Kline:
    mid = (high + low) / 2
    return Kline(
        open_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
        open=mid, high=high, low=low, close=mid, volume=vol,
    )


def test_empty_inputs_returns_empty():
    r = identify_sr_levels(klines_1d=[], swings=[], current_price=100.0)
    assert r == []


def test_swing_high_above_current_is_resistance():
    klines = [_kline(110, 90)] * 50
    swings = [_sp("high", 108), _sp("low", 92)]
    r = identify_sr_levels(klines, swings, current_price=100.0)
    resistances = [x for x in r if x.kind == LevelKind.RESISTANCE]
    supports = [x for x in r if x.kind == LevelKind.SUPPORT]
    assert any(abs(x.price - 108) < 1 for x in resistances)
    assert any(abs(x.price - 92) < 1 for x in supports)


def test_swing_and_volume_overlap_strength_high():
    """swing + volume이 같은 가격대에 있으면 strength=high."""
    klines = [_kline(110, 100, 10000)] * 30   # 105 근처 고볼륨
    swings = [_sp("high", 105)]   # 같은 가격
    r = identify_sr_levels(klines, swings, current_price=95.0,
                            max_resistances=5)
    # 105 근처 저항에 high strength 있어야
    near_105 = [x for x in r if abs(x.price - 105) < 6]
    assert any(x.strength == "high" for x in near_105)


def test_volume_only_level_medium_if_top_bucket():
    """volume_node 단독이면 medium (상위 1 volume이면)."""
    klines = [_kline(120, 110, 50000)] * 20 + [_kline(100, 95, 1000)] * 20
    swings = []   # swing 없음
    r = identify_sr_levels(klines, swings, current_price=105.0)
    volume_based = [x for x in r if "volume_node" in x.sources]
    assert len(volume_based) > 0
    # 적어도 1개는 medium 이상
    assert any(x.strength in ("medium", "high") for x in volume_based)


def test_levels_limited_by_max_count():
    klines = [_kline(100 + i, 90 + i, 1000) for i in range(50)]
    swings = [_sp("high", 150), _sp("high", 145), _sp("high", 140),
              _sp("high", 135), _sp("low", 80), _sp("low", 75)]
    r = identify_sr_levels(klines, swings, current_price=120,
                            max_supports=2, max_resistances=2)
    assert len([x for x in r if x.kind == LevelKind.RESISTANCE]) <= 2
    assert len([x for x in r if x.kind == LevelKind.SUPPORT]) <= 2


def test_merge_tolerance_combines_close_levels():
    """1% 이내 가까운 level은 병합."""
    klines = [_kline(110, 90)] * 30
    swings = [_sp("high", 108), _sp("high", 108.5)]   # 0.46% 차이
    r = identify_sr_levels(klines, swings, current_price=100.0,
                            merge_tolerance_pct=1.0)
    # 병합되어 1개만 나와야 함
    resistances = [x for x in r if x.kind == LevelKind.RESISTANCE]
    # 108 ~ 108.5 구간에 1개만
    near_108 = [x for x in resistances if 107 <= x.price <= 109]
    assert len(near_108) == 1


def test_sr_level_is_dataclass():
    from dataclasses import is_dataclass
    assert is_dataclass(SRLevel)
    level = SRLevel(price=100.0, kind=LevelKind.SUPPORT,
                    strength="medium", sources=["swing_low"])
    assert level.price == 100.0
```

- [ ] **Step 2: Run — fail**

```
pytest tests/test_analysis_support_resistance.py -v
```

Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement**

`D:\사주캔들\src\sajucandle\analysis\support_resistance.py`:

```python
"""Swing points + Volume profile → SRLevel 융합.

Level 후보:
  - swing_high → RESISTANCE 후보 (price = sp.price)
  - swing_low → SUPPORT 후보
  - volume_node → 현재가 위면 RESISTANCE, 아래면 SUPPORT
    (node 중간가 사용)

Merge: 같은 kind의 후보들 중 merge_tolerance_pct% 이내 병합 → sources 합침.
Strength:
  - swing_* + volume_node 모두 있음 → "high"
  - volume_node 있고 상위 1 volume → "medium"
  - 그 외 → "low"

현재가 기준:
  - SUPPORT: price < current, 가까운 순 max_supports개
  - RESISTANCE: price > current, 가까운 순 max_resistances개
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Literal, Optional

from sajucandle.analysis.swing import SwingPoint
from sajucandle.analysis.volume_profile import VolumeNode, compute_volume_profile
from sajucandle.market_data import Kline


class LevelKind(str, Enum):
    SUPPORT = "support"
    RESISTANCE = "resistance"


@dataclass
class SRLevel:
    price: float
    kind: LevelKind
    strength: Literal["low", "medium", "high"]
    sources: list[str] = field(default_factory=list)


def identify_sr_levels(
    klines_1d: list[Kline],
    swings: list[SwingPoint],
    current_price: float,
    *,
    max_supports: int = 3,
    max_resistances: int = 3,
    merge_tolerance_pct: float = 0.5,
    volume_top_n: int = 5,
    volume_bucket_count: int = 20,
) -> list[SRLevel]:
    if not klines_1d or current_price <= 0:
        return []

    volume_nodes = compute_volume_profile(
        klines_1d, bucket_count=volume_bucket_count, top_n=volume_top_n
    )
    top_volume_sum = volume_nodes[0].volume_sum if volume_nodes else 0.0

    # 후보 수집
    candidates: list[SRLevel] = []

    # swing 후보
    for sp in swings:
        if sp.kind == "high":
            candidates.append(SRLevel(
                price=sp.price, kind=LevelKind.RESISTANCE,
                strength="low", sources=["swing_high"],
            ))
        elif sp.kind == "low":
            candidates.append(SRLevel(
                price=sp.price, kind=LevelKind.SUPPORT,
                strength="low", sources=["swing_low"],
            ))

    # volume node 후보
    for i, node in enumerate(volume_nodes):
        mid = (node.price_low + node.price_high) / 2
        is_top_volume = (node.volume_sum == top_volume_sum)
        kind = LevelKind.RESISTANCE if mid > current_price else LevelKind.SUPPORT
        strength_base: Literal["low", "medium", "high"] = (
            "medium" if is_top_volume else "low"
        )
        candidates.append(SRLevel(
            price=mid, kind=kind,
            strength=strength_base, sources=["volume_node"],
        ))

    # 병합 (같은 kind, merge_tolerance_pct% 이내)
    merged = _merge_levels(candidates, merge_tolerance_pct)

    # strength 재판정 (swing + volume 겹침)
    for level in merged:
        has_swing = any(s.startswith("swing_") for s in level.sources)
        has_volume = "volume_node" in level.sources
        if has_swing and has_volume:
            level.strength = "high"

    # 현재가 기준 필터 + 정렬
    supports = [x for x in merged if x.kind == LevelKind.SUPPORT and x.price < current_price]
    resistances = [x for x in merged if x.kind == LevelKind.RESISTANCE and x.price > current_price]

    # 가까운 순 (support는 price DESC, resistance는 price ASC)
    supports.sort(key=lambda x: current_price - x.price)
    resistances.sort(key=lambda x: x.price - current_price)

    return supports[:max_supports] + resistances[:max_resistances]


def _merge_levels(
    candidates: list[SRLevel], tolerance_pct: float
) -> list[SRLevel]:
    """같은 kind 내 가까운 가격 병합. 가중평균 가격, sources 합집합."""
    if not candidates:
        return []
    by_kind: dict[LevelKind, list[SRLevel]] = {
        LevelKind.SUPPORT: [], LevelKind.RESISTANCE: [],
    }
    for c in candidates:
        by_kind[c.kind].append(c)

    merged: list[SRLevel] = []
    for kind, group in by_kind.items():
        group = sorted(group, key=lambda x: x.price)
        cluster: list[SRLevel] = []

        def _flush(cl: list[SRLevel]):
            if not cl:
                return
            # 가중평균이 아닌 단순 평균 (가중치 소스가 애매)
            avg_price = sum(x.price for x in cl) / len(cl)
            all_sources = []
            max_strength = "low"
            order = {"low": 0, "medium": 1, "high": 2}
            for x in cl:
                for s in x.sources:
                    if s not in all_sources:
                        all_sources.append(s)
                if order[x.strength] > order[max_strength]:
                    max_strength = x.strength
            merged.append(SRLevel(
                price=avg_price, kind=kind,
                strength=max_strength, sources=all_sources,
            ))

        for c in group:
            if not cluster:
                cluster.append(c)
                continue
            last = cluster[-1]
            if abs(c.price - last.price) / max(last.price, 1e-9) * 100 <= tolerance_pct:
                cluster.append(c)
            else:
                _flush(cluster)
                cluster = [c]
        _flush(cluster)

    return merged
```

- [ ] **Step 4: Run — PASS**

```
pytest tests/test_analysis_support_resistance.py -v
```

Expected: 7 passed.

- [ ] **Step 5: Full regression + Commit**

```
pytest -q
git add src/sajucandle/analysis/support_resistance.py tests/test_analysis_support_resistance.py
git commit -m "feat(analysis): add S/R identification (swing + volume fusion)"
```

---

## Task 4: analysis/trade_setup.py (TDD)

**Files:**
- Create: `src/sajucandle/analysis/trade_setup.py`
- Create: `tests/test_analysis_trade_setup.py`

- [ ] **Step 1: Write failing tests**

`D:\사주캔들\tests\test_analysis_trade_setup.py`:

```python
"""analysis.trade_setup: 하이브리드 ATR + S/R snap → SL/TP/R:R/risk_pct."""
from __future__ import annotations

import pytest

from sajucandle.analysis.support_resistance import LevelKind, SRLevel
from sajucandle.analysis.trade_setup import TradeSetup, compute_trade_setup


def _support(price: float, strength: str = "medium") -> SRLevel:
    return SRLevel(price=price, kind=LevelKind.SUPPORT,
                   strength=strength, sources=["swing_low"])  # type: ignore[arg-type]


def _resist(price: float, strength: str = "medium") -> SRLevel:
    return SRLevel(price=price, kind=LevelKind.RESISTANCE,
                   strength=strength, sources=["swing_high"])  # type: ignore[arg-type]


def test_no_sr_uses_pure_atr():
    """S/R 없으면 SL=entry-1.5*ATR, TP1=entry+1.5*ATR, TP2=entry+3*ATR."""
    setup = compute_trade_setup(entry=100.0, atr_1d=2.0, sr_levels=[])
    assert setup.stop_loss == pytest.approx(100.0 - 1.5 * 2.0)
    assert setup.take_profit_1 == pytest.approx(100.0 + 1.5 * 2.0)
    assert setup.take_profit_2 == pytest.approx(100.0 + 3.0 * 2.0)
    assert setup.sl_basis == "atr"
    assert setup.tp1_basis == "atr"
    assert setup.tp2_basis == "atr"


def test_sl_snaps_to_nearby_support():
    """ATR 기본 SL 거리 ±30% 안에 support 있으면 snap."""
    # entry=100, atr=2, 기본 SL = 97. 1.5*2=3이 SL 거리. ±30% = [2.1, 3.9]
    # support 98 (거리 2, 범위 밖), support 97.2 (거리 2.8, 범위 안) → snap
    supports = [_support(97.2)]
    setup = compute_trade_setup(entry=100.0, atr_1d=2.0, sr_levels=supports)
    assert setup.sl_basis == "sr_snap"
    # SL은 지지 밑 0.2*ATR = 97.2 - 0.4 = 96.8
    assert setup.stop_loss == pytest.approx(97.2 - 0.2 * 2.0)


def test_tp1_snaps_to_nearby_resistance():
    """TP1 거리 ±30% 안에 resistance 있으면 snap (저항 약간 전)."""
    # entry=100, atr=2, 기본 TP1=103, 범위 [102.1, 103.9]
    # resistance 103.5 (범위 안) → snap, TP1 = 103.5 - 0.2*2 = 103.1
    resists = [_resist(103.5)]
    setup = compute_trade_setup(entry=100.0, atr_1d=2.0, sr_levels=resists)
    assert setup.tp1_basis == "sr_snap"
    assert setup.take_profit_1 == pytest.approx(103.5 - 0.2 * 2.0)


def test_tp2_wider_tolerance_5050():
    """TP2는 ±50% tolerance (멀리 있는 저항 포함)."""
    # entry=100, atr=2, TP2 기본=106, 범위 ±50% = [103, 109]
    # resistance 107 → snap TP2
    resists = [_resist(107.0)]
    setup = compute_trade_setup(entry=100.0, atr_1d=2.0, sr_levels=resists)
    # TP1=103 기본 (103.0~)... TP2 snap
    assert setup.take_profit_2 == pytest.approx(107.0 - 0.2 * 2.0)
    assert setup.tp2_basis == "sr_snap"


def test_risk_pct_computation():
    """risk_pct = (entry - sl) / entry * 100."""
    setup = compute_trade_setup(entry=100.0, atr_1d=2.0, sr_levels=[])
    # SL = 97, risk = 3/100 = 3%
    assert setup.risk_pct == pytest.approx(3.0)


def test_rr_computation():
    """rr_tp1 = (tp1 - entry) / (entry - sl)."""
    setup = compute_trade_setup(entry=100.0, atr_1d=2.0, sr_levels=[])
    # SL=97, TP1=103, RR=3/3=1.0
    assert setup.rr_tp1 == pytest.approx(1.0)
    # TP2=106, RR=6/3=2.0
    assert setup.rr_tp2 == pytest.approx(2.0)


def test_strongest_support_wins_when_multiple_in_range():
    """범위 안에 여러 지지 있으면 strength 높은 게 우선."""
    supports = [_support(97.2, "low"), _support(97.4, "high")]
    setup = compute_trade_setup(entry=100.0, atr_1d=2.0, sr_levels=supports)
    assert setup.sl_basis == "sr_snap"
    # strength=high인 97.4로 snap
    assert setup.stop_loss == pytest.approx(97.4 - 0.2 * 2.0)


def test_trade_setup_is_dataclass():
    from dataclasses import is_dataclass
    assert is_dataclass(TradeSetup)
```

- [ ] **Step 2: Run — fail**

```
pytest tests/test_analysis_trade_setup.py -v
```

Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement**

`D:\사주캔들\src\sajucandle\analysis\trade_setup.py`:

```python
"""하이브리드 ATR + S/R snap SL·TP 산출.

기본: entry ± N * ATR.
S/R 있고 기본 거리 근방(±tolerance)에 있으면 snap.
  - SL → support 밑 _SR_BUFFER_ATR*ATR 만큼 여유
  - TP → resistance 밑 _SR_BUFFER_ATR*ATR 만큼 앞서 익절 (보수적)

튜닝 상수는 module-level, Week 11 백테스트 후 조정.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

from sajucandle.analysis.support_resistance import LevelKind, SRLevel


_SL_ATR_MULT = 1.5
_TP1_ATR_MULT = 1.5
_TP2_ATR_MULT = 3.0
_SNAP_TOLERANCE = 0.3        # ATR 배수의 ±30%
_SNAP_TOLERANCE_TP2 = 0.5    # TP2는 ±50%
_SR_BUFFER_ATR = 0.2


@dataclass
class TradeSetup:
    entry: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: float
    risk_pct: float
    rr_tp1: float
    rr_tp2: float
    sl_basis: Literal["atr", "sr_snap"]
    tp1_basis: Literal["atr", "sr_snap"]
    tp2_basis: Literal["atr", "sr_snap"]


_STRENGTH_ORDER = {"low": 0, "medium": 1, "high": 2}


def _best_level_in_range(
    candidates: list[SRLevel],
    price_min: float,
    price_max: float,
) -> Optional[SRLevel]:
    """범위 안에서 strength 최고 레벨 반환 (동점이면 price 기준 중간값)."""
    hits = [c for c in candidates if price_min <= c.price <= price_max]
    if not hits:
        return None
    hits.sort(key=lambda c: _STRENGTH_ORDER[c.strength], reverse=True)
    return hits[0]


def compute_trade_setup(
    entry: float,
    atr_1d: float,
    sr_levels: list[SRLevel],
) -> TradeSetup:
    if atr_1d <= 0:
        # degenerate: SL/TP 기본값 entry 기준 1% 거리로 fallback
        atr_1d = entry * 0.01

    supports = [x for x in sr_levels if x.kind == LevelKind.SUPPORT]
    resists = [x for x in sr_levels if x.kind == LevelKind.RESISTANCE]

    # SL
    sl_base = entry - _SL_ATR_MULT * atr_1d
    sl_min = entry - (_SL_ATR_MULT + _SNAP_TOLERANCE) * atr_1d
    sl_max = entry - (_SL_ATR_MULT - _SNAP_TOLERANCE) * atr_1d
    sl_best = _best_level_in_range(supports, sl_min, sl_max)
    if sl_best is not None:
        stop_loss = sl_best.price - _SR_BUFFER_ATR * atr_1d
        sl_basis: Literal["atr", "sr_snap"] = "sr_snap"
    else:
        stop_loss = sl_base
        sl_basis = "atr"

    # TP1
    tp1_base = entry + _TP1_ATR_MULT * atr_1d
    tp1_min = entry + (_TP1_ATR_MULT - _SNAP_TOLERANCE) * atr_1d
    tp1_max = entry + (_TP1_ATR_MULT + _SNAP_TOLERANCE) * atr_1d
    tp1_best = _best_level_in_range(resists, tp1_min, tp1_max)
    if tp1_best is not None:
        take_profit_1 = tp1_best.price - _SR_BUFFER_ATR * atr_1d
        tp1_basis: Literal["atr", "sr_snap"] = "sr_snap"
    else:
        take_profit_1 = tp1_base
        tp1_basis = "atr"

    # TP2 (wider tolerance)
    tp2_base = entry + _TP2_ATR_MULT * atr_1d
    tp2_min = entry + (_TP2_ATR_MULT - _SNAP_TOLERANCE_TP2) * atr_1d
    tp2_max = entry + (_TP2_ATR_MULT + _SNAP_TOLERANCE_TP2) * atr_1d
    tp2_best = _best_level_in_range(resists, tp2_min, tp2_max)
    if tp2_best is not None:
        take_profit_2 = tp2_best.price - _SR_BUFFER_ATR * atr_1d
        tp2_basis: Literal["atr", "sr_snap"] = "sr_snap"
    else:
        take_profit_2 = tp2_base
        tp2_basis = "atr"

    risk = entry - stop_loss
    risk_pct = (risk / entry * 100) if entry > 0 else 0.0
    rr_tp1 = ((take_profit_1 - entry) / risk) if risk > 0 else 0.0
    rr_tp2 = ((take_profit_2 - entry) / risk) if risk > 0 else 0.0

    return TradeSetup(
        entry=entry,
        stop_loss=stop_loss,
        take_profit_1=take_profit_1,
        take_profit_2=take_profit_2,
        risk_pct=risk_pct,
        rr_tp1=rr_tp1,
        rr_tp2=rr_tp2,
        sl_basis=sl_basis,
        tp1_basis=tp1_basis,
        tp2_basis=tp2_basis,
    )
```

- [ ] **Step 4: Run — PASS**

```
pytest tests/test_analysis_trade_setup.py -v
```

Expected: 8 passed.

- [ ] **Step 5: Full regression + Commit**

```
pytest -q
git add src/sajucandle/analysis/trade_setup.py tests/test_analysis_trade_setup.py
git commit -m "feat(analysis): add trade setup (hybrid ATR + S/R snap)"
```

---

## Task 5: composite.py — AnalysisResult sr_levels + atr_1d

**Files:**
- Modify: `src/sajucandle/analysis/composite.py`
- Modify: `tests/test_analysis_composite.py`

- [ ] **Step 1: Write failing tests**

`tests/test_analysis_composite.py` 맨 아래에 추가:

```python
# ─────────────────────────────────────────────
# Week 9: sr_levels + atr_1d 필드
# ─────────────────────────────────────────────


def test_analyze_returns_sr_levels_and_atr():
    from datetime import datetime, timezone
    from sajucandle.analysis.composite import analyze
    from sajucandle.market_data import Kline

    # 단조증가 데이터: swing 안 잡히는 edge case라도 atr_1d는 계산돼야
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    up = [
        Kline(
            open_time=base.replace(day=(i % 28) + 1),
            open=100 + i * 0.3,
            high=100 + i * 0.3 + 0.5,
            low=100 + i * 0.3 - 0.5,
            close=100 + i * 0.3,
            volume=1000.0,
        )
        for i in range(100)
    ]
    r = analyze(up, up, up)
    # sr_levels 필드 존재
    assert hasattr(r, "sr_levels")
    assert isinstance(r.sr_levels, list)
    # atr_1d 필드 존재
    assert hasattr(r, "atr_1d")
    assert r.atr_1d > 0
```

- [ ] **Step 2: Run — fail**

```
pytest tests/test_analysis_composite.py -v -k "sr_levels_and_atr"
```

Expected: `AttributeError: 'AnalysisResult' object has no attribute 'sr_levels'`.

- [ ] **Step 3: Modify composite.py**

`D:\사주캔들\src\sajucandle\analysis\composite.py`:

**(a) imports 추가:**
```python
from sajucandle.analysis.support_resistance import SRLevel, identify_sr_levels
from sajucandle.analysis.swing import _atr
```

**(b) AnalysisResult dataclass 확장:**

```python
@dataclass
class AnalysisResult:
    structure: StructureAnalysis
    alignment: Alignment
    rsi_1h: float
    volume_ratio_1d: float
    composite_score: int
    reason: str
    # Week 9
    sr_levels: list[SRLevel] = field(default_factory=list)
    atr_1d: float = 0.0
```

`from dataclasses import dataclass, field` 확인.

**(c) analyze() 함수 끝부분에 sr_levels/atr_1d 계산 + AnalysisResult에 주입:**

기존 `return AnalysisResult(structure=..., ..., reason=reason)` 직전에:

```python
    # Week 9: S/R + ATR(1d)
    current = klines_1d[-1].close if klines_1d else 0.0
    sr_levels = (
        identify_sr_levels(klines_1d, swings, current)
        if klines_1d and current > 0
        else []
    )
    atr_1d_value = _atr(klines_1d, 14) if len(klines_1d) >= 15 else 0.0

    return AnalysisResult(
        structure=structure,
        alignment=alignment,
        rsi_1h=rsi_1h,
        volume_ratio_1d=vr_1d,
        composite_score=composite,
        reason=reason,
        sr_levels=sr_levels,
        atr_1d=atr_1d_value,
    )
```

**주의:** `_atr`는 `swing.py`에 있는 private 함수지만 같은 패키지 내 재사용. import 시 `# noqa` 불필요.

- [ ] **Step 4: Run — PASS**

```
pytest tests/test_analysis_composite.py -v
```

Expected: 기존 + 신규 1개 passed.

- [ ] **Step 5: Full regression + Commit**

```
pytest -q
git add src/sajucandle/analysis/composite.py tests/test_analysis_composite.py
git commit -m "feat(analysis): composite populates sr_levels + atr_1d"
```

---

## Task 6: models.py — SRLevel + TradeSetup Pydantic (TDD via Task 7)

**Files:**
- Modify: `src/sajucandle/models.py`

Task 7 signal_service에서 sr_levels/trade_setup 필드 사용하므로 Pydantic 모델 먼저 추가.

- [ ] **Step 1: Add Pydantic models**

`D:\사주캔들\src\sajucandle\models.py`의 `AnalysisSummary` 정의 **직전**에 새 모델 추가, 그리고 `AnalysisSummary`에 2개 필드 추가:

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
    """Week 8: 시장 구조 + 멀티 TF + 보조지표 요약."""
    structure: StructureSummary
    alignment: AlignmentSummary
    rsi_1h: float
    volume_ratio_1d: float
    composite_score: int = Field(ge=0, le=100)
    reason: str
    # Week 9
    sr_levels: List[SRLevelSummary] = Field(default_factory=list)
    trade_setup: Optional[TradeSetupSummary] = None
```

- [ ] **Step 2: Verify import**

```
python -c "from sajucandle.models import SRLevelSummary, TradeSetupSummary, AnalysisSummary; print('ok')"
```

Expected: `ok`.

- [ ] **Step 3: Full regression + Commit**

```
pytest -q
git add src/sajucandle/models.py
git commit -m "feat(models): add SRLevelSummary + TradeSetupSummary"
```

Expected: 회귀 0 (Optional/default이라 비파괴).

---

## Task 7: signal_service.py — TradeSetup 조건부 생성 (TDD, 큰 태스크)

**Files:**
- Modify: `src/sajucandle/signal_service.py`
- Modify: `tests/test_signal_service.py`

- [ ] **Step 1: Write failing tests**

`tests/test_signal_service.py` 맨 아래에 추가:

```python
# ─────────────────────────────────────────────
# Week 9: TradeSetup 조건부 생성
# ─────────────────────────────────────────────


def test_week9_trade_setup_on_entry_grade():
    """'진입' 등급일 때 trade_setup 필드 채워짐."""
    fake = _make_fake_market_client()
    # 강한 상승 + 정렬 데이터로 "진입" 달성
    strong = _make_klines(n=200, base_close=100.0, drift=0.5)
    fake.klines_by_interval = {"1h": strong, "4h": strong, "1d": strong}
    score_svc = _make_score_service()
    svc = SignalService(
        score_service=score_svc,
        market_router=_make_router(fake),
    )
    resp = svc.compute(_profile(), date(2026, 4, 16), "BTCUSDT")
    if resp.signal_grade in ("강진입", "진입"):
        assert resp.analysis is not None
        # trade_setup 필드 존재 확인
        assert resp.analysis.trade_setup is not None
        assert resp.analysis.trade_setup.entry > 0
        assert resp.analysis.trade_setup.stop_loss < resp.analysis.trade_setup.entry
        assert resp.analysis.trade_setup.take_profit_1 > resp.analysis.trade_setup.entry
        assert resp.analysis.trade_setup.risk_pct > 0


def test_week9_trade_setup_none_on_gwanmang_grade():
    """'관망' 등급에서는 trade_setup=None."""
    fake = _make_fake_market_client()
    # 횡보 데이터로 "관망" 또는 "회피" 유도
    flat = _make_klines(n=200, base_close=100.0, drift=0.0)
    fake.klines_by_interval = {"1h": flat, "4h": flat, "1d": flat}
    # 사주 낮게 → composite 낮게
    score_svc = _make_score_service_with_fixed_composite(30)
    svc = SignalService(
        score_service=score_svc,
        market_router=_make_router(fake),
    )
    resp = svc.compute(_profile(), date(2026, 4, 16), "BTCUSDT")
    if resp.signal_grade in ("관망", "회피"):
        assert resp.analysis is not None
        assert resp.analysis.trade_setup is None


def test_week9_sr_levels_always_populated_in_response():
    """sr_levels는 등급 상관없이 analysis에 있어야 (빈 리스트 가능)."""
    fake = _make_fake_market_client()
    score_svc = _make_score_service()
    svc = SignalService(
        score_service=score_svc,
        market_router=_make_router(fake),
    )
    resp = svc.compute(_profile(), date(2026, 4, 16), "BTCUSDT")
    assert resp.analysis is not None
    assert hasattr(resp.analysis, "sr_levels")
    assert isinstance(resp.analysis.sr_levels, list)
```

- [ ] **Step 2: Run — fail**

```
pytest tests/test_signal_service.py -v -k "week9"
```

Expected: `trade_setup` 필드 또는 관련 로직 없어서 FAIL.

- [ ] **Step 3: Modify signal_service.py**

`D:\사주캔들\src\sajucandle\signal_service.py`:

**(a) imports 추가:**

```python
from sajucandle.analysis.trade_setup import TradeSetup, compute_trade_setup
from sajucandle.models import (
    # 기존 ...
    SRLevelSummary,
    TradeSetupSummary,
)
```

**(b) `_analysis_to_summary` 시그니처 변경 — `trade_setup` 파라미터 추가:**

기존:
```python
def _analysis_to_summary(a: AnalysisResult) -> AnalysisSummary:
    return AnalysisSummary(
        structure=StructureSummary(...),
        alignment=AlignmentSummary(...),
        rsi_1h=a.rsi_1h,
        volume_ratio_1d=a.volume_ratio_1d,
        composite_score=a.composite_score,
        reason=a.reason,
    )
```

교체:
```python
def _analysis_to_summary(
    a: AnalysisResult,
    trade_setup: Optional[TradeSetup] = None,
) -> AnalysisSummary:
    sr_summaries = [
        SRLevelSummary(
            price=lvl.price,
            kind=lvl.kind.value,
            strength=lvl.strength,
        )
        for lvl in a.sr_levels
    ]
    ts_summary = None
    if trade_setup is not None:
        ts_summary = TradeSetupSummary(
            entry=trade_setup.entry,
            stop_loss=trade_setup.stop_loss,
            take_profit_1=trade_setup.take_profit_1,
            take_profit_2=trade_setup.take_profit_2,
            risk_pct=trade_setup.risk_pct,
            rr_tp1=trade_setup.rr_tp1,
            rr_tp2=trade_setup.rr_tp2,
        )
    return AnalysisSummary(
        structure=StructureSummary(
            state=a.structure.state.value,
            score=a.structure.score,
        ),
        alignment=AlignmentSummary(
            tf_1h=a.alignment.tf_1h.value,
            tf_4h=a.alignment.tf_4h.value,
            tf_1d=a.alignment.tf_1d.value,
            aligned=a.alignment.aligned,
            bias=a.alignment.bias,
            score=a.alignment.score,
        ),
        rsi_1h=a.rsi_1h,
        volume_ratio_1d=a.volume_ratio_1d,
        composite_score=a.composite_score,
        reason=a.reason,
        sr_levels=sr_summaries,
        trade_setup=ts_summary,
    )
```

**(c) `SignalService.compute()` 내부 — 등급 결정 후 trade_setup 조건부 계산:**

기존 `grade = _grade_signal(final, analysis)` 직후:

```python
        # Week 9: TradeSetup 조건부 생성
        trade_setup: Optional[TradeSetup] = None
        if grade in ("강진입", "진입") and analysis.atr_1d > 0:
            trade_setup = compute_trade_setup(
                entry=current,
                atr_1d=analysis.atr_1d,
                sr_levels=analysis.sr_levels,
            )

        analysis_summary = _analysis_to_summary(analysis, trade_setup)
```

기존 `analysis_summary = _analysis_to_summary(analysis)` 호출을 위 `_analysis_to_summary(analysis, trade_setup)`로 교체.

`Optional` 임포트 확인.

- [ ] **Step 4: Run — PASS**

```
pytest tests/test_signal_service.py -v -k "week9"
```

Expected: 3 passed.

- [ ] **Step 5: Full regression**

```
pytest -q
```

Expected: 회귀 0.

- [ ] **Step 6: Commit**

```
git add src/sajucandle/signal_service.py tests/test_signal_service.py
git commit -m "feat(signal): conditional TradeSetup for 진입/강진입 grades"
```

---

## Task 8: repositories.py — insert_signal_log SL/TP 필드 10개

**Files:**
- Modify: `src/sajucandle/repositories.py`
- Modify: `tests/test_repositories.py`

- [ ] **Step 1: Write failing tests**

`tests/test_repositories.py` 맨 아래에 추가:

```python
# ─────────────────────────────────────────────
# Week 9: insert_signal_log SL/TP 필드
# ─────────────────────────────────────────────


async def test_insert_signal_log_with_trade_setup(db_conn):
    await _register_user(db_conn, 300001)
    row_id = await insert_signal_log(
        db_conn,
        source="ondemand",
        telegram_chat_id=300001,
        ticker="BTCUSDT",
        target_date=date(2026, 4, 19),
        entry_price=72000.0,
        saju_score=56,
        analysis_score=72,
        structure_state="uptrend",
        alignment_bias="bullish",
        rsi_1h=60.0,
        volume_ratio_1d=1.2,
        composite_score=70,
        signal_grade="진입",
        # Week 9
        stop_loss=70000.0,
        take_profit_1=74000.0,
        take_profit_2=76000.0,
        risk_pct=2.78,
        rr_tp1=1.0,
        rr_tp2=2.0,
        sl_basis="atr",
        tp1_basis="sr_snap",
        tp2_basis="atr",
    )
    row = await db_conn.fetchrow(
        "SELECT stop_loss, take_profit_1, take_profit_2, risk_pct, "
        "rr_tp1, rr_tp2, sl_basis, tp1_basis, tp2_basis "
        "FROM signal_log WHERE id = $1", row_id
    )
    assert float(row["stop_loss"]) == 70000.0
    assert float(row["take_profit_1"]) == 74000.0
    assert float(row["take_profit_2"]) == 76000.0
    assert float(row["rr_tp1"]) == 1.0
    assert row["sl_basis"] == "atr"
    assert row["tp1_basis"] == "sr_snap"


async def test_insert_signal_log_without_trade_setup_nulls(db_conn):
    """SL/TP 미제공 시 NULL 저장 (기존 insert 호출 호환)."""
    await _register_user(db_conn, 300002)
    row_id = await insert_signal_log(
        db_conn,
        source="ondemand",
        telegram_chat_id=300002,
        ticker="BTCUSDT",
        target_date=date(2026, 4, 19),
        entry_price=72000.0,
        saju_score=56,
        analysis_score=50,
        structure_state="range",
        alignment_bias="mixed",
        rsi_1h=None,
        volume_ratio_1d=None,
        composite_score=50,
        signal_grade="관망",
    )
    row = await db_conn.fetchrow(
        "SELECT stop_loss, risk_pct, sl_basis FROM signal_log WHERE id = $1",
        row_id
    )
    assert row["stop_loss"] is None
    assert row["risk_pct"] is None
    assert row["sl_basis"] is None
```

- [ ] **Step 2: Run — fail**

```
pytest tests/test_repositories.py -v -k "with_trade_setup or without_trade_setup_nulls"
```

Expected: `TypeError: insert_signal_log() got an unexpected keyword argument 'stop_loss'` 또는 skip(TEST_DATABASE_URL 없음).

- [ ] **Step 3: Modify insert_signal_log**

`D:\사주캔들\src\sajucandle\repositories.py`의 `insert_signal_log` 함수 수정.

기존 파라미터 + 신규 10개 Optional:

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
            sl_basis, tp1_basis, tp2_basis
        ) VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13,
            $14, $15, $16, $17, $18, $19, $20, $21, $22
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
    )
    return int(row["id"])
```

- [ ] **Step 4: Run — PASS (or skipped)**

```
pytest tests/test_repositories.py -v -k "with_trade_setup or without_trade_setup_nulls"
```

Expected (TEST_DATABASE_URL 있음): 2 passed. 없음: 2 skipped + collection 성공.

- [ ] **Step 5: Full regression + Commit**

```
pytest -q
git add src/sajucandle/repositories.py tests/test_repositories.py
git commit -m "feat(repo): extend insert_signal_log with SL/TP/RR/basis fields"
```

---

## Task 9: api.py — signal_endpoint에 SL/TP insert + admin ohlcv 엔드포인트

**Files:**
- Modify: `src/sajucandle/api.py`
- Modify: `tests/test_api_signal.py`
- Create: `tests/test_api_ohlcv.py`

두 가지 변경 한 커밋:
1. 기존 `signal_endpoint`의 `insert_signal_log` 호출에 trade_setup 필드 확장
2. 새 `admin_ohlcv_endpoint` 추가

- [ ] **Step 1: Write failing tests for ohlcv endpoint**

`D:\사주캔들\tests\test_api_ohlcv.py`:

```python
"""api: /v1/admin/ohlcv 엔드포인트."""
from __future__ import annotations

import os
from unittest.mock import patch, MagicMock

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from sajucandle.api import create_app


@pytest.fixture
def api_key(monkeypatch):
    monkeypatch.setenv("SAJUCANDLE_API_KEY", "test-key")
    return "test-key"


@pytest.fixture
def client(api_key, monkeypatch):
    # DATABASE_URL 없어도 엔드포인트 자체는 동작 (DB 안 씀)
    app = create_app()
    with TestClient(app) as c:
        yield c


HEADERS = {"X-SAJUCANDLE-KEY": "test-key"}


def test_ohlcv_requires_api_key(client):
    r = client.get("/v1/admin/ohlcv", params={"ticker": "BTCUSDT"})
    assert r.status_code == 401


def test_ohlcv_rejects_unsupported_ticker(client):
    r = client.get(
        "/v1/admin/ohlcv",
        params={"ticker": "AMZN"},
        headers=HEADERS,
    )
    assert r.status_code == 400
    assert "unsupported ticker" in r.json()["detail"].lower()


def test_ohlcv_rejects_unsupported_interval(client):
    r = client.get(
        "/v1/admin/ohlcv",
        params={"ticker": "BTCUSDT", "interval": "15m"},
        headers=HEADERS,
    )
    assert r.status_code == 400


def test_ohlcv_rejects_bad_limit(client):
    r = client.get(
        "/v1/admin/ohlcv",
        params={"ticker": "BTCUSDT", "limit": "9999"},
        headers=HEADERS,
    )
    assert r.status_code == 400


def test_ohlcv_rejects_bad_since(client):
    r = client.get(
        "/v1/admin/ohlcv",
        params={"ticker": "BTCUSDT", "since": "not-a-date"},
        headers=HEADERS,
    )
    assert r.status_code == 400


def test_ohlcv_returns_klines_for_aapl(client, monkeypatch):
    """yfinance mock 통해 AAPL 5봉 반환."""
    idx = pd.date_range(end="2026-04-19", periods=5, freq="1h",
                        tz="America/New_York")
    df = pd.DataFrame({
        "Open": [180.0] * 5,
        "High": [181.0] * 5,
        "Low": [179.0] * 5,
        "Close": [180.5] * 5,
        "Volume": [1_000_000] * 5,
    }, index=idx)
    fake_ticker = MagicMock()
    fake_ticker.history.return_value = df

    with patch("sajucandle.market.yfinance.yf.Ticker", return_value=fake_ticker):
        r = client.get(
            "/v1/admin/ohlcv",
            params={"ticker": "AAPL", "interval": "1h", "limit": "5"},
            headers=HEADERS,
        )
    assert r.status_code == 200
    body = r.json()
    assert body["ticker"] == "AAPL"
    assert body["interval"] == "1h"
    assert len(body["klines"]) == 5


def test_ohlcv_since_filter(client, monkeypatch):
    """since=... 이후 bar만."""
    import pandas as pd
    from datetime import datetime, timezone, timedelta
    # 10봉 중 5봉은 "since"보다 이전
    base = datetime(2026, 4, 19, 12, 0, tzinfo=timezone.utc)
    idx = pd.date_range(end=base, periods=10, freq="1h", tz="UTC")
    df = pd.DataFrame({
        "Open": [100.0] * 10, "High": [101.0] * 10,
        "Low": [99.0] * 10, "Close": [100.5] * 10,
        "Volume": [1000] * 10,
    }, index=idx)
    fake_ticker = MagicMock()
    fake_ticker.history.return_value = df

    # since: base - 4h → 5봉만 반환
    since = (base - timedelta(hours=4)).isoformat()
    with patch("sajucandle.market.yfinance.yf.Ticker", return_value=fake_ticker):
        r = client.get(
            "/v1/admin/ohlcv",
            params={"ticker": "AAPL", "interval": "1h",
                    "since": since, "limit": "20"},
            headers=HEADERS,
        )
    assert r.status_code == 200
    body = r.json()
    assert len(body["klines"]) <= 5
```

- [ ] **Step 2: Run — fail**

```
pytest tests/test_api_ohlcv.py -v
```

Expected: 404 (엔드포인트 없음).

- [ ] **Step 3: Modify api.py**

`D:\사주캔들\src\sajucandle\api.py`:

**(a) `create_app` 내부, `/v1/signal/symbols` 엔드포인트 직후에 admin_ohlcv 엔드포인트 추가:**

```python
    @app.get("/v1/admin/ohlcv")
    async def admin_ohlcv_endpoint(
        request: Request,
        ticker: str,
        interval: str = "1h",
        since: Optional[str] = None,
        limit: int = 168,
        x_sajucandle_key: Optional[str] = Header(default=None),
    ):
        """Week 9: Phase 0 tracking용 OHLCV 조회."""
        _require_api_key(request, x_sajucandle_key)
        if interval not in ("1h", "4h", "1d"):
            raise HTTPException(400, detail=f"unsupported interval: {interval}")
        if limit <= 0 or limit > 500:
            raise HTTPException(400, detail="limit must be 1..500")

        since_dt = None
        if since:
            try:
                since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
            except ValueError:
                raise HTTPException(400, detail="since must be ISO 8601")

        ticker_norm = ticker.upper().lstrip("$")
        try:
            provider = signal_service._router.get_provider(ticker_norm)
        except UnsupportedTicker as e:
            raise HTTPException(400, detail=f"unsupported ticker: {e.symbol}")

        try:
            klines = provider.fetch_klines(
                ticker_norm, interval=interval, limit=limit
            )
        except MarketDataUnavailable:
            raise HTTPException(502, detail="market data unavailable")

        if since_dt is not None:
            klines = [k for k in klines if k.open_time >= since_dt]

        logger.info(
            "admin ohlcv ticker=%s interval=%s count=%s since=%s",
            ticker_norm, interval, len(klines), since,
        )
        return {
            "ticker": ticker_norm,
            "interval": interval,
            "klines": [k.to_dict() for k in klines],
        }
```

**주의:** `signal_service._router`는 sub-instance로 접근하는 private. 깔끔한 대안은 `market_router`를 `create_app` 내부 지역변수로 꺼내는 것. 구현 시 깔끔한 쪽 선택.

**대안 (더 깔끔):** `create_app` 내에서 market_router를 한 번 만들어 signal_service + admin_ohlcv 둘 다 재사용:

```python
def create_app(...):
    # ... 기존 코드 ...
    
    # Week 9: market_router를 외부로 꺼내서 재사용
    def _build_market_router() -> MarketRouter:
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
        return MarketRouter(binance=binance, yfinance=yfinance_client)
    
    market_router = _build_market_router()
    
    def _build_signal_service() -> SignalService:
        # 위에서 만든 market_router 재사용
        redis_client = None   # 필요 시 별도
        return SignalService(
            score_service=score_service,
            market_router=market_router,
            redis_client=redis_client,
        )
```

`admin_ohlcv_endpoint`는 `market_router`를 사용 (클로저 캡처).

**(b) `signal_endpoint`의 insert_signal_log 호출에 trade_setup 필드 추가:**

기존 insert 호출:
```python
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
```

교체 (trade_setup 있을 때만 채움):
```python
ts = result.analysis.trade_setup if result.analysis else None
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
    # Week 9
    stop_loss=ts.stop_loss if ts else None,
    take_profit_1=ts.take_profit_1 if ts else None,
    take_profit_2=ts.take_profit_2 if ts else None,
    risk_pct=ts.risk_pct if ts else None,
    rr_tp1=ts.rr_tp1 if ts else None,
    rr_tp2=ts.rr_tp2 if ts else None,
    sl_basis=None,   # Week 8 Pydantic TradeSetupSummary에는 basis 없음, Week 10에 노출 고려
    tp1_basis=None,
    tp2_basis=None,
)
```

**주의:** `TradeSetupSummary`에는 `sl_basis` 등이 없다(스펙 §4.7 — basis는 내부만). DB에는 저장하되 API 응답엔 노출 안 함. 현재 스펙 구조에서는 signal_endpoint가 `result.analysis.trade_setup`으로 Pydantic 필드만 접근 가능 → basis 정보 못 얻음.

**해결:** Task 7의 signal_service에서 `_analysis_to_summary(analysis, trade_setup)` 호출 시, 그 위 스코프에서 `trade_setup` (원본 dataclass)을 보관해 `signal_endpoint`에 전달하는 경로 만들기 어려움. **간단 대안:** Task 6에서 `TradeSetupSummary`에 3개 basis 필드 추가해 API 응답에도 노출 → signal_endpoint가 그걸 DB에 저장.

**Task 6 보강 (여기서 반영):** `TradeSetupSummary`에 basis 3개 Literal 필드 추가.

본 Task 9에서 Task 6을 재열어 수정할 필요 — 세부는 아래 Step 5에서.

- [ ] **Step 4: Write failing test for trade_setup fields in response**

`tests/test_api_signal.py` 맨 아래에 추가:

```python
def test_signal_response_has_trade_setup_on_entry_grade(
    client, stub_yfinance, db_registered_user,
):
    """'진입' 이상 등급일 때 analysis.trade_setup 필드 있음."""
    resp = client.get(
        f"/v1/users/{db_registered_user}/signal",
        params={"ticker": "AAPL"},
        headers={"X-SAJUCANDLE-KEY": "test-key"},
    )
    assert resp.status_code == 200
    body = resp.json()
    grade = body["signal_grade"]
    ts = body["analysis"].get("trade_setup")
    if grade in ("강진입", "진입"):
        assert ts is not None
        assert ts["entry"] > 0
        assert ts["stop_loss"] < ts["entry"]
        assert ts["take_profit_1"] > ts["entry"]
    else:
        assert ts is None
```

- [ ] **Step 5: Modify Task 6 Pydantic — TradeSetupSummary에 basis 필드 추가**

`D:\사주캔들\src\sajucandle\models.py`:

```python
class TradeSetupSummary(BaseModel):
    entry: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: float
    risk_pct: float
    rr_tp1: float
    rr_tp2: float
    sl_basis: Literal["atr", "sr_snap"]
    tp1_basis: Literal["atr", "sr_snap"]
    tp2_basis: Literal["atr", "sr_snap"]
```

그리고 `signal_service._analysis_to_summary`에서 basis 필드 채우기:

```python
    ts_summary = None
    if trade_setup is not None:
        ts_summary = TradeSetupSummary(
            entry=trade_setup.entry,
            stop_loss=trade_setup.stop_loss,
            take_profit_1=trade_setup.take_profit_1,
            take_profit_2=trade_setup.take_profit_2,
            risk_pct=trade_setup.risk_pct,
            rr_tp1=trade_setup.rr_tp1,
            rr_tp2=trade_setup.rr_tp2,
            sl_basis=trade_setup.sl_basis,
            tp1_basis=trade_setup.tp1_basis,
            tp2_basis=trade_setup.tp2_basis,
        )
```

그리고 api.py signal_endpoint의 insert 호출:

```python
    sl_basis=ts.sl_basis if ts else None,
    tp1_basis=ts.tp1_basis if ts else None,
    tp2_basis=ts.tp2_basis if ts else None,
```

- [ ] **Step 6: Run tests — PASS**

```
pytest tests/test_api_ohlcv.py tests/test_api_signal.py tests/test_signal_service.py -v
```

Expected: 전량 통과.

- [ ] **Step 7: Full regression + Commit**

```
pytest -q
git add src/sajucandle/api.py src/sajucandle/models.py src/sajucandle/signal_service.py tests/test_api_ohlcv.py tests/test_api_signal.py
git commit -m "feat(api): GET /v1/admin/ohlcv + log SL/TP to signal_log"
```

---

## Task 10: api_client.py — get_admin_ohlcv (TDD)

**Files:**
- Modify: `src/sajucandle/api_client.py`
- Modify: `tests/test_api_client.py`

- [ ] **Step 1: Write failing tests**

`tests/test_api_client.py` 맨 아래에 추가:

```python
# ─────────────────────────────────────────────
# Week 9: get_admin_ohlcv
# ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_admin_ohlcv_returns_klines():
    import respx
    from httpx import Response
    from sajucandle.api_client import ApiClient

    with respx.mock(base_url="http://test") as mock:
        mock.get("/v1/admin/ohlcv").mock(
            return_value=Response(
                200,
                json={
                    "ticker": "BTCUSDT",
                    "interval": "1h",
                    "klines": [
                        {"open_time": "2026-04-19T10:00:00+00:00",
                         "open": 70000, "high": 70500, "low": 69800,
                         "close": 70200, "volume": 100},
                        {"open_time": "2026-04-19T11:00:00+00:00",
                         "open": 70200, "high": 70800, "low": 70100,
                         "close": 70700, "volume": 120},
                    ],
                },
            )
        )
        c = ApiClient(base_url="http://test", api_key="k")
        klines = await c.get_admin_ohlcv("BTCUSDT")
    assert len(klines) == 2
    assert klines[0]["open_time"] == "2026-04-19T10:00:00+00:00"


@pytest.mark.asyncio
async def test_get_admin_ohlcv_with_since_and_limit():
    import respx
    from httpx import Response
    from sajucandle.api_client import ApiClient

    with respx.mock(base_url="http://test") as mock:
        route = mock.get("/v1/admin/ohlcv").mock(
            return_value=Response(200, json={"ticker": "AAPL",
                                              "interval": "4h",
                                              "klines": []})
        )
        c = ApiClient(base_url="http://test", api_key="k")
        await c.get_admin_ohlcv(
            "AAPL", interval="4h",
            since="2026-04-19T10:00:00+00:00",
            limit=50,
        )
    # 요청 URL에 since/limit이 들어갔는지 검증
    req = route.calls.last.request
    assert "since=" in str(req.url)
    assert "limit=50" in str(req.url)
    assert "interval=4h" in str(req.url)


@pytest.mark.asyncio
async def test_get_admin_ohlcv_401_raises():
    import respx
    from httpx import Response
    from sajucandle.api_client import ApiClient, ApiError

    with respx.mock(base_url="http://test") as mock:
        mock.get("/v1/admin/ohlcv").mock(
            return_value=Response(401, json={"detail": "invalid key"})
        )
        c = ApiClient(base_url="http://test", api_key="wrong")
        with pytest.raises(ApiError) as exc:
            await c.get_admin_ohlcv("BTCUSDT")
    assert exc.value.status == 401
```

- [ ] **Step 2: Run — fail**

```
pytest tests/test_api_client.py -v -k "admin_ohlcv"
```

Expected: AttributeError.

- [ ] **Step 3: Implement**

`D:\사주캔들\src\sajucandle\api_client.py`의 `ApiClient` 클래스 마지막(`get_admin_watchlist_symbols` 다음)에 추가:

```python
    async def get_admin_ohlcv(
        self,
        ticker: str,
        *,
        interval: str = "1h",
        since: Optional[str] = None,
        limit: int = 168,
    ) -> list[dict]:
        """GET /v1/admin/ohlcv. Phase 0 tracking용 OHLCV 조회.

        반환: [{"open_time","open","high","low","close","volume"}, ...]
        """
        params: Dict[str, str] = {
            "ticker": ticker,
            "interval": interval,
            "limit": str(limit),
        }
        if since:
            params["since"] = since
        async with self._client() as c:
            r = await c.get("/v1/admin/ohlcv", params=params)
        await self._raise_for_status(r)
        return list(r.json().get("klines", []))
```

- [ ] **Step 4: Run — PASS**

```
pytest tests/test_api_client.py -v -k "admin_ohlcv"
```

Expected: 3 passed.

- [ ] **Step 5: Full regression + Commit**

```
pytest -q
git add src/sajucandle/api_client.py tests/test_api_client.py
git commit -m "feat(api_client): add get_admin_ohlcv for Phase 0 tracking"
```

---

## Task 11: broadcast.py — Phase 0 default callback → admin ohlcv 호출

**Files:**
- Modify: `src/sajucandle/broadcast.py`
- Modify: `tests/test_broadcast.py`

Week 8의 `_default_get_klines`가 빈 리스트 반환했던 것을 admin ohlcv 호출로 교체. api_client 클로저 캡처.

- [ ] **Step 1: Write failing tests**

`tests/test_broadcast.py` 맨 아래에 추가:

```python
# ─────────────────────────────────────────────
# Week 9: Phase 0 default callback이 admin ohlcv 호출
# ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_phase0_default_get_klines_calls_admin_ohlcv():
    """run_broadcast 내부 default _get_klines가 api_client.get_admin_ohlcv 호출."""
    from datetime import date, datetime, timezone, timedelta
    from unittest.mock import AsyncMock, MagicMock
    from sajucandle.broadcast import run_broadcast
    from sajucandle.repositories import SignalLogRow

    two_hours_ago = datetime.now(timezone.utc) - timedelta(hours=2)
    pending_row = SignalLogRow(
        id=401, sent_at=two_hours_ago, source="ondemand",
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

    api_client = MagicMock()
    api_client.get_admin_users = AsyncMock(return_value=[])
    api_client.get_admin_watchlist_symbols = AsyncMock(return_value=[])
    # 핵심: Phase 0에서 api_client.get_admin_ohlcv 호출되는지 검증
    api_client.get_admin_ohlcv = AsyncMock(return_value=[
        {
            "open_time": (two_hours_ago + timedelta(minutes=30)).isoformat(),
            "open": 71000, "high": 72000, "low": 70500,
            "close": 71500, "volume": 1000,
        },
    ])
    # admin_chat_id=None라 Phase 1 skip. pending_tracking DI
    list_pending = AsyncMock(return_value=[pending_row])
    update_tracking = AsyncMock()

    send = AsyncMock()
    summary = await run_broadcast(
        api_client=api_client,
        send_message=send,
        chat_ids=[],
        target_date=date(2026, 4, 19),
        dry_run=True,
        admin_chat_id=None,
        skip_watchlist=True,
        list_pending_tracking_fn=list_pending,
        update_signal_tracking_fn=update_tracking,
        # get_klines_for_tracking_fn 미제공 → default 사용 → api_client.get_admin_ohlcv 호출
    )
    # default는 api_client.get_admin_ohlcv를 호출해야 함
    api_client.get_admin_ohlcv.assert_called()
    # MFE/MAE 업데이트 호출됨
    update_tracking.assert_called()
    assert summary.tracking_updated >= 1
```

- [ ] **Step 2: Run — fail**

```
pytest tests/test_broadcast.py -v -k "default_get_klines_calls_admin_ohlcv"
```

Expected: `AssertionError: Expected call: get_admin_ohlcv(...) not called.` (default가 빈 리스트 반환이라 get_admin_ohlcv 호출 안 됨).

- [ ] **Step 3: Modify broadcast.py**

`D:\사주캔들\src\sajucandle\broadcast.py`의 `run_broadcast` 내부 `_default_get_klines` 정의 부분을 찾아 교체:

기존:
```python
    if get_klines_for_tracking_fn is None:
        async def _default_get_klines(ticker, sent_at):
            # skeleton: admin OHLCV 엔드포인트가 없어 빈 리스트 반환.
            return []
        get_klines_for_tracking_fn = _default_get_klines
```

교체:
```python
    if get_klines_for_tracking_fn is None:
        async def _default_get_klines(ticker, sent_at):
            """Week 9: admin OHLCV 엔드포인트 호출."""
            try:
                raw = await api_client.get_admin_ohlcv(
                    ticker,
                    interval="1h",
                    since=sent_at.isoformat(),
                    limit=168,
                )
            except Exception as e:
                logger.warning(
                    "phase0 ohlcv fetch failed ticker=%s: %s", ticker, e
                )
                return []
            from sajucandle.market_data import Kline
            result = []
            for d in raw:
                try:
                    result.append(Kline.from_dict(d))
                except Exception as e:
                    logger.warning(
                        "phase0 kline parse failed: %s", e
                    )
            return result
        get_klines_for_tracking_fn = _default_get_klines
```

- [ ] **Step 4: Run — PASS**

```
pytest tests/test_broadcast.py -v -k "default_get_klines_calls_admin_ohlcv"
```

Expected: 1 passed.

- [ ] **Step 5: Full regression + Commit**

```
pytest -q
git add src/sajucandle/broadcast.py tests/test_broadcast.py
git commit -m "feat(broadcast): Phase 0 default callback calls admin OHLCV (real data)"
```

---

## Task 12: handlers.py — 카드 포맷 등급별 분기 (큰 태스크)

**Files:**
- Modify: `src/sajucandle/handlers.py`
- Modify: `tests/test_handlers.py`

- [ ] **Step 1: Write failing tests**

`tests/test_handlers.py` 맨 아래에 추가:

```python
# ─────────────────────────────────────────────
# Week 9: 등급별 카드 블록 (세팅 vs 주요 레벨)
# ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_card_shows_trade_setup_on_entry_grade(monkeypatch):
    """'진입' 등급일 때 '세팅' 블록 표시."""
    from sajucandle import handlers
    from unittest.mock import AsyncMock, MagicMock

    payload = _aapl_signal_payload()
    payload["signal_grade"] = "진입"
    payload["analysis"]["trade_setup"] = {
        "entry": 184.12,
        "stop_loss": 180.50,
        "take_profit_1": 188.50,
        "take_profit_2": 193.00,
        "risk_pct": 2.0,
        "rr_tp1": 1.2,
        "rr_tp2": 2.4,
        "sl_basis": "atr",
        "tp1_basis": "sr_snap",
        "tp2_basis": "atr",
    }
    payload["analysis"]["sr_levels"] = []

    async def fake_get_signal(chat_id, ticker="BTCUSDT", date=None):
        return payload

    monkeypatch.setattr(handlers, "_api_client",
                        MagicMock(get_signal=fake_get_signal))
    context = MagicMock(args=["AAPL"])
    update = _make_update(text="/signal AAPL", chat_id=42)
    update.message.reply_text = AsyncMock()

    await handlers.signal_command(update, context)
    sent = update.message.reply_text.call_args[0][0]
    assert "세팅" in sent or "진입" in sent
    assert "손절" in sent
    assert "180.50" in sent
    assert "익절" in sent
    assert "R:R" in sent
    assert "리스크" in sent
    assert "2.0" in sent


@pytest.mark.asyncio
async def test_card_shows_sr_levels_on_gwanmang_grade(monkeypatch):
    """'관망' 등급일 때 '주요 레벨' 블록 표시."""
    from sajucandle import handlers
    from unittest.mock import AsyncMock, MagicMock

    payload = _aapl_signal_payload()
    payload["signal_grade"] = "관망"
    payload["analysis"]["trade_setup"] = None
    payload["analysis"]["sr_levels"] = [
        {"price": 188.50, "kind": "resistance", "strength": "high"},
        {"price": 193.00, "kind": "resistance", "strength": "medium"},
        {"price": 180.50, "kind": "support", "strength": "high"},
        {"price": 177.00, "kind": "support", "strength": "low"},
    ]

    async def fake_get_signal(chat_id, ticker="BTCUSDT", date=None):
        return payload

    monkeypatch.setattr(handlers, "_api_client",
                        MagicMock(get_signal=fake_get_signal))
    context = MagicMock(args=["AAPL"])
    update = _make_update(text="/signal AAPL", chat_id=42)
    update.message.reply_text = AsyncMock()

    await handlers.signal_command(update, context)
    sent = update.message.reply_text.call_args[0][0]
    assert "주요 레벨" in sent or "저항" in sent
    assert "188.50" in sent
    assert "180.50" in sent
    # 세팅 블록은 없어야
    assert "손절" not in sent or "R:R" not in sent


@pytest.mark.asyncio
async def test_card_gwanmang_without_sr_levels_shows_no_block(monkeypatch):
    """관망 + sr_levels 빈 리스트면 주요 레벨 블록도 생략."""
    from sajucandle import handlers
    from unittest.mock import AsyncMock, MagicMock

    payload = _aapl_signal_payload()
    payload["signal_grade"] = "관망"
    payload["analysis"]["trade_setup"] = None
    payload["analysis"]["sr_levels"] = []

    async def fake_get_signal(chat_id, ticker="BTCUSDT", date=None):
        return payload

    monkeypatch.setattr(handlers, "_api_client",
                        MagicMock(get_signal=fake_get_signal))
    context = MagicMock(args=["AAPL"])
    update = _make_update(text="/signal AAPL", chat_id=42)
    update.message.reply_text = AsyncMock()

    await handlers.signal_command(update, context)
    sent = update.message.reply_text.call_args[0][0]
    assert "주요 레벨" not in sent
    assert "손절" not in sent
```

기존 헬퍼 `_aapl_signal_payload`가 `analysis.trade_setup`, `analysis.sr_levels`를 이미 반환하지 않을 가능성 → 헬퍼 수정 필요. 파일 상단에서 `_aapl_signal_payload`, `_btc_signal_payload` 찾아서:

```python
def _aapl_signal_payload() -> dict:
    return {
        ...,
        "analysis": {
            "structure": {"state": "uptrend", "score": 70},
            "alignment": {...},
            "rsi_1h": 60.0,
            "volume_ratio_1d": 1.2,
            "composite_score": 72,
            "reason": "...",
            "sr_levels": [],           # 기본 빈 (Week 9)
            "trade_setup": None,       # 기본 None (Week 9)
        },
    }
```

- [ ] **Step 2: Run — fail**

```
pytest tests/test_handlers.py -v -k "trade_setup_on_entry or sr_levels_on_gwanmang or without_sr_levels_shows_no"
```

Expected: 포맷 미구현으로 FAIL.

- [ ] **Step 3: Modify _format_signal_card**

`D:\사주캔들\src\sajucandle\handlers.py`의 `_format_signal_card` 함수 내부 — 기존 "구조/정렬/진입조건" 블록 이후, "종합" 라인 이전에 등급별 분기 추가:

기존 흐름:
```python
    # 분석 3줄
    if analysis:
        lines.append("")
        lines.append(f"구조: ...")
        lines.append(f"정렬: ...")
        lines.append(f"진입조건: ...")
    
    lines.append("")
    lines.append(f"종합: ...")
```

수정:
```python
    # 분석 3줄 (기존 Week 8)
    if analysis:
        lines.append("")
        lines.append(f"구조: ...")
        lines.append(f"정렬: ...")
        lines.append(f"진입조건: ...")

        # Week 9: 등급별 추가 블록
        grade = data.get("signal_grade", "")
        ts = analysis.get("trade_setup")
        sr_levels = analysis.get("sr_levels") or []

        if grade in ("강진입", "진입") and ts:
            _append_trade_setup_block(lines, ts)
        elif sr_levels:
            _append_sr_levels_block(lines, sr_levels)

    lines.append("")
    lines.append(f"종합: ...")
```

두 헬퍼 함수 추가 (같은 파일):

```python
def _append_trade_setup_block(lines: list, ts: dict) -> None:
    """진입/강진입 등급에 '세팅' 블록 삽입."""
    entry = ts["entry"]
    sl = ts["stop_loss"]
    tp1 = ts["take_profit_1"]
    tp2 = ts["take_profit_2"]
    risk = ts["risk_pct"]
    rr1 = ts["rr_tp1"]
    rr2 = ts["rr_tp2"]

    sl_pct = (sl - entry) / entry * 100 if entry else 0.0
    tp1_pct = (tp1 - entry) / entry * 100 if entry else 0.0
    tp2_pct = (tp2 - entry) / entry * 100 if entry else 0.0

    lines.append("")
    lines.append("세팅:")
    lines.append(f" 진입 ${entry:,.2f}")
    lines.append(f" 손절 ${sl:,.2f} ({sl_pct:+.1f}%)")
    lines.append(
        f" 익절1 ${tp1:,.2f} ({tp1_pct:+.1f}%)  "
        f"익절2 ${tp2:,.2f} ({tp2_pct:+.1f}%)"
    )
    lines.append(f" R:R {rr1:.1f} / {rr2:.1f}   리스크 {risk:.1f}%")


def _append_sr_levels_block(lines: list, levels: list) -> None:
    """관망/회피 등급에 '주요 레벨' 블록 삽입."""
    if not levels:
        return
    resistances = sorted(
        [l for l in levels if l["kind"] == "resistance"],
        key=lambda l: l["price"],
    )
    supports = sorted(
        [l for l in levels if l["kind"] == "support"],
        key=lambda l: l["price"],
        reverse=True,
    )
    if not resistances and not supports:
        return
    lines.append("")
    lines.append("주요 레벨:")
    if resistances:
        prices = " · ".join(f"${l['price']:,.2f}" for l in resistances)
        lines.append(f" 저항 {prices}")
    if supports:
        prices = " · ".join(f"${l['price']:,.2f}" for l in supports)
        lines.append(f" 지지 {prices}")
```

- [ ] **Step 4: Run — PASS**

```
pytest tests/test_handlers.py -v -k "trade_setup_on_entry or sr_levels_on_gwanmang or without_sr_levels"
```

Expected: 3 passed.

기존 테스트가 Week 8 3줄 포맷 검증만 있으면 그대로 통과. 만약 깨지면 payload 헬퍼에 sr_levels/trade_setup 기본값(빈/None) 추가로 처리.

- [ ] **Step 5: Full regression + Commit**

```
pytest -q
git add src/sajucandle/handlers.py tests/test_handlers.py
git commit -m "feat(bot): card blocks by grade (trade setup vs S/R levels)"
```

---

## Task 13: README + lint + push

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Lint**

```
ruff check src/ tests/
```

Expected: clean.

- [ ] **Step 2: Full pytest**

```
pytest -q
```

Expected: 280+ passed, 60+ skipped.

- [ ] **Step 3: README update**

Week 8 섹션 아래에 추가:

```markdown
## Week 9 Phase 2: S/R + SL/TP + admin OHLCV

Week 8의 "왜 진입?"에서 Week 9는 **"어디에 진입/손절/익절?"**로 격상. 지지/저항 자동 식별 + 하이브리드 ATR·S/R SL/TP 제안.

### 새 분석 모듈
- `analysis/volume_profile.py` — VPVR 매물대 상위 N개
- `analysis/support_resistance.py` — Swing + Volume 융합 → SRLevel
- `analysis/trade_setup.py` — 하이브리드 ATR + S/R snap SL/TP

### 새 카드 포맷

**진입/강진입:**
```
구조: 상승추세 (HH-HL)
정렬: 1d↑ 4h↑ 1h↑  (강정렬)
진입조건: RSI(1h) 35 · 거래량 1.5x

세팅:
 진입 $184.12
 손절 $180.50 (-2.0%)
 익절1 $188.50 (+2.4%)  익절2 $193.00 (+4.8%)
 R:R 1.2 / 2.4   리스크 2.0%

종합: 72 | 진입
```

**관망/회피:**
```
주요 레벨:
 저항 $188.50 · $193.00 · $196.50
 지지 $180.50 · $177.00 · $172.00

종합: 48 | 관망
```

### 새 API 엔드포인트
- `GET /v1/admin/ohlcv?ticker=&interval=&since=&limit=` — Phase 0 tracking용 OHLCV 조회

### Phase 0 실데이터 연결
Week 8의 `_default_get_klines` skeleton이 admin OHLCV 호출로 교체되어 **signal_log의 MFE/MAE가 실제로 채워지기 시작**.

### signal_log 확장 컬럼 (migration 004)
`stop_loss`, `take_profit_1`, `take_profit_2`, `risk_pct`, `rr_tp1`, `rr_tp2`, `sl_basis`, `tp1_basis`, `tp2_basis`.

### 범위 밖 (Week 10~11)
- 시그널 발송 거부 규칙 (BREAKDOWN에서 매수 차단)
- MFE/MAE 통계 집계 API + 카드에 백테스트 프루프
- 튜닝 상수 최적화
```

테스트 카운트, 아키텍처 다이어그램에 analysis 패키지 3모듈 추가.

- [ ] **Step 4: Commit + Push**

```
git add README.md
git commit -m "docs: Week 9 S/R + SL/TP + admin OHLCV"
git log --oneline ed5f655..HEAD
git push origin main
```

Expected: Railway 3서비스 자동 재배포.

- [ ] **Step 5: Manual steps (사용자 직접)**

1. Supabase Studio → SQL Editor → `migrations/004_signal_log_tradesetup.sql` 실행
2. 배포 완료 후 `/signal AAPL`, `/signal BTCUSDT` 호출 — 등급에 따라 세팅 or 주요 레벨 블록 확인
3. `curl.exe -H "X-SAJUCANDLE-KEY: <KEY>" ".../v1/admin/ohlcv?ticker=BTCUSDT&limit=5"` — 5봉 반환
4. 다음날 모닝 broadcast 후:
   ```
   SELECT stop_loss, take_profit_1, risk_pct, mfe_7d_pct, mae_7d_pct
   FROM signal_log ORDER BY sent_at DESC LIMIT 5;
   ```
   SL/TP + MFE/MAE 값 있는지

---

## Self-Review

### Spec coverage
- [x] §2.1 S/R 자동 식별 → Task 2 (volume_profile) + Task 3 (support_resistance)
- [x] §2.2 하이브리드 SL/TP → Task 4 (trade_setup)
- [x] §2.3 리스크 % 표시 → Task 4 (risk_pct 계산) + Task 12 (카드 표시)
- [x] §2.4 sr_levels + trade_setup 필드 → Task 5 (composite) + Task 6 (models) + Task 7 (signal_service)
- [x] §2.5 카드 등급별 분기 → Task 12
- [x] §2.6 GET /v1/admin/ohlcv → Task 9
- [x] §2.7 get_admin_ohlcv → Task 10
- [x] §2.8 Phase 0 실데이터 연결 → Task 11
- [x] §2.9 signal_log SL/TP 저장 → Task 1 (migration) + Task 8 (repo) + Task 9 (api 호출)
- [x] §5 admin OHLCV 엔드포인트 스펙 → Task 9
- [x] §8 카드 포맷 → Task 12
- [x] §11 배포 → Task 13

### Placeholder scan
- "TBD", "TODO", "similar to" 없음.
- Phase 0 skeleton의 default callback이 Week 9에서 실데이터 연결 — Task 11에서 구체 구현.
- basis 필드가 API 응답에도 노출되도록 Task 9 Step 5에서 Pydantic 수정 명시.

### Type consistency
- `SRLevel(price, kind, strength, sources)` Task 3 정의 ↔ support_resistance.py 사용 ↔ Task 6 `SRLevelSummary` ↔ Task 12 카드 사용 일치
- `TradeSetup(entry, stop_loss, ...)` Task 4 정의 ↔ Task 6 `TradeSetupSummary`(basis 포함) ↔ Task 9 insert_signal_log 필드명 일치
- `AnalysisResult.sr_levels / atr_1d` Task 5 ↔ Task 7 signal_service에서 사용
- `LevelKind` enum str value "support"/"resistance" ↔ `SRLevelSummary.kind` Literal 일치
- `SignalResponse.analysis.trade_setup.sl_basis` Literal["atr","sr_snap"] 값과 dataclass TradeSetup.sl_basis Literal 일치

### 주의사항
- Task 9가 api.py + models.py + signal_service.py 3파일 건드림 — 큰 태스크이지만 한 커밋. basis 필드 노출 맥락상 분리 어려움. 분리 원하면 Task 9a (엔드포인트) + Task 9b (insert) + Task 6b (basis 추가 + signal_service 반영)로 세분화 가능.
- Task 11은 default callback 교체만이라 작아 보이지만 Phase 0 흐름 전체가 의존하므로 신중히.
- `handlers._append_trade_setup_block`, `_append_sr_levels_block`은 module-private (underscore prefix).
- Redis 캐시는 기존 Week 6 OHLCV 캐시(ohlcv:*:fresh)가 admin_ohlcv_endpoint에서도 공유됨. Phase 0 호출 시 Phase 1 precompute와 같은 심볼이면 캐시 히트.

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-04-19-week9-sr-tradesetup.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**

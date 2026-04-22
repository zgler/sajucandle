"""Phase 2: --mode longonly|symmetric 검증.

longonly 모드가 symmetric 분석 결과에서 숏 사이드만 필터링하는지 확인.
LONG 사이드는 두 모드 동일 (회귀 0).

composite.analyze가 합성 monotonic 데이터에서 RANGE로 폴백해버리므로
(RANGE는 _grade_signal이 '관망' 강제), 엔진 필터 동작 검증에는 analyze를
monkeypatch로 제어된 AnalysisResult로 대체한다.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock

import pytest

from sajucandle.backtest.engine import (
    _apply_longonly_filter,
    run_backtest,
)
from sajucandle.backtest.history import TickerHistory
from sajucandle.market_data import Kline


def _k(t: datetime, price: float) -> Kline:
    return Kline(open_time=t, open=price, high=price + 1, low=price - 1,
                 close=price, volume=100.0)


def _trivial_history(ticker: str, from_dt: datetime, to_dt: datetime) -> TickerHistory:
    n_hours = int((to_dt - from_dt).total_seconds() / 3600) + 100
    k1h = [_k(from_dt + timedelta(hours=i), 100.0) for i in range(n_hours)]
    k4h = [_k(from_dt + timedelta(hours=4 * i), 100.0) for i in range(n_hours // 4)]
    k1d = [_k(from_dt + timedelta(days=i), 100.0) for i in range(n_hours // 24 + 1)]
    return TickerHistory(
        ticker=ticker, klines_1h=k1h, klines_4h=k4h, klines_1d=k1d,
    )


def _make_controlled_analysis(direction: str, state: str = "downtrend"):
    """엔진에 주입할 AnalysisResult — direction/state/score 명시 제어.

    structure.state가 RANGE가 아니면 _grade_signal이 direction 기반 판정.
    """
    from sajucandle.analysis.composite import AnalysisResult
    from sajucandle.analysis.structure import MarketStructure, StructureAnalysis
    from sajucandle.analysis.multi_timeframe import Alignment
    from sajucandle.analysis.timeframe import TrendDirection

    state_enum = MarketStructure(state)
    if direction == "SHORT":
        tf = TrendDirection.DOWN
        bias = "bearish"
        long_s, short_s = 20, 80
    elif direction == "LONG":
        tf = TrendDirection.UP
        bias = "bullish"
        long_s, short_s = 80, 20
    else:
        tf = TrendDirection.FLAT
        bias = "mixed"
        long_s, short_s = 50, 50

    return AnalysisResult(
        structure=StructureAnalysis(
            state=state_enum, last_high=None, last_low=None,
            score=long_s, long_score=long_s, short_score=short_s,
        ),
        alignment=Alignment(
            tf_1h=tf, tf_4h=tf, tf_1d=tf,
            aligned=True, bias=bias,
            score=long_s, long_score=long_s, short_score=short_s,
        ),
        rsi_1h=70.0 if direction == "SHORT" else 30.0,
        volume_ratio_1d=1.3,
        composite_score=max(long_s, short_s),
        reason="controlled",
        sr_levels=[], atr_1d=2.0,
        long_score=long_s, short_score=short_s,
        direction=direction,
    )


# ─────────────────────────────────────────────
# _apply_longonly_filter 단위
# ─────────────────────────────────────────────


def test_longonly_filter_strips_short_entries():
    assert _apply_longonly_filter("진입_S", "SHORT") == ("관망", "NEUTRAL")
    assert _apply_longonly_filter("강진입_S", "SHORT") == ("관망", "NEUTRAL")


def test_longonly_filter_preserves_long_entries():
    assert _apply_longonly_filter("진입_L", "LONG") == ("진입_L", "LONG")
    assert _apply_longonly_filter("강진입_L", "LONG") == ("강진입_L", "LONG")


def test_longonly_filter_preserves_gwanmang():
    assert _apply_longonly_filter("관망", "NEUTRAL") == ("관망", "NEUTRAL")
    assert _apply_longonly_filter("관망", "LONG") == ("관망", "LONG")


def test_longonly_filter_normalizes_short_direction_even_on_gwanmang():
    """관망+SHORT 조합(낮은 score)도 direction은 NEUTRAL로 정규화."""
    assert _apply_longonly_filter("관망", "SHORT") == ("관망", "NEUTRAL")


# ─────────────────────────────────────────────
# run_backtest mode 통합
# ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_symmetric_mode_produces_short_signals(monkeypatch):
    """controlled SHORT+DOWNTREND 입력 → symmetric 모드에서 숏 진입 등급 발생."""
    from_dt = datetime(2026, 1, 1, tzinfo=timezone.utc)
    to_dt = datetime(2026, 1, 11, tzinfo=timezone.utc)
    hist = _trivial_history("BTCUSDT", from_dt, to_dt)

    monkeypatch.setattr(
        "sajucandle.backtest.engine.analyze",
        lambda k1h, k4h, k1d: _make_controlled_analysis("SHORT", "downtrend"),
    )

    inserted: list[dict] = []

    async def fake_insert(**kwargs):
        inserted.append(kwargs)
        return len(inserted)

    await run_backtest(
        ticker="BTCUSDT",
        from_dt=from_dt, to_dt=to_dt,
        run_id="phase2-test-symmetric",
        router=MagicMock(),
        saju_score_fn=lambda d, ac: 50,
        insert_log_fn=fake_insert,
        history_override=hist,
        mode="symmetric",
    )

    grades = [r["signal_grade"] for r in inserted]
    directions = [r["signal_direction"] for r in inserted]
    short_entries = sum(1 for g in grades if g in ("진입_S", "강진입_S"))
    assert short_entries >= 1, grades
    assert "SHORT" in directions


@pytest.mark.asyncio
async def test_longonly_mode_strips_short_entries_and_direction(monkeypatch):
    """동일 입력 + longonly 모드 → 숏 등급 + SHORT direction 모두 0건."""
    from_dt = datetime(2026, 1, 1, tzinfo=timezone.utc)
    to_dt = datetime(2026, 1, 11, tzinfo=timezone.utc)
    hist = _trivial_history("BTCUSDT", from_dt, to_dt)

    monkeypatch.setattr(
        "sajucandle.backtest.engine.analyze",
        lambda k1h, k4h, k1d: _make_controlled_analysis("SHORT", "downtrend"),
    )

    inserted: list[dict] = []

    async def fake_insert(**kwargs):
        inserted.append(kwargs)
        return len(inserted)

    await run_backtest(
        ticker="BTCUSDT",
        from_dt=from_dt, to_dt=to_dt,
        run_id="phase2-test-longonly",
        router=MagicMock(),
        saju_score_fn=lambda d, ac: 50,
        insert_log_fn=fake_insert,
        history_override=hist,
        mode="longonly",
    )

    grades = [r["signal_grade"] for r in inserted]
    directions = [r["signal_direction"] for r in inserted]
    assert all(g not in ("진입_S", "강진입_S") for g in grades), grades
    assert "SHORT" not in directions


@pytest.mark.asyncio
async def test_longonly_preserves_long_sides_exactly(monkeypatch):
    """controlled LONG 입력 → symmetric/longonly 결과 핵심 필드 동일 (회귀 0)."""
    from_dt = datetime(2026, 1, 1, tzinfo=timezone.utc)
    to_dt = datetime(2026, 1, 11, tzinfo=timezone.utc)
    hist = _trivial_history("BTCUSDT", from_dt, to_dt)

    monkeypatch.setattr(
        "sajucandle.backtest.engine.analyze",
        lambda k1h, k4h, k1d: _make_controlled_analysis("LONG", "uptrend"),
    )

    sym_rows: list[dict] = []
    lon_rows: list[dict] = []

    async def sym_insert(**kwargs):
        sym_rows.append(kwargs)
        return len(sym_rows)

    async def lon_insert(**kwargs):
        lon_rows.append(kwargs)
        return len(lon_rows)

    await run_backtest(
        ticker="BTCUSDT",
        from_dt=from_dt, to_dt=to_dt,
        run_id="phase2-test-sym-sides",
        router=MagicMock(),
        saju_score_fn=lambda d, ac: 50,
        insert_log_fn=sym_insert,
        history_override=hist,
        mode="symmetric",
    )
    await run_backtest(
        ticker="BTCUSDT",
        from_dt=from_dt, to_dt=to_dt,
        run_id="phase2-test-lon-sides",
        router=MagicMock(),
        saju_score_fn=lambda d, ac: 50,
        insert_log_fn=lon_insert,
        history_override=hist,
        mode="longonly",
    )

    def _extract(r):
        return (r["target_date"], r["signal_grade"], r["composite_score"],
                r["signal_direction"],
                r.get("stop_loss"), r.get("take_profit_1"))

    sym_long = sorted(_extract(r) for r in sym_rows
                       if r["signal_grade"] in ("진입_L", "강진입_L"))
    lon_long = sorted(_extract(r) for r in lon_rows
                       if r["signal_grade"] in ("진입_L", "강진입_L"))
    assert sym_long == lon_long
    assert len(sym_long) >= 1

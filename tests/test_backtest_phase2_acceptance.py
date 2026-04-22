"""Phase 2 완료 기준 acceptance 테스트.

60일 합성 히스토리 (상승장 20일 + 박스 20일 + 하락장 20일) A/B 모드 비교.

스펙 §3.8 비교 지표 + §12 완료 기준:
- symmetric 모드: 하락장 구간에 SHORT 신호 ≥ 1건
- longonly 모드: 하락장 구간에 SHORT 신호 = 0건
- 두 모드의 LONG 신호는 완전 일치 (회귀 0)
- signal_direction 컬럼 값도 올바르게 기록

composite.analyze가 합성 monotonic 데이터에서 RANGE 폴백 이슈가 있으므로
engine에서 analyze를 구간별 controlled 결과로 monkeypatch. 엔진 레벨 모드
분기가 올바르게 작동하는지 검증.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from sajucandle.backtest.engine import run_backtest
from sajucandle.backtest.history import TickerHistory
from sajucandle.market_data import Kline


def _trivial_history(ticker: str, from_dt: datetime, to_dt: datetime) -> TickerHistory:
    n_hours = int((to_dt - from_dt).total_seconds() / 3600) + 100
    k1h = [
        Kline(
            open_time=from_dt + timedelta(hours=i),
            open=100, high=101, low=99, close=100, volume=100.0,
        )
        for i in range(n_hours)
    ]
    k4h = [
        Kline(
            open_time=from_dt + timedelta(hours=4 * i),
            open=100, high=101, low=99, close=100, volume=100.0,
        )
        for i in range(n_hours // 4)
    ]
    k1d = [
        Kline(
            open_time=from_dt + timedelta(days=i),
            open=100, high=101, low=99, close=100, volume=100.0,
        )
        for i in range(n_hours // 24 + 1)
    ]
    return TickerHistory(
        ticker=ticker, klines_1h=k1h, klines_4h=k4h, klines_1d=k1d,
    )


def _make_result(direction: str, state: str, score: int = 80):
    from sajucandle.analysis.composite import AnalysisResult
    from sajucandle.analysis.structure import MarketStructure, StructureAnalysis
    from sajucandle.analysis.multi_timeframe import Alignment
    from sajucandle.analysis.timeframe import TrendDirection

    state_enum = MarketStructure(state)
    if direction == "SHORT":
        tf = TrendDirection.DOWN
        bias = "bearish"
        long_s, short_s = 100 - score, score
    elif direction == "LONG":
        tf = TrendDirection.UP
        bias = "bullish"
        long_s, short_s = score, 100 - score
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
        rsi_1h=70.0 if direction == "SHORT" else 30.0 if direction == "LONG" else 50.0,
        volume_ratio_1d=1.2,
        composite_score=max(long_s, short_s),
        reason="controlled",
        sr_levels=[], atr_1d=2.0,
        long_score=long_s, short_score=short_s,
        direction=direction,
    )


def _phase_by_date(d):
    """t 날짜에 따라 구간별 analyze 결과 반환.

    테스트에서 from_dt=2026-03-01 ~ to_dt=2026-04-30 가정:
      day 1-20: UPTREND, LONG
      day 21-40: RANGE, NEUTRAL
      day 41+: DOWNTREND, SHORT
    """
    if d.month == 3 and d.day <= 20:
        return _make_result("LONG", "uptrend", score=80)
    elif (d.month == 3 and d.day > 20) or (d.month == 4 and d.day <= 9):
        return _make_result("NEUTRAL", "range", score=50)
    else:
        return _make_result("SHORT", "downtrend", score=80)


@pytest.mark.asyncio
async def test_phase2_acceptance_symmetric_produces_short_in_downtrend(monkeypatch):
    from_dt = datetime(2026, 3, 1, tzinfo=timezone.utc)
    to_dt = datetime(2026, 4, 30, tzinfo=timezone.utc)
    hist = _trivial_history("BTCUSDT", from_dt, to_dt)

    monkeypatch.setattr(
        "sajucandle.backtest.engine.analyze",
        lambda k1h, k4h, k1d: _phase_by_date(k1d[-1].open_time.date()),
    )

    inserted: list[dict] = []

    async def fake_insert(**kwargs):
        inserted.append(kwargs)
        return len(inserted)

    await run_backtest(
        ticker="BTCUSDT",
        from_dt=from_dt, to_dt=to_dt,
        run_id="phase2-accept-sym",
        router=MagicMock(),
        saju_score_fn=lambda d, ac: 50,
        insert_log_fn=fake_insert,
        history_override=hist,
        mode="symmetric",
    )

    long_count = sum(
        1 for r in inserted if r["signal_grade"] in ("진입_L", "강진입_L")
    )
    short_count = sum(
        1 for r in inserted if r["signal_grade"] in ("진입_S", "강진입_S")
    )
    neutral_count = sum(
        1 for r in inserted if r["signal_grade"] == "관망"
    )

    # 기대: 3 구간 각각 ~20일씩
    assert long_count >= 15, f"LONG count too low: {long_count}"
    assert short_count >= 15, f"SHORT count too low: {short_count}"
    assert neutral_count >= 15, f"NEUTRAL count too low: {neutral_count}"


@pytest.mark.asyncio
async def test_phase2_acceptance_longonly_zero_shorts(monkeypatch):
    """동일 입력 + longonly 모드 → 하락장 SHORT 신호 0건."""
    from_dt = datetime(2026, 3, 1, tzinfo=timezone.utc)
    to_dt = datetime(2026, 4, 30, tzinfo=timezone.utc)
    hist = _trivial_history("BTCUSDT", from_dt, to_dt)

    monkeypatch.setattr(
        "sajucandle.backtest.engine.analyze",
        lambda k1h, k4h, k1d: _phase_by_date(k1d[-1].open_time.date()),
    )

    inserted: list[dict] = []

    async def fake_insert(**kwargs):
        inserted.append(kwargs)
        return len(inserted)

    await run_backtest(
        ticker="BTCUSDT",
        from_dt=from_dt, to_dt=to_dt,
        run_id="phase2-accept-lon",
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
async def test_phase2_acceptance_long_side_identical_between_modes(monkeypatch):
    """스펙 §3.8 회귀 방어: LONG 사이드 두 모드에서 완전 일치."""
    from_dt = datetime(2026, 3, 1, tzinfo=timezone.utc)
    to_dt = datetime(2026, 4, 30, tzinfo=timezone.utc)
    hist = _trivial_history("BTCUSDT", from_dt, to_dt)

    monkeypatch.setattr(
        "sajucandle.backtest.engine.analyze",
        lambda k1h, k4h, k1d: _phase_by_date(k1d[-1].open_time.date()),
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
        run_id="phase2-accept-sym2",
        router=MagicMock(),
        saju_score_fn=lambda d, ac: 50,
        insert_log_fn=sym_insert,
        history_override=hist,
        mode="symmetric",
    )
    await run_backtest(
        ticker="BTCUSDT",
        from_dt=from_dt, to_dt=to_dt,
        run_id="phase2-accept-lon2",
        router=MagicMock(),
        saju_score_fn=lambda d, ac: 50,
        insert_log_fn=lon_insert,
        history_override=hist,
        mode="longonly",
    )

    sym_long = sorted(
        (r["target_date"], r["signal_grade"], r["composite_score"],
         r["signal_direction"])
        for r in sym_rows if r["signal_grade"] in ("진입_L", "강진입_L")
    )
    lon_long = sorted(
        (r["target_date"], r["signal_grade"], r["composite_score"],
         r["signal_direction"])
        for r in lon_rows if r["signal_grade"] in ("진입_L", "강진입_L")
    )
    assert sym_long == lon_long
    assert len(sym_long) >= 15


@pytest.mark.asyncio
async def test_phase2_acceptance_direction_propagates_to_db(monkeypatch):
    """스펙 §5.1: signal_direction 컬럼이 symmetric 모드에서 LONG/SHORT/NEUTRAL
    모두 채워짐."""
    from_dt = datetime(2026, 3, 1, tzinfo=timezone.utc)
    to_dt = datetime(2026, 4, 30, tzinfo=timezone.utc)
    hist = _trivial_history("BTCUSDT", from_dt, to_dt)

    monkeypatch.setattr(
        "sajucandle.backtest.engine.analyze",
        lambda k1h, k4h, k1d: _phase_by_date(k1d[-1].open_time.date()),
    )

    inserted: list[dict] = []

    async def fake_insert(**kwargs):
        inserted.append(kwargs)
        return len(inserted)

    await run_backtest(
        ticker="BTCUSDT",
        from_dt=from_dt, to_dt=to_dt,
        run_id="phase2-accept-direction",
        router=MagicMock(),
        saju_score_fn=lambda d, ac: 50,
        insert_log_fn=fake_insert,
        history_override=hist,
        mode="symmetric",
    )

    dirs = set(r["signal_direction"] for r in inserted)
    assert {"LONG", "SHORT", "NEUTRAL"}.issubset(dirs), dirs


@pytest.mark.asyncio
async def test_phase2_acceptance_trade_setup_direction_correct(monkeypatch):
    """스펙 §7.1: SHORT TradeSetup은 SL>entry>TP, LONG은 기존대로."""
    from_dt = datetime(2026, 3, 1, tzinfo=timezone.utc)
    to_dt = datetime(2026, 4, 30, tzinfo=timezone.utc)
    hist = _trivial_history("BTCUSDT", from_dt, to_dt)

    monkeypatch.setattr(
        "sajucandle.backtest.engine.analyze",
        lambda k1h, k4h, k1d: _phase_by_date(k1d[-1].open_time.date()),
    )

    inserted: list[dict] = []

    async def fake_insert(**kwargs):
        inserted.append(kwargs)
        return len(inserted)

    await run_backtest(
        ticker="BTCUSDT",
        from_dt=from_dt, to_dt=to_dt,
        run_id="phase2-accept-ts",
        router=MagicMock(),
        saju_score_fn=lambda d, ac: 50,
        insert_log_fn=fake_insert,
        history_override=hist,
        mode="symmetric",
    )

    long_rows = [
        r for r in inserted
        if r["signal_grade"] in ("진입_L", "강진입_L") and r["stop_loss"] is not None
    ]
    short_rows = [
        r for r in inserted
        if r["signal_grade"] in ("진입_S", "강진입_S") and r["stop_loss"] is not None
    ]
    assert len(long_rows) >= 1
    assert len(short_rows) >= 1

    for r in long_rows:
        entry = r["entry_price"]
        assert r["stop_loss"] < entry
        assert entry < r["take_profit_1"] < r["take_profit_2"]

    for r in short_rows:
        entry = r["entry_price"]
        assert r["stop_loss"] > entry
        assert entry > r["take_profit_1"] > r["take_profit_2"]

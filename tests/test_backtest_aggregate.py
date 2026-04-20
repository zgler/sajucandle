"""backtest.aggregate: run별 GradeStats 집계."""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from sajucandle.backtest.aggregate import aggregate_run
from sajucandle.repositories import insert_signal_log, update_signal_tracking

# DB integration tests — TEST_DATABASE_URL 있을 때만
pytestmark = pytest.mark.asyncio


async def _seed(db_conn, run_id: str, entries: list[tuple[str, float, float]]):
    """entries: (grade, mfe_pct, mae_pct) 튜플들 — 전부 tracking_done=TRUE로 저장."""
    from sajucandle.repositories import UserProfile, upsert_user
    await upsert_user(db_conn, UserProfile(
        telegram_chat_id=600001,
        birth_year=1990, birth_month=3, birth_day=15,
        birth_hour=14, birth_minute=0, asset_class_pref="swing",
    ))
    for i, (grade, mfe, mae) in enumerate(entries):
        row_id = await insert_signal_log(
            db_conn,
            source="backtest", telegram_chat_id=None,
            ticker="BTCUSDT", target_date=date(2026, 1, 1) + timedelta(days=i),
            entry_price=100.0, saju_score=50, analysis_score=60,
            structure_state="range", alignment_bias="mixed",
            rsi_1h=None, volume_ratio_1d=None,
            composite_score=60, signal_grade=grade,
            run_id=run_id,
        )
        await update_signal_tracking(
            db_conn, row_id,
            mfe_pct=mfe, mae_pct=mae,
            close_24h=100 + mfe, close_7d=100 + mfe,
            tracking_done=True,
        )


async def test_aggregate_run_empty_returns_empty_list(db_conn):
    r = await aggregate_run(db_conn, run_id="phase1-nonexistent")
    assert r == []


async def test_aggregate_run_win_rate_by_grade(db_conn):
    run_id = "phase1-test-winrate"
    await _seed(db_conn, run_id, [
        ("진입", 3.0, -1.0),
        ("진입", 2.0, -2.0),
        ("진입", -0.5, -3.0),  # 패 (mfe <= 0)
        ("관망", 1.0, -1.0),
    ])
    r = await aggregate_run(db_conn, run_id=run_id)
    by_grade = {gs.grade: gs for gs in r}
    assert by_grade["진입"].count == 3
    assert by_grade["진입"].win_rate == pytest.approx(2 / 3, abs=0.01)
    assert by_grade["진입"].avg_mfe == pytest.approx((3 + 2 - 0.5) / 3, abs=0.01)
    assert by_grade["관망"].count == 1
    assert by_grade["관망"].win_rate == 1.0

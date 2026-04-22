"""repositories 단위 테스트. 각 테스트는 트랜잭션 롤백."""
from __future__ import annotations

import pytest

from datetime import date, datetime, timedelta, timezone

from sajucandle.repositories import (
    UserProfile,
    add_to_watchlist,
    aggregate_signal_stats,
    count_watchlist,
    delete_user,
    get_user,
    insert_signal_log,
    list_all_watchlist_tickers,
    list_chat_ids,
    list_pending_tracking,
    list_watchlist,
    remove_from_watchlist,
    update_signal_tracking,
    upsert_user,
)


async def test_upsert_inserts_when_new(db_conn):
    profile = UserProfile(
        telegram_chat_id=111,
        birth_year=1990, birth_month=3, birth_day=15,
        birth_hour=14, birth_minute=0,
        asset_class_pref="swing",
    )
    saved = await upsert_user(db_conn, profile)
    assert saved.telegram_chat_id == 111
    assert saved.birth_year == 1990
    assert saved.created_at is not None
    assert saved.updated_at is not None


async def test_upsert_updates_when_exists(db_conn):
    p1 = UserProfile(
        telegram_chat_id=222,
        birth_year=1990, birth_month=3, birth_day=15,
        birth_hour=14, birth_minute=0,
        asset_class_pref="swing",
    )
    await upsert_user(db_conn, p1)

    p2 = UserProfile(
        telegram_chat_id=222,
        birth_year=1991, birth_month=6, birth_day=20,
        birth_hour=9, birth_minute=30,
        asset_class_pref="scalp",
    )
    saved = await upsert_user(db_conn, p2)
    assert saved.birth_year == 1991
    assert saved.birth_month == 6
    assert saved.asset_class_pref == "scalp"


async def test_get_returns_none_when_missing(db_conn):
    assert await get_user(db_conn, 9999) is None


async def test_get_returns_profile(db_conn):
    await upsert_user(db_conn, UserProfile(
        telegram_chat_id=333,
        birth_year=2000, birth_month=1, birth_day=1,
        birth_hour=0, birth_minute=0,
        asset_class_pref="long",
    ))
    got = await get_user(db_conn, 333)
    assert got is not None
    assert got.telegram_chat_id == 333
    assert got.asset_class_pref == "long"


async def test_delete_is_idempotent(db_conn):
    # 없어도 에러 없이
    await delete_user(db_conn, 4444)

    await upsert_user(db_conn, UserProfile(
        telegram_chat_id=4444,
        birth_year=1990, birth_month=3, birth_day=15,
        birth_hour=14, birth_minute=0,
        asset_class_pref="swing",
    ))
    await delete_user(db_conn, 4444)
    assert await get_user(db_conn, 4444) is None


async def test_list_chat_ids_empty(db_conn):
    # 다른 테스트 트랜잭션은 롤백되므로 빈 상태 기대
    ids = await list_chat_ids(db_conn)
    assert ids == []


async def test_list_chat_ids_returns_all_registered(db_conn):
    for cid in (5001, 5002, 5003):
        await upsert_user(db_conn, UserProfile(
            telegram_chat_id=cid,
            birth_year=1990, birth_month=3, birth_day=15,
            birth_hour=14, birth_minute=0,
            asset_class_pref="swing",
        ))
    ids = await list_chat_ids(db_conn)
    assert sorted(ids) == [5001, 5002, 5003]


# ─────────────────────────────────────────────
# Week 7: watchlist CRUD
# ─────────────────────────────────────────────



async def _register_user(db_conn, chat_id: int) -> None:
    """watchlist FK를 만족시키기 위한 전제 사용자 등록."""
    await upsert_user(db_conn, UserProfile(
        telegram_chat_id=chat_id,
        birth_year=1990, birth_month=3, birth_day=15,
        birth_hour=14, birth_minute=0,
        asset_class_pref="swing",
    ))


async def test_list_watchlist_empty(db_conn):
    await _register_user(db_conn, 100001)
    items = await list_watchlist(db_conn, 100001)
    assert items == []


async def test_add_and_list_watchlist(db_conn):
    await _register_user(db_conn, 100002)
    await add_to_watchlist(db_conn, 100002, "AAPL")
    items = await list_watchlist(db_conn, 100002)
    assert len(items) == 1
    assert items[0].ticker == "AAPL"
    assert items[0].added_at is not None


async def test_list_watchlist_ordered_by_added_at_asc(db_conn):
    await _register_user(db_conn, 100003)
    await add_to_watchlist(db_conn, 100003, "AAPL")
    await add_to_watchlist(db_conn, 100003, "MSFT")
    await add_to_watchlist(db_conn, 100003, "BTCUSDT")
    items = await list_watchlist(db_conn, 100003)
    tickers = [i.ticker for i in items]
    assert tickers == ["AAPL", "MSFT", "BTCUSDT"]


async def test_add_duplicate_raises_unique_violation(db_conn):
    import asyncpg
    await _register_user(db_conn, 100004)
    await add_to_watchlist(db_conn, 100004, "AAPL")
    with pytest.raises(asyncpg.UniqueViolationError):
        await add_to_watchlist(db_conn, 100004, "AAPL")


async def test_remove_from_watchlist_returns_true_when_existed(db_conn):
    await _register_user(db_conn, 100005)
    await add_to_watchlist(db_conn, 100005, "AAPL")
    deleted = await remove_from_watchlist(db_conn, 100005, "AAPL")
    assert deleted is True
    items = await list_watchlist(db_conn, 100005)
    assert items == []


async def test_remove_from_watchlist_returns_false_when_missing(db_conn):
    await _register_user(db_conn, 100006)
    deleted = await remove_from_watchlist(db_conn, 100006, "AAPL")
    assert deleted is False


async def test_count_watchlist(db_conn):
    await _register_user(db_conn, 100007)
    assert await count_watchlist(db_conn, 100007) == 0
    await add_to_watchlist(db_conn, 100007, "AAPL")
    await add_to_watchlist(db_conn, 100007, "MSFT")
    assert await count_watchlist(db_conn, 100007) == 2


async def test_list_all_watchlist_tickers_union(db_conn):
    await _register_user(db_conn, 100008)
    await _register_user(db_conn, 100009)
    await add_to_watchlist(db_conn, 100008, "AAPL")
    await add_to_watchlist(db_conn, 100008, "TSLA")
    await add_to_watchlist(db_conn, 100009, "AAPL")
    await add_to_watchlist(db_conn, 100009, "BTCUSDT")
    symbols = await list_all_watchlist_tickers(db_conn)
    assert symbols == {"AAPL", "TSLA", "BTCUSDT"}


async def test_delete_user_cascades_watchlist(db_conn):
    await _register_user(db_conn, 100010)
    await add_to_watchlist(db_conn, 100010, "AAPL")
    await delete_user(db_conn, 100010)
    items = await list_watchlist(db_conn, 100010)
    assert items == []


# ─────────────────────────────────────────────
# Week 8: signal_log CRUD
# ─────────────────────────────────────────────


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
    await db_conn.execute("""
        INSERT INTO signal_log (sent_at, source, telegram_chat_id,
            ticker, target_date, entry_price,
            saju_score, analysis_score, structure_state, alignment_bias,
            composite_score, signal_grade, tracking_done)
        VALUES ($1, 'ondemand', $2, 'BTCUSDT', $3, 72000,
                50, 70, 'uptrend', 'bullish', 68, '진입', FALSE)
    """,
    datetime.now(timezone.utc) - timedelta(hours=2),
    200002, date(2026, 4, 19))

    pending = await list_pending_tracking(db_conn, now=datetime.now(timezone.utc))
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
    for p in pending:
        assert p.telegram_chat_id != 200003


async def test_update_signal_tracking_sets_mfe_mae(db_conn):
    await _register_user(db_conn, 200004)
    row_id = await insert_signal_log(
        db_conn,
        source="ondemand", telegram_chat_id=200004,
        ticker="BTCUSDT", target_date=date(2026, 4, 19),
        entry_price=72000.0,
        saju_score=56, analysis_score=72,
        structure_state="uptrend", alignment_bias="bullish",
        rsi_1h=None, volume_ratio_1d=None,
        composite_score=70, signal_grade="진입",
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
    """SL/TP 미제공 시 NULL 저장."""
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


# ─────────────────────────────────────────────
# Week 10 Phase 1: aggregate_signal_stats
# ─────────────────────────────────────────────


async def test_aggregate_signal_stats_empty(db_conn):
    now = datetime.now(timezone.utc)
    stats = await aggregate_signal_stats(db_conn, since=now - timedelta(days=30))
    assert stats["total"] == 0
    assert stats["by_grade"] == {}
    assert stats["tracking_completed"] == 0
    assert stats["tracking_pending"] == 0
    assert stats["sample_size"] == 0


async def test_aggregate_signal_stats_counts_by_grade(db_conn):
    await _register_user(db_conn, 400001)
    now = datetime.now(timezone.utc)
    for grade in ["진입", "진입", "진입", "관망", "회피"]:
        await insert_signal_log(
            db_conn,
            source="ondemand", telegram_chat_id=400001,
            ticker="BTCUSDT", target_date=date(2026, 4, 19),
            entry_price=70000.0,
            saju_score=50, analysis_score=60,
            structure_state="range", alignment_bias="mixed",
            rsi_1h=None, volume_ratio_1d=None,
            composite_score=60, signal_grade=grade,
        )
    stats = await aggregate_signal_stats(db_conn, since=now - timedelta(days=30))
    assert stats["total"] == 5
    assert stats["by_grade"]["진입"] == 3
    assert stats["by_grade"]["관망"] == 1
    assert stats["by_grade"]["회피"] == 1


async def test_aggregate_signal_stats_ticker_filter(db_conn):
    await _register_user(db_conn, 400002)
    now = datetime.now(timezone.utc)
    for ticker in ["BTCUSDT", "BTCUSDT", "AAPL"]:
        await insert_signal_log(
            db_conn,
            source="ondemand", telegram_chat_id=400002,
            ticker=ticker, target_date=date(2026, 4, 19),
            entry_price=100.0,
            saju_score=50, analysis_score=60,
            structure_state="range", alignment_bias="mixed",
            rsi_1h=None, volume_ratio_1d=None,
            composite_score=60, signal_grade="관망",
        )
    stats = await aggregate_signal_stats(
        db_conn, since=now - timedelta(days=30), ticker="BTCUSDT"
    )
    assert stats["total"] == 2


async def test_aggregate_signal_stats_grade_filter(db_conn):
    await _register_user(db_conn, 400003)
    now = datetime.now(timezone.utc)
    for grade in ["진입", "관망", "관망"]:
        await insert_signal_log(
            db_conn,
            source="ondemand", telegram_chat_id=400003,
            ticker="BTCUSDT", target_date=date(2026, 4, 19),
            entry_price=100.0,
            saju_score=50, analysis_score=60,
            structure_state="range", alignment_bias="mixed",
            rsi_1h=None, volume_ratio_1d=None,
            composite_score=60, signal_grade=grade,
        )
    stats = await aggregate_signal_stats(
        db_conn, since=now - timedelta(days=30), grade="관망"
    )
    assert stats["total"] == 2
    assert stats["by_grade"] == {"관망": 2}


async def test_aggregate_signal_stats_mfe_mae_only_from_tracking_done(db_conn):
    await _register_user(db_conn, 400004)
    now = datetime.now(timezone.utc)
    id1 = await insert_signal_log(
        db_conn,
        source="ondemand", telegram_chat_id=400004,
        ticker="BTCUSDT", target_date=date(2026, 4, 19),
        entry_price=100.0,
        saju_score=50, analysis_score=60,
        structure_state="range", alignment_bias="mixed",
        rsi_1h=None, volume_ratio_1d=None,
        composite_score=60, signal_grade="진입",
    )
    await update_signal_tracking(
        db_conn, id1,
        mfe_pct=3.0, mae_pct=-1.0,
        close_24h=None, close_7d=None,
        tracking_done=True,
    )
    await insert_signal_log(
        db_conn,
        source="ondemand", telegram_chat_id=400004,
        ticker="BTCUSDT", target_date=date(2026, 4, 19),
        entry_price=100.0,
        saju_score=50, analysis_score=60,
        structure_state="range", alignment_bias="mixed",
        rsi_1h=None, volume_ratio_1d=None,
        composite_score=60, signal_grade="진입",
    )
    stats = await aggregate_signal_stats(db_conn, since=now - timedelta(days=30))
    assert stats["total"] == 2
    assert stats["tracking_completed"] == 1
    assert stats["tracking_pending"] == 1
    assert stats["sample_size"] == 1
    assert stats["mfe_avg"] == 3.0
    assert stats["mae_avg"] == -1.0


# ─────────────────────────────────────────────
# Phase 1: insert_signal_log run_id
# ─────────────────────────────────────────────


async def test_insert_signal_log_with_run_id(db_conn):
    await _register_user(db_conn, 500001)
    row_id = await insert_signal_log(
        db_conn,
        source="backtest",
        telegram_chat_id=None,
        ticker="BTCUSDT",
        target_date=date(2026, 4, 19),
        entry_price=70000.0,
        saju_score=50,
        analysis_score=72,
        structure_state="uptrend",
        alignment_bias="bullish",
        rsi_1h=60.0,
        volume_ratio_1d=1.2,
        composite_score=70,
        signal_grade="진입",
        run_id="phase1-abc1234-baseline",
    )
    row = await db_conn.fetchrow(
        "SELECT run_id, source FROM signal_log WHERE id = $1", row_id
    )
    assert row["run_id"] == "phase1-abc1234-baseline"
    assert row["source"] == "backtest"


async def test_insert_signal_log_run_id_default_none(db_conn):
    """기존 호출 (run_id 미지정) 하위호환 — NULL 저장."""
    await _register_user(db_conn, 500002)
    row_id = await insert_signal_log(
        db_conn,
        source="ondemand",
        telegram_chat_id=500002,
        ticker="BTCUSDT",
        target_date=date(2026, 4, 19),
        entry_price=70000.0,
        saju_score=50,
        analysis_score=50,
        structure_state="range",
        alignment_bias="mixed",
        rsi_1h=None,
        volume_ratio_1d=None,
        composite_score=50,
        signal_grade="관망",
    )
    row = await db_conn.fetchrow(
        "SELECT run_id FROM signal_log WHERE id = $1", row_id
    )
    assert row["run_id"] is None


async def test_aggregate_signal_stats_default_excludes_backtest(db_conn):
    """run_id 미지정 시 backtest row 제외, 운영(NULL)만 집계."""
    await _register_user(db_conn, 500003)
    # 운영 signal
    await insert_signal_log(
        db_conn, source="ondemand", telegram_chat_id=500003,
        ticker="BTCUSDT", target_date=date(2026, 4, 19),
        entry_price=70000.0, saju_score=50, analysis_score=60,
        structure_state="range", alignment_bias="mixed",
        rsi_1h=None, volume_ratio_1d=None,
        composite_score=60, signal_grade="관망",
    )
    # 백테스트 signal (같은 사용자, 다른 날짜로 덮어쓰기 방지)
    await insert_signal_log(
        db_conn, source="backtest", telegram_chat_id=500003,
        ticker="BTCUSDT", target_date=date(2026, 4, 18),
        entry_price=70000.0, saju_score=50, analysis_score=60,
        structure_state="range", alignment_bias="mixed",
        rsi_1h=None, volume_ratio_1d=None,
        composite_score=60, signal_grade="진입",
        run_id="phase1-test-a",
    )
    now = datetime.now(timezone.utc)
    stats = await aggregate_signal_stats(db_conn, since=now - timedelta(days=30))
    # 운영 row 1개만 집계
    assert stats["total"] == 1
    assert stats["by_grade"].get("관망") == 1
    assert "진입" not in stats["by_grade"] or stats["by_grade"]["진입"] == 0


async def test_aggregate_signal_stats_with_run_id(db_conn):
    """run_id 명시 시 해당 run만 집계."""
    await _register_user(db_conn, 500004)
    await insert_signal_log(
        db_conn, source="backtest", telegram_chat_id=500004,
        ticker="BTCUSDT", target_date=date(2026, 4, 19),
        entry_price=70000.0, saju_score=50, analysis_score=72,
        structure_state="uptrend", alignment_bias="bullish",
        rsi_1h=None, volume_ratio_1d=None,
        composite_score=70, signal_grade="진입",
        run_id="phase1-test-b",
    )
    now = datetime.now(timezone.utc)
    stats = await aggregate_signal_stats(
        db_conn, since=now - timedelta(days=30), run_id="phase1-test-b"
    )
    assert stats["total"] == 1
    assert stats["by_grade"]["진입"] == 1


# ─────────────────────────────────────────────
# Phase 2: signal_direction
# ─────────────────────────────────────────────


async def test_insert_signal_log_with_signal_direction(db_conn):
    await _register_user(db_conn, 600001)
    row_id = await insert_signal_log(
        db_conn,
        source="ondemand",
        telegram_chat_id=600001,
        ticker="BTCUSDT",
        target_date=date(2026, 4, 22),
        entry_price=70000.0,
        saju_score=55,
        analysis_score=72,
        structure_state="downtrend",
        alignment_bias="bearish",
        rsi_1h=75.0,
        volume_ratio_1d=1.3,
        composite_score=70,
        signal_grade="진입_S",
        signal_direction="SHORT",
    )
    row = await db_conn.fetchrow(
        "SELECT signal_direction, signal_grade FROM signal_log WHERE id = $1",
        row_id,
    )
    assert row["signal_direction"] == "SHORT"
    assert row["signal_grade"] == "진입_S"


async def test_insert_signal_log_signal_direction_default_null(db_conn):
    """기존 호출 (signal_direction 미지정) 하위호환 — NULL 저장."""
    await _register_user(db_conn, 600002)
    row_id = await insert_signal_log(
        db_conn,
        source="ondemand",
        telegram_chat_id=600002,
        ticker="AAPL",
        target_date=date(2026, 4, 22),
        entry_price=180.0,
        saju_score=50,
        analysis_score=50,
        structure_state="range",
        alignment_bias="mixed",
        rsi_1h=None,
        volume_ratio_1d=None,
        composite_score=50,
        signal_grade="관망",
    )
    row = await db_conn.fetchrow(
        "SELECT signal_direction FROM signal_log WHERE id = $1", row_id
    )
    assert row["signal_direction"] is None


async def test_insert_signal_log_all_three_directions(db_conn):
    await _register_user(db_conn, 600003)
    for direction, grade in (
        ("LONG", "강진입_L"),
        ("SHORT", "강진입_S"),
        ("NEUTRAL", "관망"),
    ):
        await insert_signal_log(
            db_conn,
            source="backtest",
            telegram_chat_id=None,
            ticker=f"T_{direction}",
            target_date=date(2026, 4, 22),
            entry_price=100.0,
            saju_score=50,
            analysis_score=70,
            structure_state="uptrend",
            alignment_bias="bullish",
            rsi_1h=60.0,
            volume_ratio_1d=1.2,
            composite_score=70,
            signal_grade=grade,
            signal_direction=direction,
        )
    rows = await db_conn.fetch(
        "SELECT signal_direction FROM signal_log WHERE ticker LIKE 'T_%'"
    )
    assert sorted(r["signal_direction"] for r in rows) == ["LONG", "NEUTRAL", "SHORT"]

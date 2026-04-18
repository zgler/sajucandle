"""repositories 단위 테스트. 각 테스트는 트랜잭션 롤백."""
from __future__ import annotations

import pytest

from sajucandle.repositories import (
    UserProfile,
    add_to_watchlist,
    count_watchlist,
    delete_user,
    get_user,
    list_all_watchlist_tickers,
    list_chat_ids,
    list_watchlist,
    remove_from_watchlist,
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

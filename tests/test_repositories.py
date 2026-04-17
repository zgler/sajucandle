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

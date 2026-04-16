"""repositories 단위 테스트. 각 테스트는 트랜잭션 롤백."""
from __future__ import annotations

from sajucandle.repositories import (
    UserProfile,
    delete_user,
    get_user,
    list_chat_ids,
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

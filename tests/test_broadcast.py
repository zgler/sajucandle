"""broadcast 단위 테스트. API/Telegram 모두 mock."""
from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

from sajucandle.api_client import ApiError, NotFoundError
from sajucandle.broadcast import (
    BroadcastSummary,
    _parse_args,
    format_morning_card,
    run_broadcast,
)


# ─────────────────────────────────────────────
# format_morning_card
# ─────────────────────────────────────────────

def _score_fixture() -> dict:
    return {
        "chat_id": 12345,
        "date": "2026-04-16",
        "asset_class": "swing",
        "iljin": "己未",
        "composite_score": 64,
        "signal_grade": "🔄 관망",
        "axes": {
            "wealth":     {"score": 50, "reason": "재성 신호 없음"},
            "decision":   {"score": 82, "reason": "비견+삼합"},
            "volatility": {"score": 50, "reason": "형충 없음"},
            "flow":       {"score": 70, "reason": "삼합 2자"},
        },
        "best_hours": [
            {"shichen": "巳", "time_range": "09:00~11:00", "multiplier": 1.15},
        ],
    }


def test_format_morning_card_contains_header_and_score():
    text = format_morning_card(_score_fixture(), date(2026, 4, 16))
    assert "2026-04-16" in text
    assert "(목)" in text           # 요일
    assert "오늘의 명식 참고" in text
    assert "己未" in text
    assert "swing" in text
    assert "관망" in text
    assert "재물운" in text
    assert "결단운" in text
    assert "/signal" in text        # CTA
    assert "정보 제공" in text      # disclaimer


def test_format_morning_card_without_best_hours():
    s = _score_fixture()
    s["best_hours"] = []
    text = format_morning_card(s, date(2026, 4, 16))
    assert "추천 시진" not in text


def test_format_morning_card_different_weekdays():
    # 2026-04-13 = 월, 14 화, 15 수, 16 목, 17 금, 18 토, 19 일
    for d, wd in [
        (date(2026, 4, 13), "(월)"),
        (date(2026, 4, 17), "(금)"),
        (date(2026, 4, 19), "(일)"),
    ]:
        text = format_morning_card(_score_fixture(), d)
        assert wd in text


# ─────────────────────────────────────────────
# run_broadcast
# ─────────────────────────────────────────────

@pytest.fixture
def fake_api() -> MagicMock:
    api = MagicMock()
    api.get_score = AsyncMock(return_value=_score_fixture())
    return api


async def test_run_broadcast_happy_path(fake_api):
    send = AsyncMock()
    summary = await run_broadcast(
        api_client=fake_api,
        send_message=send,
        chat_ids=[1, 2, 3],
        target_date=date(2026, 4, 16),
        send_delay=0,
    )
    assert summary.sent == 3
    assert summary.failed == 0
    assert send.await_count == 3
    assert fake_api.get_score.await_count == 3
    # get_score는 date 인자 전달 확인
    for call in fake_api.get_score.await_args_list:
        assert call.kwargs.get("date") == "2026-04-16"


async def test_run_broadcast_dry_run_does_not_send(fake_api):
    send = AsyncMock()
    summary = await run_broadcast(
        api_client=fake_api,
        send_message=send,
        chat_ids=[1, 2],
        target_date=date(2026, 4, 16),
        dry_run=True,
        send_delay=0,
    )
    assert summary.sent == 2
    assert send.await_count == 0


async def test_run_broadcast_skips_notfound(fake_api):
    fake_api.get_score = AsyncMock(
        side_effect=[
            _score_fixture(),
            NotFoundError(404, "user not found"),
            _score_fixture(),
        ]
    )
    send = AsyncMock()
    summary = await run_broadcast(
        api_client=fake_api,
        send_message=send,
        chat_ids=[1, 2, 3],
        target_date=date(2026, 4, 16),
        send_delay=0,
    )
    assert summary.sent == 2
    assert summary.not_found == 1
    assert send.await_count == 2


async def test_run_broadcast_skips_api_error(fake_api):
    fake_api.get_score = AsyncMock(side_effect=ApiError(500, "boom"))
    send = AsyncMock()
    summary = await run_broadcast(
        api_client=fake_api,
        send_message=send,
        chat_ids=[1, 2],
        target_date=date(2026, 4, 16),
        send_delay=0,
    )
    assert summary.sent == 0
    assert summary.failed == 2
    assert send.await_count == 0


async def test_run_broadcast_handles_forbidden(fake_api):
    class FakeForbidden(Exception): ...

    send = AsyncMock(side_effect=[None, FakeForbidden("blocked"), None])
    summary = await run_broadcast(
        api_client=fake_api,
        send_message=send,
        chat_ids=[1, 2, 3],
        target_date=date(2026, 4, 16),
        forbidden_exc=FakeForbidden,
        send_delay=0,
    )
    assert summary.sent == 2
    assert summary.blocked == 1
    assert summary.failed == 0


async def test_run_broadcast_handles_bad_request(fake_api):
    class FakeBadReq(Exception): ...

    send = AsyncMock(side_effect=FakeBadReq("chat not found"))
    summary = await run_broadcast(
        api_client=fake_api,
        send_message=send,
        chat_ids=[1],
        target_date=date(2026, 4, 16),
        bad_request_exc=FakeBadReq,
        send_delay=0,
    )
    assert summary.sent == 0
    assert summary.bad_request == 1


async def test_run_broadcast_unknown_send_exception_is_failure(fake_api):
    send = AsyncMock(side_effect=RuntimeError("wat"))
    summary = await run_broadcast(
        api_client=fake_api,
        send_message=send,
        chat_ids=[1],
        target_date=date(2026, 4, 16),
        send_delay=0,
    )
    assert summary.sent == 0
    assert summary.failed == 1


async def test_run_broadcast_empty_chat_ids(fake_api):
    send = AsyncMock()
    summary = await run_broadcast(
        api_client=fake_api,
        send_message=send,
        chat_ids=[],
        target_date=date(2026, 4, 16),
        send_delay=0,
    )
    assert summary.total() == 0
    assert send.await_count == 0


# ─────────────────────────────────────────────
# CLI parsing
# ─────────────────────────────────────────────

def test_parse_args_defaults():
    args = _parse_args([])
    assert args.dry_run is False
    assert args.test_chat_id is None
    assert args.date is None


def test_parse_args_all_flags():
    args = _parse_args(["--dry-run", "--test-chat-id", "12345", "--date", "2026-04-20"])
    assert args.dry_run is True
    assert args.test_chat_id == 12345
    assert args.date == "2026-04-20"


# ─────────────────────────────────────────────
# Summary
# ─────────────────────────────────────────────

def test_summary_total_and_log():
    s = BroadcastSummary(sent=3, failed=1, blocked=2, not_found=1, bad_request=0)
    assert s.total() == 7
    assert "sent=3" in s.as_log()
    assert "blocked=2" in s.as_log()


# ─────────────────────────────────────────────
# Week 7: BroadcastSummary 확장 + format_watchlist_summary
# ─────────────────────────────────────────────


def test_broadcast_summary_has_watchlist_fields():
    from sajucandle.broadcast import BroadcastSummary
    s = BroadcastSummary()
    assert s.watchlist_sent == 0
    assert s.watchlist_skipped_empty == 0
    assert s.watchlist_failed == 0
    assert s.precompute_ok == 0
    assert s.precompute_failed == 0


def test_format_watchlist_summary_renders_open_stock():
    from datetime import date
    from sajucandle.broadcast import format_watchlist_summary

    signals = [{
        "ticker": "AAPL",
        "price": {"current": 184.12, "change_pct_24h": 1.23},
        "composite_score": 66,
        "signal_grade": "진입",
        "market_status": {"is_open": True, "category": "us_stock",
                           "last_session_date": "2026-04-16"},
    }]
    card = format_watchlist_summary(signals, date(2026, 4, 17))
    assert "2026-04-17" in card
    assert "관심 종목" in card
    assert "AAPL" in card
    assert "66" in card
    assert "진입" in card
    assert "184.12" in card
    assert "+1.23" in card
    assert "🕐" not in card
    assert "정보 제공" in card


def test_format_watchlist_summary_closed_stock_shows_clock():
    from datetime import date
    from sajucandle.broadcast import format_watchlist_summary

    signals = [{
        "ticker": "TSLA",
        "price": {"current": 215.00, "change_pct_24h": -2.3},
        "composite_score": 45,
        "signal_grade": "관망",
        "market_status": {"is_open": False, "category": "us_stock",
                           "last_session_date": "2026-04-16"},
    }]
    card = format_watchlist_summary(signals, date(2026, 4, 17))
    assert "🕐" in card


def test_format_watchlist_summary_btc_no_clock():
    """crypto는 24/7이라 휴장 아이콘 없음."""
    from datetime import date
    from sajucandle.broadcast import format_watchlist_summary

    signals = [{
        "ticker": "BTCUSDT",
        "price": {"current": 72120.0, "change_pct_24h": 1.5},
        "composite_score": 72,
        "signal_grade": "진입",
        "market_status": {"is_open": True, "category": "crypto",
                           "last_session_date": "2026-04-17"},
    }]
    card = format_watchlist_summary(signals, date(2026, 4, 17))
    assert "🕐" not in card
    # BTCUSDT는 [BTC]로 축약
    assert "[BTC]" in card


def test_format_watchlist_summary_failed_signal():
    """시그널 실패한 심볼은 '데이터 불가'."""
    from datetime import date
    from sajucandle.broadcast import format_watchlist_summary

    signals = [{
        "ticker": "XYZ",
        "error": "데이터 불가",
    }]
    card = format_watchlist_summary(signals, date(2026, 4, 17))
    assert "XYZ" in card
    assert "데이터 불가" in card


def test_format_watchlist_summary_empty_returns_none():
    from datetime import date
    from sajucandle.broadcast import format_watchlist_summary
    assert format_watchlist_summary([], date(2026, 4, 17)) is None


def test_format_watchlist_summary_multiple_mixed():
    from datetime import date
    from sajucandle.broadcast import format_watchlist_summary

    signals = [
        {"ticker": "BTCUSDT",
         "price": {"current": 72000.0, "change_pct_24h": 1.5},
         "composite_score": 72, "signal_grade": "진입",
         "market_status": {"is_open": True, "category": "crypto",
                            "last_session_date": "2026-04-17"}},
        {"ticker": "AAPL",
         "price": {"current": 184.12, "change_pct_24h": 1.2},
         "composite_score": 65, "signal_grade": "진입",
         "market_status": {"is_open": False, "category": "us_stock",
                            "last_session_date": "2026-04-16"}},
        {"ticker": "TSLA", "error": "데이터 불가"},
    ]
    card = format_watchlist_summary(signals, date(2026, 4, 17))
    for t in ["BTC", "AAPL", "TSLA"]:
        assert t in card
    assert card.count("\n") >= 4


# ─────────────────────────────────────────────
# Week 7: Phase 1 Precompute
# ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_precompute_warms_cache_for_all_symbols():
    """run_broadcast 시작 시 admin chat으로 watchlist union 심볼 선조회."""
    from datetime import date
    from unittest.mock import AsyncMock, MagicMock
    from sajucandle.broadcast import run_broadcast

    api_client = MagicMock()
    api_client.get_admin_users = AsyncMock(return_value=[])
    api_client.get_admin_watchlist_symbols = AsyncMock(
        return_value=["AAPL", "TSLA"]
    )
    precompute_calls = []
    async def fake_get_signal(chat_id, ticker=None, date=None):
        precompute_calls.append((chat_id, ticker))
        return {}
    api_client.get_signal = fake_get_signal

    send = AsyncMock()
    summary = await run_broadcast(
        api_client=api_client,
        send_message=send,
        chat_ids=[],
        target_date=date(2026, 4, 17),
        dry_run=True,
        admin_chat_id=7492682272,
    )
    assert len(precompute_calls) == 2
    assert all(c[0] == 7492682272 for c in precompute_calls)
    tickers_called = {c[1] for c in precompute_calls}
    assert tickers_called == {"AAPL", "TSLA"}
    assert summary.precompute_ok == 2
    assert summary.precompute_failed == 0


@pytest.mark.asyncio
async def test_precompute_continues_on_partial_failure():
    """일부 심볼 실패해도 나머지 진행."""
    from datetime import date
    from unittest.mock import AsyncMock, MagicMock
    from sajucandle.api_client import ApiError
    from sajucandle.broadcast import run_broadcast

    api_client = MagicMock()
    api_client.get_admin_users = AsyncMock(return_value=[])
    api_client.get_admin_watchlist_symbols = AsyncMock(
        return_value=["AAPL", "TSLA"]
    )
    async def fake_get_signal(chat_id, ticker=None, date=None):
        if ticker == "AAPL":
            raise ApiError(502, "chart data unavailable")
        return {}
    api_client.get_signal = fake_get_signal

    send = AsyncMock()
    summary = await run_broadcast(
        api_client=api_client,
        send_message=send,
        chat_ids=[],
        target_date=date(2026, 4, 17),
        dry_run=True,
        admin_chat_id=7492682272,
    )
    assert summary.precompute_ok == 1
    assert summary.precompute_failed == 1


@pytest.mark.asyncio
async def test_precompute_skipped_when_admin_chat_id_none():
    """admin_chat_id=None이면 Phase 1 skip."""
    from datetime import date
    from unittest.mock import AsyncMock, MagicMock
    from sajucandle.broadcast import run_broadcast

    api_client = MagicMock()
    api_client.get_admin_users = AsyncMock(return_value=[])
    api_client.get_admin_watchlist_symbols = AsyncMock(return_value=["AAPL"])
    api_client.get_signal = AsyncMock()

    send = AsyncMock()
    summary = await run_broadcast(
        api_client=api_client,
        send_message=send,
        chat_ids=[],
        target_date=date(2026, 4, 17),
        dry_run=True,
        admin_chat_id=None,
    )
    api_client.get_admin_watchlist_symbols.assert_not_called()
    api_client.get_signal.assert_not_called()
    assert summary.precompute_ok == 0
    assert summary.precompute_failed == 0


@pytest.mark.asyncio
async def test_precompute_failure_does_not_abort_phase2():
    """Phase 1 완전 실패해도 Phase 2(사주 카드)는 진행."""
    from datetime import date
    from unittest.mock import AsyncMock, MagicMock
    from sajucandle.api_client import ApiError
    from sajucandle.broadcast import run_broadcast

    api_client = MagicMock()
    api_client.get_admin_users = AsyncMock(return_value=[])
    api_client.get_admin_watchlist_symbols = AsyncMock(
        side_effect=ApiError(500, "db down")
    )
    api_client.get_score = AsyncMock(return_value=_score_fixture())
    api_client.get_signal = AsyncMock()

    send = AsyncMock()
    summary = await run_broadcast(
        api_client=api_client,
        send_message=send,
        chat_ids=[99],
        target_date=date(2026, 4, 17),
        dry_run=True,
        admin_chat_id=7492682272,
    )
    assert summary.precompute_ok == 0
    # Phase 2가 정상 실행됐는지 (get_score 호출 확인)
    api_client.get_score.assert_called_once()


# ─────────────────────────────────────────────
# Week 7: Phase 3 Watchlist 요약
# ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_watchlist_summary_sent_for_user_with_items():
    """watchlist 있는 사용자에게 2번째 메시지로 요약 발송."""
    from datetime import date
    from unittest.mock import AsyncMock, MagicMock
    from sajucandle.broadcast import run_broadcast

    api_client = MagicMock()
    api_client.get_admin_users = AsyncMock(return_value=[99])
    api_client.get_admin_watchlist_symbols = AsyncMock(return_value=[])
    api_client.get_score = AsyncMock(return_value=_score_fixture())

    async def fake_get_watchlist(chat_id):
        return [
            {"ticker": "AAPL", "added_at": "2026-04-16T09:00:00+09:00"},
        ]
    api_client.get_watchlist = fake_get_watchlist

    async def fake_get_signal(chat_id, ticker=None, date=None):
        return {
            "ticker": ticker,
            "price": {"current": 184.12, "change_pct_24h": 1.2},
            "composite_score": 65, "signal_grade": "진입",
            "market_status": {"is_open": True, "category": "us_stock",
                               "last_session_date": "2026-04-16"},
        }
    api_client.get_signal = fake_get_signal

    sent_messages = []
    async def send(chat_id, text):
        sent_messages.append((chat_id, text))

    summary = await run_broadcast(
        api_client=api_client,
        send_message=send,
        chat_ids=[99],
        target_date=date(2026, 4, 17),
        dry_run=False,
        admin_chat_id=None,
        skip_watchlist=False,
    )
    assert len(sent_messages) == 2
    assert "관심 종목" in sent_messages[1][1]
    assert "AAPL" in sent_messages[1][1]
    assert summary.watchlist_sent == 1
    assert summary.watchlist_skipped_empty == 0


@pytest.mark.asyncio
async def test_watchlist_skipped_for_empty_user():
    """watchlist 비어있는 사용자는 1통(사주)만 발송."""
    from datetime import date
    from unittest.mock import AsyncMock, MagicMock
    from sajucandle.broadcast import run_broadcast

    api_client = MagicMock()
    api_client.get_admin_users = AsyncMock(return_value=[99])
    api_client.get_admin_watchlist_symbols = AsyncMock(return_value=[])
    api_client.get_score = AsyncMock(return_value=_score_fixture())
    api_client.get_watchlist = AsyncMock(return_value=[])
    api_client.get_signal = AsyncMock()

    sent_messages = []
    async def send(chat_id, text):
        sent_messages.append((chat_id, text))

    summary = await run_broadcast(
        api_client=api_client,
        send_message=send,
        chat_ids=[99],
        target_date=date(2026, 4, 17),
        dry_run=False,
        admin_chat_id=None,
        skip_watchlist=False,
    )
    assert len(sent_messages) == 1
    assert summary.watchlist_skipped_empty == 1
    assert summary.watchlist_sent == 0


@pytest.mark.asyncio
async def test_watchlist_partial_signal_failure_still_sends():
    """일부 심볼 시그널 실패해도 나머지 포함해 요약 발송."""
    from datetime import date
    from unittest.mock import AsyncMock, MagicMock
    from sajucandle.api_client import ApiError
    from sajucandle.broadcast import run_broadcast

    api_client = MagicMock()
    api_client.get_admin_users = AsyncMock(return_value=[99])
    api_client.get_admin_watchlist_symbols = AsyncMock(return_value=[])
    api_client.get_score = AsyncMock(return_value=_score_fixture())
    api_client.get_watchlist = AsyncMock(return_value=[
        {"ticker": "AAPL", "added_at": "2026-04-16"},
        {"ticker": "TSLA", "added_at": "2026-04-17"},
    ])

    async def fake_get_signal(chat_id, ticker=None, date=None):
        if ticker == "TSLA":
            raise ApiError(502, "chart data unavailable")
        return {
            "ticker": ticker,
            "price": {"current": 184.12, "change_pct_24h": 1.2},
            "composite_score": 65, "signal_grade": "진입",
            "market_status": {"is_open": True, "category": "us_stock",
                               "last_session_date": "2026-04-16"},
        }
    api_client.get_signal = fake_get_signal

    sent_messages = []
    async def send(chat_id, text):
        sent_messages.append((chat_id, text))

    summary = await run_broadcast(
        api_client=api_client,
        send_message=send,
        chat_ids=[99],
        target_date=date(2026, 4, 17),
        dry_run=False,
        admin_chat_id=None,
        skip_watchlist=False,
    )
    assert len(sent_messages) == 2
    assert "데이터 불가" in sent_messages[1][1]
    assert "AAPL" in sent_messages[1][1]
    assert "TSLA" in sent_messages[1][1]
    assert summary.watchlist_sent == 1


@pytest.mark.asyncio
async def test_skip_watchlist_flag_disables_phase3():
    """skip_watchlist=True 시 Phase 3 완전 skip."""
    from datetime import date
    from unittest.mock import AsyncMock, MagicMock
    from sajucandle.broadcast import run_broadcast

    api_client = MagicMock()
    api_client.get_admin_users = AsyncMock(return_value=[99])
    api_client.get_admin_watchlist_symbols = AsyncMock(return_value=[])
    api_client.get_score = AsyncMock(return_value=_score_fixture())
    api_client.get_watchlist = AsyncMock()
    api_client.get_signal = AsyncMock()

    sent_messages = []
    async def send(chat_id, text):
        sent_messages.append((chat_id, text))

    summary = await run_broadcast(
        api_client=api_client,
        send_message=send,
        chat_ids=[99],
        target_date=date(2026, 4, 17),
        dry_run=False,
        admin_chat_id=None,
        skip_watchlist=True,
    )
    api_client.get_watchlist.assert_not_called()
    assert len(sent_messages) == 1
    assert summary.watchlist_sent == 0
    assert summary.watchlist_skipped_empty == 0


@pytest.mark.asyncio
async def test_watchlist_dry_run_does_not_send():
    """dry_run=True면 Phase 3도 전송 skip."""
    from datetime import date
    from unittest.mock import AsyncMock, MagicMock
    from sajucandle.broadcast import run_broadcast

    api_client = MagicMock()
    api_client.get_admin_users = AsyncMock(return_value=[99])
    api_client.get_admin_watchlist_symbols = AsyncMock(return_value=[])
    api_client.get_score = AsyncMock(return_value=_score_fixture())
    api_client.get_watchlist = AsyncMock(return_value=[
        {"ticker": "AAPL", "added_at": "2026-04-16"},
    ])
    api_client.get_signal = AsyncMock(return_value={
        "ticker": "AAPL",
        "price": {"current": 184.12, "change_pct_24h": 1.2},
        "composite_score": 65, "signal_grade": "진입",
        "market_status": {"is_open": True, "category": "us_stock",
                           "last_session_date": "2026-04-16"},
    })

    sent_messages = []
    async def send(chat_id, text):
        sent_messages.append((chat_id, text))

    await run_broadcast(
        api_client=api_client,
        send_message=send,
        chat_ids=[99],
        target_date=date(2026, 4, 17),
        dry_run=True,
        admin_chat_id=None,
        skip_watchlist=False,
    )
    assert len(sent_messages) == 0


def test_cli_parses_skip_watchlist_flag():
    """argparse --skip-watchlist 플래그 파싱."""
    from sajucandle.broadcast import _parse_args
    args = _parse_args(["--skip-watchlist"])
    assert args.skip_watchlist is True


def test_cli_default_skip_watchlist_false():
    from sajucandle.broadcast import _parse_args
    args = _parse_args([])
    assert args.skip_watchlist is False


# ─────────────────────────────────────────────
# Week 8: 톤 완화 + BroadcastSummary 확장
# ─────────────────────────────────────────────


def test_format_morning_card_title_changed_to_myeongsik_reference():
    """제목이 '사주캔들' → '오늘의 명식 참고'."""
    from datetime import date
    from sajucandle.broadcast import format_morning_card

    card = format_morning_card(_score_fixture(), date(2026, 4, 19))
    assert "오늘의 명식 참고" in card
    assert "사주캔들" not in card


def test_format_morning_card_uses_new_disclaimer():
    """끝이 '정보 제공' disclaimer."""
    from datetime import date
    from sajucandle.broadcast import format_morning_card

    card = format_morning_card(_score_fixture(), date(2026, 4, 19))
    assert "정보 제공" in card
    assert "엔터테인먼트" not in card


def test_format_morning_card_has_seongyang_line():
    """'종합: N | grade' 대신 '성향: grade'."""
    from datetime import date
    from sajucandle.broadcast import format_morning_card

    card = format_morning_card(_score_fixture(), date(2026, 4, 19))
    assert "성향:" in card


def test_format_morning_card_cta_includes_watchlist():
    """CTA 줄에 /watchlist 포함."""
    from datetime import date
    from sajucandle.broadcast import format_morning_card

    card = format_morning_card(_score_fixture(), date(2026, 4, 19))
    assert "/watchlist" in card


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


# ─────────────────────────────────────────────
# Week 8: Phase 0 tracking
# ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_phase0_tracking_computes_mfe_mae():
    """run_phase0_tracking: pending row 조회 → MFE/MAE 계산 → update."""
    from datetime import date as _d, datetime, timezone, timedelta
    from unittest.mock import AsyncMock
    from sajucandle.broadcast import run_phase0_tracking
    from sajucandle.repositories import SignalLogRow
    from sajucandle.market_data import Kline

    two_hours_ago = datetime.now(timezone.utc) - timedelta(hours=2)
    pending = [
        SignalLogRow(
            id=101, sent_at=two_hours_ago, source="ondemand",
            telegram_chat_id=99, ticker="BTCUSDT",
            target_date=_d(2026, 4, 19), entry_price=70000.0,
            saju_score=50, analysis_score=70,
            structure_state="uptrend", alignment_bias="bullish",
            rsi_1h=None, volume_ratio_1d=None,
            composite_score=68, signal_grade="진입",
            mfe_7d_pct=None, mae_7d_pct=None,
            close_24h=None, close_7d=None,
            last_tracked_at=None, tracking_done=False,
        ),
    ]

    # post-entry klines: entry=70000 → high=72500, low=69500
    post = [
        Kline(open_time=two_hours_ago + timedelta(minutes=30),
              open=71000, high=72000, low=69500, close=71500, volume=1000),
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
    # update_tracking 호출 인자 검증
    _, kwargs = update_tracking.call_args
    # mfe = (72500/70000 - 1) * 100 ≈ 3.571
    assert kwargs["mfe_pct"] == pytest.approx(3.571, abs=0.01)
    # mae = (69500/70000 - 1) * 100 ≈ -0.714
    assert kwargs["mae_pct"] == pytest.approx(-0.714, abs=0.01)
    assert kwargs["tracking_done"] is False


@pytest.mark.asyncio
async def test_run_phase0_tracking_marks_done_after_7d():
    from datetime import date as _d, datetime, timezone, timedelta
    from unittest.mock import AsyncMock
    from sajucandle.broadcast import run_phase0_tracking
    from sajucandle.repositories import SignalLogRow
    from sajucandle.market_data import Kline

    eight_days_ago = datetime.now(timezone.utc) - timedelta(days=8)
    pending = [
        SignalLogRow(
            id=102, sent_at=eight_days_ago, source="ondemand",
            telegram_chat_id=99, ticker="BTCUSDT",
            target_date=_d(2026, 4, 10), entry_price=70000.0,
            saju_score=50, analysis_score=70,
            structure_state="uptrend", alignment_bias="bullish",
            rsi_1h=None, volume_ratio_1d=None,
            composite_score=68, signal_grade="진입",
            mfe_7d_pct=None, mae_7d_pct=None,
            close_24h=None, close_7d=None,
            last_tracked_at=None, tracking_done=False,
        ),
    ]
    post = [
        Kline(open_time=eight_days_ago + timedelta(hours=1),
              open=70000, high=75000, low=69000, close=74000, volume=1000),
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
    _, kwargs = update_tracking.call_args
    assert kwargs["tracking_done"] is True
    assert result["completed"] == 1


@pytest.mark.asyncio
async def test_run_phase0_tracking_list_pending_exception_returns_empty_summary():
    """list_pending 실패 시 updated=failed=completed=0."""
    from datetime import datetime, timezone
    from unittest.mock import AsyncMock
    from sajucandle.broadcast import run_phase0_tracking

    async def fail_list(**kwargs):
        raise RuntimeError("db down")

    result = await run_phase0_tracking(
        list_pending=fail_list,
        update_tracking=AsyncMock(),
        get_klines=AsyncMock(),
        now=datetime.now(timezone.utc),
    )
    assert result["updated"] == 0
    assert result["failed"] == 0


@pytest.mark.asyncio
async def test_run_phase0_tracking_per_row_exception_counts_failed():
    """row별 update 실패 → failed 카운트."""
    from datetime import date as _d, datetime, timezone, timedelta
    from unittest.mock import AsyncMock
    from sajucandle.broadcast import run_phase0_tracking
    from sajucandle.repositories import SignalLogRow

    two_hours_ago = datetime.now(timezone.utc) - timedelta(hours=2)
    pending = [
        SignalLogRow(
            id=103, sent_at=two_hours_ago, source="ondemand",
            telegram_chat_id=99, ticker="BTCUSDT",
            target_date=_d(2026, 4, 19), entry_price=70000.0,
            saju_score=50, analysis_score=70,
            structure_state="uptrend", alignment_bias="bullish",
            rsi_1h=None, volume_ratio_1d=None,
            composite_score=68, signal_grade="진입",
            mfe_7d_pct=None, mae_7d_pct=None,
            close_24h=None, close_7d=None,
            last_tracked_at=None, tracking_done=False,
        ),
    ]

    async def fail_get_klines(ticker, sent_at):
        raise RuntimeError("network")

    result = await run_phase0_tracking(
        list_pending=AsyncMock(return_value=pending),
        update_tracking=AsyncMock(),
        get_klines=fail_get_klines,
        now=datetime.now(timezone.utc),
    )
    assert result["failed"] == 1
    assert result["updated"] == 0


# ─────────────────────────────────────────────
# Week 9: Phase 0 default callback이 admin ohlcv 호출
# ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_phase0_default_get_klines_calls_admin_ohlcv():
    """run_broadcast default _get_klines가 api_client.get_admin_ohlcv 호출."""
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
    api_client.get_admin_ohlcv = AsyncMock(return_value=[
        {
            "open_time": (two_hours_ago + timedelta(minutes=30)).isoformat(),
            "open": 71000, "high": 72000, "low": 70500,
            "close": 71500, "volume": 1000,
        },
    ])
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
    api_client.get_admin_ohlcv.assert_called()
    update_tracking.assert_called()
    assert summary.tracking_updated >= 1

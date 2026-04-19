"""핸들러 테스트. api_client를 monkeypatch로 목킹."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from sajucandle import handlers
from sajucandle.api_client import ApiError, NotFoundError


def _update(text: str, chat_id: int = 12345):
    """최소 Update + Message 목."""
    msg = MagicMock()
    msg.reply_text = AsyncMock()
    msg.text = text
    msg.chat_id = chat_id
    upd = MagicMock()
    upd.message = msg
    upd.effective_chat.id = chat_id
    return upd


def _ctx(args: list[str]):
    ctx = MagicMock()
    ctx.args = args
    return ctx


# ── parse_birth_args (기존 테스트 유지) ──

def test_parse_birth_args_valid():
    assert handlers.parse_birth_args(["1990-03-15", "14:00"]) == (1990, 3, 15, 14, 0)


def test_parse_birth_args_with_seconds_ignored():
    assert handlers.parse_birth_args(["1990-03-15", "14:00:30"]) == (1990, 3, 15, 14, 0)


def test_parse_birth_args_hour_only():
    assert handlers.parse_birth_args(["1990-03-15", "14"]) == (1990, 3, 15, 14, 0)


def test_parse_birth_args_empty_raises():
    with pytest.raises(handlers.BirthParseError):
        handlers.parse_birth_args([])


def test_parse_birth_args_missing_time_raises():
    with pytest.raises(handlers.BirthParseError):
        handlers.parse_birth_args(["1990-03-15"])


def test_parse_birth_args_bad_date_format_raises():
    with pytest.raises(handlers.BirthParseError):
        handlers.parse_birth_args(["1990/03/15", "14:00"])


def test_parse_birth_args_invalid_hour_raises():
    with pytest.raises(handlers.BirthParseError):
        handlers.parse_birth_args(["1990-03-15", "25:00"])


def test_parse_birth_args_invalid_month_raises():
    with pytest.raises(handlers.BirthParseError):
        handlers.parse_birth_args(["1990-13-15", "14:00"])


# ── /start ──

async def test_start_with_no_args_shows_help():
    upd = _update("/start")
    await handlers.start_command(upd, _ctx([]))
    upd.message.reply_text.assert_awaited_once()
    call_text = upd.message.reply_text.await_args.args[0]
    assert "/start" in call_text


async def test_start_valid_calls_put_user_and_replies_card(monkeypatch):
    fake = MagicMock()
    fake.put_user = AsyncMock(return_value={
        "telegram_chat_id": 12345,
        "birth_year": 1990, "birth_month": 3, "birth_day": 15,
        "birth_hour": 14, "birth_minute": 0,
        "asset_class_pref": "swing",
        "created_at": "2026-04-16T00:00:00Z",
        "updated_at": "2026-04-16T00:00:00Z",
    })
    monkeypatch.setattr(handlers, "_api_client", fake)

    upd = _update("/start 1990-03-15 14:00")
    await handlers.start_command(upd, _ctx(["1990-03-15", "14:00"]))

    fake.put_user.assert_awaited_once()
    call_kwargs = fake.put_user.await_args.kwargs
    assert call_kwargs["birth_year"] == 1990
    upd.message.reply_text.assert_awaited_once()


# ── /score ──

async def test_score_replies_with_score(monkeypatch):
    fake = MagicMock()
    fake.get_score = AsyncMock(return_value={
        "chat_id": 12345,
        "date": "2026-04-16",
        "asset_class": "swing",
        "iljin": "庚申",
        "composite_score": 72,
        "signal_grade": "👍 진입각",
        "axes": {
            "wealth":     {"score": 78, "reason": "재성 투간"},
            "decision":   {"score": 65, "reason": ""},
            "volatility": {"score": 70, "reason": ""},
            "flow":       {"score": 75, "reason": ""},
        },
        "best_hours": [
            {"shichen": "巳", "time_range": "09:00~11:00", "multiplier": 1.15},
        ],
    })
    monkeypatch.setattr(handlers, "_api_client", fake)

    upd = _update("/score")
    await handlers.score_command(upd, _ctx([]))

    fake.get_score.assert_awaited_once_with(12345, date=None, asset=None)
    text = upd.message.reply_text.await_args.args[0]
    assert "72" in text
    assert "진입각" in text


async def test_score_404_tells_user_to_register(monkeypatch):
    fake = MagicMock()
    fake.get_score = AsyncMock(side_effect=NotFoundError(404, "user not found"))
    monkeypatch.setattr(handlers, "_api_client", fake)

    upd = _update("/score")
    await handlers.score_command(upd, _ctx([]))

    text = upd.message.reply_text.await_args.args[0]
    assert "/start" in text


async def test_score_with_asset_arg(monkeypatch):
    fake = MagicMock()
    fake.get_score = AsyncMock(return_value={
        "chat_id": 12345, "date": "2026-04-16", "asset_class": "scalp",
        "iljin": "甲子", "composite_score": 50, "signal_grade": "😐 관망",
        "axes": {
            "wealth": {"score": 50, "reason": ""},
            "decision": {"score": 50, "reason": ""},
            "volatility": {"score": 50, "reason": ""},
            "flow": {"score": 50, "reason": ""},
        },
        "best_hours": [],
    })
    monkeypatch.setattr(handlers, "_api_client", fake)

    await handlers.score_command(_update("/score scalp"), _ctx(["scalp"]))
    fake.get_score.assert_awaited_once_with(12345, date=None, asset="scalp")


# ── /me ──

async def test_me_shows_profile(monkeypatch):
    fake = MagicMock()
    fake.get_user = AsyncMock(return_value={
        "telegram_chat_id": 12345,
        "birth_year": 1990, "birth_month": 3, "birth_day": 15,
        "birth_hour": 14, "birth_minute": 0,
        "asset_class_pref": "swing",
        "created_at": "2026-04-16T00:00:00Z",
        "updated_at": "2026-04-16T00:00:00Z",
    })
    monkeypatch.setattr(handlers, "_api_client", fake)

    upd = _update("/me")
    await handlers.me_command(upd, _ctx([]))
    fake.get_user.assert_awaited_once_with(12345)
    text = upd.message.reply_text.await_args.args[0]
    assert "1990" in text
    assert "swing" in text


async def test_me_404(monkeypatch):
    fake = MagicMock()
    fake.get_user = AsyncMock(side_effect=NotFoundError(404, "nope"))
    monkeypatch.setattr(handlers, "_api_client", fake)

    upd = _update("/me")
    await handlers.me_command(upd, _ctx([]))
    assert "/start" in upd.message.reply_text.await_args.args[0]


# ── /forget ──

async def test_forget_deletes(monkeypatch):
    fake = MagicMock()
    fake.delete_user = AsyncMock(return_value=None)
    monkeypatch.setattr(handlers, "_api_client", fake)

    upd = _update("/forget")
    await handlers.forget_command(upd, _ctx([]))
    fake.delete_user.assert_awaited_once_with(12345)
    assert upd.message.reply_text.await_count == 1


# ── /signal ──

def _signal_payload():
    return {
        "chat_id": 12345, "ticker": "BTCUSDT", "date": "2026-04-16",
        "price": {"current": 67432.1, "change_pct_24h": 2.15},
        "saju": {"composite": 55, "grade": "🔄 관망"},
        "chart": {
            "score": 72, "rsi": 58.2, "ma20": 65100.0, "ma50": 62300.0,
            "ma_trend": "up", "volume_ratio": 1.3,
            "reason": "RSI 58(중립), MA20>MA50, 볼륨→",
        },
        "composite_score": 65, "signal_grade": "진입",
        "best_hours": [
            {"shichen": "寅", "time_range": "03:00~05:00", "multiplier": 1.1},
        ],
        "analysis": {
            "structure": {"state": "uptrend", "score": 70},
            "alignment": {
                "tf_1h": "up", "tf_4h": "up", "tf_1d": "up",
                "aligned": True, "bias": "bullish", "score": 90,
            },
            "rsi_1h": 58.2,
            "volume_ratio_1d": 1.3,
            "composite_score": 72,
            "reason": "1d↑ 4h↑ 1h↑ (강정렬) · RSI(1h) 58 · 볼륨→",
        },
    }


async def test_signal_replies_with_combined_card(monkeypatch):
    fake = MagicMock()
    fake.get_signal = AsyncMock(return_value=_signal_payload())
    monkeypatch.setattr(handlers, "_api_client", fake)

    upd = _update("/signal")
    await handlers.signal_command(upd, _ctx([]))
    fake.get_signal.assert_awaited_once_with(12345, ticker="BTCUSDT")
    text = upd.message.reply_text.await_args.args[0]
    assert "BTCUSDT" in text
    assert "65" in text  # composite
    assert "진입" in text  # grade
    assert "67,432" in text  # price formatted
    assert "RSI" in text


async def test_signal_404_tells_user_to_register(monkeypatch):
    fake = MagicMock()
    fake.get_signal = AsyncMock(side_effect=NotFoundError(404, "user not found"))
    monkeypatch.setattr(handlers, "_api_client", fake)

    upd = _update("/signal")
    await handlers.signal_command(upd, _ctx([]))
    assert "/start" in upd.message.reply_text.await_args.args[0]


async def test_signal_502_market_unavailable(monkeypatch):
    fake = MagicMock()
    fake.get_signal = AsyncMock(
        side_effect=ApiError(502, "chart data unavailable")
    )
    monkeypatch.setattr(handlers, "_api_client", fake)

    upd = _update("/signal")
    await handlers.signal_command(upd, _ctx([]))
    text = upd.message.reply_text.await_args.args[0]
    assert "시장 데이터" in text


async def test_signal_generic_500(monkeypatch):
    fake = MagicMock()
    fake.get_signal = AsyncMock(side_effect=ApiError(500, "boom"))
    monkeypatch.setattr(handlers, "_api_client", fake)

    upd = _update("/signal")
    await handlers.signal_command(upd, _ctx([]))
    text = upd.message.reply_text.await_args.args[0]
    assert "500" in text


# ── /help ──

async def test_help_lists_commands():
    upd = _update("/help")
    await handlers.help_command(upd, _ctx([]))
    text = upd.message.reply_text.await_args.args[0]
    for cmd in ("/start", "/score", "/signal", "/me", "/forget"):
        assert cmd in text


# ─────────────────────────────────────────────
# Week 6: /signal 심볼 인자, /signal list, 배지
# ─────────────────────────────────────────────

def _make_update(text: str, chat_id: int):
    """가짜 Telegram Update 객체. chat_id + message.text."""
    from unittest.mock import MagicMock
    update = MagicMock()
    update.message = MagicMock()
    update.message.text = text
    update.effective_chat = MagicMock()
    update.effective_chat.id = chat_id
    return update


def _btc_signal_payload() -> dict:
    return {
        "ticker": "BTCUSDT",
        "date": "2026-04-16",
        "price": {"current": 72000.0, "change_pct_24h": 1.5},
        "saju": {"composite": 56, "grade": "😐 관망"},
        "chart": {"score": 72, "rsi": 60.0, "ma20": 71000.0, "ma50": 69000.0,
                  "ma_trend": "up", "volume_ratio": 1.2,
                  "reason": "MA 우상향"},
        "composite_score": 66,
        "signal_grade": "진입",
        "best_hours": [],
        "market_status": {"is_open": True, "last_session_date": "2026-04-16",
                          "category": "crypto"},
        "analysis": {
            "structure": {"state": "uptrend", "score": 70},
            "alignment": {
                "tf_1h": "up", "tf_4h": "up", "tf_1d": "up",
                "aligned": True, "bias": "bullish", "score": 90,
            },
            "rsi_1h": 60.0,
            "volume_ratio_1d": 1.2,
            "composite_score": 72,
            "reason": "1d↑ 4h↑ 1h↑ (강정렬) · RSI(1h) 60 · 볼륨→",
        },
    }


def _aapl_signal_payload() -> dict:
    return {
        "ticker": "AAPL",
        "date": "2026-04-16",
        "price": {"current": 184.12, "change_pct_24h": 1.23},
        "saju": {"composite": 56, "grade": "😐 관망"},
        "chart": {"score": 72, "rsi": 62.0, "ma20": 180.0, "ma50": 175.0,
                  "ma_trend": "up", "volume_ratio": 1.1,
                  "reason": "MA 우상향, RSI 62"},
        "composite_score": 66,
        "signal_grade": "진입",
        "best_hours": [],
        "market_status": {"is_open": True, "last_session_date": "2026-04-16",
                          "category": "us_stock"},
        "analysis": {
            "structure": {"state": "uptrend", "score": 70},
            "alignment": {
                "tf_1h": "up", "tf_4h": "up", "tf_1d": "up",
                "aligned": True, "bias": "bullish", "score": 90,
            },
            "rsi_1h": 62.0,
            "volume_ratio_1d": 1.1,
            "composite_score": 72,
            "reason": "1d↑ 4h↑ 1h↑ (강정렬) · RSI(1h) 62 · 볼륨→",
            "sr_levels": [],            # Week 9 default
            "trade_setup": None,        # Week 9 default
        },
    }


@pytest.mark.asyncio
async def test_signal_no_arg_uses_btcusdt(monkeypatch):
    """`/signal` (인자 없음) → ticker=BTCUSDT."""
    from sajucandle import handlers
    from unittest.mock import AsyncMock, MagicMock

    captured = {}
    async def fake_get_signal(chat_id, ticker="BTCUSDT", date=None):
        captured["ticker"] = ticker
        return _btc_signal_payload()

    monkeypatch.setattr(handlers, "_api_client",
                        MagicMock(get_signal=fake_get_signal))

    update = _make_update(text="/signal", chat_id=42)
    context = MagicMock(args=[])
    update.message.reply_text = AsyncMock()

    await handlers.signal_command(update, context)
    assert captured["ticker"] == "BTCUSDT"


@pytest.mark.asyncio
async def test_signal_aapl_routes_to_stock(monkeypatch):
    """`/signal AAPL` → ticker=AAPL."""
    from sajucandle import handlers
    from unittest.mock import AsyncMock, MagicMock

    captured = {}
    async def fake_get_signal(chat_id, ticker="BTCUSDT", date=None):
        captured["ticker"] = ticker
        return _aapl_signal_payload()

    monkeypatch.setattr(handlers, "_api_client",
                        MagicMock(get_signal=fake_get_signal))

    update = _make_update(text="/signal AAPL", chat_id=42)
    context = MagicMock(args=["AAPL"])
    update.message.reply_text = AsyncMock()

    await handlers.signal_command(update, context)
    assert captured["ticker"] == "AAPL"


@pytest.mark.asyncio
async def test_signal_lowercase_aapl_is_normalized(monkeypatch):
    """`/signal aapl` → AAPL."""
    from sajucandle import handlers
    from unittest.mock import AsyncMock, MagicMock

    captured = {}
    async def fake_get_signal(chat_id, ticker="BTCUSDT", date=None):
        captured["ticker"] = ticker
        return _aapl_signal_payload()

    monkeypatch.setattr(handlers, "_api_client",
                        MagicMock(get_signal=fake_get_signal))
    context = MagicMock(args=["aapl"])
    update = _make_update(text="/signal aapl", chat_id=42)
    update.message.reply_text = AsyncMock()

    await handlers.signal_command(update, context)
    assert captured["ticker"] == "AAPL"


@pytest.mark.asyncio
async def test_signal_dollar_prefix_stripped(monkeypatch):
    """`/signal $AAPL` → AAPL."""
    from sajucandle import handlers
    from unittest.mock import AsyncMock, MagicMock

    captured = {}
    async def fake_get_signal(chat_id, ticker="BTCUSDT", date=None):
        captured["ticker"] = ticker
        return _aapl_signal_payload()

    monkeypatch.setattr(handlers, "_api_client",
                        MagicMock(get_signal=fake_get_signal))
    context = MagicMock(args=["$AAPL"])
    update = _make_update(text="/signal $AAPL", chat_id=42)
    update.message.reply_text = AsyncMock()

    await handlers.signal_command(update, context)
    assert captured["ticker"] == "AAPL"


@pytest.mark.asyncio
async def test_signal_list_fetches_catalog(monkeypatch):
    """`/signal list` → get_supported_symbols 호출 + 메시지에 티커 포함."""
    from sajucandle import handlers
    from unittest.mock import AsyncMock, MagicMock

    async def fake_symbols():
        return [
            {"ticker": "BTCUSDT", "name": "Bitcoin", "category": "crypto"},
            {"ticker": "AAPL", "name": "Apple", "category": "us_stock"},
        ]

    monkeypatch.setattr(handlers, "_api_client",
                        MagicMock(get_supported_symbols=fake_symbols,
                                  get_signal=AsyncMock()))
    context = MagicMock(args=["list"])
    update = _make_update(text="/signal list", chat_id=42)
    update.message.reply_text = AsyncMock()

    await handlers.signal_command(update, context)
    sent = update.message.reply_text.call_args[0][0]
    assert "BTCUSDT" in sent
    assert "AAPL" in sent


@pytest.mark.asyncio
async def test_signal_unknown_symbol_shows_list_hint(monkeypatch):
    """`/signal UNKNOWN` → API 400 → 안내 문구."""
    from sajucandle import handlers
    from sajucandle.api_client import ApiError
    from unittest.mock import AsyncMock, MagicMock

    async def fake_get_signal(chat_id, ticker="BTCUSDT", date=None):
        raise ApiError(400, "unsupported ticker: UNKNOWN")

    monkeypatch.setattr(handlers, "_api_client",
                        MagicMock(get_signal=fake_get_signal))
    context = MagicMock(args=["UNKNOWN"])
    update = _make_update(text="/signal UNKNOWN", chat_id=42)
    update.message.reply_text = AsyncMock()

    await handlers.signal_command(update, context)
    sent = update.message.reply_text.call_args[0][0]
    assert "지원하지 않" in sent or "list" in sent.lower()


@pytest.mark.asyncio
async def test_signal_aapl_card_shows_closed_badge(monkeypatch):
    """휴장 상태의 AAPL 응답 → 카드에 '휴장 중' + 기준 날짜 포함."""
    from sajucandle import handlers
    from unittest.mock import AsyncMock, MagicMock

    payload = _aapl_signal_payload()
    payload["market_status"] = {
        "is_open": False,
        "last_session_date": "2026-04-16",
        "category": "us_stock",
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
    assert "휴장" in sent
    assert "2026-04-16" in sent


@pytest.mark.asyncio
async def test_signal_btc_card_has_no_badge_line(monkeypatch):
    """BTC 응답은 배지 줄을 표시하지 않는다 (기존 포맷 유지)."""
    from sajucandle import handlers
    from unittest.mock import AsyncMock, MagicMock

    payload = _btc_signal_payload()
    payload["market_status"] = {
        "is_open": True,
        "last_session_date": "2026-04-16",
        "category": "crypto",
    }

    async def fake_get_signal(chat_id, ticker="BTCUSDT", date=None):
        return payload

    monkeypatch.setattr(handlers, "_api_client",
                        MagicMock(get_signal=fake_get_signal))
    context = MagicMock(args=[])
    update = _make_update(text="/signal", chat_id=42)
    update.message.reply_text = AsyncMock()

    await handlers.signal_command(update, context)
    sent = update.message.reply_text.call_args[0][0]
    assert "휴장" not in sent
    assert "장 중" not in sent


# ─────────────────────────────────────────────
# Week 7: /watch /unwatch /watchlist
# ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_watch_success(monkeypatch):
    from sajucandle import handlers
    from unittest.mock import AsyncMock, MagicMock

    captured = {}
    async def fake_add(chat_id, ticker):
        captured["ticker"] = ticker

    monkeypatch.setattr(
        handlers, "_api_client",
        MagicMock(
            add_watchlist=fake_add,
            get_watchlist=AsyncMock(return_value=[{"ticker": "AAPL"}]),
        ),
    )
    context = MagicMock(args=["AAPL"])
    update = _make_update(text="/watch AAPL", chat_id=42)
    update.message.reply_text = AsyncMock()

    await handlers.watch_command(update, context)
    assert captured["ticker"] == "AAPL"
    sent = update.message.reply_text.call_args[0][0]
    assert "AAPL" in sent
    assert "추가" in sent
    assert "/5" in sent


@pytest.mark.asyncio
async def test_watch_normalizes_lowercase_and_dollar(monkeypatch):
    from sajucandle import handlers
    from unittest.mock import AsyncMock, MagicMock

    captured = {}
    async def fake_add(chat_id, ticker):
        captured["ticker"] = ticker

    monkeypatch.setattr(
        handlers, "_api_client",
        MagicMock(
            add_watchlist=fake_add,
            get_watchlist=AsyncMock(return_value=[]),
        ),
    )
    context = MagicMock(args=["$aapl"])
    update = _make_update(text="/watch $aapl", chat_id=42)
    update.message.reply_text = AsyncMock()

    await handlers.watch_command(update, context)
    assert captured["ticker"] == "AAPL"


@pytest.mark.asyncio
async def test_watch_no_args_shows_usage(monkeypatch):
    from sajucandle import handlers
    from unittest.mock import AsyncMock, MagicMock

    monkeypatch.setattr(handlers, "_api_client", MagicMock())
    context = MagicMock(args=[])
    update = _make_update(text="/watch", chat_id=42)
    update.message.reply_text = AsyncMock()

    await handlers.watch_command(update, context)
    sent = update.message.reply_text.call_args[0][0]
    assert "사용법" in sent


@pytest.mark.asyncio
async def test_watch_full_409(monkeypatch):
    from sajucandle import handlers
    from sajucandle.api_client import ApiError
    from unittest.mock import AsyncMock, MagicMock

    async def fake_add(chat_id, ticker):
        raise ApiError(409, "watchlist full (max 5)")

    monkeypatch.setattr(
        handlers, "_api_client",
        MagicMock(add_watchlist=fake_add),
    )
    context = MagicMock(args=["AAPL"])
    update = _make_update(text="/watch AAPL", chat_id=42)
    update.message.reply_text = AsyncMock()

    await handlers.watch_command(update, context)
    sent = update.message.reply_text.call_args[0][0]
    assert "최대 5개" in sent


@pytest.mark.asyncio
async def test_watch_already_409(monkeypatch):
    from sajucandle import handlers
    from sajucandle.api_client import ApiError
    from unittest.mock import AsyncMock, MagicMock

    async def fake_add(chat_id, ticker):
        raise ApiError(409, "already in watchlist")

    monkeypatch.setattr(
        handlers, "_api_client",
        MagicMock(add_watchlist=fake_add),
    )
    context = MagicMock(args=["AAPL"])
    update = _make_update(text="/watch AAPL", chat_id=42)
    update.message.reply_text = AsyncMock()

    await handlers.watch_command(update, context)
    sent = update.message.reply_text.call_args[0][0]
    assert "이미" in sent


@pytest.mark.asyncio
async def test_watch_unsupported_400(monkeypatch):
    from sajucandle import handlers
    from sajucandle.api_client import ApiError
    from unittest.mock import AsyncMock, MagicMock

    async def fake_add(chat_id, ticker):
        raise ApiError(400, "unsupported ticker: AMZN")

    monkeypatch.setattr(
        handlers, "_api_client",
        MagicMock(add_watchlist=fake_add),
    )
    context = MagicMock(args=["AMZN"])
    update = _make_update(text="/watch AMZN", chat_id=42)
    update.message.reply_text = AsyncMock()

    await handlers.watch_command(update, context)
    sent = update.message.reply_text.call_args[0][0]
    assert "지원하지 않" in sent
    assert "/signal list" in sent


@pytest.mark.asyncio
async def test_watch_user_not_registered_404(monkeypatch):
    from sajucandle import handlers
    from sajucandle.api_client import NotFoundError
    from unittest.mock import AsyncMock, MagicMock

    async def fake_add(chat_id, ticker):
        raise NotFoundError(404, "user not found")

    monkeypatch.setattr(
        handlers, "_api_client",
        MagicMock(add_watchlist=fake_add),
    )
    context = MagicMock(args=["AAPL"])
    update = _make_update(text="/watch AAPL", chat_id=42)
    update.message.reply_text = AsyncMock()

    await handlers.watch_command(update, context)
    sent = update.message.reply_text.call_args[0][0]
    assert "생년월일" in sent


@pytest.mark.asyncio
async def test_unwatch_success(monkeypatch):
    from sajucandle import handlers
    from unittest.mock import AsyncMock, MagicMock

    captured = {}
    async def fake_remove(chat_id, ticker):
        captured["ticker"] = ticker

    monkeypatch.setattr(
        handlers, "_api_client",
        MagicMock(remove_watchlist=fake_remove),
    )
    context = MagicMock(args=["AAPL"])
    update = _make_update(text="/unwatch AAPL", chat_id=42)
    update.message.reply_text = AsyncMock()

    await handlers.unwatch_command(update, context)
    assert captured["ticker"] == "AAPL"
    sent = update.message.reply_text.call_args[0][0]
    assert "🗑️" in sent or "제거" in sent


@pytest.mark.asyncio
async def test_unwatch_missing_404(monkeypatch):
    from sajucandle import handlers
    from sajucandle.api_client import NotFoundError
    from unittest.mock import AsyncMock, MagicMock

    async def fake_remove(chat_id, ticker):
        raise NotFoundError(404, "not in watchlist")

    monkeypatch.setattr(
        handlers, "_api_client",
        MagicMock(remove_watchlist=fake_remove),
    )
    context = MagicMock(args=["AAPL"])
    update = _make_update(text="/unwatch AAPL", chat_id=42)
    update.message.reply_text = AsyncMock()

    await handlers.unwatch_command(update, context)
    sent = update.message.reply_text.call_args[0][0]
    assert "없습니다" in sent or "없" in sent


@pytest.mark.asyncio
async def test_unwatch_no_args_shows_usage(monkeypatch):
    from sajucandle import handlers
    from unittest.mock import AsyncMock, MagicMock

    monkeypatch.setattr(handlers, "_api_client", MagicMock())
    context = MagicMock(args=[])
    update = _make_update(text="/unwatch", chat_id=42)
    update.message.reply_text = AsyncMock()

    await handlers.unwatch_command(update, context)
    sent = update.message.reply_text.call_args[0][0]
    assert "사용법" in sent


@pytest.mark.asyncio
async def test_watchlist_empty(monkeypatch):
    from sajucandle import handlers
    from unittest.mock import AsyncMock, MagicMock

    async def fake_list(chat_id):
        return []

    monkeypatch.setattr(
        handlers, "_api_client",
        MagicMock(get_watchlist=fake_list),
    )
    context = MagicMock(args=[])
    update = _make_update(text="/watchlist", chat_id=42)
    update.message.reply_text = AsyncMock()

    await handlers.watchlist_command(update, context)
    sent = update.message.reply_text.call_args[0][0]
    assert "비어있" in sent
    assert "/watch" in sent


@pytest.mark.asyncio
async def test_watchlist_renders_items(monkeypatch):
    from sajucandle import handlers
    from unittest.mock import AsyncMock, MagicMock

    async def fake_list(chat_id):
        return [
            {"ticker": "BTCUSDT", "added_at": "2026-04-15T09:00:00+09:00"},
            {"ticker": "AAPL", "added_at": "2026-04-16T10:00:00+09:00"},
            {"ticker": "TSLA", "added_at": "2026-04-17T11:00:00+09:00"},
        ]

    monkeypatch.setattr(
        handlers, "_api_client",
        MagicMock(get_watchlist=fake_list),
    )
    context = MagicMock(args=[])
    update = _make_update(text="/watchlist", chat_id=42)
    update.message.reply_text = AsyncMock()

    await handlers.watchlist_command(update, context)
    sent = update.message.reply_text.call_args[0][0]
    assert "3/5" in sent
    assert "BTCUSDT" in sent
    assert "AAPL" in sent
    assert "TSLA" in sent
    assert "Bitcoin" in sent or "Apple" in sent


@pytest.mark.asyncio
async def test_help_includes_watch_commands(monkeypatch):
    from sajucandle import handlers
    from unittest.mock import AsyncMock, MagicMock

    context = MagicMock(args=[])
    update = _make_update(text="/help", chat_id=42)
    update.message.reply_text = AsyncMock()

    await handlers.help_command(update, context)
    sent = update.message.reply_text.call_args[0][0]
    assert "/watch" in sent
    assert "/unwatch" in sent
    assert "/watchlist" in sent


# ─────────────────────────────────────────────
# Week 8: 새 카드 포맷 (구조/정렬/진입조건 + DISCLAIMER 교체)
# ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_signal_card_shows_structure_alignment_entry(monkeypatch):
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
    assert "상승추세" in sent
    assert "정렬:" in sent
    assert "1d" in sent
    assert "진입조건:" in sent or "RSI" in sent


@pytest.mark.asyncio
async def test_signal_card_uses_new_disclaimer(monkeypatch):
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
        "composite_score": 50, "reason": "...",
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
    from sajucandle import handlers
    from unittest.mock import AsyncMock, MagicMock

    payload = _aapl_signal_payload()
    payload["saju"] = {"composite": 56, "grade": "😐 관망"}
    payload["analysis"] = {
        "structure": {"state": "uptrend", "score": 70},
        "alignment": {"tf_1h": "up", "tf_4h": "up", "tf_1d": "up",
                      "aligned": True, "bias": "bullish", "score": 90},
        "rsi_1h": 40.0, "volume_ratio_1d": 1.2,
        "composite_score": 72, "reason": "...",
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
    assert "손절" not in sent


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

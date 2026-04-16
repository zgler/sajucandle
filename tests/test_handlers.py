"""핸들러 테스트. api_client를 monkeypatch로 목킹."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from sajucandle import handlers
from sajucandle.api_client import NotFoundError


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


# ── /help ──

async def test_help_lists_commands():
    upd = _update("/help")
    await handlers.help_command(upd, _ctx([]))
    text = upd.message.reply_text.await_args.args[0]
    for cmd in ("/start", "/score", "/me", "/forget"):
        assert cmd in text

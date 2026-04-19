"""Telegram 커맨드 핸들러. API 호출만 수행, 엔진/DB 직접 접근 금지."""
from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Optional

import httpx
from telegram import Update
from telegram.ext import ContextTypes

from sajucandle.api_client import ApiClient, ApiError, NotFoundError
from sajucandle.format import DISCLAIMER

logger = logging.getLogger(__name__)


class BirthParseError(ValueError):
    """사용자 생년월일시 인자 파싱 실패."""


def parse_birth_args(args: list[str]) -> tuple[int, int, int, int, int]:
    """`/start YYYY-MM-DD HH:MM` → (year, month, day, hour, minute).

    허용 포맷:
      - `YYYY-MM-DD HH:MM`
      - `YYYY-MM-DD HH:MM:SS` (초는 무시)
      - `YYYY-MM-DD HH`       (분 = 0)
    """
    if len(args) < 2:
        raise BirthParseError(
            "사용법: /start YYYY-MM-DD HH:MM\n예: /start 1990-03-15 14:00"
        )
    date_str, time_str = args[0], args[1]
    try:
        date_part = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError as e:
        raise BirthParseError(
            f"날짜 형식이 잘못되었습니다 (YYYY-MM-DD): {date_str}"
        ) from e
    time_part = None
    for fmt in ("%H:%M:%S", "%H:%M", "%H"):
        try:
            time_part = datetime.strptime(time_str, fmt).time()
            break
        except ValueError:
            continue
    if time_part is None:
        raise BirthParseError(f"시각 형식이 잘못되었습니다 (HH:MM): {time_str}")
    return (
        date_part.year, date_part.month, date_part.day,
        time_part.hour, time_part.minute,
    )


def _build_api_client() -> ApiClient:
    base = os.environ.get("SAJUCANDLE_API_BASE_URL", "http://127.0.0.1:8000")
    key = os.environ.get("SAJUCANDLE_API_KEY", "")
    return ApiClient(base_url=base, api_key=key, timeout=10.0)


# 프로세스 수명 동안 1개 유지. 테스트에서 monkeypatch로 치환 가능.
_api_client = _build_api_client()


# ─────────────────────────────────────────────
# Commands
# ─────────────────────────────────────────────

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """`/start [YYYY-MM-DD HH:MM]`.

    인자 없으면 사용법 안내. 있으면 API upsert 후 등록 확인 메시지.
    """
    if update.message is None:
        return
    args = list(context.args or [])
    if not args:
        await update.message.reply_text(
            "사용법:\n/start YYYY-MM-DD HH:MM\n예: /start 1990-03-15 14:00\n\n"
            "생년월일시를 저장하면 매일 /score 로 그날 점수를 볼 수 있습니다."
        )
        return
    try:
        year, month, day, hour, minute = parse_birth_args(args)
    except BirthParseError as e:
        await update.message.reply_text(str(e))
        return

    chat_id = update.effective_chat.id
    try:
        await _api_client.put_user(
            chat_id,
            birth_year=year, birth_month=month, birth_day=day,
            birth_hour=hour, birth_minute=minute,
            asset_class_pref="swing",
        )
    except httpx.TimeoutException:
        await update.message.reply_text("서버 응답이 느립니다. 잠시 후 다시 시도해주세요.")
        return
    except httpx.TransportError as e:
        logger.warning("transport error: %s", e)
        await update.message.reply_text("서버에 연결할 수 없습니다. 잠시 후 다시 시도해주세요.")
        return
    except ApiError as e:
        logger.warning("api error: %s", e)
        await update.message.reply_text(f"서버 오류가 발생했습니다. ({e.status})")
        return
    except Exception:
        logger.exception("start_command unexpected error chat_id=%s", chat_id)
        await update.message.reply_text("예기치 못한 오류가 발생했습니다.")
        return

    logger.info(
        "start ok chat_id=%s birth=%04d-%02d-%02d %02d:%02d",
        chat_id, year, month, day, hour, minute,
    )
    await update.message.reply_text(
        f"✅ 등록 완료.\n"
        f"생년월일: {year:04d}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}\n"
        f"이제 /score 로 오늘 점수를 확인하세요."
    )


async def score_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """`/score [swing|scalp|long|default]`. 오늘 점수 카드."""
    if update.message is None:
        return
    chat_id = update.effective_chat.id
    args = list(context.args or [])
    asset: Optional[str] = args[0] if args else None

    try:
        data = await _api_client.get_score(chat_id, date=None, asset=asset)
    except NotFoundError:
        await update.message.reply_text(
            "먼저 생년월일을 등록하세요.\n예: /start 1990-03-15 14:00"
        )
        return
    except httpx.TimeoutException:
        await update.message.reply_text("서버 응답이 느립니다. 잠시 후 다시.")
        return
    except httpx.TransportError:
        await update.message.reply_text("서버에 연결할 수 없습니다.")
        return
    except ApiError as e:
        logger.warning("score api error chat_id=%s status=%s", chat_id, e.status)
        await update.message.reply_text(f"서버 오류 ({e.status}).")
        return
    except Exception:
        logger.exception("score_command unexpected error chat_id=%s asset=%s", chat_id, asset)
        await update.message.reply_text("예기치 못한 오류가 발생했습니다.")
        return

    lines = [
        f"── {data['date']} ({data['iljin']}) ── [{data['asset_class']}]",
        f"재물운: {data['axes']['wealth']['score']:>3}  | {data['axes']['wealth']['reason']}",
        f"결단운: {data['axes']['decision']['score']:>3}  | {data['axes']['decision']['reason']}",
        f"충돌운: {data['axes']['volatility']['score']:>3}  | {data['axes']['volatility']['reason']}",
        f"합  운: {data['axes']['flow']['score']:>3}  | {data['axes']['flow']['reason']}",
        "────────────────────────────────",
        f"종합: {data['composite_score']:>3}  | {data['signal_grade']}",
    ]
    if data["best_hours"]:
        hrs = ", ".join(
            f"{h['shichen']}시 {h['time_range']}" for h in data["best_hours"]
        )
        lines.append(f"추천 시진: {hrs}")
    await update.message.reply_text("\n".join(lines))


async def me_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """`/me`. 등록된 프로필 조회."""
    if update.message is None:
        return
    chat_id = update.effective_chat.id
    try:
        data = await _api_client.get_user(chat_id)
    except NotFoundError:
        await update.message.reply_text(
            "등록된 정보가 없습니다.\n/start YYYY-MM-DD HH:MM 로 먼저 등록하세요."
        )
        return
    except httpx.TimeoutException:
        await update.message.reply_text("서버 응답이 느립니다.")
        return
    except httpx.TransportError:
        await update.message.reply_text("서버에 연결할 수 없습니다.")
        return
    except ApiError as e:
        logger.warning("me api error chat_id=%s status=%s", chat_id, e.status)
        await update.message.reply_text(f"서버 오류 ({e.status}).")
        return
    except Exception:
        logger.exception("me_command unexpected error chat_id=%s", chat_id)
        await update.message.reply_text("예기치 못한 오류가 발생했습니다.")
        return

    await update.message.reply_text(
        f"등록된 정보:\n"
        f"생년월일: {data['birth_year']:04d}-{data['birth_month']:02d}-{data['birth_day']:02d}\n"
        f"시각: {data['birth_hour']:02d}:{data['birth_minute']:02d}\n"
        f"선호 자산군: {data['asset_class_pref']}\n"
        f"(변경은 /start 로 재등록, 삭제는 /forget)"
    )


async def forget_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """`/forget`. 프로필 삭제 (idempotent)."""
    if update.message is None:
        return
    chat_id = update.effective_chat.id
    try:
        await _api_client.delete_user(chat_id)
    except httpx.TimeoutException:
        await update.message.reply_text("서버 응답이 느립니다. 잠시 후 다시.")
        return
    except httpx.TransportError:
        await update.message.reply_text("서버에 연결할 수 없습니다.")
        return
    except ApiError as e:
        logger.warning("forget api error chat_id=%s status=%s", chat_id, e.status)
        await update.message.reply_text(f"서버 오류 ({e.status}).")
        return
    except Exception:
        logger.exception("forget_command unexpected error chat_id=%s", chat_id)
        await update.message.reply_text("예기치 못한 오류가 발생했습니다.")
        return
    logger.info("forget ok chat_id=%s", chat_id)
    await update.message.reply_text("🗑️ 등록된 정보를 모두 삭제했습니다.")


async def signal_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """`/signal [심볼|list]`. 사주 + 차트 결합 신호.

    · 인자 없음: BTCUSDT
    · `/signal list`: 지원 심볼 목록
    · 그 외: 해당 심볼 조회 (내부에서 upper + $제거 정규화)
    """
    if update.message is None:
        return
    chat_id = update.effective_chat.id
    args = list(context.args or [])

    # 서브커맨드: list
    if args and args[0].lower() == "list":
        await _show_symbol_list(update)
        return

    # ticker 정규화
    if args:
        ticker = args[0].upper().lstrip("$")
    else:
        ticker = "BTCUSDT"

    try:
        data = await _api_client.get_signal(chat_id, ticker=ticker)
    except NotFoundError:
        await update.message.reply_text(
            "먼저 생년월일을 등록하세요.\n예: /start 1990-03-15 14:00"
        )
        return
    except httpx.TimeoutException:
        await update.message.reply_text("서버 응답이 느립니다. 잠시 후 다시.")
        return
    except httpx.TransportError:
        await update.message.reply_text("서버에 연결할 수 없습니다.")
        return
    except ApiError as e:
        if e.status == 400 and "unsupported" in (e.detail or "").lower():
            await update.message.reply_text(
                f"지원하지 않는 심볼: {ticker}\n"
                f"/signal list 로 지원 심볼을 확인하세요."
            )
        elif e.status == 502:
            await update.message.reply_text("시장 데이터 일시 불능. 잠시 후 다시.")
        else:
            logger.warning(
                "signal api error chat_id=%s status=%s", chat_id, e.status
            )
            await update.message.reply_text(f"서버 오류 ({e.status}).")
        return
    except Exception:
        logger.exception("signal_command unexpected error chat_id=%s", chat_id)
        await update.message.reply_text("예기치 못한 오류가 발생했습니다.")
        return

    logger.info(
        "signal ok chat_id=%s ticker=%s composite=%s grade=%s",
        chat_id, data["ticker"], data["composite_score"], data["signal_grade"],
    )

    await update.message.reply_text(_format_signal_card(data))


def _append_trade_setup_block(lines: list, ts: dict) -> None:
    """진입/강진입 등급에 '세팅' 블록 삽입."""
    entry = ts["entry"]
    sl = ts["stop_loss"]
    tp1 = ts["take_profit_1"]
    tp2 = ts["take_profit_2"]
    risk = ts["risk_pct"]
    rr1 = ts["rr_tp1"]
    rr2 = ts["rr_tp2"]

    sl_pct = (sl - entry) / entry * 100 if entry else 0.0
    tp1_pct = (tp1 - entry) / entry * 100 if entry else 0.0
    tp2_pct = (tp2 - entry) / entry * 100 if entry else 0.0

    lines.append("")
    lines.append("세팅:")
    lines.append(f" 진입 ${entry:,.2f}")
    lines.append(f" 손절 ${sl:,.2f} ({sl_pct:+.1f}%)")
    lines.append(
        f" 익절1 ${tp1:,.2f} ({tp1_pct:+.1f}%)  "
        f"익절2 ${tp2:,.2f} ({tp2_pct:+.1f}%)"
    )
    lines.append(f" R:R {rr1:.1f} / {rr2:.1f}   리스크 {risk:.1f}%")


def _append_sr_levels_block(lines: list, levels: list) -> None:
    """관망/회피 등급에 '주요 레벨' 블록 삽입."""
    if not levels:
        return
    resistances = sorted(
        [lvl for lvl in levels if lvl["kind"] == "resistance"],
        key=lambda lvl: lvl["price"],
    )
    supports = sorted(
        [lvl for lvl in levels if lvl["kind"] == "support"],
        key=lambda lvl: lvl["price"],
        reverse=True,
    )
    if not resistances and not supports:
        return
    lines.append("")
    lines.append("주요 레벨:")
    if resistances:
        prices = " · ".join(f"${lvl['price']:,.2f}" for lvl in resistances)
        lines.append(f" 저항 {prices}")
    if supports:
        prices = " · ".join(f"${lvl['price']:,.2f}" for lvl in supports)
        lines.append(f" 지지 {prices}")


_STRUCTURE_LABEL = {
    "uptrend": "상승추세 (HH-HL)",
    "downtrend": "하락추세 (LH-LL)",
    "range": "횡보 (박스)",
    "breakout": "상승 돌파",
    "breakdown": "하락 이탈",
}

_TF_ARROW_UI = {"up": "↑", "down": "↓", "flat": "→"}


def _format_signal_card(data: dict) -> str:
    """/signal 응답 dict → 카드 문자열 (Week 8 포맷).

    구조:
      ── date ticker ──
      (장 배지 — Week 6)
      현재가: ...

      구조: ...
      정렬: 1d↑ 4h↑ 1h↑ (강정렬)
      진입조건: RSI(1h) 35 · 거래량 1.5x

      종합: N | grade
      사주: N (grade)

      ※ DISCLAIMER
    """
    price = data["price"]
    saju = data["saju"]
    status = data.get("market_status") or {}
    category = status.get("category", "crypto")
    analysis = data.get("analysis")

    change_sign = "+" if price["change_pct_24h"] >= 0 else ""
    lines = [f"── {data['date']} {data['ticker']} ──"]

    if category == "us_stock":
        if status.get("is_open"):
            lines.append("🟢 장 중")
        else:
            last = status.get("last_session_date", "")
            lines.append(f"🕐 휴장 중 · 기준: {last} 종가")

    lines.append(
        f"현재가: ${price['current']:,.2f} "
        f"({change_sign}{price['change_pct_24h']:.2f}%)"
    )

    # 분석 3줄 (analysis 있을 때만)
    if analysis:
        lines.append("")
        struct_state = analysis["structure"]["state"]
        lines.append(f"구조: {_STRUCTURE_LABEL.get(struct_state, struct_state)}")
        align = analysis["alignment"]
        tf_str = (
            f"1d{_TF_ARROW_UI.get(align['tf_1d'], '?')} "
            f"4h{_TF_ARROW_UI.get(align['tf_4h'], '?')} "
            f"1h{_TF_ARROW_UI.get(align['tf_1h'], '?')}"
        )
        if align["aligned"]:
            align_tag = "강정렬"
        elif align["bias"] == "mixed":
            align_tag = "혼조"
        else:
            align_tag = "부분정렬"
        lines.append(f"정렬: {tf_str}  ({align_tag})")
        rsi_v = analysis.get("rsi_1h", 50.0)
        vr = analysis.get("volume_ratio_1d", 1.0)
        lines.append(f"진입조건: RSI(1h) {rsi_v:.0f} · 거래량 {vr:.1f}x")

        # Week 9: 등급별 블록
        grade = data.get("signal_grade", "")
        ts = analysis.get("trade_setup")
        sr_levels = analysis.get("sr_levels") or []

        if grade in ("강진입", "진입") and ts:
            _append_trade_setup_block(lines, ts)
        elif sr_levels:
            _append_sr_levels_block(lines, sr_levels)

    lines.append("")
    lines.append(f"종합: {data['composite_score']:>3} | {data['signal_grade']}")
    lines.append(f"사주: {saju['composite']:>3} ({saju['grade']})")

    if data.get("best_hours"):
        hrs = ", ".join(
            f"{h['shichen']}시 {h['time_range']}" for h in data["best_hours"]
        )
        lines.append(f"추천 시진: {hrs}")

    lines.append("")
    lines.append(f"※ {DISCLAIMER}")
    return "\n".join(lines)


async def _show_symbol_list(update: Update) -> None:
    """`/signal list` — 지원 심볼 카탈로그 표시."""
    try:
        symbols = await _api_client.get_supported_symbols()
    except (httpx.TimeoutException, httpx.TransportError):
        await update.message.reply_text("서버에 연결할 수 없습니다.")
        return
    except ApiError as e:
        await update.message.reply_text(f"서버 오류 ({e.status}).")
        return

    crypto = [s for s in symbols if s.get("category") == "crypto"]
    stocks = [s for s in symbols if s.get("category") == "us_stock"]
    lines = ["지원 심볼:", "────────────"]
    if crypto:
        lines.append("암호화폐")
        for s in crypto:
            lines.append(f"  · {s['ticker']} — {s['name']}")
        lines.append("")
    if stocks:
        lines.append("미국주식")
        for s in stocks:
            lines.append(f"  · {s['ticker']} — {s['name']}")
        lines.append("")
    lines.append("사용법: /signal AAPL")
    await update.message.reply_text("\n".join(lines))


# ─────────────────────────────────────────────
# Week 7: watchlist commands
# ─────────────────────────────────────────────

_SYMBOL_NAMES = {
    "BTCUSDT": "Bitcoin",
    "AAPL": "Apple",
    "MSFT": "Microsoft",
    "GOOGL": "Alphabet",
    "NVDA": "NVIDIA",
    "TSLA": "Tesla",
}


def _symbol_name(ticker: str) -> str:
    return _SYMBOL_NAMES.get(ticker, ticker)


async def watch_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """`/watch <심볼>` — 관심 종목 추가 (최대 5개)."""
    if update.message is None:
        return
    chat_id = update.effective_chat.id
    args = list(context.args or [])

    if not args:
        await update.message.reply_text(
            "사용법: /watch <심볼>\n예: /watch AAPL"
        )
        return

    ticker = args[0].upper().lstrip("$")

    try:
        await _api_client.add_watchlist(chat_id, ticker)
    except NotFoundError:
        await update.message.reply_text(
            "먼저 생년월일을 등록하세요.\n예: /start 1990-03-15 14:00"
        )
        return
    except httpx.TimeoutException:
        await update.message.reply_text("서버 응답이 느립니다. 잠시 후 다시.")
        return
    except httpx.TransportError:
        await update.message.reply_text("서버에 연결할 수 없습니다.")
        return
    except ApiError as e:
        detail = (e.detail or "").lower()
        if e.status == 409 and "full" in detail:
            await update.message.reply_text(
                "관심 종목은 최대 5개입니다.\n"
                "/watchlist 에서 제거 후 다시 시도."
            )
        elif e.status == 409 and "already" in detail:
            await update.message.reply_text(f"이미 관심 종목에 있습니다: {ticker}")
        elif e.status == 400 and "unsupported" in detail:
            await update.message.reply_text(
                f"지원하지 않는 심볼: {ticker}\n"
                f"/signal list 로 확인."
            )
        else:
            logger.warning(
                "watch api error chat_id=%s status=%s", chat_id, e.status
            )
            await update.message.reply_text(f"서버 오류 ({e.status}).")
        return
    except Exception:
        logger.exception("watch_command unexpected error chat_id=%s", chat_id)
        await update.message.reply_text("예기치 못한 오류가 발생했습니다.")
        return

    # 성공 시 현재 개수 조회해서 표시
    try:
        items = await _api_client.get_watchlist(chat_id)
        count = len(items)
    except Exception:
        count = "?"

    await update.message.reply_text(
        f"✅ {ticker} ({_symbol_name(ticker)}) 관심 종목 추가 완료.\n"
        f"현재 {count}/5개. /watchlist 로 전체 확인."
    )


async def unwatch_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """`/unwatch <심볼>` — 관심 종목 제거."""
    if update.message is None:
        return
    chat_id = update.effective_chat.id
    args = list(context.args or [])

    if not args:
        await update.message.reply_text("사용법: /unwatch <심볼>")
        return

    ticker = args[0].upper().lstrip("$")

    try:
        await _api_client.remove_watchlist(chat_id, ticker)
    except NotFoundError:
        await update.message.reply_text(f"관심 종목에 없습니다: {ticker}")
        return
    except httpx.TimeoutException:
        await update.message.reply_text("서버 응답이 느립니다. 잠시 후 다시.")
        return
    except httpx.TransportError:
        await update.message.reply_text("서버에 연결할 수 없습니다.")
        return
    except ApiError as e:
        logger.warning(
            "unwatch api error chat_id=%s status=%s", chat_id, e.status
        )
        await update.message.reply_text(f"서버 오류 ({e.status}).")
        return
    except Exception:
        logger.exception("unwatch_command unexpected error chat_id=%s", chat_id)
        await update.message.reply_text("예기치 못한 오류가 발생했습니다.")
        return

    await update.message.reply_text(f"🗑️ {ticker} 관심 종목에서 제거했습니다.")


async def watchlist_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """`/watchlist` — 본인 관심 종목 목록."""
    if update.message is None:
        return
    chat_id = update.effective_chat.id

    try:
        items = await _api_client.get_watchlist(chat_id)
    except httpx.TimeoutException:
        await update.message.reply_text("서버 응답이 느립니다. 잠시 후 다시.")
        return
    except httpx.TransportError:
        await update.message.reply_text("서버에 연결할 수 없습니다.")
        return
    except ApiError as e:
        logger.warning(
            "watchlist api error chat_id=%s status=%s", chat_id, e.status
        )
        await update.message.reply_text(f"서버 오류 ({e.status}).")
        return

    if not items:
        await update.message.reply_text(
            "관심 종목이 비어있습니다.\n"
            "/watch AAPL 로 추가하세요.\n"
            "/signal list 로 지원 심볼 확인."
        )
        return

    lines = [f"📊 관심 종목 ({len(items)}/5)", "─────────────"]
    for i, it in enumerate(items, start=1):
        ticker = it["ticker"]
        added = it.get("added_at", "")[:10]   # "2026-04-15" 부분만
        lines.append(f"{i}. {ticker} — {_symbol_name(ticker)} ({added} 추가)")
    lines.append("")
    lines.append("/unwatch <심볼> 로 제거")
    lines.append("매일 07:00 자동 시그널 발송됩니다.")

    await update.message.reply_text("\n".join(lines))


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """`/help`. 명령어 목록."""
    if update.message is None:
        return
    await update.message.reply_text(
        "SajuCandle 봇 사용법\n"
        "─────────────\n"
        "/start YYYY-MM-DD HH:MM — 생년월일시 등록\n"
        "/score [swing|scalp|long] — 오늘 사주 점수\n"
        "/signal [심볼] — 사주+차트 결합 신호\n"
        "  · 지원: BTCUSDT, AAPL, MSFT, GOOGL, NVDA, TSLA\n"
        "  · /signal list — 전체 목록\n"
        "/watch <심볼> — 관심 종목 추가 (최대 5개)\n"
        "/unwatch <심볼> — 관심 종목 제거\n"
        "/watchlist — 내 관심 종목 + 매일 07:00 자동 시그널\n"
        "/me — 등록된 정보 확인\n"
        "/forget — 내 정보 삭제\n"
        "/help — 이 도움말\n"
        "\n※ 엔터테인먼트 목적. 투자 추천 아님."
    )

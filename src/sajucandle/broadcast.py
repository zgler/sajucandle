"""데일리 푸시 브로드캐스트.

Railway Cron이 매일 22:00 UTC (= 07:00 KST)에 1회 실행:
  python -m sajucandle.broadcast

1. GET /v1/admin/users → chat_ids
2. 각 사용자 GET /v1/users/{id}/score → 카드 포맷팅
3. Telegram Bot.send_message 발송 (50ms 간격)

실패 시:
- Forbidden (봇 차단) / BadRequest → 스킵 + 로깅
- NotFoundError (사용자 삭제) → 스킵
- 기타 API 에러 → 스킵, 요약 counter 반영
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Awaitable, Callable, Optional

import httpx

from sajucandle.api_client import ApiClient, ApiError, NotFoundError

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))
_SEND_DELAY_SEC = 0.05  # rate limit: 20 msg/sec < Telegram 30/sec 한도


SendMessage = Callable[[int, str], Awaitable[None]]


@dataclass
class BroadcastSummary:
    sent: int = 0
    failed: int = 0      # API 에러, 네트워크 등
    blocked: int = 0     # Telegram Forbidden
    not_found: int = 0   # 사용자 등록 삭제됨
    bad_request: int = 0  # Telegram BadRequest
    # Week 7: watchlist + precompute
    watchlist_sent: int = 0
    watchlist_skipped_empty: int = 0
    watchlist_failed: int = 0
    precompute_ok: int = 0
    precompute_failed: int = 0

    def total(self) -> int:
        return self.sent + self.failed + self.blocked + self.not_found + self.bad_request

    def as_log(self) -> str:
        return (
            f"sent={self.sent} failed={self.failed} blocked={self.blocked} "
            f"not_found={self.not_found} bad_request={self.bad_request} "
            f"total={self.total()}"
        )


_WEEKDAY_KR = ["월", "화", "수", "목", "금", "토", "일"]


def format_morning_card(score: dict, target_date: date) -> str:
    """score_endpoint 응답 dict → 모닝 카드 텍스트.

    Plain text, no HTML. 이모지만 사용.
    """
    weekday = _WEEKDAY_KR[target_date.weekday()]
    header = f"☀️ {target_date.isoformat()} ({weekday}) 사주캔들"
    axes = score["axes"]
    lines = [
        header,
        f"── {score['iljin']} [{score['asset_class']}] ──",
        f"재물운: {axes['wealth']['score']:>3}  | {axes['wealth']['reason']}",
        f"결단운: {axes['decision']['score']:>3}  | {axes['decision']['reason']}",
        f"충돌운: {axes['volatility']['score']:>3}  | {axes['volatility']['reason']}",
        f"합  운: {axes['flow']['score']:>3}  | {axes['flow']['reason']}",
        "────────────",
        f"종합: {score['composite_score']:>3}  | {score['signal_grade']}",
    ]
    if score.get("best_hours"):
        hrs = ", ".join(
            f"{h['shichen']}시 {h['time_range']}" for h in score["best_hours"]
        )
        lines.append(f"추천 시진: {hrs}")
    lines.append("")
    lines.append("오늘 BTC는 /signal 로 확인하세요.")
    lines.append("")
    lines.append("※ 엔터테인먼트 목적. 투자 추천 아님.")
    return "\n".join(lines)


_WEEKDAY_KO = ["월", "화", "수", "목", "금", "토", "일"]


def _short_ticker(ticker: str) -> str:
    """BTCUSDT → BTC 축약. 그 외는 원본 유지."""
    if ticker.endswith("USDT"):
        return ticker[:-4]
    return ticker


def format_watchlist_summary(signals: list[dict], target_date) -> Optional[str]:
    """watchlist 요약 카드.

    signals 원소:
      - 정상: {"ticker", "price":{"current","change_pct_24h"},
               "composite_score", "signal_grade",
               "market_status":{"is_open","category","last_session_date"}}
      - 실패: {"ticker", "error": str}

    빈 리스트면 None 반환 (호출자가 전송 skip).
    """
    if not signals:
        return None
    weekday = _WEEKDAY_KO[target_date.weekday()]
    lines = [f"📊 {target_date.isoformat()} ({weekday}) 관심 종목", "─────────────"]
    for s in signals:
        if "error" in s:
            lines.append(f"[{_short_ticker(s['ticker'])}]  {s['error']}")
            continue
        t = _short_ticker(s["ticker"])
        score = s.get("composite_score", 0)
        grade = s.get("signal_grade", "")
        price = s.get("price", {})
        cur = price.get("current", 0.0)
        pct = price.get("change_pct_24h", 0.0)
        sign = "+" if pct >= 0 else ""
        status = s.get("market_status") or {}
        clock = ""
        if status.get("category") == "us_stock" and not status.get("is_open"):
            clock = "  🕐"
        lines.append(
            f"[{t}] {score:>3} {grade}  ${cur:,.2f}  ({sign}{pct:.2f}%){clock}"
        )
    lines.append("")
    lines.append("상세: /signal <심볼>")
    lines.append("※ 엔터테인먼트 목적. 투자 추천 아님.")
    return "\n".join(lines)


async def run_broadcast(
    api_client: ApiClient,
    send_message: SendMessage,
    chat_ids: list[int],
    target_date: date,
    *,
    dry_run: bool = False,
    forbidden_exc: Optional[type[BaseException]] = None,
    bad_request_exc: Optional[type[BaseException]] = None,
    send_delay: float = _SEND_DELAY_SEC,
    admin_chat_id: Optional[int] = None,   # Week 7: Phase 1 precompute
    skip_watchlist: bool = False,           # Week 7: Phase 3 toggle
) -> BroadcastSummary:
    """chat_ids 순회하며 카드 발송. 예외는 잡아서 summary에 누적.

    - `forbidden_exc`, `bad_request_exc`: Telegram 예외 타입 주입.
      프로덕션에서는 `telegram.error.Forbidden`, `BadRequest` 전달.
      테스트에서는 주입 안 하면 해당 분기 안 탐.
    """
    summary = BroadcastSummary()

    # ─── Phase 1: Precompute (watchlist 심볼 캐시 워밍) ───
    if admin_chat_id is not None:
        try:
            symbols = await api_client.get_admin_watchlist_symbols()
        except Exception as e:
            logger.warning("broadcast precompute symbol list failed: %s", e)
            symbols = []
        for ticker in symbols:
            try:
                await api_client.get_signal(
                    admin_chat_id,
                    ticker=ticker,
                    date=target_date.isoformat(),
                )
                summary.precompute_ok += 1
            except Exception as e:
                logger.warning(
                    "broadcast precompute failed ticker=%s: %s", ticker, e
                )
                summary.precompute_failed += 1

    for chat_id in chat_ids:
        # 1. 점수 조회
        try:
            score = await api_client.get_score(chat_id, date=target_date.isoformat())
        except NotFoundError:
            logger.info("broadcast skip chat_id=%s reason=not_found", chat_id)
            summary.not_found += 1
            continue
        except ApiError as e:
            logger.warning(
                "broadcast skip chat_id=%s reason=api_error status=%s",
                chat_id, e.status,
            )
            summary.failed += 1
            continue
        except (httpx.TimeoutException, httpx.TransportError) as e:
            logger.warning(
                "broadcast skip chat_id=%s reason=network error=%s",
                chat_id, type(e).__name__,
            )
            summary.failed += 1
            continue
        except Exception as e:
            logger.exception(
                "broadcast unexpected score error chat_id=%s: %s", chat_id, e
            )
            summary.failed += 1
            continue

        text = format_morning_card(score, target_date)

        if dry_run:
            logger.info("[DRY-RUN] chat_id=%s text=\n%s", chat_id, text)
            summary.sent += 1
            continue

        # 2. 전송
        try:
            await send_message(chat_id, text)
            summary.sent += 1
            logger.info("broadcast sent chat_id=%s", chat_id)
        except Exception as e:
            exc_name = type(e).__name__
            if forbidden_exc is not None and isinstance(e, forbidden_exc):
                logger.info("broadcast blocked chat_id=%s", chat_id)
                summary.blocked += 1
            elif bad_request_exc is not None and isinstance(e, bad_request_exc):
                logger.warning(
                    "broadcast bad_request chat_id=%s err=%s", chat_id, e
                )
                summary.bad_request += 1
            else:
                logger.warning(
                    "broadcast send failed chat_id=%s err=%s: %s",
                    chat_id, exc_name, e,
                )
                summary.failed += 1

        if send_delay > 0:
            await asyncio.sleep(send_delay)

    # ─── Phase 3: Watchlist 요약 ───
    if not skip_watchlist:
        for chat_id in chat_ids:
            try:
                items = await api_client.get_watchlist(chat_id)
            except Exception as e:
                logger.warning(
                    "watchlist fetch failed chat_id=%s: %s", chat_id, e
                )
                summary.watchlist_failed += 1
                continue

            if not items:
                summary.watchlist_skipped_empty += 1
                continue

            signals = []
            for it in items:
                ticker = it["ticker"]
                try:
                    sig = await api_client.get_signal(
                        chat_id,
                        ticker=ticker,
                        date=target_date.isoformat(),
                    )
                    signals.append(sig)
                except Exception as e:
                    logger.warning(
                        "watchlist signal failed chat_id=%s ticker=%s: %s",
                        chat_id, ticker, e,
                    )
                    signals.append({"ticker": ticker, "error": "데이터 불가"})

            card = format_watchlist_summary(signals, target_date)
            if card is None:
                continue
            if dry_run:
                logger.info(
                    "[DRY-RUN] watchlist chat_id=%s text=\n%s",
                    chat_id, card,
                )
            else:
                try:
                    await send_message(chat_id, card)
                    summary.watchlist_sent += 1
                    await asyncio.sleep(send_delay)
                except Exception as e:
                    logger.warning(
                        "watchlist send failed chat_id=%s: %s", chat_id, e
                    )
                    summary.watchlist_failed += 1

    logger.info(
        "broadcast done date=%s sent=%s failed=%s blocked=%s not_found=%s "
        "bad_request=%s watchlist_sent=%s watchlist_skipped_empty=%s "
        "watchlist_failed=%s precompute_ok=%s precompute_failed=%s",
        target_date.isoformat(),
        summary.sent, summary.failed, summary.blocked,
        summary.not_found, summary.bad_request,
        summary.watchlist_sent, summary.watchlist_skipped_empty,
        summary.watchlist_failed,
        summary.precompute_ok, summary.precompute_failed,
    )
    return summary


# ─────────────────────────────────────────────
# CLI entry
# ─────────────────────────────────────────────


def _parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="python -m sajucandle.broadcast",
        description="SajuCandle daily push broadcast",
    )
    p.add_argument(
        "--dry-run", action="store_true",
        help="전송 안 하고 출력만",
    )
    p.add_argument(
        "--test-chat-id", type=int, default=None,
        help="admin 리스트 무시하고 이 chat_id에만 보냄",
    )
    p.add_argument(
        "--date", type=str, default=None,
        help="점수 산출 기준 날짜 (YYYY-MM-DD). 기본: KST 오늘",
    )
    p.add_argument(
        "--skip-watchlist",
        action="store_true",
        help="Phase 3 watchlist 요약을 발송하지 않음 (Week 5 동작 유지)",
    )
    return p.parse_args(argv)


def _require_env(name: str) -> str:
    v = os.environ.get(name, "").strip()
    if not v:
        print(f"ERROR: {name} 환경변수가 필요합니다.", file=sys.stderr)
        sys.exit(1)
    return v


async def _async_main(args: argparse.Namespace) -> int:
    base_url = _require_env("SAJUCANDLE_API_BASE_URL")
    api_key = _require_env("SAJUCANDLE_API_KEY")
    bot_token = _require_env("BOT_TOKEN")

    # 대상 날짜
    if args.date:
        try:
            target_date = date.fromisoformat(args.date)
        except ValueError:
            print(f"ERROR: --date 형식이 잘못되었습니다: {args.date}", file=sys.stderr)
            return 1
    else:
        target_date = datetime.now(tz=KST).date()

    # chat_ids
    api = ApiClient(base_url=base_url, api_key=api_key, timeout=15.0)
    if args.test_chat_id is not None:
        chat_ids = [args.test_chat_id]
        logger.info("using test chat_id=%s (admin list skipped)", args.test_chat_id)
    else:
        try:
            chat_ids = await api.get_admin_users()
        except ApiError as e:
            print(f"ERROR: admin 리스트 조회 실패 status={e.status}", file=sys.stderr)
            return 1
        except (httpx.TimeoutException, httpx.TransportError) as e:
            print(f"ERROR: admin 리스트 네트워크 실패: {e}", file=sys.stderr)
            return 1
        logger.info("fetched %s chat_ids from admin", len(chat_ids))

    if not chat_ids:
        logger.info("no users to broadcast — exiting")
        return 0

    # Telegram Bot
    from telegram import Bot
    from telegram.error import BadRequest, Forbidden
    bot = Bot(token=bot_token)

    async def send_message(chat_id: int, text: str) -> None:
        await bot.send_message(chat_id=chat_id, text=text)

    admin_chat_id_env = os.environ.get("SAJUCANDLE_ADMIN_CHAT_ID")
    admin_chat_id = int(admin_chat_id_env) if admin_chat_id_env else None

    summary = await run_broadcast(
        api_client=api,
        send_message=send_message,
        chat_ids=chat_ids,
        target_date=target_date,
        dry_run=args.dry_run,
        forbidden_exc=Forbidden,
        bad_request_exc=BadRequest,
        admin_chat_id=admin_chat_id,
        skip_watchlist=args.skip_watchlist,
    )
    print(f"date={target_date.isoformat()} {summary.as_log()}")
    return 0


def main() -> None:
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO,
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    args = _parse_args()
    exit_code = asyncio.run(_async_main(args))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()

"""Telegram 커맨드 핸들러 + 인자 파싱 유틸."""
from __future__ import annotations

import logging
import os
from datetime import datetime

from telegram import Update
from telegram.ext import ContextTypes

from sajucandle.cache import BaziCache
from sajucandle.cached_engine import CachedSajuEngine
from sajucandle.format import render_bazi_card

logger = logging.getLogger(__name__)


class BirthParseError(ValueError):
    """사용자 생년월일시 인자 파싱 실패."""


def parse_birth_args(args: list[str]) -> tuple[int, int, int, int, int]:
    """`/start YYYY-MM-DD HH:MM` 인자를 (year, month, day, hour, minute)로.

    허용 포맷:
      - `YYYY-MM-DD HH:MM`
      - `YYYY-MM-DD HH:MM:SS` (초는 무시)
      - `YYYY-MM-DD HH`       (분 = 0)

    Raises:
        BirthParseError: 인자 부족, 포맷 오류, 값 범위 오류.
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
        raise BirthParseError(
            f"시각 형식이 잘못되었습니다 (HH:MM): {time_str}"
        )

    return (
        date_part.year,
        date_part.month,
        date_part.day,
        time_part.hour,
        time_part.minute,
    )


def _build_engine() -> CachedSajuEngine:
    """REDIS_URL 환경변수 있으면 실제 Redis 연결, 없으면 no-op 캐시.

    Upstash는 rediss:// (TLS). 연결 실패해도 캐시 없이 엔진 동작.
    """
    redis_url = os.environ.get("REDIS_URL")
    redis_client = None
    if redis_url:
        try:
            import redis as redis_lib

            redis_client = redis_lib.from_url(redis_url)
            redis_client.ping()
            logger.info("Redis 연결 성공. BaziCache 활성화.")
        except Exception as e:
            logger.warning("Redis 연결 실패 (%s). 캐시 없이 진행.", e)
            redis_client = None
    else:
        logger.info("REDIS_URL 미설정. 캐시 없이 진행.")
    cache = BaziCache(redis_client=redis_client)
    return CachedSajuEngine(cache=cache)


# 엔진은 프로세스 수명 동안 1개만 유지
_engine = _build_engine()


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """`/start YYYY-MM-DD HH:MM` 커맨드. 명식 카드로 응답."""
    if update.message is None:
        return

    try:
        year, month, day, hour, minute = parse_birth_args(list(context.args or []))
    except BirthParseError as e:
        await update.message.reply_text(str(e))
        return

    try:
        chart = _engine.calc_bazi(year, month, day, hour)
    except Exception as e:  # lunar_python 내부 에러
        await update.message.reply_text(
            "명식 계산 중 문제가 발생했습니다. 날짜를 다시 확인해주세요.\n"
            f"({type(e).__name__})"
        )
        return

    birth_str = f"{year:04d}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}"
    card = render_bazi_card(chart, birth_str=birth_str)
    await update.message.reply_text(card)

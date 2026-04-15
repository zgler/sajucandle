"""Telegram 커맨드 핸들러 + 인자 파싱 유틸."""
from __future__ import annotations

from datetime import datetime

from telegram import Update
from telegram.ext import ContextTypes

from sajucandle.format import render_bazi_card
from sajucandle.saju_engine import SajuEngine


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


# 엔진은 프로세스 수명 동안 1개만 유지
_engine = SajuEngine()


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

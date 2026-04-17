"""Telegram 봇 엔트리 포인트. Railway 또는 로컬에서 실행."""
from __future__ import annotations

import logging
import os
import sys

from telegram.ext import Application, CommandHandler

from sajucandle.handlers import (
    forget_command,
    help_command,
    me_command,
    score_command,
    signal_command,
    start_command,
    unwatch_command,
    watch_command,
    watchlist_command,
)


def _configure_logging() -> None:
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO,
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)


def main() -> None:
    _configure_logging()

    token = os.environ.get("BOT_TOKEN")
    if not token:
        print("ERROR: BOT_TOKEN 환경변수가 설정되지 않았습니다.", file=sys.stderr)
        print("로컬 실행 예: BOT_TOKEN=xxx python -m sajucandle.bot", file=sys.stderr)
        sys.exit(1)

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("score", score_command))
    app.add_handler(CommandHandler("signal", signal_command))
    app.add_handler(CommandHandler("me", me_command))
    app.add_handler(CommandHandler("forget", forget_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("watch", watch_command))
    app.add_handler(CommandHandler("unwatch", unwatch_command))
    app.add_handler(CommandHandler("watchlist", watchlist_command))

    logging.info("SajuCandle bot starting (polling mode)...")
    app.run_polling()


if __name__ == "__main__":
    main()

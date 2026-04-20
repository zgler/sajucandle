"""Phase 1 백테스트 CLI — argparse 진입점."""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sajucandle import db
from sajucandle.backtest.aggregate import aggregate_run
from sajucandle.backtest.engine import run_backtest
from sajucandle.market.router import MarketRouter
from sajucandle.market.yfinance import YFinanceClient
from sajucandle.market_data import BinanceClient

logger = logging.getLogger(__name__)


def _short_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short=7", "HEAD"],
            text=True,
        ).strip()
    except Exception:
        return "unknown"


def _default_run_id(label: str = "auto") -> str:
    sha = _short_sha()
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"phase1-{sha}-{label}-{today}"


def _parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m sajucandle.backtest",
        description="SajuCandle Phase 1 백테스트 하네스",
    )
    sub = parser.add_subparsers(dest="subcommand", required=True)

    # run
    run_p = sub.add_parser("run", help="백테스트 실행")
    run_p.add_argument("--ticker", required=True, help="심볼 (예: BTCUSDT, AAPL)")
    run_p.add_argument("--from", dest="from_dt", required=True,
                        type=lambda s: datetime.fromisoformat(s).replace(tzinfo=timezone.utc),
                        help="시작 날짜 (YYYY-MM-DD)")
    run_p.add_argument("--to", dest="to_dt", required=True,
                        type=lambda s: datetime.fromisoformat(s).replace(tzinfo=timezone.utc),
                        help="종료 날짜 (YYYY-MM-DD)")
    run_p.add_argument("--run-id", default=None,
                        help="백테스트 run 식별자. 미지정 시 자동 생성")
    run_p.add_argument("--cache-dir", default=".cache/backtest",
                        help="OHLCV 디스크 캐시 경로")

    # aggregate
    agg_p = sub.add_parser("aggregate", help="run별 집계 결과")
    agg_p.add_argument("--run-id", required=True)
    agg_p.add_argument("--json", action="store_true", help="JSON 출력")

    return parser.parse_args(argv)


async def _run_cmd(args: argparse.Namespace) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    run_id = args.run_id or _default_run_id(label="auto")
    router = MarketRouter(binance=BinanceClient(), yfinance=YFinanceClient())

    # DB 연결
    dsn = os.environ.get("DATABASE_URL") or os.environ.get("TEST_DATABASE_URL")
    if not dsn:
        print("ERROR: DATABASE_URL 또는 TEST_DATABASE_URL 환경변수 필요", file=sys.stderr)
        return 1
    # Supabase transaction pooler(6543) 호환을 위해 prepared statement 비활성.
    # Session pooler(5432)에서도 안전 (단지 성능 미세 손실).
    await db.connect(dsn, statement_cache_size=0)

    try:
        summary = await run_backtest(
            ticker=args.ticker.upper().lstrip("$"),
            from_dt=args.from_dt,
            to_dt=args.to_dt,
            run_id=run_id,
            router=router,
            cache_dir=Path(args.cache_dir),
        )
        print(f"\nBacktest done — run_id={summary.run_id}")
        print(f"  ticker={summary.ticker}")
        print(f"  signals_total={summary.signals_total}")
        print("  by_grade:")
        for g, c in sorted(summary.signals_by_grade.items()):
            print(f"    {g:<6} {c}")
        print(f"  insert_errors={summary.insert_errors}")
        return 0
    finally:
        await db.close()


async def _aggregate_cmd(args: argparse.Namespace) -> int:
    logging.basicConfig(level=logging.WARNING)
    dsn = os.environ.get("DATABASE_URL") or os.environ.get("TEST_DATABASE_URL")
    if not dsn:
        print("ERROR: DATABASE_URL 필요", file=sys.stderr)
        return 1
    # Supabase transaction pooler(6543) 호환을 위해 prepared statement 비활성.
    # Session pooler(5432)에서도 안전 (단지 성능 미세 손실).
    await db.connect(dsn, statement_cache_size=0)
    try:
        async with db.acquire() as conn:
            stats = await aggregate_run(conn, run_id=args.run_id)
        if args.json:
            import dataclasses
            print(json.dumps(
                [dataclasses.asdict(s) for s in stats],
                ensure_ascii=False, indent=2,
            ))
        else:
            print(f"\nRun: {args.run_id}")
            print(f"{'grade':<8} {'n':>5} {'win%':>7} {'avg_mfe':>8} {'avg_mae':>8} {'rr_tp1':>7}")
            print("-" * 48)
            for s in stats:
                rr = f"{s.avg_rr_tp1:.2f}" if s.avg_rr_tp1 else "  -  "
                print(f"{s.grade:<8} {s.count:>5} "
                      f"{s.win_rate*100:>6.1f}% "
                      f"{s.avg_mfe:>+7.2f}% {s.avg_mae:>+7.2f}% {rr:>7}")
            if not stats:
                print("(해당 run_id에 tracking_done=TRUE 데이터 없음)")
        return 0
    finally:
        await db.close()


def main(argv: Optional[list[str]] = None) -> int:
    args = _parse_args(argv)
    if args.subcommand == "run":
        return asyncio.run(_run_cmd(args))
    elif args.subcommand == "aggregate":
        return asyncio.run(_aggregate_cmd(args))
    return 1


if __name__ == "__main__":
    sys.exit(main())

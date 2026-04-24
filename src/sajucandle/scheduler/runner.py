"""월간 리밸런싱 스케줄러.

매월 1일 오전 9시 (KST) 자동 실행:
  1. 주식 30종 신호 생성 (C 필터 전략)
  2. data/signals/YYYY-MM/ 에 JSON + HTML + 텍스트 저장
  3. 이전 달 보유 종목 자동 로드 → SELL/BUY 비교

실행:
  python -m sajucandle.scheduler.runner          # 즉시 1회 실행
  python -m sajucandle.scheduler.runner --daemon  # 스케줄러 상시 실행

저장 경로:
  data/signals/YYYY-MM/stock_signals.json
  data/signals/YYYY-MM/stock_signals.html
  data/signals/YYYY-MM/stock_signals.txt
  data/signals/holdings.json   ← 현재 보유 종목 (매 실행 후 갱신)
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

_root = Path(__file__).parent.parent.parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root / "src"))

from sajucandle.manseryeok.core import SajuCalculator
from sajucandle.ticker.loader import load_tickers
from sajucandle.signal.engine import generate_signals
from sajucandle.signal.renderer import render_telegram, render_email_html, render_text

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

SIGNALS_DIR = _root / "data" / "signals"
HOLDINGS_FILE = SIGNALS_DIR / "holdings.json"

# ── 상수 ─────────────────────────────────────────────────────────────────
TOP_N = 5
WATCH_BUFFER = 5
SAJU_THRESHOLD = 30.0
ASSET_CLASS = "stock"


# ── 보유 종목 persistence ─────────────────────────────────────────────────

def load_holdings() -> set[str]:
    """저장된 현재 보유 종목 로드."""
    if not HOLDINGS_FILE.exists():
        return set()
    try:
        data = json.loads(HOLDINGS_FILE.read_text(encoding="utf-8"))
        return set(data.get("holdings", []))
    except Exception:
        return set()


def save_holdings(holdings: set[str], dt: datetime) -> None:
    """보유 종목 저장."""
    SIGNALS_DIR.mkdir(parents=True, exist_ok=True)
    HOLDINGS_FILE.write_text(
        json.dumps(
            {"holdings": sorted(holdings), "updated_at": dt.isoformat()},
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )


# ── 신호 저장 ─────────────────────────────────────────────────────────────

def save_report(report, dt: datetime) -> Path:
    """신호 리포트를 JSON / HTML / TXT 로 저장."""
    month_dir = SIGNALS_DIR / dt.strftime("%Y-%m")
    month_dir.mkdir(parents=True, exist_ok=True)

    # JSON
    json_path = month_dir / "stock_signals.json"
    out = {
        "generated_at": dt.isoformat(),
        "asset_class": ASSET_CLASS,
        "universe": report.universe_size,
        "saju_survivors": report.survivors,
        "top_n": report.top_n,
        "saju_filter_threshold": report.saju_filter_threshold,
        "prev_holdings": sorted(report.prev_holdings),
        "new_holdings": sorted(report.new_holdings),
        "signals": [
            {
                "symbol": s.symbol,
                "signal": s.signal.value,
                "saju_score": s.saju_score,
                "quant_score": s.quant_score,
                "rank": s.rank,
                "reason": s.reason,
                "breakdown": s.breakdown,
            }
            for s in sorted(report.signals,
                            key=lambda x: (_SIG_ORDER.get(x.signal.value, 9), x.rank or 999))
        ],
    }
    json_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    # HTML
    html_path = month_dir / "stock_signals.html"
    html_path.write_text(render_email_html(report), encoding="utf-8")

    # TXT
    txt_path = month_dir / "stock_signals.txt"
    txt_path.write_text(render_text(report), encoding="utf-8")

    return month_dir


_SIG_ORDER = {"BUY": 1, "HOLD": 2, "SELL": 3, "WATCH": 4, "KILL": 5}


# ── 핵심 잡 ───────────────────────────────────────────────────────────────

def run_monthly_job(dt: datetime | None = None) -> None:
    """월간 신호 생성 잡 (스케줄러 or 즉시 실행 공용)."""
    if dt is None:
        dt = datetime.now().replace(hour=9, minute=0, second=0, microsecond=0)

    log.info(f"월간 신호 생성 시작: {dt.strftime('%Y-%m-%d')}")

    calc = SajuCalculator()
    csv = _root / "data" / "tickers" / "stock_universe_30.csv"
    tickers = load_tickers(csv)
    stock_tickers = {s: r for s, r in tickers.items() if r.asset_class == ASSET_CLASS}
    log.info(f"유니버스: {len(stock_tickers)}종")

    current_holdings = load_holdings()
    log.info(f"이전 보유: {sorted(current_holdings) or '없음'}")

    report = generate_signals(
        calc=calc,
        records=stock_tickers,
        asset_class=ASSET_CLASS,
        target_dt=dt,
        current_holdings=current_holdings,
        top_n=TOP_N,
        watch_buffer=WATCH_BUFFER,
        saju_filter_threshold=SAJU_THRESHOLD,
        fast_macro=True,
    )

    # 파일 저장 (출력 전에 먼저)
    out_dir = save_report(report, dt)
    save_holdings(report.new_holdings, dt)

    # 콘솔 출력
    print()
    print(render_text(report))
    print()
    print("텔레그램 메시지:")
    print(render_telegram(report))
    print()

    log.info(f"저장 완료: {out_dir}")
    log.info(f"새 보유: {sorted(report.new_holdings)}")

    buys = [s.symbol for s in report.signals if s.signal.value == "BUY"]
    sells = [s.symbol for s in report.signals if s.signal.value == "SELL"]
    if buys:
        log.info(f"BUY: {buys}")
    if sells:
        log.info(f"SELL: {sells}")


# ── 진입점 ────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="사주캔들 월간 신호 스케줄러")
    parser.add_argument("--daemon", action="store_true", help="스케줄러 상시 실행 (매월 1일 09:00 KST)")
    parser.add_argument("--date", type=str, default=None, help="즉시 실행 날짜 YYYY-MM-DD (기본: 오늘)")
    args = parser.parse_args()

    if args.daemon:
        log.info("스케줄러 시작 — 매월 1일 09:00 KST 실행")
        scheduler = BlockingScheduler(timezone="Asia/Seoul")
        scheduler.add_job(
            run_monthly_job,
            trigger=CronTrigger(day=1, hour=9, minute=0, timezone="Asia/Seoul"),
            id="monthly_signal",
            name="월간 사주캔들 신호 생성",
            misfire_grace_time=3600,   # 1시간 내 재실행 허용
            replace_existing=True,
        )
        log.info(f"등록 완료: {scheduler.get_jobs()[0].name}")
        try:
            scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            log.info("스케줄러 종료")
    else:
        # 즉시 1회 실행
        dt = None
        if args.date:
            dt = datetime.strptime(args.date, "%Y-%m-%d").replace(hour=9)
        run_monthly_job(dt)


if __name__ == "__main__":
    main()

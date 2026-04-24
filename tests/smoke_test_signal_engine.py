"""Signal Engine 스모크 테스트.

오늘 날짜 기준으로 주식 30종 신호 생성.
BUY / HOLD / SELL / WATCH / KILL 분류 출력.
"""

import json
import sys
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from sajucandle.manseryeok.core import SajuCalculator
from sajucandle.ticker.loader import load_tickers
from sajucandle.signal.engine import generate_signals, SignalType


def main():
    calc = SajuCalculator()
    stock_csv = project_root / "data" / "tickers" / "stock_universe_30.csv"
    tickers = load_tickers(stock_csv)
    stock_tickers = {s: r for s, r in tickers.items() if r.asset_class == "stock"}
    print(f"[UNIVERSE] 주식 {len(stock_tickers)}개\n")

    target_dt = datetime.now().replace(hour=9, minute=0, second=0, microsecond=0)

    # 시뮬레이션: 가정상 현재 보유 종목
    assumed_holdings = {"AAPL", "MSFT", "JPM", "XOM", "KO"}
    print(f"[현재 보유 가정] {sorted(assumed_holdings)}\n")

    print("신호 생성 중 (fast_macro=True)...")
    report = generate_signals(
        calc=calc,
        records=stock_tickers,
        asset_class="stock",
        target_dt=target_dt,
        current_holdings=assumed_holdings,
        top_n=5,
        watch_buffer=5,
        saju_filter_threshold=30.0,
        fast_macro=True,
    )

    print()
    print(report.summary())

    # JSON 저장
    out = {
        "target_dt": target_dt.isoformat(),
        "universe": report.universe_size,
        "saju_survivors": report.survivors,
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
            for s in sorted(report.signals, key=lambda x: (x.signal.value, -(x.rank or 999)))
        ],
    }
    out_file = Path(__file__).parent / "smoke_output_signal_engine.json"
    with out_file.open("w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\n상세: {out_file}")


if __name__ == "__main__":
    main()

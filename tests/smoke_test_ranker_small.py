"""축소 랭커 스모크: 주식 3 + 코인 3.

목적: 파이프라인이 integrally 작동하는지 빠르게 확인.
"""

import json
import sys
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", write_through=True)
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from sajucandle.manseryeok.core import SajuCalculator
from sajucandle.ticker.loader import load_tickers
from sajucandle.quant.ranker import rank_universe


def main():
    calc = SajuCalculator()
    all_tickers = load_tickers()

    # 종목 축소
    pick = ["NVDA", "AAPL", "MSFT", "BTC-USD", "ETH-USD", "SOL-USD"]
    tickers = {s: all_tickers[s] for s in pick if s in all_tickers}
    print(f"[UNIVERSE] {list(tickers)}", flush=True)

    target_dt = datetime(2026, 4, 23, 12, 0)

    for asset in ["coin", "stock"]:
        print(f"\n=== {asset.upper()} ===", flush=True)
        top = rank_universe(calc, tickers, target_dt, asset_class=asset, top_n=5)
        for i, r in enumerate(top, 1):
            print(f"  {i}. {r['symbol']:<11} {r['primary_pillar']:<6} "
                  f"S={r['saju_100']:5.1f} Q={r['quant_100']:5.1f} "
                  f"Raw={r['raw']:5.1f} Final={r['final']:5.1f}", flush=True)

    out_file = Path(__file__).parent / "smoke_output_ranker_small.json"
    top_all = []
    for asset in ["coin", "stock"]:
        top_all.extend(rank_universe(calc, tickers, target_dt, asset_class=asset, top_n=5))
    with out_file.open("w", encoding="utf-8") as f:
        json.dump(top_all, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n상세: {out_file}", flush=True)


if __name__ == "__main__":
    main()

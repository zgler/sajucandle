"""통합 랭커 스모크 테스트.

20개 샘플 종목 전체를 30% 사주 + 70% 퀀트로 평가 → 자산군별 Top 10.
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
from sajucandle.quant.ranker import rank_universe


def main():
    calc = SajuCalculator()
    tickers = load_tickers()
    print(f"[LOAD] 종목 {len(tickers)}개")

    target_dt = datetime(2026, 4, 23, 12, 0)
    print(f"[TARGET] {target_dt}\n")

    for asset in ["coin", "stock"]:
        print("=" * 100)
        print(f"[RANKING] {asset.upper()} Top 10")
        print("=" * 100)
        top = rank_universe(calc, tickers, target_dt, asset_class=asset, top_n=10)
        print(f"{'순위':<4}{'종목':<11}{'섹터':<12}{'일주':<6}{'사주':>6}{'퀀트':>6}{'Raw':>6}{'Final':>7}  페널티")
        print("-" * 100)
        for i, r in enumerate(top, 1):
            p = "⚠" if r["penalty_applied"] else " "
            print(f"{i:<4}{r['symbol']:<11}{r['sector'][:11]:<12}"
                  f"{r['primary_pillar']:<6}"
                  f"{r['saju_100']:>6.1f}{r['quant_100']:>6.1f}"
                  f"{r['raw']:>6.1f}{r['final']:>7.1f}  {p}")

    # 저장
    all_rank = rank_universe(calc, tickers, target_dt, asset_class=None, top_n=30)
    out_file = Path(__file__).parent / "smoke_output_ranker.json"
    with out_file.open("w", encoding="utf-8") as f:
        json.dump(all_rank, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n상세: {out_file}")


if __name__ == "__main__":
    main()

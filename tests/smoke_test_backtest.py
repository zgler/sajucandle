"""백테스트 + Placebo Null Test 통합 스모크.

규모 축소 버전 (Phase 1):
- 기간: 2025-01 ~ 2026-04 (16개월, 15회 리밸런싱)
- 자산군: 코인 (yfinance 의존도 낮고 빠름)
- 종목: Top 100 샘플 중 10개
- Placebo: 5회 시행
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
from sajucandle.quant.backtest import BacktestConfig, run_backtest
from sajucandle.quant.null_test import placebo_test


def main():
    calc = SajuCalculator()
    tickers = load_tickers()
    # 코인만
    coin_tickers = {s: r for s, r in tickers.items() if r.asset_class == "coin"}
    print(f"[UNIVERSE] 코인 {len(coin_tickers)}개\n")

    cfg = BacktestConfig(
        start=datetime(2025, 1, 1),
        end=datetime(2026, 4, 1),
        top_n=3,
        label="coin_phase1",
    )

    print("=" * 70)
    print("[1] 실제 사주 백테스트")
    print("=" * 70)
    real = run_backtest(calc, coin_tickers, cfg, "coin")
    for k, v in real.stats.items():
        print(f"  {k}: {v}")
    print(f"\n리밸런싱 {len(real.rebalance_log)}회")
    for log in real.rebalance_log[:3] + real.rebalance_log[-2:]:
        print(f"  {log['date']}: 보유={log['held']} 수익={log['period_return']:+.2%} 자본={log['equity']}")

    print("\n" + "=" * 70)
    print("[2] Placebo Null Test (랜덤 사주 5회)")
    print("=" * 70)
    placebo = placebo_test(calc, coin_tickers, cfg, "coin", n_trials=3)
    print(f"\n실제 sharpe: {placebo['real'].get('sharpe')}")
    print(f"랜덤 평균 sharpe: {placebo['placebo_mean'].get('sharpe')} ± {placebo['placebo_std'].get('sharpe')}")
    print(f"z-score (sharpe): {placebo['zscore'].get('sharpe')}")
    print(f"판정: {placebo['verdict']}")

    print("\n상세 결과:")
    for m in ["cagr", "sharpe", "sortino", "hit_rate"]:
        print(f"  {m:<10}  real={placebo['real'].get(m)}  "
              f"placebo={placebo['placebo_mean'].get(m)}±{placebo['placebo_std'].get(m)}  "
              f"z={placebo['zscore'].get(m)}")

    out = {
        "real_backtest": real.stats,
        "real_log_sample": real.rebalance_log[:5],
        "placebo_test": placebo,
    }
    out_file = Path(__file__).parent / "smoke_output_backtest.json"
    with out_file.open("w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n상세: {out_file}")


if __name__ == "__main__":
    main()

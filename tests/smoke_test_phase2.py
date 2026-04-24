"""Phase 2 Null Test — Shuffle Test + Regime Decomposition Test.

Phase 1에서 Placebo z-score = -2.08 (FAIL) 기록.
Phase 2는 나머지 2종 Null Test 실행:
  1. Shuffle Test  : 상장일을 종목간 셔플 → 실제가 분포 상위 5% 내?
  2. Regime Decomp : Bull/Bear/Sideways 별 사주 엣지 존재 여부

3종 최종 판정:
  pass ≥ 2 → 30% 유지 / marginal 검토
  pass ≤ 1 → 사주 필터 전용 격하 고려
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
from sajucandle.quant.null_test import shuffle_test, regime_decomposition_test


def main():
    calc = SajuCalculator()
    tickers = load_tickers()
    coin_tickers = {s: r for s, r in tickers.items() if r.asset_class == "coin"}
    print(f"[UNIVERSE] 코인 {len(coin_tickers)}개\n")

    cfg = BacktestConfig(
        start=datetime(2025, 1, 1),
        end=datetime(2026, 4, 1),
        top_n=3,
        fast_macro=True,
        label="coin_phase2",
    )

    # ──────────────────────────────────────────────────
    print("=" * 70)
    print("[1] Shuffle Test (n=5)")
    print("    종목간 상장일/창립일을 셔플 → 실제 배치가 분포 상위 몇 %?")
    print("=" * 70)
    shuf = shuffle_test(calc, coin_tickers, cfg, "coin", n_trials=5)
    print(f"  실제 sharpe:   {shuf['real_sharpe']}")
    print(f"  셔플 분포:     {shuf['shuffled_sharpes']}")
    print(f"  백분위:        {shuf['percentile']:.1%}")
    print(f"  판정:          {shuf['verdict'].upper()}")
    print()

    # ──────────────────────────────────────────────────
    print("=" * 70)
    print("[2] Regime Decomposition Test (placebo=5)")
    print("    Bull/Bear/Sideways 레짐별 사주 초과 수익 측정")
    print("=" * 70)
    regime = regime_decomposition_test(
        calc, coin_tickers, cfg, "coin",
        n_placebo=5,
        regime_threshold=0.05,
    )
    for r, s in regime["regime_stats"].items():
        edge = "✓ EDGE" if s["edge_detected"] else "✗"
        count = s["count"]
        real = s["real_avg_return"]
        placebo = s["placebo_avg"]
        z = s["zscore"]
        print(f"  {r:8s} ({count:2d}기간)  실제={real}  placebo={placebo}  z={z}  {edge}")
    print(f"\n  엣지 감지 레짐: {regime['edge_detected_in']}")
    print(f"  판정:           {regime['verdict'].upper()}")
    print()

    # ──────────────────────────────────────────────────
    print("=" * 70)
    print("[3] 3종 Null Test 종합 판정")
    print("=" * 70)
    results = {
        "placebo": "fail",   # Phase 1 결과 (z=-2.08)
        "shuffle": shuf["verdict"],
        "regime":  regime["verdict"],
    }
    pass_count = sum(1 for v in results.values() if v == "pass")
    marg_count = sum(1 for v in results.values() if v == "marginal")
    print(f"  Placebo : FAIL  (Phase 1 결과, z=-2.08)")
    print(f"  Shuffle : {results['shuffle'].upper()}")
    print(f"  Regime  : {results['regime'].upper()}")
    print()
    if pass_count >= 2:
        final = "30% 가중치 유지 / 상향 검토 가능"
    elif pass_count + marg_count >= 2:
        final = "30% 유지 (marginal 포함), 활성 레짐 집중 고려"
    else:
        final = "사주 필터 전용 격하 고려 (PRD §12-4: 1개 이하 통과)"
    print(f"  최종: {final}")

    out = {
        "shuffle_test": shuf,
        "regime_test": {k: v for k, v in regime.items() if k != "periods"},
        "regime_periods": regime["periods"],
        "phase1_placebo_verdict": "fail",
        "phase1_placebo_zscore_sharpe": -2.08,
        "pass_count": pass_count,
        "final_verdict": final,
    }
    out_file = Path(__file__).parent / "smoke_output_phase2.json"
    with out_file.open("w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n상세: {out_file}")


if __name__ == "__main__":
    main()

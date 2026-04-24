"""아웃오브샘플 검증 — C 필터 전략 overfitting 여부.

분할:
  학습 (in-sample)  : 2015-01 ~ 2019-12 (60개월)
  테스트 (out-of-sample): 2020-01 ~ 2024-12 (60개월)

검증 포인트:
  1. 학습에서 튜닝된 saju_filter_threshold (30)가 테스트에서도 유효한가?
  2. 학습 기간 CAGR/Sharpe와 테스트 기간 지표가 크게 다르면 overfitting 의심
  3. 여러 threshold (0/20/30/40/50)에 대해 학습 → 최적값 → 테스트

기준:
  Pass  — 학습 최적 threshold가 테스트 기간에도 top quartile 유지
  Fail  — 학습 최적값이 테스트에서 worse than median → overfitting
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


def run_filter_grid(calc, tickers, asset, start, end, thresholds, shared_cache):
    """여러 threshold에 대해 동일 기간 백테스트."""
    results = {}
    for t in thresholds:
        cfg = BacktestConfig(
            start=start, end=end, top_n=5, fast_macro=True,
            saju_filter_mode=True, saju_filter_threshold=t,
            label=f"threshold_{int(t)}",
        )
        r = run_backtest(calc, tickers, cfg, asset, quant_cache=shared_cache)
        s = r.stats
        if s:
            results[t] = {
                "cagr": s["cagr"], "sharpe": s["sharpe"],
                "mdd": s["mdd"], "hit_rate": s["hit_rate"],
                "final_equity": s["final_equity"],
            }
            print(f"  threshold={t:>4.0f}  CAGR={s['cagr']:.1%}  "
                  f"Sharpe={s['sharpe']}  MDD={s['mdd']:.1%}")
        else:
            results[t] = None
    return results


def main():
    calc = SajuCalculator()
    stock_csv = project_root / "data" / "tickers" / "stock_universe_30.csv"
    tickers = load_tickers(stock_csv)
    stock_tickers = {s: r for s, r in tickers.items() if r.asset_class == "stock"}
    print(f"[UNIVERSE] 주식 {len(stock_tickers)}종\n")

    asset = "stock"
    thresholds = [0.0, 20.0, 30.0, 40.0, 50.0]

    # ── 학습 기간 (2015-2019) ──────────────────────────────────────────
    train_start = datetime(2015, 1, 1)
    train_end = datetime(2019, 12, 31)
    print("=" * 70)
    print("[학습 기간] 2015-01 ~ 2019-12 (60개월)")
    print("=" * 70)
    train_cache = {}
    # 먼저 threshold=0으로 cache 빌드
    train_results = run_filter_grid(
        calc, stock_tickers, asset, train_start, train_end,
        thresholds, train_cache,
    )

    # 학습 최적 threshold (Sharpe 기준)
    best_train = max(
        (t for t, v in train_results.items() if v),
        key=lambda t: train_results[t]["sharpe"],
    )
    print(f"\n  → 학습 최적 threshold: {best_train:.0f} "
          f"(Sharpe={train_results[best_train]['sharpe']})")

    # ── 테스트 기간 (2020-2024) ────────────────────────────────────────
    test_start = datetime(2020, 1, 1)
    test_end = datetime(2024, 12, 31)
    print()
    print("=" * 70)
    print("[테스트 기간] 2020-01 ~ 2024-12 (60개월, OUT-OF-SAMPLE)")
    print("=" * 70)
    test_cache = {}
    test_results = run_filter_grid(
        calc, stock_tickers, asset, test_start, test_end,
        thresholds, test_cache,
    )

    # 테스트에서 best_train 순위
    test_ranking = sorted(
        [(t, v) for t, v in test_results.items() if v],
        key=lambda x: x[1]["sharpe"], reverse=True,
    )
    train_best_test_rank = next(
        (i for i, (t, _) in enumerate(test_ranking) if t == best_train), -1
    )
    test_best = test_ranking[0][0] if test_ranking else None

    # ── 판정 ───────────────────────────────────────────────────────────
    print()
    print("=" * 70)
    print("[Overfitting 판정]")
    print("=" * 70)

    train_best_sharpe = train_results[best_train]["sharpe"]
    test_at_train_best = test_results.get(best_train, {}).get("sharpe")
    test_best_sharpe = test_results[test_best]["sharpe"] if test_best is not None else None

    print(f"  학습 최적 threshold     : {best_train:.0f}  (학습 Sharpe={train_best_sharpe})")
    print(f"  테스트 최적 threshold   : {test_best:.0f}  (테스트 Sharpe={test_best_sharpe})")
    print(f"  학습 최적값의 테스트 Sharpe: {test_at_train_best}")
    print(f"  테스트 내 순위          : {train_best_test_rank + 1}/{len(test_ranking)}")

    # 성과 degradation
    if test_at_train_best is not None and train_best_sharpe:
        degradation = (train_best_sharpe - test_at_train_best) / abs(train_best_sharpe) * 100
        print(f"  Sharpe 감소율           : {degradation:.1f}%")

    # 판정
    verdict_lines = []
    if best_train == test_best:
        verdict_lines.append("✓ 학습 최적값이 테스트에서도 최적 → 일관성 있음")
    elif train_best_test_rank < len(test_ranking) / 2:
        verdict_lines.append(f"△ 학습 최적값이 테스트 상위 50% → 부분 일관성")
    else:
        verdict_lines.append("✗ 학습 최적값이 테스트 하위 → Overfitting 의심")

    if test_at_train_best is not None:
        if test_at_train_best > 0.8:
            verdict_lines.append(f"✓ 테스트 Sharpe > 0.8 (SPY 초과 수준) → 실용적")
        elif test_at_train_best > 0.5:
            verdict_lines.append(f"△ 테스트 Sharpe 0.5~0.8 → 제한적 실용성")
        else:
            verdict_lines.append(f"✗ 테스트 Sharpe < 0.5 → 실전 배포 부적합")

    for line in verdict_lines:
        print(f"  {line}")

    # ── 최종 결론 ──────────────────────────────────────────────────────
    print()
    print("=" * 70)
    print("[결론]")
    print("=" * 70)
    overall_pass = (
        best_train == test_best and
        test_at_train_best is not None and
        test_at_train_best > 0.8
    )
    if overall_pass:
        print(f"  ✓ PASS — C 필터 threshold={best_train:.0f}은 OOS 검증 통과")
    else:
        # 조건부 통과
        if test_at_train_best is not None and test_at_train_best > 0.5:
            print(f"  △ MARGINAL — threshold={best_train:.0f} OOS에서 약화되나 사용 가능")
        else:
            print(f"  ✗ FAIL — threshold={best_train:.0f}은 overfitting 가능성")

    out = {
        "train_period": "2015-01~2019-12",
        "test_period": "2020-01~2024-12",
        "train_results": train_results,
        "test_results": test_results,
        "best_train_threshold": best_train,
        "best_test_threshold": test_best,
        "train_best_test_rank": train_best_test_rank + 1,
        "verdict": verdict_lines,
    }
    out_file = Path(__file__).parent / "smoke_output_oos_validation.json"
    with out_file.open("w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n상세: {out_file}")


if __name__ == "__main__":
    main()

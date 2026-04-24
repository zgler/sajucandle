"""saju_score_v2 10% 설정 Null Test — Placebo + Shuffle.

v2 scorer (월운×일주 36% + 세운오행 37% + 신살 27%) + 10% 가중이
통계적으로 유의한 alpha를 생성하는지 검증.

핵심 질문:
  v2 10%는 random 사주 10%보다 유의하게 좋은가?
  실제 날짜 배치가 셔플 분포 상위 5% 내에 있는가?

비교 기준:
  이전 v1 30% Null Test: Placebo z=-7.46 (FAIL), Shuffle 0%ile (FAIL)
  기대: v2 10%는 harmful 컴포넌트 제거로 FAIL→MARGINAL 또는 PASS
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
from sajucandle.quant.backtest import BacktestConfig
from sajucandle.quant.null_test import placebo_test, shuffle_test
from sajucandle.saju.scorer import saju_score_v2


def main():
    calc = SajuCalculator()
    stock_csv = project_root / "data" / "tickers" / "stock_universe_30.csv"
    tickers = load_tickers(stock_csv)
    stock_tickers = {s: r for s, r in tickers.items() if r.asset_class == "stock"}
    print(f"[UNIVERSE] 주식 {len(stock_tickers)}개\n")

    start = datetime(2015, 1, 1)
    end = datetime(2024, 12, 31)

    cfg = BacktestConfig(
        start=start, end=end, top_n=5, fast_macro=True,
        saju_weight=0.10,
        saju_score_fn=saju_score_v2,
        label="v2_10pct_nulltest",
    )

    # ── Placebo Test ──────────────────────────────────────────────────────
    print("=" * 70)
    print("Placebo Test (n=10) — v2 10% vs 랜덤 사주 10%")
    print("  해석: z>+2 → 사주 신호 유의 / z<0 → 사주가 퀀트 훼손")
    print("=" * 70)
    pl = placebo_test(calc, stock_tickers, cfg, "stock", n_trials=10)

    print(f"\n  실제 v2 10%  : CAGR={pl['real']['cagr']:.1%}  Sharpe={pl['real']['sharpe']}  "
          f"MDD={pl['real']['mdd']:.1%}  hit={pl['real']['hit_rate']:.1%}")
    print(f"  Placebo 평균 : CAGR={pl['placebo_mean']['cagr']:.1%}  "
          f"Sharpe={pl['placebo_mean']['sharpe']}  (n={pl['n_trials']})")
    print(f"  Placebo std  : Sharpe±{pl['placebo_std']['sharpe']}")
    print(f"  z-score      : CAGR z={pl['zscore']['cagr']}  Sharpe z={pl['zscore']['sharpe']}")
    print(f"  판정         : {pl['verdict'].upper()}")
    print()

    # ── Shuffle Test ──────────────────────────────────────────────────────
    print("=" * 70)
    print("Shuffle Test (n=10) — v2 10%, 실제 날짜 vs 셔플 날짜")
    print("  해석: ≥95%ile → PASS / ≥80%ile → MARGINAL")
    print("=" * 70)
    sh = shuffle_test(calc, stock_tickers, cfg, "stock", n_trials=10)

    print(f"\n  실제 Sharpe  : {sh['real_sharpe']}")
    print(f"  셔플 분포    : {sh['shuffled_sharpes']}")
    print(f"  Percentile   : {sh['percentile']:.1%}")
    print(f"  판정         : {sh['verdict'].upper()}")
    print()

    # ── 종합 ──────────────────────────────────────────────────────────────
    pass_count = sum(1 for v in [pl['verdict'], sh['verdict']] if v == "pass")
    marginal_count = sum(1 for v in [pl['verdict'], sh['verdict']] if v == "marginal")

    print("=" * 70)
    print("[종합 판정]")
    print("=" * 70)
    print(f"  Placebo : {pl['verdict'].upper()}  (Sharpe z={pl['zscore']['sharpe']})")
    print(f"  Shuffle : {sh['verdict'].upper()}  (percentile={sh['percentile']:.1%})")
    print(f"  pass={pass_count}, marginal={marginal_count}")

    if pass_count >= 2:
        overall = "PASS — v2 10% 사주 신호 통계적으로 유의. 가중치 유지 or 상향 검토."
    elif pass_count + marginal_count >= 2:
        overall = "MARGINAL — 부분 유의. v2 10% 가중치 유지, 추가 샘플 필요."
    elif pass_count + marginal_count == 1:
        overall = "MARGINAL(약) — v2 필터 전용 또는 10% 유지 (추가 검증 권장)."
    else:
        overall = "FAIL — 통계적 유의성 미확인. 필터 전용(0%) 설정 권장."

    print(f"\n  → {overall}")

    # ── 이전 결과 비교 ────────────────────────────────────────────────────
    print()
    print("=" * 70)
    print("[v1 30% vs v2 10% Null Test 비교]")
    print("=" * 70)
    print(f"  v1 30% Placebo z(sharpe) : -7.46  → FAIL")
    print(f"  v2 10% Placebo z(sharpe) : {pl['zscore']['sharpe']}  → {pl['verdict'].upper()}")
    print(f"  v1 30% Shuffle percentile: 0.0%  → FAIL")
    print(f"  v2 10% Shuffle percentile: {sh['percentile']:.1%}  → {sh['verdict'].upper()}")

    out = {
        "config": {"saju_weight": 0.10, "scorer": "saju_score_v2", "period": "2015-2024", "universe": "stock_30"},
        "placebo": pl,
        "shuffle": sh,
        "summary": {"pass_count": pass_count, "marginal_count": marginal_count, "verdict": overall},
    }
    out_file = Path(__file__).parent / "smoke_output_nulltest_v2.json"
    with out_file.open("w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n상세: {out_file}")


if __name__ == "__main__":
    main()

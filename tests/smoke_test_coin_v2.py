"""코인 유니버스 재설계 백테스트 — C 필터 전략.

변경 사항:
  유니버스: 10종 → 15종 (LTC/BCH/ATOM/DOT/UNI 추가)
  기간: 2025-01~2026-04 (15개월) → 2020-10~2024-12 (51개월)
  전략: C 필터 전용 (사주 < 30 제외, 퀀트만 랭킹)

비교:
  순수 퀀트 (필터 없음)
  C 필터 <30
  C 필터 <40

이전 결과 (10종, 15개월):
  실제 사주: Sharpe -1.21  CAGR -38%
  Placebo:   Sharpe -0.95 ± 0.23
  z-score:   -2.08  → FAIL
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


def run_v(label, calc, tickers, cfg, qcache):
    r = run_backtest(calc, tickers, cfg, "coin", quant_cache=qcache)
    s = r.stats
    if not s:
        print(f"  [{label:<30}] 결과 없음 (리밸런싱 부족)")
        return r
    print(f"  [{label:<30}] CAGR={s.get('cagr'):.1%}  Sharpe={s.get('sharpe')}  "
          f"MDD={s.get('mdd'):.1%}  hit={s.get('hit_rate'):.1%}  equity={s.get('final_equity')}")
    return r


def main():
    calc = SajuCalculator()
    coin_csv = project_root / "data" / "tickers" / "coin_universe_15.csv"
    tickers = load_tickers(coin_csv)
    coin_tickers = {s: r for s, r in tickers.items() if r.asset_class == "coin"}
    print(f"[UNIVERSE] 코인 {len(coin_tickers)}종: {sorted(coin_tickers.keys())}\n")

    # 2020-10부터: UNI(2020-09-17), AVAX(2020-09-21), DOT(2020-08-18) 상장 후 안정화
    start = datetime(2020, 10, 1)
    end = datetime(2024, 12, 31)
    print(f"[기간] {start.strftime('%Y-%m')} ~ {end.strftime('%Y-%m')} "
          f"({(end.year - start.year) * 12 + end.month - start.month}개월)\n")

    print("=" * 70)
    print("quant cache 빌드 (순수 퀀트 기준)...")
    print("=" * 70)
    shared_cache: dict = {}
    base_cfg = BacktestConfig(
        start=start, end=end, top_n=3, fast_macro=True,
        saju_filter_mode=True, saju_filter_threshold=0.0,
        label="coin_pure_quant",
    )
    pq = run_v("순수퀀트 (필터없음)", calc, coin_tickers, base_cfg, shared_cache)
    print()

    print("=" * 70)
    print("C 필터 전략 비교")
    print("=" * 70)
    cfg_30 = BacktestConfig(
        start=start, end=end, top_n=3, fast_macro=True,
        saju_filter_mode=True, saju_filter_threshold=30.0,
        label="coin_C_filter30",
    )
    c30 = run_v("C 필터 <30", calc, coin_tickers, cfg_30, shared_cache)

    cfg_40 = BacktestConfig(
        start=start, end=end, top_n=3, fast_macro=True,
        saju_filter_mode=True, saju_filter_threshold=40.0,
        label="coin_C_filter40",
    )
    c40 = run_v("C 필터 <40", calc, coin_tickers, cfg_40, shared_cache)

    cfg_saju30 = BacktestConfig(
        start=start, end=end, top_n=3, fast_macro=True,
        saju_weight=0.30,
        label="coin_saju30pct",
    )
    saju30 = run_v("사주 30% 가중 (이전 방식)", calc, coin_tickers, cfg_saju30, shared_cache)

    print()
    print("=" * 70)
    print("[종합 비교]")
    print("=" * 70)

    def fmt(r):
        s = r.stats
        if not s:
            return "결과 없음"
        return (f"CAGR={s.get('cagr'):.1%}  Sharpe={s.get('sharpe')}  "
                f"MDD={s.get('mdd'):.1%}  equity={s.get('final_equity')}")

    print(f"  BTC B&H (참고)         : CAGR≈+68%/yr (2020-2024 누적 +1,100%)")
    print(f"  순수 퀀트              : {fmt(pq)}")
    print(f"  C 필터 <30             : {fmt(c30)}")
    print(f"  C 필터 <40             : {fmt(c40)}")
    print(f"  사주 30% 가중(이전)    : {fmt(saju30)}")
    print()
    print("  ※ 이전 결과 (10종, 15개월, 2025-01~2026-04):")
    print("    사주 30% 가중: Sharpe=-1.21  CAGR=-38%  (Placebo z=-2.08 FAIL)")

    out = {
        "period": f"{start.strftime('%Y-%m')}~{end.strftime('%Y-%m')}",
        "universe": f"코인 {len(coin_tickers)}종",
        "pure_quant": pq.stats,
        "C_filter_30": c30.stats,
        "C_filter_40": c40.stats,
        "saju_30pct": saju30.stats,
    }
    out_file = Path(__file__).parent / "smoke_output_coin_v2.json"
    with out_file.open("w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n상세: {out_file}")


if __name__ == "__main__":
    main()

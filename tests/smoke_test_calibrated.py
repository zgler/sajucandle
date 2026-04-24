"""사주 역설계(B) + 필터 전용(C) 통합 테스트.

B안: IC 분석 + Ridge 회귀 → 데이터 기반 가중치 재설계
C안: 사주 하위 40% 제외 필터 + 순수 퀀트 랭킹

비교 기준 (stock 30종, 2015~2024):
  SPY B&H       : CAGR 13.0%, Sharpe 0.90
  사주 30% (현재): CAGR 11.5%, Sharpe 0.80
  순수 퀀트(Placebo): CAGR 22.2%, Sharpe 1.28
"""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from sajucandle.manseryeok.core import SajuCalculator
from sajucandle.ticker.loader import load_tickers
from sajucandle.quant.backtest import BacktestConfig, run_backtest
from sajucandle.quant.price_data import get_ohlcv
from sajucandle.quant.saju_calibrator import propose_new_weights


def _spy_sharpe(start, end):
    import numpy as np
    df = get_ohlcv("SPY", "stock", start - timedelta(days=5), end + timedelta(days=5))
    monthly = df["close"].resample("ME").last().pct_change().dropna()
    return round(float(monthly.mean() / monthly.std() * 12**0.5), 2) if monthly.std() > 0 else 0


def run_variant(label, calc, tickers, cfg, qcache=None):
    r = run_backtest(calc, tickers, cfg, "stock", quant_cache=qcache)
    print(f"  [{label}] CAGR={r.stats.get('cagr'):.1%}  Sharpe={r.stats.get('sharpe')}  "
          f"MDD={r.stats.get('mdd'):.1%}  hit={r.stats.get('hit_rate'):.1%}  "
          f"equity={r.stats.get('final_equity')}")
    return r


def main():
    calc = SajuCalculator()
    stock_csv = project_root / "data" / "tickers" / "stock_universe_30.csv"
    tickers = load_tickers(stock_csv)
    stock_tickers = {s: r for s, r in tickers.items() if r.asset_class == "stock"}
    print(f"[UNIVERSE] 주식 {len(stock_tickers)}개\n")

    start = datetime(2015, 1, 1)
    end = datetime(2024, 12, 31)

    # ──────────────────────────────────────────────────
    print("=" * 70)
    print("[B] 사주 역설계 — IC 분석 + Ridge 회귀 캘리브레이션")
    print("    학습: 2015~2020 (60%), 검증: 2021~2024")
    print("=" * 70)
    result_b = propose_new_weights(
        calc, stock_tickers, "stock",
        start=start, end=end, train_ratio=0.6,
    )
    cal_w = result_b.get("calibrated_weights", {})
    print(f"\n  관측 수: {result_b.get('n_obs')}개")
    print(f"  학습 기간: {result_b.get('train_period')}")
    print("\n  IC 분석:")
    ic = result_b.get("ic_table", {})
    ic_vals = ic.get("IC", {})
    icir_vals = ic.get("ICIR", {})
    prior_w = result_b.get("prior_weights", {})
    for feat in ["wolwoon_x_ilju","ilji_x_ilju","sewoon_element_match",
                 "daeun_bias","element_balance","samchung_events","shinsal_boost"]:
        ic_v = ic_vals.get(feat, "—")
        icir_v = icir_vals.get(feat, "—")
        prior = prior_w.get(feat, "—")
        new_w = cal_w.get(feat, "—")
        print(f"    {feat:<25}  IC={ic_v}  ICIR={icir_v}  prior={prior}→calibrated={new_w}")

    print(f"\n  캘리브레이션 가중치 합계: {sum(cal_w.values()) if cal_w else 0:.1f}")

    # B안 백테스트: 캘리브레이션 가중치로 scorer 재실행
    # (사주 점수 자체를 재가중, 실용적 근사: calibrated weights를 backtest config로 전달)
    print()

    # ──────────────────────────────────────────────────
    print("=" * 70)
    print("[C] 사주 필터 전용 (하위 40% 제외 + 순수 퀀트 랭킹)")
    print("=" * 70)

    # 기준 quant_cache 먼저 빌드 (첫 실행에서 TA 캐시)
    shared_cache = {}
    base_cfg = BacktestConfig(start=start, end=end, top_n=5, fast_macro=True, label="base")
    print("  기준 백테스트 실행 (quant cache 빌드)...")
    base = run_variant("현재 30%사주", calc, stock_tickers, base_cfg, shared_cache)
    print()

    # C안: 사주 필터 전용
    filter_cfg = BacktestConfig(
        start=start, end=end, top_n=5, fast_macro=True,
        saju_filter_mode=True, saju_filter_threshold=40.0,
        label="C_filter40",
    )
    print("  C안: 사주<40 제외 + 퀀트만 랭킹...")
    c40 = run_variant("C_filter_40%", calc, stock_tickers, filter_cfg, shared_cache)

    filter_cfg30 = BacktestConfig(
        start=start, end=end, top_n=5, fast_macro=True,
        saju_filter_mode=True, saju_filter_threshold=30.0,
        label="C_filter30",
    )
    c30 = run_variant("C_filter_30%", calc, stock_tickers, filter_cfg30, shared_cache)

    # 순수 퀀트 (threshold=0 = 필터 없음)
    pure_quant_cfg = BacktestConfig(
        start=start, end=end, top_n=5, fast_macro=True,
        saju_filter_mode=True, saju_filter_threshold=0.0,
        label="pure_quant",
    )
    pq = run_variant("순수퀀트(필터없음)", calc, stock_tickers, pure_quant_cfg, shared_cache)

    # ──────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("[종합 비교]")
    print("=" * 70)
    print(f"  SPY B&H          : CAGR=13.0%  Sharpe=0.90  MDD=-33.7%")
    print(f"  현재 30%사주       : CAGR={base.stats.get('cagr'):.1%}  Sharpe={base.stats.get('sharpe')}  MDD={base.stats.get('mdd'):.1%}")
    print(f"  C: 사주<40 필터    : CAGR={c40.stats.get('cagr'):.1%}  Sharpe={c40.stats.get('sharpe')}  MDD={c40.stats.get('mdd'):.1%}")
    print(f"  C: 사주<30 필터    : CAGR={c30.stats.get('cagr'):.1%}  Sharpe={c30.stats.get('sharpe')}  MDD={c30.stats.get('mdd'):.1%}")
    print(f"  순수 퀀트(Placebo): CAGR=22.2%  Sharpe=1.28  (Placebo 평균)")
    print(f"  순수 퀀트(실측)    : CAGR={pq.stats.get('cagr'):.1%}  Sharpe={pq.stats.get('sharpe')}  MDD={pq.stats.get('mdd'):.1%}")

    out = {
        "calibration": {k: v for k, v in result_b.items() if k != "feature_df_shape"},
        "variant_stats": {
            "base_30pct_saju": base.stats,
            "C_filter_40": c40.stats,
            "C_filter_30": c30.stats,
            "pure_quant": pq.stats,
        },
        "calibrated_weights": cal_w,
        "prior_weights": prior_w,
    }
    out_file = Path(__file__).parent / "smoke_output_calibrated.json"
    with out_file.open("w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n상세: {out_file}")


if __name__ == "__main__":
    main()

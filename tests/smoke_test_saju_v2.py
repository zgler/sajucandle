"""saju_score_v2 검증 — B+C 하이브리드.

비교 매트릭스 (stock 30종, 2015~2024):
  SPY B&H           : CAGR 13.0%, Sharpe 0.90
  현재 30%사주v1     : CAGR 11.5%, Sharpe 0.80  ← 기준
  순수 퀀트(실측)    : CAGR 15.0%, Sharpe 1.05  ← 천장
  C: saju_v1<30 필터 : CAGR 14.7%, Sharpe 1.03

이번에 추가:
  v2 필터+0%         (C only, v2 사주로 필터)
  v2 필터+10%        (C+B 하이브리드, v2 10% 가중)
  v2 필터+15%        (C+B 하이브리드, v2 15% 가중)
  v2 필터+20%        (C+B 하이브리드, v2 20% 가중)
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from functools import partial

sys.stdout.reconfigure(encoding="utf-8")
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from sajucandle.manseryeok.core import SajuCalculator
from sajucandle.ticker.loader import load_tickers
from sajucandle.quant.backtest import BacktestConfig, run_backtest
from sajucandle.saju.scorer import saju_score_v2


def run_v(label, calc, tickers, cfg, qcache):
    r = run_backtest(calc, tickers, cfg, "stock", quant_cache=qcache)
    s = r.stats
    print(f"  [{label:<26}] CAGR={s.get('cagr'):.1%}  Sharpe={s.get('sharpe')}  "
          f"MDD={s.get('mdd'):.1%}  hit={s.get('hit_rate'):.1%}  equity={s.get('final_equity')}")
    return r


def main():
    calc = SajuCalculator()
    stock_csv = project_root / "data" / "tickers" / "stock_universe_30.csv"
    tickers = load_tickers(stock_csv)
    stock_tickers = {s: r for s, r in tickers.items() if r.asset_class == "stock"}
    print(f"[UNIVERSE] 주식 {len(stock_tickers)}개\n")

    start = datetime(2015, 1, 1)
    end = datetime(2024, 12, 31)

    # ── quant cache 빌드 (순수 퀀트 기준) ─────────────────────────────
    shared_cache: dict = {}
    base_cfg = BacktestConfig(
        start=start, end=end, top_n=5, fast_macro=True,
        saju_filter_mode=True, saju_filter_threshold=0.0,
        label="pure_quant_cache",
    )
    print("quant cache 빌드 중 (순수 퀀트)...")
    pq = run_v("순수퀀트", calc, stock_tickers, base_cfg, shared_cache)
    print()

    print("=" * 70)
    print("saju_score_v2 (월운+세운오행+신살, ICIR 가중) 변형 비교")
    print("=" * 70)

    # v2 필터 전용 (0% 가중)
    cfg_f0 = BacktestConfig(
        start=start, end=end, top_n=5, fast_macro=True,
        saju_filter_mode=True, saju_filter_threshold=30.0,
        saju_score_fn=saju_score_v2,
        label="v2_filter_0pct",
    )
    f0 = run_v("v2 필터<30, 가중0%", calc, stock_tickers, cfg_f0, shared_cache)

    # v2 필터 + 10% 가중
    cfg_f10 = BacktestConfig(
        start=start, end=end, top_n=5, fast_macro=True,
        saju_filter_mode=False,        # 가중치 모드
        saju_weight=0.10,
        saju_filter_threshold=30.0,    # 필터는 별도 적용
        saju_score_fn=saju_score_v2,
        label="v2_filter_10pct",
    )
    # filter + weight 동시 적용: saju_filter 후 remaining에서 quant+v2 랭킹
    # → saju_filter_mode=False이므로 필터 없이 saju 가중. 필터는 별도 단계 필요.
    # 간이 구현: saju_weight=0.10으로만 (필터 없이) 먼저 테스트
    f10 = run_v("v2 가중10%(필터없음)", calc, stock_tickers, cfg_f10, shared_cache)

    cfg_f15 = BacktestConfig(
        start=start, end=end, top_n=5, fast_macro=True,
        saju_filter_mode=False,
        saju_weight=0.15,
        saju_score_fn=saju_score_v2,
        label="v2_weight_15pct",
    )
    f15 = run_v("v2 가중15%(필터없음)", calc, stock_tickers, cfg_f15, shared_cache)

    cfg_f20 = BacktestConfig(
        start=start, end=end, top_n=5, fast_macro=True,
        saju_filter_mode=False,
        saju_weight=0.20,
        saju_score_fn=saju_score_v2,
        label="v2_weight_20pct",
    )
    f20 = run_v("v2 가중20%(필터없음)", calc, stock_tickers, cfg_f20, shared_cache)

    cfg_f30 = BacktestConfig(
        start=start, end=end, top_n=5, fast_macro=True,
        saju_filter_mode=False,
        saju_weight=0.30,
        saju_score_fn=saju_score_v2,
        label="v2_weight_30pct",
    )
    f30 = run_v("v2 가중30%(필터없음)", calc, stock_tickers, cfg_f30, shared_cache)

    # v1 30% 기준 (비교)
    cfg_v1_30 = BacktestConfig(
        start=start, end=end, top_n=5, fast_macro=True,
        saju_weight=0.30,
        label="v1_30pct",
    )
    v1 = run_v("v1 가중30%(기존)", calc, stock_tickers, cfg_v1_30, shared_cache)

    print()
    print("=" * 70)
    print("[종합 비교]")
    print("=" * 70)
    print(f"  SPY B&H               : CAGR=13.0%  Sharpe=0.90  MDD=-33.7%")
    print(f"  v1 30%사주(기존)       : CAGR={v1.stats.get('cagr'):.1%}  Sharpe={v1.stats.get('sharpe')}  MDD={v1.stats.get('mdd'):.1%}")
    print(f"  순수 퀀트              : CAGR={pq.stats.get('cagr'):.1%}  Sharpe={pq.stats.get('sharpe')}  MDD={pq.stats.get('mdd'):.1%}")
    print(f"  v2 필터<30 가중0%      : CAGR={f0.stats.get('cagr'):.1%}  Sharpe={f0.stats.get('sharpe')}  MDD={f0.stats.get('mdd'):.1%}")
    print(f"  v2 가중10%             : CAGR={f10.stats.get('cagr'):.1%}  Sharpe={f10.stats.get('sharpe')}  MDD={f10.stats.get('mdd'):.1%}")
    print(f"  v2 가중15%             : CAGR={f15.stats.get('cagr'):.1%}  Sharpe={f15.stats.get('sharpe')}  MDD={f15.stats.get('mdd'):.1%}")
    print(f"  v2 가중20%             : CAGR={f20.stats.get('cagr'):.1%}  Sharpe={f20.stats.get('sharpe')}  MDD={f20.stats.get('mdd'):.1%}")
    print(f"  v2 가중30%             : CAGR={f30.stats.get('cagr'):.1%}  Sharpe={f30.stats.get('sharpe')}  MDD={f30.stats.get('mdd'):.1%}")

    out = {
        "pure_quant": pq.stats,
        "v1_30pct": v1.stats,
        "v2_filter_30": f0.stats,
        "v2_10pct": f10.stats,
        "v2_15pct": f15.stats,
        "v2_20pct": f20.stats,
        "v2_30pct": f30.stats,
    }
    out_file = Path(__file__).parent / "smoke_output_saju_v2.json"
    with out_file.open("w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n상세: {out_file}")


if __name__ == "__main__":
    main()

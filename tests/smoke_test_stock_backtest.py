"""주식 백테스트 Phase 3.

- 유니버스: S&P500 대형주 30종
- 기간: 2015-01-01 ~ 2024-12-31 (10년, 120회 리밸런싱)
- Top N: 5
- Null Test: Placebo 5회 + Shuffle 5회
- 벤치마크: SPY (Buy & Hold 비교)

코인과 달리 주식은 상장일/창립일이 명확 → 사주 기준 더 신뢰도 높음.
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
from sajucandle.quant.null_test import placebo_test, shuffle_test
from sajucandle.quant.price_data import get_ohlcv


def _spy_stats(start: datetime, end: datetime) -> dict:
    """SPY Buy & Hold 성과 (벤치마크)."""
    import numpy as np
    df = get_ohlcv("SPY", "stock", start - timedelta(days=5), end + timedelta(days=5))
    if df.empty:
        return {}
    df = df[(df.index >= str(start.date())) & (df.index <= str(end.date()))]
    if df.empty or len(df) < 2:
        return {}
    total_return = float(df["close"].iloc[-1] / df["close"].iloc[0] - 1)
    years = (end - start).days / 365.25
    cagr = (1 + total_return) ** (1 / years) - 1

    monthly = df["close"].resample("ME").last().pct_change().dropna()
    sharpe = float(monthly.mean() / monthly.std() * (12 ** 0.5)) if monthly.std() > 0 else 0
    peak = df["close"].cummax()
    mdd = float(((df["close"] - peak) / peak).min())
    return {
        "cagr": round(cagr, 4),
        "sharpe": round(sharpe, 2),
        "mdd": round(mdd, 4),
        "total_return": round(total_return, 4),
    }


def main():
    calc = SajuCalculator()
    stock_csv = project_root / "data" / "tickers" / "stock_universe_30.csv"
    tickers = load_tickers(stock_csv)
    stock_tickers = {s: r for s, r in tickers.items() if r.asset_class == "stock"}
    print(f"[UNIVERSE] 주식 {len(stock_tickers)}개: {list(stock_tickers.keys())}\n")

    start = datetime(2015, 1, 1)
    end = datetime(2024, 12, 31)

    cfg = BacktestConfig(
        start=start,
        end=end,
        top_n=5,
        fast_macro=True,
        label="stock_10y",
    )

    # ──────────────────────────────────────────────────
    print("=" * 70)
    print("[0] SPY Buy & Hold 벤치마크 (2015~2024)")
    print("=" * 70)
    spy = _spy_stats(start, end)
    for k, v in spy.items():
        print(f"  SPY {k}: {v}")
    print()

    # ──────────────────────────────────────────────────
    print("=" * 70)
    print("[1] 실제 사주 백테스트 (2015~2024, Top5)")
    print("=" * 70)
    real = run_backtest(calc, stock_tickers, cfg, "stock")
    for k, v in real.stats.items():
        print(f"  {k}: {v}")
    print(f"\n리밸런싱 {len(real.rebalance_log)}회")
    for log in real.rebalance_log[:3] + real.rebalance_log[-2:]:
        print(f"  {log['date']}: {log['held']}  net={log['net_return']:+.2%}  equity={log['equity']}")

    # ──────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("[2] Placebo Null Test (n=5)")
    print("=" * 70)
    placebo = placebo_test(calc, stock_tickers, cfg, "stock", n_trials=5)
    print(f"  실제 sharpe:   {placebo['real'].get('sharpe')}")
    print(f"  랜덤 sharpe:   {placebo['placebo_mean'].get('sharpe')} ± {placebo['placebo_std'].get('sharpe')}")
    print(f"  z-score:       {placebo['zscore'].get('sharpe')}")
    print(f"  판정:          {placebo['verdict'].upper()}")
    for m in ["cagr", "sharpe", "sortino", "hit_rate"]:
        print(f"    {m:<10}  real={placebo['real'].get(m)}  "
              f"rand={placebo['placebo_mean'].get(m)}±{placebo['placebo_std'].get(m)}  "
              f"z={placebo['zscore'].get(m)}")

    # ──────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("[3] Shuffle Test (n=5)")
    print("=" * 70)
    shuf = shuffle_test(calc, stock_tickers, cfg, "stock", n_trials=5)
    print(f"  실제 sharpe:   {shuf['real_sharpe']}")
    print(f"  셔플 분포:     {[round(s, 2) for s in shuf['shuffled_sharpes']]}")
    print(f"  백분위:        {shuf['percentile']:.1%}")
    print(f"  판정:          {shuf['verdict'].upper()}")

    # ──────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("[4] 종합 판정")
    print("=" * 70)
    verdicts = {
        "placebo": placebo["verdict"],
        "shuffle": shuf["verdict"],
    }
    pass_cnt = sum(1 for v in verdicts.values() if v == "pass")
    marg_cnt = sum(1 for v in verdicts.values() if v == "marginal")
    spy_sharpe = spy.get("sharpe", 0)
    real_sharpe = real.stats.get("sharpe", 0)
    alpha = round(real_sharpe - spy_sharpe, 2) if spy_sharpe else None
    print(f"  SPY sharpe vs 사주 sharpe: {spy_sharpe} vs {real_sharpe}  (alpha: {alpha})")
    print(f"  Placebo: {verdicts['placebo'].upper()}")
    print(f"  Shuffle: {verdicts['shuffle'].upper()}")
    print()
    if pass_cnt + marg_cnt >= 2:
        final = "주식에서 사주 신호 확인 → 30% 가중치 유지"
    elif pass_cnt + marg_cnt == 1:
        final = "혼재 → 추가 검증 필요 (기간 확장, 유니버스 확대)"
    else:
        final = "주식도 FAIL → 사주 필터 전용 격하 강력 시사"
    print(f"  결론: {final}")

    out = {
        "spy_benchmark": spy,
        "real_backtest": real.stats,
        "real_log_sample": real.rebalance_log[:10],
        "placebo_test": placebo,
        "shuffle_test": shuf,
        "pass_count": pass_cnt,
        "marginal_count": marg_cnt,
        "final_verdict": final,
    }
    out_file = Path(__file__).parent / "smoke_output_stock_backtest.json"
    with out_file.open("w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n상세: {out_file}")


if __name__ == "__main__":
    main()

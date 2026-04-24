"""Regime-conditional Signal Engine 검증.

전략:
  Sideways 레짐 → 사주 필터 ON (C 전략 활성)
  Bull / Bear   → 사주 필터 OFF (순수 퀀트)

근거:
  Phase 2 코인 Regime 실험: Sideways에서 z=1.08 (유일한 marginal edge)
  Bull/Bear에서 사주는 edge 없음 → 필터 낭비

비교:
  A. 순수 퀀트 (레짐 무관)
  B. C 필터 항상 ON (기존 전략)
  C. Regime-conditional (횡보 시에만 ON)  ← 신규
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
from sajucandle.signal.regime import detect_regime_monthly_series, Regime


def print_regime_distribution(asset_class, start, end):
    series = detect_regime_monthly_series(asset_class, start, end)
    counts = {r.value: 0 for r in Regime}
    for r in series.values():
        counts[r.value] += 1
    total = sum(counts.values())
    print(f"  레짐 분포 ({total}개월):")
    for regime, cnt in counts.items():
        if regime == "unknown":
            continue
        pct = cnt / total * 100 if total else 0
        print(f"    {regime:<9}: {cnt}개월 ({pct:.0f}%)")
    return series


def run_v(label, calc, tickers, cfg, qcache, asset):
    r = run_backtest(calc, tickers, cfg, asset, quant_cache=qcache)
    s = r.stats
    if not s:
        print(f"  [{label:<35}] 결과 없음")
        return r
    print(f"  [{label:<35}] CAGR={s.get('cagr'):.1%}  Sharpe={s.get('sharpe')}  "
          f"MDD={s.get('mdd'):.1%}  hit={s.get('hit_rate'):.1%}")
    return r


def run_regime_conditional_backtest(
    calc, tickers, asset_class, start, end, regime_series,
    top_n=5, saju_threshold=30.0, fast_macro=True,
    shared_cache=None,
):
    """레짐별로 사주 필터를 on/off하는 백테스트.

    매월: 레짐 판단 → Sideways면 C 필터, 나머지는 순수 퀀트.
    backtest.py의 run_backtest를 활용하되 월별로 config를 다르게 해야 해서
    여기서는 두 개의 결과를 합산하는 방식으로 구현.
    """
    import numpy as np
    import pandas as pd
    from sajucandle.quant.backtest import (
        _month_starts, BacktestResult, _forward_return,
        _quant_score_backtest, COST_STOCK, COST_COIN,
    )
    from sajucandle.quant.price_data import get_ohlcv
    from sajucandle.ticker.saju_resolver import resolve_ticker_saju
    from sajucandle.saju.scorer import saju_score
    from datetime import timedelta

    rebalance_dates = _month_starts(start, end)
    if len(rebalance_dates) < 2:
        return None

    bench_symbol = "SPY" if asset_class == "stock" else "BTC-USD"
    bench_df = get_ohlcv(
        bench_symbol, asset_class,
        start - timedelta(days=400), end + timedelta(days=5),
    )

    cost = COST_STOCK if asset_class == "stock" else COST_COIN
    if shared_cache is None:
        shared_cache = {}

    resolved_cache = {}
    for sym, rec in tickers.items():
        if rec.asset_class != asset_class:
            continue
        try:
            resolved_cache[sym] = resolve_ticker_saju(calc, rec)
        except Exception:
            continue

    equity = 1.0
    curve = {}
    log = []
    prev_holdings = set()

    for i, rb_date in enumerate(rebalance_dates[:-1]):
        next_date = rebalance_dates[i + 1]
        curve[rb_date] = equity

        date_str = rb_date.strftime("%Y-%m-%d")
        regime = regime_series.get(date_str, Regime.UNKNOWN)
        use_saju_filter = (regime == Regime.SIDEWAYS)

        macro_val = 50.0  # fast_macro

        scores = []
        for sym, resolved in resolved_cache.items():
            try:
                if not resolved.get("primary_pillar"):
                    continue
                primary_source = resolved["primary_source"]
                if primary_source == "founding":
                    primary_saju = resolved["components"]["founding"]["saju"]
                elif primary_source == "listing":
                    primary_saju = resolved["components"]["listing"]["saju"]
                else:
                    primary_saju = resolved["components"]["transition"][0]["saju"]

                sc = saju_score(
                    calc=calc,
                    ticker_primary_pillar=resolved["primary_pillar"],
                    ticker_saju=primary_saju,
                    target_dt=rb_date,
                )
                s = sc["total_100"]
            except Exception:
                continue

            # 횡보장에서만 필터 적용
            if use_saju_filter and s < saju_threshold:
                continue

            cache_key = (sym, date_str)
            if cache_key in shared_cache:
                q = shared_cache[cache_key]
            else:
                q = _quant_score_backtest(sym, asset_class, rb_date, macro_val, bench_df)
                shared_cache[cache_key] = q

            scores.append({"symbol": sym, "saju": s, "quant": q, "final": q})

        scores.sort(key=lambda x: x["final"], reverse=True)
        top = scores[:top_n]
        held = {x["symbol"] for x in top}

        turnover = (len(prev_holdings.symmetric_difference(held)) /
                    max(len(held), 1) / 2) if prev_holdings else 1.0
        rets = [_forward_return(x["symbol"], asset_class, rb_date, next_date)
                for x in top]
        period_return = float(np.mean(rets)) if rets else 0.0
        period_return_net = period_return - turnover * cost
        equity *= (1 + period_return_net)

        log.append({
            "date": date_str,
            "regime": regime.value,
            "saju_filter": use_saju_filter,
            "held": [x["symbol"] for x in top],
            "net_return": round(period_return_net, 4),
            "equity": round(equity, 4),
        })
        prev_holdings = held

    curve[rebalance_dates[-1]] = equity
    eq_series = pd.Series(curve)
    rets_s = pd.Series([l["net_return"] for l in log])

    if len(rets_s) == 0:
        return None

    annualized = (equity ** (12 / len(rets_s))) - 1
    sharpe = (rets_s.mean() / rets_s.std() * np.sqrt(12)) if rets_s.std() > 0 else 0
    peak = eq_series.cummax()
    dd = (eq_series - peak) / peak
    mdd = float(dd.min())
    hit = float((rets_s > 0).mean())

    # 레짐별 히트율
    sideways_rets = [l["net_return"] for l in log if l["regime"] == "sideways"]
    bull_rets = [l["net_return"] for l in log if l["regime"] == "bull"]
    bear_rets = [l["net_return"] for l in log if l["regime"] == "bear"]

    return {
        "cagr": round(annualized, 4),
        "sharpe": round(sharpe, 2),
        "mdd": round(mdd, 4),
        "hit_rate": round(hit, 3),
        "final_equity": round(equity, 4),
        "n_rebalances": len(rets_s),
        "sideways_avg": round(float(np.mean(sideways_rets)), 4) if sideways_rets else None,
        "bull_avg": round(float(np.mean(bull_rets)), 4) if bull_rets else None,
        "bear_avg": round(float(np.mean(bear_rets)), 4) if bear_rets else None,
        "regime_log": log,
    }


def main():
    calc = SajuCalculator()
    stock_csv = project_root / "data" / "tickers" / "stock_universe_30.csv"
    tickers = load_tickers(stock_csv)
    stock_tickers = {s: r for s, r in tickers.items() if r.asset_class == "stock"}
    print(f"[UNIVERSE] 주식 {len(stock_tickers)}종\n")

    start = datetime(2015, 1, 1)
    end = datetime(2024, 12, 31)
    asset = "stock"

    print("레짐 분포 분석 (SPY 기준, 3개월 롤링)...")
    regime_series = print_regime_distribution(asset, start, end)
    print()

    # ── quant cache 빌드 ───────────────────────────────────────────────
    print("=" * 70)
    shared_cache = {}
    base_cfg = BacktestConfig(
        start=start, end=end, top_n=5, fast_macro=True,
        saju_filter_mode=True, saju_filter_threshold=0.0,
        label="pure_quant",
    )
    print("A. 순수 퀀트 (레짐 무관, 필터 없음)")
    pq = run_v("순수퀀트", calc, stock_tickers, base_cfg, shared_cache, asset)

    # ── C 필터 항상 ON ─────────────────────────────────────────────────
    print()
    c_cfg = BacktestConfig(
        start=start, end=end, top_n=5, fast_macro=True,
        saju_filter_mode=True, saju_filter_threshold=30.0,
        label="C_filter_always",
    )
    print("B. C 필터 항상 ON (사주<30 제외)")
    c_always = run_v("C필터 항상ON", calc, stock_tickers, c_cfg, shared_cache, asset)

    # ── Regime-conditional ─────────────────────────────────────────────
    print()
    print("C. Regime-conditional (횡보장에서만 사주 필터 ON)")
    rc = run_regime_conditional_backtest(
        calc, stock_tickers, asset, start, end,
        regime_series, top_n=5, saju_threshold=30.0,
        shared_cache=shared_cache,
    )
    if rc:
        print(f"  [{'Regime-conditional':<35}] CAGR={rc['cagr']:.1%}  "
              f"Sharpe={rc['sharpe']}  MDD={rc['mdd']:.1%}  hit={rc['hit_rate']:.1%}")
        print(f"    레짐별 평균 월수익: "
              f"Bull={rc['bull_avg']:.2%}  Bear={rc['bear_avg']:.2%}  "
              f"Sideways={rc['sideways_avg']:.2%}")

    # ── 종합 ───────────────────────────────────────────────────────────
    print()
    print("=" * 70)
    print("[종합 비교]")
    print("=" * 70)
    print(f"  SPY B&H              : CAGR=13.0%  Sharpe=0.90  MDD=-33.7%")
    s = pq.stats
    print(f"  A. 순수 퀀트         : CAGR={s.get('cagr'):.1%}  Sharpe={s.get('sharpe')}  MDD={s.get('mdd'):.1%}")
    s = c_always.stats
    print(f"  B. C필터 항상ON      : CAGR={s.get('cagr'):.1%}  Sharpe={s.get('sharpe')}  MDD={s.get('mdd'):.1%}")
    if rc:
        print(f"  C. Regime-cond       : CAGR={rc['cagr']:.1%}  Sharpe={rc['sharpe']}  MDD={rc['mdd']:.1%}")

    out = {
        "period": "2015-2024",
        "regime_distribution": {k: v.value for k, v in regime_series.items()},
        "pure_quant": pq.stats,
        "C_filter_always": c_always.stats,
        "regime_conditional": rc,
    }
    out_file = Path(__file__).parent / "smoke_output_regime_engine.json"
    with out_file.open("w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n상세: {out_file}")


if __name__ == "__main__":
    main()

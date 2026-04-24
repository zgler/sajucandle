"""Null Test — 사주 신호 정당성 검증 (PRD §12).

3종:
  1. Placebo Test  : 실제 사주 → 랜덤 점수로 대체, 10회 독립 시행
                     진짜가 랜덤 평균 + 2σ 이상 → 사주 신호 있음
  2. Shuffle Test  : 종목의 상장일을 무작위 셔플 → 같은 룰
                     실제 배치가 셔플 분포 상위 5% 내 → 통과
  3. Regime Decomposition : 상승/하락/횡보 각각에서 엣지 측정

통과·실패 프로토콜 (PRD §12-4):
  3개 통과 → 30% 유지 또는 40% 상향 검토
  2개 통과 → 30% 유지, 활성 레짐만
  1개 이하 → 사주는 필터 전용으로 격하
  0개 → 엔진 재설계
"""

from __future__ import annotations

import random
import statistics
from datetime import datetime, timedelta
from typing import Dict, List

import numpy as np
import pandas as pd

from ..manseryeok.core import SajuCalculator
from ..ticker.schema import TickerRecord
from .backtest import BacktestConfig, run_backtest
from .price_data import get_ohlcv


def _random_saju_score_fn(seed: int = 0):
    """랜덤 사주 점수 생성 함수 (placebo).

    scorer.saju_score와 동일 시그니처. total_100만 0~100 랜덤 반환.
    """
    rng = random.Random(seed)

    def _fn(calc, ticker_primary_pillar, ticker_saju, target_dt, **kwargs):
        return {
            "total_100": rng.uniform(0, 100),
            "breakdown": {},
            "weighted": {},
            "weights": {},
        }
    return _fn


def placebo_test(
    calc: SajuCalculator,
    records: Dict[str, TickerRecord],
    config: BacktestConfig,
    asset_class: str,
    n_trials: int = 10,
) -> Dict:
    """Placebo: 랜덤 사주 점수로 10회 백테스트 → 분포 산출.

    Returns
    -------
    {
      "real": {"cagr": ..., "sharpe": ...},
      "placebo_mean": {...},
      "placebo_std": {...},
      "zscore": {"cagr": ..., "sharpe": ...},
      "verdict": "pass" | "fail" | "marginal",
      "confidence": float   # 0~1
    }
    """
    # 실제 (quant_cache 빌드)
    shared_quant_cache: Dict = {}
    real = run_backtest(calc, records, config, asset_class, quant_cache=shared_quant_cache)
    real_stats = real.stats

    # 랜덤 시행 — quant_cache 재사용으로 TA 재계산 생략
    placebo_results = []
    for trial in range(n_trials):
        cfg = BacktestConfig(
            start=config.start, end=config.end,
            rebalance_freq=config.rebalance_freq,
            top_n=config.top_n, saju_weight=config.saju_weight,
            saju_score_fn=_random_saju_score_fn(seed=100 + trial),
            label=f"placebo_{trial}",
            fast_macro=config.fast_macro,
        )
        r = run_backtest(calc, records, cfg, asset_class, quant_cache=shared_quant_cache)
        placebo_results.append(r.stats)

    def _mean_std(key):
        vals = [p.get(key, 0) for p in placebo_results if key in p]
        if not vals:
            return 0, 0
        if len(vals) < 2:
            return vals[0], 0
        return statistics.mean(vals), statistics.stdev(vals)

    metrics = ["cagr", "sharpe", "sortino", "hit_rate"]
    placebo_mean = {}
    placebo_std = {}
    zscore = {}
    for m in metrics:
        pm, ps = _mean_std(m)
        placebo_mean[m] = round(pm, 4)
        placebo_std[m] = round(ps, 4)
        if ps > 0:
            zscore[m] = round((real_stats.get(m, 0) - pm) / ps, 2)
        else:
            zscore[m] = None

    # 판정: sharpe z-score가 +2σ 이상이면 pass, 0~+2 marginal, 그 아래 fail
    sharpe_z = zscore.get("sharpe")
    if sharpe_z is None:
        verdict = "inconclusive"
    elif sharpe_z >= 2.0:
        verdict = "pass"
    elif sharpe_z >= 0.5:
        verdict = "marginal"
    else:
        verdict = "fail"

    return {
        "real": real_stats,
        "placebo_mean": placebo_mean,
        "placebo_std": placebo_std,
        "zscore": zscore,
        "verdict": verdict,
        "n_trials": n_trials,
        "asset_class": asset_class,
    }


def shuffle_test(
    calc: SajuCalculator,
    records: Dict[str, TickerRecord],
    config: BacktestConfig,
    asset_class: str,
    n_trials: int = 10,
) -> Dict:
    """Shuffle Test — 상장일/창립일을 종목 간 무작위 셔플.

    실제 배치 성과가 셔플 분포 상위 5% 내에 있으면 통과.
    """
    target_recs = {s: r for s, r in records.items() if r.asset_class == asset_class}
    symbols = list(target_recs.keys())

    # 실제 (quant_cache 빌드)
    shared_quant_cache: Dict = {}
    real_result = run_backtest(calc, target_recs, config, asset_class, quant_cache=shared_quant_cache)
    real = real_result.stats
    shuffled_sharpes = []

    for trial in range(n_trials):
        rng = random.Random(500 + trial)
        rotated = symbols.copy()
        rng.shuffle(rotated)
        swapped: Dict[str, TickerRecord] = {}
        for orig_sym, new_sym in zip(symbols, rotated):
            orig = target_recs[orig_sym]
            donor = target_recs[new_sym]
            import copy
            new_rec = copy.deepcopy(orig)
            new_rec.founding_date = donor.founding_date
            new_rec.founding_time = donor.founding_time
            new_rec.listing_date = donor.listing_date
            new_rec.listing_time = donor.listing_time
            new_rec.transition_points = donor.transition_points
            new_rec.birth_city = donor.birth_city
            swapped[orig_sym] = new_rec
        # quant_cache 재사용 (사주 날짜가 바뀌어도 같은 symbol, date의 TA는 동일)
        r = run_backtest(calc, swapped, config, asset_class, quant_cache=shared_quant_cache)
        shuffled_sharpes.append(r.stats.get("sharpe", 0))

    real_sharpe = real.get("sharpe", 0)
    # 실제가 셔플 분포에서 몇 분위?
    percentile = sum(1 for s in shuffled_sharpes if s < real_sharpe) / max(len(shuffled_sharpes), 1)

    if percentile >= 0.95:
        verdict = "pass"
    elif percentile >= 0.8:
        verdict = "marginal"
    else:
        verdict = "fail"

    return {
        "real_sharpe": round(real_sharpe, 3),
        "shuffled_sharpes": [round(s, 3) for s in shuffled_sharpes],
        "percentile": round(percentile, 3),
        "verdict": verdict,
        "n_trials": n_trials,
        "asset_class": asset_class,
    }


def _classify_regime(bench_return: float, threshold: float = 0.05) -> str:
    """단일 기간 벤치마크 수익률로 레짐 분류."""
    if bench_return >= threshold:
        return "bull"
    if bench_return <= -threshold:
        return "bear"
    return "sideways"


def regime_decomposition_test(
    calc: SajuCalculator,
    records: Dict[str, TickerRecord],
    config: BacktestConfig,
    asset_class: str,
    n_placebo: int = 5,
    regime_threshold: float = 0.05,
) -> Dict:
    """Regime Decomposition Test — Bull/Bear/Sideways 레짐별 사주 엣지 측정.

    알고리즘:
    1. 실제 사주 백테스트 → 기간별 순수익 수열
    2. 벤치마크(BTC or SPY) 기간 수익률로 각 기간을 Bull/Bear/Sideways 분류
    3. 레짐별로 실제 수익률 평균 계산
    4. Placebo n회 시행 → 레짐별 랜덤 기준선 산출
    5. 레짐별 excess return = 실제 - 랜덤 기준선

    판정:
      Bull/Bear/Sideways 중 어느 레짐에서 실제가 placebo 평균 + 1σ 이상이면
      해당 레짐에서 "edge_detected"
    """
    bench_symbol = "BTC-USD" if asset_class == "coin" else "SPY"

    # 벤치마크 데이터 로드 (전 기간)
    bench_df = get_ohlcv(
        bench_symbol, asset_class,
        config.start - timedelta(days=10), config.end + timedelta(days=10),
    )

    # 리밸런싱 날짜 생성 (backtest.py의 _month_starts와 동일 로직)
    dates = []
    cur = datetime(config.start.year, config.start.month, 1)
    if cur < config.start:
        cur = datetime(
            config.start.year + (config.start.month // 12),
            (config.start.month % 12) + 1, 1,
        )
    while cur <= config.end:
        dates.append(cur)
        if cur.month == 12:
            cur = datetime(cur.year + 1, 1, 1)
        else:
            cur = datetime(cur.year, cur.month + 1, 1)

    def _bench_return(start: datetime, end: datetime) -> float:
        if bench_df.empty:
            return 0.0
        sub = bench_df[
            (bench_df.index >= pd.Timestamp(start)) &
            (bench_df.index <= pd.Timestamp(end))
        ]
        if sub.empty or len(sub) < 2:
            return 0.0
        return float(sub["close"].iloc[-1] / sub["close"].iloc[0] - 1)

    # 실제 백테스트 (quant_cache 빌드)
    shared_quant_cache: Dict = {}
    real_result = run_backtest(calc, records, config, asset_class, quant_cache=shared_quant_cache)
    real_log = real_result.rebalance_log

    # 레짐 분류
    periods_with_regime = []
    for log in real_log:
        start_dt = datetime.strptime(log["date"], "%Y-%m-%d")
        end_dt = datetime.strptime(log["next_date"], "%Y-%m-%d")
        br = _bench_return(start_dt, end_dt)
        regime = _classify_regime(br, regime_threshold)
        periods_with_regime.append({
            "date": log["date"],
            "net_return": log["net_return"],
            "bench_return": round(br, 4),
            "regime": regime,
        })

    def _regime_avg(log_list, regime: str) -> float:
        vals = [p["net_return"] for p in log_list if p["regime"] == regime]
        return float(np.mean(vals)) if vals else float("nan")

    real_by_regime = {
        r: _regime_avg(periods_with_regime, r)
        for r in ["bull", "bear", "sideways"]
    }
    regime_counts = {
        r: sum(1 for p in periods_with_regime if p["regime"] == r)
        for r in ["bull", "bear", "sideways"]
    }

    # Placebo 시행 → 레짐별 기준선
    placebo_by_regime: Dict[str, List[float]] = {"bull": [], "bear": [], "sideways": []}
    for trial in range(n_placebo):
        cfg = BacktestConfig(
            start=config.start, end=config.end,
            rebalance_freq=config.rebalance_freq,
            top_n=config.top_n, saju_weight=config.saju_weight,
            saju_score_fn=_random_saju_score_fn(seed=800 + trial),
            label=f"regime_placebo_{trial}",
            fast_macro=config.fast_macro,
        )
        p_result = run_backtest(calc, records, cfg, asset_class, quant_cache=shared_quant_cache)
        p_log = p_result.rebalance_log

        # 같은 날짜 구조로 레짐 매핑 (이미 분류된 periods_with_regime 사용)
        date_regime = {p["date"]: p["regime"] for p in periods_with_regime}
        p_by_regime: Dict[str, List[float]] = {"bull": [], "bear": [], "sideways": []}
        for lg in p_log:
            r = date_regime.get(lg["date"])
            if r:
                p_by_regime[r].append(lg["net_return"])
        for r in ["bull", "bear", "sideways"]:
            avg = float(np.mean(p_by_regime[r])) if p_by_regime[r] else float("nan")
            placebo_by_regime[r].append(avg)

    def _safe_mean_std(vals):
        clean = [v for v in vals if not (isinstance(v, float) and np.isnan(v))]
        if not clean:
            return float("nan"), float("nan")
        m = float(np.mean(clean))
        s = float(np.std(clean, ddof=1)) if len(clean) > 1 else 0.0
        return m, s

    regime_stats = {}
    edge_detected = []
    for r in ["bull", "bear", "sideways"]:
        pm, ps = _safe_mean_std(placebo_by_regime[r])
        real_avg = real_by_regime[r]
        count = regime_counts[r]
        if not np.isnan(real_avg) and not np.isnan(pm) and ps > 0:
            z = (real_avg - pm) / ps
            edge = z >= 1.0
        else:
            z = float("nan")
            edge = False
        regime_stats[r] = {
            "count": count,
            "real_avg_return": round(real_avg, 4) if not np.isnan(real_avg) else None,
            "placebo_avg": round(pm, 4) if not np.isnan(pm) else None,
            "placebo_std": round(ps, 4) if not np.isnan(ps) else None,
            "zscore": round(z, 2) if not np.isnan(z) else None,
            "edge_detected": edge,
        }
        if edge:
            edge_detected.append(r)

    if len(edge_detected) >= 2:
        verdict = "pass"
    elif len(edge_detected) == 1:
        verdict = "marginal"
    else:
        verdict = "fail"

    return {
        "regime_stats": regime_stats,
        "edge_detected_in": edge_detected,
        "verdict": verdict,
        "periods": periods_with_regime,
        "real_overall_sharpe": real_result.stats.get("sharpe"),
        "n_placebo": n_placebo,
        "asset_class": asset_class,
        "regime_threshold": regime_threshold,
    }

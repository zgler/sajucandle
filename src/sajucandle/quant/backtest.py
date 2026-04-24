"""백테스트 프레임워크.

Phase 1 범위 (축약):
- 월 1회 리밸런싱 (월초)
- Top N 보유 (균등 가중)
- 거래비용: 주식 왕복 15bp, 코인 왕복 10bp
- 사주 + TA + Macro만 조합 (FA·OnChain은 "현재 스냅샷" 의존성 때문에 과거 시점 정확 불가)

사용 시나리오:
  1. 실제 성과 측정
  2. **Null Test**: 사주 점수만 변형해서 동일 공식 실행 → 사주 엣지 검증

성과 지표:
- CAGR, Sharpe, Sortino, MDD, 턴오버, 히트레이트
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Callable, Dict, List, Optional

import numpy as np
import pandas as pd

from ..manseryeok.core import SajuCalculator
from ..ticker.schema import TickerRecord
from .price_data import get_ohlcv
from .technical import ta_score_stock, ta_score_coin
from .macro import macro_score_stock
from .crypto_macro import crypto_macro_score
from ..saju.scorer import saju_score
from ..ticker.saju_resolver import resolve_ticker_saju


# Phase 1 백테스트용 간이 가중치 (FA·OnChain 제외로 재분배)
SAJU_W = 0.30
QUANT_W = 0.70
QUANT_SUB_W_STOCK = {"macro": 0.33, "ta": 0.67}
QUANT_SUB_W_COIN = {"macro": 0.33, "ta": 0.67}

# 거래비용 (왕복)
COST_STOCK = 0.0015   # 15bp
COST_COIN = 0.0010    # 10bp


@dataclass
class BacktestConfig:
    start: datetime
    end: datetime
    rebalance_freq: str = "monthly"   # 현재 월간만 지원
    top_n: int = 10
    saju_weight: float = SAJU_W
    saju_score_fn: Optional[Callable] = None  # Null Test용 사주 변형 함수
    label: str = "default"
    fast_macro: bool = True  # True면 매 리밸런싱마다 FRED/yfinance 호출 생략, 상수 50 사용
    # C안: 사주 필터 전용 모드
    saju_filter_mode: bool = False     # True면 사주는 가중치 0, 하위 threshold% 제외 필터만
    saju_filter_threshold: float = 40.0  # 사주 점수 이 값 미만이면 후보 제외
    # B안: 캘리브레이션된 가중치 (제공 시 scorer.py 기본값 대신 사용)
    saju_weights_override: Optional[Dict] = None


@dataclass
class BacktestResult:
    config: BacktestConfig
    equity_curve: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    rebalance_log: List[Dict] = field(default_factory=list)
    stats: Dict = field(default_factory=dict)
    # (sym, date_str) → quant_score. Null Test에서 재사용해 TA 재계산 생략.
    quant_cache: Dict = field(default_factory=dict)


def _month_starts(start: datetime, end: datetime) -> List[datetime]:
    dates = []
    cur = datetime(start.year, start.month, 1)
    if cur < start:
        cur = datetime(start.year + (start.month // 12),
                       (start.month % 12) + 1, 1)
    while cur <= end:
        dates.append(cur)
        # 다음 달 1일
        if cur.month == 12:
            cur = datetime(cur.year + 1, 1, 1)
        else:
            cur = datetime(cur.year, cur.month + 1, 1)
    return dates


def _ta_score_for(symbol: str, asset: str, asof: datetime,
                   bench_df: pd.DataFrame) -> float:
    lookback = 400
    df = get_ohlcv(symbol, asset, asof - timedelta(days=lookback), asof)
    if df.empty or len(df) < 30:
        return 50.0
    if asset == "stock":
        return ta_score_stock(df, bench_df)["total"]
    return ta_score_coin(df, bench_df)["total"]


def _quant_score_backtest(symbol: str, asset: str, asof: datetime,
                          macro_val: float, bench_df: pd.DataFrame) -> float:
    ta = _ta_score_for(symbol, asset, asof, bench_df)
    w = QUANT_SUB_W_STOCK if asset == "stock" else QUANT_SUB_W_COIN
    return w["macro"] * macro_val + w["ta"] * ta


def _forward_return(symbol: str, asset: str, start: datetime, end: datetime) -> float:
    """start → end 사이 수익률."""
    df = get_ohlcv(symbol, asset, start - timedelta(days=5), end + timedelta(days=5))
    if df.empty:
        return 0.0
    # start 이상 첫 종가, end 이하 마지막 종가
    df = df[(df.index >= pd.Timestamp(start)) & (df.index <= pd.Timestamp(end))]
    if df.empty or len(df) < 2:
        return 0.0
    return float(df["close"].iloc[-1] / df["close"].iloc[0] - 1)


def run_backtest(
    calc: SajuCalculator,
    records: Dict[str, TickerRecord],
    config: BacktestConfig,
    asset_class: str,
    quant_cache: Optional[Dict] = None,  # 제공 시 TA 재계산 생략 (Null Test 최적화)
) -> BacktestResult:
    """간이 백테스트.

    Phase 1 단순화:
    - 월초에 리밸런싱 (다음 달 1일까지 보유)
    - 사주는 매 시점 정확히 계산 (만세력 deterministic)
    - 퀀트는 TA + Macro만 (FA/OnChain 생략)
    """
    result = BacktestResult(config=config)
    rebalance_dates = _month_starts(config.start, config.end)
    if len(rebalance_dates) < 2:
        return result

    # 공통 벤치마크 데이터 (전 기간)
    bench_symbol = "SPY" if asset_class == "stock" else "BTC-USD"
    bench_df = get_ohlcv(
        bench_symbol, asset_class,
        config.start - timedelta(days=400), config.end + timedelta(days=5),
    )

    equity = 1.0
    curve = {}
    cost = COST_STOCK if asset_class == "stock" else COST_COIN
    saju_fn = config.saju_score_fn or saju_score

    # 티커의 resolve_ticker_saju 결과는 target_dt에 의존하지 않음 → 한 번만 계산
    resolved_cache: Dict[str, Dict] = {}
    for sym, rec in records.items():
        if rec.asset_class != asset_class:
            continue
        try:
            resolved_cache[sym] = resolve_ticker_saju(calc, rec)
        except Exception:
            continue

    prev_holdings: set = set()

    for i, rb_date in enumerate(rebalance_dates[:-1]):
        next_date = rebalance_dates[i + 1]
        curve[rb_date] = equity

        # Macro at rb_date
        if config.fast_macro:
            macro_val = 50.0  # Null Test 속도 우선, 사주 엣지 측정이 목적
        else:
            try:
                if asset_class == "stock":
                    macro_val = macro_score_stock(asof=rb_date)["total"]
                else:
                    macro_val = crypto_macro_score(asof=rb_date)["total"]
            except Exception:
                macro_val = 50.0

        # 각 종목 스코어
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
                sc_result = saju_fn(
                    calc=calc,
                    ticker_primary_pillar=resolved["primary_pillar"],
                    ticker_saju=primary_saju,
                    target_dt=rb_date,
                )
                s = sc_result["total_100"]

                # C안: 필터 모드 — 하위 threshold% 제외
                if config.saju_filter_mode and s < config.saju_filter_threshold:
                    continue  # 후보 풀에서 제외

                cache_key = (sym, rb_date.strftime("%Y-%m-%d"))
                if quant_cache is not None and cache_key in quant_cache:
                    q = quant_cache[cache_key]
                else:
                    q = _quant_score_backtest(sym, asset_class, rb_date, macro_val, bench_df)
                    if quant_cache is not None:
                        quant_cache[cache_key] = q

                # C안: 필터 모드에서는 퀀트만 랭킹
                if config.saju_filter_mode:
                    final = q
                else:
                    final = config.saju_weight * s + (1 - config.saju_weight) * q
                scores.append({"symbol": sym, "saju": s, "quant": q, "final": final})
            except Exception:
                continue

        # Top N
        scores.sort(key=lambda x: x["final"], reverse=True)
        top = scores[:config.top_n]
        held = {x["symbol"] for x in top}

        # 회전율: 교체된 종목 비율
        turnover = len(prev_holdings.symmetric_difference(held)) / max(len(held), 1) / 2 if prev_holdings else 1.0

        # 기간 수익률 (균등 가중)
        rets = []
        for x in top:
            r = _forward_return(x["symbol"], asset_class, rb_date, next_date)
            rets.append(r)
        period_return = float(np.mean(rets)) if rets else 0.0
        # 거래비용 적용 (회전율 비례)
        period_return_net = period_return - turnover * cost

        equity *= (1 + period_return_net)

        result.rebalance_log.append({
            "date": rb_date.strftime("%Y-%m-%d"),
            "next_date": next_date.strftime("%Y-%m-%d"),
            "held": [x["symbol"] for x in top],
            "scores": [(x["symbol"], round(x["final"], 1)) for x in top],
            "period_return": round(period_return, 4),
            "turnover": round(turnover, 2),
            "net_return": round(period_return_net, 4),
            "equity": round(equity, 4),
        })

        prev_holdings = held

    curve[rebalance_dates[-1]] = equity
    result.equity_curve = pd.Series(curve)
    if quant_cache is not None:
        result.quant_cache = quant_cache

    # 통계
    rets = pd.Series([log["net_return"] for log in result.rebalance_log])
    if len(rets) > 0:
        annualized = (equity ** (12 / len(rets))) - 1 if len(rets) > 0 else 0
        sharpe = (rets.mean() / rets.std() * np.sqrt(12)) if rets.std() > 0 else 0
        downside = rets[rets < 0]
        sortino = (rets.mean() / downside.std() * np.sqrt(12)) if len(downside) > 0 and downside.std() > 0 else 0
        peak = result.equity_curve.cummax()
        dd = (result.equity_curve - peak) / peak
        mdd = float(dd.min())
        hit = float((rets > 0).mean())
        avg_turnover = float(pd.Series([log["turnover"] for log in result.rebalance_log]).mean())
        result.stats = {
            "cagr": round(annualized, 4),
            "sharpe": round(sharpe, 2),
            "sortino": round(sortino, 2),
            "mdd": round(mdd, 4),
            "hit_rate": round(hit, 3),
            "n_rebalances": len(rets),
            "final_equity": round(equity, 4),
            "avg_turnover": round(avg_turnover, 2),
        }
    return result

"""통합 랭커 — 30% 사주 + 70% 퀀트.

PRD §7 최종 공식:
  Raw = 0.30 × Saju_100 + 0.70 × Quant_100
  Penalty: Saju < 30 OR Quant < 30 → Raw × 0.5
  하드 필터: 대흉일진 × 종목 충 동시 → 제외 (현재는 soft 경고)

퀀트 4레이어 합산 (Phase 1: 수급·레짐 제외, 가중치 재분배):
  주식 Quant = 0.28 × Macro + 0.44 × FA + 0.28 × TA
  코인 Quant = 0.28 × Macro + 0.44 × OnChain + 0.28 × TA

레짐별 가중치 오버라이드는 백테스트 결과로 튜닝 예정.
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from ..manseryeok.core import SajuCalculator
from ..saju.scorer import saju_score
from ..ticker.saju_resolver import resolve_ticker_saju
from ..ticker.schema import TickerRecord
from .fundamental import fa_score
from .macro import macro_score_stock
from .crypto_macro import crypto_macro_score
from .onchain import onchain_score
from .price_data import get_ohlcv
from .technical import ta_score_stock, ta_score_coin


# 자산군별 퀀트 가중치 (Phase 1 = 수급·레짐 제외 재분배)
QUANT_WEIGHTS_STOCK = {"macro": 0.28, "fa": 0.44, "ta": 0.28}
QUANT_WEIGHTS_COIN = {"macro": 0.28, "onchain": 0.44, "ta": 0.28}

# 최종 가중치 (PRD 초기값 30/70)
SAJU_WEIGHT = 0.30
QUANT_WEIGHT = 0.70

# 페널티 임계치
MIN_ACCEPTABLE_SUB_SCORE = 30.0


def compute_quant_score_stock(
    symbol: str,
    target_dt: datetime,
    macro: Optional[Dict] = None,
    bench_spy_df=None,
) -> Dict:
    """주식 퀀트 스코어 (100점). Macro는 공통이라 외부에서 주입 가능."""
    from datetime import timedelta
    if macro is None:
        macro = macro_score_stock(asof=target_dt)

    # 가격 데이터
    if bench_spy_df is None:
        bench_spy_df = get_ohlcv("SPY", "stock", target_dt - timedelta(days=400), target_dt)
    df = get_ohlcv(symbol, "stock", target_dt - timedelta(days=400), target_dt)

    ta = ta_score_stock(df, bench_spy_df)
    fa = fa_score(symbol)

    w = QUANT_WEIGHTS_STOCK
    total = w["macro"] * macro["total"] + w["fa"] * fa["total"] + w["ta"] * ta["total"]

    return {
        "total": round(total, 1),
        "components": {"macro": macro, "fa": fa, "ta": ta},
        "weights": w,
    }


def compute_quant_score_coin(
    symbol: str,
    target_dt: datetime,
    macro: Optional[Dict] = None,
    bench_btc_df=None,
) -> Dict:
    """코인 퀀트 스코어 (100점)."""
    from datetime import timedelta
    if macro is None:
        macro = crypto_macro_score(asof=target_dt)

    if bench_btc_df is None:
        bench_btc_df = get_ohlcv("BTC-USD", "coin", target_dt - timedelta(days=400), target_dt)
    df = get_ohlcv(symbol, "coin", target_dt - timedelta(days=400), target_dt)

    ta = ta_score_coin(df, bench_btc_df)
    oc = onchain_score(symbol)

    w = QUANT_WEIGHTS_COIN
    total = w["macro"] * macro["total"] + w["onchain"] * oc["total"] + w["ta"] * ta["total"]

    return {
        "total": round(total, 1),
        "components": {"macro": macro, "onchain": oc, "ta": ta},
        "weights": w,
    }


def rank_single(
    calc: SajuCalculator,
    record: TickerRecord,
    target_dt: datetime,
    shared_context: Optional[Dict] = None,
) -> Dict:
    """단일 종목의 통합 스코어 산출.

    shared_context는 {"stock_macro": ..., "coin_macro": ..., "spy_df": ..., "btc_df": ...}.
    여러 종목을 한번에 평가할 때 매크로·벤치를 재사용해 호출 비용 절감.
    """
    # Saju score
    resolved = resolve_ticker_saju(calc, record)
    if not resolved.get("primary_pillar"):
        return {"symbol": record.symbol, "error": "no primary saju", "skip": True}
    primary_source = resolved["primary_source"]
    if primary_source == "founding":
        primary_saju = resolved["components"]["founding"]["saju"]
    elif primary_source == "listing":
        primary_saju = resolved["components"]["listing"]["saju"]
    else:
        primary_saju = resolved["components"]["transition"][0]["saju"]

    saju_result = saju_score(
        calc=calc,
        ticker_primary_pillar=resolved["primary_pillar"],
        ticker_saju=primary_saju,
        target_dt=target_dt,
    )

    # Quant score
    ctx = shared_context or {}
    if record.asset_class == "stock":
        quant = compute_quant_score_stock(
            record.symbol, target_dt,
            macro=ctx.get("stock_macro"), bench_spy_df=ctx.get("spy_df"),
        )
    elif record.asset_class == "coin":
        quant = compute_quant_score_coin(
            record.symbol, target_dt,
            macro=ctx.get("coin_macro"), bench_btc_df=ctx.get("btc_df"),
        )
    else:
        return {"symbol": record.symbol, "error": f"unknown asset_class {record.asset_class}"}

    saju_100 = saju_result["total_100"]
    quant_100 = quant["total"]

    # Raw 결합
    raw = SAJU_WEIGHT * saju_100 + QUANT_WEIGHT * quant_100

    # 페널티 룰
    penalty_applied = False
    if saju_100 < MIN_ACCEPTABLE_SUB_SCORE or quant_100 < MIN_ACCEPTABLE_SUB_SCORE:
        final = raw * 0.5
        penalty_applied = True
    else:
        final = raw

    return {
        "symbol": record.symbol,
        "name": record.name,
        "asset_class": record.asset_class,
        "sector": record.sector,
        "primary_pillar": resolved["primary_pillar"],
        "primary_source": primary_source,
        "saju_100": saju_100,
        "quant_100": quant_100,
        "raw": round(raw, 1),
        "final": round(final, 1),
        "penalty_applied": penalty_applied,
        "saju_detail": saju_result,
        "quant_detail": quant,
    }


def rank_universe(
    calc: SajuCalculator,
    records: Dict[str, TickerRecord],
    target_dt: datetime,
    asset_class: Optional[str] = None,
    top_n: int = 10,
    diversity_constraints: bool = True,
) -> List[Dict]:
    """유니버스 전체 랭킹.

    asset_class: "stock" | "coin" | None(혼합)
    top_n: 반환할 상위 N
    diversity_constraints: 다양성 제약 (같은 섹터/오행 상한)
    """
    from datetime import timedelta

    # 공통 컨텍스트 준비 (Macro·벤치를 한 번만 계산)
    ctx: Dict = {}
    has_stock = any(r.asset_class == "stock" for r in records.values())
    has_coin = any(r.asset_class == "coin" for r in records.values())
    if has_stock:
        ctx["stock_macro"] = macro_score_stock(asof=target_dt)
        ctx["spy_df"] = get_ohlcv("SPY", "stock",
                                   target_dt - timedelta(days=400), target_dt)
    if has_coin:
        ctx["coin_macro"] = crypto_macro_score(asof=target_dt)
        ctx["btc_df"] = get_ohlcv("BTC-USD", "coin",
                                   target_dt - timedelta(days=400), target_dt)

    results: List[Dict] = []
    for sym, rec in records.items():
        if asset_class and rec.asset_class != asset_class:
            continue
        try:
            r = rank_single(calc, rec, target_dt, shared_context=ctx)
            if r.get("skip") or r.get("error"):
                continue
            results.append(r)
        except Exception as e:
            results.append({"symbol": sym, "error": str(e)})

    valid = [r for r in results if "error" not in r]
    valid.sort(key=lambda x: x["final"], reverse=True)

    if not diversity_constraints:
        return valid[:top_n]

    # 다양성: 같은 섹터 최대 2 (주식), 동일 카테고리 최대 3 (코인)
    picked: List[Dict] = []
    sector_count: Dict[str, int] = {}
    for r in valid:
        sec = r.get("sector", "") or "unknown"
        limit = 3 if r["asset_class"] == "coin" else 2
        if sector_count.get(sec, 0) >= limit:
            continue
        picked.append(r)
        sector_count[sec] = sector_count.get(sec, 0) + 1
        if len(picked) >= top_n:
            break
    return picked

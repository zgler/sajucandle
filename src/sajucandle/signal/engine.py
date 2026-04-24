"""Signal Engine — 월간 리밸런싱 신호 생성 (Phase 4).

확정 전략: C 필터 전용
  1. 사주 점수 < 30 → KILL (후보 제외)
  2. 통과 종목을 퀀트(TA + Macro)로 랭킹
  3. Top N → BUY / HOLD
  4. 보유 중이지만 Top N 탈락 → SELL
  5. Top N+1 ~ Top N*2 → WATCH

신호 타입:
  BUY   신규 편입 (Top N 진입, 미보유)
  HOLD  유지 (Top N 유지, 보유 중)
  SELL  청산 (Top N 탈락, 보유 중)
  WATCH 관찰 (Top N 근접, 미편입)
  KILL  사주 필터 탈락 (점수 < threshold)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Set

from ..manseryeok.core import SajuCalculator
from ..ticker.schema import TickerRecord
from ..ticker.saju_resolver import resolve_ticker_saju
from ..saju.scorer import saju_score
from ..quant.price_data import get_ohlcv
from ..quant.technical import ta_score_stock, ta_score_coin
from ..quant.macro import macro_score_stock
from ..quant.crypto_macro import crypto_macro_score
from .regime import detect_regime, Regime


class SignalType(str, Enum):
    BUY = "BUY"
    HOLD = "HOLD"
    SELL = "SELL"
    WATCH = "WATCH"
    KILL = "KILL"


@dataclass
class TickerSignal:
    symbol: str
    signal: SignalType
    saju_score: float
    quant_score: float
    rank: Optional[int]       # 퀀트 순위 (KILL은 None)
    reason: str
    breakdown: Dict = field(default_factory=dict)


@dataclass
class SignalReport:
    target_dt: datetime
    asset_class: str
    signals: List[TickerSignal]
    top_n: int
    saju_filter_threshold: float
    universe_size: int
    survivors: int            # 사주 필터 통과 수
    prev_holdings: Set[str]
    new_holdings: Set[str]
    regime: Optional[str] = None          # "bull" / "bear" / "sideways" / None
    regime_bench_return: Optional[float] = None
    saju_active: bool = True              # False면 이번 달 사주 필터 비활성

    def by_signal(self, signal: SignalType) -> List[TickerSignal]:
        return [s for s in self.signals if s.signal == signal]

    def summary(self) -> str:
        regime_str = ""
        if self.regime:
            active_str = "사주ON" if self.saju_active else "사주OFF(순수퀀트)"
            regime_str = f"  레짐={self.regime.upper()} ({active_str})"
        lines = [
            f"[{self.target_dt.strftime('%Y-%m-%d')} {self.asset_class.upper()} 신호]{regime_str}",
            f"유니버스 {self.universe_size}종 → 사주 통과 {self.survivors}종",
            "",
        ]
        for sig_type in [SignalType.BUY, SignalType.HOLD, SignalType.SELL,
                         SignalType.WATCH, SignalType.KILL]:
            items = self.by_signal(sig_type)
            if not items:
                continue
            lines.append(f"  [{sig_type.value}]")
            for t in items:
                rank_str = f"#{t.rank}" if t.rank else "—"
                lines.append(
                    f"    {t.symbol:<8} {rank_str:<4} "
                    f"사주={t.saju_score:.1f}  퀀트={t.quant_score:.1f}  {t.reason}"
                )
        return "\n".join(lines)


def _ta_score(symbol: str, asset_class: str, asof: datetime,
              bench_df) -> float:
    df = get_ohlcv(symbol, asset_class, asof - timedelta(days=400), asof)
    if df.empty or len(df) < 30:
        return 50.0
    if asset_class == "stock":
        return ta_score_stock(df, bench_df)["total"]
    return ta_score_coin(df, bench_df)["total"]


def generate_signals(
    calc: SajuCalculator,
    records: Dict[str, TickerRecord],
    asset_class: str,
    target_dt: datetime,
    current_holdings: Optional[Set[str]] = None,
    top_n: int = 5,
    watch_buffer: int = 5,
    saju_filter_threshold: float = 30.0,
    fast_macro: bool = False,
    regime_conditional: bool = False,   # True면 횡보장에서만 사주 필터 ON
    regime_lookback_months: int = 3,
) -> SignalReport:
    """현재 시점 신호 생성.

    Parameters
    ----------
    regime_conditional : True면 Sideways 레짐에서만 사주 필터 적용.
                         Bull/Bear에서는 순수 퀀트 랭킹.
    """
    if current_holdings is None:
        current_holdings = set()

    # ── 레짐 감지 ────────────────────────────────────────────────────────
    current_regime: Optional[str] = None
    regime_return: Optional[float] = None
    saju_active = True  # 기본: 사주 필터 항상 ON

    if regime_conditional:
        regime_enum, regime_return = detect_regime(
            asset_class, target_dt, lookback_months=regime_lookback_months,
        )
        current_regime = regime_enum.value
        # 횡보장(Sideways)에서만 사주 필터 ON
        saju_active = (regime_enum == Regime.SIDEWAYS)

    bench_symbol = "SPY" if asset_class == "stock" else "BTC-USD"
    bench_df = get_ohlcv(
        bench_symbol, asset_class,
        target_dt - timedelta(days=400),
        target_dt + timedelta(days=1),
    )

    if fast_macro:
        macro_val = 50.0
    else:
        try:
            if asset_class == "stock":
                macro_val = macro_score_stock(asof=target_dt)["total"]
            else:
                macro_val = crypto_macro_score(asof=target_dt)["total"]
        except Exception:
            macro_val = 50.0

    # ── 1. 각 종목 사주 + 퀀트 점수 ────────────────────────────────────
    scored: List[Dict] = []
    killed: List[Dict] = []

    for sym, rec in records.items():
        if rec.asset_class != asset_class:
            continue
        try:
            resolved = resolve_ticker_saju(calc, rec)
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
                target_dt=target_dt,
            )
            s = sc["total_100"]
        except Exception:
            continue

        # 레짐 조건부: saju_active=False(Bull/Bear)면 필터 스킵
        if saju_active and s < saju_filter_threshold:
            killed.append({"symbol": sym, "saju_score": s})
            continue

        try:
            ta = _ta_score(sym, asset_class, target_dt, bench_df)
        except Exception:
            ta = 50.0

        q = 0.33 * macro_val + 0.67 * ta
        scored.append({
            "symbol": sym,
            "saju_score": s,
            "quant_score": q,
            "ta": ta,
            "macro": macro_val,
        })

    # ── 2. 퀀트 랭킹 ────────────────────────────────────────────────────
    scored.sort(key=lambda x: x["quant_score"], reverse=True)
    for i, item in enumerate(scored):
        item["rank"] = i + 1

    top_set = {item["symbol"] for item in scored[:top_n]}
    watch_set = {item["symbol"] for item in scored[top_n:top_n + watch_buffer]}

    # ── 3. 신호 분류 ────────────────────────────────────────────────────
    signals: List[TickerSignal] = []

    for item in scored:
        sym = item["symbol"]
        rank = item["rank"]
        in_top = sym in top_set
        in_watch = sym in watch_set
        held = sym in current_holdings

        if in_top and held:
            sig = SignalType.HOLD
            reason = f"Top{top_n} 유지"
        elif in_top and not held:
            sig = SignalType.BUY
            reason = f"Top{top_n} 신규 진입"
        elif in_watch and held:
            sig = SignalType.SELL
            reason = f"Top{top_n} 탈락 (현재 #{rank}), 청산 권장"
        elif in_watch:
            sig = SignalType.WATCH
            reason = f"Top{top_n} 근접 대기 (#{rank})"
        elif held:
            sig = SignalType.SELL
            reason = f"순위 #{rank}로 하락, 청산"
        else:
            continue  # 관심 없음 (상위 N+buffer 밖)

        signals.append(TickerSignal(
            symbol=sym,
            signal=sig,
            saju_score=round(item["saju_score"], 1),
            quant_score=round(item["quant_score"], 1),
            rank=rank,
            reason=reason,
            breakdown={"ta": round(item["ta"], 1), "macro": round(item["macro"], 1)},
        ))

    for item in killed:
        sym = item["symbol"]
        held = sym in current_holdings
        signals.append(TickerSignal(
            symbol=sym,
            signal=SignalType.KILL,
            saju_score=round(item["saju_score"], 1),
            quant_score=0.0,
            rank=None,
            reason=f"사주 점수 {item['saju_score']:.1f} < {saju_filter_threshold} (필터 탈락)",
        ))

    return SignalReport(
        target_dt=target_dt,
        asset_class=asset_class,
        signals=signals,
        top_n=top_n,
        saju_filter_threshold=saju_filter_threshold,
        universe_size=len([r for r in records.values() if r.asset_class == asset_class]),
        survivors=len(scored),
        prev_holdings=current_holdings,
        new_holdings=top_set,
        regime=current_regime,
        regime_bench_return=regime_return,
        saju_active=saju_active,
    )

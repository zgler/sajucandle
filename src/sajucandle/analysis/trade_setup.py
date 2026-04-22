"""하이브리드 ATR + S/R snap SL·TP 산출.

Phase 2: direction("LONG"|"SHORT") 매개변수. 숏은 공식 대칭 역전.
상수(_SL_ATR_MULT 등)는 방향 공유 — Phase 4 백테스트에서 분리 여부 재검토.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

from sajucandle.analysis.support_resistance import LevelKind, SRLevel


SignalDirection = Literal["LONG", "SHORT", "NEUTRAL"]

_SL_ATR_MULT = 1.5
_TP1_ATR_MULT = 1.5
_TP2_ATR_MULT = 3.0
_SNAP_TOLERANCE = 0.3
_SNAP_TOLERANCE_TP2 = 0.5
_SR_BUFFER_ATR = 0.2


@dataclass
class TradeSetup:
    entry: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: float
    risk_pct: float
    rr_tp1: float
    rr_tp2: float
    sl_basis: Literal["atr", "sr_snap"]
    tp1_basis: Literal["atr", "sr_snap"]
    tp2_basis: Literal["atr", "sr_snap"]
    direction: SignalDirection = "LONG"


_STRENGTH_ORDER = {"low": 0, "medium": 1, "high": 2}


def _best_level_in_range(
    candidates: list[SRLevel],
    price_min: float,
    price_max: float,
) -> Optional[SRLevel]:
    hits = [c for c in candidates if price_min <= c.price <= price_max]
    if not hits:
        return None
    hits.sort(key=lambda c: _STRENGTH_ORDER[c.strength], reverse=True)
    return hits[0]


def _compute_long(
    entry: float, atr_1d: float, sr_levels: list[SRLevel]
) -> TradeSetup:
    supports = [x for x in sr_levels if x.kind == LevelKind.SUPPORT]
    resists = [x for x in sr_levels if x.kind == LevelKind.RESISTANCE]

    # SL = entry - mult*atr, support snap, lvl - buffer
    sl_base = entry - _SL_ATR_MULT * atr_1d
    sl_min = entry - (_SL_ATR_MULT + _SNAP_TOLERANCE) * atr_1d
    sl_max = entry - (_SL_ATR_MULT - _SNAP_TOLERANCE) * atr_1d
    sl_best = _best_level_in_range(supports, sl_min, sl_max)
    if sl_best is not None:
        stop_loss = sl_best.price - _SR_BUFFER_ATR * atr_1d
        sl_basis: Literal["atr", "sr_snap"] = "sr_snap"
    else:
        stop_loss = sl_base
        sl_basis = "atr"

    # TP1 = entry + mult*atr, resistance snap, lvl - buffer
    tp1_base = entry + _TP1_ATR_MULT * atr_1d
    tp1_min = entry + (_TP1_ATR_MULT - _SNAP_TOLERANCE) * atr_1d
    tp1_max = entry + (_TP1_ATR_MULT + _SNAP_TOLERANCE) * atr_1d
    tp1_best = _best_level_in_range(resists, tp1_min, tp1_max)
    if tp1_best is not None:
        take_profit_1 = tp1_best.price - _SR_BUFFER_ATR * atr_1d
        tp1_basis: Literal["atr", "sr_snap"] = "sr_snap"
    else:
        take_profit_1 = tp1_base
        tp1_basis = "atr"

    # TP2 (여유 tolerance)
    tp2_base = entry + _TP2_ATR_MULT * atr_1d
    tp2_min = entry + (_TP2_ATR_MULT - _SNAP_TOLERANCE_TP2) * atr_1d
    tp2_max = entry + (_TP2_ATR_MULT + _SNAP_TOLERANCE_TP2) * atr_1d
    tp2_best = _best_level_in_range(resists, tp2_min, tp2_max)
    if tp2_best is not None:
        take_profit_2 = tp2_best.price - _SR_BUFFER_ATR * atr_1d
        tp2_basis: Literal["atr", "sr_snap"] = "sr_snap"
    else:
        take_profit_2 = tp2_base
        tp2_basis = "atr"

    risk = entry - stop_loss
    risk_pct = (risk / entry * 100) if entry > 0 else 0.0
    rr_tp1 = ((take_profit_1 - entry) / risk) if risk > 0 else 0.0
    rr_tp2 = ((take_profit_2 - entry) / risk) if risk > 0 else 0.0

    return TradeSetup(
        entry=entry,
        stop_loss=stop_loss,
        take_profit_1=take_profit_1,
        take_profit_2=take_profit_2,
        risk_pct=risk_pct,
        rr_tp1=rr_tp1,
        rr_tp2=rr_tp2,
        sl_basis=sl_basis,
        tp1_basis=tp1_basis,
        tp2_basis=tp2_basis,
        direction="LONG",
    )


def _compute_short(
    entry: float, atr_1d: float, sr_levels: list[SRLevel]
) -> TradeSetup:
    """Short 버전: 공식 대칭 역전.

    - SL > entry (resistance snap, lvl + buffer*atr)
    - TP1/TP2 < entry (support snap, lvl + buffer*atr)
    - risk = SL - entry (양수)
    - rr = (entry - tp*) / risk
    """
    supports = [x for x in sr_levels if x.kind == LevelKind.SUPPORT]
    resists = [x for x in sr_levels if x.kind == LevelKind.RESISTANCE]

    # SL = entry + mult*atr, resistance snap, lvl + buffer
    sl_base = entry + _SL_ATR_MULT * atr_1d
    sl_min = entry + (_SL_ATR_MULT - _SNAP_TOLERANCE) * atr_1d
    sl_max = entry + (_SL_ATR_MULT + _SNAP_TOLERANCE) * atr_1d
    sl_best = _best_level_in_range(resists, sl_min, sl_max)
    if sl_best is not None:
        stop_loss = sl_best.price + _SR_BUFFER_ATR * atr_1d
        sl_basis: Literal["atr", "sr_snap"] = "sr_snap"
    else:
        stop_loss = sl_base
        sl_basis = "atr"

    # TP1 = entry - mult*atr, support snap, lvl + buffer
    tp1_base = entry - _TP1_ATR_MULT * atr_1d
    tp1_min = entry - (_TP1_ATR_MULT + _SNAP_TOLERANCE) * atr_1d
    tp1_max = entry - (_TP1_ATR_MULT - _SNAP_TOLERANCE) * atr_1d
    tp1_best = _best_level_in_range(supports, tp1_min, tp1_max)
    if tp1_best is not None:
        take_profit_1 = tp1_best.price + _SR_BUFFER_ATR * atr_1d
        tp1_basis: Literal["atr", "sr_snap"] = "sr_snap"
    else:
        take_profit_1 = tp1_base
        tp1_basis = "atr"

    # TP2
    tp2_base = entry - _TP2_ATR_MULT * atr_1d
    tp2_min = entry - (_TP2_ATR_MULT + _SNAP_TOLERANCE_TP2) * atr_1d
    tp2_max = entry - (_TP2_ATR_MULT - _SNAP_TOLERANCE_TP2) * atr_1d
    tp2_best = _best_level_in_range(supports, tp2_min, tp2_max)
    if tp2_best is not None:
        take_profit_2 = tp2_best.price + _SR_BUFFER_ATR * atr_1d
        tp2_basis: Literal["atr", "sr_snap"] = "sr_snap"
    else:
        take_profit_2 = tp2_base
        tp2_basis = "atr"

    risk = stop_loss - entry
    risk_pct = (risk / entry * 100) if entry > 0 else 0.0
    rr_tp1 = ((entry - take_profit_1) / risk) if risk > 0 else 0.0
    rr_tp2 = ((entry - take_profit_2) / risk) if risk > 0 else 0.0

    return TradeSetup(
        entry=entry,
        stop_loss=stop_loss,
        take_profit_1=take_profit_1,
        take_profit_2=take_profit_2,
        risk_pct=risk_pct,
        rr_tp1=rr_tp1,
        rr_tp2=rr_tp2,
        sl_basis=sl_basis,
        tp1_basis=tp1_basis,
        tp2_basis=tp2_basis,
        direction="SHORT",
    )


def compute_trade_setup(
    entry: float,
    atr_1d: float,
    sr_levels: list[SRLevel],
    direction: SignalDirection = "LONG",
) -> TradeSetup:
    if atr_1d <= 0:
        atr_1d = entry * 0.01

    if direction == "SHORT":
        return _compute_short(entry, atr_1d, sr_levels)
    return _compute_long(entry, atr_1d, sr_levels)

"""analysis.trade_setup: 하이브리드 ATR + S/R snap → SL/TP/R:R/risk_pct."""
from __future__ import annotations

import pytest

from sajucandle.analysis.support_resistance import LevelKind, SRLevel
from sajucandle.analysis.trade_setup import TradeSetup, compute_trade_setup


def _support(price: float, strength: str = "medium") -> SRLevel:
    return SRLevel(price=price, kind=LevelKind.SUPPORT,
                   strength=strength, sources=["swing_low"])  # type: ignore[arg-type]


def _resist(price: float, strength: str = "medium") -> SRLevel:
    return SRLevel(price=price, kind=LevelKind.RESISTANCE,
                   strength=strength, sources=["swing_high"])  # type: ignore[arg-type]


def test_no_sr_uses_pure_atr():
    setup = compute_trade_setup(entry=100.0, atr_1d=2.0, sr_levels=[])
    assert setup.stop_loss == pytest.approx(100.0 - 1.5 * 2.0)
    assert setup.take_profit_1 == pytest.approx(100.0 + 1.5 * 2.0)
    assert setup.take_profit_2 == pytest.approx(100.0 + 3.0 * 2.0)
    assert setup.sl_basis == "atr"
    assert setup.tp1_basis == "atr"
    assert setup.tp2_basis == "atr"


def test_sl_snaps_to_nearby_support():
    supports = [_support(97.2)]
    setup = compute_trade_setup(entry=100.0, atr_1d=2.0, sr_levels=supports)
    assert setup.sl_basis == "sr_snap"
    assert setup.stop_loss == pytest.approx(97.2 - 0.2 * 2.0)


def test_tp1_snaps_to_nearby_resistance():
    resists = [_resist(103.5)]
    setup = compute_trade_setup(entry=100.0, atr_1d=2.0, sr_levels=resists)
    assert setup.tp1_basis == "sr_snap"
    assert setup.take_profit_1 == pytest.approx(103.5 - 0.2 * 2.0)


def test_tp2_wider_tolerance_5050():
    resists = [_resist(107.0)]
    setup = compute_trade_setup(entry=100.0, atr_1d=2.0, sr_levels=resists)
    assert setup.take_profit_2 == pytest.approx(107.0 - 0.2 * 2.0)
    assert setup.tp2_basis == "sr_snap"


def test_risk_pct_computation():
    setup = compute_trade_setup(entry=100.0, atr_1d=2.0, sr_levels=[])
    assert setup.risk_pct == pytest.approx(3.0)


def test_rr_computation():
    setup = compute_trade_setup(entry=100.0, atr_1d=2.0, sr_levels=[])
    assert setup.rr_tp1 == pytest.approx(1.0)
    assert setup.rr_tp2 == pytest.approx(2.0)


def test_strongest_support_wins_when_multiple_in_range():
    supports = [_support(97.2, "low"), _support(97.4, "high")]
    setup = compute_trade_setup(entry=100.0, atr_1d=2.0, sr_levels=supports)
    assert setup.sl_basis == "sr_snap"
    assert setup.stop_loss == pytest.approx(97.4 - 0.2 * 2.0)


def test_trade_setup_is_dataclass():
    from dataclasses import is_dataclass
    assert is_dataclass(TradeSetup)


# ─────────────────────────────────────────────
# Phase 2: direction="SHORT" 대칭
# ─────────────────────────────────────────────


def test_long_default_unchanged():
    """direction 미지정 시 LONG 기본값 유지 (하위호환)."""
    setup = compute_trade_setup(entry=100.0, atr_1d=2.0, sr_levels=[])
    assert setup.direction == "LONG"
    assert setup.stop_loss < setup.entry
    assert setup.entry < setup.take_profit_1 < setup.take_profit_2


def test_short_no_sr_uses_pure_atr():
    setup = compute_trade_setup(
        entry=100.0, atr_1d=2.0, sr_levels=[], direction="SHORT"
    )
    assert setup.direction == "SHORT"
    # SL > entry > TP1 > TP2
    assert setup.stop_loss == pytest.approx(100.0 + 1.5 * 2.0)
    assert setup.take_profit_1 == pytest.approx(100.0 - 1.5 * 2.0)
    assert setup.take_profit_2 == pytest.approx(100.0 - 3.0 * 2.0)
    assert setup.sl_basis == "atr"
    assert setup.tp1_basis == "atr"
    assert setup.tp2_basis == "atr"


def test_short_sl_snaps_to_nearby_resistance():
    resists = [_resist(102.8)]
    setup = compute_trade_setup(
        entry=100.0, atr_1d=2.0, sr_levels=resists, direction="SHORT"
    )
    assert setup.sl_basis == "sr_snap"
    # SL = resistance + buffer*atr (위로 offset)
    assert setup.stop_loss == pytest.approx(102.8 + 0.2 * 2.0)


def test_short_tp1_snaps_to_nearby_support():
    supports = [_support(96.5)]
    setup = compute_trade_setup(
        entry=100.0, atr_1d=2.0, sr_levels=supports, direction="SHORT"
    )
    assert setup.tp1_basis == "sr_snap"
    # TP1 = support + buffer*atr (위로 offset, 즉 support 위에서 익절)
    assert setup.take_profit_1 == pytest.approx(96.5 + 0.2 * 2.0)


def test_short_tp2_wider_tolerance():
    supports = [_support(93.0)]
    setup = compute_trade_setup(
        entry=100.0, atr_1d=2.0, sr_levels=supports, direction="SHORT"
    )
    assert setup.tp2_basis == "sr_snap"
    assert setup.take_profit_2 == pytest.approx(93.0 + 0.2 * 2.0)


def test_short_risk_pct_positive():
    setup = compute_trade_setup(
        entry=100.0, atr_1d=2.0, sr_levels=[], direction="SHORT"
    )
    # risk = SL - entry = 3.0 → risk_pct = 3.0
    assert setup.risk_pct == pytest.approx(3.0)


def test_short_rr_positive():
    setup = compute_trade_setup(
        entry=100.0, atr_1d=2.0, sr_levels=[], direction="SHORT"
    )
    # rr_tp1 = (entry - tp1) / risk = 3.0 / 3.0 = 1.0
    assert setup.rr_tp1 == pytest.approx(1.0)
    assert setup.rr_tp2 == pytest.approx(2.0)


def test_short_strongest_resistance_wins():
    resists = [_resist(102.8, "low"), _resist(102.9, "high")]
    setup = compute_trade_setup(
        entry=100.0, atr_1d=2.0, sr_levels=resists, direction="SHORT"
    )
    assert setup.sl_basis == "sr_snap"
    assert setup.stop_loss == pytest.approx(102.9 + 0.2 * 2.0)


def test_long_short_symmetric_rr_no_snap():
    """S/R 없을 때 L/S rr 절대값 대칭."""
    long_s = compute_trade_setup(entry=100.0, atr_1d=2.0, sr_levels=[])
    short_s = compute_trade_setup(
        entry=100.0, atr_1d=2.0, sr_levels=[], direction="SHORT"
    )
    assert long_s.rr_tp1 == pytest.approx(short_s.rr_tp1)
    assert long_s.rr_tp2 == pytest.approx(short_s.rr_tp2)
    assert long_s.risk_pct == pytest.approx(short_s.risk_pct)

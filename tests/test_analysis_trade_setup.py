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

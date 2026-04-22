"""Phase 2: SignalDirection + direction/long_score/short_score 필드 round-trip."""
from __future__ import annotations

import json

from sajucandle.models import (
    AlignmentSummary,
    AnalysisSummary,
    StructureSummary,
    TradeSetupSummary,
)


def _base_analysis_kwargs():
    return {
        "structure": StructureSummary(state="uptrend", score=70),
        "alignment": AlignmentSummary(
            tf_1h="up", tf_4h="up", tf_1d="up",
            aligned=True, bias="bullish", score=95,
        ),
        "rsi_1h": 55.0,
        "volume_ratio_1d": 1.2,
        "composite_score": 80,
        "reason": "test",
    }


def test_analysis_summary_direction_default_none():
    a = AnalysisSummary(**_base_analysis_kwargs())
    assert a.direction is None
    assert a.long_score is None
    assert a.short_score is None


def test_analysis_summary_direction_long():
    a = AnalysisSummary(
        **_base_analysis_kwargs(),
        direction="LONG",
        long_score=80,
        short_score=20,
    )
    assert a.direction == "LONG"
    assert a.long_score == 80
    assert a.short_score == 20


def test_analysis_summary_direction_short():
    a = AnalysisSummary(
        **_base_analysis_kwargs(),
        direction="SHORT",
        long_score=25,
        short_score=85,
    )
    assert a.direction == "SHORT"


def test_analysis_summary_json_roundtrip_with_direction():
    original = AnalysisSummary(
        **_base_analysis_kwargs(),
        direction="SHORT",
        long_score=30,
        short_score=75,
    )
    js = original.model_dump_json()
    loaded = AnalysisSummary(**json.loads(js))
    assert loaded.direction == "SHORT"
    assert loaded.long_score == 30
    assert loaded.short_score == 75


def test_analysis_summary_legacy_json_accepts_missing_direction():
    """구버전 클라이언트가 보낸 JSON은 direction 없어도 파싱."""
    legacy = {
        "structure": {"state": "uptrend", "score": 70},
        "alignment": {"tf_1h": "up", "tf_4h": "up", "tf_1d": "up",
                       "aligned": True, "bias": "bullish", "score": 95},
        "rsi_1h": 55.0,
        "volume_ratio_1d": 1.2,
        "composite_score": 80,
        "reason": "legacy",
    }
    a = AnalysisSummary(**legacy)
    assert a.direction is None


def test_trade_setup_summary_direction_default_none():
    ts = TradeSetupSummary(
        entry=100.0, stop_loss=97.0,
        take_profit_1=103.0, take_profit_2=106.0,
        risk_pct=3.0, rr_tp1=1.0, rr_tp2=2.0,
        sl_basis="atr", tp1_basis="atr", tp2_basis="atr",
    )
    assert ts.direction is None


def test_trade_setup_summary_direction_short():
    ts = TradeSetupSummary(
        entry=100.0, stop_loss=103.0,
        take_profit_1=97.0, take_profit_2=94.0,
        risk_pct=3.0, rr_tp1=1.0, rr_tp2=2.0,
        sl_basis="atr", tp1_basis="atr", tp2_basis="atr",
        direction="SHORT",
    )
    assert ts.direction == "SHORT"

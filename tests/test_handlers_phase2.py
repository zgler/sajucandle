"""Phase 2: 5등급 라벨 + 숏 세팅 블록 + /guide."""
from __future__ import annotations

from sajucandle.handlers import (
    _GRADE_LABEL,
    _GUIDE_TEXT,
    _append_trade_setup_block,
    _format_signal_card,
    _format_stats_card,
)


def _base_signal_data(grade: str, direction: str | None, ts=None):
    return {
        "date": "2026-04-22",
        "ticker": "BTCUSDT",
        "price": {"current": 70000.0, "change_pct_24h": -2.5},
        "saju": {"composite": 50, "grade": "보통"},
        "chart": {
            "score": 70, "rsi": 70, "ma20": 70000, "ma50": 71000,
            "ma_trend": "down", "volume_ratio": 1.3, "reason": "...",
        },
        "composite_score": 72,
        "signal_grade": grade,
        "best_hours": [],
        "market_status": {"is_open": True, "last_session_date": "2026-04-22",
                          "category": "crypto"},
        "analysis": {
            "structure": {"state": "downtrend", "score": 20},
            "alignment": {
                "tf_1h": "down", "tf_4h": "down", "tf_1d": "down",
                "aligned": True, "bias": "bearish", "score": 90,
            },
            "rsi_1h": 70.0, "volume_ratio_1d": 1.3,
            "composite_score": 72, "reason": "하락 강정렬",
            "sr_levels": [], "trade_setup": ts,
            "direction": direction,
        },
    }


def test_grade_label_phase2_entries():
    assert _GRADE_LABEL["강진입_L"].endswith("(롱)")
    assert _GRADE_LABEL["진입_L"].endswith("(롱)")
    assert _GRADE_LABEL["진입_S"].endswith("(숏)")
    assert _GRADE_LABEL["강진입_S"].endswith("(숏)")
    assert _GRADE_LABEL["관망"] == "🟡 관망"


def test_grade_label_legacy_compat():
    """레거시 grade는 롱 라벨로 자동 매핑."""
    assert _GRADE_LABEL["강진입"].endswith("(롱)")
    assert _GRADE_LABEL["진입"].endswith("(롱)")
    assert _GRADE_LABEL["회피"] == "🟡 관망"


def test_format_card_grade_label_short_entry():
    data = _base_signal_data(grade="진입_S", direction="SHORT")
    card = _format_signal_card(data)
    assert "진입 (숏)" in card
    assert "🔴" in card


def test_format_card_grade_label_strong_short():
    data = _base_signal_data(grade="강진입_S", direction="SHORT")
    card = _format_signal_card(data)
    assert "강진입 (숏)" in card
    assert "🧊" in card


def test_format_card_short_setup_block():
    """숏 TradeSetup이 있으면 '세팅 (숏)' 라벨 + SL>entry>TP."""
    ts = {
        "entry": 70000.0,
        "stop_loss": 72000.0,
        "take_profit_1": 68000.0,
        "take_profit_2": 66000.0,
        "risk_pct": 2.86,
        "rr_tp1": 1.0,
        "rr_tp2": 2.0,
        "sl_basis": "atr",
        "tp1_basis": "atr",
        "tp2_basis": "atr",
        "direction": "SHORT",
    }
    data = _base_signal_data(grade="진입_S", direction="SHORT", ts=ts)
    card = _format_signal_card(data)
    assert "세팅 (숏)" in card
    # 손절은 entry 위 → pct 양수
    assert "+2.9%" in card or "+2.86%" in card or "+3" in card
    # TP1은 entry 아래 → pct 음수
    assert "-2.9%" in card or "-2.86%" in card or "-3" in card


def test_format_card_long_setup_block_still_works():
    """롱은 기존 의미 유지 + 라벨 '세팅 (롱)'."""
    ts = {
        "entry": 70000.0,
        "stop_loss": 68000.0,
        "take_profit_1": 72000.0,
        "take_profit_2": 74000.0,
        "risk_pct": 2.86,
        "rr_tp1": 1.0,
        "rr_tp2": 2.0,
        "sl_basis": "atr",
        "tp1_basis": "atr",
        "tp2_basis": "atr",
        "direction": "LONG",
    }
    data = _base_signal_data(grade="진입_L", direction="LONG", ts=ts)
    data["analysis"]["structure"]["state"] = "uptrend"
    data["analysis"]["alignment"]["bias"] = "bullish"
    card = _format_signal_card(data)
    assert "세팅 (롱)" in card


def test_format_card_legacy_setup_without_direction_key():
    """레거시 TradeSetup (direction 키 없음) → '세팅 (롱)' fallback."""
    ts = {
        "entry": 70000.0,
        "stop_loss": 68000.0,
        "take_profit_1": 72000.0,
        "take_profit_2": 74000.0,
        "risk_pct": 2.86,
        "rr_tp1": 1.0,
        "rr_tp2": 2.0,
        "sl_basis": "atr",
        "tp1_basis": "atr",
        "tp2_basis": "atr",
        # direction 키 없음
    }
    lines: list[str] = []
    _append_trade_setup_block(lines, ts)
    text = "\n".join(lines)
    assert "세팅 (롱)" in text


def test_guide_text_mentions_short_and_five_grades():
    assert "강진입 (롱)" in _GUIDE_TEXT
    assert "진입 (롱)" in _GUIDE_TEXT
    assert "진입 (숏)" in _GUIDE_TEXT
    assert "강진입 (숏)" in _GUIDE_TEXT
    assert "관망" in _GUIDE_TEXT
    assert "숏 실행" in _GUIDE_TEXT


def test_guide_text_no_legacy_avoid_grade():
    """Phase 2: '회피' 등급 설명 제거 (롱 가이드에서)."""
    # '회피' 단어는 제거됨
    assert "회피" not in _GUIDE_TEXT


def test_stats_card_shows_phase2_grades():
    stats = {
        "total": 5,
        "by_grade": {
            "강진입_L": 1, "진입_L": 2, "관망": 1, "진입_S": 1,
        },
        "by_direction": {"LONG": 3, "SHORT": 1, "NEUTRAL": 1},
        "tracking": {"completed": 0, "pending": 5},
        "mfe_mae": {"sample_size": 0},
        "filters": {},
    }
    card = _format_stats_card(stats)
    assert "강진입 (롱)" in card
    assert "진입 (롱)" in card
    assert "진입 (숏)" in card
    assert "방향별" in card
    assert "LONG 3" in card
    assert "SHORT 1" in card

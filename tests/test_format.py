from sajucandle.format import DISCLAIMER, render_bazi_card
from sajucandle.saju_engine import SajuEngine


# ─────────────────────────────────────────────
# Week 8: DISCLAIMER 상수
# ─────────────────────────────────────────────

def test_disclaimer_is_info_purpose_not_entertainment():
    assert "정보 제공" in DISCLAIMER
    assert "엔터테인먼트" not in DISCLAIMER
    assert "본인" in DISCLAIMER


def test_disclaimer_is_single_line():
    assert "\n" not in DISCLAIMER


def test_render_bazi_card_uses_new_disclaimer():
    """Week 8: render_bazi_card도 새 DISCLAIMER 사용."""
    engine = SajuEngine()
    chart = engine.calc_bazi(1990, 3, 15, 14)
    card = render_bazi_card(chart, birth_str="1990-03-15 14:00")
    assert DISCLAIMER in card
    assert "엔터테인먼트" not in card


def test_render_bazi_card_contains_four_pillars():
    """명식 카드는 연주/월주/일주/시주 4개 기둥을 모두 포함."""
    engine = SajuEngine()
    chart = engine.calc_bazi(1990, 3, 15, 14)

    card = render_bazi_card(chart, birth_str="1990-03-15 14:00")

    # 1990-03-15 14시 기준 프로토타입 예제: 庚午 己卯 己卯 辛未
    assert "庚午" in card
    assert "己卯" in card
    assert "辛未" in card
    assert "1990-03-15 14:00" in card


def test_render_bazi_card_has_header_and_day_master():
    """카드에 명식 헤더와 일간 라벨이 있어야 함."""
    engine = SajuEngine()
    chart = engine.calc_bazi(1990, 3, 15, 14)

    card = render_bazi_card(chart, birth_str="1990-03-15 14:00")

    assert "명식" in card or "四柱" in card
    assert "일간" in card
    # 일간은 己 (이 생일 기준)
    assert "己" in card


def test_render_bazi_card_is_plain_text_and_multiline():
    """Telegram plain text 모드용 — 비어있지 않고 여러 줄."""
    engine = SajuEngine()
    chart = engine.calc_bazi(1990, 3, 15, 14)

    card = render_bazi_card(chart, birth_str="1990-03-15 14:00")

    assert len(card) > 50
    assert "\n" in card


def test_render_bazi_card_handles_missing_hour():
    """시주가 없는(None) BaziChart도 깨지지 않아야 함."""
    engine = SajuEngine()
    chart = engine.calc_bazi(1990, 3, 15, 14)
    chart.hour_gan = None
    chart.hour_zhi = None

    card = render_bazi_card(chart, birth_str="1990-03-15 (시간 미상)")

    assert "1990-03-15" in card
    assert len(card) > 50

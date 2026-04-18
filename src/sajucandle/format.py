"""명식(사주) 카드 렌더러 + 공통 메시지 상수.

Week 8: disclaimer를 "엔터테인먼트 목적" → "정보 제공 목적"으로 톤 상향.
"""
from __future__ import annotations

from sajucandle.saju_engine import BaziChart


DISCLAIMER = "정보 제공 목적. 투자 판단과 손실 책임은 본인에게 있습니다."


def _pillar(gan: str | None, zhi: str | None) -> str:
    """천간+지지를 하나의 기둥 문자열로. 둘 중 하나라도 None이면 '미상'."""
    if not gan or not zhi:
        return "미상"
    return f"{gan}{zhi}"


def render_bazi_card(chart: BaziChart, birth_str: str) -> str:
    """BaziChart를 Telegram 메시지용 plain text 카드로 변환.

    Args:
        chart: SajuEngine.calc_bazi() 결과.
        birth_str: 사용자가 입력한 생년월일시 문자열 (예: "1990-03-15 14:00").

    Returns:
        여러 줄 plain text. Telegram sendMessage(parse_mode=None)로 전송 가능.
    """
    year = _pillar(chart.year_gan, chart.year_zhi)
    month = _pillar(chart.month_gan, chart.month_zhi)
    day = _pillar(chart.day_gan, chart.day_zhi)
    hour = _pillar(chart.hour_gan, chart.hour_zhi)

    lines = [
        "🕯️ 사주캔들 명식",
        "─────────────",
        f"생년월일시: {birth_str}",
        "",
        f"연주: {year}",
        f"월주: {month}",
        f"일주: {day}  ← 일간 {chart.day_gan}",
        f"시주: {hour}",
        "",
        f"※ {DISCLAIMER}",
    ]
    return "\n".join(lines)

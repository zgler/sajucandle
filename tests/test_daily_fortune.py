"""tests/test_daily_fortune.py — 일일 투자 운세 단위 테스트."""
from __future__ import annotations

from datetime import datetime

import pytest

from sajucandle.saju.daily_fortune import generate_daily_fortune, DailyFortune


@pytest.fixture
def sample_saju() -> dict:
    return {
        "year_pillar": "甲辰", "month_pillar": "丙寅",
        "day_pillar": "庚午", "hour_pillar": "戊寅",
        "year_stem": "甲", "year_branch": "辰",
        "month_stem": "丙", "month_branch": "寅",
        "day_stem": "庚", "day_branch": "午",
        "hour_stem": "戊", "hour_branch": "寅",
    }


class TestGenerateDailyFortune:
    def test_returns_daily_fortune(self, sample_saju: dict):
        result = generate_daily_fortune(sample_saju, datetime(2026, 5, 13))
        assert isinstance(result, DailyFortune)

    def test_has_three_scores(self, sample_saju: dict):
        result = generate_daily_fortune(sample_saju, datetime(2026, 5, 13))
        assert 0 <= result.judgment_score <= 100
        assert 0 <= result.execution_score <= 100
        assert 0 <= result.patience_score <= 100

    def test_has_coaching_text(self, sample_saju: dict):
        result = generate_daily_fortune(sample_saju, datetime(2026, 5, 13))
        assert len(result.tengod_label) > 0
        assert len(result.coaching) > 0
        assert len(result.caution) > 0
        assert len(result.detail) > 0

    def test_different_dates_yield_different_results(self, sample_saju: dict):
        r1 = generate_daily_fortune(sample_saju, datetime(2026, 5, 13))
        r2 = generate_daily_fortune(sample_saju, datetime(2026, 5, 14))
        assert r1.tengod_label != r2.tengod_label or r1.judgment_score != r2.judgment_score

    def test_has_shinsal_messages(self, sample_saju: dict):
        result = generate_daily_fortune(sample_saju, datetime(2026, 5, 13))
        assert isinstance(result.shinsal_messages, list)

    def test_has_relation_summary(self, sample_saju: dict):
        result = generate_daily_fortune(sample_saju, datetime(2026, 5, 13))
        assert isinstance(result.relation_messages, list)

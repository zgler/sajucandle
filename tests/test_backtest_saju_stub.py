from datetime import date

from sajucandle.backtest.saju_stub import fixed_saju_score


def test_fixed_saju_score_returns_50():
    assert fixed_saju_score(date(2026, 4, 20), "swing") == 50
    assert fixed_saju_score(date(2020, 1, 1), "scalp") == 50
    assert fixed_saju_score(date.today(), "long") == 50

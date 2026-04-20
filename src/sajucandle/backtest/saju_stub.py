"""백테스트용 사주 점수 스텁.

Phase 1은 중립값 50으로 고정. Phase 4 민감도 분석에서 {0, 50, 100} 3값 비교 예정.
"""
from __future__ import annotations

from datetime import date


def fixed_saju_score(target_date: date, asset_class: str) -> int:
    """백테스트용 고정 사주 composite. 가중치 10%라 결과 편향 제한적."""
    return 50

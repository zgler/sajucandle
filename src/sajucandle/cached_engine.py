"""BaziCache를 두른 SajuEngine 래퍼. 봇과 API 모두 공용."""
from __future__ import annotations

from sajucandle.cache import BaziCache
from sajucandle.saju_engine import BaziChart, SajuEngine


class CachedSajuEngine:
    """SajuEngine과 동일한 메서드 시그니처, 내부적으로 캐시 사용.

    calc_bazi는 (year, month, day, hour) 튜플 단위로 캐시. 분은 시진 분할에
    영향 없어서 키에서 제외.
    """

    def __init__(
        self,
        cache: BaziCache,
        engine: SajuEngine | None = None,
    ) -> None:
        self._cache = cache
        self._engine = engine or SajuEngine()

    def calc_bazi(
        self,
        year: int,
        month: int,
        day: int,
        hour: int,
    ) -> BaziChart:
        key = f"bazi:{year:04d}{month:02d}{day:02d}{hour:02d}"
        return self._cache.get_or_compute(
            key,
            lambda: self._engine.calc_bazi(year, month, day, hour),
        )

    @property
    def engine(self) -> SajuEngine:
        """Public access to the underlying SajuEngine (e.g. for calc_daily_score)."""
        return self._engine

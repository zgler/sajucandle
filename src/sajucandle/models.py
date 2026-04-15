"""API 요청/응답 Pydantic 모델. BaziChart dataclass와 변환 함수."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from sajucandle.saju_engine import BaziChart


class BirthRequest(BaseModel):
    """생년월일시. 시간은 24시 기준, 분은 시진에 영향 없어 무시."""

    year: int = Field(ge=1900, le=2100)
    month: int = Field(ge=1, le=12)
    day: int = Field(ge=1, le=31)
    hour: int = Field(ge=0, le=23)
    minute: int = Field(default=0, ge=0, le=59)


class PillarModel(BaseModel):
    gan: Optional[str] = None
    zhi: Optional[str] = None


class BaziResponse(BaseModel):
    birth_solar: str
    birth_lunar: str
    year: PillarModel
    month: PillarModel
    day: PillarModel
    hour: PillarModel  # gan/zhi Optional (시주 미상 케이스)
    day_gan: str
    wuxing_dist: dict[str, int]
    day_master_strength: str
    yongsin: Optional[str] = None


def bazi_chart_to_response(chart: BaziChart) -> BaziResponse:
    """BaziChart dataclass → Pydantic 응답. WuXing enum은 str로 직렬화."""
    return BaziResponse(
        birth_solar=chart.birth_solar,
        birth_lunar=chart.birth_lunar,
        year=PillarModel(gan=chart.year_gan, zhi=chart.year_zhi),
        month=PillarModel(gan=chart.month_gan, zhi=chart.month_zhi),
        day=PillarModel(gan=chart.day_gan, zhi=chart.day_zhi),
        hour=PillarModel(gan=chart.hour_gan, zhi=chart.hour_zhi),
        day_gan=chart.day_gan,
        wuxing_dist={
            (k.value if hasattr(k, "value") else str(k)): v
            for k, v in chart.wuxing_dist.items()
        },
        day_master_strength=chart.day_master_strength,
        yongsin=chart.yongsin.value if chart.yongsin else None,
    )

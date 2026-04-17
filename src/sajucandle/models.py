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


# ─────────────────────────────────────────────
# Week 3: User profile + Score
# ─────────────────────────────────────────────

from datetime import datetime  # noqa: E402
from typing import List, Literal  # noqa: E402


AssetClass = Literal["swing", "scalp", "long", "default"]


class UserProfileRequest(BaseModel):
    """PUT /v1/users/{chat_id} body."""

    birth_year: int = Field(ge=1900, le=2100)
    birth_month: int = Field(ge=1, le=12)
    birth_day: int = Field(ge=1, le=31)
    birth_hour: int = Field(ge=0, le=23)
    birth_minute: int = Field(default=0, ge=0, le=59)
    asset_class_pref: AssetClass = "swing"


class UserProfileResponse(BaseModel):
    telegram_chat_id: int
    birth_year: int
    birth_month: int
    birth_day: int
    birth_hour: int
    birth_minute: int
    asset_class_pref: AssetClass
    created_at: datetime
    updated_at: datetime


class AxisScore(BaseModel):
    score: int = Field(ge=0, le=100)
    reason: str = ""


class HourRecommendation(BaseModel):
    shichen: str          # "巳"
    time_range: str       # "09:00~11:00"
    multiplier: float     # 1.15


class SajuScoreResponse(BaseModel):
    chat_id: int
    date: str             # "2026-04-16"
    asset_class: AssetClass
    iljin: str            # "庚申"
    composite_score: int = Field(ge=0, le=100)
    signal_grade: str     # "🔥 강한 진입" 같은 원본 문자열
    axes: dict[str, AxisScore]   # keys: wealth, decision, volatility, flow
    best_hours: List[HourRecommendation]


# ─────────────────────────────────────────────
# Week 4: 사주 + 차트 결합 신호
# ─────────────────────────────────────────────


class PricePoint(BaseModel):
    current: float
    change_pct_24h: float


class SajuSummary(BaseModel):
    composite: int = Field(ge=0, le=100)
    grade: str            # 사주 단독 등급 (SajuScoreResponse.signal_grade)


class ChartSummary(BaseModel):
    score: int = Field(ge=0, le=100)
    rsi: float
    ma20: float
    ma50: float
    ma_trend: Literal["up", "down", "flat"]
    volume_ratio: float
    reason: str


class MarketStatus(BaseModel):
    """시장 개장 상태. 카드에 배지 표시용."""
    is_open: bool
    last_session_date: str   # ISO "YYYY-MM-DD" (주식=NY tz, crypto=UTC)
    category: Literal["crypto", "us_stock"]


class SignalResponse(BaseModel):
    chat_id: int
    ticker: str
    date: str             # "2026-04-16"
    price: PricePoint
    saju: SajuSummary
    chart: ChartSummary
    composite_score: int = Field(ge=0, le=100)
    signal_grade: str     # "강진입" | "진입" | "관망" | "회피"
    best_hours: List[HourRecommendation]
    market_status: MarketStatus

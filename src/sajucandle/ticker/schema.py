"""종목 레코드 스키마.

PRD §4-2 다층 사주:
  종목사주 = 0.5 × 창립일_일주 + 0.3 × 상장일_일주 + 0.2 × 전환점_일주

필드:
  symbol            : "NVDA", "BTC-USD" 등 유일 식별자
  name              : "NVIDIA Corp.", "Bitcoin"
  asset_class       : "stock" | "coin"
  market            : "NASDAQ" | "NYSE" | "KOSPI" | "Binance" | "onchain" 등
  sector            : 주식 GICS 섹터 / 코인 카테고리 (L1, DeFi, Meme 등)

  founding_date     : 창립일 (YYYY-MM-DD), 없으면 null
  listing_date      : 상장일 (YYYY-MM-DD), 코인이면 메인넷 런칭일
  transition_points : JSON list of {date: YYYY-MM-DD, label: str}
                      예: [{"date": "2023-06-01", "label": "S&P500 편입"}]

  founding_time     : 창립 시각 HH:MM (KST), 모르면 "00:00"
  listing_time      : 상장 시각 HH:MM (KST), 모르면 "09:30" 뉴욕 개장 등
  birth_city        : 창립/상장 도시명 (태양시 보정용)

  weight_founding   : 가중치 (0~1), 기본 0.5
  weight_listing    : 기본 0.3
  weight_transition : 기본 0.2

  notes             : 자유 메모
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class TransitionPoint:
    date: str        # YYYY-MM-DD
    label: str       # 설명 (예: "S&P500 편입")
    time: str = "00:00"


@dataclass
class TickerRecord:
    symbol: str
    name: str
    asset_class: str  # "stock" | "coin"
    market: str

    founding_date: Optional[str] = None
    founding_time: str = "09:00"   # 평균적 업무시작 시간 기본값
    listing_date: Optional[str] = None
    listing_time: str = "09:30"
    birth_city: str = "New York"

    transition_points: List[TransitionPoint] = field(default_factory=list)

    sector: str = ""

    weight_founding: float = 0.5
    weight_listing: float = 0.3
    weight_transition: float = 0.2

    notes: str = ""

    def normalize_weights(self) -> None:
        """유효한 구성요소만 기준으로 가중치 재정규화.

        예: founding_date가 없으면 listing 0.6 + transition 0.4로 재분배.
        """
        total_w = 0.0
        if self.founding_date:
            total_w += self.weight_founding
        if self.listing_date:
            total_w += self.weight_listing
        if self.transition_points:
            total_w += self.weight_transition
        if total_w == 0:
            return
        if self.founding_date:
            self.weight_founding = self.weight_founding / total_w
        else:
            self.weight_founding = 0.0
        if self.listing_date:
            self.weight_listing = self.weight_listing / total_w
        else:
            self.weight_listing = 0.0
        if self.transition_points:
            self.weight_transition = self.weight_transition / total_w
        else:
            self.weight_transition = 0.0


# CSV 컬럼 (평탄화된 형태)
CSV_COLUMNS = [
    "symbol", "name", "asset_class", "market", "sector",
    "founding_date", "founding_time",
    "listing_date", "listing_time",
    "birth_city",
    "transition_points_json",
    "weight_founding", "weight_listing", "weight_transition",
    "notes",
]

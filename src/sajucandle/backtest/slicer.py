"""HistoryWindow — 백테스트 시점 t 기준 OHLCV 슬라이싱.

룩어헤드 방지: slice_at(t)는 `open_time + interval <= t`인 봉만 반환.
post_bars_1h(t, hours)는 반대로 t 이후 봉 반환 (백테스트 추적용).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sajucandle.backtest.history import TickerHistory
from sajucandle.market_data import Kline


@dataclass
class HistoryWindow:
    history: TickerHistory

    def slice_at(self, t: datetime) -> tuple[list[Kline], list[Kline], list[Kline]]:
        """t 이전에 **닫힌** 봉만 반환. 각 TF 별도.

        룩어헤드 방지: `k.open_time + interval <= t`
        """
        def _closed_before(klines: list[Kline], interval: timedelta) -> list[Kline]:
            return [k for k in klines if k.open_time + interval <= t]

        k1h = _closed_before(self.history.klines_1h, timedelta(hours=1))
        k4h = _closed_before(self.history.klines_4h, timedelta(hours=4))
        k1d = _closed_before(self.history.klines_1d, timedelta(days=1))
        return k1h, k4h, k1d

    def post_bars_1h(self, t: datetime, hours: int = 168) -> list[Kline]:
        """t 이후 hours시간치 1h봉 반환 (MFE/MAE 추적용).

        룩어헤드 허용 — 백테스트 시점에서 미래는 이미 확정된 과거 데이터.
        """
        end = t + timedelta(hours=hours)
        return [k for k in self.history.klines_1h if t <= k.open_time < end]

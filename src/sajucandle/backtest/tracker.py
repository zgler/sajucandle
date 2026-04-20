"""백테스트 MFE/MAE 계산 — broadcast.run_phase0_tracking 공식 재사용."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from sajucandle.market_data import Kline


@dataclass
class MfeMae:
    mfe_pct: float
    mae_pct: float
    close_24h: Optional[float]
    close_7d: Optional[float]


def compute_mfe_mae(
    *,
    entry_price: float,
    post_bars_1h: list[Kline],
    sent_at: datetime,
) -> Optional[MfeMae]:
    """entry_price 대비 sent_at 이후 post_bars의 최고/최저가 → MFE/MAE %.

    - MFE = (max(high) / entry - 1) × 100
    - MAE = (min(low)  / entry - 1) × 100   (음수)
    - close_24h/7d = sent_at+24h/+7d 이후 첫 봉의 close

    Returns None: entry <= 0 or post_bars 비어있음.
    """
    if entry_price <= 0 or not post_bars_1h:
        return None
    highs = [k.high for k in post_bars_1h]
    lows = [k.low for k in post_bars_1h]
    mfe = (max(highs) / entry_price - 1.0) * 100.0
    mae = (min(lows) / entry_price - 1.0) * 100.0

    close_24h: Optional[float] = None
    close_7d: Optional[float] = None
    t_24h = sent_at + timedelta(hours=24)
    t_7d = sent_at + timedelta(days=7)
    for k in post_bars_1h:
        if close_24h is None and k.open_time >= t_24h:
            close_24h = k.close
        if close_7d is None and k.open_time >= t_7d:
            close_7d = k.close
            break

    return MfeMae(
        mfe_pct=mfe, mae_pct=mae,
        close_24h=close_24h, close_7d=close_7d,
    )

"""Volume Profile (VPVR) 근사치: 가격 bucket별 거래량 누적.

MVP: 각 봉의 중간값 (high+low)/2가 속한 bucket에 volume 전체 배정.
"""
from __future__ import annotations

from dataclasses import dataclass

from sajucandle.market_data import Kline


@dataclass
class VolumeNode:
    price_low: float
    price_high: float
    volume_sum: float


def compute_volume_profile(
    klines: list[Kline],
    bucket_count: int = 20,
    top_n: int = 3,
) -> list[VolumeNode]:
    """가격 범위를 bucket_count 등분 → 각 bucket 거래량 합 → 상위 top_n.

    반환: volume_sum 내림차순. 빈 입력/가격 range=0이면 [].
    """
    if not klines or bucket_count <= 0 or top_n <= 0:
        return []

    price_min = min(k.low for k in klines)
    price_max = max(k.high for k in klines)
    if price_max <= price_min:
        return []

    bucket_width = (price_max - price_min) / bucket_count
    if bucket_width <= 0:
        return []

    buckets: list[float] = [0.0] * bucket_count
    for k in klines:
        mid = (k.high + k.low) / 2
        idx = int((mid - price_min) / bucket_width)
        if idx == bucket_count:
            idx = bucket_count - 1
        if 0 <= idx < bucket_count:
            buckets[idx] += k.volume

    nodes: list[VolumeNode] = []
    for i, vol in enumerate(buckets):
        if vol <= 0:
            continue
        low = price_min + i * bucket_width
        high = price_min + (i + 1) * bucket_width
        nodes.append(VolumeNode(
            price_low=low, price_high=high, volume_sum=vol,
        ))

    nodes.sort(key=lambda n: n.volume_sum, reverse=True)
    return nodes[:top_n]

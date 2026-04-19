"""analysis.volume_profile: 가격 bucket별 거래량 누적 → 매물대 상위 N개."""
from __future__ import annotations

from datetime import datetime, timezone

from sajucandle.analysis.volume_profile import VolumeNode, compute_volume_profile
from sajucandle.market_data import Kline


def _mk_klines(triples: list[tuple[float, float, float]]) -> list[Kline]:
    """Each tuple = (high, low, volume). open=close=(h+l)/2."""
    out = []
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for i, (h, lo, v) in enumerate(triples):
        mid = (h + lo) / 2
        out.append(Kline(
            open_time=base.replace(day=(i % 28) + 1),
            open=mid, high=h, low=lo, close=mid, volume=v,
        ))
    return out


def test_compute_volume_profile_empty():
    assert compute_volume_profile([]) == []


def test_compute_volume_profile_returns_top_n_nodes():
    klines = _mk_klines([
        (105, 100, 100),
        (110, 105, 500),
        (105, 100, 200),
        (110, 105, 500),
        (115, 110, 50),
        (105, 100, 300),
    ])
    nodes = compute_volume_profile(klines, bucket_count=5, top_n=3)
    assert len(nodes) <= 3
    assert all(isinstance(n, VolumeNode) for n in nodes)
    assert nodes[0].volume_sum >= nodes[-1].volume_sum


def test_volume_node_is_dataclass():
    from dataclasses import is_dataclass
    assert is_dataclass(VolumeNode)
    n = VolumeNode(price_low=100.0, price_high=105.0, volume_sum=500.0)
    assert n.price_low == 100.0


def test_compute_volume_profile_bucket_boundaries():
    klines = _mk_klines([(100 + i, 100 + i, 10) for i in range(10)])
    nodes = compute_volume_profile(klines, bucket_count=10, top_n=5)
    assert len(nodes) == 5
    for n in nodes:
        assert n.price_low < n.price_high


def test_compute_volume_profile_single_price_returns_one_node():
    klines = _mk_klines([(100, 100, 100)] * 5)
    nodes = compute_volume_profile(klines, bucket_count=5, top_n=3)
    assert len(nodes) <= 1

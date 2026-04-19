"""Swing points + Volume profile → SRLevel 융합.

후보 수집 → merge → strength 판정 → 현재가 기준 필터 + 정렬.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Literal

from sajucandle.analysis.swing import SwingPoint
from sajucandle.analysis.volume_profile import compute_volume_profile
from sajucandle.market_data import Kline


class LevelKind(str, Enum):
    SUPPORT = "support"
    RESISTANCE = "resistance"


@dataclass
class SRLevel:
    price: float
    kind: LevelKind
    strength: Literal["low", "medium", "high"]
    sources: list[str] = field(default_factory=list)


_STRENGTH_ORDER = {"low": 0, "medium": 1, "high": 2}


def identify_sr_levels(
    klines_1d: list[Kline],
    swings: list[SwingPoint],
    current_price: float,
    *,
    max_supports: int = 3,
    max_resistances: int = 3,
    merge_tolerance_pct: float = 0.5,
    volume_top_n: int = 5,
    volume_bucket_count: int = 20,
) -> list[SRLevel]:
    if not klines_1d or current_price <= 0:
        return []

    volume_nodes = compute_volume_profile(
        klines_1d, bucket_count=volume_bucket_count, top_n=volume_top_n
    )
    top_volume_sum = volume_nodes[0].volume_sum if volume_nodes else 0.0

    # 후보 수집
    candidates: list[SRLevel] = []
    for sp in swings:
        if sp.kind == "high":
            candidates.append(SRLevel(
                price=sp.price, kind=LevelKind.RESISTANCE,
                strength="low", sources=["swing_high"],
            ))
        elif sp.kind == "low":
            candidates.append(SRLevel(
                price=sp.price, kind=LevelKind.SUPPORT,
                strength="low", sources=["swing_low"],
            ))

    for node in volume_nodes:
        mid = (node.price_low + node.price_high) / 2
        is_top = (node.volume_sum == top_volume_sum)
        kind = LevelKind.RESISTANCE if mid > current_price else LevelKind.SUPPORT
        strength: Literal["low", "medium", "high"] = "medium" if is_top else "low"
        candidates.append(SRLevel(
            price=mid, kind=kind, strength=strength, sources=["volume_node"],
        ))

    # 병합
    merged = _merge_levels(candidates, merge_tolerance_pct)

    # strength 재판정: swing + volume 겹침 → high
    for level in merged:
        has_swing = any(s.startswith("swing_") for s in level.sources)
        has_volume = "volume_node" in level.sources
        if has_swing and has_volume:
            level.strength = "high"

    # 현재가 기준 필터 + 정렬
    supports = [x for x in merged
                if x.kind == LevelKind.SUPPORT and x.price < current_price]
    resistances = [x for x in merged
                   if x.kind == LevelKind.RESISTANCE and x.price > current_price]
    supports.sort(key=lambda x: current_price - x.price)
    resistances.sort(key=lambda x: x.price - current_price)

    return supports[:max_supports] + resistances[:max_resistances]


def _merge_levels(
    candidates: list[SRLevel], tolerance_pct: float
) -> list[SRLevel]:
    if not candidates:
        return []
    by_kind: dict[LevelKind, list[SRLevel]] = {
        LevelKind.SUPPORT: [], LevelKind.RESISTANCE: [],
    }
    for c in candidates:
        by_kind[c.kind].append(c)

    merged: list[SRLevel] = []
    for kind, group in by_kind.items():
        group = sorted(group, key=lambda x: x.price)
        cluster: list[SRLevel] = []

        def _flush(cl: list[SRLevel]):
            if not cl:
                return
            avg_price = sum(x.price for x in cl) / len(cl)
            all_sources: list[str] = []
            max_strength: Literal["low", "medium", "high"] = "low"
            for x in cl:
                for s in x.sources:
                    if s not in all_sources:
                        all_sources.append(s)
                if _STRENGTH_ORDER[x.strength] > _STRENGTH_ORDER[max_strength]:
                    max_strength = x.strength
            merged.append(SRLevel(
                price=avg_price, kind=kind,
                strength=max_strength, sources=all_sources,
            ))

        for c in group:
            if not cluster:
                cluster.append(c)
                continue
            last = cluster[-1]
            if abs(c.price - last.price) / max(last.price, 1e-9) * 100 <= tolerance_pct:
                cluster.append(c)
            else:
                _flush(cluster)
                cluster = [c]
        _flush(cluster)

    return merged

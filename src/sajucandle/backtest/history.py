"""벌크 OHLCV 로더 + 디스크 JSON 캐시.

Phase 1 시간 스냅샷 메커니즘: bulk fetch + in-memory slice (Decision 3.1-B).
디스크 캐시로 재실행 시 HTTP 0회 (`.cache/backtest/{ticker}_{interval}.json`).
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from sajucandle.market.base import MarketDataProvider
from sajucandle.market_data import Kline

logger = logging.getLogger(__name__)

_DEFAULT_LIMIT_1D = 750       # 2년 여유
_DEFAULT_LIMIT_4H = 4400      # 2년 × 6
_DEFAULT_LIMIT_1H = 17600     # 2년 × 24


@dataclass
class TickerHistory:
    ticker: str
    klines_1h: list[Kline]
    klines_4h: list[Kline]
    klines_1d: list[Kline]


def _cache_path(cache_dir: Path, ticker: str, interval: str) -> Path:
    safe = ticker.replace("/", "_")
    return cache_dir / f"{safe}_{interval}.json"


def _load_cache(p: Path) -> Optional[list[Kline]]:
    if not p.exists():
        return None
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        return [Kline.from_dict(d) for d in raw]
    except Exception as e:
        logger.warning("cache load failed %s: %s", p, e)
        return None


def _save_cache(p: Path, klines: list[Kline]) -> None:
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            json.dumps([k.to_dict() for k in klines], ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception as e:
        logger.warning("cache save failed %s: %s", p, e)


def load_history(
    ticker: str,
    from_dt: datetime,
    to_dt: datetime,
    *,
    provider: MarketDataProvider,
    cache_dir: Optional[Path] = None,
) -> TickerHistory:
    """Provider에서 1h/4h/1d OHLCV 벌크 로드.

    cache_dir 제공 시 디스크 JSON 캐시 사용 (재실행 시 HTTP 0회).
    from_dt/to_dt는 현재는 limit 계산 참고용 (provider가 `since` 미지원이면 최근 N봉만 반환).
    """
    if cache_dir:
        cache_dir = Path(cache_dir)

    klines_by_interval: dict[str, list[Kline]] = {}
    limits = {"1h": _DEFAULT_LIMIT_1H, "4h": _DEFAULT_LIMIT_4H, "1d": _DEFAULT_LIMIT_1D}

    for interval, limit in limits.items():
        # 캐시 확인
        if cache_dir:
            cpath = _cache_path(cache_dir, ticker, interval)
            cached = _load_cache(cpath)
            if cached is not None:
                logger.info("cache hit %s %s (%d bars)", ticker, interval, len(cached))
                klines_by_interval[interval] = cached
                continue
        # Provider fetch
        logger.info("fetching %s %s (limit=%d)", ticker, interval, limit)
        klines = provider.fetch_klines(ticker, interval=interval, limit=limit)
        klines_by_interval[interval] = klines
        # 캐시 저장
        if cache_dir:
            _save_cache(_cache_path(cache_dir, ticker, interval), klines)

    return TickerHistory(
        ticker=ticker,
        klines_1h=klines_by_interval["1h"],
        klines_4h=klines_by_interval["4h"],
        klines_1d=klines_by_interval["1d"],
    )

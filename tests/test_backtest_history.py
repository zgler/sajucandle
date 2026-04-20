"""backtest.history: OHLCV 벌크 로더 + 디스크 JSON 캐시."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock

from sajucandle.backtest.history import TickerHistory, load_history
from sajucandle.market_data import Kline


def _kline(ts: datetime, v: float) -> Kline:
    return Kline(open_time=ts, open=v, high=v + 1, low=v - 1, close=v, volume=100)


def test_load_history_returns_three_tf(tmp_path):
    """provider.fetch_klines 3회 호출 (1h, 4h, 1d)."""
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    provider = MagicMock()
    provider.fetch_klines = MagicMock(return_value=[_kline(base, 100.0)])

    hist = load_history(
        ticker="BTCUSDT",
        from_dt=base,
        to_dt=datetime(2026, 2, 1, tzinfo=timezone.utc),
        provider=provider,
        cache_dir=tmp_path,
    )
    assert isinstance(hist, TickerHistory)
    assert hist.ticker == "BTCUSDT"
    # 1h / 4h / 1d 각각 fetch_klines 호출
    assert provider.fetch_klines.call_count == 3
    # 각 호출의 interval 검증
    intervals = [c.kwargs.get("interval") or c.args[1]
                 for c in provider.fetch_klines.call_args_list]
    assert set(intervals) == {"1h", "4h", "1d"}


def test_load_history_disk_cache_hit(tmp_path):
    """두 번째 호출 시 provider 호출 안 함 (캐시 파일 존재)."""
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    provider = MagicMock()
    provider.fetch_klines = MagicMock(return_value=[_kline(base, 100.0)])

    # 1st call — fetch
    load_history(
        ticker="BTCUSDT", from_dt=base,
        to_dt=datetime(2026, 2, 1, tzinfo=timezone.utc),
        provider=provider, cache_dir=tmp_path,
    )
    assert provider.fetch_klines.call_count == 3

    # 2nd call — cache hit
    load_history(
        ticker="BTCUSDT", from_dt=base,
        to_dt=datetime(2026, 2, 1, tzinfo=timezone.utc),
        provider=provider, cache_dir=tmp_path,
    )
    assert provider.fetch_klines.call_count == 3   # 증가 없음


def test_load_history_cache_file_format(tmp_path):
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    provider = MagicMock()
    provider.fetch_klines = MagicMock(return_value=[
        _kline(base, 100.0), _kline(base, 101.0),
    ])

    load_history(
        ticker="BTCUSDT", from_dt=base,
        to_dt=datetime(2026, 2, 1, tzinfo=timezone.utc),
        provider=provider, cache_dir=tmp_path,
    )
    # cache file 존재 확인
    cache_files = list(tmp_path.glob("*.json"))
    assert len(cache_files) == 3   # 1h / 4h / 1d
    for f in cache_files:
        data = json.loads(f.read_text(encoding="utf-8"))
        assert isinstance(data, list)
        assert len(data) == 2
        assert "open_time" in data[0]

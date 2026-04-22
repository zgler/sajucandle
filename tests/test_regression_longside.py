"""Phase 2 회귀 방어: LONG 사이드 고정 스냅샷.

Phase 2 전환 후 LONG direction 결과의 핵심 필드(grade, composite_score,
TradeSetup entry/SL/TP/R:R)를 JSON 스냅샷으로 고정. 미래 엔진 변경이
롱 사이드를 깨뜨리는지 여부를 정량 감지한다.

스냅샷 갱신 절차(의도된 변경일 때):
    pytest tests/test_regression_longside.py --update-snapshot
    (or) UPDATE_SNAPSHOT=1 pytest tests/test_regression_longside.py
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from sajucandle.backtest.engine import run_backtest
from sajucandle.backtest.history import TickerHistory
from sajucandle.market_data import Kline


SNAPSHOT_PATH = Path(__file__).parent / "snapshots" / "phase2_longside_baseline.json"


def _uptrend_history(ticker: str) -> TickerHistory:
    """Phase 1 smoke와 동일한 monotonic uptrend 합성 히스토리."""
    base = datetime(2025, 1, 1, tzinfo=timezone.utc)
    k1d = [
        Kline(
            open_time=base + timedelta(days=i),
            open=100 + i * 0.5, high=100 + i * 0.5 + 1,
            low=100 + i * 0.5 - 1, close=100 + i * 0.5, volume=1000,
        )
        for i in range(200)
    ]
    k4h = [
        Kline(
            open_time=base + timedelta(hours=4 * i),
            open=100 + i * 0.08, high=100 + i * 0.08 + 0.5,
            low=100 + i * 0.08 - 0.5, close=100 + i * 0.08, volume=300,
        )
        for i in range(200 * 6)
    ]
    k1h = [
        Kline(
            open_time=base + timedelta(hours=i),
            open=100 + i * 0.02, high=100 + i * 0.02 + 0.2,
            low=100 + i * 0.02 - 0.2, close=100 + i * 0.02, volume=100,
        )
        for i in range(200 * 24)
    ]
    return TickerHistory(ticker=ticker, klines_1h=k1h, klines_4h=k4h, klines_1d=k1d)


async def _collect_rows(mode: str) -> list[dict]:
    from_dt = datetime(2025, 3, 1, tzinfo=timezone.utc)
    to_dt = datetime(2025, 3, 11, tzinfo=timezone.utc)
    hist = _uptrend_history("BTCUSDT")

    inserted: list[dict] = []

    async def fake_insert(**kwargs):
        inserted.append(kwargs)
        return len(inserted)

    await run_backtest(
        ticker="BTCUSDT",
        from_dt=from_dt, to_dt=to_dt,
        run_id=f"phase2-snapshot-{mode}",
        router=MagicMock(),
        saju_score_fn=lambda d, ac: 50,
        insert_log_fn=fake_insert,
        history_override=hist,
        mode=mode,
    )
    return inserted


def _extract_core(rows: list[dict], long_only: bool = False) -> list[dict]:
    """핵심 필드 추출, 정렬. entry_price·SL·TP·rr는 소수 6자리로 고정해서
    부동소수 jitter 제거.

    long_only=True면 진입_L/강진입_L 만 필터. False면 전체 row (관망 포함).
    """
    def _round(v):
        return round(v, 6) if isinstance(v, (int, float)) else v

    keys = [
        "target_date", "signal_grade", "composite_score",
        "signal_direction", "entry_price",
        "stop_loss", "take_profit_1", "take_profit_2",
        "risk_pct", "rr_tp1", "rr_tp2",
        "sl_basis", "tp1_basis", "tp2_basis",
    ]
    out = []
    for r in rows:
        if long_only and r.get("signal_grade") not in ("진입_L", "강진입_L"):
            continue
        row_out = {k: _round(r.get(k)) for k in keys}
        row_out["target_date"] = str(row_out["target_date"])
        out.append(row_out)
    out.sort(key=lambda x: x["target_date"])
    return out


@pytest.mark.asyncio
async def test_phase2_smoke_snapshot():
    """symmetric 모드 출력 전체(10 rows)가 고정 스냅샷과 일치.

    의도된 변경 시: UPDATE_SNAPSHOT=1 로 재생성.
    """
    rows = await _collect_rows(mode="symmetric")
    core = _extract_core(rows, long_only=False)

    update = os.environ.get("UPDATE_SNAPSHOT") == "1"
    need_seed = (
        not SNAPSHOT_PATH.exists()
        or SNAPSHOT_PATH.read_text(encoding="utf-8").strip() in ("", "[]")
    )
    if update or need_seed:
        SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
        SNAPSHOT_PATH.write_text(
            json.dumps(core, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        pytest.skip(f"snapshot written to {SNAPSHOT_PATH} ({len(core)} rows)")

    expected = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    assert core == expected, (
        f"스냅샷 불일치.\n"
        f"expected ({len(expected)} rows): {expected[:2]}...\n"
        f"got ({len(core)} rows): {core[:2]}..."
    )


@pytest.mark.asyncio
async def test_phase2_longonly_matches_symmetric_on_monotonic_uptrend():
    """monotonic uptrend smoke에서 longonly vs symmetric 출력 완전 동일.

    실 합성 데이터에서 LONG 사이드 회귀 0 검증 (스펙 §3.8 회귀 방어 조건 §9.4).
    """
    sym = _extract_core(await _collect_rows(mode="symmetric"))
    lon = _extract_core(await _collect_rows(mode="longonly"))
    assert sym == lon

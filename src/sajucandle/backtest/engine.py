"""Phase 1 백테스트 엔진.

매일 1회 UTC 종가 시점에 analyze + grade + trade_setup + MFE/MAE 계산 →
signal_log에 source='backtest' + run_id로 기록.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Awaitable, Callable, Optional

from sajucandle.analysis.composite import analyze
from sajucandle.analysis.trade_setup import compute_trade_setup
from sajucandle.backtest.history import TickerHistory, load_history
from sajucandle.backtest.saju_stub import fixed_saju_score
from sajucandle.backtest.slicer import HistoryWindow
from sajucandle.backtest.tracker import compute_mfe_mae
from sajucandle.market.router import MarketRouter
from sajucandle.signal_service import _grade_signal
from sajucandle import repositories

logger = logging.getLogger(__name__)


@dataclass
class BacktestSummary:
    run_id: str
    ticker: str
    from_dt: datetime
    to_dt: datetime
    signals_total: int = 0
    signals_by_grade: dict[str, int] = field(default_factory=dict)
    insert_errors: int = 0


async def run_backtest(
    *,
    ticker: str,
    from_dt: datetime,
    to_dt: datetime,
    run_id: str,
    router: MarketRouter,
    saju_score_fn: Callable[[date, str], int] = fixed_saju_score,
    asset_class: str = "swing",
    cache_dir: Optional[Path] = None,
    insert_log_fn: Optional[Callable[..., Awaitable[int]]] = None,
    history_override: Optional[TickerHistory] = None,
) -> BacktestSummary:
    """Phase 1 백테스트 엔트리.

    Args:
        insert_log_fn: 테스트 주입용. None이면 repositories.insert_signal_log 사용.
        history_override: 테스트 주입용. None이면 router에서 fetch.
    """
    # 히스토리 준비
    if history_override is not None:
        hist = history_override
    else:
        provider = router.get_provider(ticker)
        hist = load_history(
            ticker, from_dt, to_dt, provider=provider, cache_dir=cache_dir
        )
    window = HistoryWindow(history=hist)

    # 일별 시점 생성 (UTC 00:00 시리즈)
    signal_times: list[datetime] = []
    cursor = datetime(from_dt.year, from_dt.month, from_dt.day,
                      0, 0, tzinfo=timezone.utc) + timedelta(days=1)
    end = datetime(to_dt.year, to_dt.month, to_dt.day,
                   0, 0, tzinfo=timezone.utc)
    while cursor <= end:
        signal_times.append(cursor)
        cursor += timedelta(days=1)

    summary = BacktestSummary(
        run_id=run_id, ticker=ticker,
        from_dt=from_dt, to_dt=to_dt,
    )

    from sajucandle import db

    for t in signal_times:
        try:
            k1h, k4h, k1d = window.slice_at(t)
            # 분석에 필요한 최소 데이터:
            #   - 1d: 최소 2봉 (current close)
            #   - 1h: RSI(14) 위해 15봉 이상
            # EMA50/스윙 부족 시 analyze는 RANGE/FLAT로 graceful fallback.
            if len(k1d) < 1:
                continue
            if len(k1h) < 15:
                continue

            analysis = analyze(k1h, k4h, k1d)
            current = k1d[-1].close

            saju = saju_score_fn(t.date(), asset_class)
            final = round(0.1 * saju + 0.9 * analysis.composite_score)
            final = max(0, min(100, final))

            grade = _grade_signal(final, analysis)

            ts = None
            if grade in ("강진입", "진입") and analysis.atr_1d > 0:
                ts = compute_trade_setup(
                    entry=current, atr_1d=analysis.atr_1d,
                    sr_levels=analysis.sr_levels,
                )

            # MFE/MAE
            post = window.post_bars_1h(t, hours=168)
            mfe_mae = compute_mfe_mae(
                entry_price=current, post_bars_1h=post, sent_at=t,
            )

            # 7일(168h)치 post_bars_1h가 full로 있으면 tracking 완료.
            # post_bars_1h는 strict inequality (open_time < end)라 마지막 봉의
            # open_time은 t+167h 근처. 개수로 판정이 가장 정확.
            tracking_done = len(post) >= 168

            # insert
            insert_fn = insert_log_fn
            if insert_fn is None:
                async def _default_insert(**kwargs):
                    if db.get_pool() is None:
                        raise RuntimeError("db pool not initialized")
                    async with db.acquire() as conn:
                        return await repositories.insert_signal_log(conn, **kwargs)
                insert_fn = _default_insert

            try:
                await insert_fn(
                    source="backtest",
                    telegram_chat_id=None,
                    ticker=ticker,
                    target_date=t.date(),
                    entry_price=current,
                    saju_score=saju,
                    analysis_score=analysis.composite_score,
                    structure_state=analysis.structure.state.value,
                    alignment_bias=analysis.alignment.bias,
                    rsi_1h=analysis.rsi_1h,
                    volume_ratio_1d=analysis.volume_ratio_1d,
                    composite_score=final,
                    signal_grade=grade,
                    stop_loss=ts.stop_loss if ts else None,
                    take_profit_1=ts.take_profit_1 if ts else None,
                    take_profit_2=ts.take_profit_2 if ts else None,
                    risk_pct=ts.risk_pct if ts else None,
                    rr_tp1=ts.rr_tp1 if ts else None,
                    rr_tp2=ts.rr_tp2 if ts else None,
                    sl_basis=ts.sl_basis if ts else None,
                    tp1_basis=ts.tp1_basis if ts else None,
                    tp2_basis=ts.tp2_basis if ts else None,
                    run_id=run_id,
                )
                # 주의: MFE/MAE는 별도 update_signal_tracking 호출로 기록해야 한다.
                # Phase 1 최소 구현은 insert 시점에서 mfe_mae는 이미 계산됐으므로
                # 동일 connection에서 UPDATE 수행.
                if mfe_mae is not None and db.get_pool() is not None and insert_log_fn is None:
                    async with db.acquire() as conn:
                        last_id = await conn.fetchval(
                            "SELECT id FROM signal_log WHERE run_id = $1 "
                            "AND ticker = $2 AND target_date = $3 "
                            "ORDER BY id DESC LIMIT 1",
                            run_id, ticker, t.date(),
                        )
                        if last_id:
                            await repositories.update_signal_tracking(
                                conn, last_id,
                                mfe_pct=mfe_mae.mfe_pct,
                                mae_pct=mfe_mae.mae_pct,
                                close_24h=mfe_mae.close_24h,
                                close_7d=mfe_mae.close_7d,
                                tracking_done=tracking_done,
                            )

                summary.signals_total += 1
                summary.signals_by_grade[grade] = (
                    summary.signals_by_grade.get(grade, 0) + 1
                )
            except Exception as e:
                logger.warning("insert signal_log 실패 t=%s: %s", t, e)
                summary.insert_errors += 1

        except Exception as e:
            logger.warning("backtest t=%s 예외: %s", t, e)
            continue

    logger.info(
        "backtest done run_id=%s ticker=%s total=%d grades=%s errors=%d",
        run_id, ticker, summary.signals_total,
        summary.signals_by_grade, summary.insert_errors,
    )
    return summary

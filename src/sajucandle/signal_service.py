"""사주 + 차트 결합 신호 서비스 (Week 8 개편).

책임:
1. ScoreService.compute() → 사주 composite (가중치 0.1)
2. MarketRouter → 1h/4h/1d 3개 TF fetch
3. analysis.composite.analyze() → AnalysisResult (가중치 0.9)
4. 가중합 → final_score + grade (grade는 추가 조건 필요)
5. SignalResponse 조립 (analysis 필드 + chart 하위호환)
6. Redis 캐시 (signal:*, TTL=300)
"""
from __future__ import annotations

import json
import logging
from datetime import date
from typing import Optional

from sajucandle.analysis.composite import AnalysisResult, analyze
from sajucandle.analysis.structure import MarketStructure
from sajucandle.analysis.trade_setup import TradeSetup, compute_trade_setup
from sajucandle.market.router import MarketRouter
from sajucandle.market_data import Kline
from sajucandle.models import (
    AlignmentSummary,
    AnalysisSummary,
    ChartSummary,
    MarketStatus,
    PricePoint,
    SajuSummary,
    SignalResponse,
    SRLevelSummary,
    StructureSummary,
    TradeSetupSummary,
)
from sajucandle.repositories import UserProfile
from sajucandle.score_service import ScoreService

logger = logging.getLogger(__name__)

_SIGNAL_TTL = 300


def _grade_signal(score: int, analysis: AnalysisResult) -> str:
    """Week 8: 강진입은 점수 + 정렬 + 상승구조 3조건 모두 만족."""
    if (score >= 75
            and analysis.alignment.aligned
            and analysis.structure.state in (MarketStructure.UPTREND, MarketStructure.BREAKOUT)):
        return "강진입"
    if score >= 60:
        return "진입"
    if score >= 40:
        return "관망"
    return "회피"


def _analysis_to_summary(
    a: AnalysisResult,
    trade_setup: Optional[TradeSetup] = None,
) -> AnalysisSummary:
    sr_summaries = [
        SRLevelSummary(
            price=lvl.price,
            kind=lvl.kind.value,
            strength=lvl.strength,
        )
        for lvl in a.sr_levels
    ]
    ts_summary = None
    if trade_setup is not None:
        ts_summary = TradeSetupSummary(
            entry=trade_setup.entry,
            stop_loss=trade_setup.stop_loss,
            take_profit_1=trade_setup.take_profit_1,
            take_profit_2=trade_setup.take_profit_2,
            risk_pct=trade_setup.risk_pct,
            rr_tp1=trade_setup.rr_tp1,
            rr_tp2=trade_setup.rr_tp2,
            sl_basis=trade_setup.sl_basis,
            tp1_basis=trade_setup.tp1_basis,
            tp2_basis=trade_setup.tp2_basis,
        )
    return AnalysisSummary(
        structure=StructureSummary(
            state=a.structure.state.value,
            score=a.structure.score,
        ),
        alignment=AlignmentSummary(
            tf_1h=a.alignment.tf_1h.value,
            tf_4h=a.alignment.tf_4h.value,
            tf_1d=a.alignment.tf_1d.value,
            aligned=a.alignment.aligned,
            bias=a.alignment.bias,
            score=a.alignment.score,
        ),
        rsi_1h=a.rsi_1h,
        volume_ratio_1d=a.volume_ratio_1d,
        composite_score=a.composite_score,
        reason=a.reason,
        sr_levels=sr_summaries,
        trade_setup=ts_summary,
    )


class SignalService:
    def __init__(
        self,
        score_service: ScoreService,
        market_router: MarketRouter,
        redis_client=None,
    ):
        self._score = score_service
        self._router = market_router
        self._redis = redis_client

    def compute(
        self,
        profile: UserProfile,
        target_date: date,
        ticker: str,
    ) -> SignalResponse:
        cache_key = (
            f"signal:{profile.telegram_chat_id}:{target_date.isoformat()}:{ticker}"
        )
        cached = self._redis_get(cache_key)
        if cached is not None:
            return cached

        saju_resp = self._score.compute(
            profile, target_date, profile.asset_class_pref
        )
        provider = self._router.get_provider(ticker)

        # 3개 TF fetch
        klines_1d: list[Kline] = provider.fetch_klines(ticker, interval="1d", limit=100)
        klines_4h: list[Kline] = provider.fetch_klines(ticker, interval="4h", limit=150)
        klines_1h: list[Kline] = provider.fetch_klines(ticker, interval="1h", limit=200)

        # 분석
        analysis = analyze(klines_1h, klines_4h, klines_1d)

        # 가격 (1d 기준)
        current = klines_1d[-1].close
        prev = klines_1d[-2].close if len(klines_1d) >= 2 else current
        change_pct = ((current / prev) - 1.0) * 100 if prev else 0.0

        # 최종 점수 + 등급
        final = round(0.1 * saju_resp.composite_score + 0.9 * analysis.composite_score)
        final = max(0, min(100, final))
        grade = _grade_signal(final, analysis)

        # Week 9: TradeSetup 조건부 생성
        trade_setup: Optional[TradeSetup] = None
        if grade in ("강진입", "진입") and analysis.atr_1d > 0:
            trade_setup = compute_trade_setup(
                entry=current,
                atr_1d=analysis.atr_1d,
                sr_levels=analysis.sr_levels,
            )

        is_crypto = ticker.upper().lstrip("$") == "BTCUSDT"
        market_status = MarketStatus(
            is_open=provider.is_market_open(ticker),
            last_session_date=provider.last_session_date(ticker).isoformat(),
            category="crypto" if is_crypto else "us_stock",
        )

        analysis_summary = _analysis_to_summary(analysis, trade_setup)

        # ma_trend 매핑 (하위호환 ChartSummary용)
        tf_1d_value = analysis.alignment.tf_1d.value
        ma_trend_map = {"up": "up", "down": "down", "flat": "flat"}

        resp = SignalResponse(
            chat_id=profile.telegram_chat_id,
            ticker=ticker,
            date=target_date.isoformat(),
            price=PricePoint(current=current, change_pct_24h=change_pct),
            saju=SajuSummary(
                composite=saju_resp.composite_score,
                grade=saju_resp.signal_grade,
            ),
            chart=ChartSummary(
                score=analysis.composite_score,
                rsi=analysis.rsi_1h,
                ma20=current,   # 하위호환 placeholder
                ma50=current,
                ma_trend=ma_trend_map.get(tf_1d_value, "flat"),  # type: ignore[arg-type]
                volume_ratio=analysis.volume_ratio_1d,
                reason=analysis.reason,
            ),
            composite_score=final,
            signal_grade=grade,
            best_hours=saju_resp.best_hours,
            market_status=market_status,
            analysis=analysis_summary,
        )

        self._redis_set(cache_key, resp)
        return resp

    # ─────────────────────────────────────────────
    # cache helpers
    # ─────────────────────────────────────────────

    def _redis_get(self, key: str) -> Optional[SignalResponse]:
        if self._redis is None:
            return None
        try:
            raw = self._redis.get(key)
        except Exception as e:
            logger.warning("signal cache GET 실패: %s", e)
            return None
        if raw is None:
            return None
        try:
            if isinstance(raw, (bytes, bytearray)):
                raw = raw.decode("utf-8")
            return SignalResponse(**json.loads(raw))
        except Exception as e:
            logger.warning("signal cache deserialize 실패: %s", e)
            return None

    def _redis_set(self, key: str, resp: SignalResponse) -> None:
        if self._redis is None:
            return
        try:
            self._redis.setex(key, _SIGNAL_TTL, resp.model_dump_json())
        except Exception as e:
            logger.warning("signal cache SET 실패: %s", e)

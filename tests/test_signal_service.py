"""signal_service: saju + chart 결합, Redis 캐시 검증."""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional

import fakeredis
import pytest

from sajucandle.cache import BaziCache
from sajucandle.cached_engine import CachedSajuEngine
from sajucandle.market.router import MarketRouter
from sajucandle.market_data import Kline, MarketDataUnavailable
from sajucandle.repositories import UserProfile
from sajucandle.score_service import ScoreService
from sajucandle.signal_service import SignalService, _grade_signal


def _profile() -> UserProfile:
    return UserProfile(
        telegram_chat_id=42,
        birth_year=1990, birth_month=3, birth_day=15,
        birth_hour=14, birth_minute=0,
        asset_class_pref="swing",
    )


def _make_klines(
    n: int = 100,
    base_close: float = 100.0,
    drift: float = 0.3,
) -> list[Kline]:
    """연속적으로 drift씩 오르는 Kline. 마지막 볼륨 스파이크."""
    out = []
    ts = datetime(2026, 2, 1, tzinfo=timezone.utc)
    one_day = 86400
    for i in range(n):
        c = base_close + i * drift
        out.append(
            Kline(
                open_time=datetime.fromtimestamp(ts.timestamp() + i * one_day, tz=timezone.utc),
                open=c - 0.1, high=c + 0.5, low=c - 0.5, close=c,
                volume=1000.0 if i < n - 1 else 2500.0,
            )
        )
    return out


class _FakeMarketClient:
    """BinanceClient 대체. interval별 다른 시리즈 지원."""

    def __init__(self, klines: Optional[list[Kline]] = None, raise_exc: Exception = None):
        self.klines = klines or _make_klines()
        self.raise_exc = raise_exc
        self.call_count = 0
        self.klines_by_interval: dict[str, list] = {}  # interval → klines

    def fetch_klines(self, symbol: str, interval: str = "1d", limit: int = 100):
        self.call_count += 1
        if self.raise_exc is not None:
            raise self.raise_exc
        if interval in self.klines_by_interval:
            return self.klines_by_interval[interval]
        return self.klines


def _make_fake_market_client(klines=None, raise_exc=None):
    """테스트용 fake provider. is_market_open=True, last_session_date=오늘 UTC."""
    fake = _FakeMarketClient(klines=klines, raise_exc=raise_exc)

    from datetime import datetime as _dt, timezone as _tz
    fake.is_market_open = lambda symbol: True
    fake.last_session_date = lambda symbol: _dt.now(_tz.utc).date()
    return fake


def _make_router(fake_client) -> MarketRouter:
    """_FakeMarketClient를 양쪽 슬롯에 꽂은 MarketRouter.

    테스트에서는 같은 fake로 양쪽 모두 반환.
    """
    return MarketRouter(binance=fake_client, yfinance=fake_client)


# ─────────────────────────────────────────────
# grade boundaries
# ─────────────────────────────────────────────

def _make_aligned_uptrend_analysis():
    """강진입_L 조건을 만족하는 aligned+uptrend+bullish+LONG AnalysisResult stub."""
    from unittest.mock import MagicMock
    from sajucandle.analysis.structure import MarketStructure

    a = MagicMock()
    a.alignment.aligned = True
    a.alignment.bias = "bullish"
    a.structure.state = MarketStructure.UPTREND
    a.direction = "LONG"
    return a


@pytest.mark.parametrize("score,expected", [
    (100, "강진입_L"), (75, "강진입_L"),
    (74, "진입_L"), (60, "진입_L"),
    (59, "관망"), (40, "관망"),
    (39, "관망"), (0, "관망"),   # Phase 2: "회피" 제거
])
def test_grade_boundaries(score, expected):
    analysis = _make_aligned_uptrend_analysis()
    assert _grade_signal(score, analysis) == expected


# ─────────────────────────────────────────────
# compute basic shape
# ─────────────────────────────────────────────

def test_compute_basic_response_shape():
    engine = CachedSajuEngine(cache=BaziCache(redis_client=None))
    score_svc = ScoreService(engine=engine, redis_client=None)
    market = _make_fake_market_client()
    svc = SignalService(
        score_service=score_svc, market_router=_make_router(market), redis_client=None
    )

    resp = svc.compute(_profile(), target_date=date(2026, 4, 16), ticker="BTCUSDT")
    assert resp.chat_id == 42
    assert resp.ticker == "BTCUSDT"
    assert resp.date == "2026-04-16"
    assert 0 <= resp.composite_score <= 100
    assert resp.signal_grade in {
        "강진입_L", "진입_L", "관망", "진입_S", "강진입_S",
    }
    assert 0 <= resp.saju.composite <= 100
    assert 0 <= resp.chart.score <= 100
    assert "RSI" in resp.chart.reason
    assert resp.price.current == market.klines[-1].close


# ─────────────────────────────────────────────
# cache behavior
# ─────────────────────────────────────────────

def test_compute_cache_hit_on_second_call():
    r = fakeredis.FakeRedis()
    engine = CachedSajuEngine(cache=BaziCache(redis_client=r))
    score_svc = ScoreService(engine=engine, redis_client=r)
    market = _make_fake_market_client()
    svc = SignalService(
        score_service=score_svc, market_router=_make_router(market), redis_client=r
    )

    r1 = svc.compute(_profile(), target_date=date(2026, 4, 16), ticker="BTCUSDT")
    first_calls = market.call_count
    assert first_calls == 3  # 1d + 4h + 1h 3개 TF fetch

    r2 = svc.compute(_profile(), target_date=date(2026, 4, 16), ticker="BTCUSDT")
    # 두 번째는 signal:* 캐시 히트 → market 호출 없음
    assert market.call_count == first_calls
    assert r1.model_dump() == r2.model_dump()

    # 캐시 키 포맷 확인
    keys = [k.decode() for k in r.keys("signal:*")]
    assert keys == ["signal:42:2026-04-16:BTCUSDT"]


def test_compute_cache_key_varies_by_ticker():
    r = fakeredis.FakeRedis()
    engine = CachedSajuEngine(cache=BaziCache(redis_client=r))
    score_svc = ScoreService(engine=engine, redis_client=r)
    market = _make_fake_market_client()
    svc = SignalService(
        score_service=score_svc, market_router=_make_router(market), redis_client=r
    )

    svc.compute(_profile(), target_date=date(2026, 4, 16), ticker="BTCUSDT")
    svc.compute(_profile(), target_date=date(2026, 4, 16), ticker="AAPL")

    keys = sorted(k.decode() for k in r.keys("signal:*"))
    assert keys == [
        "signal:42:2026-04-16:AAPL",
        "signal:42:2026-04-16:BTCUSDT",
    ]


def test_compute_without_redis_still_works():
    engine = CachedSajuEngine(cache=BaziCache(redis_client=None))
    score_svc = ScoreService(engine=engine, redis_client=None)
    market = _make_fake_market_client()
    svc = SignalService(
        score_service=score_svc, market_router=_make_router(market), redis_client=None
    )
    resp = svc.compute(_profile(), target_date=date(2026, 4, 16), ticker="BTCUSDT")
    assert resp.composite_score >= 0


# ─────────────────────────────────────────────
# weight verification
# ─────────────────────────────────────────────

class _FixedScoreService:
    """ScoreService 대체. 고정된 saju composite/grade 반환."""

    def __init__(self, composite: int, grade: str = "관망"):
        self._composite = composite
        self._grade = grade

    def compute(self, profile, target_date, asset_class):
        from sajucandle.models import AxisScore, HourRecommendation, SajuScoreResponse
        return SajuScoreResponse(
            chat_id=profile.telegram_chat_id,
            date=target_date.isoformat(),
            asset_class=asset_class,
            iljin="庚申",
            composite_score=self._composite,
            signal_grade=self._grade,
            axes={
                "wealth":     AxisScore(score=50, reason=""),
                "decision":   AxisScore(score=50, reason=""),
                "volatility": AxisScore(score=50, reason=""),
                "flow":       AxisScore(score=50, reason=""),
            },
            best_hours=[HourRecommendation(shichen="寅", time_range="03:00~05:00", multiplier=1.1)],
        )


def test_compute_final_weighting_saju_only():
    """saju=100, chart=analysis.composite_score → final = 0.1*100 + 0.9*analysis."""
    score_svc = _FixedScoreService(composite=100)
    market = _make_fake_market_client()
    svc = SignalService(
        score_service=score_svc, market_router=_make_router(market), redis_client=None
    )
    resp = svc.compute(_profile(), target_date=date(2026, 4, 16), ticker="BTCUSDT")
    # 0.1*100 + 0.9*analysis = 10 + 0.9*analysis. analysis >= 0 → final >= 10
    assert resp.composite_score >= 10


def test_compute_final_weighting_chart_dominant():
    """saju=0 → final = 0.1*0 + 0.9*analysis = round(0.9 * chart.score)."""
    score_svc = _FixedScoreService(composite=0)
    market = _make_fake_market_client()
    svc = SignalService(
        score_service=score_svc, market_router=_make_router(market), redis_client=None
    )
    resp = svc.compute(_profile(), target_date=date(2026, 4, 16), ticker="BTCUSDT")
    # chart.score == analysis.composite_score; final = round(0.9 * chart.score)
    expected = round(0.9 * resp.chart.score)
    assert resp.composite_score == expected


def test_compute_final_weighting_50_50():
    score_svc = _FixedScoreService(composite=50)
    market = _make_fake_market_client()
    svc = SignalService(
        score_service=score_svc, market_router=_make_router(market), redis_client=None
    )
    resp = svc.compute(_profile(), target_date=date(2026, 4, 16), ticker="BTCUSDT")
    # final = round(0.1*50 + 0.9*analysis) = round(5 + 0.9*chart.score)
    expected = round(0.1 * 50 + 0.9 * resp.chart.score)
    assert resp.composite_score == expected


# ─────────────────────────────────────────────
# market data failure propagates
# ─────────────────────────────────────────────

def test_compute_propagates_market_data_unavailable():
    score_svc = _FixedScoreService(composite=50)
    market = _make_fake_market_client(raise_exc=MarketDataUnavailable("boom"))
    svc = SignalService(
        score_service=score_svc, market_router=_make_router(market), redis_client=None
    )
    with pytest.raises(MarketDataUnavailable):
        svc.compute(_profile(), target_date=date(2026, 4, 16), ticker="BTCUSDT")


def test_signal_compute_populates_market_status():
    """compute 결과에 market_status 필드가 채워진다."""
    fake = _make_fake_market_client()
    cache = BaziCache(redis_client=fakeredis.FakeStrictRedis())
    engine = CachedSajuEngine(cache=cache)
    score_svc = ScoreService(engine=engine, redis_client=None)

    svc = SignalService(
        score_service=score_svc,
        market_router=_make_router(fake),
    )
    resp = svc.compute(_profile(), date(2026, 4, 16), "BTCUSDT")
    assert resp.market_status.is_open is True
    assert resp.market_status.category in ("crypto", "us_stock")
    assert len(resp.market_status.last_session_date) == 10


# ─────────────────────────────────────────────
# Week 8: 가중치 재조정 + grade_signal 추가조건 + analysis 필드
# ─────────────────────────────────────────────


def _make_score_service():
    """실제 ScoreService (CachedSajuEngine 기반, redis=None)."""
    cache = BaziCache(redis_client=None)
    engine = CachedSajuEngine(cache=cache)
    return ScoreService(engine=engine, redis_client=None)


def _make_score_service_with_fixed_composite(composite: int):
    """테스트용 ScoreService. 어떤 입력이든 지정된 composite 반환."""
    from unittest.mock import MagicMock
    from sajucandle.models import AxisScore, SajuScoreResponse

    svc = MagicMock()
    def fake_compute(profile, target_date, asset_class):
        return SajuScoreResponse(
            chat_id=profile.telegram_chat_id,
            date=target_date.isoformat(),
            asset_class=asset_class,
            iljin="庚申",
            composite_score=composite,
            signal_grade="진입" if composite >= 60 else "관망",
            axes={
                "wealth": AxisScore(score=composite, reason=""),
                "decision": AxisScore(score=composite, reason=""),
                "volatility": AxisScore(score=composite, reason=""),
                "flow": AxisScore(score=composite, reason=""),
            },
            best_hours=[],
        )
    svc.compute = fake_compute
    return svc


def test_week8_analysis_field_populated():
    """SignalResponse.analysis 필드가 채워짐."""
    fake = _make_fake_market_client()
    score_svc = _make_score_service()
    svc = SignalService(
        score_service=score_svc,
        market_router=_make_router(fake),
    )
    resp = svc.compute(_profile(), date(2026, 4, 16), "BTCUSDT")
    assert resp.analysis is not None
    assert resp.analysis.structure.state in (
        "uptrend", "downtrend", "range", "breakout", "breakdown"
    )
    assert resp.analysis.alignment.tf_1d in ("up", "down", "flat")
    assert 0 <= resp.analysis.composite_score <= 100


def test_week8_chart_field_backward_compat():
    """기존 chart 필드는 analysis 값으로 채워짐."""
    fake = _make_fake_market_client()
    score_svc = _make_score_service()
    svc = SignalService(
        score_service=score_svc,
        market_router=_make_router(fake),
    )
    resp = svc.compute(_profile(), date(2026, 4, 16), "BTCUSDT")
    assert resp.chart is not None
    assert resp.chart.score == resp.analysis.composite_score


def test_week8_strong_grade_requires_aligned_and_uptrend():
    """점수만 75+ 해도 aligned=False면 '진입' 이하."""
    # mixed TF: 1h up / 4h flat / 1d down → aligned=False
    fake = _make_fake_market_client()
    up = _make_klines(n=200, base_close=100.0, drift=0.5)
    flat = _make_klines(n=200, base_close=100.0, drift=0.0)
    dn = _make_klines(n=200, base_close=150.0, drift=-0.3)
    fake.klines_by_interval = {"1h": up, "4h": flat, "1d": dn}
    score_svc = _make_score_service_with_fixed_composite(80)
    svc = SignalService(
        score_service=score_svc,
        market_router=_make_router(fake),
    )
    resp = svc.compute(_profile(), date(2026, 4, 16), "BTCUSDT")
    assert resp.signal_grade != "강진입"


def test_week8_weights_01_09():
    """새 가중치: 0.1 saju + 0.9 analysis."""
    fake = _make_fake_market_client()
    # 강한 상승 데이터로 analysis 점수 높게
    strong_up = _make_klines(n=200, base_close=100.0, drift=0.5)
    fake.klines_by_interval = {"1h": strong_up, "4h": strong_up, "1d": strong_up}
    score_svc = _make_score_service_with_fixed_composite(40)   # 사주=40
    svc = SignalService(
        score_service=score_svc,
        market_router=_make_router(fake),
    )
    resp = svc.compute(_profile(), date(2026, 4, 16), "BTCUSDT")
    # composite = round(0.1*40 + 0.9*analysis) — analysis 60~90 예상 → composite 58~85
    assert 55 <= resp.composite_score <= 90


# ─────────────────────────────────────────────
# Week 9: TradeSetup 조건부 생성
# ─────────────────────────────────────────────


def test_week9_trade_setup_on_entry_grade():
    """'진입'/'강진입' 등급일 때 trade_setup 채워짐."""
    fake = _make_fake_market_client()
    strong = _make_klines(n=200, base_close=100.0, drift=0.5)
    fake.klines_by_interval = {"1h": strong, "4h": strong, "1d": strong}
    score_svc = _make_score_service()
    svc = SignalService(
        score_service=score_svc,
        market_router=_make_router(fake),
    )
    resp = svc.compute(_profile(), date(2026, 4, 16), "BTCUSDT")
    if resp.signal_grade in ("강진입", "진입"):
        assert resp.analysis is not None
        assert resp.analysis.trade_setup is not None
        ts = resp.analysis.trade_setup
        assert ts.entry > 0
        assert ts.stop_loss < ts.entry
        assert ts.take_profit_1 > ts.entry
        assert ts.risk_pct > 0
        assert ts.sl_basis in ("atr", "sr_snap")


def test_week9_trade_setup_none_on_lower_grade():
    """'관망'/'회피'에서는 trade_setup=None."""
    fake = _make_fake_market_client()
    flat = _make_klines(n=200, base_close=100.0, drift=0.0)
    fake.klines_by_interval = {"1h": flat, "4h": flat, "1d": flat}
    score_svc = _make_score_service_with_fixed_composite(30)
    svc = SignalService(
        score_service=score_svc,
        market_router=_make_router(fake),
    )
    resp = svc.compute(_profile(), date(2026, 4, 16), "BTCUSDT")
    if resp.signal_grade in ("관망", "회피"):
        assert resp.analysis is not None
        assert resp.analysis.trade_setup is None


def test_week9_sr_levels_always_in_response():
    """sr_levels는 등급 무관 list (빈 리스트 가능)."""
    fake = _make_fake_market_client()
    score_svc = _make_score_service()
    svc = SignalService(
        score_service=score_svc,
        market_router=_make_router(fake),
    )
    resp = svc.compute(_profile(), date(2026, 4, 16), "BTCUSDT")
    assert resp.analysis is not None
    assert isinstance(resp.analysis.sr_levels, list)


# ─────────────────────────────────────────────
# Week 10 Phase 2: DOWNTREND/BREAKDOWN 진입 차단
# ─────────────────────────────────────────────


def test_week10_downtrend_with_short_direction_is_short_entry():
    """Phase 2: DOWNTREND + SHORT direction → 진입_S (숏 진입)."""
    from sajucandle.analysis.composite import AnalysisResult
    from sajucandle.analysis.structure import MarketStructure, StructureAnalysis
    from sajucandle.analysis.multi_timeframe import Alignment
    from sajucandle.analysis.timeframe import TrendDirection
    from sajucandle.signal_service import _grade_signal

    analysis = AnalysisResult(
        structure=StructureAnalysis(
            state=MarketStructure.DOWNTREND,
            last_high=None, last_low=None, score=20,
            long_score=20, short_score=80,
        ),
        alignment=Alignment(
            tf_1h=TrendDirection.DOWN, tf_4h=TrendDirection.DOWN,
            tf_1d=TrendDirection.DOWN, aligned=True,
            bias="bearish", score=10,
            long_score=10, short_score=90,
        ),
        rsi_1h=40.0, volume_ratio_1d=1.0,
        composite_score=65, reason="...",
        long_score=25, short_score=65,
        direction="SHORT",
    )
    assert _grade_signal(65, analysis) == "진입_S"


def test_week10_breakdown_with_short_direction_is_short_entry():
    """BREAKDOWN + SHORT direction → 진입_S."""
    from sajucandle.analysis.composite import AnalysisResult
    from sajucandle.analysis.structure import MarketStructure, StructureAnalysis
    from sajucandle.analysis.multi_timeframe import Alignment
    from sajucandle.analysis.timeframe import TrendDirection
    from sajucandle.signal_service import _grade_signal

    analysis = AnalysisResult(
        structure=StructureAnalysis(
            state=MarketStructure.BREAKDOWN,
            last_high=None, last_low=None, score=30,
            long_score=30, short_score=70,
        ),
        alignment=Alignment(
            tf_1h=TrendDirection.DOWN, tf_4h=TrendDirection.FLAT,
            tf_1d=TrendDirection.UP, aligned=False,
            bias="mixed", score=50,
            long_score=50, short_score=50,
        ),
        rsi_1h=55.0, volume_ratio_1d=1.2,
        composite_score=68, reason="...",
        long_score=40, short_score=68,
        direction="SHORT",
    )
    assert _grade_signal(68, analysis) == "진입_S"


def test_week10_uptrend_long_entry_stays_entry_long():
    """UPTREND + score 65는 '진입_L' 유지 (회귀 확인)."""
    from sajucandle.analysis.composite import AnalysisResult
    from sajucandle.analysis.structure import MarketStructure, StructureAnalysis
    from sajucandle.analysis.multi_timeframe import Alignment
    from sajucandle.analysis.timeframe import TrendDirection
    from sajucandle.signal_service import _grade_signal

    analysis = AnalysisResult(
        structure=StructureAnalysis(
            state=MarketStructure.UPTREND,
            last_high=None, last_low=None, score=70,
            long_score=70, short_score=20,
        ),
        alignment=Alignment(
            tf_1h=TrendDirection.UP, tf_4h=TrendDirection.UP,
            tf_1d=TrendDirection.UP, aligned=True,
            bias="bullish", score=90,
            long_score=90, short_score=10,
        ),
        rsi_1h=45.0, volume_ratio_1d=1.3,
        composite_score=65, reason="...",
        long_score=65, short_score=20,
        direction="LONG",
    )
    assert _grade_signal(65, analysis) == "진입_L"


def test_week10_range_forces_neutral():
    """Phase 2: RANGE 구조는 direction/score 무관 관망 강제."""
    from sajucandle.analysis.composite import AnalysisResult
    from sajucandle.analysis.structure import MarketStructure, StructureAnalysis
    from sajucandle.analysis.multi_timeframe import Alignment
    from sajucandle.analysis.timeframe import TrendDirection
    from sajucandle.signal_service import _grade_signal

    analysis = AnalysisResult(
        structure=StructureAnalysis(
            state=MarketStructure.RANGE,
            last_high=None, last_low=None, score=50,
            long_score=50, short_score=50,
        ),
        alignment=Alignment(
            tf_1h=TrendDirection.FLAT, tf_4h=TrendDirection.UP,
            tf_1d=TrendDirection.FLAT, aligned=False,
            bias="bullish", score=60,
            long_score=60, short_score=40,
        ),
        rsi_1h=50.0, volume_ratio_1d=1.0,
        composite_score=62, reason="...",
        long_score=55, short_score=45,
        direction="LONG",   # RANGE면 direction 무시
    )
    assert _grade_signal(62, analysis) == "관망"


# ─────────────────────────────────────────────
# Phase 2: 5등급 + direction 조합
# ─────────────────────────────────────────────


def _make_analysis(
    state,
    direction,
    bias="bullish",
    aligned=True,
    long_score=70,
    short_score=20,
):
    from sajucandle.analysis.composite import AnalysisResult
    from sajucandle.analysis.structure import StructureAnalysis
    from sajucandle.analysis.multi_timeframe import Alignment
    from sajucandle.analysis.timeframe import TrendDirection

    return AnalysisResult(
        structure=StructureAnalysis(
            state=state, last_high=None, last_low=None,
            score=long_score, long_score=long_score, short_score=short_score,
        ),
        alignment=Alignment(
            tf_1h=TrendDirection.UP, tf_4h=TrendDirection.UP,
            tf_1d=TrendDirection.UP, aligned=aligned, bias=bias,
            score=long_score, long_score=long_score, short_score=short_score,
        ),
        rsi_1h=50.0, volume_ratio_1d=1.0,
        composite_score=max(long_score, short_score), reason="...",
        long_score=long_score, short_score=short_score,
        direction=direction,
    )


def test_phase2_strong_long_grade():
    from sajucandle.analysis.structure import MarketStructure
    from sajucandle.signal_service import _grade_signal

    a = _make_analysis(
        state=MarketStructure.UPTREND, direction="LONG",
        bias="bullish", aligned=True,
        long_score=85, short_score=15,
    )
    assert _grade_signal(85, a) == "강진입_L"


def test_phase2_strong_short_grade():
    from sajucandle.analysis.structure import MarketStructure
    from sajucandle.signal_service import _grade_signal

    a = _make_analysis(
        state=MarketStructure.DOWNTREND, direction="SHORT",
        bias="bearish", aligned=True,
        long_score=15, short_score=85,
    )
    assert _grade_signal(85, a) == "강진입_S"


def test_phase2_long_entry_fallback_when_not_aligned():
    """LONG + score≥75 이지만 aligned=False → 강진입_L 조건 미충족 → 진입_L."""
    from sajucandle.analysis.structure import MarketStructure
    from sajucandle.signal_service import _grade_signal

    a = _make_analysis(
        state=MarketStructure.UPTREND, direction="LONG",
        bias="bullish", aligned=False,
        long_score=78, short_score=20,
    )
    assert _grade_signal(78, a) == "진입_L"


def test_phase2_short_entry_fallback_when_breakout_not_breakdown():
    """SHORT + score≥75 + bullish bias → 강진입_S 조건 미충족 → 진입_S."""
    from sajucandle.analysis.structure import MarketStructure
    from sajucandle.signal_service import _grade_signal

    a = _make_analysis(
        state=MarketStructure.BREAKDOWN, direction="SHORT",
        bias="mixed", aligned=False,    # 조건 불충족
        long_score=25, short_score=80,
    )
    assert _grade_signal(80, a) == "진입_S"


def test_phase2_neutral_direction_always_gwanmang():
    from sajucandle.analysis.structure import MarketStructure
    from sajucandle.signal_service import _grade_signal

    a = _make_analysis(
        state=MarketStructure.UPTREND, direction="NEUTRAL",
        long_score=72, short_score=68,
    )
    assert _grade_signal(72, a) == "관망"


def test_phase2_no_avoid_grade_returned():
    """'회피' 등급이 절대 반환되지 않음 (invariant)."""
    from sajucandle.analysis.structure import MarketStructure
    from sajucandle.signal_service import _grade_signal

    for state in [
        MarketStructure.UPTREND,
        MarketStructure.DOWNTREND,
        MarketStructure.RANGE,
        MarketStructure.BREAKOUT,
        MarketStructure.BREAKDOWN,
    ]:
        for direction in ("LONG", "SHORT", "NEUTRAL"):
            for score in (0, 30, 59, 60, 74, 75, 100):
                a = _make_analysis(
                    state=state, direction=direction,
                    long_score=score if direction != "SHORT" else 100 - score,
                    short_score=score if direction == "SHORT" else 100 - score,
                )
                grade = _grade_signal(score, a)
                assert grade != "회피"
                assert grade in {
                    "강진입_L", "진입_L", "관망", "진입_S", "강진입_S",
                }


def test_phase2_short_trade_setup_direction_propagated():
    """compute 내부: SHORT 등급 → TradeSetup.direction=SHORT."""
    from sajucandle.signal_service import SignalService
    from unittest.mock import MagicMock

    # 숏 시나리오 합성 히스토리 (하락)
    dn_1h = [100 - i * 0.2 for i in range(200)]
    dn_4h = [100 - i * 0.3 for i in range(100)]
    dn_1d = [100 - i * 0.5 for i in range(100)]

    def _klines_from(closes):
        return [
            Kline(
                open_time=datetime(2026, 2, 1, tzinfo=timezone.utc),
                open=c, high=c + 0.5, low=c - 0.5, close=c,
                volume=1000.0,
            )
            for c in closes
        ]

    fake = MagicMock()
    fake.fetch_klines = lambda s, interval, limit: (
        _klines_from(dn_1d) if interval == "1d"
        else _klines_from(dn_4h) if interval == "4h"
        else _klines_from(dn_1h)
    )
    fake.is_market_open = lambda s: True
    fake.last_session_date = lambda s: date(2026, 4, 16)
    router = MarketRouter(binance=fake, yfinance=fake)

    engine = CachedSajuEngine(cache=BaziCache(redis_client=None))
    score_svc = ScoreService(engine=engine, redis_client=None)
    svc = SignalService(score_service=score_svc, market_router=router, redis_client=None)

    resp = svc.compute(_profile(), date(2026, 4, 16), "BTCUSDT")
    # 하락장에서 숏 direction + 진입_S or 강진입_S 기대
    assert resp.analysis is not None
    if resp.signal_grade in ("진입_S", "강진입_S"):
        assert resp.analysis.direction == "SHORT"
        assert resp.analysis.trade_setup is not None
        assert resp.analysis.trade_setup.direction == "SHORT"
        assert resp.analysis.trade_setup.stop_loss > resp.analysis.trade_setup.entry
        assert (
            resp.analysis.trade_setup.take_profit_1 < resp.analysis.trade_setup.entry
        )

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
    """강진입 조건을 만족하는 aligned+uptrend AnalysisResult stub."""
    from unittest.mock import MagicMock
    from sajucandle.analysis.structure import MarketStructure

    a = MagicMock()
    a.alignment.aligned = True
    a.structure.state = MarketStructure.UPTREND
    return a


@pytest.mark.parametrize("score,expected", [
    (100, "강진입"), (75, "강진입"),
    (74, "진입"), (60, "진입"),
    (59, "관망"), (40, "관망"),
    (39, "회피"), (0, "회피"),
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
    assert resp.signal_grade in {"강진입", "진입", "관망", "회피"}
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

"""tech_analysis: RSI/MA/volume + score_chart 순수 함수 테스트."""
from __future__ import annotations

import pytest

from sajucandle.tech_analysis import (
    ChartScoreBreakdown,
    _rsi_score,
    _rsi_score_short,
    rsi,
    score_chart,
    sma,
    volume_ratio,
)


# ─────────────────────────────────────────────
# SMA
# ─────────────────────────────────────────────

def test_sma_simple():
    assert sma([1, 2, 3, 4, 5], period=3) == 4.0


def test_sma_full_range():
    assert sma([10, 20, 30], period=3) == 20.0


def test_sma_insufficient_data_raises():
    with pytest.raises(ValueError):
        sma([1.0, 2.0], period=3)


def test_sma_invalid_period():
    with pytest.raises(ValueError):
        sma([1.0, 2.0, 3.0], period=0)


# ─────────────────────────────────────────────
# RSI
# ─────────────────────────────────────────────

def test_rsi_monotonic_up_near_100():
    # 15개 연속 상승 → RSI ≈ 100
    closes = [float(i) for i in range(1, 16)]  # 1..15
    assert rsi(closes, period=14) >= 99.0


def test_rsi_monotonic_down_near_zero():
    closes = [float(i) for i in range(15, 0, -1)]  # 15..1
    assert rsi(closes, period=14) <= 1.0


def test_rsi_flat_returns_50ish():
    # 가격 변화 0 → avg_gain=avg_loss=0 → 코드상 50 반환
    closes = [100.0] * 15
    val = rsi(closes, period=14)
    assert val == 50.0


def test_rsi_insufficient_data_raises():
    with pytest.raises(ValueError):
        rsi([1.0] * 14, period=14)  # period+1 = 15 필요


def test_rsi_known_mixed_sequence():
    # 실제 계산: 15개 closes, 상승/하락 섞임. 중립 ~ 50 근처 기대.
    closes = [
        100, 102, 101, 103, 102,
        104, 103, 105, 104, 106,
        105, 107, 106, 108, 107,
    ]
    val = rsi(closes, period=14)
    # 대략 60~70 사이일 것 (상승 압력 약간 우위)
    assert 40 < val < 80


# ─────────────────────────────────────────────
# volume_ratio
# ─────────────────────────────────────────────

def test_volume_ratio_spike():
    # 지난 20일 평균 10, 오늘 20 → ratio 2.0
    volumes = [10.0] * 20 + [20.0]
    assert volume_ratio(volumes, lookback=20) == pytest.approx(2.0)


def test_volume_ratio_drop():
    volumes = [10.0] * 20 + [5.0]
    assert volume_ratio(volumes, lookback=20) == pytest.approx(0.5)


def test_volume_ratio_flat():
    volumes = [100.0] * 21
    assert volume_ratio(volumes, lookback=20) == pytest.approx(1.0)


def test_volume_ratio_insufficient_data():
    with pytest.raises(ValueError):
        volume_ratio([1.0] * 20, lookback=20)  # lookback+1 = 21 필요


def test_volume_ratio_zero_past_avg_returns_neutral():
    # 과거 전부 0이면 1.0 (무의미 구간, 중립 처리)
    volumes = [0.0] * 20 + [50.0]
    assert volume_ratio(volumes, lookback=20) == 1.0


# ─────────────────────────────────────────────
# score_chart
# ─────────────────────────────────────────────

def _make_bullish_series():
    """건강한 상승 setup: MA20>MA50(상승세) + RSI 중립(pullback 후 반등) + 볼륨 스파이크."""
    # 40일 완만 상승 → uptrend 확립 (MA50이 낮은 구간까지 포함)
    closes = [100.0 + i * 0.5 for i in range(40)]  # 100 → 119.5
    # 10일 pullback: 연속 하락으로 RSI를 중립 이하로 끌어내림
    for _ in range(10):
        closes.append(closes[-1] - 0.8)
    # 5일 bounce 시작
    for _ in range(5):
        closes.append(closes[-1] + 0.3)
    # 55개. MA20(최근 20일)은 pullback+bounce로 완만, MA50은 전체 저점 포함 낮음
    # → MA20 > MA50 유지되어 trend="up"
    volumes = [100.0] * 54 + [250.0]  # 오늘 볼륨 스파이크
    return closes, volumes


def _make_bearish_series():
    """RSI 높음(과매수) + MA20<MA50 + 볼륨 빈약."""
    # 50일간 완만 하락 → MA20<MA50. 최근 급등 → RSI 높게.
    closes = [200.0 - i * 1.0 for i in range(50)]  # 200→151
    closes += [closes[-1] + 3.0, closes[-1] + 4.0, closes[-1] + 5.0]  # 급등
    closes += [closes[-1] + 2.0, closes[-1] + 1.0]
    volumes = [100.0] * 54 + [30.0]  # 오늘 볼륨 빈약
    return closes, volumes


def _make_neutral_series():
    """RSI ~50 + MA flat + volume_ratio ~1."""
    closes = [100.0 + (i % 2) * 0.1 for i in range(55)]  # 100, 100.1 반복
    volumes = [100.0] * 55
    return closes, volumes


def test_score_chart_bullish():
    closes, volumes = _make_bullish_series()
    b = score_chart(closes, volumes)
    assert isinstance(b, ChartScoreBreakdown)
    assert b.ma_trend == "up"
    assert b.score >= 55  # 상승 추세 + 볼륨 스파이크
    assert b.volume_ratio_value >= 1.5


def test_score_chart_bearish():
    closes, volumes = _make_bearish_series()
    b = score_chart(closes, volumes)
    assert b.ma_trend == "down"
    assert b.score <= 45
    assert b.volume_ratio_value < 0.5


def test_score_chart_neutral_flat():
    closes, volumes = _make_neutral_series()
    b = score_chart(closes, volumes)
    # 거의 평평: RSI ~50, MA ratio ~1, vol ratio ~1
    # 예상: 0.4*50 + 0.4*50 + 0.2*55 = 51
    assert 45 <= b.score <= 60
    assert b.ma_trend == "flat"


def test_score_chart_returns_bounded_score():
    """여러 시나리오 돌려서 score가 0~100 안에 있는지."""
    for closes, volumes in (
        _make_bullish_series(),
        _make_bearish_series(),
        _make_neutral_series(),
    ):
        b = score_chart(closes, volumes)
        assert 0 <= b.score <= 100


def test_score_chart_reason_has_rsi_and_trend():
    closes, volumes = _make_bullish_series()
    b = score_chart(closes, volumes)
    assert "RSI" in b.reason
    assert "MA20" in b.reason  # "MA20>MA50" 등
    assert "볼륨" in b.reason


def test_score_chart_insufficient_closes_raises():
    with pytest.raises(ValueError):
        score_chart([100.0] * 30, [50.0] * 30)  # closes < 50


def test_score_chart_insufficient_volumes_raises():
    with pytest.raises(ValueError):
        score_chart([100.0] * 55, [50.0] * 15)  # volumes < 21


# ─────────────────────────────────────────────
# Phase 2: _rsi_score_short 대칭
# ─────────────────────────────────────────────

def test_rsi_score_short_oversold_low():
    # RSI 20 (과매도) → 숏 관점에서 불리 → 20
    assert _rsi_score_short(20) == 20
    assert _rsi_score_short(29.9) == 20


def test_rsi_score_short_weak_low():
    # 30~44 구간
    assert _rsi_score_short(30) == 40
    assert _rsi_score_short(44.9) == 40


def test_rsi_score_short_neutral():
    # 45~54 구간
    assert _rsi_score_short(45) == 50
    assert _rsi_score_short(50) == 50
    assert _rsi_score_short(54.9) == 50


def test_rsi_score_short_weak_high():
    # 55~69 구간
    assert _rsi_score_short(55) == 55
    assert _rsi_score_short(69.9) == 55


def test_rsi_score_short_overbought():
    # 과매수(높은 RSI) → 숏 가점 → 70
    assert _rsi_score_short(70) == 70
    assert _rsi_score_short(80) == 70
    assert _rsi_score_short(100) == 70


def test_rsi_score_long_short_complementary():
    """대칭 sanity: extreme에서 반대 방향 스코어."""
    # 과매도: 롱 가점 70, 숏 감점 20
    assert _rsi_score(25) == 70
    assert _rsi_score_short(25) == 20
    # 과매수: 롱 감점 20, 숏 가점 70
    assert _rsi_score(80) == 20
    assert _rsi_score_short(80) == 70
    # 중립: 둘 다 50
    assert _rsi_score(50) == 50
    assert _rsi_score_short(50) == 50

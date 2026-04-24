"""Macro Score (주식용).

PRD §5-1 구성 (100점):
  Fed 금리 / 2Y-10Y 스프레드     20
  DXY 추세                        15
  VIX 수준·추세                   20
  CPI YoY 방향                    15
  섹터 RS (AI·에너지·유틸·방어)   30

데이터 소스:
- FRED (무료): 금리·수익률곡선·DXY·VIX·CPI
- yfinance: 섹터 ETF 가격 (XLK·XLE·XLU·XLP)

키 포인트:
- FRED는 pandas_datareader로 접근 (API key 불필요)
- 네트워크 접근 실패 시 폴백: 50점(중립)
- 장기 캐싱은 별도 레이어 (price_data.py 참조)

PRD §5-1 주식 섹터 오행 매핑 (참고):
  AI/Tech  → 火   Technology(XLK), Semi(SOXX)
  Energy   → 金   Energy(XLE)
  Utilities→ 水   Utilities(XLU)
  Defensive→ 土   Consumer Staples(XLP)
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict, Optional

import numpy as np
import pandas as pd


# 주요 섹터 ETF
SECTOR_ETFS = {
    "Technology": "XLK",
    "Semiconductor": "SOXX",
    "Energy": "XLE",
    "Utilities": "XLU",
    "Consumer Staples": "XLP",
    "Financials": "XLF",
    "Healthcare": "XLV",
    "Industrials": "XLI",
    "Materials": "XLB",
    "Real Estate": "XLRE",
    "Consumer Discretionary": "XLY",
    "Communication": "XLC",
}


def _fetch_fred(series_id: str, start: datetime, end: datetime,
                timeout: float = 60, retries: int = 3) -> pd.Series:
    """FRED 시리즈를 pandas Series로 반환. 실패 시 빈 시리즈.

    FRED 공개 CSV URL (API key 불필요):
      https://fred.stlouisfed.org/graph/fredgraph.csv?id=<series_id>

    서버가 종종 느려 타임아웃/재시도 적용.
    """
    import io
    import time
    import requests
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    for attempt in range(retries):
        try:
            r = requests.get(url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
            r.raise_for_status()
            df = pd.read_csv(io.StringIO(r.text))
            date_col = "DATE" if "DATE" in df.columns else df.columns[0]
            val_col = series_id if series_id in df.columns else df.columns[-1]
            df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
            df = df.dropna(subset=[date_col])
            df[val_col] = pd.to_numeric(df[val_col], errors="coerce")
            df = df.dropna(subset=[val_col]).set_index(date_col)
            s = df[val_col]
            mask = (s.index >= pd.Timestamp(start)) & (s.index <= pd.Timestamp(end))
            return s[mask]
        except Exception:
            if attempt < retries - 1:
                time.sleep(2 ** attempt)  # 1s, 2s, 4s
                continue
    return pd.Series(dtype=float)


def _fetch_yf(symbol: str, start: datetime, end: datetime) -> pd.Series:
    """yfinance로 종가 Series 반환. 실패 시 빈 시리즈."""
    try:
        import yfinance as yf
        df = yf.download(symbol, start=start.strftime("%Y-%m-%d"),
                         end=(end + timedelta(days=1)).strftime("%Y-%m-%d"),
                         interval="1d", progress=False, auto_adjust=True)
        if df.empty:
            return pd.Series(dtype=float)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return df["Close"].dropna()
    except Exception:
        return pd.Series(dtype=float)


def _score_yield_curve(start: datetime, end: datetime) -> float:
    """2Y-10Y 스프레드 점수.

    - 플러스(+) : 정상 → 100
    - 0 근처   : 중립 → 50
    - 역전(-0.5% 이하) : 경기침체 신호 → 20
    """
    s = _fetch_fred("T10Y2Y", start, end)
    if s.empty:
        return 50.0
    val = float(s.iloc[-1])
    if val >= 0.5: return 100.0
    if val >= 0.0: return 80.0
    if val >= -0.5: return 40.0
    return 20.0


def _score_dxy(start: datetime, end: datetime) -> float:
    """DXY(달러 인덱스) 추세 점수.

    - 강달러 상승 추세: 위험자산에 역풍 → 30
    - 횡보 : 중립 → 50
    - 약달러 추세 : 위험자산 우호 → 80

    소스: yfinance DX-Y.NYB (ICE US Dollar Index) 우선, 실패 시 FRED DTWEXBGS.
    """
    s = _fetch_yf("DX-Y.NYB", start, end)
    if s.empty:
        s = _fetch_fred("DTWEXBGS", start, end)
    if s.empty or len(s) < 30:
        return 50.0
    # 최근 20일 평균 vs 90일 전 평균
    recent = s.iloc[-20:].mean()
    past = s.iloc[-90:-70].mean() if len(s) >= 90 else s.iloc[:20].mean()
    change = (recent - past) / past * 100 if past != 0 else 0
    if change >= 2.0: return 30.0
    if change <= -2.0: return 80.0
    return 50.0 + max(-20, min(20, -change * 10))


def _score_vix(start: datetime, end: datetime) -> float:
    """VIX 수준·추세 점수.

    - <15 : 매우 낮음(안정) → 90
    - 15~20: 정상 → 80
    - 20~30: 긴장 → 50
    - >30 : 공포 → 20
    킬스위치: >40이면 별도 처리(호출자가 감지)

    소스: yfinance ^VIX 우선, 실패 시 FRED VIXCLS.
    """
    s = _fetch_yf("^VIX", start, end)
    if s.empty:
        s = _fetch_fred("VIXCLS", start, end)
    if s.empty:
        return 50.0
    val = float(s.iloc[-1])
    if val < 15: return 90.0
    if val < 20: return 80.0
    if val < 25: return 60.0
    if val < 30: return 40.0
    if val < 40: return 25.0
    return 10.0


def _score_cpi(start: datetime, end: datetime) -> float:
    """CPI YoY 방향 점수.

    - 하락 추세 (연준 완화 기대): 80
    - 안정 2~3%: 70
    - 상승 추세: 30~50
    - 재급등: 20
    """
    s = _fetch_fred("CPIAUCSL", start, end)
    if s.empty or len(s) < 24:
        return 50.0
    # YoY 계산
    yoy = s.pct_change(12) * 100
    yoy = yoy.dropna()
    if yoy.empty:
        return 50.0
    latest = float(yoy.iloc[-1])
    # 추세: 최근 3개월 변화
    recent3 = yoy.iloc[-3:].mean() if len(yoy) >= 3 else latest
    past3 = yoy.iloc[-6:-3].mean() if len(yoy) >= 6 else latest
    trend = recent3 - past3
    base = 50.0
    if 2 <= latest <= 3: base = 70
    elif 1 <= latest < 2: base = 80
    elif latest < 1: base = 60  # 디플레 우려
    elif 3 < latest <= 5: base = 40
    else: base = 20
    # 추세 보정
    if trend < -0.3: base += 10
    elif trend > 0.3: base -= 10
    return max(0.0, min(100.0, base))


def _score_sector_rs(start: datetime, end: datetime) -> float:
    """섹터 RS: Technology/Energy/Utilities/Consumer Staples의 최근 60일 성과 평균.

    벤치: SPY.
    플러스 높은 섹터 다수면 상승 국면 → 점수↑
    """
    from .price_data import get_ohlcv
    try:
        spy = get_ohlcv("SPY", "stock", start, end)
        if spy.empty or len(spy) < 60:
            return 50.0
        spy_ret = spy["close"].iloc[-1] / spy["close"].iloc[-60] - 1
        rs_scores = []
        for name in ["XLK", "XLE", "XLU", "XLP", "XLF", "XLI"]:
            df = get_ohlcv(name, "stock", start, end)
            if df.empty or len(df) < 60:
                continue
            r = df["close"].iloc[-1] / df["close"].iloc[-60] - 1
            rs_scores.append((1 + r) / (1 + spy_ret))
        if not rs_scores:
            return 50.0
        avg_rs = float(np.mean(rs_scores))
        # 1.1 이상 → 90, 1.0 → 50, 0.9 이하 → 20
        if avg_rs >= 1.1: return 90.0
        if avg_rs <= 0.9: return 20.0
        return (avg_rs - 0.9) / 0.2 * 70 + 20
    except Exception:
        return 50.0


def macro_score_stock(asof: Optional[datetime] = None) -> Dict:
    """주식 Macro Score (100점 만점).

    Parameters
    ----------
    asof : datetime | None
        평가 기준 시각. 기본 = 오늘.
    """
    if asof is None:
        asof = datetime.utcnow()
    # 각 지표 lookback 다름
    long_start = asof - timedelta(days=730)   # 2년
    mid_start = asof - timedelta(days=365)    # 1년

    breakdown = {
        "yield_curve": _score_yield_curve(long_start, asof),
        "dxy_trend": _score_dxy(mid_start, asof),
        "vix": _score_vix(mid_start, asof),
        "cpi": _score_cpi(long_start, asof),
        "sector_rs": _score_sector_rs(mid_start, asof),
    }
    weights = {
        "yield_curve": 20,
        "dxy_trend": 15,
        "vix": 20,
        "cpi": 15,
        "sector_rs": 30,
    }
    total = sum(breakdown[k] / 100 * w for k, w in weights.items())
    return {
        "total": round(total, 1),
        "breakdown": {k: round(v, 1) for k, v in breakdown.items()},
        "weights": weights,
        "asof": asof.isoformat(),
    }

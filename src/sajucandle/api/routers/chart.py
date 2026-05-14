"""차트 라우터 — /api/chart/ohlcv, /api/chart/analysis."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from sajucandle.manseryeok.core import get_saju_calculator
from sajucandle.quant.price_data import get_ohlcv
from sajucandle.quant.technical import ta_score_stock, ta_score_coin
from sajucandle.saju.scorer import saju_score
from sajucandle.ticker.loader import load_tickers
from sajucandle.ticker.saju_resolver import resolve_ticker_saju
from sajucandle.ticker.schema import TickerRecord

router = APIRouter()

# 알려진 코인 심볼 (asset_class 자동 판별용)
_KNOWN_COINS = {
    "BTC", "ETH", "SOL", "DOGE", "BNB", "XRP",
    "AVAX", "LINK", "MATIC", "ADA", "DOT", "ATOM",
}


def _guess_asset_class(symbol: str) -> str:
    """심볼로 asset_class 추론. 알려진 코인이면 coin, 나머지 stock."""
    clean = symbol.upper().replace("-USD", "").replace("/USDT", "")
    return "coin" if clean in _KNOWN_COINS else "stock"


def _get_ticker_record(symbol: str, asset_class: str) -> Optional[TickerRecord]:
    """sample_tickers에서 종목 레코드 조회. 없으면 None."""
    tickers = load_tickers()
    # 정확 매치
    if symbol in tickers:
        return tickers[symbol]
    # 코인: BTC → BTC-USD 매치
    if asset_class == "coin":
        alt = f"{symbol}-USD"
        if alt in tickers:
            return tickers[alt]
    return None


def _compute_saju_filter(
    symbol: str,
    asset_class: str,
    gender: str = "M",
    threshold: float = 30.0,
) -> dict:
    """C 필터 판정: 종목 사주 × 오늘 일진/세운 궁합 점수가 threshold 이상이면 통과.
    종목 상장일 미상이면 passed=None 반환."""
    rec = _get_ticker_record(symbol, asset_class)
    if rec is None or not rec.listing_date:
        return {"passed": None, "threshold": threshold}

    calc = get_saju_calculator()

    # 종목 사주
    resolved = resolve_ticker_saju(calc, rec)
    if not resolved.get("primary_pillar"):
        return {"passed": None, "threshold": threshold}

    primary_source = resolved["primary_source"]
    if primary_source == "founding":
        primary_saju = resolved["components"]["founding"]["saju"]
    elif primary_source == "listing":
        primary_saju = resolved["components"]["listing"]["saju"]
    else:
        primary_saju = resolved["components"]["transition"][0]["saju"]

    # C 필터: 종목 사주 × 오늘 일진/세운/월운 궁합 점수
    sc = saju_score(
        calc=calc,
        ticker_primary_pillar=resolved["primary_pillar"],
        ticker_saju=primary_saju,
        target_dt=datetime.now(),
        gender_of_user=gender,
    )
    score = sc["total_100"]
    return {"passed": score >= threshold, "threshold": threshold}


def _get_ticker_name(symbol: str, asset_class: str) -> str:
    """종목 이름 조회. 미등록이면 심볼 반환."""
    rec = _get_ticker_record(symbol, asset_class)
    return rec.name if rec else symbol


def _get_current_signal(symbol: str, asset_class: str) -> Optional[str]:
    """sample_tickers 등록 종목만 시그널 반환. 미등록이면 None."""
    rec = _get_ticker_record(symbol, asset_class)
    if rec is None:
        return None
    # 시그널 엔진 호출은 무거우므로 간소화:
    # 캐시된 시그널이 있으면 사용, 없으면 None
    # v1에서는 시그널 계산을 생략하고 None 반환
    return None


# ── 스키마 ────────────────────────────────────────────

class ChartOhlcvRequest(BaseModel):
    symbol: str
    asset_class: Optional[str] = None
    months: int = 3
    birth_date: str = ""
    birth_time: str = "00:00"
    gender: str = "M"


# ── 라우트 ────────────────────────────────────────────

@router.post("/api/chart/ohlcv")
def chart_ohlcv(req: ChartOhlcvRequest):
    """캔들 데이터 + 사주 필터 판정 + 현재 시그널."""
    symbol = req.symbol.upper().strip()
    if not symbol:
        raise HTTPException(status_code=400, detail="종목 심볼을 입력해주세요")

    asset_class = req.asset_class or _guess_asset_class(symbol)

    # OHLCV 조회
    end = datetime.now()
    start = end - timedelta(days=req.months * 31)
    try:
        df = get_ohlcv(symbol, asset_class, start, end)
    except Exception:
        raise HTTPException(status_code=404, detail=f"가격 데이터를 가져올 수 없습니다: {symbol}")

    if df.empty:
        raise HTTPException(status_code=404, detail=f"가격 데이터가 없습니다: {symbol}")

    # 현재가 / 등락률
    current_price = float(df["close"].iloc[-1])
    if len(df) >= 2:
        prev_close = float(df["close"].iloc[-2])
        price_change_pct = round((current_price - prev_close) / prev_close * 100, 2)
    else:
        price_change_pct = 0.0

    # 사주 필터
    saju_filter = {"passed": None, "threshold": 30}
    try:
        saju_filter = _compute_saju_filter(
            symbol, asset_class, req.gender,
        )
    except Exception:
        saju_filter = {"passed": None, "threshold": 30}

    # OHLCV를 JSON 직렬화
    ohlcv_list = []
    for idx, row in df.iterrows():
        ohlcv_list.append({
            "date": idx.strftime("%Y-%m-%d"),
            "open": round(float(row["open"]), 2),
            "high": round(float(row["high"]), 2),
            "low": round(float(row["low"]), 2),
            "close": round(float(row["close"]), 2),
            "volume": int(row["volume"]),
        })

    return {
        "symbol": symbol,
        "name": _get_ticker_name(symbol, asset_class),
        "asset_class": asset_class,
        "current_price": round(current_price, 2),
        "price_change_pct": price_change_pct,
        "saju_filter": saju_filter,
        "current_signal": _get_current_signal(symbol, asset_class),
        "ohlcv": ohlcv_list,
        "signal_markers": [],  # v1: 시그널 마커 미구현
    }


@router.get("/api/chart/analysis")
def chart_analysis(symbol: str, asset_class: str = "stock"):
    """퀀트 상세 분석 (유료). v1에서는 프론트에서 호출하지 않음."""
    symbol = symbol.upper().strip()

    end = datetime.now()
    start = end - timedelta(days=400)
    df = get_ohlcv(symbol, asset_class, start, end)
    if df.empty or len(df) < 30:
        raise HTTPException(status_code=404, detail="분석에 필요한 데이터가 부족합니다")

    # 벤치마크
    bench_sym = "SPY" if asset_class == "stock" else "BTC-USD"
    bench_df = get_ohlcv(bench_sym, asset_class, start, end)

    # TA score
    if asset_class == "stock":
        ta = ta_score_stock(df, bench_df)
    else:
        ta = ta_score_coin(df, bench_df)

    return {
        "symbol": symbol,
        "quant_scores": {
            "ta_score": {"total": ta["total"], "breakdown": ta.get("breakdown", {})},
            "macro_score": {"total": 50, "breakdown": {}},   # v1 간소화
        },
        "signal_history": [],  # v1: 미구현
        "ta_detail": ta.get("breakdown", {}),
        "rank": {"position": 0, "total_passed": 0},  # v1: 미구현
    }

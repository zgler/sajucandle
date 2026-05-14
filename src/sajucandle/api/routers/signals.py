"""사주캔들 Signal 라우터 — /health, /signals/stock, /signals/stock/html, /signals/stock/telegram."""

from __future__ import annotations

import sys
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import List, Optional, Set

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

_root = Path(__file__).parent.parent.parent.parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from sajucandle.manseryeok.core import SajuCalculator
from sajucandle.ticker.loader import load_tickers
from sajucandle.signal.engine import generate_signals, SignalType
from sajucandle.signal.renderer import render_telegram, render_email_html

router = APIRouter()


# ── 싱글턴 초기화 ─────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def _get_calc() -> SajuCalculator:
    return SajuCalculator()


@lru_cache(maxsize=1)
def _get_tickers():
    csv = _root / "data" / "tickers" / "stock_universe_30.csv"
    return load_tickers(csv)


# ── 응답 스키마 ───────────────────────────────────────────────────────────

class SignalItem(BaseModel):
    symbol: str
    signal: str
    saju_score: float
    quant_score: float
    rank: Optional[int]
    reason: str
    breakdown: dict


class SignalResponse(BaseModel):
    target_dt: str
    asset_class: str
    universe: int
    saju_survivors: int
    top_n: int
    saju_filter_threshold: float
    new_holdings: List[str]
    signals: List[SignalItem]


# ── 헬퍼 ─────────────────────────────────────────────────────────────────

_SIGNAL_ORDER = {
    SignalType.BUY: 1,
    SignalType.HOLD: 2,
    SignalType.SELL: 3,
    SignalType.WATCH: 4,
    SignalType.KILL: 5,
}


def _parse_date(date_str: Optional[str]) -> datetime:
    if not date_str:
        return datetime.now().replace(hour=9, minute=0, second=0, microsecond=0)
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").replace(hour=9)
    except ValueError:
        raise HTTPException(status_code=400, detail="date 형식: YYYY-MM-DD")


def _parse_holdings(holdings_str: Optional[str]) -> Set[str]:
    if not holdings_str:
        return set()
    return {s.strip().upper() for s in holdings_str.split(",") if s.strip()}


# ── 라우트 ────────────────────────────────────────────────────────────────

@router.get("/health")
def health():
    return {"status": "ok", "time": datetime.now().isoformat()}


@router.get("/signals/stock", response_model=SignalResponse)
def signals_stock(
    date: Optional[str] = Query(None, description="YYYY-MM-DD (기본: 오늘)"),
    top_n: int = Query(5, ge=1, le=20),
    watch_buffer: int = Query(5, ge=0, le=20),
    saju_threshold: float = Query(30.0, ge=0.0, le=100.0),
    holdings: Optional[str] = Query(None, description="현재 보유 심볼 쉼표 구분, 예: AAPL,MSFT"),
    fast_macro: bool = Query(True),
):
    """주식 신호 JSON."""
    target_dt = _parse_date(date)
    current_holdings = _parse_holdings(holdings)

    tickers = _get_tickers()
    stock_tickers = {s: r for s, r in tickers.items() if r.asset_class == "stock"}

    try:
        report = generate_signals(
            calc=_get_calc(),
            records=stock_tickers,
            asset_class="stock",
            target_dt=target_dt,
            current_holdings=current_holdings,
            top_n=top_n,
            watch_buffer=watch_buffer,
            saju_filter_threshold=saju_threshold,
            fast_macro=fast_macro,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return SignalResponse(
        target_dt=report.target_dt.isoformat(),
        asset_class="stock",
        universe=report.universe_size,
        saju_survivors=report.survivors,
        top_n=report.top_n,
        saju_filter_threshold=report.saju_filter_threshold,
        new_holdings=sorted(report.new_holdings),
        signals=[
            SignalItem(
                symbol=s.symbol,
                signal=s.signal.value,
                saju_score=s.saju_score,
                quant_score=s.quant_score,
                rank=s.rank,
                reason=s.reason,
                breakdown=s.breakdown,
            )
            for s in sorted(report.signals,
                            key=lambda x: (_SIGNAL_ORDER.get(x.signal, 9), x.rank or 999))
        ],
    )


@router.get("/signals/stock/html", response_class=HTMLResponse)
def signals_stock_html(
    date: Optional[str] = Query(None),
    top_n: int = Query(5),
    saju_threshold: float = Query(30.0),
    holdings: Optional[str] = Query(None),
):
    """이메일 HTML 미리보기."""
    target_dt = _parse_date(date)
    current_holdings = _parse_holdings(holdings)

    tickers = _get_tickers()
    stock_tickers = {s: r for s, r in tickers.items() if r.asset_class == "stock"}

    report = generate_signals(
        calc=_get_calc(),
        records=stock_tickers,
        asset_class="stock",
        target_dt=target_dt,
        current_holdings=current_holdings,
        top_n=top_n,
        saju_filter_threshold=saju_threshold,
        fast_macro=True,
    )
    return render_email_html(report)


@router.get("/signals/stock/telegram")
def signals_stock_telegram(
    date: Optional[str] = Query(None),
    top_n: int = Query(5),
    saju_threshold: float = Query(30.0),
    holdings: Optional[str] = Query(None),
):
    """텔레그램 메시지 미리보기."""
    target_dt = _parse_date(date)
    current_holdings = _parse_holdings(holdings)

    tickers = _get_tickers()
    stock_tickers = {s: r for s, r in tickers.items() if r.asset_class == "stock"}

    report = generate_signals(
        calc=_get_calc(),
        records=stock_tickers,
        asset_class="stock",
        target_dt=target_dt,
        current_holdings=current_holdings,
        top_n=top_n,
        saju_filter_threshold=saju_threshold,
        fast_macro=True,
    )
    return {"message": render_telegram(report)}

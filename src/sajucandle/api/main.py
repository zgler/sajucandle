"""FastAPI 서버 — 사주캔들 Signal API.

실행:
  uvicorn sajucandle.api.main:app --reload --port 8000

엔드포인트:
  GET /signals/stock          현재 시점 주식 신호 (Top5 + SELL + WATCH + KILL)
  GET /signals/stock/html     이메일 HTML 미리보기
  GET /signals/stock/telegram 텔레그램 메시지 미리보기
  GET /health                 헬스체크
"""

from __future__ import annotations

import sys
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import List, Optional, Set

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

# src를 path에 추가 (uvicorn이 프로젝트 루트에서 실행될 때)
_root = Path(__file__).parent.parent.parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from sajucandle.manseryeok.core import SajuCalculator
from sajucandle.ticker.loader import load_tickers
from sajucandle.signal.engine import generate_signals, SignalType
from sajucandle.signal.renderer import render_telegram, render_email_html

app = FastAPI(
    title="사주캔들 Signal API",
    description="사주 필터(C전략) + 퀀트 랭킹 기반 월간 리밸런싱 신호",
    version="1.0.0",
)

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


# ── 라우트 ────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "time": datetime.now().isoformat()}


@app.get("/signals/stock", response_model=SignalResponse)
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


@app.get("/signals/stock/html", response_class=HTMLResponse)
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


@app.get("/signals/stock/telegram")
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


# ── 사주 운세 API (MVP) ─────────────────────────────────────────────────────

from fastapi.middleware.cors import CORSMiddleware
from sajucandle.manseryeok.core import get_saju_calculator
from sajucandle.saju.investor_profile import classify_investor_type
from sajucandle.saju.daily_fortune import generate_daily_fortune
from sajucandle.saju.fortune_templates import (
    SEWOON_TEMPLATES,
    DAEUN_TEMPLATES,
)
from sajucandle.saju.investor_profile import DAY_MASTER_DESCRIPTIONS
from sajucandle.saju.tengod import ten_god_for_stem
from sajucandle.saju.daeun import compute_daeun
from sajucandle.saju.sewoon import compute_sewoon_wolwoon_ilji

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ProfileRequest(BaseModel):
    year: int
    month: int
    day: int
    hour: Optional[int] = None
    minute: int = 0
    gender: str = "M"


def _calc_saju_for_user(req_year: int, req_month: int, req_day: int,
                        req_hour: Optional[int], req_minute: int = 0) -> dict:
    """유저 생년월일 → 사주 계산. 시간 미입력 시 시주 제거."""
    calc = get_saju_calculator()
    h = req_hour if req_hour is not None else 0
    saju = calc.calculate_saju(req_year, req_month, req_day, h, req_minute)
    if req_hour is None:
        saju["hour_pillar"] = ""
        saju["hour_stem"] = ""
        saju["hour_branch"] = ""
    return saju


@app.post("/api/saju/profile")
def saju_profile(req: ProfileRequest):
    """생년월일시 → 투자 체질 프로필."""
    saju = _calc_saju_for_user(req.year, req.month, req.day, req.hour, req.minute)
    profile = classify_investor_type(saju)
    return {
        "saju": {
            "year_pillar": saju["year_pillar"],
            "month_pillar": saju["month_pillar"],
            "day_pillar": saju["day_pillar"],
            "hour_pillar": saju.get("hour_pillar", ""),
        },
        "day_master": profile.day_master,
        "day_master_element": profile.day_master_element,
        "day_master_description": DAY_MASTER_DESCRIPTIONS.get(profile.day_master, ""),
        "investor_type": profile.investor_type,
        "description": profile.description,
        "strengths": profile.strengths,
        "weaknesses": profile.weaknesses,
        "risk_score": profile.risk_score,
        "element_distribution": profile.element_distribution,
        "dominant_group": profile.dominant_group,
        "tengod_counts": profile.tengod_counts,
    }


@app.get("/api/saju/daily")
def saju_daily(
    year: int,
    month: int,
    day: int,
    hour: Optional[int] = None,
    minute: int = 0,
    gender: str = "M",
    date: Optional[str] = None,
):
    """오늘의 매매 기운."""
    saju = _calc_saju_for_user(year, month, day, hour, minute)

    if date:
        parts = date.split("-")
        target = datetime(int(parts[0]), int(parts[1]), int(parts[2]), 12)
    else:
        target = datetime.now().replace(hour=12, minute=0, second=0, microsecond=0)

    fortune = generate_daily_fortune(saju, target)
    return {
        "date": fortune.date,
        "day_pillar_today": fortune.day_pillar_today,
        "tengod_label": fortune.tengod_label,
        "judgment_score": fortune.judgment_score,
        "execution_score": fortune.execution_score,
        "patience_score": fortune.patience_score,
        "coaching": fortune.coaching,
        "caution": fortune.caution,
        "detail": fortune.detail,
        "shinsal_messages": fortune.shinsal_messages,
        "relation_messages": fortune.relation_messages,
    }


@app.get("/api/saju/yearly")
def saju_yearly(
    year: int,
    month: int,
    day: int,
    hour: Optional[int] = None,
    minute: int = 0,
    gender: str = "M",
    target_year: Optional[int] = None,
):
    """올해 세운/대운 투자 흐름 해설."""
    saju = _calc_saju_for_user(year, month, day, hour, minute)
    calc = get_saju_calculator()
    now = datetime.now()
    ty = target_year or now.year

    target = datetime(ty, now.month, now.day, 12)
    context = compute_sewoon_wolwoon_ilji(calc, target)

    sewoon_pillar = context["sewoon"]
    sewoon_stem = sewoon_pillar[0] if sewoon_pillar else ""
    day_stem = saju["day_stem"]
    sewoon_tg = ten_god_for_stem(day_stem, sewoon_stem)

    group_map = {
        "비견": "비겁", "겁재": "비겁",
        "식신": "식상", "상관": "식상",
        "편재": "재성", "정재": "재성",
        "편관": "관성", "정관": "관성",
        "편인": "인성", "정인": "인성",
    }

    h = hour if hour is not None else 0
    birth_dt = datetime(year, month, day, h, minute)
    daeun_data = compute_daeun(
        calc.data, birth_dt,
        saju["year_pillar"], saju["month_pillar"], gender,
    )

    current_daeun = None
    age = ty - year
    for d in daeun_data.get("daeun", []):
        if d["start_age"] <= age < d["end_age"]:
            current_daeun = d
            break

    daeun_info = {}
    if current_daeun:
        daeun_stem = current_daeun["stem"]
        daeun_tg = ten_god_for_stem(day_stem, daeun_stem)
        daeun_group = group_map.get(daeun_tg, "비겁")
        daeun_info = {
            "pillar": current_daeun["pillar"],
            "tengod": daeun_tg,
            "group": daeun_group,
            "message": DAEUN_TEMPLATES.get(daeun_group, ""),
            "start_age": current_daeun["start_age"],
            "end_age": current_daeun["end_age"],
        }

    return {
        "target_year": ty,
        "sewoon_pillar": sewoon_pillar,
        "sewoon_tengod": sewoon_tg,
        "sewoon_message": SEWOON_TEMPLATES.get(sewoon_tg, ""),
        "daeun": daeun_info,
    }

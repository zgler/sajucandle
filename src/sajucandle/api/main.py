"""FastAPI 서버 — 사주캔들 Signal API.

실행:
  uvicorn sajucandle.api.main:app --reload --port 8000

엔드포인트:
  GET /signals/stock          현재 시점 주식 신호 (Top5 + SELL + WATCH + KILL)
  GET /signals/stock/html     이메일 HTML 미리보기
  GET /signals/stock/telegram 텔레그램 메시지 미리보기
  GET /health                 헬스체크
  POST /api/saju/profile      투자 체질 프로필
  GET  /api/saju/daily        오늘의 매매 기운
  GET  /api/saju/yearly       세운/대운 투자 흐름
  POST /api/saju/report       사주 투자 감정서
  POST /api/payments/confirm  Toss 결제 승인
"""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from sajucandle.api.routers import signals, saju, payments

app = FastAPI(
    title="사주캔들 Signal API",
    description="사주 필터(C전략) + 퀀트 랭킹 기반 월간 리밸런싱 신호",
    version="1.0.0",
)


def _build_cors_origins() -> list[str]:
    """환경변수 기반 CORS origin 목록 구성."""
    origins = [
        "http://localhost:3000",
        "http://localhost:3001",
    ]
    frontend_url = os.environ.get("FRONTEND_URL")
    if frontend_url:
        origins.append(frontend_url.rstrip("/"))
    return origins


app.add_middleware(
    CORSMiddleware,
    allow_origins=_build_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(signals.router)
app.include_router(saju.router)
app.include_router(payments.router)

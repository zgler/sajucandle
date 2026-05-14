"""사주캔들 결제 라우터 — /api/payments/confirm."""

from __future__ import annotations

import base64
import os
from datetime import datetime
from typing import Optional

import anthropic
import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from sajucandle.saju.report_context import collect_report_context
from sajucandle.saju.report_generator import generate_report

router = APIRouter()

TIER_PRICES = {"standard": 990, "premium": 9900}


class PaymentConfirmRequest(BaseModel):
    payment_key: str = Field(min_length=1)
    order_id: str = Field(min_length=1)
    amount: int
    year: int
    month: int
    day: int
    hour: Optional[int] = None
    gender: str = "M"
    tier: str = "standard"


@router.post("/api/payments/confirm")
async def payment_confirm(req: PaymentConfirmRequest):
    """Toss 결제 승인 후 전체 잠금 해제 감정서를 반환한다."""
    # 1. tier / amount 유효성 검증
    if req.tier not in TIER_PRICES:
        raise HTTPException(status_code=400, detail=f"유효하지 않은 tier입니다: {req.tier}")
    if req.amount != TIER_PRICES[req.tier]:
        raise HTTPException(
            status_code=400,
            detail=f"금액 불일치: {req.tier} 티어는 {TIER_PRICES[req.tier]}원이어야 합니다",
        )

    # 2. Toss 시크릿 키 확인
    secret_key = os.environ.get("TOSS_SECRET_KEY")
    if not secret_key:
        raise HTTPException(status_code=503, detail="결제 서비스 준비 중입니다")

    # 3. Toss 결제 승인 API 호출
    credentials = base64.b64encode(f"{secret_key}:".encode()).decode()
    try:
        async with httpx.AsyncClient() as client:
            toss_resp = await client.post(
                "https://api.tosspayments.com/v1/payments/confirm",
                headers={
                    "Authorization": f"Basic {credentials}",
                    "Content-Type": "application/json",
                },
                json={
                    "paymentKey": req.payment_key,
                    "orderId": req.order_id,
                    "amount": req.amount,
                },
                timeout=30,
            )
    except (httpx.TimeoutException, httpx.ConnectError) as exc:
        raise HTTPException(status_code=502, detail=f"결제 서버 연결 실패: {exc}") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"결제 요청 오류: {exc}") from exc

    if toss_resp.status_code != 200:
        toss_data = toss_resp.json()
        raise HTTPException(
            status_code=400,
            detail={
                "success": False,
                "error": toss_data.get("message", "결제 승인 실패"),
                "code": toss_data.get("code", "UNKNOWN"),
            },
        )

    # 4. 전체 잠금 해제 감정서 생성
    now_year = datetime.now().year
    hour_str = f"{req.hour:02d}" if req.hour is not None else "00"
    report_id = f"rpt_{req.year}{req.month:02d}{req.day:02d}{hour_str}{req.gender}_{now_year}"

    context = collect_report_context(
        req.year, req.month, req.day,
        req.hour, req.gender, now_year,
    )
    try:
        sections = await generate_report(context, tier=req.tier)
    except ValueError:
        raise HTTPException(
            status_code=502,
            detail="결제는 완료되었습니다. 감정서 생성 중 오류가 발생했습니다. 다시 시도해 주세요.",
        )
    except anthropic.APITimeoutError:
        raise HTTPException(
            status_code=502,
            detail="결제는 완료되었습니다. 감정서 생성 중 오류가 발생했습니다. 다시 시도해 주세요.",
        )
    except Exception:
        raise HTTPException(
            status_code=502,
            detail="결제는 완료되었습니다. 감정서 생성 중 오류가 발생했습니다. 다시 시도해 주세요.",
        )

    unlocked = [{**sec, "locked": False} for sec in sections]

    return {
        "success": True,
        "payment": {
            "order_id": req.order_id,
            "amount": req.amount,
            "tier": req.tier,
        },
        "report": {
            "report_id": report_id,
            "target_year": now_year,
            "tier": req.tier,
            "sections": unlocked,
        },
    }

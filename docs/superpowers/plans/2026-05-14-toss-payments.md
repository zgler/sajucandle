# Toss Payments 결제 연동 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Toss Payments로 감정서 봉인 해제 결제 플로우 구현 (DB 없이 최소 구현)

**Architecture:** 프론트에서 Toss SDK로 결제창 호출 → 성공 시 서버 `/api/payments/confirm`이 Toss 승인 API 확정 + 잠금 없는 전체 감정서 생성 반환 → 클라이언트 localStorage에 캐시. DB 없음.

**Tech Stack:** Toss Payments JS SDK (`@tosspayments/tosspayments-sdk`), httpx (이미 설치됨), FastAPI, Next.js

---

## File Structure

| 파일 | 역할 | 변경 |
|------|------|------|
| `src/sajucandle/api/main.py` | 결제 승인 엔드포인트 추가 | Modify |
| `tests/test_api_payment.py` | 결제 엔드포인트 테스트 | Create |
| `frontend/src/lib/types.ts` | `PaymentConfirmResponse` 타입 추가 | Modify |
| `frontend/src/lib/api.ts` | `confirmPayment()` 함수 추가 | Modify |
| `frontend/src/app/report/page.tsx` | `handlePurchase` → Toss SDK 호출로 변경 | Modify |
| `frontend/src/app/report/success/page.tsx` | 결제 성공 리다이렉트 페이지 | Create |
| `frontend/src/app/report/fail/page.tsx` | 결제 실패 리다이렉트 페이지 | Create |

---

### Task 1: 백엔드 결제 승인 엔드포인트

**Files:**
- Modify: `src/sajucandle/api/main.py:430-496` (감정서 API 섹션 뒤에 추가)
- Create: `tests/test_api_payment.py`

- [ ] **Step 1: 테스트 파일 작성**

`tests/test_api_payment.py` 생성:

```python
"""tests/test_api_payment.py — POST /api/payments/confirm 엔드포인트 테스트."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch, MagicMock

import pytest
from fastapi.testclient import TestClient
from sajucandle.api.main import app


@pytest.fixture
def client():
    return TestClient(app)


MOCK_SECTIONS = [
    {"id": i, "title": f"섹션{i}", "content": f"내용{i}", "highlight": f"핵심{i}"}
    for i in range(1, 8)
]

VALID_PAYLOAD = {
    "payment_key": "test_paymentKey_123",
    "order_id": "ord_1715670000_rpt_test_standard",
    "amount": 990,
    "year": 1995,
    "month": 3,
    "day": 1,
    "hour": 14,
    "gender": "M",
    "tier": "standard",
}


class TestPaymentConfirmValidation:
    """금액/티어 검증 테스트 — Toss API 호출 전에 거부되어야 함."""

    def test_tier_amount_mismatch_returns_400(self, client: TestClient):
        """standard 티어인데 9900원이면 400."""
        payload = {**VALID_PAYLOAD, "amount": 9900, "tier": "standard"}
        resp = client.post("/api/payments/confirm", json=payload)
        assert resp.status_code == 400

    def test_premium_amount_mismatch_returns_400(self, client: TestClient):
        """premium 티어인데 990원이면 400."""
        payload = {**VALID_PAYLOAD, "amount": 990, "tier": "premium"}
        resp = client.post("/api/payments/confirm", json=payload)
        assert resp.status_code == 400

    def test_invalid_tier_returns_400(self, client: TestClient):
        """unknown 티어이면 400."""
        payload = {**VALID_PAYLOAD, "tier": "unknown", "amount": 990}
        resp = client.post("/api/payments/confirm", json=payload)
        assert resp.status_code == 400


class TestPaymentConfirmSuccess:
    """Toss 승인 성공 → 전체 감정서 반환."""

    def _mock_toss_success(self):
        """httpx.AsyncClient.post가 200 반환하도록 mock."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "DONE", "orderId": VALID_PAYLOAD["order_id"]}
        return mock_response

    def test_confirm_success_returns_full_report(self, client: TestClient):
        mock_resp = self._mock_toss_success()
        with patch("sajucandle.api.main._has_anthropic_key", return_value=True), \
             patch("sajucandle.api.main.collect_report_context", return_value={}), \
             patch("sajucandle.api.main.generate_report",
                   new_callable=AsyncMock, return_value=MOCK_SECTIONS), \
             patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
            resp = client.post("/api/payments/confirm", json=VALID_PAYLOAD)

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["payment"]["tier"] == "standard"
        assert data["payment"]["amount"] == 990
        # 모든 섹션이 locked=False여야 함
        for sec in data["report"]["sections"]:
            assert sec["locked"] is False
            assert sec["content"] != ""

    def test_confirm_premium_returns_premium_tier(self, client: TestClient):
        mock_resp = self._mock_toss_success()
        payload = {**VALID_PAYLOAD, "tier": "premium", "amount": 9900}
        with patch("sajucandle.api.main._has_anthropic_key", return_value=True), \
             patch("sajucandle.api.main.collect_report_context", return_value={}), \
             patch("sajucandle.api.main.generate_report",
                   new_callable=AsyncMock, return_value=MOCK_SECTIONS), \
             patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
            resp = client.post("/api/payments/confirm", json=payload)

        assert resp.status_code == 200
        data = resp.json()
        assert data["payment"]["tier"] == "premium"
        assert data["payment"]["amount"] == 9900


class TestPaymentConfirmFailure:
    """Toss 승인 실패 케이스."""

    def test_toss_api_rejects_returns_400(self, client: TestClient):
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.json.return_value = {"code": "ALREADY_PROCESSED_PAYMENT", "message": "이미 처리된 결제"}
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
            resp = client.post("/api/payments/confirm", json=VALID_PAYLOAD)

        assert resp.status_code == 400
        data = resp.json()
        assert data["detail"]["success"] is False

    def test_no_toss_secret_key_returns_503(self, client: TestClient):
        with patch.dict("os.environ", {}, clear=False), \
             patch("os.environ.get", side_effect=lambda k, d=None: None if k == "TOSS_SECRET_KEY" else d):
            # TOSS_SECRET_KEY가 없으면 503
            resp = client.post("/api/payments/confirm", json=VALID_PAYLOAD)
        # 환경변수 없으면 서비스 불가
        assert resp.status_code in (400, 503)
```

- [ ] **Step 2: 테스트 실행하여 실패 확인**

Run: `cd "C:/Users/user/Downloads/사주캔들/.claude/worktrees/serene-merkle-406ed6" && ./.venv/Scripts/python.exe -m pytest tests/test_api_payment.py -v`
Expected: FAIL — `/api/payments/confirm` 엔드포인트 없음 (404)

- [ ] **Step 3: 엔드포인트 구현**

`src/sajucandle/api/main.py` 파일 끝(line 497 이후)에 추가:

```python
# ── 결제 승인 API ─────────────────────────────────────────────────────────────
import base64
import httpx

TIER_PRICES = {"standard": 990, "premium": 9900}


class PaymentConfirmRequest(BaseModel):
    payment_key: str
    order_id: str
    amount: int
    year: int
    month: int
    day: int
    hour: Optional[int] = None
    gender: str = "M"
    tier: str = "standard"


@app.post("/api/payments/confirm")
async def confirm_payment(req: PaymentConfirmRequest):
    """Toss Payments 결제 승인 + 전체 감정서 생성."""
    # 1. 티어-금액 검증
    if req.tier not in TIER_PRICES:
        raise HTTPException(status_code=400, detail="잘못된 티어입니다")
    if TIER_PRICES[req.tier] != req.amount:
        raise HTTPException(
            status_code=400,
            detail=f"금액 불일치: {req.tier} 티어는 {TIER_PRICES[req.tier]}원입니다",
        )

    # 2. Toss 승인 API 호출
    toss_secret = os.environ.get("TOSS_SECRET_KEY")
    if not toss_secret:
        raise HTTPException(status_code=503, detail="결제 서비스 준비 중입니다")

    auth_header = "Basic " + base64.b64encode(
        f"{toss_secret}:".encode()
    ).decode()

    async with httpx.AsyncClient(timeout=30.0) as http:
        toss_resp = await http.post(
            "https://api.tosspayments.com/v1/payments/confirm",
            headers={
                "Authorization": auth_header,
                "Content-Type": "application/json",
            },
            json={
                "paymentKey": req.payment_key,
                "orderId": req.order_id,
                "amount": req.amount,
            },
        )

    if toss_resp.status_code != 200:
        error_data = toss_resp.json()
        raise HTTPException(
            status_code=400,
            detail={
                "success": False,
                "error": error_data.get("message", "결제 승인에 실패했습니다"),
                "code": error_data.get("code", "PAYMENT_FAILED"),
            },
        )

    # 3. 전체 감정서 생성 (잠금 없음)
    if not _has_anthropic_key():
        raise HTTPException(status_code=503, detail="감정서 서비스 준비 중입니다")

    now_year = datetime.now().year
    hour_str = f"{req.hour:02d}" if req.hour is not None else "00"
    report_id = f"rpt_{req.year}{req.month:02d}{req.day:02d}{hour_str}{req.gender}_{now_year}"

    try:
        context = collect_report_context(
            req.year, req.month, req.day,
            req.hour, req.gender, now_year,
        )
        sections = await generate_report(context, tier=req.tier)
    except Exception:
        raise HTTPException(
            status_code=502,
            detail="결제는 완료되었습니다. 감정서 생성 중 오류가 발생했습니다. 다시 시도해 주세요.",
        )

    # 4. 전체 섹션 반환 (locked=False)
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
```

- [ ] **Step 4: 테스트 실행하여 통과 확인**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_api_payment.py -v`
Expected: PASS (validation 테스트 3개 + success 테스트 2개 + failure 테스트 2개)

- [ ] **Step 5: 기존 테스트 회귀 확인**

Run: `./.venv/Scripts/python.exe -m pytest tests/ -q`
Expected: 기존 74개 + 신규 7개 = 81개 전부 PASS

- [ ] **Step 6: 커밋**

```bash
git add src/sajucandle/api/main.py tests/test_api_payment.py
git commit -m "feat(api): add POST /api/payments/confirm endpoint for Toss Payments"
```

---

### Task 2: 프론트엔드 타입 + API 함수

**Files:**
- Modify: `frontend/src/lib/types.ts:79` (끝에 추가)
- Modify: `frontend/src/lib/api.ts:97` (끝에 추가)

- [ ] **Step 1: PaymentConfirmResponse 타입 추가**

`frontend/src/lib/types.ts` 파일 끝에 추가:

```typescript
export interface PaymentInfo {
  order_id: string;
  amount: number;
  tier: string;
}

export interface PaymentConfirmResponse {
  success: boolean;
  payment: PaymentInfo;
  report: ReportResponse;
}
```

- [ ] **Step 2: confirmPayment 함수 추가**

`frontend/src/lib/api.ts` 파일 끝에 추가 (import에 `PaymentConfirmResponse` 추가):

먼저 import 줄 수정:
```typescript
// 기존:
import type { ProfileResponse, DailyFortuneResponse, YearlyFortuneResponse, ReportResponse } from "./types";
// 변경:
import type { ProfileResponse, DailyFortuneResponse, YearlyFortuneResponse, ReportResponse, PaymentConfirmResponse } from "./types";
```

파일 끝에 함수 추가:
```typescript
export async function confirmPayment(params: {
  payment_key: string;
  order_id: string;
  amount: number;
  year: number;
  month: number;
  day: number;
  hour?: number;
  gender: "M" | "F";
  tier: "standard" | "premium";
}): Promise<PaymentConfirmResponse> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 300000);

  try {
    const res = await fetch(`${API_BASE}/api/payments/confirm`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(params),
      signal: controller.signal,
    });
    if (!res.ok) {
      const text = await res.text();
      throw new Error(`confirmPayment failed: ${res.status} ${text}`);
    }
    return res.json();
  } finally {
    clearTimeout(timeout);
  }
}
```

- [ ] **Step 3: 빌드 확인**

Run: `cd frontend && npx next build`
Expected: 빌드 성공

- [ ] **Step 4: 커밋**

```bash
git add frontend/src/lib/types.ts frontend/src/lib/api.ts
git commit -m "feat(frontend): add PaymentConfirmResponse type and confirmPayment API function"
```

---

### Task 3: Toss SDK 설치 + handlePurchase 연동

**Files:**
- Modify: `frontend/package.json` (npm install)
- Modify: `frontend/src/app/report/page.tsx:1-10,284-289` (import + handlePurchase)

- [ ] **Step 1: Toss SDK 설치**

Run: `cd frontend && npm install @tosspayments/tosspayments-sdk`

- [ ] **Step 2: handlePurchase를 Toss SDK 호출로 변경**

`frontend/src/app/report/page.tsx` 수정:

import 섹션(line 1~8)에 추가:
```typescript
import { loadTossPayments } from "@tosspayments/tosspayments-sdk";
```

`handlePurchase` 함수(line 284~289)를 교체:
```typescript
  async function handlePurchase(tier: "standard" | "premium") {
    if (!user) return;

    const clientKey = process.env.NEXT_PUBLIC_TOSS_CLIENT_KEY;
    if (!clientKey) {
      setToastVisible(true);
      setTimeout(() => setToastVisible(false), 2500);
      return;
    }

    const amount = tier === "standard" ? 990 : 9900;
    const reportId = buildReportId(user);
    const orderId = `ord_${Date.now()}_${reportId}_${tier}`;
    const orderName = `사주캔들 투자 감정서 (${tier === "standard" ? "Standard" : "Premium"})`;

    // pending_order를 localStorage에 저장 (success 페이지에서 사용)
    try {
      localStorage.setItem("pending_order", JSON.stringify({
        tier,
        year: user.year,
        month: user.month,
        day: user.day,
        hour: user.hour,
        gender: user.gender,
      }));
    } catch {
      // ignore
    }

    try {
      const tossPayments = await loadTossPayments(clientKey);
      const payment = tossPayments.payment({ customerKey: reportId });
      await payment.requestPayment({
        method: "CARD",
        amount: { currency: "KRW", value: amount },
        orderId,
        orderName,
        successUrl: `${window.location.origin}/report/success`,
        failUrl: `${window.location.origin}/report/fail`,
      });
    } catch (err) {
      // 사용자가 결제창 닫은 경우 등
      console.error("Payment request failed:", err);
    }
  }
```

- [ ] **Step 3: 빌드 확인**

Run: `cd frontend && npx next build`
Expected: 빌드 성공

- [ ] **Step 4: 커밋**

```bash
git add frontend/package.json frontend/package-lock.json frontend/src/app/report/page.tsx
git commit -m "feat(report): integrate Toss Payments SDK in handlePurchase"
```

---

### Task 4: 결제 성공 페이지

**Files:**
- Create: `frontend/src/app/report/success/page.tsx`

- [ ] **Step 1: success 페이지 작성**

`frontend/src/app/report/success/page.tsx` 생성:

```tsx
"use client";

import { useEffect, useState, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { confirmPayment } from "@/lib/api";
import type { UserData } from "@/lib/types";

const REPORT_CACHE_PREFIX = "saju_report_";

function buildReportId(user: UserData): string {
  const h = user.hour !== undefined ? String(user.hour).padStart(2, "0") : "00";
  const y = new Date().getFullYear();
  return `rpt_${user.year}${String(user.month).padStart(2, "0")}${String(user.day).padStart(2, "0")}${h}${user.gender}_${y}`;
}

function SuccessContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [status, setStatus] = useState<"loading" | "error">("loading");
  const [errorMsg, setErrorMsg] = useState("");

  useEffect(() => {
    const paymentKey = searchParams.get("paymentKey");
    const orderId = searchParams.get("orderId");
    const amount = searchParams.get("amount");

    if (!paymentKey || !orderId || !amount) {
      setStatus("error");
      setErrorMsg("결제 정보가 누락되었습니다.");
      return;
    }

    // pending_order에서 사주 정보 로드
    let pendingOrder: {
      tier: "standard" | "premium";
      year: number;
      month: number;
      day: number;
      hour?: number;
      gender: "M" | "F";
    } | null = null;

    try {
      const raw = localStorage.getItem("pending_order");
      if (raw) pendingOrder = JSON.parse(raw);
    } catch {
      // ignore
    }

    if (!pendingOrder) {
      setStatus("error");
      setErrorMsg("주문 정보를 찾을 수 없습니다. 감정서 페이지에서 다시 시도해 주세요.");
      return;
    }

    confirmPayment({
      payment_key: paymentKey,
      order_id: orderId,
      amount: Number(amount),
      year: pendingOrder.year,
      month: pendingOrder.month,
      day: pendingOrder.day,
      hour: pendingOrder.hour,
      gender: pendingOrder.gender,
      tier: pendingOrder.tier,
    })
      .then((data) => {
        // 전체 감정서를 localStorage에 캐시
        const reportId = buildReportId(pendingOrder as UserData);
        try {
          localStorage.setItem(
            REPORT_CACHE_PREFIX + reportId,
            JSON.stringify(data.report),
          );
          localStorage.removeItem("pending_order");
        } catch {
          // ignore
        }
        // 감정서 페이지로 리다이렉트
        router.replace("/report");
      })
      .catch((err) => {
        setStatus("error");
        setErrorMsg(
          err instanceof Error
            ? err.message
            : "결제 승인 중 오류가 발생했습니다.",
        );
      });
  }, [searchParams, router]);

  if (status === "error") {
    return (
      <div className="min-h-screen bg-stone-950 flex items-center justify-center px-6">
        <div className="text-center space-y-4 max-w-sm">
          <div className="w-12 h-12 mx-auto rounded-full bg-red-950/60 border border-red-900/30 flex items-center justify-center">
            <span className="text-red-400 text-lg font-serif">凶</span>
          </div>
          <p className="text-sm text-red-300 font-medium">결제 승인 실패</p>
          <p className="text-[12px] text-stone-500 leading-relaxed">{errorMsg}</p>
          <button
            onClick={() => router.replace("/report")}
            className="mt-4 px-6 py-2.5 rounded-xl text-[13px] font-medium text-stone-200 bg-stone-900 border border-stone-700/60 hover:bg-stone-800 transition-all"
          >
            감정서로 돌아가기
          </button>
        </div>
      </div>
    );
  }

  // loading 상태
  return (
    <div className="min-h-screen bg-stone-950 flex items-center justify-center px-6">
      <div className="text-center space-y-4">
        <div className="flex gap-2 justify-center">
          {[0, 1, 2, 3].map((i) => (
            <div
              key={i}
              className="w-1.5 h-1.5 rounded-full bg-amber-400/50 ink-dot"
              style={{ animationDelay: `${i * 300}ms` }}
            />
          ))}
        </div>
        <p className="text-[15px] text-stone-300 font-medium">결제를 확인하고 있습니다</p>
        <p className="text-[12px] text-stone-600">감정서 전체를 생성 중입니다. 잠시만 기다려 주세요.</p>
      </div>
    </div>
  );
}

export default function PaymentSuccessPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen bg-stone-950 flex items-center justify-center">
          <p className="text-stone-500 text-sm">로딩 중...</p>
        </div>
      }
    >
      <SuccessContent />
    </Suspense>
  );
}
```

- [ ] **Step 2: 빌드 확인**

Run: `cd frontend && npx next build`
Expected: 빌드 성공

- [ ] **Step 3: 커밋**

```bash
git add frontend/src/app/report/success/page.tsx
git commit -m "feat(report): add payment success redirect page"
```

---

### Task 5: 결제 실패 페이지

**Files:**
- Create: `frontend/src/app/report/fail/page.tsx`

- [ ] **Step 1: fail 페이지 작성**

`frontend/src/app/report/fail/page.tsx` 생성:

```tsx
"use client";

import { Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";

function FailContent() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const code = searchParams.get("code") ?? "UNKNOWN";
  const message = searchParams.get("message") ?? "결제가 취소되었거나 실패했습니다.";

  return (
    <div className="min-h-screen bg-stone-950 flex items-center justify-center px-6">
      <div className="text-center space-y-4 max-w-sm">
        <div className="w-12 h-12 mx-auto rounded-full bg-red-950/60 border border-red-900/30 flex items-center justify-center">
          <span className="text-red-400 text-lg font-serif">凶</span>
        </div>
        <p className="text-sm text-red-300 font-medium">결제 실패</p>
        <p className="text-[12px] text-stone-500 leading-relaxed">{message}</p>
        <p className="text-[10px] text-stone-700">에러 코드: {code}</p>
        <button
          onClick={() => router.replace("/report")}
          className="mt-4 px-6 py-2.5 rounded-xl text-[13px] font-medium text-stone-200 bg-stone-900 border border-stone-700/60 hover:bg-stone-800 transition-all"
        >
          감정서로 돌아가기
        </button>
      </div>
    </div>
  );
}

export default function PaymentFailPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen bg-stone-950 flex items-center justify-center">
          <p className="text-stone-500 text-sm">로딩 중...</p>
        </div>
      }
    >
      <FailContent />
    </Suspense>
  );
}
```

- [ ] **Step 2: 빌드 확인**

Run: `cd frontend && npx next build`
Expected: 빌드 성공, `/report/fail` 라우트 표시

- [ ] **Step 3: 커밋**

```bash
git add frontend/src/app/report/fail/page.tsx
git commit -m "feat(report): add payment failure redirect page"
```

---

### Task 6: 전체 빌드 + 회귀 검증

**Files:** 없음 (검증만)

- [ ] **Step 1: 백엔드 전체 테스트**

Run: `./.venv/Scripts/python.exe -m pytest tests/ -q`
Expected: 81개+ 전부 PASS

- [ ] **Step 2: 프론트엔드 빌드**

Run: `cd frontend && npx next build`
Expected: 빌드 성공, 라우트에 `/report/success`와 `/report/fail` 표시

- [ ] **Step 3: 환경변수 확인 메모 출력**

아래 환경변수가 설정되어야 결제 플로우가 동작함을 확인:
- 백엔드: `TOSS_SECRET_KEY` (테스트: `test_sk_...`)
- 프론트엔드: `NEXT_PUBLIC_TOSS_CLIENT_KEY` (테스트: `test_ck_...`)
- 값은 [Toss 개발자센터](https://developers.tosspayments.com)에서 확인

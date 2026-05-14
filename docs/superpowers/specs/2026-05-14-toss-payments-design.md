# Toss Payments 결제 연동 설계

**목표:** 감정서 봉인 해제를 위한 Toss Payments 결제 플로우 구현 (DB 없이 최소 구현)

**결정사항:**
- DB 없음 — Toss 승인 검증만, 결과는 클라이언트 localStorage
- 결제 후 즉시 전체 감정서 재생성 (잠금 없는 버전)
- Toss Payments 위젯 SDK (브라우저) + 서버 승인 API
- 테스트 모드(`test_ck_...` / `test_sk_...`)로 개발, 라이브 키 교체로 전환

---

## 1. 결제 플로우

```
사용자: 감정서 페이지에서 티어 선택 (standard 990원 / premium 9,900원)
  → 프론트: orderId 생성 + localStorage에 pending_order 저장
  → 프론트: Toss SDK requestPayment() 호출 → 결제창 표시
  → 사용자: 결제 수단 선택 후 결제 완료
  → Toss: successUrl(/report/success)로 리다이렉트 (paymentKey, orderId, amount 쿼리)
  → 프론트: /report/success 페이지에서 쿼리 파싱
  → 프론트: POST /api/payments/confirm 호출
  → 백엔드: Toss 승인 API 호출하여 결제 확정
  → 백엔드: 잠금 없는 전체 감정서 생성 → 반환
  → 프론트: 전체 감정서를 localStorage에 캐시 → /report로 리다이렉트
```

**실패 플로우:**
```
결제 실패/취소 → Toss가 failUrl(/report/fail)로 리다이렉트
  → 프론트: 에러 코드/메시지 표시 + "돌아가기" 버튼
```

## 2. 백엔드 API

### 새 엔드포인트: `POST /api/payments/confirm`

**Request:**
```json
{
  "payment_key": "toss_paymentKey_string",
  "order_id": "ord_1715670000_rpt_199503010014M_2026_standard",
  "amount": 990,
  "year": 1995,
  "month": 3,
  "day": 1,
  "hour": 14,
  "gender": "M",
  "tier": "standard"
}
```

**처리 순서:**
1. `tier`와 `amount` 매칭 검증 — `standard=990`, `premium=9900`. 불일치 시 400 에러
2. Toss 승인 API 호출: `POST https://api.tosspayments.com/v1/payments/confirm`
   - Header: `Authorization: Basic {base64(TOSS_SECRET_KEY + ':')}`
   - Body: `{ paymentKey, orderId, amount }`
3. 승인 성공 → `generate_report(context, tier=tier)` 호출 (모든 섹션 `locked=False`)
4. 감정서 + 결제 정보 반환

**Response (성공):**
```json
{
  "success": true,
  "payment": {
    "order_id": "ord_...",
    "amount": 990,
    "tier": "standard"
  },
  "report": {
    "report_id": "rpt_...",
    "target_year": 2026,
    "tier": "standard",
    "sections": [
      { "id": 1, "title": "...", "content": "...", "locked": false },
      { "id": 2, "title": "...", "content": "...", "locked": false },
      ...전체 7개 섹션, 모두 locked=false
    ]
  }
}
```

**Response (실패):**
```json
{
  "success": false,
  "error": "결제 승인에 실패했습니다",
  "code": "PAYMENT_FAILED"
}
```

### 환경변수

| 변수 | 용도 | 테스트 값 |
|------|------|-----------|
| `TOSS_SECRET_KEY` | 서버 승인 API 인증 | `test_sk_...` (Toss 개발자센터에서 확인) |

### 기존 코드 변경

- `main.py`의 기존 `/api/saju/report` 엔드포인트: 변경 없음. 섹션 3~7 잠금 로직 유지.
- 결제 확인 엔드포인트에서만 잠금 없는 전체 버전을 생성.

## 3. 프론트엔드

### 새 파일

**`frontend/src/app/report/success/page.tsx`** — 결제 성공 리다이렉트 랜딩
- URL 쿼리에서 `paymentKey`, `orderId`, `amount` 파싱
- localStorage에서 `pending_order` 로드 (사주 정보 + tier)
- `POST /api/payments/confirm` 호출
- 성공 → 전체 감정서를 localStorage 캐시에 덮어쓰기 → `/report`로 리다이렉트
- 실패 → 에러 표시 + "감정서로 돌아가기" 버튼

**`frontend/src/app/report/fail/page.tsx`** — 결제 실패 리다이렉트 랜딩
- URL 쿼리에서 `code`, `message` 파싱
- 에러 메시지 표시 + "감정서로 돌아가기" 버튼

### 기존 파일 변경

**`frontend/src/app/report/page.tsx`** — `handlePurchase(tier)` 수정:
- orderId 생성: `ord_{timestamp}_{reportId}_{tier}`
- localStorage에 `pending_order` 저장: `{ tier, year, month, day, hour, gender }`
- Toss SDK `requestPayment()` 호출:
  ```
  amount: tier === "standard" ? 990 : 9900
  orderId: 위에서 생성한 ID
  orderName: "사주캔들 투자 감정서 (Standard)" 또는 "(Premium)"
  successUrl: {origin}/report/success
  failUrl: {origin}/report/fail
  ```

**`frontend/src/lib/api.ts`** — `confirmPayment()` 함수 추가:
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
}): Promise<PaymentConfirmResponse>
```

### NPM 패키지

`@tosspayments/tosspayments-sdk` — Toss Payments 브라우저 SDK

### 환경변수

| 변수 | 용도 | 테스트 값 |
|------|------|-----------|
| `NEXT_PUBLIC_TOSS_CLIENT_KEY` | 브라우저 SDK 인증 | `test_ck_...` (Toss 개발자센터에서 확인) |

## 4. 에러 처리 & 엣지 케이스

### 금액 위변조 방지
- 서버에서 `tier → amount` 매핑 검증 (`standard=990`, `premium=9900`)
- 클라이언트가 보낸 amount와 tier가 불일치하면 400 에러로 즉시 거부

### 중복 결제 방지
- orderId에 타임스탬프 포함하여 유니크 보장
- 같은 orderId로 재승인 시도 시 Toss API가 자체 거부 (이미 승인된 건이면 승인 응답 반환)

### 결제 성공 후 감정서 생성 실패
- 결제는 확정됐지만 AI 생성이 타임아웃/에러인 경우
- 에러 메시지에 "결제는 완료되었습니다. 다시 시도해 주세요" 안내
- 재시도: 같은 paymentKey/orderId로 `/api/payments/confirm` 재호출
  - Toss는 이미 승인된 건이므로 승인 응답 반환 → 감정서만 재생성

### localStorage 유실
- 브라우저 데이터 삭제 시 봉인 해제 상태 소실됨
- DB 없는 최소 구현의 알려진 제약. 추후 DB 도입 시 해결.

## 5. 가격 정책

| 티어 | 가격 | AI 모델 | 콘텐츠 |
|------|------|---------|--------|
| standard | 990원 | claude-sonnet-4-6 | 전체 7섹션 |
| premium | 9,900원 | claude-opus-4-6 | 전체 7섹션 (더 깊은 분석) |

## 6. 알려진 제약 (DB 없는 최소 구현)

- 결제 기록이 서버에 남지 않음 (Toss 대시보드에서만 확인 가능)
- 사용자 인증 없음 — 누구나 사주 정보 입력하면 결제 가능
- localStorage 삭제 시 재열람 불가 (재결제 필요)
- 환불 처리는 Toss 대시보드에서 수동 처리

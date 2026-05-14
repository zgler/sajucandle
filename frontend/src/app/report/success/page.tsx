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

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

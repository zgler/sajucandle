"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import TabNav from "@/components/TabNav";
import { loadUser } from "@/lib/storage";
import { fetchReport } from "@/lib/api";
import type { UserData, ReportResponse } from "@/lib/types";
import { loadTossPayments } from "@tosspayments/tosspayments-sdk";
import { buildReportId, loadCachedReport, saveCachedReport } from "@/lib/report";
import SectionCard from "@/components/report/SectionCard";
import LoadingAnimation from "@/components/report/LoadingAnimation";

/* ── Main Page ────────────────────────────────────── */
export default function ReportPage() {
  const router = useRouter();
  const [user, setUser] = useState<UserData | null>(null);
  const [report, setReport] = useState<ReportResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [toastVisible, setToastVisible] = useState(false);

  useEffect(() => {
    const u = loadUser();
    if (!u) {
      router.replace("/");
      return;
    }
    setUser(u);

    const reportId = buildReportId(u);
    const cached = loadCachedReport(reportId);
    if (cached) {
      setReport(cached);
      setLoading(false);
      return;
    }

    fetchReport({
      year: u.year,
      month: u.month,
      day: u.day,
      hour: u.hour,
      gender: u.gender,
    })
      .then((data) => {
        setReport(data);
        saveCachedReport(data);
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : "감정서 생성에 실패했습니다.");
      })
      .finally(() => setLoading(false));
  }, [router]);

  function handleRetry() {
    if (!user) return;
    setError(null);
    setLoading(true);
    fetchReport({
      year: user.year,
      month: user.month,
      day: user.day,
      hour: user.hour,
      gender: user.gender,
    })
      .then((data) => {
        setReport(data);
        saveCachedReport(data);
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : "감정서 생성에 실패했습니다.");
      })
      .finally(() => setLoading(false));
  }

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

  const lockedCount = report?.sections.filter((s) => s.locked).length ?? 0;

  return (
    <div className="min-h-screen bg-stone-950">
      <TabNav />

      {/* ─ Page header ─ */}
      <div className="px-5 pt-7 pb-5">
        <div className="flex items-center gap-2.5 mb-1.5">
          {/* Decorative hanja seal */}
          <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-amber-400/90 to-amber-600/90 flex items-center justify-center shadow-lg shadow-amber-500/15 report-header-enter">
            <span className="text-[11px] text-stone-950 font-black font-serif">鑑</span>
          </div>
          <div className="report-header-enter" style={{ animationDelay: "80ms" }}>
            <h1 className="text-lg font-bold text-stone-100 tracking-tight font-serif-ko">
              나의 투자 감정서
            </h1>
          </div>
        </div>
        <div className="report-header-enter ml-[38px]" style={{ animationDelay: "160ms" }}>
          <p className="text-[11px] text-stone-600 tracking-wide">
            {report
              ? `${report.target_year}년 세운 기준 · ${report.tier === "standard" ? "STANDARD" : "PREMIUM"} 감정`
              : "사주 명식 기반 개인 맞춤 투자 분석"}
          </p>
        </div>

        {/* Ornamental divider */}
        <div className="mt-5 flex items-center gap-3 report-header-enter" style={{ animationDelay: "240ms" }}>
          <div className="flex-1 h-px bg-gradient-to-r from-transparent via-stone-800 to-transparent" />
          <span className="text-[10px] text-stone-700 font-serif tracking-[0.3em]">命 理 鑑 定</span>
          <div className="flex-1 h-px bg-gradient-to-r from-transparent via-stone-800 to-transparent" />
        </div>
      </div>

      <div className="px-4 pb-12 space-y-5">
        {/* Loading */}
        {loading && <LoadingAnimation />}

        {/* Error */}
        {error && (
          <div className="ml-3 bg-red-950/30 border border-red-900/40 rounded-2xl p-6 text-center space-y-3">
            <div className="w-10 h-10 mx-auto rounded-full bg-red-950/60 border border-red-900/30 flex items-center justify-center mb-2">
              <span className="text-red-400 text-sm font-serif">凶</span>
            </div>
            <p className="text-sm text-red-300 font-medium">감정서 생성에 실패했습니다</p>
            <p className="text-[12px] text-stone-600 leading-relaxed">{error}</p>
            <button
              onClick={handleRetry}
              className="mt-2 px-6 py-2.5 rounded-xl text-[13px] font-medium text-stone-200 bg-stone-900 border border-stone-700/60 hover:bg-stone-800 hover:border-stone-600 transition-all duration-300"
            >
              다시 시도
            </button>
          </div>
        )}

        {/* Report sections */}
        {report && (
          <>
            {report.sections.map((section, i) => (
              <SectionCard key={section.id} section={section} index={i} />
            ))}

            {/* ─ Paywall CTA ─ */}
            {lockedCount > 0 && (
              <div className="relative -mt-12 pt-16 pb-2 paywall-enter">
                {/* Fade gradient */}
                <div className="absolute inset-x-0 -top-12 h-16 bg-gradient-to-b from-transparent to-stone-950 pointer-events-none" />

                <div className="ml-3 rounded-2xl border border-amber-500/15 overflow-hidden">
                  {/* Decorative top edge */}
                  <div className="h-px w-full bg-gradient-to-r from-transparent via-amber-500/40 to-transparent" />

                  <div className="bg-gradient-to-b from-stone-900/90 to-stone-950/95 backdrop-blur-xl px-6 py-7 text-center">
                    {/* Lock icon */}
                    <div className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-amber-500/[0.07] border border-amber-500/15 text-[11px] text-amber-400/80 font-medium tracking-wide mb-4">
                      <svg className="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                        <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
                        <path d="M7 11V7a5 5 0 0 1 10 0v4" />
                      </svg>
                      {lockedCount}개 섹션 봉인
                    </div>

                    <p className="text-[16px] font-bold text-stone-100 tracking-tight mb-2">
                      감정서 전체를 열람하시겠습니까
                    </p>
                    <p className="text-[12px] text-stone-500 leading-[1.7] mb-6 max-w-[260px] mx-auto">
                      세운 전략 · 월별 타이밍 · 현재 대운<br />
                      투자 스타일 · 투자 함정 분석
                    </p>

                    {/* Tier selection */}
                    <div className="space-y-2.5">
                      <button
                        onClick={() => handlePurchase("standard")}
                        className="group relative w-full py-3.5 rounded-xl font-bold text-stone-950 overflow-hidden transition-all duration-500"
                      >
                        <div className="absolute inset-0 bg-gradient-to-r from-amber-400 via-amber-300 to-amber-400 transition-all duration-500 group-hover:from-amber-300 group-hover:via-amber-200 group-hover:to-amber-300" />
                        <div className="absolute inset-0 paywall-shimmer opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
                        <span className="relative text-[15px] tracking-wide">
                          990원으로 봉인 해제
                        </span>
                      </button>

                      <button
                        onClick={() => handlePurchase("premium")}
                        className="group w-full py-3 rounded-xl font-bold text-amber-300 border border-amber-500/25 hover:border-amber-500/50 hover:bg-amber-500/[0.05] transition-all duration-300"
                      >
                        <span className="text-[13px] tracking-wide">
                          9,900원 · PREMIUM
                        </span>
                        <span className="block text-[10px] text-stone-500 font-normal mt-0.5">
                          Opus 모델 · 더 깊은 분석
                        </span>
                      </button>
                    </div>

                    <p className="text-[10px] text-stone-700 mt-4 leading-relaxed">
                      본 감정서는 명리학적 해석이며 투자 권유가 아닙니다
                    </p>
                  </div>
                </div>
              </div>
            )}

            {/* ─ PDF Download ─ */}
            <div className="ml-3 mt-2 report-section-enter print-hidden" style={{ animationDelay: "840ms" }}>
              <button
                onClick={() => window.print()}
                className="w-full flex items-center justify-center gap-2 py-3 rounded-xl border border-stone-800/60 bg-stone-900/40 hover:bg-stone-900/80 hover:border-stone-700/60 transition-all duration-300 group"
              >
                <svg className="w-4 h-4 text-stone-500 group-hover:text-stone-400 transition-colors" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                  <polyline points="7 10 12 15 17 10" />
                  <line x1="12" y1="15" x2="12" y2="3" />
                </svg>
                <span className="text-[13px] text-stone-500 group-hover:text-stone-400 font-medium tracking-tight transition-colors">
                  PDF로 저장
                </span>
              </button>
            </div>

            {/* ─ Footer seal ─ */}
            <div className="pt-6 pb-4 text-center report-section-enter" style={{ animationDelay: "900ms" }}>
              <div className="flex items-center justify-center gap-3 mb-3">
                <div className="w-12 h-px bg-gradient-to-r from-transparent to-stone-800" />
                <span className="text-stone-700 text-[10px] font-serif tracking-[0.4em]">鑑定完了</span>
                <div className="w-12 h-px bg-gradient-to-l from-transparent to-stone-800" />
              </div>
              <p className="text-[10px] text-stone-800">
                사주캔들 · SAJUCANDLE
              </p>
            </div>
          </>
        )}
      </div>

      {/* Toast */}
      {toastVisible && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 toast-enter">
          <div className="px-5 py-3 rounded-xl bg-stone-900/95 backdrop-blur-md border border-stone-700/60 shadow-2xl shadow-black/40">
            <p className="text-[13px] text-stone-300 whitespace-nowrap">
              결제 기능 준비 중입니다
            </p>
          </div>
        </div>
      )}
    </div>
  );
}

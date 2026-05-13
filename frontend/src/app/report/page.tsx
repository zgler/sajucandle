"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import TabNav from "@/components/TabNav";
import { loadUser } from "@/lib/storage";
import { fetchReport } from "@/lib/api";
import type { UserData, ReportResponse, ReportSection } from "@/lib/types";

const SECTION_ICONS = ["", "Ⅰ", "Ⅱ", "Ⅲ", "Ⅳ", "Ⅴ", "Ⅵ", "Ⅶ"];

const REPORT_CACHE_PREFIX = "saju_report_";

function loadCachedReport(reportId: string): ReportResponse | null {
  try {
    const raw = localStorage.getItem(REPORT_CACHE_PREFIX + reportId);
    if (!raw) return null;
    return JSON.parse(raw) as ReportResponse;
  } catch {
    return null;
  }
}

function saveCachedReport(report: ReportResponse): void {
  try {
    localStorage.setItem(REPORT_CACHE_PREFIX + report.report_id, JSON.stringify(report));
  } catch {
    // storage full or unavailable
  }
}

function buildReportId(user: UserData): string {
  const h = user.hour !== undefined ? String(user.hour).padStart(2, "0") : "00";
  const y = new Date().getFullYear();
  return `rpt_${user.year}${String(user.month).padStart(2, "0")}${String(user.day).padStart(2, "0")}${h}${user.gender}_${y}`;
}

function SectionCard({ section, blurred }: { section: ReportSection; blurred: boolean }) {
  return (
    <div className="relative group">
      <div
        className={`bg-zinc-900/80 backdrop-blur-sm rounded-2xl border border-zinc-800/80 overflow-hidden transition-all duration-500 ${
          blurred ? "select-none" : ""
        }`}
      >
        {/* Section header */}
        <div className="px-5 pt-5 pb-3 flex items-start gap-3">
          <span className="flex-shrink-0 w-8 h-8 rounded-lg bg-gradient-to-br from-amber-500/20 to-amber-600/10 border border-amber-500/20 flex items-center justify-center text-amber-400 text-sm font-bold">
            {SECTION_ICONS[section.id]}
          </span>
          <div className="flex-1 min-w-0">
            <h3 className="text-base font-bold text-zinc-100 tracking-tight">
              {section.title}
            </h3>
            {section.highlight && (
              <div className="mt-2 px-3 py-2 rounded-lg bg-amber-500/8 border border-amber-500/15">
                <p className="text-sm text-amber-300/90 font-medium leading-snug">
                  {section.highlight}
                </p>
              </div>
            )}
          </div>
        </div>

        {/* Section content */}
        <div className={`px-5 pb-5 ${blurred ? "blur-[8px]" : ""}`}>
          <p className="text-sm text-zinc-400 leading-[1.8] whitespace-pre-line">
            {section.content}
          </p>
        </div>
      </div>

      {/* Blur gradient overlay */}
      {blurred && (
        <div className="absolute inset-0 rounded-2xl bg-gradient-to-t from-zinc-950 via-zinc-950/60 to-transparent pointer-events-none" />
      )}
    </div>
  );
}

function LoadingAnimation() {
  return (
    <div className="flex flex-col items-center justify-center py-24 px-4">
      {/* Candle flame animation */}
      <div className="relative w-16 h-24 mb-8">
        {/* Candle body */}
        <div className="absolute bottom-0 left-1/2 -translate-x-1/2 w-8 h-14 rounded-t-sm rounded-b-md bg-gradient-to-b from-amber-200/20 to-amber-200/5 border border-amber-300/10" />
        {/* Wick */}
        <div className="absolute bottom-14 left-1/2 -translate-x-1/2 w-[2px] h-3 bg-zinc-600" />
        {/* Flame outer */}
        <div className="absolute bottom-[60px] left-1/2 -translate-x-1/2 w-5 h-8 rounded-full bg-amber-500/30 animate-pulse" />
        {/* Flame inner */}
        <div className="absolute bottom-[62px] left-1/2 -translate-x-1/2 w-3 h-5 rounded-full bg-amber-400/60 animate-pulse" style={{ animationDelay: "0.15s" }} />
        {/* Flame core */}
        <div className="absolute bottom-[64px] left-1/2 -translate-x-1/2 w-1.5 h-3 rounded-full bg-amber-200/80 animate-pulse" style={{ animationDelay: "0.3s" }} />
        {/* Glow */}
        <div className="absolute bottom-[50px] left-1/2 -translate-x-1/2 w-20 h-20 rounded-full bg-amber-500/5 animate-pulse" />
      </div>

      <p className="text-base font-semibold text-zinc-300 mb-2">감정서 작성 중</p>
      <p className="text-sm text-zinc-500 text-center leading-relaxed">
        사주 원국과 세운을 분석하여<br />
        맞춤 투자 감정서를 생성하고 있습니다
      </p>

      {/* Progress dots */}
      <div className="flex gap-1.5 mt-6">
        {[0, 1, 2].map((i) => (
          <div
            key={i}
            className="w-1.5 h-1.5 rounded-full bg-amber-400/60 animate-bounce"
            style={{ animationDelay: `${i * 0.2}s` }}
          />
        ))}
      </div>
    </div>
  );
}

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

  function handlePurchase() {
    setToastVisible(true);
    setTimeout(() => setToastVisible(false), 2500);
  }

  return (
    <div className="min-h-screen bg-zinc-950">
      <TabNav />

      {/* Page header */}
      <div className="px-4 pt-6 pb-4">
        <div className="flex items-center gap-2 mb-1">
          <div className="w-5 h-5 rounded bg-gradient-to-br from-amber-400 to-amber-600 flex items-center justify-center">
            <span className="text-[10px] text-zinc-950 font-black">鑑</span>
          </div>
          <h1 className="text-lg font-bold text-zinc-100 tracking-tight">
            나의 투자 감정서
          </h1>
        </div>
        <p className="text-xs text-zinc-500 ml-7">
          {report
            ? `${report.target_year}년 기준 · ${report.tier === "standard" ? "Standard" : "Premium"}`
            : "사주 명식 기반 개인 맞춤 투자 분석"}
        </p>
      </div>

      <div className="px-4 pb-10 space-y-4">
        {/* Loading */}
        {loading && <LoadingAnimation />}

        {/* Error */}
        {error && (
          <div className="bg-red-950/40 border border-red-900/50 rounded-2xl p-5 text-center space-y-3">
            <p className="text-sm text-red-400 font-medium">감정서 생성 실패</p>
            <p className="text-xs text-zinc-500 leading-relaxed">{error}</p>
            <button
              onClick={handleRetry}
              className="px-5 py-2 rounded-xl text-sm font-medium text-zinc-100 bg-zinc-800 border border-zinc-700 hover:bg-zinc-700 transition-colors"
            >
              다시 시도
            </button>
          </div>
        )}

        {/* Report sections */}
        {report && (
          <>
            {report.sections.map((section) => (
              <SectionCard
                key={section.id}
                section={section}
                blurred={section.id > 2}
              />
            ))}

            {/* Paywall CTA */}
            <div className="relative -mt-16 pt-20 pb-2">
              <div className="bg-gradient-to-b from-zinc-950/0 via-zinc-950/80 to-zinc-950 absolute inset-x-0 -top-16 h-20 pointer-events-none" />
              <div className="bg-zinc-900/90 backdrop-blur-md rounded-2xl border border-amber-500/20 p-6 text-center space-y-4">
                <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-amber-500/10 border border-amber-500/20 text-xs text-amber-400 font-medium">
                  5개 섹션 잠김
                </div>
                <p className="text-base font-bold text-zinc-100">
                  감정서 전체 보기
                </p>
                <p className="text-xs text-zinc-500 leading-relaxed">
                  세운 전략 · 월별 타이밍 · 대운 분석 · 투자 스타일 · 투자 함정
                </p>
                <button
                  onClick={handlePurchase}
                  className="w-full py-3.5 rounded-xl font-bold text-zinc-950 bg-gradient-to-r from-amber-400 to-amber-500 hover:from-amber-300 hover:to-amber-400 transition-all duration-300 shadow-lg shadow-amber-500/20"
                >
                  4,900원으로 잠금 해제
                </button>
                <p className="text-[10px] text-zinc-600">
                  명리학 기반 해석이며 투자 권유가 아닙니다
                </p>
              </div>
            </div>
          </>
        )}
      </div>

      {/* Toast */}
      {toastVisible && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 px-5 py-3 rounded-xl bg-zinc-800 border border-zinc-700 text-sm text-zinc-300 shadow-xl animate-fade-in z-50">
          결제 기능 준비 중입니다
        </div>
      )}
    </div>
  );
}

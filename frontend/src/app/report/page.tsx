"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import TabNav from "@/components/TabNav";
import { loadUser } from "@/lib/storage";
import { fetchReport } from "@/lib/api";
import type { UserData, ReportResponse, ReportSection } from "@/lib/types";

/* ── 오행 accent per section ─────────────────────── */
const SECTION_META: Record<
  number,
  { icon: string; hanja: string; accent: string; accentBg: string; accentBorder: string; glowColor: string }
> = {
  1: { icon: "Ⅰ",  hanja: "命", accent: "text-amber-300",  accentBg: "bg-amber-500/8",   accentBorder: "border-amber-500/15", glowColor: "rgba(245,158,11,0.06)" },
  2: { icon: "Ⅱ",  hanja: "性", accent: "text-emerald-300", accentBg: "bg-emerald-500/8",  accentBorder: "border-emerald-500/15", glowColor: "rgba(16,185,129,0.06)" },
  3: { icon: "Ⅲ",  hanja: "運", accent: "text-sky-300",     accentBg: "bg-sky-500/8",      accentBorder: "border-sky-500/15", glowColor: "rgba(56,189,248,0.06)" },
  4: { icon: "Ⅳ",  hanja: "時", accent: "text-violet-300",  accentBg: "bg-violet-500/8",   accentBorder: "border-violet-500/15", glowColor: "rgba(139,92,246,0.06)" },
  5: { icon: "Ⅴ",  hanja: "勢", accent: "text-rose-300",    accentBg: "bg-rose-500/8",     accentBorder: "border-rose-500/15", glowColor: "rgba(244,63,94,0.06)" },
  6: { icon: "Ⅵ",  hanja: "策", accent: "text-teal-300",    accentBg: "bg-teal-500/8",     accentBorder: "border-teal-500/15", glowColor: "rgba(20,184,166,0.06)" },
  7: { icon: "Ⅶ",  hanja: "戒", accent: "text-orange-300",  accentBg: "bg-orange-500/8",   accentBorder: "border-orange-500/15", glowColor: "rgba(251,146,60,0.06)" },
};

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

/* ── Section Card ─────────────────────────────────── */
function SectionCard({ section, index }: { section: ReportSection; index: number }) {
  const meta = SECTION_META[section.id] ?? SECTION_META[1];
  const locked = section.locked;

  return (
    <div
      className="report-section-enter relative group"
      style={{ animationDelay: `${index * 120}ms` }}
    >
      {/* Decorative vertical accent line */}
      <div
        className={`absolute left-0 top-6 bottom-6 w-[2px] rounded-full transition-all duration-700 ${
          locked ? "opacity-20" : "opacity-60"
        }`}
        style={{ background: `linear-gradient(to bottom, transparent, ${meta.glowColor.replace("0.06", "0.8")}, transparent)` }}
      />

      <div
        className={`ml-3 rounded-2xl border overflow-hidden transition-all duration-500 ${
          locked
            ? "bg-stone-950/60 border-stone-800/40 select-none"
            : "bg-stone-950/80 border-stone-800/60"
        }`}
        style={!locked ? { boxShadow: `0 0 40px ${meta.glowColor}` } : undefined}
      >
        {/* ─ Header ─ */}
        <div className="px-5 pt-5 pb-3">
          <div className="flex items-start gap-3.5">
            {/* Hanja badge */}
            <div className="flex-shrink-0 relative">
              <div className={`w-10 h-10 rounded-xl flex items-center justify-center border ${
                locked ? "bg-stone-900/60 border-stone-700/30" : "bg-stone-900/80 border-stone-700/50"
              }`}>
                <span className={`text-lg font-serif leading-none ${locked ? "text-stone-600" : meta.accent} transition-colors`}>
                  {meta.hanja}
                </span>
              </div>
              <span className={`absolute -bottom-1 -right-1 text-[9px] font-bold tracking-wider ${
                locked ? "text-stone-700" : "text-stone-500"
              }`}>
                {meta.icon}
              </span>
            </div>

            {/* Title + highlight */}
            <div className="flex-1 min-w-0 pt-0.5">
              <h3 className={`text-[15px] font-bold tracking-tight transition-colors ${
                locked ? "text-stone-500" : "text-stone-200"
              }`}>
                {section.title}
              </h3>
              {section.highlight && (
                <div className={`mt-2.5 px-3.5 py-2.5 rounded-lg border ${
                  locked
                    ? "bg-stone-900/30 border-stone-800/30"
                    : `${meta.accentBg} ${meta.accentBorder}`
                }`}>
                  <p className={`text-[13px] font-medium leading-[1.6] ${
                    locked ? "text-stone-600" : meta.accent
                  }`}>
                    {locked ? "잠금 해제 후 확인할 수 있습니다" : section.highlight}
                  </p>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* ─ Content ─ */}
        <div className={`px-5 pb-5 ${locked ? "blur-[6px] opacity-30" : ""}`}>
          <div className="report-content-text text-[13px] text-stone-400 leading-[2] whitespace-pre-line">
            {locked ? (
              <p>
                이 섹션은 프리미엄 감정서에 포함된 분석입니다.
                사주 원국의 깊은 해석과 맞춤 투자 전략을 담고 있습니다.
                잠금을 해제하여 전체 내용을 확인하세요.
              </p>
            ) : (
              section.content
            )}
          </div>
        </div>
      </div>

      {/* Sealed overlay for locked */}
      {locked && (
        <div className="absolute inset-0 ml-3 rounded-2xl overflow-hidden pointer-events-none">
          <div className="absolute inset-0 bg-gradient-to-t from-stone-950 via-stone-950/50 to-transparent" />
          {/* Seal stamp */}
          <div className="absolute bottom-4 right-4 w-10 h-10 rounded-full border border-stone-700/40 flex items-center justify-center rotate-[-12deg] opacity-30">
            <span className="text-stone-500 text-xs font-serif">封</span>
          </div>
        </div>
      )}
    </div>
  );
}

/* ── Loading Animation ────────────────────────────── */
function LoadingAnimation() {
  return (
    <div className="flex flex-col items-center justify-center py-28 px-4">
      {/* Candle assembly */}
      <div className="relative w-20 h-32 mb-10">
        {/* Ambient glow */}
        <div className="absolute bottom-8 left-1/2 -translate-x-1/2 w-32 h-32 rounded-full bg-amber-500/[0.04] flame-glow" />

        {/* Candle body */}
        <div className="absolute bottom-0 left-1/2 -translate-x-1/2 w-7 h-16 rounded-t-sm rounded-b-lg overflow-hidden">
          <div className="absolute inset-0 bg-gradient-to-b from-stone-300/15 to-stone-400/5" />
          <div className="absolute inset-0 bg-gradient-to-r from-transparent via-stone-200/5 to-transparent" />
        </div>

        {/* Wick */}
        <div className="absolute bottom-[64px] left-1/2 -translate-x-1/2 w-[1.5px] h-3 bg-stone-600 rounded-full" />

        {/* Flame layers */}
        <div className="flame-flicker absolute bottom-[72px] left-1/2 -translate-x-1/2">
          <div className="w-6 h-10 rounded-full bg-amber-500/20 blur-[2px]" />
        </div>
        <div className="flame-flicker-delayed absolute bottom-[74px] left-1/2 -translate-x-1/2">
          <div className="w-4 h-7 rounded-full bg-amber-400/40 blur-[1px]" />
        </div>
        <div className="flame-flicker absolute bottom-[76px] left-1/2 -translate-x-1/2">
          <div className="w-2 h-4 rounded-full bg-amber-200/70" />
        </div>
      </div>

      <p className="text-[15px] font-semibold text-stone-300 mb-2.5 tracking-tight">
        감정서를 작성하고 있습니다
      </p>
      <p className="text-[13px] text-stone-600 text-center leading-relaxed max-w-[240px]">
        사주 명식과 올해 세운을 교차 분석하여 맞춤 투자 감정서를 생성합니다
      </p>

      {/* Ink dots loading */}
      <div className="flex gap-2 mt-8">
        {[0, 1, 2, 3].map((i) => (
          <div
            key={i}
            className="w-1 h-1 rounded-full bg-amber-400/50 ink-dot"
            style={{ animationDelay: `${i * 300}ms` }}
          />
        ))}
      </div>

      {/* Elapsed time */}
      <ElapsedTime />
    </div>
  );
}

function ElapsedTime() {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    const interval = setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => clearInterval(interval);
  }, []);

  if (seconds < 10) return null;

  const min = Math.floor(seconds / 60);
  const sec = seconds % 60;
  return (
    <p className="text-[11px] text-stone-700 mt-4 tabular-nums">
      {min > 0 ? `${min}분 ` : ""}{sec}초 경과
    </p>
  );
}

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

  function handlePurchase(tier: "standard" | "premium") {
    // TODO: 결제 연동 후 실제 결제 플로우로 교체
    console.log(`Purchase requested: ${tier}`);
    setToastVisible(true);
    setTimeout(() => setToastVisible(false), 2500);
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

"use client";

import type { ReportSection } from "@/lib/types";

export const SECTION_META: Record<
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

export default function SectionCard({ section, index }: { section: ReportSection; index: number }) {
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

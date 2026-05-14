"use client";

import { useState, useEffect } from "react";

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

export default function LoadingAnimation() {
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

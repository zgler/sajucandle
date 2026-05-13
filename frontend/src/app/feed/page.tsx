"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import TabNav from "@/components/TabNav";
import DailyFortune from "@/components/DailyFortune";
import FortuneDetail from "@/components/FortuneDetail";
import { loadUser } from "@/lib/storage";
import { fetchDailyFortune } from "@/lib/api";
import type { DailyFortuneResponse } from "@/lib/types";

export default function FeedPage() {
  const router = useRouter();
  const [fortune, setFortune] = useState<DailyFortuneResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const user = loadUser();
    if (!user) {
      router.replace("/");
      return;
    }
    fetchDailyFortune({
      year: user.year,
      month: user.month,
      day: user.day,
      hour: user.hour,
      gender: user.gender,
    })
      .then(setFortune)
      .catch((err) => setError(err instanceof Error ? err.message : "오류가 발생했습니다."))
      .finally(() => setLoading(false));
  }, [router]);

  return (
    <div className="min-h-screen bg-zinc-950">
      <TabNav />

      <div className="px-4 py-5 space-y-4 pb-10">
        {loading && (
          <div className="flex items-center justify-center py-20">
            <div className="w-8 h-8 border-2 border-zinc-700 border-t-amber-500 rounded-full animate-spin" />
          </div>
        )}

        {error && (
          <div className="bg-red-950/50 border border-red-800 text-red-400 text-sm rounded-xl px-4 py-4">
            <p className="font-medium mb-1">데이터 로드 실패</p>
            <p className="text-xs">{error}</p>
            <p className="text-xs mt-2 text-red-500">백엔드 서버가 실행 중인지 확인하세요.</p>
          </div>
        )}

        {fortune && (
          <>
            <DailyFortune fortune={fortune} />
            <FortuneDetail fortune={fortune} />

            {/* Signal Placeholder Card */}
            <div className="bg-zinc-900 rounded-2xl p-5 border border-zinc-800 border-dashed">
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-sm font-semibold text-zinc-400 uppercase tracking-wide">
                  이달의 종목 시그널
                </h3>
                <span className="text-xs bg-zinc-800 text-zinc-500 px-2 py-0.5 rounded-full">
                  준비중
                </span>
              </div>
              <p className="text-sm text-zinc-600 leading-relaxed">
                사주 필터 기반 월간 시그널 (BUY / HOLD / SELL) 기능이 곧 오픈됩니다.
                <br />
                <span className="text-zinc-700">사주 C 필터 · 퀀트 랭킹 · 레짐 감지</span>
              </p>
              <div className="mt-4 flex gap-2">
                {["BUY", "HOLD", "WATCH"].map((sig) => (
                  <span
                    key={sig}
                    className="text-xs px-2.5 py-1 rounded-full bg-zinc-800 text-zinc-600"
                  >
                    {sig === "BUY" ? "매수" : sig === "HOLD" ? "유지" : "관망"}
                  </span>
                ))}
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

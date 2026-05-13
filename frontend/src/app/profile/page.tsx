"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import TabNav from "@/components/TabNav";
import ProfileCard from "@/components/ProfileCard";
import { loadUser, clearUser } from "@/lib/storage";
import { fetchYearlyFortune } from "@/lib/api";
import { shareKakao } from "@/lib/kakao";
import type { UserData, YearlyFortuneResponse } from "@/lib/types";

export default function ProfilePage() {
  const router = useRouter();
  const [user, setUser] = useState<UserData | null>(null);
  const [yearly, setYearly] = useState<YearlyFortuneResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const u = loadUser();
    if (!u) {
      router.replace("/");
      return;
    }
    setUser(u);
    fetchYearlyFortune({
      year: u.year,
      month: u.month,
      day: u.day,
      hour: u.hour,
      gender: u.gender,
    })
      .then(setYearly)
      .catch((err) => setError(err instanceof Error ? err.message : "오류가 발생했습니다."))
      .finally(() => setLoading(false));
  }, [router]);

  function handleShare() {
    if (!user?.profile) return;
    const shareUrl = `${window.location.origin}/card/${encodeURIComponent(
      user.profile.investor_type
    )}`;
    shareKakao(
      shareUrl,
      "사주캔들 — 나의 투자 체질",
      `나는 ${user.profile.investor_type}! 사주로 알아보는 나의 투자 성향`
    );
  }

  function handleReset() {
    if (confirm("사주 정보를 초기화하고 처음부터 시작할까요?")) {
      clearUser();
      router.replace("/");
    }
  }

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
          </div>
        )}

        {user?.profile && (
          <ProfileCard profile={user.profile} />
        )}

        {yearly && (
          <>
            {/* Yearly outlook */}
            <div className="bg-zinc-900 rounded-2xl p-5 border border-zinc-800 space-y-4">
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-semibold text-zinc-200 uppercase tracking-wide">
                  {yearly.year}년 세운 흐름
                </h3>
                <span className="text-xs bg-zinc-800 text-zinc-400 px-2 py-0.5 rounded-full">
                  {yearly.sewoon_stem}{yearly.sewoon_branch} · {yearly.sewoon_element}
                </span>
              </div>
              <p className="text-sm text-zinc-400 leading-relaxed">{yearly.yearly_outlook}</p>

              {/* Monthly tips */}
              {yearly.monthly_tips && yearly.monthly_tips.length > 0 && (
                <div className="space-y-2">
                  <p className="text-xs text-zinc-500 uppercase tracking-wide">월별 포인트</p>
                  {yearly.monthly_tips.map((tip, i) => (
                    <div
                      key={i}
                      className="flex gap-2 text-sm text-zinc-300 bg-zinc-800/50 rounded-lg px-3 py-2"
                    >
                      <span className="text-amber-400 flex-shrink-0">{i + 1}월</span>
                      <span>{tip}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Daeun */}
            <div className="bg-zinc-900 rounded-2xl p-5 border border-zinc-800 space-y-3">
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-semibold text-zinc-200 uppercase tracking-wide">
                  현재 대운
                </h3>
                <span className="text-xs bg-zinc-800 text-zinc-400 px-2 py-0.5 rounded-full">
                  {yearly.daeun_stem}{yearly.daeun_branch} · {yearly.daeun_element}
                </span>
              </div>
              <p className="text-xs text-zinc-500">만 {yearly.daeun_start_age}세부터 시작된 대운</p>
              <p className="text-sm text-zinc-400 leading-relaxed">{yearly.daeun_description}</p>
            </div>
          </>
        )}

        {/* Report CTA */}
        <button
          onClick={() => router.push("/report")}
          className="w-full bg-gradient-to-br from-zinc-900 to-zinc-900/80 rounded-2xl p-5 border border-amber-500/15 hover:border-amber-500/30 transition-all duration-300 text-left group"
        >
          <div className="flex items-start gap-3">
            <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-amber-400 to-amber-600 flex items-center justify-center flex-shrink-0">
              <span className="text-xs text-zinc-950 font-black">鑑</span>
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-bold text-zinc-100 mb-0.5">나의 투자 감정서</p>
              <p className="text-xs text-zinc-500">사주로 읽는 {new Date().getFullYear()}년 투자 전략</p>
            </div>
            <span className="text-zinc-600 group-hover:text-amber-400 transition-colors text-lg mt-1">
              &rsaquo;
            </span>
          </div>
        </button>

        {/* Actions */}
        <div className="space-y-3 pt-2">
          <button
            onClick={handleShare}
            className="w-full py-3 rounded-xl font-medium text-zinc-950 bg-amber-500 hover:bg-amber-400 transition-colors"
          >
            카카오톡으로 공유하기
          </button>
          <button
            onClick={handleReset}
            className="w-full py-3 rounded-xl font-medium text-zinc-500 bg-zinc-900 border border-zinc-800 hover:text-zinc-300 hover:border-zinc-700 transition-colors text-sm"
          >
            사주 정보 초기화
          </button>
        </div>

        <p className="text-center text-xs text-zinc-600 pb-4">
          본 콘텐츠는 오락 목적이며 투자 조언이 아닙니다.
        </p>
      </div>
    </div>
  );
}

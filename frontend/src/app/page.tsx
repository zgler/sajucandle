"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import OnboardingForm from "@/components/OnboardingForm";
import ProfileCard from "@/components/ProfileCard";
import { loadUser, saveUser } from "@/lib/storage";
import type { ProfileResponse, UserData } from "@/lib/types";

export default function Home() {
  const router = useRouter();
  const [profile, setProfile] = useState<ProfileResponse | null>(null);
  const [userData, setUserData] = useState<UserData | null>(null);
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    const user = loadUser();
    if (user) {
      // Already onboarded — go to feed
      router.replace("/feed");
    } else {
      setChecked(true);
    }
  }, [router]);

  function handleOnboardingComplete(user: UserData, p: ProfileResponse) {
    const updated: UserData = { ...user, profile: p };
    saveUser(updated);
    setUserData(updated);
    setProfile(p);
  }

  function handleGoToFeed() {
    router.push("/feed");
  }

  if (!checked && !profile) {
    return (
      <div className="min-h-screen bg-zinc-950 flex items-center justify-center">
        <div className="w-8 h-8 border-2 border-zinc-700 border-t-amber-500 rounded-full animate-spin" />
      </div>
    );
  }

  if (profile && userData) {
    return (
      <div className="min-h-screen bg-zinc-950 px-4 py-8 space-y-6">
        {/* Header */}
        <div className="text-center">
          <div className="text-4xl mb-2">🕯️</div>
          <h1 className="text-xl font-bold text-zinc-100">분석 완료!</h1>
          <p className="text-zinc-400 text-sm mt-1">나의 투자 체질을 확인해보세요</p>
        </div>

        <ProfileCard profile={profile} />

        {/* CTA */}
        <button
          onClick={handleGoToFeed}
          className="w-full py-3.5 rounded-xl font-semibold text-zinc-950 bg-gradient-to-r from-amber-400 to-amber-600 hover:from-amber-300 hover:to-amber-500 transition-all shadow-lg shadow-amber-500/25 text-base"
        >
          매일 운세 보러가기 →
        </button>
      </div>
    );
  }

  return <OnboardingForm onComplete={handleOnboardingComplete} />;
}

"use client";

import { useState, FormEvent } from "react";
import { fetchProfile } from "@/lib/api";
import { saveUser } from "@/lib/storage";
import type { ProfileResponse, UserData } from "@/lib/types";

interface Props {
  onComplete: (user: UserData, profile: ProfileResponse) => void;
}

export default function OnboardingForm({ onComplete }: Props) {
  const [year, setYear] = useState("");
  const [month, setMonth] = useState("");
  const [day, setDay] = useState("");
  const [hour, setHour] = useState("unknown");
  const [gender, setGender] = useState<"M" | "F">("M");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const params = {
        year: Number(year),
        month: Number(month),
        day: Number(day),
        hour: hour === "unknown" ? undefined : Number(hour),
        gender,
      };
      const profile = await fetchProfile(params);
      const userData: UserData = { ...params, profile };
      saveUser(userData);
      onComplete(userData, profile);
    } catch (err) {
      setError(err instanceof Error ? err.message : "오류가 발생했습니다.");
    } finally {
      setLoading(false);
    }
  }

  const yearOptions = Array.from({ length: 91 }, (_, i) => 2010 - i);
  const monthOptions = Array.from({ length: 12 }, (_, i) => i + 1);
  const dayOptions = Array.from({ length: 31 }, (_, i) => i + 1);
  const hourOptions = Array.from({ length: 24 }, (_, i) => i);

  const selectClass =
    "w-full bg-zinc-800 border border-zinc-700 text-zinc-100 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-amber-500 focus:border-transparent";

  return (
    <div className="min-h-screen bg-zinc-950 flex items-center justify-center px-4">
      <div className="w-full max-w-md">
        {/* Header */}
        <div className="text-center mb-8">
          <div className="text-5xl mb-3">🕯️</div>
          <h1 className="text-2xl font-bold text-zinc-100 mb-1">사주캔들</h1>
          <p className="text-zinc-400 text-sm">사주로 읽는 나의 투자 체질</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-5">
          {/* Birth Year */}
          <div>
            <label className="block text-xs font-medium text-zinc-400 mb-1.5 uppercase tracking-wide">
              출생연도
            </label>
            <select
              value={year}
              onChange={(e) => setYear(e.target.value)}
              required
              className={selectClass}
            >
              <option value="">연도 선택</option>
              {yearOptions.map((y) => (
                <option key={y} value={y}>
                  {y}년
                </option>
              ))}
            </select>
          </div>

          {/* Birth Month & Day */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-zinc-400 mb-1.5 uppercase tracking-wide">
                월
              </label>
              <select
                value={month}
                onChange={(e) => setMonth(e.target.value)}
                required
                className={selectClass}
              >
                <option value="">월 선택</option>
                {monthOptions.map((m) => (
                  <option key={m} value={m}>
                    {m}월
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-zinc-400 mb-1.5 uppercase tracking-wide">
                일
              </label>
              <select
                value={day}
                onChange={(e) => setDay(e.target.value)}
                required
                className={selectClass}
              >
                <option value="">일 선택</option>
                {dayOptions.map((d) => (
                  <option key={d} value={d}>
                    {d}일
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* Birth Hour */}
          <div>
            <label className="block text-xs font-medium text-zinc-400 mb-1.5 uppercase tracking-wide">
              태어난 시간 (선택)
            </label>
            <select
              value={hour}
              onChange={(e) => setHour(e.target.value)}
              className={selectClass}
            >
              <option value="unknown">모름</option>
              {hourOptions.map((h) => (
                <option key={h} value={h}>
                  {String(h).padStart(2, "0")}시
                </option>
              ))}
            </select>
          </div>

          {/* Gender */}
          <div>
            <label className="block text-xs font-medium text-zinc-400 mb-1.5 uppercase tracking-wide">
              성별
            </label>
            <div className="grid grid-cols-2 gap-3">
              {(["M", "F"] as const).map((g) => (
                <button
                  key={g}
                  type="button"
                  onClick={() => setGender(g)}
                  className={`py-2.5 rounded-lg text-sm font-medium transition-all ${
                    gender === g
                      ? "bg-amber-500 text-zinc-950 shadow-lg shadow-amber-500/20"
                      : "bg-zinc-800 text-zinc-400 border border-zinc-700 hover:border-zinc-500"
                  }`}
                >
                  {g === "M" ? "남성" : "여성"}
                </button>
              ))}
            </div>
          </div>

          {/* Error */}
          {error && (
            <div className="bg-red-950/50 border border-red-800 text-red-400 text-sm rounded-lg px-4 py-3">
              {error}
            </div>
          )}

          {/* Submit */}
          <button
            type="submit"
            disabled={loading}
            className="w-full py-3.5 rounded-xl font-semibold text-zinc-950 bg-gradient-to-r from-amber-400 to-amber-600 hover:from-amber-300 hover:to-amber-500 transition-all shadow-lg shadow-amber-500/25 disabled:opacity-50 disabled:cursor-not-allowed text-base mt-2"
          >
            {loading ? (
              <span className="flex items-center justify-center gap-2">
                <span className="w-4 h-4 border-2 border-zinc-950/30 border-t-zinc-950 rounded-full animate-spin" />
                분석 중...
              </span>
            ) : (
              "내 투자 체질 알아보기"
            )}
          </button>
        </form>

        <p className="text-center text-xs text-zinc-600 mt-6">
          본 서비스는 오락 목적이며 투자 조언이 아닙니다.
        </p>
      </div>
    </div>
  );
}

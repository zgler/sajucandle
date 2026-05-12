import type { ProfileResponse } from "@/lib/types";
import PillarChart from "./PillarChart";
import ElementBar from "./ElementBar";

interface Props {
  profile: ProfileResponse;
  compact?: boolean;
}

export default function ProfileCard({ profile, compact = false }: Props) {
  return (
    <div className="bg-zinc-900 rounded-2xl p-5 space-y-5 border border-zinc-800">
      {/* Investor Type */}
      <div className="text-center">
        <p className="text-xs text-zinc-500 uppercase tracking-wide mb-1">
          투자 체질
        </p>
        <h2 className="text-xl font-bold text-amber-400">{profile.investor_type}</h2>
        <p className="text-sm text-zinc-400 mt-1 leading-relaxed">
          {profile.day_master_description}
        </p>
      </div>

      {/* 4 Pillars */}
      <div>
        <p className="text-xs text-zinc-500 uppercase tracking-wide mb-3 text-center">
          사주 원국
        </p>
        <PillarChart pillars={profile.pillars} />
      </div>

      {/* Element Distribution */}
      <ElementBar distribution={profile.element_distribution} />

      {!compact && (
        <>
          {/* Strengths / Weaknesses */}
          <div className="grid grid-cols-2 gap-3">
            <div className="bg-green-950/30 rounded-xl p-3 border border-green-900/40">
              <p className="text-xs text-green-400 font-medium mb-2">강점</p>
              <ul className="space-y-1">
                {profile.strengths.map((s, i) => (
                  <li key={i} className="text-xs text-zinc-300 flex gap-1.5">
                    <span className="text-green-400 mt-0.5">▸</span>
                    {s}
                  </li>
                ))}
              </ul>
            </div>
            <div className="bg-red-950/30 rounded-xl p-3 border border-red-900/40">
              <p className="text-xs text-red-400 font-medium mb-2">약점</p>
              <ul className="space-y-1">
                {profile.weaknesses.map((w, i) => (
                  <li key={i} className="text-xs text-zinc-300 flex gap-1.5">
                    <span className="text-red-400 mt-0.5">▸</span>
                    {w}
                  </li>
                ))}
              </ul>
            </div>
          </div>

          {/* Risk Score */}
          <div>
            <div className="flex justify-between items-center mb-1.5">
              <p className="text-xs text-zinc-500 uppercase tracking-wide">
                리스크 성향
              </p>
              <span className="text-sm font-bold text-zinc-100">
                {profile.risk_score}
                <span className="text-xs text-zinc-500 font-normal">/100</span>
              </span>
            </div>
            <div className="bg-zinc-800 rounded-full h-2">
              <div
                className="h-2 rounded-full bg-gradient-to-r from-green-500 via-yellow-500 to-red-500 transition-all duration-700"
                style={{ width: `${profile.risk_score}%` }}
              />
            </div>
            <div className="flex justify-between mt-1">
              <span className="text-xs text-zinc-600">안정형</span>
              <span className="text-xs text-zinc-600">공격형</span>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

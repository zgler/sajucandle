"use client";

interface Props {
  symbol: string;
}

function ScoreBar({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div className="mb-2.5">
      <div className="flex justify-between mb-1">
        <span className="text-zinc-400 text-xs">{label}</span>
        <span className={`text-xs font-bold ${color}`}>{value}</span>
      </div>
      <div className="h-1.5 bg-zinc-800 rounded-full">
        <div
          className="h-1.5 rounded-full"
          style={{ width: `${value}%`, background: value >= 60 ? "#4ade80" : "#fbbf24" }}
        />
      </div>
    </div>
  );
}

export default function AnalysisDashboard({ symbol }: Props) {
  const handleCta = () => {
    alert("구독 서비스 준비 중입니다. 곧 만나요!");
  };

  return (
    <div>
      {/* 퀀트 분석 — 블러 */}
      <div className="px-4 py-3.5 bg-zinc-900 border-t border-zinc-800/50">
        <div className="flex items-center gap-2 mb-3">
          <span className="text-white text-sm font-bold">퀀트 분석</span>
          <span className="text-[9px] px-1.5 py-0.5 rounded bg-amber-400/20 text-amber-400">PRO</span>
        </div>
        <div className="blur-[6px] pointer-events-none select-none">
          <ScoreBar label="기술지표 (TA)" value={72} color="text-green-400" />
          <ScoreBar label="거시지표 (Macro)" value={58} color="text-amber-400" />
          <ScoreBar label="펀더멘털 (FA)" value={81} color="text-green-400" />
        </div>
      </div>

      {/* 시그널 이력 — 블러 */}
      <div className="px-4 py-3.5 bg-zinc-900 border-t border-zinc-800/30">
        <div className="text-white text-sm font-bold mb-2.5">시그널 이력</div>
        <div className="blur-[5px] pointer-events-none select-none">
          <div className="flex gap-1.5 flex-wrap">
            {["5월 BUY", "4월 HOLD", "3월 BUY", "2월 WATCH", "1월 SELL", "12월 BUY"].map((t, i) => {
              const color = t.includes("BUY")
                ? "bg-green-400/10 text-green-400"
                : t.includes("SELL")
                ? "bg-red-400/10 text-red-400"
                : "bg-amber-400/10 text-amber-400";
              return (
                <span key={i} className={`text-[11px] px-2.5 py-1 rounded-md font-medium ${color}`}>
                  {t}
                </span>
              );
            })}
          </div>
        </div>
      </div>

      {/* 기술지표 세부 — 블러 */}
      <div className="px-4 py-3.5 bg-zinc-900 border-t border-zinc-800/30">
        <div className="text-white text-sm font-bold mb-2.5">기술지표 세부</div>
        <div className="blur-[5px] pointer-events-none select-none text-xs text-zinc-400">
          {[
            ["Supertrend (10,3)", "▲ 상승", "text-green-400"],
            ["RSI (14)", "58.3", "text-amber-400"],
            ["MACD 히스토그램", "+ 양전환", "text-green-400"],
            ["MA 정배열 (20/60/200)", "✓", "text-green-400"],
            ["거래량 추세", "1.4x", "text-green-400"],
          ].map(([label, value, color], i) => (
            <div key={i} className="flex justify-between py-1 border-b border-zinc-800/50 last:border-b-0">
              <span>{label}</span>
              <span className={`font-semibold ${color}`}>{value}</span>
            </div>
          ))}
        </div>
      </div>

      {/* 종목 순위 — 블러 */}
      <div className="px-4 py-3 bg-zinc-800/50 border-t border-zinc-800/30">
        <div className="blur-[5px] pointer-events-none select-none flex justify-between items-center">
          <span className="text-zinc-400 text-xs">필터 통과 종목 중 순위</span>
          <span className="text-amber-400 text-xl font-bold">#3 / 17</span>
        </div>
      </div>

      {/* CTA */}
      <div className="px-4 py-6 text-center bg-gradient-to-b from-zinc-900 to-zinc-950 border-t-2 border-amber-400/30">
        <div className="text-amber-400 text-base font-bold mb-1">🔓 상세 분석 잠금 해제</div>
        <div className="text-zinc-500 text-xs mb-4">
          퀀트 점수 · 기술지표 · 시그널 이력 · 종목 순위
        </div>
        <button
          onClick={handleCta}
          className="bg-gradient-to-r from-amber-400 to-amber-500 text-black px-8 py-3 rounded-lg text-sm font-bold shadow-lg shadow-amber-400/30"
        >
          월 4,900원 구독
        </button>
        <div className="text-zinc-600 text-[10px] mt-2.5">전 종목 무제한 분석</div>
      </div>
    </div>
  );
}

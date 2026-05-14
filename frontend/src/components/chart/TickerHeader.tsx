"use client";

import type { ChartOhlcvResponse } from "@/lib/chart-types";

interface Props {
  data: ChartOhlcvResponse;
}

const SIGNAL_COLORS: Record<string, string> = {
  BUY: "text-green-400 bg-green-400/10 border-green-400/30",
  HOLD: "text-amber-400 bg-amber-400/10 border-amber-400/30",
  SELL: "text-red-400 bg-red-400/10 border-red-400/30",
  WATCH: "text-amber-400 bg-amber-400/10 border-amber-400/30",
  KILL: "text-red-400 bg-red-400/10 border-red-400/30",
};

export default function TickerHeader({ data }: Props) {
  const changeColor = data.price_change_pct >= 0 ? "text-green-400" : "text-red-400";
  const changeSign = data.price_change_pct >= 0 ? "+" : "";

  // 사주 필터 뱃지
  let filterBadge: React.ReactNode;
  if (data.saju_filter.passed === true) {
    filterBadge = (
      <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-green-400/10 border border-green-400/20">
        <span className="text-sm">✅</span>
        <div>
          <div className="text-green-400 text-xs font-bold">사주 필터 통과</div>
          <div className="text-green-400/60 text-[10px]">내 명식과 상충 없음</div>
        </div>
      </div>
    );
  } else if (data.saju_filter.passed === false) {
    filterBadge = (
      <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-red-400/10 border border-red-400/20">
        <span className="text-sm">❌</span>
        <div>
          <div className="text-red-400 text-xs font-bold">사주 필터 탈락</div>
          <div className="text-red-400/60 text-[10px]">명식 상충 감지</div>
        </div>
      </div>
    );
  } else {
    filterBadge = (
      <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-zinc-700/30 border border-zinc-700/40">
        <span className="text-sm">⚠️</span>
        <div>
          <div className="text-zinc-400 text-xs font-bold">판정 불가</div>
          <div className="text-zinc-500 text-[10px]">상장일 미상</div>
        </div>
      </div>
    );
  }

  return (
    <div className="px-4 py-4 bg-gradient-to-br from-zinc-900 to-zinc-950">
      {/* 종목 이름 */}
      <div className="flex items-center gap-3 mb-2">
        <div className="w-9 h-9 rounded-lg bg-amber-400/10 border border-amber-400/30 flex items-center justify-center text-[10px] text-amber-400 font-bold">
          {data.symbol.slice(0, 2)}
        </div>
        <div>
          <div className="text-white text-lg font-bold tracking-tight">{data.name}</div>
          <div className="text-zinc-500 text-xs">
            {data.symbol} · {data.asset_class === "coin" ? "Crypto" : "Stock"}
          </div>
        </div>
      </div>

      {/* 가격 */}
      <div className="flex items-baseline gap-2 mb-3">
        <span className="text-white text-2xl font-bold tracking-tight">
          {data.asset_class === "coin" ? "" : "$"}{data.current_price.toLocaleString()}
        </span>
        <span className={`text-sm font-semibold ${changeColor}`}>
          {changeSign}{data.price_change_pct}%
        </span>
      </div>

      {/* 뱃지 */}
      <div className="flex gap-2 flex-wrap">
        {filterBadge}
        {data.current_signal ? (
          <div className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg border ${SIGNAL_COLORS[data.current_signal] || "text-zinc-400 bg-zinc-700/30 border-zinc-700/40"}`}>
            <span className="text-sm">📊</span>
            <div>
              <div className="text-xs font-bold">{data.current_signal}</div>
              <div className="text-[10px] opacity-60">
                {new Date().getMonth() + 1}월 시그널
              </div>
            </div>
          </div>
        ) : (
          <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-zinc-700/30 border border-zinc-700/40">
            <span className="text-sm">📊</span>
            <div>
              <div className="text-zinc-500 text-xs font-bold">시그널 미지원</div>
              <div className="text-zinc-600 text-[10px]">미등록 종목</div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

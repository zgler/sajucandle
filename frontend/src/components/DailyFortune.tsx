import type { DailyFortuneResponse } from "@/lib/types";

interface Props {
  fortune: DailyFortuneResponse;
}

interface ScoreBarProps {
  label: string;
  value: number;
  colorClass: string;
}

function ScoreBar({ label, value, colorClass }: ScoreBarProps) {
  const clamped = Math.min(100, Math.max(0, value));
  return (
    <div>
      <div className="flex justify-between items-center mb-1">
        <span className="text-sm text-zinc-300">{label}</span>
        <span className="text-sm font-bold text-zinc-100">{clamped}</span>
      </div>
      <div className="bg-zinc-800 rounded-full h-2.5">
        <div
          className={`${colorClass} h-2.5 rounded-full transition-all duration-700`}
          style={{ width: `${clamped}%` }}
        />
      </div>
    </div>
  );
}

function scoreColor(value: number): string {
  if (value >= 70) return "bg-green-500";
  if (value >= 40) return "bg-yellow-500";
  return "bg-red-500";
}

function formatDate(dateStr: string): string {
  const d = new Date(dateStr);
  const year = d.getFullYear();
  const month = d.getMonth() + 1;
  const day = d.getDate();
  const weekdays = ["일", "월", "화", "수", "목", "금", "토"];
  const weekday = weekdays[d.getDay()];
  return `${year}년 ${month}월 ${day}일 (${weekday})`;
}

export default function DailyFortune({ fortune }: Props) {
  const avg = Math.round(
    (fortune.scores.judgment + fortune.scores.action + fortune.scores.patience) / 3
  );

  return (
    <div className="bg-zinc-900 rounded-2xl p-5 space-y-5 border border-zinc-800">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <p className="text-xs text-zinc-500 uppercase tracking-wide">오늘의 매매 기운</p>
          <p className="text-sm text-zinc-400 mt-0.5">{formatDate(fortune.date)}</p>
        </div>
        <div className="text-center">
          <div className={`text-2xl font-bold ${avg >= 70 ? "text-green-400" : avg >= 40 ? "text-yellow-400" : "text-red-400"}`}>
            {avg}
          </div>
          <div className="text-xs text-zinc-500">종합</div>
        </div>
      </div>

      {/* 일진 badge */}
      <div className="flex gap-2">
        <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-zinc-800 text-xs text-zinc-300 border border-zinc-700">
          <span className="text-amber-400 font-bold">{fortune.iljin_stem}</span>
          <span className="text-zinc-300 font-bold">{fortune.iljin_branch}</span>
          <span className="text-zinc-500">일</span>
        </span>
        <span className="inline-flex items-center px-3 py-1 rounded-full bg-zinc-800 text-xs text-zinc-400 border border-zinc-700">
          {fortune.iljin_element}
        </span>
      </div>

      {/* Score Bars */}
      <div className="space-y-3">
        <ScoreBar
          label="판단운"
          value={fortune.scores.judgment}
          colorClass={scoreColor(fortune.scores.judgment)}
        />
        <ScoreBar
          label="실행운"
          value={fortune.scores.action}
          colorClass={scoreColor(fortune.scores.action)}
        />
        <ScoreBar
          label="인내운"
          value={fortune.scores.patience}
          colorClass={scoreColor(fortune.scores.patience)}
        />
      </div>

      {/* Coaching */}
      <div className="bg-zinc-800/60 rounded-xl p-4 border border-zinc-700/50">
        <p className="text-xs text-amber-400 font-medium mb-1.5">오늘의 조언</p>
        <p className="text-sm text-zinc-300 leading-relaxed">{fortune.coaching}</p>
      </div>

      {/* Caution */}
      {fortune.caution && (
        <div className="bg-red-950/30 rounded-xl p-4 border border-red-900/40">
          <p className="text-xs text-red-400 font-medium mb-1.5">⚠ 주의</p>
          <p className="text-sm text-zinc-300 leading-relaxed">{fortune.caution}</p>
        </div>
      )}
    </div>
  );
}

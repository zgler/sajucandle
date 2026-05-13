import type { DailyFortuneResponse } from "@/lib/types";

interface Props {
  fortune: DailyFortuneResponse;
}

export default function FortuneDetail({ fortune }: Props) {
  return (
    <div className="bg-zinc-900 rounded-2xl p-5 space-y-4 border border-zinc-800">
      <h3 className="text-sm font-semibold text-zinc-200 uppercase tracking-wide">
        명리 해설
      </h3>

      {/* Detail text */}
      {fortune.detail && (
        <p className="text-sm text-zinc-400 leading-relaxed">{fortune.detail}</p>
      )}

      {/* Shinsal messages */}
      {fortune.shinsal_messages && fortune.shinsal_messages.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs text-amber-500 font-medium uppercase tracking-wide">
            신살 작용
          </p>
          {fortune.shinsal_messages.map((msg, i) => (
            <div
              key={i}
              className="flex gap-2 text-sm text-zinc-300 bg-amber-950/20 rounded-lg px-3 py-2 border border-amber-900/30"
            >
              <span className="text-amber-400 mt-0.5 flex-shrink-0">◆</span>
              <span>{msg}</span>
            </div>
          ))}
        </div>
      )}

      {/* Relation messages */}
      {fortune.relation_messages && fortune.relation_messages.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs text-blue-400 font-medium uppercase tracking-wide">
            천간지지 관계
          </p>
          {fortune.relation_messages.map((msg, i) => (
            <div
              key={i}
              className="flex gap-2 text-sm text-zinc-300 bg-blue-950/20 rounded-lg px-3 py-2 border border-blue-900/30"
            >
              <span className="text-blue-400 mt-0.5 flex-shrink-0">◆</span>
              <span>{msg}</span>
            </div>
          ))}
        </div>
      )}

      {/* Disclaimer */}
      <div className="pt-2 border-t border-zinc-800">
        <p className="text-xs text-zinc-600 text-center leading-relaxed">
          본 콘텐츠는 오락 목적이며 투자 조언이 아닙니다.
          <br />
          투자는 반드시 본인의 판단과 책임 하에 결정하세요.
        </p>
      </div>
    </div>
  );
}

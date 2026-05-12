import Link from "next/link";
import type { Metadata } from "next";

interface Props {
  params: Promise<{ id: string }>;
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { id } = await params;
  const investorType = decodeURIComponent(id);
  return {
    title: `${investorType} — 사주캔들`,
    description: `나는 ${investorType}! 사주로 알아보는 나의 투자 체질`,
    openGraph: {
      title: `${investorType} — 사주캔들`,
      description: `나는 ${investorType}! 사주로 알아보는 나의 투자 체질`,
    },
  };
}

export default async function CardPage({ params }: Props) {
  const { id } = await params;
  const investorType = decodeURIComponent(id);

  return (
    <div className="min-h-screen bg-zinc-950 flex flex-col items-center justify-center px-4 py-12 space-y-8">
      {/* Card */}
      <div className="w-full max-w-sm bg-gradient-to-br from-zinc-900 to-zinc-800 rounded-3xl p-8 border border-zinc-700 shadow-2xl text-center space-y-4">
        <div className="text-5xl">🕯️</div>
        <div>
          <p className="text-xs text-zinc-500 uppercase tracking-widest mb-1">투자 체질</p>
          <h1 className="text-2xl font-bold text-amber-400">{investorType}</h1>
        </div>
        <div className="w-12 h-px bg-zinc-700 mx-auto" />
        <p className="text-sm text-zinc-400 leading-relaxed">
          사주 명리학으로 읽는 나의 투자 성향
        </p>
      </div>

      {/* CTA */}
      <div className="w-full max-w-sm space-y-3 text-center">
        <p className="text-zinc-400 text-sm">나의 투자 체질은 무엇일까요?</p>
        <Link
          href="/"
          className="block w-full py-4 rounded-2xl font-bold text-zinc-950 bg-gradient-to-r from-amber-400 to-amber-600 hover:from-amber-300 hover:to-amber-500 transition-all shadow-lg shadow-amber-500/25 text-base"
        >
          나도 해보기 →
        </Link>
        <p className="text-xs text-zinc-600">
          무료 · 1분 소요
        </p>
      </div>

      {/* Disclaimer */}
      <p className="text-xs text-zinc-700 text-center max-w-xs">
        본 콘텐츠는 오락 목적이며 투자 조언이 아닙니다.
      </p>
    </div>
  );
}

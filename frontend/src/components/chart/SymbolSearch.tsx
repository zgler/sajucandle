"use client";

import { useState } from "react";

interface Props {
  onSearch: (symbol: string) => void;
  loading: boolean;
}

export default function SymbolSearch({ onSearch, loading }: Props) {
  const [input, setInput] = useState("");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = input.trim().toUpperCase();
    if (trimmed) onSearch(trimmed);
  };

  return (
    <form
      onSubmit={handleSubmit}
      className="flex items-center gap-2 px-4 py-3 bg-zinc-900 border-b border-zinc-800"
    >
      <span className="text-zinc-500 text-sm">🔍</span>
      <input
        type="text"
        value={input}
        onChange={(e) => setInput(e.target.value)}
        placeholder="종목 검색... NVDA, BTC, AAPL"
        className="flex-1 bg-transparent text-zinc-100 text-sm placeholder-zinc-600 outline-none"
        disabled={loading}
      />
      <button
        type="submit"
        disabled={loading || !input.trim()}
        className="text-xs text-amber-400 font-medium px-3 py-1.5 rounded-md bg-amber-400/10 disabled:opacity-40"
      >
        {loading ? "조회 중..." : "조회"}
      </button>
    </form>
  );
}

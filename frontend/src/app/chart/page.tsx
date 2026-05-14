"use client";

import { useState } from "react";
import { loadUser } from "@/lib/storage";
import { fetchChartOhlcv } from "@/lib/api";
import type { ChartOhlcvResponse } from "@/lib/chart-types";
import TabNav from "@/components/TabNav";
import SymbolSearch from "@/components/chart/SymbolSearch";
import TickerHeader from "@/components/chart/TickerHeader";
import CandleChart from "@/components/chart/CandleChart";
import PeriodSelector from "@/components/chart/PeriodSelector";
import AnalysisDashboard from "@/components/chart/AnalysisDashboard";

export default function ChartPage() {
  const [data, setData] = useState<ChartOhlcvResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [months, setMonths] = useState(3);

  const handleSearch = async (symbol: string, periodMonths?: number) => {
    setLoading(true);
    setError(null);

    const m = periodMonths ?? months;
    const user = loadUser();

    try {
      const result = await fetchChartOhlcv({
        symbol,
        months: m,
        birth_date: user
          ? `${user.year}-${String(user.month).padStart(2, "0")}-${String(user.day).padStart(2, "0")}`
          : undefined,
        birth_time: user?.hour !== undefined ? `${String(user.hour).padStart(2, "0")}:00` : undefined,
        gender: user?.gender,
      });
      setData(result);
    } catch (err: any) {
      setError(err.message || "조회에 실패했습니다");
      setData(null);
    } finally {
      setLoading(false);
    }
  };

  const handlePeriodChange = (m: number) => {
    setMonths(m);
    if (data) {
      handleSearch(data.symbol, m);
    }
  };

  return (
    <div className="min-h-screen bg-zinc-950">
      <TabNav />

      <SymbolSearch onSearch={handleSearch} loading={loading} />

      {error && (
        <div className="px-4 py-8 text-center">
          <p className="text-red-400 text-sm">{error}</p>
        </div>
      )}

      {!data && !error && !loading && (
        <div className="px-4 py-16 text-center">
          <p className="text-zinc-600 text-4xl mb-3">📊</p>
          <p className="text-zinc-500 text-sm">종목을 검색하면 차트가 표시됩니다</p>
          <p className="text-zinc-600 text-xs mt-1">NVDA, BTC, AAPL, ETH ...</p>
        </div>
      )}

      {loading && !data && (
        <div className="px-4 py-16 text-center">
          <p className="text-amber-400 text-sm animate-pulse">차트 데이터 조회 중...</p>
        </div>
      )}

      {data && (
        <>
          <TickerHeader data={data} />
          <CandleChart ohlcv={data.ohlcv} markers={data.signal_markers} />
          <PeriodSelector selected={months} onSelect={handlePeriodChange} />
          <AnalysisDashboard symbol={data.symbol} />
        </>
      )}
    </div>
  );
}

"use client";

import { useEffect, useRef } from "react";
import type { OhlcvBar, SignalMarker } from "@/lib/chart-types";

interface Props {
  ohlcv: OhlcvBar[];
  markers: SignalMarker[];
}

export default function CandleChart({ ohlcv, markers }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<ReturnType<typeof import("lightweight-charts").createChart> | null>(null);

  useEffect(() => {
    if (!containerRef.current || ohlcv.length === 0) return;

    let cancelled = false;

    import("lightweight-charts").then((LWC) => {
      if (cancelled || !containerRef.current) return;

      // 기존 차트 제거
      if (chartRef.current) {
        chartRef.current.remove();
        chartRef.current = null;
      }

      const chart = LWC.createChart(containerRef.current, {
        width: containerRef.current.clientWidth,
        height: 300,
        layout: {
          background: { type: LWC.ColorType.Solid, color: "#0a0f1e" },
          textColor: "#666",
          fontSize: 11,
        },
        grid: {
          vertLines: { color: "#1e293b40" },
          horzLines: { color: "#1e293b40" },
        },
        crosshair: {
          mode: LWC.CrosshairMode.Normal,
          vertLine: { color: "#fbbf2440", labelBackgroundColor: "#fbbf24" },
          horzLine: { color: "#fbbf2440", labelBackgroundColor: "#fbbf24" },
        },
        rightPriceScale: {
          borderColor: "#1e293b",
          scaleMargins: { top: 0.1, bottom: 0.2 },
        },
        timeScale: {
          borderColor: "#1e293b",
          timeVisible: false,
        },
      });

      chartRef.current = chart;

      // 캔들스틱
      const candleSeries = chart.addCandlestickSeries({
        upColor: "#4ade80",
        downColor: "#ef4444",
        borderDownColor: "#ef4444",
        borderUpColor: "#4ade80",
        wickDownColor: "#ef444488",
        wickUpColor: "#4ade8088",
      });

      const candleData = ohlcv.map((bar) => ({
        time: bar.date as string,
        open: bar.open,
        high: bar.high,
        low: bar.low,
        close: bar.close,
      }));
      candleSeries.setData(candleData);

      // 거래량
      const volumeSeries = chart.addHistogramSeries({
        priceFormat: { type: "volume" },
        priceScaleId: "vol",
      });
      volumeSeries.setData(
        ohlcv.map((bar) => ({
          time: bar.date as string,
          value: bar.volume,
          color: bar.close >= bar.open ? "#4ade8020" : "#ef444420",
        })),
      );
      chart.priceScale("vol").applyOptions({
        scaleMargins: { top: 0.85, bottom: 0 },
      });

      // MA20
      const ma20Data: { time: string; value: number }[] = [];
      for (let i = 19; i < ohlcv.length; i++) {
        let sum = 0;
        for (let j = i - 19; j <= i; j++) sum += ohlcv[j].close;
        ma20Data.push({ time: ohlcv[i].date, value: +(sum / 20).toFixed(2) });
      }
      if (ma20Data.length > 0) {
        const maSeries = chart.addLineSeries({
          color: "#fbbf2480",
          lineWidth: 1,
          priceLineVisible: false,
          lastValueVisible: false,
        });
        maSeries.setData(ma20Data);
      }

      // 시그널 마커
      if (markers.length > 0) {
        const MARKER_MAP: Record<string, { position: string; color: string; shape: string }> = {
          BUY: { position: "belowBar", color: "#4ade80", shape: "arrowUp" },
          SELL: { position: "aboveBar", color: "#ef4444", shape: "arrowDown" },
          HOLD: { position: "belowBar", color: "#fbbf24", shape: "circle" },
          WATCH: { position: "belowBar", color: "#fbbf24", shape: "circle" },
          KILL: { position: "aboveBar", color: "#ef4444", shape: "arrowDown" },
        };
        const chartMarkers = markers
          .filter((m) => MARKER_MAP[m.signal])
          .map((m) => ({
            time: m.date as string,
            ...(MARKER_MAP[m.signal] as any),
            text: m.signal,
          }));
        if (chartMarkers.length > 0) {
          candleSeries.setMarkers(chartMarkers);
        }
      }

      chart.timeScale().fitContent();

      // 리사이즈
      const ro = new ResizeObserver((entries) => {
        if (entries[0]) {
          chart.applyOptions({ width: entries[0].contentRect.width });
        }
      });
      ro.observe(containerRef.current);

      // cleanup에 ro 해제 추가
      return () => {
        ro.disconnect();
      };
    });

    return () => {
      cancelled = true;
      if (chartRef.current) {
        chartRef.current.remove();
        chartRef.current = null;
      }
    };
  }, [ohlcv, markers]);

  return <div ref={containerRef} className="w-full h-[300px] bg-[#0a0f1e]" />;
}

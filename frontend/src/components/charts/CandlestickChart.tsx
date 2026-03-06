"use client";

import { useEffect, useRef } from "react";
import {
  createChart,
  CandlestickSeries,
  createSeriesMarkers,
  ColorType,
  type IChartApi,
  type ISeriesApi,
  type CandlestickSeriesOptions,
  type DeepPartial,
  type SeriesMarker,
  type CandlestickData,
  type Time,
} from "lightweight-charts";

export type OhlcCandle = {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
};

export type TradeMarker = {
  timestamp: string;
  side: "buy" | "sell";
  price: number;
};

function toUnixTimestamp(iso: string): number {
  return Math.floor(new Date(iso).getTime() / 1000);
}

export function CandlestickChart({
  candles,
  trades,
}: {
  candles: OhlcCandle[];
  trades: TradeMarker[];
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);

  useEffect(() => {
    if (!containerRef.current || candles.length === 0) return;

    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: "#a1a1aa",
        fontFamily: "inherit",
      },
      grid: {
        vertLines: { color: "rgba(255,255,255,0.04)" },
        horzLines: { color: "rgba(255,255,255,0.04)" },
      },
      crosshair: {
        vertLine: { color: "rgba(255,255,255,0.15)", labelBackgroundColor: "#333" },
        horzLine: { color: "rgba(255,255,255,0.15)", labelBackgroundColor: "#333" },
      },
      timeScale: {
        borderColor: "rgba(255,255,255,0.08)",
        timeVisible: true,
        secondsVisible: false,
      },
      rightPriceScale: {
        borderColor: "rgba(255,255,255,0.08)",
      },
    });
    chartRef.current = chart;

    const seriesOptions: DeepPartial<CandlestickSeriesOptions> = {
      upColor: "#22c55e",
      downColor: "#ef4444",
      borderVisible: false,
      wickUpColor: "#22c55e",
      wickDownColor: "#ef4444",
    };
    const candleSeries: ISeriesApi<"Candlestick"> = chart.addSeries(
      CandlestickSeries,
      seriesOptions,
    );

    const chartCandles: CandlestickData<Time>[] = candles.map((c) => ({
      time: toUnixTimestamp(c.timestamp) as Time,
      open: c.open,
      high: c.high,
      low: c.low,
      close: c.close,
    }));
    candleSeries.setData(chartCandles);

    if (trades.length > 0) {
      const markers: SeriesMarker<Time>[] = trades
        .map((t) => {
          const isBuy = t.side === "buy";
          return {
            time: toUnixTimestamp(t.timestamp) as Time,
            position: (isBuy ? "belowBar" : "aboveBar") as "belowBar" | "aboveBar",
            color: isBuy ? "#22c55e" : "#ef4444",
            shape: (isBuy ? "arrowUp" : "arrowDown") as "arrowUp" | "arrowDown",
            text: isBuy ? "BUY" : "SELL",
          };
        })
        .sort((a, b) => (a.time as number) - (b.time as number));

      createSeriesMarkers(candleSeries, markers);
    }

    chart.timeScale().fitContent();

    const ro = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const { width } = entry.contentRect;
        if (width > 0) {
          chart.applyOptions({ width });
        }
      }
    });
    ro.observe(containerRef.current);

    return () => {
      ro.disconnect();
      chart.remove();
      chartRef.current = null;
    };
  }, [candles, trades]);

  if (candles.length === 0) {
    return (
      <p className="text-muted-foreground text-sm py-8 text-center">
        No candle data available for this run.
      </p>
    );
  }

  return <div ref={containerRef} className="w-full h-[420px]" />;
}

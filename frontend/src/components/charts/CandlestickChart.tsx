"use client";

import { useEffect, useRef } from "react";
import {
  createChart,
  CandlestickSeries,
  HistogramSeries,
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

export type RegimeBand = {
  timestamp: string;
  regime: string;
};

const REGIME_COLORS: Record<string, string> = {
  trend: "rgba(34, 197, 94, 0.18)",
  range: "rgba(59, 130, 246, 0.18)",
  high_vol: "rgba(239, 68, 68, 0.18)",
};

function toUnixTimestamp(iso: string): number {
  return Math.floor(new Date(iso).getTime() / 1000);
}

/** Unique bar opens sorted ascending (seconds), matching candle series `time`. */
function candleBarOpensSec(candles: OhlcCandle[]): number[] {
  const secs = candles.map((c) => toUnixTimestamp(c.timestamp));
  return [...new Set(secs)].sort((a, b) => a - b);
}

/**
 * Map a trade instant to the candle bar open it belongs to.
 * Returns the latest bar open ≤ trade time, or null if the trade is before the
 * first bar or after the last bar's close window (prevents piling onto the edges).
 */
function snapTradeToBarOpenSec(tradeMs: number, barOpensAsc: number[]): number | null {
  if (barOpensAsc.length === 0) return null;
  const t = Math.floor(tradeMs / 1000);
  if (t < barOpensAsc[0]) return null;

  const lastOpen = barOpensAsc[barOpensAsc.length - 1];
  const barSpan =
    barOpensAsc.length >= 2
      ? barOpensAsc[barOpensAsc.length - 1] - barOpensAsc[barOpensAsc.length - 2]
      : 3600;
  if (t >= lastOpen + barSpan) return null;

  if (t >= lastOpen) return lastOpen;

  let lo = 0;
  let hi = barOpensAsc.length - 2;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (barOpensAsc[mid + 1] <= t) lo = mid + 1;
    else hi = mid - 1;
  }
  return barOpensAsc[lo];
}

type MarkerAgg = {
  time: number;
  side: "buy" | "sell";
  count: number;
};

function buildTradeMarkersForChart(
  trades: TradeMarker[],
  barOpensAsc: number[],
): SeriesMarker<Time>[] {
  if (trades.length === 0 || barOpensAsc.length === 0) return [];

  const groups = new Map<string, MarkerAgg>();
  for (const t of trades) {
    const barSec = snapTradeToBarOpenSec(new Date(t.timestamp).getTime(), barOpensAsc);
    if (barSec == null) continue;
    const side = t.side;
    const key = `${barSec}:${side}`;
    const g = groups.get(key);
    if (g) g.count += 1;
    else groups.set(key, { time: barSec, side, count: 1 });
  }

  const rows = Array.from(groups.values());
  rows.sort((a, b) => a.time - b.time || (a.side === "buy" ? -1 : 1));

  return rows.map((g) => {
    const isBuy = g.side === "buy";
    const label = isBuy ? "BUY" : "SELL";
    const text = g.count > 1 ? `${label} ×${g.count}` : label;
    return {
      time: g.time as Time,
      position: (isBuy ? "belowBar" : "aboveBar") as "belowBar" | "aboveBar",
      color: isBuy ? "#22c55e" : "#ef4444",
      shape: (isBuy ? "arrowUp" : "arrowDown") as "arrowUp" | "arrowDown",
      text,
    };
  });
}

export function CandlestickChart({
  candles,
  trades,
  regimes = [],
}: {
  candles: OhlcCandle[];
  trades: TradeMarker[];
  regimes?: RegimeBand[];
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

    if (regimes.length > 0) {
      const regimeMap = new Map<number, string>();
      for (const r of regimes) {
        regimeMap.set(toUnixTimestamp(r.timestamp), r.regime);
      }

      const maxPrice = Math.max(...candles.map((c) => c.high));
      const regimeData = candles.map((c) => {
        const ts = toUnixTimestamp(c.timestamp);
        const regime = regimeMap.get(ts);
        return {
          time: ts as Time,
          value: maxPrice * 1.1,
          color: regime ? (REGIME_COLORS[regime] ?? "rgba(128,128,128,0.1)") : "transparent",
        };
      });

      const regimeSeries = chart.addSeries(HistogramSeries, {
        priceScaleId: "",
        lastValueVisible: false,
        priceLineVisible: false,
      });
      regimeSeries.priceScale().applyOptions({
        scaleMargins: { top: 0, bottom: 0 },
      });
      regimeSeries.setData(regimeData);
    }

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
      const barOpensAsc = candleBarOpensSec(candles);
      const markers = buildTradeMarkersForChart(trades, barOpensAsc);
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
  }, [candles, trades, regimes]);

  if (candles.length === 0) {
    return (
      <p className="text-muted-foreground text-sm py-8 text-center">
        No candle data available for this run.
      </p>
    );
  }

  return <div ref={containerRef} className="w-full h-[420px]" />;
}

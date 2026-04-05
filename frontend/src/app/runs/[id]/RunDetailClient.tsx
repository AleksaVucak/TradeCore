"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  backtestsApi,
  marketDataApi,
  regimesApi,
  type BacktestRunDetail,
  type BenchmarkResponse,
  type CandleResponse,
  type ModelInfoOut,
  type RegimeLabelOut,
  type RegimePerformanceResponse,
} from "@/lib/api/endpoints";
import { getToken } from "@/lib/auth";
import {
  CandlestickChart,
  type OhlcCandle,
  type TradeMarker,
  type RegimeBand,
} from "@/components/charts/CandlestickChart";
import {
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
  Line,
  ComposedChart,
  Legend,
} from "recharts";
import { MonteCarloCard } from "@/components/MonteCarloCard";
import { RiskMetricsCard } from "@/components/RiskMetricsCard";

function formatPct(value: number | null | undefined): string {
  if (value == null) return "—";
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
}

function formatDateRange(start: string, end: string): string {
  try {
    const s = new Date(start);
    const e = new Date(end);
    return `${s.toLocaleDateString()} – ${e.toLocaleDateString()}`;
  } catch {
    return `${start} – ${end}`;
  }
}

function formatTimestamp(ts: string): string {
  try {
    return new Date(ts).toLocaleString();
  } catch {
    return ts;
  }
}

function formatNumber(value: number, decimals = 2): string {
  return value.toLocaleString(undefined, {
    minimumFractionDigits: 0,
    maximumFractionDigits: decimals,
  });
}

function StatusBadge({ status }: { status: string }) {
  const variant =
    status === "completed"
      ? "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400"
      : status === "failed"
        ? "bg-destructive/15 text-destructive"
        : status === "running"
          ? "bg-blue-500/15 text-blue-700 dark:text-blue-400"
          : "bg-muted text-muted-foreground";
  return (
    <span
      className={`inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium capitalize ${variant}`}
    >
      {status}
    </span>
  );
}

export function RunDetailClient({ runId }: { runId: string }) {
  const [run, setRun] = useState<BacktestRunDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [benchmark, setBenchmark] = useState<BenchmarkResponse | null>(null);

  useEffect(() => {
    const token = getToken();
    if (!token) {
      queueMicrotask(() => {
        setError("Please log in to view this run.");
        setLoading(false);
      });
      return;
    }
    backtestsApi
      .get(token, runId)
      .then((data) => {
        setRun(data);
        setError(null);
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : "Failed to load run");
        setRun(null);
      })
      .finally(() => setLoading(false));
  }, [runId]);

  const equityCurve = run?.equity_curve;

  const chartData = useMemo(() => {
    if (!equityCurve || equityCurve.length === 0) return [];

    const strategyData = [...equityCurve]
      .sort(
        (a, b) =>
          new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
      )
      .map((p) => ({
        timestamp: p.timestamp,
        equity_value: p.equity_value,
      }));

    if (!benchmark || benchmark.equity_curve.length === 0) {
      return strategyData;
    }

    const benchmarkMap = new Map(
      benchmark.equity_curve.map((p) => [p.timestamp, p.equity_value])
    );

    return strategyData.map((p) => ({
      ...p,
      benchmark_value: benchmarkMap.get(p.timestamp) ?? undefined,
    }));
  }, [equityCurve, benchmark]);

  const hasEquityData = chartData.length > 0;
  const hasBenchmarkData = benchmark && benchmark.equity_curve.length > 0;

  const equityDomain = useMemo(() => {
    if (!hasEquityData) return { min: 0, max: 0, initial: 0 };
    const strategyValues = chartData.map((d) => d.equity_value);
    const benchmarkValues = chartData
      .map((d) => (d as { benchmark_value?: number }).benchmark_value)
      .filter((v): v is number => v !== undefined);
    const allValues = [...strategyValues, ...benchmarkValues];
    const min = Math.min(...allValues);
    const max = Math.max(...allValues);
    const initial = strategyValues[0];
    return { min, max, initial };
  }, [chartData, hasEquityData]);

  const gradientOffset = useMemo(() => {
    if (!hasEquityData) return 0;
    const { min, max, initial } = equityDomain;
    if (max === min) return 0.5;
    return Math.max(0, Math.min(1, (max - initial) / (max - min)));
  }, [equityDomain, hasEquityData]);

  const [ohlcCandles, setOhlcCandles] = useState<OhlcCandle[]>([]);
  const [candlesLoading, setCandlesLoading] = useState(false);
  const [regimeLabels, setRegimeLabels] = useState<RegimeLabelOut[]>([]);
  const [regimePerformance, setRegimePerformance] = useState<RegimePerformanceResponse | null>(null);
  const [modelInfo, setModelInfo] = useState<ModelInfoOut | null>(null);

  useEffect(() => {
    if (!run || run.status !== "completed") return;
    const token = getToken();
    if (!token) return;
    queueMicrotask(() => setCandlesLoading(true));
    marketDataApi
      .candles(token, {
        symbol_id: run.symbol_id,
        timeframe: run.timeframe,
        start: run.start_time,
        end: run.end_time,
      })
      .then((data: CandleResponse[]) => {
        setOhlcCandles(
          data.map((c) => ({
            timestamp: c.timestamp,
            open: c.open,
            high: c.high,
            low: c.low,
            close: c.close,
          })),
        );
      })
      .catch(() => setOhlcCandles([]))
      .finally(() => setCandlesLoading(false));
  }, [run]);

  useEffect(() => {
    if (!run || run.status !== "completed") return;
    const token = getToken();
    if (!token) return;
    backtestsApi
      .getBenchmark(token, runId)
      .then((data) => setBenchmark(data))
      .catch(() => setBenchmark(null));
  }, [run, runId]);

  useEffect(() => {
    if (!run || run.status !== "completed") return;
    const token = getToken();
    if (!token) return;

    let cancelled = false;

    async function loadRegimes() {
      try {
        await regimesApi.ensureForRun(token!, runId);
      } catch {
        // Best-effort; if ensure fails we still try to read existing labels
      }

      if (cancelled) return;

      const [labelsResult, perfResult, modelResult] = await Promise.allSettled([
        regimesApi.getForRun(token!, runId),
        regimesApi.getPerformanceForRun(token!, runId),
        regimesApi.getModelForRun(token!, runId),
      ]);

      if (cancelled) return;

      setRegimeLabels(
        labelsResult.status === "fulfilled" ? labelsResult.value.labels : [],
      );
      setRegimePerformance(
        perfResult.status === "fulfilled" ? perfResult.value : null,
      );
      setModelInfo(
        modelResult.status === "fulfilled" ? modelResult.value : null,
      );
    }

    loadRegimes();
    return () => { cancelled = true; };
  }, [run, runId]);

  const regimeBands: RegimeBand[] = useMemo(() => {
    return regimeLabels.map((l) => ({
      timestamp: l.timestamp,
      regime: l.regime,
    }));
  }, [regimeLabels]);

  const regimeSummary = useMemo(() => {
    if (regimeLabels.length === 0) return null;
    const counts: Record<string, number> = {};
    for (const l of regimeLabels) {
      counts[l.regime] = (counts[l.regime] || 0) + 1;
    }
    const total = regimeLabels.length;
    return { counts, total };
  }, [regimeLabels]);

  const trades = run?.trades;
  const closedTradeCount = useMemo(() => {
    if (!trades || trades.length === 0) return 0;
    return trades.filter((t) => t.side === "sell" && t.pnl != null).length;
  }, [trades]);

  const tradeMarkers: TradeMarker[] = useMemo(() => {
    if (!trades || trades.length === 0) return [];
    return trades.map((t) => ({
      timestamp: t.timestamp,
      side: t.side as "buy" | "sell",
      price: t.price,
    }));
  }, [trades]);

  if (loading) {
    return (
      <div className="mt-6 space-y-6">
        <div className="flex flex-wrap items-center gap-3">
          <Skeleton className="h-7 w-48" />
          <Skeleton className="h-5 w-20 rounded-md" />
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
          {Array.from({ length: 8 }).map((_, i) => (
            <Card key={i}>
              <CardHeader className="pb-2">
                <Skeleton className="h-3 w-20" />
              </CardHeader>
              <CardContent>
                <Skeleton className="h-6 w-16" />
              </CardContent>
            </Card>
          ))}
        </div>
        <Card>
          <CardHeader className="pb-2">
            <Skeleton className="h-5 w-32" />
            <Skeleton className="h-4 w-48 mt-1" />
          </CardHeader>
          <CardContent>
            <Skeleton className="h-[280px] w-full rounded-md" />
          </CardContent>
        </Card>
      </div>
    );
  }

  if (error || !run) {
    return (
      <div className="mt-4">
        <p className="text-destructive">{error ?? "Run not found."}</p>
      </div>
    );
  }

  const isFailed = run.status === "failed";
  const hasErrorMessage = isFailed && run.error_message;
  const hasMetrics = run.status === "completed" && run.metrics && typeof run.metrics === "object";
  const metrics = hasMetrics ? (run.metrics as Record<string, number>) : null;

  return (
    <>
      {/* Page shell */}
      <div className="mt-4 flex flex-wrap items-center gap-3">
        <h1 className="text-xl font-semibold tracking-tight">
          Run {runId.slice(0, 8)}…
        </h1>
        <StatusBadge status={run.status} />
      </div>
      <p className="text-muted-foreground mt-1 text-sm">
        {run.timeframe} · {formatDateRange(run.start_time, run.end_time)}
      </p>

      {/* Error card (failed runs) */}
      {hasErrorMessage && (
        <Card className="mt-6 border-destructive/50 bg-destructive/5">
          <CardHeader className="pb-2">
            <CardTitle className="text-base text-destructive">
              Run failed
            </CardTitle>
            <CardDescription>
              This backtest run failed. Error message:
            </CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-sm font-mono whitespace-pre-wrap wrap-break-word">
              {run.error_message}
            </p>
          </CardContent>
        </Card>
      )}

      {/* Metrics cards (completed runs with metrics) */}
      {hasMetrics && metrics && (
        <div className="mt-6">
          <h2 className="text-sm font-medium text-muted-foreground mb-3">
            Summary
          </h2>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
            {typeof metrics.total_return_pct === "number" && (
              <Card>
                <CardHeader className="pb-1 pt-3 px-4">
                  <CardTitle className="text-xs font-medium text-muted-foreground">
                    Total return
                  </CardTitle>
                </CardHeader>
                <CardContent className="pb-3 px-4">
                  <p
                    className={`text-lg font-semibold tabular-nums ${
                      metrics.total_return_pct >= 0
                        ? "text-emerald-600 dark:text-emerald-400"
                        : "text-destructive"
                    }`}
                  >
                    {formatPct(metrics.total_return_pct)}
                  </p>
                </CardContent>
              </Card>
            )}
            {typeof metrics.max_drawdown_pct === "number" && (
              <Card>
                <CardHeader className="pb-1 pt-3 px-4">
                  <CardTitle className="text-xs font-medium text-muted-foreground">
                    Max drawdown
                  </CardTitle>
                </CardHeader>
                <CardContent className="pb-3 px-4">
                  <p className="text-lg font-semibold tabular-nums text-muted-foreground">
                    {metrics.max_drawdown_pct.toFixed(2)}%
                  </p>
                </CardContent>
              </Card>
            )}
            {typeof metrics.num_trades === "number" && (
              <Card>
                <CardHeader className="pb-1 pt-3 px-4">
                  <CardTitle className="text-xs font-medium text-muted-foreground">
                    Trades
                  </CardTitle>
                </CardHeader>
                <CardContent className="pb-3 px-4">
                  <p className="text-lg font-semibold tabular-nums">
                    {metrics.num_trades}
                  </p>
                </CardContent>
              </Card>
            )}
            {typeof metrics.final_equity === "number" && (
              <Card>
                <CardHeader className="pb-1 pt-3 px-4">
                  <CardTitle className="text-xs font-medium text-muted-foreground">
                    Final equity
                  </CardTitle>
                </CardHeader>
                <CardContent className="pb-3 px-4">
                  <p className="text-lg font-semibold tabular-nums">
                    {formatNumber(metrics.final_equity)}
                  </p>
                </CardContent>
              </Card>
            )}
            {typeof metrics.win_rate === "number" && (
              <Card>
                <CardHeader className="pb-1 pt-3 px-4">
                  <CardTitle className="text-xs font-medium text-muted-foreground">
                    Win rate
                  </CardTitle>
                </CardHeader>
                <CardContent className="pb-3 px-4">
                  <p className="text-lg font-semibold tabular-nums">
                    {metrics.win_rate.toFixed(1)}%
                  </p>
                </CardContent>
              </Card>
            )}
            {typeof metrics.profit_factor === "number" && (
              <Card>
                <CardHeader className="pb-1 pt-3 px-4">
                  <CardTitle className="text-xs font-medium text-muted-foreground">
                    Profit factor
                  </CardTitle>
                </CardHeader>
                <CardContent className="pb-3 px-4">
                  <p className="text-lg font-semibold tabular-nums">
                    {metrics.profit_factor.toFixed(2)}
                  </p>
                </CardContent>
              </Card>
            )}
            {typeof metrics.sharpe_ratio === "number" && (
              <Card>
                <CardHeader className="pb-1 pt-3 px-4">
                  <CardTitle className="text-xs font-medium text-muted-foreground">
                    Sharpe ratio
                  </CardTitle>
                </CardHeader>
                <CardContent className="pb-3 px-4">
                  <p className="text-lg font-semibold tabular-nums">
                    {metrics.sharpe_ratio.toFixed(2)}
                  </p>
                </CardContent>
              </Card>
            )}
            {typeof metrics.annualized_return_pct === "number" && (
              <Card>
                <CardHeader className="pb-1 pt-3 px-4">
                  <CardTitle className="text-xs font-medium text-muted-foreground">
                    Ann. return
                  </CardTitle>
                </CardHeader>
                <CardContent className="pb-3 px-4">
                  <p className="text-lg font-semibold tabular-nums text-muted-foreground">
                    {formatPct(metrics.annualized_return_pct)}
                  </p>
                </CardContent>
              </Card>
            )}
            {benchmark && (
              <Card>
                <CardHeader className="pb-1 pt-3 px-4">
                  <CardTitle className="text-xs font-medium text-muted-foreground">
                    Alpha
                  </CardTitle>
                </CardHeader>
                <CardContent className="pb-3 px-4">
                  <p
                    className={`text-lg font-semibold tabular-nums ${
                      benchmark.alpha_pct >= 0
                        ? "text-emerald-600 dark:text-emerald-400"
                        : "text-destructive"
                    }`}
                  >
                    {formatPct(benchmark.alpha_pct)}
                  </p>
                </CardContent>
              </Card>
            )}
            {benchmark && (
              <Card>
                <CardHeader className="pb-1 pt-3 px-4">
                  <CardTitle className="text-xs font-medium text-muted-foreground">
                    B&H return
                  </CardTitle>
                </CardHeader>
                <CardContent className="pb-3 px-4">
                  <p className="text-lg font-semibold tabular-nums text-muted-foreground">
                    {formatPct(benchmark.total_return_pct)}
                  </p>
                </CardContent>
              </Card>
            )}
          </div>
        </div>
      )}

      {/* Risk metrics card (Phase 12.3) */}
      <RiskMetricsCard runId={runId} runStatus={run.status} />

      {/* Monte Carlo robustness (Phase 14.3) */}
      <MonteCarloCard
        runId={runId}
        runStatus={run.status}
        closedTradeCount={closedTradeCount}
      />

      {/* Equity curve chart with benchmark (Phase 12.4) */}
      <Card className="mt-6">
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Equity curve</CardTitle>
          <CardDescription>
            {hasEquityData
              ? `Strategy vs buy-and-hold (${chartData.length} point${chartData.length !== 1 ? "s" : ""})`
              : "No equity data for this run."}
            {hasBenchmarkData && benchmark && (
              <span className="ml-2">
                · Alpha:{" "}
                <span
                  className={
                    benchmark.alpha_pct >= 0
                      ? "text-emerald-600 dark:text-emerald-400 font-medium"
                      : "text-destructive font-medium"
                  }
                >
                  {benchmark.alpha_pct >= 0 ? "+" : ""}
                  {benchmark.alpha_pct.toFixed(2)}%
                </span>
              </span>
            )}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {hasEquityData ? (
            <div className="h-[320px] w-full">
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart
                  data={chartData}
                  margin={{ top: 10, right: 10, left: 10, bottom: 5 }}
                >
                  <defs>
                    <linearGradient id="equityStroke" x1="0" y1="0" x2="0" y2="1">
                      <stop offset={0} stopColor="#22c55e" />
                      <stop offset={gradientOffset} stopColor="#22c55e" />
                      <stop offset={gradientOffset} stopColor="#ef4444" />
                      <stop offset={1} stopColor="#ef4444" />
                    </linearGradient>
                    <linearGradient id="equityFill" x1="0" y1="0" x2="0" y2="1">
                      <stop offset={0} stopColor="#22c55e" stopOpacity={0.25} />
                      <stop offset={gradientOffset} stopColor="#22c55e" stopOpacity={0.05} />
                      <stop offset={gradientOffset} stopColor="#ef4444" stopOpacity={0.05} />
                      <stop offset={1} stopColor="#ef4444" stopOpacity={0.25} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid
                    strokeDasharray="3 3"
                    stroke="hsl(var(--border))"
                    opacity={0.4}
                  />
                  <XAxis
                    dataKey="timestamp"
                    tickFormatter={(ts) =>
                      new Date(ts).toLocaleDateString(undefined, {
                        month: "short",
                        day: "numeric",
                      })
                    }
                    tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 11 }}
                    axisLine={{ stroke: "hsl(var(--border))" }}
                    tickLine={{ stroke: "hsl(var(--border))" }}
                  />
                  <YAxis
                    tickFormatter={(v) =>
                      v >= 1000 ? `${(v / 1000).toFixed(1)}k` : String(v)
                    }
                    tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 11 }}
                    axisLine={{ stroke: "hsl(var(--border))" }}
                    tickLine={{ stroke: "hsl(var(--border))" }}
                    domain={["auto", "auto"]}
                  />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: "hsl(var(--card))",
                      border: "1px solid hsl(var(--border))",
                      borderRadius: "var(--radius)",
                      fontSize: 12,
                    }}
                    labelStyle={{ color: "hsl(var(--foreground))" }}
                    formatter={(value, name) => [
                      typeof value === "number"
                        ? value.toLocaleString(undefined, {
                            minimumFractionDigits: 2,
                            maximumFractionDigits: 2,
                          })
                        : "—",
                      name === "equity_value" ? "Strategy" : "Buy & Hold",
                    ]}
                    labelFormatter={(label) =>
                      new Date(String(label)).toLocaleString(undefined, {
                        dateStyle: "medium",
                        timeStyle: "short",
                      })
                    }
                  />
                  <Legend
                    verticalAlign="top"
                    height={36}
                    formatter={(value) =>
                      value === "equity_value" ? "Strategy" : "Buy & Hold"
                    }
                  />
                  <ReferenceLine
                    y={equityDomain.initial}
                    stroke="hsl(var(--muted-foreground))"
                    strokeDasharray="4 4"
                    strokeOpacity={0.6}
                    label={{
                      value: "Start",
                      position: "insideTopRight",
                      fill: "hsl(var(--muted-foreground))",
                      fontSize: 10,
                    }}
                  />
                  <Area
                    type="monotone"
                    dataKey="equity_value"
                    stroke="url(#equityStroke)"
                    strokeWidth={2.5}
                    fill="url(#equityFill)"
                    dot={false}
                    activeDot={{ r: 4, fill: "#fff", strokeWidth: 2 }}
                  />
                  {hasBenchmarkData && (
                    <Line
                      type="monotone"
                      dataKey="benchmark_value"
                      stroke="#6366f1"
                      strokeWidth={2}
                      strokeDasharray="5 5"
                      dot={false}
                      activeDot={{ r: 3, fill: "#6366f1" }}
                    />
                  )}
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <p className="text-muted-foreground text-sm py-8 text-center">
              Equity curve is only available for completed runs with trade
              activity or equity snapshots.
            </p>
          )}
        </CardContent>
      </Card>

      {/* Candlestick chart with trade markers */}
      {run.status === "completed" && (
        <Card className="mt-6">
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Price chart</CardTitle>
            <CardDescription>
              {candlesLoading
                ? "Loading candle data…"
                : ohlcCandles.length > 0
                  ? `${ohlcCandles.length} candle${ohlcCandles.length !== 1 ? "s" : ""} · ${run.timeframe}${run.trades.length > 0 ? ` · ${run.trades.length} trade marker${run.trades.length !== 1 ? "s" : ""}` : ""}`
                  : "No candle data available for this symbol and timeframe."}
            </CardDescription>
          </CardHeader>
          <CardContent>
            {candlesLoading ? (
              <p className="text-muted-foreground text-sm py-8 text-center">
                Loading candle data…
              </p>
            ) : (
              <CandlestickChart candles={ohlcCandles} trades={tradeMarkers} regimes={regimeBands} />
            )}
          </CardContent>
        </Card>
      )}

      {/* Regime summary */}
      {run.status === "completed" && regimeSummary && (
        <Card className="mt-6">
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Market regime analysis</CardTitle>
            <CardDescription>
              ML-predicted regime for each bar in this run window ({regimeSummary.total} bars labeled)
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-4">
              {(["trend", "range", "high_vol"] as const).map((regime) => {
                const count = regimeSummary.counts[regime] ?? 0;
                const pct = regimeSummary.total > 0 ? ((count / regimeSummary.total) * 100).toFixed(1) : "0.0";
                const colorClasses: Record<string, string> = {
                  trend: "bg-emerald-500/20 text-emerald-600 dark:text-emerald-400 border-emerald-500/30",
                  range: "bg-blue-500/20 text-blue-600 dark:text-blue-400 border-blue-500/30",
                  high_vol: "bg-red-500/20 text-red-600 dark:text-red-400 border-red-500/30",
                };
                const dotColors: Record<string, string> = {
                  trend: "bg-emerald-500",
                  range: "bg-blue-500",
                  high_vol: "bg-red-500",
                };
                const labels: Record<string, string> = {
                  trend: "Trend",
                  range: "Range",
                  high_vol: "High Volatility",
                };
                return (
                  <div
                    key={regime}
                    className={`flex items-center gap-3 rounded-lg border px-4 py-3 ${colorClasses[regime]}`}
                  >
                    <span className={`h-3 w-3 rounded-full ${dotColors[regime]}`} />
                    <div>
                      <p className="text-sm font-medium">{labels[regime]}</p>
                      <p className="text-xs opacity-80">
                        {count} bars · {pct}%
                      </p>
                    </div>
                  </div>
                );
              })}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Model info card */}
      {run.status === "completed" && modelInfo && (
        <Card className="mt-6">
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Regime model info</CardTitle>
            <CardDescription>
              ML model used for regime classification on this run
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-x-6 gap-y-4 text-sm">
              <div>
                <p className="text-muted-foreground text-xs font-medium mb-0.5">Model</p>
                <p className="font-medium">{modelInfo.name} <span className="text-muted-foreground text-xs">#{modelInfo.id}</span></p>
              </div>
              {modelInfo.accuracy != null && (
                <div>
                  <p className="text-muted-foreground text-xs font-medium mb-0.5">Accuracy</p>
                  <p className="font-semibold tabular-nums">{(modelInfo.accuracy * 100).toFixed(1)}%</p>
                </div>
              )}
              {modelInfo.tuned && modelInfo.cv_best_score != null && (
                <div>
                  <p className="text-muted-foreground text-xs font-medium mb-0.5">CV score (F1)</p>
                  <p className="font-semibold tabular-nums">{(modelInfo.cv_best_score * 100).toFixed(1)}%</p>
                </div>
              )}
              {modelInfo.tuned && modelInfo.cv_folds != null && (
                <div>
                  <p className="text-muted-foreground text-xs font-medium mb-0.5">CV folds</p>
                  <p className="tabular-nums">{modelInfo.cv_folds}</p>
                </div>
              )}
              {modelInfo.n_train != null && (
                <div>
                  <p className="text-muted-foreground text-xs font-medium mb-0.5">Train samples</p>
                  <p className="tabular-nums">{modelInfo.n_train.toLocaleString()}</p>
                </div>
              )}
              {modelInfo.n_test != null && (
                <div>
                  <p className="text-muted-foreground text-xs font-medium mb-0.5">Test samples</p>
                  <p className="tabular-nums">{modelInfo.n_test.toLocaleString()}</p>
                </div>
              )}
              <div>
                <p className="text-muted-foreground text-xs font-medium mb-0.5">Tuned</p>
                <p>
                  {modelInfo.tuned ? (
                    <span className="inline-flex items-center rounded-md bg-emerald-500/15 text-emerald-700 dark:text-emerald-400 px-2 py-0.5 text-xs font-medium">
                      Yes
                    </span>
                  ) : (
                    <span className="inline-flex items-center rounded-md bg-muted text-muted-foreground px-2 py-0.5 text-xs font-medium">
                      No
                    </span>
                  )}
                </p>
              </div>
              {modelInfo.training_start && modelInfo.training_end && (
                <div>
                  <p className="text-muted-foreground text-xs font-medium mb-0.5">Training window</p>
                  <p className="text-xs">{formatDateRange(modelInfo.training_start, modelInfo.training_end)}</p>
                </div>
              )}
            </div>
            {modelInfo.best_params && Object.keys(modelInfo.best_params).length > 0 && (
              <div className="mt-4 pt-4 border-t border-border">
                <p className="text-muted-foreground text-xs font-medium mb-2">
                  {modelInfo.tuned ? "Best hyperparameters" : "Model parameters"}
                </p>
                <div className="flex flex-wrap gap-2">
                  {Object.entries(modelInfo.best_params).map(([k, v]) => (
                    <span
                      key={k}
                      className="inline-flex items-center rounded-md bg-muted px-2.5 py-1 text-xs font-mono"
                    >
                      {k}={String(v ?? "None")}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Per-regime performance breakdown */}
      {run.status === "completed" && regimePerformance && regimePerformance.regimes.length > 0 && (
        <Card className="mt-6">
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Performance by regime</CardTitle>
            <CardDescription>
              Trade results grouped by the market regime each trade occurred in
              {regimePerformance.total_trades_matched > 0
                ? ` (${regimePerformance.total_trades_matched} trade${regimePerformance.total_trades_matched !== 1 ? "s" : ""} matched)`
                : ""}
            </CardDescription>
          </CardHeader>
          <CardContent className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border">
                  <th className="text-left py-3 px-2 font-medium">Regime</th>
                  <th className="text-right py-3 px-2 font-medium">Bars</th>
                  <th className="text-right py-3 px-2 font-medium">Trades</th>
                  <th className="text-right py-3 px-2 font-medium">W / L</th>
                  <th className="text-right py-3 px-2 font-medium">Win rate</th>
                  <th className="text-right py-3 px-2 font-medium">Total PnL</th>
                  <th className="text-right py-3 px-2 font-medium">Avg PnL</th>
                </tr>
              </thead>
              <tbody>
                {regimePerformance.regimes.map((r) => {
                  const dotColors: Record<string, string> = {
                    trend: "bg-emerald-500",
                    range: "bg-blue-500",
                    high_vol: "bg-red-500",
                  };
                  return (
                    <tr
                      key={r.regime}
                      className="border-b border-border/80 hover:bg-muted/50"
                    >
                      <td className="py-3 px-2">
                        <div className="flex items-center gap-2">
                          <span className={`inline-block h-2.5 w-2.5 rounded-full ${dotColors[r.regime] ?? "bg-gray-400"}`} />
                          <span className="font-medium">{r.label}</span>
                        </div>
                      </td>
                      <td className="py-3 px-2 text-right tabular-nums text-muted-foreground">
                        {r.bars} <span className="text-xs opacity-70">({r.bars_pct}%)</span>
                      </td>
                      <td className="py-3 px-2 text-right tabular-nums">
                        {r.num_trades}
                      </td>
                      <td className="py-3 px-2 text-right tabular-nums text-muted-foreground">
                        {r.num_trades > 0 ? `${r.wins} / ${r.losses}` : "—"}
                      </td>
                      <td className="py-3 px-2 text-right tabular-nums">
                        {r.win_rate != null ? (
                          <span
                            className={
                              r.win_rate >= 50
                                ? "text-emerald-600 dark:text-emerald-400"
                                : "text-destructive"
                            }
                          >
                            {r.win_rate.toFixed(1)}%
                          </span>
                        ) : (
                          <span className="text-muted-foreground">—</span>
                        )}
                      </td>
                      <td className="py-3 px-2 text-right tabular-nums">
                        {r.num_trades > 0 ? (
                          <span
                            className={
                              r.total_pnl >= 0
                                ? "text-emerald-600 dark:text-emerald-400"
                                : "text-destructive"
                            }
                          >
                            {r.total_pnl >= 0 ? "+" : ""}
                            {formatNumber(r.total_pnl)}
                          </span>
                        ) : (
                          <span className="text-muted-foreground">—</span>
                        )}
                      </td>
                      <td className="py-3 px-2 text-right tabular-nums">
                        {r.avg_pnl != null ? (
                          <span
                            className={
                              r.avg_pnl >= 0
                                ? "text-emerald-600 dark:text-emerald-400"
                                : "text-destructive"
                            }
                          >
                            {r.avg_pnl >= 0 ? "+" : ""}
                            {formatNumber(r.avg_pnl)}
                          </span>
                        ) : (
                          <span className="text-muted-foreground">—</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </CardContent>
        </Card>
      )}

      {/* Trades table */}
      <Card className="mt-6">
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Trades</CardTitle>
          <CardDescription>
            {run.trades.length === 0
              ? "No trades for this run."
              : `${run.trades.length} trade${run.trades.length !== 1 ? "s" : ""}.`}
          </CardDescription>
        </CardHeader>
        {run.trades.length > 0 ? (
          <CardContent className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border">
                  <th className="text-left py-3 px-2 font-medium">
                    Timestamp
                  </th>
                  <th className="text-left py-3 px-2 font-medium">
                    Side
                  </th>
                  <th className="text-right py-3 px-2 font-medium">
                    Price
                  </th>
                  <th className="text-right py-3 px-2 font-medium">
                    Quantity
                  </th>
                  <th className="text-right py-3 px-2 font-medium">
                    Fee
                  </th>
                  <th className="text-right py-3 px-2 font-medium">
                    Slippage
                  </th>
                  <th className="text-right py-3 px-2 font-medium">
                    PnL
                  </th>
                </tr>
              </thead>
              <tbody>
                {run.trades.map((trade) => (
                  <tr
                    key={trade.id}
                    className="border-b border-border/80 hover:bg-muted/50"
                  >
                    <td className="py-3 px-2 text-muted-foreground whitespace-nowrap">
                      {formatTimestamp(trade.timestamp)}
                    </td>
                    <td className="py-3 px-2 capitalize">{trade.side}</td>
                    <td className="py-3 px-2 text-right tabular-nums">
                      {formatNumber(trade.price)}
                    </td>
                    <td className="py-3 px-2 text-right tabular-nums">
                      {formatNumber(trade.quantity)}
                    </td>
                    <td className="py-3 px-2 text-right tabular-nums text-muted-foreground">
                      {formatNumber(trade.fee)}
                    </td>
                    <td className="py-3 px-2 text-right tabular-nums text-muted-foreground">
                      {formatNumber(trade.slippage)}
                    </td>
                    <td className="py-3 px-2 text-right tabular-nums">
                      {trade.pnl != null ? (
                        <span
                          className={
                            trade.pnl >= 0
                              ? "text-emerald-600 dark:text-emerald-400"
                              : "text-destructive"
                          }
                        >
                          {trade.pnl >= 0 ? "+" : ""}
                          {formatNumber(trade.pnl)}
                        </span>
                      ) : (
                        <span className="text-muted-foreground">—</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        ) : null}
      </Card>
    </>
  );
}

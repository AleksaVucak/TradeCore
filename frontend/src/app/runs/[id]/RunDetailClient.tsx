"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  backtestsApi,
  marketDataApi,
  type BacktestRunDetail,
  type CandleResponse,
} from "@/lib/api/endpoints";
import { getToken } from "@/lib/auth";
import {
  CandlestickChart,
  type OhlcCandle,
  type TradeMarker,
} from "@/components/charts/CandlestickChart";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from "recharts";

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

  useEffect(() => {
    const token = getToken();
    if (!token) {
      setError("Please log in to view this run.");
      setLoading(false);
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

  const chartData = useMemo(() => {
    if (!run?.equity_curve || run.equity_curve.length === 0) return [];
    return [...run.equity_curve]
      .sort(
        (a, b) =>
          new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
      )
      .map((p) => ({
        timestamp: p.timestamp,
        equity_value: p.equity_value,
      }));
  }, [run?.equity_curve]);

  const hasEquityData = chartData.length > 0;

  const equityDomain = useMemo(() => {
    if (!hasEquityData) return { min: 0, max: 0, initial: 0 };
    const values = chartData.map((d) => d.equity_value);
    const min = Math.min(...values);
    const max = Math.max(...values);
    const initial = values[0];
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

  useEffect(() => {
    if (!run || run.status !== "completed") return;
    const token = getToken();
    if (!token) return;
    setCandlesLoading(true);
    marketDataApi
      .candles(token, {
        symbol_id: run.symbol_id,
        timeframe: run.timeframe,
        start: run.start_time,
        end: run.end_time,
        limit: 5000,
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

  const tradeMarkers: TradeMarker[] = useMemo(() => {
    if (!run?.trades || run.trades.length === 0) return [];
    return run.trades.map((t) => ({
      timestamp: t.timestamp,
      side: t.side as "buy" | "sell",
      price: t.price,
    }));
  }, [run?.trades]);

  if (loading) {
    return (
      <div className="mt-4">
        <p className="text-muted-foreground">Loading run…</p>
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
            Metrics
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
          </div>
        </div>
      )}

      {/* Equity curve chart */}
      <Card className="mt-6">
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Equity curve</CardTitle>
          <CardDescription>
            {hasEquityData
              ? `Equity over time (${chartData.length} point${chartData.length !== 1 ? "s" : ""})`
              : "No equity data for this run."}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {hasEquityData ? (
            <div className="h-[320px] w-full">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart
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
                    dataKey="equity_value"
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
                    formatter={(value: number | undefined) => [
                      (value ?? 0).toLocaleString(undefined, {
                        minimumFractionDigits: 2,
                        maximumFractionDigits: 2,
                      }),
                      "Equity",
                    ]}
                    labelFormatter={(label) =>
                      new Date(label).toLocaleString(undefined, {
                        dateStyle: "medium",
                        timeStyle: "short",
                      })
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
                </AreaChart>
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
              <CandlestickChart candles={ohlcCandles} trades={tradeMarkers} />
            )}
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

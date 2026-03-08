"use client";

import Link from "next/link";
import { type ReactNode, useEffect, useMemo, useState } from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  backtestsApi,
  type BacktestRunDetail,
  type BacktestRunListItem,
  type EquityPointOut,
} from "@/lib/api/endpoints";
import { getToken } from "@/lib/auth";
import {
  Area,
  ComposedChart,
  Line,
  LineChart,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
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

type MetricDef = {
  key: string;
  label: string;
  format: (v: number) => string;
  higherIsBetter: boolean;
};

const METRIC_DEFS: MetricDef[] = [
  {
    key: "total_return_pct",
    label: "Total return",
    format: (v) => formatPct(v),
    higherIsBetter: true,
  },
  {
    key: "max_drawdown_pct",
    label: "Max drawdown",
    format: (v) => `${v.toFixed(2)}%`,
    higherIsBetter: false,
  },
  {
    key: "num_trades",
    label: "Trades",
    format: (v) => String(Math.round(v)),
    higherIsBetter: true,
  },
  {
    key: "win_rate",
    label: "Win rate",
    format: (v) => `${v.toFixed(1)}%`,
    higherIsBetter: true,
  },
  {
    key: "sharpe_ratio",
    label: "Sharpe ratio",
    format: (v) => v.toFixed(2),
    higherIsBetter: true,
  },
  {
    key: "profit_factor",
    label: "Profit factor",
    format: (v) => v.toFixed(2),
    higherIsBetter: true,
  },
  {
    key: "final_equity",
    label: "Final equity",
    format: (v) => formatNumber(v),
    higherIsBetter: true,
  },
  {
    key: "annualized_return_pct",
    label: "Ann. return",
    format: (v) => formatPct(v),
    higherIsBetter: true,
  },
];

function getWinner(
  a: number | undefined,
  b: number | undefined,
  higherIsBetter: boolean,
): "a" | "b" | "tie" | "none" {
  if (a == null && b == null) return "none";
  if (a == null) return "b";
  if (b == null) return "a";
  if (a === b) return "tie";
  if (higherIsBetter) return a > b ? "a" : "b";
  return a < b ? "a" : "b";
}

function RunHeaderCard({
  label,
  run,
}: {
  label: string;
  run: BacktestRunDetail;
}) {
  return (
    <Card className="flex-1 min-w-0">
      <CardHeader className="pb-3">
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            {label}
          </span>
          <StatusBadge status={run.status} />
        </div>
        <CardTitle className="text-base mt-1">
          <Link
            href={`/runs/${run.id}`}
            className="text-primary underline-offset-4 hover:underline"
          >
            {run.id.slice(0, 8)}…
          </Link>
        </CardTitle>
        <CardDescription>
          {run.timeframe} · {formatDateRange(run.start_time, run.end_time)}
        </CardDescription>
      </CardHeader>
    </Card>
  );
}

function MetricsComparisonTable({
  runA,
  runB,
}: {
  runA: BacktestRunDetail;
  runB: BacktestRunDetail;
}) {
  const metricsA =
    runA.status === "completed" && runA.metrics
      ? (runA.metrics as Record<string, number>)
      : null;
  const metricsB =
    runB.status === "completed" && runB.metrics
      ? (runB.metrics as Record<string, number>)
      : null;

  if (!metricsA && !metricsB) {
    return (
      <Card className="mt-6">
        <CardHeader>
          <CardTitle className="text-base">Metrics comparison</CardTitle>
          <CardDescription>
            Neither run has metrics available.
          </CardDescription>
        </CardHeader>
      </Card>
    );
  }

  const availableMetrics = METRIC_DEFS.filter(
    (m) =>
      (metricsA && typeof metricsA[m.key] === "number") ||
      (metricsB && typeof metricsB[m.key] === "number"),
  );

  const winsA = availableMetrics.filter((m) => {
    const valA = metricsA?.[m.key];
    const valB = metricsB?.[m.key];
    return getWinner(valA, valB, m.higherIsBetter) === "a";
  }).length;

  const winsB = availableMetrics.filter((m) => {
    const valA = metricsA?.[m.key];
    const valB = metricsB?.[m.key];
    return getWinner(valA, valB, m.higherIsBetter) === "b";
  }).length;

  return (
    <Card className="mt-6">
      <CardHeader className="pb-2">
        <CardTitle className="text-base">Metrics comparison</CardTitle>
        <CardDescription>
          Side-by-side metrics with better value highlighted
          <span className="ml-2 text-xs">
            (Run A wins {winsA} · Run B wins {winsB})
          </span>
        </CardDescription>
      </CardHeader>
      <CardContent className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border">
              <th className="text-left py-3 px-2 font-medium">Metric</th>
              <th className="text-right py-3 px-2 font-medium">
                <span className="inline-flex items-center gap-1.5">
                  Run A
                </span>
              </th>
              <th className="text-right py-3 px-2 font-medium">
                <span className="inline-flex items-center gap-1.5">
                  Run B
                </span>
              </th>
              <th className="text-center py-3 px-2 font-medium w-20">
                Better
              </th>
            </tr>
          </thead>
          <tbody>
            {availableMetrics.map((m) => {
              const valA = metricsA?.[m.key];
              const valB = metricsB?.[m.key];
              const winner = getWinner(valA, valB, m.higherIsBetter);

              const cellA =
                typeof valA === "number" ? m.format(valA) : "—";
              const cellB =
                typeof valB === "number" ? m.format(valB) : "—";

              const winClassA =
                winner === "a"
                  ? "text-emerald-600 dark:text-emerald-400 font-semibold"
                  : "";
              const winClassB =
                winner === "b"
                  ? "text-emerald-600 dark:text-emerald-400 font-semibold"
                  : "";

              return (
                <tr
                  key={m.key}
                  className="border-b border-border/80 hover:bg-muted/50"
                >
                  <td className="py-3 px-2 font-medium">{m.label}</td>
                  <td
                    className={`py-3 px-2 text-right tabular-nums ${winClassA}`}
                  >
                    {cellA}
                  </td>
                  <td
                    className={`py-3 px-2 text-right tabular-nums ${winClassB}`}
                  >
                    {cellB}
                  </td>
                  <td className="py-3 px-2 text-center">
                    {winner === "a" && (
                      <span className="inline-flex items-center rounded-md bg-emerald-500/15 text-emerald-700 dark:text-emerald-400 px-2 py-0.5 text-xs font-medium">
                        A
                      </span>
                    )}
                    {winner === "b" && (
                      <span className="inline-flex items-center rounded-md bg-blue-500/15 text-blue-700 dark:text-blue-400 px-2 py-0.5 text-xs font-medium">
                        B
                      </span>
                    )}
                    {winner === "tie" && (
                      <span className="inline-flex items-center rounded-md bg-muted text-muted-foreground px-2 py-0.5 text-xs font-medium">
                        Tie
                      </span>
                    )}
                    {winner === "none" && (
                      <span className="text-muted-foreground text-xs">—</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </CardContent>
    </Card>
  );
}

type EquityChartPoint = {
  timestamp: string;
  equity_a?: number;
  equity_b?: number;
};

type DrawdownChartPoint = {
  timestamp: string;
  drawdown_a?: number;
  drawdown_b?: number;
};

function sortEquity(curve: EquityPointOut[]): EquityPointOut[] {
  return [...curve].sort(
    (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime(),
  );
}

function computeDrawdownSeries(
  sorted: EquityPointOut[],
): { timestamp: string; drawdown: number }[] {
  let peak = -Infinity;
  return sorted.map((p) => {
    if (p.equity_value > peak) peak = p.equity_value;
    const dd = peak > 0 ? ((peak - p.equity_value) / peak) * 100 : 0;
    return { timestamp: p.timestamp, drawdown: Math.round(dd * 100) / 100 };
  });
}

function mergeEquitySeries(
  curveA: EquityPointOut[],
  curveB: EquityPointOut[],
): EquityChartPoint[] {
  const mapA = new Map<number, number>();
  for (const p of curveA) mapA.set(new Date(p.timestamp).getTime(), p.equity_value);
  const mapB = new Map<number, number>();
  for (const p of curveB) mapB.set(new Date(p.timestamp).getTime(), p.equity_value);

  const allTimes = new Set([...mapA.keys(), ...mapB.keys()]);
  const sorted = [...allTimes].sort((a, b) => a - b);

  return sorted.map((t) => ({
    timestamp: new Date(t).toISOString(),
    equity_a: mapA.get(t),
    equity_b: mapB.get(t),
  }));
}

function mergeDrawdownSeries(
  ddA: { timestamp: string; drawdown: number }[],
  ddB: { timestamp: string; drawdown: number }[],
): DrawdownChartPoint[] {
  const mapA = new Map<number, number>();
  for (const p of ddA) mapA.set(new Date(p.timestamp).getTime(), p.drawdown);
  const mapB = new Map<number, number>();
  for (const p of ddB) mapB.set(new Date(p.timestamp).getTime(), p.drawdown);

  const allTimes = new Set([...mapA.keys(), ...mapB.keys()]);
  const sorted = [...allTimes].sort((a, b) => a - b);

  return sorted.map((t) => ({
    timestamp: new Date(t).toISOString(),
    drawdown_a: mapA.get(t),
    drawdown_b: mapB.get(t),
  }));
}

function ensureMinimalCurve(
  run: BacktestRunDetail,
): EquityPointOut[] {
  const curve = run.equity_curve ?? [];
  if (curve.length > 0) return curve;
  if (run.status !== "completed") return [];
  const initialValue =
    (run.metrics as Record<string, number> | null)?.final_equity ?? 10_000;
  return [
    { timestamp: run.start_time, equity_value: initialValue },
    { timestamp: run.end_time, equity_value: initialValue },
  ];
}

const CHART_STYLE = {
  grid: { strokeDasharray: "3 3", stroke: "hsl(var(--border))", opacity: 0.4 },
  xTick: { fill: "hsl(var(--muted-foreground))", fontSize: 11 },
  xAxis: { stroke: "hsl(var(--border))" },
  yTick: { fill: "hsl(var(--muted-foreground))", fontSize: 11 },
  tooltip: {
    backgroundColor: "hsl(var(--card))",
    border: "1px solid hsl(var(--border))",
    borderRadius: "var(--radius)",
    fontSize: 12,
  },
};

function EquityComparisonChart({
  runA,
  runB,
}: {
  runA: BacktestRunDetail;
  runB: BacktestRunDetail;
}) {
  const data = useMemo(() => {
    const sortedA = sortEquity(ensureMinimalCurve(runA));
    const sortedB = sortEquity(ensureMinimalCurve(runB));
    return mergeEquitySeries(sortedA, sortedB);
  }, [runA, runB]);

  if (data.length === 0) {
    return (
      <Card className="mt-6">
        <CardHeader>
          <CardTitle className="text-base">Equity comparison</CardTitle>
          <CardDescription>
            No equity data available for either run.
          </CardDescription>
        </CardHeader>
      </Card>
    );
  }

  return (
    <Card className="mt-6">
      <CardHeader className="pb-2">
        <CardTitle className="text-base">Equity comparison</CardTitle>
        <CardDescription>
          Absolute account value over time — Run A (green) vs Run B (blue)
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="h-[340px] w-full">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart
              data={data}
              margin={{ top: 10, right: 10, left: 28, bottom: 5 }}
            >
              <CartesianGrid {...CHART_STYLE.grid} />
              <XAxis
                dataKey="timestamp"
                tickFormatter={(ts: string) =>
                  new Date(ts).toLocaleDateString(undefined, {
                    month: "short",
                    day: "numeric",
                  })
                }
                tick={CHART_STYLE.xTick}
                axisLine={CHART_STYLE.xAxis}
                tickLine={CHART_STYLE.xAxis}
              />
              <YAxis
                tickFormatter={(v: number) =>
                  v >= 1000 ? `${(v / 1000).toFixed(1)}k` : String(v)
                }
                tick={CHART_STYLE.yTick}
                axisLine={CHART_STYLE.xAxis}
                tickLine={CHART_STYLE.xAxis}
                domain={["auto", "auto"]}
                label={{
                  value: "Equity ($)",
                  angle: -90,
                  position: "insideLeft",
                  style: { fill: "hsl(var(--muted-foreground))", fontSize: 11 },
                }}
              />
              <Tooltip
                contentStyle={CHART_STYLE.tooltip}
                labelStyle={{ color: "hsl(var(--foreground))" }}
                labelFormatter={(label: ReactNode) =>
                  new Date(String(label)).toLocaleString(undefined, {
                    dateStyle: "medium",
                    timeStyle: "short",
                  })
                }
                formatter={(
                  value: number | undefined,
                  name: string | undefined,
                ) => [
                  value != null
                    ? value.toLocaleString(undefined, {
                        minimumFractionDigits: 2,
                        maximumFractionDigits: 2,
                      })
                    : "—",
                  name === "equity_a" ? "Run A" : "Run B",
                ]}
              />
              <Legend
                formatter={(value: string) =>
                  value === "equity_a" ? "Run A" : "Run B"
                }
              />
              <Area
                type="monotone"
                dataKey="equity_a"
                fill="#22c55e"
                fillOpacity={0.12}
                stroke="none"
                legendType="none"
              />
              <Area
                type="monotone"
                dataKey="equity_b"
                fill="#3b82f6"
                fillOpacity={0.12}
                stroke="none"
                legendType="none"
              />
              <Line
                type="monotone"
                dataKey="equity_a"
                stroke="#22c55e"
                strokeWidth={2}
                dot={false}
                connectNulls
                activeDot={{ r: 3 }}
              />
              <Line
                type="monotone"
                dataKey="equity_b"
                stroke="#3b82f6"
                strokeWidth={2}
                dot={false}
                connectNulls
                activeDot={{ r: 3 }}
              />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  );
}

function DrawdownComparisonChart({
  runA,
  runB,
}: {
  runA: BacktestRunDetail;
  runB: BacktestRunDetail;
}) {
  const data = useMemo(() => {
    const sortedA = sortEquity(ensureMinimalCurve(runA));
    const sortedB = sortEquity(ensureMinimalCurve(runB));
    const ddA = computeDrawdownSeries(sortedA);
    const ddB = computeDrawdownSeries(sortedB);
    return mergeDrawdownSeries(ddA, ddB);
  }, [runA, runB]);

  if (data.length === 0) {
    return (
      <Card className="mt-6">
        <CardHeader>
          <CardTitle className="text-base">Drawdown comparison</CardTitle>
          <CardDescription>
            No equity data available to compute drawdown.
          </CardDescription>
        </CardHeader>
      </Card>
    );
  }

  return (
    <Card className="mt-6">
      <CardHeader className="pb-2">
        <CardTitle className="text-base">Drawdown comparison</CardTitle>
        <CardDescription>
          Peak-to-trough drawdown (%) — Run A (red) vs Run B (orange); lower is better
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="h-[300px] w-full">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart
              data={data}
              margin={{ top: 10, right: 10, left: 28, bottom: 5 }}
            >
              <CartesianGrid {...CHART_STYLE.grid} />
              <XAxis
                dataKey="timestamp"
                tickFormatter={(ts: string) =>
                  new Date(ts).toLocaleDateString(undefined, {
                    month: "short",
                    day: "numeric",
                  })
                }
                tick={CHART_STYLE.xTick}
                axisLine={CHART_STYLE.xAxis}
                tickLine={CHART_STYLE.xAxis}
              />
              <YAxis
                tickFormatter={(v: number) => `${v.toFixed(1)}%`}
                tick={CHART_STYLE.yTick}
                axisLine={CHART_STYLE.xAxis}
                tickLine={CHART_STYLE.xAxis}
                reversed
                domain={["auto", 0]}
                label={{
                  value: "Drawdown (%)",
                  angle: -90,
                  position: "insideLeft",
                  style: { fill: "hsl(var(--muted-foreground))", fontSize: 11 },
                }}
              />
              <Tooltip
                contentStyle={CHART_STYLE.tooltip}
                labelStyle={{ color: "hsl(var(--foreground))" }}
                labelFormatter={(label: ReactNode) =>
                  new Date(String(label)).toLocaleString(undefined, {
                    dateStyle: "medium",
                    timeStyle: "short",
                  })
                }
                formatter={(
                  value: number | undefined,
                  name: string | undefined,
                ) => [
                  value != null ? `${value.toFixed(2)}%` : "—",
                  name === "drawdown_a" ? "Run A" : "Run B",
                ]}
              />
              <Legend
                formatter={(value: string) =>
                  value === "drawdown_a" ? "Run A" : "Run B"
                }
              />
              <Line
                type="monotone"
                dataKey="drawdown_a"
                stroke="#ef4444"
                strokeWidth={2}
                dot={false}
                connectNulls
                activeDot={{ r: 3 }}
              />
              <Line
                type="monotone"
                dataKey="drawdown_b"
                stroke="#f97316"
                strokeWidth={2}
                dot={false}
                connectNulls
                activeDot={{ r: 3 }}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  );
}

export default function CompareRunsPage() {
  const [runs, setRuns] = useState<BacktestRunListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [runIdA, setRunIdA] = useState<string>("");
  const [runIdB, setRunIdB] = useState<string>("");

  const [runA, setRunA] = useState<BacktestRunDetail | null>(null);
  const [runB, setRunB] = useState<BacktestRunDetail | null>(null);
  const [loadingA, setLoadingA] = useState(false);
  const [loadingB, setLoadingB] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  useEffect(() => {
    const token = getToken();
    if (!token) {
      queueMicrotask(() => {
        setError("Please log in to compare runs.");
        setLoading(false);
      });
      return;
    }
    backtestsApi
      .list(token)
      .then((data) => {
        setRuns(data);
        setError(null);
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : "Failed to load runs");
        setRuns([]);
      })
      .finally(() => setLoading(false));
  }, []);

  const completedRuns = runs.filter((r) => r.status === "completed");

  function handleCompare() {
    if (!runIdA || !runIdB) return;
    const token = getToken();
    if (!token) return;

    setDetailError(null);
    setRunA(null);
    setRunB(null);
    setLoadingA(true);
    setLoadingB(true);

    backtestsApi
      .get(token, runIdA)
      .then((data) => setRunA(data))
      .catch(() => setDetailError("Failed to load Run A."))
      .finally(() => setLoadingA(false));

    backtestsApi
      .get(token, runIdB)
      .then((data) => setRunB(data))
      .catch(() =>
        setDetailError((p) =>
          p ? `${p} Failed to load Run B.` : "Failed to load Run B."
        )
      )
      .finally(() => setLoadingB(false));
  }

  const canCompare = runIdA && runIdB && runIdA !== runIdB;

  return (
    <div className="min-h-screen bg-background">
      <header className="border-b border-border px-6 py-4">
        <Link
          href="/backtests"
          className="text-muted-foreground hover:text-foreground text-sm"
        >
          ← Run history
        </Link>
        <h1 className="text-xl font-semibold tracking-tight mt-2">
          Compare runs
        </h1>
        <p className="text-muted-foreground text-sm mt-1">
          Select two completed runs to compare side by side
        </p>
      </header>
      <main className="container mx-auto max-w-5xl px-6 py-8">
        {error && (
          <Card className="mb-6 border-destructive/50">
            <CardHeader className="pb-2">
              <CardTitle className="text-base text-destructive">Something went wrong</CardTitle>
              <CardDescription>{error}</CardDescription>
            </CardHeader>
            <CardContent>
              <button
                onClick={() => window.location.reload()}
                className="text-sm font-medium text-primary underline-offset-4 hover:underline"
              >
                Try again
              </button>
            </CardContent>
          </Card>
        )}

        {loading ? (
          <Card>
            <CardHeader className="pb-2">
              <Skeleton className="h-5 w-28" />
              <Skeleton className="h-4 w-52 mt-1" />
            </CardHeader>
            <CardContent>
              <div className="flex flex-col sm:flex-row gap-4 items-end">
                <Skeleton className="h-10 flex-1" />
                <Skeleton className="h-10 flex-1" />
                <Skeleton className="h-10 w-24" />
              </div>
            </CardContent>
          </Card>
        ) : completedRuns.length < 2 ? (
          <Card>
            <CardHeader>
              <CardTitle className="text-base">
                Not enough completed runs
              </CardTitle>
              <CardDescription>
                You need at least 2 completed backtest runs to use the
                comparison view. Run more backtests first.
              </CardDescription>
            </CardHeader>
          </Card>
        ) : (
          <>
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-base">Select runs</CardTitle>
                <CardDescription>
                  Pick two completed runs to compare ({completedRuns.length}{" "}
                  available)
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="flex flex-col sm:flex-row gap-4 items-end">
                  <div className="flex-1 min-w-0">
                    <label
                      htmlFor="run-a"
                      className="block text-xs font-medium text-muted-foreground mb-1.5"
                    >
                      Run A
                    </label>
                    <select
                      id="run-a"
                      value={runIdA}
                      onChange={(e) => setRunIdA(e.target.value)}
                      className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                    >
                      <option value="">Select a run…</option>
                      {completedRuns.map((r) => (
                        <option key={r.id} value={r.id} disabled={r.id === runIdB}>
                          {r.id.slice(0, 8)}… · {r.symbol_name ?? r.symbol_id} ·{" "}
                          {r.timeframe} · {formatPct(r.total_return_pct)}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div className="hidden sm:flex items-center justify-center px-2 text-muted-foreground text-lg font-light">
                    vs
                  </div>

                  <div className="flex-1 min-w-0">
                    <label
                      htmlFor="run-b"
                      className="block text-xs font-medium text-muted-foreground mb-1.5"
                    >
                      Run B
                    </label>
                    <select
                      id="run-b"
                      value={runIdB}
                      onChange={(e) => setRunIdB(e.target.value)}
                      className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                    >
                      <option value="">Select a run…</option>
                      {completedRuns.map((r) => (
                        <option key={r.id} value={r.id} disabled={r.id === runIdA}>
                          {r.id.slice(0, 8)}… · {r.symbol_name ?? r.symbol_id} ·{" "}
                          {r.timeframe} · {formatPct(r.total_return_pct)}
                        </option>
                      ))}
                    </select>
                  </div>

                  <Button
                    onClick={handleCompare}
                    disabled={!canCompare}
                    className="sm:self-end"
                  >
                    Compare
                  </Button>
                </div>
                {runIdA && runIdB && runIdA === runIdB && (
                  <p className="text-destructive text-xs mt-2">
                    Please select two different runs.
                  </p>
                )}
              </CardContent>
            </Card>

            {detailError && (
              <Card className="mt-4 border-destructive/50">
                <CardHeader className="pb-2">
                  <CardTitle className="text-base text-destructive">Failed to load runs</CardTitle>
                  <CardDescription>{detailError}</CardDescription>
                </CardHeader>
                <CardContent>
                  <button
                    onClick={handleCompare}
                    className="text-sm font-medium text-primary underline-offset-4 hover:underline"
                  >
                    Retry
                  </button>
                </CardContent>
              </Card>
            )}

            {(loadingA || loadingB) && (
              <div className="mt-6 space-y-6">
                <div className="flex flex-col md:flex-row gap-4">
                  <Card className="flex-1 min-w-0">
                    <CardHeader className="pb-3">
                      <Skeleton className="h-4 w-12" />
                      <Skeleton className="h-5 w-24 mt-1" />
                      <Skeleton className="h-4 w-40 mt-1" />
                    </CardHeader>
                  </Card>
                  <Card className="flex-1 min-w-0">
                    <CardHeader className="pb-3">
                      <Skeleton className="h-4 w-12" />
                      <Skeleton className="h-5 w-24 mt-1" />
                      <Skeleton className="h-4 w-40 mt-1" />
                    </CardHeader>
                  </Card>
                </div>
                <Card>
                  <CardHeader className="pb-2">
                    <Skeleton className="h-5 w-40" />
                    <Skeleton className="h-4 w-64 mt-1" />
                  </CardHeader>
                  <CardContent className="space-y-3">
                    {Array.from({ length: 6 }).map((_, i) => (
                      <div key={i} className="flex items-center gap-4">
                        <Skeleton className="h-4 w-28" />
                        <Skeleton className="h-4 w-20 ml-auto" />
                        <Skeleton className="h-4 w-20" />
                        <Skeleton className="h-5 w-8 rounded-md" />
                      </div>
                    ))}
                  </CardContent>
                </Card>
              </div>
            )}

            {runA && runB && !loadingA && !loadingB && (
              <>
                <div className="mt-6 flex flex-col md:flex-row gap-4">
                  <RunHeaderCard label="Run A" run={runA} />
                  <RunHeaderCard label="Run B" run={runB} />
                </div>
                <MetricsComparisonTable runA={runA} runB={runB} />
                <EquityComparisonChart runA={runA} runB={runB} />
                <DrawdownComparisonChart runA={runA} runB={runB} />
              </>
            )}
          </>
        )}
      </main>
    </div>
  );
}

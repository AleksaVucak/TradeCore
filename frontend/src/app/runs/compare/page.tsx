"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  backtestsApi,
  type BacktestRunDetail,
  type BacktestRunListItem,
} from "@/lib/api/endpoints";
import { getToken } from "@/lib/auth";

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
      setError("Please log in to compare runs.");
      setLoading(false);
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
          <p className="text-destructive text-sm mb-4">{error}</p>
        )}

        {loading ? (
          <p className="text-muted-foreground text-sm">Loading runs…</p>
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
              <p className="text-destructive text-sm mt-4">{detailError}</p>
            )}

            {(loadingA || loadingB) && (
              <p className="text-muted-foreground text-sm mt-6">
                Loading run details…
              </p>
            )}

            {runA && runB && !loadingA && !loadingB && (
              <>
                <div className="mt-6 flex flex-col md:flex-row gap-4">
                  <RunHeaderCard label="Run A" run={runA} />
                  <RunHeaderCard label="Run B" run={runB} />
                </div>
                <MetricsComparisonTable runA={runA} runB={runB} />
              </>
            )}
          </>
        )}
      </main>
    </div>
  );
}

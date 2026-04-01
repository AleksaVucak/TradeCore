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
import { Skeleton } from "@/components/ui/skeleton";
import { backtestsApi, type BacktestRunListItem } from "@/lib/api/endpoints";
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

export default function BacktestsPage() {
  const [runs, setRuns] = useState<BacktestRunListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const token = getToken();
    if (!token) {
      queueMicrotask(() => {
        setError("Please log in to view run history.");
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

  return (
    <div className="min-h-screen bg-background">
      <header className="border-b border-border px-6 py-4">
        <Link
          href="/"
          className="text-muted-foreground hover:text-foreground text-sm"
        >
          ← Dashboard
        </Link>
        <div className="flex items-center justify-between mt-2">
          <div>
            <h1 className="text-xl font-semibold tracking-tight">
              Run history
            </h1>
            <p className="text-muted-foreground text-sm mt-1">
              Table of backtest runs: status, symbol, strategy, return, drawdown
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Link
              href="/backtests/walk-forward"
              className="inline-flex items-center justify-center rounded-md border border-input bg-background px-4 py-2 text-sm font-medium hover:bg-accent hover:text-accent-foreground transition-colors"
            >
              Walk-forward
            </Link>
            <Link
              href="/backtests/new"
              className="inline-flex items-center justify-center rounded-md bg-primary text-primary-foreground px-4 py-2 text-sm font-medium hover:bg-primary/90 transition-colors"
            >
              New backtest
            </Link>
          </div>
        </div>
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
              <Skeleton className="h-5 w-24" />
              <Skeleton className="h-4 w-48 mt-1" />
            </CardHeader>
            <CardContent className="space-y-3">
              {Array.from({ length: 5 }).map((_, i) => (
                <div key={i} className="flex items-center gap-4">
                  <Skeleton className="h-4 w-20" />
                  <Skeleton className="h-5 w-16 rounded-md" />
                  <Skeleton className="h-4 w-12" />
                  <Skeleton className="h-4 w-24 hidden sm:block" />
                  <Skeleton className="h-4 w-16 ml-auto" />
                  <Skeleton className="h-4 w-16 hidden sm:block" />
                </div>
              ))}
            </CardContent>
          </Card>
        ) : runs.length === 0 ? (
          <Card>
            <CardHeader>
              <CardTitle className="text-base">No runs yet</CardTitle>
              <CardDescription>
                Create a backtest or run walk-forward validation from the app to start analyzing a
                strategy.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="flex flex-wrap gap-4">
                <Link
                  href="/backtests/new"
                  className="text-sm font-medium text-primary underline-offset-4 hover:underline"
                >
                  Start a new backtest
                </Link>
                <Link
                  href="/backtests/walk-forward"
                  className="text-sm font-medium text-primary underline-offset-4 hover:underline"
                >
                  Run walk-forward validation
                </Link>
              </div>
            </CardContent>
          </Card>
        ) : (
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-base">Runs</CardTitle>
              <CardDescription>
                {runs.length} run{runs.length !== 1 ? "s" : ""}. Click a run to
                view details.
              </CardDescription>
            </CardHeader>
            <CardContent className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border">
                    <th className="text-left py-3 px-2 font-medium">
                      Run
                    </th>
                    <th className="text-left py-3 px-2 font-medium">
                      Status
                    </th>
                    <th className="text-left py-3 px-2 font-medium hidden sm:table-cell">
                      Symbol
                    </th>
                    <th className="text-left py-3 px-2 font-medium hidden md:table-cell">
                      Strategy
                    </th>
                    <th className="text-right py-3 px-2 font-medium">
                      Return
                    </th>
                    <th className="text-right py-3 px-2 font-medium hidden sm:table-cell">
                      Drawdown
                    </th>
                    <th className="text-left py-3 px-2 font-medium hidden lg:table-cell">
                      Timeframe
                    </th>
                    <th className="text-left py-3 px-2 font-medium hidden lg:table-cell">
                      Date range
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {runs.map((run) => (
                    <tr
                      key={run.id}
                      className="border-b border-border/80 hover:bg-muted/50"
                    >
                      <td className="py-3 px-2">
                        <Link
                          href={`/runs/${run.id}`}
                          className="text-primary font-medium underline-offset-4 hover:underline"
                        >
                          {run.id.slice(0, 8)}…
                        </Link>
                      </td>
                      <td className="py-3 px-2">
                        <StatusBadge status={run.status} />
                      </td>
                      <td className="py-3 px-2 text-muted-foreground hidden sm:table-cell">
                        {run.symbol_name ?? run.symbol_id}
                      </td>
                      <td className="py-3 px-2 text-muted-foreground hidden md:table-cell">
                        {run.strategy_name ?? "—"}
                      </td>
                      <td className="py-3 px-2 text-right tabular-nums">
                        {formatPct(run.total_return_pct)}
                      </td>
                      <td className="py-3 px-2 text-right tabular-nums text-muted-foreground hidden sm:table-cell">
                        {formatPct(run.max_drawdown_pct)}
                      </td>
                      <td className="py-3 px-2 text-muted-foreground hidden lg:table-cell">
                        {run.timeframe}
                      </td>
                      <td className="py-3 px-2 text-muted-foreground whitespace-nowrap hidden lg:table-cell">
                        {formatDateRange(run.start_time, run.end_time)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </CardContent>
          </Card>
        )}
      </main>
    </div>
  );
}

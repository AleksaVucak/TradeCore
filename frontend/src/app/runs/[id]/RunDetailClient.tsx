"use client";

import { useEffect, useState } from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { backtestsApi, type BacktestRunDetail } from "@/lib/api/endpoints";
import { getToken } from "@/lib/auth";

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

  return (
    <>
      <h1 className="text-xl font-semibold mt-4">
        Run {runId.slice(0, 8)}…
      </h1>
      <p className="text-muted-foreground mt-1 text-sm">
        {run.timeframe} · {run.start_time} – {run.end_time}
      </p>

      {hasErrorMessage && (
        <Card className="mt-4 border-destructive/50 bg-destructive/5">
          <CardHeader className="pb-2">
            <CardTitle className="text-base text-destructive">
              Run failed
            </CardTitle>
            <CardDescription>
              This backtest run failed. Error message (Phase 7.3):
            </CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-sm font-mono whitespace-pre-wrap wrap-break-word">
              {run.error_message}
            </p>
          </CardContent>
        </Card>
      )}

      <Card className="mt-4">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium text-muted-foreground">
            Status
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm font-medium capitalize">{run.status}</p>
          {run.status === "completed" && run.metrics && (
            <p className="text-muted-foreground text-sm mt-1">
              {run.metrics.num_trades ?? 0} trades · Final equity:{" "}
              {run.metrics.final_equity ?? "—"}
            </p>
          )}
        </CardContent>
      </Card>

      <p className="text-muted-foreground text-sm mt-4">
        Full run detail with charts and metrics (Phase 8).
      </p>
    </>
  );
}

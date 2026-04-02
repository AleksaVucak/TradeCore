"use client";

import { useEffect, useState } from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { backtestsApi, type MonteCarloResponse } from "@/lib/api/endpoints";
import { getToken } from "@/lib/auth";

function formatPct(value: number): string {
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
}

function formatNumber(value: number, decimals = 2): string {
  return value.toLocaleString(undefined, {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

type MonteCarloCardProps = {
  runId: string;
  runStatus: string;
  /** Count of sell trades with realized P&L (Monte Carlo needs at least 2). */
  closedTradeCount: number;
};

export function MonteCarloCard({
  runId,
  runStatus,
  closedTradeCount,
}: MonteCarloCardProps) {
  const [data, setData] = useState<MonteCarloResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const token = getToken();
  const shouldFetch =
    runStatus === "completed" && !!token && closedTradeCount >= 2;

  useEffect(() => {
    if (!shouldFetch) {
      return;
    }

    let cancelled = false;

    (async () => {
      setLoading(true);
      try {
        const res = await backtestsApi.postMonteCarlo(token!, runId, {
          num_simulations: 500,
          method: "bootstrap",
        });
        if (!cancelled) {
          setData(res);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) {
          const message = err instanceof Error ? err.message : "Failed to load Monte Carlo analysis";
          setError(message);
          setData(null);
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [runId, shouldFetch, token]);

  if (runStatus !== "completed") {
    return null;
  }

  if (!token) {
    return null;
  }

  if (closedTradeCount < 2) {
    return (
      <Card className="mt-6">
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Monte Carlo robustness</CardTitle>
          <CardDescription>
            Resampled trade P&amp;L paths (Phase 14.3). Requires at least two closed trades with
            realized P&amp;L. This run has {closedTradeCount}.
          </CardDescription>
        </CardHeader>
      </Card>
    );
  }

  if (loading) {
    return (
      <Card className="mt-6">
        <CardHeader className="pb-2">
          <Skeleton className="h-5 w-48" />
          <Skeleton className="h-4 w-72 mt-1" />
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-12 w-full" />
            ))}
          </div>
        </CardContent>
      </Card>
    );
  }

  if (error) {
    return (
      <Card className="mt-6 border-destructive/30">
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Monte Carlo robustness</CardTitle>
          <CardDescription className="text-destructive">{error}</CardDescription>
        </CardHeader>
      </Card>
    );
  }

  if (!data) {
    return null;
  }

  return (
    <Card className="mt-6">
      <CardHeader className="pb-2">
        <CardTitle className="text-base">Monte Carlo robustness</CardTitle>
        <CardDescription>
          {data.num_simulations} simulations · {data.method} · {data.num_closed_trades} closed
          trades · seed {data.seed ?? "random"}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        <div>
          <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-3">
            Return distribution
          </h3>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
            <div className="flex flex-col">
              <span className="text-xs text-muted-foreground font-medium">Median return</span>
              <span className="text-sm font-semibold tabular-nums">
                {formatPct(data.median_total_return_pct)}
              </span>
            </div>
            <div className="flex flex-col">
              <span className="text-xs text-muted-foreground font-medium">P5 / P95 return</span>
              <span className="text-sm font-semibold tabular-nums">
                {formatPct(data.p5_total_return_pct)} / {formatPct(data.p95_total_return_pct)}
              </span>
            </div>
            <div className="flex flex-col">
              <span className="text-xs text-muted-foreground font-medium">Best / worst</span>
              <span className="text-sm font-semibold tabular-nums">
                {formatPct(data.best_total_return_pct)} / {formatPct(data.worst_total_return_pct)}
              </span>
            </div>
            {data.original_total_return_pct != null && (
              <div className="flex flex-col">
                <span className="text-xs text-muted-foreground font-medium">Actual run return</span>
                <span className="text-sm font-semibold tabular-nums">
                  {formatPct(data.original_total_return_pct)}
                </span>
              </div>
            )}
          </div>
        </div>

        <div>
          <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-3">
            Final equity
          </h3>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
            <div className="flex flex-col">
              <span className="text-xs text-muted-foreground font-medium">Median</span>
              <span className="text-sm font-semibold tabular-nums">
                {formatNumber(data.median_final_equity)}
              </span>
            </div>
            <div className="flex flex-col">
              <span className="text-xs text-muted-foreground font-medium">P5 / P95</span>
              <span className="text-sm font-semibold tabular-nums">
                {formatNumber(data.p5_final_equity)} / {formatNumber(data.p95_final_equity)}
              </span>
            </div>
            <div className="flex flex-col">
              <span className="text-xs text-muted-foreground font-medium">Range</span>
              <span className="text-sm font-semibold tabular-nums">
                {formatNumber(data.worst_final_equity)} – {formatNumber(data.best_final_equity)}
              </span>
            </div>
          </div>
        </div>

        <div>
          <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-3">
            Drawdown (simulated)
          </h3>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
            <div className="flex flex-col">
              <span className="text-xs text-muted-foreground font-medium">Median max DD</span>
              <span className="text-sm font-semibold tabular-nums text-muted-foreground">
                {data.median_max_drawdown_pct.toFixed(2)}%
              </span>
            </div>
            <div className="flex flex-col">
              <span className="text-xs text-muted-foreground font-medium">P95 max DD</span>
              <span className="text-sm font-semibold tabular-nums text-muted-foreground">
                {data.p95_max_drawdown_pct.toFixed(2)}%
              </span>
            </div>
            <div className="flex flex-col">
              <span className="text-xs text-muted-foreground font-medium">Worst max DD</span>
              <span className="text-sm font-semibold tabular-nums text-destructive">
                {data.worst_max_drawdown_pct.toFixed(2)}%
              </span>
            </div>
          </div>
        </div>

        <div>
          <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-3">
            Scenario probabilities
          </h3>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
            <div className="flex flex-col">
              <span className="text-xs text-muted-foreground font-medium">Profit</span>
              <span className="text-sm font-semibold tabular-nums text-emerald-600 dark:text-emerald-400">
                {data.probability_profit_pct.toFixed(1)}%
              </span>
            </div>
            <div className="flex flex-col">
              <span className="text-xs text-muted-foreground font-medium">Loss</span>
              <span className="text-sm font-semibold tabular-nums text-destructive">
                {data.probability_loss_pct.toFixed(1)}%
              </span>
            </div>
            <div className="flex flex-col">
              <span className="text-xs text-muted-foreground font-medium">Max DD &gt; 10%</span>
              <span className="text-sm font-semibold tabular-nums text-muted-foreground">
                {data.probability_drawdown_gt_10_pct.toFixed(1)}%
              </span>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

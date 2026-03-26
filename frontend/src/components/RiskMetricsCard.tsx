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
import { backtestsApi, type RiskMetricsResponse } from "@/lib/api/endpoints";
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

function formatRatio(value: number): string {
  return value.toFixed(2);
}

type MetricItemProps = {
  label: string;
  value: string;
  hint?: string;
  colorize?: "pct" | "pnl" | "ratio" | "none";
  rawValue?: number;
};

function MetricItem({ label, value, hint, colorize = "none", rawValue }: MetricItemProps) {
  let colorClass = "";
  if (colorize !== "none" && rawValue !== undefined) {
    if (colorize === "pct" || colorize === "pnl") {
      colorClass = rawValue >= 0
        ? "text-emerald-600 dark:text-emerald-400"
        : "text-destructive";
    } else if (colorize === "ratio") {
      colorClass = rawValue > 0
        ? "text-emerald-600 dark:text-emerald-400"
        : rawValue < 0
          ? "text-destructive"
          : "";
    }
  }

  return (
    <div className="flex flex-col">
      <span className="text-xs text-muted-foreground font-medium">{label}</span>
      <span className={`text-sm font-semibold tabular-nums ${colorClass}`}>
        {value}
      </span>
      {hint && <span className="text-[10px] text-muted-foreground">{hint}</span>}
    </div>
  );
}

type RiskMetricsCardProps = {
  runId: string;
  runStatus: string;
};

export function RiskMetricsCard({ runId, runStatus }: RiskMetricsCardProps) {
  const [metrics, setMetrics] = useState<RiskMetricsResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const token = getToken();
  const shouldFetch = runStatus === "completed" && !!token;

  useEffect(() => {
    if (!shouldFetch) {
      return;
    }

    let cancelled = false;

    (async () => {
      setLoading(true);
      try {
        const data = await backtestsApi.getRiskMetrics(token!, runId);
        if (!cancelled) {
          setMetrics(data);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) {
          const message = err instanceof Error ? err.message : "Failed to load risk metrics";
          if (message.includes("400") || message.includes("not completed")) {
            setError(null);
            setMetrics(null);
          } else {
            setError(message);
          }
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

  if (loading) {
    return (
      <Card className="mt-6">
        <CardHeader className="pb-2">
          <Skeleton className="h-5 w-40" />
          <Skeleton className="h-4 w-64 mt-1" />
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
            {Array.from({ length: 12 }).map((_, i) => (
              <div key={i} className="flex flex-col gap-1">
                <Skeleton className="h-3 w-20" />
                <Skeleton className="h-5 w-16" />
              </div>
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
          <CardTitle className="text-base">Risk metrics</CardTitle>
          <CardDescription className="text-destructive">
            {error}
          </CardDescription>
        </CardHeader>
      </Card>
    );
  }

  if (!metrics) {
    return null;
  }

  return (
    <Card className="mt-6">
      <CardHeader className="pb-2">
        <CardTitle className="text-base">Risk metrics</CardTitle>
        <CardDescription>
          Advanced risk-adjusted performance metrics for this backtest
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Risk-Adjusted Returns */}
        <div>
          <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-3">
            Risk-Adjusted Returns
          </h3>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
            <MetricItem
              label="Sharpe ratio"
              value={formatRatio(metrics.sharpe_ratio)}
              hint="Return per unit risk"
              colorize="ratio"
              rawValue={metrics.sharpe_ratio}
            />
            <MetricItem
              label="Sortino ratio"
              value={formatRatio(metrics.sortino_ratio)}
              hint="Penalizes downside only"
              colorize="ratio"
              rawValue={metrics.sortino_ratio}
            />
            <MetricItem
              label="Calmar ratio"
              value={formatRatio(metrics.calmar_ratio)}
              hint="Ann. return / max DD"
              colorize="ratio"
              rawValue={metrics.calmar_ratio}
            />
          </div>
        </div>

        {/* Returns */}
        <div>
          <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-3">
            Returns
          </h3>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
            <MetricItem
              label="Total return"
              value={formatPct(metrics.total_return_pct)}
              colorize="pct"
              rawValue={metrics.total_return_pct}
            />
            <MetricItem
              label="Annualized return"
              value={formatPct(metrics.annualized_return_pct)}
              colorize="pct"
              rawValue={metrics.annualized_return_pct}
            />
            <MetricItem
              label="Initial equity"
              value={formatNumber(metrics.initial_equity)}
            />
            <MetricItem
              label="Final equity"
              value={formatNumber(metrics.final_equity)}
            />
          </div>
        </div>

        {/* Drawdowns */}
        <div>
          <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-3">
            Drawdowns
          </h3>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
            <MetricItem
              label="Max drawdown"
              value={`${metrics.max_drawdown_pct.toFixed(2)}%`}
              hint="Largest peak-to-trough"
            />
            <MetricItem
              label="Avg drawdown"
              value={`${metrics.avg_drawdown_pct.toFixed(2)}%`}
              hint="Mean drawdown level"
            />
          </div>
        </div>

        {/* Value at Risk */}
        <div>
          <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-3">
            Value at Risk
          </h3>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
            <MetricItem
              label="VaR 95%"
              value={formatPct(metrics.var_95)}
              hint="5th percentile return"
              colorize="pct"
              rawValue={metrics.var_95}
            />
            <MetricItem
              label="VaR 99%"
              value={formatPct(metrics.var_99)}
              hint="1st percentile return"
              colorize="pct"
              rawValue={metrics.var_99}
            />
            <MetricItem
              label="CVaR 95%"
              value={formatPct(metrics.cvar_95)}
              hint="Expected shortfall"
              colorize="pct"
              rawValue={metrics.cvar_95}
            />
            <MetricItem
              label="CVaR 99%"
              value={formatPct(metrics.cvar_99)}
              hint="Expected shortfall"
              colorize="pct"
              rawValue={metrics.cvar_99}
            />
          </div>
        </div>

        {/* Trade Statistics */}
        <div>
          <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-3">
            Trade Statistics
          </h3>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
            <MetricItem
              label="Total trades"
              value={String(metrics.num_trades)}
            />
            <MetricItem
              label="Win rate"
              value={`${metrics.win_rate.toFixed(1)}%`}
              colorize="ratio"
              rawValue={metrics.win_rate - 50}
            />
            <MetricItem
              label="Profit factor"
              value={formatRatio(metrics.profit_factor)}
              hint="Gross profit / loss"
              colorize="ratio"
              rawValue={metrics.profit_factor - 1}
            />
            <MetricItem
              label="Avg trade PnL"
              value={formatNumber(metrics.avg_trade_pnl)}
              colorize="pnl"
              rawValue={metrics.avg_trade_pnl}
            />
            <MetricItem
              label="Avg win"
              value={formatNumber(metrics.avg_win)}
              colorize="pnl"
              rawValue={metrics.avg_win}
            />
            <MetricItem
              label="Avg loss"
              value={formatNumber(metrics.avg_loss)}
              colorize="pnl"
              rawValue={metrics.avg_loss}
            />
            <MetricItem
              label="Largest win"
              value={formatNumber(metrics.largest_win)}
              colorize="pnl"
              rawValue={metrics.largest_win}
            />
            <MetricItem
              label="Largest loss"
              value={formatNumber(metrics.largest_loss)}
              colorize="pnl"
              rawValue={metrics.largest_loss}
            />
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

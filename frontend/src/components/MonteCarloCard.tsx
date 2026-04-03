"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import {
  backtestsApi,
  type MonteCarloHistogramBinOut,
  type MonteCarloResponse,
} from "@/lib/api/endpoints";
import { getToken } from "@/lib/auth";
import { cn } from "@/lib/utils";

function formatPct(value: number): string {
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
}

function formatNumber(value: number, decimals = 2): string {
  return value.toLocaleString(undefined, {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

const SIMULATION_COUNTS = [100, 250, 500, 1000, 2500, 5000, 10_000] as const;

const selectClassName = cn(
  "h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-xs",
  "focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px] outline-none"
);

type HistogramMetric = "return_pct" | "final_equity";

function binIndexForValue(bins: MonteCarloHistogramBinOut[], x: number): number | null {
  if (bins.length === 0) return null;
  for (let i = 0; i < bins.length; i++) {
    const b = bins[i];
    const last = i === bins.length - 1;
    if (last) {
      if (x >= b.bin_start && x <= b.bin_end) return i;
    } else if (x >= b.bin_start && x < b.bin_end) {
      return i;
    }
  }
  if (x < bins[0].bin_start) return 0;
  if (x > bins[bins.length - 1].bin_end) return bins.length - 1;
  return null;
}

type MonteCarloCardProps = {
  runId: string;
  runStatus: string;
  /** Count of sell trades with realized P&L (Monte Carlo needs at least 2). */
  closedTradeCount: number;
};

type FormState = {
  num_simulations: number;
  method: "bootstrap" | "shuffle";
  seed: string;
};

const defaultForm = (): FormState => ({
  num_simulations: 500,
  method: "bootstrap",
  seed: "",
});

export function MonteCarloCard({
  runId,
  runStatus,
  closedTradeCount,
}: MonteCarloCardProps) {
  const [data, setData] = useState<MonteCarloResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [form, setForm] = useState<FormState>(defaultForm);
  const [histogramMetric, setHistogramMetric] = useState<HistogramMetric>("return_pct");
  /** Bumps on mount (per run), run change, or explicit "Run simulation". */
  const [fetchKey, setFetchKey] = useState(1);
  const formRef = useRef(form);
  formRef.current = form;

  const token = getToken();
  const shouldFetch =
    runStatus === "completed" && !!token && closedTradeCount >= 2;

  useEffect(() => {
    setForm(defaultForm());
    setData(null);
    setError(null);
    setFormError(null);
    setFetchKey(1);
  }, [runId]);

  useEffect(() => {
    if (!shouldFetch) {
      return;
    }

    let cancelled = false;
    const f = formRef.current;

    (async () => {
      setLoading(true);
      setError(null);
      try {
        const body: {
          num_simulations: number;
          method: "bootstrap" | "shuffle";
          seed?: number | null;
        } = {
          num_simulations: f.num_simulations,
          method: f.method,
        };
        const trimmed = f.seed.trim();
        if (trimmed !== "") {
          body.seed = Number(trimmed);
        }

        const res = await backtestsApi.postMonteCarlo(token!, runId, body);
        if (!cancelled) {
          setData(res);
        }
      } catch (err) {
        if (!cancelled) {
          const message =
            err instanceof Error ? err.message : "Failed to load Monte Carlo analysis";
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
  }, [runId, shouldFetch, token, fetchKey]);

  const runAnalysis = useCallback(() => {
    const trimmed = formRef.current.seed.trim();
    if (trimmed !== "") {
      const n = Number(trimmed);
      if (!Number.isInteger(n)) {
        setFormError("Seed must be a whole number (or leave empty for random).");
        return;
      }
    }
    setFormError(null);
    setFetchKey((k) => k + 1);
  }, []);

  const histogramBins = useMemo(() => {
    if (!data) return [];
    return histogramMetric === "return_pct"
      ? data.histogram_return_pct
      : data.histogram_final_equity;
  }, [data, histogramMetric]);

  const histogramChartData = useMemo(() => {
    return histogramBins.map((b, i) => ({
      ix: i,
      count: b.count,
      lo: b.bin_start,
      hi: b.bin_end,
    }));
  }, [histogramBins]);

  const medianReferenceIx = useMemo(() => {
    if (!data || histogramBins.length === 0) return null;
    const median =
      histogramMetric === "return_pct"
        ? data.median_total_return_pct
        : data.median_final_equity;
    return binIndexForValue(histogramBins, median);
  }, [data, histogramBins, histogramMetric]);

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
            Resampled trade P&amp;L paths (Phase 14.3–14.4). Requires at least two closed trades
            with realized P&amp;L. This run has {closedTradeCount}.
          </CardDescription>
        </CardHeader>
      </Card>
    );
  }

  const showSkeleton = loading && !data;

  if (showSkeleton) {
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

  if (error && !data) {
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

  const ci = data.confidence_intervals;

  return (
    <Card className="mt-6">
      <CardHeader className="pb-2">
        <CardTitle className="text-base">Monte Carlo robustness</CardTitle>
        <CardDescription>
          Phase 14.4: configure simulations, inspect outcome histograms, and read central percentile
          intervals over the resampled distribution.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        <div className="flex flex-col gap-4 rounded-lg border border-border/60 bg-muted/20 p-4 sm:flex-row sm:flex-wrap sm:items-end">
          <div className="grid flex-1 gap-4 sm:grid-cols-3 min-w-0">
            <div className="space-y-2">
              <Label htmlFor="mc-sims">Simulations</Label>
              <select
                id="mc-sims"
                className={selectClassName}
                value={form.num_simulations}
                disabled={loading}
                onChange={(e) =>
                  setForm((f) => ({ ...f, num_simulations: Number(e.target.value) }))
                }
              >
                {SIMULATION_COUNTS.map((n) => (
                  <option key={n} value={n}>
                    {n.toLocaleString()}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="mc-method">Method</Label>
              <select
                id="mc-method"
                className={selectClassName}
                value={form.method}
                disabled={loading}
                onChange={(e) =>
                  setForm((f) => ({
                    ...f,
                    method: e.target.value as "bootstrap" | "shuffle",
                  }))
                }
              >
                <option value="bootstrap">Bootstrap (resample P&amp;L with replacement)</option>
                <option value="shuffle">Shuffle (random order, same multiset)</option>
              </select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="mc-seed">Seed (optional)</Label>
              <Input
                id="mc-seed"
                type="text"
                inputMode="numeric"
                placeholder="Random"
                value={form.seed}
                disabled={loading}
                onChange={(e) => setForm((f) => ({ ...f, seed: e.target.value }))}
              />
            </div>
          </div>
          <Button type="button" onClick={runAnalysis} disabled={loading} className="shrink-0">
            {loading ? "Running…" : "Run simulation"}
          </Button>
        </div>
        {formError && (
          <p className="text-sm text-destructive" role="alert">
            {formError}
          </p>
        )}
        {error && data && (
          <p className="text-sm text-destructive" role="alert">
            {error}
          </p>
        )}

        <div>
          <p className="text-xs text-muted-foreground mb-3">
            Last result: {data.num_simulations.toLocaleString()} runs · {data.method} ·{" "}
            {data.num_closed_trades} closed trades · seed {data.seed ?? "random"}
          </p>
          <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">
            Outcome histogram
          </h3>
          <div className="flex flex-wrap gap-2 mb-3">
            <Button
              type="button"
              variant={histogramMetric === "return_pct" ? "default" : "outline"}
              size="sm"
              className="h-8"
              onClick={() => setHistogramMetric("return_pct")}
            >
              Total return %
            </Button>
            <Button
              type="button"
              variant={histogramMetric === "final_equity" ? "default" : "outline"}
              size="sm"
              className="h-8"
              onClick={() => setHistogramMetric("final_equity")}
            >
              Final equity
            </Button>
          </div>
          <div
            className={cn(
              "h-[240px] w-full min-w-0 rounded-md border border-border/50 bg-background/50 p-2",
              loading && "opacity-60"
            )}
          >
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={histogramChartData} margin={{ top: 8, right: 8, left: 0, bottom: 4 }}>
                <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                <XAxis
                  dataKey="ix"
                  tick={false}
                  tickLine={false}
                  axisLine={{ className: "stroke-border" }}
                  label={{
                    value:
                      histogramMetric === "return_pct"
                        ? "Return % (bins left → right)"
                        : "Equity bins (low → high)",
                    position: "insideBottom",
                    offset: -2,
                    className: "fill-muted-foreground text-[10px]",
                  }}
                />
                <YAxis
                  allowDecimals={false}
                  width={40}
                  className="text-xs fill-muted-foreground"
                  axisLine={{ className: "stroke-border" }}
                />
                <Tooltip
                  content={({ active, payload }) => {
                    if (!active || !payload?.length) return null;
                    const row = payload[0].payload as {
                      ix: number;
                      count: number;
                      lo: number;
                      hi: number;
                    };
                    const range =
                      histogramMetric === "return_pct"
                        ? `${formatPct(row.lo)} to ${formatPct(row.hi)}`
                        : `${formatNumber(row.lo)} to ${formatNumber(row.hi)}`;
                    return (
                      <div className="rounded-md border bg-popover px-3 py-2 text-xs shadow-md">
                        <p className="font-medium text-popover-foreground">{range}</p>
                        <p className="text-muted-foreground tabular-nums">
                          Count: {row.count.toLocaleString()}
                        </p>
                      </div>
                    );
                  }}
                />
                <Bar
                  dataKey="count"
                  fill="var(--primary)"
                  radius={[3, 3, 0, 0]}
                  maxBarSize={48}
                />
                {medianReferenceIx != null && (
                  <ReferenceLine
                    x={medianReferenceIx}
                    stroke="var(--chart-2)"
                    strokeDasharray="4 4"
                    label={{
                      value: "Median",
                      position: "top",
                      className: "fill-muted-foreground text-[10px]",
                    }}
                  />
                )}
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div>
          <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-1">
            Central percentile intervals
          </h3>
          <p className="text-xs text-muted-foreground mb-3">
            Intervals are taken from the simulated outcome distribution (P5–P95 ≈ 90% central mass;
            P2.5–P97.5 ≈ 95%). They describe resampling uncertainty, not a classical parametric
            confidence interval.
          </p>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="rounded-md border border-border/60 p-3 space-y-2">
              <p className="text-xs font-semibold text-foreground">Total return %</p>
              <p className="text-sm tabular-nums">
                <span className="text-muted-foreground">90% central: </span>
                {formatPct(ci.return_pct_ci_90_low)} — {formatPct(ci.return_pct_ci_90_high)}
              </p>
              <p className="text-sm tabular-nums">
                <span className="text-muted-foreground">95% central: </span>
                {formatPct(ci.return_pct_ci_95_low)} — {formatPct(ci.return_pct_ci_95_high)}
              </p>
            </div>
            <div className="rounded-md border border-border/60 p-3 space-y-2">
              <p className="text-xs font-semibold text-foreground">Final equity</p>
              <p className="text-sm tabular-nums">
                <span className="text-muted-foreground">90% central: </span>
                {formatNumber(ci.final_equity_ci_90_low)} —{" "}
                {formatNumber(ci.final_equity_ci_90_high)}
              </p>
              <p className="text-sm tabular-nums">
                <span className="text-muted-foreground">95% central: </span>
                {formatNumber(ci.final_equity_ci_95_low)} —{" "}
                {formatNumber(ci.final_equity_ci_95_high)}
              </p>
            </div>
          </div>
        </div>

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

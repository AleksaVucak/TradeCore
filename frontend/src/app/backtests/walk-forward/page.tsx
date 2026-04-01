"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
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
import {
  backtestsApi,
  marketDataApi,
  strategiesApi,
  symbolsApi,
  type CoverageRangeResponse,
  type StrategyDetail,
  type StrategyListItem,
  type Symbol,
  type WalkForwardValidationResponse,
} from "@/lib/api/endpoints";
import { getToken } from "@/lib/auth";

const TIMEFRAMES = ["1h", "4h", "1d"] as const;

function toDateTimeLocalValue(date: Date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  const hours = String(date.getHours()).padStart(2, "0");
  const minutes = String(date.getMinutes()).padStart(2, "0");
  return `${year}-${month}-${day}T${hours}:${minutes}`;
}

function toUTCISOString(value: string) {
  return new Date(value).toISOString().replace(/\.\d{3}Z$/, "Z");
}

function formatDateTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

function formatPct(value: number | null | undefined) {
  if (value == null) return "—";
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
}

function formatNumber(value: number, decimals = 2) {
  return value.toLocaleString(undefined, {
    minimumFractionDigits: 0,
    maximumFractionDigits: decimals,
  });
}

function getDefaultWindowBars(timeframe: (typeof TIMEFRAMES)[number]) {
  if (timeframe === "4h") return 42;
  if (timeframe === "1d") return 30;
  return 24;
}

function getDefaultStepBars(timeframe: (typeof TIMEFRAMES)[number]) {
  if (timeframe === "4h") return 21;
  if (timeframe === "1d") return 15;
  return 12;
}

export default function WalkForwardPage() {
  const [token, setToken] = useState<string | null>(null);
  const [initialStrategyIdFromQuery, setInitialStrategyIdFromQuery] = useState("");

  const [strategies, setStrategies] = useState<StrategyListItem[]>([]);
  const [symbols, setSymbols] = useState<Symbol[]>([]);
  const [selectedStrategyId, setSelectedStrategyId] = useState("");
  const [selectedVersionId, setSelectedVersionId] = useState("");
  const [selectedSymbolId, setSelectedSymbolId] = useState("");
  const [timeframe, setTimeframe] = useState<(typeof TIMEFRAMES)[number]>("1h");
  const [startTime, setStartTime] = useState(() => {
    const start = new Date();
    start.setMonth(start.getMonth() - 3);
    return toDateTimeLocalValue(start);
  });
  const [endTime, setEndTime] = useState(() => toDateTimeLocalValue(new Date()));
  const [initialEquity, setInitialEquity] = useState("10000");
  const [windowBars, setWindowBars] = useState("24");
  const [stepBars, setStepBars] = useState("12");

  const [selectedStrategy, setSelectedStrategy] = useState<StrategyDetail | null>(null);
  const [coverage, setCoverage] = useState<CoverageRangeResponse[]>([]);
  const [result, setResult] = useState<WalkForwardValidationResponse | null>(null);
  const [coverageLoading, setCoverageLoading] = useState(false);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const activeVersion = useMemo(
    () =>
      selectedStrategy?.versions.find((version) => version.is_active) ??
      selectedStrategy?.versions[0] ??
      null,
    [selectedStrategy]
  );

  const chartData = useMemo(
    () =>
      result?.windows.map((window) => ({
        name: `W${window.window_index + 1}`,
        total_return_pct: window.total_return_pct,
        max_drawdown_pct: window.max_drawdown_pct,
        num_trades: window.num_trades,
      })) ?? [],
    [result]
  );

  useEffect(() => {
    if (typeof window === "undefined") return;
    const params = new URLSearchParams(window.location.search);
    setInitialStrategyIdFromQuery(params.get("strategyId") ?? "");
  }, []);

  useEffect(() => {
    const currentToken = getToken();
    setToken(currentToken);
    if (!currentToken) {
      queueMicrotask(() => {
        setError("Please log in to run walk-forward validation.");
        setLoading(false);
      });
      return;
    }

    let cancelled = false;
    (async () => {
      try {
        const [strategyList, symbolList] = await Promise.all([
          strategiesApi.list(currentToken),
          symbolsApi.list(),
        ]);
        if (cancelled) return;
        setStrategies(strategyList);
        setSymbols(symbolList);
        const initialStrategyId =
          initialStrategyIdFromQuery &&
          strategyList.some((strategy) => String(strategy.id) === initialStrategyIdFromQuery)
            ? initialStrategyIdFromQuery
            : strategyList[0]
              ? String(strategyList[0].id)
              : "";
        if (strategyList.length > 0) {
          setSelectedStrategyId(initialStrategyId);
        }
        if (symbolList.length > 0) {
          setSelectedSymbolId(String(symbolList[0].id));
        }
        setError(null);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load form options.");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [initialStrategyIdFromQuery]);

  useEffect(() => {
    setWindowBars(String(getDefaultWindowBars(timeframe)));
    setStepBars(String(getDefaultStepBars(timeframe)));
  }, [timeframe]);

  useEffect(() => {
    if (!token || !selectedStrategyId) return;
    let cancelled = false;
    (async () => {
      try {
        const detail = await strategiesApi.get(token, Number(selectedStrategyId));
        if (cancelled) return;
        setSelectedStrategy(detail);
        const defaultVersion =
          detail.versions.find((version) => version.is_active) ?? detail.versions[0] ?? null;
        setSelectedVersionId(defaultVersion ? String(defaultVersion.id) : "");
      } catch (err) {
        if (!cancelled) {
          setSelectedStrategy(null);
          setSelectedVersionId("");
          setError(err instanceof Error ? err.message : "Failed to load strategy versions.");
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [token, selectedStrategyId]);

  useEffect(() => {
    if (!token || !selectedSymbolId) return;
    let cancelled = false;
    (async () => {
      setCoverageLoading(true);
      try {
        const data = await marketDataApi.coverage(token, {
          symbol_id: Number(selectedSymbolId),
          timeframe,
        });
        if (cancelled) return;
        setCoverage(data);
      } catch (err) {
        if (!cancelled) {
          setCoverage([]);
          setError(err instanceof Error ? err.message : "Failed to load market-data coverage.");
        }
      } finally {
        if (!cancelled) setCoverageLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [token, selectedSymbolId, timeframe]);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token) {
      setError("Please log in to run walk-forward validation.");
      return;
    }
    if (!selectedVersionId || !selectedSymbolId) {
      setError("Please choose a strategy version and symbol.");
      return;
    }

    const startIso = toUTCISOString(startTime);
    const endIso = toUTCISOString(endTime);
    if (new Date(startIso) >= new Date(endIso)) {
      setError("End date must be after start date.");
      return;
    }

    const equityValue = Number(initialEquity);
    const windowValue = Number(windowBars);
    const stepValue = Number(stepBars);
    if (!Number.isFinite(equityValue) || equityValue <= 0) {
      setError("Initial equity must be greater than 0.");
      return;
    }
    if (!Number.isInteger(windowValue) || windowValue < 2) {
      setError("Window bars must be a whole number of at least 2.");
      return;
    }
    if (!Number.isInteger(stepValue) || stepValue < 1) {
      setError("Step bars must be a whole number of at least 1.");
      return;
    }

    setSubmitting(true);
    setError(null);
    setResult(null);

    try {
      const response = await backtestsApi.runWalkForward(token, {
        strategy_version_id: Number(selectedVersionId),
        symbol_id: Number(selectedSymbolId),
        timeframe,
        start_time: startIso,
        end_time: endIso,
        initial_equity: equityValue,
        window_bars: windowValue,
        step_bars: stepValue,
      });
      setResult(response);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to run walk-forward validation.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen bg-background">
      <header className="border-b border-border px-6 py-4">
        <Link href="/backtests" className="text-muted-foreground hover:text-foreground text-sm">
          ← Back to run history
        </Link>
        <h1 className="mt-2 text-xl font-semibold tracking-tight">Walk-forward validation</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Test the same strategy across many rolling windows to see whether performance stays
          stable over time.
        </p>
      </header>

      <main className="container mx-auto max-w-6xl px-6 py-8 space-y-6">
        {error && (
          <Card className="border-destructive/50">
            <CardHeader className="pb-2">
              <CardTitle className="text-base text-destructive">Something went wrong</CardTitle>
              <CardDescription>{error}</CardDescription>
            </CardHeader>
          </Card>
        )}

        <Card>
          <CardHeader>
            <CardTitle>Run validation</CardTitle>
            <CardDescription>
              Pick a strategy, market, and rolling-window settings. The backend will evaluate the
              same strategy configuration across many consecutive windows and return a consistency
              summary.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {loading ? (
              <p className="text-sm text-muted-foreground">Loading form…</p>
            ) : (
              <form className="space-y-5" onSubmit={handleSubmit}>
                <div className="grid gap-5 md:grid-cols-2">
                  <div className="space-y-2">
                    <Label htmlFor="strategy">Strategy</Label>
                    <select
                      id="strategy"
                      className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-xs outline-none focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px] disabled:cursor-not-allowed disabled:opacity-50"
                      value={selectedStrategyId}
                      onChange={(event) => setSelectedStrategyId(event.target.value)}
                      disabled={strategies.length === 0}
                    >
                      {strategies.length === 0 ? (
                        <option value="">No strategies available</option>
                      ) : (
                        strategies.map((strategy) => (
                          <option key={strategy.id} value={strategy.id}>
                            {strategy.name}
                          </option>
                        ))
                      )}
                    </select>
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="version">Strategy version</Label>
                    <select
                      id="version"
                      className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-xs outline-none focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px] disabled:cursor-not-allowed disabled:opacity-50"
                      value={selectedVersionId}
                      onChange={(event) => setSelectedVersionId(event.target.value)}
                      disabled={!selectedStrategy || selectedStrategy.versions.length === 0}
                    >
                      {!selectedStrategy || selectedStrategy.versions.length === 0 ? (
                        <option value="">No versions available</option>
                      ) : (
                        [...selectedStrategy.versions]
                          .sort((a, b) => b.version_number - a.version_number)
                          .map((version) => (
                            <option key={version.id} value={version.id}>
                              v{version.version_number}
                              {version.is_active ? " (active)" : ""}
                            </option>
                          ))
                      )}
                    </select>
                    {activeVersion && (
                      <p className="text-xs text-muted-foreground">
                        Active version: v{activeVersion.version_number}
                      </p>
                    )}
                  </div>
                </div>

                <div className="grid gap-5 md:grid-cols-2">
                  <div className="space-y-2">
                    <Label htmlFor="symbol">Symbol</Label>
                    <select
                      id="symbol"
                      className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-xs outline-none focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px] disabled:cursor-not-allowed disabled:opacity-50"
                      value={selectedSymbolId}
                      onChange={(event) => setSelectedSymbolId(event.target.value)}
                      disabled={symbols.length === 0}
                    >
                      {symbols.length === 0 ? (
                        <option value="">No symbols available</option>
                      ) : (
                        symbols.map((symbol) => (
                          <option key={symbol.id} value={symbol.id}>
                            {symbol.symbol}
                          </option>
                        ))
                      )}
                    </select>
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="timeframe">Timeframe</Label>
                    <select
                      id="timeframe"
                      className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-xs outline-none focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px]"
                      value={timeframe}
                      onChange={(event) =>
                        setTimeframe(event.target.value as (typeof TIMEFRAMES)[number])
                      }
                    >
                      {TIMEFRAMES.map((option) => (
                        <option key={option} value={option}>
                          {option}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>

                <div className="grid gap-5 md:grid-cols-2">
                  <div className="space-y-2">
                    <Label htmlFor="start-time">Start date</Label>
                    <Input
                      id="start-time"
                      type="datetime-local"
                      value={startTime}
                      onChange={(event) => setStartTime(event.target.value)}
                    />
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="end-time">End date</Label>
                    <Input
                      id="end-time"
                      type="datetime-local"
                      value={endTime}
                      onChange={(event) => setEndTime(event.target.value)}
                    />
                  </div>
                </div>

                <div className="grid gap-5 md:grid-cols-3">
                  <div className="space-y-2">
                    <Label htmlFor="initial-equity">Initial equity</Label>
                    <Input
                      id="initial-equity"
                      type="number"
                      min="0.01"
                      step="0.01"
                      value={initialEquity}
                      onChange={(event) => setInitialEquity(event.target.value)}
                    />
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="window-bars">Window bars</Label>
                    <Input
                      id="window-bars"
                      type="number"
                      min="2"
                      step="1"
                      value={windowBars}
                      onChange={(event) => setWindowBars(event.target.value)}
                    />
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="step-bars">Step bars</Label>
                    <Input
                      id="step-bars"
                      type="number"
                      min="1"
                      step="1"
                      value={stepBars}
                      onChange={(event) => setStepBars(event.target.value)}
                    />
                  </div>
                </div>

                <div className="rounded-lg border bg-muted/30 p-4 text-sm text-muted-foreground">
                  `window bars` controls how much data goes into each evaluation window. `step bars`
                  controls how far forward the next window moves. Smaller steps create more
                  overlapping windows, which gives you a more detailed stability view.
                </div>

                <div className="flex flex-wrap gap-3">
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => {
                      const end = new Date();
                      const start = new Date(end);
                      start.setMonth(start.getMonth() - 3);
                      setTimeframe("1h");
                      setStartTime(toDateTimeLocalValue(start));
                      setEndTime(toDateTimeLocalValue(end));
                      setInitialEquity("10000");
                      setWindowBars("24");
                      setStepBars("12");
                      setResult(null);
                    }}
                  >
                    Reset defaults
                  </Button>
                  <Button
                    type="submit"
                    disabled={submitting || !selectedVersionId || !selectedSymbolId}
                  >
                    {submitting ? "Running…" : "Run validation"}
                  </Button>
                </div>
              </form>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Market data coverage</CardTitle>
            <CardDescription>
              Check that the selected symbol and timeframe already have stored candles for the date
              range you want to validate.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {coverageLoading ? (
              <p className="text-sm text-muted-foreground">Loading coverage…</p>
            ) : coverage.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                No stored coverage found for this symbol/timeframe. You may need to fetch market
                data first.
              </p>
            ) : (
              <div className="space-y-3">
                {coverage.map((row) => (
                  <div key={`${row.symbol_id}-${row.timeframe}`} className="rounded-lg border p-4">
                    <p className="text-sm font-medium">
                      {symbols.find((symbol) => symbol.id === row.symbol_id)?.symbol ??
                        row.symbol_id}{" "}
                      · {row.timeframe}
                    </p>
                    <p className="mt-2 text-sm text-muted-foreground">
                      Start: {formatDateTime(row.start_date)}
                    </p>
                    <p className="text-sm text-muted-foreground">
                      End: {formatDateTime(row.end_date)}
                    </p>
                    <p className="text-sm text-muted-foreground">
                      Candles: {formatNumber(row.candle_count, 0)}
                    </p>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {result && (
          <>
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium text-muted-foreground">
                    Total windows
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-2xl font-semibold">{result.summary.total_windows}</p>
                </CardContent>
              </Card>
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium text-muted-foreground">
                    Profitable windows
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-2xl font-semibold">
                    {result.summary.profitable_windows}
                    <span className="ml-2 text-sm text-muted-foreground">
                      ({result.summary.profitable_window_pct.toFixed(1)}%)
                    </span>
                  </p>
                </CardContent>
              </Card>
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium text-muted-foreground">
                    Avg return
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <p
                    className={`text-2xl font-semibold ${
                      result.summary.avg_total_return_pct >= 0
                        ? "text-emerald-600 dark:text-emerald-400"
                        : "text-destructive"
                    }`}
                  >
                    {formatPct(result.summary.avg_total_return_pct)}
                  </p>
                </CardContent>
              </Card>
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium text-muted-foreground">
                    Avg drawdown
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-2xl font-semibold text-muted-foreground">
                    {result.summary.avg_max_drawdown_pct.toFixed(2)}%
                  </p>
                </CardContent>
              </Card>
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium text-muted-foreground">
                    Best window
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-2xl font-semibold text-emerald-600 dark:text-emerald-400">
                    {formatPct(result.summary.best_total_return_pct)}
                  </p>
                </CardContent>
              </Card>
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium text-muted-foreground">
                    Worst window
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-2xl font-semibold text-destructive">
                    {formatPct(result.summary.worst_total_return_pct)}
                  </p>
                </CardContent>
              </Card>
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium text-muted-foreground">
                    Avg Sharpe
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-2xl font-semibold">
                    {result.summary.avg_sharpe_ratio.toFixed(2)}
                  </p>
                </CardContent>
              </Card>
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium text-muted-foreground">
                    Window / step
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-2xl font-semibold">
                    {result.summary.window_bars} / {result.summary.step_bars}
                  </p>
                </CardContent>
              </Card>
            </div>

            <Card>
              <CardHeader>
                <CardTitle>Window performance</CardTitle>
                <CardDescription>
                  Returns by rolling window. A smoother, consistently positive shape usually means
                  the strategy is more stable across time.
                </CardDescription>
              </CardHeader>
              <CardContent>
                {chartData.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No window data to chart.</p>
                ) : (
                  <div className="h-[320px] w-full">
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={chartData} margin={{ top: 10, right: 16, left: 8, bottom: 4 }}>
                        <CartesianGrid
                          strokeDasharray="3 3"
                          stroke="hsl(var(--border))"
                          opacity={0.4}
                        />
                        <XAxis
                          dataKey="name"
                          tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 11 }}
                          axisLine={{ stroke: "hsl(var(--border))" }}
                          tickLine={{ stroke: "hsl(var(--border))" }}
                        />
                        <YAxis
                          tickFormatter={(value) => `${value.toFixed(1)}%`}
                          tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 11 }}
                          axisLine={{ stroke: "hsl(var(--border))" }}
                          tickLine={{ stroke: "hsl(var(--border))" }}
                        />
                        <Tooltip
                          contentStyle={{
                            backgroundColor: "hsl(var(--card))",
                            border: "1px solid hsl(var(--border))",
                            borderRadius: "var(--radius)",
                            fontSize: 12,
                          }}
                          formatter={(value, name) => {
                            if (typeof value !== "number") return ["—", String(name)];
                            if (name === "num_trades") return [value, "Trades"];
                            if (name === "max_drawdown_pct") return [`${value.toFixed(2)}%`, "Drawdown"];
                            return [`${value.toFixed(2)}%`, "Return"];
                          }}
                        />
                        <Line
                          type="monotone"
                          dataKey="total_return_pct"
                          stroke="#22c55e"
                          strokeWidth={2.5}
                          dot={false}
                          activeDot={{ r: 4, fill: "#22c55e" }}
                        />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Per-window results</CardTitle>
                <CardDescription>
                  Compare each rolling window directly to spot strong periods, weak periods, and
                  stretches with no trades.
                </CardDescription>
              </CardHeader>
              <CardContent className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border">
                      <th className="py-3 px-2 text-left font-medium">Window</th>
                      <th className="py-3 px-2 text-left font-medium hidden md:table-cell">
                        Date range
                      </th>
                      <th className="py-3 px-2 text-right font-medium">Trades</th>
                      <th className="py-3 px-2 text-right font-medium">Return</th>
                      <th className="py-3 px-2 text-right font-medium hidden sm:table-cell">
                        Drawdown
                      </th>
                      <th className="py-3 px-2 text-right font-medium hidden lg:table-cell">
                        Sharpe
                      </th>
                      <th className="py-3 px-2 text-right font-medium hidden lg:table-cell">
                        Final equity
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.windows.map((window) => (
                      <tr key={window.window_index} className="border-b border-border/80 hover:bg-muted/50">
                        <td className="py-3 px-2 font-medium">W{window.window_index + 1}</td>
                        <td className="py-3 px-2 text-muted-foreground hidden md:table-cell whitespace-nowrap">
                          {formatDateTime(window.start_time)} to {formatDateTime(window.end_time)}
                        </td>
                        <td className="py-3 px-2 text-right tabular-nums">{window.num_trades}</td>
                        <td className="py-3 px-2 text-right tabular-nums">
                          <span
                            className={
                              window.total_return_pct >= 0
                                ? "text-emerald-600 dark:text-emerald-400"
                                : "text-destructive"
                            }
                          >
                            {formatPct(window.total_return_pct)}
                          </span>
                        </td>
                        <td className="py-3 px-2 text-right tabular-nums text-muted-foreground hidden sm:table-cell">
                          {window.max_drawdown_pct.toFixed(2)}%
                        </td>
                        <td className="py-3 px-2 text-right tabular-nums hidden lg:table-cell">
                          {window.sharpe_ratio.toFixed(2)}
                        </td>
                        <td className="py-3 px-2 text-right tabular-nums hidden lg:table-cell">
                          {formatNumber(window.final_equity)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </CardContent>
            </Card>
          </>
        )}

        {strategies.length === 0 && (
          <Card>
            <CardHeader>
              <CardTitle>No strategies yet</CardTitle>
              <CardDescription>
                Create a strategy before running walk-forward validation.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Link
                href="/strategies/new"
                className="text-sm font-medium text-primary underline-offset-4 hover:underline"
              >
                Create a strategy
              </Link>
            </CardContent>
          </Card>
        )}
      </main>
    </div>
  );
}

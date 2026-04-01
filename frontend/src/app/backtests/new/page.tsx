"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
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
} from "@/lib/api/endpoints";
import { getToken } from "@/lib/auth";

const TIMEFRAMES = ["1h", "4h"] as const;

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

function formatNumber(value: number) {
  return new Intl.NumberFormat().format(value);
}

export default function NewBacktestPage() {
  const router = useRouter();
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

  const [selectedStrategy, setSelectedStrategy] = useState<StrategyDetail | null>(null);
  const [coverage, setCoverage] = useState<CoverageRangeResponse[]>([]);
  const [coverageLoading, setCoverageLoading] = useState(false);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const activeVersion = useMemo(
    () => selectedStrategy?.versions.find((version) => version.is_active) ?? selectedStrategy?.versions[0] ?? null,
    [selectedStrategy]
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
        setError("Please log in to create a backtest.");
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
    if (!token || !selectedStrategyId) return;
    let cancelled = false;
    (async () => {
      try {
        const detail = await strategiesApi.get(token, Number(selectedStrategyId));
        if (cancelled) return;
        setSelectedStrategy(detail);
        const defaultVersion = detail.versions.find((version) => version.is_active) ?? detail.versions[0] ?? null;
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
      setError("Please log in to create a backtest.");
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
    if (!Number.isFinite(equityValue) || equityValue <= 0) {
      setError("Initial equity must be greater than 0.");
      return;
    }

    setSubmitting(true);
    setError(null);

    try {
      const run = await backtestsApi.create(token, {
        strategy_version_id: Number(selectedVersionId),
        symbol_id: Number(selectedSymbolId),
        timeframe,
        start_time: startIso,
        end_time: endIso,
        initial_equity: equityValue,
      });
      router.push(`/runs/${run.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create backtest.");
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
        <h1 className="mt-2 text-xl font-semibold tracking-tight">New backtest</h1>
      </header>

      <main className="container mx-auto max-w-5xl px-6 py-8 space-y-6">
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
            <CardTitle>Create a backtest</CardTitle>
            <CardDescription>
              Choose a strategy version, symbol, timeframe, and date range. This submits to the existing
              backtest API and starts the run immediately.
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
                              v{version.version_number}{version.is_active ? " (active)" : ""}
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
                      onChange={(event) => setTimeframe(event.target.value as (typeof TIMEFRAMES)[number])}
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

                <div className="max-w-xs space-y-2">
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

                <div className="flex flex-wrap gap-3">
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => {
                      const end = new Date();
                      const start = new Date(end);
                      start.setMonth(start.getMonth() - 3);
                      setStartTime(toDateTimeLocalValue(start));
                      setEndTime(toDateTimeLocalValue(end));
                      setInitialEquity("10000");
                    }}
                  >
                    Reset defaults
                  </Button>
                  <Button type="submit" disabled={submitting || !selectedVersionId || !selectedSymbolId}>
                    {submitting ? "Starting…" : "Run backtest"}
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
              Use the selected symbol and timeframe to check whether your chosen range is already loaded.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {coverageLoading ? (
              <p className="text-sm text-muted-foreground">Loading coverage…</p>
            ) : coverage.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                No stored coverage found for this symbol/timeframe. You may need to fetch market data first.
              </p>
            ) : (
              <div className="space-y-3">
                {coverage.map((row) => (
                  <div key={`${row.symbol_id}-${row.timeframe}`} className="rounded-lg border p-4">
                    <p className="text-sm font-medium">
                      {symbols.find((symbol) => symbol.id === row.symbol_id)?.symbol ?? row.symbol_id} · {row.timeframe}
                    </p>
                    <p className="mt-2 text-sm text-muted-foreground">
                      Start: {formatDateTime(row.start_date)}
                    </p>
                    <p className="text-sm text-muted-foreground">
                      End: {formatDateTime(row.end_date)}
                    </p>
                    <p className="text-sm text-muted-foreground">
                      Candles: {formatNumber(row.candle_count)}
                    </p>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {strategies.length === 0 && (
          <Card>
            <CardHeader>
              <CardTitle>No strategies yet</CardTitle>
              <CardDescription>
                Create a strategy before launching a backtest.
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

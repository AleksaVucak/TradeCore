"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
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
import { Progress } from "@/components/ui/progress";
import {
  marketDataApi,
  regimesApi,
  symbolsApi,
  type CoverageRangeResponse,
  type FetchJobStatusResponse,
  type ModelInfoOut,
  type Symbol,
} from "@/lib/api/endpoints";
import { SentimentPanel } from "@/components/SentimentPanel";
import { getToken } from "@/lib/auth";

const TIMEFRAMES = ["1h", "4h"] as const;
const WS_BASE =
  process.env.NEXT_PUBLIC_WS_URL ??
  (typeof window !== "undefined"
    ? `${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.hostname}:8000`
    : "ws://localhost:8000");

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

function formatDateTime(value: string | null | undefined) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

function formatDateOnly(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString();
}

function formatNumber(value: number) {
  return new Intl.NumberFormat().format(value);
}

function getMarketDataWebSocketUrl(jobId: string, token: string) {
  const url = new URL(`${WS_BASE}/ws/market-data/${jobId}`);
  url.searchParams.set("token", token);
  return url.toString();
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

export default function MarketDataPage() {
  const [token, setToken] = useState<string | null>(null);
  const [symbols, setSymbols] = useState<Symbol[]>([]);
  const [symbolsLoading, setSymbolsLoading] = useState(true);
  const [selectedSymbolId, setSelectedSymbolId] = useState<string>("");
  const [timeframe, setTimeframe] = useState<(typeof TIMEFRAMES)[number]>("1h");

  useEffect(() => {
    queueMicrotask(() => setToken(getToken()));
  }, []);
  const [startDate, setStartDate] = useState(() => {
    const start = new Date();
    start.setDate(start.getDate() - 30);
    return toDateTimeLocalValue(start);
  });
  const [endDate, setEndDate] = useState(() => toDateTimeLocalValue(new Date()));

  const [coverage, setCoverage] = useState<CoverageRangeResponse[]>([]);
  const [coverageLoading, setCoverageLoading] = useState(false);
  const [jobs, setJobs] = useState<FetchJobStatusResponse[]>([]);
  const [jobsLoading, setJobsLoading] = useState(true);
  const [activeJob, setActiveJob] = useState<FetchJobStatusResponse | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const [models, setModels] = useState<ModelInfoOut[]>([]);
  const [modelsLoading, setModelsLoading] = useState(false);
  const [trainSubmitting, setTrainSubmitting] = useState(false);
  const [trainTune, setTrainTune] = useState(false);
  const [trainTaskId, setTrainTaskId] = useState<string | null>(null);
  const [trainState, setTrainState] = useState<string | null>(null);
  const [trainProgressPct, setTrainProgressPct] = useState<number | null>(null);
  const [trainPhase, setTrainPhase] = useState<string | null>(null);
  const [trainResult, setTrainResult] = useState<{ accuracy: number | null; model_id: number | null; error: string | null } | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const selectedSymbol = useMemo(
    () => symbols.find((symbol) => String(symbol.id) === selectedSymbolId) ?? null,
    [selectedSymbolId, symbols]
  );

  async function loadRecentJobs(token: string) {
    const data = await marketDataApi.listFetchJobs(token, { limit: 8 });
    setJobs(data);
    setActiveJob((current) => {
      if (current) {
        return data.find((job) => job.job_id === current.job_id) ?? current;
      }
      return data.find((job) => job.status === "pending" || job.status === "running") ?? null;
    });
  }

  async function loadCoverage(token: string, symbolId: number, selectedTimeframe: string) {
    setCoverageLoading(true);
    try {
      const data = await marketDataApi.coverage(token, {
        symbol_id: symbolId,
        timeframe: selectedTimeframe,
      });
      setCoverage(data);
    } catch (err) {
      setCoverage([]);
      throw err;
    } finally {
      setCoverageLoading(false);
    }
  }

  async function loadModels(token: string, symbolId: number, tf: string) {
    setModelsLoading(true);
    try {
      const data = await regimesApi.listModels(token, { symbol_id: symbolId, timeframe: tf });
      setModels(data.models);
    } catch {
      setModels([]);
    } finally {
      setModelsLoading(false);
    }
  }

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  const startPolling = useCallback(
    (taskId: string) => {
      stopPolling();
      setTrainTaskId(taskId);
      setTrainState("PENDING");
      setTrainProgressPct(0);
      setTrainPhase("Queued");
      setTrainResult(null);

      pollRef.current = setInterval(async () => {
        const token = getToken();
        if (!token) return;
        try {
          const s = await regimesApi.getTrainStatus(token, taskId);
          setTrainState(s.state);
          if (s.progress_pct != null) setTrainProgressPct(s.progress_pct);
          if (s.phase != null) setTrainPhase(s.phase);

          if (s.state === "SUCCESS" && !s.error) {
            stopPolling();
            setTrainProgressPct(100);
            setTrainPhase("Complete");
            setTrainResult({ accuracy: s.accuracy, model_id: s.model_id, error: null });
            setTrainTaskId(null);
            if (selectedSymbolId) {
              await loadModels(token, Number(selectedSymbolId), timeframe);
            }
          } else if (s.state === "FAILURE" || s.error) {
            stopPolling();
            setTrainProgressPct(null);
            setTrainPhase(null);
            setTrainResult({ accuracy: null, model_id: null, error: s.error || "Training failed" });
            setTrainTaskId(null);
          }
        } catch {
          // transient error, keep polling
        }
      }, 3000);
    },
    [stopPolling, selectedSymbolId, timeframe],
  );

  useEffect(() => {
    return () => stopPolling();
  }, [stopPolling]);

  useEffect(() => {
    let cancelled = false;

    (async () => {
      const token = getToken();
      if (!token) {
        queueMicrotask(() => {
          if (!cancelled) {
            setError("Please log in to manage market data.");
            setSymbolsLoading(false);
            setJobsLoading(false);
          }
        });
        return;
      }

      try {
        const [symbolData, jobData] = await Promise.all([
          symbolsApi.list(),
          marketDataApi.listFetchJobs(token, { limit: 8 }),
        ]);

        if (cancelled) return;

        setSymbols(symbolData);
        setJobs(jobData);
        if (symbolData.length > 0) {
          setSelectedSymbolId((current) => current || String(symbolData[0].id));
        }
        setError(null);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load market data page.");
        }
      } finally {
        if (!cancelled) {
          setSymbolsLoading(false);
          setJobsLoading(false);
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    const token = getToken();
    if (!token || !selectedSymbolId) return;

    (async () => {
      try {
        await Promise.all([
          loadCoverage(token, Number(selectedSymbolId), timeframe),
          loadModels(token, Number(selectedSymbolId), timeframe),
        ]);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load coverage.");
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [selectedSymbolId, timeframe]);

  useEffect(() => {
    if (!activeJob || (activeJob.status !== "pending" && activeJob.status !== "running")) {
      return;
    }

    const token = getToken();
    if (!token) return;
    const jobId = activeJob.job_id;

    let cancelled = false;
    let closedIntentionally = false;
    const websocket = new WebSocket(getMarketDataWebSocketUrl(jobId, token));

    websocket.onmessage = async (event) => {
      try {
        const next = JSON.parse(event.data) as FetchJobStatusResponse;
        if (cancelled) return;
        setActiveJob(next);
        setJobs((current) => {
          const nextJobs = [...current];
          const existingIndex = nextJobs.findIndex((job) => job.job_id === next.job_id);
          if (existingIndex >= 0) {
            nextJobs[existingIndex] = next;
          } else {
            nextJobs.unshift(next);
          }
          return nextJobs.slice(0, 8);
        });

        if (next.status === "completed") {
          setNotice("Fetch completed successfully.");
          if (selectedSymbolId === String(next.symbol_id) && timeframe === next.timeframe) {
            await loadCoverage(token, next.symbol_id, next.timeframe);
          }
        } else if (next.status === "failed") {
          setError(next.error_message ?? "Fetch failed.");
        }
      } catch {
        if (!cancelled) {
          setError("Received an invalid progress update.");
        }
      }
    };

    websocket.onerror = () => {
      if (!cancelled) {
        setError("Live progress connection failed. Refresh the page and try again.");
      }
    };

    websocket.onclose = async () => {
      if (cancelled || closedIntentionally) return;
      try {
        const latest = await marketDataApi.getFetchJob(token, jobId);
        if (cancelled) return;
        setActiveJob(latest);
        await loadRecentJobs(token);
        if (latest.status === "completed") {
          setNotice("Fetch completed successfully.");
          if (selectedSymbolId === String(latest.symbol_id) && timeframe === latest.timeframe) {
            await loadCoverage(token, latest.symbol_id, latest.timeframe);
          }
        } else if (latest.status === "failed") {
          setError(latest.error_message ?? "Fetch failed.");
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to refresh fetch status.");
        }
      }
    };

    return () => {
      cancelled = true;
      closedIntentionally = true;
      websocket.close();
    };
  }, [activeJob, selectedSymbolId, timeframe]);

  async function handleFetchSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const token = getToken();
    if (!token) {
      setError("Please log in to fetch market data.");
      return;
    }
    if (!selectedSymbolId) {
      setError("Please choose a symbol.");
      return;
    }
    if (!startDate || !endDate) {
      setError("Please choose both a start and end date.");
      return;
    }

    const startIso = toUTCISOString(startDate);
    const endIso = toUTCISOString(endDate);
    if (new Date(startIso) >= new Date(endIso)) {
      setError("End date must be after start date.");
      return;
    }

    setSubmitting(true);
    setError(null);
    setNotice(null);

    try {
      const created = await marketDataApi.fetch(token, {
        symbol_id: Number(selectedSymbolId),
        timeframe,
        start_date: startIso,
        end_date: endIso,
      });

      setActiveJob({
        ...created,
        total_chunks: 0,
        completed_chunks: 0,
        candles_fetched: 0,
        progress_pct: 0,
        error_message: null,
        started_at: null,
        completed_at: null,
      });
      setNotice("Fetch job started. Progress will update automatically.");
      await loadRecentJobs(token);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start fetch job.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen bg-background">
      <header className="border-b border-border px-6 py-4">
        <Link href="/" className="text-muted-foreground hover:text-foreground text-sm">
          ← Dashboard
        </Link>
        <h1 className="text-xl font-semibold tracking-tight mt-2">Market data</h1>
      </header>
      <main className="container mx-auto max-w-5xl px-6 py-8">
        {error && (
          <Card className="mb-6 border-destructive/50">
            <CardHeader className="pb-2">
              <CardTitle className="text-base text-destructive">Something went wrong</CardTitle>
              <CardDescription>{error}</CardDescription>
            </CardHeader>
          </Card>
        )}

        {notice && (
          <Card className="mb-6 border-emerald-500/30">
            <CardHeader className="pb-2">
              <CardTitle className="text-base text-emerald-700 dark:text-emerald-400">
                Status
              </CardTitle>
              <CardDescription>{notice}</CardDescription>
            </CardHeader>
          </Card>
        )}

        <Card>
          <CardHeader>
            <CardTitle>Fetch historical candles</CardTitle>
            <CardDescription>
              Choose a symbol, timeframe, and date range. The backend fetches candles in
              the background and stores them idempotently.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form className="space-y-5" onSubmit={handleFetchSubmit}>
              <div className="grid gap-5 md:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="symbol">Symbol</Label>
                  <select
                    id="symbol"
                    className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-xs outline-none focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px] disabled:cursor-not-allowed disabled:opacity-50"
                    value={selectedSymbolId}
                    onChange={(event) => setSelectedSymbolId(event.target.value)}
                    disabled={symbolsLoading || symbols.length === 0}
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
                  <Label htmlFor="start-date">Start date</Label>
                  <Input
                    id="start-date"
                    type="datetime-local"
                    value={startDate}
                    onChange={(event) => setStartDate(event.target.value)}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="end-date">End date</Label>
                  <Input
                    id="end-date"
                    type="datetime-local"
                    value={endDate}
                    onChange={(event) => setEndDate(event.target.value)}
                  />
                </div>
              </div>

              <div className="flex flex-wrap gap-3">
                <Button type="submit" disabled={submitting || symbolsLoading || !selectedSymbolId}>
                  {submitting ? "Starting…" : "Fetch market data"}
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => {
                    const now = new Date();
                    const start = new Date(now);
                    start.setDate(start.getDate() - 30);
                    setStartDate(toDateTimeLocalValue(start));
                    setEndDate(toDateTimeLocalValue(now));
                  }}
                >
                  Reset to last 30 days
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>

        <Card className="mt-6">
          <CardHeader>
            <CardTitle>Coverage for selected symbol</CardTitle>
            <CardDescription>
              Coverage comes from the Phase 13.2 backend endpoint and shows the candle
              range already stored for the selected symbol and timeframe.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {coverageLoading ? (
              <p className="text-sm text-muted-foreground">Loading coverage…</p>
            ) : coverage.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                No candles found yet for {selectedSymbol?.symbol ?? "this symbol"} at {timeframe}.
              </p>
            ) : (
              <div className="grid gap-4 md:grid-cols-3">
                {coverage.map((row) => (
                  <div key={`${row.symbol_id}-${row.timeframe}`} className="rounded-lg border p-4">
                    <p className="text-sm font-medium">
                      {selectedSymbol?.symbol ?? row.symbol_id} · {row.timeframe}
                    </p>
                    <p className="mt-2 text-sm text-muted-foreground">
                      Start: {formatDateTime(row.start_date)}
                    </p>
                    <p className="text-sm text-muted-foreground">
                      End: {formatDateTime(row.end_date)}
                    </p>
                    <p className="mt-2 text-sm text-muted-foreground">
                      Candles: {formatNumber(row.candle_count)}
                    </p>
                    <p className="text-xs text-muted-foreground mt-2">
                      {formatDateOnly(row.start_date)} to {formatDateOnly(row.end_date)}
                    </p>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Phase 17.4 — sentiment panel for the currently selected symbol */}
        {selectedSymbol && (
          <div className="mt-6">
            <SentimentPanel
              token={token}
              symbol={selectedSymbol.symbol}
              symbolId={selectedSymbol.id}
              showRefresh
              description={`Recent news sentiment for ${selectedSymbol.symbol}. Use "Refresh news" to enqueue a fresh fetch from the Phase 17.1 pipeline.`}
            />
          </div>
        )}

        <Card className="mt-6">
          <CardHeader>
            <CardTitle>Active fetch job</CardTitle>
            <CardDescription>
              Live progress updates stream over WebSocket while the fetch job runs.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {!activeJob ? (
              <p className="text-sm text-muted-foreground">
                Start a fetch job to see live status here.
              </p>
            ) : (
              <div className="space-y-4">
                <div className="flex flex-wrap items-center gap-3">
                  <StatusBadge status={activeJob.status} />
                  <span className="text-sm text-muted-foreground">
                    Job {activeJob.job_id.slice(0, 8)}…
                  </span>
                  <span className="text-sm text-muted-foreground">
                    {activeJob.timeframe} · {activeJob.symbol_id}
                  </span>
                </div>
                <div className="space-y-2">
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-muted-foreground">Progress</span>
                    <span>{activeJob.progress_pct.toFixed(1)}%</span>
                  </div>
                  <div className="h-2 overflow-hidden rounded-full bg-muted">
                    <div
                      className="h-full bg-primary transition-all"
                      style={{ width: `${Math.max(0, Math.min(100, activeJob.progress_pct))}%` }}
                    />
                  </div>
                </div>
                <div className="grid gap-3 md:grid-cols-2">
                  <div className="rounded-lg border p-3 text-sm">
                    <p className="text-muted-foreground">Chunks</p>
                    <p className="font-medium">
                      {activeJob.completed_chunks} / {activeJob.total_chunks || "—"}
                    </p>
                  </div>
                  <div className="rounded-lg border p-3 text-sm">
                    <p className="text-muted-foreground">Candles fetched</p>
                    <p className="font-medium">{formatNumber(activeJob.candles_fetched)}</p>
                  </div>
                  <div className="rounded-lg border p-3 text-sm">
                    <p className="text-muted-foreground">Started</p>
                    <p className="font-medium">{formatDateTime(activeJob.started_at ?? activeJob.created_at)}</p>
                  </div>
                  <div className="rounded-lg border p-3 text-sm">
                    <p className="text-muted-foreground">Completed</p>
                    <p className="font-medium">{formatDateTime(activeJob.completed_at)}</p>
                  </div>
                </div>
                {activeJob.error_message && (
                  <p className="text-sm text-destructive">{activeJob.error_message}</p>
                )}
              </div>
            )}
          </CardContent>
        </Card>

        <Card className="mt-6">
          <CardHeader>
            <CardTitle>Recent fetch jobs</CardTitle>
            <CardDescription>
              Most recent market-data fetch jobs for the current user.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {jobsLoading ? (
              <p className="text-sm text-muted-foreground">Loading jobs…</p>
            ) : jobs.length === 0 ? (
              <p className="text-sm text-muted-foreground">No fetch jobs yet.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border">
                      <th className="px-2 py-3 text-left font-medium">Job</th>
                      <th className="px-2 py-3 text-left font-medium">Status</th>
                      <th className="px-2 py-3 text-left font-medium">Symbol</th>
                      <th className="px-2 py-3 text-left font-medium">Timeframe</th>
                      <th className="px-2 py-3 text-left font-medium">Range</th>
                      <th className="px-2 py-3 text-right font-medium">Progress</th>
                    </tr>
                  </thead>
                  <tbody>
                    {jobs.map((job) => {
                      const symbol = symbols.find((item) => item.id === job.symbol_id);
                      return (
                        <tr key={job.job_id} className="border-b border-border/70">
                          <td className="px-2 py-3 text-muted-foreground">{job.job_id.slice(0, 8)}…</td>
                          <td className="px-2 py-3">
                            <StatusBadge status={job.status} />
                          </td>
                          <td className="px-2 py-3 text-muted-foreground">
                            {symbol?.symbol ?? job.symbol_id}
                          </td>
                          <td className="px-2 py-3 text-muted-foreground">{job.timeframe}</td>
                          <td className="px-2 py-3 text-muted-foreground">
                            {formatDateOnly(job.start_date)} to {formatDateOnly(job.end_date)}
                          </td>
                          <td className="px-2 py-3 text-right tabular-nums">
                            {job.progress_pct.toFixed(1)}%
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>
        {/* Regime model training */}
        <Card className="mt-6">
          <CardHeader>
            <CardTitle>Regime model training</CardTitle>
            <CardDescription>
              Train an ML model to classify market regimes (trend, range, high volatility)
              for the selected symbol and timeframe. Existing models are listed below.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-5">
            <div className="flex flex-wrap items-end gap-4">
              <div className="space-y-1">
                <Label className="text-xs text-muted-foreground">Symbol</Label>
                <p className="text-sm font-medium">{selectedSymbol?.symbol ?? "—"}</p>
              </div>
              <div className="space-y-1">
                <Label className="text-xs text-muted-foreground">Timeframe</Label>
                <p className="text-sm font-medium">{timeframe}</p>
              </div>
              <label className="flex items-center gap-2 text-sm cursor-pointer">
                <input
                  type="checkbox"
                  checked={trainTune}
                  onChange={(e) => setTrainTune(e.target.checked)}
                  className="rounded border-input"
                  disabled={!!trainTaskId}
                />
                Hyperparameter tuning
              </label>
              <Button
                disabled={trainSubmitting || !!trainTaskId || !selectedSymbolId}
                onClick={async () => {
                  const token = getToken();
                  if (!token || !selectedSymbolId) return;
                  setTrainSubmitting(true);
                  setError(null);
                  setNotice(null);
                  setTrainResult(null);
                  try {
                    const res = await regimesApi.train(token, {
                      symbol_id: Number(selectedSymbolId),
                      timeframe,
                      tune: trainTune,
                    });
                    startPolling(res.task_id);
                  } catch (err) {
                    setError(
                      err instanceof Error ? err.message : "Failed to start training.",
                    );
                  } finally {
                    setTrainSubmitting(false);
                  }
                }}
              >
                {trainSubmitting ? "Starting…" : "Train regime model"}
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={modelsLoading || !selectedSymbolId}
                onClick={async () => {
                  const token = getToken();
                  if (token && selectedSymbolId) {
                    await loadModels(token, Number(selectedSymbolId), timeframe);
                  }
                }}
              >
                {modelsLoading ? "Loading…" : "Refresh models"}
              </Button>
            </div>

            {trainTaskId && trainState && (
              <div className="rounded-lg border border-blue-500/30 bg-blue-500/10 px-4 py-3 space-y-3">
                <div className="flex items-center gap-3">
                  <svg className="h-4 w-4 animate-spin text-blue-500 shrink-0" viewBox="0 0 24 24" fill="none">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                  <p className="text-sm text-blue-700 dark:text-blue-400">
                    {trainPhase ?? "Training in progress…"}
                  </p>
                  {trainProgressPct != null && (
                    <span className="ml-auto text-sm font-medium tabular-nums text-blue-700 dark:text-blue-400">
                      {trainProgressPct}%
                    </span>
                  )}
                </div>
                <Progress value={trainProgressPct ?? 0} className="h-2" />
              </div>
            )}

            {trainResult && !trainResult.error && (
              <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-4 py-3">
                <p className="text-sm text-emerald-700 dark:text-emerald-400">
                  Training complete!
                  {trainResult.accuracy != null && (
                    <span className="ml-2">
                      Accuracy: <span className="font-semibold tabular-nums">{(trainResult.accuracy * 100).toFixed(1)}%</span>
                    </span>
                  )}
                  {trainResult.model_id != null && (
                    <span className="ml-2 text-xs opacity-70">(Model #{trainResult.model_id})</span>
                  )}
                </p>
              </div>
            )}

            {trainResult?.error && (
              <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3">
                <p className="text-sm text-destructive">
                  Training failed: {trainResult.error}
                </p>
              </div>
            )}

            {modelsLoading ? (
              <p className="text-sm text-muted-foreground">Loading models…</p>
            ) : models.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                No trained models yet for {selectedSymbol?.symbol ?? "this symbol"} at {timeframe}.
                Train one above to enable regime analysis on your backtests.
              </p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border">
                      <th className="px-2 py-3 text-left font-medium">ID</th>
                      <th className="px-2 py-3 text-left font-medium">Name</th>
                      <th className="px-2 py-3 text-right font-medium">Accuracy</th>
                      <th className="px-2 py-3 text-right font-medium">Train / Test</th>
                      <th className="px-2 py-3 text-left font-medium">Tuned</th>
                      <th className="px-2 py-3 text-left font-medium">Created</th>
                    </tr>
                  </thead>
                  <tbody>
                    {models.map((m) => (
                      <tr key={m.id} className="border-b border-border/70">
                        <td className="px-2 py-3 tabular-nums text-muted-foreground">
                          #{m.id}
                        </td>
                        <td className="px-2 py-3 font-medium">{m.name}</td>
                        <td className="px-2 py-3 text-right tabular-nums">
                          {m.accuracy != null ? `${(m.accuracy * 100).toFixed(1)}%` : "—"}
                        </td>
                        <td className="px-2 py-3 text-right tabular-nums text-muted-foreground">
                          {m.n_train != null && m.n_test != null
                            ? `${m.n_train.toLocaleString()} / ${m.n_test.toLocaleString()}`
                            : "—"}
                        </td>
                        <td className="px-2 py-3">
                          {m.tuned ? (
                            <span className="inline-flex items-center rounded-md bg-emerald-500/15 text-emerald-700 dark:text-emerald-400 px-2 py-0.5 text-xs font-medium">
                              Yes
                            </span>
                          ) : (
                            <span className="inline-flex items-center rounded-md bg-muted text-muted-foreground px-2 py-0.5 text-xs font-medium">
                              No
                            </span>
                          )}
                        </td>
                        <td className="px-2 py-3 text-muted-foreground">
                          {formatDateTime(m.created_at)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>
      </main>
    </div>
  );
}

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
import {
  backtestsApi,
  strategiesApi,
  symbolsApi,
  type BacktestRunListItem,
} from "@/lib/api/endpoints";
import { getToken } from "@/lib/auth";

export default function Home() {
  const [symbolsCount, setSymbolsCount] = useState<number | null>(null);
  const [strategiesCount, setStrategiesCount] = useState<number | null>(null);
  const [runs, setRuns] = useState<BacktestRunListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  function fetchData() {
    setLoading(true);
    setError(null);
    const token = getToken();
    Promise.all([
      symbolsApi.list().then((s) => s.length),
      token ? strategiesApi.list(token).then((s) => s.length) : Promise.resolve(0),
      token ? backtestsApi.list(token) : Promise.resolve([]),
    ])
      .then(([sCount, stCount, runList]) => {
        setSymbolsCount(sCount);
        setStrategiesCount(stCount);
        setRuns(runList);
      })
      .catch((err) => {
        const msg = err instanceof Error ? err.message : "Failed to load";
        setError(msg === "Not authenticated" ? "Please log in again." : msg);
      })
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    fetchData();
  }, []);

  useEffect(() => {
    const handler = () => fetchData();
    window.addEventListener("tradecore:auth", handler);
    return () => window.removeEventListener("tradecore:auth", handler);
  }, []);

  return (
    <div className="min-h-screen bg-background">
      <main className="container mx-auto max-w-5xl px-6 py-8">
        <div className="mb-8">
          <h2 className="text-2xl font-semibold">Dashboard</h2>
          <p className="text-muted-foreground">Overview and quick actions</p>
        </div>
        {error && (
          <p className="mb-4 text-sm text-destructive">{error}</p>
        )}
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                Total runs
              </CardTitle>
            </CardHeader>
            <CardContent>
              <span className="text-2xl font-bold">
                {loading ? "—" : runs.length}
              </span>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                Strategies
              </CardTitle>
            </CardHeader>
            <CardContent>
              <span className="text-2xl font-bold">
                {loading ? "—" : strategiesCount ?? "—"}
              </span>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                Symbols
              </CardTitle>
            </CardHeader>
            <CardContent>
              <span className="text-2xl font-bold">
                {loading ? "—" : symbolsCount ?? "—"}
              </span>
            </CardContent>
          </Card>
        </div>
        <div className="mt-8 grid gap-4 md:grid-cols-2">
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                Quick actions
              </CardTitle>
            </CardHeader>
            <CardContent className="flex gap-2 flex-wrap">
              <Link
                href="/backtests"
                className="text-sm font-medium text-primary underline-offset-4 hover:underline"
              >
                New backtest
              </Link>
              <span className="text-muted-foreground">·</span>
              <Link
                href="/strategies"
                className="text-sm font-medium text-primary underline-offset-4 hover:underline"
              >
                New strategy
              </Link>
              <span className="text-muted-foreground">·</span>
              <Link
                href="/market-data"
                className="text-sm font-medium text-primary underline-offset-4 hover:underline"
              >
                Load market data
              </Link>
            </CardContent>
          </Card>
        </div>
        <div className="mt-8">
          <Card>
            <CardHeader>
              <CardTitle>Recent runs</CardTitle>
              <CardDescription>Your latest backtest runs</CardDescription>
            </CardHeader>
            <CardContent>
              {loading ? (
                <p className="text-sm text-muted-foreground">Loading…</p>
              ) : runs.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  No runs yet. Create a backtest to get started.
                </p>
              ) : (
                <ul className="space-y-2">
                  {runs.slice(0, 10).map((run) => (
                    <li key={run.id} className="flex items-center justify-between text-sm">
                      <Link
                        href={`/runs/${run.id}`}
                        className="text-primary underline-offset-4 hover:underline"
                      >
                        {run.id.slice(0, 8)}…
                      </Link>
                      <span className="text-muted-foreground">
                        {run.timeframe} · {run.status}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
        </div>
      </main>
    </div>
  );
}

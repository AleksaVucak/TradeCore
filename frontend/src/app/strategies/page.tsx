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
import { strategiesApi, type StrategyListItem } from "@/lib/api/endpoints";
import { getToken } from "@/lib/auth";

export default function StrategiesPage() {
  const [strategies, setStrategies] = useState<StrategyListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const token = getToken();
    if (!token) {
      queueMicrotask(() => {
        setError("Please log in to view strategies.");
        setLoading(false);
      });
      return;
    }
    setLoading(true);
    setError(null);
    strategiesApi
      .list(token)
      .then((items) => {
        setStrategies(items);
      })
      .catch((err) => {
        const msg = err instanceof Error ? err.message : "Failed to load strategies.";
        setError(msg === "Not authenticated" ? "Please log in again." : msg);
      })
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="min-h-screen bg-background">
      <header className="border-b border-border px-6 py-4">
        <Link href="/" className="text-muted-foreground hover:text-foreground text-sm">
          ← Dashboard
        </Link>
        <h1 className="text-xl font-semibold tracking-tight mt-2">Strategies</h1>
      </header>
      <main className="container mx-auto max-w-5xl px-6 py-8 space-y-6">
        <div className="flex items-center justify-between gap-4">
          <div>
            <p className="text-sm text-muted-foreground">
              Your saved trading strategies. Create a new strategy to use in backtests later.
            </p>
          </div>
          <Link
            href="/strategies/new"
            className="text-sm font-medium text-primary underline-offset-4 hover:underline"
          >
            New strategy
          </Link>
        </div>

        {error && (
          <Card className="border-destructive/50">
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

        <Card>
          <CardHeader>
            <CardTitle>Strategies</CardTitle>
            <CardDescription>
              {loading
                ? "Loading…"
                : strategies.length === 0
                ? "No strategies yet. Create your first strategy to get started."
                : `${strategies.length} strateg${strategies.length === 1 ? "y" : "ies"} found.`}
            </CardDescription>
          </CardHeader>
          <CardContent>
            {loading ? (
              <div className="space-y-3">
                {Array.from({ length: 3 }).map((_, i) => (
                  <div key={i} className="flex items-center gap-4">
                    <Skeleton className="h-4 w-32" />
                    <Skeleton className="h-5 w-16 rounded-md" />
                    <Skeleton className="h-4 w-28 hidden sm:block" />
                    <Skeleton className="h-4 w-20 ml-auto" />
                  </div>
                ))}
              </div>
            ) : strategies.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                No strategies found. Create a strategy to see it listed here.
              </p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="border-b border-border text-xs uppercase text-muted-foreground">
                    <tr>
                      <th className="py-2 text-left font-medium">Name</th>
                      <th className="py-2 text-left font-medium">Type</th>
                      <th className="py-2 text-left font-medium hidden sm:table-cell">Created</th>
                      <th className="py-2 text-right font-medium">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {strategies.map((s) => (
                      <tr
                        key={s.id}
                        className="border-b border-border last:border-0 hover:bg-accent/40"
                      >
                        <td className="py-2 pr-4 align-middle">
                          <span className="font-medium">{s.name}</span>
                        </td>
                        <td className="py-2 pr-4 align-middle">
                          <span className="rounded bg-muted px-2 py-0.5 text-xs uppercase tracking-wide">
                            {s.strategy_type}
                          </span>
                        </td>
                        <td className="py-2 pr-4 align-middle text-muted-foreground hidden sm:table-cell">
                          {new Date(s.created_at).toLocaleString()}
                        </td>
                        <td className="py-2 pl-4 align-middle text-right">
                          <Link
                            href={`/strategies/${s.id}`}
                            className="text-xs font-medium text-primary underline-offset-4 hover:underline"
                          >
                            View details
                          </Link>
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
